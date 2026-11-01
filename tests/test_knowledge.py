"""Memoria real en SQLite/Markdown: persistencia, conflictos y fallos del disco."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from modules.knowledge import Conocimiento
from modules.memory import MemoryStore


class TestConocimiento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "memory.db"
        self.vault = Path(self.tmp.name) / "vault"
        self.k = Conocimiento(self.db, self.vault)
        self.addCleanup(self.k.close)
        self.store = MemoryStore(self.db)
        self.addCleanup(self.store.close)

    def nota(self, id_):
        return next(self.vault.rglob(id_ + ".md"))

    def test_hechos_se_exportan_y_ediciones_regresan_a_sqlite(self):
        self.store.remember("editor", "code")
        r = self.k.recuperar("editor")[0]
        p = self.nota(r["id"])
        p.write_text(p.read_text().replace("\ncode\n", "\nvscodium\n"))
        self.assertEqual(self.k.recuperar("editor")[0]["body"], "vscodium")
        self.assertEqual(self.store.recall("editor")[0]["value"], "vscodium")
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_olvidar_no_resucita_copias_viejas_ni_procedimientos(self):
        self.store.remember("editor", "vscodium")
        self.k.registrar_resultado(
            "abre vscodium",
            [{"accion": "open_application", "ok": True, "verificado": True}], completado=True,
        )
        r = self.k.recuperar("editor")[0]
        p = self.nota(r["id"])
        viejo = p.read_text()
        self.assertTrue(self.store.forget("editor"))
        self.k.sincronizar()
        (self.vault / "Preferencias" / "copia.md").write_text(viejo)
        self.assertEqual(self.k.recuperar("vscodium"), [])
        self.assertFalse(p.exists())
        self.assertTrue((self.vault / "Preferencias" / "copia.md").exists())

    def test_eliminar_markdown_olvida_el_hecho(self):
        self.store.remember("ciudad", "Cartago")
        r = self.k.recuperar("ciudad")[0]
        self.nota(r["id"]).unlink()
        self.assertEqual(self.k.recuperar("ciudad"), [])
        self.assertEqual(self.store.recall("ciudad"), [])

    def test_conflicto_no_sobrescribe_edicion_humana(self):
        id_ = self.k.guardar("Decisiones", "motor", "piper")
        self.k.sincronizar()
        p = self.nota(id_)
        p.write_text(p.read_text().replace("piper", "otro"))
        self.k.guardar("Decisiones", "motor", "actualizado", id_=id_)
        self.k.sincronizar()
        self.assertIn("otro", p.read_text())
        self.assertEqual(self.k.recuperar("motor"), [])
        self.assertTrue(list((self.vault / "Pendientes-de-validar").glob("*.md")))

    def test_candidatos_caducados_y_secretos_no_contaminan_contexto(self):
        self.k.guardar(
            "Pendientes-de-validar",
            "preferencia",
            "favorito bachata",
            estado="pendiente",
        )
        self.k.guardar("Entorno", "volumen", "volumen 50", vence=1)
        self.k.guardar("Entorno", "token", "nvapi-" + ("A" * 40))
        self.assertEqual(self.k.recuperar("bachata"), [])
        self.assertEqual(self.k.recuperar("volumen"), [])
        self.assertNotIn("A" * 40, self.k.recuperar("token")[0]["body"])

    def test_recuperacion_tras_fallo_exportacion_y_reinicio(self):
        id_ = self.k.guardar("Entorno", "proyecto", "proyecto ejemplo Python")
        with mock.patch.object(self.k, "_escribir", side_effect=OSError("disco")):
            self.k.sincronizar()
        self.assertEqual(
            self.k.conn.execute(
                "SELECT dirty FROM knowledge WHERE id=?", (id_,)
            ).fetchone()[0],
            1,
        )
        self.k.close()
        self.k = Conocimiento(self.db, self.vault)
        self.addCleanup(self.k.close)
        self.assertEqual(self.k.recuperar("Python")[0]["id"], id_)
        self.assertTrue(self.nota(id_).is_file())

    def test_edicion_nueva_y_confirmacion_humana_de_candidato(self):
        (self.vault / "Preferencias" / "editor.md").write_text(
            "Uso Code para proyectos Python"
        )
        self.assertTrue(self.k.recuperar("Python"))
        id_ = self.k.guardar(
            "Pendientes-de-validar", "género", "bachata", estado="pendiente"
        )
        self.k.sincronizar()
        p = self.nota(id_)
        p.write_text(
            p.read_text().replace('"status": "pendiente"', '"status": "confirmado"')
        )
        self.assertEqual(self.k.recuperar("bachata")[0]["body"], "bachata")

    def test_concurrencia_y_recuerdos_sin_efectos_inventados(self):
        errores = []

        def escribir(i):
            try:
                self.k.guardar("Entorno", f"proyecto {i}", f"Python {i}")
            except Exception as e:
                errores.append(e)

        hilos = [threading.Thread(target=escribir, args=(i,)) for i in range(10)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.k.registrar_resultado(
            "acción inventada",
            [{"accion": "open_application", "ok": True, "verificado": False}],
        )
        self.k.sincronizar()
        self.assertEqual(errores, [])
        self.assertFalse(list((self.vault / "Aprendizajes").glob("*.md")))
        self.assertLessEqual(len(self.k.recuperar("Python")), 4)

    def test_dos_instancias_sincronizan_sin_duplicar_notas(self):
        otra=Conocimiento(self.db,self.vault);self.addCleanup(otra.close)
        errores=[]
        def escribir(k,prefijo):
            try:
                for i in range(5):
                    k.guardar('Entorno',f'{prefijo} {i}',f'proyecto {i}')
                    k.sincronizar()
            except Exception as e:errores.append(e)
        h1=threading.Thread(target=escribir,args=(self.k,'A'))
        h2=threading.Thread(target=escribir,args=(otra,'B'))
        h1.start();h2.start();h1.join();h2.join()
        self.assertEqual(errores,[])
        self.assertEqual(len(list((self.vault/'Entorno').glob('*.md'))),10)

    def test_conflicto_se_oculta_tambien_del_router_clasico_y_se_resuelve(self):
        self.store.remember('editor','Code')
        r=self.k.recuperar('editor')[0];p=self.nota(r['id'])
        p.write_text(p.read_text().replace('\nCode\n','\nCambio humano\n'))
        self.store.remember('editor','VSCodium')
        self.k.sincronizar()
        self.assertEqual(self.store.recall('editor'),[])
        self.assertEqual(self.store.list_facts(),[])
        self.store.remember('editor','Elección final')
        self.k.sincronizar()
        self.assertEqual(self.store.recall('editor')[0]['value'],'Elección final')
        self.assertIn('Elección final',p.read_text())

    def test_sqlite_no_disponible_no_inventa_guardado(self):
        import sqlite3
        conn=mock.Mock(in_transaction=False)
        conn.execute.side_effect=sqlite3.OperationalError('solo lectura')
        with mock.patch.object(self.k,'conn',conn):
            self.assertIsNone(self.k.guardar('Entorno','ejemplo','dato'))
        conn.rollback.assert_called_once()

    def test_un_objetivo_incompleto_no_se_aprende_como_procedimiento(self):
        self.k.registrar_resultado('abre app y termina otra cosa',[{'accion':'open_application','ok':True,'verificado':True}],completado=False)
        self.assertFalse(list((self.vault/'Aprendizajes').glob('*.md')))
        self.assertIn('incompleto',next((self.vault/'Sesiones').glob('*.md')).read_text())

    def test_olvido_borra_valores_activos_y_permite_recordar_explicitamente(self):
        self.store.remember('editor','Code')
        self.store.remember('editor','VSCodium')
        self.store.log_turn('assistant','Tu editor es VSCodium.',ok=True)
        r=self.k.recuperar('editor')[0]
        self.store.forget('editor');self.k.sincronizar()
        row=self.k.conn.execute('SELECT body,title FROM knowledge WHERE id=?',(r['id'],)).fetchone()
        self.assertEqual(tuple(row),('',''))
        self.assertEqual(self.store._conn.execute('SELECT count(*) FROM fact_history').fetchone()[0],0)
        self.assertEqual(self.store.recent_turns(),[])
        self.store.remember('editor','Otro editor')
        self.assertEqual(self.k.recuperar('editor')[0]['body'],'Otro editor')
