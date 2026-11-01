"""Aísla el entorno de unittest antes de importar los módulos de la suite."""

import atexit
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config

_entorno = tempfile.TemporaryDirectory(prefix="limits-suite-")
atexit.register(_entorno.cleanup)
Config.AGENT_MODE = "legacy"
Config.SPOTIFY_MCP_ENABLED = False
Config.AGENT_COHERENT = False
Config.AGENT_SEMANTIC = False
Config.KNOWLEDGE_ENABLED = False
Config.MEMORY_PATH = ":memory:"
Config.AGENT_TASK_PATH = str(Path(_entorno.name) / "tareas")
Config.LOG_PATH = str(Path(_entorno.name) / "limits.log")
_original = unittest.TestCase.run


def _aislar(self, result=None):
    from modules import memory

    with (
        tempfile.TemporaryDirectory(prefix="limits-prueba-") as carpeta,
        patch.object(Config, "MEMORY_PATH", ":memory:"),
        patch.object(Config, "AGENT_TASK_PATH", str(Path(carpeta) / "tareas")),
    ):
        anterior = memory._default_store
        store = memory.MemoryStore(":memory:")
        memory.set_store(store)
        try:
            return _original(self, result)
        finally:
            actual = memory._default_store
            if actual is not None and actual is not anterior:
                actual.close()
            store.close()
            memory.set_store(anterior)


unittest.TestCase.run = _aislar
