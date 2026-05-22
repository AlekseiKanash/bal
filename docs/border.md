# Border

**File:** `widgets/border.py`  
**Class:** `Border`

## Purpose

Draws a rectangular frame at a fixed terminal position using box-drawing characters. Acts as an overlay: `_build_sorted_list` always renders `Border` instances last so their frame chars appear on top of any content drawn inside the box.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  CPU  ▇▇▇░░░░░░░░░░░░░░░░░░   42%  ▄▂▅▃·····  8.3W                            │
│  GPU  ░░░░░░░░░░░░░░░░░░░░░░    0%  ··········  0.0W                            │
│  RAM  ▇▇▇▇▇▇▇░░░░░░░░░░░░░░   58%  ▄▅▆▅▄▅▆▇·  23.4GB                          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Box-drawing characters used: `┌ ─ ┐ │ └ ┘`

## Constructor

```python
Border(row: int, height: int, width: int, col: int = 1)
```

| Parameter | Description |
|---|---|
| `row` | Terminal row of the top edge |
| `height` | Total height including top and bottom edges |
| `width` | Total width including left and right edges |
| `col` | Terminal column of the left edge (default 1) |

`row` must always be set explicitly — auto-assignment (`row=None`) is not supported because the widget spans multiple rows.

## Methods

### `tick(delta_ms: float)`

Calls `draw()` unconditionally every tick. The frame is static so redrawing is cheap; correctness requires it to run after all content widgets so the border chars land on top.

### `draw()`

Renders the full frame using ANSI cursor positioning (no `\033[2K` line erase):
- Top row: `┌` + `─` × (width − 2) + `┐`
- Middle rows: `│` at left column, `│` at right column only — does not touch the interior
- Bottom row: `└` + `─` × (width − 2) + `┘`

Wrapped in `\033[s` / `\033[u` (save/restore cursor) so the active cursor position is undisturbed. Does **not** call `sys.stdout.flush()` — the update loop flushes once after all widgets have drawn.

## Z-order

`_build_sorted_list` partitions the widget list into regular widgets (sorted by `_row`) and overlays (`Border` instances), which are appended at the end. This guarantees the border frame is written last in every tick, after content widgets have drawn — preventing content from overwriting the frame chars.

## Usage example

```python
Border(row=2, height=5, width=83)
```

Content widgets with `row` values 3–5 render inside the box; the border's bottom edge lands at row 6.
