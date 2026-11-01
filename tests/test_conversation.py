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

    def test_encargo_sin_voz_inventada_antes_de_ejecutar(self):
        ejecutor=ProveedorFalso(lote('set_volume',{'level':20}))
        o=self.crear([{'intent':'task','goal':'Bajar el volumen al 20 %.','response':'Voy a ajustarlo.'},
                      entrega('Ya está al 20 %.')],ejecutor)
        eventos=[]
        r=o.atender('Déjalo al veinte',on_event=eventos.append)
        self.assertEqual(self.cambios,[20])
        self.assertEqual(len(ejecutor.consultas),1)
        self.assertEqual(ejecutor.consultas[0][1]['encargo'],'Bajar el volumen al 20 %.')
        self.assertEqual(eventos,[])
        self.assertTrue(r.ok)

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

    def test_efecto_directo_incompleto_tambien_entrega_sin_replanificar(self):
        o=self.crear([lote('set_volume',{'level':20},False),
                      entrega('Volumen ajustado y comprobado.')])
        o.atender('Baja al veinte')
        self.assertEqual(self.cambios,[20])
        self.assertEqual(len(self.interlocutor.consultas),1)

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
