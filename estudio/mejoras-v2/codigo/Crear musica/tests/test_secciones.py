import copy
from contextlib import ExitStack
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import wave


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from secciones import aplicar_secciones, cargar_configuracion, guardar_configuracion
import nucleo as N


LISTAS = (
    "Length", "KeyPatternID", "KeySoundID", "MissionID1", "MissionID2",
    "MissionDanceID", "MissionSuccessDanceID", "MissionFailDanceID",
    "MissionCameraID", "DanceCameraID",
)


def chart(largos=(16, 16, 16, 16, 16), segundas=()):
    n = len(largos)
    salida = {col: ",".join(["0"] * n) for col in LISTAS}
    salida.update({
        "Length": ",".join(map(str, largos)),
        "KeyPatternID": ",".join(["4"] * n),
        "MissionID1": ",".join(str(157 + i) for i in range(n)),
        "MissionID2": ",".join("313" if i in segundas else "0" for i in range(n)),
        "MissionDanceID": ",".join(["511"] * n),
        "MissionSuccessDanceID": ",".join(["611"] * n),
        "MissionFailDanceID": ",".join(str(201 + i) for i in range(n)),
        "MissionCameraID": ",".join(["101"] + ["0"] * (n - 1)),
        "DanceCameraID": ",".join(["111"] * (n - 1) + ["241"]),
    })
    return salida


def patron(desde, hasta, primera=(1, 1, 1, 1), segunda=None, bolsa=4):
    return dict(desde=desde, hasta=hasta, tipo="patron", primera=list(primera),
                segunda=None if segunda is None else list(segunda), bolsa=bolsa)


def descanso(desde, hasta):
    return dict(desde=desde, hasta=hasta, tipo="descanso")


def reemplazo(tiempo, primera=(3, 3, 3, 3), segunda=None, bolsa=1):
    return dict(tipo="reemplazar", tiempo=tiempo, primera=list(primera),
                segunda=None if segunda is None else list(segunda), bolsa=bolsa)


def inicios(listas, inicio=10.0, bpm=60.0):
    t = float(listas.get("StartDelayTime", inicio))
    salida = []
    for largo in listas["Length"].split(","):
        salida.append(t)
        t += float(largo) * 60.0 / bpm
    return salida, t


class SeccionesTest(unittest.TestCase):
    def setUp(self):
        self.fila = {"ID": "2001", "Filename": "bkg2001", "Difficulty": "1",
                     "BPM": "60", "StartDelayTime": "10"}
        self.original = chart()

    def aplicar(self, secciones, listas=None, inicio=10.0, bpm=60.0):
        return aplicar_secciones(self.fila, self.original if listas is None else listas,
                                 inicio, bpm, secciones)

    def comprobar_listas_alineadas(self, resultado):
        longitudes = {len(resultado[c].split(",")) for c in LISTAS}
        self.assertEqual(len(longitudes), 1)
        self.assertEqual(resultado["MissionCameraID"].split(",")[0], "101")
        self.assertEqual(resultado["DanceCameraID"].split(",")[-1], "241")

    def test_sin_secciones_conserva_todos_los_valores(self):
        for vacio in ([], ()):
            with self.subTest(vacio=vacio):
                self.assertEqual(self.aplicar(vacio), self.original)

    def test_no_modifica_los_argumentos(self):
        secciones = [patron(10, 30), descanso(42, 46)]
        antes = copy.deepcopy((self.fila, self.original, secciones))
        self.aplicar(secciones)
        self.assertEqual((self.fila, self.original, secciones), antes)

    def test_patron_usa_inicio_y_limites_semiabiertos(self):
        resultado = self.aplicar([patron(26, 42, (2, 0, 1, 0), (0, 1, 0, 1), 1)])
        self.assertEqual(resultado["MissionID1"].split(","), ["157", "256", "159", "160", "161"])
        self.assertEqual(resultado["MissionID2"].split(","), ["0", "27", "0", "0", "0"])
        self.assertEqual(resultado["KeyPatternID"].split(","), ["4", "1", "4", "4", "4"])
        self.assertEqual(inicios(resultado)[0], [10, 26, 42, 58, 74])

    def test_ultimo_patron_gana_sin_limites_automaticos_de_softnyx(self):
        resultado = self.aplicar([patron(10, 43, (1, 1, 1, 1), bolsa=1),
                                  patron(26, 43, (3, 3, 3, 3), bolsa=2)])
        self.assertEqual(resultado["MissionID1"].split(",")[:3], ["157", "469", "469"])
        self.assertEqual(resultado["KeyPatternID"].split(",")[:3], ["1", "2", "2"])

    def test_none_desactiva_segunda_tanda(self):
        resultado = self.aplicar([patron(26, 27)], chart(segundas=(1,)))
        self.assertEqual(resultado["MissionID2"].split(",")[1], "0")

    def test_descanso_intermedio_conserva_inicios_y_flechas_supervivientes(self):
        resultado = self.aplicar([descanso(26, 30)])
        self.assertEqual(inicios(resultado), ([10, 42, 58, 74], 90))
        self.assertEqual(resultado["Length"], "32,16,16,16")
        self.assertEqual(resultado["MissionID1"], "157,159,160,161")
        self.assertEqual(resultado["MissionFailDanceID"], "201,203,204,205")
        self.comprobar_listas_alineadas(resultado)

    def test_descanso_inicial_desplaza_arranque_sin_mover_las_que_quedan(self):
        resultado = self.aplicar([descanso(10, 14)])
        self.assertEqual(float(resultado["StartDelayTime"]), 26)
        self.assertEqual(inicios(resultado), ([26, 42, 58, 74], 90))
        self.assertEqual(resultado["MissionID1"], "158,159,160,161")
        self.comprobar_listas_alineadas(resultado)

    def test_descanso_final_conserva_fin_chart(self):
        resultado = self.aplicar([descanso(58, 90)])
        self.assertEqual(inicios(resultado), ([10, 26, 42], 90))
        self.assertEqual(resultado["Length"], "16,16,48")
        self.comprobar_listas_alineadas(resultado)

    def test_descanso_mayor_a_96_tiempos_no_reintroduce_misiones(self):
        resultado = self.aplicar([descanso(26, 154)], chart((16,) * 10))
        self.assertEqual(inicios(resultado), ([10, 154], 170))
        self.assertEqual(resultado["Length"], "144,16")
        self.assertEqual(len(resultado["MissionID1"].split(",")), 2)
        self.comprobar_listas_alineadas(resultado)

    def test_descanso_interseca_ventana_aunque_inicio_quede_fuera(self):
        resultado = self.aplicar([descanso(28, 29)])
        self.assertEqual(inicios(resultado)[0], [10, 42, 58, 74])

    def test_fin_de_ventana_no_cuenta_como_solape(self):
        resultado = self.aplicar([descanso(30, 31)])
        self.assertEqual(resultado, self.original)

    def test_descanso_contempla_los_otros_cuatro_beats_de_segunda_tanda(self):
        resultado = self.aplicar([descanso(31, 32)], chart(segundas=(1,)))
        self.assertEqual(inicios(resultado)[0], [10, 42, 58, 74])

    def test_descanso_considera_segunda_tanda_final_que_agrega_el_patron(self):
        resultado = self.aplicar([patron(26, 27, segunda=(1, 1, 1, 1)), descanso(31, 32)])
        self.assertEqual(inicios(resultado)[0], [10, 42, 58, 74])

    def test_descanso_considera_segunda_tanda_final_que_quita_el_patron(self):
        resultado = self.aplicar([patron(26, 27), descanso(31, 32)], chart(segundas=(1,)))
        self.assertEqual(inicios(resultado)[0], [10, 26, 42, 58, 74])
        self.assertEqual(resultado["MissionID2"].split(",")[1], "0")

    def test_descanso_siempre_tiene_prioridad_sobre_patrones(self):
        for secciones in ([descanso(26, 30), patron(10, 90)],
                          [patron(10, 90), descanso(26, 30)]):
            with self.subTest(secciones=secciones):
                resultado = self.aplicar(secciones)
                self.assertEqual(inicios(resultado)[0], [10, 42, 58, 74])
                self.assertEqual(resultado["MissionID1"], "157,157,157,157")

    def test_descanso_ignora_campos_de_patrones(self):
        seccion = descanso(26, 30)
        seccion.update(primera="irrelevante", segunda="irrelevante", bolsa=999)
        self.assertEqual(self.aplicar([seccion]), self.aplicar([descanso(26, 30)]))

    def test_bpm_convierte_ventanas_y_largos_a_segundos(self):
        resultado = self.aplicar([descanso(18, 20)], bpm=120)
        self.assertEqual(inicios(resultado, bpm=120), ([10, 26, 34, 42], 50))
        self.assertEqual(resultado["Length"], "32,16,16,16")

    def test_rechaza_descanso_que_elimina_todo(self):
        with self.assertRaisesRegex(ValueError, ".+"):
            self.aplicar([descanso(0, 100)])

    def test_segunda_tanda_explicita_no_cabe_en_mision_corta(self):
        with self.assertRaisesRegex(ValueError, ".+"):
            self.aplicar([patron(10, 11, segunda=(1, 1, 1, 1))], chart((8, 16, 16)))

    def test_patron_sin_segunda_tanda_es_valido_en_mision_corta(self):
        resultado = self.aplicar([patron(10, 11)], chart((8, 16, 16)))
        self.assertEqual(resultado["MissionID1"].split(",")[0], "157")
        self.assertEqual(resultado["MissionID2"].split(",")[0], "0")

    def test_rechaza_intervalos_y_numeros_invalidos(self):
        malas = [descanso(10, 10), descanso(20, 10), descanso(-1, 10),
                 descanso(math.nan, 20), descanso(10, math.inf),
                 descanso("no", 20), descanso(True, 20)]
        for seccion in malas:
            with self.subTest(seccion=seccion), self.assertRaises(ValueError):
                self.aplicar([seccion])

    def test_rechaza_patrones_y_bolsas_invalidos(self):
        malas = []
        for valor in ([1, 1, 1], [1, 1, 1, 4], [1, 1, 1, -1],
                      [1, 1, 1, 1.5], [1, 1, 1, True], "1111"):
            s = patron(10, 20)
            s["primera"] = valor
            malas.append(s)
        for valor in (0, 5, True, 1.5, "cuatro"):
            s = patron(10, 20)
            s["bolsa"] = valor
            malas.append(s)
        for valor in ([1], [1, 2, 3, 4], "1234"):
            s = patron(10, 20)
            s["segunda"] = valor
            malas.append(s)
        for seccion in malas:
            with self.subTest(seccion=seccion), self.assertRaises(ValueError):
                self.aplicar([seccion])

    def test_rechaza_estructura_de_secciones_malformada(self):
        malas = ["no", {}, [None], [dict(desde=10, hasta=20, tipo="otro")],
                 [dict(desde=10, hasta=20, tipo="patron")],
                 [dict(hasta=20, tipo="descanso")]]
        for secciones in malas:
            with self.subTest(secciones=secciones), self.assertRaises(ValueError):
                self.aplicar(secciones)


class PersistenciaSeccionesTest(unittest.TestCase):
    def test_archivo_inexistente_no_tiene_configuracion(self):
        with tempfile.TemporaryDirectory() as carpeta:
            self.assertEqual(cargar_configuracion(carpeta, "bkg2001:2001"),
                             {"secciones": [], "inicio": None, "misiones": []})

    def test_guardar_y_recargar_por_fila_conserva_otras_claves(self):
        with tempfile.TemporaryDirectory() as carpeta:
            primera = [patron(10, 30, (2, 0, 2, 0), segunda=(1, 1, 1, 1), bolsa=1)]
            otra = [descanso(42, 50)]
            guardar_configuracion(carpeta, "bkg2001:2001", primera, inicio=10.5)
            guardar_configuracion(carpeta, "bkg2001:2002", otra)
            self.assertEqual(cargar_configuracion(carpeta, "bkg2001:2001"),
                             {"secciones": primera, "inicio": 10.5, "misiones": []})
            self.assertEqual(cargar_configuracion(carpeta, "bkg2001:2002"),
                             {"secciones": otra, "inicio": None, "misiones": []})
            guardar_configuracion(carpeta, "bkg2001:2001", [])
            self.assertEqual(cargar_configuracion(carpeta, "bkg2001:2001"),
                             {"secciones": [], "inicio": None, "misiones": []})
            self.assertEqual(cargar_configuracion(carpeta, "bkg2001:2002"),
                             {"secciones": otra, "inicio": None, "misiones": []})
            ruta = Path(carpeta) / "configuracion_secciones.json"
            contenido = json.loads(ruta.read_text(encoding="utf-8"))
            self.assertIn("version", contenido)
            self.assertEqual(list(Path(carpeta).iterdir()), [ruta])

    def test_lectura_corrupta_falla_claro_y_no_se_pisa_al_guardar(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "configuracion_secciones.json"
            ruta.write_text("{ incompleto", encoding="utf-8")
            for operacion in (lambda: cargar_configuracion(carpeta, "bkg1:1"),
                              lambda: guardar_configuracion(carpeta, "bkg1:1", [])):
                with self.subTest(operacion=operacion), self.assertRaisesRegex(ValueError, ".+"):
                    operacion()
            self.assertEqual(ruta.read_text(encoding="utf-8"), "{ incompleto")

    def test_guardado_invalido_no_destruye_configuracion_anterior(self):
        with tempfile.TemporaryDirectory() as carpeta:
            valida = [descanso(20, 30)]
            guardar_configuracion(carpeta, "bkg1:1", valida)
            ruta = Path(carpeta) / "configuracion_secciones.json"
            antes = ruta.read_bytes()
            with self.assertRaises(ValueError):
                guardar_configuracion(carpeta, "bkg1:1", [descanso(20, math.nan)])
            self.assertEqual(ruta.read_bytes(), antes)
            self.assertEqual(cargar_configuracion(carpeta, "bkg1:1"),
                             {"secciones": valida, "inicio": None, "misiones": []})

    def test_rechaza_ancla_invalida_sin_pisar_archivo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            guardar_configuracion(carpeta, "bkg1:1", [], inicio=0)
            ruta = Path(carpeta) / "configuracion_secciones.json"
            antes = ruta.read_bytes()
            for inicio in (-1, math.nan, math.inf, True, "ayer"):
                with self.subTest(inicio=inicio), self.assertRaises(ValueError):
                    guardar_configuracion(carpeta, "bkg1:1", [], inicio=inicio)
                self.assertEqual(ruta.read_bytes(), antes)

    def test_lee_version1_sin_cambiar_el_archivo_y_migra_al_guardar(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "configuracion_secciones.json"
            secciones = [descanso(20, 30)]
            anterior = {"version": 1, "charts": {
                "bkg1:1": {"secciones": secciones, "inicio": 10.5}}}
            ruta.write_text(json.dumps(anterior), encoding="utf-8")
            contenido_original = ruta.read_bytes()
            self.assertEqual(cargar_configuracion(carpeta, "bkg1:1"),
                             dict(secciones=secciones, inicio=10.5, misiones=[]))
            self.assertEqual(ruta.read_bytes(), contenido_original)
            guardar_configuracion(carpeta, "bkg2:2", [], inicio=0,
                                  misiones=[reemplazo(16)])
            actualizado = json.loads(ruta.read_text(encoding="utf-8"))
            self.assertEqual(actualizado["version"], 2)
            self.assertEqual(cargar_configuracion(carpeta, "bkg1:1"),
                             dict(secciones=secciones, inicio=10.5, misiones=[]))
            self.assertEqual(cargar_configuracion(carpeta, "bkg2:2")["misiones"],
                             [reemplazo(16)])

    def test_guardar_secciones_preserva_acciones_salvo_limpieza_explicita(self):
        with tempfile.TemporaryDirectory() as carpeta:
            acciones = [reemplazo(26, segunda=(2, 2, 2, 2))]
            guardar_configuracion(carpeta, "bkg1:1", [], inicio=10,
                                  misiones=acciones)
            guardar_configuracion(carpeta, "bkg1:1", [descanso(42, 46)], inicio=10)
            self.assertEqual(cargar_configuracion(carpeta, "bkg1:1"),
                             dict(secciones=[descanso(42, 46)], inicio=10,
                                  misiones=acciones))
            guardar_configuracion(carpeta, "bkg1:1", [], inicio=10, misiones=None)
            self.assertEqual(cargar_configuracion(carpeta, "bkg1:1")["misiones"], acciones)
            guardar_configuracion(carpeta, "bkg1:1", [], inicio=10, misiones=[])
            self.assertEqual(cargar_configuracion(carpeta, "bkg1:1")["misiones"], [])

    def test_acciones_invalidas_no_destruyen_preferencias_anteriores(self):
        with tempfile.TemporaryDirectory() as carpeta:
            guardar_configuracion(carpeta, "bkg1:1", [], inicio=10,
                                  misiones=[reemplazo(26)])
            ruta = Path(carpeta) / "configuracion_secciones.json"
            antes = ruta.read_bytes()
            with self.assertRaises(ValueError):
                guardar_configuracion(carpeta, "bkg1:1", [], inicio=10,
                                      misiones=[reemplazo(math.nan)])
            self.assertEqual(ruta.read_bytes(), antes)


class IntegracionNucleoTest(unittest.TestCase):
    def setUp(self):
        self.fila = {"ID": "900001", "Filename": "bkgprueba", "Difficulty": "1",
                     "BPM": "60", "StartDelayTime": "0", "Second": "64",
                     "MissionFailDanceID": "201"}
        self.rej = {"bpm": 60.0, "dur": 64.0, "fin_beat": 64.0, "ogg": None}
        self.secciones = [patron(0, 64, (3, 3, 3, 3), (2, 2, 2, 2), bolsa=1),
                          descanso(0, 4)]
        parches = [
            mock.patch.object(N, "pozo", side_effect=lambda nombre, estrellas:
                              {"0": 1} if "spaces" in nombre else {"157": 1}),
            mock.patch.object(N, "id_de_semilla", side_effect=lambda identificador: identificador),
            mock.patch.object(N, "menos_space_de", return_value=False),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def test_generar_sin_secciones_conserva_resultado_original(self):
        referencia = N.generar(self.fila, self.rej, 1, 0)
        self.assertEqual(N.generar(self.fila, self.rej, 1, 0, secciones=[]), referencia)
        self.assertEqual(referencia[0]["Length"], "16,16,16,16")

    def test_generar_rechaza_estructuras_falsas_malformadas(self):
        for secciones in (None, {}, 0, ""):
            with self.subTest(secciones=secciones), self.assertRaises(ValueError):
                N.generar(self.fila, self.rej, 1, 0, secciones=secciones)

    def test_generar_respeta_triples_manuales_y_actualiza_informe_tras_descanso(self):
        resultado, informe = N.generar(self.fila, self.rej, 1, 0,
                                      secciones=self.secciones)
        self.assertEqual(float(resultado["StartDelayTime"]), 16)
        self.assertEqual(resultado["Length"], "16,16,16")
        self.assertEqual(resultado["MissionID1"], "469,469,469")
        self.assertEqual(resultado["MissionID2"], "313,313,313")
        self.assertEqual(resultado["KeyPatternID"], "1,1,1")
        self.assertEqual({len(resultado[c].split(",")) for c in LISTAS}, {3})
        self.assertEqual(informe["misiones"], 3)
        self.assertEqual(informe["descansos"], 1)
        self.assertEqual(informe["flechas"], 12)
        self.assertEqual(informe["tandas2"], 3)
        self.assertEqual(informe["flechas2"], 8)
        self.assertEqual(informe["space"], 0)
        self.assertEqual(informe["sin_space"], 3)
        self.assertEqual(informe["sin_flechas"], 0)
        self.assertEqual(informe["reparto"], [0, 0, 0, 100])
        self.assertEqual(informe["fin_chart"], 64)
        self.assertEqual(informe["largas"], 0)
        self.assertEqual(informe["partidas"], 0)
        marcas = N.golpes(resultado, float(resultado["StartDelayTime"]), 60)
        self.assertEqual(min(g["t"] for g in marcas), 16)
        self.assertEqual(len(marcas), 24)

    def test_generar_tambien_conserva_fin_chart_con_descanso_final(self):
        resultado, informe = N.generar(self.fila, self.rej, 1, 0,
                                      secciones=[descanso(48, 64)])
        self.assertEqual(resultado["Length"], "16,16,32")
        self.assertEqual(float(resultado["StartDelayTime"]), 0)
        self.assertEqual(informe["misiones"], 3)
        self.assertEqual(informe["fin_chart"], 64)
        self.assertEqual(informe["largas"], 1)

    def test_descanso_inicial_preserva_indices_con_tempo_y_arranque_decimales(self):
        bpm, inicio = 120.123, 12.34567
        rej = dict(self.rej, bpm=bpm, dur=200, fin_beat=200)
        resultado, informe = N.generar(
            self.fila, rej, 1, inicio, bpm=bpm,
            secciones=[descanso(inicio, inicio + 0.1)])
        self.assertAlmostEqual(float(resultado["StartDelayTime"]),
                               inicio + 16 * 60 / bpm, places=10)
        self.assertEqual(informe["misiones"], 22)
        self.assertEqual(len(resultado["Length"].split(",")), 22)
        self.assertAlmostEqual(informe["fin_chart"], inicio + 23 * 16 * 60 / bpm,
                               places=10)

    def test_previo_usa_arranque_real_para_golpes_escucha_y_arranques(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ogg = Path(carpeta) / "prueba.ogg"
            ogg.touch()
            rej = dict(self.rej, ogg=ogg)
            salida = Path(carpeta) / "escucha.wav"
            with mock.patch.object(N, "golpes", wraps=N.golpes) as golpes, \
                    mock.patch.object(N, "armar_escucha") as escuchar:
                ruta, informe = N.previo(self.fila, rej, 1, 0, segundos=20,
                                         salida=salida, musica=False,
                                         secciones=self.secciones)
            self.assertEqual(ruta, salida)
            self.assertEqual(golpes.call_args.args[1:], (16.0, 60.0))
            self.assertEqual(informe["arranques"], [16, 32, 48])
            self.assertEqual(informe["desde"], 14.5)
            self.assertEqual(informe["misiones"], 3)
            self.assertEqual(informe["marcas"], 11)
            self.assertEqual(informe["flechas"], 29)
            self.assertEqual(informe["space"], 0)
            self.assertEqual(escuchar.call_args.args[2], 14.5)
            self.assertEqual(escuchar.call_args.kwargs["inicios_mision"], [16, 32, 48])
            self.assertEqual(min(g["t"] for g in escuchar.call_args.args[1]), 16)

    def test_probar_los_cuatro_propaga_secciones_a_cada_previo(self):
        def previo_sin_audio(*args, **kwargs):
            with wave.open(str(kwargs["salida"]), "wb") as archivo:
                archivo.setnchannels(1)
                archivo.setsampwidth(2)
                archivo.setframerate(N.SR_ESCUCHA)
                archivo.writeframes(b"\x00\x00" * 8)

        with tempfile.TemporaryDirectory() as carpeta:
            cache = Path(carpeta)
            with mock.patch.object(N, "CACHE", cache), \
                    mock.patch.object(N, "previo", side_effect=previo_sin_audio) as previo:
                salida, informe = N.probar_los_cuatro(
                    self.fila, self.rej, 1, [0, 1, 2, 3],
                    salida=cache / "cuatro.wav", secciones=self.secciones)
            self.assertTrue(salida.is_file())
            self.assertEqual(informe["tramos"], 4)
            self.assertEqual(previo.call_count, 4)
            for llamada in previo.call_args_list:
                self.assertEqual(llamada.kwargs["secciones"], self.secciones)

    def test_comparar_compases_escucha_despues_del_descanso_inicial(self):
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
            rej = dict(self.rej, ogg=ogg)
            with mock.patch.object(N, "CACHE", cache), \
                    mock.patch.object(N, "armar_escucha", side_effect=escribir_wav) as escuchar:
                N.probar_los_cuatro(self.fila, rej, 1, [0, 0, 0, 0],
                                   salida=cache / "cuatro.wav",
                                   secciones=[descanso(0, 4)])
            self.assertEqual(escuchar.call_count, 4)
            for llamada in escuchar.call_args_list:
                self.assertEqual(llamada.args[2], 15.6)
                self.assertEqual(llamada.kwargs["inicios_mision"], [16, 32, 48])


class ConsejoBPMTest(unittest.TestCase):
    def test_identifica_x3_y_x4_con_el_bpm_que_persiste_la_tabla(self):
        base = 120.123
        for factor in (3, 4):
            with self.subTest(factor=factor):
                consejo = N.consejo_bpm({"bpm": base, "ogg": None},
                                        bpm_tabla=round(base * factor, 2),
                                        con_medicion=False)
                self.assertEqual([o["factor"] for o in consejo["opciones"] if o["usada"]],
                                 [factor])

    def test_no_confunde_tempo_cercano_con_multiplo_exacto(self):
        consejo = N.consejo_bpm({"bpm": 100, "ogg": None},
                                bpm_tabla=299.99, con_medicion=False)
        self.assertFalse(any(o["usada"] for o in consejo["opciones"]))

    def test_admite_relacion_inversa_del_triple_en_medicion_de_audio(self):
        consejo = N.consejo_bpm({"bpm": 300, "bpm_audio": 300, "ogg": None},
                                bpm_tabla=100, con_medicion=False)
        self.assertFalse(any("no coincide" in aviso.lower()
                             for aviso in consejo["avisos"]))


class CopiarConfiguracionTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.carpeta = Path(temporal.name)
        self.ogg = self.carpeta / "original.ogg"
        self.ogg.write_bytes(b"audio de prueba")
        self.destinos = self.carpeta / "copias_audio"
        self.fila = dict(chart((16, 16, 16, 16)), ID="2001", Filename="bkg2001",
                         Title="Cancion de prueba", Difficulty="1", SoundSourceSN="2001",
                         BPM="60", StartDelayTime="0", Second="64", Newsong="0",
                         Popularity="1")
        self.tabla = SimpleNamespace(filas=[self.fila])
        self.original = copy.deepcopy(self.fila)
        contexto = ExitStack()
        self.addCleanup(contexto.close)
        parches = {
            "ESTUDIO": self.carpeta,
            "OGG_NUEVOS": self.destinos,
            "BKG_SNB": self.carpeta / "snb",
        }
        for nombre, valor in parches.items():
            contexto.enter_context(mock.patch.object(N, nombre, valor))
        funciones = {
            "buscar_ogg": self.ogg, "_nombres_ocupados": set(),
            "anotar_mia": None, "anotar_estilo": None, "anotar_partes": None,
            "anotar_menos_space": None, "anotar_copias": None,
            "estilo_de": "clasico", "partes_de": False, "menos_space_de": False,
        }
        for nombre, valor in funciones.items():
            contexto.enter_context(mock.patch.object(N, nombre, return_value=valor))
        self.convertir = contexto.enter_context(mock.patch.object(
            N, "correr_snb_local",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr="")))

    def test_duplicar_cancion_copia_secciones_y_ancla_a_la_nueva_clave(self):
        secciones = [patron(10, 30, (2, 0, 1, 0), bolsa=1), descanso(40, 50)]
        clave_original = "bkg2001:2001"
        guardar_configuracion(self.carpeta, clave_original, secciones, inicio=12.34567,
                              misiones=[reemplazo(28.34567, segunda=(2, 2, 2, 2))])
        configuracion = cargar_configuracion(self.carpeta, clave_original)

        ids, mensaje = N.copiar_cancion(self.tabla, [self.fila])

        self.assertEqual(ids, ["2002"])
        self.assertIn("Copia lista", mensaje)
        self.assertEqual(len(self.tabla.filas), 2)
        copia = self.tabla.filas[-1]
        self.assertNotEqual(copia["Filename"], self.fila["Filename"])
        clave_copia = "%s:%s" % (copia["Filename"], copia["ID"])
        self.assertEqual(cargar_configuracion(self.carpeta, clave_copia), configuracion)
        self.assertEqual(cargar_configuracion(self.carpeta, clave_original), configuracion)
        self.assertEqual(self.fila, self.original)
        self.assertEqual((self.destinos / (copia["Filename"] + ".ogg")).read_bytes(),
                         self.ogg.read_bytes())
        self.convertir.assert_called_once()

    def test_duplicar_tambien_copia_acciones_sin_secciones_ni_ancla(self):
        acciones = [reemplazo(16)]
        guardar_configuracion(self.carpeta, "bkg2001:2001", [], misiones=acciones)
        N.copiar_cancion(self.tabla, [self.fila])
        copia = self.tabla.filas[-1]
        self.assertEqual(cargar_configuracion(
            self.carpeta, "%s:%s" % (copia["Filename"], copia["ID"])),
            dict(secciones=[], inicio=None, misiones=acciones))
        self.assertEqual(cargar_configuracion(self.carpeta, "bkg2001:2001"),
                         dict(secciones=[], inicio=None, misiones=acciones))

    def test_configuracion_corrupta_frena_copia_antes_de_crear_audio_o_convertir(self):
        ruta = self.carpeta / "configuracion_secciones.json"
        ruta.write_text("{ corrupto", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, ".+"):
            N.copiar_cancion(self.tabla, [self.fila])
        self.convertir.assert_not_called()
        self.assertEqual(self.tabla.filas, [self.original])
        self.assertFalse(self.destinos.exists())
        self.assertEqual(ruta.read_text(encoding="utf-8"), "{ corrupto")


if __name__ == "__main__":
    unittest.main()
