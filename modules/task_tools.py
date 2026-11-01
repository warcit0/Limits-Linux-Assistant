"""Herramientas con evidencia, alcance de archivos y pruebas aisladas."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import re
import shlex
import shutil
import tempfile

from modules.agent_providers import ejecutar_proceso, ErrorProveedor
from modules.grounding import check


LECTURAS = {"get_system_info", "get_volume", "get_time", "list_running_apps",
            "get_current_song", "get_lyrics", "memory_stats", "workspace_list", "search_file", "list_directory"}
ACCIONES = {"open_application", "close_application", "set_volume", "set_brightness",
            "media_control", "focus_window", "lock_screen", "shutdown", "reboot",
            "copy_file", "move_file", "rename_file", "open_file", "workspace_switch", "workspace_back", "workspace_move"}
from modules.operational import NOMBRES
ACCIONES |= NOMBRES
from modules.capability_tools import Capacidades, LECTURAS_CAP, ACCIONES_CAP
LECTURAS |= LECTURAS_CAP | {"memory_list", "memory_recall", "git_status", "docker_status", "list_tvs"}
ACCIONES |= {"remember", "forget", "reveal_file", "reveal_last", "open_last"}
ACCIONES |= ACCIONES_CAP | {"web_search", "open_url", "spotify_play", "youtube_play", "tv_cast", "tv_control"}

SENSIBLES = {"shutdown", "reboot", "move_file", "rename_file", "aplicar_script"}
PERSONALES = {".env", ".ssh", ".gnupg", ".aws", ".config", ".limits", ".codex",
              ".agents", ".git", "limits-env", "node_modules", "__pycache__"}


def huella(valor):
    datos = valor if isinstance(valor, bytes) else json.dumps(valor, sort_keys=True,
                                                            ensure_ascii=False).encode()
    return hashlib.sha256(datos).hexdigest()


def _privada(ruta):
    return any(p in PERSONALES or p.startswith(".env.") for p in ruta.parts)


def extraer_raices(texto):
    """Solo rutas escritas por el usuario o carpetas conocidas nombradas."""
    try:
        tokens = shlex.split(texto)
    except ValueError:
        tokens = texto.split()
    rutas = []
    for token in tokens:
        token = token.strip("¿?¡!,:;")
        if token.startswith(("~/", "/")):
            ruta = Path(token).expanduser()
            if not ruta.exists():
                ruta = Path(token.rstrip(".)]")).expanduser()
            if ruta.exists() and not _privada(ruta) and ruta.resolve() not in {Path("/"), Path.home()}:
                rutas.append(str(ruta.resolve()))
    for nombre in ("Descargas", "Downloads", "Documentos", "Documents", "Escritorio", "Desktop"):
        if re.search(r"\b" + nombre + r"\b", texto, re.I):
            ruta = Path.home() / nombre
            if ruta.is_dir():
                rutas.append(str(ruta.resolve()))
    return list(dict.fromkeys(rutas))


def huella_autorizacion(tarea, nombre, parametros):
    return huella({"objetivo":tarea.objetivo,"revision":tarea.revision,
                   "accion":nombre,"parametros":parametros})


class HerramientasTarea:
    def __init__(self, executor, almacen, limite_lectura=16000):
        self.executor = executor
        self.almacen = almacen
        self.limite_lectura = limite_lectura
        self.operaciones = None
        self.capacidades = Capacidades(self)

    def catalogo(self, tarea):
        catalogo = {
            "listar_carpeta": "(ruta:str) lista hasta 100 entradas de una raíz autorizada; obtiene rutas observadas.",
            "leer_archivo": "(ruta:str, inicio:int=0) lee una parte acotada del texto observado; siguiente indica el próximo desplazamiento en bytes.",
        }
        if not tarea.raices:
            catalogo.clear()
        for nombre in sorted(LECTURAS | (ACCIONES if tarea.modo == "actuar" else set())):
            handler = self.executor.action_map.get(nombre)
            if handler:
                catalogo[nombre] = str(inspect.signature(handler)) + " " + " ".join((inspect.getdoc(handler) or "").split())[:320]
                if tarea.semantica and nombre == "media_control":
                    catalogo[nombre] = "(action:str, player:str opcional) play reanuda, pause pausa, next siguiente, previous anterior, stop detiene. Nunca alterna: elige el estado solicitado explícitamente."
                if tarea.semantica and nombre == "spotify_play":
                    catalogo[nombre] = "(query:str) busca y solicita reproducir contenido en Spotify por artista, canción o género. query requiere una canción, artista o género indicado por el usuario; no inventar una consulta genérica. Una orden de activar/reanudar la reproducción sin contenido nuevo corresponde a media_control action play."
        if tarea.rol in {"desarrollo", "cotidiano"} and tarea.modo in {"preparar", "actuar"}:
            catalogo.update({
                "preparar_script": "(nombre:str, contenido:str) crea un script Python en la carpeta privada de la tarea. Usa /datos como carpeta de entrada. No se ejecuta en el host.",
                "probar_script": "(script:str, ruta:str) ejecuta el script sobre una copia temporal de la raíz autorizada; devuelve salida y cambios comprobados.",
                "aplicar_script": "(script:str, ruta:str) propone aplicar EXACTAMENTE el script probado a la raíz original; requiere confirmación del usuario, incluso en modo preparar.",
            })
        if self.operaciones and tarea.modo == "actuar":
            for paso in tarea.plan_operativo:
                if paso["accion"].startswith("operacion_"):
                    catalogo[paso["accion"]] = "Paso explícito del plan del usuario; parámetros vinculados a su petición."
        if tarea.semantica:
            catalogo.update(self.capacidades.catalogo(tarea))
        if getattr(tarea,"coherente",False):
            from modules.capability_tools import FAMILIAS
            comunes = {"consultar_capacidades","consultar_ventanas","consultar_escritorio",
                       "buscar_aplicaciones","abrir_aplicacion",
                       "get_volume","get_system_info","get_current_song","set_volume",
                       "set_brightness","media_control","spotify_play","open_application",
                       "close_application","workspace_switch","workspace_back","get_time","enfocar_ventana","mover_ventana","cerrar_ventana",
                       "ocultar_especial","buscar_proyectos","abrir_proyecto"}
            for familia in tarea.capacidades:
                comunes.update(FAMILIAS.get(familia,set()))
            if tarea.raices:
                comunes.update({"listar_carpeta","leer_archivo"})
            if tarea.rol == "desarrollo":
                comunes.update(FAMILIAS["desarrollo"])
            if getattr(tarea,"cotidiano_local",False) and tarea.rol == "cotidiano":
                comunes.update({'youtube_play','web_search','focus_window'})
                comunes.discard('consultar_ventanas')  # consultar_escritorio ya obtiene ventanas, foco y especiales.
                if getattr(tarea,'conversacional',False):
                    comunes.update({'buscar_memoria','memory_recall','memory_list','memory_stats','remember','forget'})
                    # Un solo contrato de foco: dirección observada, sin lanzar apps.
                    comunes.discard('focus_window')
                from commands.apps import AppCommands
                if not AppCommands.disponibles():
                    comunes -= {'open_application','close_application','focus_window'}
                if 'open_application' in catalogo:
                    catalogo['open_application'] = '(app:str) abre SOLO una app conocida: '+', '.join(AppCommands.disponibles())+'. Para otras usa buscar_aplicaciones y abrir_aplicacion. No acepta argumentos extra.'
                if getattr(getattr(self,"config",None),"SPOTIFY_MCP_ENABLED",False):
                    comunes.update({"spotify_buscar","spotify_estado","spotify_reproducir","spotify_control"})
                    comunes.discard("spotify_play")
            catalogo = {k:v for k,v in catalogo.items() if k in comunes}
            if getattr(tarea,"cotidiano_local",False) and re.search(r"\b(?:solo local|sin internet|sin nube)\b", tarea.objetivo, re.I):
                catalogo = {k:v for k,v in catalogo.items() if not k.startswith("spotify_") and k not in {"web_search","open_url","youtube_play","tv_cast"}}
        if tarea.semantica and not getattr(tarea,"coherente",False):
            from modules.capability_tools import FAMILIAS
            permitidas = {"consultar_capacidades", "buscar_memoria"}
            if tarea.seleccion_herramientas:
                permitidas.update(tarea.seleccion_herramientas)
            else:
                for familia in tarea.capacidades:
                    permitidas.update(FAMILIAS.get(familia, set()))
            catalogo = {k:v for k,v in catalogo.items() if k in permitidas}
        if getattr(tarea,"cotidiano_local",False) and tarea.rol == 'cotidiano':
            # El catálogo describe contratos estables. Los destinos se verifican al ejecutar.
            directa = tarea.entidades.get('orden_rapida',{})
            nombre = directa.get('action')
            if nombre in self.executor.action_map:
                handler = self.executor.action_map[nombre]
                catalogo[nombre] = str(inspect.signature(handler))+' '+(inspect.getdoc(handler) or '')[:320]
        return catalogo

    def contratos(self, tarea):
        """Deriva esquemas del catálogo real para llamadas nativas de herramientas."""
        from modules.capability_tools import CAMPOS
        from modules.grounding import PARAM_ENUMS
        contratos = []
        internos = {"listar_carpeta": {"ruta"}, "leer_archivo": {"ruta", "inicio"},
                    "preparar_script": {"nombre", "contenido"}, "probar_script": {"script", "ruta"},
                    "aplicar_script": {"script", "ruta"}}
        for nombre, descripcion in self.catalogo(tarea).items():
            propiedades, requeridos = {}, []
            handler = self.executor.action_map.get(nombre)
            from modules.spotify_mcp import CONTRATOS as SPOTIFY_CONTRATOS
            spotify = next((c for c in SPOTIFY_CONTRATOS if c["name"] == nombre),None)
            if spotify:
                contratos.append({"type":"function","function":{"name":nombre,"description":descripcion,"parameters":spotify["inputSchema"]}})
                continue
            if handler:
                for campo, p in inspect.signature(handler).parameters.items():
                    if getattr(tarea,'cotidiano_local',False) and ((nombre == 'open_application' and campo == 'args') or (nombre == 'media_control' and campo == 'verify')):
                        continue
                    tipo = str(p.annotation)
                    base = "integer" if "int" in tipo else "number" if "float" in tipo else "boolean" if "bool" in tipo else "string"
                    propiedades[campo] = {"type": base}
                    if nombre in {'open_application','close_application','focus_window'} and campo == 'app' and getattr(tarea,'cotidiano_local',False):
                        from commands.apps import AppCommands
                        propiedades[campo]['enum'] = sorted(AppCommands.disponibles())
                    if base == "string" and not (nombre == "remember" and campo == "key"): propiedades[campo]["minLength"] = 1
                    if campo in PARAM_ENUMS.get(nombre, {}):
                        propiedades[campo]["enum"] = [v for v in PARAM_ENUMS[nombre][campo] if not (nombre == "media_control" and v == "play-pause")]
                    if p.default is inspect.Parameter.empty or (nombre in ACCIONES and campo in {"action","level","query","target","app"}):
                        requeridos.append(campo)
            else:
                for campo in CAMPOS.get(nombre, internos.get(nombre, set())):
                    propiedades[campo] = {"type": "integer", "minimum": 0} if campo == "inicio" else {"type": "string", "minLength": 1}
                    if campo != "inicio" and not (nombre == "consultar_escritorio" and campo == "workspace"): requeridos.append(campo)
            contratos.append({"type": "function", "function": {"name": nombre, "description": descripcion,
                "parameters": {"type": "object", "properties": propiedades, "required": requeridos, "additionalProperties": False}}})
        return contratos

    @staticmethod
    def validar_ruta(tarea, valor, *, observada=False):
        if not isinstance(valor, str) or not valor or len(valor) > 4096:
            raise ValueError("Indica una ruta válida.")
        original = Path(valor).expanduser()
        ruta = original.resolve()
        if _privada(original) or _privada(ruta) or original.is_symlink():
            raise ValueError("La ruta es privada o un enlace simbólico.")
        if not any(ruta == Path(r) or ruta.is_relative_to(Path(r)) for r in tarea.raices):
            raise ValueError("Ruta fuera del alcance indicado. Pide al usuario la carpeta concreta.")
        if observada and str(ruta) not in tarea.observadas and str(ruta) not in tarea.raices:
            raise ValueError("Primero observa el archivo con listar_carpeta.")
        return ruta

    def normalizar_parametros(self,nombre,parametros):
        from modules.argument_contracts import normalizar_argumentos
        handler = self.executor.action_map.get(nombre)
        p = normalizar_argumentos(handler,parametros) if handler else parametros
        if nombre in {'open_application','close_application','focus_window'} and isinstance(p,dict):
            from modules.app_router import resolver_aplicacion
            p = {**p,'app':resolver_aplicacion(p.get('app','')) or p.get('app','')}
        return p

    def validar(self, tarea, nombre, parametros):
        parametros = self.normalizar_parametros(nombre,parametros)
        if nombre not in self.catalogo(tarea) or not isinstance(parametros, dict):
            raise ValueError("Herramienta o parámetros no permitidos para esta tarea.")
        if tarea.semantica and nombre in self.capacidades.catalogo(tarea):
            return self.capacidades.validar(tarea, nombre, parametros)
        if nombre.startswith("operacion_"):
            if not self.operaciones or not any(p["accion"] == nombre and p["parametros"] == parametros for p in tarea.plan_operativo):
                raise ValueError("La operación no está autorizada por este plan.")
            return parametros
        if (nombre in {"probar_script", "aplicar_script"} and parametros.get("ruta") == "/datos"
                and len(tarea.raices) == 1):
            # /datos es el alias enseñado para el sandbox, no una raíz nueva.
            parametros = {**parametros, "ruta": tarea.raices[0]}
        propios = {"listar_carpeta": {"ruta"}, "leer_archivo": {"ruta"},
                   "preparar_script": {"nombre", "contenido"},
                   "probar_script": {"script", "ruta"}, "aplicar_script": {"script", "ruta"}}
        if nombre in propios:
            if nombre == "leer_archivo" and set(parametros).issubset({"ruta", "inicio"}) and "ruta" in parametros:
                if not isinstance(parametros["ruta"], str) or type(parametros.get("inicio", 0)) is not int or parametros.get("inicio", 0) < 0:
                    raise ValueError("Indica una ruta y un desplazamiento entero no negativo.")
                self.validar_ruta(tarea, parametros["ruta"], observada=True)
                return parametros
            if set(parametros) != propios[nombre] or not all(isinstance(v, str) for v in parametros.values()):
                raise ValueError("Los parámetros no coinciden con la herramienta.")
            if "ruta" in parametros:
                self.validar_ruta(tarea, parametros["ruta"], observada=nombre == "leer_archivo")
            if nombre in {"probar_script", "aplicar_script"}:
                self._script(tarea, parametros["script"])
            return parametros
        if tarea.semantica and nombre in {"open_application","close_application"}:
            from commands.apps import AppCommands
            from modules.app_router import resolver_aplicacion
            app = resolver_aplicacion(parametros.get('app','')) or str(parametros.get('app','')).lower()
            parametros = {**parametros,'app':app}
            if app not in AppCommands.APP_MAP or (getattr(tarea,"cotidiano_local",False) and app not in AppCommands.disponibles()):
                raise ValueError("Aplicación desconocida; consulta las aplicaciones o ventanas reales antes de elegir el destino.")
            if getattr(tarea,"cotidiano_local",False) and nombre == "open_application" and set(parametros) != {"app"}:
                raise ValueError("Para abrir una app conocida usa solo app. No se aceptan argumentos extra.")
        if tarea.semantica and nombre == "media_control" and parametros.get("action") == "play-pause":
            raise ValueError("Esta herramienta requiere un estado explícito: play para reanudar, pause para pausar. Consulta el estado si necesitas alternarlo.")
        if tarea.semantica and nombre in ACCIONES:
            obligatorios = {"media_control": {"action"}, "set_volume": {"level"}, "set_brightness": {"level"}}
            if not obligatorios.get(nombre, set()).issubset(parametros):
                raise ValueError("Indica explícitamente los parámetros de la operación; no se usan valores por defecto para una orden.")
        if getattr(tarea,"cotidiano_local",False) and nombre in {"search_file","list_directory","open_file"}:
            if not parametros.get("path"):
                raise ValueError("Indica una carpeta del usuario o una ruta observada; no se buscará en todo HOME por defecto.")
            self.validar_ruta(tarea,parametros["path"],observada=nombre == "open_file")
            ruta = Path(parametros["path"])
            if nombre == "open_file" and (ruta.suffix.lower() in {".desktop",".appimage",".sh",".run"} or ruta.is_file() and ruta.stat().st_mode & 0o111):
                raise ValueError("No abriré un ejecutable como si fuera un documento. Usa una aplicación instalada o el flujo de scripts.")
        if tarea.semantica and nombre == "media_control" and (parametros.get("action") == "play" or getattr(tarea,"coherente",False)):
            parametros = {**parametros, "verify": True}
        handler = self.executor.action_map[nombre]
        inspect.signature(handler).bind(**parametros)
        if any(not isinstance(v, (str, int, float, bool, type(None))) for v in parametros.values()):
            raise ValueError("Parámetro de comando con tipo inválido.")
        if tarea.semantica:
            for campo, valor in parametros.items():
                if isinstance(valor, str) and ((not valor.strip() and not (nombre == "remember" and campo == "key")) or len(valor) > 4000):
                    raise ValueError(f"El parámetro {campo} debe ser texto no vacío de hasta 4000 caracteres.")
        prueba = tarea.semantica and tarea.autorizaciones_semanticas.get(huella_autorizacion(tarea,nombre,parametros)) is True
        # En conversación la intención la decide el interlocutor. Grounding conserva
        # catálogo/enums; no vuelve a interpretar frases mediante hints/exclusiones.
        veredicto = check(nombre, parametros, '' if getattr(tarea,'conversacional',False) else tarea.objetivo, self.executor.action_map, semantic_evidence=prueba)
        if not veredicto.ok:
            raise ValueError("La acción no tiene evidencia en el objetivo autorizado.")
        for campo in ("path", "source", "destination"):
            if campo in parametros:
                self.validar_ruta(tarea, parametros[campo], observada=campo != "destination")
        return veredicto.params

    def ejecutar(self, tarea, nombre, parametros, cancelar):
        parametros = self.validar(tarea, nombre, parametros)
        if cancelar.is_set():
            raise ErrorProveedor("Tarea cancelada.")
        if tarea.semantica and nombre in self.capacidades.catalogo(tarea):
            return self.capacidades.ejecutar(tarea, nombre, parametros, cancelar)
        if nombre.startswith("operacion_"):
            return self.operaciones.ejecutar(tarea, nombre, parametros, cancelar)
        if nombre == "listar_carpeta":
            ruta = self.validar_ruta(tarea, parametros["ruta"])
            entradas = []
            for p in sorted(ruta.iterdir())[:200]:
                if p.is_symlink() or _privada(p) or p.name.startswith("."):
                    continue
                entradas.append({"ruta": str(p.resolve()), "tipo": "carpeta" if p.is_dir() else "archivo"})
                if len(entradas) >= 100:
                    break
            tarea.observadas = list(dict.fromkeys(tarea.observadas + [e["ruta"] for e in entradas]))[-400:]
            return {"ok": True, "verificado": True, "datos": entradas, "evidencia": str(ruta)}
        if nombre == "leer_archivo":
            ruta = self.validar_ruta(tarea, parametros["ruta"], observada=True)
            with ruta.open("rb") as f:
                f.seek(parametros.get("inicio", 0))
                contenido = f.read(self.limite_lectura + 1)
            if b"\x00" in contenido:
                raise ValueError("El archivo no es texto.")
            return {"ok": True, "verificado": True, "datos": contenido[:self.limite_lectura].decode("utf-8", "replace"),
                    "truncado": len(contenido) > self.limite_lectura, "evidencia": str(ruta),
                    "siguiente": parametros.get("inicio", 0) + self.limite_lectura if len(contenido) > self.limite_lectura else None}
        if nombre == "preparar_script":
            nombre_archivo = parametros["nombre"]
            if not re.fullmatch(r"[\w-]{1,80}\.py", nombre_archivo):
                raise ValueError("El nombre debe ser un archivo .py sin directorios.")
            contenido = parametros["contenido"]
            if len(contenido.encode()) > 64000:
                raise ValueError("El script supera 64 KB.")
            compile(contenido, nombre_archivo, "exec")
            ruta = self.almacen.carpeta(tarea) / nombre_archivo
            ruta.write_text(contenido, encoding="utf-8")
            ruta.chmod(0o600)
            if str(ruta) not in tarea.artefactos:
                tarea.artefactos.append(str(ruta))
            tarea.revision += 1
            tarea.pendiente = None
            tarea.pruebas.clear()
            return {"ok": True, "datos": {"script": str(ruta), "sha256": huella(ruta.read_bytes())}, "verificado": "sintaxis"}
        if nombre in {"probar_script", "aplicar_script"}:
            return self._ejecutar_script(tarea, parametros, cancelar, aplicar=nombre == "aplicar_script")
        # Los handlers originales siguen protegidos por firma y grounding.
        from modules.presence import actividad
        with actividad("ejecutando"):
            handler = self.executor.action_map[nombre]
            sistema = getattr(handler,'__self__',None)
            if nombre == 'media_control' and hasattr(sistema,'_control_multimedia'):
                resultado = sistema._control_multimedia(**parametros,cancelar=cancelar)
            else:
                resultado = handler(**parametros)
        if nombre == "search_file":
            for ruta in self.executor.files.last_matches:
                try:
                    observada = self.validar_ruta(tarea,ruta)
                    if str(observada) not in tarea.observadas:
                        tarea.observadas.append(str(observada))
                except ValueError:
                    continue
        from modules.command_result import ResultadoComando, normalizar_resultado
        if getattr(tarea,"coherente",False):
            return normalizar_resultado(resultado,lectura=nombre in LECTURAS)
        if isinstance(resultado, ResultadoComando):
            return {"ok": resultado.ok is not False, "datos": str(resultado), "verificado": resultado.verificado,
                    "estado": "comprobado" if resultado.verificado else "solicitado" if resultado.ok is not False else "error"}
        texto = str(resultado or "Solicitud enviada al sistema.")
        error = bool(re.search(r"^(?:no pude|no puedo|error)\b", texto.strip(), re.I)) or (nombre not in LECTURAS and bool(re.search(r"^(?:no\b|error\b|ocurri[oó]\b|⚠)", texto.strip(), re.I)))
        return {"ok": not error, "datos": texto,
                "verificado": nombre in LECTURAS or (nombre.startswith("workspace_") and not error) or (nombre == "media_control" and parametros.get("verify") is True and not error),
                "estado": "error" if error else "observado" if nombre in LECTURAS else "solicitado"}

    def _script(self, tarea, valor):
        ruta = Path(valor).expanduser().resolve()
        if str(ruta) not in tarea.artefactos or ruta.parent != self.almacen.carpeta(tarea).resolve() or ruta.suffix != ".py":
            raise ValueError("El script no pertenece a esta tarea.")
        return ruta

    def inventario(self, raiz):
        """Rechaza árboles que no se puedan copiar y comparar con límites claros."""
        resultado = {}
        total = 0
        for p in sorted(raiz.rglob("*")):
            relativo = p.relative_to(raiz)
            if len(resultado) >= 200:
                raise ValueError("Usa una carpeta de hasta 200 entradas para probar el script.")
            if p.is_symlink() or _privada(relativo) or any(c.startswith(".") for c in relativo.parts):
                raise ValueError("La carpeta contiene enlaces o archivos privados; usa una carpeta de trabajo específica.")
            if p.is_file():
                total += p.stat().st_size
                if total > 5_000_000 or len(resultado) >= 200:
                    raise ValueError("Usa una carpeta de hasta 200 archivos y 5 MB para probar el script.")
                resultado[str(relativo)] = huella(p.read_bytes())
            elif p.is_dir():
                resultado[str(relativo) + "/"] = "carpeta"
            else:
                raise ValueError("La carpeta contiene un archivo especial.")
        return resultado

    def _ejecutar_script(self, tarea, parametros, cancelar, *, aplicar):
        script = self._script(tarea, parametros["script"])
        raiz = self.validar_ruta(tarea, parametros["ruta"])
        if not raiz.is_dir():
            raise ValueError("Indica una carpeta de datos.")
        antes = self.inventario(raiz)
        clave = huella({"script": huella(script.read_bytes()), "raiz": str(raiz), "datos": antes})
        if aplicar and clave not in tarea.pruebas:
            raise ValueError("El script o los datos cambiaron: vuelve a probar antes de aprobar.")
        if not shutil.which("bwrap"):
            raise ValueError("No está disponible el aislamiento bwrap; el script no se ejecutó.")
        with tempfile.TemporaryDirectory(prefix="limits-script-") as temporal:
            copia = Path(temporal) / "datos"
            if aplicar:
                objetivo = raiz
            else:
                shutil.copytree(raiz, copia)
                objetivo = copia
            # Únicamente runtime de Python y la carpeta de datos: sin HOME ni red.
            cmd = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
                   "--clearenv", "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/tmp",
                   "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                   "--ro-bind", "/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
                   "--tmpfs", "/tmp", "--bind", str(objetivo), "/datos",
                   "--ro-bind", str(script), "/script.py", "--chdir", "/datos",
                   "--", "/usr/bin/python", "-I", "-c",
                   "import resource,runpy; resource.setrlimit(resource.RLIMIT_CPU,(8,8)); "
                   "resource.setrlimit(resource.RLIMIT_AS,(536870912,536870912)); "
                   "resource.setrlimit(resource.RLIMIT_FSIZE,(5000000,5000000)); "
                   "resource.setrlimit(resource.RLIMIT_NPROC,(32,32)); runpy.run_path('/script.py',run_name='__main__')"]
            codigo, salida, errores = ejecutar_proceso(cmd, cancelar=cancelar, timeout=12)
            despues = self.inventario(objetivo)
            cambios = [p for p in sorted(set(antes) | set(despues)) if antes.get(p) != despues.get(p)]
            resultado = {"ok": codigo == 0, "codigo": codigo, "datos": salida[:4000],
                         "error": errores[:1500], "cambios": cambios, "sha256": huella(script.read_bytes()),
                         "raiz": str(raiz), "aplicado": aplicar, "verificado": True}
            if codigo == 0 and not aplicar:
                tarea.pruebas[clave] = {"revision": tarea.revision, "cambios": cambios,
                                       "script": str(script), "raiz": str(raiz)}
            return resultado
