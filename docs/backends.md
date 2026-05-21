# Backend Bridge

**Package:** `bal.backends`

**Classes:** `OllamaBackend`, `OmlxBackend`

## Purpose

Each concrete backend encapsulates all logic for starting and interacting with its respective backend server. The CLI talks to backends only through the public bridge surface exported by `bal.backends`.

Backend-specific HTTP endpoints, settings files, subprocess commands, model discovery, and agent execution live under `bal/backends/`.

## Shared Public Interface

| Member | Type | Description |
|---|---|---|
| `backend_name` | `str` | `"ollama"` or `"omlx"` |
| `model_name` | property `str` | Model name passed via `--model`, or `"(none)"` |
| `version` | property `str \| None` | Server version; populated by `start()` |
| `start()` | method | Start or attach to the server, then populate `version` |
| `preload_model()` | method | Load the model into memory; no-op for omlx |
| `cleanup()` | method | Unload/stop resources owned by this session |
| `launch_command(agent)` | method | Return the `bal <agent> <model>` UI hint |
| `resolve_model(model_arg)` | method | Resolve an optional model argument for agent proxy mode |
| `exec_agent(agent, model)` | method | Execute the backend-specific agent command |

## Bridge Functions

| Function | Description |
|---|---|
| `create_backend(name, model_name, model_dir=None)` | Instantiate the selected backend |
| `detect_running_backend()` | Return the name of the currently running backend, or `None` |
| `list_available_models()` | Return `ModelChoice` entries from running APIs or local fallback scans |
| `find_backend_model_matches(model_name)` | Return matching `(backend, model)` pairs for disambiguation |
| `scan_local_models_by_backend()` | Return local model names grouped by backend for `bal list` |

### `start()`

Runs the server startup sequence:
1. Checks if the server is already running.
   - **ollama**: exits with code 1 if already running (exclusive lifecycle ownership).
   - **omlx**: attaches to the running instance; `_serve_process` stays `None` so cleanup never stops it.
2. Starts the server as a background subprocess and waits for it to become ready (up to 30 seconds). If the server does not start in time, the spawned process is terminated before exiting with code 1.
3. Fetches the server version and exposes it through `version`.

After `start()` returns, the server is up and `version` is populated. Model loading is **not** done here — it is the caller's responsibility (see `init_session`).

### `cleanup()`

Runs the graceful shutdown sequence. Terminates the server subprocess if this instance started it; leaves it running otherwise.

For `OllamaBackend`, also unloads the model first via POST `/api/generate` with `keep_alive: 0`.

Registered with `atexit` by `init_session()` so it runs on both normal exit and `sys.exit()`. SIGTERM is also handled by `run_input_loop` and calls `sys.exit(0)`, which triggers `atexit`.

### `launch_command(agent)`

Returns the `bal <agent> <model>` command shown in the UI hint section. Both backends return the same format.

### `preload_model()`

Loads the model into memory.

- **OllamaBackend**: POST `/api/generate` with `keep_alive: -1`; streams progress to stdout; exits with code 1 on error.
- **OmlxBackend**: POST `/v1/chat/completions` with `max_tokens: 1` to trigger eager load; prints a warning on failure but does not exit.

### Cleanup Model Handling

Evicts the model from memory.

- **OllamaBackend**: POST `/api/generate` with `keep_alive: 0`; errors are silently swallowed.
- **OmlxBackend**: no-op — omlx uses LRU eviction.

## `OllamaBackend`

```python
OllamaBackend(model_name: str)
```

Communicates with `http://localhost:11434` using the ollama REST API.

### Private Methods

| Method | Description |
|---|---|
| `_wait_for_server_ready()` | Polls `is_server_running()` until ready or 30 s timeout |
| `_start_server()` | Spawns `ollama serve` as a background `Popen` process |
| `_ensure_server_running()` | Checks health, starts server if needed; terminates process and exits on timeout |
| `_fetch_version()` | GET `/api/version`; returns version string or `"unknown"` |
| `_unload_model()` | POST `/api/generate` with `keep_alive: 0`; swallows errors |

## `OmlxBackend`

```python
OmlxBackend(model_name: str, model_dir: str | None = None)
```

Source repo: https://github.com/jundot/omlx

Communicates with the URL and port read from `~/.omlx/settings.json` (`server.host` / `server.port`; defaults: `127.0.0.1:8000`) using the OpenAI-compatible REST API.

Settings (`api_key`, `server_url`, `model_dir`) are loaded from `~/.omlx/settings.json` in `__init__`, so the instance is fully configured at construction — before `start()` is called. This is required for the agent proxy path, which creates a backend without calling `start()`.

`model_dir` defaults to `~/.omlx/models` (or the value from `settings.model.model_dir`) and is passed to `omlx serve --model-dir`.

### Private Methods

| Method | Description |
|---|---|
| `_is_server_running()` | GET `/v1/models` health check using the instance's `_server_url`; returns bool |
| `_wait_for_server_ready()` | Polls `_is_server_running()` until ready or 30 s timeout |
| `_start_server()` | Spawns `omlx serve --model-dir <path>` as a background `Popen` process |
| `_ensure_server_running()` | Attaches if running; starts server if not; terminates process and exits on timeout |
| `_fetch_version()` | GET `/api/status`; returns version string or `"unknown"` |

## `init_session(backend, model_name, model_dir=None, dry_run=False)`

Module-level factory function. Instantiates the appropriate backend class based on `backend`, calls `start()`, and conditionally loads the model:

- **Normal mode**: calls `preload_model()` to load the model into memory.
- **Dry-run mode** (`--dry-run`): skips model loading; the server is started but no model is resident.

Registers `cleanup()` with `atexit` in both modes.

## Lifecycle

```
init_session(backend, model_name)
        │
        ├─ OllamaBackend(model_name)  or  OmlxBackend(model_name, model_dir)
        │         └─ settings loaded at __init__ (omlx only)
        │
    backend.start()          ← server up, version set; model NOT yet loaded
        │
  preload_model()            ← called by init_session() unless --dry-run
        │
        │  (interactive session runs)
        │
    backend.cleanup()        ← model unloaded (ollama only), server stopped if we started it
```
