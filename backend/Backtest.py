from backtesting import Strategy
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from backtesting.lib import crossover, resample_apply
from ta.trend import MACD, EMAIndicator
from ta.volatility import AverageTrueRange

def bbband(close, window=20, num_std=2):
    close = pd.Series(close)
    sma = close.rolling(window).mean()
    std = close.rolling(window).std() 
    upper = sma + (num_std * std)
    lower = sma - (num_std * std)
    return upper.values, sma.values, lower.values

def get_rsi(values, window=14):
    return RSIIndicator(close=pd.Series(values), window=window).rsi().values

def ma(close, fast=10, slow=25):
    close = pd.Series(close)
    fast_ma = close.rolling(fast).mean()
    slow_ma = close.rolling(slow).mean()
    return fast_ma.values, slow_ma.values

def mean_reversion(close, window=20):
    close = pd.Series(close)
    mean = close.rolling(window).mean()
    std = close.rolling(window).std()
    z = (close - mean) / std
    return z.values


def volume(volume,window=30):
    volume=pd.Series(volume)
    average_vol=volume.rolling(window).mean()
    return average_vol
    
def ema(close, window=50):
    close = pd.Series(close)
    return EMAIndicator(close=close, window=window).ema_indicator().values

def macd_indicator(close, fast=12, slow=26, signal=9):
    close = pd.Series(close)
    macd = MACD( close=close, window_fast=fast, window_slow=slow, window_sign=signal, )
    return (
        macd.macd().values,
        macd.macd_signal().values,
    )

def get_atr(high, low, close, window=14):
    high = pd.Series(high)
    low = pd.Series(low)
    close = pd.Series(close)
    atr = AverageTrueRange(
        high=high,
        low=low,
        close=close,
        window=window
    )
    return atr.average_true_range().values

def highest_high(high, window=20):
    high = pd.Series(high)
    return high.rolling(window).max().values

class BaseStrategy(Strategy):
    fee_pct = 0.2
    slippage_pct = 0.1
    max_pos_pct = 20.0
    cooldown_bars = 3

    def init(self):
        super().init()
        self._last_trade_bar = -1

    def _bar_index(self):
        return len(self.data)

    def _cooldown_ok(self):
        if self._last_trade_bar < 0:
            return True
        return (self._bar_index() - self._last_trade_bar) > self.cooldown_bars

    def _enter_long(self, sl=None):
        if not self._cooldown_ok():
            return
        size = min(max(self.max_pos_pct, 0), 100) / 100
        if size <= 0:
            return
        price = self.data.Close[-1]
        slip_price = price * (1 + self.slippage_pct / 100)
        stop_loss = sl if sl is not None else slip_price * 0.90
        self.buy(size=size, limit=slip_price, sl=stop_loss)
        self._last_trade_bar = self._bar_index()

class bollinger_band(BaseStrategy):
    def init(self):
        super().init()
        self.bb_upper, self.middle, self.lower = self.I(bbband, self.data.Close)
        
    def next(self):
        price = self.data.Close[-1]
        if price < self.lower[-1] and not self.position:
            self._enter_long()
        elif price > self.middle[-1] and self.position:
            self.position.close()

class macrossover(BaseStrategy):
    def init(self):
        super().init()
        self.fast, self.slow = self.I(ma, self.data.Close)
        
    def next(self):
        if self.fast[-1] > self.slow[-1] and not self.position:
            self._enter_long()
        elif self.fast[-1] < self.slow[-1] and self.position:
            self.position.close()

class MeanReversion(BaseStrategy):
    z_entry = 1.95
    def init(self):
        super().init()
        self.zscore = self.I(mean_reversion, self.data.Close)
        
    def next(self):
        if self.zscore[-1] < -self.z_entry and not self.position:
            self._enter_long()
        elif self.zscore[-1] > 0 and self.position:
            self.position.close()

class BollingerRsi(BaseStrategy):
    rsi_lower = 35
    rsi_upper = 70 
    
    def init(self):
        super().init()
        self.bband_upper, self.bband_middle, self.lower = self.I(bbband, self.data.Close)
        self.rsi = self.I(get_rsi, self.data.Close)
        
    def next(self):
        price = self.data.Close[-1]
        
        
        if price <= self.lower[-1] and self.rsi[-1] <= self.rsi_lower:
            if not self.position:
                self._enter_long()
        
    
        elif self.position:
            
            if price >= self.bband_upper[-1] and self.rsi[-1] >= self.rsi_upper:
                self.position.close()
            
            
            elif price < self.bband_middle[-1] and self.rsi[-1] > 50:
                 self.position.close()
                 





def SMA(values, n):

    return pd.Series(values).rolling(n).mean()

class VolumeBreakout(BaseStrategy):
    
    vol_period = 20
    entry_multiplier = 2.2
    exit_multiplier = 0.85

    def init(self):
        super().init()
        self.avg_vol = self.I(SMA, self.data.Volume, self.vol_period)
        self.bband_upper,self.bband_middle,self.bband_lower=self.I(bbband,self.data.Close)
        
    def next(self):
    
        current_vol = self.data.Volume[-1]
        avg_vol_now = self.avg_vol[-1]
        price = self.data.Close[-1]

        
        if price<=self.bband_lower[-1] and  current_vol > (self.exit_multiplier * avg_vol_now):
            if not self.position:
                stop_loss = price * 0.90      # Stop loss will be 10% below entry price 
                self._enter_long(sl=stop_loss)
                
        
        elif self.position and price>=self.bband_middle[-1] and current_vol < (self.entry_multiplier * avg_vol_now):
            self.position.close()

class MACDCross(BaseStrategy):
    fast = 12
    slow = 26
    signal = 9

    def init(self):
        super().init()
        self.macd, self.signal_line = self.I(macd_indicator, self.data.Close, self.fast, self.slow, self.signal)

    def next(self):
        if crossover(self.macd, self.signal_line) and not self.position:
            self._enter_long()
        elif crossover(self.signal_line, self.macd) and self.position:
            self.position.close()


class RSIMeanReversion(BaseStrategy):
    rsi_window = 14
    rsi_lower = 30
    rsi_upper = 70

    def init(self):
        super().init()
        self.rsi = self.I(get_rsi, self.data.Close, self.rsi_window)

    def next(self):
        if self.rsi[-1] < self.rsi_lower and not self.position:
            self._enter_long()
        elif self.rsi[-1] > self.rsi_upper and self.position:
            self.position.close()


class ATRBreakout(BaseStrategy):
    atr_window = 14
    atr_mult = 2.0
    ema_trend = 50
    lookback = 20

    def init(self):
        super().init()
        self.atr = self.I(get_atr, self.data.High, self.data.Low,
                          self.data.Close, self.atr_window)
        self.ema = self.I(ema, self.data.Close, self.ema_trend)
        self.highest = self.I(highest_high, self.data.High, self.lookback)

    def next(self):
        price = self.data.Close[-1]
        breakout = self.highest[-2]

        if (
            price > breakout
            and price > self.ema[-1]
            and not self.position
        ):
            stop_loss = price - self.atr_mult * self.atr[-1]
            self._enter_long(sl=stop_loss)

        elif self.position:
            if price < self.ema[-1]:
                self.position.close()