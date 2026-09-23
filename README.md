# Higgsfield-API skill

Generate media using your Higgsfield API account, estimate costs, upload inputs, follow requests, and download results. This local Python client calls Higgsfield directly and does not require Higgsfield MCP. Generation uses your Higgsfield API balance; any AI assistant you use has separate billing. The package is composed by two main part whic are the Python CLI and the skill package and below more details about it:

| Part | Purpose | Requirements |
| --- | --- | --- |
| Python CLI | Executes API requests and downloads media | This checkout, Python, dependencies, credentials, internet |
| `skills/higgsfield-api/` | Teaches an assistant how to operate the CLI | A working CLI and an assistant able to read files and execute commands |

**The skill is instructions, not a standalone generator.** Copying it does not install the CLI or copy your credentials. Keep one working project and point your assistants at it, or set up the project on another machine.

Most important you must just create the `.env` in your editor and enter the two values in the API KEY section from the [Higgsfield Console](https://console.higgsfield.ai):

```dotenv
HF_API_KEY_ID=your-key-id
HF_API_KEY_SECRET=your-key-secret
```
Keep credentials out of prompts, shell arguments, screenshots, and shared files. The client sends the documented [Authorization header](https://docs.higgsfield.ai/docs/authentication).

## My Python CLI Technicality (managed automatically by the agent using the skill)

Python 3.12 or newer is required; Python 3.13 is the recommended runtime, selected in `.python-version`. The default `.venv` has been rebuilt on Python 3.13.12 with locked dependencies. The old environment is preserved as `.venv-legacy-python39` for recovery only; do not use it for current development. Keep the checkout in its intended permanent location and install in editable mode. Default credentials, history, and downloads are located relative to the source checkout.

For reproducible installation, use uv 0.11.4 and the included `uv.lock`. With uv and Python 3.13 installed, a fresh checkout can use:

```bash
uv sync --locked --extra dev --python 3.13
uv run --no-sync pytest -q
uv run --no-sync higgsfield doctor
```

This manages `.venv`. A separate locked validation environment is also available:

```bash
UV_PROJECT_ENVIRONMENT=.venv-production uv sync --locked --extra dev --python 3.13
./.venv-production/bin/python -m pytest -q
./.venv-production/bin/higgsfield doctor
```

You can substitute `./.venv-production/bin/higgsfield` in any example below. Both executables resolve the same credentials and `GENERATIONS/` directory. `uv sync --locked` fails if the lockfile needs updating; upgrade dependencies deliberately and rerun tests. Omit `--extra dev` for a runtime-only installation. The lock covers application/test dependencies; the isolated build backend is still selected from the packaging requirements.

The pip alternative below resolves dependency ranges instead of using the uv lock:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e '.[dev]'
```

For runtime dependencies without test tools, use `pip install -e .` instead. Activation is optional when using the explicit executable path. To use shorter commands in a terminal:

```bash
source .venv/bin/activate
higgsfield --help
# Later:
deactivate
```

Create the credentials file only if missing:

```bash
test -e .env || cp .env.example .env
chmod 600 .env
```

Open `.env` in your editor and enter the two values from the [Higgsfield Console](https://console.higgsfield.ai):

```dotenv
HF_API_KEY_ID=your-key-id
HF_API_KEY_SECRET=your-key-secret
```

The ID is the actual credential ID, not its friendly display name. The secret is its associated secret; do not infer these from string length. Quotes are optional for ordinary values: `HF_API_KEY_SECRET="your-key-secret"` also works. Keep credentials out of prompts, shell arguments, screenshots, and shared files. The client sends the documented [Authorization header](https://docs.higgsfield.ai/docs/authentication).

```bash
./.venv/bin/higgsfield doctor
./.venv/bin/higgsfield doctor --live
```

`doctor` checks local configuration without contacting Higgsfield. `--live` probes a deliberately nonexistent request: `authenticated: true` with `probe_status: 404` is the expected successful result. A `401` indicates invalid credentials. Neither command generates media.

| Configuration | Behavior |
| --- | --- |
| Project `.env` | Loaded automatically, even when the terminal is elsewhere |
| `--env-file /absolute/path/credentials.env` | Selects another credentials file; place **before** the subcommand |
| Exported environment variables | Override file values, including with `--env-file` |
| `HIGGSFIELD_REQUEST_TIMEOUT=30` | Per-request timeout in seconds, separate from total polling time |
| `HF_KEY` or `HF_CREDENTIALS` | Combined `ID:SECRET` compatibility format |
| `HF_API_KEY` / `HF_API_SECRET` | Compatibility aliases for ID / secret |

Prefer the two explicit credential variables and avoid mixing formats. An alternate credentials file does not change the output directory. `.env` and `.env.*` are ignored except `.env.example`; store other secret filenames outside the checkout or add appropriate ignore rules.

## Models and costs

```bash
./.venv/bin/higgsfield models
```

This now fetches every page of the public catalog used by Higgsfield's console. It includes model families/workflows, providers, output types, default modes, and public indicative pricing. 

```bash
./.venv/bin/higgsfield models --search seedance
./.venv/bin/higgsfield models --provider bytedance --output-type video
./.venv/bin/higgsfield models --search image --output-type image
./.venv/bin/higgsfield models --starters
```

For more and detailed information consult the [live catalog](https://console.higgsfield.ai/).

According to [Higgsfield billing and retention](https://docs.higgsfield.ai/docs/concepts/billing-and-retention), failed or moderated requests are uncharged/refunded, eligible canceled queued requests are refunded, and output remains available for at least seven days. Download files for long-term storage.

## Generate video and images

### Text to video

Estimate the tested starter example:

```bash
./.venv/bin/higgsfield estimate seedance-2-text \
  --set 'prompt=A cinematic tracking shot along a sunlit coastal road' \
  --set resolution=720p \
  --set generate_audio=true \
  --set duration=5 \
  --set aspect_ratio=16:9
```

After reviewing the amount, submit:

```bash
./.venv/bin/higgsfield generate seedance-2-text \
  --set 'prompt=A cinematic tracking shot along a sunlit coastal road' \
  --set resolution=720p \
  --set generate_audio=true \
  --set duration=5 \
  --set aspect_ratio=16:9 \
  --download
```

### Text to image

```bash
./.venv/bin/higgsfield estimate soul \
  --set 'prompt=Editorial portrait in soft daylight'
```

After reviewing the estimate:

```bash
./.venv/bin/higgsfield generate soul \
  --set 'prompt=Editorial portrait in soft daylight' \
  --download
```

## Local media inputs

Upload the input:

```bash
./.venv/bin/higgsfield upload /absolute/path/first-frame.jpg
```

This sends your media to external storage and returns `public_url`. Use that HTTPS URL in the generation request, not the local file path.

Documented upload formats include JPEG, PNG, WebP, GIF, WAV, and MP4. A selected model can impose further restrictions. See [file uploads](https://docs.higgsfield.ai/docs/concepts/file-uploads).

Replace `PUBLIC_IMAGE_URL` below with the upload result:

```bash
./.venv/bin/higgsfield estimate seedance-2-image \
  --set 'image_url=PUBLIC_IMAGE_URL' \
  --set 'prompt=Slow cinematic camera movement through the scene' \
  --set resolution=720p --set generate_audio=true --set duration=5
```

After reviewing the estimate, run the same command with `generate` instead of `estimate` and append `--download`.

For video/audio input, use an endpoint that supports it and its documented fields, such as `video_url` or `audio_url`. Existing publicly accessible HTTPS media can be supplied directly. `upload FILE --content-type image/jpeg` overrides MIME detection; it does not convert the file.

## Reusable requests and other endpoints

For repeatable jobs or complex prompts, create `request.json` in your editor:

```json
{
  "prompt": "A cinematic tracking shot along a sunlit coastal road",
  "resolution": "720p",
  "generate_audio": true,
  "duration": 5,
  "aspect_ratio": "16:9"
}
```

```bash
./.venv/bin/higgsfield estimate seedance-2-text --data-file request.json
# Run after reviewing cost:
./.venv/bin/higgsfield generate seedance-2-text --data-file request.json --download
```

Request JSON is not automatically ignored by Git. Review private prompts and input URLs before sharing it; never put credentials inside.

For another model, substitute its documented endpoint ID and compatible payload:

```bash
./.venv/bin/higgsfield estimate provider/model/workflow --data-file request.json
./.venv/bin/higgsfield generate provider/model/workflow --data-file request.json --download
```

| Input | Example | Meaning |
| --- | --- | --- |
| Repeated fields | `--set duration=5 --set generate_audio=true` | Parses JSON values; other text stays a string |
| Inline JSON | `--data '{"prompt":"Soft daylight portrait"}'` | Supplies one object |
| JSON file | `--data-file request.json` | Reads one object from disk |
| Override | `--data-file request.json --set duration=10` | Overrides a field |
| Nested field | `--set options.enabled=true` | Creates a nested object if the model accepts it |

Do not combine `--data` and `--data-file`. Both can be combined with `--set`. To force a numeric-looking string, use `--set 'field="123"'`. Quote shell prompts; use a JSON file for apostrophes or complicated punctuation.

## Background work and recovery

Submit without waiting:

```bash
./.venv/bin/higgsfield generate seedance-2-text --data-file request.json --no-wait
```

Preserve the returned `request_id` and `status_url`. Processing continues remotely after the command exits. Combining `--no-wait` with `--download` or `--output-dir` is rejected before submission. Use a later status command to download.

Replace the placeholders with the returned values:

```bash
# Inspect:
./.venv/bin/higgsfield status REQUEST_ID --status-url OFFICIAL_STATUS_URL

# Wait and download:
./.venv/bin/higgsfield status REQUEST_ID \
  --status-url OFFICIAL_STATUS_URL \
  --wait --download --wait-timeout 3600
```

Status URLs may use `api.higgsfield.ai` or `platform.higgsfield.ai`; both HTTPS hosts are accepted. Without `--status-url`, the command first recovers a saved URL from local history, then falls back to the API host. Preserve the URL for use on another machine.

Resume this way after closing the terminal, pressing Ctrl+C, reaching the polling timeout, or a download error. Stopping the local process does not cancel remote generation. **Do not run another generation to recover an existing one:** that creates another potentially billable job. After an ambiguous submission timeout, inspect local history and the Console before retrying.

```bash
./.venv/bin/higgsfield history --limit 20
./.venv/bin/higgsfield cancel REQUEST_ID
```

Cancellation is available only while the request remains eligible in the queue. The current command calls the API-host cancel endpoint; there is no `--cancel-url` option.

For custom integrations, generation accepts `--webhook https://your-service.example/higgsfield --no-wait`. This forwards a callback address to Higgsfield. This project does not include a webhook receiver, notification service, or automatic background downloader.

## Downloads and history

```text
Higgfields/
  .env                         Credentials
  .higgsfield/history.jsonl    Request events
  GENERATIONS/
    <request-id>/
      <provider-filename>.mp4  Or image/audio/other supported artifact
```

Append `--output-dir /absolute/path/my-media` to a downloading command to override the parent directory. The request-ID subfolder is still added. Relative overrides resolve from the terminal's current directory.

History records submissions, terminal responses, status lookups, downloads, and cancellation events. It is not a complete account job list. Terminal/status results are recorded before attempting downloads, preserving recovery information when a download fails. One request may have several entries; `--limit` counts events, not unique requests. Submitted prompt payloads are not explicitly recorded, so keep request JSON for reproducibility.

Credentials, history, and generated files are covered by `.gitignore`. This does not encrypt files, back them up, or exclude them from a manually created ZIP. Back up valuable media separately.

## Use with other AI systems

The CLI is independent of an AI provider. Compatibility depends on the host's tools and runtime.

| Environment | Approach |
| --- | --- |
| Local agent with terminal/filesystem access | Read the skill and execute this checkout's CLI |
| Agent supporting SKILL.md packages | Install the whole skill folder using that host's documented mechanism and point it at the CLI |
| Agent without native skill support | Supply the instructions and reference as task context |
| Remote/cloud agent | Install the project in its environment, inject credentials through its secret mechanism, retrieve outputs there |
| Chat-only assistant without execution tools | Ask for commands/prompts and execute them yourself |

There is no universal installation path or invocation syntax for every AI system. `$higgsfield-api` is the Codex example. `agents/openai.yaml` supplies Codex metadata; the operational guidance lives in `SKILL.md` and its reference.

## Official references

- [Documentation index](https://docs.higgsfield.ai/docs/llms.txt)
- [Model catalog](https://console.higgsfield.ai/)
- [Authentication](https://docs.higgsfield.ai/docs/authentication)
- [Requests](https://docs.higgsfield.ai/docs/concepts/requests)
- [Polling](https://docs.higgsfield.ai/docs/concepts/polling)
- [Uploads](https://docs.higgsfield.ai/docs/concepts/file-uploads)
- [Errors and retries](https://docs.higgsfield.ai/docs/concepts/errors)
- [Billing and retention](https://docs.higgsfield.ai/docs/concepts/billing-and-retention)
- [Codex skills](https://learn.chatgpt.com/docs/build-skills)
