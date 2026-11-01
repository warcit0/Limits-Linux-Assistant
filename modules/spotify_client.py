"""Cliente MCP stdio acotado, cancelable y sin repetición automática de efectos."""

import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

from modules.spotify_mcp import validar


def llamar(config,nombre,parametros,cancelar):
    validar(nombre,parametros)
    if cancelar.is_set():
        raise ValueError('Operación Spotify cancelada.')
    if not config.SPOTIFY_MCP_ENABLED or not config.SPOTIFY_CLIENT_ID:
        raise ValueError('Spotify MCP está preparado pero falta conectar tu cuenta; los controles locales siguen disponibles.')
    proceso = subprocess.Popen([sys.executable,'-m','modules.spotify_mcp'],cwd=Path(__file__).resolve().parent.parent,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
    fin = time.monotonic()+config.SPOTIFY_MCP_TIMEOUT
    selector = selectors.DefaultSelector()
    selector.register(proceso.stdout,selectors.EVENT_READ)
    buffer = b''
    def enviar(m):
        proceso.stdin.write((json.dumps(m,ensure_ascii=False)+'\n').encode())
        proceso.stdin.flush()
    def recibir(id_):
        nonlocal buffer
        while time.monotonic()<fin:
            if cancelar.is_set():
                raise ValueError('Operación Spotify cancelada; comprueba su estado antes de repetirla.')
            if b'\n' in buffer:
                linea,buffer = buffer.split(b'\n',1)
                m = json.loads(linea)
                if m.get('id') == id_:
                    if 'error' in m:
                        raise ValueError('El servidor MCP rechazó la petición.')
                    return m['result']
            elif selector.select(.1):
                bloque = os.read(proceso.stdout.fileno(),65536)
                if not bloque:
                    raise ValueError('El servidor Spotify MCP se cerró antes de responder.')
                buffer += bloque
                if len(buffer)>128000:
                    raise ValueError('Respuesta Spotify demasiado grande.')
        raise ValueError('Spotify agotó el tiempo disponible; consulta el estado antes de repetir una acción.')
    try:
        enviar({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'Limits','version':'1.0.0'}}})
        recibir(1)
        enviar({'jsonrpc':'2.0','method':'notifications/initialized'})
        enviar({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':nombre,'arguments':parametros}})
        r = recibir(2)
        contenido = r.get('content',[])
        if not contenido or contenido[0].get('type') != 'text':
            raise ValueError('Spotify MCP devolvió un resultado inválido.')
        datos = json.loads(contenido[0]['text'])
        if not isinstance(datos,dict):
            raise ValueError('Spotify MCP devolvió un resultado inválido.')
        return datos
    finally:
        selector.close()
        try:
            os.killpg(proceso.pid,signal.SIGTERM)
            proceso.wait(timeout=1)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(proceso.pid,signal.SIGKILL)
            proceso.wait(timeout=1)
        proceso.stdin.close()
        proceso.stdout.close()
