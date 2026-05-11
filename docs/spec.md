# ollama-session — Specification

## Overview

`ollama-session` is a Python CLI tool that starts the ollama server, loads a chosen model into memory via the ollama HTTP API, and provides a clean persistent terminal session for interacting with local LLMs. It manages the full lifecycle: server startup, model loading, the interactive session, model unloading, and server shutdown.

## Usage

```
python ollama-session.py --model <model-name>
python ollama-session.py --dry-run [--model <model-name>]
```

`--model` is required in normal mode. `--dry-run` starts the server and shows the UI without loading a model — useful for UI development and testing widgets.

Example:

```
python ollama-session.py --model llama3
python ollama-session.py --dry-run
```

## Components

| File | Responsibility |
|---|---|
| `ollama-session.py` | Entry point. CLI argument parsing, `OllamaSession` class, session UI orchestration, input loop. See [ollama_session.md](ollama_session.md). |
| `widgets/header.py` | `SessionHeader` class — renders and continuously updates the stats line pinned to row 1 of the terminal. See [session_header.md](session_header.md). |
| `widgets/meter.py` | `ValueMeter` class — progress bar + sparkline widget pinned to a fixed terminal row. See [meter.md](meter.md). |
| `widgets/horizontal_text.py` | `HorizontalText` class — renders a single line of text pinned to a fixed terminal row. See [horizontal_text.md](horizontal_text.md). |
| `widgets/border.py` | `Border` class — draws a rectangular frame at a fixed terminal position; always rendered last (overlay). See [border.md](border.md). |

## Ollama Server

ollama exposes a REST API on `http://localhost:11434` (default port).
The script communicates with ollama exclusively through this API using Python's built-in `urllib` — no third-party HTTP libraries.

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

## Startup Sequence

1. Parse CLI arguments. Exit with a clear error if `--model` is missing and `--dry-run` is not set.
2. Check if the ollama server is already running by sending GET `/` with a short timeout.
   - If not running: start `ollama serve` as a background subprocess and poll GET `/` until it responds (up to a timeout).
   - If already running: log the issue and exit with code 1.
3. Retrieve the ollama version via GET `/api/version`.
4. Unless `--dry-run`: load the model into memory via POST `/api/generate` with `keep_alive: -1`. Stream and display the response so the user can see loading progress.
5. Clear the terminal and build the widget UI.
6. Enter the command input loop.

Steps 2–3 are encapsulated in `OllamaSession.start()`. Step 4 is called by `init_ollama()` so it can be skipped in dry-run mode. The startup log is visible before the terminal is cleared, so any errors or warnings from ollama appear naturally.

## Stats Header

See [session_header.md](session_header.md) for full documentation of the `SessionHeader` class.

The header is displayed on the first line of the terminal and updated in-place every second:

```
Ollama-Session | ollama 0.6.1 | Loaded: llama3 | Running: 0:02:34
```

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

Below the meter border, the UI displays a static section showing how to connect an AI agent to the running model:

```
─── How to run using an agent ───────────────────────────────────────────────────

  ollama launch claude --model <model-name>
  ollama launch codex --model <model-name>
  ollama launch opencode --model <model-name>
  ollama launch openclaw --model <model-name>
```

The model name is substituted at startup from the `--model` argument.

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

**Graceful shutdown sequence:**
1. Unload the model via POST `/api/generate` with `keep_alive: 0`.
2. If the script started `ollama serve` itself, terminate that subprocess. If ollama was already running when the script started, leave it running.
3. Restore the terminal to a clean state (cursor visible, no dangling ANSI codes).

## Out of Scope for This Iteration

- Sending user input to the model and displaying responses
- Any `/`-prefixed commands beyond graceful exit
- Session history or logging
- Multi-model or model-switching support
- Custom ollama server host or port
