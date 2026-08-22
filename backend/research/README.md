# Research harness

Offline harness for the look-ahead bias study. Implements the published research
design; section numbers in the module docstrings point back at it.

The API wants a fast cached endpoint, the study wants a slow reproducible batch
job, and making one serve both is how the leak being measured gets reintroduced.
So the boundary runs through this package rather than around it:

- **Shared with production.** `features.py`, `hmm_regime.py` and `rule_regime.py`
  are inference primitives. `backend/hmm_service.py` imports them, so the
  forward recursion behind `/hmm` is the same tested code the study uses.
- **Study only.** `arms.py`, `walkforward.py`, `config.py`, `data.py`,
  `metrics.py` and `runner.py`. No API path imports these, and no request
  reaches them.

## Running it

Everything runs from the `backend/` directory.

```bash
python -m research.runner --config research/configs/smoke.yaml
```

That uses synthetic data and finishes in under a minute. It is a pipeline check,
not a result — the windows are far too short to fit a meaningful HMM.

For real work, snapshot the database once and run against the snapshot:

```bash
python -m research.runner --config research/configs/baseline.yaml --snapshot research/data/nepse_snapshot.csv.gz
```

Then Phase 0, which can invalidate everything downstream and so runs first:

```bash
python -m research.runner --config research/configs/baseline.yaml --audit-only
```

Read `audit.csv` before going further. Two columns decide whether the study is
viable at all:

- `suspected_corporate_actions` — single-day moves above 20%. If this is
  materially above zero, establish whether `Close` is adjusted for bonus issues
  before trusting anything. Unadjusted prices fabricate the volatility regime
  changes the HMM is supposed to detect.
- whether delisted symbols are present at all, which the audit cannot tell you —
  you have to ask where `nepseintel` came from.

Then the full study:

```bash
python -m research.runner --config research/configs/baseline.yaml
```

## Output

One directory per run under `research/results/<run_id>/`:

| File | Contents |
| --- | --- |
| `config.json` | the exact config, plus its hash |
| `audit.csv` | Phase 0 data quality, per symbol |
| `excluded.csv` | every symbol rejected, and why |
| `fold_results.csv` | one row per (symbol, arm, fold) with diagnostics |
| `summary.csv` | stitched out-of-sample metrics per (symbol, arm) |
| `deltas.csv` | the headline result — the leak, decomposed |
| `oos_returns.csv` | per-bar out-of-sample returns, for your own statistics |

Every row carries `config_hash`, so any figure traces back to the parameters
behind it.

## The arms

| Arm | Regime signal | Fit scope | Decode |
| --- | --- | --- | --- |
| `A0` | none — buy and hold | — | — |
| `A1:<strategy>` | none — one fixed strategy | — | — |
| `A2` | rule-based thresholds | no fitting | — |
| `B1` | Gaussian HMM | entire series | smoothed |
| `B2` | Gaussian HMM | entire series | filtered |
| `B3` | Gaussian HMM | training fold only | filtered |

`B1` reproduces what `/hmm` does today. `B3` is the only arm that could have
been traded. `B1 - B2` is the smoothing leak, `B2 - B3` the fitting leak.

## Things worth knowing before you interpret results

**The smoothing leak is diluted by the selection rule.** Strategy selection is
`argmax` over eight candidates, which is a coarse function of the labels. On the
synthetic smoke data, filtered and smoothed labels disagree on about 1% of bars
yet select the *same* strategy in every fold, so `B1 - B2` comes out at exactly
zero. That is a real property of the design, not a bug. Persistent regimes make
filtered and smoothed decoding agree, and small label differences then rarely
change which strategy wins.

If the same thing happens on real data, report the label-level disagreement
rate (`smoothed_disagreement`, already recorded per fold) alongside the P&L
delta. The mechanism is real even when the P&L channel does not resolve it, and
a paper that shows both is more honest than one that only reports whichever
number came out larger.

**Regime is read once per fold**, at the last training bar, and held for the
whole test window. Re-reading it each test bar would be closer to live trading,
but switching strategies mid-run is not expressible in `backtesting.py`. Stated
limitation, not an oversight.

**`A2` is stronger here than in the app.** The application reads
`REGIME_STRATEGY_MAP[regime][0]`; the study uses the same data-driven selection
rule as the HMM arms, because otherwise the comparison confounds the labelling
scheme with the hand-authored mapping. Say so in the paper — it makes any result
favouring the HMM more credible, not less.

**`deflated_sharpe` in `summary.csv` assumes normal returns.** It is indicative
only. For anything going in the paper, recompute from `oos_returns.csv` with
`metrics.deflated_sharpe_ratio`, which uses the actual skew and kurtosis — and
verify the formula against Bailey & López de Prado first. It was written from
memory.

## Tests

```bash
python -m pytest tests/ -q
```

`test_research_leakage.py` is the one that matters. It asserts both directions
mechanically, from the bar indices recorded at the moment of fitting:

- `B3` never fits on a test bar, or on an embargo bar
- `B1` and `B2` still fit on the whole series

The second is as important as the first. If someone "fixes" the leaked arms, the
study silently stops measuring anything and the headline number becomes zero.

`test_research_hmm.py` validates the hand-rolled forward recursion against
`hmmlearn`'s own `score()`, and checks that rewriting the tail of an observation
sequence cannot change any filtered label before the cut — the property that
makes filtered decoding tradeable in the first place.

`test_research_rule_regime.py` keeps the vectorised copy of the rule-based
classifier in agreement with the live `detect_regime`.

## Cost of a full run

Roughly, per symbol: `folds × |K candidates| × restarts` HMM fits for `B3`, plus
one full-series fit shared by `B1` and `B2`, plus eight training backtests and
one test backtest per fold (cached and shared across arms). On ~2000 bars that is
about 19 folds and a few hundred fits — order of a minute per symbol with the
baseline config. Budget accordingly before launching the seed sweep.
