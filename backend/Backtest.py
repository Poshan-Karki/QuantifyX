from backtesting import Strategy
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from backtesting.lib import resample_apply

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
    

class bollinger_band(Strategy):
    def init(self):
        self.bb_upper, self.middle, self.lower = self.I(bbband, self.data.Close)
        
    def next(self):
        price = self.data.Close[-1]
        if price < self.lower[-1] and not self.position:
            self.buy()
        elif price > self.middle[-1] and self.position:
            self.position.close()

class macrossover(Strategy):
    def init(self):
        self.fast, self.slow = self.I(ma, self.data.Close)
        
    def next(self):
        if self.fast[-1] > self.slow[-1] and not self.position:
            self.buy()
        elif self.fast[-1] < self.slow[-1] and self.position:
            self.position.close()

class MeanReversion(Strategy):
    z_entry = 1.95
    def init(self):
        self.zscore = self.I(mean_reversion, self.data.Close)
        
    def next(self):
        if self.zscore[-1] < -self.z_entry and not self.position:
            self.buy()
        elif self.zscore[-1] > 0 and self.position:
            self.position.close()

class BollingerRsi(Strategy):
    rsi_lower = 35
    rsi_upper = 70 
    
    def init(self):
        self.bband_upper, self.bband_middle, self.lower = self.I(bbband, self.data.Close)
        self.rsi = self.I(get_rsi, self.data.Close)
        
    def next(self):
        price = self.data.Close[-1]
        
        
        if price <= self.lower[-1] and self.rsi[-1] <= self.rsi_lower:
            if not self.position:
                self.buy()
        
    
        elif self.position:
            
            if price >= self.bband_upper[-1] and self.rsi[-1] >= self.rsi_upper:
                self.position.close()
            
            
            elif price < self.bband_middle[-1] and self.rsi[-1] > 50:
                 self.position.close()
                 
                 
                 



def SMA(values, n):

    return pd.Series(values).rolling(n).mean()

class VolumeBreakout(Strategy):
    
    vol_period = 20
    entry_multiplier = 2.2
    exit_multiplier = 0.85

    def init(self):
        
        self.avg_vol = self.I(SMA, self.data.Volume, self.vol_period)
        self.bband_upper,self.bband_middle,self.bband_lower=self.I(bbband,self.data.Close
                                                                   )
        
    def next(self):
    
        current_vol = self.data.Volume[-1]
        avg_vol_now = self.avg_vol[-1]
        price = self.data.Close[-1]

        
        if price<=self.bband_lower and  current_vol > (self.exit_multiplier * avg_vol_now):
            if not self.position:
                self.buy(sl=0.95)
                
        
        elif self.position and price>=self.bband_middle and current_vol < (self.entry_multiplier * avg_vol_now):
            self.position.close()