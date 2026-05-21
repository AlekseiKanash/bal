import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from bal import cli
from bal.backends import ModelChoice, create_backend, list_available_models
from bal.backends.ollama import OllamaBackend
from bal.backends.omlx import OmlxBackend
from bal.widgets.header import SessionHeader
from bal.widgets.status_separator import SessionStatus, SessionStatusSeparator


_FAKE_SETTINGS = {
    "api_key": "",
    "server_url": "http://127.0.0.1:8000",
    "raw": {},
}


class FakeBackend:
    backend_name = "fake"

    def __init__(self, model_name="model"):
        self._model_name = model_name
        self._version = "1.2.3"
        self.calls = []

    @property
    def model_name(self):
        return self._model_name

    @property
    def version(self):
        return self._version

    def start(self):
        self.calls.append("start")

    def cleanup(self):
        self.calls.append("cleanup")

    def preload_model(self):
        self.calls.append("preload")

    def model_size_bytes(self):
        return 0

    def launch_command(self, agent):
        return f"bal {agent} {self.model_name}"


class FakeProcess:
    def __init__(self, poll_result, raise_timeout=False):
        self._poll_result = poll_result
        self._raise_timeout = raise_timeout
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return self._poll_result

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.waited = True
        if self._raise_timeout:
            raise subprocess.TimeoutExpired(cmd="", timeout=timeout)

    def kill(self):
        self.killed = True


def make_omlx_backend(model_name="qwen", model_dir=None):
    with mock.patch("bal.backends.omlx._load_settings", return_value=_FAKE_SETTINGS):
        return OmlxBackend(model_name, model_dir=model_dir)


class CreateBackendTests(unittest.TestCase):
    def test_create_backend_returns_selected_backend(self):
        self.assertIsInstance(create_backend("ollama", "llama3"), OllamaBackend)

        with mock.patch("bal.backends.omlx._load_settings", return_value=_FAKE_SETTINGS):
            self.assertIsInstance(create_backend("omlx", "qwen"), OmlxBackend)

    def test_create_backend_raises_for_unknown_backend(self):
        with self.assertRaises(ValueError):
            create_backend("unknown", "model")


class StartSessionTests(unittest.TestCase):
    """_start_session orchestrates the backend lifecycle and status transitions."""

    def _run_start_session(self, fake, *, dry_run=False, capture_status=None):
        registered = []

        def register(func):
            registered.append(func)

        def maybe_capture(session, status):
            if capture_status is not None:
                capture_status["status"] = status
            return mock.MagicMock()

        with (
            mock.patch.object(cli, "create_backend", return_value=fake),
            mock.patch.object(cli.atexit, "register", side_effect=register),
            mock.patch.object(cli, "start_session_ui", side_effect=maybe_capture),
            mock.patch.object(cli, "run_input_loop"),
            mock.patch.object(cli, "ram_getter", return_value="10.0"),
            redirect_stdout(io.StringIO()),
        ):
            cli._start_session("ollama", fake.model_name, dry_run=dry_run)
        return registered

    def test_start_session_runs_start_then_preload(self):
        fake = FakeBackend("qwen3")
        self._run_start_session(fake)
        self.assertEqual(fake.calls, ["start", "preload"])

    def test_dry_run_skips_preload(self):
        fake = FakeBackend("qwen3")
        self._run_start_session(fake, dry_run=True)
        self.assertEqual(fake.calls, ["start"])

    def test_registers_restore_terminal_then_cleanup_with_atexit(self):
        fake = FakeBackend("qwen3")
        registered = self._run_start_session(fake)
        self.assertEqual(registered[0], cli.restore_terminal)
        self.assertEqual(registered[1], fake.cleanup)

    def test_status_reaches_live_after_preload(self):
        fake = FakeBackend("qwen3")
        captured = {}
        self._run_start_session(fake, capture_status=captured)
        self.assertEqual(captured["status"].state, SessionStatus.LIVE)

    def test_dry_run_status_also_reaches_live(self):
        fake = FakeBackend("qwen3")
        captured = {}
        self._run_start_session(fake, dry_run=True, capture_status=captured)
        self.assertEqual(captured["status"].state, SessionStatus.LIVE)


class HeaderTests(unittest.TestCase):
    def test_session_header_renders_backend_version_model_and_elapsed_time(self):
        backend = SimpleNamespace(
            backend_name="ollama",
            version="0.6.1",
            model_name="llama3",
        )

        with mock.patch("bal.widgets.header.time.time", return_value=100.0):
            header = SessionHeader(backend, row=1)

        out = io.StringIO()
        with redirect_stdout(out):
            header.tick(100.0 + 3723)

        rendered = out.getvalue()
        self.assertIn("BAL | ollama 0.6.1", rendered)
        self.assertIn("Loaded: llama3", rendered)
        self.assertIn("Running: 1:02:03", rendered)


class SessionStatusTests(unittest.TestCase):
    def test_initial_state_is_booting(self):
        self.assertEqual(SessionStatus().state, SessionStatus.BOOTING)

    def test_start_loading_advances_state_and_records_fields(self):
        s = SessionStatus()
        s.start_loading("qwen3", model_size_gb=18.0, baseline_ram_gb=10.0, ram_getter=lambda: "10.5")
        self.assertEqual(s.state, SessionStatus.LOADING)
        self.assertEqual(s.model_name, "qwen3")
        self.assertEqual(s.model_size_gb, 18.0)
        self.assertEqual(s.baseline_ram_gb, 10.0)
        self.assertGreater(s.load_started_at, 0)

    def test_set_live_advances_state(self):
        s = SessionStatus()
        s.set_live()
        self.assertEqual(s.state, SessionStatus.LIVE)


class SessionStatusSeparatorTests(unittest.TestCase):
    WIDTH = 83

    def _render(self, status, now=0.0):
        return SessionStatusSeparator(status, width=self.WIDTH, row=1)._format(now)

    def test_booting_label_pads_to_width(self):
        out = self._render(SessionStatus())
        self.assertTrue(out.startswith("─── Booting "))
        self.assertEqual(len(out), self.WIDTH)

    def test_loading_renders_percent_bar_and_elapsed(self):
        s = SessionStatus()
        s.start_loading("qwen3", model_size_gb=10.0, baseline_ram_gb=10.0, ram_getter=lambda: "12.0")
        out = self._render(s, now=s.load_started_at + 5)
        self.assertIn("Loading qwen3", out)
        self.assertIn("20%", out)
        self.assertIn("(5s)", out)
        self.assertEqual(len(out), self.WIDTH)

    def test_loading_caps_at_99_percent(self):
        s = SessionStatus()
        s.start_loading("qwen3", model_size_gb=10.0, baseline_ram_gb=0.0, ram_getter=lambda: "100.0")
        out = self._render(s, now=s.load_started_at + 1)
        self.assertIn("99%", out)
        self.assertNotIn("100%", out)

    def test_loading_with_unknown_size_omits_bar_and_percent(self):
        s = SessionStatus()
        s.start_loading("qwen3", model_size_gb=0.0, baseline_ram_gb=0.0, ram_getter=lambda: "0")
        out = self._render(s, now=s.load_started_at + 3)
        self.assertIn("Loading qwen3", out)
        self.assertIn("(3s)", out)
        self.assertNotIn("%", out)
        self.assertNotIn("[", out)
        self.assertEqual(len(out), self.WIDTH)

    def test_loading_negative_delta_renders_zero_percent(self):
        # Free pages reclaimed during load can make delta briefly negative.
        s = SessionStatus()
        s.start_loading("qwen3", model_size_gb=10.0, baseline_ram_gb=20.0, ram_getter=lambda: "15.0")
        out = self._render(s, now=s.load_started_at + 1)
        self.assertIn("0%", out)

    def test_live_label_pads_to_width(self):
        s = SessionStatus()
        s.set_live()
        out = self._render(s)
        self.assertTrue(out.startswith("─── Live "))
        self.assertEqual(len(out), self.WIDTH)


class ModelSizeBytesTests(unittest.TestCase):
    def test_ollama_returns_size_from_api_tags(self):
        backend = OllamaBackend("llama3:8b")
        body = json.dumps({"models": [
            {"name": "llama3:8b", "size": 4_800_000_000},
            {"name": "other:1b", "size": 1_000_000_000},
        ]})
        with mock.patch("bal.backends.ollama.http_get", return_value=body):
            self.assertEqual(backend.model_size_bytes(), 4_800_000_000)

    def test_ollama_returns_zero_when_model_not_listed(self):
        backend = OllamaBackend("missing")
        body = json.dumps({"models": [{"name": "other:1b", "size": 10}]})
        with mock.patch("bal.backends.ollama.http_get", return_value=body):
            self.assertEqual(backend.model_size_bytes(), 0)

    def test_ollama_returns_zero_when_api_fails(self):
        backend = OllamaBackend("llama3:8b")
        with mock.patch("bal.backends.ollama.http_get", side_effect=Exception("down")):
            self.assertEqual(backend.model_size_bytes(), 0)

    def test_omlx_sums_file_sizes_in_model_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = os.path.join(tmp, "qwen3")
            os.makedirs(os.path.join(model_dir, "weights"))
            with open(os.path.join(model_dir, "config.json"), "wb") as f:
                f.write(b"x" * 100)
            with open(os.path.join(model_dir, "weights", "model.bin"), "wb") as f:
                f.write(b"x" * 5000)

            backend = make_omlx_backend("qwen3", model_dir=tmp)
            self.assertEqual(backend.model_size_bytes(), 5100)

    def test_omlx_returns_zero_when_directory_missing(self):
        backend = make_omlx_backend("nonexistent", model_dir="/no/such/path")
        self.assertEqual(backend.model_size_bytes(), 0)


class ListAvailableModelsTests(unittest.TestCase):
    def test_per_backend_fallback_combines_live_and_scanned(self):
        # Ollama server down → fall back to its filesystem scan.
        # Omlx server up → use its live list.
        # Both backends should contribute models to the picker.
        with (
            mock.patch.object(OllamaBackend, "fetch_models", return_value=[]),
            mock.patch.object(OllamaBackend, "scan_models", return_value=["llama3:8b"]),
            mock.patch.object(
                OmlxBackend, "fetch_models",
                return_value=[ModelChoice("Qwen3", "omlx", "", "omlx Qwen3")],
            ),
        ):
            models = list_available_models()

        names = {(m.backend, m.name) for m in models}
        self.assertIn(("ollama", "llama3:8b"), names)
        self.assertIn(("omlx", "Qwen3"), names)


class CleanupTests(unittest.TestCase):
    def test_ollama_cleanup_unloads_and_stops_live_owned_process(self):
        backend = OllamaBackend("llama3")
        process = FakeProcess(poll_result=None)
        backend._serve_process = process

        with (
            mock.patch.object(backend, "_unload_model") as unload,
            redirect_stdout(io.StringIO()),
        ):
            backend.cleanup()

        unload.assert_called_once_with()
        self.assertTrue(process.terminated)
        self.assertTrue(process.waited)
        self.assertFalse(process.killed)

    def test_ollama_cleanup_kills_process_after_timeout(self):
        backend = OllamaBackend("llama3")
        process = FakeProcess(poll_result=None, raise_timeout=True)
        backend._serve_process = process

        with (
            mock.patch.object(backend, "_unload_model"),
            redirect_stdout(io.StringIO()),
        ):
            backend.cleanup()

        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)

    def test_ollama_cleanup_does_not_stop_exited_process(self):
        backend = OllamaBackend("llama3")
        process = FakeProcess(poll_result=0)
        backend._serve_process = process

        with (
            mock.patch.object(backend, "_unload_model") as unload,
            redirect_stdout(io.StringIO()),
        ):
            backend.cleanup()

        unload.assert_called_once_with()
        self.assertFalse(process.terminated)

    def test_omlx_cleanup_stops_live_owned_process_only(self):
        backend = make_omlx_backend()
        live = FakeProcess(poll_result=None)
        backend._serve_process = live

        with redirect_stdout(io.StringIO()):
            backend.cleanup()

        self.assertTrue(live.terminated)
        self.assertTrue(live.waited)

        attached = make_omlx_backend()
        attached._serve_process = None
        with redirect_stdout(io.StringIO()):
            attached.cleanup()

    def test_omlx_cleanup_kills_process_after_timeout(self):
        backend = make_omlx_backend()
        process = FakeProcess(poll_result=None, raise_timeout=True)
        backend._serve_process = process

        with redirect_stdout(io.StringIO()):
            backend.cleanup()

        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)


class EnsureServerRunningTests(unittest.TestCase):
    def test_ollama_terminates_process_when_server_does_not_start(self):
        backend = OllamaBackend("llama3")
        process = FakeProcess(poll_result=None)

        with (
            mock.patch.object(backend, "_start_server", return_value=process),
            mock.patch.object(backend, "_wait_for_server_ready", return_value=False),
            redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as cm,
        ):
            backend._ensure_server_running()

        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(process.terminated)

    def test_omlx_terminates_process_when_server_does_not_start(self):
        backend = make_omlx_backend()
        process = FakeProcess(poll_result=None)

        with (
            mock.patch.object(OmlxBackend, "is_server_running", return_value=False),
            mock.patch.object(backend, "_start_server", return_value=process),
            mock.patch.object(backend, "_wait_for_server_ready", return_value=False),
            redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as cm,
        ):
            backend._ensure_server_running()

        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(process.terminated)


class AgentExecTests(unittest.TestCase):
    def test_ollama_exec_agent_calls_ollama_launch_with_model(self):
        backend = OllamaBackend("llama3")
        with mock.patch("bal.backends.ollama.os.execvp") as execvp:
            backend.exec_agent("claude", "llama3")

        execvp.assert_called_once_with(
            "ollama",
            ["ollama", "launch", "claude", "--model", "llama3"],
        )

    def test_ollama_exec_agent_without_model_omits_model_flag(self):
        backend = OllamaBackend("llama3")
        with mock.patch("bal.backends.ollama.os.execvp") as execvp:
            backend.exec_agent("claude", None)

        execvp.assert_called_once_with("ollama", ["ollama", "launch", "claude"])

    def test_omlx_claude_exec_sets_anthropic_env(self):
        backend = make_omlx_backend()
        backend._api_key = "mykey"
        backend._server_url = "http://127.0.0.1:8000"
        with mock.patch("bal.backends.omlx.os.execvpe") as execvpe:
            backend.exec_agent("claude", "qwen3")

        binary, cmd, env = execvpe.call_args.args
        self.assertEqual(binary, "claude")
        self.assertEqual(cmd, ["claude"])
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:8000")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "mykey")
        self.assertEqual(env["ANTHROPIC_DEFAULT_SONNET_MODEL"], "qwen3")
        self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "qwen3")
        self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "qwen3")

    def test_omlx_codex_exec_uses_provider_config_and_api_key(self):
        backend = make_omlx_backend()
        backend._api_key = "secret"
        backend._server_url = "http://127.0.0.1:8000"
        with mock.patch("bal.backends.omlx.os.execvpe") as execvpe:
            backend.exec_agent("codex", "qwen")

        binary, cmd, env = execvpe.call_args.args
        self.assertEqual(binary, "codex")
        self.assertEqual(
            cmd,
            ["codex", "-c", 'model_provider="omlx"', "-c", 'model="qwen"'],
        )
        self.assertEqual(env["OMLX_API_KEY"], "secret")

    def test_omlx_unknown_agent_uses_omlx_launch(self):
        backend = make_omlx_backend()
        backend._api_key = "mykey"
        backend._server_url = "http://127.0.0.1:8000"
        with mock.patch("bal.backends.omlx.os.execvp") as execvp:
            backend.exec_agent("opencode", "qwen3")

        execvp.assert_called_once_with(
            "omlx",
            ["omlx", "launch", "opencode", "--model", "qwen3", "--api-key", "mykey"],
        )

    def test_omlx_exec_agent_uses_settings_without_calling_start(self):
        # Regression for crash: _run_agent creates a backend without calling start().
        # exec_agent must use the URL and key loaded at construction time.
        settings = {
            "api_key": "fromfile",
            "server_url": "http://127.0.0.1:9000",
            "raw": {},
        }
        with mock.patch("bal.backends.omlx._load_settings", return_value=settings):
            backend = OmlxBackend("qwen")

        with mock.patch("bal.backends.omlx.os.execvpe") as execvpe:
            backend.exec_agent("claude", None)

        _, _, env = execvpe.call_args.args
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:9000")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "fromfile")


class ResolveModelTests(unittest.TestCase):
    def test_omlx_resolve_model_returns_arg_when_given(self):
        backend = make_omlx_backend()
        self.assertEqual(backend.resolve_model("llama3"), "llama3")

    def test_omlx_resolve_model_queries_api_when_no_arg(self):
        backend = make_omlx_backend()
        backend._api_key = "key"
        response_body = json.dumps({"data": [{"id": "qwen3-8b"}]})
        with mock.patch("bal.backends.omlx.http_get", return_value=response_body):
            result = backend.resolve_model(None)
        self.assertEqual(result, "qwen3-8b")

    def test_omlx_resolve_model_returns_none_when_api_fails(self):
        backend = make_omlx_backend()
        with mock.patch("bal.backends.omlx.http_get", side_effect=Exception("connection refused")):
            result = backend.resolve_model(None)
        self.assertIsNone(result)

    def test_ollama_resolve_model_returns_arg_unchanged(self):
        backend = OllamaBackend("llama3")
        self.assertEqual(backend.resolve_model("qwen3"), "qwen3")
        self.assertIsNone(backend.resolve_model(None))


class RunAgentTests(unittest.TestCase):
    def test_run_agent_exits_when_no_backend_running(self):
        with (
            mock.patch.object(cli, "detect_running_backend", return_value=None),
            self.assertRaises(SystemExit) as cm,
            redirect_stdout(io.StringIO()),
        ):
            cli._run_agent("claude", None)
        self.assertEqual(cm.exception.code, 1)


class ParseArgsTests(unittest.TestCase):
    def _parse(self, *argv):
        with mock.patch("sys.argv", ["bal", *argv]):
            return cli.parse_args()

    def test_bare_has_all_defaults(self):
        args = self._parse()
        self.assertIsNone(args.command)
        self.assertIsNone(args.server_model)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.backend, "ollama")
        self.assertFalse(args.select)

    def test_select_flag(self):
        self.assertTrue(self._parse("--select").select)

    def test_list_command(self):
        self.assertEqual(self._parse("list").command, "list")

    def test_agent_without_model(self):
        args = self._parse("claude")
        self.assertEqual(args.command, "claude")
        self.assertIsNone(args.model_arg)

    def test_agent_with_model(self):
        args = self._parse("claude", "qwen3")
        self.assertEqual(args.command, "claude")
        self.assertEqual(args.model_arg, "qwen3")

    def test_server_model_flag(self):
        self.assertEqual(self._parse("--model", "qwen3").server_model, "qwen3")

    def test_model_dir_flag(self):
        self.assertEqual(self._parse("--model-dir", "/models").model_dir, "/models")

    def test_dry_run_flag(self):
        self.assertTrue(self._parse("--dry-run").dry_run)

    def test_backend_flag(self):
        self.assertEqual(self._parse("--model", "q", "--backend", "omlx").backend, "omlx")

    def test_unknown_command_exits(self):
        with self.assertRaises(SystemExit):
            self._parse("unknownagent")


class MainDispatchTests(unittest.TestCase):
    def _run(self, *argv):
        with mock.patch("sys.argv", ["bal", *argv]):
            cli.main()

    def test_bare_invocation_picks_model_then_starts_session(self):
        choice = ModelChoice("llama3", "ollama", "latest", "ollama llama3")
        with (
            mock.patch.object(cli, "_pick_model", return_value=choice) as pick,
            mock.patch.object(cli, "_start_session") as start,
        ):
            self._run()
        pick.assert_called_once()
        start.assert_called_once_with("ollama", "llama3", model_dir=None, dry_run=False)

    def test_bare_invocation_cancel_skips_session(self):
        with (
            mock.patch.object(cli, "_pick_model", return_value=None),
            mock.patch.object(cli, "_start_session") as start,
        ):
            self._run()
        start.assert_not_called()

    def test_select_flag_picks_model_then_starts_session(self):
        choice = ModelChoice("llama3", "ollama", "latest", "ollama llama3")
        with (
            mock.patch.object(cli, "_pick_model", return_value=choice) as pick,
            mock.patch.object(cli, "_start_session") as start,
        ):
            self._run("--select")
        pick.assert_called_once()
        start.assert_called_once_with("ollama", "llama3", model_dir=None, dry_run=False)

    def test_list_calls_list_models(self):
        with mock.patch.object(cli, "list_models") as m:
            self._run("list")
        m.assert_called_once()

    def test_agent_calls_run_agent(self):
        with mock.patch.object(cli, "_run_agent") as m:
            self._run("claude")
        m.assert_called_once_with("claude", None)

    def test_agent_with_model_calls_run_agent(self):
        with mock.patch.object(cli, "_run_agent") as m:
            self._run("claude", "qwen3")
        m.assert_called_once_with("claude", "qwen3")

    def test_server_model_calls_start_session(self):
        with mock.patch.object(cli, "_start_session") as m:
            self._run("--model", "qwen3")
        m.assert_called_once_with("ollama", "qwen3", model_dir=None, dry_run=False)

    def test_server_dry_run_calls_start_session(self):
        with mock.patch.object(cli, "_start_session") as m:
            self._run("--dry-run")
        m.assert_called_once_with("ollama", None, model_dir=None, dry_run=True)


if __name__ == "__main__":
    unittest.main()
