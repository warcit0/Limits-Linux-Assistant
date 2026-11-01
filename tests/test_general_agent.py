"""Política semántica transversal con efectos, observaciones y fallos controlados."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_objectives import ExecutorFalso, ProveedorFalso, herramienta, respuesta

from config import Config
from modules.command_result import ResultadoComando
from modules.orchestrator import Orquestador


def clasificar(modo="actuar", *, objetivos=None, observa=True, continuar=False):
    return {
        "rol": "cotidiano",
        "modo": modo,
        "continuar": continuar,
        "objetivos": objetivos or ["resultado solicitado"],
        "requiere_observacion": observa,
        "capacidades": ["sistema", "aplicaciones", "multimedia"],
    }


class ProveedorGeneralFalso(ProveedorFalso):
    def consultar(self, sistema, contexto, **kwargs):
        if contexto.get("evaluar_pregunta"):
            return {"necesaria":True,"motivo":"Falta una elección del usuario en este escenario."}
        if contexto.get("autorizar_operacion"):
            return {"permitida":True,"motivo":"Petición explícita del usuario en el escenario."}
        if contexto.get("evaluar_objetivo"):
            self.consultas.append((sistema, contexto))
            ids = [e["id"] for e in contexto["evidencias"] if e.get("resultado", {}).get("ok") and e["resultado"].get("verificado")]
            efectos = [e for e in contexto["evidencias"] if e["herramienta"] in {"set_volume","set_brightness"} and e.get("resultado", {}).get("ok")]
            completo = bool(ids) and (len(efectos)>=len(contexto["objetivos"]) if kwargs["tarea"].modo == "actuar" else True)
            return {"completo":completo, "pendientes":[] if completo else ["paso restante"], "evidencias":ids}
        return super().consultar(sistema, contexto, **kwargs)


class TestAgenteGeneral(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Config()
        self.config.AGENT_SEMANTIC = True
        self.config.KNOWLEDGE_ENABLED = False
        self.config.AGENT_TASK_PATH = str(Path(self.tmp.name) / "tareas")
        self.config.AGENT_MAX_STEPS = 7
        self.config.AGENT_TIMEOUT = 20
        self.executor = ExecutorFalso()
        self.executor.action_map["set_volume"] = self.volumen
        self.executor.action_map["set_brightness"] = self.brillo
        self.efectos = []

    def volumen(self, level: int, mode: str = "absolute"):
        self.efectos.append(("volumen", level))
        return ResultadoComando(
            f"Volumen comprobado: {level} %.", ok=True, verificado=True
        )

    def brillo(self, level: int):
        self.efectos.append(("brillo", level))
        return ResultadoComando(
            f"Brillo comprobado: {level} %.", ok=True, verificado=True
        )

    def coord(self, *decisiones, especialista=None):
        self.p = ProveedorGeneralFalso(*decisiones)
        self.especialista = especialista or self.p
        return Orquestador(
            self.config,
            self.executor,
            proveedores={
                "cotidiano": self.p,
                "analisis": self.especialista,
                "desarrollo": self.especialista,
            },
        )

    def test_orden_sin_verbo_canonico_no_pierde_herramientas(self):
        c = self.coord(
            clasificar(), herramienta("set_volume", level=25), respuesta("Hecho")
        )
        r = c.atender("Sería genial tener el volumen al 25")
        self.assertTrue(r.ok)
        self.assertEqual(self.efectos, [("volumen", 25)])

    def test_datos_del_equipo_no_se_inventan_y_se_consultan(self):
        c = self.coord(
            clasificar("leer"),
            respuesta("El volumen es 75%"),
            herramienta("get_volume"),
            respuesta("El volumen es 99%"),
        )
        r = c.atender("¿Cómo está el volumen?")
        self.assertIn("30 %", r)
        self.assertNotIn("99", r)
        self.assertNotIn("75", r)

    def test_compuesto_exige_otro_resultado_y_conserva_solo_observaciones(self):
        c = self.coord(
            clasificar(objetivos=["volumen 20", "brillo 40"]),
            herramienta("set_volume", level=20),
            respuesta("Ya hice todo"),
            herramienta("set_brightness", level=40),
            respuesta("Listo"),
        )
        r = c.atender("volumen al 20 y brillo al 40")
        self.assertEqual(self.efectos, [("volumen", 20), ("brillo", 40)])
        self.assertTrue(r.ok)

    def test_error_de_parametros_replanifica_sin_repetir_efectos(self):
        c = self.coord(
            clasificar(),
            herramienta("set_volume", inventado=15),
            herramienta("set_volume", level=15),
            respuesta("Bien"),
        )
        r = c.atender("déjame el volumen al 15")
        self.assertTrue(r.ok)
        self.assertEqual(self.efectos, [("volumen", 15)])

    def test_escala_tras_dos_respuestas_sin_observar(self):
        experto = ProveedorGeneralFalso(
            clasificar("leer"), herramienta("get_volume"), respuesta("Listo")
        )
        c = self.coord(
            clasificar("leer"),
            respuesta("inventado"),
            respuesta("inventado otra vez"),
            especialista=experto,
        )
        r = c.atender("necesito saber el volumen real")
        self.assertIn("30 %", r)
        self.assertEqual(len(experto.consultas), 3)

    def test_negaciones_no_autorizan_mutacion_aunque_modelo_insista(self):
        c = self.coord(
            clasificar(),
            herramienta("set_volume", level=15),
            {"tipo": "pregunta", "texto": "¿Quieres consultar el volumen actual?"},
        )
        r = c.atender("No cambies el volumen, dime cómo funciona")
        self.assertEqual(self.efectos, [])
        self.assertIsNone(r.ok)

    def test_shutdown_sigue_exigiendo_confirmacion_explicita(self):
        c = self.coord(clasificar(), herramienta("shutdown"))
        r = c.atender("apaga el equipo")
        self.assertIn("confirmar", r)
        self.assertEqual(self.executor.apagados, 0)
        c.atender("cancelar")
        c.atender("confirmar")
        self.assertEqual(self.executor.apagados, 0)

    def test_dialogo_separa_conversacion_de_objetivo(self):
        c = self.coord(
            clasificar("leer", observa=False),
            respuesta("Podemos comparar formatos. ¿Qué formato usas?"),
        )
        r = c.atender("Quiero hablar de formatos")
        c.registrar_dialogo("Quiero hablar de formatos", r, "local")
        self.p.decisiones += [
            clasificar("leer", observa=False, continuar=True),
            respuesta("CSV permite tablas sencillas."),
        ]
        r = c.atender("CSV")
        self.assertIn("CSV", r)
        self.assertTrue(self.p.consultas[-1][1]["dialogo"])

    def test_ventana_debe_observarse_antes_de_enfocarla(self):
        c = self.coord(
            clasificar(),
            herramienta("enfocar_ventana", address="0xf"),
            {"tipo": "pregunta", "texto": "¿Qué aplicación quieres enfocar?"},
        )
        with mock.patch.object(c.operaciones, "_enfocar_cliente") as foco:
            c.atender("pon al frente el programa de máquinas")
            foco.assert_not_called()

    def test_catalogo_general_no_depende_del_plan_regex(self):
        from modules.executor import CommandExecutor

        c = Orquestador(
            self.config, CommandExecutor(), proveedores={"cotidiano": ProveedorFalso()}
        )
        from modules.task_state import Tarea

        t = Tarea(
            "test",
            "objetivo",
            modo="actuar",
            semantica=True,
            capacidades=[
                "sistema",
                "aplicaciones",
                "multimedia",
                "proyectos",
                "television",
            ],
        )
        catalogo = c.herramientas.catalogo(t)
        for nombre in (
            "consultar_ventanas",
            "enfocar_ventana",
            "buscar_proyectos",
            "abrir_proyecto",
            "spotify_play",
            "youtube_play",
            "tv_cast",
            "get_system_info",
            "set_volume",
        ):
            self.assertIn(nombre, catalogo)

    def test_operacion_no_solicitada_se_rechaza_antes_del_efecto(self):
        c = self.coord(clasificar(), herramienta('set_volume',level=99),
                       {'tipo':'pregunta','texto':'¿Quieres otro volumen? '})
        original = self.p.consultar
        def consultar(sistema, contexto, **kw):
            if contexto.get('autorizar_operacion'):
                return {'permitida':False,'motivo':'El usuario pidió 25, no 99.'}
            return original(sistema,contexto,**kw)
        self.p.consultar = consultar
        r = c.atender('deja el volumen al 25')
        self.assertEqual(self.efectos,[])
        self.assertIsNot(r.ok,True)

    def test_evaluador_no_puede_acreditar_recibos_inexistentes(self):
        c = self.coord(clasificar('leer'),herramienta('get_volume'),respuesta('Hecho'),
                       {'tipo':'pregunta','texto':'¿Quieres revisar otra cosa?'})
        original = self.p.consultar
        def consultar(sistema,contexto,**kw):
            if contexto.get('evaluar_objetivo'):
                return {'completo':True,'pendientes':[],'evidencias':[999]}
            return original(sistema,contexto,**kw)
        self.p.consultar = consultar
        r = c.atender('consulta mi volumen')
        self.assertIsNot(r.ok,True)

    def test_solo_local_se_respeta_antes_de_clasificar(self):
        c = self.coord()
        local = ProveedorGeneralFalso(clasificar('leer'),herramienta('get_volume'))
        c._local = local
        r = c.atender('solo local, necesito saber el volumen')
        self.assertIn('30 %',r)
        self.assertEqual(self.p.consultas,[])
        self.assertFalse(c._escalar(c.almacen.cargar('local')))

    def test_olvido_invalida_dialogo_de_otras_sesiones(self):
        from modules.memory import MemoryStore
        from modules.task_state import Tarea
        self.config.KNOWLEDGE_ENABLED = True
        self.config.MEMORY_PATH = str(Path(self.tmp.name)/'memoria.db')
        self.config.KNOWLEDGE_VAULT = str(Path(self.tmp.name)/'vault')
        store = MemoryStore(self.config.MEMORY_PATH);self.addCleanup(store.close)
        store.remember('editor','Code')
        c = self.coord(clasificar('leer',observa=False),respuesta('Podemos conversar.'))
        self.addCleanup(c.conocimiento.close)
        t = Tarea('otra','editor favorito',semantica=True,dialogo=[{'asistente':'Tu editor es Code'}])
        c.almacen.guardar(t)
        store.forget('editor')
        c.atender('charlemos','otra')
        self.assertEqual(self.p.consultas[0][1]['dialogo'],[])
        self.assertIsNone(self.p.consultas[0][1]['tarea_anterior'])

    def test_negacion_de_un_dominio_no_bloquea_otro_solicitado(self):
        c=self.coord(clasificar(),herramienta('set_brightness',level=40))
        r=c.atender('No cambies el volumen; sube el brillo al 40')
        self.assertTrue(r.ok)
        self.assertEqual(self.efectos,[('brillo',40)])

    def test_prohibicion_global_conserva_modo_lectura(self):
        c=self.coord(clasificar(),herramienta('set_brightness',level=40),{'tipo':'pregunta','texto':'¿Quieres consultar el brillo?'})
        c.atender('No hagas cambios; dime si subir el brillo al 40 sería cómodo')
        self.assertEqual(self.efectos,[])

    def test_propuesta_local_pasa_por_autorizacion_y_evidencia_sin_otro_router(self):
        c=self.coord()
        r=c.atender('me vendría bien el volumen al 25',propuesta_local={'action':'set_volume','params':{'level':25},'grounded':True})
        self.assertTrue(r.ok)
        self.assertEqual(self.efectos,[('volumen',25)])
        self.assertFalse(any('tarea_anterior' in ctx for _,ctx in self.p.consultas))

    def test_capacidad_inexistente_se_comunica_sin_fingir_efectos(self):
        c=self.coord(clasificar(),{'tipo':'limitacion','texto':'No puedo escanear documentos.'})
        original=self.p.consultar
        def consultar(sistema,contexto,**kw):
            if 'limitacion_propuesta' in contexto:
                return {'necesaria':True,'motivo':'No tengo una herramienta de escáner configurada.'}
            return original(sistema,contexto,**kw)
        self.p.consultar=consultar
        r=c.atender('escanea este documento con mi impresora')
        self.assertFalse(r.ok)
        self.assertEqual(self.efectos,[])
        self.assertIn('escáner',r)

    def test_analisis_general_lee_archivo_real_y_conserva_sintesis(self):
        ruta=Path(self.tmp.name)/'datos.txt';ruta.write_text('A: 12\nB: 8\n')
        clasificacion=clasificar('leer');clasificacion.update(rol='analisis',capacidades=['archivos'],requiere_sintesis=True)
        c=self.coord(clasificacion,herramienta('leer_archivo',ruta=str(ruta)),respuesta('La suma de A y B es 20.'))
        r=c.atender(f'Analiza el archivo {ruta} y suma A y B')
        self.assertTrue(r.ok)
        self.assertIn('20',r)
        evaluaciones=[ctx for _,ctx in self.p.consultas if ctx.get('evaluar_objetivo')]
        self.assertIn('A: 12',evaluaciones[0]['evidencias'][0]['resultado']['datos'])
        self.assertIn('20',evaluaciones[0]['respuesta_propuesta'])

    def test_alias_de_parametros_se_normaliza_antes_de_autorizar(self):
        c=self.coord(clasificar(),herramienta('set_volume',value=25))
        r=c.atender('volumen al 25')
        self.assertTrue(r.ok)
        self.assertEqual(self.efectos,[('volumen',25)])
