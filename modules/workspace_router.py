"""Órdenes completas de espacios de trabajo; variantes del dictado acotadas."""

import re
import unicodedata


def normalizar_orden(texto):
    texto = "".join(
        c
        for c in unicodedata.normalize("NFD", texto.casefold())
        if not unicodedata.combining(c)
    )
    return re.sub(
        r"^(?:(?:perfecto|bien|vale|por favor|limits)[,. ]+)+", "", texto
    ).strip(" .¿?¡!")


def match_workspace_route(texto):
    t = normalizar_orden(texto)
    dominio = r"(?:workspace|work\s+space|world\s+space|word\s+space|espacio de trabajo|escritorio)"
    if re.fullmatch(
        r"(?:lista|muestra|dime|que) (?:los )?(?:espacios de trabajo|workspaces)(?: abiertos| existen)?",
        t,
    ):
        return _orden("workspace_list")
    if re.fullmatch(
        r"(?:vuelve|regresa)(?: al (?:workspace|espacio de trabajo|escritorio) anterior| al anterior)",
        t,
    ):
        return _orden("workspace_back")
    numeros = dict(
        zip(
            (
                "uno dos tres cuatro cinco seis siete ocho nueve diez primero segundo tercero cuarto quinto sexto septimo octavo noveno decimo"
            ).split(),
            list(range(1, 11)) * 2,
        )
    )
    m = re.fullmatch(
        rf"(?:(?P<mover>(?:mueve|manda|envia) (?:esta |la )?ventana)|(?:mueveme|llevame|cambia(?:me)?|ve|vete|pasate)) (?:al? |hacia el )?(?:{dominio} )?(?P<n>\d+|{'|'.join(numeros)})",
        t,
    )
    if not m:
        return None
    n = m["n"]
    target = str(numeros.get(n, n))
    if target == "0":
        target = "10"
    return _orden("workspace_move" if m["mover"] else "workspace_switch", target=target)


def _orden(accion, **params):
    return {
        "intent": "workspace",
        "action": accion,
        "params": params,
        "response": "",
        "confidence": 1.0,
    }
