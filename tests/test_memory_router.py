"""Tests de modules/memory_router.py — frases explícitas y señuelos."""

import unittest

from modules.memory import MemoryStore, set_store
from modules.memory_router import match_memory_route


class TestMemoryRouter(unittest.TestCase):
    def test_recuerda_hecho(self):
        route = match_memory_route("recuerda que mi proyecto principal es Limits")
        self.assertEqual(route["action"], "remember")
        self.assertEqual(route["params"]["key"], "mi proyecto principal")
        self.assertEqual(route["params"]["value"], "Limits")

    def test_acuérdate_de_que(self):
        route = match_memory_route("acuérdate de que el wifi se cae los martes")
        self.assertEqual(route["action"], "remember")
        self.assertEqual(route["params"]["key"], "")
        self.assertEqual(route["params"]["value"], "el wifi se cae los martes")

    def test_apunta_nota(self):
        route = match_memory_route("apunta que la reunión es el lunes a las 9")
        self.assertEqual(route["action"], "remember")
        self.assertEqual(route["params"]["key"], "la reunión")
        self.assertIn("lunes", route["params"]["value"])

    def test_recuerda_sin_que_no_guarda(self):
        # «recuerda apagar la luz» es un recordatorio, no un hecho.
        self.assertIsNone(match_memory_route("recuerda apagar la luz"))

    def test_olvida(self):
        route = match_memory_route("olvida mi proyecto principal")
        self.assertEqual(route["action"], "forget")
        self.assertEqual(route["params"]["key"], "mi proyecto principal")

    def test_qué_sabes_de_mí(self):
        for frase in ("¿qué sabes de mí?", "¿qué recuerdas?", "qué tienes apuntado",
                      "muéstrame tu memoria"):
            route = match_memory_route(frase)
            self.assertIsNotNone(route, frase)
            self.assertEqual(route["action"], "memory_list", frase)

    def test_qué_sabes_sobre_algo(self):
        route = match_memory_route("¿qué sabes de mi proyecto?")
        self.assertEqual(route["action"], "memory_recall")
        self.assertEqual(route["params"]["query"], "mi proyecto")

    def test_cuál_es_mi_dato(self):
        route = match_memory_route("¿cuál es mi proyecto principal?")
        self.assertEqual(route["action"], "memory_recall")
        self.assertEqual(route["params"]["query"], "proyecto principal")
        route = match_memory_route("cuáles son mis lenguajes favoritos")
        self.assertEqual(route["params"]["query"], "lenguajes favoritos")

    def test_no_secuestra_otras_ordenes(self):
        for frase in ("abre spotify", "¿qué hora es?", "lista la carpeta work",
                      "investiga sobre la memoria ram", "olvida eso y abre steam"):
            route = match_memory_route(frase)
            if frase == "olvida eso y abre steam":
                self.assertIsNotNone(route)  # empieza por «olvida»; el executor avisa
            else:
                self.assertIsNone(route, frase)


class TestRouterExecutor(unittest.TestCase):
    """Integración router → executor con un store en memoria."""

    def setUp(self):
        self.store = MemoryStore(":memory:")
        set_store(self.store)
        from modules.executor import CommandExecutor
        self.ex = CommandExecutor()

    def tearDown(self):
        set_store(None)
        self.store.close()

    def _run(self, frase):
        route = match_memory_route(frase)
        self.assertIsNotNone(route, frase)
        return self.ex.execute(route)

    def test_ciclo_completo(self):
        self.assertIn("Anotado", self._run("recuerda que mi proyecto principal es Limits"))
        self.assertIn("Limits", self._run("¿qué sabes de mí?"))
        self.assertIn("Limits", self._run("¿qué sabes de mi proyecto?"))
        self.assertIn("Limits", self._run("¿cuál es mi proyecto principal?"))
        self.assertIn("Olvidado", self._run("olvida mi proyecto principal"))
        self.assertIn("Todavía no sé nada", self._run("¿qué sabes de mí?"))

    def test_olvidar_inexistente(self):
        self.assertIn("No tenía nada", self._run("olvida la luna"))

    def test_nota_libre_se_lista(self):
        self._run("apunta que el wifi se cae los martes")
        self.assertIn("wifi", self._run("¿qué sabes de mí?"))


if __name__ == "__main__":
    unittest.main()
