import pandas as pd
from ta.momentum import RSIIndicator


def pattern_finder(df):
    df['Vol_Avg30']=df['Volume'].rolling(30).mean()
    df['trigger']=df['Volume']>(df['Vol_Avg30']*3)
    triggers=df[df['trigger']==True].copy()
    result=[]
    for i in triggers.index:
        if i+10<len(df):
            price_now = df.loc[i, 'Close']
            price_future = df.loc[i+10, 'Close']
            outcome = ((price_future - price_now) / price_now) * 100
            result.append({"date": str(df.loc[i, 'Date']), "return": outcome,"rsi":rsi(df['Close'])})
            
    return result
    
    
    
    
def rsi(close):
    return RSIIndicator(close=pd.Series(close)).rsi()

import pandas as pd

def get_bollinger_triggers(df, window=20, num_std=2, horizon=5):
    
    df['middle_band'] = df['Close'].rolling(window=window).mean()
    std = df['Close'].rolling(window=window).std()
    df['upper_band'] = df['middle_band'] + (num_std * std)
    df['lower_band'] = df['middle_band'] - (num_std * std)
    
    df['bandwidth'] = (df['upper_band'] - df['lower_band']) / df['middle_band']
    
    signals = []
    
    for i in range(1, len(df)):
        signal_found = False
        signal_type = ""
        reason = ""
        

        if df['Close'].iloc[i-1] < df['lower_band'].iloc[i-1] and df['Close'].iloc[i] > df['lower_band'].iloc[i]:
            signal_found = True
            signal_type = "Bullish Reversal"
            reason = "Price pierced the Lower Band and closed back inside."

    
        elif df['bandwidth'].iloc[i] < df['bandwidth'].rolling(50).min().iloc[i]:
            signal_found = True
            signal_type = "Volatility Squeeze"
            reason = "Bands have tightened significantly. Expect a massive breakout soon."

        if signal_found:
            if i + horizon < len(df):
                price_at_signal = df['Close'].iloc[i]
                price_after_horizon = df['Close'].iloc[i + horizon]
            
                pct_return = ((price_after_horizon - price_at_signal) / price_at_signal) * 100
            else:
                pct_return = None  

            signals.append({
                "date": str(df.index[i]),
                "type": signal_type,
                "reason": reason,
                "price_at_signal": round(df['Close'].iloc[i], 2),
                f"return_{horizon}d_%": round(pct_return, 2) if pct_return is not None else "Pending"
            })
            
    return signals
    
    