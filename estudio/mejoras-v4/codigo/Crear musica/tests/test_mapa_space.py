"""El mapa distingue los SPACE jugables de los tramos sin misiones, sin Tk."""
import copy
from pathlib import Path
import sys
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import estudio
import nucleo as N


class Valor:
    def __init__(self, valor): self.valor = valor
    def get(self): return self.valor


class Etiqueta:
    def __init__(self): self.texto = ''
    def config(self, **kw): self.texto = kw.get('text', self.texto)


class Lienzo:
    def __init__(self): self.figuras = []
    def delete(self, *_args): self.figuras.clear()
    def _agregar(self, tipo, *coords, **kw):
        self.figuras.append(dict(tipo=tipo, coords=coords, **kw))
        return len(self.figuras)
    def create_rectangle(self, *a, **kw): return self._agregar('rect', *a, **kw)
    def create_text(self, *a, **kw): return self._agregar('text', *a, **kw)
    def create_line(self, *a, **kw): return self._agregar('line', *a, **kw)
    def create_polygon(self, *a, **kw): return self._agregar('polygon', *a, **kw)
    def coords(self, *_args): pass
    def itemconfig(self, *_args, **_kw): pass


class Mapa:
    """Solo sustituye los widgets: ejecuta los métodos reales del mapa."""
    def __init__(self, primera='1', segunda='0', largo=16):
        self.fila = dict(ID='29991', Filename='bkgprueba', BPM='60', StartDelayTime='4',
                         Length=str(largo), MissionID1=primera, MissionID2=segunda)
        self.listas = dict(self.fila)
        self.bpm, self.inicio, self.dur, self.ventana = 60., 4., 64., 4.
        golpes = N.golpes(self.fila, self.inicio, self.bpm)
        self.misiones = [dict(n=1, t=4., ventana=4., flechas=sum(g['flechas'] for g in golpes),
                             space=sum(g['space'] for g in golpes), tanda2=segunda!='0',
                             largo_t=largo, largo=float(largo), grupo=0)]
        self.padre = SimpleNamespace(sucias=set(), v_descanso=Valor(False),
                                     ultimos_spaces=(), ultimos_inv=(), ultimos_suave=(),
                                     ultimos_ritmos=(), recortes={})
        self.secciones, self.quitados, self.repes, self.frases, self.grupos = [], [], set(), [], []
        self.original, self.guardado, self.sonando = False, True, False
        self.rej = dict(graves=[], fin_beat=64.)
        self.info, self.lbl_cab, self.lienzo = Etiqueta(), Etiqueta(), Lienzo()
        self.v0, self.v1, self.cabeza = 0., 64., 1
        self.desde, self.t0 = 4., 0.
        self.after = Mock()

    def __getattr__(self, nombre):
        metodo = getattr(estudio.VentanaEntera, nombre)
        return MethodType(metodo, self) if callable(metodo) else metodo

    def _con_zoom(self): return False
    def _t_de_x(self, x): return x
    def _x(self, t): return t
    def _reloj(self, t): return '%.2f' % t
    def _reloj_fino(self, t): return '%.2f' % t
    def secciones_del_mapa(self): return self.secciones
    def parar(self): self.sonando = False

    def hover(self, t):
        self.sonando = False
        self.encima(SimpleNamespace(x=t))
        return self.info.texto

    def reproduciendo(self, t):
        self.sonando, self.desde, self.t0 = True, t, 0.
        with patch.object(estudio.time, 'time', return_value=0.): self._mover()
        self.sonando = False
        return self.info.texto

    def bloques(self):
        self._dibujar()
        return [f for f in self.lienzo.figuras if f['tipo']=='rect'
                and len(f['coords'])==4 and f['coords'][1] in (70, 75)]


class MapaSpaceTests(unittest.TestCase):
    def assert_solo_space(self, texto):
        self.assertIn('SOLO SPACE', texto.upper())
        self.assertNotIn('CALLADA', texto.upper())
        self.assertNotIn('NO ENTRA NINGUNA', texto.upper())

    def test_cabecera_cuenta_misiones_solo_space_como_activas(self):
        mapa = Mapa()
        mapa._texto_cabecera()
        self.assert_solo_space(mapa.lbl_cab.texto)

    def test_hover_muestra_cuatro_space_y_no_silencio(self):
        mapa = Mapa()
        texto = mapa.hover(4.5)
        self.assert_solo_space(texto)
        self.assertIn('4 SPACE', texto)

    def test_hover_segunda_tanda_de_space_permanece_dentro_de_la_mision(self):
        mapa = Mapa(segunda='1')
        texto = mapa.hover(9.)
        self.assert_solo_space(texto)
        self.assertIn('8 SPACE', texto)
        self.assertIn('2 tandas', texto)
        self.assertNotIn('entre misiones', texto.lower())

    def test_reproduccion_space_no_lleva_etiqueta_callada(self):
        mapa = Mapa()
        texto = mapa.reproduciendo(4.5)
        self.assert_solo_space(texto)
        self.assertIn('4 SPACE', texto)

    def test_reproduccion_segunda_tanda_muestra_los_ocho_space(self):
        mapa = Mapa(segunda='1')
        texto = mapa.reproduciendo(9.)
        self.assert_solo_space(texto)
        self.assertIn('8 SPACE', texto)
        self.assertNotIn('entre misiones', texto.lower())

    def test_space_heredado_sin_marca_manual_es_turquesa(self):
        mapa = Mapa()
        bloques = mapa.bloques()
        self.assertEqual(len(bloques), 1)
        self.assertEqual(bloques[0]['fill'], '#2bb3a3')
        self.assertIsNone(mapa._marca_de(mapa.misiones[0]))

    def test_las_dos_tandas_de_space_son_turquesas(self):
        mapa = Mapa(segunda='1')
        bloques = mapa.bloques()
        self.assertEqual(len(bloques), 2)
        self.assertEqual({b['fill'] for b in bloques}, {'#2bb3a3'})

    def test_marca_legacy_de_quitado_no_oculta_los_space_que_realmente_existen(self):
        mapa = Mapa()
        mapa.quitados = [(4., 8.)]
        self.assertTrue(mapa._quitada(mapa.misiones[0]))
        self.assertEqual(mapa.bloques()[0]['fill'], '#2bb3a3')
        self.assert_solo_space(mapa.hover(4.5))

    def test_patron_manual_con_flechas_conserva_su_color(self):
        mapa = Mapa(primera='157')
        mapa.secciones = [dict(tipo='patron', desde=4., hasta=8.)]
        self.assertEqual(mapa.bloques()[0]['fill'], '#b179e3')
        self.assertNotIn('SOLO SPACE', mapa.hover(4.5).upper())

    def test_mision_mixta_no_se_etiqueta_solo_space(self):
        mapa = Mapa(primera='126')  # una flecha y tres SPACE
        texto = mapa.hover(4.5)
        self.assertIn('3 SPACE', texto)
        self.assertNotIn('SOLO SPACE', texto.upper())
        self.assertNotIn('CALLADA', texto.upper())
        self.assertNotEqual(mapa.bloques()[0]['fill'], '#2bb3a3')

    def test_descanso_explicito_sigue_sin_misiones(self):
        mapa = Mapa()
        mapa.secciones = [dict(tipo='descanso', desde=16., hasta=24.)]
        texto = mapa.hover(18.)
        self.assertIn('DESCANSO SIN MISIONES', texto)
        self.assertIn('no salen flechas ni SPACE', texto)

    def test_cola_larga_no_llama_descanso_a_la_mision_space(self):
        mapa = Mapa(largo=32)
        texto = mapa.hover(4.5)
        self.assert_solo_space(texto)
        self.assertNotIn('(descanso)', texto.lower())
        self.assertIn('después', texto.lower())

    def test_colores_y_textos_no_modifican_los_datos_ni_golpes_space(self):
        mapa = Mapa(segunda='1')
        antes = copy.deepcopy(mapa.listas)
        golpes = N.golpes(mapa.listas, mapa.inicio, mapa.bpm)
        mapa._texto_cabecera(); mapa.bloques(); mapa.hover(9.); mapa.reproduciendo(9.)
        self.assertEqual(mapa.listas, antes)
        self.assertEqual(N.golpes(mapa.listas, mapa.inicio, mapa.bpm), golpes)
        self.assertEqual(sum(g['space'] for g in golpes), 8)


if __name__ == '__main__': unittest.main()
