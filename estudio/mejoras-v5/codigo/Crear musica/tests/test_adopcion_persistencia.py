"""Snapshots de adopción: migración, aislamiento y guardado atómico."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import secciones as S


def fuente():
    fila = {c: '0,0' for c in S.LISTAS}
    fila.update(ID='100', Filename='bkgprueba', Title='Hypno', Difficulty='10',
                BPM='240', StartDelayTime='4', Second='64', Length='16,32',
                KeyPatternID='4,1', MissionID1='469,387', MissionID2='0,313')
    return fila


def adopcion():
    return dict(version=1, origen=fuente(), inicio=4.,
                descansos=[dict(tipo='descanso', desde=12., hasta=16.)])


class PersistenciaAdopcionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.carpeta = Path(self.tmp.name)
        self.ruta = self.carpeta / S.ARCHIVO
        self.clave = 'bkgprueba:200'

    def guardar(self, **kwargs):
        return S.guardar_configuracion(self.carpeta, self.clave, [], inicio=4., **kwargs)

    def test_sin_adopcion_devuelve_none(self):
        self.assertEqual(S.cargar_configuracion(self.carpeta, self.clave),
                         dict(secciones=[], inicio=None, misiones=[], adopcion=None))

    def test_snapshot_roundtrip_es_independiente_de_argumentos_y_lecturas(self):
        cfg = adopcion()
        original = copy.deepcopy(cfg)
        self.guardar(adopcion=cfg)
        cfg['origen']['MissionID1'] = '1,1'
        cargada = S.cargar_configuracion(self.carpeta, self.clave)
        self.assertEqual(cargada['adopcion'], original)
        cargada['adopcion']['origen']['Title'] = 'No cambiar'
        self.assertEqual(S.cargar_configuracion(self.carpeta, self.clave)['adopcion'], original)

    def test_omitir_conserva_none_borra_y_no_toca_otras_filas(self):
        self.guardar(adopcion=adopcion())
        S.guardar_configuracion(self.carpeta, 'bkgprueba:300', [], adopcion=adopcion())
        self.guardar(misiones=[])
        self.assertIsNotNone(S.cargar_configuracion(self.carpeta, self.clave)['adopcion'])
        self.guardar(adopcion=None)
        self.assertIsNone(S.cargar_configuracion(self.carpeta, self.clave)['adopcion'])
        self.assertIsNotNone(S.cargar_configuracion(self.carpeta, 'bkgprueba:300')['adopcion'])

    def test_lee_v1_y_v2_y_migra_a_v3_sin_perder_secciones(self):
        for version in (1, 2):
            with self.subTest(version=version):
                secciones = [dict(tipo='descanso', desde=10., hasta=12.)]
                self.ruta.write_text(json.dumps(dict(version=version, charts={self.clave:dict(secciones=secciones, inicio=4)})))
                cfg = S.cargar_configuracion(self.carpeta, self.clave)
                self.assertEqual(cfg, dict(secciones=secciones, inicio=4., misiones=[], adopcion=None))
                self.guardar(adopcion=adopcion())
                self.assertEqual(json.loads(self.ruta.read_text())['version'], 3)

    def test_otro_bkg_se_rechaza_sin_reemplazar_archivo(self):
        self.guardar(adopcion=adopcion())
        antes = self.ruta.read_bytes()
        invalida = adopcion()
        invalida['origen']['Filename'] = 'bkgotro'
        with self.assertRaisesRegex(ValueError, 'otro archivo bkg'):
            self.guardar(adopcion=invalida)
        self.assertEqual(self.ruta.read_bytes(), antes)

    def test_adopcion_corrupta_al_leer_frena_guardado_y_conserva_original(self):
        self.guardar(adopcion=adopcion())
        datos = json.loads(self.ruta.read_text())
        datos['charts'][self.clave]['adopcion']['origen']['BPM'] = 'NaN'
        self.ruta.write_text(json.dumps(datos))
        antes = self.ruta.read_bytes()
        with self.assertRaisesRegex(ValueError, 'No pude leer'):
            self.guardar(adopcion=None)
        self.assertEqual(self.ruta.read_bytes(), antes)

    def test_valida_listas_tandas_bolsa_y_finitud_sin_tocar_fuente(self):
        casos = [('Length','16'), ('Length','2,32'), ('MissionID2','313,0'),
                 ('KeyPatternID','5,1'), ('MissionID1','626,1'), ('MissionID1','0,1'),
                 ('BPM','inf'), ('StartDelayTime','-1')]
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                cfg = adopcion()
                cfg['origen'][campo] = valor
                if campo == 'MissionID2': cfg['origen']['Length'] = '8,32'
                antes = copy.deepcopy(cfg)
                with self.assertRaises(ValueError): S.validar_adopcion(cfg)
                self.assertEqual(cfg, antes)

    def test_solo_descansos_y_version_snapshot_conocida(self):
        for cambio in (dict(version=2), dict(version=True), dict(inicio=float('nan')),
                       dict(descansos=[dict(tipo='patron',desde=0,hasta=4,primera=[1]*4,segunda=None,bolsa=4)])):
            with self.subTest(cambio=cambio):
                with self.assertRaises(ValueError): S.validar_adopcion(dict(adopcion(), **cambio))

    def test_error_de_reemplazo_atomico_conserva_archivo_y_limpia_temporal(self):
        self.guardar(adopcion=adopcion())
        antes = self.ruta.read_bytes()
        with mock.patch.object(S.os, 'replace', side_effect=OSError('fallo controlado')):
            with self.assertRaises(OSError): self.guardar(adopcion=None)
        self.assertEqual(self.ruta.read_bytes(), antes)
        self.assertEqual([p.name for p in self.carpeta.iterdir()], [S.ARCHIVO])


if __name__ == '__main__': unittest.main()
