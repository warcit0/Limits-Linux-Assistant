"""Prioridad, SSE y fallos de los especialistas sin solicitudes reales."""

import json
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import requests

from modules.agent_providers import (Cancelado, ErrorProveedor, ErrorNvidia,
                                    ProveedorNvidia, ProveedorConRespaldo)


DECISION = {"tipo": "respuesta", "texto": "Quedan 60 euros."}


def evento(valor):
    return b"data: " + json.dumps(valor).encode()


def flujo(texto=None, motivo="stop"):
    return [evento({"choices": [{"delta": {"reasoning_content": "texto interno"}}]}),
            evento({"choices": [{"delta": {"content": texto or json.dumps(DECISION)}, "finish_reason": motivo}]}),
            b"data: [DONE]"]


class TestNvidia(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(NVIDIA_API_KEY="secreto-de-prueba",
                                      NVIDIA_BASE_URL="https://ejemplo.invalid/v1",
                                      NVIDIA_MAX_TOKENS=4096, NVIDIA_THINKING_ENABLED=False)
        self.proveedor = ProveedorNvidia(self.config, "modelo-a")
        self.cancelar = threading.Event()
        self.http = mock.Mock(status_code=200, headers={})
        self.http.iter_lines.return_value = flujo()
        self.post = mock.patch("modules.agent_providers.requests.post", return_value=self.http).start()
        self.addCleanup(mock.patch.stopall)

    def consultar(self):
        return self.proveedor.consultar("instrucción", {}, tarea=None, cancelar=self.cancelar, timeout=5)

    def test_sse_separa_razonamiento_y_cierra_conexion(self):
        self.assertEqual(self.consultar(), DECISION)
        self.http.close.assert_called_once()
        payload = self.post.call_args.kwargs["json"]
        self.assertNotIn(self.config.NVIDIA_API_KEY, json.dumps(payload))
        self.assertEqual(payload["model"], "modelo-a")
        self.assertNotIn("tools", payload)

    def test_decision_herramienta_se_entrega_sin_ejecutarla(self):
        decision = {"tipo": "herramienta", "accion": "leer_archivo", "parametros": {"ruta": "/datos/a"}}
        self.http.iter_lines.return_value = flujo(json.dumps(decision))
        resultado = self.proveedor.consultar("instrucción", {"herramientas": {"leer_archivo": {}}},
                                            tarea=None, cancelar=self.cancelar, timeout=5)
        self.assertEqual(resultado, decision)

    def test_contrato_escritorio_conserva_su_catalogo(self):
        decision = {"tool": "search_file", "args": {"name": "informe.txt"}}
        self.http.iter_lines.return_value = flujo(json.dumps(decision))
        resultado = self.proveedor.consultar("instrucción", {"herramientas_escritorio": ["search_file"]},
                                            tarea=None, cancelar=self.cancelar, timeout=5)
        self.assertEqual(resultado, decision)

    def test_desktop_utiliza_el_mismo_grupo_sin_ejecutar_en_proveedor(self):
        from modules.desktop_agent import DesktopAgent
        grupo = mock.Mock()
        grupo.consultar.return_value = {"tool": "done", "args": {"message": "Listo"}}
        agente = DesktopAgent(provider="nvidia", proveedor_remoto=grupo)
        resultado = agente._plan([{"role": "system", "content": "instrucción"},
                                 {"role": "user", "content": "Objetivo"}])
        self.assertEqual(resultado["tool"], "done")
        grupo.consultar.assert_called_once()

    def test_desktop_ambos_fallan_no_invoca_opencode(self):
        from modules.desktop_agent import DesktopAgent
        grupo = mock.Mock()
        grupo.consultar.side_effect = ErrorProveedor("Fallaron ambos")
        agente = DesktopAgent(provider="nvidia", proveedor_remoto=grupo)
        with mock.patch.object(agente, "_query_opencode") as antiguo:
            self.assertIsNone(agente._plan([]))
            antiguo.assert_not_called()

    def test_formato_invalido_dispara_fallback(self):
        for texto in ('[]', 'sin JSON', '{"tipo":"respuesta","texto":""}',
                      '{"tipo":"herramienta","accion":"shell","parametros":{}}'):
            with self.subTest(texto=texto):
                self.http.iter_lines.return_value = flujo(texto)
                with self.assertRaises(ErrorProveedor):
                    self.consultar()

    def test_truncamiento_no_es_decision_valida(self):
        self.http.iter_lines.return_value = flujo(motivo="length")
        with self.assertRaises(ErrorNvidia):
            self.consultar()

    def test_stream_cortado_rechaza_json_aparentemente_completo(self):
        self.http.iter_lines.return_value = flujo(motivo=None)
        with self.assertRaises(ErrorNvidia):
            self.consultar()

    def test_http_error_no_expone_cuerpo_ni_credencial(self):
        self.http.status_code = 429
        self.http.text = self.config.NVIDIA_API_KEY
        self.http.headers = {"Retry-After": "90"}
        with self.assertRaises(ErrorNvidia) as captura:
            self.consultar()
        self.assertNotIn(self.config.NVIDIA_API_KEY, str(captura.exception))
        self.assertEqual(captura.exception.espera, 90)
        self.http.close.assert_called_once()

    def test_fallo_red_no_expone_excepcion_original(self):
        self.post.side_effect = requests.ConnectionError(self.config.NVIDIA_API_KEY)
        with self.assertRaises(ErrorNvidia) as captura:
            self.consultar()
        self.assertNotIn(self.config.NVIDIA_API_KEY, str(captura.exception))

    def test_cancelacion_previa_no_hace_red(self):
        self.cancelar.set()
        with self.assertRaises(Cancelado):
            self.consultar()
        self.post.assert_not_called()

    def test_cancelacion_durante_flujo_descarta_decision(self):
        def lineas(**kwargs):
            yield flujo()[0]
            self.cancelar.set()
            yield flujo()[1]
        self.http.iter_lines.side_effect = lineas
        with self.assertRaises(Cancelado):
            self.consultar()
        self.http.close.assert_called_once()

    def test_clave_ausente_falla_sin_red(self):
        self.proveedor.clave = ""
        with self.assertRaisesRegex(ErrorNvidia, "NVIDIA_API_KEY"):
            self.consultar()
        self.post.assert_not_called()


class TestPrioridad(unittest.TestCase):
    def setUp(self):
        self.a = SimpleNamespace(modelo="a", consultar=mock.Mock(return_value=DECISION))
        self.b = SimpleNamespace(modelo="b", consultar=mock.Mock(return_value=DECISION))
        self.grupo = ProveedorConRespaldo([self.a, self.b], enfriamiento=60)
        self.cancelar = threading.Event()

    def consultar(self):
        return self.grupo.consultar("instrucción", {}, tarea=None, cancelar=self.cancelar, timeout=10)

    def test_principal_se_mantiene_mientras_funcione(self):
        for _ in range(4):
            self.assertEqual(self.consultar(), DECISION)
            self.assertEqual(self.grupo.ultimo_modelo, "a")
        self.b.consultar.assert_not_called()

    def test_fallo_cambia_al_otro_en_mismo_paso(self):
        self.a.consultar.side_effect = ErrorNvidia("HTTP 429")
        self.assertEqual(self.consultar(), DECISION)
        self.assertEqual(self.grupo.ultimo_modelo, "b")
        self.a.consultar.assert_called_once()
        self.b.consultar.assert_called_once()
        self.assertLess(self.a.consultar.call_args.kwargs["timeout"], 5.01)

    def test_fallidos_se_enfrian_y_se_recuperan(self):
        self.a.consultar.side_effect = [ErrorNvidia("HTTP 429"), DECISION]
        self.consultar()
        self.consultar()
        self.assertEqual(self.a.consultar.call_count, 1)
        with mock.patch("modules.agent_providers.time.monotonic", return_value=self.grupo._hasta[0] + 1):
            self.consultar()
        self.assertEqual(self.grupo.ultimo_modelo, "a")

    def test_ambos_fallan_sin_bucle(self):
        self.a.consultar.side_effect = self.b.consultar.side_effect = ErrorNvidia("HTTP 500")
        with self.assertRaisesRegex(ErrorProveedor, "Ningún proveedor"):
            self.consultar()
        with self.assertRaisesRegex(ErrorProveedor, "temporalmente"):
            self.consultar()
        self.assertEqual((self.a.consultar.call_count, self.b.consultar.call_count), (1, 1))

    def test_retry_after_prolonga_enfriamiento(self):
        self.a.consultar.side_effect = ErrorNvidia("HTTP 429", espera=300)
        with mock.patch("modules.agent_providers.time.monotonic", return_value=100):
            self.consultar()
        self.assertEqual(self.grupo._hasta[0], 400)

    def test_cancelado_no_consulta_suplente(self):
        self.a.consultar.side_effect = Cancelado("Tarea cancelada.")
        with self.assertRaises(Cancelado):
            self.consultar()
        self.b.consultar.assert_not_called()
        self.assertFalse(self.grupo._hasta)

    def test_respuesta_tardia_cancelada_no_avanza(self):
        def consultar(*args, **kwargs):
            self.cancelar.set()
            return DECISION
        self.a.consultar.side_effect = consultar
        with self.assertRaises(Cancelado):
            self.consultar()
        self.b.consultar.assert_not_called()

    def test_grupo_vacio_falla_claramente(self):
        self.grupo = ProveedorConRespaldo([])
        with self.assertRaises(ErrorProveedor):
            self.consultar()

    def coordinador(self):
        from config import Config
        from modules.orchestrator import Orquestador
        config = SimpleNamespace(**{nombre: getattr(Config, nombre) for nombre in dir(Config) if nombre.isupper()})
        config.AGENT_REMOTE_PROVIDER = "opencode_con_respaldo"
        config.AGENT_GLM_FALLBACK = False
        config.AGENT_GROQ_FALLBACK = False
        config.AGENT_SUPER_FALLBACK = False
        return Orquestador(config, mock.Mock())

    def test_parejas_independientes_por_rol(self):
        c = self.coordinador()
        desarrollo, analisis = c.proveedores["desarrollo"], c.proveedores["analisis"]
        self.assertIsNot(desarrollo, analisis)
        self.assertEqual([p.modelo for p in desarrollo.proveedores],
                         ["opencode/deepseek-v4.1-flash-free", "deepseek-ai/deepseek-v4.1-flash"])
        self.assertEqual([p.modelo for p in analisis.proveedores],
                         ["opencode/big-pickle", "nvidia/nemotron-3.5-bolt-e4b"])

    def test_cuota_agotada_solo_consulta_respaldo_del_mismo_rol(self):
        c = self.coordinador()
        for rol in ("desarrollo", "analisis"):
            grupo = c.proveedores[rol]
            principal, respaldo = grupo.proveedores
            with mock.patch.object(principal, "consultar", side_effect=ErrorProveedor("429")), \
                 mock.patch.object(respaldo, "consultar", return_value=DECISION) as consulta:
                self.assertEqual(grupo.consultar("instrucción", {}, tarea=None,
                                                cancelar=self.cancelar, timeout=10), DECISION)
                consulta.assert_called_once()
                self.assertEqual(grupo.ultimo_modelo, respaldo.modelo)

    def test_desktop_prioriza_opencode_y_solo_despues_nvidia(self):
        from modules.desktop_agent import DesktopAgent
        respaldo = mock.Mock()
        respaldo.consultar.return_value = {"tool": "done", "args": {"message": "OK"}}
        agente = DesktopAgent(provider="opencode", opencode_api_key="clave-ficticia",
                              fallback="nvidia", proveedor_remoto=respaldo)
        decision = {"tool": "done", "args": {"message": "OpenCode"}}
        with mock.patch.object(agente, "_query_opencode", return_value=decision):
            self.assertEqual(agente._plan([]), decision)
        respaldo.consultar.assert_not_called()
        with mock.patch.object(agente, "_query_opencode", return_value=None):
            self.assertEqual(agente._plan([])["args"]["message"], "OK")
        respaldo.consultar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
