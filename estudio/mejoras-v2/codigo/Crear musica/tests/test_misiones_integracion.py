"""Ediciones de misiones en generación y escucha, sin cliente ni análisis de audio."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import wave


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nucleo as N


def reemplazo(tiempo, primera=(3, 3, 3, 3), segunda=(2, 2, 2, 2), bolsa=1):
    return dict(tipo="reemplazar", tiempo=tiempo, primera=list(primera),
                segunda=None if segunda is None else list(segunda), bolsa=bolsa)


class MisionesIntegracionTest(unittest.TestCase):
    def setUp(self):
        self.fila = dict(ID="900001", Filename="bkgprueba", Difficulty="1",
                         BPM="60", StartDelayTime="0", Second="64",
                         MissionFailDanceID="201")
        self.rej = dict(bpm=60.0, dur=64.0, fin_beat=64.0, ogg=None)
        parches = [
            mock.patch.object(N, "pozo", side_effect=lambda nombre, estrellas:
                              {"0": 1} if "spaces" in nombre else {"157": 1}),
            mock.patch.object(N, "id_de_semilla", side_effect=lambda identificador: identificador),
            mock.patch.object(N, "menos_space_de", return_value=False),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def test_sin_acciones_conserva_la_generacion_anterior(self):
        original = N.generar(self.fila, self.rej, 1, 0)
        self.assertEqual(N.generar(self.fila, self.rej, 1, 0, misiones=[]), original)

    def test_x1_a_x4_respetan_triples_manuales_y_actualizan_conteos(self):
        for factor in range(1, 5):
            with self.subTest(factor=factor):
                bpm = 60.0 * factor
                original, _ = N.generar(self.fila, self.rej, 1, 0, bpm=bpm)
                resultado, informe = N.generar(
                    self.fila, self.rej, 1, 0, bpm=bpm,
                    misiones=[reemplazo(32.0 / factor)])
                self.assertEqual(resultado["MissionID1"].split(",")[2], "469")
                self.assertEqual(resultado["MissionID2"].split(",")[2], "313")
                self.assertEqual(resultado["KeyPatternID"].split(",")[2], "1")
                cambiadas = {c for c in resultado if resultado[c] != original[c]}
                self.assertTrue(cambiadas <= {"MissionID1", "MissionID2", "KeyPatternID"})
                self.assertTrue({"MissionID1", "MissionID2"} <= cambiadas)
                n = 4 * factor
                self.assertEqual(informe["misiones"], n)
                self.assertAlmostEqual(informe["flechas"], 4 + 8 / n)
                self.assertEqual(informe["tandas2"], 1)
                self.assertEqual(informe["flechas2"], 8)
                self.assertEqual(informe["space"], 0)
                self.assertEqual(informe["sin_space"], n)
                self.assertEqual(informe["fin_chart"], 64)
                marcas = N.golpes(resultado, 0, bpm)
                self.assertEqual(len(marcas), 4 * n + 4)

    def test_accion_se_aplica_despues_de_patron_y_descanso_sin_cambiar_tiempos(self):
        secciones = [dict(tipo="patron", desde=0, hasta=64,
                          primera=[1, 1, 1, 1], segunda=None, bolsa=4),
                     dict(tipo="descanso", desde=0, hasta=4)]
        resultado, informe = N.generar(
            self.fila, self.rej, 1, 0, secciones=secciones,
            misiones=[reemplazo(32, segunda=None)])
        self.assertEqual(float(resultado["StartDelayTime"]), 16)
        self.assertEqual(resultado["Length"], "16,16,16")
        self.assertEqual(resultado["MissionID1"], "157,469,157")
        self.assertEqual(resultado["MissionID2"], "0,0,0")
        self.assertEqual(resultado["KeyPatternID"], "4,1,4")
        self.assertEqual(informe["misiones"], 3)
        self.assertAlmostEqual(informe["flechas"], 20 / 3)
        self.assertEqual(informe["descansos"], 1)
        self.assertEqual(informe["tandas2"], 0)
        self.assertEqual(informe["fin_chart"], 64)

    def test_accion_no_reintroduce_una_mision_eliminada_por_descanso(self):
        original = copy.deepcopy(self.fila)
        acciones = [reemplazo(16)]
        acciones_originales = copy.deepcopy(acciones)
        resultado, _ = N.generar(
            self.fila, self.rej, 1, 0,
            secciones=[dict(tipo="descanso", desde=16, hasta=20)],
            misiones=acciones)
        self.assertEqual(resultado["Length"], "32,16,16")
        self.assertFalse(any(16 <= g["t"] < 20 for g in N.golpes(resultado, 0, 60)))
        self.assertEqual(acciones, acciones_originales)
        self.assertEqual(self.fila, original)
        recuperado, _ = N.generar(self.fila, self.rej, 1, 0, misiones=acciones)
        self.assertEqual(recuperado["MissionID1"].split(",")[1], "469")
        self.assertEqual(recuperado["MissionID2"].split(",")[1], "313")

    def test_previo_incluye_las_dos_tandas_de_la_mision_reemplazada(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ogg = Path(carpeta) / "audio.ogg"
            ogg.touch()
            with mock.patch.object(N, "armar_escucha") as escuchar:
                _, informe = N.previo(
                    self.fila, dict(self.rej, ogg=ogg), 1, 0,
                    segundos=24, desde=0, musica=False,
                    salida=Path(carpeta) / "previo.wav", misiones=[reemplazo(16)])
            self.assertEqual(informe["misiones"], 4)
            self.assertEqual(informe["marcas"], 12)
            self.assertEqual(informe["flechas"], 24)
            self.assertEqual(informe["space"], 0)
            marcas = escuchar.call_args.args[1]
            reemplazadas = [g for g in marcas if 16 <= g["t"] < 24]
            self.assertEqual([g["flechas"] for g in reemplazadas], [3] * 4 + [2] * 4)
            self.assertEqual([g["tanda"] for g in reemplazadas], [1] * 4 + [2] * 4)

    def test_comparar_compases_aplica_acciones_en_todos_los_previos(self):
        def escribir_wav(ogg, marcas, desde, segundos, salida, **kwargs):
            with wave.open(str(salida), "wb") as archivo:
                archivo.setnchannels(1)
                archivo.setsampwidth(2)
                archivo.setframerate(N.SR_ESCUCHA)
                archivo.writeframes(b"\x00\x00" * 8)

        with tempfile.TemporaryDirectory() as carpeta:
            cache = Path(carpeta)
            ogg = cache / "audio.ogg"
            ogg.touch()
            with mock.patch.object(N, "CACHE", cache), \
                    mock.patch.object(N, "armar_escucha", side_effect=escribir_wav) as escuchar:
                N.probar_los_cuatro(
                    self.fila, dict(self.rej, ogg=ogg), 1, [0, 0, 0, 0],
                    salida=cache / "cuatro.wav", misiones=[reemplazo(16)])
            self.assertEqual(escuchar.call_count, 4)
            for llamada in escuchar.call_args_list:
                marcas = [g for g in llamada.args[1] if 16 <= g["t"] < 24]
                self.assertEqual([g["flechas"] for g in marcas], [3] * 4 + [2] * 4)


if __name__ == "__main__":
    unittest.main()
