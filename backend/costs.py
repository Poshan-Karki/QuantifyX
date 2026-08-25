
#: Round-trip cost defaults, in percent. These are the numbers the UI shows,
#: served by GET /defaults so the form cannot drift from the backend again.
DEFAULT_FEE_PCT = 0.2
DEFAULT_SLIPPAGE_PCT = 0.1
DEFAULT_MAX_POS_PCT = 20.0
DEFAULT_COOLDOWN_BARS = 3

#: Guards on user-supplied costs. A combined cost at or above 100% would make
#: backtesting.py's commission model meaningless.
MAX_TOTAL_COST_PCT = 50.0


def total_cost_pct(fee_pct: float, slippage_pct: float) -> float:
    """Combined one-way cost in percent, charged on entry and again on exit."""
    total = float(fee_pct) + float(slippage_pct)
    if total < 0:
        raise ValueError("Trading costs cannot be negative.")
    if total > MAX_TOTAL_COST_PCT:
        raise ValueError(
            f"Fee plus slippage is {total:.2f}%, above the {MAX_TOTAL_COST_PCT:.0f}% "
            "ceiling. Check the fee and slippage inputs."
        )
    return total


def commission_fraction(fee_pct: float, slippage_pct: float) -> float:
    """`total_cost_pct` as the 0-1 fraction backtesting.py's `commission` wants."""
    return total_cost_pct(fee_pct, slippage_pct) / 100.0


DEFAULT_TRADE_PARAMS = {
    "fee_pct": DEFAULT_FEE_PCT,
    "slippage_pct": DEFAULT_SLIPPAGE_PCT,
    "max_pos_pct": DEFAULT_MAX_POS_PCT,
    "cooldown_bars": DEFAULT_COOLDOWN_BARS,
}
