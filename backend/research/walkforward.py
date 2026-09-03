"""Walk-forward fold generation (design section 4.5).

Generalises analysis_split.chronological_holdout from a single 70/30 split into
repeated train/test folds, by default contiguous: train ends at bar t, test
begins at bar t.

On the embargo, which used to default to 60 bars and no longer does.

Its stated purpose was that no test bar should share a rolling indicator window
with a training bar. That is not leakage. Every feature here is a function of
bar t and earlier bars only, so a test bar reaching back into training data is
reading its own past -- exactly what a live trader does at time t. Information
does not flow backwards across that boundary.

The construction an embargo genuinely protects against is a forward-looking
label: when a training sample at bar s carries a label computed over [s, s+h]
and s+h lands inside the test window, the training set contains test-period
information and must be purged. This study has no such label. The HMM is
unsupervised, and strategy selection scores training-window Sharpe over training
bars alone. There is nothing to purge.

What the embargo did buy was distance from serial correlation across the
boundary -- a real but much weaker concern -- and it charged for it in
staleness. The regime driving a test window was read before the gap, so with a
60-bar embargo and a 60-bar test window the label was 60 to 120 bars old in use.

Whether that staleness helped or hurt the measured deltas is an open empirical
question, and deliberately not answered here. A smoke run on two synthetic
symbols moved every delta substantially when the gap was restored, which
establishes only that the protocol choice is consequential -- n=2, different
fold counts, different test windows, so it is evidence of sensitivity and
nothing more. Do not cite it.

The change is justified on correctness, not on which number it produces: there
is no forward-looking label to purge, and a fresher causal label was available
for free. embargo_bars therefore defaults to 0 and survives as a knob, so the
previous design stays reproducible and "does the gap change the answer?" gets
run on real data rather than argued about. See configs/ablation_embargo.yaml,
and report the comparison in the paper whichever way it comes out.

Warm-up is now a separate concept from the embargo. Indicator warm-up may reach
back into training bars; it is neither fitted on nor scored, and reading past
bars is causal. The one invariant that has not moved: no arm may *fit* on a bar
at or after train_end.
"""

from __future__ import annotations

from dataclasses import dataclass

ANCHORED = "anchored"
ROLLING = "rolling"
SCHEMES = (ANCHORED, ROLLING)


@dataclass(frozen=True)
class Fold:
    """One walk-forward fold, as half-open integer bar ranges.

    [train_start, train_end)  the only bars any fitting step may see
    [train_end, test_start)   embargo, empty by default -- never fitted, never scored
    [test_start, test_end)    evaluated out of sample, never fitted

    Indicator warm-up runs backwards from test_start and may cross into either
    of the earlier ranges. That is causal and deliberate; see the module
    docstring.
    """

    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int

    @property
    def train_bars(self) -> int:
        return self.train_end - self.train_start

    @property
    def test_bars(self) -> int:
        return self.test_end - self.test_start

    @property
    def embargo_bars(self) -> int:
        return self.test_start - self.train_end

    @property
    def regime_read_bar(self) -> int:
        """The bar whose label selects the strategy for this fold's test window.

        The last bar before the test window, not the last *training* bar. With a
        contiguous fold these coincide; with an embargo they do not, and reading
        at train_end - 1 threw away labels that were both available and causal.
        """
        return self.test_start - 1

    @property
    def max_regime_age_bars(self) -> int:
        """Age of the regime label at the last bar it still governs.

        The label is read once and held across the test window, so this is the
        worst case, not the average. On a contiguous 60-bar fold it is 60; under
        the old 60-bar embargo with the read at train_end - 1 it was 120.

        Recorded per fold so staleness is a measured quantity in the results
        rather than an assumption in a docstring.
        """
        return self.test_end - 1 - self.regime_read_bar

    @property
    def train_slice(self) -> slice:
        return slice(self.train_start, self.train_end)

    @property
    def test_slice(self) -> slice:
        return slice(self.test_start, self.test_end)

    def execution_slice(self, warmup_bars: int) -> slice:
        """Bars to feed the backtester so test-window indicators are warm.

        Starts warmup_bars before the test window. It may cross the embargo and
        run on into training bars, which is intended: computing an indicator at
        bar t from bars at or before t is what happens live, and those bars are
        in t's past whatever window they were assigned to. They are never fitted
        on and never scored -- only returns from test_start onward count, see
        metrics.trim_to_test.

        This used to raise when warmup exceeded the embargo, which forced the
        embargo to be at least as wide as the longest indicator lookback and so
        forced the staleness described in the module docstring.
        """
        if warmup_bars < 0:
            raise ValueError(f"warmup_bars must be non-negative, got {warmup_bars}")

        start = self.test_start - warmup_bars
        if start < 0:
            raise ValueError(
                f"fold {self.index}: warm-up of {warmup_bars} bars reaches back past the "
                f"start of the series from test_start {self.test_start}. Increase "
                "train_bars, or shorten warmup_bars."
            )
        return slice(start, self.test_end)


def generate_folds(
    n_bars: int,
    scheme: str = ANCHORED,
    train_bars: int = 750,
    test_bars: int = 60,
    embargo_bars: int = 0,
    step: int | None = None,
) -> list[Fold]:
    """Build the fold sequence for a series of n_bars.

    step defaults to test_bars, which makes the out-of-sample segments
    non-overlapping and contiguous -- the property that lets them be stitched
    into a single equity curve without double-counting any bar.
    """
    if scheme not in SCHEMES:
        raise ValueError(f"scheme must be one of {SCHEMES}, got {scheme!r}")
    for name, value in (
        ("train_bars", train_bars),
        ("test_bars", test_bars),
        ("n_bars", n_bars),
    ):
        if value <= 0:
            raise ValueError(f"{name} must be positive, got {value}")
    if embargo_bars < 0:
        raise ValueError(f"embargo_bars must be non-negative, got {embargo_bars}")

    if step is None:
        step = test_bars
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")

    folds: list[Fold] = []
    train_end = train_bars
    while True:
        test_start = train_end + embargo_bars
        test_end = test_start + test_bars
        if test_end > n_bars:
            break
        train_start = 0 if scheme == ANCHORED else max(0, train_end - train_bars)
        folds.append(Fold(len(folds), train_start, train_end, test_start, test_end))
        train_end += step

    return folds


def required_bars(train_bars: int, test_bars: int, embargo_bars: int = 0, min_folds: int = 1) -> int:
    """Minimum series length that yields min_folds folds, for inclusion criteria."""
    if min_folds < 1:
        raise ValueError(f"min_folds must be at least 1, got {min_folds}")
    return train_bars + embargo_bars + test_bars * min_folds


def assert_folds_sound(folds: list[Fold]) -> None:
    """Structural invariants every fold sequence must satisfy.

    Called by the runner before any fitting happens, so a misconfigured sweep
    fails immediately rather than producing quietly contaminated results.
    """
    if not folds:
        raise ValueError(
            "No folds were generated. The series is shorter than "
            "train_bars + embargo_bars + test_bars -- lower those, or exclude the symbol."
        )

    previous_test_end = None
    for fold in folds:
        if fold.train_start < 0:
            raise ValueError(f"fold {fold.index}: negative train_start")
        if fold.train_end <= fold.train_start:
            raise ValueError(f"fold {fold.index}: empty training window")
        if fold.test_start < fold.train_end:
            raise ValueError(
                f"fold {fold.index}: test window starts before training ends -- direct leakage"
            )
        if fold.test_end <= fold.test_start:
            raise ValueError(f"fold {fold.index}: empty test window")
        if previous_test_end is not None and fold.test_start < previous_test_end:
            raise ValueError(
                f"fold {fold.index}: test window overlaps the previous fold's, so stitched "
                "out-of-sample returns would double-count bars"
            )
        previous_test_end = fold.test_end
