"""Per-bar rule-based regime labels for arm A2 (design section 4.1).

market_regime.detect_regime answers "what regime is the market in *now*", which
is all the API needs. The study needs a label on every bar of a training fold,
so the same classification is expressed here as a vectorised series.

The thresholds are copied from detect_regime deliberately rather than
refactored out of it -- the endpoint is live code and the study should not be
able to change it by accident. test_rule_regime.py asserts the two agree on the
final bar, which is what keeps this copy honest.
"""

from __future__ import annotations

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

TRENDING_UP = "Trending Up"
TRENDING_DOWN = "Trending Down"
HIGH_VOLATILITY = "High Volatility"
LOW_VOLATILITY = "Low Volatility"
RANGING = "Ranging/Sideways"

REGIMES = (TRENDING_UP, TRENDING_DOWN, HIGH_VOLATILITY, LOW_VOLATILITY, RANGING)

#: Longest lookback used below (the 50-bar EMA, read 10 bars back for its slope).
WARMUP_BARS = 60


def rule_regime_series(df: pd.DataFrame) -> pd.Series:
    """Label every bar of df, mirroring detect_regime's classification exactly.

    Returns a string Series indexed like df. Leading bars where the indicators
    have not warmed up are NaN.
    """
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    adx_ind = ADXIndicator(high=high, low=low, close=close, window=14)
    adx = adx_ind.adx()
    adx_pos = adx_ind.adx_pos()
    adx_neg = adx_ind.adx_neg()

    atr = AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
    atr_pct = (atr / close) * 100

    bb = BollingerBands(close=close, window=20, window_dev=2)
    bb_width = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg()
    # detect_regime compares against bb_width.iloc[-30:].mean(), i.e. the trailing
    # 30 values including the current one.
    bb_width_avg = bb_width.rolling(30, min_periods=30).mean()

    ema50 = EMAIndicator(close=close, window=50).ema_indicator()
    ema_slope = (ema50 - ema50.shift(10)) / ema50.shift(10) * 100

    is_trending = adx > 25
    trend_is_up = (adx_pos > adx_neg) & (ema_slope > 0)
    high_volatility = (atr_pct > 2.5) | (bb_width > bb_width_avg * 1.3)
    squeeze = bb_width < bb_width_avg * 0.7

    # Same precedence as the if/elif chain in detect_regime.
    labels = pd.Series(RANGING, index=df.index, dtype=object)
    labels = labels.mask(squeeze, LOW_VOLATILITY)
    labels = labels.mask(high_volatility, HIGH_VOLATILITY)
    labels = labels.mask(is_trending & ~trend_is_up, TRENDING_DOWN)
    labels = labels.mask(is_trending & trend_is_up, TRENDING_UP)

    warm = adx.notna() & bb_width_avg.notna() & ema_slope.notna() & atr_pct.notna()
    return labels.where(warm)
