from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dialogo_secciones import (
    _normalizar_seccion, _tiempo_editable, formatear_tiempo, parsear_tiempo,
)


class TiemposSeccionesTest(unittest.TestCase):
    def test_lee_segundos_y_minutos_con_punto_o_coma(self):
        for texto, esperado in (("0", 0), ("12.5", 12.5), ("12,5", 12.5),
                                 (" 1:02.345 ", 62.345), ("2:03,5", 123.5)):
            with self.subTest(texto=texto):
                self.assertAlmostEqual(parsear_tiempo(texto), esperado)

    def test_rechaza_tiempos_invalidos_y_no_finitos(self):
        for texto in ("", "-1", "NaN", "inf", "1e999", "1:60", "1:-2", "1:inf",
                      "1:02:03", "1.5:20", "hola", "1,2.3"):
            with self.subTest(texto=texto):
                with self.assertRaises(ValueError):
                    parsear_tiempo(texto)

    def test_el_redondeo_no_muestra_sesenta_segundos(self):
        self.assertEqual(formatear_tiempo(59.9999), "1:00.000")
        self.assertEqual(formatear_tiempo(3599.9999), "60:00.000")
        self.assertEqual(formatear_tiempo(0), "0:00.000")

    def test_editar_no_redondea_el_limite_fuera_del_audio(self):
        duracion = 100.123456789
        self.assertEqual(parsear_tiempo(_tiempo_editable(duracion)), duracion)


class IntervalosSeccionesTest(unittest.TestCase):
    def test_admite_el_final_exacto_del_audio(self):
        seccion = dict(desde=0, hasta=100, tipo="descanso")
        self.assertEqual(_normalizar_seccion(seccion, 100), seccion)

    def test_rechaza_intervalos_vacios_invertidos_y_fuera_del_audio(self):
        for desde, hasta in ((0, 0), (20, 10), (-1, 10), (0, 100.1),
                              (float("nan"), 10), (0, float("inf"))):
            with self.subTest(desde=desde, hasta=hasta):
                with self.assertRaises(ValueError):
                    _normalizar_seccion(dict(desde=desde, hasta=hasta, tipo="descanso"), 100)

    def test_las_tandas_de_la_copia_no_modifican_el_original(self):
        original = dict(desde=0, hasta=100, tipo="patron", primera=[1, 0, 1, 0],
                        segunda=[2, 0, 2, 0], bolsa=4)
        copia = _normalizar_seccion(original, 100)
        copia["primera"][0] = 3
        copia["segunda"][0] = 3
        self.assertEqual(original["primera"], [1, 0, 1, 0])
        self.assertEqual(original["segunda"], [2, 0, 2, 0])

    def test_space_sigue_siendo_patron_y_no_descanso(self):
        seccion = _normalizar_seccion(dict(desde=0, hasta=100, tipo="patron",
                                         primera=[0, 0, 0, 0], segunda=None, bolsa=4), 100)
        self.assertEqual(seccion["tipo"], "patron")
        self.assertEqual(seccion["primera"], [0, 0, 0, 0])
        self.assertIsNone(seccion["segunda"])

    def test_descanso_no_conserva_misiones_del_formulario(self):
        seccion = _normalizar_seccion(dict(desde=0, hasta=100, tipo="descanso",
                                         primera=[3, 3, 3, 3], segunda=None, bolsa=4), 100)
        self.assertEqual(set(seccion), {"desde", "hasta", "tipo"})


if __name__ == "__main__":
    unittest.main()
