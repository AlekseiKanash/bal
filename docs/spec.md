# ollama-session — Specification

## Overview

`ollama-session` is a Python CLI tool with two modes of operation:

1. **Server mode** — starts a local LLM backend, loads a model, and shows a live terminal UI with system metrics and agent launch hints.
2. **Agent proxy mode** — auto-detects the running backend and `exec`s the appropriate agent command, replacing itself with the agent process.

Two backends are supported:

| Backend | Binary | Base URL | API style |
|---|---|---|---|
| `ollama` (default) | `ollama` | `http://localhost:11434` | ollama REST API |
| `omlx` | `omlx` | `http://localhost:8000` | OpenAI-compatible REST API |

## Usage

```
ollama-session <agent> [model]          launch agent against running backend
ollama-session list                     show available models (no server needed)
ollama-session --model <name> [options] start server, load model, show live UI

agents:  claude  codex  opencode  openclaw
```

Typical two-terminal workflow:

```
# Terminal 1 — start server and load model
ollama-session --model Qwen3 --backend omlx

# Terminal 2 — launch an agent against it
ollama-session claude
ollama-session claude Qwen3   # explicit model name
```

### `list` command

Prints all available models for every backend and the exact command to start a session with each one:

```
Available models:

ollama
     llama3:latest                                ollama-session --model llama3:latest
omlx
     Qwen3.6-35B-A3B-MLX-8bit                    ollama-session --model Qwen3.6-35B-A3B-MLX-8bit --backend omlx
     Qwen3.6-35B-A3B-UD-MLX-4bit                 ollama-session --model Qwen3.6-35B-A3B-UD-MLX-4bit --backend omlx
```

Both backends are discovered from the filesystem — no server needs to be running.

- **ollama**: walks `~/.ollama/models/manifests/` and collects manifest files; names are reconstructed as `model:tag` for standard library models.
- **omlx**: lists subdirectories of `~/.omlx/models`.

### Server mode flags

| Flag | Required | Default | Description |
|---|---|---|---|
| `--model` | Yes (unless `--dry-run`) | — | Model name to load |
| `--backend` | No | `ollama` | Backend to use: `ollama` or `omlx` |
| `--model-dir` | No | `~/.omlx/models` | Model directory passed to `omlx serve` |
| `--dry-run` | No | off | Start the server and show the UI without loading a model |

Example:

```
ollama-session --model llama3
ollama-session --model llama3 --backend omlx --model-dir ~/models
ollama-session --dry-run
ollama-session --dry-run --backend omlx
```

## Components

| File | Responsibility |
|---|---|
| `ollama-session.py` | Entry point. CLI argument parsing, `OllamaSession` / `OmlxSession` classes, session UI orchestration, input loop, agent proxy subcommand. See [ollama_session.md](ollama_session.md). |
| `widgets/header.py` | `SessionHeader` class — renders and continuously updates the stats line pinned to row 1 of the terminal. See [session_header.md](session_header.md). |
| `widgets/meter.py` | `ValueMeter` class — progress bar + sparkline widget pinned to a fixed terminal row. See [meter.md](meter.md). |
| `widgets/horizontal_text.py` | `HorizontalText` class — renders a single line of text pinned to a fixed terminal row. See [horizontal_text.md](horizontal_text.md). |
| `widgets/border.py` | `Border` class — draws a rectangular frame at a fixed terminal position; always rendered last (overlay). See [border.md](border.md). |

## Backend Interface

Both session classes expose the same interface so the rest of the code is backend-agnostic:

| Member | Type | Description |
|---|---|---|
| `backend_name` | class attr `str` | `"ollama"` or `"omlx"` |
| `_model_name` | instance attr `str` | Model name passed via `--model` |
| `_version` | instance attr `str \| None` | Server version; populated by `start()` |
| `start()` | method | Start or attach to the server, populate `_version` |
| `cleanup()` | method | Unload the model and stop the server (if we started it) |
| `_preload_model()` | method | Load the model (no-op for omlx) |
| `_unload_model()` | method | Unload the model (no-op for omlx) |

## Ollama Backend

ollama exposes a REST API on `http://localhost:11434`.
Communication uses Python's built-in `urllib` — no third-party HTTP libraries.

Key endpoints used:

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Health check — returns `"Ollama is running"` when ready |
| `/api/version` | GET | Returns `{"version": "0.6.1"}` |
| `/api/generate` | POST | Load or unload a model |

**Load model** — POST `/api/generate`:
```json
{"model": "<model-name>", "keep_alive": -1}
```
`keep_alive: -1` keeps the model resident in memory indefinitely.

**Unload model** — POST `/api/generate`:
```json
{"model": "<model-name>", "keep_alive": 0}
```
`keep_alive: 0` immediately evicts the model from memory.

## omlx Backend

omlx exposes an OpenAI-compatible REST API on `http://localhost:8000`.
Started with `omlx serve --model-dir <path>`.

Key endpoints used:

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/models` | GET | Health check — any HTTP response (including 401) confirms the server is listening |

Version is read by running `omlx --version` as a subprocess.

Model preloading and unloading are not performed via the API — omlx auto-loads models on first request and uses LRU eviction when memory pressure requires it.

**API key authentication:** omlx enables API key auth by default, so `GET /v1/models` returns 401 when no key is supplied. The health check treats any HTTP-level response as "server is up" — only connection-level failures (refused, timeout) count as "not running".

omlx is commonly kept running as a persistent background service (e.g. via `brew services` or the macOS menu-bar app). When the script finds omlx already listening on port 8000 it attaches to that instance instead of starting a new one.

## Startup Sequence (Server Mode)

1. Parse CLI arguments. Exit with a clear error if `--model` is missing and `--dry-run` is not set.
2. Check if the backend server is already running using its health endpoint.
   - **ollama — already running**: exit with code 1 (the script wants exclusive control for model lifecycle management).
   - **ollama — not running**: start `ollama serve` as a background subprocess and poll the health endpoint until it responds (up to 30 seconds).
   - **omlx — already running**: attach to the existing instance; `_serve_process` remains `None` so cleanup will not stop it.
   - **omlx — not running**: start `omlx serve --model-dir <path>` as a background subprocess and poll until ready (up to 30 seconds).
3. Retrieve the server version.
4. Unless `--dry-run`: load the model into memory. For ollama this streams progress to stdout; for omlx this is a no-op.
5. Clear the terminal and build the widget UI.
6. Enter the command input loop.

Steps 2–3 are encapsulated in each session class's `start()`. Step 4 is called by `init_session()` so it can be skipped in dry-run mode. The startup log is visible before the terminal is cleared, so any errors or warnings appear naturally.

## Stats Header

See [session_header.md](session_header.md) for full documentation of the `SessionHeader` class.

The header is displayed on the first line of the terminal and updated in-place every second:

```
Ollama-Session | ollama 0.6.1 | Loaded: llama3 | Running: 0:02:34
Ollama-Session | omlx 0.3.8   | Loaded: llama3 | Running: 0:02:34
```

The backend name in the header comes from the session's `backend_name` attribute.

## System Meters

Three `ValueMeter` widgets render inside a `Border` frame below the header, each updated every second:

| Meter | Load source | Power source | Unit |
|---|---|---|---|
| CPU | `psutil.cpu_percent()` | `sudo powermetrics --samplers cpu_power` | % / W |
| GPU | `ioreg -c AGXAccelerator` `"Device Utilization %"` (macOS); `0` elsewhere | same `powermetrics` sample | % / W |
| RAM | `vm_stat` anonymous + wired + compressor pages (macOS); `psutil` `total − available` elsewhere | — | GB |

Each meter shows: progress bar (load %), color-coded percentage, sparkline history, and trailing power in watts (CPU/GPU) or current value (RAM).

Power is sampled by `_PowermetricsSampler`, a background daemon thread that runs `sudo powermetrics` continuously and caches the latest CPU/GPU watt values behind a lock. Getters read from the cache non-blockingly.

See [meter.md](meter.md) for full `ValueMeter` documentation.

## Widget Render Loop

All widgets implement `tick(now: float)`. The update loop calls every widget's `tick()` once per second, then flushes stdout once. Flushing after all widgets have drawn (rather than per widget) ensures the terminal receives a complete frame atomically — preventing visible flicker between intermediate states.

`_build_sorted_list` sorts regular widgets by `_row` and appends `Border` instances last so their frame chars always render on top of content.

## Agent Hints

Below the meter border, the UI displays a static section showing how to launch each agent against the running model. Commands are generated by `session.launch_command(agent, model_name)` and are identical for both backends:

```
  ollama-session claude <model-name>
  ollama-session codex <model-name>
  ollama-session opencode <model-name>
  ollama-session openclaw <model-name>
```

## Agent Proxy Mode

When the first argument is an agent name, the script auto-detects the running backend and `exec`s the appropriate command, replacing itself with the agent process.

**Backend detection order:**
1. Try `GET {omlx_url}/v1/models` — any HTTP response → omlx
2. Try `GET http://localhost:11434/` — 200 OK → ollama
3. Neither responding → error and exit 1

**Model resolution:**
- Model name provided as second argument → use it directly
- Omitted + omlx → query `GET /v1/models`, use `data[0].id`
- Omitted + ollama → omit `--model` from the launch command

**Command construction (`_exec_agent`):**

| Backend | Agent | Command |
|---|---|---|
| omlx | `claude` | `os.execvpe("claude", ...)` with `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`, `API_TIMEOUT_MS=3000000`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` |
| omlx | others | `omlx launch <agent> [--model <model>] --api-key <key>` |
| ollama | any | `ollama launch <agent> [--model <model>]` |

Settings (`api_key`, `server_url`) are read from `~/.omlx/settings.json` via `_load_omlx_settings()`.

## Input Loop

After the stats header is shown, the script reads user input line by line:

- Lines beginning with `/` are treated as commands and dispatched to a command handler.
- All other input is silently ignored in this iteration (future iterations will route it to the model).

No user-facing commands are defined yet other than the termination mechanism described below.

## Termination

| Trigger | Behavior |
|---|---|
| `Ctrl-C` (SIGINT) | Run graceful shutdown (see below), restore the terminal, and exit. |
| Script killed / terminal closed | `atexit` registration ensures graceful shutdown runs on normal and `sys.exit()` paths. |

**Graceful shutdown sequence (ollama):**
1. Unload the model via POST `/api/generate` with `keep_alive: 0`.
2. If the script started `ollama serve` itself, terminate that subprocess. If ollama was already running when the script started, leave it running.
3. Restore the terminal to a clean state (cursor visible, no dangling ANSI codes).

**Graceful shutdown sequence (omlx):**
1. If the script started `omlx serve` itself, terminate that subprocess. If the script attached to a pre-existing omlx instance, leave it running.
2. Restore the terminal to a clean state.

## Out of Scope for This Iteration

- Sending user input to the model and displaying responses
- Any `/`-prefixed commands beyond graceful exit
- Session history or logging
- Multi-model or model-switching support
- Custom server host or port overrides
