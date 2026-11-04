"""
Test setup for the NutriScan API.

The EfficientNet model loads a checkpoint at import time, so it is replaced
with a stub. Firebase token checks are replaced with a fake verifier, so tests
never call Google, OpenAI, S3 or DynamoDB.
"""
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ["ADMIN_EMAIL"] = "admin@example.com"

fake_model_service = types.ModuleType("services.model_service")
fake_model_service.classifier = MagicMock()
sys.modules["services.model_service"] = fake_model_service

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from services import auth_service  # noqa: E402

USER_TOKEN = "user-token"
ADMIN_TOKEN = "admin-token"


async def _fake_verify_token(token: str) -> dict:
    if token == USER_TOKEN:
        return {"sub": "user-1", "email": "user@example.com"}
    if token == ADMIN_TOKEN:
        return {"sub": "admin-1", "email": "admin@example.com"}
    raise ValueError("bad token")


@pytest.fixture(autouse=True)
def _patch_auth(monkeypatch):
    monkeypatch.setattr(auth_service, "verify_token", _fake_verify_token)
    auth_service._calls.clear()
    yield
    auth_service._calls.clear()


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def user_headers():
    return {"Authorization": f"Bearer {USER_TOKEN}"}


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}
