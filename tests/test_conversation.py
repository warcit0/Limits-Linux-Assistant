"""Regresiones simuladas preparadas; no ejecutadas por petición del usuario."""

import tempfile
import unittest
from unittest.mock import patch

from config import Config
from modules.command_result import ResultadoComando
from modules.conversation import estado_respuesta
from modules.local_permissions import autorizar_capacidad
from modules.orchestrator import Orquestador
from modules.task_state import Tarea
from test_objectives import ExecutorFalso, ProveedorFalso


def texto(respuesta, intent='chat', complete=True):
    return {'intent':intent,'operations':[],'complete':complete,'response':respuesta}


def lote(accion, parametros, complete=True):
    return {'intent':'command','operations':[{'action':accion,'params':parametros}],
            'complete':complete,'response':''}


def entrega(respuesta, complete=True):
    return {'intent':'chat','complete':complete,'response':respuesta}


class TestInterlocutor(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config=Config()
        self.config.AGENT_MODE='conversacional'
        self.config.AGENT_SEMANTIC=self.config.AGENT_COHERENT=True
        self.config.AGENT_TASK_PATH=self.tmp.name
        self.config.KNOWLEDGE_ENABLED=False
        self.config.AGENT_QWEN_DIAGNOSTICS=False
        self.config.AGENT_TIMEOUT=10
        self.config.AGENT_MAX_STEPS=6
        self.ex=ExecutorFalso()
        self.cambios=[]
        def volumen(level:int):
            self.cambios.append(level)
            return ResultadoComando('Volumen comprobado.',ok=True,verificado=True)
        self.ex.action_map['set_volume']=volumen

    def crear(self, decisiones, ejecutor=None):
        self.interlocutor=ProveedorFalso(*decisiones)
        self.ejecutor=ejecutor or ProveedorFalso()
        self.o=Orquestador(self.config,self.ex,proveedores={
            'conversacion':self.interlocutor,'cotidiano':self.ejecutor})
        return self.o

    def test_conversar_no_invoca_ejecutor(self):
        o=self.crear([texto('Podemos organizar las ideas. ¿Qué quieres conseguir?')])
        r=o.atender('Tengo ganas de organizarme')
        self.assertIn('Qué quieres',r)
        self.assertEqual(self.ejecutor.consultas,[])
        self.assertEqual(self.cambios,[])

    def test_llamada_directa_entrega_recibo_sin_otra_inferencia(self):
        o=self.crear([lote('set_volume',{'level':35}),entrega('Está al 35 %.')])
        with patch('modules.local_permissions.autorizar',side_effect=AssertionError('No usar permisos léxicos')):
            r=o.atender('Déjalo un poco más bajo, al treinta y cinco')
        self.assertEqual(self.cambios,[35])
        self.assertEqual(str(r),'Volumen comprobado.')
        self.assertFalse(self.ejecutor.consultas)
        self.assertEqual(len(self.interlocutor.consultas),1)

    def test_consultar_y_actuar_usa_el_mismo_asistente(self):
        o=self.crear([lote('get_volume',{},False),lote('set_volume',{'level':20})])
        eventos=[]
        r=o.atender('Consulta el volumen y déjalo al veinte',on_event=eventos.append)
        self.assertEqual(self.cambios,[20])
        self.assertEqual(len(self.interlocutor.consultas),2)
        self.assertEqual(self.ejecutor.consultas,[])
        c=self.interlocutor.consultas[-1][1]
        self.assertEqual(c['entrada'],'Consulta el volumen y déjalo al veinte')
        self.assertEqual(c['resultados'][0]['herramienta'],'get_volume')
        self.assertNotIn('encargo',c)
        self.assertEqual(eventos,[])
        self.assertTrue(r.ok)

    def test_encargo_antiguo_no_activa_un_segundo_ejecutor(self):
        o=self.crear([{'intent':'task','goal':'Cambiar volumen','response':''},
                      lote('set_volume',{'level':20})])
        o.atender('Déjalo al veinte')
        self.assertFalse(self.ejecutor.consultas)
        self.assertEqual(len(self.interlocutor.consultas),2)
        self.assertEqual(self.cambios,[20])

    def test_respuesta_corta_conserva_pregunta_y_dialogo(self):
        o=self.crear([texto('¿Prefieres trabajar con música o en silencio?','clarify',False),
                      texto('De acuerdo, trabajamos en silencio.')])
        r=o.atender('Ayúdame a concentrarme')
        o.registrar_dialogo('Ayúdame a concentrarme',r,'local')
        o.atender('En silencio')
        c=self.interlocutor.consultas[-1][1]
        self.assertNotIn('continuidad',c)
        self.assertEqual(c['dialogo'][0]['usuario'],'Ayúdame a concentrarme')

    def test_sensible_pide_confirmacion_sin_ejecutar(self):
        o=self.crear([lote('consultar_capacidades',{'categoria':'sistema'},False),
                      lote('shutdown',{})])
        r=o.atender('Apaga el equipo')
        self.assertIn('confirmar',r)
        self.assertEqual(self.ex.apagados,0)
        self.assertEqual(o.almacen.cargar('local').estado,'aprobacion')

    def test_adelante_sin_aprobacion_es_dialogo(self):
        o=self.crear([texto('Podemos empezar por ordenar tus ideas.')])
        self.assertIn('ideas',o.atender('Adelante'))
        self.assertEqual(len(self.interlocutor.consultas),1)

    def test_efecto_incierto_no_se_repite(self):
        def incierto(level:int):
            self.cambios.append(level)
            return ResultadoComando('Solicitud enviada.',ok=True,verificado=False)
        self.ex.action_map['set_volume']=incierto
        o=self.crear([lote('set_volume',{'level':20}),
                      entrega('Lo solicité, pero no pude comprobar el cambio.',complete=False)])
        r=o.atender('Baja al veinte')
        self.assertEqual(self.cambios,[20])
        self.assertIsNone(r.ok)

    def test_entrega_no_repite_efectos_ni_reintenta_inferencias(self):
        repetido=lote('set_volume',{'level':20})
        o=self.crear([repetido,repetido])
        r=o.atender('Baja al veinte')
        self.assertEqual(self.cambios,[20])
        self.assertEqual(len(self.interlocutor.consultas),1)
        self.assertIn('comprobado',str(r))
        self.assertNotIn('Quedan partes',str(r))
        self.assertTrue(r.ok)

    def test_efecto_no_final_continua_con_el_mismo_modelo(self):
        o=self.crear([lote('set_volume',{'level':20},False),
                      texto('Volumen ajustado y comprobado.')])
        r=o.atender('Baja al veinte')
        self.assertEqual(self.cambios,[20])
        self.assertEqual(len(self.interlocutor.consultas),2)
        self.assertFalse(self.ejecutor.consultas)
        self.assertEqual(str(r),'Volumen comprobado.')

    def test_atajo_completo_no_necesita_inferencia(self):
        o=self.crear([])
        r=o.atender('qué hora es')
        self.assertEqual(len(self.interlocutor.consultas),0)
        self.assertIn('doce',str(r))

    def test_lote_sensible_no_adelanta_efectos(self):
        decision={'intent':'command','operations':[
            {'action':'set_volume','params':{'level':20}},
            {'action':'shutdown','params':{}}],'complete':True,'response':''}
        o=self.crear([lote('consultar_capacidades',{'categoria':'sistema'},False),decision])
        r=o.atender('Baja al veinte y apaga el equipo')
        self.assertIn('confirmar',str(r))
        self.assertEqual(self.cambios,[])
        self.assertEqual(self.ex.apagados,0)
        t=o.almacen.cargar('local')
        self.assertEqual(len(t.pendiente['lote']),2)
        o.atender('confirmo')
        self.assertEqual(self.cambios,[20])
        self.assertEqual(self.ex.apagados,1)

    def test_chat_inicial_no_se_registra_como_operacion(self):
        o=self.crear([texto('He cambiado de espacio.')])
        r=o.atender('Llévame al siguiente entorno')
        self.assertEqual(r.tipo_cierre,'conversacion')
        self.assertEqual(r.acciones,[])

    def test_dictado_ambiguo_no_exige_copiar_el_texto(self):
        d=lote('set_volume',{'level':20})
        d['response']='He comprobado algo que todavía no se ejecutó.'
        o=self.crear([d])
        eventos=[]
        r=o.atender('Déjalo ahy al bente',on_event=eventos.append)
        self.assertEqual(self.cambios,[20])
        self.assertEqual(eventos,[])
        self.assertEqual(str(r),'Volumen comprobado.')

    def test_catalogo_conversacional_solo_enfoca_direcciones_observadas(self):
        o=self.crear([])
        t=Tarea('s','Llévame al editor',modo='actuar',semantica=True,
                coherente=True,cotidiano_local=True,conversacional=True)
        self.assertNotIn('focus_window',o.herramientas.catalogo(t))

    def test_politica_y_destino_separados_del_lenguaje(self):
        t=Tarea('s','Me cuesta escucharlo',conversacional=True)
        autorizar_capacidad(t,'set_volume',{'level':50})
        with self.assertRaises(ValueError):
            autorizar_capacidad(t,'run_terminal_command',{'command':'rm -rf /'})
        with self.assertRaises(ValueError):
            autorizar_capacidad(t,'remember',{'text':'inferencia','key':''})
        t.historial=[{'herramienta':'set_volume','resultado':{'ok':True,'verificado':False}}]
        self.assertEqual(estado_respuesta(t,{'tipo':'respuesta','completa':True}),'parcial')

    def test_mover_por_nombre_resuelve_sin_inferencia_preparatoria(self):
        o=self.crear([lote('mover_ventana',{'aplicacion':'firefox','target':'2'})])
        ventana={'address':'0x1234567','class':'firefox','title':'Navegador',
                 'workspace':{'id':3,'name':'3'}}
        datos={'clients':[ventana],'activewindow':ventana,'activeworkspace':{'id':3},'monitors':[]}
        recibo={'ok':True,'verificado':True,'resumen':'Ventana movida y comprobada.'}
        with patch.object(o.operaciones,'_leer',side_effect=lambda clave:datos[clave]), \
             patch('modules.app_router.resolver_aplicacion',return_value='firefox'), \
             patch.object(o.herramientas.capacidades,'_mutar_escritorio',return_value=recibo) as mutar:
            r=o.atender('Pon el navegador en mi segundo escritorio')
        self.assertIn('comprobada',r)
        self.assertEqual(len(self.interlocutor.consultas),1)
        self.assertEqual(mutar.call_args.args[2],{'address':'0x1234567','target':'2'})
        self.assertNotIn('Aplicaciones con ventanas',str(r))

    def test_ambiguedad_en_segundo_paso_impide_todos_los_efectos(self):
        d={'intent':'command','operations':[{'action':'set_volume','params':{'level':20}},
            {'action':'mover_ventana','params':{'aplicacion':'firefox','target':'2'}}],
            'complete':True,'response':''}
        o=self.crear([d])
        ventanas=[{'address':f'0x123456{i}','class':'firefox','title':f'Ventana {i}',
                   'workspace':{'id':3,'name':'3'}} for i in (1,2)]
        datos={'clients':ventanas,'activewindow':ventanas[0],'activeworkspace':{'id':3},'monitors':[]}
        with patch.object(o.operaciones,'_leer',side_effect=lambda clave:datos[clave]), \
             patch('modules.app_router.resolver_aplicacion',return_value='firefox'):
            r=o.atender('Baja el volumen y mueve Firefox al segundo espacio')
        self.assertEqual(self.cambios,[])
        self.assertIn('Cuál',str(r))
        self.assertEqual(o.almacen.cargar('local').estado,'aclaracion')
        self.assertEqual(len(self.interlocutor.consultas),1)

    def test_proyecto_por_nombre_conserva_la_ruta_resuelta(self):
        from pathlib import Path
        carpeta=Path(self.tmp.name)/'GestorCotizaciones'
        carpeta.mkdir()
        o=self.crear([lote('abrir_proyecto',{'nombre':'gestor de cotizaciones'})])
        recibo={'ok':True,'verificado':True,'datos':'Proyecto abierto y comprobado.'}
        with patch.object(o.operaciones,'_proyectos',return_value=[carpeta]), \
             patch.object(o.operaciones,'ejecutar',return_value=recibo) as abrir:
            r=o.atender('Quiero trabajar en el gestor de cotizaciones con Code')
        self.assertIn('Proyecto abierto',str(r))
        self.assertEqual(abrir.call_args.args[2]['ruta'],str(carpeta))
        self.assertEqual(len(self.interlocutor.consultas),1)

    def test_rechazo_muestra_la_propuesta_al_corregir(self):
        incorrecta=lote('mover_ventana',{'address':'workspace_switch(2)','target':'firefox'})
        o=self.crear([incorrecta,incorrecta])
        o.atender('Mueve Firefox al segundo escritorio')
        c=self.interlocutor.consultas[-1][1]
        self.assertEqual(c['decision_rechazada']['operaciones'],incorrecta['operations'])
        self.assertIn('address',c['decision_rechazada']['motivo'])
        self.assertEqual(self.cambios,[])
        self.assertEqual(len(self.interlocutor.consultas),2)

    def test_preparar_dos_aplicaciones_conserva_ambas_observaciones(self):
        import threading
        o=self.crear([])
        t=Tarea('s','Abre dos aplicaciones',modo='actuar',semantica=True,
                coherente=True,cotidiano_local=True,conversacional=True)
        apps=[{'id':'uno.desktop','nombre':'Uno'},{'id':'dos.desktop','nombre':'Dos'}]
        with patch('modules.installed_apps.buscar',side_effect=[[apps[0]],[apps[1]]]), \
             patch('modules.app_router.resolver_aplicacion',return_value=None):
            for app in apps:
                o.herramientas.capacidades.preparar(t,'abrir_aplicacion',{'nombre':app['nombre']},threading.Event())
        self.assertEqual(set(t.entidades['aplicaciones']),{'uno.desktop','dos.desktop'})

    def test_origen_desambigua_sin_elegir_la_primera_ventana(self):
        import threading
        o=self.crear([])
        t=Tarea('s','Mueve la del espacio tres al dos',modo='actuar',semantica=True,
                coherente=True,cotidiano_local=True,conversacional=True)
        ventanas=[{'address':f'0x123456{i}','class':'firefox','title':'Navegador',
                   'workspace':{'id':i,'name':str(i)}} for i in (3,4)]
        datos={'clients':ventanas,'activewindow':ventanas[0],'activeworkspace':{'id':3},'monitors':[]}
        with patch.object(o.operaciones,'_leer',side_effect=lambda clave:datos[clave]), \
             patch('modules.app_router.resolver_aplicacion',return_value='firefox'):
            p=o.herramientas.capacidades.preparar(t,'mover_ventana',
                {'aplicacion':'firefox','origen':'3','target':'2'},threading.Event())
        self.assertEqual(p,{'address':'0x1234563','target':'2'})
