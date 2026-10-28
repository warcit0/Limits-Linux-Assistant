"""Tests de modules/memory.py — CRUD, FTS, presupuesto, redacción y fallos."""

import os
import tempfile
import unittest
from pathlib import Path

from modules.memory import MemoryStore, normalize_key, redact


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_recuerda_y_lee(self):
        msg = self.store.remember("mi proyecto principal", "Limits")
        self.assertIn("Anotado", msg)
        facts = self.store.list_facts()
        self.assertEqual(facts[0]["key"], "proyecto_principal")
        self.assertEqual(facts[0]["value"], "Limits")

    def test_upsert_guarda_historial(self):
        self.store.remember("proyecto principal", "Limits")
        self.store.remember("proyecto principal", "gemdev")
        facts = self.store.list_facts()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["value"], "gemdev")
        row = self.store._conn.execute(
            "SELECT old_value, new_value FROM fact_history").fetchone()
        self.assertEqual(tuple(row), ("Limits", "gemdev"))

    def test_nota_sin_clave(self):
        self.store.remember("", "el wifi se cae los martes")
        facts = self.store.list_facts()
        self.assertTrue(facts[0]["key"].startswith("nota_"))

    def test_recall_ignora_acentos(self):
        self.store.remember("musica favorita", "música de cámara")
        self.assertEqual(len(self.store.recall("musica")), 1)
        self.assertEqual(len(self.store.recall("música")), 1)

    def test_recall_sin_resultados(self):
        self.assertEqual(self.store.recall("no existe"), [])

    def test_forget_exacto_y_parcial(self):
        self.store.remember("proyecto principal", "Limits")
        self.assertTrue(self.store.forget("proyecto principal"))
        self.assertEqual(self.store.list_facts(), [])
        self.store.remember("proyecto principal", "Limits")
        self.assertTrue(self.store.forget("proyecto"))
        self.assertFalse(self.store.forget("inexistente"))

    def test_facts_block_respeta_presupuesto_sin_cortar(self):
        for i in range(30):
            self.store.remember(f"dato numero {i}", "x" * 40)
        block = self.store.facts_block(max_bytes=600)
        self.assertLessEqual(len(block.encode("utf-8")), 600)
        self.assertTrue(block.startswith("- "))
        for line in block.splitlines():
            self.assertTrue(line.startswith("- "))
            self.assertIn(": ", line)

    def test_facts_block_vacio(self):
        self.assertEqual(self.store.facts_block(), "")

    def test_redaccion_de_secretos(self):
        self.store.remember("token groq", "gsk_abcdef1234567890")
        value = self.store.list_facts()[0]["value"]
        self.assertNotIn("gsk_", value)
        self.assertIn("[redactado]", value)

    def test_redaccion_utilidades(self):
        self.assertEqual(redact("Bearer abcdef123456789"), "[redactado]")
        self.assertEqual(redact("ghp_" + "a" * 30), "[redactado]")
        self.assertEqual(redact("hola"), "hola")

    def test_normalize_key(self):
        self.assertEqual(normalize_key("Mi Proyecto Principal"), "proyecto_principal")
        self.assertEqual(normalize_key("el wifi de casa"), "wifi_de_casa")
        self.assertEqual(normalize_key("  "), "")

    def test_episodios(self):
        self.store.log_turn("user", "hola", intent="x")
        self.store.log_turn("assistant", "buenas")
        turns = self.store.recent_turns(6)
        self.assertEqual([t["role"] for t in turns], ["user", "assistant"])
        self.assertEqual(turns[0]["text"], "hola")

    def test_episodios_no_guardan_vacio(self):
        self.store.log_turn("user", "")
        self.assertEqual(self.store.stats()["episodes"], 0)

    def test_stats(self):
        self.store.remember("a", "b")
        self.store.log_turn("user", "hola")
        stats = self.store.stats()
        self.assertTrue(stats["enabled"])
        self.assertEqual(stats["facts"], 1)
        self.assertEqual(stats["episodes"], 1)


class TestPersistencia(unittest.TestCase):
    def test_sobrevive_al_cierre(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.db"
            store = MemoryStore(path)
            store.remember("proyecto principal", "Limits")
            store.close()

            again = MemoryStore(path)
            self.assertEqual(again.list_facts()[0]["value"], "Limits")
            again.close()

    def test_permisos_600(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.db"
            store = MemoryStore(path)
            store.close()
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class TestDegradacion(unittest.TestCase):
    def test_db_corrupta_no_revienta(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.db"
            path.write_bytes(b"esto no es sqlite" * 100)
            store = MemoryStore(path)
            self.assertFalse(store.enabled)
            self.assertIn("desactivada", store.remember("a", "b"))
            self.assertEqual(store.recall("a"), [])
            self.assertEqual(store.facts_block(), "")
            self.assertEqual(store.recent_turns(), [])
            self.assertFalse(store.forget("a"))
            self.assertEqual(store.list_facts(), [])
            store.close()

    def test_deshabilitada_explicitamente(self):
        store = MemoryStore(":memory:", enabled=False)
        self.assertFalse(store.enabled)
        self.assertEqual(store.stats()["facts"], 0)

    def test_ruta_sin_permisos(self):
        store = MemoryStore("/proc/no-se-puede/memory.db")
        self.assertFalse(store.enabled)
        self.assertIn("desactivada", store.remember("a", "b"))


if __name__ == "__main__":
    unittest.main()
