import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from bal import cli
from bal.backends import ModelChoice, create_backend
from bal.backends.ollama import OllamaBackend
from bal.backends.omlx import OmlxBackend
from bal.widgets.header import SessionHeader


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

    def launch_command(self, agent):
        return f"bal {agent} {self.model_name}"


class FakeProcess:
    def __init__(self, poll_result):
        self._poll_result = poll_result
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return self._poll_result

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.waited = True

    def kill(self):
        self.killed = True


def make_omlx_backend(model_name="qwen"):
    settings = {
        "api_key": "",
        "server_url": "http://127.0.0.1:8000",
        "raw": {},
    }
    with mock.patch("bal.backends.omlx.load_settings", return_value=settings):
        return OmlxBackend(model_name)


class InitSessionTests(unittest.TestCase):
    def test_create_backend_returns_selected_backend(self):
        self.assertIsInstance(create_backend("ollama", "llama3"), OllamaBackend)

        settings = {
            "api_key": "",
            "server_url": "http://127.0.0.1:8000",
            "raw": {},
        }
        with mock.patch("bal.backends.omlx.load_settings", return_value=settings):
            self.assertIsInstance(create_backend("omlx", "qwen"), OmlxBackend)

    def test_init_session_starts_registers_cleanup_then_preloads(self):
        fake = FakeBackend("Qwen")
        events = []

        def register(func):
            events.append(("register", func))

        def preload():
            events.append(("preload", None))
            fake.calls.append("preload")

        fake.preload_model = preload

        with (
            mock.patch.object(cli, "create_backend", return_value=fake),
            mock.patch.object(cli.atexit, "register", side_effect=register),
            redirect_stdout(io.StringIO()),
        ):
            session = cli.init_session("ollama", "Qwen", dry_run=False)

        self.assertIs(session, fake)
        self.assertEqual(fake.calls, ["start", "preload"])
        self.assertEqual(events[0], ("register", fake.cleanup))
        self.assertEqual(events[1], ("preload", None))

    def test_init_session_dry_run_skips_preload(self):
        fake = FakeBackend("Qwen")

        with (
            mock.patch.object(cli, "create_backend", return_value=fake),
            mock.patch.object(cli.atexit, "register"),
            redirect_stdout(io.StringIO()),
        ):
            session = cli.init_session("omlx", "Qwen", model_dir="/models", dry_run=True)

        self.assertIs(session, fake)
        self.assertEqual(fake.calls, ["start"])


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


class AgentExecTests(unittest.TestCase):
    def test_ollama_agent_exec_uses_ollama_launch_command(self):
        backend = OllamaBackend("llama3")
        with mock.patch("bal.backends.ollama.os.execvp") as execvp:
            backend.exec_agent("claude", "llama3")

        execvp.assert_called_once_with(
            "ollama",
            ["ollama", "launch", "claude", "--model", "llama3"],
        )

    def test_omlx_codex_exec_uses_provider_config_and_api_key(self):
        settings = {
            "api_key": "secret",
            "server_url": "http://127.0.0.1:8000",
            "raw": {},
        }
        with mock.patch("bal.backends.omlx.os.execvpe") as execvpe:
            with mock.patch("bal.backends.omlx.load_settings", return_value=settings):
                backend = OmlxBackend("qwen")
            backend.exec_agent("codex", "qwen")

        binary, cmd, env = execvpe.call_args.args
        self.assertEqual(binary, "codex")
        self.assertEqual(
            cmd,
            ["codex", "-c", 'model_provider="omlx"', "-c", 'model="qwen"'],
        )
        self.assertEqual(env["OMLX_API_KEY"], "secret")


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
