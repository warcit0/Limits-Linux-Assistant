"""Catálogo observado de aplicaciones .desktop; apertura sin shell ni rutas del modelo."""

import configparser
from difflib import SequenceMatcher
import hashlib
from pathlib import Path
import re
import subprocess
import time
from modules.grounding import fold

RAICES = (Path.home()/'.local/share/applications', Path('/usr/local/share/applications'), Path('/usr/share/applications'))


def catalogo():
    resultado = {}
    for raiz in RAICES:
        if not raiz.is_dir():
            continue
        for ruta in sorted(raiz.rglob('*.desktop'))[:1500]:
            if ruta.is_symlink():
                continue
            id_ = str(ruta.relative_to(raiz)).replace('/','-')
            if id_ in resultado:
                continue
            try:
                raw = ruta.read_bytes()
                if len(raw)>64000:
                    continue
                parser = configparser.ConfigParser(interpolation=None,strict=False)
                parser.read_string(raw.decode('utf-8'))
                e = parser['Desktop Entry']
                if e.get('Type','Application') != 'Application' or e.get('Hidden','false').lower() == 'true' or e.get('NoDisplay','false').lower() == 'true':
                    continue
                nombre = e.get('Name[es]',e.get('Name','')).strip()
                if not nombre or not e.get('Exec'):
                    continue
                resultado[id_] = {'id':id_,'nombre':nombre,'descripcion':e.get('Comment[es]',e.get('Comment',''))[:200],
                    'palabras':e.get('Keywords[es]',e.get('Keywords',''))[:300], 'clase':e.get('StartupWMClass',''),
                    'ruta':str(ruta),'huella':hashlib.sha256(raw).hexdigest()}
            except (OSError,ValueError,UnicodeError,configparser.Error,KeyError):
                continue
    return resultado


def buscar(consulta):
    tokens = [x for x in re.findall(r'\w+',fold(consulta)) if len(x)>2 and x not in {'del','los','las','una','para'}]
    if not tokens:
        return []
    candidatos = []
    instaladas = list(catalogo().values())
    for app in instaladas:
        texto = fold(' '.join(str(app[k]) for k in ('id','nombre','descripcion','palabras','clase')))
        puntuacion = sum(1 for token in tokens if token in texto)
        if puntuacion:
            candidatos.append((puntuacion/len(tokens),app))
    candidatos.sort(key=lambda x:(-x[0],x[1]['nombre']))
    if not candidatos:
        # Sugerencias, nunca aperturas implícitas: solo nombres parecidos con prefijo común.
        consulta_normal = fold(consulta).strip()
        aproximadas = []
        if len(consulta_normal) >= 4:
            for app in instaladas:
                nombres = [fold(app['nombre']),fold(Path(app['id']).stem.rsplit('.',1)[-1])]
                similitud = max((SequenceMatcher(None,consulta_normal,n).ratio() for n in nombres if n[:2] == consulta_normal[:2]),default=0)
                if similitud >= .5:
                    aproximadas.append((similitud,{**app,'aproximada':True}))
        aproximadas.sort(key=lambda p:(-p[0],p[1]['nombre']))
        return [app for _,app in aproximadas[:3]]
    mejores = [app for puntuacion,app in candidatos if puntuacion>=max(.5,candidatos[0][0]-.15)]
    return mejores[:12]


def abrir(tarea,id_,cancelar):
    observado = tarea.entidades.get('aplicaciones',{}).get(id_)
    actual = catalogo().get(id_)
    if not observado or not actual or actual['huella'] != observado.get('huella'):
        raise ValueError('La aplicación cambió o no está observada; vuelve a buscarla.')
    if cancelar.is_set():
        raise ValueError('Apertura cancelada.')
    subprocess.Popen(['gio','launch',actual['ruta']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    from commands.workspaces import WorkspaceCommands
    ws = WorkspaceCommands()
    claves = {fold(actual['clase']),fold(Path(id_).stem),fold(actual['nombre'])} - {''}
    fin = time.monotonic()+4
    while time.monotonic()<fin:
        if cancelar.is_set():
            return {'ok':True,'verificado':False,'datos':'La apertura se solicitó antes de cancelar; no la repetiré automáticamente.'}
        for v in ws._leer('clients'):
            if claves & {fold(v.get('class','')),fold(v.get('initialClass',''))}:
                texto = actual['nombre']+' está abierta; he comprobado su ventana.'
                return {'ok':True,'verificado':True,'datos':texto,'resumen':texto}
        cancelar.wait(.1)
    texto = 'He solicitado abrir '+actual['nombre']+', pero todavía no he comprobado su ventana.'
    return {'ok':True,'verificado':False,'datos':texto,'resumen':texto}
