from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Base
from app.main import create_app


@pytest.fixture
def app(tmp_path):
    application = create_app(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(application.state.engine)
    return application


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(app) -> Iterator[Session]:
    session = app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
