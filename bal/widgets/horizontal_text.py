import sys


class HorizontalText:
    """Renders a single line of text pinned to a fixed terminal row."""

    def __init__(self, text: str, row: int | None = None):
        self._text = text
        self._row = row
        self._drawn = False

    def tick(self, delta_ms: float) -> None:
        """Re-render the text line in-place at the assigned row."""
        if not self._drawn:
            sys.stdout.write(f"\033[s\033[{self._row};1H\033[2K{self._text}\033[u")
            self._drawn = True
