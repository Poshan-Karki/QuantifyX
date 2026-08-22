"""Data snapshot and the Phase 0 audit (design section 3).

The study runs against a dated snapshot file, never against the live database.
Re-querying mid-study silently changes the sample, and a result you cannot
reproduce is not a result.

The audit is Phase 0 because two of its findings can invalidate everything
downstream: unadjusted corporate actions, which fabricate the volatility regime
changes the HMM is supposed to detect, and missing delisted symbols, which
biases every arm upward. Both go in the paper regardless of the answer.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OHLCV = ["Open", "High", "Low", "Close", "Volume"]

#: NEPSE's daily price band. Verify the current figure and its history before
#: citing anything derived from it -- the band has not always been 10%, and some
#: securities are exempt.
CIRCUIT_LIMIT_PCT = 10.0

#: A single-day move this large is more likely a bonus issue or split showing up
#: in unadjusted prices than a real return.
CORPORATE_ACTION_THRESHOLD = 0.20


def snapshot_from_db(out_path: str | Path, symbols: list[str] | None = None) -> Path:
    """Dump nepseintel to a compressed CSV for the study to run against.

    db is imported here rather than at module scope so the rest of the harness,
    and its tests, work without DATABASE_URL set.
    """
    from sqlalchemy import text

    from db import Sessionlocal

    query = 'SELECT "Date","Symbol","Open","High","Low","Close","Vol" FROM nepseintel'
    params: dict = {}
    if symbols:
        query += ' WHERE "Symbol" = ANY(:symbols)'
        params["symbols"] = [s.upper() for s in symbols]
    query += ' ORDER BY "Symbol","Date"'

    session = Sessionlocal()
    try:
        rows = session.execute(text(query), params).fetchall()
    finally:
        session.close()

    if not rows:
        raise RuntimeError("nepseintel returned no rows -- check the connection and the table name")

    frame = pd.DataFrame(rows, columns=["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_path, index=False, compression="infer")
    return out_path


def load_snapshot(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["Date"])
    missing = {"Date", "Symbol", *OHLCV} - set(frame.columns)
    if missing:
        raise ValueError(f"snapshot is missing column(s): {sorted(missing)}")
    return frame


def symbol_frames(snapshot: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split a snapshot into per-symbol OHLCV frames with a DatetimeIndex.

    Duplicate dates are dropped, keeping the last, and the count is reported by
    audit() so the decision is visible rather than silent.
    """
    frames: dict[str, pd.DataFrame] = {}
    for symbol, group in snapshot.groupby("Symbol", sort=True):
        frame = group.sort_values("Date").drop_duplicates(subset="Date", keep="last")
        frame = frame.set_index("Date")[OHLCV].astype(float)
        frames[str(symbol).upper()] = frame
    return frames


def audit(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Per-symbol data quality table -- Phase 0 of the study.

    Every column here answers a question a referee will ask. suspected_corporate
    _actions in particular: if that count is materially above zero, establish
    whether Close is adjusted before running anything else.
    """
    records = []
    for symbol, group in snapshot.groupby("Symbol", sort=True):
        frame = group.sort_values("Date")
        duplicates = int(frame["Date"].duplicated().sum())
        frame = frame.drop_duplicates(subset="Date", keep="last").set_index("Date")

        close = frame["Close"].astype(float)
        volume = frame["Volume"].astype(float)
        returns = close.pct_change()
        gaps = frame.index.to_series().diff().dt.days

        limit = CIRCUIT_LIMIT_PCT / 100.0
        records.append(
            {
                "symbol": str(symbol).upper(),
                "n_bars": len(frame),
                "first_date": frame.index.min(),
                "last_date": frame.index.max(),
                "duplicate_dates": duplicates,
                "median_volume": float(volume.median()),
                "zero_volume_days": int((volume <= 0).sum()),
                "zero_volume_pct": float((volume <= 0).mean() * 100),
                "nonpositive_close": int((close <= 0).sum()),
                "high_below_low": int((frame["High"] < frame["Low"]).sum()),
                "max_abs_return": float(returns.abs().max()),
                "at_circuit_limit": int((returns.abs() >= limit * 0.999).sum()),
                "suspected_corporate_actions": int((returns.abs() > CORPORATE_ACTION_THRESHOLD).sum()),
                "max_calendar_gap_days": float(gaps.max()) if len(gaps) > 1 else np.nan,
            }
        )
    return pd.DataFrame.from_records(records)


def eligible_symbols(
    frames: dict[str, pd.DataFrame],
    min_bars: int,
    min_median_volume: float = 0.0,
) -> tuple[list[str], dict[str, str]]:
    """Apply the section 3.2 inclusion criteria.

    Returns the accepted symbols and, for everything rejected, why -- the
    exclusion table belongs in the paper.
    """
    accepted: list[str] = []
    rejected: dict[str, str] = {}
    for symbol, frame in sorted(frames.items()):
        if len(frame) < min_bars:
            rejected[symbol] = f"only {len(frame)} bars, need {min_bars}"
            continue
        median_volume = float(frame["Volume"].median())
        if median_volume < min_median_volume:
            rejected[symbol] = f"median volume {median_volume:.0f} below {min_median_volume:.0f}"
            continue
        accepted.append(symbol)
    return accepted, rejected
