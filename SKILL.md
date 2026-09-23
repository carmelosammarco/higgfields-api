---
name: higgsfield-api
description: Generate, estimate, upload, monitor, cancel, and download media through the Higgsfield API using the bundled Python CLI. Use for Higgsfield API-key workflows when the user wants media created or an existing API request managed.
---

# Higgsfield API

This skill includes its own CLI source and dependency lock. Treat this folder as the skill root, and run commands from the active task's writable working directory. The CLI reads `.env` (which is inside the higgsfield-api skill folder), writes `.higgsfield/history.jsonl`, and saves downloads to `GENERATIONS/<request-id>/` relative to that working directory. If the current directory is the installed skill, move to the user's task workspace first.

Use `<skill-root>/.venv/bin/higgsfield` after a one-time `uv sync --project <skill-root> --locked --python 3.13` (Python 3.12+ is supported). If `uv` is unavailable, read [references/cli-and-api.md](references/cli-and-api.md) for the pip setup. Keep runtime folders out of any copy distributed to others.

## Workflow

1. Run `doctor` to check local configuration. The CLI accepts `HF_API_KEY_ID` and `HF_API_KEY_SECRET` from the `.env` inside the higgsfield-api skill folder; `--env-file PATH` selects another file. Ask the user to configure credentials locally when the `.env` file is absent and you can show an example by using the `.env-example` file present in the higgsfield-api skill folder. Never request or print the values in chat.
2. Use `models` for public discovery, then check the chosen workflow's current model page for its endpoint and input schema. The catalog can be incomplete. `models --starters` gives offline aliases.
3. For generation, call `estimate` with the exact planned parameters. Present the returned amount or pricing description accurately. A formula is not a confirmed numeric total.
4. When the user has authorized generation, submit once with `generate ENDPOINT ... --download`. For an asynchronous job, use `--no-wait`, preserve the request ID and status URL, and later use `status REQUEST_ID --wait --download`.
5. If local input media is required, use `upload FILE` and pass its returned URL in the endpoint's documented parameter. Uploading sends that file to Higgsfield.
6. Report the terminal status and absolute downloaded paths. Embed each downloaded image, video, or audio in the same chat response with `![descriptive label](/absolute/path/to/file)` where the host supports local media previews. Link any other artifact using an absolute local file path. The files remain in the task working directory; chat previews reference those files.

Read [references/cli-and-api.md](references/cli-and-api.md) for exact commands, setup, recovery, model discovery, and endpoint limits.

## Operational limits

- Generation uses the user's Higgsfield API balance. Estimation is preferred before submitting paid work.
- Do not automatically repeat a generation POST after an ambiguous timeout. Check local history and the Higgsfield Console first; the CLI has no idempotency key.
- Treat `failed`, `nsfw`, and `canceled` as terminal failures. Resume an existing request instead of submitting it again when polling or downloading was interrupted.
- Use authenticated estimates for pricing. A strict budget needs a numeric quote or a separate decision by the user.
- Download wanted media promptly; remote output retention is limited.
- Never include credentials in request payloads, command arguments, generated files, or responses.
