"""Valida el corpus offline: cada action esperada existe en el action_map."""

import json
import unittest
from pathlib import Path

from modules.executor import CommandExecutor

CORPUS = Path(__file__).resolve().parent / "corpus_ordenes.json"

# confirm/cancel se resuelven en execute() antes del map; el corpus las incluye
SPECIAL = {"confirm", "cancel"}


class TestCorpusOrdenes(unittest.TestCase):
    def test_actions_existen_en_executor(self):
        data = json.loads(CORPUS.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data), 10)
        ex = CommandExecutor()
        known = set(ex.action_map) | SPECIAL
        for item in data:
            self.assertIn(
                item["action"], known,
                f"Corpus action desconocida: {item['action']} ({item['phrase']})",
            )
            self.assertTrue(item["phrase"].strip())


if __name__ == "__main__":
    unittest.main()
