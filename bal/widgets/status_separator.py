import sys

from .meter import _BAR_FULL, _BAR_EMPTY


class SessionStatus:
    BOOTING = "booting"
    LOADING = "loading"
    LIVE = "live"

    def __init__(self):
        self.state = self.BOOTING
        self.model_name = ""
        self.model_size_gb = 0.0
        self.baseline_ram_gb = 0.0
        self.ram_getter = None

    def start_loading(self, model_name, model_size_gb, baseline_ram_gb, ram_getter):
        self.model_name = model_name
        self.model_size_gb = model_size_gb
        self.baseline_ram_gb = baseline_ram_gb
        self.ram_getter = ram_getter
        self.state = self.LOADING

    def set_live(self):
        self.state = self.LIVE


class SessionStatusSeparator:
    """Re-renders a horizontal-rule status line that reflects SessionStatus."""

    BAR_WIDTH = 13

    def __init__(self, status, width=83, row=None):
        self._status = status
        self._width = width
        self._row = row
        self._accumulated_seconds = 0.0

    def tick(self, delta_ms: float) -> None:
        if self._status.state == SessionStatus.LOADING:
            self._accumulated_seconds += delta_ms / 1000.0
        line = self._format(self._accumulated_seconds)
        sys.stdout.write(f"\033[s\033[{self._row};1H\033[2K{line}\033[u")

    def _format(self, elapsed):
        if self._status.state == SessionStatus.LIVE:
            return self._pad("─── Live ")
        if self._status.state == SessionStatus.LOADING:
            return self._loading_line(elapsed)
        return self._pad("─── Booting ")

    def _loading_line(self, elapsed):
        elapsed_int = int(elapsed)
        size_gb = self._status.model_size_gb
        if size_gb <= 0:
            return self._pad(f"─── Loading {self._status.model_name} ({elapsed_int}s) ")
        pct = self._progress_pct(size_gb)
        filled = round(pct * self.BAR_WIDTH / 100)
        bar = _BAR_FULL * filled + _BAR_EMPTY * (self.BAR_WIDTH - filled)
        return self._pad(f"─── Loading {self._status.model_name} {pct}% [{bar}] ({elapsed_int}s) ")

    def _progress_pct(self, size_gb):
        try:
            delta = float(self._status.ram_getter()) - self._status.baseline_ram_gb
        except (TypeError, ValueError):
            return 0
        if delta <= 0:
            return 0
        return min(99, int(delta / size_gb * 100))

    def _pad(self, prefix):
        pad = max(0, self._width - len(prefix))
        return prefix + "─" * pad
