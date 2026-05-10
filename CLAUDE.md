# CLAUDE.md

Python 3 CLI tool that manages a local LLM session via ollama: starts the server, loads a model, shows a live stats header, and runs an input loop.

## Project map

| File | What it is |
|---|---|
| `spec.md` | Full specification — architecture, endpoints, startup sequence, termination |
| `ollama-session.py` | Entry point. `OllamaSession` class + CLI arg parsing, session UI, input loop |
| `header.py` | `SessionHeader` class — ANSI stats line pinned to a fixed terminal row |
| `meter.py` | `ValueMeter` class — progress bar + sparkline widget pinned to a fixed terminal row |
| `horizontal_text.py` | `HorizontalText` class — renders a single line of text pinned to a fixed terminal row |
| `ollama_session.md` | `OllamaSession` reference — attributes, `start()`, `cleanup()`, private methods |
| `session_header.md` | `SessionHeader` reference — constructor, `start()`, `tick()`, ANSI sequence |
| `meter.md` | `ValueMeter` reference — constructor, `tick()`, `render()`, `draw()` |
| `horizontal_text.md` | `HorizontalText` reference — constructor, `tick()`, ANSI sequence |

## Key facts

- ollama REST API on `http://localhost:11434`, accessed via `urllib` only (no third-party HTTP libs)
- `OllamaSession` owns the server process and model lifecycle; `SessionHeader` and `ValueMeter` are pure display objects
- `SessionHeader` reads `_version` and `_model_name` directly from the `OllamaSession` instance
- Update loop lives in `ollama-session.py` (`_run_update_loop`); it passes a shared `now` timestamp to every updatable object's `tick(now)` method
- `_build_ui` constructs all widgets; `_build_sorted_list` assigns rows to widgets with `row=None` and sorts all widgets by row
- Graceful shutdown registered via `atexit` — unloads model, stops server only if we started it

## Coding guide

See [coding_guide.md](coding_guide.md).
