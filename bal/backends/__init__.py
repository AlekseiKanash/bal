from .base import ModelChoice
from .manager import BackendManager
from .ollama import OllamaBackend
from .omlx import OmlxBackend

backends_manager = BackendManager()
