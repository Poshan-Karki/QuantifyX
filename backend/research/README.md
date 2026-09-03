# Research harness

Offline harness for the look-ahead bias study. Implements the published research
design; section numbers in the module docstrings point back at it.

## What this study claims

Written down because the title and abstract will drift toward something broader
than the harness measures, and this is the sentence to check them against.

**The outcome variable is trading performance, not label accuracy.** Every
headline number in `deltas.csv` is a difference in annualised Sharpe between two
stitched out-of-sample *trading* curves whose arms differ only in how much
future information the regime labels were allowed to use. The claim the harness
supports is:

> Regime labels contaminated with future information inflate the backtested
> out-of-sample Sharpe of a regime-conditioned strategy-selection rule by X,
> decomposed into a smoothing component and a parameter-estimation component.

**Two mechanisms, separately identified.** This is the contribution; "leakage
inflates backtests" on its own is not a finding.

| delta | arms | mechanism |
| :--- | :--- | :--- |
| `smoothing_leak` | B1 − B2 | Viterbi decoding lets later bars set earlier labels |
| `fitting_leak` | B2 − B3 | parameters estimated on bars the trader had not seen |
| `total_leak` | B1 − B3 | both together |

**What cannot be claimed.** Say these plainly in the limitations section rather
than letting a reviewer find them:

- *No statement about regime-detection accuracy.* The states are latent and
  there is no ground truth, so nothing here measures whether a label is
  "correct" — only what trading on it earns. `smoothed_disagreement` and
  `label_churn` are label-level diagnostics to report alongside the P&L delta,
  never as a substitute for it.
- *The bias is measured through one channel.* One strategy pool, one selection
  rule (best in-regime training Sharpe), regime read once per fold. A different
  pool or selection rule would give a different number. The magnitude is
  channel-specific; the direction and the decomposition are the durable results.
- *The population is NEPSE.* Frontier, thin, and — per the Phase 0 audit —
  carrying prices that are not adjusted for corporate actions. Generalisation to
  liquid developed markets is an assumption, not a result.
- *Walk-forward is the benchmark, not the setting.* B3 is the walk-forward arm;
  B1 and B2 deliberately violate it. Phrasing the bias as occurring "under
  walk-forward validation" inverts the relationship — correctly executed
  walk-forward is what removes it.

A title that fits the above names the decomposition and the channel, for
example: *Decomposing Look-Ahead Bias in Hidden Markov Regime Detection:
Smoothing versus Estimation Leakage in Walk-Forward Strategy Selection.*

The API wants a fast cached endpoint, the study wants a slow reproducible batch
job, and making one serve both is how the leak being measured gets reintroduced.
So the boundary runs between two packages, and the dependency runs one way:

```
research  ->  regime, costs, Backtest      allowed, and used
app       ->  research                     never; tests assert it
```

- **`backend/regime/`** — the inference primitives both sides share:
  `features.py`, `hmm_regime.py`, `rule_regime.py`, `synthetic.py`.
  `backend/hmm_service.py` imports them, so the forward recursion behind `/hmm`
  is the same tested code the study runs against. This is application code and
  does not live here.
- **`backend/research/`** — the experiment: `arms.py`, `walkforward.py`,
  `config.py`, `data.py`, `execution.py`, `metrics.py`, `runner.py` and
  `tests/`. No API path imports any of it, and no request reaches it.

Those primitives used to live in this package, which had the dependency
backwards — `hmm_service.py` imported from a research package, so the study
could not be removed or relocated without taking the API down with it.
`test_the_regime_package_never_imports_the_study` pins the corrected direction.

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

If the same thing happens on real data, report the label-level disagreement rate
alongside the P&L delta. `deltas.csv` carries both channels side by side so this
takes no assembly:

| column | channel |
| :--- | :--- |
| `smoothing_leak` | P&L cost of smoothed decoding |
| `label_disagreement_full_fit` | share of bars where smoothed and filtered labels differ (B1/B2) |
| `fitting_leak` | P&L cost of full-series estimation |
| `label_disagreement_fold_fit` | same disagreement measured within the honest fold fit (B3) |
| `max_regime_age_bars` | staleness of the label at the last bar it governs |

On the smoke data that pairing reads `smoothing_leak = 0.000` against
`label_disagreement_full_fit ≈ 0.009`: the labels genuinely differed on roughly
1% of bars and the selection rule absorbed all of it. The mechanism is real even
when the P&L channel does not resolve it, and a paper that shows both is more
honest than one that only reports whichever number came out larger.

**Folds are contiguous: train ends at bar *t*, test begins at bar *t*.**
`embargo_bars` defaults to `0`. The gap it used to impose was not preventing
leakage — every feature is a function of bar *t* and earlier, so a test bar
reaching back into training data is reading its own past, which is what a live
trader does. Purging exists for forward-looking *labels*, and this study has
none: the HMM is unsupervised and selection scores training-window Sharpe over
training bars alone.

Indicator warm-up is now a separate concept and may cross into training bars.
Warm-up bars are neither fitted on nor scored. The one invariant that did not
move: **no arm may fit on a bar at or after `train_end`**, and
`research/tests/test_leakage.py` asserts it with and without a gap.

`configs/ablation_embargo.yaml` reproduces the 60-bar gap. Run it — a smoke run
on two synthetic symbols moved every delta substantially between the two
protocols, which shows the choice is consequential and nothing more (n=2, and
the fold counts differ so the windows are not comparable). Report the real-data
comparison in the paper whichever way it comes out.

**Regime is read once per fold**, at `test_start - 1` — the last bar before the
test window — and held for the whole window. It used to be read at
`train_end - 1`; with the old 60-bar gap that made the label 60 bars stale
before the window even opened, and up to 120 bars stale in use. Nothing required
that: the forward decode already labels every bar up to `test_end`, and row *t*
of a forward recursion depends only on rows ≤ *t*, so the fresher label was both
available and causal. `max_regime_age_bars` in `fold_results.csv` records the
staleness per fold, so it is measured rather than assumed.

Re-reading the regime each test bar would be closer still to live trading, but
switching strategies mid-run is not expressible in `backtesting.py`. That part
remains a stated limitation, not an oversight.

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

The study's own suite:

```bash
python -m pytest research/tests -q
```

Or both suites at once — `pytest.ini` lists `tests` and `research/tests`, and
this is what CI runs:

```bash
python -m pytest -q
```

`research/tests/test_leakage.py` is the one that matters. It asserts both directions
mechanically, from the bar indices recorded at the moment of fitting:

- `B3` never fits on a bar at or after `train_end`, with and without an embargo
- the regime read bar is never inside the test window
- `B1` and `B2` still fit on the whole series

The second is as important as the first. If someone "fixes" the leaked arms, the
study silently stops measuring anything and the headline number becomes zero.

`tests/test_regime_hmm.py` validates the hand-rolled forward recursion against
`hmmlearn`'s own `score()`, and checks that rewriting the tail of an observation
sequence cannot change any filtered label before the cut — the property that
makes filtered decoding tradeable in the first place.

`tests/test_regime_rule.py` keeps the vectorised copy of the rule-based
classifier in agreement with the live `detect_regime`.

## Cost of a full run

Roughly, per symbol: `folds × |K candidates| × restarts` HMM fits for `B3`, plus
one full-series fit shared by `B1` and `B2`, plus eight training backtests and
one test backtest per fold (cached and shared across arms). On ~2000 bars that is
about 19 folds and a few hundred fits — order of a minute per symbol with the
baseline config. Budget accordingly before launching the seed sweep.
