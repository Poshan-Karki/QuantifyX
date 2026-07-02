from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from sqlalchemy.pool import NullPool

load_dotenv()
datbase_url=os.getenv('DATABASE_URL')
engine=create_engine(
    datbase_url,
    poolclass=NullPool
    
)
Sessionlocal=sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)