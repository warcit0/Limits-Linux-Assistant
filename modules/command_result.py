"""Resultado compatible con str; la evidencia procede del handler, no del modelo."""


class ResultadoComando(str):
    def __new__(cls, texto, *, ok=None, verificado=False):
        obj = super().__new__(cls, texto)
        obj.ok = ok
        obj.verificado = bool(verificado)
        return obj


def normalizar_resultado(valor, *, lectura=False):
    """Adapta handlers antiguos sin confundir retorno vacío con éxito."""
    import re
    if isinstance(valor, ResultadoComando):
        ok = valor.ok is not False
        verificado = valor.verificado
        texto = str(valor)
    elif valor is None or valor == '':
        ok, verificado = False, False
        texto = 'La herramienta no devolvió evidencia del resultado.'
    else:
        texto = str(valor)
        fallo = bool(re.search(r'^(?:no pude|no puedo|error|ocurri[oó]|⚠|no hay|no existe|no he)\b',texto.strip(),re.I))
        # Una ausencia observada es válida para consultas, salvo fallo explícito.
        if lectura:
            fallo = bool(re.search(r'^(?:no pude|no puedo|error|ocurri[oó]|⚠)',texto.strip(),re.I))
        ok, verificado = not fallo, lectura and not fallo
    estado = 'fallido' if not ok else 'completado' if verificado else 'sin_verificar'
    resumen = texto if not isinstance(valor,(dict,list)) else 'La consulta devolvió datos estructurados.'
    if ok and not lectura and not isinstance(valor,ResultadoComando):
        resumen = 'La herramienta recibió la petición; su efecto no está comprobado.'
    return {'ok':ok,'verificado':verificado,'estado':estado,'datos':texto,
            'resumen':resumen,'evidencia':texto if verificado else '',
            'motivo':texto if not ok else ''}


def normalizar_recibo(recibo):
    """Contrato uniforme también para capacidades internas y sandbox."""
    r = dict(recibo)
    ok = r.get('ok') is True
    verificado = r.get('verificado',False) if ok else False
    r['ok'], r['verificado'] = ok, verificado
    r['estado'] = 'fallido' if not ok else 'completado' if verificado else 'sin_verificar'
    r.setdefault('resumen',str(r.get('datos','')) if isinstance(r.get('datos'),str) else '')
    r.setdefault('evidencia',r.get('datos') if verificado else None)
    r.setdefault('motivo','' if ok else 'La herramienta no completó el paso.')
    return r
