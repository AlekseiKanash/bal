import sys


def _format_elapsed_time(total_seconds):
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


class SessionHeader:
    """Renders the stats line pinned to a fixed terminal row."""

    def __init__(self, backend, row: int | None = None):
        self._backend = backend
        self._row = row
        self._accumulated_seconds = 0.0

    def tick(self, delta_ms: float) -> None:
        """Re-render the header line in-place using ANSI save/restore cursor."""
        self._accumulated_seconds += delta_ms / 1000.0
        time_str = _format_elapsed_time(self._accumulated_seconds)
        line = (
            f"BAL | {self._backend.backend_name} {self._backend.version}"
            f" | Loaded: {self._backend.model_name}"
            f" | Running: {time_str}"
        )
        sys.stdout.write(f"\033[s\033[{self._row};1H\033[2K{line}\033[u")
