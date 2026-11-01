"""Conecta Spotify mediante PKCE y callback exclusivo en loopback."""

import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import secrets
import sys
import time
import urllib.parse
import webbrowser

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from config import Config
from modules.spotify_api import SCOPES,intercambiar_codigo


def main():
    config = Config()
    if not config.SPOTIFY_CLIENT_ID:
        print('Configura SPOTIFY_CLIENT_ID en .env y registra http://127.0.0.1:8898/callback en Spotify Developer.')
        return 1
    verificador = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b'=').decode()
    estado = secrets.token_urlsafe(32)
    resultado = {}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            uri = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(uri.query)
            valido = uri.path == '/callback' and hmac.compare_digest(q.get('state',[''])[0],estado)
            if valido:
                resultado['code'] = q.get('code',[''])[0]
                resultado['error'] = q.get('error',[''])[0]
            self.send_response(200 if valido else 400)
            self.send_header('Content-Type','text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(('Puedes volver a Limits.' if valido else 'Callback no válido.').encode())
    url = 'https://accounts.spotify.com/authorize?'+urllib.parse.urlencode({'response_type':'code',
        'client_id':config.SPOTIFY_CLIENT_ID,'redirect_uri':config.SPOTIFY_REDIRECT_URI,
        'scope':SCOPES,'state':estado,'code_challenge_method':'S256','code_challenge':challenge})
    with HTTPServer(('127.0.0.1',8898),Callback) as servidor:
        servidor.timeout = 1
        print('Abriendo Spotify para autorizar la cuenta. Espera máxima: 3 minutos.')
        if not webbrowser.open(url):
            print('No pude abrir el navegador. Ejecuta este comando desde tu sesión gráfica.')
            return 1
        fin = time.monotonic()+180
        while not resultado and time.monotonic()<fin:
            servidor.handle_request()
    if not resultado.get('code'):
        print('No se completó la autorización de Spotify.')
        return 1
    try:
        intercambiar_codigo(config,resultado['code'],verificador)
    except (ValueError,OSError):
        print('No pude conectar Spotify. Revisa Client ID, redirect URI y conexión.')
        return 1
    print('Spotify conectado. Activa SPOTIFY_MCP_ENABLED=true y reinicia Limits.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
