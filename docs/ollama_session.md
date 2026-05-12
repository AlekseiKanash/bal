# Session Classes

**File:** `ollama-session.py`  
**Classes:** `OllamaSession`, `OmlxSession`

## Purpose

Each class encapsulates all logic for starting and interacting with its respective backend server. They manage the server process, model lifecycle, and expose version and model name for display by `SessionHeader`.

Both classes share the same public interface so the rest of the code is backend-agnostic.

## Shared Public Interface

### Attributes

| Attribute | Type | Set by | Description |
|---|---|---|---|
| `backend_name` | class attr `str` | declaration | `"ollama"` or `"omlx"` |
| `_model_name` | `str` | constructor | Name of the model to load |
| `_version` | `str \| None` | `start()` | Server version string; `None` until `start()` is called |

### `start()`

Runs the server startup sequence:
1. Checks if the server is already running; exits with code 1 if it is.
2. Starts the server as a background subprocess and waits for it to become ready (up to 30 seconds).
3. Fetches the server version and stores it in `_version`.

After `start()` returns, the server is up and `_version` is populated. Model loading is **not** done here — it is the caller's responsibility (see `init_session`).

### `cleanup()`

Runs the graceful shutdown sequence. Terminates the server subprocess if this instance started it; leaves it running otherwise.

For `OllamaSession`, also unloads the model first via POST `/api/generate` with `keep_alive: 0`.

Registered with `atexit` by `init_session()` so it runs on both normal exit and `sys.exit()`.

### `_preload_model()`

Loads the model into memory.

- **OllamaSession**: POST `/api/generate` with `keep_alive: -1`; streams progress to stdout; exits with code 1 on error.
- **OmlxSession**: no-op — omlx auto-loads models on first inference request.

### `_unload_model()`

Evicts the model from memory.

- **OllamaSession**: POST `/api/generate` with `keep_alive: 0`; errors are silently swallowed.
- **OmlxSession**: no-op — omlx uses LRU eviction.

## `OllamaSession`

```python
OllamaSession(model_name: str)
```

Communicates with `http://localhost:11434` using the ollama REST API.

### Private Methods

| Method | Description |
|---|---|
| `_is_server_running()` | GET `/` health check; returns bool |
| `_wait_for_server_ready()` | Polls `_is_server_running()` until ready or 30 s timeout |
| `_start_server()` | Spawns `ollama serve` as a background `Popen` process |
| `_ensure_server_running()` | Orchestrates server check and conditional start; returns the process or exits |
| `_fetch_version()` | GET `/api/version`; returns version string or `"unknown"` |

## `OmlxSession`

```python
OmlxSession(model_name: str, model_dir: str | None = None)
```

Communicates with `http://localhost:8000` using the OpenAI-compatible REST API.

`model_dir` defaults to `~/.omlx/models` and is passed to `omlx serve --model-dir`.

### Private Methods

| Method | Description |
|---|---|
| `_is_server_running()` | GET `/v1/models` health check; returns bool |
| `_wait_for_server_ready()` | Polls `_is_server_running()` until ready or 30 s timeout |
| `_start_server()` | Spawns `omlx serve --model-dir <path>` as a background `Popen` process |
| `_ensure_server_running()` | Orchestrates server check and conditional start; returns the process or exits |
| `_fetch_version()` | Runs `omlx --version`; returns version string or `"unknown"` |

## `init_session(backend, model_name, model_dir=None, dry_run=False)`

Module-level factory function. Instantiates the appropriate session class based on `backend`, calls `start()`, and conditionally loads the model:

- **Normal mode**: calls `_preload_model()` to load the model into memory.
- **Dry-run mode** (`--dry-run`): skips model loading; the server is started but no model is resident.

Registers `cleanup()` with `atexit` in both modes.

## Lifecycle

```
init_session(backend, model_name)
        │
        ├─ OllamaSession(model_name)  or  OmlxSession(model_name, model_dir)
        │
    session.start()          ← server up, _version set; model NOT yet loaded
        │
  _preload_model()           ← called by init_session() unless --dry-run
        │
        │  (interactive session runs)
        │
    session.cleanup()        ← model unloaded (ollama only), server stopped if we started it
```
