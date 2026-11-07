"""Regeneración y escucha de una instantánea adoptada sin sortear otra vez."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nucleo as N
import secciones as S


def fuente(bpm='60'):
    f = {c:'0,0,0' for c in S.LISTAS}
    f.update(ID='100',Filename='bkgprueba',Title='Hypno',Difficulty='10',
             BPM=bpm,StartDelayTime='4',Second='100',Length='16,32,16',
             KeyPatternID='4,1,3',MissionID1='387,313,141',MissionID2='141,0,313',
             MissionDanceID='511,511,511',MissionSuccessDanceID='611,611,611',
             MissionFailDanceID='201,201,201',MissionCameraID='101,0,0',DanceCameraID='111,111,241')
    return f


def reemplazo(tiempo, primera=(3,3,3,3)):
    return dict(tipo='reemplazar', tiempo=tiempo, primera=list(primera), segunda=None, bolsa=4)


class GeneracionAdopcionTest(unittest.TestCase):
    def setUp(self):
        self.origen=fuente()
        self.destino=dict(fuente(), ID='200',Difficulty='6')
        self.rej=dict(bpm=60.,dur=100.,fin_beat=100.,ogg=None)
        self.cfg=dict(version=1,origen=copy.deepcopy(self.origen),inicio=4.,
                      descansos=[dict(tipo='descanso',desde=36.,hasta=52.)])

    def generar(self, **kwargs):
        return N.generar(self.destino,self.rej,6,kwargs.pop('inicio',4.),
                         adopcion=self.cfg,**kwargs)

    def test_regenerar_usa_snapshot_sin_sorteo_ni_redistribucion_automatica(self):
        antes=(copy.deepcopy(self.destino),copy.deepcopy(self.cfg))
        with mock.patch.object(N,'pozo',side_effect=AssertionError('no sortear')):
            nuevo,info=self.generar(por_musica=True,por_partes=True,menos_space=True)
        for c in S.LISTAS+('StartDelayTime',): self.assertEqual(nuevo[c],self.origen[c],c)
        self.assertEqual(info['misiones'],3)
        self.assertEqual(info['fin_chart'],68)
        self.assertEqual(info['adopcion']['misiones_destino'],3)
        self.assertEqual((self.destino,self.cfg),antes)
        self.assertNotIn('ID',nuevo)
        self.assertNotIn('Filename',nuevo)

    def test_tope_usa_estrellas_y_bpm_destino_y_conserva_ceros(self):
        self.cfg['origen']['BPM']='240'
        self.cfg['descansos']=[]
        self.destino['BPM']='240'
        nuevo,info=self.generar(bpm=240)
        self.assertEqual(N.patron(nuevo['MissionID1'].split(',')[0]),[2,0,2,1])
        self.assertEqual(nuevo['Length'],self.origen['Length'])
        self.assertEqual(nuevo['BPM'],'240')
        self.assertEqual(nuevo['Difficulty'],'6')
        self.assertEqual(info['adopcion']['tope_flechas'],2)

    def test_cambio_inicio_desplaza_chart_y_descansos_juntos(self):
        nuevo,info=self.generar(inicio=8.)
        self.assertEqual(float(nuevo['StartDelayTime']),8.)
        self.assertEqual(nuevo['Length'],'16,32,16')
        self.assertEqual(info['adopcion']['descansos'],[dict(tipo='descanso',desde=40.,hasta=56.)])

    def test_bpm_distinto_remapea_en_segundos_y_no_copia_length_crudo(self):
        nuevo,info=self.generar(bpm=120)
        self.assertEqual(nuevo['Length'],'32,64,32')
        self.assertEqual(float(nuevo['StartDelayTime']),4.)
        self.assertAlmostEqual(info['fin_chart'],68)
        self.assertFalse(info['adopcion']['mismo_bpm'])

    def test_borde_descanso_redondeado_no_elimina_primera_mision_adaptada(self):
        from test_adoptar_version import fila
        origen=fila(100,bpm=240,largos=(32,16,16),inicio='10.975123456789')
        destino=dict(origen,ID='200',BPM='60',Difficulty='6')
        cfg=dict(version=1,origen=origen,inicio=float(origen['StartDelayTime']),descansos=[])
        nuevo,info=N.generar(destino,dict(bpm=60.,dur=300.),6,cfg['inicio'],bpm=60.,adopcion=cfg)
        self.assertEqual(nuevo['Length'],'8,4,4')
        self.assertEqual(info['misiones'],3)
        self.assertAlmostEqual(float(nuevo['StartDelayTime']),cfg['inicio'])
        self.assertEqual(N.resumen_descansos(dict(destino,**nuevo),info['adopcion']['descansos'])['entradas_en_descanso'],0)

    def test_nuevo_descanso_quita_mision_y_edicion_cubierta_queda_inactiva(self):
        nuevo,info=self.generar(secciones=[dict(tipo='descanso',desde=20.,hasta=24.)],
                                 misiones=[reemplazo(20.)])
        self.assertEqual(nuevo['Length'],'48,16')
        self.assertEqual(len(nuevo['MissionID1'].split(',')),2)
        self.assertEqual(info['descansos_seccion'],1)

    def test_patron_manual_posterior_no_se_recorta_otra_vez(self):
        self.cfg['origen']['BPM']='240'
        self.cfg['descansos']=[]
        nuevo,_=self.generar(bpm=240,misiones=[reemplazo(4.)])
        self.assertEqual(N.patron(nuevo['MissionID1'].split(',')[0]),[3,3,3,3])

    def test_solo_space_e_invertir_se_aplican_a_base_sin_cambiar_geometria(self):
        nuevo,info=self.generar(solo_space=[(4.,8.)],invertir=[(20.,24.)])
        self.assertEqual(nuevo['MissionID1'].split(',')[0],'1')
        self.assertEqual(nuevo['MissionID2'].split(',')[0],'1')
        self.assertEqual(nuevo['Length'],self.origen['Length'])
        self.assertEqual(info['puro_space'],1)
        self.assertEqual(info['invertidas'],1)

    def test_repetir_fija_bolsa_y_casilleros_sin_space(self):
        nuevo,info=self.generar(repetir=[(20.,36.)])
        self.assertEqual(nuevo['KeyPatternID'].split(',')[1],'1')
        self.assertTrue(all(x>0 for x in N.patron(nuevo['MissionID1'].split(',')[1])))
        self.assertEqual(info['repes'],1)

    def test_solo_space_posterior_a_repetir_conserva_segunda_tanda_vacia(self):
        nuevo,_=self.generar(repetir=[(4.,20.)],solo_space=[(4.,8.)])
        self.assertEqual(nuevo['MissionID1'].split(',')[0],'1')
        self.assertEqual(nuevo['MissionID2'].split(',')[0],'1')

    def test_fin_no_finito_o_negativo_se_rechaza(self):
        for fin in (float('nan'),float('inf'),-1.,0.):
            with self.subTest(fin=fin),self.assertRaises(ValueError):
                self.generar(fin=fin)

    def test_recorte_fin_descarta_misiones_fuera_del_audio(self):
        nuevo,info=self.generar(fin=40)
        self.assertEqual(nuevo['Length'],'16,20')
        self.assertEqual(info['fin_chart'],40)
        self.assertEqual(info['misiones'],2)

    def test_previo_usa_las_mismas_flechas_adoptadas(self):
        with tempfile.TemporaryDirectory() as d:
            ogg=Path(d)/'audio.ogg';ogg.touch()
            with mock.patch.object(N,'armar_escucha') as escuchar:
                _,info=N.previo(self.destino,dict(self.rej,ogg=ogg),6,4.,segundos=8,
                                salida=Path(d)/'previo.wav',adopcion=self.cfg)
            self.assertEqual(info['misiones'],3)
            marcas=escuchar.call_args.args[1]
            self.assertEqual([g['flechas'] for g in marcas[:4]],[3,0,2,1])
            self.assertEqual([g['space'] for g in marcas[:4]],[0,1,0,0])

    def test_cuatro_previos_conservan_snapshot_y_desplazan_inicio(self):
        with tempfile.TemporaryDirectory() as d:
            cache=Path(d)
            def previo(*args,**kwargs):
                with wave.open(str(kwargs['salida']),'wb') as f:
                    f.setnchannels(1);f.setsampwidth(2);f.setframerate(N.SR_ESCUCHA);f.writeframes(b'\0\0'*8)
            with mock.patch.object(N,'CACHE',cache),mock.patch.object(N,'previo',side_effect=previo) as pre:
                N.probar_los_cuatro(self.destino,self.rej,6,[4,8,12,16],salida=cache/'todos.wav',adopcion=self.cfg)
            self.assertEqual([call.args[3] for call in pre.call_args_list],[4.,8.,12.,16.])
            self.assertTrue(all(call.kwargs['adopcion']==self.cfg for call in pre.call_args_list))

    def test_copiar_cancion_remapea_bkg_de_snapshot_sin_tocar_original(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);audio=base/'audio.ogg';audio.write_bytes(b'fixture')
            S.guardar_configuracion(base,'bkgprueba:200',[],inicio=4.,adopcion=self.cfg)
            tabla=SimpleNamespace(filas=[copy.deepcopy(self.destino)])
            funciones=dict(buscar_ogg=audio,_nombres_ocupados=set(),anotar_mia=None,
                           anotar_estilo=None,anotar_partes=None,anotar_menos_space=None,
                           anotar_copias=None,estilo_de='clasico',partes_de=False,menos_space_de=False,
                           correr_snb_local=SimpleNamespace(returncode=0,stdout='',stderr=''))
            from contextlib import ExitStack
            with ExitStack() as stack:
                for nombre,valor in dict(ESTUDIO=base,OGG_NUEVOS=base/'ogg',BKG_SNB=base/'snb').items():
                    stack.enter_context(mock.patch.object(N,nombre,valor))
                for nombre,valor in funciones.items(): stack.enter_context(mock.patch.object(N,nombre,return_value=valor))
                N.copiar_cancion(tabla,tabla.filas[:])
            nueva=tabla.filas[-1]
            cfg=S.cargar_configuracion(base,'%s:%s'%(nueva['Filename'],nueva['ID']))
            self.assertEqual(cfg['adopcion']['origen']['Filename'],nueva['Filename'])
            self.assertNotEqual(nueva['Filename'],'bkgprueba')
            self.assertEqual(cfg['adopcion']['origen']['ID'],'100')
            self.assertEqual(S.cargar_configuracion(base,'bkgprueba:200')['adopcion'],self.cfg)


if __name__ == '__main__': unittest.main()
