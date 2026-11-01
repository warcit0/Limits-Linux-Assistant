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
            r"\b(?:ya (?:estas|te encuentras|se encuentra)|(?:he|hemos) (?:abierto|movido|cambiado|buscado|reproducido|ejecutado)|estoy (?:abriendo|buscando|reproduciendo)|voy a (?:abrir|buscar|mover|reproducir))\b",
            t,
        )
    )
