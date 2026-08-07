"""Pytest fixtures."""

import os

# Force isolated ports / in-memory friendly defaults before app imports mutate caches
os.environ.setdefault("REDIS_PORT", "59999")
os.environ.setdefault("POSTGRES_PORT", "59998")
os.environ.setdefault("QDRANT_PORT", "59997")

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.memory.conversation import reset_memory_for_tests
from app.rag.vectorstores.factory import reset_vector_store


@pytest.fixture(autouse=True)
def _reset_singletons():
    get_settings.cache_clear()
    reset_memory_for_tests()
    reset_vector_store()
    yield
    reset_memory_for_tests()
    reset_vector_store()
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
