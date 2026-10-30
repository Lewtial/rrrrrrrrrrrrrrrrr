"""Contenido y copiado de misiones sin abrir ventanas ni reproducir audio."""
import copy
from pathlib import Path
import sys
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor_misiones import (BOLSAS, CASILLEROS, EditorMisiones, accion_reemplazo,
                             contenido_mision, listar_misiones)


def listas():
    return {"Length": "16,24,8", "MissionID1": "136,469,1",
            "MissionID2": "0,52,0", "KeyPatternID": "4,1,3"}


class ListarMisionesTests(unittest.TestCase):
    def test_lista_todas_las_misiones_y_calcula_horarios_con_sus_largos(self):
        misiones = listar_misiones(listas(), 10, 120)
        self.assertEqual(len(misiones), 3)
        self.assertEqual([m["n"] for m in misiones], [1, 2, 3])
        self.assertEqual([m["t"] for m in misiones], [10, 18, 30])
        self.assertEqual([m["largo"] for m in misiones], [16, 24, 8])

    def test_decodifica_casilleros_space_segunda_tanda_y_bolsa(self):
        primera, segunda, tercera = listar_misiones(listas(), 10, 120)
        self.assertEqual(primera["primera"], [1, 0, 2, 0])
        self.assertIsNone(primera["segunda"])
        self.assertEqual(segunda["primera"], [3, 3, 3, 3])
        self.assertEqual(segunda["segunda"], [0, 2, 0, 1])
        self.assertEqual(tercera["primera"], [0, 0, 0, 0])
        self.assertEqual([primera["bolsa"], segunda["bolsa"], tercera["bolsa"]],
                         [4, 1, 3])

    def test_segunda_tanda_de_space_es_distinta_de_no_tener_segunda(self):
        fuente = listas()
        fuente["MissionID2"] = "0,1,136"
        misiones = listar_misiones(fuente, 10, 120)
        self.assertIsNone(misiones[0]["segunda"])
        self.assertEqual(misiones[1]["segunda"], [0, 0, 0, 0])
        self.assertEqual(misiones[2]["segunda"], [1, 0, 2, 0])

    def test_prioriza_arranque_real_guardado_en_el_chart(self):
        fuente = listas()
        fuente["StartDelayTime"] = "41.25"
        misiones = listar_misiones(fuente, 10, 120)
        self.assertEqual([m["t"] for m in misiones], [41.25, 49.25, 61.25])

    def test_no_modifica_el_chart_al_listar(self):
        fuente = listas()
        antes = copy.deepcopy(fuente)
        resultado = listar_misiones(fuente, 10, 120)
        resultado[0]["primera"][0] = 3
        self.assertEqual(fuente, antes)

    def test_admite_largos_enteros_escritos_con_decimal(self):
        fuente = listas()
        fuente["Length"] = "16.0,24.0,8.0"
        self.assertEqual([m["largo"] for m in listar_misiones(fuente, 10, 120)],
                         [16, 24, 8])

    def test_rechaza_columnas_desalineadas(self):
        for columna in ("MissionID1", "MissionID2", "KeyPatternID"):
            with self.subTest(columna=columna):
                fuente = listas()
                fuente[columna] = ",".join(fuente[columna].split(",")[:-1])
                with self.assertRaises(ValueError):
                    listar_misiones(fuente, 10, 120)

    def test_rechaza_tempo_o_arranque_no_finitos(self):
        for bpm in (0, -1, float("nan"), float("inf")):
            with self.subTest(bpm=bpm), self.assertRaises(ValueError):
                listar_misiones(listas(), 10, bpm)
        for inicio in (-1, float("nan"), float("inf")):
            with self.subTest(inicio=inicio), self.assertRaises(ValueError):
                listar_misiones(listas(), inicio, 120)


class CopiarMisionesTests(unittest.TestCase):
    def setUp(self):
        self.misiones = listar_misiones(listas(), 10, 120)

    def test_copiar_extrae_solo_contenido_sin_horario_ni_duracion(self):
        contenido = contenido_mision(self.misiones[1])
        self.assertEqual(contenido, {"primera": [3, 3, 3, 3],
                                    "segunda": [0, 2, 0, 1], "bolsa": 1})

    def test_copia_profunda_independiza_ambas_tandas(self):
        original = copy.deepcopy(self.misiones[1])
        contenido = contenido_mision(self.misiones[1])
        contenido["primera"][0] = 0
        contenido["segunda"][1] = 0
        self.assertEqual(self.misiones[1], original)

    def test_pegar_usa_horario_destino_sin_cambiar_su_largo(self):
        destino = self.misiones[0]
        antes = copy.deepcopy(destino)
        contenido = contenido_mision(self.misiones[1])
        accion = accion_reemplazo(destino, contenido)
        self.assertEqual(accion, {"tipo": "reemplazar", "tiempo": 10,
                                  "primera": [3, 3, 3, 3],
                                  "segunda": [0, 2, 0, 1], "bolsa": 1})
        self.assertNotIn("Length", accion)
        self.assertNotIn("largo", accion)
        self.assertEqual(destino, antes)

    def test_pegar_repetidamente_no_comparte_casilleros_entre_acciones(self):
        contenido = contenido_mision(self.misiones[1])
        primero = accion_reemplazo(self.misiones[0], contenido)
        segundo = accion_reemplazo(self.misiones[1], contenido)
        primero["primera"][0] = 0
        primero["segunda"][1] = 0
        self.assertEqual(segundo["primera"], [3, 3, 3, 3])
        self.assertEqual(segundo["segunda"], [0, 2, 0, 1])
        self.assertEqual(contenido["primera"], [3, 3, 3, 3])
        self.assertEqual(contenido["segunda"], [0, 2, 0, 1])

    def test_no_pega_segunda_tanda_en_mision_corta_ni_modifica_entradas(self):
        destino = self.misiones[2]
        contenido = contenido_mision(self.misiones[1])
        antes = copy.deepcopy((destino, contenido))
        with self.assertRaises(ValueError):
            accion_reemplazo(destino, contenido)
        self.assertEqual((destino, contenido), antes)

    def test_pega_una_tanda_en_mision_corta(self):
        contenido = contenido_mision(self.misiones[0])
        accion = accion_reemplazo(self.misiones[2], contenido)
        self.assertEqual(accion["tiempo"], 30)
        self.assertEqual(accion["primera"], [1, 0, 2, 0])
        self.assertIsNone(accion["segunda"])


class Variable:
    def __init__(self, valor=None):
        self.valor = valor

    def get(self):
        return self.valor

    def set(self, valor):
        self.valor = valor


class Tabla:
    def __init__(self):
        self.filas = {}
        self.seleccion = ()

    def get_children(self):
        return tuple(self.filas)

    def delete(self, *ids):
        for iid in ids:
            self.filas.pop(iid, None)

    def insert(self, _padre, _posicion, iid, values):
        self.filas[iid] = values

    def selection_set(self, iid):
        self.seleccion = (iid,)

    def selection(self):
        return self.seleccion

    def focus(self, _iid):
        pass

    def see(self, _iid):
        pass


class FlujoEditorTests(unittest.TestCase):
    @staticmethod
    def editor():
        editor = SimpleNamespace(
            padre=SimpleNamespace(trabajando=False, padre=None),
            portapapeles=dict(primera=[1, 0, 2, 0], segunda=None, bolsa=4),
            _mision_actual=Mock(return_value=dict(t=18, largo=24)),
            al_aplicar=Mock(), destroy=Mock(), actualizar=Mock(), lbl_estado=Mock())
        editor._ocupado = MethodType(EditorMisiones._ocupado, editor)
        return editor

    def test_callback_pendiente_o_rechazado_no_cierra_ni_cambia_portapapeles(self):
        for resultado in (None, False):
            with self.subTest(resultado=resultado):
                editor = self.editor()
                editor.al_aplicar.return_value = resultado
                antes = copy.deepcopy(editor.portapapeles)
                EditorMisiones._enviar_contenido(editor, editor.portapapeles)
                editor.al_aplicar.assert_called_once_with([
                    dict(tipo="reemplazar", tiempo=18,
                         primera=[1, 0, 2, 0], segunda=None, bolsa=4)])
                self.assertEqual(editor.portapapeles, antes)
                editor.destroy.assert_not_called()
                editor.actualizar.assert_not_called()

    def test_trabajo_en_ancestro_bloquea_callback_sin_tocar_seleccion(self):
        editor = self.editor()
        editor.padre.padre = SimpleNamespace(trabajando=True, padre=None)
        self.assertFalse(EditorMisiones._enviar_contenido(editor, editor.portapapeles))
        editor.al_aplicar.assert_not_called()
        editor._mision_actual.assert_not_called()
        editor.destroy.assert_not_called()

    def test_actualizar_preserva_mision_tomada_y_destino_mientras_refresca_chart(self):
        editor = self.editor()
        original = copy.deepcopy(editor.portapapeles)
        editor._tiempo_seleccionado, editor._refrescando = 18, False
        editor.tabla = Tabla()
        editor.lbl_identidad, editor.lbl_destino = Mock(), Mock()
        editor.v_primera = [Variable() for _ in range(4)]
        editor.v_segunda = [Variable() for _ in range(4)]
        editor.v_dos_tandas, editor.v_bolsa = Variable(), Variable()
        editor._combos_segunda = [Mock() for _ in range(4)]
        for nombre in ("_seleccionar", "_mision_actual", "_cambiar_segunda"):
            setattr(editor, nombre, MethodType(getattr(EditorMisiones, nombre), editor))
        fuente = listas()
        fuente["MissionID1"] = "136,157,1"
        fuente["KeyPatternID"] = "4,3,3"
        EditorMisiones.actualizar(editor, {"ID": "9001", "Title": "Prueba"},
                                 fuente, 10, 120)
        self.assertEqual(editor.tabla.selection(), ("2",))
        self.assertEqual(editor._tiempo_seleccionado, 18)
        self.assertEqual(editor.portapapeles, original)
        self.assertEqual(len(editor.tabla.filas), 3)
        self.assertEqual([v.get() for v in editor.v_primera], [CASILLEROS[1]] * 4)
        self.assertEqual(editor.v_bolsa.get(), BOLSAS[2])


if __name__ == "__main__":
    unittest.main()
