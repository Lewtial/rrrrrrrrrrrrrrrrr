"""Adopción pura: geometría, SPACE, límites y remapeo entre BPM."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adoptar_version import adoptar_version, limite_por_nivel
from secciones import LISTAS


def codificar(patron):
    return str(1+sum(a*b for a,b in zip(patron,(125,25,5,1))))


def patron(codigo):
    n=int(codigo)-1
    return [0]*4 if n<0 else [n//125,(n//25)%5,(n//5)%5,n%5]


def fila(id_=1, bpm=240, estrellas=10, largos=(16,16,16,16), primera=None,
         segunda=None, inicio='7.25', filename='bkg-hypno'):
    n=len(largos)
    resultado={c:','.join(str(100*k+i) for i in range(n)) for k,c in enumerate(LISTAS)}
    resultado.update(ID=str(id_), Filename=filename, Title='Hypno', Singer='Fixture',
                     BPM=str(bpm), Difficulty=str(estrellas), StartDelayTime=inicio,
                     Length=','.join(map(str,largos)),
                     MissionID1=','.join(primera or [codificar([3,0,2,1])]*n),
                     MissionID2=','.join(segunda or ['0']*n),
                     KeyPatternID=','.join(str(1+i%4) for i in range(n)),
                     MissionCameraID=','.join(['101']+['0']*(n-1)),
                     DanceCameraID=','.join(['111']*(n-1)+['241']),
                     Second='300', CutOff='70000', Popularity='43')
    return resultado


def tiempos(f, bpm):
    t=float(f['StartDelayTime'])
    salida=[]
    for l in f['Length'].split(','):
        salida.append(t)
        t+=int(l)*60/bpm
    return salida,t


class LimitesAdopcionTest(unittest.TestCase):
    def test_limites_del_usuario_en_fronteras(self):
        for estrellas in (4,5,6):
            for bpm, esperado in ((100,3),(220,3),(220.01,2),(225,2),(229.99,2),(230,2),(300,2)):
                with self.subTest(estrellas=estrellas,bpm=bpm):
                    self.assertEqual(limite_por_nivel(estrellas,bpm),esperado)

    def test_niveles_iniciales_y_profesionales(self):
        for s in (1,2,3):
            self.assertEqual(limite_por_nivel(s,120),2)
        for s in (7,8):
            self.assertEqual(limite_por_nivel(s,229),3)
            self.assertEqual(limite_por_nivel(s,230),2)
        for s in (9,10):
            self.assertEqual(limite_por_nivel(s,320),3)

    def test_rechaza_estrellas_y_bpm_invalidos(self):
        for s,b in ((0,120),(11,120),(True,120),(5,0),(5,float('nan')),(5,float('inf'))):
            with self.subTest(s=s,b=b),self.assertRaises(ValueError):
                limite_por_nivel(s,b)


class AdoptarVersionTest(unittest.TestCase):
    def setUp(self):
        self.origen=fila()
        self.destino=fila(2,estrellas=6,primera=['157']*4)

    def test_mismo_bpm_preserva_geometria_y_columnas_auxiliares(self):
        originales=copy.deepcopy((self.origen,self.destino))
        nuevos,info=adoptar_version(self.origen,self.destino)
        for c in LISTAS:
            if c not in ('MissionID1','MissionID2'):
                self.assertEqual(nuevos[c],self.origen[c],c)
        self.assertEqual(nuevos['StartDelayTime'],self.origen['StartDelayTime'])
        self.assertEqual(tiempos(nuevos,240),tiempos(self.origen,240))
        self.assertEqual((self.origen,self.destino),originales)
        self.assertTrue(info['mismo_bpm'])
        self.assertEqual(info['error_max_segundos'],0)
        self.assertEqual(info['misiones_omitidas'],0)

    def test_capa_ambas_tandas_sin_cambiar_space_ni_su_ausencia(self):
        self.origen['MissionID2']=','.join(['0','1',codificar([0,3,2,0]),codificar([3,0,3,1])])
        nuevos,info=adoptar_version(self.origen,self.destino)
        for col in ('MissionID1','MissionID2'):
            for antes,despues in zip(self.origen[col].split(','),nuevos[col].split(',')):
                self.assertEqual([x==0 for x in patron(antes)],[x==0 for x in patron(despues)])
                self.assertLessEqual(max(patron(despues)),2)
        self.assertEqual(nuevos['MissionID2'].split(',')[:2],['0','1'])
        self.assertEqual(info['grupos_reducidos'],7)
        self.assertEqual(info['flechas_retiradas'],7)

    def test_no_sortea_ni_reordena_casilleros(self):
        nuevos,_=adoptar_version(self.origen,self.destino)
        self.assertEqual(nuevos['MissionID1'],','.join([codificar([2,0,2,1])]*4))
        self.assertEqual(adoptar_version(self.origen,self.destino),adoptar_version(self.origen,self.destino))

    def test_estrellas_manuales_actualizan_solo_difficulty(self):
        nuevos,info=adoptar_version(self.origen,self.destino,estrellas=10)
        self.assertEqual(nuevos['Difficulty'],'10')
        self.assertEqual(nuevos['MissionID1'],self.origen['MissionID1'])
        self.assertEqual(info['tope_flechas'],3)
        self.assertEqual(set(nuevos),set(LISTAS)|{'StartDelayTime','Difficulty'})
        self.assertNotIn('BPM',nuevos)
        self.assertNotIn('ID',nuevos)
        self.assertNotIn('Title',nuevos)
        self.assertNotIn('CutOff',nuevos)
        self.assertEqual(self.destino['Difficulty'],'6')

    def test_bpm_220_permite_triples_y_bpm230_los_recorta(self):
        for bpm,tope in ((220,3),(230,2)):
            origen=fila(bpm=bpm)
            destino=fila(2,bpm=bpm,estrellas=6)
            nuevos,info=adoptar_version(origen,destino)
            self.assertEqual(max(patron(nuevos['MissionID1'].split(',')[0])),tope)
            self.assertEqual(info['tope_flechas'],tope)

    def test_limite_explicito_puede_ser_mas_bajo_nunca_superar_nivel(self):
        nuevos,_=adoptar_version(self.origen,self.destino,limite_flechas=1)
        self.assertEqual(patron(nuevos['MissionID1'].split(',')[0]),[1,0,1,1])
        for invalido in (0,3,4,True):
            with self.subTest(invalido=invalido),self.assertRaises(ValueError):
                adoptar_version(self.origen,self.destino,limite_flechas=invalido)

    def test_duplicar_bpm_conserva_segundos_y_recalcula_length(self):
        self.origen['BPM']='120'
        nuevos,info=adoptar_version(self.origen,self.destino)
        self.assertEqual(nuevos['Length'],'32,32,32,32')
        self.assertEqual(tiempos(nuevos,240),tiempos(self.origen,120))
        self.assertFalse(info['mismo_bpm'])
        self.assertEqual(info['error_max_segundos'],0)
        self.assertEqual(info['misiones_destino'],4)

    def test_reducir_bpm_recalcula_length_y_reporta_segundas_imposibles(self):
        self.destino['BPM']='120'
        self.origen['MissionID2']=','.join([codificar([0,3,1,2])]*4)
        nuevos,info=adoptar_version(self.origen,self.destino)
        self.assertEqual(nuevos['Length'],'8,8,8,8')
        self.assertEqual(nuevos['MissionID2'],'0,0,0,0')
        self.assertEqual(info['segundas_retiradas'],4)
        self.assertTrue(any('segundas tandas' in a for a in info['advertencias']))
        self.assertEqual(tiempos(nuevos,120),tiempos(self.origen,240))

    def test_bpm_no_multiplo_reporta_cada_desvio_y_fin(self):
        self.origen['BPM']='120'
        self.destino['BPM']='135'
        nuevos,info=adoptar_version(self.origen,self.destino)
        self.assertTrue(all(int(x)%4==0 for x in nuevos['Length'].split(',')))
        self.assertEqual(len(info['ajustes']),4)
        self.assertGreater(info['error_max_segundos'],0)
        for ajuste,t in zip(info['ajustes'],tiempos(nuevos,135)[0]):
            self.assertAlmostEqual(ajuste['inicio_destino'],t)
            self.assertAlmostEqual(ajuste['desvio_segundos'],t-ajuste['inicio_origen'])
        self.assertAlmostEqual(tiempos(nuevos,135)[1],info['fin_destino'])
        self.assertAlmostEqual(info['fin_origen'],tiempos(self.origen,120)[1])
        self.assertAlmostEqual(info['duracion_destino'],info['fin_destino']-info['inicio_destino'])

    def test_colisiones_omiten_mision_con_motivo_y_listas_alineadas(self):
        origen=fila(bpm=320,largos=(4,4,4,4,4,4,4,4))
        destino=fila(2,bpm=80,estrellas=6)
        nuevos,info=adoptar_version(origen,destino)
        self.assertGreater(info['misiones_omitidas'],0)
        self.assertTrue(any('mismo compás' in x['motivo'] for x in info['omisiones']))
        self.assertEqual(len({len(nuevos[c].split(',')) for c in LISTAS}),1)
        self.assertEqual(info['misiones_destino']+info['misiones_omitidas'],8)
        self.assertTrue(all(int(x)>=4 for x in nuevos['Length'].split(',')))

    def test_descansos_explicitos_se_respetan_por_ventana_completa(self):
        self.origen['BPM']='120'
        self.destino['BPM']='60'
        # La fuente entra a los7.25 y15.25. A60 la primera ventana llega11.25,
        # invadiendo un descanso que la fuente120 terminaba antes de cruzar.
        descansos=[dict(tipo='descanso',desde=10,hasta=12)]
        nuevos,info=adoptar_version(self.origen,self.destino,descansos=descansos)
        self.assertEqual(info['misiones_omitidas'],1)
        self.assertIn('descanso',info['omisiones'][0]['motivo'])
        for t in tiempos(nuevos,60)[0]:
            self.assertFalse(min(t+4,12)>max(t,10)+1e-4)
        self.assertEqual(float(nuevos['StartDelayTime']),15.25)

    def test_hueco_largo_inferido_no_se_rellena_al_cambiar_bpm(self):
        origen=fila(bpm=120,largos=(32,16,16))
        destino=fila(2,bpm=60,estrellas=6)
        nuevos,info=adoptar_version(origen,destino)
        descanso=info['descansos'][0]
        self.assertEqual(descanso,dict(tipo='descanso',desde=15.25,hasta=23.25))
        for t in tiempos(nuevos,60)[0]:
            self.assertFalse(min(t+4,descanso['hasta'])>max(t,descanso['desde'])+1e-4)
        self.assertEqual(tiempos(nuevos,60)[0],[7.25,23.25,31.25])

    def test_mismo_bpm_rechaza_descanso_inconsistente_sin_mutar(self):
        antes=copy.deepcopy((self.origen,self.destino))
        with self.assertRaisesRegex(ValueError,'invade un descanso'):
            adoptar_version(self.origen,self.destino,descansos=[dict(tipo='descanso',desde=7.5,hasta=9)])
        self.assertEqual((self.origen,self.destino),antes)

    def test_mismo_bpm_conserva_restos_tiempos_y_start_literal(self):
        origen=fila(largos=(32,16,48),inicio='007.250000')
        nuevos,info=adoptar_version(origen,self.destino)
        self.assertEqual(nuevos['Length'],'32,16,48')
        self.assertEqual(nuevos['StartDelayTime'],'007.250000')
        self.assertEqual(info['fin_origen'],info['fin_destino'])

    def test_mismo_bpm_conserva_literalmente_espacios_en_auxiliares(self):
        self.origen['Length']='16, 16,16,16 '
        self.origen['MissionDanceID']=' 51,52, 53,54 '
        self.origen['MissionID2']=' 0,0,0,0 '
        nuevos,_=adoptar_version(self.origen,self.destino)
        for campo in ('Length','MissionDanceID','MissionID2'):
            self.assertEqual(nuevos[campo],self.origen[campo])

    def test_redondeo_no_sobrepasa_duracion_conocida_del_audio(self):
        origen=fila(bpm=120,largos=(16,16))
        destino=fila(2,bpm=135,estrellas=6)
        origen['Second']=destino['Second']='23.3'
        nuevos,info=adoptar_version(origen,destino)
        self.assertLessEqual(tiempos(nuevos,135)[1],23.3)
        self.assertLessEqual(info['fin_destino'],23.3)

    def test_mismo_titulo_otro_bkg_se_rechaza(self):
        self.destino['Filename']='otro'
        with self.assertRaisesRegex(ValueError,'mismo archivo bkg'):
            adoptar_version(self.origen,self.destino)

    def test_no_adopta_la_misma_fila(self):
        with self.assertRaisesRegex(ValueError,'diferente'):
            adoptar_version(self.origen,self.origen)

    def test_lista_desalineada_o_patron_invalido_se_rechaza(self):
        for campo,valor in (('MissionID1','157'),('MissionID1','0,1,1,1'),('MissionID1','-1,1,1,1'),
                            ('MissionID2','900,0,0,0'),('KeyPatternID','5,4,4,4'),
                            ('Length','0,16,16,16'),('Length','2,16,16,16')):
            with self.subTest(campo=campo),self.assertRaises(ValueError):
                adoptar_version(dict(self.origen,**{campo:valor}),self.destino)

    def test_bpm_arranque_y_dificultad_invalidos_se_rechazan(self):
        for campo,valor in (('BPM','nan'),('BPM','inf'),('BPM','0'),('StartDelayTime','-1')):
            with self.subTest(campo=campo),self.assertRaises(ValueError):
                adoptar_version(dict(self.origen,**{campo:valor}),self.destino)
        for s in (0,11,True):
            with self.subTest(s=s),self.assertRaises(ValueError):
                adoptar_version(self.origen,self.destino,estrellas=s)

    def test_segunda_tanda_corta_en_fuente_no_se_oculta(self):
        origen=fila(largos=(8,16),segunda=['157','0'])
        with self.assertRaisesRegex(ValueError,'origen tiene segunda tanda'):
            adoptar_version(origen,self.destino)

    def test_todos_los_argumentos_se_conservan_con_descansos_y_limite(self):
        self.origen['BPM']='120'
        descansos=[dict(tipo='descanso',desde=100,hasta=110)]
        antes=copy.deepcopy((self.origen,self.destino,descansos))
        adoptar_version(self.origen,self.destino,descansos=descansos,limite_flechas=1)
        self.assertEqual((self.origen,self.destino,descansos),antes)


if __name__=='__main__': unittest.main()
