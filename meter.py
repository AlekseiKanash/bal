import sys


_BAR_FULL = "█"
_BAR_EMPTY = "░"
_SPARK_CHARS = "▁▂▃▄▅▆▇█"
_SPARK_EMPTY = "·"


class ValueMeter:
    """Reusable numeric metric widget: progress bar + sparkline history, driven by a pluggable getter."""

    def __init__(
        self,
        label: str,
        getter,
        max_value: float,
        row: int,
        unit: str = "",
        bar_width: int = 20,
        history_size: int = 10,
        update_interval: float = 1.0,
        label_width: int = 6,
        formatter=None,
    ):
        self._label = label
        self._getter = getter
        self._max_value = max_value
        self._row = row
        self._unit = unit
        self._bar_width = bar_width
        self._history_size = history_size
        self._update_interval = update_interval
        self._label_width = label_width
        self._formatter = formatter
        self._history = [None] * history_size  # ring buffer; None = not yet sampled
        self._head = 0                          # next write index
        self._current = 0.0
        self._last_update = 0.0

    def tick(self, now: float) -> None:
        """Fetch a new value if the interval has elapsed, then render at the assigned row."""
        if now - self._last_update >= self._update_interval:
            self._current = float(self._getter())
            self._history[self._head] = self._current
            self._head = (self._head + 1) % self._history_size
            self._last_update = now
        self.draw()

    def render(self) -> str:
        """Return the formatted meter string."""
        pct = max(0.0, min(1.0, self._current / self._max_value)) if self._max_value else 0.0
        bar = self._build_bar(pct)
        spark = self._build_spark()
        current_str = self._formatter(self._current) if self._formatter else str(self._current)
        return f"{self._label:<{self._label_width}}  {bar}  {int(pct * 100):3d}%  {spark}  {current_str}{self._unit}"

    def draw(self, col: int = 1) -> None:
        """Render at the assigned row without disturbing the active cursor."""
        sys.stdout.write(f"\033[s\033[{self._row};{col}H\033[2K{self.render()}\033[u")
        sys.stdout.flush()

    def print(self) -> None:
        """Render at the current cursor position (for inline or debug use)."""
        sys.stdout.write(self.render() + "\n")
        sys.stdout.flush()

    def _build_bar(self, pct: float) -> str:
        filled = round(pct * self._bar_width)
        return _BAR_FULL * filled + _BAR_EMPTY * (self._bar_width - filled)

    def _build_spark(self) -> str:
        ordered = self._history[self._head:] + self._history[:self._head]  # oldest → newest
        chars = []
        for val in ordered:
            if val is None:
                chars.append(_SPARK_EMPTY)
            else:
                frac = max(0.0, min(1.0, val / self._max_value)) if self._max_value else 0.0
                index = min(int(frac * len(_SPARK_CHARS)), len(_SPARK_CHARS) - 1)
                chars.append(_SPARK_CHARS[index])
        return "".join(chars)
