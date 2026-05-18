import json
import urllib.request
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ModelChoice:
    """An available model in the interactive selection menu."""
    name: str
    backend: str
    version: str
    display: str


class Backend(Protocol):
    backend_name: str

    @property
    def model_name(self) -> str:
        ...

    @property
    def version(self) -> str | None:
        ...

    def start(self) -> None:
        ...

    def preload_model(self) -> None:
        ...

    def cleanup(self) -> None:
        ...

    def launch_command(self, agent: str) -> str:
        ...

    def resolve_model(self, model_arg: str | None) -> str | None:
        ...

    def exec_agent(self, agent: str, model: str | None) -> None:
        ...


def http_get(path, base_url, timeout=5, headers=None):
    req = urllib.request.Request(base_url + path, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()


def http_post(path, payload, base_url, timeout=30):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)
