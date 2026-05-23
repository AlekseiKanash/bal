from .base import Backend, ModelChoice


class BackendManager:
    backends: list[type["Backend"]] = []

    @classmethod
    def register(cls, backend_cls: type["Backend"]) -> type["Backend"]:
        cls.backends.append(backend_cls)
        return backend_cls

    @classmethod
    def create_backend(cls, backend, model_name, model_dir=None):
        for backend_cls in cls.backends:
            if backend_cls.backend_name == backend:
                return backend_cls(model_name or "(none)", model_dir=model_dir)
        raise ValueError(f"Unknown backend: {backend}")

    @classmethod
    def detect_running_backend(cls):
        for backend_cls in cls.backends:
            if backend_cls.is_server_running():
                return backend_cls.backend_name
        return None

    @classmethod
    def list_available_models(cls):
        models = []
        for backend_cls in cls.backends:
            live = backend_cls.fetch_models()
            if live:
                models.extend(live)
                continue
            for name in backend_cls.scan_models() or []:
                tag = name.split(":")[-1] if ":" in name else ""
                models.append(ModelChoice(
                    name=name, backend=backend_cls.backend_name, version=tag,
                    display=f"{backend_cls.backend_name} {name}",
                ))
        return models

    @classmethod
    def find_backend_model_matches(cls, model_name):
        all_models = cls.list_available_models()
        return [
            (m.backend, m.name)
            for m in all_models
            if model_name in m.name or m.name in model_name
        ]

    @classmethod
    def scan_local_models_by_backend(cls):
        return {backend_cls.backend_name: backend_cls.scan_models() for backend_cls in cls.backends}

    @classmethod
    def local_model_dirs(cls):
        return {backend_cls.backend_name: backend_cls.model_dir() for backend_cls in cls.backends}
