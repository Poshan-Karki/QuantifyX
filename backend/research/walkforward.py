"""Walk-forward fold generation (design section 4.5).

Generalises analysis_split.chronological_holdout from a single 70/30 split into
repeated train/test folds separated by an embargo gap.

The embargo exists so that no test bar shares a rolling indicator window with a
training bar. It is not dead space: bars in the embargo are the warm-up for the
indicators evaluated during the test window, which is legitimate because at
trading time t you genuinely know the bars immediately before t. What embargo
bars are never used for is fitting anything, or scoring anything.
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
    [train_end, test_start)   embargo -- indicator warm-up only, never fitted
    [test_start, test_end)    evaluated out of sample, never fitted
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
    def train_slice(self) -> slice:
        return slice(self.train_start, self.train_end)

    @property
    def test_slice(self) -> slice:
        return slice(self.test_start, self.test_end)

    def execution_slice(self, warmup_bars: int) -> slice:
        """Bars to feed the backtester so test-window indicators are warm.

        Starts warmup_bars before the test window -- inside the embargo, which is
        sized to cover exactly this. Only returns from test_start onward are
        scored; see metrics.trim_to_test.
        """
        if warmup_bars > self.embargo_bars:
            raise ValueError(
                f"warmup_bars ({warmup_bars}) exceeds the embargo ({self.embargo_bars}). "
                "Widen embargo_bars so indicator warm-up cannot reach into training data."
            )
        return slice(self.test_start - warmup_bars, self.test_end)


def generate_folds(
    n_bars: int,
    scheme: str = ANCHORED,
    train_bars: int = 750,
    test_bars: int = 60,
    embargo_bars: int = 60,
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


def required_bars(train_bars: int, test_bars: int, embargo_bars: int, min_folds: int = 1) -> int:
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
