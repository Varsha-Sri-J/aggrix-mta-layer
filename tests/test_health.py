"""
Unit and Integration Tests for AGGRIX Health & Root Endpoints
"""

import os
import sys
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

# Ensure backend directory is in Python path for test discovery
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database.connection import check_db_connection, get_db
from app.main import app


# In-memory SQLite engine for executing real SELECT 1 queries during tests
test_engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db_healthy():
    """Dependency override providing an active SQLite in-memory session (executes SELECT 1)."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_get_db_unhealthy():
    """Dependency override simulating database connection failure."""
    mock_session = MagicMock()
    mock_session.execute.side_effect = OperationalError(
        statement="SELECT 1",
        params={},
        orig=Exception("could not connect to server: Connection refused"),
    )
    try:
        yield mock_session
    finally:
        pass


@pytest.fixture
def client():
    """Default test client with standard dependency overrides."""
    app.dependency_overrides[get_db] = override_get_db_healthy
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestRootEndpoint:
    """Tests for GET / application root metadata endpoint."""

    def test_root_returns_200_and_metadata(self, client: TestClient):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "AGGRIX MTA Layer"
        assert data["status"] == "running"
        assert "version" in data
        assert "docs_url" in data


class TestHealthEndpoint:
    """Tests for GET /health service and database connectivity check."""

    def test_health_check_healthy(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert data["error"] is None

    def test_health_check_unhealthy(self):
        # Override with failure dependency
        app.dependency_overrides[get_db] = override_get_db_unhealthy
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["database"] == "disconnected"
            assert "could not connect" in data["error"]
        app.dependency_overrides.clear()

    def test_versioned_health_check(self, client: TestClient):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"


class TestDatabaseConnectionHelper:
    """Direct unit tests for check_db_connection function."""

    def test_check_db_connection_success(self):
        db = TestingSessionLocal()
        try:
            is_connected, error = check_db_connection(db)
            assert is_connected is True
            assert error is None
        finally:
            db.close()

    def test_check_db_connection_failure(self):
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Simulated DB connection timeout")
        is_connected, error = check_db_connection(mock_db)
        assert is_connected is False
        assert "Simulated DB connection timeout" in error
