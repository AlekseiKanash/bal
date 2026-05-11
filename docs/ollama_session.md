# OllamaSession

**File:** `ollama-session.py`  
**Class:** `OllamaSession`

## Purpose

Encapsulates all logic for starting and interacting with the ollama server. Manages the server process, model lifecycle, and exposes version and model name for display by `SessionHeader`.

## Constructor

```python
OllamaSession(model_name: str)
```

Stores the model name. Does not start the server or touch the network.

## Public Interface

### Attributes

| Attribute | Type | Set by | Description |
|---|---|---|---|
| `_model_name` | `str` | constructor | Name of the model to load |
| `_version` | `str \| None` | `start()` | ollama server version string; `None` until `start()` is called |

### `start()`

Runs the server startup sequence:
1. Checks if the ollama server is already running; exits with code 1 if it is.
2. Starts `ollama serve` as a background subprocess and waits for it to become ready.
3. Fetches the server version via GET `/api/version` and stores it in `_version`.

After `start()` returns, the server is up and `_version` is populated. Model loading is **not** done here — it is the caller's responsibility (see `init_ollama`).

### `cleanup()`

Runs the graceful shutdown sequence:
1. Unloads the model via POST `/api/generate` with `keep_alive: 0`.
2. Terminates the `ollama serve` subprocess if this instance started it; leaves it running otherwise.

Registered with `atexit` by `init_ollama()` so it runs on both normal exit and `sys.exit()`.

## `init_ollama(model_name, dry_run=False)`

Module-level factory function. Creates an `OllamaSession`, calls `start()`, and conditionally loads the model:

- **Normal mode**: calls `_preload_model()` to load the model into memory.
- **Dry-run mode** (`--dry-run`): skips model loading; the server is started but no model is resident.

Registers `cleanup()` with `atexit` in both modes.

## Lifecycle

```
OllamaSession(model_name)   ← construct; no side effects
        │
    session.start()          ← server up, _version set; model NOT yet loaded
        │
  _preload_model()           ← called by init_ollama() unless --dry-run
        │
        │  (interactive session runs)
        │
    session.cleanup()        ← model unloaded, server stopped if we started it
```

## Private Methods

| Method | Description |
|---|---|
| `_is_server_running()` | GET `/` health check; returns bool |
| `_wait_for_server_ready()` | Polls `_is_server_running()` until ready or timeout |
| `_start_server()` | Spawns `ollama serve` as a background `Popen` process |
| `_ensure_server_running()` | Orchestrates server check and conditional start; returns the process or exits |
| `_fetch_version()` | GET `/api/version`; returns version string or `"unknown"` |
| `_preload_model()` | POST `/api/generate` with `keep_alive: -1`; streams progress to stdout |
| `_unload_model()` | POST `/api/generate` with `keep_alive: 0`; errors are silently swallowed |
