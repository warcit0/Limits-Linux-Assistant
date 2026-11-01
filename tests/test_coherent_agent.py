"""Aceptación sin red del ciclo completo: decisiones, ejecución y respuesta."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
from modules.command_result import ResultadoComando, normalizar_resultado
from modules.orchestrator import Orquestador
from modules.task_state import Tarea
from test_objectives import ExecutorFalso, ProveedorFalso


def plan(texto,*pasos):
    return {'tipo':'plan','finaliza':False,'pasos':[{'accion':a,'parametros':p,'solicitud':texto} for a,p in pasos]}


def final(texto='Resultado.',ids=(0,),pendientes=()):
    return {'tipo':'respuesta','texto':texto,'evidencias':list(ids),'pendientes':list(pendientes)}


class ProveedorControlado(ProveedorFalso):
    def consultar(self,sistema,contexto,**kwargs):
        if contexto.get('autorizar_operacion'):
            self.consultas.append((sistema,contexto))
            return {'permitida':False,'motivo':'El escenario no autoriza ese efecto.'}
        return super().consultar(sistema,contexto,**kwargs)


class TestCicloCoherente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Config()
        self.config.AGENT_SEMANTIC = self.config.AGENT_COHERENT = True
        self.config.KNOWLEDGE_ENABLED = False
        self.config.AGENT_TASK_PATH = self.tmp.name
        self.config.AGENT_TIMEOUT = 10
        self.config.AGENT_MAX_STEPS = 5
        self.ex = ExecutorFalso()
        self.cambios = []
        self.ex.action_map['set_volume'] = self.volumen
        self.ex.action_map['set_brightness'] = self.brillo

    def volumen(self,level:int,mode:str='absolute'):
        self.cambios.append(('volumen',level))
        return ResultadoComando(f'Volumen al {level} %; comprobado.',ok=True,verificado=True)

    def brillo(self,level:int):
        self.cambios.append(('brillo',level))
        return ResultadoComando(f'Brillo al {level} %; comprobado.',ok=True,verificado=True)

    def crear(self,*decisiones):
        self.p = ProveedorControlado(*decisiones)
        self.o = Orquestador(self.config,self.ex,proveedores={'cotidiano':self.p,'analisis':self.p,'desarrollo':self.p})
        return self.o

    def test_compuesto_dos_inferencias_sin_jueces(self):
        t='Pon volumen al 40 y brillo al 60'
        o=self.crear(plan(t,('set_volume',{'level':40}),('set_brightness',{'level':60})),final(ids=(0,1)))
        r=o.atender(t)
        self.assertEqual(self.cambios,[('volumen',40),('brillo',60)])
        self.assertTrue(r.ok)
        self.assertEqual(len(self.p.consultas),2)
        self.assertIn('Brillo al 60',r)
        trazas=list(Path(self.tmp.name).glob('trabajos/*/traza.jsonl'))
        self.assertEqual(len(trazas),1)

    def test_ventanas_son_respuesta_principal(self):
        t='Qué hay en el workspace 1'
        o=self.crear(plan(t,('consultar_ventanas',{})),final('En el espacio 1 está Firefox.'))
        with patch.object(o.operaciones,'_leer',return_value=[{'address':'0x1234567','class':'firefox','title':'Navegador','workspace':{'id':1,'name':'1'}}]):
            r=o.atender(t)
        self.assertTrue(r.ok)
        self.assertEqual(str(r),'En el espacio 1 está Firefox.')
        self.assertEqual(len(self.p.consultas),2)

    def test_plan_completo_cierra_sin_inferencia_final(self):
        t='Pon volumen al 40 y brillo al 60'
        decision=plan(t,('set_volume',{'level':40}),('set_brightness',{'level':60}))
        decision['finaliza']=True
        o=self.crear(decision)
        r=o.atender(t)
        self.assertTrue(r.ok)
        self.assertEqual(len(self.p.consultas),1)
        self.assertEqual(len(self.cambios),2)

    def test_play_y_volumen_conserva_ambas_ordenes(self):
        t='Dale Play a la música y volumen al 100'
        def media(action:str,player:str=None,verify:bool=False):
            self.cambios.append(('media',action,verify))
            return ResultadoComando('Música reproduciéndose; comprobado.',ok=True,verificado=True)
        self.ex.action_map['media_control']=media
        decision=plan(t,('media_control',{'action':'play'}),('set_volume',{'level':100}))
        decision['finaliza']=True
        o=self.crear(decision)
        r=o.atender(t)
        self.assertTrue(r.ok)
        self.assertEqual(self.cambios,[('media','play',True),('volumen',100)])
        self.assertEqual(len(self.p.consultas),1)

    def test_valores_compuestos_no_se_cruzan(self):
        from modules.coherent_agent import autorizacion_directa
        t=Tarea('local','Pon brillo al 40 y volumen al 60')
        self.assertFalse(autorizacion_directa(t,'set_volume',{'level':40},self.ex))
        self.assertTrue(autorizacion_directa(t,'set_volume',{'level':60},self.ex))

    def test_workspace_filtrado_tiene_resumen_verificado(self):
        t='Qué hay en el workspace 1'
        decision=plan(t,('consultar_escritorio',{'workspace':'1'}))
        decision['finaliza']=True
        o=self.crear(decision)
        def leer(nombre):
            return {'activeworkspace':{'id':2},'activewindow':{},'monitors':[],
                    'clients':[{'address':'0x1234567','class':'firefox','title':'Título privado','workspace':{'id':1}},
                               {'address':'0x2234567','class':'spotify','title':'Música','workspace':{'id':2}}]}[nombre]
        with patch.object(o.operaciones,'_leer',side_effect=leer):
            r=o.atender(t)
        self.assertTrue(r.ok)
        self.assertIn('firefox',r)
        self.assertNotIn('spotify',r)
        self.assertNotIn('0x1234567',r)
        self.assertEqual(len(self.p.consultas),1)

    def test_aprobacion_caducada_no_se_recupera(self):
        import time
        o=self.crear()
        tarea=Tarea('local','Apaga el equipo',modo='actuar',estado='aprobacion',semantica=True,coherente=True)
        tarea.pendiente={'accion':'shutdown','parametros':{},'revision':tarea.revision,'tarea':tarea.id,'creado':time.time()-4000}
        o.almacen.guardar(tarea)
        r=o.atender('confirmar')
        self.assertFalse(r.ok)
        self.assertEqual(self.ex.apagados,0)

    def test_accion_y_consulta_se_presentan_ambas(self):
        t='Pon volumen al 40 y dime cuánta RAM uso'
        o=self.crear(plan(t,('set_volume',{'level':40}),('get_system_info',{'component':'memory'})),final(ids=(0,1)))
        r=o.atender(t)
        self.assertIn('Volumen al 40',r)
        self.assertIn('RAM usada',r)

    def test_pipeline_movil_no_llama_router_qwen(self):
        from main import make_pipeline
        from modules.gateway import TurnGate
        from unittest.mock import Mock
        t='Dale Play a la música y volumen al 100'
        def media(action:str,verify:bool=False):
            return ResultadoComando('Música reproduciéndose.',ok=True,verificado=True)
        self.ex.action_map['media_control']=media
        decision=plan(t,('media_control',{'action':'play'}),('set_volume',{'level':100}))
        decision['finaliza']=True
        o=self.crear(decision)
        llm=Mock()
        llm.process.side_effect=AssertionError('No debe pasar por Qwen')
        gate=TurnGate()
        pipeline=make_pipeline(llm,self.ex,Mock(),gate,orchestrator=o)
        with patch('modules.memory.get_store'):
            r=pipeline(t,speak=False,session_id='movil-prueba')
        self.assertIn('Volumen al 100',r)
        llm.process.assert_not_called()
        self.assertTrue(gate.acquire(0))
        gate.release()

    def test_confirmar_no_oculta_otros_pasos_pendientes(self):
        import time
        o=self.crear()
        self.ex.action_map['shutdown']=lambda:ResultadoComando('Apagado solicitado.',ok=True,verificado=True)
        tarea=Tarea('local','Apaga el equipo y cambia el brillo',modo='actuar',estado='aprobacion',semantica=True,coherente=True,capacidades=['sistema'])
        tarea.pendiente={'accion':'shutdown','parametros':{},'revision':tarea.revision,'tarea':tarea.id,'creado':time.time()}
        tarea.plan_resultados=[{'accion':'shutdown','solicitud':'Apaga el equipo','estado':'pendiente'},
                              {'accion':'set_brightness','solicitud':'cambia el brillo','estado':'pendiente'}]
        o.almacen.guardar(tarea)
        r=o.atender('confirmar')
        self.assertIsNone(r.ok)
        self.assertIn('otros pasos pendientes',r)
        self.assertEqual(o.almacen.cargar('local').pendientes_objetivo,['cambia el brillo'])

    def test_none_nunca_exito_y_fallo_parcial(self):
        t='Pon volumen al 40 y brillo al 60'
        self.ex.action_map['set_brightness']=lambda level: None
        o=self.crear(plan(t,('set_volume',{'level':40}),('set_brightness',{'level':60})),final(ids=(0,),pendientes=('brillo pendiente',)))
        r=o.atender(t)
        self.assertIsNone(r.ok)
        self.assertIn('Volumen al 40',r)
        self.assertIn('no devolvió evidencia',r)
        self.assertFalse(normalizar_resultado(None)['ok'])

    def test_negacion_no_concede_permiso(self):
        t='No cambies el volumen'
        o=self.crear(plan(t,('set_volume',{'level':70})),{'tipo':'pregunta','texto':'¿Qué dato quieres consultar?','evidencias':[],'pendientes':[]})
        o.atender(t)
        self.assertEqual(self.cambios,[])

    def test_objetivo_inventado_no_ejecuta(self):
        t='Cierra la ventana especial'
        self.ex.action_map['close_application']=lambda app:self.cambios.append(app)
        o=self.crear(plan(t,('close_application',{'app':'special_window'})),{'tipo':'pregunta','texto':'¿Quieres ocultar el espacio especial o cerrar una aplicación?','evidencias':[],'pendientes':[]})
        r=o.atender(t)
        self.assertEqual(self.cambios,[])
        self.assertNotIn('Solicitud enviada',r)

    def test_429_tras_efecto_conserva_recibo(self):
        from modules.agent_providers import ErrorProveedor
        t='Pon volumen al 40'
        o=self.crear(plan(t,('set_volume',{'level':40})),ErrorProveedor('Proveedor sin cuota.'))
        r=o.atender(t)
        self.assertIn('Volumen al 40',r)
        self.assertEqual(self.cambios,[('volumen',40)])
        self.assertEqual(len(o.almacen.cargar('local').recibos),1)

    def test_cancelacion_durante_handler_conserva_efecto(self):
        t='Pon volumen al 40'
        o=self.crear(plan(t,('set_volume',{'level':40})))
        def volumen(level:int,mode:str='absolute'):
            self.cambios.append(('volumen',level))
            o.cancelar('local')
            return ResultadoComando('Volumen al 40 %; comprobado.',ok=True,verificado=True)
        self.ex.action_map['set_volume']=volumen
        r=o.atender(t)
        self.assertTrue(r.cancelada)
        recibos=o.almacen.cargar('local').recibos
        self.assertTrue(next(iter(recibos.values()))['resultado']['verificado'])
        self.assertEqual(len(self.p.consultas),1)

    def test_rechaza_datos_crudos_y_corrige_una_vez(self):
        t='Qué hay en el workspace 1'
        o=self.crear(plan(t,('consultar_ventanas',{})),final("[{'address':'0x1234567'}]"),final('No hay ventanas en el espacio 1.'))
        with patch.object(o.operaciones,'_leer',return_value=[]):
            r=o.atender(t)
        self.assertTrue(r.ok)
        self.assertNotIn('address',r)
        self.assertEqual(len(self.p.consultas),3)

    def test_datos_externos_no_autorizan_efecto(self):
        t='Consulta el estado del disco'
        o=self.crear(plan(t,('get_system_info',{'component':'disk'})),plan(t,('set_volume',{'level':100})),final('He consultado el disco.',ids=(0,)))
        o.atender(t)
        self.assertEqual(self.cambios,[])

    def test_path_guard_y_confirmaciones(self):
        from modules.task_tools import huella_autorizacion
        tarea=Tarea('local','Mover archivo',semantica=True,coherente=True,modo='actuar')
        o=self.crear()
        with self.assertRaises(ValueError):
            o.herramientas.validar_ruta(tarea,'/etc/passwd',observada=True)
        self.assertIn('No hay un plan vigente',o.atender('confirmar'))
        self.assertEqual(self.ex.apagados,0)

    def test_dialogo_se_conserva_entre_turnos(self):
        o=self.crear(final('Hola, ¿qué quieres hacer?',ids=()),final('Podemos revisar tus aplicaciones.',ids=()))
        r=o.atender('Hola')
        o.registrar_dialogo('Hola',r,'local')
        o.atender('Qué me recomiendas')
        self.assertTrue(self.p.consultas[-1][1]['dialogo'])

    def test_especial_observado_no_se_togglea_si_oculto(self):
        import threading
        o=self.crear()
        tarea=Tarea('local','Oculta el especial music',semantica=True,coherente=True,modo='actuar',entidades={'especiales':['music']})
        with patch('commands.workspaces.WorkspaceCommands._leer',return_value=[]),patch('commands.workspaces.WorkspaceCommands._dispatch') as dispatch:
            r=o.herramientas.capacidades.ejecutar(tarea,'ocultar_especial',{'nombre':'music'},threading.Event())
        self.assertTrue(r['verificado'])
        dispatch.assert_not_called()
