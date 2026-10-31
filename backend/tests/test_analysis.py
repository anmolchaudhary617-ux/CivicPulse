import io
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from app import main as api


def upload(client, image_bytes, *, filename="sample.png", content_type="image/png", provider="gemini"):
    return client.post(
        "/api/analyze",
        files={"image": (filename, image_bytes, content_type)},
        data={"provider": provider},
    )


def test_health_endpoint_returns_provider_status(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "gemini_key_configured": bool(api.os.getenv("GEMINI_API_KEY", "").strip()),
        "gemini_model": api.GEMINI_MODEL,
        "ollama_reachable": True,
        "local_model": api.OLLAMA_MODEL,
        "local_model_available": False,
    }


@pytest.mark.parametrize(
    ("image_format", "content_type", "filename"),
    [
        ("JPEG", "image/jpeg", "sample.jpg"),
        ("PNG", "image/png", "sample.png"),
        ("WEBP", "image/webp", "sample.webp"),
    ],
)
def test_analyze_accepts_supported_image_formats(
    client, monkeypatch, analysis_payload, image_bytes, image_format, content_type, filename
):
    monkeypatch.setattr(
        api,
        "analyze_gemini",
        AsyncMock(return_value={**analysis_payload, "provider": "gemini"}),
    )

    response = upload(
        client,
        image_bytes(image_format),
        filename=filename,
        content_type=content_type,
    )

    assert response.status_code == 200
    assert response.json()["image_name"] == filename
    assert response.json()["provider"] == "gemini"


@pytest.mark.parametrize(
    ("provider", "expected_provider"),
    [("gemini", "gemini"), ("local", "local")],
)
def test_provider_response_contracts(
    client,
    monkeypatch,
    ollama_http,
    json_ai_response,
    image_bytes,
    provider,
    expected_provider,
):
    if provider == "gemini":
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-credential")
        monkeypatch.setattr(
            api.asyncio,
            "to_thread",
            AsyncMock(return_value=json_ai_response),
        )
    else:
        routes, _ = ollama_http
        routes[("POST", "/api/chat")] = httpx.Response(
            200,
            json={"message": {"content": json_ai_response}},
        )

    response = upload(
        client,
        image_bytes(),
        provider=provider,
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "issue_type",
        "severity",
        "title",
        "description",
        "evidence",
        "department",
        "confidence",
        "limitations",
        "provider",
        "image_name",
    }
    assert body["provider"] == expected_provider
    assert body["issue_type"] == "Pothole"
    assert isinstance(body["evidence"], list)
    assert isinstance(body["limitations"], list)


@pytest.mark.parametrize(
    ("provider", "response_body"),
    [
        ("gemini", "not valid JSON"),
        ("gemini", '{"issue_type":'),
        ("local", "not valid JSON"),
        ("local", '{"issue_type":'),
    ],
)
def test_analyze_rejects_malformed_ai_json(
    client, monkeypatch, ollama_http, image_bytes, provider, response_body
):
    if provider == "gemini":
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-credential")
        monkeypatch.setattr(
            api.asyncio,
            "to_thread",
            AsyncMock(return_value=response_body),
        )
    else:
        routes, _ = ollama_http
        routes[("POST", "/api/chat")] = httpx.Response(
            200,
            json={"message": {"content": response_body}},
        )

    response = upload(client, image_bytes(), provider=provider)

    assert response.status_code == 502
    assert "JSON" in response.json()["detail"]


def test_gemini_provider_error_is_reported_without_exposing_provider_details(
    client, monkeypatch, image_bytes
):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-credential")
    monkeypatch.setattr(
        api.asyncio,
        "to_thread",
        AsyncMock(side_effect=RuntimeError("unauthorized test-key-not-a-real-credential")),
    )

    response = upload(client, image_bytes(), provider="gemini")

    assert response.status_code == 502
    assert "authentication failed" in response.json()["detail"].lower()
    assert "test-key-not-a-real-credential" not in response.json()["detail"]


@pytest.mark.parametrize(
    ("status_code", "expected_status"),
    [(404, 503), (500, 502)],
)
def test_ollama_provider_errors_are_reported(
    client, ollama_http, image_bytes, status_code, expected_status
):
    routes, _ = ollama_http
    routes[("POST", "/api/chat")] = httpx.Response(status_code, text="provider failure")

    response = upload(client, image_bytes(), provider="local")

    assert response.status_code == expected_status


def test_analyze_rejects_unsupported_provider(client, image_bytes):
    response = upload(client, image_bytes(), provider="other")

    assert response.status_code == 400


def test_analyze_rejects_missing_image(client):
    response = client.post("/api/analyze", data={"provider": "gemini"})

    assert response.status_code == 422


def test_analyze_rejects_empty_image(client):
    response = upload(client, b"")

    assert response.status_code == 400


def test_analyze_rejects_invalid_image_bytes(client):
    response = upload(client, b"not an image")

    assert response.status_code == 400


def test_analyze_rejects_unsupported_image_format(client, image_bytes):
    response = upload(
        client,
        image_bytes("GIF"),
        filename="sample.gif",
        content_type="image/gif",
    )

    assert response.status_code == 415


def test_analyze_rejects_image_mime_mismatch(client, image_bytes):
    response = upload(
        client,
        image_bytes("PNG"),
        filename="sample.jpg",
        content_type="image/jpeg",
    )

    assert response.status_code == 415


def test_analyze_rejects_image_above_byte_limit(client):
    response = upload(client, b"x" * (api.MAX_IMAGE_BYTES + 1))

    assert response.status_code == 413


def test_analyze_rejects_image_above_pixel_limit(client):
    image = Image.new("1", (5000, 4001))
    output = io.BytesIO()
    image.save(output, format="PNG")

    response = upload(client, output.getvalue())

    assert response.status_code == 413


def test_gemini_provider_rejects_missing_api_key(client, monkeypatch, image_bytes):
    monkeypatch.setenv("GEMINI_API_KEY", "")

    response = upload(client, image_bytes(), provider="gemini")

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_ollama_request_contains_image_and_model(
    client, ollama_http, image_bytes, json_ai_response
):
    routes, requests = ollama_http
    routes[("POST", "/api/chat")] = httpx.Response(
        200,
        json={"message": {"content": json_ai_response}},
    )
    image = image_bytes()

    response = upload(client, image, provider="local")

    assert response.status_code == 200
    chat_request = next(request for request in requests if request.url.path == "/api/chat")
    body = json.loads(chat_request.content)
    assert body["model"] == api.OLLAMA_MODEL
    assert body["messages"][0]["images"] == [api.base64.b64encode(image).decode("ascii")]
