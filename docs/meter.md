# ValueMeter

**File:** `widgets/meter.py`  
**Class:** `ValueMeter`

## Purpose

Reusable numeric metric widget: progress bar + sparkline history, driven by a pluggable getter. Renders at a fixed terminal row.

```
  CPU  ▇▇▇▇▇▇▇▇▇▇▇▇░░░░░░░░   62%  ▁▂▃▄▅▆▇▇··  8.3W
```

The percentage is color-coded: green [0–49%], yellow [50–89%], red [90–100%]. The trailing value after the sparkline is provided by `secondary_getter` when set, otherwise falls back to the primary current value + `unit`.

`ValueMeter` is a pure display object — it owns no threads. The caller drives updates by calling `tick(now)` at the desired interval.

## Constructor

```python
ValueMeter(
    label: str,
    getter,
    max_value: float,
    row: int | None = None,
    unit: str = "",
    bar_width: int = 20,
    history_size: int = 10,
    update_interval: float = 1.0,
    label_width: int = 4,
    formatter=None,
    secondary_getter=None,
    secondary_unit: str = "",
)
```

| Parameter | Description |
|---|---|
| `label` | Display name, left-padded to `label_width` |
| `getter` | Zero-argument callable returning the current numeric value (drives bar and sparkline) |
| `max_value` | Upper bound for bar and sparkline scaling |
| `row` | Terminal row to render at; `None` = auto-assigned by `_build_sorted_list` |
| `unit` | String appended after the primary value when no `secondary_getter` is set |
| `bar_width` | Number of block characters in the progress bar |
| `history_size` | Sparkline ring-buffer length |
| `update_interval` | Seconds between getter calls |
| `label_width` | Column width reserved for the label |
| `formatter` | Optional `(float) -> str`; defaults to `str()` |
| `secondary_getter` | Optional zero-argument callable whose return value replaces the primary suffix after the sparkline |
| `secondary_unit` | String appended after the `secondary_getter` value (e.g. `"W"`) |

## Methods

### `tick(now: float)`

Fetches a new value if `update_interval` has elapsed, appends to ring buffer, then calls `draw()`.

### `render() -> str`

Returns the formatted meter string without writing to the terminal.

### `draw(col: int = 1)`

Writes `render()` at the assigned row, followed by `\033[K` (erase to end of line) to clear any trailing characters from a previous longer render. Does **not** call `sys.stdout.flush()` — the update loop flushes once after all widgets have drawn.

### `print()`

Writes `render()` at the current cursor position. For inline or debug use.

## Internals

Ring buffer `_history[history_size]` written round-robin via `_head`. `_build_bar` fills block chars proportional to `pct`. `_build_spark` reads oldest-to-newest; unsampled slots render as `·`. `_pct_color` maps the percentage to an ANSI color code.
