#!/usr/bin/env python3

import argparse
import atexit
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from header import SessionHeader


OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_SERVER_START_TIMEOUT_SECONDS = 30
OLLAMA_HEALTH_POLL_INTERVAL_SECONDS = 0.5
MODEL_LOAD_TIMEOUT_SECONDS = 120
HEADER_UPDATE_INTERVAL_SECONDS = 1
INPUT_PROMPT = "> "


def parse_args():
    parser = argparse.ArgumentParser(
        description="Start a persistent local LLM session via ollama."
    )
    parser.add_argument("--model", required=True, help="Ollama model name to load")
    return parser.parse_args()


def http_get(path, timeout=5):
    with urllib.request.urlopen(OLLAMA_BASE_URL + path, timeout=timeout) as resp:
        return resp.read().decode()


def http_post(path, payload, timeout=30):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        OLLAMA_BASE_URL + path,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


class OllamaSession:
    def __init__(self, model_name):
        self._model_name = model_name
        self._version = None
        self._serve_process = None

    def start(self):
        self._serve_process = self._ensure_server_running()
        self._version = self._fetch_version()
        print(f"  ollama {self._version}", flush=True)
        print(f"Loading {self._model_name}...", flush=True)
        self._preload_model()

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


def init_ollama(model_name):
    ollama = OllamaSession(model_name)
    ollama.start()
    atexit.register(ollama.cleanup)
    return ollama


def restore_terminal():
    sys.stdout.write("\033[?25h")  # ensure cursor is visible on exit
    sys.stdout.flush()


def _run_update_loop(header: SessionHeader, stop_event: threading.Event):
    while not stop_event.is_set():
        header.update()
        stop_event.wait(HEADER_UPDATE_INTERVAL_SECONDS)


def start_session_ui(ollama: OllamaSession):
    os.system("clear")
    header = SessionHeader(ollama)
    header.start()
    sys.stdout.write("\n\n")
    sys.stdout.flush()
    stop_event = threading.Event()
    threading.Thread(target=_run_update_loop, args=(header, stop_event), daemon=True).start()
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
    ollama = init_ollama(args.model)
    stop_event = start_session_ui(ollama)
    run_input_loop(stop_event)


if __name__ == "__main__":
    main()
