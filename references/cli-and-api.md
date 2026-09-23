# Higgsfield CLI and API reference

## Runtime and working directory

The skill folder is a portable Python project. From any writable task directory, run its CLI with an absolute path:

```bash
uv sync --project /absolute/path/to/higgsfield-api --locked --python 3.13
/absolute/path/to/higgsfield-api/.venv/bin/higgsfield doctor
```

Python 3.12 or newer is supported. Alternatively, create a virtual environment in the skill folder and run `python -m pip install -e /absolute/path/to/higgsfield-api` with that environment's Python. The `uv.lock` pins application dependencies; pip resolves the dependency ranges in `pyproject.toml`.

The CLI uses the current working directory for `.env`, `.higgsfield/history.jsonl`, and `GENERATIONS/`. This lets the same installed skill serve multiple task workspaces. Run all commands for one request from the same directory so `status` can recover its saved official URL. `--env-file /absolute/path/to/credentials.env` goes before the subcommand; exported credentials override file values. The bundled `.env.example` shows the two supported primary variable names. Do not copy populated `.env`, `.venv`, request history, or generated media when distributing the skill.

## Commands

```text
higgsfield [--env-file PATH] doctor [--live]
higgsfield models [--search TEXT] [--provider SLUG] [--output-type image|video|audio]
higgsfield models --starters
higgsfield estimate ENDPOINT [--data JSON | --data-file FILE] [--set KEY=VALUE ...]
higgsfield generate ENDPOINT [payload options] [--wait | --no-wait]
    [--wait-timeout SECONDS] [--download] [--output-dir PATH] [--webhook HTTPS_URL]
higgsfield status REQUEST_ID [--status-url OFFICIAL_URL] [--wait | --no-wait]
    [--wait-timeout SECONDS] [--download] [--output-dir PATH]
higgsfield upload FILE [--content-type MIME]
higgsfield cancel REQUEST_ID
higgsfield history [--limit N]
```

`--set` parses JSON values and leaves other text as strings. Dotted keys create nested objects. A JSON payload can come from `--data` or `--data-file`; repeated `--set` options override its fields. [examples/video.json](../examples/video.json) is a sample payload, not a guaranteed current model schema. A synchronous `generate` prints accepted and final JSON objects; `generate --no-wait` prints one accepted object.

`generate --download` and `status --download` save files under `GENERATIONS/<request-id>/` in the current working directory by default. `--output-dir PATH` changes the parent directory and requires `--download`. `generate --no-wait` cannot download in that call. Downloads never overwrite existing filenames. An unsuccessful terminal request exits with code 3.

## Discovery and model schemas

`models` follows pages of the public console catalog without sending credentials and reports count discrepancies. The feed is not a documented stable API contract; its `default_mode_id` is only a discovery hint. `models --starters` is the explicit offline option. An arbitrary documented endpoint ID works without a bundled alias.

For current workflow fields, consult the [Higgsfield model catalog](https://console.higgsfield.ai/models) and selected model's API page. The [shared documentation index](https://docs.higgsfield.ai/docs/llms.txt) and OpenAPI specification are supplementary. Public catalog prices are indicative; use `estimate` for the authenticated account. Estimates may return a pricing formula instead of a numeric amount.

## Request lifecycle

- `doctor` checks local configuration; `doctor --live` performs a read-only authentication probe.
- Nonterminal states are `queued` and `in_progress`. Terminal states include `completed`, `failed`, `nsfw`, and `canceled`.
- Keep the accepted `request_id` and `status_url`. Local history normally recovers the status URL; supply `--status-url` explicitly if history is missing.
- A canceled queued request may be refunded. Cancellation may fail after processing starts.
- Polling begins at roughly two seconds and backs off. Retrying a status GET after a transient server error is different from repeating a paid generation POST.
- If submission times out ambiguously, inspect history and the Console before considering another submission.
- Download important outputs promptly because remote links are time limited.

Useful provider pages: [authentication](https://docs.higgsfield.ai/docs/authentication), [requests](https://docs.higgsfield.ai/docs/concepts/requests), [polling](https://docs.higgsfield.ai/docs/concepts/polling), [uploads](https://docs.higgsfield.ai/docs/concepts/file-uploads), [errors](https://docs.higgsfield.ai/docs/concepts/errors), and [billing and retention](https://docs.higgsfield.ai/docs/concepts/billing-and-retention).
