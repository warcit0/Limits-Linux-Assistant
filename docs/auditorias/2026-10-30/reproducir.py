import sys, json, tempfile, asyncio, threading
from pathlib import Path
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(Path.cwd()))
from commands.dev import DevCommands
from commands.apps import AppCommands
from modules.grounding import check
from modules.executor import CommandExecutor
from modules.memory import MemoryStore
from modules.gateway import GatewayServer, TurnGate, regenerate_token
from modules.desktop_agent import DesktopAgent
from main import make_pipeline
out={}
with patch('commands.dev.subprocess.Popen') as pop:
    DevCommands().run_command('echo inocuo; echo SEGUNDO_COMANDO',show_output=True)
    out['shell_terminal']=pop.call_args.args[0]
e=CommandExecutor()
proposal={'intent':'app_open','action':'open_application','params':{'app':'python3','args':['-c','print("solo prueba")']},'response':'Hecho'}
v=check(proposal['action'],proposal['params'],'hola',frozenset(e.action_map))
with patch('commands.apps.subprocess.Popen') as pop:
    e.execute({**proposal,'grounded':v.ok})
    out['app_arbitraria']={'grounding':v.ok,'argv':pop.call_args.args[0] if pop.called else None}
with tempfile.TemporaryDirectory() as tmp:
    store=MemoryStore(Path(tmp)/'memory.db')
    store.remember('color','azul')
    with ThreadPoolExecutor(max_workers=1) as pool:
        out['memoria_otro_hilo']=pool.submit(lambda:{'recall':store.recall('color'),'remember':store.remember('color','verde'),'stats':store.stats()}).result()
    out['memoria_hilo_original']=store.recall('color')
    store.remember('color','rojo');store.forget('color')
    out['olvido_historial_restante']=store._conn.execute('SELECT COUNT(*) FROM fact_history').fetchone()[0]
    store.close()
    server=GatewayServer(Mock(),token_path=str(Path(tmp)/'token'))
    old=server.token;new=regenerate_token(str(Path(tmp)/'token'))
    out['rotacion']={'archivo_cambio':old!=new,'servidor_conserva_anterior':server.token==old}
llm=Mock();llm.process.return_value={'action':'confirm','intent':'confirm','confidence':0.01,'grounded':True}
e=CommandExecutor();danger=Mock(return_value='APAGADO SIMULADO');e.action_map['shutdown']=danger
e.execute({'action':'shutdown','response':'Apagando'})
pipeline=make_pipeline(llm,e,Mock(),TurnGate(),gemini=Mock(chat=Mock(return_value='respuesta simulada')))
with patch('modules.memory.get_store',return_value=Mock()):
    pipeline('gemini hola',speak=False)
    out['pending_despues_gemini']=e._pending_action is not None
    pipeline('cualquier frase',speak=False)
    out['confirm_baja_confianza']=danger.called
files=Mock();files.last_matches=['/tmp/archivo_turno_anterior'];files.last_opened=None
agent=DesktopAgent(files=files,opencode_api_key='simulada')
out['path_guard_estado_anterior']=agent._path_guard('copy_file',{'source':'/tmp/archivo_turno_anterior'})
voice=Mock();pipe=make_pipeline(Mock(),Mock(),voice,TurnGate(),gemini=Mock(chat=Mock(return_value='respuesta Gemini')))
with patch('modules.memory.get_store',return_value=Mock()): pipe('gemini hola')
out['gemini_source']= {'args':voice.speak.call_args.args,'kwargs':voice.speak.call_args.kwargs}
async def overlap():
    gate=TurnGate();started=threading.Event();finish=threading.Event();over=[]
    def pipeline(text,timeout,speak):
        assert gate.acquire(timeout)
        try:return 'respuesta'
        finally:gate.release()
    def speak(text):
        unlocked=gate.acquire(0)
        over.append(unlocked)
        if unlocked:gate.release()
    with tempfile.TemporaryDirectory() as tmp:
        server=GatewayServer(pipeline,token_path=str(Path(tmp)/'token'),speak_fn=speak)
        ws=Mock();ws.send_json=__import__('unittest.mock',fromlist=['AsyncMock']).AsyncMock()
        await server._run_command(ws,'hola')
    return over
out['gate_libre_durante_tts_remoto']=asyncio.run(overlap())
Path('/tmp/limits-audit-probes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2))
