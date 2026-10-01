from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def test_health(tmp_path):
    client = TestClient(create_app(make_settings(tmp_path)))
    assert client.get("/health").json() == {"status": "ok"}
