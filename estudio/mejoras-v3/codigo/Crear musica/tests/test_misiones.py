import copy
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from misiones import aplicar_misiones, validar_misiones
from secciones import LISTAS, aplicar_secciones


def chart(largos=(16, 16, 16), inicio=10.0):
    n = len(largos)
    salida = {c: ",".join(["0"] * n) for c in LISTAS}
    salida.update({
        "Length": ",".join(map(str, largos)),
        "MissionID1": ",".join(str(157 + i) for i in range(n)),
        "MissionID2": ",".join("313" if i % 2 else "0" for i in range(n)),
        "KeyPatternID": ",".join(str(1 + i % 4) for i in range(n)),
        "MissionDanceID": ",".join(str(501 + i) for i in range(n)),
        "MissionSuccessDanceID": ",".join(str(601 + i) for i in range(n)),
        "MissionFailDanceID": ",".join(str(201 + i) for i in range(n)),
        "MissionCameraID": ",".join(["101"] + ["0"] * (n - 1)),
        "DanceCameraID": ",".join(["111"] * (n - 1) + ["241"]),
        "StartDelayTime": str(inicio), "Second": "100", "BPM": "60",
        "Difficulty": "1",
    })
    return salida


def reemplazo(tiempo=26.0, primera=(2, 0, 1, 0), segunda=None, bolsa=4):
    return dict(tipo="reemplazar", tiempo=tiempo, primera=list(primera),
                segunda=None if segunda is None else list(segunda), bolsa=bolsa)


class MisionesTest(unittest.TestCase):
    def setUp(self):
        self.original = chart()
        self.fila = dict(self.original, ID="2001", Filename="bkg2001")

    def aplicar(self, acciones, listas=None, inicio=10.0, bpm=60.0, secciones=(),
                permitir_inactivas=False):
        return aplicar_misiones(self.fila, self.original if listas is None else listas,
                                 inicio, bpm, acciones, secciones=secciones,
                                 permitir_inactivas=permitir_inactivas)

    def test_sin_acciones_conserva_todo_literalmente(self):
        for acciones in ([], ()):
            self.assertEqual(self.aplicar(acciones), self.original)
            self.assertIsNot(self.aplicar(acciones), self.original)

    def test_reemplazar_cambia_solo_tandas_y_bolsa_destino(self):
        resultado = self.aplicar([reemplazo(segunda=(1, 1, 1, 1), bolsa=3)])
        esperado = dict(self.original)
        esperado.update(MissionID1="157,256,159", MissionID2="0,157,0",
                        KeyPatternID="1,3,3")
        self.assertEqual(resultado, esperado)
        self.assertEqual({len(resultado[c].split(",")) for c in LISTAS}, {3})

    def test_no_mueve_inicios_ni_fin_del_chart(self):
        resultado = self.aplicar([reemplazo()])
        self.assertEqual(resultado["Length"], self.original["Length"])
        self.assertEqual(resultado["StartDelayTime"], self.original["StartDelayTime"])
        self.assertEqual(resultado["Second"], self.original["Second"])

    def test_no_modifica_argumentos(self):
        acciones = [reemplazo()]
        secciones = [dict(tipo="descanso", desde=70, hasta=80)]
        antes = copy.deepcopy((self.fila, self.original, acciones, secciones))
        self.aplicar(acciones, secciones=secciones)
        self.assertEqual((self.fila, self.original, acciones, secciones), antes)

    def test_acepta_destino_con_redondeo_a_cuatro_decimales(self):
        resultado = self.aplicar([reemplazo(tiempo=26.00009)])
        self.assertEqual(resultado["MissionID1"].split(",")[1], "256")
        resultado = self.aplicar([reemplazo(tiempo=100.0001)], listas=chart(inicio=84))
        self.assertEqual(resultado["MissionID1"].split(",")[1], "256")

    def test_rechaza_tiempo_que_no_es_inicio_existente(self):
        for tiempo in (0, 10.001, 25.9998, 27, 58, 99):
            with self.subTest(tiempo=tiempo), self.assertRaisesRegex(ValueError, "No existe"):
                self.aplicar([reemplazo(tiempo=tiempo)])

    def test_ancla_real_del_chart_tiene_prioridad_sobre_formulario(self):
        listas = chart(inicio=42)
        resultado = self.aplicar([reemplazo(tiempo=58)], listas=listas, inicio=10)
        self.assertEqual(resultado["MissionID1"], "157,256,159")
        self.assertEqual(resultado["StartDelayTime"], "42")

    def test_destino_usa_bpm_para_tiempo_absoluto(self):
        resultado = self.aplicar([reemplazo(tiempo=18)], bpm=120)
        self.assertEqual(resultado["MissionID1"], "157,256,159")

    def test_ultimo_reemplazo_del_mismo_destino_gana(self):
        acciones = [reemplazo(primera=(1, 1, 1, 1), segunda=(3, 3, 3, 3)),
                    reemplazo(primera=(3, 3, 3, 3), segunda=None, bolsa=1)]
        resultado = self.aplicar(acciones)
        self.assertEqual(resultado["MissionID1"], "157,469,159")
        self.assertEqual(resultado["MissionID2"], "0,0,0")
        self.assertEqual(resultado["KeyPatternID"], "1,1,3")

    def test_sin_limites_automaticos_de_softnyx(self):
        resultado = self.aplicar([reemplazo(primera=(3, 3, 3, 3))])
        self.assertEqual(resultado["Difficulty"], "1")
        self.assertEqual(resultado["MissionID1"].split(",")[1], "469")

    def test_segunda_none_la_quita_y_patron_cero_sigue_siendo_tanda(self):
        resultado = self.aplicar([reemplazo(segunda=None)])
        self.assertEqual(resultado["MissionID2"], "0,0,0")
        resultado = self.aplicar([reemplazo(segunda=(0, 0, 0, 0))])
        self.assertEqual(resultado["MissionID2"], "0,1,0")

    def test_rechaza_segunda_en_mision_menor_de_16(self):
        with self.assertRaisesRegex(ValueError, "menos de 16"):
            self.aplicar([reemplazo(segunda=(1, 1, 1, 1))], listas=chart((16, 8, 16)))
        resultado = self.aplicar([reemplazo()], listas=chart((16, 8, 16)))
        self.assertEqual(resultado["Length"], "16,8,16")

    def test_rechaza_ventana_que_cruza_descanso(self):
        descanso = dict(tipo="descanso", desde=28, hasta=29)
        with self.assertRaisesRegex(ValueError, "descanso"):
            self.aplicar([reemplazo()], secciones=[descanso])

    def test_descanso_en_segunda_tanda_solo_impide_segunda_tanda(self):
        descanso = dict(tipo="descanso", desde=31, hasta=32)
        self.aplicar([reemplazo()], secciones=[descanso])
        with self.assertRaisesRegex(ValueError, "descanso"):
            self.aplicar([reemplazo(segunda=(0, 0, 0, 0))], secciones=[descanso])

    def test_reproduccion_suspende_copia_cuyo_destino_retiro_el_descanso(self):
        secciones = [dict(tipo="descanso", desde=26, hasta=30)]
        listas = aplicar_secciones(self.fila, self.original, 10, 60, secciones)
        acciones = [reemplazo()]
        antes = copy.deepcopy((acciones, listas, secciones))
        resultado = self.aplicar(acciones, listas=listas, secciones=secciones,
                                 permitir_inactivas=True)
        self.assertEqual(resultado, listas)
        self.assertEqual((acciones, listas, secciones), antes)
        self.assertEqual(resultado["Length"], "32,16")

    def test_quitar_descanso_recupera_copia_persistida(self):
        acciones = [reemplazo(primera=(3, 3, 3, 3), bolsa=1)]
        secciones = [dict(tipo="descanso", desde=26, hasta=30)]
        listas = aplicar_secciones(self.fila, self.original, 10, 60, secciones)
        self.aplicar(acciones, listas=listas, secciones=secciones,
                     permitir_inactivas=True)
        recuperado = self.aplicar(acciones, permitir_inactivas=True)
        self.assertEqual(recuperado["MissionID1"], "157,469,159")
        self.assertEqual(recuperado["KeyPatternID"], "1,1,3")
        self.assertEqual(recuperado["Length"], self.original["Length"])

    def test_reproduccion_suspende_si_segunda_deseada_cruza_descanso(self):
        acciones = [reemplazo(segunda=(0, 0, 0, 0))]
        secciones = [dict(tipo="descanso", desde=31, hasta=32)]
        listas = aplicar_secciones(self.fila, self.original, 10, 60, secciones)
        resultado = self.aplicar(acciones, listas=listas, secciones=secciones,
                                 permitir_inactivas=True)
        self.assertEqual(resultado, listas)
        self.assertEqual(len(resultado["Length"].split(",")), 2)

    def test_edicion_directa_sigue_rechazando_destino_cubierto(self):
        acciones = [reemplazo()]
        secciones = [dict(tipo="descanso", desde=26, hasta=30)]
        with self.assertRaisesRegex(ValueError, "descanso"):
            self.aplicar(acciones, secciones=secciones)
        listas = aplicar_secciones(self.fila, self.original, 10, 60, secciones)
        with self.assertRaisesRegex(ValueError, "No existe"):
            self.aplicar(acciones, listas=listas, secciones=secciones)

    def test_reproduccion_rechaza_destino_ausente_fuera_de_descanso(self):
        with self.assertRaisesRegex(ValueError, "No existe"):
            self.aplicar([reemplazo(tiempo=99)],
                         secciones=[dict(tipo="descanso", desde=26, hasta=30)],
                         permitir_inactivas=True)

    def test_ultima_accion_suspendida_no_reactiva_anterior_del_destino(self):
        acciones = [reemplazo(primera=(1, 1, 1, 1)),
                    reemplazo(tiempo=26.00009, segunda=(1, 1, 1, 1))]
        secciones = [dict(tipo="descanso", desde=31, hasta=32)]
        listas = aplicar_secciones(self.fila, self.original, 10, 60, secciones)
        self.assertEqual(self.aplicar(acciones, listas=listas, secciones=secciones,
                                      permitir_inactivas=True), listas)

    def test_redondeos_sucesivos_no_reactivan_copias_antiguas_suspendidas(self):
        acciones = [reemplazo(tiempo=26, primera=(1, 1, 1, 1)),
                    reemplazo(tiempo=26.00009, primera=(2, 2, 2, 2)),
                    reemplazo(tiempo=26.00018, segunda=(1, 1, 1, 1))]
        secciones = [dict(tipo="descanso", desde=31, hasta=32)]
        listas = aplicar_secciones(self.fila, self.original, 10, 60, secciones)
        self.assertEqual(self.aplicar(acciones, listas=listas, secciones=secciones,
                                      permitir_inactivas=True), listas)

    def test_limites_de_descanso_son_semiabiertos(self):
        self.aplicar([reemplazo()], secciones=[dict(tipo="descanso", desde=30, hasta=31)])
        self.aplicar([reemplazo()], secciones=[dict(tipo="descanso", desde=20, hasta=26)])

    def test_redondeo_del_arranque_no_crea_conflicto_en_borde_de_descanso(self):
        listas = chart(inicio=10.00005)
        self.aplicar([reemplazo()], listas=listas,
                     secciones=[dict(tipo="descanso", desde=30, hasta=31)])
        self.aplicar([reemplazo()], listas=listas,
                     secciones=[dict(tipo="descanso", desde=20, hasta=26.0001)])

    def test_no_normaliza_columnas_ni_elementos_ajenos(self):
        original = dict(self.original, MissionID1=" 157 ,158, 159 ",
                        MissionDanceID=" 501 , 502 ,503 ", Length="16, 16,16")
        resultado = self.aplicar([reemplazo()], listas=original)
        self.assertEqual(resultado["MissionID1"], " 157 ,256, 159 ")
        self.assertEqual(resultado["MissionDanceID"], original["MissionDanceID"])
        self.assertEqual(resultado["Length"], original["Length"])

    def test_rechaza_listas_desalineadas(self):
        with self.assertRaisesRegex(ValueError, "misma cantidad"):
            self.aplicar([reemplazo()], listas=dict(self.original, KeySoundID="0,0"))

    def test_rechaza_crear_y_estructuras_malformadas(self):
        for invalido in (None, {}, "", 0, [None], [dict(reemplazo(), tipo="crear")]):
            with self.subTest(invalido=invalido), self.assertRaises(ValueError):
                validar_misiones(invalido)

    def test_rechaza_tiempos_y_bpm_invalidos(self):
        for numero in (float("nan"), float("inf"), -1, True, "26"):
            with self.subTest(numero=numero), self.assertRaises(ValueError):
                self.aplicar([reemplazo(tiempo=numero)])
        for bpm in (0, -1, float("inf"), float("nan"), True):
            with self.subTest(bpm=bpm), self.assertRaises(ValueError):
                self.aplicar([reemplazo()], bpm=bpm)

    def test_rechaza_patrones_y_bolsas_invalidos(self):
        for patron in ([1, 1, 1], [1, 1, 1, 4], [True, 1, 1, 1], "1111", [1.0] * 4):
            with self.subTest(patron=patron), self.assertRaises(ValueError):
                validar_misiones([dict(reemplazo(), primera=patron)])
        for bolsa in (0, 5, "1", 1.0, True):
            with self.subTest(bolsa=bolsa), self.assertRaises(ValueError):
                validar_misiones([dict(reemplazo(), bolsa=bolsa)])


if __name__ == "__main__":
    unittest.main()
