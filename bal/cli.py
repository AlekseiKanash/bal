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

from simple_term_menu import TerminalMenu

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


def _pick_model():
    """Interactively select a model; returns ModelChoice or None if cancelled."""
    models = _list_available_models()
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


def _start_session(backend, model_name, *, model_dir=None, dry_run=False):
    atexit.register(restore_terminal)
    session = init_session(backend, model_name, model_dir=model_dir, dry_run=dry_run)
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
