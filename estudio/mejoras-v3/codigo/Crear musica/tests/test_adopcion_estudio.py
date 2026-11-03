"""Adopción desde el panel: estado real, persistencia y cambios concurrentes."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nucleo as N
import secciones as S
from adopcion_estudio import AdopcionVersiones, descansos_configuracion
from test_adoptar_version import fila, codificar
from test_bpm import Valor


class Panel(AdopcionVersiones):
    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)
        self.pareja = [fila(1), fila(2, estrellas=6), fila(3, estrellas=4)]
        self.tabla = SimpleNamespace(filas=self.pareja,
            por_id=lambda id_: next((f for f in self.pareja if f['ID']==str(id_)), None))
        self.trabajando = False
        self.recortes = {}
        self.spins = {f['ID']:(Valor(int(f['Difficulty'])), None, Valor('x1')) for f in self.pareja}
        self.bpms = {f['ID']:float(f['BPM']) for f in self.pareja}
        self.gen_fila = {f['ID']:Valor(True) for f in self.pareja}
        self.filas_enviadas = {f['ID']:copy.deepcopy(f) for f in self.pareja}
        self.sucias, self.modificadas = set(), set()
        self.b_enviar = Mock()
        self._pintar_arreglar, self._pintar_revision, self.pintar_lista = Mock(), Mock(), Mock()
        self._resultado_adopcion = Mock()
        self.mapas = []

    def _mapas_adopcion(self): return self.mapas
    def bpm_de_fila(self, id_): return self.bpms[str(id_)]
    def config_secciones(self, f):
        return S.cargar_configuracion(self.carpeta, f['Filename']+':'+f['ID'])
    def guardar_secciones(self, f, secciones, inicio, misiones=None, adopcion=S.CONSERVAR_ADOPCION):
        S.guardar_configuracion(self.carpeta, f['Filename']+':'+f['ID'], secciones,
                                inicio=inicio, misiones=misiones, adopcion=adopcion)


class AdopcionPanelTest(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.panel=Panel(t.name)
        parche=patch.object(N,'es_original',return_value=False)
        parche.start();self.addCleanup(parche.stop)

    def plan(self, estrellas=6): return self.panel._preparar_adopcion('2','1',estrellas)

    def test_preparar_no_modifica_filas_preferencias_ni_pendientes(self):
        p=self.panel;antes=copy.deepcopy(p.pareja)
        plan=self.plan()
        self.assertEqual(p.pareja,antes)
        self.assertFalse(list(p.carpeta.iterdir()))
        self.assertFalse(p.sucias)
        self.assertEqual(plan['resumen']['tope_flechas'],2)
        self.assertIn('Mismo BPM',plan['texto_resumen'])

    def test_aplicar_cambia_solo_destino_conserva_identidad_y_marca_envio(self):
        p=self.panel;antes=copy.deepcopy(p.pareja)
        p._aplicar_adopcion(self.plan())
        self.assertEqual(len(p.pareja),3)
        self.assertEqual(p.pareja[0],antes[0]);self.assertEqual(p.pareja[2],antes[2])
        d=p.pareja[1]
        for c in ('ID','Filename','Title','Singer','BPM','Difficulty','Second'):
            self.assertEqual(d[c],antes[1][c],c)
        self.assertEqual(N.patron(d['MissionID1'].split(',')[0]),[2,0,2,1])
        self.assertEqual(d['Length'],antes[0]['Length'])
        self.assertEqual(d['StartDelayTime'],antes[0]['StartDelayTime'])
        self.assertEqual(p.sucias,{'2'})
        self.assertEqual({k:v.get() for k,v in p.gen_fila.items()},{'1':False,'2':True,'3':False})

    def test_estrellas_manuales_permiten_adoptar_triples_en_destino_alto(self):
        p=self.panel;p._aplicar_adopcion(self.plan(9))
        self.assertEqual(p.pareja[1]['Difficulty'],'9')
        self.assertEqual(p.spins['2'][0].get(),9)
        self.assertEqual(N.patron(p.pareja[1]['MissionID1'].split(',')[0]),[3,0,2,1])
        self.assertEqual(p.pareja[1]['CutOff'],str(N.cutoff_de(9)))

    def test_destino_usa_bpm_efectivo_y_remapea_geometria(self):
        p=self.panel;p.bpms['2']=120
        plan=self.plan();p._aplicar_adopcion(plan)
        self.assertEqual(p.pareja[1]['BPM'],'120')
        self.assertNotEqual(p.pareja[1]['Length'],p.pareja[0]['Length'])
        self.assertIn('BPM distintos',plan['texto_resumen'])
        self.assertFalse(plan['resumen']['mismo_bpm'])

    def test_nueva_base_reemplaza_ajustes_previos_del_destino(self):
        p=self.panel
        p.guardar_secciones(p.pareja[1],[dict(tipo='patron',desde=0.,hasta=300.,
            primera=[1,1,1,1],segunda=None,bolsa=1)],0.,
            misiones=[dict(tipo='reemplazar',tiempo=7.25,primera=[1]*4,segunda=None,bolsa=2)])
        p._aplicar_adopcion(self.plan())
        cfg=p.config_secciones(p.pareja[1])
        self.assertEqual(cfg['secciones'],[]);self.assertEqual(cfg['misiones'],[])
        self.assertEqual(cfg['adopcion']['origen'],p.pareja[0])

    def test_regenerar_tras_recargar_conserva_adopcion_independiente_del_origen(self):
        p=self.panel;p._aplicar_adopcion(self.plan())
        adoptada=copy.deepcopy(p.pareja[1]);cfg=p.config_secciones(adoptada)
        p.pareja[0]['MissionID1']=','.join([codificar([1]*4)]*4)
        nuevos,_=N.generar(adoptada,dict(bpm=240.,dur=300.),6,cfg['inicio'],bpm=240,
                           adopcion=cfg['adopcion'])
        for c in S.LISTAS+('StartDelayTime',): self.assertEqual(nuevos[c],adoptada[c],c)

    def test_rechaza_vista_previa_si_cambia_origen_destino_o_bpm_panel(self):
        for cambio in ('origen','destino','bpm','estrellas_panel','cfg'):
            with self.subTest(cambio=cambio):
                p=self.panel;plan=self.plan()
                if cambio=='origen': p.pareja[0]['Title']+=' nuevo'
                elif cambio=='destino': p.pareja[1]['Title']+=' nuevo'
                elif cambio=='bpm': p.bpms['2']=120
                elif cambio=='estrellas_panel': p.spins['2'][0].set(7)
                else: p.guardar_secciones(p.pareja[1],[],1.)
                antes=copy.deepcopy(p.pareja)
                with self.assertRaisesRegex(ValueError,'vista previa'):
                    p._aplicar_adopcion(plan)
                self.assertEqual(p.pareja,antes)
                self.assertFalse(p.sucias)

    def test_fallo_guardado_no_modifica_chart_ni_pendientes(self):
        p=self.panel;plan=self.plan();antes=copy.deepcopy(p.pareja)
        with patch.object(p,'guardar_secciones',side_effect=OSError('disco')):
            with self.assertRaises(OSError):p._aplicar_adopcion(plan)
        self.assertEqual(p.pareja,antes);self.assertFalse(p.sucias)
        self.assertFalse(list(p.carpeta.iterdir()))

    def test_rechaza_cancion_distinta_y_proteccion_original(self):
        p=self.panel
        p.pareja[0]['Filename']='otro-bkg'
        with self.assertRaises(ValueError):self.plan()
        p.pareja[0]['Filename']=p.pareja[1]['Filename']
        with patch.object(N,'es_original',return_value=True):
            with self.assertRaisesRegex(ValueError,'protegida'):self.plan()

    def test_no_pisa_mapa_con_cambios_sin_generar(self):
        p=self.panel;origen=p.pareja[0]
        listas=dict(origen,MissionID1=','.join(['157']*4))
        p.mapas=[SimpleNamespace(fila=origen,listas=listas,bpm=240.)]
        with self.assertRaisesRegex(ValueError,'sin generar'):self.plan()
        self.assertFalse(list(p.carpeta.iterdir()))

    def test_no_adopta_un_mapa_con_repeticion_marcada_sin_generar(self):
        p=self.panel;f=p.pareja[0]
        p.mapas=[SimpleNamespace(fila=f,listas=copy.deepcopy(f),bpm=240.,
                                repes={0},guardado=False)]
        with self.assertRaisesRegex(ValueError,'sin generar'):self.plan()

    def test_marcas_anteriores_no_cambian_chart_adoptado_al_regenerar(self):
        p=self.panel
        p.ultimas_repes=p.ultimos_spaces=p.ultimos_inv=p.ultimos_suave=((7.25,11.25),)
        p.ultimos_mudos=((11.25,15.25),)
        p.ultimos_ritmos=(7.25,15.25)
        p.ultimas_frases=(7.25,15.25)
        p.v_frases,p.v_descanso=Valor(True),Valor(True)
        p._aplicar_adopcion(self.plan())
        d=p.pareja[1];cfg=p.config_secciones(d)
        nuevo,_=N.generar(d,dict(bpm=240.,dur=300.),6,cfg['inicio'],bpm=240.,
                           adopcion=cfg['adopcion'],mudos=p.ultimos_mudos,
                           repetir=p.ultimas_repes,solo_space=p.ultimos_spaces,
                           invertir=p.ultimos_inv,suave=p.ultimos_suave)
        for c in S.LISTAS+('StartDelayTime',):self.assertEqual(nuevo[c],d[c],c)
        self.assertFalse(p.v_frases.get());self.assertFalse(p.v_descanso.get())

    def test_recorte_o_trabajo_pendiente_bloquean_preparacion(self):
        p=self.panel;p.trabajando=True
        with self.assertRaises(ValueError):self.plan()
        p.trabajando=False;p.recortes[p.pareja[0]['Filename']]={}
        with self.assertRaisesRegex(ValueError,'recorte'):self.plan()

    def test_quitar_adopcion_conserva_chart_actual_y_ediciones_posteriores(self):
        p=self.panel;p._aplicar_adopcion(self.plan());actual=copy.deepcopy(p.pareja)
        d=p.pareja[1];cfg=p.config_secciones(d)
        accion=dict(tipo='reemplazar',tiempo=7.25,primera=[1]*4,segunda=None,bolsa=1)
        p.guardar_secciones(d,[],cfg['inicio'],misiones=[accion])
        p.quitar_adopcion('2')
        self.assertIsNone(p.config_secciones(d)['adopcion'])
        self.assertEqual(p.config_secciones(d)['misiones'],[accion])
        self.assertEqual(p.pareja,actual)


class DescansosConfiguracionTest(unittest.TestCase):
    def test_descansos_heredados_se_desplazan_y_no_se_duplican(self):
        a=dict(tipo='descanso',desde=12.,hasta=16.)
        cfg=dict(inicio=4.,secciones=[a],adopcion=dict(inicio=0.,descansos=[dict(a,desde=8.,hasta=12.)]))
        antes=copy.deepcopy(cfg)
        self.assertEqual(descansos_configuracion(cfg),[a])
        self.assertEqual(cfg,antes)

    def test_mover_ancla_antes_del_audio_recorta_intervalos_negativos(self):
        cfg=dict(inicio=0.,secciones=[],adopcion=dict(inicio=10.,descansos=[
            dict(tipo='descanso',desde=5.,hasta=8.),dict(tipo='descanso',desde=9.,hasta=12.)]))
        self.assertEqual(descansos_configuracion(cfg),[dict(tipo='descanso',desde=0.,hasta=2.)])


if __name__=='__main__': unittest.main()
