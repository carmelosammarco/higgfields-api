import json

import httpx
import pytest

from higgsfield_cli.client import HiggsfieldClient, HiggsfieldError, artifact_urls, normalize_endpoint
from higgsfield_cli.config import Settings


def settings() -> Settings:
    return Settings(key_id="id", key_secret="secret")


def test_submit_uses_documented_authorization_and_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Key id:secret"
        assert request.url.path == "/bytedance/seedance-2.0/text-to-video"
        assert json.loads(request.content) == {"prompt": "hello"}
        return httpx.Response(200, json={"status": "queued", "request_id": "123"})

    with HiggsfieldClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = client.submit("bytedance/seedance-2.0/text-to-video", {"prompt": "hello"})
    assert result["request_id"] == "123"


def test_status_and_cancel_paths():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(202)
        return httpx.Response(200, json={"status": "queued", "request_id": "123"})

    with HiggsfieldClient(settings(), transport=httpx.MockTransport(handler)) as client:
        client.status("123")
        assert client.cancel("123")["status"] == "canceled"
    assert seen == [("GET", "/requests/123/status"), ("POST", "/requests/123/cancel")]


def test_status_accepts_returned_official_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.higgsfield.ai/requests/123/status"
        return httpx.Response(200, json={"status": "completed", "request_id": "123"})

    with HiggsfieldClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = client.status(
            "123", status_url="https://api.higgsfield.ai/requests/123/status"
        )
    assert result["status"] == "completed"


def test_status_accepts_returned_platform_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://platform.higgsfield.ai/requests/123/status"
        assert request.headers["Authorization"] == "Key id:secret"
        return httpx.Response(200, json={"status": "completed", "request_id": "123"})

    with HiggsfieldClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = client.status(
            "123", status_url="https://platform.higgsfield.ai/requests/123/status"
        )
    assert result["status"] == "completed"


def test_status_rejects_foreign_url_to_protect_credentials():
    with HiggsfieldClient(settings(), transport=httpx.MockTransport(lambda request: None)) as client:
        with pytest.raises(HiggsfieldError):
            client.status("123", status_url="https://evil.example/steal")


def test_estimate_uses_estimate_prefix():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/estimate/higgsfield-ai/soul/v2/standard"
        return httpx.Response(200, json={"credits": "1.5", "usd": "0.09"})

    with HiggsfieldClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = client.estimate("higgsfield-ai/soul/v2/standard", {"prompt": "hello"})
    assert result["usd"] == "0.09"


@pytest.mark.parametrize("status,authenticated", [(404, True), (401, False)])
def test_check_auth_interprets_documented_statuses(status, authenticated):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={"detail": "probe"}))
    with HiggsfieldClient(settings(), transport=transport) as client:
        assert client.check_auth()["authenticated"] is authenticated


def test_wait_stops_on_terminal_status_without_extra_poll():
    responses = iter(
        [
            {"status": "queued", "request_id": "123"},
            {"status": "in_progress", "request_id": "123"},
            {"status": "completed", "request_id": "123", "video": {"url": "https://cdn/x.mp4"}},
        ]
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=next(responses))

    with HiggsfieldClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = client.wait("123", timeout=10, sleep=lambda _: None)
    assert result["status"] == "completed"
    assert calls == ["/requests/123/status"] * 3


def test_rejects_foreign_model_url():
    with pytest.raises(HiggsfieldError):
        normalize_endpoint("https://evil.example/model")


def test_rejects_non_https_webhook():
    with HiggsfieldClient(settings(), transport=httpx.MockTransport(lambda request: None)) as client:
        with pytest.raises(HiggsfieldError):
            client.submit("provider/model/workflow", {}, webhook_url="http://localhost/hook")


def test_extracts_only_artifact_urls():
    payload = {
        "status_url": "https://api.higgsfield.ai/requests/1/status",
        "images": [{"url": "https://cdn.example/a.png"}],
        "video": {"url": "https://cdn.example/a.mp4"},
    }
    assert artifact_urls(payload) == ["https://cdn.example/a.png", "https://cdn.example/a.mp4"]
