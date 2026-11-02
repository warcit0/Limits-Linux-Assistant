"""Contratos de inferencia y catálogo: pruebas sin red ni acciones del escritorio."""

import json
import threading
import unittest
from unittest import mock

from commands.workspaces import WorkspaceCommands
from config import Config
from modules.agent_providers import ProveedorGroq, ProveedorOllama
from modules.task_state import Tarea


class TestContratosSemanticos(unittest.TestCase):
    def test_respaldo_acepta_esquema_de_interpretacion_y_no_solo_worker(self):
        c = Config()
        c.GROQ_API_KEY = "clave-simulada"
        clasificacion = {
            "rol": "cotidiano",
            "modo": "actuar",
            "continuar": False,
            "objetivos": ["resultado"],
            "requiere_observacion": True,
            "capacidades": ["sistema"],
        }
        r = mock.Mock(status_code=200)
        r.json.return_value = {
            "choices": [
                {
                    "message": {"content": json.dumps(clasificacion)},
                    "finish_reason": "stop",
                }
            ]
        }
        with mock.patch(
            "modules.agent_providers.requests.post", return_value=r
        ) as post:
            salida = ProveedorGroq(c).consultar(
                "clasifica",
                {"tarea_anterior": None, "semantico": True},
                tarea=Tarea("t", "objetivo"),
                cancelar=threading.Event(),
                timeout=5,
            )
        self.assertEqual(salida, clasificacion)
        schema = post.call_args.kwargs["json"]["response_format"]["json_schema"][
            "schema"
        ]
        self.assertIn("objetivos", schema["properties"])

    def test_ollama_llamadas_nativas_se_convierten_en_decisiones(self):
        c = Config()
        r = mock.Mock()
        r.status_code = 200
        r.iter_lines.return_value = [
            json.dumps(
                {
                    "message": {
                        "tool_calls": [
                            {"function": {"name": "get_volume", "arguments": {}}}
                        ]
                    }
                }
            ).encode()
        ]
        contrato = {
            "type": "function",
            "function": {
                "name": "get_volume",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        ctx = {
            "semantico": True,
            "herramientas": {"get_volume": "()"},
            "contratos": [contrato],
        }
        with mock.patch(
            "modules.agent_providers.requests.post", return_value=r
        ) as post:
            salida = ProveedorOllama(c).consultar(
                "elige",
                ctx,
                tarea=Tarea("t", "objetivo"),
                cancelar=threading.Event(),
                timeout=5,
            )
        self.assertEqual(salida["accion"], "get_volume")
        self.assertNotIn("format", post.call_args.kwargs["json"])
        self.assertEqual(post.call_args.kwargs["json"]["tools"], [contrato])

    def test_especial_visible_no_se_alterna_y_oculta(self):
        c = WorkspaceCommands()
        with (
            mock.patch.object(
                c,
                "_leer",
                side_effect=[
                    [{"id": -98, "name": "special:music"}],
                    [{"specialWorkspace": {"id": -98, "name": "special:music"}}],
                ],
            ),
            mock.patch.object(c, "_dispatch") as dispatch,
        ):
            self.assertIn("ya está visible", c.switch("music"))
            dispatch.assert_not_called()

    def test_especial_se_abre_y_se_comprueba(self):
        c = WorkspaceCommands()
        with (
            mock.patch.object(
                c,
                "_leer",
                side_effect=[
                    [{"id": -98, "name": "special:music"}],
                    [{"specialWorkspace": {"id": 0, "name": ""}}],
                    {"id": 1},
                    [{"specialWorkspace": {"id": -98, "name": "special:music"}}],
                ],
            ),
            mock.patch.object(c, "_dispatch") as dispatch,
        ):
            self.assertIn("comprobado", c.switch("music"))
            dispatch.assert_called_once_with("togglespecialworkspace", "music")

    def test_alias_no_inventa_parametros_y_rechaza_conflictos(self):
        from modules.argument_contracts import normalizar_argumentos
        def media(action='play-pause',player=None):pass
        self.assertEqual(normalizar_argumentos(media,{'command':'play','player':'spotify'}),{'action':'play','player':'spotify'})
        with self.assertRaises(ValueError):normalizar_argumentos(media,{'command':'play','action':'pause'})
        def terminal(command):pass
        self.assertEqual(normalizar_argumentos(terminal,{'command':'pwd'}),{'command':'pwd'})
