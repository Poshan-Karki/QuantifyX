
from dotenv import load_dotenv
import os
from typing import Annotated,List,TypedDict
import pandas as pd
from langgraph.graph import START,END
from langgraph.prebuilt import ToolNode,tools_condition
from langchain_groq import ChatGroq
from langchain_core import tools
from demo import pattern_finder,get_bollinger_triggers
from Backtest import BollingerRsi,bollinger_band,MeanReversion,macrossover
from backtesting import Backtest
from langchain.agent import create_agent 
from pydantic import BaseModel
from langgraph.prebuilt import create_react_agent


load_dotenv()

api_key=os.getenv("groq_api_key")
model="gpt-4o"

agent=create_agent(ChatGroq(model=model,api_key=api_key))

class input(BaseModel):
    investment:float
    debt:float
    intrest_rate:float
    time_period:int
    salary:float
    other_expenses:float
    stock_investment:float
    stock_name:str


class Output(BaseModel):
    summary:str

    

@tools
def BollingerRsi(inv,data):
    result=Backtest(BollingerRsi,cash=inv,commission=0)
    return result
    
@tools
def bollinger(data):
    result=get_bollinger_triggers(data)
    return data



    
    
