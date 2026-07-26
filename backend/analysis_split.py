TRAINING_RATIO = 0.70
MIN_TRAINING_BARS = 60
MIN_HOLDOUT_BARS = 60


def chronological_holdout(
    df,
    training_ratio=TRAINING_RATIO,
    min_training_bars=MIN_TRAINING_BARS,
    min_holdout_bars=MIN_HOLDOUT_BARS,
):
    """Split ordered market data into non-overlapping training and holdout sets."""
    total_bars = len(df)
    minimum_bars = min_training_bars + min_holdout_bars

    if total_bars < minimum_bars:
        raise ValueError(
            "Auto Strategy needs at least "
            f"{minimum_bars} price bars ({min_training_bars} for strategy selection "
            f"and {min_holdout_bars} for later testing). "
            "Choose an earlier start date or turn off Auto Strategy."
        )

    split_index = int(total_bars * training_ratio)
    split_index = max(split_index, min_training_bars)
    split_index = min(split_index, total_bars - min_holdout_bars)

    training_df = df.iloc[:split_index].copy()
    holdout_df = df.iloc[split_index:].copy()
    return training_df, holdout_df


def period_details(df):
    """Return JSON-ready boundaries for an ordered DatetimeIndex data frame."""
    return {
        "start": df.index[0].strftime("%Y-%m-%d"),
        "end": df.index[-1].strftime("%Y-%m-%d"),
        "bars": len(df),
    }
