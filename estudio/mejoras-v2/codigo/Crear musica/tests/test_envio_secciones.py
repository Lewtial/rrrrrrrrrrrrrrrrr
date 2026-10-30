"""Del mapa al musictable: las secciones aplicadas deben poder enviarse."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import estudio
import nucleo as N
from mapa_secciones import EdicionSeccionesMapa


class Valor:
    def __init__(self, valor):
        self.valor = valor

    def get(self):
        return self.valor

    def set(self, valor):
        self.valor = valor


class Control:
    def __init__(self, **configuracion):
        self.configuracion = configuracion

    def config(self, **configuracion):
        self.configuracion.update(configuracion)


def patron(cantidad):
    return dict(tipo="patron", desde=0, hasta=96,
                primera=[cantidad] * 4, segunda=None, bolsa=4)


def descanso(desde=32, hasta=48):
    return dict(tipo="descanso", desde=desde, hasta=hasta)


def fila(identificador, estrellas):
    resultado = {columna: ",".join(["0"] * 6) for columna in N.LISTAS}
    resultado.update(ID=str(identificador), Filename="prueba", Title="Prueba",
                     Singer="Fixture", Difficulty=str(estrellas), BPM="60",
                     StartDelayTime="0", Second="96", Length=",".join(["16"] * 6),
                     KeyPatternID=",".join(["4"] * 6),
                     MissionID1=",".join(["157"] * 6),
                     MissionFailDanceID=",".join(["201"] * 6))
    return resultado


class Padre:
    def __init__(self):
        self.pareja = [fila(9001, 1), fila(9002, 7)]
        self.configs = {f["ID"]: dict(secciones=[], inicio=None) for f in self.pareja}
        self.trabajando = False
        self.sucias, self.modificadas = {"cambio-anterior"}, {"cambio-anterior"}
        self.v_descanso, self.v_sinsp = Valor(False), Valor(False)
        self.ultimas_repes = ()
        self.spins = {f["ID"]: (Valor(int(f["Difficulty"])), None, Valor("x1"))
                      for f in self.pareja}
        self.audio_por_borrar, self.recortes = set(), {}
        self.b_enviar = Control(state="normal")
        self.pintar_lista = Mock()
        self.exportadas = []
        self.tabla = SimpleNamespace(filas=self.pareja,
                                     guardar=Mock(side_effect=self._exportar))
        self._en_hilo = Mock(side_effect=self._ejecutar)
        self.fallar_guardado = None
        self.guardados = 0

    @staticmethod
    def _ejecutar(_texto, trabajo, despues):
        despues(trabajo())

    def _exportar(self, _etiqueta):
        self.exportadas.append(copy.deepcopy(self.tabla.filas))
        return Path("/tmp/respaldo-simulado.slk.spak")

    def config_secciones(self, f):
        return self.configs[f["ID"]]

    def guardar_secciones(self, f, secciones, inicio):
        self.guardados += 1
        if self.guardados == self.fallar_guardado:
            self.fallar_guardado = None
            raise OSError("falló el segundo guardado")
        self.configs[f["ID"]] = dict(secciones=copy.deepcopy(secciones), inicio=inicio)

    def extras(self, f):
        return dict(secciones=copy.deepcopy(self.config_secciones(f)["secciones"]))

    @staticmethod
    def frases_de():
        return None

    @staticmethod
    def modo_space():
        return "softnyx"

    @staticmethod
    def mudos_de(_fila):
        return ()

    @staticmethod
    def bpm_de_fila(_identificador):
        return 60


class Mapa(EdicionSeccionesMapa):
    def __init__(self, padre):
        self.padre = padre
        self.original = False
        self.fila = padre.pareja[0]
        self.listas = dict(self.fila)
        self.estrellas, self.bpm, self.inicio = 1, 60, 0
        self.dur = 96
        self.rej = dict(bpm=60, dur=96, fin_beat=96, ogg=None)
        self.por_musica = False
        self.guardado = False
        self.v_ambas = Valor(False)
        self.v0 = 0
        self.parar, self._rehacer_mapa = Mock(), Mock()
        self.info = Control()

    @staticmethod
    def tramos_mudos():
        return ()

    @staticmethod
    def _t_de_x(x):
        return float(x)

    @staticmethod
    def _mision_en(x):
        return dict(t=int(float(x) // 16) * 16, largo=16)


def eventos_en(f, desde, hasta):
    return [g for g in N.golpes(f, float(f["StartDelayTime"]), float(f["BPM"]))
            if desde <= g["t"] < hasta]


class EnvioSeccionesTests(unittest.TestCase):
    def setUp(self):
        self.padre = Padre()
        self.mapa = Mapa(self.padre)
        parches = [
            patch.object(N, "pozo", side_effect=lambda nombre, estrellas:
                         {"0": 1} if "spaces" in nombre else {"157": 1}),
            patch.object(N, "id_de_semilla", side_effect=lambda identificador: identificador),
            patch.object(N, "menos_space_de", return_value=False),
            patch.object(N, "mapa_sn", return_value="mapa simulado"),
            patch.object(estudio.messagebox, "askyesno", return_value=True),
            patch.object(estudio.messagebox, "showinfo"),
            patch.object(estudio.messagebox, "showerror"),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def test_aplicar_y_enviar_sin_generar_exporta_el_descanso_del_mapa(self):
        self.mapa.aplicar_editor_secciones([descanso()])
        self.assertEqual(eventos_en(self.mapa.listas, 32, 48), [])
        self.assertEqual(eventos_en(self.padre.pareja[0], 32, 48), [])
        self.assertEqual(self.padre.sucias, {"cambio-anterior", "9001"})
        self.assertEqual(self.padre.modificadas, {"cambio-anterior", "9001"})
        self.assertEqual(self.padre.b_enviar.configuracion["state"], "normal")
        self.assertTrue(self.mapa.guardado)
        visible = copy.deepcopy(self.mapa.listas)
        estudio.Estudio.enviar(self.padre)
        self.padre.tabla.guardar.assert_called_once_with("estudio")
        exportada = self.padre.exportadas[0][0]
        self.assertEqual(eventos_en(exportada, 32, 48), [])
        for columna in N.LISTAS + ["StartDelayTime", "BPM", "Difficulty"]:
            self.assertEqual(exportada[columna], visible[columna])
        self.assertEqual(self.padre.sucias, set())

    def test_aplicar_solo_actual_conserva_la_otra_dificultad(self):
        otra_fila = copy.deepcopy(self.padre.pareja[1])
        self.padre.configs["9002"] = dict(secciones=[patron(2)], inicio=0)
        otra_config = copy.deepcopy(self.padre.configs["9002"])
        self.mapa.aplicar_editor_secciones([descanso()])
        self.assertEqual(self.padre.pareja[1], otra_fila)
        self.assertEqual(self.padre.configs["9002"], otra_config)
        self.assertNotIn("9002", self.padre.sucias)

    def test_herramienta_descanso_ambas_preserva_patrones_de_cada_version(self):
        self.mapa.v_ambas.set(True)
        self.padre.configs["9001"] = dict(secciones=[patron(1)], inicio=0)
        self.padre.configs["9002"] = dict(
            secciones=[patron(2), descanso(64, 80)], inicio=0)
        self.mapa.descanso_seccion(SimpleNamespace(x=33))
        for identificador, cantidad in (("9001", 1), ("9002", 2)):
            with self.subTest(identificador=identificador):
                configuradas = self.padre.configs[identificador]["secciones"]
                self.assertIn(patron(cantidad), configuradas)
                self.assertIn(descanso(), configuradas)
                f = next(f for f in self.padre.pareja if f["ID"] == identificador)
                self.assertEqual(eventos_en(f, 32, 48), [])
                self.assertEqual(N.patron(f["MissionID1"].split(",")[0]),
                                 [cantidad] * 4)
        self.assertIn(descanso(64, 80), self.padre.configs["9002"]["secciones"])
        self.assertIn("9002", self.padre.sucias)

    def test_quitar_descanso_ambas_conserva_patrones_y_descansos_distantes(self):
        self.mapa.v_ambas.set(True)
        self.padre.configs["9001"] = dict(secciones=[patron(1), descanso()], inicio=0)
        self.padre.configs["9002"] = dict(
            secciones=[patron(2), descanso(), descanso(64, 80)], inicio=0)
        self.mapa.descanso_seccion(SimpleNamespace(x=33))
        self.assertEqual(self.padre.configs["9001"]["secciones"], [patron(1)])
        self.assertEqual(self.padre.configs["9002"]["secciones"],
                         [patron(2), descanso(64, 80)])
        self.assertTrue(eventos_en(self.padre.pareja[0], 32, 48))
        self.assertTrue(eventos_en(self.padre.pareja[1], 32, 48))
        self.assertEqual(eventos_en(self.padre.pareja[1], 64, 80), [])

    def test_herramienta_solo_actual_no_toca_la_otra_version(self):
        self.mapa.v_ambas.set(False)
        antes = copy.deepcopy(self.padre.pareja[1])
        self.mapa.descanso_seccion(SimpleNamespace(x=33))
        self.assertEqual(self.padre.configs["9001"]["secciones"], [descanso()])
        self.assertEqual(self.padre.configs["9002"]["secciones"], [])
        self.assertEqual(self.padre.pareja[1], antes)

    def test_fallo_segundo_guardado_no_cambia_filas_flags_ni_preview(self):
        self.padre.configs["9001"] = dict(secciones=[patron(1)], inicio=0)
        self.padre.configs["9002"] = dict(secciones=[patron(2)], inicio=0)
        filas = copy.deepcopy(self.padre.pareja)
        configuraciones = copy.deepcopy(self.padre.configs)
        preview = copy.deepcopy(self.mapa.listas)
        flags = (set(self.padre.sucias), set(self.padre.modificadas),
                 dict(self.padre.b_enviar.configuracion), self.mapa.guardado)
        self.padre.fallar_guardado = 2
        self.mapa.aplicar_editor_secciones([descanso()], todas_versiones=True)
        self.assertEqual(self.padre.pareja, filas)
        self.assertEqual(self.padre.configs, configuraciones)
        self.assertEqual(self.mapa.listas, preview)
        self.assertEqual((self.padre.sucias, self.padre.modificadas,
                          self.padre.b_enviar.configuracion, self.mapa.guardado), flags)
        self.padre.pintar_lista.assert_not_called()
        self.mapa._rehacer_mapa.assert_not_called()

    def test_dialogo_hereda_ambito_actual_del_mapa(self):
        self.mapa.v_ambas.set(True)
        dialogo = SimpleNamespace(v_todas=Valor(False))
        with patch("dialogo_secciones.DialogoSecciones", return_value=dialogo):
            self.mapa.abrir_secciones_tramos()
        self.assertTrue(dialogo.v_todas.get())


if __name__ == "__main__":
    unittest.main()
