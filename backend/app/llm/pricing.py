"""Cost estimation from token usage.

Prices are USD per million tokens (input, output), from Anthropic's public
price list as of 2026-11-03. They are an estimate for display and budgeting,
not a billing record: update the table when prices change.
"""

PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated cost of one call, or None when the model's price is unknown."""
    prices = PRICES_USD_PER_MTOK.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)
