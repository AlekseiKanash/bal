#!/usr/bin/env python3
# bal — LLM Backend Launcher
# Manages ollama/omlx server lifecycle and proxies agent launch commands.

import argparse
import atexit
import os
import shutil
import signal
import sys
import threading
import time

from importlib.metadata import version as _meta_version

from simple_term_menu import TerminalMenu

from .backends import (
    backends_manager,
    BackendManager,
)
from .widgets.header import SessionHeader
from .widgets.horizontal_text import HorizontalText
from .widgets.border import Border
from .widgets.statistics import StatisticsWidget, ram_getter
from .widgets.status_separator import SessionStatus, SessionStatusSeparator
from .widgets.log_widget import LogWidget


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

AGENTS = ("claude", "codex", "opencode", "openclaw")


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
    backend_names = sorted(cls.backend_name for cls in BackendManager.backends)
    parser.add_argument("--backend", default=backend_names[0], choices=backend_names)
    parser.add_argument("--model-dir", default=None, metavar="PATH")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _pick_model():
    """Interactively select a model; returns ModelChoice or None if cancelled."""
    models = backends_manager.list_available_models()
    if not models:
        print("Error: no models available on any backend.", file=sys.stderr)
        sys.exit(1)
    idx = TerminalMenu([m.display for m in models], title="Select a model").show()
    if idx is None:
        return None
    return models[idx]


def _resolve_session_params(args):
    """Return (backend, model_name, model_dir, dry_run) or None if cancelled."""
    bare = args.command is None and args.server_model is None and not args.dry_run
    if args.select or bare:
        choice = _pick_model()
        if choice is None:
            return None
        return choice.backend, choice.name, None, False
    return args.backend, args.server_model, args.model_dir, args.dry_run


def _select_backend_for_model(model_name):
    """When a model name exists on multiple backends, ask user to pick."""
    matching = backends_manager.find_backend_model_matches(model_name)

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
    model_dirs = backends_manager.local_model_dirs()
    local_models = backends_manager.scan_local_models_by_backend()

    for cls in BackendManager.backends:
        print(cls.backend_name)
        models = local_models.get(cls.backend_name)
        if models is None:
            print(f"     (directory not found: {model_dirs.get(cls.backend_name, 'unknown')})")
        elif models:
            for name in models:
                print(f"     {name:<{col}} {script} --model {name} --backend {cls.backend_name}")
        else:
            print("     (no models)")
        print()


def restore_terminal():
    if sys.stdout.isatty():
        sys.stdout.write("\033[r")        # reset scrolling region to full screen
        sys.stdout.write("\033[?25h")     # ensure cursor is visible on exit
        sys.stdout.flush()


def _run_update_loop(updatables: list, stop_event: threading.Event):
    _last_tick = time.time()
    while not stop_event.is_set():
        now = time.time()
        delta_ms = (now - _last_tick) * 1000
        _last_tick = now
        for obj in updatables:
            obj.tick(delta_ms)
        sys.stdout.flush()
        stop_event.wait(HEADER_UPDATE_INTERVAL_SECONDS)


def _build_ui(session, status) -> list:
    """Build and initialize all updatable UI objects. Must be called after terminal is cleared."""

    lines = []

    lines += [
        SessionHeader(session, row=1),
        Border(row=2, height=5, width=83),
    ]

    lines += [StatisticsWidget()]

    lines += [
        HorizontalText(""),
        HorizontalText("─── How to run using an agent ───────────────────────────────────────────────────"),
        HorizontalText(""),
    ]
    lines += [
        HorizontalText(f"  {session.launch_command(agent)}")
        for agent in AGENTS
    ]

    lines += [
        HorizontalText(""),
        SessionStatusSeparator(status, width=83),
        HorizontalText(""),
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


def start_session_ui(session, status):
    sys.stdout.write("\033[2J\033[H")                    # clear + home
    updatables = _build_ui(session, status)
    for w in updatables:
        w.tick(0.0)                                      # first paint, delta = 0
    ui_bottom = max(w._row + getattr(w, "height", 1) - 1 for w in updatables)
    term_rows = shutil.get_terminal_size().lines
    log_top = ui_bottom + 1
    sys.stdout.write(f"\033[{log_top};{term_rows}r")     # DECSTBM scroll region
    sys.stdout.write(f"\033[{log_top};1H")               # park cursor in log area
    sys.stdout.flush()
    log_widget = LogWidget(log_top)
    updatables.append(log_widget)
    stop_event = threading.Event()
    threading.Thread(target=_run_update_loop, args=(updatables, stop_event), daemon=True).start()
    return stop_event, log_widget


def run_input_loop(stop_event: threading.Event, log_widget: LogWidget):
    def handle_exit(signum, frame):
        stop_event.set()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    try:
        while True:
            try:
                user_input = input(INPUT_PROMPT)
            except EOFError:
                break
            log_widget.append(user_input)
            if user_input.startswith("/"):
                # Command dispatch — no commands defined yet
                pass
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()


def _start_session(backend, model_name, *, model_dir=None, dry_run=False):
    atexit.register(restore_terminal)
    session = backends_manager.create_backend(backend, model_name, model_dir=model_dir)
    atexit.register(session.cleanup)
    status = SessionStatus()
    stop_event, log_widget = start_session_ui(session, status)
    session.start()
    if not dry_run:
        size_gb = session.model_size_bytes() / (1024 ** 3)
        baseline_gb = float(ram_getter())
        status.start_loading(session.model_name, size_gb, baseline_gb, ram_getter)
        print(f"Loading {session.model_name}...", flush=True)
        session.preload_model()
    status.set_live()
    run_input_loop(stop_event, log_widget)


def _run_agent(agent, model_arg):
    backend_name = backends_manager.detect_running_backend()
    if backend_name is None:
        _names = ", ".join(cls.backend_name for cls in BackendManager.backends)
        print(f"Error: no backend running (tried {_names}).", file=sys.stderr)
        sys.exit(1)
    backend = backends_manager.create_backend(backend_name, None)
    if model_arg is None:
        backend.exec_agent(agent, backend.resolve_model(None))
        return
    result = _select_backend_for_model(model_arg)
    if result is not None:
        backend_name, model_arg = result
        backend = backends_manager.create_backend(backend_name, model_arg)
    backend.exec_agent(agent, backend.resolve_model(model_arg))


def main():
    args = parse_args()

    if args.command == "list":
        list_models()
        return
    if args.command in AGENTS:
        _run_agent(args.command, args.model_arg)
        return

    params = _resolve_session_params(args)
    if params is None:
        return
    backend, model_name, model_dir, dry_run = params
    _start_session(backend, model_name, model_dir=model_dir, dry_run=dry_run)
