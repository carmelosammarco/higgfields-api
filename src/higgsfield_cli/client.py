from __future__ import annotations

import json
import mimetypes
import random
import os
import re
import tempfile
import math
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional
from urllib.parse import unquote, urlparse

import httpx

from .config import Settings


TERMINAL_STATUSES = {"completed", "failed", "nsfw", "canceled", "cancelled"}
STATUS_HOSTS = {"api.higgsfield.ai", "platform.higgsfield.ai"}


def validate_request_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", value):
        raise HiggsfieldError("Invalid request ID")
    return value


class HiggsfieldError(RuntimeError):
    """A safe, user-facing API or input error."""


def normalize_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip()
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        parsed = urlparse(endpoint)
        if (parsed.scheme != "https" or parsed.netloc != "api.higgsfield.ai"
                or parsed.query or parsed.fragment):
            raise HiggsfieldError("Model URLs must use https://api.higgsfield.ai")
        endpoint = parsed.path
    endpoint = endpoint.strip("/")
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", endpoint)
            or any(part in {".", ".."} for part in endpoint.split("/"))
            or endpoint.startswith(("requests/", "files/", "estimate/"))):
        raise HiggsfieldError("Provide a model endpoint ID such as provider/model/workflow")
    return endpoint


def _safe_error(response: httpx.Response) -> str:
    correlation = response.headers.get("X-Correlation-ID")
    try:
        payload = response.json()
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        rendered = json.dumps(detail, ensure_ascii=False)
    except (ValueError, TypeError):
        rendered = response.text.strip() or response.reason_phrase
    suffix = f" (correlation ID: {correlation})" if correlation else ""
    return f"Higgsfield API returned HTTP {response.status_code}: {rendered}{suffix}"


class HiggsfieldClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.settings = settings
        self._client = httpx.Client(
            base_url=settings.base_url,
            headers={
                "Authorization": f"Key {settings.credential}",
                "Accept": "application/json",
                "User-Agent": "higgsfield-api-cli/0.1.0",
            },
            timeout=settings.request_timeout,
            transport=transport,
            follow_redirects=False,
        )

    def __enter__(self) -> "HiggsfieldClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _json_request(self, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise HiggsfieldError(f"Network error while contacting Higgsfield: {exc}") from exc
        if response.is_error:
            raise HiggsfieldError(_safe_error(response))
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise HiggsfieldError("Higgsfield returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise HiggsfieldError("Higgsfield returned an unexpected JSON response")
        correlation = response.headers.get("X-Correlation-ID")
        if correlation:
            payload.setdefault("_correlation_id", correlation)
        return payload

    def submit(
        self,
        endpoint: str,
        arguments: Mapping[str, Any],
        *,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        endpoint = normalize_endpoint(endpoint)
        if webhook_url:
            parsed_webhook = urlparse(webhook_url)
            if parsed_webhook.scheme != "https" or not parsed_webhook.netloc:
                raise HiggsfieldError("Webhook URL must be a public HTTPS URL")
        params = {"hf_webhook": webhook_url} if webhook_url else None
        return self._json_request("POST", f"/{endpoint}", json=dict(arguments), params=params)

    def check_auth(self) -> Dict[str, Any]:
        """Verify credentials using a guaranteed-nonexistent request ID.

        The API documents 401 for invalid credentials and 404 for an unknown
        request/account combination, so a 404 proves authentication completed.
        """
        probe_id = "00000000-0000-0000-0000-000000000000"
        try:
            response = self._client.get(f"/requests/{probe_id}/status")
        except httpx.HTTPError as exc:
            raise HiggsfieldError(f"Network error while contacting Higgsfield: {exc}") from exc
        if response.status_code == 404:
            return {"authenticated": True, "probe_status": 404}
        if response.status_code == 401:
            return {"authenticated": False, "probe_status": 401}
        if response.is_error:
            raise HiggsfieldError(_safe_error(response))
        return {"authenticated": True, "probe_status": response.status_code}

    def estimate(self, endpoint: str, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        endpoint = normalize_endpoint(endpoint)
        return self._json_request("POST", f"/estimate/{endpoint}", json=dict(arguments))

    def status(self, request_id: str, *, status_url: Optional[str] = None) -> Dict[str, Any]:
        request_id = validate_request_id(request_id)
        url = f"/requests/{request_id.strip()}/status"
        if status_url:
            parsed = urlparse(status_url)
            if (
                parsed.scheme != "https"
                or parsed.hostname not in STATUS_HOSTS
                or parsed.port not in (None, 443)
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise HiggsfieldError(
                    "Status URL must use an official Higgsfield HTTPS host"
                )
            url = status_url
        return self._json_request("GET", url)

    def cancel(self, request_id: str) -> Dict[str, Any]:
        request_id = validate_request_id(request_id)
        payload = self._json_request("POST", f"/requests/{request_id.strip()}/cancel")
        return payload or {"request_id": request_id.strip(), "status": "canceled"}

    def wait(
        self,
        request_id: str,
        *,
        timeout: float = 1800,
        status_url: Optional[str] = None,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Dict[str, Any]:
        if not math.isfinite(timeout) or timeout <= 0:
            raise HiggsfieldError("Polling timeout must be a positive finite number")
        deadline = time.monotonic() + timeout
        delay = 2.0
        transient_failures = 0
        last_status: Optional[str] = None
        while True:
            if time.monotonic() >= deadline:
                raise HiggsfieldError(
                    f"Timed out waiting for {request_id}; the generation may still be running."
                )
            try:
                result = self.status(request_id, status_url=status_url)
                transient_failures = 0
            except HiggsfieldError as exc:
                message = str(exc)
                if "HTTP 5" not in message and "Network error" not in message:
                    raise
                transient_failures += 1
                if transient_failures > 6:
                    raise
                sleep(min(delay, max(0.0, deadline - time.monotonic())))
                delay = min(delay * 1.5, 10.0)
                continue

            status = str(result.get("status", "unknown")).lower()
            if on_update and status != last_status:
                on_update(result)
            last_status = status
            if status in TERMINAL_STATUSES:
                return result
            sleep(min(delay + random.uniform(0, 0.5), max(0.0, deadline - time.monotonic())))
            delay = min(delay * 1.5, 10.0)

    def upload_file(self, file_path: Path, content_type: Optional[str] = None) -> Dict[str, Any]:
        path = file_path.expanduser().resolve()
        if not path.is_file():
            raise HiggsfieldError(f"File not found: {path}")
        detected = content_type or mimetypes.guess_type(path.name)[0]
        if not detected:
            raise HiggsfieldError("Could not detect content type; pass --content-type")
        ticket = self._json_request(
            "POST", "/files/generate-upload-url", json={"content_type": detected}
        )
        upload_url = ticket.get("upload_url")
        public_url = ticket.get("public_url")
        headers = ticket.get("upload_headers") or {}
        if not isinstance(upload_url, str) or not isinstance(public_url, str):
            raise HiggsfieldError("Upload response is missing upload_url or public_url")
        if any(urlparse(url).scheme != "https" or not urlparse(url).hostname
               for url in (upload_url, public_url)):
            raise HiggsfieldError("Upload URLs must use HTTPS")
        if not isinstance(headers, dict):
            raise HiggsfieldError("Upload response contains invalid upload_headers")
        try:
            with path.open("rb") as source:
                response = httpx.put(
                    upload_url,
                    headers={str(k): str(v) for k, v in headers.items()},
                    content=source,
                    timeout=max(120.0, self.settings.request_timeout),
                )
        except (OSError, httpx.HTTPError) as exc:
            raise HiggsfieldError(f"Upload failed: {exc}") from exc
        if response.is_error:
            raise HiggsfieldError(f"Storage upload returned HTTP {response.status_code}")
        return {"public_url": public_url, "content_type": detected}


def artifact_urls(payload: Any) -> List[str]:
    """Find generated artifact URLs without following arbitrary metadata links."""
    urls: List[str] = []
    artifact_keys = {"images", "video", "audio", "audios", "zip", "mov", "jsx", "fbx", "ply"}

    def collect(value: Any, in_artifact: bool = False) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "url" and in_artifact and isinstance(item, str):
                    urls.append(item)
                else:
                    collect(item, in_artifact or key in artifact_keys)
        elif isinstance(value, list):
            for item in value:
                collect(item, in_artifact)

    collect(payload)
    return list(dict.fromkeys(urls))


def download_artifacts(
    urls: Iterable[str],
    output_dir: Path,
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: List[Path] = []
    with httpx.Client(timeout=120, follow_redirects=True, transport=transport) as client:
        for index, url in enumerate(urls, start=1):
            parsed = urlparse(url)
            if parsed.scheme != "https":
                raise HiggsfieldError(f"Refusing non-HTTPS artifact URL: {url}")
            name = Path(unquote(parsed.path)).name or f"artifact-{index}"
            if name in {".", ".."} or "\x00" in name:
                raise HiggsfieldError("Invalid artifact filename")
            destination = output_dir / name
            temporary = None
            try:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".download-", delete=False) as target:
                        temporary = Path(target.name)
                        for chunk in response.iter_bytes():
                            target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                # Publish a complete file without replacing an existing file,
                # including when another downloader races us.
                suffix = 0
                while True:
                    try:
                        os.link(temporary, destination)
                        break
                    except FileExistsError:
                        suffix += 1
                        original = Path(name)
                        destination = output_dir / f"{original.stem}-{suffix}{original.suffix}"
            except (OSError, httpx.HTTPError) as exc:
                raise HiggsfieldError(f"Artifact download failed: {type(exc).__name__}") from exc
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            saved.append(destination)
    return saved
