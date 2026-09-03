"""Batch runner (design sections 9 and 10).

    python -m research.runner --config research/configs/baseline.yaml
    python -m research.runner --config research/configs/baseline.yaml --audit-only

Writes one directory per run containing the config that produced it, one row per
(symbol, arm, fold), the stitched per-(symbol, arm) summary, and the bias deltas
that answer RQ1. Every row carries the config hash.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .arms import build_context, run_arm, stitch
from .config import (
    ARM_BUY_HOLD,
    ARM_HMM_FIT_LEAKED,
    ARM_HMM_HONEST,
    ARM_HMM_LEAKED,
    FIXED_ARMS,
    StudyConfig,
)
from .data import audit, eligible_symbols, load_snapshot, symbol_frames
from .execution import STRATEGY_NAMES
from .metrics import deflated_sharpe_ratio, per_period_sharpe, summarise
from .walkforward import required_bars


def _log(message: str) -> None:
    print(message, flush=True)


def run_study(cfg: StudyConfig) -> Path:
    out_dir = Path(cfg.output_dir) / cfg.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg.write_json(out_dir / "config.json")
    config_hash = cfg.config_hash()

    _log(f"run {cfg.run_id}  config {config_hash}")
    snapshot = load_snapshot(cfg.data_path)

    audit_table = audit(snapshot)
    audit_table.to_csv(out_dir / "audit.csv", index=False)
    _flag_audit_risks(audit_table)

    frames = symbol_frames(snapshot)
    needed = max(cfg.min_bars, required_bars(cfg.train_bars, cfg.test_bars, cfg.embargo_bars, cfg.min_folds))
    accepted, rejected = eligible_symbols(frames, needed, cfg.min_median_volume)

    if cfg.symbols:
        wanted = {s.upper() for s in cfg.symbols}
        for symbol in sorted(set(accepted) - wanted):
            rejected[symbol] = "not in configured symbol list"
        accepted = [s for s in accepted if s in wanted]

    pd.DataFrame(
        sorted(rejected.items()), columns=["symbol", "reason"]
    ).to_csv(out_dir / "excluded.csv", index=False)

    if not accepted:
        raise RuntimeError(
            f"no symbol met the inclusion criteria (needs {needed} bars). "
            f"See {out_dir / 'excluded.csv'}."
        )
    _log(f"{len(accepted)} symbols eligible, {len(rejected)} excluded (needs {needed} bars)")

    fold_rows: list[dict] = []
    summary_rows: list[dict] = []
    returns_frames: list[pd.DataFrame] = []
    started = time.time()

    for position, symbol in enumerate(accepted, start=1):
        try:
            ctx = build_context(symbol, frames[symbol], cfg)
        except ValueError as exc:
            rejected[symbol] = str(exc)
            _log(f"  [{position}/{len(accepted)}] {symbol}: skipped -- {exc}")
            continue

        per_arm: dict[str, pd.Series] = {}
        for arm in cfg.arms:
            outcomes = run_arm(ctx, arm)
            for outcome in outcomes:
                fold_rows.append({**outcome.row(), "config_hash": config_hash})

            stitched = stitch(outcomes)
            per_arm[arm] = stitched
            if len(stitched):
                returns_frames.append(
                    pd.DataFrame(
                        {
                            "symbol": symbol,
                            "arm": arm,
                            "date": stitched.index,
                            "ret": stitched.to_numpy(),
                        }
                    )
                )
            summary_rows.append(
                {
                    "symbol": symbol,
                    "arm": arm,
                    "n_folds": len(outcomes),
                    **summarise(stitched, n_trades=sum(o.n_trades for o in outcomes)),
                    "failed_folds": sum(1 for o in outcomes if not o.ok),
                    # Label-level diagnostics, carried up from the folds. The
                    # smoothing leak can measure exactly zero while the labels
                    # genuinely differ -- persistent regimes make filtered and
                    # smoothed decoding pick the same strategy -- and then this
                    # is the only evidence the mechanism exists. It has to sit
                    # beside the P&L delta, not two files away.
                    "smoothed_disagreement": _mean_or_nan(
                        [o.smoothed_disagreement for o in outcomes]
                    ),
                    "label_churn": _mean_or_nan([o.label_churn for o in outcomes]),
                    "max_regime_age_bars": _max_or_nan(
                        [o.max_regime_age_bars for o in outcomes]
                    ),
                    "config_hash": config_hash,
                }
            )

        _log(
            f"  [{position}/{len(accepted)}] {symbol}: {len(ctx.folds)} folds, "
            f"{len(cfg.arms)} arms, {time.time() - started:.0f}s elapsed"
        )

    summary = pd.DataFrame(summary_rows)
    summary = _add_deflated_sharpe(summary, cfg)

    pd.DataFrame(fold_rows).to_csv(out_dir / "fold_results.csv", index=False)
    summary.to_csv(out_dir / "summary.csv", index=False)
    if returns_frames:
        pd.concat(returns_frames).to_csv(out_dir / "oos_returns.csv", index=False)

    deltas = bias_deltas(summary)
    if len(deltas):
        deltas.to_csv(out_dir / "deltas.csv", index=False)
        _report_headline(deltas)

    _log(f"done in {time.time() - started:.0f}s -- {out_dir}")
    return out_dir


def _flag_audit_risks(audit_table: pd.DataFrame) -> None:
    """Surface the two Phase 0 findings that can invalidate the study."""
    suspects = int((audit_table["suspected_corporate_actions"] > 0).sum())
    if suspects:
        _log(
            f"  WARNING: {suspects} symbol(s) show single-day moves above "
            "20%, which is what unadjusted bonus issues look like. Confirm whether "
            "Close is corporate-action adjusted before trusting any result."
        )
    zero_volume = int((audit_table["zero_volume_pct"] > 5).sum())
    if zero_volume:
        _log(f"  note: {zero_volume} symbol(s) have zero volume on more than 5% of bars")


def _add_deflated_sharpe(summary: pd.DataFrame, cfg: StudyConfig) -> pd.DataFrame:
    """Deflate each regime arm's Sharpe for the strategy search behind it.

    The variance of Sharpe across trials is estimated from the fixed-strategy
    arms on the same symbol -- those are precisely the pool the selector chose
    from, evaluated over the same folds. When the A1 arms are not in the run,
    the deflation is left as NaN rather than guessed at.
    """
    if summary.empty:
        return summary

    summary = summary.copy()
    summary["deflated_sharpe"] = np.nan
    summary["n_trials"] = np.nan

    regime_arms = {ARM_HMM_LEAKED, ARM_HMM_FIT_LEAKED, ARM_HMM_HONEST, "A2"}
    fixed = set(FIXED_ARMS)

    for symbol, group in summary.groupby("symbol"):
        pool = group[group["arm"].isin(fixed)]["sharpe_per_period"].dropna()
        variance = float(np.var(pool, ddof=1)) if len(pool) > 1 else np.nan

        for idx in group.index:
            if group.loc[idx, "arm"] not in regime_arms:
                continue
            n_trials = len(STRATEGY_NAMES) * int(group.loc[idx, "n_folds"] or 0)
            summary.loc[idx, "n_trials"] = n_trials
            if not np.isfinite(variance):
                continue
            sharpe = group.loc[idx, "sharpe_per_period"]
            if not np.isfinite(sharpe):
                continue
            # Reconstruct a return series with this Sharpe is not possible here,
            # so deflation runs on the stored per-period Sharpe via its own path.
            summary.loc[idx, "deflated_sharpe"] = _deflate_from_summary(
                sharpe, n_trials, variance, int(group.loc[idx, "n_bars"] or 0)
            )
    return summary


def _deflate_from_summary(sharpe: float, n_trials: int, variance: float, n_obs: int) -> float:
    """Normal-moment deflation, used when only summary statistics are to hand.

    metrics.deflated_sharpe_ratio is the version to prefer -- it uses the actual
    skew and kurtosis of the return series. This assumes normality, which
    overstates significance for fat-tailed returns, so treat it as indicative and
    recompute from oos_returns.csv for anything that goes in the paper.
    """
    from scipy.stats import norm

    from .metrics import expected_max_sharpe

    if n_obs < 3 or not np.isfinite(sharpe):
        return float("nan")
    threshold = expected_max_sharpe(n_trials, variance)
    return float(norm.cdf((sharpe - threshold) * np.sqrt(n_obs - 1)))


def _mean_or_nan(values: list) -> float:
    present = [v for v in values if v is not None and not pd.isna(v)]
    return float(np.mean(present)) if present else float("nan")


def _max_or_nan(values: list) -> float:
    present = [v for v in values if v is not None and not pd.isna(v)]
    return float(np.max(present)) if present else float("nan")


def bias_deltas(summary: pd.DataFrame) -> pd.DataFrame:
    """The headline result: the leak decomposed, per symbol (design section 5)."""
    if summary.empty:
        return pd.DataFrame()

    pivot = summary.pivot_table(index="symbol", columns="arm", values="sharpe_annualised")
    needed = {ARM_HMM_LEAKED, ARM_HMM_FIT_LEAKED, ARM_HMM_HONEST}
    if not needed.issubset(pivot.columns):
        return pd.DataFrame()

    out = pd.DataFrame(index=pivot.index)
    out["sharpe_B1_leaked"] = pivot[ARM_HMM_LEAKED]
    out["sharpe_B2_fit_leaked"] = pivot[ARM_HMM_FIT_LEAKED]
    out["sharpe_B3_honest"] = pivot[ARM_HMM_HONEST]
    out["total_leak"] = pivot[ARM_HMM_LEAKED] - pivot[ARM_HMM_HONEST]
    out["smoothing_leak"] = pivot[ARM_HMM_LEAKED] - pivot[ARM_HMM_FIT_LEAKED]
    out["fitting_leak"] = pivot[ARM_HMM_FIT_LEAKED] - pivot[ARM_HMM_HONEST]

    # The label-level channel, beside the P&L channel it explains. A zero
    # smoothing_leak with a non-zero disagreement rate is a real result -- the
    # labels differed and the selection rule absorbed it -- not a null.
    if "smoothed_disagreement" in summary.columns:
        disagreement = summary.pivot_table(
            index="symbol", columns="arm", values="smoothed_disagreement"
        )
        if ARM_HMM_LEAKED in disagreement.columns:
            out["label_disagreement_full_fit"] = disagreement[ARM_HMM_LEAKED]
        if ARM_HMM_HONEST in disagreement.columns:
            out["label_disagreement_fold_fit"] = disagreement[ARM_HMM_HONEST]
    if "max_regime_age_bars" in summary.columns:
        age = summary.pivot_table(
            index="symbol", columns="arm", values="max_regime_age_bars"
        )
        if ARM_HMM_HONEST in age.columns:
            out["max_regime_age_bars"] = age[ARM_HMM_HONEST]
    if "A2" in pivot.columns:
        out["sharpe_A2_rules"] = pivot["A2"]
        out["hmm_minus_rules"] = pivot[ARM_HMM_HONEST] - pivot["A2"]
    if ARM_BUY_HOLD in pivot.columns:
        out["sharpe_A0_buy_hold"] = pivot[ARM_BUY_HOLD]
    return out.reset_index()


def _report_headline(deltas: pd.DataFrame) -> None:
    def describe(column: str) -> str:
        values = deltas[column].dropna()
        if values.empty:
            return "n/a"
        return f"median {values.median():+.3f}  mean {values.mean():+.3f}  n={len(values)}"

    _log("")
    _log("  Sharpe deltas across symbols (annualised):")
    _log(f"    total leak      B1 - B3   {describe('total_leak')}")
    _log(f"    smoothing leak  B1 - B2   {describe('smoothing_leak')}")
    _log(f"    fitting leak    B2 - B3   {describe('fitting_leak')}")
    if "hmm_minus_rules" in deltas:
        _log(f"    HMM vs rules    B3 - A2   {describe('hmm_minus_rules')}")
    _log("")


def run_audit_only(cfg: StudyConfig) -> Path:
    out_dir = Path(cfg.output_dir) / cfg.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = load_snapshot(cfg.data_path)
    table = audit(snapshot)
    path = out_dir / "audit.csv"
    table.to_csv(path, index=False)
    _flag_audit_risks(table)
    _log(f"audited {len(table)} symbols -> {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="path to a study config YAML")
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="run Phase 0 data quality checks and stop",
    )
    parser.add_argument("--snapshot", help="write a fresh snapshot from the database and exit")
    args = parser.parse_args(argv)

    cfg = StudyConfig.from_yaml(args.config)

    if args.snapshot:
        from .data import snapshot_from_db

        path = snapshot_from_db(args.snapshot)
        _log(f"snapshot written to {path}")
        return 0

    if args.audit_only:
        run_audit_only(cfg)
        return 0

    run_study(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
