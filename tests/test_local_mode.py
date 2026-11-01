"""Contratos del recorrido local. Preparados sin ejecutar durante la mejora 6."""

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import Config
from modules.command_result import ResultadoComando
from modules.local_permissions import autorizar
from modules.orchestrator import Orquestador
from modules.task_state import Tarea
from test_objectives import ExecutorFalso, ProveedorFalso


class TestEncadenadas(unittest.TestCase):
    def test_reutiliza_variantes_del_router_de_espacios(self):
        from modules.operation_intent import separar_encadenadas
        self.assertEqual(separar_encadenadas('cierra firefox y vamos al espacio de trabajo 1'),
                         ['cierra firefox','vamos al espacio de trabajo 1'])

    def test_conectores_y_nombres(self):
        from modules.operation_intent import separar_encadenadas
        for conector in ('y','además','también','y además','luego'):
            with self.subTest(conector=conector):
                self.assertEqual(separar_encadenadas('detén la música '+conector+' volumen al 60'),
                                 ['detén la música','volumen al 60'])
        self.assertEqual(separar_encadenadas('reproduce rock y roll'),['reproduce rock y roll'])
        self.assertEqual(separar_encadenadas('busca "abre code y sube volumen"'),
                         ['busca "abre code y sube volumen"'])



class TestRecorridoLocal(unittest.TestCase):
    def setUp(self):
        from commands.apps import AppCommands
        parche = patch.object(AppCommands,'disponibles',return_value=dict(AppCommands.APP_MAP))
        parche.start(); self.addCleanup(parche.stop)
        parche = patch.object(AppCommands,'predeterminada',return_value='nautilus')
        parche.start(); self.addCleanup(parche.stop)

    def test_catalogo_estable_y_validacion_de_destinos(self):
        from modules.task_tools import HerramientasTarea
        tools = HerramientasTarea(ExecutorFalso(),None)
        t = Tarea('s','Cierra Firefox',modo='actuar',semantica=True,coherente=True,cotidiano_local=True)
        inicial = set(tools.catalogo(t))
        t.objetivo = 'Abre el proyecto gestor con Code'
        self.assertEqual(set(tools.catalogo(t)),inicial)
        self.assertIn('abrir_proyecto',inicial)
        self.assertIn('cerrar_ventana',inicial)
        with self.assertRaises(ValueError):
            tools.validar(t,'cerrar_ventana',{'address':'0x1'})
        with self.assertRaises(ValueError):
            autorizar(t,'open_application',{'app':'code'},None)

    def test_proyecto_con_editor_antes_o_despues(self):
        from modules.operation_intent import proyecto_solicitado
        for frase in ('Abre code con el proyecto gestor de cotizaciones','Abre gestor de cotizaciones con code','Abre el proyecto gestor de cotizaciones con code'):
            self.assertEqual(proyecto_solicitado(frase),'gestor de cotizaciones')
            with self.assertRaises(ValueError):
                autorizar(Tarea('s',frase,modo='actuar',cotidiano_local=True),'open_application',{'app':'code'},None)

    def test_alias_compartidos_y_recibos(self):
        from modules.app_router import match_app_route
        from modules.command_result import normalizar_resultado
        for frase in ('abre el explorador de archivos','Abre archivos'):
            r = match_app_route(frase)
            self.assertEqual(r['params']['app'],'nautilus')
            t = Tarea('s',frase,modo='actuar',cotidiano_local=True)
            autorizar(t,'open_application',{'app':'nautilus'},None)
        recibo = normalizar_resultado(ResultadoComando('Solicitud multimedia enviada; efecto sin comprobar.',ok=True))
        self.assertFalse(recibo['verificado'])

    def test_pregunta_no_ofrece_mutaciones(self):
        from modules.general_agent import modo_semantico
        from modules.task_tools import HerramientasTarea
        t = Tarea('s','Qué aplicaciones tengo abiertas',modo=modo_semantico('Qué aplicaciones tengo abiertas','actuar'),
                  semantica=True,coherente=True,cotidiano_local=True)
        catalogo = HerramientasTarea(ExecutorFalso(),None).catalogo(t)
        self.assertEqual(t.modo,'leer')
        self.assertIn('consultar_escritorio',catalogo)
        self.assertNotIn('open_application',catalogo)

    def test_destino_de_busqueda_y_reanudacion_generica(self):
        from modules.media_router import match_media_route
        t = Tarea('s','Busca en YouTube Vegetta77',modo='actuar',cotidiano_local=True)
        with self.assertRaises(ValueError):
            autorizar(t,'web_search',{'query':'Vegetta77','engine':'google'},None)
        autorizar(t,'web_search',{'query':'Vegetta77','engine':'youtube'},None)
        r = match_media_route('Reproduce la música de Spotify')
        self.assertEqual(r['action'],'media_control')
        self.assertEqual(r['params']['player'],'spotify')

    def test_orden_compuesta_se_resuelve_sin_juez_ni_especialista(self):
        texto = 'Brillo al 10 y volumen al 50'
        proveedor = ProveedorFalso({'intent':'command','operations':[
            {'action':'set_brightness','params':{'level':10}},
            {'action':'set_volume','params':{'level':50}}], 'complete':True,'response':''})
        ex = ExecutorFalso()
        cambios = []
        def brillo(level:int):
            cambios.append(('brillo',level))
            return ResultadoComando('Brillo comprobado.',ok=True,verificado=True)
        def volumen(level:int):
            cambios.append(('volumen',level))
            return ResultadoComando('Volumen comprobado.',ok=True,verificado=True)
        ex.action_map.update(set_brightness=brillo,set_volume=volumen)
        config = Config()
        config.AGENT_MODE = 'local'
        config.AGENT_SEMANTIC = config.AGENT_COHERENT = True
        config.KNOWLEDGE_ENABLED = False
        with tempfile.TemporaryDirectory() as carpeta:
            config.AGENT_TASK_PATH = carpeta
            o = Orquestador(config,ex,proveedores={'cotidiano':proveedor})
            r = o.atender(texto)
        self.assertTrue(r.ok)
        self.assertEqual(cambios,[('brillo',10),('volumen',50)])
        self.assertEqual(len(proveedor.consultas),1)

    def test_fallo_ollama_no_invoca_remotos(self):
        from modules.agent_providers import ErrorProveedor
        p = ProveedorFalso(ErrorProveedor('Ollama no disponible.'))
        remoto = ProveedorFalso()
        c = Config()
        c.AGENT_MODE = 'local'
        c.AGENT_SEMANTIC = c.AGENT_COHERENT = True
        c.KNOWLEDGE_ENABLED = False
        with tempfile.TemporaryDirectory() as carpeta:
            c.AGENT_TASK_PATH = carpeta
            o = Orquestador(c,ExecutorFalso(),proveedores={'cotidiano':p,'analisis':remoto,'desarrollo':remoto})
            r = o.atender('Consulta el volumen del equipo')
        self.assertFalse(r.ok)
        self.assertFalse(remoto.consultas)

    def test_negacion_no_autoriza_cierre(self):
        t = Tarea('s','No cierres Firefox',modo='actuar',cotidiano_local=True)
        with self.assertRaises(ValueError):
            autorizar(t,'close_application',{'app':'firefox'},None)

    def test_cada_operacion_conserva_destino_de_su_clausula(self):
        t = Tarea('s','Abre Spotify y cierra Code',modo='actuar',cotidiano_local=True)
        with self.assertRaises(ValueError):
            autorizar(t,'close_application',{'app':'spotify'},None)
        autorizar(t,'close_application',{'app':'code'},None)

    def test_ventana_activa_observada_no_se_inventa(self):
        t = Tarea('s','Cierra lo que estoy viendo',modo='actuar',cotidiano_local=True,
                  entidades={'ventana_activa':'0x1','ventanas_detalle':[{'address':'0x1','class':'virt-manager','title':'Virtual Machine Manager'}]})
        autorizar(t,'cerrar_ventana',{'address':'0x1'},None)
        with self.assertRaises(ValueError):
            autorizar(t,'cerrar_ventana',{'address':'0x2'},None)

    def test_spotify_sin_configuracion_no_lanza_proceso(self):
        from modules.spotify_client import llamar
        import threading
        c = SimpleNamespace(SPOTIFY_MCP_ENABLED=False)
        with patch('modules.spotify_client.subprocess.Popen') as abrir:
            with self.assertRaises(ValueError):
                llamar(c,'spotify_estado',{},threading.Event())
            abrir.assert_not_called()

    def test_efecto_sin_recibo_no_se_declara_exitoso(self):
        from modules.command_result import normalizar_resultado
        self.assertFalse(normalizar_resultado(None)['ok'])


class TestContratoQwenSimple(unittest.TestCase):
    def setUp(self):
        from commands.apps import AppCommands
        parche = patch.object(AppCommands,'disponibles',return_value=dict(AppCommands.APP_MAP))
        parche.start(); self.addCleanup(parche.stop)
        parche = patch.object(AppCommands,'predeterminada',return_value='nautilus')
        parche.start(); self.addCleanup(parche.stop)

    def test_una_decision_no_concede_permisos(self):
        from modules.coherent_agent import decision_local
        t = Tarea('s','Abre Spotify',cotidiano_local=True)
        d = decision_local({'intent':'command','operations':[{'action':'open_application',
            'params':{'app':'spotify'}}],'complete':True,'response':''},t)
        self.assertEqual(d['pasos'][0]['accion'],'open_application')
        self.assertFalse(t.autorizaciones_semanticas)
        self.assertFalse(t.recibos)

    def test_especialista_no_es_una_salida_inicial(self):
        from modules.coherent_agent import catalogo_local, esquema_local
        t = Tarea('s','Abre Spotify',cotidiano_local=True)
        c = catalogo_local({'open_application':'abre una aplicación conocida'},t)
        self.assertNotIn('especialista_analisis',c)
        self.assertNotIn('delegar',esquema_local(c)['properties']['intent']['enum'])
        t.capacidades.append('especialistas')
        self.assertIn('especialista_analisis',catalogo_local(c,t))

    def test_contexto_no_incluye_planes_internos(self):
        from modules.coherent_agent import contexto_local
        c = contexto_local({'entrada':'Hola','plan_resultados':[{'estado':'pendiente'}],
                            'contratos':[{'interno':'no exponer'}],'resultados':[]})
        self.assertNotIn('plan_resultados',c)
        self.assertNotIn('contratos',c)
        self.assertNotIn('clausulas_pendientes',c)

    def test_atajo_comparte_contrato_y_no_consulta_modelo(self):
        from modules.coherent_agent import compilar_rapida
        contrato = compilar_rapida('cierra firefox')
        self.assertEqual(contrato['operations'],[{'action':'close_application','params':{'app':'firefox'}}])
        ex, proveedor = ExecutorFalso(), ProveedorFalso()
        cierres = []
        def cerrar(app:str):
            cierres.append(app)
            return ResultadoComando('Firefox cerrado.',ok=True,verificado=True)
        ex.action_map['close_application'] = cerrar
        c = Config()
        c.AGENT_MODE = 'local'
        c.AGENT_SEMANTIC = c.AGENT_COHERENT = True
        c.KNOWLEDGE_ENABLED = False
        with tempfile.TemporaryDirectory() as carpeta:
            c.AGENT_TASK_PATH = carpeta
            o = Orquestador(c,ex,proveedores={'cotidiano':proveedor})
            r = o.atender('cierra firefox')
        self.assertTrue(r.ok)
        self.assertEqual(cierres,['firefox'])
        self.assertFalse(proveedor.consultas)

    def test_esquema_conserva_parametros_del_handler(self):
        from modules.coherent_agent import esquema_local
        firma = {'type':'function','function':{'name':'close_application','parameters':{
            'type':'object','properties':{'app':{'type':'string'}},'required':['app'],'additionalProperties':False}}}
        s = esquema_local({'close_application':'cierra una app'},[firma])
        p = s['properties']['operations']['items']['anyOf'][0]['properties']
        self.assertEqual(p['action'],{'const':'close_application'})
        self.assertEqual(p['params'],firma['function']['parameters'])

    def test_error_tecnico_no_se_lee_en_voz(self):
        from modules.coherent_agent import error_publico
        t = Tarea('s','Abre Spotify',cotidiano_local=True)
        error = ValueError('Esta petición es cotidiana. Usa las herramientas locales o aclara el dato que falta; no la delegues por un fallo.')
        self.assertNotIn('Usa las herramientas',error_publico(error,t))
