import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import get_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    test_db_path = str(tmp_path / "test_podmentor.db")
    test_settings = Settings(
        app_name="podmentor",
        environment="test",
        database_path=test_db_path,
        primary_model="gemini-1.5-flash",
        fallback_model="gemini-1.5-flash-8b",
    )
    app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    get_db(test_db_path).clear_all()
