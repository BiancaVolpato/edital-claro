"""Cost estimation from token usage.

Prices are USD per million tokens (input, output), standard tier, from the
public price lists of Anthropic (as of 2026-11-03) and OpenAI (as of
2026-11-12; short-context prices). They are an estimate for display and
budgeting, not a billing record: update the table when prices change.
"""

PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    # OpenAI
    "gpt-6-astra": (10.00, 50.00),
    "gpt-6.1-sol": (2.00, 10.00),
    "gpt-6.1-terra": (1.00, 5.00),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6-sol": (2.00, 10.00),
    "gpt-5.6-sol": (4.00, 20.00),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.5-pro": (30.00, 180.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-pro": (30.00, 180.00),
}


def model_prices(model: str) -> tuple[float, float] | None:
    """Prices of ``model``, also when the API names a dated snapshot of it.

    A response may name the exact snapshot that served it (e.g. a model id
    followed by a date); it is priced as the longest listed id it extends.
    """
    if model in PRICES_USD_PER_MTOK:
        return PRICES_USD_PER_MTOK[model]
    prefixes = [name for name in PRICES_USD_PER_MTOK if model.startswith(f"{name}-")]
    return PRICES_USD_PER_MTOK[max(prefixes, key=len)] if prefixes else None


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated cost of one call, or None when the model's price is unknown."""
    prices = model_prices(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)
