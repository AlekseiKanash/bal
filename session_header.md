# SessionHeader

**File:** `header.py`  
**Class:** `SessionHeader`

## Purpose

Renders and updates the stats line pinned to the first row of the terminal. The line shows the ollama version, the loaded model name, and a live elapsed-time counter.

```
Ollama-Session | ollama 0.6.1 | Loaded: llama3 | Running: 0:02:34
```

`SessionHeader` is a pure display object — it owns no threads. The caller is responsible for driving updates by calling `update()` at the desired interval.

## Constructor

```python
SessionHeader(ollama: OllamaSession)
```

Accepts an `OllamaSession` instance and reads `_version` and `_model_name` from it at render time. Does not touch the terminal or start any threads. Safe to construct before the terminal is cleared.

## Lifecycle

```
SessionHeader(ollama)            ← construct early, no side effects
        │
        │  (clear terminal here)
        │
    header.start()               ← records start time, renders row 1 once
        │
        │  caller drives the update loop and calls header.update() on each tick
        │
    (caller stops the loop)
```

### `start()`

Records the session start time and calls `update()` once for the initial render. Must be called after the terminal has been cleared so row 1 is available.

### `update()`

Writes the current header string to row 1 without disturbing the cursor position the user sees. The sequence used:

| ANSI code | Effect |
|---|---|
| `\033[s` | Save current cursor position |
| `\033[1;1H` | Move cursor to row 1, column 1 |
| `\033[2K` | Clear the entire line |
| _(header text)_ | Write the updated stats line |
| `\033[u` | Restore saved cursor position |

## Threading

`SessionHeader` contains no threads and no locks. All update calls are driven by the single update thread in `ollama-session.py` (`_run_update_loop`), which holds the `stop_event` and calls `header.update()` on a one-second interval.
