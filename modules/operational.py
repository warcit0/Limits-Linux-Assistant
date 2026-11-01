"""Planes cotidianos vinculados a la petición y resultados observables."""

import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

from modules.operation_intent import (
    es_orden,
    normalizar,
    orden_limpia,
    referencia_explicita,
)
from modules.workspace_router import match_workspace_route

NOMBRES = {
    "workspace_switch",
    "operacion_abrir_proyecto",
    "operacion_enfocar",
    "operacion_abrir_app",
    "operacion_youtube",
    "operacion_reanudar",
}
PRIVADOS = {
    ".env",
    ".ssh",
    ".config",
    ".limits",
    ".codex",
    ".agents",
    ".git",
    "node_modules",
    "limits-env",
    ".venv",
}


def clave(texto):
    texto = re.sub(r"([a-z])([A-Z])", r"\1 \2", texto)
    return re.sub(r"[^a-z0-9]", "", normalizar(texto).replace(" de ", " "))


def resultado(texto, *, ok=True, verificado=False, referente=None, aclaracion=False):
    return {
        "ok": ok,
        "datos": texto,
        "verificado": verificado,
        "estado": "aclaracion"
        if aclaracion
        else "comprobado"
        if verificado
        else "solicitado"
        if ok
        else "error",
        **({"referente": referente} if referente else {}),
    }


class Operaciones:
    def __init__(self, config, executor):
        self.config, self.executor = config, executor

    def planificar(self, entrada, anterior=None):
        t = orden_limpia(entrada)
        referente = (
            anterior.referente
            if anterior and anterior.estado not in {"cancelada", "sustituida"}
            else {}
        )
        if referencia_explicita(entrada) and re.match(
            r"(?:abrelo|abremelo|muestramelo)\b", t
        ):
            if not referente:
                return [
                    {
                        "accion": "operacion_abrir_proyecto",
                        "parametros": {"nombre": "", "editor": "code"},
                    }
                ]
            pasos = []
            espacio = re.search(r"(?:espacio de trabajo|workspace|work space) (\d+)", t)
            if espacio:
                pasos.append(
                    {
                        "accion": "workspace_switch",
                        "parametros": {
                            "target": ("10" if espacio[1] == "0" else espacio[1])
                        },
                    }
                )
            if referente.get("tipo") == "proyecto":
                pasos.append(
                    {
                        "accion": "operacion_abrir_proyecto",
                        "parametros": {
                            "nombre": referente["nombre"],
                            "editor": "code",
                            **(
                                {
                                    "workspace": (
                                        "10" if espacio[1] == "0" else espacio[1]
                                    )
                                }
                                if espacio
                                else {}
                            ),
                        },
                    }
                )
            elif referente.get("tipo") == "aplicacion":
                pasos.append(
                    {
                        "accion": "operacion_abrir_app",
                        "parametros": {"app": referente["app"]},
                    }
                )
            return pasos or None
        if referente.get("tipo") == "youtube" and re.match(
            r"(?:un |el )?video (?:sobre|de)\b", t
        ):
            return [
                {
                    "accion": "operacion_youtube",
                    "parametros": {
                        "query": re.sub(r"^(?:un |el )?video (?:sobre|de)\s+", "", t),
                        "app": referente["app"],
                    },
                }
            ]
        if not es_orden(entrada):
            return None
        partes = re.split(
            r"\s+y\s+(?=(?:abre|busca|reproduce|reanuda|mueve|cambia|enfoca)\b)", t
        )
        pasos, navegador = [], "chromium"
        for parte in partes:
            parte = orden_limpia(parte)
            ruta = match_workspace_route(parte.replace("muevete ", "mueveme ", 1))
            if ruta and ruta["action"] in {
                "workspace_switch",
                "workspace_back",
                "workspace_list",
                "workspace_move",
            }:
                # Las variantes mecánicas simples siguen sus handlers; solo cambio se compone aquí.
                if ruta["action"] != "workspace_switch":
                    return None
                pasos.append(
                    {"accion": "workspace_switch", "parametros": ruta["params"]}
                )
                continue
            if re.match(r"(?:muevete|mueveme|ve|cambia|llevame|enfoca)\b", parte):
                app = re.search(r"\b(firefox|chromium|spotify|code)\b", parte)
                if not app:
                    return None
                navegador = app[1] if app[1] in {"firefox", "chromium"} else navegador
                pasos.append(
                    {"accion": "operacion_enfocar", "parametros": {"app": app[1]}}
                )
                continue
            if re.match(r"(?:busca|buscame|buscar)\b", parte) and "youtube" in parte:
                q = re.sub(r"^(?:busca|buscame|buscar)\s+(?:en )?youtube\s+", "", parte)
                q = re.sub(r"\s+en youtube$", "", q)
                q = re.sub(r"^(?:busca|buscame|buscar)\s+", "", q)
                q = re.sub(r"^(?:un |el )?video (?:sobre|de)\s+", "", q)
                if not q or q == parte:
                    return None
                pasos.append(
                    {
                        "accion": "operacion_youtube",
                        "parametros": {"query": q, "app": navegador},
                    }
                )
                continue
            if re.fullmatch(
                r"(?:reproduce|reanuda|reproducir)(?: (?:la )?(?:musica|reproduccion|spotify))?",
                parte,
            ):
                pasos.append(
                    {
                        "accion": "operacion_reanudar",
                        "parametros": {"player": "spotify"},
                    }
                )
                continue
            if re.match(r"(?:abre|abrir|abras|abreme)\b", parte):
                objeto = re.sub(r"^(?:abre|abrir|abras|abreme)\s+", "", parte)
                from commands.apps import AppCommands
                from modules.app_router import _catalog

                app = _catalog().get(re.sub(r"^(?:el|la) ", "", objeto))
                if app in AppCommands.APP_MAP:
                    pasos.append(
                        {"accion": "operacion_abrir_app", "parametros": {"app": app}}
                    )
                    continue
                nombre = None
                m = re.fullmatch(
                    r"(?:code|vscode) con (?:la )?(?:carpeta|proyecto) (.+)", objeto
                )
                if m:
                    nombre = m[1]
                m = re.fullmatch(r"(.+?) (?:con|en) (?:code|vscode)", objeto)
                if m:
                    nombre = re.sub(
                        r"^(?:el proyecto|la carpeta|proyecto|carpeta|el|la)\s+",
                        "",
                        m[1],
                    )
                if nombre:
                    pasos.append(
                        {
                            "accion": "operacion_abrir_proyecto",
                            "parametros": {
                                "nombre": nombre.strip("\"'"),
                                "editor": "code",
                            },
                        }
                    )
                    continue
            return None  # Nunca ejecutar una parte si la otra no se entendió.
        return pasos if pasos and len(pasos) <= 6 else None

    def _leer(self, consulta):
        r = subprocess.run(
            ["hyprctl", "-j", consulta],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        import json

        return json.loads(r.stdout)

    def _clientes(self, app):
        from commands.system import SystemCommands

        return [
            c
            for c in self._leer("clients")
            if c.get("mapped", True) and SystemCommands.coincide_clase(app, c)
        ]

    @staticmethod
    def _cancelar(evento):
        if evento.is_set():
            from modules.agent_providers import Cancelado

            raise Cancelado("Tarea cancelada.")

    def _esperar(self, comprobar, evento, segundos=5):
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            self._cancelar(evento)
            valor = comprobar()
            if valor:
                return valor
            evento.wait(0.1)
        return None

    def _proyectos(self, nombre):
        coincidencias, vistos = [], set()
        limite = time.monotonic() + 1.5
        for raiz in self.config.PROJECT_ROOTS.split(":"):
            base = Path(raiz).expanduser()
            if (
                not base.is_dir()
                or base.is_symlink()
                or base.resolve() in {Path.home(), Path("/")}
            ):
                continue
            hijos = sorted(base.iterdir())
            if len(hijos) > 120:
                raise ValueError('La raíz de proyectos supera el límite; configura una raíz más concreta.')
            padres = [base, *[p for p in hijos if p.is_dir() and not p.is_symlink() and not p.name.startswith('.') and p.name not in PRIVADOS]]
            for padre in padres:
                entradas = sorted(padre.iterdir())
                if len(entradas) > 200:
                    raise ValueError('La búsqueda sería incompleta; configura una raíz de proyectos más concreta.')
                for p in entradas:
                    if time.monotonic() > limite:
                        raise ValueError(
                            "La búsqueda de proyectos superó el tiempo disponible; no seleccionaré una coincidencia parcial."
                        )
                    if (
                        p.is_symlink()
                        or p.name.startswith(".")
                        or p.name in PRIVADOS
                        or not p.is_dir()
                    ):
                        continue
                    if (
                        clave(p.name) == clave(nombre)
                        and str(p.resolve()) not in vistos
                    ):
                        vistos.add(str(p.resolve()))
                        coincidencias.append(p.resolve())
        return coincidencias

    def ejecutar(self, tarea, accion, parametros, evento):
        if not any(
            p["accion"] == accion and p["parametros"] == parametros
            for p in tarea.plan_operativo
        ):
            raise ValueError("La operación no pertenece al plan pedido por el usuario.")
        self._cancelar(evento)
        if accion == "operacion_abrir_proyecto":
            nombre = parametros["nombre"]
            if not nombre:
                return resultado(
                    "¿Qué proyecto o aplicación quieres abrir?",
                    ok=False,
                    aclaracion=True,
                )
            proyectos = self._proyectos(nombre)
            if len(proyectos) != 1:
                mensaje = (
                    f"No encontré una carpeta de proyecto llamada {nombre} en las raíces configuradas."
                    if not proyectos
                    else f"Encontré varios proyectos llamados {nombre}: "
                    + ", ".join(str(p) for p in proyectos)
                    + ". ¿Cuál quieres abrir?"
                )
                return resultado(mensaje, ok=False, aclaracion=True)
            carpeta = proyectos[0]
            existentes = self._clientes("code")
            coinciden = [
                c
                for c in existentes
                if clave(carpeta.name) in clave(c.get("title", ""))
            ]
            if not coinciden:
                subprocess.Popen(
                    ["code", "--new-window", str(carpeta)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                coinciden = self._esperar(
                    lambda: [
                        c
                        for c in self._clientes("code")
                        if clave(carpeta.name) in clave(c.get("title", ""))
                    ],
                    evento,
                )
            ref = {"tipo": "proyecto", "nombre": nombre, "ruta": str(carpeta)}
            if not coinciden:
                return resultado(
                    f"He solicitado abrir {carpeta.name} en Code, pero no he comprobado su ventana.",
                    referente=ref,
                )
            c = coinciden[0]
            destino = parametros.get("workspace")
            if destino and str(c.get("workspace", {}).get("id")) != destino:
                if destino not in {str(i) for i in range(1, 11)} | {
                    str(w["id"]) for w in self._leer("workspaces")
                }:
                    return resultado(
                        "El espacio solicitado ya no existe; no he movido la ventana.",
                        ok=False,
                    )
                self._cancelar(evento)
                subprocess.run(
                    [
                        "hyprctl",
                        "dispatch",
                        "movetoworkspacesilent",
                        f"{destino},address:{c['address']}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=True,
                )
                movido = self._esperar(
                    lambda: next(
                        (
                            v
                            for v in self._clientes("code")
                            if v.get("address") == c["address"]
                            and str(v.get("workspace", {}).get("id")) == destino
                        ),
                        None,
                    ),
                    evento,
                    1,
                )
                if not movido:
                    return resultado(
                        "No pude comprobar el destino de la ventana de Code.", ok=False
                    )
                c = movido
            self._enfocar_cliente(c, evento)
            return resultado(
                f"Code está abierto con {carpeta.name}; he comprobado su ventana.",
                verificado=True,
                referente=ref,
            )
        if accion in {"operacion_enfocar", "operacion_abrir_app"}:
            app = parametros["app"]
            clientes = self._clientes(app)
            if not clientes and accion == "operacion_abrir_app":
                self.executor.action_map["open_application"](app=app)
                clientes = self._esperar(lambda: self._clientes(app), evento)
            if not clientes:
                return resultado(
                    f"No encontré una ventana de {app}; no he comprobado la apertura ni cambiado a su espacio.",
                    ok=False,
                )
            self._enfocar_cliente(clientes[0], evento)
            espacio = clientes[0].get("workspace", {}).get("name") or clientes[0].get("workspace", {}).get("id")
            return resultado(
                f"{app} está al frente en el espacio de trabajo {espacio}; comprobado.",
                verificado=True,
                referente={"tipo": "aplicacion", "app": app},
            )
        if accion == "operacion_youtube":
            app = parametros["app"]
            query = parametros["query"]
            if app not in {"firefox", "chromium"} or not query or len(query) > 500:
                raise ValueError("Indica navegador y búsqueda válidos.")
            url = "https://www.youtube.com/results?" + urlencode(
                {"search_query": query}
            )
            subprocess.Popen(
                [app, "--new-tab", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return resultado(
                f"He enviado la búsqueda de YouTube «{query}» a {app}.",
                referente={"tipo": "youtube", "app": app, "query": query},
            )
        if accion == "operacion_reanudar":
            player = parametros["player"]
            if player != "spotify":
                raise ValueError("Reproductor no autorizado.")
            r = subprocess.run(
                ["playerctl", "--player", player, "play"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode != 0:
                return resultado(
                    "Spotify no tiene una reproducción disponible. ¿Qué canción o artista quieres escuchar?",
                    ok=False,
                    aclaracion=True,
                )

            def reproduciendo():
                r = subprocess.run(
                    ["playerctl", "--player", player, "status"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                return r.returncode == 0 and r.stdout.strip() == "Playing"

            if not self._esperar(reproduciendo, evento, 2):
                return resultado(
                    "Envié reanudar a Spotify, pero no he comprobado que esté reproduciendo.",
                    ok=False,
                    aclaracion=True,
                )
            return resultado(
                "Spotify está reproduciendo; he comprobado su estado.",
                verificado=True,
                referente={"tipo": "aplicacion", "app": "spotify"},
            )
        raise ValueError("Operación no disponible.")

    def _enfocar_cliente(self, cliente, evento):
        direccion = cliente.get("address", "")
        if not re.fullmatch(r"0x[0-9a-fA-F]+", direccion):
            raise ValueError("La ventana no tiene un identificador válido.")
        self._cancelar(evento)
        r = subprocess.run(
            ["hyprctl", "dispatch", "focuswindow", "address:" + direccion],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        if r.stdout.strip() != "ok":
            raise ValueError("Hyprland no confirmó el foco.")
        if not self._esperar(
            lambda: self._leer("activewindow").get("address") == direccion, evento, 1
        ):
            raise ValueError("No pude comprobar el foco de la ventana.")

        def destino_confirmado():
            actual = self._leer("activewindow")
            espacio = actual.get("workspace", {}).get("id")
            if actual.get("address") != direccion or espacio is None:
                return False
            if espacio < 0:
                return any(
                    m.get("specialWorkspace", {}).get("id") == espacio
                    for m in self._leer("monitors")
                )
            return self._leer("activeworkspace").get("id") == espacio

        if not self._esperar(destino_confirmado, evento, 2):
            raise ValueError("No pude comprobar el espacio de trabajo de la ventana.")
