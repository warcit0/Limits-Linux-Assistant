"""Tests del mapa del equipo inyectado en el system prompt."""

import tempfile
import unittest
from pathlib import Path

from modules.machine_map import build_machine_map


class TestMachineMap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        for name in ("Proyectos", "Work", "Descargas", "Documentos"):
            (self.home / name).mkdir()
        (self.home / "Proyectos" / "Limits").mkdir()
        (self.home / "Proyectos" / "Nolimitz").mkdir()
        (self.home / "Work" / "Treecodes").mkdir()
        (self.home / ".config").mkdir()
        (self.home / "snap").mkdir()
        (self.home / "nota.txt").write_text("x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_incluye_rutas_reales_y_hijos(self):
        m = build_machine_map(home=self.home)
        self.assertIn("~/Proyectos: Limits, Nolimitz", m)
        self.assertIn("~/Work: Treecodes", m)
        self.assertIn("Documentos", m.splitlines()[0])

    def test_no_incluye_ruido_ni_archivos(self):
        m = build_machine_map(home=self.home)
        self.assertNotIn(".config", m)
        self.assertNotIn("snap", m)
        self.assertNotIn("nota.txt", m)

    def test_presupuesto_respetado(self):
        for i in range(40):
            (self.home / "Proyectos" / f"proyecto-largo-{i}").mkdir()
        m = build_machine_map(home=self.home, budget=120)
        self.assertLessEqual(len(m), 120)
        self.assertTrue(m.endswith("…"))

    def test_carpetas_importantes_sobreviven_al_recorte(self):
        for i in range(30):
            (self.home / f"a{ i:02d}").mkdir()
        m = build_machine_map(home=self.home, top_max=4)
        self.assertIn("Proyectos", m)
        self.assertIn("Work", m)

    def test_home_inexistente_devuelve_vacio(self):
        self.assertEqual(build_machine_map(home=self.home / "nope"), "")


if __name__ == "__main__":
    unittest.main()
