import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pymysql
from .text import normalize_text
from .vars import DB_LOCATION


SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_LOCATION}"
# SQLALCHEMY_DATABASE_URL = "postgresql://user:password@postgresserver/db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


#SQLite's lower() only handles ASCII, so searches use this function instead (registered on every SQLite connection).
@event.listens_for(Engine, "connect")
def register_sqlite_functions(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function("ub_norm", 1, normalize_text, deterministic=True)


#Remove check same threat for mysql
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


Base = declarative_base()
