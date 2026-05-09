# CLAUDE.md

Python 3 CLI tool that manages a local LLM session via ollama: starts the server, loads a model, shows a live stats header, and runs an input loop.

## Project map

| File | What it is |
|---|---|
| `spec.md` | Full specification — architecture, endpoints, startup sequence, termination |
| `ollama-session.py` | Entry point. `OllamaSession` class + CLI arg parsing, session UI, input loop |
| `header.py` | `SessionHeader` class — ANSI stats line pinned to terminal row 1 |
| `ollama_session.md` | `OllamaSession` reference — attributes, `start()`, `cleanup()`, private methods |
| `session_header.md` | `SessionHeader` reference — constructor, `start()`, `update()`, ANSI sequence |

## Key facts

- ollama REST API on `http://localhost:11434`, accessed via `urllib` only (no third-party HTTP libs)
- `OllamaSession` owns the server process and model lifecycle; `SessionHeader` is a pure display object
- `SessionHeader` reads `_version` and `_model_name` directly from the `OllamaSession` instance
- Update loop lives in `ollama-session.py` (`_run_update_loop`); `SessionHeader` has no threads
- Graceful shutdown registered via `atexit` — unloads model, stops server only if we started it

## Coding guide

See [coding_guide.md](coding_guide.md).
