"""Comparison of an extraction with the golden set, and the aggregate metrics.

Rules (also in eval/ANOTACAO.md):

- dates, money, enums, booleans and structured values: exact match;
- free text (agency, object, number): similarity of the folded text, plus the
  same numbers for the edital number;
- deadlines without a date: similarity of the rule, with the same numbers;
- "the edital does not state it" (golden ``null``) is an answer too: returning
  a value there is counted as a hallucination.

Qualification requirements and annexes are lists: each extracted item is paired
with at most one golden item by text similarity (greedy, best pairs first), and
precision and recall are counted over the pairs.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel
from rapidfuzz import fuzz

from app.evaluation.golden import LIST_FIELDS, SCALAR_FIELDS, Golden, typed_value
from app.extraction.prompts import fold
from app.extraction.schemas import EditalExtraction, ExtractedField

TEXT_THRESHOLD = 80.0  # agency, number
OBJECT_THRESHOLD = 70.0  # a one-sentence summary varies more in wording
RULE_THRESHOLD = 60.0  # deadline rules are paraphrased often
ITEM_THRESHOLD = 70.0  # requirement items

Outcome = Literal["correct", "wrong", "missed", "hallucinated"]
FIELD_GROUPS: dict[str, list[str]] = {
    "identificação": [
        "number",
        "modality",
        "agency",
        "object",
        "estimated_value",
        "judgment_criterion",
        "execution_regime",
    ],
    "datas e prazos": [
        "publication_date",
        "opening",
        "impugnation_deadline",
        "clarification_deadline",
        "execution_period",
    ],
    "garantias e participação": [
        "bid_guarantee",
        "contract_guarantee",
        "site_visit",
        "consortium_allowed",
        "me_epp_exclusive",
    ],
}


def similarity(a: str, b: str) -> float:
    return float(fuzz.token_set_ratio(fold(a), fold(b)))


def _numbers(text: str) -> set[str]:
    return {n.lstrip("0") or "0" for n in re.findall(r"\d+", text)}


def _plain(value: Any) -> Any:
    return value.model_dump() if isinstance(value, BaseModel) else value


def values_match(name: str, expected: Any, predicted: Any) -> tuple[bool, float | None]:
    """Whether a predicted value is right, with the text similarity when one was used."""
    expected, predicted = _plain(expected), _plain(predicted)
    if name in ("agency", "object", "number"):
        score = similarity(str(expected), str(predicted))
        threshold = OBJECT_THRESHOLD if name == "object" else TEXT_THRESHOLD
        ok = score >= threshold
        if name == "number":
            ok = ok and _numbers(str(expected)) <= _numbers(str(predicted))
        return ok, score
    if name == "estimated_value":
        return abs(float(expected) - float(predicted)) <= 0.01, None
    if name in ("impugnation_deadline", "clarification_deadline"):
        if expected.get("date"):
            return expected["date"] == predicted.get("date"), None
        rule, other = expected.get("rule") or "", predicted.get("rule") or ""
        score = similarity(rule, other)
        return score >= RULE_THRESHOLD and _numbers(rule) <= _numbers(other), score
    if name == "opening":
        same_time = expected.get("time") is None or expected["time"] == predicted.get("time")
        return expected["date"] == predicted.get("date") and same_time, None
    if name in ("bid_guarantee", "contract_guarantee"):
        if expected["required"] != predicted.get("required"):
            return False, None
        if expected.get("percent") is None:
            return True, None
        got = predicted.get("percent")
        return got is not None and abs(float(expected["percent"]) - float(got)) < 1e-6, None
    return expected == predicted, None


@dataclass(frozen=True)
class FieldScore:
    name: str
    outcome: Outcome
    expected: Any
    predicted: Any
    similarity: float | None
    needs_review: bool  # what the system said about its own answer
    citation_confirmed: bool  # at least one citation found in the document
    on_expected_page: bool | None  # a confirmed citation on a golden page (None: no pages)

    @property
    def correct(self) -> bool:
        return self.outcome == "correct"


def score_field(
    name: str, expected_raw: Any, pages: list[int], got: ExtractedField[Any]
) -> FieldScore:
    expected = typed_value(name, expected_raw)
    predicted = got.value
    confirmed = [c for c in got.citations if c.status in ("valid", "wrong_page")]
    sim: float | None = None
    outcome: Outcome
    if expected is None:
        outcome = "correct" if predicted is None else "hallucinated"
    elif predicted is None:
        outcome = "missed"
    else:
        ok, sim = values_match(name, expected, predicted)
        outcome = "correct" if ok else "wrong"
    on_page = None
    if predicted is not None and pages:
        on_page = any(c.page in pages for c in confirmed)
    return FieldScore(
        name=name,
        outcome=outcome,
        expected=_plain(expected),
        predicted=_plain(predicted),
        similarity=sim,
        needs_review=got.needs_review,
        citation_confirmed=bool(confirmed),
        on_expected_page=on_page,
    )


@dataclass(frozen=True)
class ListScore:
    name: str
    expected: list[str]
    predicted: list[str]
    pairs: list[tuple[str, str, float]]  # (golden, extracted, similarity)

    @property
    def true_positives(self) -> int:
        return len(self.pairs)

    @property
    def missed(self) -> list[str]:
        paired = {g for g, _, _ in self.pairs}
        return [item for item in self.expected if item not in paired]

    @property
    def extra(self) -> list[str]:
        paired = {p for _, p, _ in self.pairs}
        return [item for item in self.predicted if item not in paired]


def match_items(expected: list[str], predicted: list[str]) -> list[tuple[str, str, float]]:
    """Pair each golden item with at most one extracted item, best similarities first."""
    candidates = sorted(
        (
            (similarity(g, p), gi, pi)
            for gi, g in enumerate(expected)
            for pi, p in enumerate(predicted)
        ),
        reverse=True,
    )
    used_g: set[int] = set()
    used_p: set[int] = set()
    pairs: list[tuple[str, str, float]] = []
    for score, gi, pi in candidates:
        if score < ITEM_THRESHOLD:
            break
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        pairs.append((expected[gi], predicted[pi], score))
    return pairs


@dataclass
class EditalScore:
    name: str
    fields: list[FieldScore]
    lists: list[ListScore]
    citation_counts: dict[str, int]
    cost_usd: float | None
    latency_s: float
    failed_calls: list[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return sum(f.correct for f in self.fields) / len(self.fields)


def score_edital(
    name: str,
    golden: Golden,
    extraction: EditalExtraction,
    citation_counts: dict[str, int],
    cost_usd: float | None,
    latency_s: float,
    failed_calls: list[str] | None = None,
) -> EditalScore:
    fields = [
        score_field(n, golden.fields[n].value, golden.fields[n].pages, getattr(extraction, n))
        for n in SCALAR_FIELDS
    ]
    lists = []
    for n in LIST_FIELDS:
        expected = golden.requirements.get(n, [])
        predicted = [item.value for item in getattr(extraction, n) if item.value]
        lists.append(ListScore(n, expected, predicted, match_items(expected, predicted)))
    return EditalScore(
        name=name,
        fields=fields,
        lists=lists,
        citation_counts=citation_counts,
        cost_usd=cost_usd,
        latency_s=latency_s,
        failed_calls=failed_calls or [],
    )


# --- Aggregates -------------------------------------------------------------------


@dataclass(frozen=True)
class PrecisionRecall:
    true_positives: int
    predicted: int
    expected: int

    @property
    def precision(self) -> float | None:
        return self.true_positives / self.predicted if self.predicted else None

    @property
    def recall(self) -> float | None:
        return self.true_positives / self.expected if self.expected else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if not p or not r:
            return None if p is None or r is None else 0.0
        return 2 * p * r / (p + r)


@dataclass
class VariantSummary:
    variant: str
    editais: list[EditalScore]

    @property
    def field_scores(self) -> list[FieldScore]:
        return [f for e in self.editais for f in e.fields]

    def field_accuracy(self, name: str) -> float:
        scores = [f for f in self.field_scores if f.name == name]
        return sum(f.correct for f in scores) / len(scores)

    @property
    def accuracy(self) -> float:
        scores = self.field_scores
        return sum(f.correct for f in scores) / len(scores)

    def group_accuracy(self, group: str) -> float:
        scores = [f for f in self.field_scores if f.name in FIELD_GROUPS[group]]
        return sum(f.correct for f in scores) / len(scores)

    def list_score(self, names: list[str]) -> PrecisionRecall:
        lists = [item for e in self.editais for item in e.lists if item.name in names]
        return PrecisionRecall(
            true_positives=sum(item.true_positives for item in lists),
            predicted=sum(len(item.predicted) for item in lists),
            expected=sum(len(item.expected) for item in lists),
        )

    @property
    def requirements(self) -> PrecisionRecall:
        return self.list_score([n for n in LIST_FIELDS if n.startswith("qualification_")])

    @property
    def citation_valid_rate(self) -> float | None:
        totals: Counter[str] = Counter()
        for e in self.editais:
            totals.update(e.citation_counts)
        if not totals["total"]:
            return None
        return (totals["valid"] + totals["wrong_page"]) / totals["total"]

    @property
    def citation_page_rate(self) -> float | None:
        checked = [f.on_expected_page for f in self.field_scores if f.on_expected_page is not None]
        return sum(checked) / len(checked) if checked else None

    @property
    def mean_cost_usd(self) -> float | None:
        costs = [e.cost_usd for e in self.editais]
        if not costs or any(c is None for c in costs):
            return None
        return mean(c for c in costs if c is not None)

    @property
    def mean_latency_s(self) -> float:
        return mean(e.latency_s for e in self.editais) if self.editais else 0.0

    @property
    def outcomes(self) -> Counter[str]:
        return Counter(f.outcome for f in self.field_scores)

    @property
    def review_recall(self) -> float | None:
        """Share of the wrong answers (wrong value or hallucination) the system flagged."""
        errors = [f for f in self.field_scores if f.outcome in ("wrong", "hallucinated")]
        return sum(f.needs_review for f in errors) / len(errors) if errors else None

    @property
    def unconfirmed_correct(self) -> int:
        """Right values whose citation was not found in the document."""
        return sum(
            1
            for f in self.field_scores
            if f.correct and f.predicted is not None and not f.citation_confirmed
        )
