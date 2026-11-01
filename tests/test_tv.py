"""Tests de commands/tv.py — pychromecast y subprocess totalmente mockeados."""

import os
import sys
import tempfile
import unittest
from unittest import mock

from commands.tv import TVCommands, resolve_local_file


def fake_cast(name="Living Room"):
    m = mock.Mock()
    m.device.friendly_name = name
    m.status.volume_level = 0.5
    m.status.volume_muted = False
    return m


class TestListTVs(unittest.TestCase):
    def test_sin_tvs_mensaje_amable(self):
        tv = TVCommands()
        with mock.patch.object(tv, "_discover", return_value=[]):
            out = tv.list_tvs()
        self.assertIn("No encontré", out)

    def test_con_nombres(self):
        tv = TVCommands()
        casts = [fake_cast("Living Room"), fake_cast("Dormitorio")]
        with mock.patch.object(tv, "_discover", return_value=casts):
            out = tv.list_tvs()
        self.assertIn("Living Room", out)
        self.assertIn("Dormitorio", out)


class TestTvCast(unittest.TestCase):
    def _tv(self, names=("Living Room",)):
        tv = TVCommands()
        tv._discover = mock.Mock(return_value=[fake_cast(n) for n in names])
        return tv

    def test_cast_por_query_youtube(self):
        tv = self._tv()
        qp_mod = mock.Mock()
        qp_mod.quick_play = mock.Mock()
        with mock.patch.object(tv, "_youtube_stream_url",
                               return_value="http://stream/abc"), \
             mock.patch.dict(sys.modules, {"pychromecast.quick_play": qp_mod}):
            out = tv.tv_cast(query="lofi beats")
        self.assertIn("Reproduciendo lofi beats en Living Room.", out)
        qp_mod.quick_play.assert_called_once()

    def test_cast_de_lo_que_sueno(self):
        tv = self._tv()
        qp_mod = mock.Mock()
        qp_mod.quick_play = mock.Mock()
        with mock.patch.object(tv, "_current_media_url",
                               return_value="https://video/ejemplo"), \
             mock.patch.object(tv, "_current_title", return_value="Noticias"), \
             mock.patch.dict(sys.modules, {"pychromecast.quick_play": qp_mod}):
            out = tv.tv_cast(source="current")
        self.assertIn("Reproduciendo Noticias", out)

    def test_cast_sin_parametros_pide_aclaracion(self):
        tv = self._tv()
        out = tv.tv_cast()
        self.assertIn("¿Qué quieres enviar", out)

    def test_cast_con_target_filtra_tv(self):
        tv = self._tv(names=("Living Room", "Dormitorio"))
        qp_mod = mock.Mock()
        qp_mod.quick_play = mock.Mock()
        with mock.patch.object(tv, "_youtube_stream_url",
                               return_value="http://s/x"), \
             mock.patch.dict(sys.modules, {"pychromecast.quick_play": qp_mod}):
            out = tv.tv_cast(query="jazz", target="dormi")
        self.assertIn("en Dormitorio.", out)


class TestTvControl(unittest.TestCase):
    def test_accion_valida_llama_media_controller(self):
        tv = TVCommands()
        cast = fake_cast("Living Room")
        tv._last_tv_name = "Living Room"
        tv._pick_by_name = mock.Mock(return_value=cast)
        out = tv.tv_control("pause")
        cast.media_controller.pause.assert_called_once()
        self.assertEqual(out, "Hecho en Living Room.")

    def test_accion_invalida_rechazada(self):
        tv = TVCommands()
        out = tv.tv_control("formatear")
        self.assertIn("no soportada", out)

    def test_volumen_subir_baja(self):
        tv = TVCommands()
        cast = fake_cast()
        tv._last_tv_name = "X"
        tv._pick_by_name = mock.Mock(return_value=cast)
        tv.tv_control("volume_up")
        cast.set_volume.assert_called_once_with(0.6)
        tv.tv_control("volume_down")
        cast.set_volume.assert_called_with(0.4)


class TestResolve(unittest.TestCase):
    def test_url_directa_pasa_tal_cual(self):
        url, title = TVCommands._resolve(TVCommands(), 
                                         "https://vimeo.com/xyz", "")
        self.assertEqual(url, "https://vimeo.com/xyz")

    def test_resolve_local_file_inexistente(self):
        self.assertIsNone(resolve_local_file("/tmp/no-existe-12345.mp4", lambda p: p))

    def test_resolve_local_file_con_factory(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            seen = {}
            def factory(p):
                seen["path"] = p
                return "http://lan/media/abc"
            out = resolve_local_file(f.name, factory)
            self.assertEqual(out, "http://lan/media/abc")
            self.assertTrue(os.path.isfile(seen["path"]))

    def test_resolve_local_file_sin_factory_es_none(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            self.assertIsNone(resolve_local_file(f.name, None))


if __name__ == "__main__":
    unittest.main()
