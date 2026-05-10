# SessionHeader

**File:** `header.py`  
**Class:** `SessionHeader`

## Purpose

Renders and updates the stats line pinned to a fixed terminal row. The line shows the ollama version, the loaded model name, and a live elapsed-time counter.

```
Ollama-Session | ollama 0.6.1 | Loaded: llama3 | Running: 0:02:34
```

`SessionHeader` is a pure display object — it owns no threads. The caller is responsible for driving updates by calling `tick(now)` at the desired interval.

## Constructor

```python
SessionHeader(ollama: OllamaSession, row: int | None = None)
```

Accepts an `OllamaSession` instance and reads `_version` and `_model_name` from it at render time. `row` is the terminal row to pin to; `None` means it will be assigned by `_build_sorted_list`. Does not touch the terminal or start any threads. Safe to construct before the terminal is cleared.

## Lifecycle

```
SessionHeader(ollama, row=1)     ← construct early, no side effects
        │
        │  (clear terminal here)
        │
    header.start()               ← records start time, renders assigned row once
        │
        │  caller drives the update loop and calls header.tick(now) on each tick
        │
    (caller stops the loop)
```

### `start()`

Records the session start time and calls `tick(start_time)` once for the initial render. Must be called after the terminal has been cleared so the target row is available.

### `tick(now: float)`

Writes the current header string to the assigned row without disturbing the cursor position the user sees. `now` is a Unix timestamp passed in by the update loop. The sequence used:

| ANSI code | Effect |
|---|---|
| `\033[s` | Save current cursor position |
| `\033[{row};1H` | Move cursor to the assigned row, column 1 |
| `\033[2K` | Clear the entire line |
| _(header text)_ | Write the updated stats line |
| `\033[u` | Restore saved cursor position |

## Threading

`SessionHeader` contains no threads and no locks. All update calls are driven by the single update thread in `ollama-session.py` (`_run_update_loop`), which passes a shared `now` timestamp to every updatable object on a one-second interval.
