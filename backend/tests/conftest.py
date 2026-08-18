import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
import app.models  # noqa: F401  (populate Base.metadata)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db):
    """FastAPI TestClient wired to the same in-memory `db` session the
    test uses directly, via a get_db override. Only the auth/dashboard
    routes (app/channels/auth_web.py, doctor_dashboard.py,
    admin_dashboard.py, internal.py) use Depends(get_db) — every other
    channel uses SessionLocal() directly and isn't reachable through this
    fixture (see CLAUDE.md deviations for why that split is deliberate).
    """
    from app.main import app

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
