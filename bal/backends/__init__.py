from .base import ModelChoice
from .ollama import OllamaBackend
from . import ollama
from .omlx import OmlxBackend
from . import omlx


def create_backend(backend, model_name, model_dir=None):
    if backend == "omlx":
        return OmlxBackend(model_name or "(none)", model_dir=model_dir)
    return OllamaBackend(model_name or "(none)")


def detect_running_backend():
    if omlx.is_server_running():
        return OmlxBackend("(none)")
    if ollama.is_server_running():
        return OllamaBackend("(none)")
    return None


def fetch_ollama_models():
    return ollama.fetch_models()


def fetch_omlx_models():
    return omlx.fetch_models()


def list_available_models():
    models = fetch_ollama_models() + fetch_omlx_models()
    if models:
        return models
    for name in ollama.scan_models() or []:
        tag = name.split(":")[-1] if ":" in name else ""
        models.append(ModelChoice(name=name, backend="ollama", version=tag,
                                  display=f"ollama {name}"))
    for name in omlx.scan_models() or []:
        models.append(ModelChoice(name=name, backend="omlx", version="",
                                  display=f"omlx {name}"))
    return models


def find_backend_model_matches(model_name):
    matching = []
    for m in fetch_ollama_models():
        if model_name in m.name or m.name in model_name:
            matching.append((m.backend, m.name))
    for m in fetch_omlx_models():
        if model_name in m.name or m.name in model_name:
            matching.append((m.backend, m.name))
    return matching


def scan_local_models_by_backend():
    return {
        "ollama": ollama.scan_models(),
        "omlx": omlx.scan_models(),
    }


def local_model_dirs():
    return {
        "ollama": "~/.ollama/models/manifests",
        "omlx": omlx.default_model_dir(),
    }
