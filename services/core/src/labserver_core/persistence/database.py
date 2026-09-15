import sqlite3

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = sessionmaker[Session]


def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_engine_and_session_factory(
    database_url: str,
) -> tuple[Engine, SessionFactory]:
    engine = create_engine(database_url)
    if database_url.startswith("sqlite:"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    return engine, factory
