# ollama-session — Specification

## Overview

`ollama-session` is a Python CLI tool that starts the ollama server, loads a chosen model into memory via the ollama HTTP API, and provides a clean persistent terminal session for interacting with local LLMs. It manages the full lifecycle: server startup, model loading, the interactive session, model unloading, and server shutdown.

## Usage

```
python ollama-session.py --model <model-name>
```

`--model` is required. Example:

```
python ollama-session.py --model llama3
```

## Components

| File | Responsibility |
|---|---|
| `ollama-session.py` | Entry point. CLI argument parsing, `OllamaSession` class, session UI orchestration, input loop. See [ollama_session.md](ollama_session.md). |
| `header.py` | `SessionHeader` class — renders and continuously updates the stats line pinned to row 1 of the terminal. See [session_header.md](session_header.md). |
| `meter.py` | `ValueMeter` class — progress bar + sparkline widget pinned to a fixed terminal row. See [meter.md](meter.md). |
| `horizontal_text.py` | `HorizontalText` class — renders a single line of text pinned to a fixed terminal row. See [horizontal_text.md](horizontal_text.md). |

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

1. Parse `--model` argument; exit with a clear error message if it is missing.
2. Check if the ollama server is already running by sending GET `/` with a short timeout.
   - If not running: start `ollama serve` as a background subprocess and poll GET `/` until it responds (up to a timeout).
   - If already running: log the issue and exit the script with code 1.
3. Retrieve the ollama version via GET `/api/version`.
4. Load the model into memory via POST `/api/generate` with `keep_alive: -1`. Stream and display the response so the user can see loading progress.
5. Construct a `SessionHeader` with the `OllamaSession` instance.
6. Clear the terminal.
7. Call `SessionHeader.start()` to render row 1 and begin the live counter.
8. Enter the command input loop.

Steps 2–4 are encapsulated in `OllamaSession.start()`. The startup log is visible to the user before the terminal is cleared, so any errors or warnings from ollama appear naturally.

## Stats Header

See [session_header.md](session_header.md) for full documentation of the `SessionHeader` class.

The header is displayed on the first line of the terminal and updated in-place every second:

```
Ollama-Session | ollama 0.6.1 | Loaded: llama3 | Running: 0:02:34
```

## System Meters

Three `ValueMeter` widgets render below the header, each updated every second:

| Meter | Source | Unit |
|---|---|---|
| CPU | `psutil.cpu_percent()` — actual CPU utilization delta | % |
| GPU | `ioreg -c AGXAccelerator` `"Device Utilization %"` (macOS); `0` elsewhere | % |
| RAM | `vm_stat` anonymous + wired + compressor pages (macOS); `psutil` `total − available` elsewhere | GB |

The percentage value is color-coded: green [0–49%], yellow [50–89%], red [90–100%].

See [meter.md](meter.md) for full `ValueMeter` documentation.

## Agent Hints

Below the meters, the UI displays a static section showing how to connect an AI agent to the running model:

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

Command handler architecture must allow new `/`-prefixed commands (e.g. `/help`, `/reset`, `/history`) to be registered without restructuring the input loop.

## Termination

| Trigger | Behavior |
|---|---|
| `Ctrl-C` (SIGINT) | Run graceful shutdown (see below), restore the terminal, and exit. |
| Script killed / terminal closed | `atexit` registration ensures graceful shutdown runs on normal and `sys.exit()` paths. |

**Graceful shutdown sequence:**
1. Call `SessionHeader.stop()` to end the live updater thread.
2. Unload the model via POST `/api/generate` with `keep_alive: 0`.
3. If the script started `ollama serve` itself, terminate that subprocess. If ollama was already running when the script started, leave it running.
4. Restore the terminal to a clean state (cursor visible, no dangling ANSI codes).

## Out of Scope for This Iteration

- Sending user input to the model and displaying responses
- Any `/`-prefixed commands beyond graceful exit
- Session history or logging
- Multi-model or model-switching support
- Custom ollama server host or port
