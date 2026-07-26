from fastapi import FastAPI,Depends
from db import Sessionlocal
from schema import Symbol
from sqlalchemy.orm import Session
from sqlalchemy import text
import pandas as pd
from schema import Data
from Backtest import bollinger_band
from backtesting import Backtest
import numpy as np
import math
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from schema import BacktestRequest
from Backtest import macrossover,MeanReversion,BollingerRsi,VolumeBreakout, MACDCross, RSIMeanReversion, ATRBreakout
from market_regime import detect_regime
from verdict import generate_verdict
from analysis_split import chronological_holdout, period_details
from market_context import build_contextual_verdict, resolve_market_context





app=FastAPI()

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,             
    allow_credentials=True,
    allow_methods=["*"],               
    allow_headers=["*"],               
)
def get_db():
    db=Sessionlocal()
    try:
        yield db
    finally:
        db.close()
        

 
@app.get("/")
def root():
    return {"message": "API is running"}



@app.get('/hydroname')
def get_hydro_name(db:Session=Depends(get_db)):
    query=text('SELECT "Symbol" FROM nepseintel  GROUP BY "Symbol"') 
    result=db.execute(query).fetchall()
    if not result:
        return {"status":"fail","message":"no data found"}
    
    df=pd.DataFrame(result,columns=['Symbol'])
    return df.to_dict(orient="records")
       
        
@app.post("/gethydro")
def get_hydro_data(sym:str,db:Session=Depends(get_db)):
    symbol=sym.upper()
    query=text('SELECT "Symbol","Open","High","Low","Close","Vol","Date" FROM nepseintel WHERE "Symbol" = :symbol ORDER BY "date"')
    result=db.execute(query,{"symbol":symbol}).fetchall()
    if  not result:
       return {"status": "fail", "message": "No data found"}
   
    df=pd.DataFrame(result,columns=['Symbol','Open','High','low','Close','Volume',"Date"])
    return df.to_dict(orient="records")
   

def deep_sanitize(obj):
    if isinstance(obj, dict):
        return {k: deep_sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
    
        return [deep_sanitize(i) for i in obj]
    elif isinstance(obj, (float, np.floating)):
        return float(obj) if math.isfinite(obj) else None
    elif isinstance(obj, (int, np.integer)):
        return int(obj)
    elif isinstance(obj, (pd.Timestamp, pd.Timedelta)):
        return str(obj)
    return obj
def apply_trade_params(strategy_cls, req):
    strategy_cls.fee_pct = req.fee_pct
    strategy_cls.slippage_pct = req.slippage_pct
    strategy_cls.max_pos_pct = req.max_pos_pct
    strategy_cls.cooldown_bars = req.cooldown_bars
    

@app.post("/bbband")
def test_bollinger(data: BacktestRequest, db: Session = Depends(get_db)):
    symbol1 = data.sym.upper()
    

    query = text(
        'SELECT "Date", "Open", "High", "Low", "Close", "Vol" '
        'FROM nepseintel WHERE "Symbol" = :symbol and "Date">=:date ORDER BY "Date"'
    )
    result = db.execute(query, {"symbol": symbol1,"date":data.startdate}).fetchall()
    
    if not result:
        return {"status": "fail", "message": "No data found for symbol"}

    df = pd.DataFrame(result, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    df[['Open', 'High', 'Low', 'Close', 'Volume']] = \
    df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
    
    strategies = {
        "Bollinger Band": bollinger_band,
        "Moving Average Crossover": macrossover,
        "Mean Reversion": MeanReversion,
        "Bollinger+Rsi":BollingerRsi,
        "VolumeBreakout":VolumeBreakout,
        "MACD Cross": MACDCross,
        "RSI Mean Reversion": RSIMeanReversion,
        "ATR Breakout": ATRBreakout
    }

    try:
        current_regime = detect_regime(df)
    except Exception:
        current_regime = None

    strategy_name = data.stra
    backtest_df = df
    selection_regime = None
    evaluation = {
        "mode": "full_period",
        "selected_strategy": strategy_name,
        "selection_basis": "User-selected strategy",
        "evaluation_period": period_details(df),
    }

    if data.auto_strategy:
        try:
            training_df, backtest_df = chronological_holdout(df)
            selection_regime = detect_regime(training_df)
        except ValueError as exc:
            return {"status": "fail", "message": str(exc)}
        except Exception:
            return {
                "status": "fail",
                "message": (
                    "The strategy selection period could not produce a reliable market regime. "
                    "Choose an earlier start date or turn off Auto Strategy."
                ),
            }

        recommended = selection_regime.get("recommended_strategies", [])
        if not recommended:
            return {
                "status": "fail",
                "message": "No strategy recommendation was available for the training period.",
            }

        strategy_name = recommended[0]
        evaluation = {
            "mode": "out_of_sample",
            "selected_strategy": strategy_name,
            "selection_basis": (
                f"Selected from the earlier '{selection_regime['regime']}' market regime"
            ),
            "training_period": period_details(training_df),
            "evaluation_period": period_details(backtest_df),
        }

    strategy_select = strategies.get(strategy_name)
    if not strategy_select:
        return {"status": "fail", "message": "Invalid strategy selected"}

    apply_trade_params(strategy_select, data)

    bt = Backtest(
    backtest_df,
    strategy_select,
    cash=data.investment,
    commission=data.fee_pct / 100,
    finalize_trades=True
    )
    stats = bt.run()
    trades_list = []
    if '_trades' in stats and not stats['_trades'].empty:
    
             df_trades = stats['_trades'].copy()
    

             df_trades['EntryTime'] = df_trades['EntryTime'].dt.strftime('%Y-%m-%d')
             df_trades['ExitTime'] = df_trades['ExitTime'].dt.strftime('%Y-%m-%d')
    
    
             trades_list = df_trades.to_dict(orient='records')
    
    ohlc_data = []
    for index, row in backtest_df.iterrows():
        ohlc_data.append({
            "time": index.strftime('%Y-%m-%d'),
            "open": row['Open'],
            "high": row['High'],
            "low": row['Low'],
            "close": row['Close'],
        })

    
    raw_response = {
        "summary": {
            "Start Cash": data.investment,
            "Final Equity": stats['Equity Final [$]'],
            "Return [%]": stats['Return [%]'],
            "Buy & Hold Return [%]": stats['Buy & Hold Return [%]'],
            "Max Drawdown [%]": stats['Max. Drawdown [%]'],
            "Total Trades": stats['# Trades'],
            "Win Rate [%]": stats['Win Rate [%]'],
            "Sharpe Ratio": float(stats['Sharpe Ratio']),
        },
        "ohlc": ohlc_data,
        "trades": trades_list,
        "evaluation": evaluation,
    }
    raw_response["verdict"] = generate_verdict(stats, strategy_name, current_regime)
    raw_response["regime"] = current_regime
    raw_response["selection_regime"] = selection_regime
    raw_response["market_context"] = resolve_market_context(symbol1)
    raw_response["contextual_verdict"] = build_contextual_verdict(
        raw_response["verdict"],
        raw_response["market_context"]["items"],
    )


    if strategy_name == "Bollinger Band":
        raw_response["indicators"] = {
            "upper": stats['_strategy'].bb_upper.tolist(),
            "middle": stats['_strategy'].middle.tolist(),
            "lower": stats['_strategy'].lower.tolist()
        }
    elif strategy_name == "Moving Average Crossover":
        raw_response["indicators"] = {
            "fast_ma": stats['_strategy'].fast.tolist(),
            "slow_ma": stats['_strategy'].slow.tolist()
        }
    elif strategy_name == "Mean Reversion":
        raw_response["indicators"] = {
            "zscore": stats['_strategy'].zscore.tolist()
        }
    elif strategy_name == "Bollinger+Rsi":
        raw_response["indicators"] = {
            "upper": stats['_strategy'].bband_upper.tolist(),
            "middle": stats['_strategy'].bband_middle.tolist(),
            "lower": stats['_strategy'].lower.tolist()
        }
    elif strategy_name == "VolumeBreakout":
        raw_response["indicators"] = {
            "average_vol":stats["_strategy"].avg_vol.tolist()
        }
    elif strategy_name == "MACD Cross":
        raw_response["indicators"] = {
            "macd": stats['_strategy'].macd.tolist(),
            "signal": stats['_strategy'].signal_line.tolist()
        }
    elif strategy_name == "RSI Mean Reversion":
        raw_response["indicators"] = {
            "rsi": stats['_strategy'].rsi.tolist()
        }
    elif strategy_name == "ATR Breakout":
        raw_response["indicators"] = {
        "atr": stats["_strategy"].atr.tolist(),
        "ema": stats["_strategy"].ema.tolist(),
        "highest": stats["_strategy"].highest.tolist()
    }

    return jsonable_encoder(deep_sanitize(raw_response))


@app.post('/chat')
def chat(data:  Symbol,cash2:float,db:Session=Depends(get_db)):
    query=text('SELECT "Open","High","Low","Close","Vol","Date" FROM nepseintel where "Symbol" =:symbol ORDER BY "date"')
    result=db.execute(query,{"symbol":data.sym})
    
    if not result:
        return {"status": "fail", "message": "No data found for symbol"}

    df = pd.DataFrame(result, columns=[ 'Open', 'High', 'Low', 'Close', 'Volume',"Date"])
    initial_input={
        "ticker":data.syk,
        "raw_data":df.to_dict(orient='records'),
        "cash":cash2
    }
    
@app.post("/regime")
def get_regime(data: BacktestRequest, db: Session = Depends(get_db)):
    symbol = data.sym.upper()
    query = text(
        'SELECT "Date","Open","High","Low","Close","Vol" '
        'FROM nepseintel WHERE "Symbol" = :symbol AND "Date" >= :date ORDER BY "Date"'
    )
    result = db.execute(query, {"symbol": symbol, "date": data.startdate}).fetchall()

    if not result:
        return {"status": "fail", "message": "No data found"}

    df = pd.DataFrame(result, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df.set_index("Date", inplace=True)
    df[["Open", "High", "Low", "Close", "Volume"]] = \
        df[["Open", "High", "Low", "Close", "Volume"]].astype(float)

    regime_data = detect_regime(df)
    return jsonable_encoder(deep_sanitize(regime_data))
    
@app.post('/hmm')
async def hmm_learn(symbol:Symbol,db:Session=Depends(get_db)):
    query=text('SELECT "Open","High","Close","Low","Vol","Date" FROM nepseintel WHERE "Symbol"=:symbol ORDER BY "Date"')
    print(query.text)
    result=db.execute(query,{"symbol":symbol.syk.upper()}).fetchall()
    print(result)
    if not result:
        return {"status":"fail no data"}
    df=pd.DataFrame(result,columns=['Open','High','Close','Low','Vol','Date'])
    df['log_return']=np.log(df['Close']/df['Close'].shift(1))
    df['hl_spread']=(df['High']-df['Low'])/df['Open']
    df['volume_change']=df['Vol'].pct_change()
    df.dropna(inplace=True)
    features=df[['log_return','hl_spread','volume_change']]
    scaler=StandardScaler()
    X=scaler.fit_transform(features)
    model=GaussianHMM(
        n_components=3,
        covariance_type='full',
        n_iter=200
    )
    model.fit(X)
    states =model.predict(X)
    current_state = int(states[-1])


    tomorrow_probs = model.transmat_[current_state]

    tomorrow_state = int(np.argmax(tomorrow_probs))

    return {
        "status": "success",
        "states": states.tolist(),
        "current_state": current_state,
        "tomorrow_state": tomorrow_state,
        "tomorrow_probabilities": tomorrow_probs.tolist()
    }
