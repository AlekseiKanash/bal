# CLAUDE.md

Python 3 CLI tool that manages a local LLM session via ollama: starts the server, loads a model, shows a live stats header, and runs an input loop.

## Project map

| File | What it is |
|---|---|
| `ollama-session.py` | Entry point. `OllamaSession` class + CLI arg parsing, session UI, input loop |
| `requirements.txt` | Python dependencies (`psutil`) |
| `install.sh` | Installs the tool to `~/.local/share/ollama-session/` and creates a wrapper at `~/.local/bin/ollama-session` |
| `widgets/header.py` | `SessionHeader` class — ANSI stats line pinned to a fixed terminal row |
| `widgets/meter.py` | `ValueMeter` class — progress bar + sparkline widget pinned to a fixed terminal row |
| `widgets/horizontal_text.py` | `HorizontalText` class — renders a single line of text pinned to a fixed terminal row |
| `widgets/border.py` | `Border` class — rectangular frame overlay; always rendered last so frame chars appear on top of content |
| `docs/spec.md` | Full specification — architecture, endpoints, startup sequence, termination |
| `docs/ollama_session.md` | `OllamaSession` reference — attributes, `start()`, `cleanup()`, private methods |
| `docs/session_header.md` | `SessionHeader` reference — constructor, `start()`, `tick()`, ANSI sequence |
| `docs/meter.md` | `ValueMeter` reference — constructor, `tick()`, `render()`, `draw()` |
| `docs/horizontal_text.md` | `HorizontalText` reference — constructor, `tick()`, ANSI sequence |
| `docs/border.md` | `Border` reference — constructor, `tick()`, `draw()`, Z-order behavior |

## Key facts

- ollama REST API on `http://localhost:11434`, accessed via `urllib` only (no third-party HTTP libs)
- `psutil` is used for system metrics (CPU utilization); `psutil.cpu_percent(interval=None)` is seeded once in `_build_ui` before any widget reads it
- CPU/GPU power consumption read by `_PowermetricsSampler` — background daemon thread running `sudo powermetrics`; getters read from a lock-protected cache
- `OllamaSession` owns the server process; model loading is done by `init_ollama()` after `start()`, skipped when `--dry-run` is set
- `SessionHeader` reads `_version` and `_model_name` directly from the `OllamaSession` instance
- Update loop in `_run_update_loop`: calls `tick(now)` on every widget, then flushes stdout once — single flush prevents flicker between intermediate draw states
- `_build_sorted_list` assigns rows to auto widgets, sorts by `_row`, then appends `Border` instances last so they render as overlays
- Graceful shutdown registered via `atexit` — unloads model, stops server only if we started it

## Coding guide

See [docs/coding_guide.md](docs/coding_guide.md).
