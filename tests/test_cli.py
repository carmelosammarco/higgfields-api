import json

import pytest

from higgsfield_cli import cli
from higgsfield_cli.cli import build_arguments, run


def namespace(**kwargs):
    class Args:
        data = None
        data_file = None
        set_values = None

    args = Args()
    for key, value in kwargs.items():
        setattr(args, key, value)
    return args


def test_build_arguments_merges_json_and_set_values():
    result = build_arguments(
        namespace(data='{"prompt":"hello"}', set_values=["duration=5", "meta.enabled=true"])
    )
    assert result == {"prompt": "hello", "duration": 5, "meta": {"enabled": True}}


def test_doctor_does_not_print_secret(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HF_API_KEY_ID", "visible-id")
    monkeypatch.setenv("HF_API_KEY_SECRET", "never-print-this")
    assert run(["--env-file", str(tmp_path / "none"), "doctor"]) == 0
    output = capsys.readouterr().out
    assert "never-print-this" not in output
    assert json.loads(output)["credentials_configured"] is True


def test_download_uses_project_generations_directory_by_default(monkeypatch, tmp_path):
    captured = {}

    def fake_download(urls, output_dir):
        captured["urls"] = urls
        captured["output_dir"] = output_dir
        return [output_dir / "video.mp4"]

    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "download_artifacts", fake_download)
    args = namespace(download=True, output_dir=None)
    result = {
        "status": "completed",
        "request_id": "request-123",
        "video": {"url": "https://cdn.example/video.mp4"},
    }

    paths = cli._download_if_requested(args, result)

    assert captured["output_dir"] == tmp_path / "GENERATIONS" / "request-123"
    assert paths == [str(tmp_path / "GENERATIONS" / "request-123" / "video.mp4")]


def test_download_output_dir_override_is_preserved(monkeypatch, tmp_path):
    captured = {}

    def fake_download(urls, output_dir):
        captured["output_dir"] = output_dir
        return []

    monkeypatch.setattr(cli, "download_artifacts", fake_download)
    custom = tmp_path / "custom"
    args = namespace(download=True, output_dir=str(custom))

    cli._download_if_requested(
        args,
        {"status": "completed", "request_id": "request-456", "video": {"url": "https://cdn.example/video.mp4"}},
    )

    assert captured["output_dir"] == custom / "request-456"
