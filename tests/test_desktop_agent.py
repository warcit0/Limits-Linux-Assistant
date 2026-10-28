"""Tests del lane compuesto desktop_task (OpenCode mock + guards)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from commands.files import FileCommands
from modules.desktop_agent import (
    DesktopAgent,
    _extract_json,
    _normalize_opencode_model,
    match_desktop_task_route,
)
from modules.executor import CommandExecutor


class TestMatchDesktopRoute(unittest.TestCase):
    def test_busca_y_copia(self):
        t = "busca el PDF de impuestos en Descargas y cópialo al escritorio"
        self.assertEqual(match_desktop_task_route(t), t)

    def test_busca_y_abre_no_es_compuesto(self):
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

    def test_normalize_model(self):
        self.assertEqual(
            _normalize_opencode_model("opencode/deepseek-v4.1-flash-free"),
            "deepseek-v4.1-flash-free",
        )
        self.assertEqual(
            _normalize_opencode_model("deepseek-v4.1-flash-free"),
            "deepseek-v4.1-flash-free",
        )


class TestDesktopAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "foto.png").write_text("img")
        self.files = FileCommands(search_roots=str(self.root))
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
            provider="ollama",
            fallback="off",
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

    def test_path_guard_bloquea_open_sin_search(self):
        fake = str(self.root / "inventado.pdf")
        self.plan_queue = [
            {"tool": "open_file", "args": {"path": fake}},
            {"tool": "done", "args": {"message": "No abrí."}},
        ]
        with mock.patch.object(self.files, "open_file") as opener:
            out = self.agent.run("abre inventado")
        opener.assert_not_called()
        self.assertEqual(out, "No abrí.")


class TestOpenCodeClient(unittest.TestCase):
    def test_query_opencode_ok(self):
        agent = DesktopAgent(
            files=FileCommands(),
            provider="opencode",
            opencode_api_key="test-key",
            opencode_model="opencode/deepseek-v4.1-flash-free",
            fallback="off",
        )
        fake_body = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "tool": "done",
                        "args": {"message": "Desde OpenCode."},
                    }),
                },
            }],
        }
        with mock.patch("modules.desktop_agent.requests.post") as post:
            post.return_value = mock.Mock(
                status_code=200,
                json=lambda: fake_body,
            )
            out = agent.run("cualquier cosa")
        self.assertEqual(out, "Desde OpenCode.")
        args, kwargs = post.call_args
        self.assertIn("/chat/completions", args[0])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(kwargs["json"]["model"], "deepseek-v4.1-flash-free")

    def test_fallback_a_ollama_tras_fallo_opencode(self):
        calls = {"n": 0}

        def fake_post(url, **kwargs):
            calls["n"] += 1
            m = mock.Mock()
            if "opencode.ai" in url or "chat/completions" in url:
                m.status_code = 429
                m.json.return_value = {}
                return m
            # Ollama
            m.status_code = 200
            m.json.return_value = {
                "message": {
                    "content": json.dumps({
                        "tool": "done",
                        "args": {"message": "Via Ollama."},
                    }),
                },
            }
            return m

        agent = DesktopAgent(
            files=FileCommands(),
            provider="opencode",
            opencode_api_key="test-key",
            fallback="ollama",
            ollama_model="qwen2.5:3b-instruct",
        )
        with mock.patch("modules.desktop_agent.requests.post", side_effect=fake_post):
            out = agent.run("tarea")
        self.assertEqual(out, "Via Ollama.")
        self.assertGreaterEqual(calls["n"], 2)


class TestExecutorDesktopTask(unittest.TestCase):
    def test_desktop_task_en_action_map(self):
        ex = CommandExecutor()
        self.assertIn("desktop_task", ex.action_map)
        self.assertIn("open_last", ex.action_map)

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
