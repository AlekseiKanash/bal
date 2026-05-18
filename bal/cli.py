#!/usr/bin/env python3
# bal — LLM Backend Launcher
# Manages ollama/omlx server lifecycle and proxies agent launch commands.

import argparse
import atexit
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time

import psutil
from importlib.metadata import version as _meta_version

from .backends import (
    create_backend,
    detect_running_backend,
    find_backend_model_matches,
    list_available_models,
    local_model_dirs,
    scan_local_models_by_backend,
)
from .widgets.header import SessionHeader
from .widgets.meter import ValueMeter
from .widgets.horizontal_text import HorizontalText
from .widgets.border import Border


try:
    from ._version import __version__ as _VERSION
except ImportError:
    _VERSION = None

if _VERSION:
    VERSION = _VERSION
else:
    try:
        VERSION = _meta_version("bal")
    except Exception:
        VERSION = "unknown"


HEADER_UPDATE_INTERVAL_SECONDS = 1
INPUT_PROMPT = "> "

AGENTS = {"claude", "codex", "opencode", "openclaw"}


def _set_raw_mode(fd):
    """Set fd (stdin) into raw mode for single-character input."""
    import termios
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        return None
    new = old[:]
    new[3] = new[3] & ~termios.ICANON & ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSADRAIN, new)
    return old


def _restore_mode(fd, old):
    """Restore terminal to previous state."""
    if old is not None:
        import termios
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _get_terminal_height():
    try:
        return int(os.environ.get("LINES", 24))
    except (ValueError, TypeError):
        return 24


def print_help():
    print("""\
usage:
  bal <agent> [model]          launch agent against running backend
  bal --select                 interactively pick a model and start server
  bal list                     show available models (no server needed)
  bal --model <name> [options] start server, load model, show live UI

agents:  claude  codex  opencode  openclaw

server options:
  --model <name>          model to load (required unless --dry-run or --select)
  --backend ollama|omlx   backend to use (default: ollama)
  --model-dir <path>      model directory (omlx only)
  --dry-run               start server and UI without loading a model\
""")


def parse_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--version", action="version", version=f"bal {VERSION}")
    parser.add_argument("--model", nargs="?", const=None, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backend", default="ollama", choices=["ollama", "omlx"])
    parser.add_argument("--model-dir", default=None)
    return parser.parse_args()


def _list_available_models():
    """Return all available models from both backends as ModelChoice objects."""
    return list_available_models()


def _select_model_interactive(models):
    """Display an interactive numbered menu and return the selected ModelChoice."""
    if not models:
        print("No models available.", file=sys.stderr)
        return None

    selected = 0
    old_mode = _set_raw_mode(sys.stdin.fileno())

    def render():
        lines = []
        h = _get_terminal_height()
        max_display = min(len(models), h - 8)
        start = max(0, min(selected - max_display // 2, len(models) - max_display))
        end = start + max_display

        lines.append("\033[2J\033[H")
        lines.append("\033[?25l")
        lines.append(f"\n  Select a model ({len(models)} available)\n")
        for i, m in enumerate(models[start:end]):
            idx = start + i + 1
            marker = "\033[34m >\033[0m" if i == selected else "  "
            lines.append(f"{marker} {idx}. {m.display}")
        lines.append(f"\n  Arrow keys: navigate  Enter: select  Esc/Ctrl+C: cancel")
        sys.stdout.write("".join(lines))
        sys.stdout.flush()

    def read_char():
        if old_mode is not None:
            c = sys.stdin.buffer.read(1)
            if len(c) == 0:
                return ""
            if c == b"\x1b":
                c2 = sys.stdin.buffer.read(1)
                if c2 == b"[":
                    c3 = sys.stdin.buffer.read(1)
                    if c3 == b"A":
                        return "UP"
                    elif c3 == b"B":
                        return "DOWN"
                    elif c3 == b"C":
                        return "RIGHT"
                    elif c3 == b"D":
                        return "LEFT"
                    return ""
                return "ESC"
            return c.decode("utf-8", errors="replace")
        else:
            try:
                return input(f"\nChoice [1-{len(models)}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                return "\x03"

    try:
        render()
        while True:
            key = read_char()
            if old_mode is not None:
                # Raw mode: arrow keys navigate, Enter selects, Esc cancels
                if key == "DOWN" or key == "RIGHT":
                    selected = (selected + 1) % len(models)
                    render()
                elif key == "UP" or key == "LEFT":
                    selected = (selected - 1) % len(models)
                    render()
                elif key == "\n" or key == "\r":
                    print()
                    _restore_mode(sys.stdin.fileno(), old_mode)
                    _show_cursor()
                    return models[selected]
                elif key == "\x03" or key == "ESC" or key == "q":
                    print("\nCancelled.")
                    _restore_mode(sys.stdin.fileno(), old_mode)
                    _show_cursor()
                    return None
            else:
                # Line mode: single digit is a selection
                if key.isdigit():
                    n = int(key)
                    if 1 <= n <= len(models):
                        print()
                        _restore_mode(sys.stdin.fileno(), old_mode)
                        _show_cursor()
                        return models[n - 1]
                elif key == "\x03":
                    print("\nCancelled.")
                    _restore_mode(sys.stdin.fileno(), old_mode)
                    _show_cursor()
                    return None
    except KeyboardInterrupt:
        print()
        return None
    finally:
        _restore_mode(sys.stdin.fileno(), old_mode)
        _show_cursor()


def _select_backend_for_model(model_name):
    """When a model name exists on multiple backends, ask user to pick."""
    matching = find_backend_model_matches(model_name)

    if not matching:
        return None

    if len(matching) == 1:
        return matching[0]

    prompt = f"\nModel '{model_name}' exists on multiple backends:\n"
    for i, (b, n) in enumerate(matching):
        prompt += f"  {i + 1}. {b}  {n}\n"
    prompt += f"\nPick backend [1-{len(matching)}]: "
    print(prompt, end="", flush=True)
    try:
        val = input().strip()
        idx = int(val) - 1
        if 0 <= idx < len(matching):
            return matching[idx]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    return None


def list_models():
    script = os.path.basename(sys.argv[0])
    col = 44  # model name column width

    print("Available models:")
    print("  Or run: bal --select  for interactive selection\n")
    model_dirs = local_model_dirs()

    # ollama — scan manifest files on disk
    print("ollama")
    local_models = scan_local_models_by_backend()
    ollama_models = local_models["ollama"]
    if ollama_models is None:
        print(f"     (directory not found: {model_dirs['ollama']})")
    elif ollama_models:
        for name in ollama_models:
            print(f"     {name:<{col}} {script} --model {name}")
    else:
        print("     (no models)")

    print()

    # omlx — scan model directory on disk
    print("omlx")
    omlx_models = local_models["omlx"]
    if omlx_models is not None:
        if omlx_models:
            for name in omlx_models:
                print(f"     {name:<{col}} {script} --model {name} --backend omlx")
        else:
            print("     (no models)")
    else:
        print(f"     (directory not found: {model_dirs['omlx']})")


def init_session(backend, model_name, model_dir=None, dry_run=False):
    session = create_backend(backend, model_name, model_dir=model_dir)
    session.start()
    # Register before preload so preload failures still clean up the backend.
    atexit.register(session.cleanup)
    if not dry_run:
        print(f"Loading {session.model_name}...", flush=True)
        session.preload_model()
    return session


def restore_terminal():
    if sys.stdout.isatty():
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

    agents = ["claude", "codex", "opencode", "openclaw"]
    lines += [
        HorizontalText(""),
        HorizontalText("─── How to run using an agent ───────────────────────────────────────────────────"),
        HorizontalText(""),
    ]
    lines += [
        HorizontalText(f"  {session.launch_command(agent)}")
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


def _run_select():
    """Interactive model picker flow used by --select and bare invocation."""
    models = _list_available_models()
    if not models:
        print("Error: no models available on any backend.", file=sys.stderr)
        sys.exit(1)
    choice = _select_model_interactive(models)
    if choice is None:
        return
    atexit.register(restore_terminal)
    session = init_session(choice.backend, choice.name, dry_run=False)
    stop_event = start_session_ui(session)
    run_input_loop(stop_event)


def main():
    # --- Handle --select (interactive model picker) ---
    if "--select" in sys.argv:
        sys.argv.remove("--select")
        _run_select()
        return

    if len(sys.argv) == 1:
        _run_select()
        return

    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print_help()
        sys.exit(0)

    if sys.argv[1] == "list":
        list_models()
        return

    # --- Agent launch path ---
    if sys.argv[1] in AGENTS:
        agent = sys.argv[1]
        model_arg = sys.argv[2] if len(sys.argv) > 2 else None
        backend = detect_running_backend()
        if backend is None:
            print("Error: no backend running (tried omlx and ollama).", file=sys.stderr)
            sys.exit(1)

        if model_arg is None:
            model = backend.resolve_model(None)
            backend.exec_agent(agent, model)
            return

        # Model specified but may exist on multiple backends
        result = _select_backend_for_model(model_arg)
        if result is not None:
            backend_name, model_arg = result
            backend = create_backend(backend_name, model_arg)
        model = backend.resolve_model(model_arg)
        backend.exec_agent(agent, model)
        return  # unreachable; exec replaces the process

    # --- Server mode path ---
    atexit.register(restore_terminal)
    args = parse_args()
    if args.dry_run or args.model is not None:
        session = init_session(args.backend, args.model, model_dir=args.model_dir, dry_run=args.dry_run)
        stop_event = start_session_ui(session)
        run_input_loop(stop_event)
    else:
        print_help()
        sys.exit(1)
