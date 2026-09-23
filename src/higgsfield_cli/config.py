from __future__ import annotations

import os
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


DEFAULT_BASE_URL = "https://api.higgsfield.ai"


def project_root() -> Path:
    """Return the active task's working directory for local state and outputs."""
    return Path.cwd().resolve()


def default_env_file() -> Path:
    return project_root() / ".env"


@dataclass(frozen=True)
class Settings:
    key_id: Optional[str]
    key_secret: Optional[str]
    base_url: str = DEFAULT_BASE_URL
    request_timeout: float = 30.0
    env_file: Optional[Path] = None

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    @property
    def credential(self) -> str:
        if not self.configured:
            raise ValueError(
                "Higgsfield credentials are missing. Set HF_API_KEY_ID and "
                "HF_API_KEY_SECRET in the task environment or its .env file."
            )
        return f"{self.key_id}:{self.key_secret}"

    @classmethod
    def load(cls, env_file: Optional[Path] = None) -> "Settings":
        selected = (env_file or default_env_file()).expanduser().resolve()
        if selected.exists():
            load_dotenv(selected, override=False)

        combined = os.getenv("HF_KEY") or os.getenv("HF_CREDENTIALS")
        key_id = os.getenv("HF_API_KEY_ID") or os.getenv("HF_API_KEY")
        key_secret = os.getenv("HF_API_KEY_SECRET") or os.getenv("HF_API_SECRET")
        if combined and ":" in combined and not (key_id and key_secret):
            key_id, key_secret = combined.split(":", 1)

        timeout_text = os.getenv("HIGGSFIELD_REQUEST_TIMEOUT", "30")
        try:
            request_timeout = float(timeout_text)
        except ValueError as exc:
            raise ValueError("HIGGSFIELD_REQUEST_TIMEOUT must be a number") from exc
        if not math.isfinite(request_timeout) or request_timeout <= 0:
            raise ValueError("HIGGSFIELD_REQUEST_TIMEOUT must be greater than zero")

        return cls(
            key_id=key_id,
            key_secret=key_secret,
            # Keep credentials pinned to the documented official API host.
            base_url=DEFAULT_BASE_URL,
            request_timeout=request_timeout,
            env_file=selected,
        )
