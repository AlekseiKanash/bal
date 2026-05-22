from .base import backends, ModelChoice
from .ollama import OllamaBackend
from .omlx import OmlxBackend
from .manager import BackendManager

backends_manager = BackendManager()
