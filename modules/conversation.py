"""Contratos y contexto del interlocutor; el ciclo vive en coherent_agent."""

from copy import deepcopy


def esquema_conversacion(herramientas, contratos):
    from modules.coherent_agent import esquema_local
    base = esquema_local(herramientas, contratos)
    base['properties']['intent']['enum'] = ['command', 'chat', 'clarify']
    # Los máximos se validan al recibir la decisión: las repeticiones grandes
    # de la gramática de Ollama pueden derribar su proceso de inferencia.
    especialista = {'type':'object','properties':{
        'intent':{'const':'delegate'}, 'role':{'enum':['analisis','desarrollo','investigacion']},
        'response':{'type':'string'}},
        'required':['intent','role','response'],'additionalProperties':False}
    return {'anyOf':[base,especialista]}


def contexto_conversacion(tarea, contexto, anterior):
    """Separar diálogo, memoria confirmada y recibos; ningún dato otorga permisos."""
    c = {k:deepcopy(contexto[k]) for k in ('resultados','errores','raices','observadas','reproductor_elegido') if contexto.get(k)}
    c.update(interlocutor=True, entrada=contexto.get('entrada',tarea.objetivo),
             dialogo=tarea.dialogo[-6:], memorias=tarea.memorias[:2],
             referencias_aclaracion=tarea.entidades.get('referencias_aclaracion',[]),
             familias_disponibles=contexto.get('familias_disponibles',[]))
    # El historial sirve para resolver referencias. No reinyectar el objetivo,
    # los recibos ni la pregunta anterior como trabajo activo de esta petición.
    return c


def decidir_interlocutor(o, tarea, contexto, anterior):
    """Una decisión del asistente cotidiano; las observaciones regresan aquí."""
    from modules.coherent_agent import contexto_acotado, decision_local, texto_publico
    c = contexto_conversacion(tarea,contexto,anterior)
    c.update(herramientas=contexto['herramientas'],contratos=contexto['contratos'],semantico=True,coherente=True)
    c = contexto_acotado(c,o.config.AGENT_CONTEXT_CHARS)
    d = o._consultar(tarea,o.prompt_conversacion,c,rol='conversacion')
    if not isinstance(d,dict):
        raise ValueError('El interlocutor debe devolver una decisión estructurada.')
    if d.get('intent') == 'delegate':
        if (set(d) != {'intent','response','role'} or not isinstance(d['response'],str)
                or len(d['response'])>500 or d['role'] not in {'analisis','desarrollo','investigacion'}):
            raise ValueError('Indica un especialista disponible y response vacío.')
        return {'tipo':'delegar','rol':d['role']}
    salida = decision_local(d,tarea)
    salida['completa'] = d['complete']
    if salida['tipo'] in {'respuesta','pregunta'}:
        if not texto_publico(salida['texto']) or len(salida['texto'])>4000:
            raise ValueError('Responde de forma natural, sin JSON ni instrucciones internas.')
    return salida


def estado_respuesta(tarea, decision):
    """El estado depende de recibos, nunca de una afirmación de éxito del modelo."""
    from modules.general_agent import resultados_turno
    if decision['tipo']=='pregunta':
        return 'aclaracion'
    resultados = resultados_turno(tarea)
    if not resultados:
        tarea.entidades['tipo_cierre'] = 'conversacion'
        return 'terminada' if decision.get('completa') is True else 'parcial'
    tarea.entidades['tipo_cierre'] = 'operacion'
    if (decision.get('completa') is not True
            or any(p['estado'] != 'completado' for p in tarea.plan_resultados)
            or any(h.get('error') or not h.get('resultado',{}).get('ok') or not h.get('resultado',{}).get('verificado') for h in resultados)):
        return 'parcial'
    return 'terminada'
