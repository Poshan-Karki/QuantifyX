from pydantic import BaseModel, Field
from datetime import datetime


class Symbol(BaseModel):
    syk:str
    


class Data(BaseModel):
    Symbol:str
    Date:datetime
    Open:float
    High:float
    Close:float
    Volume:float
    Return:float
    
class BacktestRequest(BaseModel):
    investment: float = Field(gt=0, description="Starting capital, must be greater than 0")
    sym: str
    stra: str
    startdate: datetime
    auto_strategy: bool = False
    fee_pct: float = Field(default=0.2, ge=0, le=100)
    slippage_pct: float = Field(default=0.1, ge=0, le=100)
    max_pos_pct: float = Field(default=20.0, gt=0, le=100)
    cooldown_bars: int = Field(default=3, ge=0)
