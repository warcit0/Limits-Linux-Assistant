"""Permisos locales por operación y destino; nunca consultan otro modelo.

Qwen interpreta la petición. Este límite independiente verifica el alcance de
los efectos propuestos, incluso si documentos o herramientas intentan ordenarlos.
"""

import re
from modules.grounding import fold
from modules.operation_intent import lectura_explicita

# Familias de operaciones, no rutas que seleccionen herramientas por frases.
VERBOS = {
    'abrir': r'abre\w*|abrir|inicia\w*|iniciar|lanza\w*|lanzar',
    'cerrar': r'cierra\w*|cerrar|termina\w*|terminar',
    'enfocar': r'enfoca\w*|enfocar|trae\w*|traer|muestra\w*|mostrar|pon\w*|poner|lleva\w*|ve|vamos',
    'espacio': r'mueve\w*|mover|cambia\w*|cambiar|lleva\w*|ir|ve|vete|vamos|pasa\w*|vuelve|regresa\w*|mete\w*|entra\w*',
    'ocultar': r'oculta\w*|ocultar|esconde\w*|esconder|cierra\w*|cerrar|sal|salir',
    'nivel': r'sube\w*|subir|baja\w*|bajar|pon\w*|poner|ajusta\w*|ajustar|cambia\w*|cambiar|deja\w*|aumenta\w*|reduce\w*',
}


def _verbo(texto, familia):
    return bool(re.search(r'\b(?:'+VERBOS[familia]+r')\b', texto))


def _nombrado(valor, texto):
    palabras = [p for p in re.findall(r'[\w]+', fold(valor)) if len(p) > 2]
    return bool(palabras) and all(re.search(r'\b'+re.escape(p)+r'\b', texto) for p in palabras)


def _destino_ventana(tarea, p, texto):
    direccion = p.get('address')
    ventanas = tarea.entidades.get('ventanas_detalle', [])
    v = next((v for v in ventanas if v.get('address') == direccion), None)
    if not v:
        return False
    # El foco se fija por una observación del turno y se vuelve a comprobar al actuar.
    activa = tarea.entidades.get('ventana_activa')
    deictico = bool(re.search(r'\b(viendo|actual|activa|esta|esa|enfrente|al frente)\b', texto))
    if deictico and direccion == activa:
        return True
    return _nombre_ventana(v,texto)


def _nombre_ventana(ventana,texto):
    from modules.app_router import resolver_aplicacion
    from commands.system import SystemCommands
    app = resolver_aplicacion(re.sub(r'^(?:la |el )?(?:app |aplicacion |ventana de )?', '', texto))
    return bool(app and SystemCommands.coincide_clase(app,ventana)) or any(_nombrado(ventana.get(k,''),texto) for k in ('class','title'))


def autorizar(tarea, accion, p, herramientas):
    from modules.task_tools import LECTURAS, ACCIONES
    directa = tarea.entidades.get('orden_rapida')
    if directa and accion == directa.get('action'):
        esperado = herramientas.normalizar_parametros(accion,directa.get('params',{}))
        if p == esperado:
            return  # Reconocedor de frase completa; los tipos, rutas y recibos siguen en el ejecutor.
    if accion in LECTURAS | {'listar_carpeta','leer_archivo','probar_script'}:
        return
    if tarea.modo == 'leer':
        raise ValueError('La petición no autoriza cambios. Puedes consultar el estado o pedir una acción explícita.')
    origen = tarea.objetivo
    texto = re.sub(r'\b(?:solo local|sin internet|sin nube|usa qwen|con qwen)\b','',fold(origen))
    clausulas = re.split(r'[;]|\b(?:y|pero|luego|despues|ademas|tambien)\b',texto)
    for clausula in clausulas:
        if not clausula.strip() or lectura_explicita(clausula) or re.search(r'\b(nunca|sin|evita|si)\b',clausula):
            continue
        if _permite_clausula(tarea,accion,p,clausula):
            return
    raise ValueError('No pude vincular esa operación y su destino a tu petición. Consulta el destino real o pide una aclaración; no repitas el mismo paso.')


def _permite_clausula(tarea,accion,p,t):
    permitido = False
    if accion in {'open_application', 'close_application'}:
        familia = 'abrir' if accion == 'open_application' else 'cerrar'
        from modules.app_router import match_app_route, resolver_aplicacion
        from modules.operation_intent import proyecto_solicitado
        if accion == 'open_application' and proyecto_solicitado(t):
            raise ValueError('Abrir el editor vacío no abre el proyecto. Usa buscar_proyectos y después abrir_proyecto con su ruta observada.')
        orden = match_app_route(t)
        alias_exacto = bool(orden and orden['action'] == accion and resolver_aplicacion(p.get('app','')) == orden['params']['app'])
        permitido = not proyecto_solicitado(t) and _verbo(t, familia) and (alias_exacto or _nombrado(p.get('app',''), t))
    elif accion == 'abrir_aplicacion':
        app = tarea.entidades.get('aplicaciones', {}).get(p.get('id'))
        permitido = bool(app and _verbo(t,'abrir') and any(_nombrado(app.get(k,''),t) for k in ('nombre','id')))
        # Una consulta aproximada se vincula a la petición, no a texto externo.
        if app and not app.get('aproximada') and _verbo(t,'abrir') and not permitido:
            consulta = tarea.entidades.get('consulta_aplicaciones','')
            permitido = bool(consulta and _nombrado(consulta,t) and len(tarea.entidades.get('aplicaciones',{})) == 1)
    elif accion in {'cerrar_ventana', 'enfocar_ventana'}:
        from modules.operation_intent import destino_espacio_especial
        permitido = not destino_espacio_especial(t) and _verbo(t, 'cerrar' if accion == 'cerrar_ventana' else 'enfocar') and _destino_ventana(tarea,p,t)
    elif accion == 'focus_window':
        from commands.apps import AppCommands
        permitido = p.get('app') in AppCommands.APP_MAP and _verbo(t,'enfocar') and _nombrado(p.get('app',''),t)
    elif accion == 'ocultar_especial':
        permitido = _verbo(t,'ocultar') and p.get('nombre') in tarea.entidades.get('especiales',[]) and (_nombrado(p.get('nombre',''),t) or bool(re.search(r'\b(especial|actual|este|ese)\b',t)))
    elif accion == 'mover_ventana':
        from modules.operation_intent import objeto_movimiento
        from commands.workspaces import normalizar_destino
        movimiento = objeto_movimiento(t)
        permitido = bool(movimiento and normalizar_destino(movimiento['target']) == normalizar_destino(p.get('target','')) and _destino_ventana(tarea,p,movimiento['objeto']))
        if permitido:
            candidatos = [v for v in tarea.entidades.get('ventanas_detalle',[]) if _nombre_ventana(v,movimiento['objeto'])]
            if len(candidatos) > 1:
                raise ValueError('Hay varias ventanas que corresponden al nombre; pregunta cuál antes de mover.')
    elif accion in {'workspace_switch','workspace_move','workspace_back'}:
        from modules.operation_intent import objeto_movimiento, destino_espacio_especial
        if objeto_movimiento(t) or destino_espacio_especial(t):
            return False  # Un cambio de escritorio no mueve ni oculta la entidad solicitada.
        from commands.workspaces import normalizar_destino
        tokens = re.findall(r'\b[\w]+\b',t)
        destino = normalizar_destino(p.get('target',''))
        nombrado = any(normalizar_destino(x) == destino for x in tokens) if destino else False
        permitido = _verbo(t,'espacio') and (accion == 'workspace_back' and bool(re.search(r'\b(anterior|vuelve|regresa)\b',t)) or nombrado)
        if accion == 'workspace_move':
            permitido = permitido and 'ventana' in t
    elif accion in {'set_volume','set_brightness'}:
        dominio = 'volumen' if accion == 'set_volume' else 'brillo'
        clausulas = re.split(r'[;,]|\by\b|\bpero\b',t)
        nivel = str(p.get('level',''))
        permitido = bool(nivel) and any(dominio in c and re.search(r'(?<!\d)'+re.escape(nivel)+r'(?!\d)',c) for c in clausulas)
        if p.get('mode','absolute') == 'relative':
            permitido = permitido and _verbo(t,'nivel')
            if re.search(r'\b(baja\w*|reduce\w*)\b',t): permitido = permitido and float(p.get('level',0)) < 0
        elif re.search(r'\b(sube\w*|baja\w*|reduce\w*|aumenta\w*)\b',t):
            permitido = permitido and bool(re.search(r'\b(a|al|hasta)\s+'+re.escape(nivel)+r'\b',t))
    elif accion in {'media_control','spotify_control'}:
        acciones = {'play':r'play|reanuda\w*|reproduc\w*|continua\w*|dale', 'pause':r'pausa\w*',
                    'stop':r'deten\w*|para', 'next':r'siguiente|otra|cambia\w*(?=\s+(?:de\s+)?(?:cancion|tema))', 'previous':r'anterior'}
        permitido = bool(re.search(r'\b(?:'+acciones.get(p.get('action'),r'(?!)')+r')\b',t))
        if p.get('player'):
            player = fold(p['player'])
            from commands.apps import AppCommands
            otro_destino = any(_nombrado(app,t) for app in AppCommands.APP_MAP if fold(app) != player)
            referencia = bool(re.search(r'\b(musica|reproduccion|cancion|tema)\b',t)) and _nombrado(player,fold(tarea.objetivo)) and not otro_destino
            continuidad = player == tarea.entidades.get('reproductor_elegido') and not otro_destino
            permitido = permitido and (_nombrado(player,t) or referencia or continuidad)
    elif accion in {'spotify_play','youtube_play','web_search'}:
        consulta = fold(p.get('query',''))
        permitido = bool(consulta and consulta in t and re.search(r'\b(pon\w*|reproduc\w*|escucha\w*|busca\w*|encuentra\w*)\b',t))
        if accion == 'web_search':
            from modules.operation_intent import motor_explicito
            motor = motor_explicito(t)
            permitido = permitido and (not motor or p.get('engine','google') == motor)
    elif accion == 'spotify_reproducir':
        uri = p.get('uri')
        elemento = tarea.entidades.get('spotify_uris',{}).get(uri)
        permitido = bool(elemento and re.search(r'\b(pon\w*|reproduc\w*|escucha\w*)\b',t) and
                         (_nombrado(elemento.get('nombre',''),t) or tarea.entidades.get('spotify_consulta') and fold(tarea.entidades['spotify_consulta']) in t or re.search(r'\b(biblioteca|guardad\w*|favorit\w*)\b',t)))
    elif accion == 'abrir_proyecto':
        from modules.operation_intent import proyecto_solicitado
        apertura = _verbo(t,'abrir') or 'proyecto' in t and _verbo(t,'espacio')
        permitido = apertura and p.get('ruta') in tarea.entidades.get('proyectos',[]) and bool(tarea.entidades.get('consulta_proyectos')) and _nombrado(tarea.entidades['consulta_proyectos'],t)
    elif accion in {'shutdown','reboot','lock_screen'}:
        verbos = {'shutdown':r'apaga\w*|apagar','reboot':r'reinicia\w*|reiniciar','lock_screen':r'bloquea\w*|bloquear'}
        permitido = bool(re.search(r'\b(?:'+verbos[accion]+r')\b',t))
    elif accion in {'copy_file','move_file','rename_file'}:
        verbos = {'copy_file':r'copia\w*|copiar','move_file':r'mueve\w*|mover','rename_file':r'renombra\w*|renombrar'}
        # Alcance y rutas observadas se comprueban otra vez en task_tools.
        permitido = bool(re.search(r'\b(?:'+verbos[accion]+r')\b',t)) and all(
            fold(str(v)) in t for k,v in p.items() if k in {'source','destination','path','new_name'})
    elif accion in {'preparar_script','probar_script','aplicar_script'}:
        permitido = tarea.rol == 'desarrollo' and bool(re.search(r'\b(script|codigo|programa)\b',t)) and bool(re.search(r'\b(crea\w*|escrib\w*|prepara\w*|genera\w*|aplica\w*|ejecuta\w*|corrig\w*)\b',t))
    elif accion == 'open_url':
        permitido = _verbo(t,'abrir') and fold(p.get('url','')) in t
    elif accion == 'open_file':
        ruta = fold(p.get('path',''))
        permitido = bool(ruta and _verbo(t,'abrir') and (ruta in t or _nombrado(ruta.rsplit('/',1)[-1],t)))
    return bool(permitido)


def validar_delegacion(entrada, rol):
    """No usar especialistas como reparación de una orden cotidiana fallida."""
    t = fold(entrada)
    desarrollo = re.search(r'\b(script|codigo|programa|funcion|repositorio|bug|tests?)\b',t)
    actual = re.search(r'\b(internet|web|noticias|novedades|actual\w*|reciente\w*|investiga\w*|gemini)\b',t)
    analisis = re.search(r'\b(documentos?|informe|compara\w*|analiza\w*|analisis|explica\w*)\b',t)
    if not {'desarrollo':desarrollo,'investigacion':actual,'analisis':analisis or len(entrada)>1800}.get(rol):
        raise ValueError('Esta petición es cotidiana. Usa las herramientas locales o aclara el dato que falta; no la delegues por un fallo.')


def autorizar_capacidad(tarea, accion, parametros):
    """Política de efectos: no reinterpreta la orden con verbos o patrones."""
    from modules.task_tools import LECTURAS, SENSIBLES
    cotidianas = {'open_application','close_application','focus_window','set_volume',
        'set_brightness','media_control','lock_screen','workspace_switch','workspace_back',
        'workspace_move','abrir_aplicacion','enfocar_ventana','mover_ventana',
        'cerrar_ventana','ocultar_especial','abrir_proyecto','open_file','reveal_file',
        'spotify_play','spotify_reproducir','spotify_control','youtube_play','web_search',
        'open_url','copy_file','tv_cast','tv_control','preparar_script'}
    if accion in LECTURAS | SENSIBLES | cotidianas | {'listar_carpeta','leer_archivo','probar_script'}:
        if accion=='abrir_aplicacion':
            app=tarea.entidades.get('aplicaciones',{}).get(parametros.get('id'),{})
            if app.get('aproximada'):
                raise ValueError('Es una sugerencia aproximada. Pide el nombre correcto y vuelve a buscarlo antes de abrir.')
        return
    if accion in {'remember','forget'}:
        # La memoria personal sigue exigiendo una petición explícita. No aprender
        # inferencias del interlocutor ni instrucciones encontradas en documentos.
        from modules.memory_router import match_memory_route
        orden=match_memory_route(tarea.objetivo)
        if orden and orden.get('action')==accion and orden.get('params',{})==parametros:
            return
        raise ValueError('Para guardar u olvidar un hecho personal hace falta una petición explícita del usuario.')
    raise ValueError('Esta capacidad no tiene una política de efectos habilitada. Usa las herramientas acotadas o el flujo de scripts con confirmación.')


def requiere_confirmacion(accion, parametros):
    """Riesgos adicionales del modo conversacional, a partir del efecto real."""
    return accion == 'tv_cast'
