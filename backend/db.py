from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from sqlalchemy.pool import NullPool

load_dotenv()
datbase_url=os.getenv('DATABASE_URL')
if not datbase_url:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "for local development, or set it in your host's environment."
    )
engine=create_engine(
    datbase_url,
    poolclass=NullPool

)
Sessionlocal=sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)