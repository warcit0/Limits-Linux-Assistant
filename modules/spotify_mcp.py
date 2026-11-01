"""Servidor MCP stdio privado para Spotify, limitado a seis herramientas.

Protocolo JSON-RPC MCP 2024-11-05; stdout se reserva para mensajes del protocolo.
Sin shell, puertos públicos, herramientas arbitrarias ni credenciales en resultados.
"""

import json
import re
import sys


def _contrato(nombre,descripcion,propiedades=None,requeridos=None):
    return {'name':nombre,'description':descripcion,'inputSchema':{'type':'object','properties':propiedades or {},
        'required':requeridos or [],'additionalProperties':False}}

TEXTO = {'type':'string','minLength':1,'maxLength':500}
CONTRATOS = [
    _contrato('spotify_buscar','Busca canciones, artistas, álbumes o playlists; no reproduce.',{'consulta':TEXTO,'tipo':{'type':'string','enum':['track','artist','album','playlist']}},['consulta']),
    _contrato('spotify_biblioteca','Consulta una muestra de canciones guardadas; no modifica la biblioteca.'),
    _contrato('spotify_estado','Consulta reproducción actual y dispositivo activo.'),
    _contrato('spotify_dispositivos','Consulta dispositivos disponibles; no cambia el destino.'),
    _contrato('spotify_reproducir','Reproduce una URI observada; dispositivo opcional debe estar observado.',{'uri':TEXTO,'dispositivo':TEXTO},['uri']),
    _contrato('spotify_control','Cambia reproducción: play reanuda contenido actual; pause pausa; next/previous cambian canción.',{'action':{'type':'string','enum':['play','pause','next','previous']}},['action']),
]
LECTURAS_SPOTIFY = {c['name'] for c in CONTRATOS[:4]}
ACCIONES_SPOTIFY = {c['name'] for c in CONTRATOS[4:]}


def validar(nombre,p):
    contrato = next((c for c in CONTRATOS if c['name'] == nombre),None)
    if not contrato or not isinstance(p,dict):
        raise ValueError('Herramienta Spotify no permitida.')
    esquema = contrato['inputSchema']
    if set(p)-set(esquema['properties']) or set(esquema['required'])-set(p):
        raise ValueError('Los parámetros no coinciden con la herramienta Spotify.')
    for k,v in p.items():
        regla = esquema['properties'][k]
        if not isinstance(v,str) or not v.strip() or len(v)>500 or 'enum' in regla and v not in regla['enum']:
            raise ValueError('Parámetro Spotify inválido.')
    if nombre == 'spotify_reproducir' and not re.fullmatch(r'spotify:(?:track|episode|album|artist|playlist):[A-Za-z0-9]{22}',p['uri']):
        raise ValueError('URI Spotify no válida.')


def servir(config):
    from modules.spotify_api import SpotifyAPI
    api = SpotifyAPI(config)
    inicializado = False
    for linea in sys.stdin:
        if len(linea)>64000:
            break
        mensaje = {}
        try:
            mensaje = json.loads(linea)
            if not isinstance(mensaje,dict):
                continue
            if 'id' not in mensaje:
                continue
            metodo = mensaje.get('method')
            if metodo == 'initialize':
                inicializado = True
                resultado = {'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'limits-spotify','version':'1.0.0'}}
            elif not inicializado:
                raise ValueError('Inicializa la sesión MCP primero.')
            elif metodo == 'ping':
                resultado = {}
            elif metodo == 'tools/list':
                resultado = {'tools':CONTRATOS}
            elif metodo == 'tools/call':
                p = mensaje.get('params',{})
                nombre,args = p.get('name'),p.get('arguments',{})
                validar(nombre,args)
                from modules.memory import redact
                datos = json.loads(redact(json.dumps(api.ejecutar(nombre,args),ensure_ascii=False)))
                resultado = {'content':[{'type':'text','text':json.dumps(datos,ensure_ascii=False)}],'isError':False}
            else:
                raise ValueError('Método MCP no permitido.')
            salida = {'jsonrpc':'2.0','id':mensaje['id'],'result':resultado}
        except (ValueError,KeyError,TypeError,OSError) as e:
            # No revelar objetos HTTP, tokens ni cuerpos de errores remotos.
            texto = str(e) if isinstance(e,ValueError) else 'No pude comunicarme con Spotify; revisa la conexión y autorización.'
            salida = {'jsonrpc':'2.0','id':mensaje.get('id'),'result':{'content':[{'type':'text','text':json.dumps({'ok':False,'verificado':False,'resumen':texto})}],'isError':True}}
        print(json.dumps(salida,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    from config import Config
    servir(Config())
