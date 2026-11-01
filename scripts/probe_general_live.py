"""Aceptación general restaurable: modelo real, volumen/sistema y memoria aislada."""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from config import Config
from main import make_pipeline
from modules.agent_providers import crear_cotidiano
from modules.executor import CommandExecutor
from modules.gateway import TurnGate
from modules.llm import LLMEngine
from modules.memory import MemoryStore
from modules.orchestrator import Orquestador


def comando(*args):
    return subprocess.run(list(args),capture_output=True,text=True,timeout=30 if args[0]=='systemctl' else 5,check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live',required=True,action='store_true');p.parse_args()
    activo=subprocess.run(['systemctl','--user','is-active','--quiet','limits.service']).returncode==0
    volumen=comando('wpctl','get-volume','@DEFAULT_AUDIO_SINK@').stdout.split()[1]
    informe={'microfono':False,'proveedor_remoto':'Groq','turnos':[]}
    try:
        if activo:comando('systemctl','--user','stop','limits.service')
        with tempfile.TemporaryDirectory(prefix='limits-general-live-') as tmp:
            c=Config();c.AGENT_SEMANTIC=True;c.KNOWLEDGE_ENABLED=True;c.AGENT_ESCALATE=False
            c.AGENT_TASK_PATH=tmp+'/tareas';c.MEMORY_PATH=tmp+'/memoria.db';c.KNOWLEDGE_VAULT=tmp+'/vault';c.AGENT_TIMEOUT=90
            store=MemoryStore(c.MEMORY_PATH)
            try:
                with mock.patch('modules.memory.get_store',return_value=store):
                    proveedor=crear_cotidiano(c);ex=CommandExecutor()
                    orq=Orquestador(c,ex,proveedores={rol:proveedor for rol in ('cotidiano','analisis','desarrollo')})
                    pipeline=make_pipeline(LLMEngine(c),ex,mock.Mock(),TurnGate(),orchestrator=orq)
                    frases=['Me vendría bien tener el volumen al 37',
                            'Dime cuánto almacenamiento libre tengo',
                            'Recuerda que mi editor favorito es Code',
                            '¿Qué editor favorito te he dicho que uso?',
                            'Olvida mi editor favorito']
                    for i,frase in enumerate(frases):
                        antes=time.monotonic();r=pipeline(frase,speak=False,session_id='validacion:general')
                        if i==0:ok=abs(ex.system._volumen_real()-37)<=1 and r.ok is True
                        elif i==1:ok=r.ok is True and any(a['accion']=='get_system_info' for a in r.acciones)
                        elif i==2:ok=bool(orq.conocimiento.recuperar('editor favorito'))
                        elif i==3:ok='code' in str(r).casefold()
                        else:ok=not orq.conocimiento.recuperar('editor favorito') and not store.recall('editor_favorito')
                        dato={'frase':frase,'respuesta':str(r),'ok':ok,'segundos':round(time.monotonic()-antes,3),'acciones':getattr(r,'acciones',[]),'historial':orq.almacen.cargar('validacion:general').historial}
                        informe['turnos'].append(dato);print(json.dumps(dato,ensure_ascii=False),flush=True)
                    orq.conocimiento.close()
            finally:store.close()
        informe['ok']=all(t['ok'] for t in informe['turnos']) and len(informe['turnos'])==5
    finally:
        comando('wpctl','set-volume','@DEFAULT_AUDIO_SINK@',volumen)
        restaurado=comando('wpctl','get-volume','@DEFAULT_AUDIO_SINK@').stdout.split()[1]
        informe['volumen_restaurado']=restaurado==volumen
        if activo:comando('systemctl','--user','start','limits.service')
        informe['ok']=informe.get('ok',False) and informe['volumen_restaurado']
        (Path(__file__).resolve().parent.parent/'logs/probe_general_live_last.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2))
    return 0 if informe['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
