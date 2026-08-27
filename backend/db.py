import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Put your Postgres connection string in "
        "backend/.env as DATABASE_URL=postgresql://... for local development, "
        "or set it in your host's environment."
    )

# Pooled rather than NullPool. This backend runs as a long-lived uvicorn process,
# so a fresh connection per request meant a full TLS handshake on every call to a
# hosted Postgres. pool_pre_ping recycles connections the provider dropped while
# idle, which is the failure NullPool was papering over.
engine = create_engine(
    database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=300,
)

Sessionlocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)
