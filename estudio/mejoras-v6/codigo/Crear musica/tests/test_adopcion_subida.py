"""Subir de nivel adapta grupos positivos sin cambiar el ritmo elegido."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adoptar_version import adoptar_version
from secciones import LISTAS
from test_adoptar_version import codificar, fila, patron


def cantidades(chart, columna):
    return [n for valor in chart[columna].split(',')
            if columna != 'MissionID2' or float(valor) != 0
            for n in patron(valor)]


def fuente(n=32, bpm=290, estrellas=6, primera=(1, 0, 2, 2), segunda=(2, 0, 1, 0)):
    return fila(1, bpm=bpm, estrellas=estrellas, largos=(16,) * n,
                primera=[codificar(primera)] * n,
                segunda=['0' if segunda is None else codificar(segunda)] * n)


class SubidaAdopcionTest(unittest.TestCase):
    def setUp(self):
        self.origen = fuente()
        self.destino = fila(2, bpm=290, estrellas=10)

    def subir(self, **kwargs):
        return adoptar_version(self.origen, self.destino, ajustar_nivel=True, **kwargs)

    def test_seis_a_diez_aumenta_flechas_y_triples_en_ambas_tandas(self):
        antes = copy.deepcopy((self.origen, self.destino))
        nuevo, info = self.subir()
        self.assertTrue(info['ajuste_subida'])
        self.assertEqual(info['origen_estrellas'], 6)
        self.assertGreater(info['grupos_aumentados_primera'], 0)
        self.assertGreater(info['grupos_aumentados_segunda'], 0)
        self.assertGreater(info['flechas_agregadas'], 0)
        self.assertGreater(info['triples_despues'], info['triples_antes'])
        self.assertGreater(info['flechas_despues'], info['flechas_antes'])
        self.assertEqual((self.origen, self.destino), antes)
        self.assertNotIn('ID', nuevo)
        self.assertNotIn('Filename', nuevo)

    def test_conserva_cada_space_y_no_reduce_grupos_positivos(self):
        nuevo, info = self.subir()
        for columna in ('MissionID1', 'MissionID2'):
            antes, despues = cantidades(self.origen, columna), cantidades(nuevo, columna)
            self.assertEqual([n == 0 for n in despues], [n == 0 for n in antes])
            self.assertTrue(all(b >= a for a, b in zip(antes, despues)))
            self.assertLessEqual(max(despues), 3)
        self.assertEqual(info['spaces_antes'], info['spaces_despues'])

    def test_solo_cambian_las_dos_columnas_de_contenido(self):
        nuevo, _ = self.subir()
        for columna in LISTAS:
            if columna not in ('MissionID1', 'MissionID2'):
                self.assertEqual(nuevo[columna], self.origen[columna], columna)
        self.assertEqual(nuevo['StartDelayTime'], self.origen['StartDelayTime'])

    def test_reparto_de_cada_tanda_sigue_su_referencia_sin_hacer_todo_triple(self):
        from nucleo import REF_FLECHAS, REF_SPACE
        self.origen = fuente(40, primera=(1, 1, 1, 1), segunda=(1, 1, 1, 1))
        nuevo, _ = self.subir()
        for columna, referencia in (('MissionID1', REF_FLECHAS[10]),
                                    ('MissionID2', REF_SPACE[10])):
            entradas = cantidades(nuevo, columna)
            for numero in (1, 2, 3):
                esperado = referencia[numero] / sum(referencia[1:])
                self.assertLessEqual(abs(entradas.count(numero) / len(entradas) - esperado),
                                     1 / len(entradas))
            self.assertGreater(entradas.count(1), 0)
            self.assertGreater(entradas.count(2), 0)
            self.assertGreater(entradas.count(3), 0)
        self.assertGreater(cantidades(nuevo, 'MissionID2').count(3),
                           cantidades(nuevo, 'MissionID1').count(3))

    def test_no_crea_segunda_tanda_ausente_y_conserva_tanda_solo_space(self):
        self.origen['MissionID2'] = ','.join(['0', '1'] * 16)
        nuevo, _ = self.subir()
        self.assertEqual(nuevo['MissionID2'], self.origen['MissionID2'])
        self.assertEqual(len(cantidades(nuevo, 'MissionID2')), 16 * 4)

    def test_solo_space_permanece_jugable_y_reporta_por_que_no_sube(self):
        self.origen = fuente(4, primera=(0, 0, 0, 0), segunda=(0, 0, 0, 0))
        nuevo, info = self.subir()
        self.assertEqual(nuevo['MissionID1'], self.origen['MissionID1'])
        self.assertEqual(nuevo['MissionID2'], self.origen['MissionID2'])
        self.assertEqual(info['grupos_aumentados'], 0)
        self.assertEqual(info['spaces_despues'], 32)
        self.assertTrue(any('solo contiene SPACE' in texto for texto in info['advertencias']))

    def test_grupos_ya_al_tope_no_cambian_y_se_explica(self):
        self.origen = fuente(4, primera=(3, 0, 3, 3), segunda=None)
        nuevo, info = self.subir()
        self.assertEqual(nuevo['MissionID1'], self.origen['MissionID1'])
        self.assertEqual(info['flechas_agregadas'], 0)
        self.assertTrue(any('ya alcanzan el límite' in texto for texto in info['advertencias']))

    def test_desactivar_modo_conserva_exactamente_la_adopcion_anterior(self):
        anterior = adoptar_version(self.origen, self.destino)
        desactivado = adoptar_version(self.origen, self.destino, ajustar_nivel=False)
        self.assertEqual(anterior, desactivado)
        self.assertEqual(desactivado[0]['MissionID1'], self.origen['MissionID1'])
        self.assertFalse(desactivado[1]['ajuste_subida'])
        self.assertEqual(desactivado[1]['flechas_agregadas'], 0)

    def test_no_eleva_al_bajar_o_adoptar_el_mismo_nivel(self):
        for nivel in (4, 6):
            with self.subTest(nivel=nivel):
                anterior, _ = adoptar_version(self.origen, self.destino, estrellas=nivel)
                nuevo, info = self.subir(estrellas=nivel)
                self.assertEqual(nuevo, anterior)
                self.assertFalse(info['ajuste_subida'])
                self.assertEqual(info['grupos_aumentados'], 0)

    def test_siete_estrellas_rapidas_solo_sube_hasta_dos(self):
        self.origen = fuente(estrellas=4, primera=(1, 0, 1, 1), segunda=(1, 0, 1, 0))
        nuevo, info = self.subir(estrellas=7)
        self.assertEqual(info['tope_flechas'], 2)
        self.assertGreater(info['flechas_agregadas'], 0)
        for c in ('MissionID1', 'MissionID2'):
            self.assertLessEqual(max(cantidades(nuevo, c)), 2)

    def test_limite_manual_mas_bajo_tambien_se_respeta_al_subir(self):
        nuevo, info = self.subir(limite_flechas=1)
        self.assertEqual(info['tope_flechas'], 1)
        self.assertEqual(info['flechas_agregadas'], 0)
        for c in ('MissionID1', 'MissionID2'):
            self.assertLessEqual(max(cantidades(nuevo, c)), 1)

    def test_repetir_y_cambiar_id_o_arranque_no_resortea_la_subida(self):
        primero, info = self.subir()
        self.assertEqual(self.subir(), (primero, info))
        for cambio in (dict(ID='999'), dict(StartDelayTime='9.25')):
            nuevo, otro_info = adoptar_version(dict(self.origen, **cambio), self.destino,
                                               ajustar_nivel=True)
            for c in ('MissionID1', 'MissionID2'):
                self.assertEqual(nuevo[c], primero[c])
            self.assertEqual(otro_info['grupos_aumentados'], info['grupos_aumentados'])

    def test_bpm_distinto_conserva_geometria_adaptada_y_descansos(self):
        self.origen = fuente(3, bpm=120)
        self.origen['Length'] = '32,16,16'
        self.destino['BPM'] = '240'
        base, base_info = adoptar_version(self.origen, self.destino)
        nuevo, info = self.subir()
        for c in LISTAS + ('StartDelayTime',):
            if c not in ('MissionID1', 'MissionID2'):
                self.assertEqual(nuevo[c], base[c], c)
        self.assertEqual(info['descansos'], base_info['descansos'])
        self.assertGreater(info['flechas_agregadas'], 0)

    def test_segunda_retirada_por_bpm_no_se_cuenta_ni_recrea(self):
        self.origen = fuente(4, bpm=240)
        self.destino['BPM'] = '120'
        nuevo, info = self.subir()
        self.assertEqual(nuevo['MissionID2'], '0,0,0,0')
        self.assertEqual(info['segundas_retiradas'], 4)
        self.assertEqual(info['grupos_aumentados_segunda'], 0)
        self.assertEqual(info['casilleros_positivos'], 12)

    def test_reporte_cuenta_los_cambios_reales_de_las_misiones_retenidas(self):
        base, _ = adoptar_version(self.origen, self.destino)
        nuevo, info = self.subir()
        antes = sum((cantidades(base, c) for c in ('MissionID1', 'MissionID2')), [])
        despues = sum((cantidades(nuevo, c) for c in ('MissionID1', 'MissionID2')), [])
        self.assertEqual(info['flechas_agregadas'], sum(despues) - sum(antes))
        self.assertEqual(info['grupos_aumentados'], sum(a != b for a, b in zip(antes, despues)))
        self.assertEqual(info['flechas_despues'], sum(despues))
        self.assertEqual(info['triples_despues'], despues.count(3))

    def test_estrellas_sucesivas_no_reducen_densidad_de_subida(self):
        self.origen = fuente(bpm=120)
        self.destino['BPM'] = '120'
        totales = [self.subir(estrellas=nivel)[1]['flechas_despues'] for nivel in (7, 8, 9, 10)]
        self.assertEqual(totales, sorted(totales))
        self.assertGreater(totales[-1], totales[0])

    def test_valida_opcion_booleana_y_nivel_origen_solo_cuando_es_necesario(self):
        for valor in (None, 0, 1, 'sí'):
            with self.subTest(opcion=valor), self.assertRaises(ValueError):
                adoptar_version(self.origen, self.destino, ajustar_nivel=valor)
        for valor in (None, 0, 11, True, 'seis'):
            with self.subTest(origen=valor), self.assertRaises(ValueError):
                adoptar_version(dict(self.origen, Difficulty=valor), self.destino, ajustar_nivel=True)
        sin_nivel = dict(self.origen)
        del sin_nivel['Difficulty']
        adoptar_version(sin_nivel, self.destino)


if __name__ == '__main__': unittest.main()
