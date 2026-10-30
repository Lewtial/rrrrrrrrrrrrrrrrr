"""Lectura de comprobación del musictable y diagnóstico de descansos, sin EXE."""
import copy
import csv
from contextlib import ExitStack
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nucleo as N
import musictable_tool as MT


def fila(identificador="2001"):
    datos = {columna: "0" for columna, _ in N.COLUMNAS}
    datos.update(ID=identificador, Title="Tema " + identificador, Singer="Prueba",
                 Difficulty="3", BPM="60", Filename="bkg" + identificador,
                 SoundSourceSN=identificador, Genre="Dance", Second="58",
                 StartDelayTime="10", CutOff="30000")
    for columna in N.LISTAS:
        datos[columna] = "0,0,0"
    datos.update(Length="16,16,16", KeyPatternID="4,4,4", MissionID1="157,157,157",
                 MissionID2="0,313,0", MissionDanceID="511,511,511",
                 MissionSuccessDanceID="611,611,611", MissionFailDanceID="201,201,201",
                 MissionCameraID="101,0,0", DanceCameraID="0,111,241")
    return datos


def descanso(desde, hasta):
    return dict(tipo="descanso", desde=desde, hasta=hasta)


class GuardadoVerificadoTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.carpeta = Path(temporal.name)
        self.ruta = self.carpeta / "musictable.slk.spak"
        self.respaldos = self.carpeta / "respaldos"
        self.respaldos.mkdir()
        self.exe = self.carpeta / "cliente.exe"
        self.exe.write_bytes(b"EXE ficticio, nunca se ejecuta")
        self.original = b"QPACK original\x00\xff\x00, debe restaurarse byte por byte"
        self.escrito = b"QPACK nuevo, escrito por el importador simulado"
        self.ruta.write_bytes(self.original)
        self.tabla = N.Tabla.__new__(N.Tabla)
        self.tabla.cab = [c for c, _ in N.COLUMNAS]
        self.tabla.cab_juego = ["Genre " if c == "Genre" else c for c in self.tabla.cab]
        self.tabla.filas = [fila("2001"), fila("2002")]
        self.tabla.csv = self.carpeta / "intencion.csv"
        self.filas_pendientes = copy.deepcopy(self.tabla.filas)
        self.transformar = lambda cabecera, filas: (cabecera, filas)
        self.ruta_verificacion = None
        self.csv_antes_de_exportar = None
        contexto = ExitStack()
        self.addCleanup(contexto.close)
        contexto.enter_context(mock.patch.object(N, "TABLA", self.ruta))
        contexto.enter_context(mock.patch.object(N, "RESPALDOS", self.respaldos))
        contexto.enter_context(mock.patch.object(N, "EXE", self.exe))
        self.tabla.huella = self.tabla._huella()
        self.huella_original = self.tabla.huella
        self.importar = contexto.enter_context(mock.patch.object(
            MT, "importar", side_effect=self._importar))
        self.exportar = contexto.enter_context(mock.patch.object(
            MT, "exportar", side_effect=self._exportar))

    def _importar(self, exe, entrada_csv, salida_spak, molde_spak):
        self.assertEqual(Path(exe), self.exe)
        self.assertEqual(Path(entrada_csv), self.tabla.csv)
        self.assertEqual(Path(salida_spak), self.ruta)
        self.assertEqual(Path(molde_spak).read_bytes(), self.original)
        self.ruta.write_bytes(self.escrito)

    def _exportar(self, exe, origen_spak, salida_csv):
        self.assertEqual(Path(exe), self.exe)
        self.assertEqual(Path(origen_spak), self.ruta)
        self.assertEqual(self.ruta.read_bytes(), self.escrito)
        self.ruta_verificacion = Path(salida_csv)
        self.assertNotEqual(self.ruta_verificacion, self.tabla.csv)
        self.csv_antes_de_exportar = self.tabla.csv.read_bytes()
        with self.tabla.csv.open(encoding="utf-8-sig", newline="") as archivo:
            contenido = list(csv.reader(archivo, delimiter=";"))
        cabecera, filas = self.transformar(contenido[0], contenido[1:])
        with self.ruta_verificacion.open("w", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.writer(archivo, delimiter=";")
            escritor.writerow(cabecera)
            escritor.writerows(filas)

    def comprobar_restauracion(self):
        self.assertEqual(self.ruta.read_bytes(), self.original)
        self.assertEqual(self.tabla.filas, self.filas_pendientes)
        self.assertEqual(self.tabla.huella, self.huella_original)
        self.assertFalse((getattr(self.tabla, "verificacion_envio", None) or {})
                         .get("correcto", False))
        for respaldo in self.respaldos.iterdir():
            self.assertEqual(respaldo.read_bytes(), self.original)
        if self.ruta_verificacion is not None:
            self.assertFalse(self.ruta_verificacion.exists())

    def test_guarda_verifica_todos_los_campos_y_publica_evidencia_del_archivo_real(self):
        self.assertEqual(len(self.tabla.cab_juego), 23)
        respaldo = self.tabla.guardar("prueba")
        self.assertEqual(respaldo.parent, self.respaldos)
        self.assertEqual(respaldo.read_bytes(), self.original)
        self.assertEqual(self.ruta.read_bytes(), self.escrito)
        self.assertEqual(self.tabla.filas, self.filas_pendientes)
        self.assertEqual(self.tabla.huella, self.tabla._huella())
        esperada = dict(filas=2, campos=23, ruta=str(self.ruta),
                        sha256=hashlib.sha256(self.escrito).hexdigest(), correcto=True)
        self.assertEqual({c: self.tabla.verificacion_envio[c] for c in esperada}, esperada)
        self.importar.assert_called_once()
        self.exportar.assert_called_once()
        self.assertEqual(self.tabla.csv.read_bytes(), self.csv_antes_de_exportar)
        self.assertFalse(self.ruta_verificacion.exists())
        with self.tabla.csv.open(encoding="utf-8-sig", newline="") as archivo:
            cabecera = next(csv.reader(archivo, delimiter=";"))
        self.assertEqual(cabecera, self.tabla.cab_juego)
        self.assertIn("Genre ", cabecera)

    def test_una_discrepancia_en_cualquiera_de_las_23_columnas_restaura_respaldo(self):
        for indice, columna in enumerate(self.tabla.cab_juego):
            with self.subTest(columna=columna):
                def cambiar(cabecera, filas, indice=indice):
                    filas[0][indice] = "valor perdido al importar"
                    return cabecera, filas
                self.transformar = cambiar
                with self.assertRaisesRegex(RuntimeError, ".+"):
                    self.tabla.guardar("prueba")
                self.comprobar_restauracion()

    def test_rechaza_cabecera_recortada_en_lugar_de_aceptar_Genre_sin_espacio(self):
        def recortar(cabecera, filas):
            return [c.strip() for c in cabecera], filas
        self.transformar = recortar
        with self.assertRaises(RuntimeError):
            self.tabla.guardar("prueba")
        self.comprobar_restauracion()

    def test_rechaza_cabeceras_reordenadas_aunque_las_celdas_las_acompanen(self):
        def reordenar(cabecera, filas):
            cabecera[1], cabecera[2] = cabecera[2], cabecera[1]
            for valores in filas:
                valores[1], valores[2] = valores[2], valores[1]
            return cabecera, filas
        self.transformar = reordenar
        with self.assertRaises(RuntimeError):
            self.tabla.guardar("prueba")
        self.comprobar_restauracion()

    def test_rechaza_columna_omitida_en_cabecera_y_filas(self):
        self.transformar = lambda cabecera, filas: (cabecera[:-1], [f[:-1] for f in filas])
        with self.assertRaises(RuntimeError):
            self.tabla.guardar("prueba")
        self.comprobar_restauracion()

    def test_rechaza_fila_omitida(self):
        self.transformar = lambda cabecera, filas: (cabecera, filas[:-1])
        with self.assertRaises(RuntimeError):
            self.tabla.guardar("prueba")
        self.comprobar_restauracion()

    def test_rechaza_fila_agregada_o_duplicada(self):
        self.transformar = lambda cabecera, filas: (cabecera, filas + [list(filas[0])])
        with self.assertRaises(RuntimeError):
            self.tabla.guardar("prueba")
        self.comprobar_restauracion()

    def test_rechaza_filas_reordenadas_por_el_importador(self):
        self.transformar = lambda cabecera, filas: (cabecera, list(reversed(filas)))
        with self.assertRaises(RuntimeError):
            self.tabla.guardar("prueba")
        self.comprobar_restauracion()

    def test_error_al_leer_el_archivo_recien_escrito_restaura_respaldo(self):
        self.exportar.side_effect = OSError("fallo de lectura simulado")
        with self.assertRaisesRegex(RuntimeError, ".+"):
            self.tabla.guardar("prueba")
        self.comprobar_restauracion()

    def test_csv_de_verificacion_vacio_no_confirma_el_envio(self):
        def vacio(exe, origen_spak, salida_csv):
            self.ruta_verificacion = Path(salida_csv)
            self.ruta_verificacion.write_bytes(b"")
        self.exportar.side_effect = vacio
        with self.assertRaises(RuntimeError):
            self.tabla.guardar("prueba")
        self.comprobar_restauracion()


class ResumenDescansosTest(unittest.TestCase):
    def setUp(self):
        self.fila = fila()

    def resumen(self, secciones, datos=None):
        return N.resumen_descansos(self.fila if datos is None else datos, secciones)

    def test_sin_descansos_no_reporta_entradas(self):
        self.assertEqual(self.resumen([]),
                         dict(tramos=0, entradas_en_descanso=0, primer_conflicto=None))

    def test_ignora_secciones_de_patrones_al_contar_tramos(self):
        patron = dict(desde=0, hasta=60, tipo="patron", primera=[1, 1, 1, 1],
                      segunda=None, bolsa=4)
        self.assertEqual(self.resumen([patron]),
                         dict(tramos=0, entradas_en_descanso=0, primer_conflicto=None))

    def test_descanso_inicial_detecta_entrada_y_devuelve_ventana_completa(self):
        self.assertEqual(self.resumen([descanso(10, 14)]),
                         dict(tramos=1, entradas_en_descanso=1,
                              primer_conflicto=dict(mision=1, desde=10.0, hasta=14.0,
                                                    descanso_desde=10.0,
                                                    descanso_hasta=14.0)))

    def test_descanso_en_la_segunda_tanda_tambien_detecta_la_mision(self):
        self.assertEqual(self.resumen([descanso(31, 32)]),
                         dict(tramos=1, entradas_en_descanso=1,
                              primer_conflicto=dict(mision=2, desde=26.0, hasta=34.0,
                                                    descanso_desde=31.0,
                                                    descanso_hasta=32.0)))

    def test_tanda_de_cuatro_SPACE_tambien_es_una_entrada(self):
        datos = dict(self.fila, MissionID1="1,157,157")
        self.assertEqual(self.resumen([descanso(10, 14)], datos)["entradas_en_descanso"], 1)
        datos = dict(self.fila, MissionID2="0,1,0")
        self.assertEqual(self.resumen([descanso(31, 32)], datos)["entradas_en_descanso"], 1)

    def test_limites_son_semiabiertos_y_no_cuentan_solo_contacto(self):
        for desde, hasta in ((0, 10), (14, 26), (34, 42), (46, 60)):
            with self.subTest(desde=desde, hasta=hasta):
                self.assertEqual(self.resumen([descanso(desde, hasta)]),
                                 dict(tramos=1, entradas_en_descanso=0,
                                      primer_conflicto=None))

    def test_mision_que_solapa_varios_descansos_se_cuenta_una_sola_vez(self):
        resumen = self.resumen([descanso(10, 13), descanso(11, 14)])
        self.assertEqual(resumen["tramos"], 2)
        self.assertEqual(resumen["entradas_en_descanso"], 1)
        self.assertEqual(resumen["primer_conflicto"],
                         dict(mision=1, desde=10.0, hasta=14.0,
                              descanso_desde=10.0, descanso_hasta=13.0))

    def test_tramo_largo_cuenta_las_tres_misiones_y_no_los_casilleros(self):
        resumen = self.resumen([descanso(0, 80)])
        self.assertEqual(resumen["entradas_en_descanso"], 3)
        self.assertEqual(resumen["primer_conflicto"]["mision"], 1)

    def test_respeta_bpm_y_arranque_guardados_en_la_fila(self):
        datos = dict(self.fila, BPM="120", StartDelayTime="5")
        resumen = self.resumen([descanso(15.5, 16)], datos)
        self.assertEqual(resumen["primer_conflicto"],
                         dict(mision=2, desde=13.0, hasta=17.0,
                              descanso_desde=15.5, descanso_hasta=16.0))

    def test_no_modifica_fila_ni_secciones(self):
        secciones = [descanso(10, 14)]
        originales = copy.deepcopy((self.fila, secciones))
        self.resumen(secciones)
        self.assertEqual((self.fila, secciones), originales)

    def test_rechaza_datos_temporales_corruptos(self):
        invalidos = [("BPM", x) for x in ("nan", "inf", "0", "-1", "no")]
        invalidos += [("StartDelayTime", x) for x in ("nan", "inf", "-1", "no")]
        invalidos += [("Length", x) for x in ("", "16,no,16", "16,nan,16", "16,0,16")]
        for campo, valor in invalidos:
            with self.subTest(campo=campo, valor=valor), self.assertRaises(ValueError):
                self.resumen([descanso(10, 14)], dict(self.fila, **{campo: valor}))

    def test_rechaza_secciones_corruptas(self):
        for secciones in (None, {}, [descanso(10, 10)], [descanso(math.nan, 14)]):
            with self.subTest(secciones=secciones), self.assertRaises(ValueError):
                self.resumen(secciones)


if __name__ == "__main__":
    unittest.main()
