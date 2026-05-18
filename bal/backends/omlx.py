import json
import os
import subprocess
import sys
import time
import urllib.error

from .base import ModelChoice, http_get


SETTINGS_PATH = os.path.expanduser("~/.omlx/settings.json")
DEFAULT_MODEL_DIR = os.path.expanduser("~/.omlx/models")


def load_settings():
    try:
        with open(SETTINGS_PATH) as f:
            s = json.load(f)
    except Exception:
        s = {}
    api_key = s.get("auth", {}).get("api_key", "")
    server = s.get("server", {})
    host = server.get("host", "127.0.0.1")
    port = server.get("port", 8000)
    return {
        "api_key": api_key,
        "server_url": f"http://{host}:{port}",
        "raw": s,
    }


class OmlxBackend:
    backend_name = "omlx"

    def __init__(self, model_name, model_dir=None):
        self._model_name = model_name
        self._version = None
        self._serve_process = None

        settings = load_settings()
        self._api_key = settings["api_key"]
        self._server_url = settings["server_url"]
        raw_settings = settings["raw"]
        self._model_dir = (
            model_dir
            or raw_settings.get("model", {}).get("model_dir")
            or DEFAULT_MODEL_DIR
        )

    @property
    def model_name(self):
        return self._model_name

    @property
    def version(self):
        return self._version

    def start(self):
        self._serve_process = self._ensure_server_running()
        self._version = self._fetch_version()
        print(f"  omlx {self._version}", flush=True)

    def cleanup(self):
        # Only stop the server if this session started it; leave pre-existing servers alone.
        # poll() is None while our child server process is still running.
        if self._serve_process is not None and self._serve_process.poll() is None:
            print("\nStopping omlx server...", flush=True)
            self._serve_process.terminate()
            try:
                self._serve_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._serve_process.kill()

    def launch_command(self, agent):
        script = os.path.basename(sys.argv[0]).removesuffix(".py")
        return f"{script} {agent} {self._model_name}"

    def resolve_model(self, model_arg):
        if model_arg:
            return model_arg
        try:
            headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
            body = http_get("/v1/models", base_url=self._server_url, timeout=2, headers=headers)
            data = json.loads(body).get("data", [])
            if data:
                return data[0]["id"]
        except Exception:
            pass
        return None

    def exec_agent(self, agent, model):
        if agent == "claude":
            env = os.environ.copy()
            env["ANTHROPIC_BASE_URL"] = self._server_url
            env["ANTHROPIC_AUTH_TOKEN"] = self._api_key
            if model:
                env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model
                env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model
                env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = model
            env["API_TIMEOUT_MS"] = "3000000"
            env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
            os.execvpe("claude", ["claude"], env)
        elif agent == "codex":
            env = os.environ.copy()
            env["OMLX_API_KEY"] = self._api_key
            cmd = ["codex",
                   "-c", 'model_provider="omlx"']
            if model:
                cmd += ["-c", f'model="{model}"']
            os.execvpe("codex", cmd, env)
        else:
            cmd = ["omlx", "launch", agent]
            if model:
                cmd += ["--model", model]
            cmd += ["--api-key", self._api_key]
            os.execvp("omlx", cmd)

    def preload_model(self):
        pass

    def _is_server_running(self):
        return is_server_running(self._server_url)

    def _wait_for_server_ready(self):
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._is_server_running():
                return True
            time.sleep(0.5)
        return False

    def _start_server(self):
        return subprocess.Popen(["omlx", "serve", "--model-dir", self._model_dir])

    def _ensure_server_running(self):
        print("Checking omlx server...", flush=True)
        if self._is_server_running():
            # omlx is commonly kept running as a service; attach to the existing instance.
            print("  Attached to running server.", flush=True)
            return None
        print("  Starting omlx serve...", flush=True)
        process = self._start_server()
        if not self._wait_for_server_ready():
            print("Error: omlx server did not start in time.", file=sys.stderr)
            sys.exit(1)
        print("  Server ready.", flush=True)
        return process

    def _fetch_version(self):
        try:
            headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
            body = http_get("/api/status", base_url=self._server_url, timeout=5, headers=headers)
            return json.loads(body).get("version", "unknown")
        except Exception:
            return "unknown"


def is_server_running(server_url=None):
    settings = load_settings()
    base_url = server_url or settings["server_url"]
    try:
        http_get("/v1/models", base_url=base_url, timeout=2)
        return True
    except urllib.error.HTTPError:
        return True  # any HTTP response means the server is listening
    except Exception:
        return False


def fetch_models():
    choices = []
    settings = load_settings()
    api_key = settings["api_key"]
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        body = http_get("/v1/models", base_url=settings["server_url"], timeout=5, headers=headers)
        data = json.loads(body)
        for m in data.get("data", []):
            model_id = m.get("id", "")
            version = m.get("version", "")
            display = f"omlx {model_id}"
            if version:
                display += f" ({version})"
            choices.append(ModelChoice(name=model_id, backend="omlx", version=version,
                                       display=display))
    except Exception:
        pass
    return choices


def scan_models():
    model_dir = DEFAULT_MODEL_DIR
    if not os.path.isdir(model_dir):
        return None
    return sorted(
        e for e in os.listdir(model_dir)
        if os.path.isdir(os.path.join(model_dir, e))
    )


def default_model_dir():
    return DEFAULT_MODEL_DIR
