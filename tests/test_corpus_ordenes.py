"""Valida el corpus offline: cada action esperada existe en el action_map."""

import json
import unittest
from pathlib import Path

from modules.executor import CommandExecutor

CORPUS = Path(__file__).resolve().parent / "corpus_ordenes.json"

# confirm/cancel se resuelven en execute() antes del map; el corpus las incluye
SPECIAL = {"confirm", "cancel"}
MIN_CORPUS = 25


class TestCorpusOrdenes(unittest.TestCase):
    def test_actions_existen_en_executor(self):
        data = json.loads(CORPUS.read_text(encoding="utf-8"))
        self.assertGreaterEqual(
            len(data), MIN_CORPUS,
            f"Corpus debe tener ≥{MIN_CORPUS} frases (plan 4)",
        )
        ex = CommandExecutor()
        known = set(ex.action_map) | SPECIAL
        for item in data:
            self.assertIn(
                item["action"], known,
                f"Corpus action desconocida: {item['action']} ({item['phrase']})",
            )
            self.assertTrue(item["phrase"].strip())

    def test_prompt_renderizado_bajo_limite(self):
        """El prompt que ve el LLM incluye el mapa del equipo: ~7KB como mucho."""
        import os
        from modules.machine_map import build_machine_map

        prompt = (Path(__file__).resolve().parents[1]
                  / "prompts" / "system_prompt.txt")
        raw = prompt.read_text(encoding="utf-8")
        from modules.clock import now_line
        memoria = "- nota: " + "x" * 580  # tope del bloque {memory} (~600 B)
        rendered = (raw.replace("{username}", os.getenv("USER", "usuario"))
                       .replace("{machine_map}", build_machine_map())
                       .replace("{now}", now_line())
                       .replace("{memory}", memoria))
        self.assertLessEqual(
            len(rendered.encode("utf-8")), 8400,
            f"prompt renderizado={len(rendered)}B supera ~8.4KB "
            "(7.8KB base + 600B de memoria); dietar few-shots",
        )
        self.assertNotIn("{machine_map}", rendered)
        self.assertNotIn("{now}", rendered)
        self.assertNotIn("{memory}", rendered)
        if (Path.home() / "Proyectos").is_dir():
            self.assertIn("~/Proyectos", rendered)


if __name__ == "__main__":
    unittest.main()
