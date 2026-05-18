import json
import os
import subprocess
import sys
import time
import urllib.error

from .base import ModelChoice, http_get, http_post


OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaBackend:
    backend_name = "ollama"

    def __init__(self, model_name):
        self._model_name = model_name
        self._version = None
        self._serve_process = None

    @property
    def model_name(self):
        return self._model_name

    @property
    def version(self):
        return self._version

    def start(self):
        self._serve_process = self._ensure_server_running()
        self._version = self._fetch_version()
        print(f"  ollama {self._version}", flush=True)

    def cleanup(self):
        print("\nUnloading model...", flush=True)
        self._unload_model()
        # poll() is None while our child server process is still running.
        if self._serve_process is not None and self._serve_process.poll() is None:
            print("Stopping ollama server...", flush=True)
            self._serve_process.terminate()
            try:
                self._serve_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._serve_process.kill()

    def launch_command(self, agent):
        script = os.path.basename(sys.argv[0]).removesuffix(".py")
        return f"{script} {agent} {self._model_name}"

    def resolve_model(self, model_arg):
        return model_arg

    def exec_agent(self, agent, model):
        cmd = ["ollama", "launch", agent]
        if model:
            cmd += ["--model", model]
        os.execvp("ollama", cmd)

    def preload_model(self):
        MODEL_LOAD_TIMEOUT_SECONDS = 120

        try:
            with http_post(
                "/api/generate",
                {"model": self._model_name, "keep_alive": -1},
                base_url=OLLAMA_BASE_URL,
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

    def _is_server_running(self):
        return is_server_running()

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
            body = http_get("/api/version", base_url=OLLAMA_BASE_URL)
            return json.loads(body).get("version", "unknown")
        except Exception:
            return "unknown"

    def _unload_model(self):
        try:
            with http_post("/api/generate", {"model": self._model_name, "keep_alive": 0}, base_url=OLLAMA_BASE_URL, timeout=10) as resp:
                resp.read()
        except Exception:
            pass


def is_server_running():
    try:
        http_get("/", base_url=OLLAMA_BASE_URL, timeout=2)
        return True
    except Exception:
        return False


def fetch_models():
    choices = []
    try:
        body = http_get("/api/tags", base_url=OLLAMA_BASE_URL, timeout=5)
        data = json.loads(body)
        for m in data.get("models", []):
            name = m.get("name", "")
            tag = name.split(":")[-1] if ":" in name else ""
            choices.append(ModelChoice(name=name, backend="ollama", version=tag,
                                       display=f"ollama {name}"))
    except Exception:
        pass
    return choices


def scan_models():
    manifests_dir = os.path.expanduser("~/.ollama/models/manifests")
    if not os.path.isdir(manifests_dir):
        return None
    models = []
    for root, _dirs, files in os.walk(manifests_dir):
        for fname in files:
            rel = os.path.relpath(os.path.join(root, fname), manifests_dir)
            parts = rel.split(os.sep)
            if len(parts) == 4:
                registry, namespace, model, tag = parts
                if registry == "registry.ollama.ai" and namespace == "library":
                    models.append(f"{model}:{tag}")
                else:
                    models.append(f"{registry}/{namespace}/{model}:{tag}")
    return sorted(models)
