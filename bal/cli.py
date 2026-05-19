#!/usr/bin/env python3
# bal — LLM Backend Launcher
# Manages ollama/omlx server lifecycle and proxies agent launch commands.

import argparse
import atexit
import os
import signal
import sys
import threading
import time

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
from .widgets.horizontal_text import HorizontalText
from .widgets.border import Border
from .widgets.statistics import StatisticsWidget


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


def parse_args():
    parser = argparse.ArgumentParser(
        prog="bal",
        add_help=True,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="LLM backend launcher",
        epilog="""\
commands:
  list                        show available models (no server needed)
  claude|codex|opencode|openclaw [model]
                              launch agent against a running backend

server options:
  --model <name>              model to load
  --backend ollama|omlx       backend (default: ollama)
  --model-dir <path>          model directory (omlx only)
  --dry-run                   start UI without loading a model

bare invocation or --select opens the interactive model picker.""",
    )
    parser.add_argument("--version", action="version", version=f"bal {VERSION}")
    parser.add_argument("--select", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs="?", choices=["list", *sorted(AGENTS)], metavar="command")
    parser.add_argument("model_arg", nargs="?", metavar="model")
    parser.add_argument("--model", dest="server_model", metavar="NAME")
    parser.add_argument("--backend", default="ollama", choices=["ollama", "omlx"])
    parser.add_argument("--model-dir", default=None, metavar="PATH")
    parser.add_argument("--dry-run", action="store_true")
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


def _build_ui(session) -> list:
    """Build and initialize all updatable UI objects. Must be called after terminal is cleared."""

    lines = []

    lines += [
        SessionHeader(session, row=1),
        Border(row=2, height=5, width=83),
    ]

    lines += [StatisticsWidget()]

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
    hi = max(all_rows) if all_rows else 1

    next_auto_row = hi + 1
    for widget in auto:
        widget._row = next_auto_row
        next_auto_row += getattr(widget, 'height', 1)

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


def _run_agent(agent, model_arg):
    backend = detect_running_backend()
    if backend is None:
        print("Error: no backend running (tried omlx and ollama).", file=sys.stderr)
        sys.exit(1)
    if model_arg is None:
        backend.exec_agent(agent, backend.resolve_model(None))
        return
    result = _select_backend_for_model(model_arg)
    if result is not None:
        backend_name, model_arg = result
        backend = create_backend(backend_name, model_arg)
    backend.exec_agent(agent, backend.resolve_model(model_arg))


def _run_server(args):
    if args.server_model is None and not args.dry_run:
        print("Error: --model is required (or use --dry-run or --select)", file=sys.stderr)
        sys.exit(1)
    atexit.register(restore_terminal)
    session = init_session(args.backend, args.server_model, model_dir=args.model_dir, dry_run=args.dry_run)
    stop_event = start_session_ui(session)
    run_input_loop(stop_event)


def main():
    args = parse_args()
    if args.select or (args.command is None and args.server_model is None and not args.dry_run):
        _run_select()
    elif args.command == "list":
        list_models()
    elif args.command in AGENTS:
        _run_agent(args.command, args.model_arg)
    else:
        _run_server(args)
