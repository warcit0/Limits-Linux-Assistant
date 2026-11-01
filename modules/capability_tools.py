"""Capacidades generales acotadas, disponibles sin coincidencia de frases."""

from pathlib import Path
import re
from types import SimpleNamespace

from modules.spotify_mcp import CONTRATOS as SPOTIFY_CONTRATOS, LECTURAS_SPOTIFY, ACCIONES_SPOTIFY

LECTURAS_CAP = {
    "consultar_capacidades",
    "buscar_aplicaciones",
    "consultar_ventanas",
    "consultar_escritorio",
    "buscar_proyectos",
    "buscar_memoria",
}
ACCIONES_CAP = {"abrir_aplicacion", "enfocar_ventana", "mover_ventana", "abrir_proyecto", "cerrar_ventana", "ocultar_especial"}
CATALOGO = {
    "buscar_aplicaciones": "(consulta:str) busca en el catálogo INSTALADO un nombre o función de app para localizarla antes de abrirla. No consulta aplicaciones abiertas o en ejecución: para eso consultar_escritorio. Devuelve ids observados; no abre nada.",
    "abrir_aplicacion": "(id:str) abre una aplicación instalada con id EXACTO obtenido de buscar_aplicaciones; verifica su ventana. No acepta comandos ni rutas inventados.",
    "consultar_escritorio": "(workspace:str opcional) consulta qué APLICACIONES están ABIERTAS y sus ventanas, foco y espacios especiales visibles. Primer paso para ocultar un especial o cerrar una ventana. workspace filtra por espacio numérico; sin workspace observa todo. No interpreta imágenes.",
    "cerrar_ventana": "(address:str) cierra SOLO una ventana observada por dirección y comprueba su desaparición; no cierra todas las ventanas de la aplicación.",
    "ocultar_especial": "(nombre:str) oculta SOLO un espacio especial observado y actualmente visible; conserva sus aplicaciones y verifica que se ocultó.",
    "consultar_capacidades": "(categoria:str) activa herramientas de aplicaciones, sistema, multimedia, archivos, proyectos, television, desarrollo, navegacion, memoria o especialistas. No ejecuta efectos.",
    "consultar_ventanas": "() devuelve ventanas reales con clase, título, dirección y workspace; resuelve aplicaciones por nombres aproximados.",
    "enfocar_ventana": "(address:str) enfoca una dirección EXACTA obtenida de consultar_ventanas y verifica foco/espacio.",
    "mover_ventana": "(address:str, target:str) mueve una ventana OBSERVADA al espacio numérico indicado y verifica su destino. No cambia el espacio del usuario. Si hay varias ventanas candidatas pregunta cuál.",
    "buscar_proyectos": "(nombre:str) busca coincidencias por nombre en PROJECT_ROOTS; devuelve rutas observadas, no abre nada.",
    "abrir_proyecto": "(ruta:str) abre con Code una ruta EXACTA obtenida de buscar_proyectos y comprueba su ventana.",
    "buscar_memoria": "(consulta:str) recupera recuerdos confirmados con origen; no autoriza acciones.",
    "proponer_recuerdo": "(titulo:str, contenido:str) guarda una inferencia pendiente de validar; no es un hecho confirmado.",
}
CAMPOS = {
    "buscar_aplicaciones": {"consulta"},
    "abrir_aplicacion": {"id"},
    "consultar_escritorio": {"workspace"},
    "cerrar_ventana": {"address"},
    "ocultar_especial": {"nombre"},
    "consultar_capacidades": {"categoria"},
    "consultar_ventanas": set(),
    "enfocar_ventana": {"address"},
    "mover_ventana": {"address", "target"},
    "buscar_proyectos": {"nombre"},
    "abrir_proyecto": {"ruta"},
    "buscar_memoria": {"consulta"},
    "proponer_recuerdo": {"titulo", "contenido"},
}

LECTURAS_CAP |= LECTURAS_SPOTIFY
ACCIONES_CAP |= ACCIONES_SPOTIFY
for _c in SPOTIFY_CONTRATOS:
    CATALOGO[_c["name"]] = _c["description"]
    CAMPOS[_c["name"]] = set(_c["inputSchema"]["properties"])


class Capacidades:
    def __init__(self, herramientas):
        self.tools = herramientas
        self.conocimiento = None

    def catalogo(self, tarea):
        return {
            k: v
            for k, v in CATALOGO.items()
            if (k not in ACCIONES_CAP or tarea.modo == "actuar")
            and (not k.startswith("spotify_") or getattr(getattr(self.tools,"config",None),"SPOTIFY_MCP_ENABLED",False))
            and (self.conocimiento or k not in {"buscar_memoria", "proponer_recuerdo"})
        }

    def validar(self, tarea, nombre, parametros):
        if nombre in LECTURAS_SPOTIFY | ACCIONES_SPOTIFY:
            from modules.spotify_mcp import validar
            if nombre not in self.catalogo(tarea):
                raise ValueError("Spotify MCP no está habilitado.")
            validar(nombre,parametros)
            if nombre == "spotify_reproducir":
                if parametros["uri"] not in tarea.entidades.get("spotify_uris",{}):
                    raise ValueError("Busca primero el contenido y elige una URI observada.")
                if parametros.get("dispositivo") and parametros["dispositivo"] not in tarea.entidades.get("spotify_dispositivos",[]):
                    raise ValueError("Consulta primero los dispositivos y elige uno observado.")
            return parametros
        campos_validos = (set(parametros).issubset(CAMPOS[nombre]) if nombre == "consultar_escritorio" else set(parametros) == CAMPOS.get(nombre,set()))
        if nombre not in self.catalogo(tarea) or not campos_validos:
            raise ValueError(
                "Parámetros incorrectos para la capacidad; consulta su firma."
            )
        if any(
            not isinstance(v, str) or not v.strip() or len(v) > 2000
            for v in parametros.values()
        ):
            raise ValueError("Indica texto no vacío de hasta 2000 caracteres.")
        if nombre == "consultar_escritorio" and parametros.get("workspace") and not re.fullmatch(r"(?:[0-9]|10|actual)",parametros["workspace"]):
            raise ValueError("workspace debe ser actual o un destino numérico de 0 a 10; 0 equivale a 10.")
        if nombre == 'consultar_escritorio' and getattr(tarea,'cotidiano_local',False) and not getattr(tarea,'conversacional',False) and parametros.get('workspace'):
            from modules.operation_intent import espacio_consultado
            from commands.workspaces import normalizar_destino
            solicitado = espacio_consultado(tarea.objetivo)
            if not solicitado or normalizar_destino(parametros['workspace']) != solicitado:
                raise ValueError('Ese filtro de espacio no pertenece a la consulta actual. Usa el destino solicitado o consulta sin filtro.')
        if (
            nombre == "consultar_capacidades"
            and parametros["categoria"] not in FAMILIAS
        ):
            raise ValueError("Elige una categoría real: " + ", ".join(FAMILIAS))
        if nombre in {"enfocar_ventana", "cerrar_ventana", "mover_ventana"} and parametros[
            "address"
        ] not in tarea.entidades.get("ventanas", []):
            raise ValueError(
                "Consulta primero las ventanas y usa una dirección observada."
            )
        if nombre == 'mover_ventana' and not re.fullmatch(r'(?:[0-9]|10)',parametros['target']):
            raise ValueError('El destino debe ser un espacio numérico de 0 a 10.')
        if nombre == "ocultar_especial" and parametros["nombre"] not in tarea.entidades.get("especiales",[]):
            raise ValueError("Consulta primero el escritorio y elige un espacio especial visible.")
        if nombre == "abrir_aplicacion" and parametros["id"] not in tarea.entidades.get("aplicaciones",{}):
            raise ValueError("Busca primero la aplicación instalada y usa su id observado.")
        if nombre == "abrir_proyecto" and parametros["ruta"] not in tarea.entidades.get(
            "proyectos", []
        ):
            raise ValueError("Busca primero los proyectos y usa una ruta observada.")
        return parametros

    def _mutar_escritorio(self,tarea,nombre,p,cancelar):
        import time
        from commands.workspaces import WorkspaceCommands
        ws = WorkspaceCommands()
        if nombre in {"cerrar_ventana", "mover_ventana"}:
            actuales = ws._leer("clients")
            direccion = p["address"]
            anterior = next((v for v in tarea.entidades.get("ventanas_detalle",[]) if v.get("address") == direccion),None)
            actual = next((v for v in actuales if v.get("address") == direccion),None)
            if not anterior or not actual or anterior.get("class") != actual.get("class"):
                raise ValueError("La ventana observada cambió; consulta las ventanas de nuevo.")
            from modules.grounding import fold
            deictico = bool(re.search(r"\b(viendo|actual|activa|esta|esa|enfrente|al frente)\b",fold(tarea.objetivo)))
            if deictico and tarea.entidades.get("ventana_activa") == direccion and ws._leer("activewindow").get("address") != direccion:
                raise ValueError("Cambió la ventana activa; consulta el escritorio antes de cerrar.")
            if cancelar.is_set():
                raise ValueError("Operación cancelada antes de cerrar la ventana.")
            if nombre == 'mover_ventana':
                destino = '10' if p['target'] == '0' else p['target']
                ws._dispatch('movetoworkspacesilent',destino+',address:'+direccion)
                condicion = lambda: any(v.get('address') == direccion and (v.get('workspace') or {}).get('id') == int(destino) for v in ws._leer('clients'))
                resumen = 'La ventana está en el espacio de trabajo '+destino+'; he comprobado su destino.'
            else:
                ws._dispatch("closewindow","address:"+direccion)
                condicion = lambda: not any(v.get("address") == direccion for v in ws._leer("clients"))
                resumen = "La ventana está cerrada; he comprobado su desaparición."
        else:
            nombre_especial = p["nombre"]
            if not re.fullmatch(r"[\w-]+",nombre_especial):
                raise ValueError("Nombre especial inválido.")
            visible = lambda: any(m.get("specialWorkspace",{}).get("name") == "special:"+nombre_especial for m in ws._leer("monitors"))
            if not visible():
                return {"ok":True,"verificado":True,"estado":"completado","datos":"El espacio especial ya está oculto.","resumen":"El espacio especial ya está oculto."}
            if cancelar.is_set():
                raise ValueError("Operación cancelada antes de ocultar el espacio.")
            ws._dispatch("togglespecialworkspace",nombre_especial)
            condicion = lambda: not visible()
            resumen = "El espacio especial está oculto; sus aplicaciones siguen abiertas."
        for _ in range(8):
            if condicion():
                return {"ok":True,"verificado":True,"estado":"completado","datos":resumen,"resumen":resumen}
            time.sleep(.1)
        return {"ok":True,"verificado":False,"estado":"sin_verificar","datos":"He enviado la solicitud, pero no pude comprobar el efecto.","resumen":"He enviado la solicitud, pero no pude comprobar el efecto."}

    def ejecutar(self, tarea, nombre, p, cancelar):
        self.validar(tarea, nombre, p)
        ops = self.tools.operaciones
        if nombre in LECTURAS_SPOTIFY | ACCIONES_SPOTIFY:
            from modules.spotify_client import llamar
            resultado = llamar(self.tools.config,nombre,p,cancelar)
            if resultado.get("ok"):
                if nombre in {"spotify_buscar","spotify_biblioteca"}:
                    tarea.entidades["spotify_uris"] = {i["uri"]:i for i in resultado.get("datos",[]) if i.get("uri")}
                    tarea.entidades["spotify_consulta"] = p.get("consulta","")
                elif nombre == "spotify_dispositivos":
                    tarea.entidades["spotify_dispositivos"] = [i["id"] for i in resultado.get("datos",[]) if i.get("id") and not i.get("is_restricted")]
            return resultado
        if nombre == "buscar_aplicaciones":
            from modules.installed_apps import buscar
            apps = buscar(p["consulta"])
            tarea.entidades["consulta_aplicaciones"] = p["consulta"]
            tarea.entidades["aplicaciones"] = {a["id"]:a for a in apps}
            datos = [{k:a[k] for k in ("id","nombre","descripcion")} | {'aproximada':a.get('aproximada',False)} for a in apps]
        elif nombre == "abrir_aplicacion":
            from modules.installed_apps import abrir
            return abrir(tarea,p["id"],cancelar)
        elif nombre == "consultar_capacidades":
            from commands.apps import AppCommands

            tarea.capacidades = list(
                dict.fromkeys(tarea.capacidades + [p["categoria"]])
            )
            if tarea.seleccion_herramientas:
                tarea.seleccion_herramientas = list(set(tarea.seleccion_herramientas) | FAMILIAS[p["categoria"]])
            datos = {"herramientas": self.tools.catalogo(tarea)}
            if p["categoria"] == "especialistas":
                datos["especialistas"] = {"desarrollo":"escribir/modificar código o scripts", "analisis":"análisis extenso", "investigacion":"actualidad e investigación web"}
        elif nombre == "consultar_escritorio":
            datos = {"workspace":ops._leer("activeworkspace"), "ventana":ops._leer("activewindow"),
                     "especiales":[m.get("specialWorkspace",{}) for m in ops._leer("monitors") if m.get("specialWorkspace",{}).get("name")]}
            tarea.entidades["ventana_activa"] = datos["ventana"].get("address")
            tarea.entidades["especiales"] = [e["name"].removeprefix("special:") for e in datos["especiales"]]
            from modules.memory import redact
            ventanas = [{k:redact(str(c.get(k,""))) if k == "title" else c.get(k) for k in ("address","class","title","workspace")} for c in ops._leer("clients") if c.get("mapped",True)][:100]
            tarea.entidades["ventanas"] = [c["address"] for c in ventanas]
            tarea.entidades["ventanas_detalle"] = [{k:c[k] for k in ("address","class","title","workspace")} for c in ventanas]
            objetivo = p.get("workspace")
            if objetivo is not None:
                if objetivo == 'actual':
                    objetivo = str(datos['workspace']['id'])
                objetivo = "10" if objetivo == "0" else objetivo
                ventanas = [c for c in ventanas if str((c.get("workspace") or {}).get("id")) == objetivo]
            datos["ventanas"] = ventanas
            if objetivo is not None:
                nombres = list(dict.fromkeys(str(c.get("class") or "aplicación") for c in ventanas))
                resumen = f"En el espacio de trabajo {objetivo} " + ("están abiertas: "+", ".join(nombres)+"." if nombres else "no hay ventanas abiertas.")
                return {"ok":True,"verificado":True,"datos":datos,"resumen":resumen,"estado":"completado"}

            from modules.memory import redact
            datos["ventana"] = {k:redact(str(datos["ventana"].get(k,""))) if k == "title" else datos["ventana"].get(k) for k in ("address","class","title","workspace")}
            nombres = list(dict.fromkeys(str(c.get('class') or 'aplicación') for c in ventanas))
            resumen = 'Aplicaciones con ventanas abiertas: '+', '.join(nombres)+'.' if nombres else 'No hay aplicaciones con ventanas abiertas.'
            if tarea.entidades['especiales']:
                resumen += ' Espacios especiales visibles: '+', '.join(tarea.entidades['especiales'])+'.'
            else:
                resumen += ' No hay espacios especiales visibles.'
            return {'ok':True,'verificado':True,'datos':datos,'resumen':resumen,'estado':'completado'}
        elif nombre in {"cerrar_ventana","ocultar_especial","mover_ventana"}:
            return self._mutar_escritorio(tarea,nombre,p,cancelar)
        elif nombre == "consultar_ventanas":
            from modules.memory import redact

            datos = [
                {
                    k: redact(str(c.get(k, ""))) if k == "title" else c.get(k)
                    for k in ("address", "class", "title", "workspace")
                }
                for c in ops._leer("clients")
                if c.get("mapped", True)
            ][:100]
            tarea.entidades["ventanas"] = [c["address"] for c in datos]
            tarea.entidades["ventanas_detalle"] = [{k:c[k] for k in ("address","class","title","workspace")} for c in datos]
            nombres = list(dict.fromkeys(str(c.get('class') or 'aplicación') for c in datos))
            resumen = 'Aplicaciones con ventanas abiertas: '+', '.join(nombres)+'.' if nombres else 'No hay aplicaciones con ventanas abiertas.'
            return {'ok':True,'verificado':True,'datos':datos,'resumen':resumen,'estado':'completado'}
        elif nombre == "enfocar_ventana":
            c = next(
                (c for c in ops._leer("clients") if c.get("address") == p["address"]),
                None,
            )
            if c is None:
                raise ValueError(
                    "La ventana ya no existe; vuelve a consultar las ventanas."
                )
            ops._enfocar_cliente(c, cancelar)
            return {
                "ok": True,
                "verificado": True,
                "datos": f"{c.get('class')} está al frente en {c.get('workspace', {}).get('name') or c.get('workspace', {}).get('id')}; comprobado.",
            }
        elif nombre == "buscar_proyectos":
            tarea.entidades["consulta_proyectos"] = p["nombre"]
            datos = [str(r) for r in ops._proyectos(p["nombre"])]
            tarea.entidades["proyectos"] = datos
            if not datos:
                return {'ok':True,'verificado':True,'datos':[], 'resumen':'No encontré ese proyecto en las carpetas de proyectos autorizadas.','estado':'completado'}
        elif nombre == "abrir_proyecto":
            ruta = Path(p["ruta"])
            # Resolver otra vez: una ruta observada no puede cambiar a un enlace.
            if ruta.is_symlink() or not ruta.is_dir():
                raise ValueError("El proyecto cambió; vuelve a consultar.")
            paso = {
                "accion": "operacion_abrir_proyecto",
                "parametros": {"nombre": ruta.name, "editor": "code"},
            }
            return ops.ejecutar(
                SimpleNamespace(plan_operativo=[paso]),
                paso["accion"],
                paso["parametros"],
                cancelar,
            )
        elif nombre == "buscar_memoria":
            datos = self.conocimiento.recuperar(p["consulta"])
        elif nombre == "proponer_recuerdo":
            id_ = self.conocimiento.guardar(
                "Pendientes-de-validar",
                p["titulo"],
                p["contenido"],
                estado="pendiente",
                origen="inferencia_modelo",
            )
            if id_ is None:
                return {"ok":False,"verificado":False,"datos":"No pude guardar el candidato de memoria."}
            return {
                "ok": True,
                "verificado": True,
                "datos": f"Candidato {id_} guardado para revisar; no se considera un hecho confirmado.",
            }
        else:
            raise ValueError("Capacidad desconocida.")
        return {"ok": True, "verificado": True, "datos": datos, "evidencia": nombre}


# El catálogo se agrupa por capacidad, nunca por frases reconocidas.
FAMILIAS = {
    "especialistas": set(),
    "aplicaciones": {
        "buscar_aplicaciones", "abrir_aplicacion",
        "consultar_escritorio",
        "cerrar_ventana",
        "ocultar_especial",
        "open_application",
        "close_application",
        "focus_window",
        "list_running_apps",
        "consultar_ventanas",
        "enfocar_ventana",
        "mover_ventana",
    },
    "sistema": {
        "get_system_info",
        "get_time",
        "get_volume",
        "set_volume",
        "set_brightness",
        "lock_screen",
        "shutdown",
        "reboot",
        "workspace_switch",
        "workspace_back",
        "workspace_move",
        "workspace_list",
    },
    "multimedia": {
        *LECTURAS_SPOTIFY, *ACCIONES_SPOTIFY,
        "spotify_play",
        "youtube_play",
        "media_control",
        "get_current_song",
        "get_lyrics",
    },
    "archivos": {
        "search_file", "list_directory", "open_file",
        "listar_carpeta",
        "leer_archivo",
        "copy_file",
        "move_file",
        "rename_file",
    },
    "proyectos": {"buscar_proyectos", "abrir_proyecto"},
    "television": {"list_tvs", "tv_cast", "tv_control"},
    "desarrollo": {
        "git_status",
        "docker_status",
        "preparar_script",
        "probar_script",
        "aplicar_script",
        "listar_carpeta",
        "leer_archivo",
    },
    "navegacion": {"web_search", "open_url"},
    "memoria": {
        "memory_list",
        "memory_recall",
        "memory_stats",
        "buscar_memoria",
        "proponer_recuerdo",
    },
}
