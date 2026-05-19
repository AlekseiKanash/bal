# Coding Guide

## Language and dependencies

- Python 3
- Third-party packages: `psutil` (system metrics), `simple-term-menu` (interactive picker). Install via `pip install -r requirements.txt`.
- Additional packages require developer approval before installation

## Style

- PEP 8, max line length 120 characters
- Spaces, not tabs
- No magic numbers — use named constants or parameters with defaults
- No global variables declared inside functions or methods
- Keep functions/methods to 20–30 lines; up to 40–50 only when extraction would cost more than it saves

## Design

- Prefer reuse over duplication
- Code and documentation should be readable by both humans and LLMs — keep it clear

See [coding_philosophy.md](coding_philosophy.md) for design rules with LLM-reviewable detection signals.
