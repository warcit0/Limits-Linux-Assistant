"""Acceso acotado a Spotify Web API y OAuth PKCE, sin secretos en el protocolo MCP."""

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
import urllib.parse
import requests

SCOPES = 'user-read-playback-state user-modify-playback-state user-read-currently-playing user-library-read playlist-read-private'


def guardar_token(config, datos):
    ruta = Path(config.SPOTIFY_TOKEN_PATH)
    ruta.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    ruta.parent.chmod(0o700)
    fd, temporal = tempfile.mkstemp(prefix='token-',dir=ruta.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(datos,f)
        os.replace(temporal,ruta)
    finally:
        if os.path.exists(temporal): os.unlink(temporal)


def intercambiar_codigo(config,codigo,verificador):
    r = requests.post('https://accounts.spotify.com/api/token',data={
        'client_id':config.SPOTIFY_CLIENT_ID,'grant_type':'authorization_code',
        'code':codigo,'redirect_uri':config.SPOTIFY_REDIRECT_URI,'code_verifier':verificador},timeout=15)
    if r.status_code != 200:
        raise ValueError('Spotify rechazó la autorización; revisa Client ID y redirect URI.')
    datos = r.json()
    datos['expires_at'] = time.time()+int(datos.get('expires_in',3600))
    guardar_token(config,datos)


class SpotifyAPI:
    def __init__(self,config):
        self.config = config

    def _token(self):
        c = self.config
        if not c.SPOTIFY_CLIENT_ID:
            raise ValueError('Spotify MCP está pendiente de configurar: falta SPOTIFY_CLIENT_ID y autorizar la cuenta con limits-spotify-login.')
        ruta = Path(c.SPOTIFY_TOKEN_PATH)
        if not ruta.is_file() or ruta.is_symlink():
            raise ValueError('Spotify requiere autorizar la cuenta con limits-spotify-login.')
        with os.fdopen(os.open(str(ruta)+'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),'w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            datos = json.loads(ruta.read_text())
            if float(datos.get('expires_at',0)) <= time.time()+30:
                r = requests.post('https://accounts.spotify.com/api/token',data={
                    'grant_type':'refresh_token','refresh_token':datos.get('refresh_token',''),
                    'client_id':c.SPOTIFY_CLIENT_ID},timeout=c.SPOTIFY_MCP_TIMEOUT)
                if r.status_code != 200:
                    raise ValueError('La autorización de Spotify caducó o fue revocada; vuelve a conectar la cuenta.')
                nuevo = r.json()
                datos.update(nuevo)
                datos['expires_at'] = time.time()+int(nuevo.get('expires_in',3600))
                guardar_token(c,datos)
            return datos['access_token']

    def _pedir(self,metodo,ruta,*,params=None,datos=None):
        # Todos los destinos se construyen aquí; el modelo nunca proporciona URLs.
        r = requests.request(metodo,'https://api.spotify.com/v1/'+ruta,
            headers={'Authorization':'Bearer '+self._token()},params=params,json=datos,
            timeout=self.config.SPOTIFY_MCP_TIMEOUT,allow_redirects=False)
        if r.status_code == 204:
            return None
        if r.status_code == 401:
            raise ValueError('Spotify necesita volver a autorizar la cuenta.')
        if r.status_code == 403:
            raise ValueError('Spotify no permite esta operación: revisa los permisos de la aplicación y los requisitos de tu cuenta, incluido Premium para reproducción Web API.')
        if r.status_code == 404:
            raise ValueError('Spotify no encontró un dispositivo activo o el contenido solicitado. Abre Spotify y consulta los dispositivos.')
        if r.status_code == 429:
            raise ValueError('Spotify limitó las peticiones. Espera '+str(r.headers.get('Retry-After','unos'))[:12]+' segundos; no repetiré la operación automáticamente.')
        if not 200 <= r.status_code < 300:
            raise ValueError('Spotify no pudo completar la operación (HTTP '+str(r.status_code)+').')
        return r.json()

    @staticmethod
    def _item(item):
        return {'uri':item.get('uri'),'nombre':item.get('name',''),
                'artistas':[a.get('name','') for a in item.get('artists',[])], 'tipo':item.get('type')}

    def estado(self):
        d = self._pedir('GET','me/player')
        if not d:
            return {'reproduciendo':False,'item':None,'dispositivo':None}
        return {'reproduciendo':d.get('is_playing',False),'item':self._item(d['item']) if d.get('item') else None,
                'contexto':(d.get('context') or {}).get('uri'),
                'dispositivo':{k:d.get('device',{}).get(k) for k in ('id','name','is_active')}}

    def ejecutar(self,nombre,p):
        if nombre == 'spotify_estado':
            d = self.estado()
            item = d.get('item')
            resumen = ('Está sonando ' if d['reproduciendo'] else 'Está pausada ')+(item['nombre']+'.' if item else 'la reproducción; no hay contenido activo confirmado.')
            return {'ok':True,'verificado':True,'datos':d,'resumen':resumen}
        if nombre == 'spotify_buscar':
            d = self._pedir('GET','search',params={'q':p['consulta'],'type':p.get('tipo','track'),'limit':5})
            items = [self._item(i) for grupo in d.values() if isinstance(grupo,dict) for i in grupo.get('items',[]) if isinstance(i,dict)]
            return {'ok':True,'verificado':True,'datos':items,'resumen':f'Encontré {len(items)} resultados en Spotify.'}
        if nombre == 'spotify_biblioteca':
            d = self._pedir('GET','me/tracks',params={'limit':10})
            items = [self._item(i['track']) for i in d.get('items',[]) if i.get('track')]
            return {'ok':True,'verificado':True,'datos':items,'resumen':f'Consulté {len(items)} canciones guardadas; es una muestra de tu biblioteca.'}
        if nombre == 'spotify_dispositivos':
            d = self._pedir('GET','me/player/devices')
            items = [{k:i.get(k) for k in ('id','name','is_active','is_restricted')} for i in d.get('devices',[])]
            return {'ok':True,'verificado':True,'datos':items,'resumen':f'Hay {len(items)} dispositivos disponibles en Spotify.'}
        if nombre == 'spotify_reproducir':
            uri = p['uri']
            tipo = uri.split(':')[1]
            cuerpo = {'uris':[uri]} if tipo in {'track','episode'} else {'context_uri':uri}
            self._pedir('PUT','me/player/play',params={'device_id':p['dispositivo']} if p.get('dispositivo') else None,datos=cuerpo)
            d = self.estado()
            mismo = (d.get('item') or {}).get('uri') == uri if tipo in {'track','episode'} else d.get('contexto') == uri
            verificado = bool(d['reproduciendo'] and mismo and (not p.get('dispositivo') or (d.get('dispositivo') or {}).get('id') == p['dispositivo']))
        else:
            accion = p['action']
            previo = self.estado() if accion in {'next','previous'} else None
            metodo,ruta = {'play':('PUT','play'),'pause':('PUT','pause'),'next':('POST','next'),'previous':('POST','previous')}[accion]
            self._pedir(metodo,'me/player/'+ruta)
            d = self.estado()
            if accion in {'next','previous'}:
                verificado = bool((d.get('item') or {}).get('uri') and (d.get('item') or {}).get('uri') != (previo.get('item') or {}).get('uri'))
            else:
                verificado = d['reproduciendo'] == (accion == 'play') and (accion != 'play' or bool(d.get('item')))
        resumen = ('He comprobado el cambio de reproducción en Spotify.' if verificado else 'Spotify aceptó la solicitud, pero aún no he comprobado el efecto; no la repetiré automáticamente.')
        return {'ok':True,'verificado':verificado,'datos':d,'resumen':resumen}
