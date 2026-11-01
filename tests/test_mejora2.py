"""Regresiones de la conversación real, pruebas de efecto y voz incremental."""

import json
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from test_objectives import BaseObjetivos, respuesta, ruta

from commands.workspaces import WorkspaceCommands
from modules.agent_providers import Cancelado
from modules.orchestrator import contexto_ruta, modo_autorizado
from modules.speech_controller import SpeechController
from modules.streaming import FlujoVoz, FrasesProgresivas, proceso_eventos
from modules.workspace_router import match_workspace_route


class TestWorkspaces(unittest.TestCase):
    def test_variantes_reales_y_numeros(self):
        for texto in [
            "muéveme al work Space 2",
            "perfecto muéveme al World space 2",
            "ve al workspace dos",
            "cambia al escritorio segundo",
            "llevame al espacio de trabajo 2",
            "bien, muéveme al word space dos",
        ]:
            with self.subTest(texto=texto):
                r = match_workspace_route(texto)
                self.assertEqual(r["action"], "workspace_switch")
                self.assertEqual(r["params"]["target"], "2")
        self.assertEqual(
            match_workspace_route("mueve esta ventana al workspace 2")["action"],
            "workspace_move",
        )
        for texto in [
            "no me muevas al workspace 2",
            "qué es un workspace",
            "pon el volumen al 2",
            "abre escritorio",
            "world space",
            "perfecto",
        ]:
            self.assertIsNone(match_workspace_route(texto))

    def test_switch_comprueba_el_estado_y_guarda_anterior(self):
        c = WorkspaceCommands()
        with (
            mock.patch.object(
                c, "_leer", side_effect=[[{"id": 2, "name": "2"}], {"id": 1}, {"id": 2}]
            ),
            mock.patch.object(c, "_dispatch") as dispatch,
        ):
            self.assertIn("comprobado", c.switch("2"))
        dispatch.assert_called_once_with("workspace", 2)
        self.assertEqual(c.anterior, 1)

    def test_destinos_vacios_y_tecla_cero(self):
        for target, esperado in [("3", 3), ("0", 10), ("10", 10)]:
            c = WorkspaceCommands()
            with (
                mock.patch.object(c, "_leer", side_effect=[[], {"id": 1}, {"id": esperado}]),
                mock.patch.object(c, "_dispatch") as dispatch,
            ):
                self.assertIn("comprobado", c.switch(target))
                dispatch.assert_called_once_with("workspace", esperado)
        self.assertEqual(match_workspace_route("ve al workspace 0")["params"]["target"], "10")

    def test_returncode_no_demuestra_el_cambio(self):
        c = WorkspaceCommands()
        with (
            mock.patch.object(
                c,
                "_leer",
                side_effect=lambda cmd: (
                    [{"id": 2, "name": "2"}] if cmd == "workspaces" else {"id": 1}
                ),
            ),
            mock.patch.object(c, "_dispatch"),
            mock.patch("commands.workspaces.time.sleep"),
        ):
            self.assertIn("no confirmó", c.switch("2"))
        self.assertIsNone(c.anterior)

    def test_destino_inexistente_no_se_crea(self):
        c = WorkspaceCommands()
        with (
            mock.patch.object(c, "_leer", return_value=[]),
            mock.patch.object(c, "_dispatch") as dispatch,
        ):
            self.assertIn("No existe", c.switch("99"))
        dispatch.assert_not_called()

    def test_mover_comprueba_la_misma_ventana(self):
        c = WorkspaceCommands()
        datos = [
            [{"id": 2, "name": "2"}],
            {"address": "0x123"},
            [{"address": "0x123", "workspace": {"id": 2}}],
        ]
        with (
            mock.patch.object(c, "_leer", side_effect=datos),
            mock.patch.object(c, "_dispatch") as dispatch,
        ):
            self.assertIn("comprobado", c.move_window("2"))
        dispatch.assert_called_once_with("movetoworkspacesilent", "2,address:0x123")


class TestHonestidad(BaseObjetivos):
    def test_pantalla_sin_vision_no_alucina(self):
        c = self.coord()
        texto = c.atender("qué estoy viendo en mi pantalla")
        self.assertIn("no tengo acceso visual", texto)
        self.assertEqual(self.falso.consultas, [])

    def test_orden_prefijada_no_es_lectura_ni_exito_ficticio(self):
        self.assertEqual(modo_autorizado("perfecto sube el volumen", "leer"), "actuar")
        c = self.coord(
            ruta(modo="leer"), respuesta("Listo, el objetivo se ha alcanzado.")
        )
        texto = c.atender("perfecto sube el volumen")
        self.assertIn("No he realizado cambios", texto)
        self.assertNotIn("objetivo se ha alcanzado", texto)

    def test_efecto_de_turno_anterior_no_justifica_nuevo_exito(self):
        c = self.coord()
        t = self.tarea()
        t.modo = "actuar"
        t.historial = [{"usuario": "abre firefox"},
                      {"herramienta": "open_application", "resultado": {"ok": True}},
                      {"usuario": "ahora cambia el volumen"}]
        c._finalizar(t, "Listo, volumen cambiado.")
        self.assertEqual(t.estado, "interrumpida")
        self.assertNotIn("volumen cambiado", t.respuesta)

    def test_solicitud_sin_comprobacion_no_se_presenta_como_hecha(self):
        c = self.coord()
        t = self.tarea()
        t.modo = "actuar"
        t.historial = [{"usuario": "abre firefox"},
                      {"herramienta": "open_application", "resultado": {"ok": True, "verificado": False}}]
        c._finalizar(t, "Ya está abierto.")
        self.assertIn("todavía no he comprobado", t.respuesta)
        self.assertNotIn("Ya está abierto", t.respuesta)

    def test_respuesta_a_pregunta_conserva_rol(self):
        anterior = {
            "rol": "analisis",
            "pregunta_abierta": "¿Comparamos ambas opciones?",
            "estado": "terminada",
        }
        c = contexto_ruta("sí, compáralas", anterior)
        self.assertTrue(c["referencia_anterior"])
        self.assertEqual(c["roles_permitidos"], ["analisis"])

    def test_si_conversacional_no_aprueba_apagado(self):
        c = self.coord(
            ruta(texto="¿Quieres una explicación?"),
            ruta(texto="Te explico las alternativas."),
        )
        c.atender("Hola")
        c.atender("sí")
        self.assertEqual(self.executor.apagados, 0)


class TestFragmentos(unittest.TestCase):
    def test_crecimiento_no_duplica_ni_lee_frases_partidas(self):
        salida = []
        f = FrasesProgresivas(salida.append)
        f.recibir("Una frase")
        self.assertEqual(salida, [])
        f.recibir("Una frase completa. Otro")
        f.recibir("Una frase completa. Otra frase completa.")
        self.assertEqual(salida, ["Una frase completa.", "Otra frase completa."])

    def test_cambios_de_formato_no_releen_el_resumen(self):
        salida = []
        f = FrasesProgresivas(salida.append)
        f.recibir("Publicación: 2026-10-31.\n")
        self.assertEqual(salida, [])
        f.recibir("Publicación: 2026-10-31. Primera noticia completa.\n\n")
        f.recibir(
            "Publicación: 2026-10-31. Primera noticia completa. Segunda noticia completa."
        )
        f.recibir(
            "Publicación: 2026-10-31. Primera noticia completa. Segunda noticia completa.",
            final=True,
        )
        self.assertFalse(f.revisado)
        self.assertEqual(" ".join(salida).count("Primera noticia completa."), 1)
        self.assertEqual(" ".join(salida).count("Segunda noticia completa."), 1)

    def test_dom_concatena_nodos_sin_repetir_lo_hablado(self):
        salida = []
        f = FrasesProgresivas(salida.append)
        f.recibir("Primera noticia: Publicación: 2026-10-31. Un dato completo.")
        f.recibir("Primera noticia:Publicación:2026-10-31.Un dato completo. Otra noticia completa.", final=True)
        self.assertFalse(f.revisado)
        self.assertEqual(len(salida), 2)
        self.assertEqual(salida[-1], "Otra noticia completa.")

    def test_revision_detiene_los_avances(self):
        salida = []
        f = FrasesProgresivas(salida.append)
        f.recibir("La cifra es 30. ")
        f.recibir("La cifra es 20. ")
        f.recibir("La cifra es 20. Confirmada.")
        self.assertTrue(f.revisado)
        self.assertEqual(salida, ["La cifra es 30."])

    def test_no_habla_codigo_ni_urls(self):
        salida = []
        f = FrasesProgresivas(salida.append)
        f.recibir("Resumen.\n\n```python\nprint(1)\n```", final=True)
        self.assertEqual(salida, ["Resumen."])
        salida = []
        f = FrasesProgresivas(salida.append)
        f.recibir("Fuente https://example.org/reporte. ", final=True)
        self.assertNotIn("https", str(salida))

    def test_evento_llega_antes_del_fin_del_proceso(self):
        inicio = time.monotonic()
        tiempos = []
        programa = "import json,time; print(json.dumps({'v':1,'type':'delta','text':'Primer avance.'}),flush=True); time.sleep(.25); print(json.dumps({'v':1,'type':'final','ok':True,'f':'ejemplo'}),flush=True)"
        resultado = proceso_eventos(
            [sys.executable, "-c", programa],
            lambda ev: tiempos.append((ev["type"], time.monotonic() - inicio)),
            threading.Event(),
            3,
        )
        self.assertEqual(resultado.returncode, 0)
        self.assertEqual([t[0] for t in tiempos], ["delta", "final"])
        self.assertGreater(tiempos[1][1] - tiempos[0][1], 0.18)

    def test_cancelacion_cierra_proceso_y_no_publica_final(self):
        evento = threading.Event()
        recibidos = []

        def recibir(ev):
            recibidos.append(ev)
            evento.set()

        programa = "import json,time; print(json.dumps({'v':1,'type':'delta','text':'Avance.'}),flush=True); time.sleep(10)"
        inicio = time.monotonic()
        with self.assertRaises(Cancelado):
            proceso_eventos([sys.executable, "-c", programa], recibir, evento, 15)
        self.assertLess(time.monotonic() - inicio, 3)
        self.assertEqual(len(recibidos), 1)

    def test_audio_una_sola_cola_y_ningun_sonido_tardio(self):
        evento = threading.Event()
        textos = []

        def hablar(texto, **kwargs):
            if not kwargs["stop_event"].is_set():
                textos.append(texto)

        speech = SpeechController(SimpleNamespace(speak=hablar), enabled=False)
        flujo = FlujoVoz(speech, evento.set, lambda: not evento.is_set())
        flujo.decir("Primero")
        limite = time.monotonic() + 1
        while not textos and time.monotonic() < limite:
            time.sleep(0.01)
        evento.set()
        flujo.decir("No debe hablar")
        flujo.cerrar()
        self.assertEqual(textos, ["Primero"])


class TestIntegracionFlujo(BaseObjetivos):
    def test_research_habla_antes_de_terminar_y_no_repite_al_final(self):
        texto = "Primer avance completo. Otra conclusión útil."
        palabras = []
        sonido = threading.Event()

        def hablar(t, **kwargs):
            palabras.append(t)
            sonido.set()
            return "ok"

        voz = SpeechController(SimpleNamespace(speak=hablar), enabled=False)

        class Gemini:
            def chat(self, entrada, **kwargs):
                emitir = kwargs["on_event"]
                emitir({"v": 1, "type": "delta", "text": "Primer avance completo. "})
                assert sonido.wait(1), "No hubo voz durante la generación"
                emitir({"v": 1, "type": "delta", "text": texto})
                self.last_full_text = texto
                return texto

        c = self.coord(gemini=Gemini())
        from main import make_pipeline
        from modules.gateway import TurnGate

        bloqueo = TurnGate()
        p = make_pipeline(mock.Mock(), self.executor, voz, bloqueo, orchestrator=c)
        with mock.patch("modules.memory.get_store"):
            r = p("investiga noticias de autos")
        self.assertTrue(r.audio_entregado)
        self.assertEqual(" ".join(palabras).count("Primer avance completo."), 1)
        self.assertTrue(bloqueo.acquire(0))
        bloqueo.release()

    def test_error_posterior_al_avance_no_se_anuncia_como_validado(self):
        palabras = []
        voz = SpeechController(
            SimpleNamespace(speak=lambda t, **kw: palabras.append(t)), enabled=False
        )

        class Gemini:
            def chat(self, entrada, **kwargs):
                kwargs["on_event"](
                    {"v": 1, "type": "delta", "text": "Avance preliminar. "}
                )
                self.last_full_text = ""
                return "No pude validar las fuentes de esta respuesta."

        c = self.coord(gemini=Gemini())
        from main import make_pipeline
        from modules.gateway import TurnGate

        p = make_pipeline(mock.Mock(), self.executor, voz, TurnGate(), orchestrator=c)
        with mock.patch("modules.memory.get_store"):
            r = p("investiga noticias de autos")
        self.assertIn("No pude validar", str(r))
        self.assertTrue(any("No pude validar" in x for x in palabras))
        self.assertFalse(r.ok)


class TestHigiene(BaseObjetivos):
    def test_cuarentena_es_reversible_y_no_toca_hechos(self):
        import sqlite3

        from modules.memory import MemoryStore
        from modules.memory_hygiene import limpiar_episodios

        ruta = self.base / "memoria.db"
        store = MemoryStore(ruta)
        store.log_turn("user", "hola", intent="test")
        store.log_turn("assistant", "resp:hola", intent="test")
        store.log_turn("user", "Una conversación real", intent="objetivo")
        store.log_turn("assistant", "Una respuesta real", intent="objetivo")
        store.close()
        informe = limpiar_episodios(ruta, False)
        self.assertEqual(informe["sinteticos"], 2)
        informe = limpiar_episodios(ruta, True)
        conn = sqlite3.connect(ruta)
        self.assertEqual(conn.execute("SELECT count(*) FROM episodes").fetchone()[0], 2)
        self.assertEqual(
            conn.execute("SELECT count(*) FROM episodes_quarantine").fetchone()[0], 2
        )
        conn.close()
        respaldo = sqlite3.connect(informe["respaldo"])
        self.assertEqual(
            respaldo.execute("SELECT count(*) FROM episodes").fetchone()[0], 4
        )
        respaldo.close()
        self.assertEqual(limpiar_episodios(ruta, False)["sinteticos"], 0)

    def test_respuestas_no_verificadas_no_alimentan_contexto(self):
        from modules.memory import MemoryStore

        s = MemoryStore(":memory:")
        s.log_turn("assistant", "Éxito inventado", ok=False)
        s.log_turn("assistant", "Resultado real", ok=True)
        self.assertEqual([t["text"] for t in s.recent_turns()], ["Resultado real"])
        s.close()


class TestAudioPCM(unittest.TestCase):
    def test_inicio_corresponde_a_pcm_no_al_inicio_del_modelo(self):
        import subprocess

        from modules.tts import TTSEngine

        original = subprocess.Popen
        marcas = []
        inicio = time.monotonic()

        def lanzar(argumentos, **kwargs):
            programa = (
                "import sys; sys.stdin.buffer.read()"
                if argumentos[0] == "aplay"
                else "import sys,time; sys.stdin.read(); time.sleep(.15); sys.stdout.buffer.write(b'\\0\\0'*4096);sys.stdout.flush()"
            )
            return original([sys.executable, "-c", programa], **kwargs)

        motor = TTSEngine.__new__(TTSEngine)
        motor.voice_model = "prueba.onnx"
        motor.voice_speed = 1.0
        motor.speaker = None
        motor.on_audio_start = lambda: marcas.append(time.monotonic() - inicio)
        with mock.patch("modules.tts.subprocess.Popen", side_effect=lanzar):
            self.assertEqual(
                motor._speak_piper("Prueba de audio", threading.Event()), "ok"
            )
        self.assertEqual(len(marcas), 1)
        self.assertGreaterEqual(marcas[0], 0.15)


class TestFechasGemini(BaseObjetivos):
    def test_fecha_de_consulta_no_acredita_publicacion_de_hoy(self):
        from modules.gemini import GeminiBridge

        p = self.base / "respuesta.md"
        p.write_text(
            "Hoy es 2026-10-31. Publicación: 2026-10-28. "
            + "Detalles de noticias anteriores. " * 20
            + "https://example.org/a https://example.net/b"
        )
        resultado = SimpleNamespace(
            returncode=0, stdout=json.dumps({"ok": True, "f": str(p)}), stderr=""
        )
        b = GeminiBridge("falso")
        with mock.patch("modules.gemini.subprocess.run", return_value=resultado):
            self.assertIn("no acredita", b.chat("noticias de hoy", research=True))
        self.assertFalse(b.last_full_text)

    def test_workspace_cancelado_en_cola_no_ejecuta(self):
        from main import make_pipeline
        from modules.gateway import TurnGate

        c = self.coord()
        p = make_pipeline(
            mock.Mock(), self.executor, mock.Mock(), TurnGate(), orchestrator=c
        )
        antes = c.generacion("local")
        c.cancelar("local")
        with mock.patch("modules.memory.get_store"):
            r = p("muéveme al work space 2", speak=False, turn_generation=antes)
        self.assertEqual(r, "Tarea cancelada.")
        self.assertEqual(self.executor.ejecuciones, [])


class TestConversacionNatural(BaseObjetivos):
    def test_conversacion_no_se_convierte_en_llamada_a_herramientas(self):
        from modules.agent_providers import ProveedorOllama
        remoto=mock.Mock()
        texto='{"tipo":"herramienta","accion":"shutdown","parametros":{}}'
        remoto.iter_lines.return_value=[json.dumps({'message':{'content':texto}}).encode()]
        with mock.patch('modules.agent_providers.requests.post',return_value=remoto) as peticion:
            r=ProveedorOllama(self.config).consultar('Conversación natural',{'conversacion':True,'entrada':'Hola','historial':[{'usuario':'Hola'}],'herramientas':{}},tarea=self.tarea(),cancelar=self.evento,timeout=5)
        self.assertEqual(r['tipo'],'respuesta')
        self.assertEqual(r['texto'],texto)
        self.assertNotIn('format',peticion.call_args.kwargs['json'])
        self.assertEqual(self.executor.apagados,0)

    def test_sin_raices_no_se_ofrece_listar_el_disco(self):
        t=self.tarea();t.raices=[]
        self.assertNotIn('listar_carpeta',self.tools.catalogo(t))
        self.assertNotIn('leer_archivo',self.tools.catalogo(t))

    def test_apps_lee_datos_reales_sin_bucle_del_modelo(self):
        self.executor.action_map['list_running_apps']=lambda: 'Aplicaciones con ventanas: Firefox'
        c=self.coord(ruta())
        r=c.atender('Prefiero revisar las aplicaciones abiertas')
        self.assertIn('Firefox',r)
        self.assertIn('¿Qué aplicación',r)
        self.assertEqual(len(self.falso.consultas),1)

    def test_eleccion_corta_no_se_descarta_como_eco(self):
        from modules.speech_controller import looks_like_echo
        self.assertFalse(looks_like_echo('la segunda','¿Quieres la primera o la segunda?'))


class TestProgresoMovil(BaseObjetivos):
    def test_movil_recibe_avances_y_stop_sin_voz_local(self):
        from test_gateway import Harness
        from websockets.sync.client import connect
        from main import make_pipeline
        from modules.gateway import TurnGate
        class Gemini:
            def chat(self,entrada,**kw):
                kw['on_event']({'v':1,'type':'delta','text':'Primer avance completo. '})
                if kw['cancel_event'].wait(3):
                    raise Cancelado('Tarea cancelada.')
                raise AssertionError('Stop no alcanzó la generación')
        c=self.coord(gemini=Gemini())
        p=make_pipeline(mock.Mock(),self.executor,mock.Mock(),TurnGate(),orchestrator=c)
        with mock.patch('modules.memory.get_store'), Harness(p,speak_remote=False) as h:
            with connect(f'ws://127.0.0.1:{h.port}/ws',additional_headers={'Authorization':f'Bearer {h.srv.token}'}) as ws:
                ws.recv(timeout=2)
                ws.send(json.dumps({'v':1,'type':'command','text':'investiga noticias de autos'}))
                recibido=False
                for _ in range(5):
                    e=json.loads(ws.recv(timeout=2))
                    if e.get('progress',{}).get('type')=='delta':
                        recibido=True;break
                self.assertTrue(recibido)
                ws.send(json.dumps({'type':'stop'}))
                mensajes=[json.loads(ws.recv(timeout=3)),json.loads(ws.recv(timeout=3))]
                self.assertTrue(any(m.get('kind')=='stopped' for m in mensajes))
                self.assertTrue(any(m.get('text')=='Tarea cancelada.' for m in mensajes))

    def test_error_de_sesion_no_pierde_el_codigo(self):
        programa="import json,sys;print(json.dumps({'v':1,'type':'error','code':'NOT_SIGNED_IN'}),flush=True);sys.exit(1)"
        r=proceso_eventos([sys.executable,'-c',programa],lambda ev:None,threading.Event(),3)
        self.assertEqual(json.loads(r.stdout)['err'],'NOT_SIGNED_IN')
