from pathlib import Path

from higgsfield_cli.config import Settings


def test_loads_separate_credentials(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("HF_KEY", raising=False)
    monkeypatch.delenv("HF_CREDENTIALS", raising=False)
    monkeypatch.setenv("HF_API_KEY_ID", "abc")
    monkeypatch.setenv("HF_API_KEY_SECRET", "xyz")
    settings = Settings.load(tmp_path / "missing.env")
    assert settings.configured
    assert settings.credential == "abc:xyz"


def test_loads_combined_credential(monkeypatch, tmp_path: Path):
    for name in ("HF_API_KEY_ID", "HF_API_KEY", "HF_API_KEY_SECRET", "HF_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HF_KEY", "abc:xyz:with-colon")
    settings = Settings.load(tmp_path / "missing.env")
    assert settings.key_id == "abc"
    assert settings.key_secret == "xyz:with-colon"

