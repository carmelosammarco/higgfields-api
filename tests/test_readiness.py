import json
from pathlib import Path

import httpx
import pytest

from higgsfield_cli import cli
from higgsfield_cli.catalog import fetch_catalog
from higgsfield_cli.client import HiggsfieldError, download_artifacts, normalize_endpoint


def test_catalog_fetches_all_pages_without_credentials():
    seen = []

    def handler(request):
        assert "authorization" not in request.headers
        seen.append(str(request.url))
        second = "page=2" in str(request.url)
        return httpx.Response(200, json={
            "count": 2, "results": [{"id": "second" if second else "first"}],
            "next": None if second else "https://dash.higgsfield.ai/api/v2/catalog-models/?page=2",
        })

    result = fetch_catalog(transport=httpx.MockTransport(handler))
    assert len(seen) == 2
    assert [m["id"] for m in result["models"]] == ["first", "second"]


@pytest.mark.parametrize("data", [
    {"count": 1, "results": [{"id": "one"}], "next": "https://evil.example/page"},
    {"results": []},
])
def test_catalog_refuses_partial_or_untrusted_results(data):
    with pytest.raises(HiggsfieldError):
        fetch_catalog(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))


def test_catalog_discloses_server_count_discrepancy():
    data = {"count": 2, "results": [{"id": "one"}], "next": None}
    result = fetch_catalog(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    assert result["count"] == 1
    assert result["advertised_count"] == 2
    assert result["count_matches"] is False
    assert result["warnings"]


def test_download_never_overwrites_and_is_complete(tmp_path):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"new media"))
    (tmp_path / "video.mp4").write_bytes(b"original")
    (tmp_path / "video-1.mp4").write_bytes(b"previous")
    saved = download_artifacts(["https://cdn.example/video.mp4"], tmp_path, transport=transport)
    assert saved == [tmp_path / "video-2.mp4"]
    assert saved[0].read_bytes() == b"new media"
    assert (tmp_path / "video.mp4").read_bytes() == b"original"
    assert (tmp_path / "video-1.mp4").read_bytes() == b"previous"
    assert not list(tmp_path.glob(".download-*"))


def test_failed_stream_leaves_no_partial_media(tmp_path):
    class BrokenStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial"
            raise httpx.ReadError("connection lost")

    transport = httpx.MockTransport(lambda r: httpx.Response(200, stream=BrokenStream()))
    with pytest.raises(HiggsfieldError):
        download_artifacts(["https://cdn.example/video.mp4"], tmp_path, transport=transport)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("endpoint", ["../requests/123", "provider/../../files", "//evil.example/a?x=y"])
def test_endpoint_traversal_is_rejected(endpoint):
    with pytest.raises(HiggsfieldError):
        normalize_endpoint(endpoint)


@pytest.mark.parametrize("flags", [
    ["--no-wait", "--download"], ["--output-dir", "/tmp/media"],
    ["--wait-timeout", "nan"], ["--wait-timeout", "-1"],
])
def test_bad_options_rejected_before_credentials_or_submission(monkeypatch, flags):
    monkeypatch.setattr(cli.Settings, "load", lambda *a: pytest.fail("must validate first"))
    assert cli.run(["generate", "soul"] + flags) == 2


def test_failed_status_is_preserved_and_recovery_url_is_used(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    url = "https://platform.higgsfield.ai/requests/123/status"
    cli.record_history("submitted", {"request_id": "123", "response": {"status_url": url}})

    class Client:
        def __init__(self, settings):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def status(self, request_id, status_url=None):
            assert status_url == url
            return {"status": "failed", "error": "provider failure"}

    monkeypatch.setattr(cli, "HiggsfieldClient", Client)
    args = cli.build_parser().parse_args(["status", "123", "--download"])
    assert cli.command_status(args, None) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
    assert not (tmp_path / "GENERATIONS").exists()
    assert json.loads(cli.history_path().read_text().splitlines()[-1])["event"] == "status"


def test_default_state_is_in_the_active_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from higgsfield_cli.config import default_env_file, project_root

    assert project_root() == tmp_path
    assert default_env_file() == tmp_path / ".env"
    assert cli.history_path() == tmp_path / ".higgsfield" / "history.jsonl"
    assert cli.generations_dir() == tmp_path / "GENERATIONS"


@pytest.mark.parametrize("state,expected", [("completed", 0), ("failed", 3), ("nsfw", 3), ("canceled", 3)])
def test_generation_lifecycle_with_download(monkeypatch, tmp_path, capsys, state, expected):
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    downloaded = []

    class Client:
        def __init__(self, settings):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def submit(self, endpoint, payload, **kwargs):
            assert payload["prompt"] == "test"
            return {"request_id": "123", "status": "queued", "status_url": "https://platform.higgsfield.ai/requests/123/status"}
        def wait(self, request_id, **kwargs):
            assert kwargs["status_url"].startswith("https://platform.higgsfield.ai/")
            return {"status": state, "video": {"url": "https://cdn.example/video.mp4"}} if state == "completed" else {"status": state}

    def download(urls, folder):
        downloaded.append(folder)
        return [folder / "video.mp4"]

    monkeypatch.setattr(cli, "HiggsfieldClient", Client)
    monkeypatch.setattr(cli, "download_artifacts", download)
    args = cli.build_parser().parse_args(["generate", "soul", "--set", "prompt=test", "--download"])
    assert cli.command_generate(args, None) == expected
    assert len(downloaded) == (1 if state == "completed" else 0)
    events = [json.loads(line) for line in cli.history_path().read_text().splitlines()]
    assert events[0]["event"] == "submitted"
    assert events[1]["response"]["status"] == state
