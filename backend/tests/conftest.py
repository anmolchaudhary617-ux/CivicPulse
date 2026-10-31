import io
import json
import os
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

with patch.dict(os.environ, {"PYTHON_DOTENV_DISABLED": "1"}):
    from app import main as api


_REAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture
def analysis_payload():
    return {
        "issue_type": "Pothole",
        "severity": "Medium",
        "title": "Road surface damage",
        "description": "A visible depression in the road surface.",
        "evidence": ["A rough-edged depression is visible"],
        "department": "Road Maintenance",
        "confidence": 0.81,
        "limitations": ["Depth cannot be established from the image"],
    }


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    database_path = tmp_path / "test-civicpulse.sqlite3"
    monkeypatch.setattr(api, "DB_PATH", database_path)
    return database_path


@pytest.fixture
def ollama_http(monkeypatch):
    routes = {}
    requests = []

    def handler(request):
        requests.append(request)
        response = routes.get((request.method, request.url.path))
        if response is None:
            return httpx.Response(200, json={"models": []})
        return response

    def client_factory(*, timeout=None, **kwargs):
        return _REAL_ASYNC_CLIENT(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
            **kwargs,
        )

    monkeypatch.setattr(api.httpx, "AsyncClient", client_factory)
    return routes, requests


@pytest.fixture
def client(isolated_database, ollama_http):
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.fixture
def image_bytes():
    def create_image(image_format="PNG", size=(32, 24)):
        output = io.BytesIO()
        Image.new("RGB", size, color=(90, 100, 110)).save(output, format=image_format)
        return output.getvalue()

    return create_image


@pytest.fixture
def json_ai_response(analysis_payload):
    return json.dumps(analysis_payload)
