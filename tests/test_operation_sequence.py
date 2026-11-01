"""Aceptación de la conversación fallida con efectos observables y aislados."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_objectives import ProveedorFalso, ruta

from config import Config
from modules.executor import CommandExecutor
from modules.operation_intent import es_orden
from modules.orchestrator import Orquestador, contexto_ruta, modo_autorizado
from modules.task_state import AlmacenTareas


class TestSecuenciaOperativa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        for nombre in ("Creador de videos", "Gestor de cotizaciones"):
            (self.raiz / nombre).mkdir()
        self.config = Config()
        self.config.PROJECT_ROOTS = str(self.raiz)
        self.config.AGENT_TASK_PATH = str(self.raiz / "tareas")
        self.executor = CommandExecutor()
        self.estado = {
            "workspace": 1,
            "active": "0xf",
            "playing": False,
            "searches": [],
            "clients": [
                {
                    "address": "0xf",
                    "class": "firefox",
                    "title": "Firefox",
                    "workspace": {"id": 2},
                }
            ],
        }
        self.almacen = AlmacenTareas(self.config.AGENT_TASK_PATH)
        self.proveedor = ProveedorFalso(ruta(texto="Hola, ¿cómo puedo ayudarte?"))
        self.c = Orquestador(
            self.config,
            self.executor,
            almacen=self.almacen,
            proveedores={
                r: self.proveedor for r in ("cotidiano", "analisis", "desarrollo")
            },
        )
        self.parche = mock.patch(
            "modules.operational.subprocess.run", side_effect=self.ejecutar
        )
        self.parche.start()
        self.addCleanup(self.parche.stop)
        self.popen = mock.patch(
            "modules.operational.subprocess.Popen", side_effect=self.abrir
        )
        self.popen.start()
        self.addCleanup(self.popen.stop)
        self.executor.action_map["open_application"] = self.abrir_app

    def abrir_app(self, app, **kwargs):
        self.estado["clients"].append(
            {
                "address": "0xa",
                "class": "Spotify",
                "title": "Spotify",
                "workspace": {"id": self.estado["workspace"]},
            }
        )

    def abrir(self, args, **kwargs):
        if args[0] == "code":
            self.estado["clients"].append(
                {
                    "address": "0xc" + str(len(self.estado["clients"])),
                    "class": "code-oss",
                    "title": Path(args[-1]).name + " — Visual Studio Code",
                    "workspace": {"id": self.estado["workspace"]},
                }
            )
        elif args[0] in {"firefox", "chromium"}:
            self.estado["searches"].append((args[0], args[-1]))
        return SimpleNamespace(poll=lambda: None)

    def ejecutar(self, args, **kwargs):
        e = self.estado
        out = "ok"
        code = 0
        if args[:2] == ["hyprctl", "-j"]:
            consulta = args[2]
            out = json.dumps(
                {
                    "clients": e["clients"],
                    "workspaces": [{"id": i, "name": str(i)} for i in (1, 2, 3)],
                    "monitors": [
                        {
                            "specialWorkspace": {
                                "id": e["workspace"] if e["workspace"] < 0 else 0
                            }
                        }
                    ],
                    "activeworkspace": {"id": e["workspace"]},
                    "activewindow": next(
                        (c for c in e["clients"] if c["address"] == e["active"]),
                        {"address": e["active"]},
                    ),
                }[consulta]
            )
        elif args[:2] == ["hyprctl", "dispatch"]:
            if args[2] == "workspace":
                e["workspace"] = int(args[3])
            elif args[2] == "focuswindow":
                e["active"] = args[3].split(":", 1)[1]
                c = next(c for c in e["clients"] if c["address"] == e["active"])
                e["workspace"] = c["workspace"]["id"]
            elif args[2] == "movetoworkspacesilent":
                destino, direccion = args[3].split(",address:")
                next(c for c in e["clients"] if c["address"] == direccion)["workspace"][
                    "id"
                ] = int(destino)
        elif args[0] == "playerctl":
            if args[-1] == "-l":
                return subprocess.CompletedProcess(
                    args, 0, stdout="spotify\n", stderr=""
                )
            if args[-1] == "play":
                e["playing"] = True
            out = "Playing" if e["playing"] else "Stopped"
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, code, stdout=out, stderr="")

    def test_foco_nativo_tambien_verifica_code_oss(self):
        from commands.system import SystemCommands
        self.estado['clients'].append({'address': '0xc', 'class': 'code-oss',
                                      'workspace': {'id': 3}})
        r = SystemCommands().focus_window('code')
        self.assertTrue(r.verificado)
        self.assertEqual(self.estado['active'], '0xc')

    def test_foco_en_aplicacion_de_workspace_especial(self):
        self.estado["clients"].append(
            {
                "address": "0xa",
                "class": "Spotify",
                "workspace": {"id": -98, "name": "special:music"},
            }
        )
        r = self.c.atender("abre spotify y reproduce la musica")
        self.assertTrue(r.ok)
        self.assertEqual(self.estado["active"], "0xa")

    def test_recorrido_real_con_resultados_por_paso(self):
        r = self.c.atender("qué tal estás hoy")
        self.assertIn("Hola", r)
        r = self.c.atender("bien livings primero muéveme al espacio de trabajo 3")
        self.assertEqual(self.estado["workspace"], 3)
        self.assertTrue(r.ok)
        self.c.atender("quiero que abras code con la carpeta creador de videos")
        self.assertTrue(
            any("Creador de videos" in x["title"] for x in self.estado["clients"])
        )
        r = self.c.atender("Ábrelo Ábreme mi pantalla en el espacio de trabajo 3")
        self.assertNotIn("archivo reciente", r)
        self.assertEqual(self.estado["workspace"], 3)
        self.c.atender("bien entonces abre el gestor de cotizaciones con code")
        self.assertTrue(
            any("Gestor de cotizaciones" in x["title"] for x in self.estado["clients"])
        )
        self.c.atender(
            "mejor muévete al espacio de trabajo donde tengo firefox y Busca en YouTube un video sobre perros"
        )
        self.assertEqual(self.estado["workspace"], 2)
        self.assertIn("search_query=perros", self.estado["searches"][-1][1])
        self.assertEqual(self.estado["searches"][-1][0], "firefox")
        r = self.c.atender("un video sobre perro haciendo acariciados")
        self.assertIn("perro+haciendo+acariciados", self.estado["searches"][-1][1])
        self.assertIsNone(
            r.ok
        )  # Se envió una URL; no se inventa verificación del contenido.
        r = self.c.atender("Abre Spotify y Reproduce la música")
        self.assertTrue(self.estado["playing"])
        self.assertTrue(r.ok)
        self.c.atender("Abre Spotify")
        r = self.c.atender("Reproduce la música")
        self.assertTrue(r.ok)
        self.assertEqual(
            len(self.proveedor.consultas), 1
        )  # Solo el saludo necesita inferencia.
        tarea = self.almacen.cargar("local")
        self.assertNotIn("creador", tarea.objetivo)
        self.assertNotIn("youtube", tarea.objetivo.lower())

    def test_los_diez_turnos_por_el_pipeline_compartido(self):
        from main import make_pipeline
        from modules.gateway import TurnGate

        frases = [
            "qué tal estás hoy",
            "bien livings primero muéveme al espacio de trabajo 3",
            "quiero que abras code con la carpeta creador de videos",
            "Ábrelo Ábreme mi pantalla en el espacio de trabajo 3",
            "bien entonces abre el gestor de cotizaciones con code",
            "mejor muévete al espacio de trabajo donde tengo firefox y Busca en YouTube un video sobre perros",
            "un video sobre perro haciendo acariciados",
            "Abre Spotify y Reproduce la música",
            "Abre Spotify",
            "Reproduce la música",
        ]
        with mock.patch("modules.memory.get_store"):
            p = make_pipeline(
                mock.Mock(), self.executor, mock.Mock(), TurnGate(), orchestrator=self.c
            )
            respuestas = [
                p(frase, speak=False, session_id="movil:prueba") for frase in frases
            ]
        self.assertEqual(self.estado["workspace"], 2)
        self.assertEqual(len(self.estado["searches"]), 2)
        self.assertTrue(self.estado["playing"])
        self.assertTrue(respuestas[-1].verificado)
        self.assertTrue(respuestas[7].ok)
        self.assertNotIn("archivo reciente", respuestas[3])
        self.assertNotIn("ya te encuentras", respuestas[1])
        self.assertEqual(len(self.proveedor.consultas), 1)

    def test_una_respuesta_conversacional_no_certifica_una_accion(self):
        self.proveedor.decisiones = [
            ruta(texto="Ya te encuentras en el espacio de trabajo 3.")
        ]
        r = self.c.atender("qué tal estás")
        self.assertNotIn("Ya te encuentras", r)
        self.assertIsNone(r.ok)
        self.assertEqual(self.estado["workspace"], 1)

    def test_destino_explicito_se_verifica_sobre_la_misma_ventana(self):
        self.c.atender("abre el proyecto creador de videos con code")
        cliente = next(c for c in self.estado["clients"] if c["class"] == "code-oss")
        cliente["workspace"]["id"] = 2
        direccion = cliente["address"]
        self.c.atender("ábrelo en el espacio de trabajo 3")
        self.assertEqual(cliente["address"], direccion)
        self.assertEqual(cliente["workspace"]["id"], 3)
        self.assertEqual(self.estado["workspace"], 3)

    def test_no_hay_acciones_si_es_pregunta_o_negacion(self):
        for s in [
            "no abras Spotify",
            "explica cómo abrir Code",
            "puedes explicar cómo abrir Spotify",
            "abre Spotify y no reproduzcas música",
            "qué pasa si abro firefox",
        ]:
            self.assertIsNone(self.c.operaciones.planificar(s))
            self.assertEqual(modo_autorizado(s, "actuar"), "leer")

    def test_cortesia_y_conjugacion_no_rebajan_la_orden(self):
        for s in [
            "quiero que abras code con la carpeta creador de videos",
            "bien entonces abre el gestor de cotizaciones con code",
            "bien livings primero muéveme al espacio de trabajo 3",
            "mejor muévete al espacio donde tengo firefox",
        ]:
            self.assertTrue(es_orden(s))
            self.assertEqual(modo_autorizado(s, "leer"), "actuar")

    def test_pregunta_generica_no_obliga_a_continuar(self):
        anterior = {
            "rol": "cotidiano",
            "estado": "terminada",
            "pregunta_abierta": "¿Algo más con lo que pueda ayudarte?",
        }
        self.assertFalse(
            contexto_ruta("bien entonces abre firefox", anterior)["referencia_anterior"]
        )

    def test_ambiguedad_de_proyecto_pide_precision_sin_abrir(self):
        extra = self.raiz / "otro"
        extra.mkdir()
        (extra / "Creador de videos").mkdir()
        self.c.atender("abre el proyecto creador de videos con code")
        self.assertEqual(len(self.estado["clients"]), 1)
        self.assertEqual(self.almacen.cargar("local").estado, "aclaracion")

    def test_sin_referente_no_se_abre_un_archivo_cualquiera(self):
        r = self.c.atender("ábrelo")
        self.assertIn("Qué proyecto", r)
        self.assertEqual(len(self.estado["clients"]), 1)

    def test_no_se_ejecuta_un_prefijo_de_plan_incompleto(self):
        self.assertIsNone(
            self.c.operaciones.planificar("abre Spotify y borra todos mis archivos")
        )

    def test_stop_impide_segundo_paso(self):
        old = self.executor.action_map["open_application"]

        def detener(app):
            old(app)
            self.c.cancelar("local")

        self.executor.action_map["open_application"] = detener
        self.c.atender("abre Spotify y reproduce la música")
        self.assertFalse(self.estado["playing"])
