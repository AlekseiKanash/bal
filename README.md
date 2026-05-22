# bal — LLM Backend Launcher

Start a local LLM session with one command. `bal` manages the server lifecycle (ollama or omlx), preloads your model, and shows a live CPU/GPU/RAM stats UI in the terminal. A second `bal` command in another terminal launches an AI coding agent pointed at the running backend.

## Requirements

- Python 3.11+
- [ollama](https://ollama.com) and/or [omlx](https://github.com/jundot/omlx) installed and on PATH

Python dependencies (`psutil`, `simple-term-menu`) are installed automatically by `install.sh`.

## Installation

```bash
git clone https://github.com/akanash/bal
cd bal
./install.sh
```

Add `~/.local/bin` to your PATH if it isn't already:

```bash
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.zshrc to make permanent
```

## Usage

**Terminal 1 — start server and load model**

```bash
bal                                      # interactive model picker (any backend)
bal --select                             # same as bare invocation
bal --model Qwen3                        # ollama (default backend)
bal --model Qwen3 --backend omlx         # omlx backend
bal --model Qwen3 --dry-run              # start UI without loading the model
```

**Terminal 2 — launch an agent against the running backend**

```bash
bal claude            # auto-detect backend, use currently loaded model
bal claude Qwen3      # explicit model name
bal codex             # OpenAI Codex CLI
bal opencode
bal openclaw
```

If a model name exists on more than one backend, `bal` prompts you to pick which one to use.

**Other**

```bash
bal list              # show available models on disk (no server needed)
bal --version
bal --help
```

## Backends

| Backend | URL | Behaviour |
|---|---|---|
| `ollama` (default) | `http://localhost:11434` | Started automatically if not running |
| `omlx` | `http://localhost:8000` | Attaches to existing server; config read from `~/.omlx/settings.json` |

## Agents

| Agent | Command |
|---|---|
| `claude` | Claude Code |
| `codex` | OpenAI Codex CLI |
| `opencode` | opencode |
| `openclaw` | openclaw |

When using omlx, each agent is launched with the backend URL and API key from `~/.omlx/settings.json` so no manual environment setup is needed.

## Options

```
positional:
  command                 list | claude | codex | opencode | openclaw
  model                   model name for agent commands (optional)

server options:
  --model <name>          model to load (required unless --dry-run or --select)
  --backend ollama|omlx   backend to use (default: ollama)
  --model-dir <path>      model directory (omlx only)
  --dry-run               start server and UI without loading a model
  --select                open the interactive model picker

other:
  --version               print version and exit
  --help                  show help and exit
```

Bare `bal` (no command, no `--model`) opens the interactive model picker.

## Homebrew

Coming soon. Formula is in `Formula/bal.rb`.

## Documentation

See [`docs/spec.md`](docs/spec.md) for architecture, startup sequence, and termination behaviour. Per-component references are in [`docs/backends.md`](docs/backends.md), [`docs/session_header.md`](docs/session_header.md), [`docs/meter.md`](docs/meter.md), [`docs/horizontal_text.md`](docs/horizontal_text.md), and [`docs/border.md`](docs/border.md).
