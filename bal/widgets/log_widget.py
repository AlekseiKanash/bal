import shutil
import sys
import threading
from collections import deque


class LogWidget:
    """Reverse-chronological log: new messages at the top, old at the bottom."""

    def __init__(self, log_top: int):
        self._log_top = log_top
        self._lines: deque[str] = deque()
        self._pending: deque[str] = deque()
        self._lock = threading.Lock()

    def append(self, message: str) -> None:
        """Thread-safe enqueue from the input loop. No I/O."""
        with self._lock:
            self._pending.append(message)

    def tick(self, delta_ms: float) -> None:
        """Dequeue pending messages, render the visible log area."""
        with self._lock:
            # Flush pending into the main buffer (newest at index 0)
            while self._pending:
                self._lines.appendleft(self._pending.popleft())

            count = len(self._lines)
            if count == 0:
                return

            # Compute visible height
            term_rows = shutil.get_terminal_size().lines
            avail = term_rows - self._log_top
            if avail <= 0:
                return

            # Show most recent lines; oldest get pushed off bottom
            offset = count - avail
            if offset < 0:
                offset = 0
            lines = list(self._lines)[offset:]

        # --- I/O happens outside the lock ---
        sys.stdout.write(f"\033[s\033[{self._log_top};1H")

        for i, line in enumerate(lines):
            row = self._log_top + i
            sys.stdout.write(f"\033[{row};1H\033[2K{line}\n")

        # Clear leftover lines when buffer shrinks
        leftover = avail - len(lines)
        for i in range(leftover):
            row = self._log_top + len(lines) + i
            sys.stdout.write(f"\033[{row};1H\033[2K")

        sys.stdout.write("\033[u")
