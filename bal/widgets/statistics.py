import platform
import re
import subprocess
import threading

import psutil

from .meter import ValueMeter


def _ram_used_gb_macos():
    """Match Activity Monitor: anonymous pages + wired + compressor pages."""
    result = subprocess.run(["vm_stat"], capture_output=True, text=True)
    page_size = 4096
    stats = {}
    for line in result.stdout.splitlines():
        if "page size of" in line:
            page_size = int(line.split("page size of")[1].split()[0])
        elif ":" in line:
            key, _, val = line.partition(":")
            try:
                stats[key.strip()] = int(val.strip().rstrip("."))
            except ValueError:
                pass
    anonymous = stats.get("Anonymous pages", 0)
    wired = stats.get("Pages wired down", 0)
    compressed = stats.get("Pages occupied by compressor", 0)
    return (anonymous + wired + compressed) * page_size / (1024**3)


def _gpu_load_macos():
    result = subprocess.run(
        ["ioreg", "-r", "-d", "1", "-w", "0", "-c", "AGXAccelerator"],
        capture_output=True, text=True,
    )
    match = re.search(r'"Device Utilization %"=(\d+)', result.stdout)
    return float(match.group(1)) if match else 0.0


def ram_getter(precision=1):
    """Used RAM in GB as a formatted string. Used by both StatisticsWidget and the loading-progress estimator."""
    if platform.system() == "Darwin":
        used_gb = _ram_used_gb_macos()
    else:
        mem = psutil.virtual_memory()
        used_gb = (mem.total - mem.available) / (1024**3)
    return f"{used_gb:.{precision}f}"


class _PowermetricsSampler:
    def __init__(self):
        self._cpu_w = 0.0
        self._gpu_w = 0.0
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                result = subprocess.run(
                    ["sudo", "powermetrics", "--samplers", "cpu_power", "-n", "1", "-i", "1000"],
                    capture_output=True, text=True, timeout=5,
                )
                cpu_w = gpu_w = 0.0
                for line in result.stdout.splitlines():
                    if line.startswith("CPU Power:"):
                        cpu_w = float(line.split(":")[1].strip().split()[0]) / 1000
                    elif line.startswith("GPU Power:"):
                        gpu_w = float(line.split(":")[1].strip().split()[0]) / 1000
                with self._lock:
                    self._cpu_w = cpu_w
                    self._gpu_w = gpu_w
            except Exception:
                pass

    def cpu_w(self) -> str:
        with self._lock:
            return f"{self._cpu_w:.1f}"

    def gpu_w(self) -> str:
        with self._lock:
            return f"{self._gpu_w:.1f}"


class StatisticsWidget:
    height = 3  # consecutive terminal rows occupied

    def __init__(self):
        self._row = None
        power = _PowermetricsSampler()
        # Seed so the first real call returns a delta, not 0.0
        psutil.cpu_percent(interval=None)
        ram_total_gb = psutil.virtual_memory().total / (1024**3)
        self._meters = [
            ValueMeter("CPU", self._cpu_getter, 100.0, unit="%",
                       secondary_getter=power.cpu_w, secondary_unit="W"),
            ValueMeter("GPU", self._gpu_getter, 100.0, unit="%",
                       secondary_getter=power.gpu_w, secondary_unit="W"),
            ValueMeter("RAM", ram_getter, ram_total_gb, unit="GB"),
        ]

    @property
    def _row(self):
        return self.__row

    @_row.setter
    def _row(self, value):
        self.__row = value
        if value is not None:
            for i, meter in enumerate(self._meters):
                meter._row = value + i

    @staticmethod
    def _cpu_getter(precision=0):
        return f"{psutil.cpu_percent(interval=None):.{precision}f}"

    @staticmethod
    def _gpu_getter(precision=0):
        if platform.system() == "Darwin":
            return f"{_gpu_load_macos():.{precision}f}"
        return "0"

    def tick(self, delta_ms: float) -> None:
        for meter in self._meters:
            meter.tick(delta_ms)
