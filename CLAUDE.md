# CLAUDE.md

## Project map

| File | What it is |
|---|---|
| `bal/cli.py` | Full implementation — backends, UI, agent proxy, `main()` |
| `bal/__init__.py` | Re-exports `main` from `bal.cli` |
| `bal/__main__.py` | `python -m bal` entry point |
| `bal.py` | Dev shim — `from bal import main` |
| `pyproject.toml` | Package metadata + setuptools-scm versioning |
| `install.sh` | Creates venv in `~/.local/share/bal/`, pip-installs from source, links `~/.local/bin/bal` |
| `Formula/bal.rb` | Homebrew formula — update `url` and `sha256` on each release |
| `bal/widgets/header.py` | `SessionHeader` — ANSI stats line pinned to a fixed terminal row |
| `bal/widgets/meter.py` | `ValueMeter` — progress bar + sparkline pinned to a fixed terminal row |
| `bal/widgets/horizontal_text.py` | `HorizontalText` — single line of text pinned to a fixed terminal row |
| `bal/widgets/border.py` | `Border` — rectangular frame overlay; always rendered last |
| `docs/spec.md` | Architecture, endpoints, startup sequence, termination |
| `docs/backends.md` | `OllamaBackend` / `OmlxBackend` reference |
| `docs/session_header.md` | `SessionHeader` reference |
| `docs/meter.md` | `ValueMeter` reference |
| `docs/horizontal_text.md` | `HorizontalText` reference |
| `docs/border.md` | `Border` reference |

## Key facts

- `http_get` / `http_post` accept a `base_url` parameter so both backends share the same HTTP helpers
- `psutil.cpu_percent(interval=None)` is seeded once in `_build_ui` before any widget reads it — prevents the first tick returning 0.0
- `_PowermetricsSampler` — background daemon thread running `sudo powermetrics`; `cpu_w()` / `gpu_w()` read from a lock-protected cache
- Both backends expose the same interface: `backend_name`, `_model_name`, `_version`, `start()`, `cleanup()`, `_preload_model()`, `_unload_model()`, `launch_command(agent, model_name)`
- `OmlxBackend` reads `~/.omlx/settings.json` at init time for `auth.api_key`, `server.host`, `server.port`, `model.model_dir`
- omlx source repo: https://github.com/jundot/omlx — refer to it for API details
- omlx health check treats any HTTP response (including 401) as "server up" — auth is on by default so unauthenticated requests return 401
- omlx attaches to a pre-existing server; `_serve_process` stays `None` so cleanup never stops it
- `init_session(backend, model_name, model_dir, dry_run)` — calls `start()` and conditionally `_preload_model()`; skips both on `--dry-run`
- `SessionHeader` reads `backend_name`, `_version`, `_model_name` directly from the session instance
- `_run_update_loop`: calls `tick(now)` on every widget then flushes stdout once — single flush prevents flicker
- `_build_sorted_list`: assigns rows to auto widgets, sorts by `_row`, appends `Border` instances last so they render as overlays
- Graceful shutdown via `atexit` — unloads model, stops server only if this session started it

## Agent proxy subcommand

- `_load_omlx_settings()` — reads `~/.omlx/settings.json`, returns `{api_key, server_url}`
- `_detect_backend()` — tries omlx first (any HTTP response = up), then ollama (200 OK = up)
- `_resolve_model(backend, settings, model_arg)` — returns `model_arg` if given; for omlx queries `GET /v1/models` and returns `data[0].id`; for ollama returns `None`
- `_exec_agent(backend, settings, agent, model)` — `os.execvp`/`os.execvpe`s the agent; for omlx+claude sets `ANTHROPIC_*` env vars; for omlx+codex execs `codex -c 'model_provider="omlx"' -c 'model="<model>"'` with `OMLX_API_KEY` — bypasses `omlx launch codex` which permanently corrupts `~/.codex/config.toml`
- `codex_models_cache.json` — copy of `~/.codex/models_cache.json` with Qwen model entries added; symlink `~/.codex/models_cache.json` → this file to suppress "Model metadata not found" warnings

## Coding guide

See [docs/coding_guide.md](docs/coding_guide.md).
