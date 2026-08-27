from datetime import datetime

from pydantic import BaseModel, Field

from costs import (
    DEFAULT_COOLDOWN_BARS,
    DEFAULT_FEE_PCT,
    DEFAULT_MAX_POS_PCT,
    DEFAULT_SLIPPAGE_PCT,
)


class HmmRequest(BaseModel):
    sym: str
    startdate: datetime | None = None


class RegimeRequest(BaseModel):
    """What /regime actually needs.

    It used to borrow BacktestRequest, which forced the frontend to invent an
    `investment` and a `stra` purely to pass validation.
    """

    sym: str
    startdate: datetime


class BacktestRequest(BaseModel):
    investment: float = Field(gt=0, description="Starting capital, must be greater than 0")
    sym: str
    stra: str
    startdate: datetime
    auto_strategy: bool = False
    fee_pct: float = Field(default=DEFAULT_FEE_PCT, ge=0, le=100)
    slippage_pct: float = Field(default=DEFAULT_SLIPPAGE_PCT, ge=0, le=100)
    max_pos_pct: float = Field(default=DEFAULT_MAX_POS_PCT, gt=0, le=100)
    cooldown_bars: int = Field(default=DEFAULT_COOLDOWN_BARS, ge=0)
