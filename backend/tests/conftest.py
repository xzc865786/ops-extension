import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Force sqlite + bypass before app imports settings cache
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DEV_AUTH_BYPASS"] = "true"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["MINIO_ENDPOINT"] = "localhost:9000"

from app.config import get_settings

get_settings.cache_clear()

from app.auth.session import create_session, upsert_extension_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app
import app.db.models  # noqa: F401


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db(db_engine):
    Session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    Session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)

    def _override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = _override
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


def make_user(db, *, sub2api_id: int, role: str = "user", username: str = "u"):
    return upsert_extension_user(
        db,
        sub2api_user_id=sub2api_id,
        username=username,
        email=f"{username}@example.com",
        role=role,
    )


def login_as(client, db, user):
    sess = create_session(db, user)
    client.cookies.set("ops_session", str(sess.id), path="/ext")
    return sess
