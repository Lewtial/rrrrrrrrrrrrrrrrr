"""Selección de otra dificultad y aplicación solo del plan realmente revisado."""
import copy
import os
from pathlib import Path
import sys
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dialogo_adoptar import DialogoAdoptar, etiqueta_fuente, preparar_fuentes, validar_estrellas
import tema as T


def destino():
    return dict(ID='30', Filename='bkg0200', Difficulty='6', BPM='230', Title='Hypno')


def fuentes():
    return [dict(ID='31', Filename='bkg0200', Difficulty='8', BPM='230', Title='Hypno'),
            dict(ID='32', Filename='bkg0200', Difficulty='10', BPM='220', Title='Hypno')]


class OpcionesAdoptarTests(unittest.TestCase):
    def test_acepta_los_diez_niveles_y_espacios_del_formulario(self):
        for n in range(1, 11):
            self.assertEqual(validar_estrellas(' %s ' % n), n)
            self.assertEqual(validar_estrellas(n), n)

    def test_rechaza_estrellas_fuera_de_rango_decimales_y_no_numericas(self):
        for valor in ('', '0', '11', '-1', '6.0', '6,5', '2e0', None, True, float('nan'), '٦'):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                validar_estrellas(valor)

    def test_muestra_fuentes_mas_dificiles_primero_y_conserva_entradas(self):
        antes = fuentes()
        original = copy.deepcopy(antes)
        resultado = preparar_fuentes(antes, destino())
        self.assertEqual([f['ID'] for f in resultado], ['32', '31'])
        resultado[0]['Title'] = 'modificado'
        self.assertEqual(antes, original)

    def test_otra_cancion_con_el_mismo_titulo_no_es_una_fuente_valida(self):
        otra = fuentes()[0]
        otra['Filename'] = 'bkg9999'
        self.assertEqual(otra['Title'], destino()['Title'])
        with self.assertRaisesRegex(ValueError, 'misma canción'):
            preparar_fuentes([otra], destino())

    def test_el_destino_no_puede_adoptarse_a_si_mismo(self):
        igual = fuentes()[0]
        igual['ID'] = 30
        with self.assertRaisesRegex(ValueError, 'distinta'):
            preparar_fuentes([igual], destino())

    def test_rechaza_ids_duplicados_y_lista_vacia(self):
        for lista in ([], [fuentes()[0], fuentes()[0]]):
            with self.subTest(lista=lista), self.assertRaises(ValueError):
                preparar_fuentes(lista, destino())

    def test_exige_bpm_validos_en_ambos_lados(self):
        for valor in ('0', '-1', 'nan', 'inf', 'hola', None):
            with self.subTest(valor=valor):
                d = destino()
                d['BPM'] = valor
                with self.assertRaises(ValueError):
                    preparar_fuentes(fuentes(), d)
                lista = fuentes()
                lista[0]['BPM'] = valor
                with self.assertRaises(ValueError):
                    preparar_fuentes(lista, destino())

    def test_etiquetas_distinguen_ids_aun_con_mismas_estrellas_y_bpm(self):
        a = fuentes()[0]
        b = dict(a, ID='999')
        self.assertNotEqual(etiqueta_fuente(a), etiqueta_fuente(b))
        self.assertIn('230 BPM', etiqueta_fuente(a))
        self.assertIn('ID 31', etiqueta_fuente(a))


@unittest.skipUnless(os.environ.get('DISPLAY'), 'Tk real necesita un display; los tests de datos siguen activos')
class DialogoAdoptarTkTests(unittest.TestCase):
    def setUp(self):
        self.raiz = tk.Tk()
        T.aplicar(self.raiz)
        self.raiz.withdraw()
        self.raiz.trabajando = False
        self.preparar = mock.Mock(return_value=dict(texto_resumen='Origen: 10 estrellas\nDestino: 6 estrellas\nMáximo: 2 flechas'))
        self.aplicar = mock.Mock(return_value=True)
        self.d = DialogoAdoptar(self.raiz, fuentes(), destino(), self.preparar, self.aplicar)
        self.raiz.update()
        self.errores = mock.patch('dialogo_adoptar.messagebox.showerror').start()
        self.addCleanup(mock.patch.stopall)

    def tearDown(self):
        self.raiz.destroy()

    def test_sin_vista_previa_no_aplica_y_no_cierra(self):
        self.assertEqual(str(self.d.b_aplicar.cget('state')), 'disabled')
        self.assertFalse(self.d._aplicar())
        self.preparar.assert_not_called()
        self.aplicar.assert_not_called()
        self.assertTrue(self.d.winfo_exists())

    def test_prepara_con_la_fuente_elegida_y_el_nivel_manual_y_aplica_el_mismo_plan(self):
        self.d.v_fuente.set(etiqueta_fuente(fuentes()[0]))
        self.d.v_estrellas.set('7')
        self.assertTrue(self.d._previsualizar())
        self.preparar.assert_called_once_with('31', 7)
        plan = self.d.plan_actual
        self.assertEqual(str(self.d.b_aplicar.cget('state')), 'normal')
        self.assertIn('Máximo: 2 flechas', self.d.texto_resumen.get('1.0', 'end'))
        self.assertTrue(self.d._aplicar())
        self.aplicar.assert_called_once()
        self.assertIs(self.aplicar.call_args.args[0], plan)
        self.assertFalse(self.d.winfo_exists())

    def test_cambiar_fuente_o_estrellas_invalida_el_plan_antes_de_aplicar(self):
        for variable, valor in ((self.d.v_fuente, etiqueta_fuente(fuentes()[0])),
                                (self.d.v_estrellas, '5')):
            self.assertTrue(self.d._previsualizar())
            variable.set(valor)
            self.assertIsNone(self.d.plan_actual)
            self.assertEqual(str(self.d.b_aplicar.cget('state')), 'disabled')
            self.assertFalse(self.d._aplicar())
            self.aplicar.assert_not_called()

    def test_preparar_invalido_no_entrega_el_plan_anterior(self):
        self.assertTrue(self.d._previsualizar())
        self.preparar.side_effect = ValueError('El chart cambió')
        self.assertFalse(self.d._previsualizar())
        self.assertIsNone(self.d.plan_actual)
        self.assertEqual(str(self.d.b_aplicar.cget('state')), 'disabled')
        self.errores.assert_called_once()
        self.assertFalse(self.d._aplicar())
        self.aplicar.assert_not_called()

    def test_rechazo_al_aplicar_conserva_dialogo_y_no_cierra(self):
        self.aplicar.return_value = False
        self.assertTrue(self.d._previsualizar())
        self.assertFalse(self.d._aplicar())
        self.assertTrue(self.d.winfo_exists())
        self.assertIn('No se aplicó', self.d.v_estado.get())

    def test_error_al_aplicar_conserva_dialogo_y_muestra_el_motivo(self):
        self.aplicar.side_effect = OSError('No se pudo guardar la configuración')
        self.assertTrue(self.d._previsualizar())
        self.assertFalse(self.d._aplicar())
        self.assertTrue(self.d.winfo_exists())
        self.errores.assert_called_once()

    def test_trabajo_en_curso_impide_preparar_y_aplicar(self):
        self.assertTrue(self.d._previsualizar())
        self.raiz.trabajando = True
        self.assertFalse(self.d._previsualizar())
        self.assertFalse(self.d._aplicar())
        self.aplicar.assert_not_called()
        self.assertEqual(self.preparar.call_count, 1)

    def test_aviso_bpm_cambia_segun_la_fuente_sin_modificar_destino(self):
        self.assertIn('BPM distintos', self.d.lbl_bpm.cget('text'))
        self.d.v_fuente.set(etiqueta_fuente(fuentes()[0]))
        self.assertIn('Mismo BPM', self.d.lbl_bpm.cget('text'))
        self.assertEqual(self.d.destino, destino())


if __name__ == '__main__':
    unittest.main()
