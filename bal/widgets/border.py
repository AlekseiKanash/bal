import sys

_TL = "┌"; _TR = "┐"; _BL = "└"; _BR = "┘"
_H  = "─"; _V  = "│"

class Border:
    def __init__(self, row: int, height: int, width: int, col: int = 1):
        self._row      = row
        self._height   = height
        self._width    = width
        self._col      = col

    def tick(self, delta_ms: float) -> None:
        self.draw()

    def draw(self) -> None:
        r0, r1 = self._row, self._row + self._height - 1
        c0, c1 = self._col, self._col + self._width - 1
        inner  = _H * (self._width - 2)
        buf    = ["\033[s"]
        buf.append(f"\033[{r0};{c0}H{_TL}{inner}{_TR}")
        for r in range(r0 + 1, r1):
            buf.append(f"\033[{r};{c0}H{_V}\033[{r};{c1}H{_V}")
        buf.append(f"\033[{r1};{c0}H{_BL}{inner}{_BR}")
        buf.append("\033[u")
        sys.stdout.write("".join(buf))
