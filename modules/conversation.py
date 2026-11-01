"""Contratos y contexto del interlocutor; el ciclo vive en coherent_agent."""

from copy import deepcopy


def esquema_conversacion(herramientas, contratos):
    from modules.coherent_agent import esquema_local
    base = esquema_local(herramientas, contratos)
    base['properties']['intent']['enum'] = ['command', 'chat', 'clarify']
    encargo = {'type':'object', 'properties':{
        'intent':{'const':'task'}, 'goal':{'type':'string','minLength':1,'maxLength':4000},
        'response':{'type':'string','maxLength':500}},
        'required':['intent','goal','response'],'additionalProperties':False}
    especialista = {'type':'object','properties':{
        'intent':{'const':'delegate'}, 'role':{'enum':['analisis','desarrollo','investigacion']},
        'response':{'type':'string','maxLength':500}},
        'required':['intent','role','response'],'additionalProperties':False}
    return {'anyOf':[base,encargo,especialista]}


def contexto_conversacion(tarea, contexto, anterior):
    """Separar diálogo, memoria confirmada y recibos; ningún dato otorga permisos."""
    from modules.clock import now_line
    c = {k:deepcopy(contexto[k]) for k in ('entrada','resultados','errores','raices','observadas','reproductor_elegido') if contexto.get(k)}
    c.update(interlocutor=True, ahora=now_line(), dialogo=tarea.dialogo,
             memorias=tarea.memorias, encargo=tarea.encargo,
             devolucion_ejecutor=tarea.entidades.get('devolucion_ejecutor',''),
             familias_disponibles=contexto.get('familias_disponibles',[]))
    if anterior and not tarea.entidades.get('memoria_olvidada') and anterior.estado not in {'cancelada','aprobacion','interrumpida','trabajando'}:
        c['continuidad'] = {'objetivo':anterior.objetivo[:2000],
            'estado':anterior.estado,'pregunta':anterior.pregunta_abierta,
            'resultados_anteriores':[{'herramienta':h['herramienta'],
                'resultado':{'ok':h.get('resultado',{}).get('ok'),
                    'verificado':h.get('resultado',{}).get('verificado'),
                    'resumen':str(h.get('resultado',{}).get('resumen',''))[:500],
                    'datos':str(h.get('resultado',{}).get('datos',''))[:1200]}}
                for h in anterior.historial if h.get('herramienta')][-3:]}
    return c


def decidir_interlocutor(o, tarea, contexto, anterior):
    """Una inferencia: conversación, llamada directa o encargo al ejecutor."""
    from modules.coherent_agent import contexto_acotado, decision_local, texto_publico
    c = contexto_conversacion(tarea,contexto,anterior)
    c.update(herramientas=contexto['herramientas'],contratos=contexto['contratos'],semantico=True,coherente=True)
    c = contexto_acotado(c,o.config.AGENT_CONTEXT_CHARS)
    d = o._consultar(tarea,o.prompt_conversacion,c,rol='conversacion')
    if not isinstance(d,dict):
        raise ValueError('El interlocutor debe devolver una decisión estructurada.')
    if d.get('intent') in {'task','delegate'}:
        campos = {'intent','response','goal' if d['intent']=='task' else 'role'}
        if set(d) != campos or not isinstance(d.get('response'),str) or len(d['response'])>500:
            raise ValueError('Indica el encargo o el especialista y una frase breve de intención.')
        if d['intent']=='task':
            if not isinstance(d['goal'],str) or not 1<=len(d['goal'].strip())<=4000:
                raise ValueError('El encargo necesita un objetivo concreto.')
            tarea.encargo = d['goal'].strip()
            salida = {'tipo':'encargo'}
        else:
            if d['role'] not in {'analisis','desarrollo','investigacion'}:
                raise ValueError('Ese especialista no está disponible.')
            salida = {'tipo':'delegar','rol':d['role']}
        if d['response'].strip():
            # Solo intención; nunca una afirmación de éxito anterior a los recibos.
            callback = o._callbacks.get(tarea.sesion)
            if callback:
                callback({'v':1,'type':'speech','text':d['response'].strip()})
        return salida
    salida = decision_local(d,tarea)
    if salida['tipo'] in {'respuesta','pregunta'}:
        if not texto_publico(salida['texto']) or len(salida['texto'])>4000:
            raise ValueError('Responde de forma natural, sin JSON ni instrucciones internas.')
        salida['completa'] = d['complete']
    return salida


def estado_respuesta(tarea, decision):
    """El estado depende de recibos, nunca de una afirmación de éxito del modelo."""
    from modules.general_agent import resultados_turno
    if decision['tipo']=='pregunta':
        return 'aclaracion'
    resultados = resultados_turno(tarea)
    if decision.get('completa') is not True or any(h.get('error') or not h.get('resultado',{}).get('ok') or not h.get('resultado',{}).get('verificado') for h in resultados):
        return 'parcial'
    return 'terminada'
