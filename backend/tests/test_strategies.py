import unittest

import pandas as pd
from backtesting import Backtest

from Backtest import VolumeBreakout


def frame_with_volume_dip(dip_volume, n_before=30, n_after=10,
                           flat_price=100.0, dip_price=80.0, base_volume=1000.0):
    """A flat price series with one sharp dip on a single bar, so the dip's
    volume relative to the rolling average is the only thing that varies.
    """
    index = pd.date_range("2024-01-01", periods=n_before + 1 + n_after, freq="D")
    closes = [flat_price] * n_before + [dip_price] + [flat_price] * n_after
    volumes = [base_volume] * n_before + [dip_volume] + [base_volume] * n_after

    close = pd.Series(closes, index=index)
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(volumes, index=index)
    # High/Low must bracket both Open and Close, or the backtesting engine
    # treats the bar as invalid and silently refuses to fill orders on it.
    high = pd.concat([open_, close], axis=1).max(axis=1) * 1.01
    low = pd.concat([open_, close], axis=1).min(axis=1) * 0.99

    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume})


class VolumeBreakoutEntryThresholdTests(unittest.TestCase):
    """Regression test for a bug where entry_multiplier (2.2) and
    exit_multiplier (0.85) were swapped in VolumeBreakout.next(): entries were
    gated on the low exit_multiplier (almost always true) and exits on the
    high entry_multiplier (almost never true), making the strategy's namesake
    volume-breakout confirmation nearly meaningless on entry and causing
    near-immediate exits after any entry.
    """

    def test_does_not_enter_on_a_dip_with_only_modest_volume(self):
        # 1.2x average volume: below entry_multiplier (2.2x) -- not a real
        # volume breakout, should not trigger an entry.
        df = frame_with_volume_dip(dip_volume=1200.0)

        stats = Backtest(df, VolumeBreakout, cash=100_000, commission=0.0,
                          finalize_trades=True).run()

        self.assertEqual(stats["# Trades"], 0)

    def test_enters_on_a_dip_with_a_genuine_volume_spike(self):
        # 2.5x average volume: above entry_multiplier (2.2x), a real spike.
        df = frame_with_volume_dip(dip_volume=2500.0)

        stats = Backtest(df, VolumeBreakout, cash=100_000, commission=0.0,
                          finalize_trades=True).run()

        self.assertEqual(stats["# Trades"], 1)


if __name__ == "__main__":
    unittest.main()
