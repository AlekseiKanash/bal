#!/usr/bin/env python3

import argparse
import atexit
import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import psutil

from widgets.header import SessionHeader
from widgets.meter import ValueMeter
from widgets.horizontal_text import HorizontalText
from widgets.border import Border


OLLAMA_BASE_URL = "http://localhost:11434"
OMLX_BASE_URL = "http://localhost:8000"

HEADER_UPDATE_INTERVAL_SECONDS = 1
INPUT_PROMPT = "> "


def parse_args():
    parser = argparse.ArgumentParser(
        description="Start a persistent local LLM session via ollama or omlx."
    )
    parser.add_argument("--model", default=None, help="Model name to load")
    parser.add_argument("--dry-run", action="store_true", help="Start UI without loading a model or server")
    parser.add_argument("--backend", default="ollama", choices=["ollama", "omlx"],
                        help="LLM backend to use (default: ollama)")
    parser.add_argument("--model-dir", default=None,
                        help="Model directory for omlx backend")
    args = parser.parse_args()
    if not args.dry_run and args.model is None:
        parser.error("--model is required unless --dry-run is specified")
    return args


def http_get(path, timeout=5, base_url=OLLAMA_BASE_URL):
    with urllib.request.urlopen(base_url + path, timeout=timeout) as resp:
        return resp.read().decode()


def http_post(path, payload, timeout=30, base_url=OLLAMA_BASE_URL):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


class OllamaSession:
    backend_name = "ollama"

    def __init__(self, model_name):
        self._model_name = model_name
        self._version = None
        self._serve_process = None

    def start(self):
        self._serve_process = self._ensure_server_running()
        self._version = self._fetch_version()
        print(f"  ollama {self._version}", flush=True)

    def cleanup(self):
        print("\nUnloading model...", flush=True)
        self._unload_model()
        if self._serve_process is not None and self._serve_process.poll() is None:
            print("Stopping ollama server...", flush=True)
            self._serve_process.terminate()
            try:
                self._serve_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._serve_process.kill()

    def _is_server_running(self):
        try:
            http_get("/", timeout=2)
            return True
        except Exception:
            return False

    def _wait_for_server_ready(self):
        OLLAMA_SERVER_START_TIMEOUT_SECONDS = 30
        OLLAMA_HEALTH_POLL_INTERVAL_SECONDS = 0.5

        deadline = time.time() + OLLAMA_SERVER_START_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self._is_server_running():
                return True
            time.sleep(OLLAMA_HEALTH_POLL_INTERVAL_SECONDS)
        return False

    def _start_server(self):
        return subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _ensure_server_running(self):
        print("Checking ollama server...", flush=True)
        if self._is_server_running():
            print("  Already running. Exiting.", flush=True)
            sys.exit(1)
        print("  Starting ollama serve...", flush=True)
        process = self._start_server()
        if not self._wait_for_server_ready():
            print("Error: ollama server did not start in time.", file=sys.stderr)
            sys.exit(1)
        print("  Server ready.", flush=True)
        return process

    def _fetch_version(self):
        try:
            body = http_get("/api/version")
            return json.loads(body).get("version", "unknown")
        except Exception:
            return "unknown"

    def _preload_model(self):
        MODEL_LOAD_TIMEOUT_SECONDS = 120

        try:
            with http_post(
                "/api/generate",
                {"model": self._model_name, "keep_alive": -1},
                timeout=MODEL_LOAD_TIMEOUT_SECONDS,
            ) as resp:
                for raw_line in resp:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    obj = json.loads(stripped)
                    if obj.get("error"):
                        print(f"  Error: {obj['error']}", file=sys.stderr, flush=True)
                        sys.exit(1)
                    if obj.get("done_reason"):
                        print(f"  {obj['done_reason']}", flush=True)
        except urllib.error.HTTPError as exc:
            print(f"  HTTP {exc.code}: {exc.read().decode()}", file=sys.stderr, flush=True)
            sys.exit(1)

    def _unload_model(self):
        try:
            with http_post("/api/generate", {"model": self._model_name, "keep_alive": 0}, timeout=10) as resp:
                resp.read()
        except Exception:
            pass


class OmlxSession:
    backend_name = "omlx"

    def __init__(self, model_name, model_dir=None):
        self._model_name = model_name
        self._model_dir = model_dir or os.path.expanduser("~/.omlx/models")
        self._version = None
        self._serve_process = None

    def start(self):
        self._serve_process = self._ensure_server_running()
        self._version = self._fetch_version()
        print(f"  omlx {self._version}", flush=True)

    def cleanup(self):
        if self._serve_process is not None and self._serve_process.poll() is None:
            print("\nStopping omlx server...", flush=True)
            self._serve_process.terminate()
            try:
                self._serve_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._serve_process.kill()

    def _is_server_running(self):
        try:
            http_get("/v1/models", timeout=2, base_url=OMLX_BASE_URL)
            return True
        except Exception:
            return False

    def _wait_for_server_ready(self):
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._is_server_running():
                return True
            time.sleep(0.5)
        return False

    def _start_server(self):
        return subprocess.Popen(
            ["omlx", "serve", "--model-dir", self._model_dir],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _ensure_server_running(self):
        print("Checking omlx server...", flush=True)
        if self._is_server_running():
            print("  Already running. Exiting.", flush=True)
            sys.exit(1)
        print("  Starting omlx serve...", flush=True)
        process = self._start_server()
        if not self._wait_for_server_ready():
            print("Error: omlx server did not start in time.", file=sys.stderr)
            sys.exit(1)
        print("  Server ready.", flush=True)
        return process

    def _fetch_version(self):
        try:
            result = subprocess.run(
                ["omlx", "--version"], capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip().split()[-1]
        except Exception:
            return "unknown"

    def _preload_model(self):
        pass

    def _unload_model(self):
        pass


def init_session(backend, model_name, model_dir=None, dry_run=False):
    if backend == "omlx":
        session = OmlxSession(model_name or "(none)", model_dir=model_dir)
    else:
        session = OllamaSession(model_name or "(none)")
    session.start()
    if not dry_run:
        print(f"Loading {session._model_name}...", flush=True)
        session._preload_model()
    atexit.register(session.cleanup)
    return session


def restore_terminal():
    sys.stdout.write("\033[?25h")  # ensure cursor is visible on exit
    sys.stdout.flush()


def _run_update_loop(updatables: list, stop_event: threading.Event):
    while not stop_event.is_set():
        now = time.time()
        for obj in updatables:
            obj.tick(now)
        sys.stdout.flush()
        stop_event.wait(HEADER_UPDATE_INTERVAL_SECONDS)


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


def cpu_getter(precision=0):
    return f"{psutil.cpu_percent(interval=None):.{precision}f}"


def gpu_getter(precision=0):
    if platform.system() == "Darwin":
        return f"{_gpu_load_macos():.{precision}f}"
    return "0"


def ram_getter(precision=1):
    if platform.system() == "Darwin":
        used_gb = _ram_used_gb_macos()
    else:
        mem = psutil.virtual_memory()
        used_gb = (mem.total - mem.available) / (1024**3)
    return f"{used_gb:.{precision}f}"


def _build_ui(session) -> list:
    """Build and initialize all updatable UI objects. Must be called after terminal is cleared."""

    lines = []
    power = _PowermetricsSampler()

    # Seed the measurement so the first real call returns a delta, not 0.0
    psutil.cpu_percent(interval=None)

    lines += [
        SessionHeader(session, row=1),
        Border(row=2, height=5, width=83),
    ]

    lines += [
        ValueMeter("CPU", cpu_getter, 100.0, unit="%", secondary_getter=power.cpu_w, secondary_unit="W"),
        ValueMeter("GPU", gpu_getter, 100.0, unit="%", secondary_getter=power.gpu_w, secondary_unit="W"),
        ValueMeter("RAM", ram_getter, psutil.virtual_memory().total / (1024**3), unit="GB"),
    ]

    model_name = session._model_name
    agents = [
        "claude",
        "codex",
        "opencode",
        "openclaw",
    ]
    lines += [
        HorizontalText(""),
        HorizontalText("─── How to run using an agent ───────────────────────────────────────────────────"),
        HorizontalText(""),
    ]
    cmd_prefix = session.backend_name
    lines += [
        HorizontalText(f"  {cmd_prefix} launch {agent} --model {model_name}")
        for agent in agents
    ]

    return _build_sorted_list(lines)


def _build_sorted_list(updatables) -> list:
    """Assign rows to auto widgets and sort them by row."""
    fixed = [m for m in updatables if m._row is not None]
    auto = [m for m in updatables if m._row is None]

    all_rows = [m._row for m in fixed]
    lo = min(all_rows) if all_rows else 1
    hi = max(all_rows) if all_rows else 1

    available = sorted(set(range(lo, hi + 1)) - set(all_rows))
    next_auto_row = hi + 1
    for i, meter in enumerate(auto):
        if i < len(available):
            meter._row = available[i]
        else:
            meter._row = next_auto_row
            next_auto_row += 1

    all_widgets = fixed + auto
    overlays = [m for m in all_widgets if isinstance(m, Border)]
    regular  = [m for m in all_widgets if not isinstance(m, Border)]
    return sorted(regular, key=lambda m: m._row) + overlays


def start_session_ui(session):
    os.system("clear")
    updatables = _build_ui(session)
    sys.stdout.write("\n" * len(updatables))
    sys.stdout.flush()
    stop_event = threading.Event()
    threading.Thread(target=_run_update_loop, args=(updatables, stop_event), daemon=True).start()
    return stop_event


def run_input_loop(stop_event: threading.Event):
    def handle_sigint(signum, frame):
        stop_event.set()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    try:
        while True:
            try:
                user_input = input(INPUT_PROMPT)
            except EOFError:
                break
            if user_input.startswith("/"):
                # Command dispatch — no commands defined yet
                pass
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()


def main():
    atexit.register(restore_terminal)
    args = parse_args()
    session = init_session(args.backend, args.model, model_dir=args.model_dir, dry_run=args.dry_run)
    stop_event = start_session_ui(session)
    run_input_loop(stop_event)


if __name__ == "__main__":
    main()
