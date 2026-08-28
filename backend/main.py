import logging
import math
import os
import threading
import time
from datetime import date

import numpy as np
import pandas as pd
from backtesting import Backtest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from analysis_split import chronological_holdout, period_details
from Backtest import (
    ATRBreakout,
    BollingerRsi,
    MACDCross,
    MeanReversion,
    RSIMeanReversion,
    VolumeBreakout,
    bollinger_band,
    macrossover,
)
from costs import DEFAULT_TRADE_PARAMS, commission_fraction
from db import Sessionlocal
from hmm_service import describe_regime
from market_context import build_contextual_verdict, resolve_market_context
from market_regime import detect_regime
from ratelimit import RateLimit
from schema import BacktestRequest, HmmRequest, RegimeRequest
from verdict import generate_verdict

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)
LOGGER = logging.getLogger("quantifyx.api")

app = FastAPI(title="QuantifyX API")

DEFAULT_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
]

origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", ",".join(DEFAULT_DEV_ORIGINS)).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """One line per request with its duration.

    The analytical endpoints take seconds, not milliseconds, and without this
    there was no way to tell a slow fit from a hung one after the fact.
    """
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        LOGGER.exception(
            "%s %s -> unhandled error in %.0fms", request.method, request.url.path, elapsed_ms
        )
        raise

    elapsed_ms = (time.perf_counter() - started) * 1000
    log = LOGGER.warning if elapsed_ms > 5000 else LOGGER.info
    log(
        "%s %s -> %s in %.0fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def get_db():
    db = Sessionlocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def root():
    return {"message": "API is running"}


@app.get("/defaults")
def trade_parameter_defaults():
    """The trade parameters the UI should start from.

    Served rather than duplicated in the frontend, which is how the form ended
    up defaulting to a cheaper, all-in configuration than the backend declared.
    """
    return DEFAULT_TRADE_PARAMS


@app.get("/data-status")
def data_status(db: Session = Depends(get_db)):
    query = text(
        'SELECT MIN("Date") AS earliest, MAX("Date") AS latest, '
        'COUNT(DISTINCT "Symbol") AS symbol_count FROM nepseintel'
    )
    row = db.execute(query).fetchone()
    if not row or row.latest is None:
        raise HTTPException(status_code=404, detail="No price data is loaded.")

    return {
        "earliest_date": str(row.earliest.date() if hasattr(row.earliest, "date") else row.earliest),
        "latest_date": str(row.latest.date() if hasattr(row.latest, "date") else row.latest),
        "symbol_count": row.symbol_count,
    }


# The symbol list changes at most once a day, but was being recomputed with a
# full GROUP BY over the price table on every page load.
_symbol_cache: dict = {"day": None, "symbols": None}
_symbol_cache_lock = threading.Lock()


def _load_symbols(db: Session) -> list[dict]:
    result = db.execute(text('SELECT DISTINCT "Symbol" FROM nepseintel ORDER BY "Symbol"')).fetchall()
    return [{"Symbol": row[0]} for row in result]


@app.get("/hydroname")
def get_hydro_name(db: Session = Depends(get_db)):
    today = date.today()
    with _symbol_cache_lock:
        if _symbol_cache["day"] == today and _symbol_cache["symbols"] is not None:
            return _symbol_cache["symbols"]

    symbols = _load_symbols(db)
    if not symbols:
        raise HTTPException(status_code=404, detail="No symbols are loaded.")

    with _symbol_cache_lock:
        _symbol_cache["day"] = today
        _symbol_cache["symbols"] = symbols
    return symbols


@app.get("/symbols/{sym}/candles")
def get_hydro_data(sym: str, db: Session = Depends(get_db)):
    """Raw OHLCV for one symbol.

    Was POST /gethydro with the symbol in the query string, which described a
    read as a write.
    """
    symbol = sym.upper()
    query = text(
        'SELECT "Symbol","Open","High","Low","Close","Vol","Date" FROM nepseintel '
        'WHERE "Symbol" = :symbol ORDER BY "Date"'
    )
    result = db.execute(query, {"symbol": symbol}).fetchall()
    if not result:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}.")

    df = pd.DataFrame(
        result,
        columns=["Symbol", "Open", "High", "Low", "Close", "Volume", "Date"],
    )
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


def configure_strategy(strategy_cls, req):
    """Return a throwaway subclass carrying this request's sizing parameters.

    Deliberately does not touch strategy_cls. The strategy classes in
    Backtest.py are module-level singletons shared by every request, and
    /bbband is a sync endpoint that FastAPI runs in a threadpool, so writing
    parameters onto the class lets two overlapping requests run each other's
    position sizes. Subclassing keeps each request's parameters to itself and
    leaves the declared defaults intact.

    Only sizing lives here. Fees and slippage are charged together as the
    Backtest commission -- see costs.commission_fraction.
    """
    return type(
        strategy_cls.__name__,
        (strategy_cls,),
        {
            "max_pos_pct": req.max_pos_pct,
            "cooldown_bars": req.cooldown_bars,
        },
    )


def _load_ohlcv(db: Session, symbol: str, startdate) -> pd.DataFrame:
    """Ordered OHLCV for a symbol from a start date, as a float DatetimeIndex frame."""
    query = text(
        'SELECT "Date", "Open", "High", "Low", "Close", "Vol" '
        'FROM nepseintel WHERE "Symbol" = :symbol AND "Date" >= :date ORDER BY "Date"'
    )
    result = db.execute(query, {"symbol": symbol, "date": startdate}).fetchall()
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {symbol} from that start date.",
        )

    df = pd.DataFrame(result, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df.set_index("Date", inplace=True)
    df[["Open", "High", "Low", "Close", "Volume"]] = df[
        ["Open", "High", "Low", "Close", "Volume"]
    ].astype(float)
    return df


@app.post("/bbband", dependencies=[Depends(RateLimit("30/minute"))])
def run_backtest(data: BacktestRequest, db: Session = Depends(get_db)):
    symbol1 = data.sym.upper()
    df = _load_ohlcv(db, symbol1, data.startdate)

    strategies = {
        "Bollinger Band": bollinger_band,
        "Moving Average Crossover": macrossover,
        "Mean Reversion": MeanReversion,
        "Bollinger+Rsi": BollingerRsi,
        "VolumeBreakout": VolumeBreakout,
        "MACD Cross": MACDCross,
        "RSI Mean Reversion": RSIMeanReversion,
        "ATR Breakout": ATRBreakout,
    }

    # Advisory only -- the verdict mentions it, nothing depends on it, so a
    # window too short to classify should not fail the backtest.
    try:
        current_regime = detect_regime(df)
    except ValueError:
        current_regime = None
    except Exception:
        LOGGER.exception("Unexpected failure detecting regime for %s", symbol1)
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
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            LOGGER.exception("Auto strategy selection failed for %s", symbol1)
            raise HTTPException(
                status_code=422,
                detail=(
                    "The strategy selection period could not produce a reliable market "
                    "regime. Choose an earlier start date or turn off Auto Strategy."
                ),
            ) from exc

        recommended = selection_regime.get("recommended_strategies", [])
        if not recommended:
            raise HTTPException(
                status_code=422,
                detail="No strategy recommendation was available for the training period.",
            )

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
        raise HTTPException(status_code=422, detail=f"Unknown strategy: {strategy_name!r}")

    strategy_select = configure_strategy(strategy_select, data)

    try:
        commission = commission_fraction(data.fee_pct, data.slippage_pct)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    bt = Backtest(
        backtest_df,
        strategy_select,
        cash=data.investment,
        commission=commission,
        finalize_trades=True,
    )
    stats = bt.run()
    trades_list = []
    if "_trades" in stats and not stats["_trades"].empty:
        df_trades = stats["_trades"].copy()
        df_trades["EntryTime"] = df_trades["EntryTime"].dt.strftime("%Y-%m-%d")
        df_trades["ExitTime"] = df_trades["ExitTime"].dt.strftime("%Y-%m-%d")
        trades_list = df_trades.to_dict(orient="records")

    ohlc_data = []
    for index, row in backtest_df.iterrows():
        ohlc_data.append(
            {
                "time": index.strftime("%Y-%m-%d"),
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
            }
        )

    raw_response = {
        "summary": {
            "Start Cash": data.investment,
            "Final Equity": stats["Equity Final [$]"],
            "Return [%]": stats["Return [%]"],
            "Buy & Hold Return [%]": stats["Buy & Hold Return [%]"],
            "Max Drawdown [%]": stats["Max. Drawdown [%]"],
            "Total Trades": stats["# Trades"],
            "Win Rate [%]": stats["Win Rate [%]"],
            "Sharpe Ratio": float(stats["Sharpe Ratio"]),
        },
        "costs": {
            "fee_pct": data.fee_pct,
            "slippage_pct": data.slippage_pct,
            "total_cost_pct": commission * 100,
            "basis": (
                "Fee and slippage are charged together on entry and again on exit. "
                "Entries fill at the next bar's open."
            ),
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
            "upper": stats["_strategy"].bb_upper.tolist(),
            "middle": stats["_strategy"].middle.tolist(),
            "lower": stats["_strategy"].lower.tolist(),
        }
    elif strategy_name == "Moving Average Crossover":
        raw_response["indicators"] = {
            "fast_ma": stats["_strategy"].fast.tolist(),
            "slow_ma": stats["_strategy"].slow.tolist(),
        }
    elif strategy_name == "Mean Reversion":
        raw_response["indicators"] = {
            "zscore": stats["_strategy"].zscore.tolist()
        }
    elif strategy_name == "Bollinger+Rsi":
        raw_response["indicators"] = {
            "upper": stats["_strategy"].bband_upper.tolist(),
            "middle": stats["_strategy"].bband_middle.tolist(),
            "lower": stats["_strategy"].lower.tolist(),
        }
    elif strategy_name == "VolumeBreakout":
        raw_response["indicators"] = {
            "average_vol": stats["_strategy"].avg_vol.tolist()
        }
    elif strategy_name == "MACD Cross":
        raw_response["indicators"] = {
            "macd": stats["_strategy"].macd.tolist(),
            "signal": stats["_strategy"].signal_line.tolist(),
        }
    elif strategy_name == "RSI Mean Reversion":
        raw_response["indicators"] = {
            "rsi": stats["_strategy"].rsi.tolist()
        }
    elif strategy_name == "ATR Breakout":
        raw_response["indicators"] = {
            "atr": stats["_strategy"].atr.tolist(),
            "ema": stats["_strategy"].ema.tolist(),
            "highest": stats["_strategy"].highest.tolist(),
        }

    return jsonable_encoder(deep_sanitize(raw_response))


@app.post("/regime", dependencies=[Depends(RateLimit("60/minute"))])
def get_regime(data: RegimeRequest, db: Session = Depends(get_db)):
    symbol = data.sym.upper()
    df = _load_ohlcv(db, symbol, data.startdate)

    try:
        regime_data = detect_regime(df)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return jsonable_encoder(deep_sanitize(regime_data))


@app.post("/hmm", dependencies=[Depends(RateLimit("10/minute"))])
def hmm_learn(data: HmmRequest, db: Session = Depends(get_db)):
    """Hidden-Markov regime detection for one symbol.

    Sync rather than async on purpose: this does a blocking database read and a
    CPU-bound fit, both of which would stall the event loop in an async def.
    FastAPI runs a sync endpoint in a threadpool instead.

    Rate limited harder than the other endpoints because an uncached symbol
    costs seconds of CPU.
    """
    symbol = data.sym.upper()
    query = 'SELECT "Date","Open","High","Low","Close","Vol" FROM nepseintel WHERE "Symbol" = :symbol'
    params = {"symbol": symbol}
    if data.startdate is not None:
        query += ' AND "Date" >= :date'
        params["date"] = data.startdate
    query += ' ORDER BY "Date"'

    result = db.execute(text(query), params).fetchall()
    if not result:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}.")

    df = pd.DataFrame(result, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df.set_index("Date", inplace=True)
    df[["Open", "High", "Low", "Close", "Volume"]] = df[
        ["Open", "High", "Low", "Close", "Volume"]
    ].astype(float)

    try:
        payload = describe_regime(symbol, df)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return jsonable_encoder(deep_sanitize(payload))
