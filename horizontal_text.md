# HorizontalText

**File:** `horizontal_text.py`  
**Class:** `HorizontalText`

## Purpose

Renders a single line of text pinned to a fixed terminal row.

```
Some Text
```

`HorizontalText` is a pure display object — it owns no threads. The caller drives updates by calling `tick(now)` at the desired interval.

## Constructor

```python
HorizontalText(text: str, row: int | None = None)
```

| Parameter | Description |
|---|---|
| `text` | The text string to render on each tick |
| `row` | Terminal row to render at; `None` = auto-assigned by `_build_sorted_list` |

## Lifecycle

```
HorizontalText("Some Text")           ← construct early, no side effects
        │
    header.tick(now)                  ← renders text at assigned row on each tick
```

### `tick(now: float)`

Writes `text` to the assigned row without disturbing the cursor position the user sees. The ANSI sequence used:

| ANSI code | Effect |
|---|---|
| `\033[s` | Save current cursor position |
| `\033[{row};1H` | Move cursor to the assigned row, column 1 |
| `\033[2K` | Clear the entire line |
| _(text)_ | Write the text |
| `\033[u` | Restore saved cursor position |

## Threading

`HorizontalText` contains no threads and no locks. All update calls are driven by the single update thread in `ollama-session.py` (`_run_update_loop`), which passes a shared `now` timestamp to every updatable object on a one-second interval.
