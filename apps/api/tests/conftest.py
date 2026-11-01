import os

os.environ.setdefault("ONEFINANCE_ENV", "test")
os.environ.setdefault("ONEFINANCE_DATABASE_URL", "postgresql+psycopg://onefinance:onefinance@localhost:5432/onefinance_test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, get_engine, session_factory  # noqa: E402
from app.seed import DEMO_EMAIL, DEMO_PASSWORD, seed_demo, seed_reference  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = session_factory()()
    seed_reference(db)
    seed_demo(db)
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    s = session_factory()()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def client():
    from app.main import app

    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = c.cookies.get("1f_csrf")
    return c


@pytest.fixture
def anon():
    from app.main import app

    return TestClient(app)
