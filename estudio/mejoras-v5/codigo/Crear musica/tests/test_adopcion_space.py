"""Las misiones solo SPACE siguen siendo entradas jugables tras adoptar.

Se comprueba la tabla real y los eventos de escucha, sin escribir al juego.
La presentación de esos mismos datos se prueba aparte en la interfaz.
"""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nucleo as N
import secciones as S
from adoptar_version import adoptar_version


def fila(identificador, bpm, largo_space=16, segunda='0'):
    salida = {c: '0,0,0' for c in S.LISTAS}
    salida.update(ID=str(identificador), Filename='bkgspace', Title='Prueba SPACE',
                  Singer='Fixture', Difficulty='10' if identificador == 1 else '6',
                  BPM=str(bpm), StartDelayTime='4', Second='100',
                  Length='16,%d,16' % largo_space, KeyPatternID='4,4,4',
                  MissionID1='157,1,157', MissionID2='0,%s,0' % segunda,
                  MissionDanceID='511,511,511', MissionSuccessDanceID='611,611,611',
                  MissionFailDanceID='201,201,201', MissionCameraID='101,0,0',
                  DanceCameraID='111,111,241')
    return salida


class AdopcionSpaceTest(unittest.TestCase):
    def test_matriz_adoptar_guardar_recargar_y_regenerar_conserva_space(self):
        # 2 largos × 2 estados de segunda tanda × 3 velocidades = 12 casos.
        for largo in (16, 32):
            for segunda in ('0', '1'):
                for bpm in (120, 240, 60):
                    with self.subTest(largo=largo, segunda=segunda, bpm=bpm):
                        origen = fila(1, 120, largo, segunda)
                        destino = fila(2, bpm)
                        nuevo, resumen = adoptar_version(origen, destino, estrellas=6)
                        cfg = dict(version=1, origen=copy.deepcopy(origen), inicio=4.,
                                   descansos=copy.deepcopy(resumen['descansos']))
                        antes = copy.deepcopy((origen, destino, cfg))
                        with tempfile.TemporaryDirectory() as carpeta:
                            S.guardar_configuracion(carpeta, 'bkgspace:2', [], inicio=4.,
                                                     adopcion=cfg)
                            recargada = S.cargar_configuracion(carpeta, 'bkgspace:2')
                        generado, _ = N.generar(
                            destino, dict(bpm=120., dur=100., fin_beat=100.), 6, 4.,
                            bpm=bpm, adopcion=recargada['adopcion'])
                        for campo in S.LISTAS + ('StartDelayTime',):
                            self.assertEqual(generado[campo], nuevo[campo], campo)
                        self.assertEqual(generado['MissionID1'], '157,1,157')
                        segunda_cabe = segunda == '1' and not (largo == 16 and bpm == 60)
                        self.assertEqual(generado['MissionID2'].split(',')[1],
                                         '1' if segunda_cabe else '0')
                        golpes = N.golpes(generado, 4., bpm)
                        espacios = [g for g in golpes if g['mision'] == 1]
                        self.assertEqual(len(espacios), 8 if segunda_cabe else 4)
                        self.assertTrue(all(g['space'] == 1 and g['flechas'] == 0
                                            for g in espacios))
                        self.assertEqual([g['tiempo'] for g in espacios],
                                         list(range(len(espacios))))
                        self.assertEqual(espacios[0]['t'], 12.)
                        self.assertEqual((origen, destino, cfg), antes)

    def test_space_y_descanso_explicito_son_distintos_y_no_se_superponen(self):
        for bpm in (120, 240):
            with self.subTest(bpm=bpm):
                origen = fila(1, 120, largo_space=32, segunda='1')
                destino = fila(2, bpm)
                descanso = dict(tipo='descanso', desde=20., hasta=28.)
                cfg = dict(version=1, origen=origen, inicio=4., descansos=[descanso])
                generado, _ = N.generar(
                    destino, dict(bpm=120., dur=100.), 6, 4., bpm=bpm, adopcion=cfg)
                golpes = N.golpes(generado, 4., bpm)
                espacios = [g for g in golpes if g['mision'] == 1]
                self.assertEqual(len(espacios), 8)
                self.assertTrue(all(g['space'] == 1 for g in espacios))
                self.assertFalse(any(20. <= g['t'] < 28. for g in golpes))
                comprobacion = N.resumen_descansos(dict(destino, **generado), [descanso])
                self.assertEqual(comprobacion['entradas_en_descanso'], 0)

    def test_previo_entrega_los_cuatro_u_ocho_space_a_la_mezcla(self):
        with tempfile.TemporaryDirectory() as carpeta:
            audio = Path(carpeta) / 'fixture.ogg'
            audio.touch()
            for segunda, cantidad in (('0', 4), ('1', 8)):
                with self.subTest(segunda=segunda):
                    origen = fila(1, 120, segunda=segunda)
                    destino = fila(2, 120)
                    cfg = dict(version=1, origen=copy.deepcopy(origen), inicio=4.,
                               descansos=[])
                    antes = copy.deepcopy((origen, destino, cfg))
                    with mock.patch.object(N, 'armar_escucha') as mezclar:
                        _, informe = N.previo(
                            destino, dict(bpm=120., dur=100., ogg=audio), 6, 4.,
                            bpm=120., desde=12., segundos=4., musica=False,
                            salida=Path(carpeta) / 'previo.wav', adopcion=cfg)
                    marcas = mezclar.call_args.args[1]
                    espacios = [g for g in marcas if g['mision'] == 1]
                    self.assertEqual(len(espacios), cantidad)
                    self.assertTrue(all(g['space'] == 1 and g['flechas'] == 0
                                        for g in espacios))
                    self.assertEqual(informe['space'], cantidad)
                    self.assertEqual(informe['flechas'], 0)
                    self.assertEqual((origen, destino, cfg), antes)


if __name__ == '__main__':
    unittest.main()
