"""Tests del lane compuesto desktop_task (LLM mockeado, sin Ollama)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from commands.files import FileCommands
from modules.desktop_agent import (
    DesktopAgent,
    _extract_json,
    match_desktop_task_route,
)
from modules.executor import CommandExecutor


class TestMatchDesktopRoute(unittest.TestCase):
    def test_busca_y_copia(self):
        t = "busca el PDF de impuestos en Descargas y cópialo al escritorio"
        self.assertEqual(match_desktop_task_route(t), t)

    def test_busca_y_abre_no_es_compuesto(self):
        # Atómico search_and_open — no bypass
        self.assertIsNone(match_desktop_task_route("busca main.py y ábrelo"))

    def test_volumen_no_rutea(self):
        self.assertIsNone(match_desktop_task_route("sube el volumen al 70"))


class TestExtractJson(unittest.TestCase):
    def test_json_limpio(self):
        self.assertEqual(
            _extract_json('{"tool":"done","args":{"message":"ok"}}')["tool"],
            "done",
        )

    def test_con_fence(self):
        raw = '```json\n{"tool":"ask_user","args":{"question":"¿Cuál?"}}\n```'
        self.assertEqual(_extract_json(raw)["tool"], "ask_user")


class TestDesktopAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "foto.png").write_text("img")
        self.files = FileCommands()
        self.pending = []

        def setter(action, params, response):
            self.pending.append((action, params, response))

        self.plan_queue = []

        def fake_llm(_messages):
            return self.plan_queue.pop(0) if self.plan_queue else None

        self.agent = DesktopAgent(
            files=self.files,
            pending_setter=setter,
            llm_callable=fake_llm,
            max_steps=5,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_done_inmediato(self):
        self.plan_queue = [
            {"tool": "done", "args": {"message": "Nada que hacer."}},
        ]
        out = self.agent.run("no hagas nada")
        self.assertEqual(out, "Nada que hacer.")

    def test_search_and_open_loop(self):
        self.plan_queue = [
            {"tool": "search_and_open",
             "args": {"name": "foto.png", "path": str(self.root)}},
            {"tool": "done", "args": {"message": "Abierto."}},
        ]
        with mock.patch.object(self.files, "open_file",
                               return_value="Abriendo mock."):
            out = self.agent.run(f"abre foto.png en {self.root}")
        self.assertEqual(out, "Abierto.")

    def test_propose_move_deja_pending(self):
        src = str(self.root / "foto.png")
        dst = str(self.root / "foto2.png")
        self.plan_queue = [
            {"tool": "propose_move",
             "args": {"source": src, "destination": dst}},
        ]
        out = self.agent.run("mueve la foto")
        self.assertIn("Confirmas", out)
        self.assertEqual(len(self.pending), 1)
        self.assertEqual(self.pending[0][0], "move_file")

    def test_ask_user(self):
        self.plan_queue = [
            {"tool": "ask_user", "args": {"question": "¿Cuál de los dos?"}},
        ]
        self.assertEqual(self.agent.run("algo ambiguo"), "¿Cuál de los dos?")

    def test_tool_desconocida_luego_done(self):
        self.plan_queue = [
            {"tool": "rm_rf", "args": {}},
            {"tool": "done", "args": {"message": "Aborté."}},
        ]
        out = self.agent.run("borra todo")
        self.assertEqual(out, "Aborté.")


class TestExecutorDesktopTask(unittest.TestCase):
    def test_desktop_task_en_action_map(self):
        ex = CommandExecutor()
        self.assertIn("desktop_task", ex.action_map)
        self.assertIn("search_and_open", ex.action_map)
        self.assertIn("reveal_file", ex.action_map)

    def test_desktop_task_usa_agent(self):
        ex = CommandExecutor()
        ex.desktop_agent._llm_callable = lambda _m: {
            "tool": "done", "args": {"message": "Hecho por agent."}
        }
        out = ex.execute({
            "action": "desktop_task",
            "params": {"goal": "lista algo"},
            "response": "Voy.",
            "confidence": 0.95,
        })
        self.assertIn("Hecho por agent", out)


if __name__ == "__main__":
    unittest.main()
