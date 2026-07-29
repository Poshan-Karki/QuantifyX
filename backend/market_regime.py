
import pandas as pd
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.momentum import RSIIndicator


REGIME_STRATEGY_MAP = {
    "Trending Up": [
        "Moving Average Crossover",
        "MACD Cross",
        "ATR Breakout",
        "VolumeBreakout"
    ],
    "Trending Down": [
        "Moving Average Crossover",  # can be reverse for downtrend
        "MACD Cross",               # for short term bearish moves
        "Mean Reversion",           # bounce plays in down moves
        "Bollinger Band"            # Might fade extreme lows
    ],
    "High Volatility": [
        "ATR Breakout",
        "MACD Cross",
        "VolumeBreakout",
        "Bollinger Band",
        "Bollinger+Rsi"
    ],
    "Low Volatility": [
        "Mean Reversion",
        "Bollinger+Rsi",
        "RSI Mean Reversion"
    ],
    "Ranging/Sideways": [
        "Mean Reversion",
        "Bollinger+Rsi",
        "RSI Mean Reversion"
    ]
}

STRATEGY_DESCRIPTIONS = {
    "Bollinger Band":            "Buy when price touches lower band; sell at midline. Works well in volatile, mean-reverting markets.",
    "Moving Average Crossover":  "Long when fast MA crosses above slow MA. Best in clean, sustained trends.",
    "Mean Reversion":            "Trade z-score extremes back toward the mean. Ideal in range-bound, low-noise markets.",
    "Bollinger+Rsi":             "Combines Bollinger oversold + RSI confirmation for higher-quality entries.",
    "VolumeBreakout":            "Buys volume-confirmed breakdowns below the lower band. Good in high-volume trending moves.",
    "MACD Cross": "Trades MACD signal-line crossovers. Performs well during sustained trends.",
    "RSI Mean Reversion": "Buys oversold RSI and exits when RSI becomes overbought. Best in sideways markets.",
    "ATR Breakout": "Buys breakouts above recent highs with ATR-based risk management. Best during strong breakouts."
}


def detect_regime(df: pd.DataFrame) -> dict:
    """
    df must have columns: Open, High, Low, Close, Volume
    and a DatetimeIndex.
    Returns a dict with regime label, confidence, indicators, and strategy recommendations.
    """
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    # --- ADX (trend strength) ---
    adx_ind = ADXIndicator(high=high, low=low, close=close, window=14)
    adx     = adx_ind.adx().iloc[-1]
    adx_pos = adx_ind.adx_pos().iloc[-1]   # +DI
    adx_neg = adx_ind.adx_neg().iloc[-1]   # -DI

    # --- Volatility: ATR relative to price ---
    atr_ind = AverageTrueRange(high=high, low=low, close=close, window=14)
    atr     = atr_ind.average_true_range().iloc[-1]
    atr_pct = (atr / close.iloc[-1]) * 100     # ATR as % of price

    # --- Bollinger Band width (normalised squeeze measure) ---
    bb = BollingerBands(close=close, window=20, window_dev=2)
    bb_width    = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg()
    bb_width_now = bb_width.iloc[-1]
    bb_width_avg = bb_width.iloc[-30:].mean()

    # --- Short-term price direction (50-day EMA slope) ---
    ema50 = EMAIndicator(close=close, window=50).ema_indicator()
    ema_slope = (ema50.iloc[-1] - ema50.iloc[-10]) / ema50.iloc[-10] * 100

    # --- RSI ---
    rsi = RSIIndicator(close=close, window=14).rsi().iloc[-1]

    # ---- Regime classification ----
    is_trending     = adx > 25
    trend_is_up     = adx_pos > adx_neg and ema_slope > 0
    high_volatility = atr_pct > 2.5 or bb_width_now > bb_width_avg * 1.3
    squeeze         = bb_width_now < bb_width_avg * 0.7

    if is_trending and trend_is_up:
        regime = "Trending Up"
        confidence = min(100, int((adx / 50) * 100))
    elif is_trending and not trend_is_up:
        regime = "Trending Down"
        confidence = min(100, int((adx / 50) * 100))
    elif high_volatility:
        regime = "High Volatility"
        confidence = min(100, int(((atr_pct - 1.5) / 3) * 100))
    elif squeeze:
        regime = "Low Volatility"
        confidence = min(100, int(((bb_width_avg - bb_width_now) / bb_width_avg) * 100))
    else:
        regime = "Ranging/Sideways"
        confidence = 60

    # Clamp confidence
    confidence = max(30, min(100, confidence))

    recommended = REGIME_STRATEGY_MAP[regime]

    return {
        "regime": regime,
        "confidence": confidence,
        "indicators": {
            "adx":            round(float(adx), 2),
            "adx_plus_di":    round(float(adx_pos), 2),
            "adx_minus_di":   round(float(adx_neg), 2),
            "atr_pct":        round(float(atr_pct), 2),
            "bb_width":       round(float(bb_width_now), 4),
            "bb_width_avg":   round(float(bb_width_avg), 4),
            "ema50_slope":    round(float(ema_slope), 3),
            "rsi":            round(float(rsi), 2),
        },
        "recommended_strategies": recommended,
        "strategy_descriptions": {s: STRATEGY_DESCRIPTIONS[s] for s in recommended},
        "reasoning": _build_reasoning(regime, adx, atr_pct, ema_slope, rsi),
    }


def _build_reasoning(regime, adx, atr_pct, ema_slope, rsi):
    lines = []
    if adx > 25:
        lines.append(f"ADX is {adx:.1f} (>25), confirming a strong trend.")
    else:
        lines.append(f"ADX is {adx:.1f} (<25), suggesting a non-trending, ranging market.")
    if atr_pct > 2.5:
        lines.append(f"ATR is {atr_pct:.1f}% of price — elevated volatility detected.")
    else:
        lines.append(f"ATR is {atr_pct:.1f}% of price — volatility is contained.")
    if ema_slope > 0:
        lines.append(f"50-EMA slope is positive ({ema_slope:.2f}%), price trending upward.")
    else:
        lines.append(f"50-EMA slope is negative ({ema_slope:.2f}%), price trending downward.")
    lines.append(f"RSI at {rsi:.1f} — {'overbought territory' if rsi > 70 else 'oversold territory' if rsi < 30 else 'neutral zone'}.")
    return " ".join(lines)
