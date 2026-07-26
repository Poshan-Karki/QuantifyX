from pydantic import BaseModel
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
    investment: float
    sym: str
    stra: str
    startdate: datetime
    auto_strategy: bool = False
    fee_pct: float = 0.2
    slippage_pct: float = 0.1
    max_pos_pct: float = 20.0
    cooldown_bars: int = 3
