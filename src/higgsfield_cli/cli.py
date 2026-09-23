from __future__ import annotations

import argparse
import json
import sys
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .catalog import CATALOG_URL, STARTERS, fetch_catalog, resolve_endpoint
from .client import (
    HiggsfieldClient,
    HiggsfieldError,
    artifact_urls,
    download_artifacts,
    validate_request_id,
    TERMINAL_STATUSES,
)
from .config import Settings, default_env_file, project_root


def _json_value(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _assign_dotted(target: Dict[str, Any], dotted_key: str, value: Any) -> None:
    if not dotted_key or any(not part for part in dotted_key.split(".")):
        raise HiggsfieldError(f"Invalid parameter name: {dotted_key!r}")
    cursor = target
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        existing = cursor.setdefault(part, {})
        if not isinstance(existing, dict):
            raise HiggsfieldError(f"Cannot set nested value below {part!r}")
        cursor = existing
    cursor[parts[-1]] = value


def build_arguments(args: argparse.Namespace) -> Dict[str, Any]:
    supplied = sum(bool(value) for value in (args.data, args.data_file))
    if supplied > 1:
        raise HiggsfieldError("Use only one of --data and --data-file")
    payload: Any = {}
    if args.data:
        try:
            payload = json.loads(args.data)
        except json.JSONDecodeError as exc:
            raise HiggsfieldError(f"--data is not valid JSON: {exc}") from exc
    elif args.data_file:
        try:
            payload = json.loads(Path(args.data_file).expanduser().read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise HiggsfieldError(f"Could not read --data-file: {exc}") from exc
    if not isinstance(payload, dict):
        raise HiggsfieldError("Generation data must be a JSON object")
    for assignment in args.set_values or []:
        if "=" not in assignment:
            raise HiggsfieldError(f"--set requires KEY=VALUE, received {assignment!r}")
        key, value = assignment.split("=", 1)
        _assign_dotted(payload, key, _json_value(value))
    return payload


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def history_path() -> Path:
    return project_root() / ".higgsfield" / "history.jsonl"


def generations_dir() -> Path:
    return project_root() / "GENERATIONS"


def record_history(event: str, payload: Dict[str, Any]) -> None:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in payload.items() if k not in {"authorization", "credentials"}}
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **clean,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _download_if_requested(args: argparse.Namespace, result: Dict[str, Any]) -> List[str]:
    if not getattr(args, "download", False):
        return []
    if str(result.get("status", "")).lower() != "completed":
        return []
    urls = artifact_urls(result)
    if not urls:
        raise HiggsfieldError("The completed response contains no downloadable artifact URLs")
    request_id = validate_request_id(str(result.get("request_id", "generation")))
    base = Path(args.output_dir).expanduser() if args.output_dir else generations_dir()
    paths = download_artifacts(urls, (base / request_id).resolve())
    return [str(path) for path in paths]


def _wait_for_result(
    client: HiggsfieldClient,
    request_id: str,
    args: argparse.Namespace,
    *,
    status_url: Optional[str] = None,
) -> Dict[str, Any]:
    def update(result: Dict[str, Any]) -> None:
        print(f"[{result.get('status', 'unknown')}] {request_id}", file=sys.stderr)

    return client.wait(
        request_id,
        timeout=args.wait_timeout,
        status_url=status_url,
        on_update=update,
    )


def command_doctor(args: argparse.Namespace, settings: Settings) -> int:
    result = {
        "version": __version__,
        "python": sys.version.split()[0],
        "project_root": str(project_root()),
        "env_file": str(settings.env_file or default_env_file()),
        "env_file_exists": bool(settings.env_file and settings.env_file.exists()),
        "credentials_configured": settings.configured,
        "credential_format": "key-id + secret" if settings.configured else None,
        "api_base_url": settings.base_url,
    }
    if args.live:
        if not settings.configured:
            raise HiggsfieldError("Cannot run --live until .env contains both credentials")
        with HiggsfieldClient(settings) as client:
            result["live_auth"] = client.check_auth()
    print_json(result)
    if args.live and not result["live_auth"]["authenticated"]:
        return 3
    return 0 if settings.configured else 2


def command_models(args: argparse.Namespace, settings: Settings) -> int:
    if args.starters:
        print_json({"catalog": CATALOG_URL, "starters": STARTERS})
        return 0
    result = fetch_catalog()
    models = result["models"]
    if args.search:
        models = [m for m in models if args.search.casefold() in json.dumps(m).casefold()]
    if args.provider:
        models = [m for m in models if args.provider.casefold() in
                  (m.get("company") or {}).get("slug", "").casefold()]
    if args.output_type:
        models = [m for m in models if args.output_type in m.get("output_types", [])]
    result["matched_count"] = len(models)
    result["models"] = [{k: m.get(k) for k in (
        "id", "title", "slug", "description", "company", "output_types",
        "availability_state", "default_mode_id", "entry_points", "pricing", "catalog_type"
    )} for m in models]
    print_json(result)
    return 0


def command_generate(args: argparse.Namespace, settings: Settings) -> int:
    endpoint = resolve_endpoint(args.endpoint)
    payload = build_arguments(args)
    with HiggsfieldClient(settings) as client:
        accepted = client.submit(endpoint, payload, webhook_url=args.webhook)
        request_id = str(accepted.get("request_id", ""))
        print_json(accepted)
        sys.stdout.flush()
        record_history("submitted", {"endpoint": endpoint, "request_id": request_id, "response": accepted})
        if not args.wait:
            return 0
        if not request_id:
            raise HiggsfieldError("Submission response did not include request_id")
        response_status_url = accepted.get("status_url")
        result = _wait_for_result(
            client,
            request_id,
            args,
            status_url=response_status_url if isinstance(response_status_url, str) else None,
        )
        result.setdefault("request_id", request_id)
        record_history("terminal", {"endpoint": endpoint, "request_id": request_id, "response": result})
        downloads = _download_if_requested(args, result)
        if downloads:
            result = {**result, "downloaded_files": downloads}
            record_history("downloaded", {"endpoint": endpoint, "request_id": request_id, "response": result})
        print_json(result)
        return 0 if str(result.get("status", "")).lower() == "completed" else 3


def command_estimate(args: argparse.Namespace, settings: Settings) -> int:
    endpoint = resolve_endpoint(args.endpoint)
    with HiggsfieldClient(settings) as client:
        print_json(client.estimate(endpoint, build_arguments(args)))
    return 0


def command_status(args: argparse.Namespace, settings: Settings) -> int:
    validate_request_id(args.request_id)
    if not args.status_url and history_path().exists():
        for line in reversed(history_path().read_text(encoding="utf-8").splitlines()):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("request_id") == args.request_id:
                saved_url = event.get("response", {}).get("status_url")
                if saved_url:
                    args.status_url = saved_url
                    break
    with HiggsfieldClient(settings) as client:
        result = (
            _wait_for_result(client, args.request_id, args, status_url=args.status_url)
            if args.wait
            else client.status(args.request_id, status_url=args.status_url)
        )
    result.setdefault("request_id", args.request_id)
    record_history("status", {"request_id": args.request_id, "response": result})
    downloads = _download_if_requested(args, result)
    if downloads:
        result = {**result, "downloaded_files": downloads}
        record_history("downloaded", {"request_id": args.request_id, "response": result})
    print_json(result)
    status = str(result.get("status", "")).lower()
    return 3 if status in TERMINAL_STATUSES and status != "completed" else 0


def command_cancel(args: argparse.Namespace, settings: Settings) -> int:
    with HiggsfieldClient(settings) as client:
        result = client.cancel(args.request_id)
    record_history("canceled", {"request_id": args.request_id, "response": result})
    print_json(result)
    return 0


def command_upload(args: argparse.Namespace, settings: Settings) -> int:
    with HiggsfieldClient(settings) as client:
        result = client.upload_file(Path(args.file), args.content_type)
    print_json(result)
    return 0


def command_history(args: argparse.Namespace, settings: Settings) -> int:
    path = history_path()
    if not path.exists():
        print_json([])
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines[-args.limit :] if line.strip()]
    print_json(records)
    return 0


def _add_payload_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", help="JSON object containing model parameters")
    parser.add_argument("--data-file", help="Path to a JSON file containing model parameters")
    parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        metavar="KEY=VALUE",
        help="Set/override a parameter; repeatable, JSON values accepted",
    )


def _add_wait_options(parser: argparse.ArgumentParser, default: bool) -> None:
    parser.add_argument(
        "--wait",
        action=argparse.BooleanOptionalAction,
        default=default,
        help="Poll until a terminal status",
    )
    parser.add_argument("--wait-timeout", type=float, default=1800, help="Total polling timeout in seconds")
    parser.add_argument("--download", action="store_true", help="Download completed artifacts")
    parser.add_argument(
        "--output-dir",
        help="Artifact directory (default: working-directory GENERATIONS directory)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="higgsfield",
        description="Generate images and videos with the Higgsfield API.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--env-file", type=Path, help="Credentials file (default: working-directory .env)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check local configuration without making an API call")
    doctor.add_argument("--live", action="store_true", help="Verify credentials with a read-only API probe")
    doctor.set_defaults(handler=command_doctor, needs_credentials=False)

    models = subparsers.add_parser("models", help="Fetch the public model catalog and indicative prices")
    models.add_argument("--starters", action="store_true", help="Offline bundled aliases and examples")
    models.add_argument("--search", help="Search catalog metadata")
    models.add_argument("--provider", help="Filter provider slug, e.g. bytedance")
    models.add_argument("--output-type", choices=["image", "video", "audio"], help="Filter output type")
    models.set_defaults(handler=command_models, needs_credentials=False)

    generate = subparsers.add_parser("generate", help="Submit any documented Higgsfield model endpoint")
    generate.add_argument("endpoint", help="Endpoint ID or starter alias from `higgsfield models`")
    _add_payload_options(generate)
    _add_wait_options(generate, default=True)
    generate.add_argument("--webhook", help="Public HTTPS webhook URL")
    generate.set_defaults(handler=command_generate, needs_credentials=True)

    estimate = subparsers.add_parser("estimate", help="Estimate authenticated cost without generating")
    estimate.add_argument("endpoint", help="Endpoint ID or starter alias")
    _add_payload_options(estimate)
    estimate.set_defaults(handler=command_estimate, needs_credentials=True)

    status = subparsers.add_parser("status", help="Read or follow an existing request")
    status.add_argument("request_id")
    status.add_argument(
        "--status-url",
        help="Official status URL returned by the generation submission",
    )
    _add_wait_options(status, default=False)
    status.set_defaults(handler=command_status, needs_credentials=True)

    cancel = subparsers.add_parser("cancel", help="Cancel a request that is still fully queued")
    cancel.add_argument("request_id")
    cancel.set_defaults(handler=command_cancel, needs_credentials=True)

    upload = subparsers.add_parser("upload", help="Upload local media and return its public URL")
    upload.add_argument("file")
    upload.add_argument("--content-type", help="Override the detected MIME type")
    upload.set_defaults(handler=command_upload, needs_credentials=True)

    history = subparsers.add_parser("history", help="Show local request history")
    history.add_argument("--limit", type=int, default=20)
    history.set_defaults(handler=command_history, needs_credentials=False)
    return parser


def run(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if hasattr(args, "wait_timeout") and (not math.isfinite(args.wait_timeout) or args.wait_timeout <= 0):
            raise HiggsfieldError("--wait-timeout must be positive and finite")
        if args.command == "generate" and not args.wait and (args.download or args.output_dir):
            raise HiggsfieldError("--no-wait cannot download; resume later with status --wait --download")
        if getattr(args, "output_dir", None) and not args.download:
            raise HiggsfieldError("--output-dir requires --download")
        if args.command == "history" and args.limit <= 0:
            raise HiggsfieldError("--limit must be positive")
        if args.command == "models" and args.starters and (args.search or args.provider or args.output_type):
            raise HiggsfieldError("Catalog filters cannot be combined with --starters")
        settings = Settings.load(args.env_file)
        if args.needs_credentials and not settings.configured:
            raise HiggsfieldError(
                f"Credentials are missing. Set HF_API_KEY_ID and HF_API_KEY_SECRET "
                f"in the environment or {default_env_file()}."
            )
        return int(args.handler(args, settings))
    except (HiggsfieldError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def main() -> None:
    raise SystemExit(run())
