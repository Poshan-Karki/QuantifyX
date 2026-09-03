"""Study configuration (design section 10).

Every sweep is a config file rather than an edited constant, and every output
row carries the hash of the config that produced it, so any figure in the paper
can be traced back to the exact parameters behind it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from costs import (
    DEFAULT_COOLDOWN_BARS,
    DEFAULT_FEE_PCT,
    DEFAULT_MAX_POS_PCT,
    DEFAULT_SLIPPAGE_PCT,
)

from .execution import STRATEGY_NAMES, TradeParams
from regime.features import DEFAULT_FEATURES
from regime.hmm_regime import DEFAULT_N_COMPONENTS
from .walkforward import ANCHORED

ARM_BUY_HOLD = "A0"
ARM_RULE = "A2"
ARM_HMM_LEAKED = "B1"
ARM_HMM_FIT_LEAKED = "B2"
ARM_HMM_HONEST = "B3"

#: Arms that fix a single strategy for the whole study, one per pool member.
FIXED_ARMS = tuple(f"A1:{name}" for name in STRATEGY_NAMES)

HMM_ARMS = (ARM_HMM_LEAKED, ARM_HMM_FIT_LEAKED, ARM_HMM_HONEST)
ALL_ARMS = (ARM_BUY_HOLD,) + FIXED_ARMS + (ARM_RULE,) + HMM_ARMS


@dataclass
class StudyConfig:
    """One reproducible run of the harness."""

    run_id: str = "baseline"
    data_path: str = "research/data/nepse_snapshot.csv.gz"
    output_dir: str = "research/results"
    symbols: list[str] | None = None

    # Walk-forward protocol (4.5)
    scheme: str = ANCHORED
    train_bars: int = 750
    test_bars: int = 60
    #: Contiguous train -> test by default. The gap is not needed to prevent
    #: leakage here (no forward-looking label exists to purge) and it aged the
    #: regime label by its own width. Kept as a knob so the previous design is
    #: reproducible -- see configs/ablation_embargo.yaml and walkforward.py.
    embargo_bars: int = 0
    step: int | None = None
    #: Longest indicator lookback in the strategy pool (ATRBreakout's 50-bar
    #: EMA), rounded up. Warm-up runs backwards from test_start and may cross
    #: into training bars: reading a bar's own past is causal, and warm-up bars
    #: are neither fitted on nor scored.
    warmup_bars: int = 60

    # Features (4.2)
    features: list[str] = field(default_factory=lambda: list(DEFAULT_FEATURES))
    vol_window: int = 60
    winsor_lower: float = 0.01
    winsor_upper: float = 0.99

    # HMM (4.2)
    n_components: list[int] = field(default_factory=lambda: list(DEFAULT_N_COMPONENTS))
    covariance_type: str = "full"
    n_iter: int = 200
    tol: float = 1e-4
    restarts: int = 10

    # Execution (4.6) -- defaults shared with the API, see backend/costs.py
    cash: float = 100_000.0
    fee_pct: float = DEFAULT_FEE_PCT
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT
    max_pos_pct: float = DEFAULT_MAX_POS_PCT
    cooldown_bars: int = DEFAULT_COOLDOWN_BARS

    # Universe inclusion (3.2)
    min_bars: int = 1500
    min_median_volume: float = 0.0
    min_folds: int = 3

    # Statistics (6)
    bootstrap_resamples: int = 2000
    bootstrap_mean_block: float = 20.0

    arms: list[str] = field(default_factory=lambda: list(ALL_ARMS))
    seed: int = 20260822

    def __post_init__(self) -> None:
        unknown = set(self.arms) - set(ALL_ARMS)
        if unknown:
            raise ValueError(f"unknown arm(s): {sorted(unknown)}; known: {list(ALL_ARMS)}")
        if self.warmup_bars < 0:
            raise ValueError(f"warmup_bars must be non-negative, got {self.warmup_bars}")
        if self.warmup_bars >= self.train_bars:
            raise ValueError(
                f"warmup_bars ({self.warmup_bars}) is not shorter than train_bars "
                f"({self.train_bars}). Warm-up runs backwards from the test window and "
                "would reach past the start of the series on the first fold."
            )
        if not self.features:
            raise ValueError("at least one feature is required")

    @property
    def trade_params(self) -> TradeParams:
        return TradeParams(
            cash=self.cash,
            fee_pct=self.fee_pct,
            slippage_pct=self.slippage_pct,
            max_pos_pct=self.max_pos_pct,
            cooldown_bars=self.cooldown_bars,
        )

    @property
    def hmm_kwargs(self) -> dict:
        return {
            "covariance_type": self.covariance_type,
            "n_iter": self.n_iter,
            "tol": self.tol,
            "restarts": self.restarts,
        }

    def to_dict(self) -> dict:
        return asdict(self)

    def config_hash(self) -> str:
        """Stable short hash of every field, recorded on each output row."""
        payload = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StudyConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        unknown = set(data) - {f for f in cls.__dataclass_fields__}
        if unknown:
            raise ValueError(f"unknown config key(s) in {path}: {sorted(unknown)}")
        return cls(**data)

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps({"config_hash": self.config_hash(), **self.to_dict()}, indent=2, default=str),
            encoding="utf-8",
        )


def derive_seed(base_seed: int, *parts: object) -> int:
    """Deterministic per-unit seed.

    Built on hashlib rather than hash(), whose string hashing is salted per
    process -- results would not reproduce across runs.
    """
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return (base_seed + int(digest[:8], 16)) % (2**31 - 1)
