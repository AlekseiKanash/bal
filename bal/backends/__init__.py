from .base import backends, ModelChoice
from .ollama import OllamaBackend
from .omlx import OmlxBackend


def create_backend(backend, model_name, model_dir=None):
    for cls in backends:
        if cls.backend_name == backend:
            return cls(model_name or "(none)", model_dir=model_dir)
    raise ValueError(f"Unknown backend: {backend}")


def detect_running_backend():
    for cls in backends:
        if cls.is_server_running():
            return cls.backend_name
    return None


def list_available_models():
    models = []
    for cls in backends:
        models.extend(cls.fetch_models())
    if models:
        return models
    for cls in backends:
        for name in cls.scan_models() or []:
            tag = name.split(":")[-1] if ":" in name else ""
            models.append(ModelChoice(name=name, backend=cls.backend_name, version=tag,
                                      display=f"{cls.backend_name} {name}"))
    return models


def find_backend_model_matches(model_name):
    all_models = list_available_models()
    return [
        (m.backend, m.name)
        for m in all_models
        if model_name in m.name or m.name in model_name
    ]


def scan_local_models_by_backend():
    return {cls.backend_name: cls.scan_models() for cls in backends}


def local_model_dirs():
    return {cls.backend_name: cls.model_dir() for cls in backends}
