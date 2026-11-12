"""Spending limit for the LLM calls of one analysis (or one eligibility check).

``BudgetedLLM`` wraps any ``LLMProvider``. Before each call it reserves the
worst-case cost of that call (estimated input plus the maximum output) and
refuses the call if the reservations and what was already spent would pass the
limit. After the call, the reservation is replaced by the actual cost. Calls run
concurrently, so reserving first is what keeps parallel calls from passing the
limit together.

A refused call raises ``BudgetExceededError``, an ``LLMError``: the pipeline
treats it like any failed call (the group is reported as not extracted), so the
analysis keeps whatever was extracted within the budget.
"""

import math
import threading

from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider, LLMResult
from app.llm.pricing import estimate_cost_usd, model_prices

# Portuguese text averages about 3.5-4 characters per token; 3 overestimates the
# input on purpose, so the reservation errs on the safe side.
CHARS_PER_TOKEN_ESTIMATE = 3


class BudgetExceededError(LLMError):
    """The call would pass the spending limit, so it was not sent."""


class BudgetedLLM:
    def __init__(self, inner: LLMProvider, limit_usd: float, max_output_tokens: int) -> None:
        self.inner = inner
        self.name = inner.name
        self.model = inner.model
        self.limit_usd = limit_usd
        self.max_output_tokens = max_output_tokens
        self.spent_usd = 0.0
        self._reserved_usd = 0.0
        self._lock = threading.Lock()

    def worst_case_cost(self, system: str, user: str) -> float | None:
        input_tokens = math.ceil((len(system) + len(user)) / CHARS_PER_TOKEN_ESTIMATE)
        return estimate_cost_usd(self.model, input_tokens, self.max_output_tokens)

    def extract[T: BaseModel](self, *, system: str, user: str, schema: type[T]) -> LLMResult[T]:
        if self.limit_usd <= 0:  # no limit configured
            return self._call(system, user, schema)
        if model_prices(self.model) is None:
            # Without a price the cost cannot be bounded: refuse instead of guessing.
            raise BudgetExceededError(
                f"o modelo {self.model} não tem preço cadastrado, então o limite de gasto não "
                "pode ser garantido (veja app/llm/pricing.py)"
            )
        reservation = self.worst_case_cost(system, user) or 0.0
        with self._lock:
            if self.spent_usd + self._reserved_usd + reservation > self.limit_usd:
                raise BudgetExceededError(
                    f"limite de gasto de US$ {self.limit_usd:.2f} por análise atingido "
                    f"(gasto até aqui: US$ {self.spent_usd:.2f})"
                )
            self._reserved_usd += reservation
        try:
            result = self._call(system, user, schema)
        finally:
            with self._lock:
                self._reserved_usd -= reservation
        return result

    def _call[T: BaseModel](self, system: str, user: str, schema: type[T]) -> LLMResult[T]:
        result = self.inner.extract(system=system, user=user, schema=schema)
        cost = estimate_cost_usd(result.model, result.input_tokens, result.output_tokens)
        with self._lock:
            self.spent_usd += cost or 0.0
        return result
