"""BPM del panel sin abrir Tk ni necesitar una pantalla."""
import sys
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import estudio


class Valor:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Widget:
    def __init__(self, padre=None, **config):
        self.padre = padre
        self.configuracion = config
        self.hijos = []
        self.eventos = {}
        if padre is not None:
            padre.hijos.append(self)

    def pack(self, **config):
        self.pack_config = config

    def bind(self, evento, callback):
        self.eventos[evento] = callback

    def config(self, **config):
        self.configuracion.update(config)

    def winfo_children(self):
        return list(self.hijos)

    def destroy(self):
        pass


def fila(id_, bpm, dificultad=3, archivo="tema"):
    return dict(ID=str(id_), BPM=str(bpm), Difficulty=str(dificultad),
                Filename=archivo, StartDelayTime="1", Title="Tema", Singer="Prueba")


def panel(filas=None, base=100):
    filas = filas or [fila(1, 100, 3), fila(2, 200, 9)]
    p = SimpleNamespace(rej={"bpm": base}, pareja=filas, spins={},
                        filas_est=Widget(), gen_fila={}, v_ini=Valor(),
                        lbl_est=Widget(), _texto_inicio=Mock(),
                        _llenar_candidatos=Mock(),
                        config_secciones=Mock(return_value={"secciones": [],
                                                           "inicio": None}))
    p._velocidad_de = MethodType(estudio.Estudio._velocidad_de, p)
    p.bpm_de_fila = MethodType(estudio.Estudio.bpm_de_fila, p)
    p._texto_estrellas = Mock()
    for f in filas:
        p.spins[f["ID"]] = (Valor(int(f["Difficulty"])), Widget(),
                             Valor(p._velocidad_de(f)))
    return p


class BPMTests(unittest.TestCase):
    def test_reconoce_los_cuatro_multiplos(self):
        p = panel()
        for factor in range(1, 5):
            with self.subTest(factor=factor):
                self.assertEqual(p._velocidad_de(fila(1, 100 * factor)),
                                 "x%d" % factor)

    def test_reconoce_el_redondeo_del_bpm_exportado(self):
        p = panel(base=89.953)
        self.assertEqual(p._velocidad_de(fila(1, 359.81)), "x4")

    @patch.object(estudio.N, "es_original", return_value=False)
    def test_cargar_rejilla_reconoce_x3_y_x4_guardados(self, _original):
        for factor in (3, 4):
            with self.subTest(factor=factor):
                p = panel([fila(1, 100 * factor)])
                p._rejilla_lista = Mock()
                rej = {"bpm": 100.02, "per": 60 / 100.02,
                       "compas": 240 / 100.02}
                estudio.Estudio._rejilla_elegida(p, rej)
                self.assertAlmostEqual(rej["bpm"], 100)
                self.assertAlmostEqual(rej["per"], 0.6)
                self.assertAlmostEqual(rej["compas"], 2.4)
                p._rejilla_lista.assert_called_once_with(rej)
                p.rej = rej
                self.assertEqual(p._velocidad_de(p.pareja[0]), "x%d" % factor)

    @patch.object(estudio.N, "es_original", return_value=False)
    def test_rejilla_no_se_ajusta_a_un_ratio_no_exacto(self, _original):
        p = panel([fila(1, 175.25)])
        p._rejilla_lista = Mock()
        rej = {"bpm": 100.02, "per": 60 / 100.02,
               "compas": 240 / 100.02}
        original = dict(rej)
        estudio.Estudio._rejilla_elegida(p, rej)
        self.assertEqual(rej, original)
        self.assertEqual(p.pareja[0]["BPM"], "175.25")

    def test_bpm_efectivo_de_los_cuatro_selectores(self):
        p = panel()
        for factor in range(1, 5):
            with self.subTest(factor=factor):
                p.spins["1"][2].set("x%d" % factor)
                self.assertEqual(p.bpm_de_fila("1"), 100 * factor)

    def test_ratio_no_exacto_conserva_el_bpm_guardado(self):
        p = panel([fila(1, 175.25)])
        self.assertEqual(p.spins["1"][2].get(), "175.25 BPM (actual)")
        self.assertEqual(p.bpm_de_fila("1"), 175.25)

    def test_bpm_cercano_no_se_corrige_silenciosamente(self):
        p = panel([fila(1, 299.99)])
        self.assertEqual(p.spins["1"][2].get(), "299.99 BPM (actual)")
        self.assertEqual(p.bpm_de_fila("1"), 299.99)

    def test_sin_selector_conserva_bpm_guardado(self):
        p = panel([fila(1, 135)])
        p.spins.clear()
        self.assertEqual(p.bpm_de_fila(1), 135)

    def test_aplicar_x2_x3_x4_solo_cambia_la_fila_dificil(self):
        for factor in (2, 3, 4):
            with self.subTest(factor=factor):
                p = panel()
                p.spins["1"][2].set("x3")
                estudio.Estudio.poner_velocidades(p, "x%d" % factor)
                self.assertEqual(p.spins["1"][2].get(), "x3")
                self.assertEqual(p.spins["2"][2].get(), "x%d" % factor)
                self.assertEqual([p.spins[i][0].get() for i in ("1", "2")],
                                 [3, 9])

    def test_x1_seleccionado_puede_cambiar_solo_la_dificil(self):
        p = panel()
        p.spins["1"][2].set("x4")
        estudio.Estudio.poner_velocidades(p, "x1", solo_dificil=True)
        self.assertEqual(p.spins["1"][2].get(), "x4")
        self.assertEqual(p.spins["2"][2].get(), "x1")

    def test_normal_restaurara_todas_las_filas(self):
        p = panel()
        p.spins["1"][2].set("x4")
        estudio.Estudio.poner_velocidades(p, "x1")
        self.assertEqual([p.spins[i][2].get() for i in ("1", "2")],
                         ["x1", "x1"])

    def test_no_ofrece_multiplicadores_mayores_a_cuatro(self):
        p = panel()
        estudio.Estudio.poner_velocidades(p, "x5")
        self.assertEqual(p.spins["2"][2].get(), "x2")
        p._texto_estrellas.assert_not_called()

    def test_muestra_bpm_efectivo_al_lado_del_selector(self):
        p = panel()
        p.spins["1"][2].set("x3")
        estudio.Estudio._texto_estrellas(p)
        self.assertIn("300.00 BPM", p.spins["1"][1].configuracion["text"])

    @patch.multiple(estudio.tk, BooleanVar=Valor, IntVar=Valor, StringVar=Valor)
    @patch.multiple(estudio.ttk, Frame=Widget, Label=Widget, Checkbutton=Widget,
                    Spinbox=Widget, Combobox=Widget)
    def test_repintar_conserva_seleccion_de_la_misma_cancion(self):
        p = panel()
        estudio.Estudio._pintar_arreglar(p)
        p.spins["1"][2].set("x4")
        p.spins["1"][0].set(7)
        estudio.Estudio._pintar_arreglar(p)
        self.assertEqual(p.spins["1"][2].get(), "x4")
        self.assertEqual(p.spins["1"][0].get(), 7)
        # Otra canción puede reutilizar el ID, pero debe leer su propio BPM.
        p.pareja = [fila(1, 135, archivo="otra")]
        estudio.Estudio._pintar_arreglar(p)
        self.assertEqual(p.spins["1"][2].get(), "135 BPM (actual)")

    @patch.multiple(estudio.tk, BooleanVar=Valor, IntVar=Valor, StringVar=Valor)
    @patch.multiple(estudio.ttk, Frame=Widget, Label=Widget, Checkbutton=Widget,
                    Spinbox=Widget, Combobox=Widget)
    def test_panel_angosto_muestra_bpm_en_linea_propia_y_ajusta_consejos(self):
        p = panel()
        estudio.Estudio._pintar_arreglar(p)
        etiqueta = p.spins["1"][1]
        fila_panel = etiqueta.padre
        controles = fila_panel.hijos[0]
        selector = next(w for w in controles.hijos if "values" in w.configuracion)
        self.assertIsNot(selector.padre, etiqueta.padre)
        self.assertEqual(etiqueta.pack_config["fill"], "x")
        self.assertNotIn("width", etiqueta.configuracion)
        p.filas_est.eventos["<Configure>"](SimpleNamespace(width=366))
        self.assertEqual(etiqueta.configuracion["wraplength"], 350)
        self.assertEqual(p.lbl_est.configuracion["wraplength"], 350)

    @patch.multiple(estudio.tk, BooleanVar=Valor, IntVar=Valor, StringVar=Valor)
    @patch.multiple(estudio.ttk, Frame=Widget, Label=Widget, Checkbutton=Widget,
                    Spinbox=Widget, Combobox=Widget)
    def test_quitar_ultima_seccion_conserva_ancla_original_del_panel(self):
        p = panel()
        p.pareja[0]["StartDelayTime"] = "17"
        p.config_secciones.return_value = {"secciones": [], "inicio": 1.25}
        estudio.Estudio._pintar_arreglar(p)
        self.assertEqual(p.v_ini.get(), "1.2500")

    def test_descansos_del_editor_no_se_duplican_como_legacy(self):
        inferidos = [(26, 42), (74, 90), (100, 116)]
        secciones = [dict(tipo="descanso", desde=30, hasta=35),
                     dict(tipo="patron", desde=70, hasta=95)]
        self.assertEqual(estudio._descansos_legacy(inferidos, secciones),
                         ((74, 90), (100, 116)))
        # Tocar el borde no es solaparse: los intervalos son semiabiertos.
        self.assertEqual(estudio._descansos_legacy([(35, 51)], secciones),
                         ((35, 51),))

    def test_quitar_descanso_tras_reabrir_restaura_misiones(self):
        f = dict(fila(1, 60, dificultad=1), Second="64",
                 MissionFailDanceID="201")
        rej = {"bpm": 60.0, "dur": 64.0, "fin_beat": 64.0, "ogg": None}
        secciones = [dict(tipo="descanso", desde=16, hasta=20)]
        with patch.object(estudio.N, "pozo", side_effect=lambda nombre, estrellas:
                          {"0": 1} if "spaces" in nombre else {"157": 1}), \
                patch.object(estudio.N, "menos_space_de", return_value=False):
            con_descanso, _ = estudio.N.generar(
                f, rej, 1, 0, bpm=60, semilla=1, secciones=secciones)
            reabierta = dict(f, **con_descanso)
            inferidos = estudio.N.descansos_guardados(reabierta)
            self.assertEqual(inferidos, [(16, 32)])
            mudos = estudio._descansos_legacy(inferidos, secciones)
            sin_descanso, informe = estudio.N.generar(
                reabierta, rej, 1, 0, bpm=60, semilla=1,
                secciones=[], mudos=mudos, descanso=True)
        self.assertEqual(informe["misiones"], 4)
        self.assertEqual(sin_descanso["Length"], "16,16,16,16")
        self.assertTrue(any(g["t"] == 16 for g in
                            estudio.N.golpes(sin_descanso, 0, 60)))

    def test_elegir_cierra_mapa_antes_de_cambiar_cancion_y_filtra_descansos(self):
        f = fila(1, 60, archivo="nueva")
        p = panel([f])
        p.cargada, p.trabajando = "anterior", False
        p.fila_actual = Mock(return_value=f)
        p.tabla = SimpleNamespace(filas=[f])
        p.parar = Mock()
        p._en_hilo = Mock()
        p._rejilla_elegida = Mock()
        p.cabecera, p.subcab = Widget(), Widget()
        for nombre in ("v_descanso", "v_sin_caminar", "v_estilo", "v_partes",
                       "v_menos_sp"):
            setattr(p, nombre, Valor())
        p.config_secciones.return_value = {
            "secciones": [dict(tipo="descanso", desde=26, hasta=42)], "inicio": 1}
        cierres = []

        class Mapa:
            def cerrar(self):
                cierres.append(p.cargada)

        p.winfo_children = Mock(return_value=[Widget(), Mapa()])
        with patch.object(estudio, "VentanaEntera", Mapa), patch.multiple(
                estudio.N,
                es_original=Mock(return_value=False),
                descansos_guardados=Mock(return_value=[(26, 42), (74, 90)]),
                ritmos_guardados=Mock(return_value=[]),
                config_guardada=Mock(return_value={"frases": [], "sin_caminar": True}),
                estilo_de=Mock(return_value="clasico"),
                partes_de=Mock(return_value=False),
                menos_space_de=Mock(return_value=False), SIN_CAMINAR=True):
            estudio.Estudio.elegir(p)
        self.assertEqual(cierres, ["anterior"])
        self.assertEqual(p.cargada, "nueva")
        self.assertEqual(p.ultimos_mudos, ((74, 90),))
        p._en_hilo.assert_called_once()

    def test_dialogo_no_recalcula_estrellas_de_otras_versiones(self):
        p = SimpleNamespace(poner_velocidades=Mock(), arreglar_estrellas=Mock())
        dialogo = SimpleNamespace(padre=p, destroy=Mock())
        estudio.VentanaBPM.aplicar(dialogo, "x4", solo_dificil=True)
        p.poner_velocidades.assert_called_once_with("x4", solo_dificil=True)
        p.arreglar_estrellas.assert_not_called()
        dialogo.destroy.assert_called_once_with()

    def test_generacion_conserva_factor_y_duracion_del_audio(self):
        f = dict(fila(1, 100, dificultad=1), Second="96",
                 MissionFailDanceID="201")
        rej = {"bpm": 100.0, "dur": 96.0, "fin_beat": 96.0, "ogg": None}
        with patch.object(estudio.N, "pozo", side_effect=lambda nombre, estrellas:
                          {"0": 1} if "spaces" in nombre else {"157": 1}), \
                patch.object(estudio.N, "menos_space_de", return_value=False):
            for factor in range(1, 5):
                with self.subTest(factor=factor):
                    p = panel([f])
                    p.spins["1"][2].set("x%d" % factor)
                    bpm = p.bpm_de_fila("1")
                    resultado, informe = estudio.N.generar(
                        f, rej, 1, 0, bpm=bpm, semilla=1)
                    self.assertEqual(float(resultado["BPM"]), 100 * factor)
                    self.assertEqual(resultado["Second"], "96")
                    self.assertEqual(informe["misiones"], 10 * factor)
                    self.assertAlmostEqual(informe["fin_chart"], 96)
                    marcas = estudio.N.golpes(resultado, 0, bpm)
                    self.assertAlmostEqual(marcas[1]["t"] - marcas[0]["t"],
                                           60 / bpm)


if __name__ == "__main__":
    unittest.main()
