# HorizontalText

**File:** `horizontal_text.py`  
**Class:** `HorizontalText`

## Purpose

Renders a single line of static text pinned to a fixed terminal row. Draws once on the first tick and skips all subsequent calls — text never changes at runtime so there is nothing to update.

```
Some Text
```

`HorizontalText` is a pure display object — it owns no threads.

## Constructor

```python
HorizontalText(text: str, row: int | None = None)
```

| Parameter | Description |
|---|---|
| `text` | The text string to render |
| `row` | Terminal row to render at; `None` = auto-assigned by `_build_sorted_list` |

## Methods

### `tick(now: float)`

Draws `text` to the assigned row on the first call, then becomes a no-op. The ANSI sequence used on the first call:

| ANSI code | Effect |
|---|---|
| `\033[s` | Save current cursor position |
| `\033[{row};1H` | Move cursor to the assigned row, column 1 |
| `\033[2K` | Clear the entire line |
| _(text)_ | Write the text |
| `\033[u` | Restore saved cursor position |

## Threading

`HorizontalText` contains no threads and no locks. All update calls are driven by the single update thread in `ollama-session.py` (`_run_update_loop`), which passes a shared `now` timestamp to every updatable object on a one-second interval.
