"""Adaptadores de modelos sin ejecución implícita de herramientas."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace

import requests

log = logging.getLogger("limits.agent_providers")


class ErrorProveedor(RuntimeError):
    pass


class Cancelado(ErrorProveedor):
    pass


class ErrorNvidia(ErrorProveedor):
    def __init__(self, mensaje, *, espera=0, estado=None, codigo=None):
        super().__init__(mensaje)
        self.espera = espera
        self.estado = estado
        self.codigo = codigo


def ejecutar_proceso(argumentos, *, cwd=None, cancelar=None, timeout=60, env=None):
    """Proceso cancelable, salida acotada y terminación del grupo completo."""
    with tempfile.TemporaryFile() as salida, tempfile.TemporaryFile() as errores:
        entorno = {**os.environ, **(env or {})} if env is not None or cwd else None
        if cwd:
            entorno["PWD"] = str(Path(cwd).resolve())
        proceso = subprocess.Popen(argumentos, cwd=cwd, stdout=salida,
                                   stderr=errores, stdin=subprocess.DEVNULL,
                                   env=entorno,
                                   start_new_session=True)
        fin = time.monotonic() + timeout
        try:
            while proceso.poll() is None:
                if os.fstat(salida.fileno()).st_size > 2_000_000 or os.fstat(errores.fileno()).st_size > 2_000_000:
                    raise ErrorProveedor("El proceso superó el límite de salida.")
                if cancelar is not None and cancelar.is_set():
                    raise Cancelado("Tarea cancelada.")
                if time.monotonic() >= fin:
                    raise ErrorProveedor("Se agotó el tiempo de respuesta.")
                try:
                    proceso.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if proceso.poll() is None:
                os.killpg(proceso.pid, signal.SIGCONT)
                os.killpg(proceso.pid, signal.SIGTERM)
                try:
                    proceso.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    os.killpg(proceso.pid, signal.SIGKILL)
                    proceso.wait()
        if cancelar is not None and cancelar.is_set():
            raise Cancelado("Tarea cancelada.")
        salida.seek(0, 2)
        longitud = salida.tell()
        if longitud > 2_000_000:
            raise ErrorProveedor("La respuesta superó el límite de salida.")
        salida.seek(0)
        errores.seek(0)
        return proceso.returncode, salida.read().decode("utf-8", "replace"), errores.read(4096).decode("utf-8", "replace")


def extraer_json(texto):
    """Tolera fences; acepta exclusivamente un objeto JSON."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        valor = json.loads(texto)
    except (ValueError, TypeError):
        raise ErrorProveedor("El modelo no devolvió una decisión válida.") from None
    if not isinstance(valor, dict):
        raise ErrorProveedor("La decisión debe ser un objeto.")
    return valor


def esquema_herramientas(contratos, permitir_respuesta=True, permitir_pregunta=True, permitir_limitacion=True):
    texto = {"type":"object", "properties":{"tipo":{"type":"string","enum":["respuesta","pregunta"]},
             "texto":{"type":"string"},"accion":{"const":""},"parametros":{"type":"object","properties":{},"additionalProperties":False}},
             "required":["tipo","texto"],"additionalProperties":False}
    tipos = (["respuesta"] if permitir_respuesta else []) + (["pregunta"] if permitir_pregunta else []) + (["limitacion"] if permitir_limitacion else [])
    texto["properties"]["tipo"]["enum"] = tipos or ["pregunta"]
    variantes = [texto] if tipos else []
    for contrato in contratos:
        f = contrato["function"]
        variantes.append({"type":"object","properties":{"tipo":{"const":"herramienta"},
            "accion":{"const":f["name"]},"texto":{"type":"string"},"parametros":f["parameters"]},
            "required":["tipo","accion","parametros"],"additionalProperties":False})
    return {"anyOf":variantes}


def esquema_pregunta():
    return {"type":"object", "properties":{"necesaria":{"type":"boolean"}, "motivo":{"type":"string"}},
            "required":["necesaria","motivo"], "additionalProperties":False}


def esquema_autorizacion():
    return {"type":"object", "properties":{"permitida":{"type":"boolean"}, "motivo":{"type":"string"}},
            "required":["permitida","motivo"], "additionalProperties":False}


def esquema_evaluacion():
    return {"type": "object", "properties": {"completo": {"type":"boolean"},
        "pendientes": {"type":"array", "items":{"type":"string"}},
        "evidencias": {"type":"array", "items":{"type":"integer"}}},
        "required":["completo","pendientes","evidencias"], "additionalProperties":False}


def esquema_ruta(contexto):
    propiedades = {
        "rol": {"type": "string", "enum": contexto.get("roles_permitidos", ["cotidiano", "analisis", "desarrollo", "investigacion"])},
        "modo": {"type": "string", "enum": ["leer", "actuar", "preparar"]},
        "continuar": {"type": "boolean"} if contexto.get("tarea_anterior") else {"const": False}}
    if contexto.get("semantico"):
        propiedades.update({"objetivos": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6},
                            "requiere_observacion": {"type": "boolean"}, "requiere_sintesis": {"type":"boolean"},
                            "capacidades": {"type": "array", "items": {"type":"string", "enum": ["aplicaciones","sistema","multimedia","archivos","proyectos","television","desarrollo","memoria","navegacion"]}, "maxItems":3}})
    if contexto.get("catalogo_disponible") and contexto.get("semantico"):
        propiedades["herramientas_sugeridas"] = {"type":"array", "items":{"type":"string", "enum":contexto["catalogo_disponible"]}, "maxItems":5}
    return {"type": "object", "properties": propiedades, "required": list(propiedades), "additionalProperties": False}


class ProveedorOllama:
    def __init__(self, config):
        self.config = config
        self.modelo = config.OLLAMA_MODEL

    def consultar(self, sistema, contexto, *, tarea, cancelar, timeout):
        if cancelar.is_set():
            raise Cancelado("Tarea cancelada.")
        natural = bool(contexto.get("conversacion"))
        formato = ({"type": "object", "properties": {
            "rol": {"type": "string", "enum": contexto.get("roles_permitidos", ["cotidiano", "analisis", "desarrollo", "investigacion"])},
            "modo": {"type": "string", "enum": ["leer", "actuar", "preparar"]},
            "continuar": ({"const": False} if contexto.get("tarea_anterior") is None else
                          {"type": "boolean"})},
            "required": ["rol", "modo", "continuar"], "additionalProperties": False}
            if "tarea_anterior" in contexto else {
                "type": "object", "properties": {
                    "tipo": {"type": "string", "enum": ["respuesta", "pregunta", "herramienta"]},
                    "texto": {"type": "string"},
                    "accion": {"type": "string", "enum": ["", *contexto.get("herramientas", {})]},
                    "parametros": {"type": "object"}},
                "required": ["tipo", "texto", "accion", "parametros"], "additionalProperties": False})
        if contexto.get("semantico") and "tarea_anterior" in contexto:
            formato["properties"].update({
                "objetivos": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                "requiere_observacion": {"type": "boolean"}})
            formato["required"] += ["objetivos", "requiere_observacion"]
        if contexto.get("coherente"):
            from modules.coherent_agent import esquema_coherente
            formato = esquema_coherente(contexto.get("contratos",[]))
        elif contexto.get("evaluar_pregunta"):
            formato = esquema_pregunta()
        elif contexto.get("autorizar_operacion"):
            formato = esquema_autorizacion()
        elif contexto.get("evaluar_objetivo"):
            formato = esquema_evaluacion()
        elif "tarea_anterior" in contexto:
            formato = esquema_ruta(contexto)
        elif contexto.get("semantico") and not contexto.get("permitir_respuesta", True):
            formato["properties"]["tipo"]["enum"] = ["herramienta", "pregunta"]
        if "tarea_anterior" not in contexto and not natural and not contexto.get("semantico"):
            sistema += ("\nContrato local de cuatro campos: tipo, texto, accion, parametros. "
                        "Para responder o preguntar usa accion vacía y parametros {}. "
                        "Para conversar o recomendar sin consultar datos del equipo, elige respuesta o pregunta. "
                        "Solo usa herramienta si el objetivo requiere obtener datos reales o realizar una operación. "
                        "Ejemplo: {\"tipo\":\"respuesta\",\"texto\":\"Podemos ordenar archivos o revisar aplicaciones. ¿Cuál prefieres?\",\"accion\":\"\",\"parametros\":{}}.")

        nativo = bool(contexto.get("semantico") and contexto.get("contratos") and not contexto.get("coherente"))
        contexto_enviado = contexto
        if nativo:
            sistema += "\nInvoca las funciones nativas para usar herramientas. Para terminar devuelve texto JSON de tipo respuesta o pregunta. No escribas una llamada como texto."
        if contexto.get("semantico") and "herramientas" in contexto and not nativo:
            sistema += "\nCatálogo real de herramientas:\n" + json.dumps(contexto["herramientas"], ensure_ascii=False, sort_keys=True)
            contexto_enviado = {k:v for k,v in contexto.items() if k != "herramientas"}
        if nativo:
            contexto_enviado = {k:v for k,v in contexto.items() if k not in {"herramientas","contratos"}}
        mensajes = [{"role": "system", "content": sistema},
                    {"role": "user", "content": json.dumps(contexto_enviado, ensure_ascii=False)}]
        modelo = self.config.OLLAMA_MODEL
        if "tarea_anterior" not in contexto:
            modelo = getattr(self.config, "AGENT_CONVERSATION_MODEL", self.config.OLLAMA_MODEL)
            observaciones = [h for h in contexto.get("historial", []) if h.get("herramienta") and h.get("resultado", {}).get("ok")]
            if not contexto.get("semantico"):
                mensajes.append({"role": "user", "content": "Petición actual: " + (contexto.get("entrada") or getattr(tarea, "objetivo", ""))
                             + "\nResponde sin repetir la petición. Las preguntas anteriores ya contestadas no se vuelven a plantear."
                             + "\nDatos ya consultados; úsalos en la respuesta: " + json.dumps(observaciones[-3:], ensure_ascii=False)})

        if natural:
            mensajes = [{"role": "system", "content": sistema}]
            for h in contexto.get("historial", [])[-8:]:
                if "usuario" in h:
                    mensajes.append({"role": "user", "content": h["usuario"]})
                elif "asistente" in h:
                    mensajes.append({"role": "assistant", "content": h["asistente"]})
            actual = contexto.get("entrada") or getattr(tarea, "objetivo", "")
            if len(mensajes) == 1 or mensajes[-1]["role"] != "user" or mensajes[-1]["content"] != actual:
                mensajes.append({"role": "user", "content": actual})
        if nativo:
            for h in contexto.get("historial", [])[-6:]:
                if h.get("herramienta") and "resultado" in h:
                    mensajes.append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": h["herramienta"], "arguments": h.get("parametros", {})}}]})
                    mensajes.append({"role": "tool", "tool_name": h["herramienta"], "content": json.dumps(h["resultado"], ensure_ascii=False)[:5000]})
        respuesta = requests.post(
            self.config.OLLAMA_URL.rstrip("/") + "/api/chat",
            json={"model": modelo, "stream": True, **({"tools": contexto["contratos"]} if nativo else {} if natural else {"format": formato}),
                  "messages": mensajes,
                  "keep_alive": self.config.OLLAMA_KEEP_ALIVE,
                  "options": {"temperature": 0, "seed": 42, "num_predict": 1200,
                              "num_ctx": self.config.OLLAMA_NUM_CTX}},
            stream=True, timeout=(5, min(getattr(self.config, "AGENT_LOCAL_READ_TIMEOUT", 20) if contexto.get("semantico") else 8, timeout)))
        fin = time.monotonic() + timeout
        partes = []
        llamadas = []
        try:
            respuesta.raise_for_status()
            for linea in respuesta.iter_lines(chunk_size=1):
                if cancelar.is_set():
                    raise Cancelado("Tarea cancelada.")
                if time.monotonic() >= fin:
                    raise ErrorProveedor("Ollama tardó demasiado.")
                if linea:
                    bloque = json.loads(linea)
                    if bloque.get("error"):
                        raise ErrorProveedor("Ollama no pudo generar la respuesta.")
                    llamadas.extend(bloque.get("message", {}).get("tool_calls") or [])
                    partes.append(bloque.get("message", {}).get("content", ""))
                    if sum(map(len, partes)) > 20000:
                        raise ErrorProveedor("Respuesta de Ollama demasiado larga.")
            if nativo and llamadas:
                llamada = llamadas[0].get("function", {})
                return {"tipo": "herramienta", "accion": llamada.get("name"), "parametros": llamada.get("arguments", {})}
            texto = "".join(partes)
            if nativo:
                try:
                    return extraer_json(texto)
                except (ValueError, ErrorProveedor):
                    return {"tipo": "respuesta", "texto": texto.strip()}
            return {"tipo": "respuesta", "texto": texto.strip()} if natural else extraer_json(texto)
        finally:
            respuesta.close()


class ProveedorNvidia:
    """Inferencia SSE; nunca ejecuta herramientas ni expone razonamiento interno."""

    def __init__(self, config, modelo, *, clave=None, variable_clave="NVIDIA_API_KEY"):
        self.config = config
        self.modelo = modelo
        self.nombre = "NVIDIA"
        self.variable_clave = variable_clave
        self.clave = config.NVIDIA_API_KEY if clave is None else clave
        self.stream = True
        self.pensar = config.NVIDIA_THINKING_ENABLED

    def consultar(self, sistema, contexto, *, tarea, cancelar, timeout):
        if cancelar.is_set():
            raise Cancelado("Tarea cancelada.")
        if not self.clave:
            raise ErrorNvidia(f"Falta configurar {self.variable_clave}.")
        fin = time.monotonic() + timeout
        respuesta = None
        partes, longitud, terminado = [], 0, False
        if "herramientas_escritorio" in contexto:
            esquema = {"type": "object", "properties": {
                "tool": {"type": "string", "enum": contexto["herramientas_escritorio"]},
                "args": {"type": "object"}}, "required": ["tool", "args"], "additionalProperties": False}
        else:
            variantes = [{"type": "object", "properties": {
                "tipo": {"type": "string", "enum": ["respuesta", "pregunta"]},
                "texto": {"type": "string"}}, "required": ["tipo", "texto"], "additionalProperties": False}]
            if contexto.get("herramientas"):
                variantes.append({"type": "object", "properties": {
                    "tipo": {"const": "herramienta"},
                    "accion": {"type": "string", "enum": list(contexto["herramientas"])},
                    "parametros": {"type": "object"}},
                    "required": ["tipo", "accion", "parametros"], "additionalProperties": False})
            esquema = {"anyOf": variantes}
        if contexto.get("coherente"):
            from modules.coherent_agent import esquema_coherente
            esquema = esquema_coherente(contexto.get("contratos",[]))
        elif contexto.get("evaluar_pregunta"):
            esquema = esquema_pregunta()
        elif contexto.get("autorizar_operacion"):
            esquema = esquema_autorizacion()
        elif contexto.get("evaluar_objetivo"):
            esquema = esquema_evaluacion()
        elif "tarea_anterior" in contexto:
            esquema = esquema_ruta(contexto)
        elif contexto.get("semantico") and contexto.get("contratos"):
            esquema = esquema_herramientas(contexto["contratos"],contexto.get("permitir_respuesta",True),contexto.get("permitir_pregunta",True),contexto.get("permitir_limitacion",True))
        payload = {"model": self.modelo, "stream": self.stream,
                   "messages": [{"role": "system", "content": sistema},
                                {"role": "user", "content": json.dumps({k:v for k,v in contexto.items() if k != "contratos" and not (contexto.get("coherente") and k == "herramientas")}, ensure_ascii=False)}],
                   "temperature": 0, "top_p": 0.95, "seed": 42,
                   "max_tokens": self.config.NVIDIA_MAX_TOKENS,
                   "response_format": {"type": "json_schema", "json_schema": {
                       "name": "paso_limits", "schema": esquema}}}
        if contexto.get("semantico") and getattr(self, "razonamiento", None) and self.modelo.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = self.razonamiento
            if tarea.rol == "cotidiano" or contexto.get("autorizar_operacion") or contexto.get("evaluar_objetivo") or "tarea_anterior" in contexto:
                payload["max_tokens"] = min(payload["max_tokens"], 768)
        if self.pensar is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": self.pensar}
        try:
            respuesta = requests.post(
                self.config.NVIDIA_BASE_URL.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + self.clave,
                         "Accept": "text/event-stream" if self.stream else "application/json"},
                json=payload, stream=self.stream, timeout=(min(5, timeout), min(20, timeout)))
            if respuesta.status_code != 200:
                try:
                    espera = max(0, min(600, float(respuesta.headers.get("Retry-After", 0))))
                except (ValueError, TypeError):
                    espera = 0
                codigo = None
                if respuesta.status_code == 400:
                    try:
                        if respuesta.json().get("error", {}).get("code") == "json_validate_failed":
                            codigo = "json_validate_failed"
                    except (ValueError, AttributeError, TypeError):
                        pass
                # No incluir cuerpo, cabeceras ni excepción HTTP: pueden contener credenciales.
                raise ErrorNvidia(f"{self.nombre} no está disponible (HTTP {respuesta.status_code}).",
                                  espera=espera, estado=respuesta.status_code, codigo=codigo)
            def bloques():
                if not self.stream:
                    yield respuesta.json()
                    return
                for linea in respuesta.iter_lines(chunk_size=1):
                    if cancelar.is_set():
                        raise Cancelado("Tarea cancelada.")
                    if time.monotonic() >= fin:
                        raise ErrorNvidia(f"Se agotó el tiempo de {self.nombre}.")
                    if not linea or not linea.startswith(b"data:"):
                        continue
                    dato = linea[5:].strip()
                    if dato == b"[DONE]":
                        return
                    yield json.loads(dato)
            for bloque in bloques():
                if cancelar.is_set():
                    raise Cancelado("Tarea cancelada.")
                if time.monotonic() >= fin:
                    raise ErrorNvidia(f"Se agotó el tiempo de {self.nombre}.")
                if bloque.get("error"):
                    raise ErrorNvidia(f"{self.nombre} interrumpió la respuesta.")
                for eleccion in bloque.get("choices", []):
                    delta = eleccion.get("delta" if self.stream else "message", {})
                    if delta.get("tool_calls"):
                        raise ErrorNvidia("El modelo utilizó un formato de herramientas no admitido.")
                    contenido = delta.get("content") or ""
                    if not isinstance(contenido, str):
                        raise ErrorNvidia("NVIDIA devolvió contenido inválido.")
                    partes.append(contenido)
                    longitud += len(contenido)
                    if longitud > 65536:
                        raise ErrorNvidia(f"La respuesta de {self.nombre} superó el límite.")
                    motivo = eleccion.get("finish_reason")
                    if motivo and motivo != "stop":
                        raise ErrorNvidia(f"{self.nombre} no completó la decisión.")
                    terminado = terminado or motivo == "stop"
            if cancelar.is_set():
                raise Cancelado("Tarea cancelada.")
            if not terminado:
                raise ErrorNvidia(f"{self.nombre} devolvió una respuesta incompleta.")
            decision = extraer_json("".join(partes))
            tipo = decision.get("tipo")
            if "herramientas_escritorio" in contexto:
                valido = (decision.get("tool") in contexto["herramientas_escritorio"] and
                          isinstance(decision.get("args"), dict))
            elif contexto.get("coherente"):
                valido = (tipo == "plan" and isinstance(decision.get("pasos"),list)) or (tipo == "delegar" and decision.get("rol") in {"analisis","desarrollo","investigacion"}) or (tipo in {"respuesta","pregunta","limitacion"} and isinstance(decision.get("texto"),str))
            elif contexto.get("evaluar_pregunta"):
                valido = isinstance(decision.get("necesaria"),bool) and isinstance(decision.get("motivo"),str)
            elif contexto.get("autorizar_operacion"):
                valido = isinstance(decision.get("permitida"),bool) and isinstance(decision.get("motivo"),str)
            elif contexto.get("evaluar_objetivo"):
                valido = isinstance(decision.get("completo"),bool) and isinstance(decision.get("pendientes"),list) and isinstance(decision.get("evidencias"),list)
            elif "tarea_anterior" in contexto:
                valido = (decision.get("rol") in contexto.get("roles_permitidos", ["cotidiano","analisis","desarrollo","investigacion"])
                          and decision.get("modo") in {"leer","actuar","preparar"}
                          and isinstance(decision.get("continuar"),bool))
            elif tipo == "herramienta":
                valido = (decision.get("accion") in contexto.get("herramientas", {}) and
                          isinstance(decision.get("parametros"), dict))
            else:
                valido = tipo in {"respuesta", "pregunta", "limitacion"} and isinstance(decision.get("texto"), str) and bool(decision["texto"].strip())
            if not valido:
                raise ErrorNvidia(f"{self.nombre} no devolvió una decisión válida.")
            return decision
        except requests.RequestException:
            if cancelar.is_set():
                raise Cancelado("Tarea cancelada.") from None
            raise ErrorNvidia(f"Falló la conexión con {self.nombre}.") from None
        except (ValueError, TypeError, AttributeError):
            raise ErrorNvidia(f"{self.nombre} devolvió una respuesta inválida.") from None
        finally:
            if respuesta is not None:
                respuesta.close()


class ProveedorGlm(ProveedorNvidia):
    """GLM con su credencial propia y respuesta completa, como el ejemplo oficial."""

    def __init__(self, config):
        super().__init__(SimpleNamespace(NVIDIA_API_KEY=config.NVIDIA_GLM_API_KEY,
                                         NVIDIA_BASE_URL=config.NVIDIA_BASE_URL,
                                         NVIDIA_MAX_TOKENS=config.NVIDIA_MAX_TOKENS,
                                         NVIDIA_THINKING_ENABLED=False), config.NVIDIA_GLM_MODEL)
        self.variable_clave = "NVIDIA_GLM_API_KEY"
        self.stream = False
        self.pensar = None


class ProveedorGroq(ProveedorNvidia):
    """Groq usa JSON sin streaming; no recibe parámetros privados de NVIDIA."""

    def __init__(self, config, modelo=None):
        super().__init__(SimpleNamespace(NVIDIA_API_KEY=config.GROQ_API_KEY,
                                         NVIDIA_BASE_URL=config.GROQ_BASE_URL,
                                         NVIDIA_MAX_TOKENS=config.GROQ_MAX_TOKENS,
                                         NVIDIA_THINKING_ENABLED=False), modelo or config.GROQ_AGENT_MODEL)
        self.nombre = "Groq"
        self.variable_clave = "GROQ_API_KEY"
        self.stream = False
        self.pensar = None
        self.razonamiento = getattr(config, "GROQ_REASONING_EFFORT", "low")

    def consultar(self, sistema, contexto, *, tarea, cancelar, timeout):
        fin = time.monotonic() + timeout
        for intento in range(2):
            restante = fin - time.monotonic()
            if restante <= 0:
                raise ErrorNvidia("Se agotó el tiempo de Groq.")
            try:
                return super().consultar(sistema, contexto, tarea=tarea, cancelar=cancelar, timeout=restante)
            except ErrorNvidia as error:
                if contexto.get("semantico") and error.estado == 429:
                    raise
                restante = fin - time.monotonic()
                if not intento and error.estado == 400 and error.codigo == "json_validate_failed" and restante > 1:
                    sistema += ('\nCorrige el formato: devuelve un solo objeto JSON, sin explicaciones externas. '
                                'Para herramientas usa {"tipo":"herramienta","accion":"nombre del catálogo","parametros":{}}; '
                                'para texto usa {"tipo":"respuesta","texto":"resultado"}.')
                    continue
                if intento or error.estado != 429 or not 0 < error.espera < restante - 1:
                    raise
                # Una única repetición de inferencia; nunca repite herramientas.
                if cancelar.wait(error.espera):
                    raise Cancelado("Tarea cancelada.") from None


class ProveedorConRespaldo:
    """Prioridad fija; consulta el respaldo únicamente si falla el principal."""

    def __init__(self, proveedores, *, enfriamiento=60):
        self.proveedores = tuple(proveedores)
        self.enfriamiento = enfriamiento
        self._lock = threading.Lock()
        self._hasta = {}
        self.ultimo_modelo = None

    def consultar(self, sistema, contexto, *, tarea, cancelar, timeout):
        fin = time.monotonic() + timeout
        if cancelar.is_set():
            raise Cancelado("Tarea cancelada.")
        with self._lock:
            cantidad = len(self.proveedores)
            orden = range(cantidad)
            candidatos = [i for i in orden if self._hasta.get(i, 0) <= time.monotonic()]
        if not candidatos:
            raise ErrorProveedor("Los proveedores de este rol están temporalmente indisponibles; inténtalo más tarde.")
        for posicion, indice in enumerate(candidatos):
            if cancelar.is_set():
                raise Cancelado("Tarea cancelada.")
            restante = fin - time.monotonic()
            if restante <= 0:
                break
            proveedor = self.proveedores[indice]
            try:
                decision = proveedor.consultar(sistema, contexto, tarea=tarea, cancelar=cancelar,
                                               timeout=restante / (len(candidatos) - posicion))
                if cancelar.is_set():
                    raise Cancelado("Tarea cancelada.")
            except Cancelado:
                raise
            except ErrorProveedor as error:
                with self._lock:
                    self._hasta[indice] = time.monotonic() + max(self.enfriamiento, getattr(error, "espera", 0))
                log.warning("especialista no disponible modelo=%s error=%s estado=%s codigo=%s; probando siguiente",
                            proveedor.modelo, type(error).__name__, getattr(error,"estado",None), getattr(error,"codigo",None))
                continue
            with self._lock:
                self.ultimo_modelo = proveedor.modelo
                self._hasta.pop(indice, None)
            log.info("especialista seleccionado modelo=%s", proveedor.modelo)
            return decision
        raise ErrorProveedor("Ningún proveedor de este rol pudo completar este paso; la tarea conserva su estado.")


def crear_cotidiano(config):
    modelos = [config.GROQ_AGENT_MODEL]
    respaldo = getattr(config, "AGENT_COGNITIVE_FALLBACK_MODEL", "openai/gpt-oss-20b")
    if respaldo and respaldo not in modelos:
        modelos.append(respaldo)
    return ProveedorConRespaldo([ProveedorGroq(config,m) for m in modelos],
                               enfriamiento=config.NVIDIA_MODEL_COOLDOWN)


def crear_respaldos(config):
    """Listas por rol; proveedores nuevos solo tras habilitarlos explícitamente."""
    desarrollo = [ProveedorNvidia(config, config.NVIDIA_DEVELOPMENT_MODEL)]
    analisis = [ProveedorNvidia(config, config.NVIDIA_ANALYSIS_MODEL,
                               clave=config.NVIDIA_BOLT_API_KEY or config.NVIDIA_API_KEY)]
    if config.AGENT_SUPER_FALLBACK:
        analisis.insert(0, ProveedorNvidia(config, config.NVIDIA_SUPER_MODEL,
                                          clave=config.NVIDIA_SUPER_API_KEY, variable_clave="NVIDIA_SUPER_API_KEY"))
    if config.AGENT_GLM_FALLBACK:
        desarrollo.insert(0, ProveedorGlm(config))
    if config.AGENT_GROQ_FALLBACK:
        desarrollo.append(ProveedorGroq(config))
        analisis.append(ProveedorGroq(config))
    return {"desarrollo": desarrollo, "analisis": analisis}


class ProveedorOpenCode:
    """OpenCode V2 decide; las herramientas reales pasan por el coordinador."""

    def __init__(self, binario, modelo, directorio):
        self.binario = str(Path(binario).expanduser()) if "/" in binario else binario
        self.modelo = modelo
        self.directorio = Path(directorio)

    def consultar(self, sistema, contexto, *, tarea, cancelar, timeout):
        if not self.modelo:
            raise ErrorProveedor("Este especialista está desactivado.")
        carpeta = self.directorio / tarea.id / tarea.rol
        carpeta.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Agente propio: no hereda herramientas, shell, preguntas ni subagentes.
        configuracion = {"model": self.modelo, "default_agent": "limits-modelo", "agents": {"limits-modelo": {
            "mode": "primary", "system": sistema,
            "permissions": [{"action": "*", "resource": "*", "effect": "deny"}]}},
            "policies": [{"action": "tool.use", "resource": "*", "effect": "deny"}],
            "snapshots": False}
        ruta = carpeta / "opencode.json"
        ruta.write_text(json.dumps(configuracion, ensure_ascii=False), encoding="utf-8")
        ruta.chmod(0o600)
        argumentos = [self.binario, "run", "--standalone", "--format", "json",
                      "--agent", "limits-modelo", "--model", self.modelo]
        sesion = tarea.sesiones_modelos.get(tarea.rol)
        if sesion:
            argumentos += ["--session", sesion]
        argumentos.append(json.dumps(contexto, ensure_ascii=False))
        codigo, salida, _ = ejecutar_proceso(argumentos, cwd=carpeta,
                                           cancelar=cancelar, timeout=timeout)
        partes = []
        for linea in salida.splitlines():
            try:
                evento = json.loads(linea)
            except ValueError:
                continue
            if evento.get("sessionID"):
                tarea.sesiones_modelos[tarea.rol] = evento["sessionID"]
            if evento.get("type") == "error":
                error = evento.get("error", {})
                estado = error.get("status") if isinstance(error, dict) else None
                raise ErrorProveedor("OpenCode no está disponible" + (f" ({estado})." if estado else "."))
            if evento.get("type") == "text":
                partes.append(evento.get("part", {}).get("text", ""))
        if codigo or not partes:
            raise ErrorProveedor("OpenCode no devolvió una respuesta utilizable.")
        return extraer_json("".join(partes))
