import sys
import time


def _format_elapsed_time(total_seconds):
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


class SessionHeader:
    """Renders the stats line pinned to a fixed terminal row."""

    def __init__(self, ollama, row: int | None = None):
        self._ollama = ollama
        self._row = row
        self._start_time = time.time()

    def start(self):
        """Record start time and do the initial render. Call after terminal is cleared."""

    def tick(self, now: float) -> None:
        """Re-render the header line in-place using ANSI save/restore cursor."""
        elapsed = now - self._start_time
        time_str = _format_elapsed_time(elapsed)
        line = (
            f"BAL | {self._ollama.backend_name} {self._ollama._version}"
            f" | Loaded: {self._ollama._model_name}"
            f" | Running: {time_str}"
        )
        sys.stdout.write(f"\033[s\033[{self._row};1H\033[2K{line}\033[u")
