"""Intención explícita del usuario, separada de la propuesta del modelo."""

import re
import unicodedata


def normalizar(texto):
    return " ".join(
        "".join(
            c
            for c in unicodedata.normalize("NFD", texto.casefold())
            if not unicodedata.combining(c)
        )
        .strip(" .,!¡¿?;:")
        .split()
    )


def orden_limpia(texto):
    texto = normalizar(texto)
    # Solo cortesía y vocativos al principio; no reemplazar palabras del objetivo.
    return re.sub(
        r"^(?:(?:bien|vale|perfecto|entonces|primero|ahora|mejor|oye|limits|limites|livings|por favor|quiero que|necesito que|me gustaria que|puedes|podrias|quiero)\b[ ,:;]*)+",
        "",
        texto,
    )


VERBO = r"(?:abre|abrir|abras|abreme|abramos|cierra|cierres|cerrar|mueve|mueveme|muevete|muevas|mover|cambia|cambiame|cambiar|llevame|ve|vete|pasate|pon|ponme|poner|sube|subas|baja|bajes|apaga|apagues|reinicia|reinicies|bloquea|pausa|reanuda|reproduce|reproducir|busca|buscame|buscar|encuentra|copia|copiar|renombra|organiza|ejecuta|aplica|haz|configura|instala)"


def lectura_explicita(texto):
    t = normalizar(texto)
    if re.match(r"(?:que|cual|cuales|cuanto|cuanta|cuantos|cuantas|quien|quienes|donde|cuando)\b", orden_limpia(texto)):
        return True
    if re.match(
        r"busca (?:contradicciones|errores|diferencias|patrones|causas|informacion|en internet|en la web|datos|noticias|novedades)\b",
        orden_limpia(texto),
    ):
        return True
    # Negaciones dentro de una petición compuesta tampoco autorizan la otra parte.
    return bool(
        re.search(r"\b(no|nunca)\b", t)
        or re.match(
            r"(?:(?:por favor|puedes|podrias|quiero que)\s+)?(?:explica\w*|dime como|ensename como|recomienda\w*|solo analiza|solo recomienda|como\b|que pasa si\b|que es\b|por que\b)",
            t,
        )
    )


def es_orden(texto):
    return not lectura_explicita(texto) and bool(
        re.match(VERBO + r"\b", orden_limpia(texto))
    )


def consulta_estado_actual(texto):
    """Distingue observar el estado actual de buscar entidades instaladas."""
    return lectura_explicita(texto) and bool(re.search(
        r'\b(abiert\w*|corriendo|ejecutando|ejecucion|activ\w*|pantalla|en uso|sonando)\b',
        normalizar(texto)))


def peticion_reconocible(texto):
    """Reutiliza reconocedores puros; reconocer una cláusula no la autoriza."""
    if es_orden(texto):
        return True
    from modules.workspace_router import match_workspace_route
    from modules.quick_routes import match_quick_route
    return bool(match_workspace_route(texto) or match_quick_route(texto))


def destino_espacio_especial(texto):
    """El objeto de la operación es un espacio, no una aplicación dentro de él."""
    return bool(re.match(
        r'(?:cierra\w*|cerrar|oculta\w*|esconde\w*|sal|salir)\s+'
        r'(?:(?:de|del|la|el|este|ese|esta|esa)\s+)*'
        r'(?:espacio(?: de trabajo)?|ventana(?: de trabajo)?|work\s*space) especial\b',
        orden_limpia(texto)))


def motor_explicito(texto):
    """Plataforma de búsqueda nombrada como destino, no como tema."""
    destinos = set(re.findall(r'\b(?:en|por|con|usando|usa)\s+(?:el buscador\s+)?'
                              r'(google|duckduckgo|youtube|github)\b', normalizar(texto)))
    if len(destinos) > 1:
        raise ValueError('Hay más de una plataforma de búsqueda; indica una por cláusula.')
    return next(iter(destinos), None)


def proyecto_solicitado(texto):
    """Extrae el objeto de abrir un proyecto, sin resolver ni autorizar rutas."""
    t = orden_limpia(texto)
    if not re.match(r'(?:abre\w*|abrir|inicia\w*)\b',t):
        return None
    from modules.app_router import resolver_aplicacion
    # El objeto «proyecto» conserva su nombre aunque el editor aparezca antes o después.
    m = re.search(r'\bproyecto\s+(.+)',t)
    nombre = m[1] if m else None
    partes = re.split(r'\s+(?:con|en)\s+',nombre or t,maxsplit=1)
    if len(partes) == 2 and resolver_aplicacion(partes[1]) in {'code','vscode'}:
        return re.sub(r'^(?:abre\w*|abrir|inicia\w*)\s+(?:el\s+)?','',partes[0])
    return nombre


def requiere_efecto(texto):
    """Impide cerrar una orden de cambio usando solo lecturas preparatorias."""
    t = orden_limpia(texto)
    return es_orden(texto) and not re.match(r'(?:busca|buscame|buscar|encuentra)\b',t)


def objeto_movimiento(texto):
    """Distingue mover una entidad de trasladarse uno mismo a otro espacio."""
    t = orden_limpia(texto)
    m = re.fullmatch(r'(?:mueve|mover|manda|envia)\s+(.+?)\s+(?:al?|hacia el)\s+'
                     r'(?:espacio de trabajo|work\s*space|escritorio)\s+(\w+)',t)
    return {'objeto':m[1], 'target':m[2]} if m else None


def espacio_consultado(texto):
    """Filtro explícito de una consulta; no reutiliza destinos de turnos anteriores."""
    m = re.search(r'\b(?:espacio de trabajo|work\s*space|escritorio)\s+(\w+)\b',normalizar(texto))
    if not m:
        return None
    if m[1] in {'actual','este'}:
        return 'actual'
    from commands.workspaces import normalizar_destino
    destino = normalizar_destino(m[1])
    return destino if re.fullmatch(r'(?:[1-9]|10)',destino) else None


def separar_encadenadas(texto):
    """Separa cláusulas con otra petición reconocible; conserva nombres y citas.

    Solo organiza el turno: no selecciona herramientas ni concede permisos.
    """
    separador = re.compile(r"\s*(?:;|\b(?:y|e|además|ademas|también|tambien|luego|después|despues|a continuación|a continuacion)\b)\s*", re.I)
    citas = list(re.finditer(r'"[^"\n]*"|«[^»\n]*»|\x27[^\x27\n]*\x27', texto))
    cortes = []
    for m in separador.finditer(texto):
        if any(c.start() <= m.start() < c.end() for c in citas):
            continue
        resto = texto[m.end():].lstrip(' ,:')
        resto = re.sub(r'^(?:(?:y|e|además|ademas|también|tambien|luego|después|despues)\b[ ,]*)+', '', resto, flags=re.I)
        # Un nombre como «rock y roll» no contiene otra petición.
        t = orden_limpia(resto)
        if peticion_reconocible(resto) or re.match(r"(?:no\s+)?(?:det[eé]n\w*|sal|oculta\w*|dime|consulta\w*)\b", t):
            cortes.append((m.start(), m.end()))
    if not cortes:
        return [texto]
    partes, inicio = [], 0
    for a,b in cortes:
        parte = texto[inicio:a].strip(' ,;:')
        if parte:
            partes.append(parte)
        inicio = b
    partes.append(texto[inicio:].strip(' ,;:'))
    # Nunca truncar ni convertir una explicación/hipótesis en órdenes separadas.
    if len(partes) > 6 or lectura_explicita(texto) or not all(partes):
        return [texto]
    return partes


def referencia_explicita(texto):
    t = orden_limpia(texto)
    return bool(
        re.search(
            r"\b(?:esa|ese|esta|este) (?:alternativa|organizacion|propuesta|resultado|archivo|carpeta|proyecto|opcion|formato|script)\b",
            t,
        )
        or re.search(
            r"\b(?:propuesta|resultado|formato|script|organizacion|alternativa|opcion) anterior\b",
            t,
        )
        or re.match(r"(?:abrelo|abremelo|muestramelo|ponlo|hazlo)\b", t)
        or re.search(
            r"\b(la segunda|la primera|esa opcion|ese archivo|esa carpeta|el anterior|la anterior|lo anterior|esa propuesta|ese proyecto)\b",
            t,
        )
    )


def pregunta_util(texto):
    return bool(texto) and not re.search(
        r"\b(algo mas|que mas|como (?:puedo|podria) ayudarte|necesitas ayuda con algo)\b",
        normalizar(texto),
    )


def afirma_accion(texto):
    t = normalizar(texto)
    if re.match(r"(?:no|todavia no|aun no)\b", t):
        return False
    return bool(
        re.search(
            r"\b(?:ya (?:estas|te encuentras|se encuentra)|(?:he|hemos) (?:abierto|cerrado|ocultado|enfocado|detenido|pausado|reanudado|movido|cambiado|buscado|reproducido|ejecutado)|estoy (?:abriendo|buscando|reproduciendo)|voy a (?:abrir|buscar|mover|reproducir))\b",
            t,
        )
    )
