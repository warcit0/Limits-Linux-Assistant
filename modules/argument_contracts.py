"""Normaliza nombres de parámetros contra la firma real, sin inferir acciones."""

import inspect

ALIAS = {
    'command': ('action',),
    'component': ('type',),
    'value': ('level',),
    'volume': ('level',),
    'brightness': ('level',),
    'workspace': ('target',),
    'application': ('app',),
    'filepath': ('path', 'ruta'),
}


def normalizar_argumentos(handler, parametros):
    if not isinstance(parametros,dict):
        raise ValueError('Los parámetros deben ser un objeto.')
    permitidos=inspect.signature(handler).parameters
    salida=dict(parametros)
    for clave,valor in parametros.items():
        if clave in permitidos:
            continue
        destinos=[d for d in ALIAS.get(clave,()) if d in permitidos]
        if len(destinos)!=1:
            continue
        destino=destinos[0]
        if destino in salida and salida[destino]!=valor:
            raise ValueError(f'Parámetros contradictorios para {destino}.')
        salida[destino]=salida.pop(clave)
    return salida
