"""Una aceptación acotada, sin audio/micrófono y con volumen restaurado."""

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import Config
from modules.orchestrator import Orquestador
from modules.executor import CommandExecutor
from modules.agent_providers import ProveedorNvidia, ProveedorOllama, Cancelado


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live",action="store_true")
    if not parser.parse_args().live:
        parser.error("La aceptación con modelos reales requiere --live.")
    config=Config()
    config.AGENT_SEMANTIC=config.AGENT_COHERENT=True
    config.KNOWLEDGE_ENABLED=False
    config.AGENT_MAX_STEPS=5
    config.AGENT_TIMEOUT=35
    cantidad=0
    inicio=time.monotonic()
    informe={'tipo':'aceptacion_acotada','limite_inferencias':20,'limite_segundos':180,'turnos':[]}
    originales={c:c.consultar for c in (ProveedorNvidia,ProveedorOllama)}
    def limitada(self,*args,**kwargs):
        nonlocal cantidad
        restante=180-(time.monotonic()-inicio)
        if cantidad>=20 or restante<=0:
            raise Cancelado('Presupuesto de aceptación agotado.')
        cantidad+=1
        kwargs['timeout']=min(kwargs['timeout'],restante)
        clase=ProveedorNvidia if isinstance(self,ProveedorNvidia) else ProveedorOllama
        return originales[clase](self,*args,**kwargs)
    ex=CommandExecutor()
    volumen=ex.system._volumen_real()
    if volumen is None:
        raise SystemExit('No pude obtener el volumen inicial; no se inicia la aceptación.')
    turnos=['Hola Limits', 'Qué hay en el workspace 1', f'Pon el volumen al {volumen}',
            'Qué volumen tengo y cuánta RAM estoy usando',
            'No cambies nada. Qué aplicaciones están abiertas',
            'Qué me recomiendas hacer ahora']
    try:
        with tempfile.TemporaryDirectory(prefix='limits-coherente-') as tmp, patch.object(ProveedorNvidia,'consultar',limitada),patch.object(ProveedorOllama,'consultar',limitada):
            config.AGENT_TASK_PATH=tmp
            o=Orquestador(config,ex)
            for texto in turnos:
                previo=cantidad
                reloj=time.monotonic()
                r=o.atender(texto,sesion='aceptacion')
                tarea=o.almacen.cargar('aceptacion')
                # Solo escenarios fijos; conservar resúmenes, nunca títulos/credenciales del escritorio.
                informe['turnos'].append({'peticion':texto,'segundos':round(time.monotonic()-reloj,3),
                    'inferencias':cantidad-previo,'estado':tarea.estado,'ok':getattr(r,'ok',None),
                    'herramientas':[{'accion':h['herramienta'],'ok':h.get('resultado',{}).get('ok'),
                                     'verificado':h.get('resultado',{}).get('verificado')} for h in tarea.historial if h.get('herramienta')]})
                o.registrar_dialogo(texto,r,'aceptacion')
                if tarea.estado in {'error','cancelada','interrumpida','parcial'}:
                    informe['detenido']='El turno no se completó; no se repite ni se cambia de modelo para mejorar la cifra.'
                    break
    finally:
        ex.system.set_volume(volumen)
        informe['inferencias']=cantidad
        informe['segundos']=round(time.monotonic()-inicio,3)
        ruta=Path('logs/probe_coherent_last.json')
        ruta.parent.mkdir(exist_ok=True)
        ruta.write_text(json.dumps(informe,ensure_ascii=False,indent=2))
        ruta.chmod(0o600)
        print(json.dumps(informe,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
