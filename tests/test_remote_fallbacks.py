"""Contratos JSON, credenciales separadas y respaldos GLM/Groq por rol."""

import json
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import requests

from modules.agent_providers import (Cancelado, ErrorProveedor, ProveedorGlm,
                                    ProveedorGroq, crear_respaldos)


class TestRespaldosRemotos(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            NVIDIA_API_KEY="clave-nvidia-original", NVIDIA_GLM_API_KEY="clave-glm",
            NVIDIA_BASE_URL="https://nvidia.invalid/v1", NVIDIA_MAX_TOKENS=4096,
            NVIDIA_THINKING_ENABLED=True, NVIDIA_MODEL_COOLDOWN=60,
            NVIDIA_DEVELOPMENT_MODEL="deepseek-ai/deepseek-v4.1-flash",
            NVIDIA_ANALYSIS_MODEL="nvidia/nemotron-3.5-bolt-e4b",
            NVIDIA_GLM_MODEL="z-ai/glm-5.3-flash", GROQ_API_KEY="clave-groq",
            NVIDIA_BOLT_API_KEY="clave-bolt", NVIDIA_SUPER_API_KEY="clave-super",
            NVIDIA_SUPER_MODEL="nvidia/nemotron-3.5-super-vl-120b-a12b", AGENT_SUPER_FALLBACK=False,
            GROQ_BASE_URL="https://groq.invalid/openai/v1", GROQ_AGENT_MODEL="openai/gpt-oss-120b",
            GROQ_MAX_TOKENS=2048,
            AGENT_GLM_FALLBACK=False, AGENT_GROQ_FALLBACK=False)
        self.cancelar = threading.Event()
        self.decision = {"tipo": "respuesta", "texto": "Quedan 60 euros."}
        self.http = mock.Mock(status_code=200, headers={})
        self.http.json.return_value = {"choices": [{"message": {
            "content": json.dumps(self.decision), "reasoning": "razonamiento interno"}, "finish_reason": "stop"}]}
        self.post = mock.patch("modules.agent_providers.requests.post", return_value=self.http).start()
        self.addCleanup(mock.patch.stopall)

    def consultar(self, proveedor=None, contexto=None):
        return (proveedor or ProveedorGroq(self.config)).consultar(
            "Devuelve JSON", contexto or {}, tarea=None, cancelar=self.cancelar, timeout=10)

    def test_groq_json_completo_sin_streaming_ni_opciones_nvidia(self):
        self.assertEqual(self.consultar(), self.decision)
        peticion = self.post.call_args.kwargs
        self.assertFalse(peticion["stream"])
        self.assertFalse(peticion["json"]["stream"])
        self.assertNotIn("chat_template_kwargs", peticion["json"])
        self.assertNotIn("tools", peticion["json"])
        self.assertEqual(peticion["headers"]["Authorization"], "Bearer clave-groq")
        self.http.iter_lines.assert_not_called()
        self.http.close.assert_called_once()

    def test_glm_usa_su_clave_sin_sustituir_la_original(self):
        self.assertEqual(self.consultar(ProveedorGlm(self.config)), self.decision)
        self.assertEqual(self.post.call_args.kwargs["headers"]["Authorization"], "Bearer clave-glm")
        self.assertEqual(self.config.NVIDIA_API_KEY, "clave-nvidia-original")

    def test_herramienta_json_se_valida_sin_ejecutarla(self):
        decision = {"tipo": "herramienta", "accion": "leer_archivo", "parametros": {"ruta": "/datos/a.txt"}}
        self.http.json.return_value["choices"][0]["message"]["content"] = json.dumps(decision)
        self.assertEqual(self.consultar(contexto={"herramientas": {"leer_archivo": "ruta"}}), decision)

    def test_no_acepta_herramientas_nativas(self):
        self.http.json.return_value["choices"][0]["message"]["tool_calls"] = [{"id": "x"}]
        with self.assertRaises(ErrorProveedor):
            self.consultar()

    def test_json_truncado_no_pasa_al_executor(self):
        self.http.json.return_value["choices"][0]["finish_reason"] = "length"
        with self.assertRaises(ErrorProveedor):
            self.consultar()

    def test_error_identifica_groq_y_no_expone_cuerpo(self):
        self.http.status_code = 429
        self.http.text = self.config.GROQ_API_KEY
        with self.assertRaises(ErrorProveedor) as captura:
            self.consultar()
        self.assertIn("Groq", str(captura.exception))
        self.assertNotIn(self.config.GROQ_API_KEY, str(captura.exception))

    def test_fallo_red_no_expone_credencial(self):
        self.post.side_effect = requests.ConnectionError(self.config.GROQ_API_KEY)
        with self.assertRaises(ErrorProveedor) as captura:
            self.consultar()
        self.assertIn("Groq", str(captura.exception))
        self.assertNotIn(self.config.GROQ_API_KEY, str(captura.exception))

    def test_cancelado_no_envia_peticion(self):
        self.cancelar.set()
        with self.assertRaises(Cancelado):
            self.consultar()
        self.post.assert_not_called()

    def test_groq_respeta_retry_after_una_vez_dentro_del_presupuesto(self):
        limitado = mock.Mock(status_code=429, headers={"Retry-After": "2"})
        self.post.side_effect = [limitado, self.http]
        with mock.patch.object(self.cancelar, "wait", return_value=False) as esperar:
            self.assertEqual(self.consultar(), self.decision)
        esperar.assert_called_once_with(2)
        self.assertEqual(self.post.call_count, 2)

    def test_groq_repite_una_vez_si_servidor_rechaza_formato_json(self):
        invalido = mock.Mock(status_code=400, headers={})
        invalido.json.return_value = {"error": {"code": "json_validate_failed", "failed_generation": "datos no confiables"}}
        self.post.side_effect = [invalido, self.http]
        self.assertEqual(self.consultar(), self.decision)
        self.assertEqual(self.post.call_count, 2)
        mensajes = self.post.call_args.kwargs["json"]["messages"]
        self.assertIn("Corrige el formato", mensajes[0]["content"])
        self.assertNotIn("datos no confiables", json.dumps(mensajes))

    def test_retry_after_no_supera_presupuesto(self):
        self.http.status_code = 429
        self.http.headers = {"Retry-After": "60"}
        with mock.patch.object(self.cancelar, "wait") as esperar:
            with self.assertRaises(ErrorProveedor):
                self.consultar()
        esperar.assert_not_called()
        self.post.assert_called_once()

    def test_cancelar_durante_retry_after_no_reintenta(self):
        self.http.status_code = 429
        self.http.headers = {"Retry-After": "2"}
        with mock.patch.object(self.cancelar, "wait", return_value=True):
            with self.assertRaises(Cancelado):
                self.consultar()
        self.post.assert_called_once()

    def test_cancelacion_durante_peticion_descarta_resultado(self):
        def enviar(*args, **kwargs):
            self.cancelar.set()
            return self.http
        self.post.side_effect = enviar
        with self.assertRaises(Cancelado):
            self.consultar()
        self.http.close.assert_called_once()

    def test_nuevos_proveedores_desactivados_conservan_parejas(self):
        modelos = {rol: [p.modelo for p in lista] for rol, lista in crear_respaldos(self.config).items()}
        self.assertEqual(modelos, {"desarrollo": [self.config.NVIDIA_DEVELOPMENT_MODEL],
                                   "analisis": [self.config.NVIDIA_ANALYSIS_MODEL]})

    def test_groq_es_ultimo_respaldo_en_ambos_roles(self):
        self.config.AGENT_GROQ_FALLBACK = True
        modelos = {rol: [p.modelo for p in lista] for rol, lista in crear_respaldos(self.config).items()}
        self.assertEqual(modelos["desarrollo"], [self.config.NVIDIA_DEVELOPMENT_MODEL, self.config.GROQ_AGENT_MODEL])
        self.assertEqual(modelos["analisis"], [self.config.NVIDIA_ANALYSIS_MODEL, self.config.GROQ_AGENT_MODEL])
        self.assertNotIn(self.config.NVIDIA_ANALYSIS_MODEL, modelos["desarrollo"])

    def test_glm_solo_se_incorpora_a_desarrollo_al_habilitarlo(self):
        self.config.AGENT_GLM_FALLBACK = True
        self.config.AGENT_GROQ_FALLBACK = True
        modelos = {rol: [p.modelo for p in lista] for rol, lista in crear_respaldos(self.config).items()}
        self.assertEqual(modelos["desarrollo"], [self.config.NVIDIA_GLM_MODEL,
                                               self.config.NVIDIA_DEVELOPMENT_MODEL, self.config.GROQ_AGENT_MODEL])
        self.assertNotIn(self.config.NVIDIA_GLM_MODEL, modelos["analisis"])

    def test_super_y_bolt_tienen_claves_propias_y_solo_rol_analisis(self):
        self.config.AGENT_SUPER_FALLBACK = True
        respaldos = crear_respaldos(self.config)
        self.assertEqual([p.modelo for p in respaldos["analisis"]],
                         [self.config.NVIDIA_SUPER_MODEL, self.config.NVIDIA_ANALYSIS_MODEL])
        self.assertEqual([p.clave for p in respaldos["analisis"]], ["clave-super", "clave-bolt"])
        self.assertNotIn(self.config.NVIDIA_SUPER_MODEL, [p.modelo for p in respaldos["desarrollo"]])
