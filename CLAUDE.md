# CLAUDE.md

Python 3 CLI tool that manages a local LLM session via ollama or omlx: starts the server, loads a model, shows a live stats header, and runs an input loop.

## Project map

| File | What it is |
|---|---|
| `ollama-session.py` | Entry point. `OllamaSession` / `OmlxSession` classes + CLI arg parsing, session UI, input loop |
| `requirements.txt` | Python dependencies (`psutil`) |
| `install.sh` | Installs the tool to `~/.local/share/ollama-session/` and creates a wrapper at `~/.local/bin/ollama-session` |
| `widgets/header.py` | `SessionHeader` class — ANSI stats line pinned to a fixed terminal row |
| `widgets/meter.py` | `ValueMeter` class — progress bar + sparkline widget pinned to a fixed terminal row |
| `widgets/horizontal_text.py` | `HorizontalText` class — renders a single line of text pinned to a fixed terminal row |
| `widgets/border.py` | `Border` class — rectangular frame overlay; always rendered last so frame chars appear on top of content |
| `docs/spec.md` | Full specification — architecture, endpoints, startup sequence, termination |
| `docs/ollama_session.md` | `OllamaSession` / `OmlxSession` reference — attributes, `start()`, `cleanup()`, private methods |
| `docs/session_header.md` | `SessionHeader` reference — constructor, `start()`, `tick()`, ANSI sequence |
| `docs/meter.md` | `ValueMeter` reference — constructor, `tick()`, `render()`, `draw()` |
| `docs/horizontal_text.md` | `HorizontalText` reference — constructor, `tick()`, ANSI sequence |
| `docs/border.md` | `Border` reference — constructor, `tick()`, `draw()`, Z-order behavior |

## Key facts

- Two backends supported: `ollama` (REST on `http://localhost:11434`) and `omlx` (OpenAI-compatible REST on `http://localhost:8000`); selected via `--backend`
- `http_get` / `http_post` accept a `base_url` parameter so both backends share the same HTTP helpers
- `psutil` is used for system metrics (CPU utilization); `psutil.cpu_percent(interval=None)` is seeded once in `_build_ui` before any widget reads it
- CPU/GPU power consumption read by `_PowermetricsSampler` — background daemon thread running `sudo powermetrics`; getters read from a lock-protected cache
- Each backend class (`OllamaSession`, `OmlxSession`) exposes the same interface: `backend_name`, `_model_name`, `_version`, `start()`, `cleanup()`, `_preload_model()`, `_unload_model()`, `launch_command(agent, model_name)`
- `OmlxSession` reads `~/.omlx/settings.json` at init time for `auth.api_key`, `server.host`, `server.port`, and `model.model_dir`
- `OmlxSession.launch_command()` produces `omlx launch <agent> --model <model> --api-key <key>`; `OllamaSession.launch_command()` produces `ollama launch <agent> --model <model>`
- omlx health check treats any HTTP response (including 401) as "server up" — auth is enabled by default so unauthenticated requests return 401
- omlx attaches to a pre-existing server instead of exiting; `_serve_process` stays `None` so cleanup does not stop it
- Session is created by `init_session(backend, model_name, model_dir, dry_run)`, which calls `start()` and conditionally `_preload_model()`; skips both when `--dry-run` is set
- `SessionHeader` reads `backend_name`, `_version`, and `_model_name` directly from the session instance
- `ollama-session.py list` scans `~/.ollama/models/manifests` (ollama) and `~/.omlx/models` (omlx) from disk — no server required
- Update loop in `_run_update_loop`: calls `tick(now)` on every widget, then flushes stdout once — single flush prevents flicker between intermediate draw states
- `_build_sorted_list` assigns rows to auto widgets, sorts by `_row`, then appends `Border` instances last so they render as overlays
- Graceful shutdown registered via `atexit` — unloads model, stops server only if we started it

## Coding guide

See [docs/coding_guide.md](docs/coding_guide.md).
