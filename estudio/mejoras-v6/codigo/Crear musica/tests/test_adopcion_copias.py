"""Caso de Trapped: adoptar un original protegido en una copia con otro bkg."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo as N
import secciones as S
from test_adopcion_estudio import Panel
from test_adoptar_version import fila
from test_bpm import Valor


class AdopcionCopiasTest(unittest.TestCase):
    def setUp(self):
        temporal=tempfile.TemporaryDirectory();self.addCleanup(temporal.cleanup)
        self.panel=Panel(temporal.name)
        self.originales=[fila(4152,bpm=145,estrellas=4,filename='bkg10213',inicio='6.574'),
                         fila(4153,bpm=290,estrellas=10,filename='bkg10213',inicio='6.574')]
        self.destino=fila(9052,bpm=290,estrellas=6,filename='bkg2824',inicio='6.574')
        self.ajena=fila(9900,bpm=290,estrellas=10,filename='bkg-ajeno',inicio='6.574')
        for f in self.originales+[self.ajena]:f['Title']='Trapped'
        self.destino.update(Title='Trapped (copia)',SoundSourceSN='9052')
        p=self.panel
        p.tabla.filas=self.originales+[self.destino,self.ajena]
        p.tabla.por_id=lambda id_:next((f for f in p.tabla.filas if str(f['ID'])==str(id_)),None)
        p.filas_enviadas={f['ID']:copy.deepcopy(f) for f in p.tabla.filas}
        self.elegir_destino(self.destino)
        self.copias={'9052':'4153'}
        protegido=patch.object(N,'es_original',side_effect=lambda f:f['Filename'] in ('bkg10213','bkg-ajeno'))
        registro=patch.object(N,'_copias',side_effect=lambda:copy.deepcopy(self.copias))
        protegido.start();registro.start()
        self.addCleanup(protegido.stop);self.addCleanup(registro.stop)

    def elegir_destino(self,d):
        p=self.panel;p.pareja=[d]
        p.spins={d['ID']:(Valor(int(d['Difficulty'])),None,Valor('x1'))}
        p.bpms={d['ID']:float(d['BPM'])};p.gen_fila={d['ID']:Valor(True)}

    def plan(self,origen='4153'):
        return self.panel._preparar_adopcion(self.panel.pareja[0]['ID'],origen,6)

    def test_copia_unica_encuentra_las_dos_dificultades_originales(self):
        p=self.panel
        fuentes=p._fuentes_adopcion(self.destino)
        self.assertEqual([f['ID'] for f in fuentes],['4152','4153'])
        self.assertEqual([f['Filename'] for f in fuentes],['bkg10213']*2)
        self.assertEqual(len(p.pareja),1)

    def test_preparar_es_inmutable_y_muestra_ambos_bkg(self):
        p=self.panel;antes=copy.deepcopy(p.tabla.filas)
        plan=self.plan()
        self.assertEqual(p.tabla.filas,antes)
        self.assertFalse(list(p.carpeta.iterdir()))
        self.assertIn('bkg10213',plan['texto_resumen']);self.assertIn('bkg2824',plan['texto_resumen'])
        self.assertEqual(plan['origen_previo'],self.originales[1])
        self.assertEqual(plan['adopcion']['origen']['ID'],'4153')
        self.assertEqual(plan['adopcion']['origen']['Filename'],'bkg2824')

    def test_adoptar_10_a_6_conserva_originales_e_identidad_copia(self):
        p=self.panel;originales=copy.deepcopy(self.originales);ajena=copy.deepcopy(self.ajena)
        plan=self.plan();p._aplicar_adopcion(plan)
        self.assertEqual(self.originales,originales);self.assertEqual(self.ajena,ajena)
        self.assertEqual(len(p.tabla.filas),4)
        self.assertEqual(self.destino['ID'],'9052');self.assertEqual(self.destino['SoundSourceSN'],'9052')
        self.assertEqual(self.destino['Filename'],'bkg2824');self.assertEqual(self.destino['BPM'],'290')
        self.assertEqual(self.destino['Difficulty'],'6')
        self.assertEqual(self.destino['Length'],originales[1]['Length'])
        self.assertEqual(self.destino['StartDelayTime'],originales[1]['StartDelayTime'])
        self.assertEqual(N.patron(self.destino['MissionID1'].split(',')[0]),[2,0,2,1])
        self.assertEqual(p.sucias,{'9052'})

    def test_regenerar_y_recargar_no_necesita_reabrir_original(self):
        p=self.panel;p._aplicar_adopcion(self.plan());adoptada=copy.deepcopy(self.destino)
        cfg=p.config_secciones(self.destino)
        self.copias.clear()
        self.originales[1]['MissionID1']=','.join(['157']*4)
        nuevo,_=N.generar(self.destino,dict(bpm=290.,dur=300.),6,cfg['inicio'],bpm=290.,adopcion=cfg['adopcion'])
        for c in S.LISTAS+('StartDelayTime',):self.assertEqual(nuevo[c],adoptada[c],c)
        self.assertEqual(p.config_secciones(self.destino)['adopcion'],cfg['adopcion'])

    def test_fuente_de_145_adapta_a_290_sin_cambiar_bpm_del_destino(self):
        p=self.panel;plan=self.plan('4152');p._aplicar_adopcion(plan)
        self.assertFalse(plan['resumen']['mismo_bpm'])
        self.assertNotEqual(self.destino['Length'],self.originales[0]['Length'])
        self.assertEqual(self.destino['BPM'],'290')

    def test_mismo_titulo_sin_vinculo_se_rechaza(self):
        p=self.panel;antes=copy.deepcopy(p.tabla.filas)
        with self.assertRaisesRegex(ValueError,'vinculada'):self.plan('9900')
        self.assertEqual(p.tabla.filas,antes)
        self.assertFalse(p.sucias);self.assertFalse(list(p.carpeta.iterdir()))

    def test_cambiar_vinculo_invalida_plan_sin_escribir(self):
        p=self.panel;plan=self.plan();antes=copy.deepcopy(p.tabla.filas)
        self.copias['9052']='9900'
        with self.assertRaises(ValueError):p._aplicar_adopcion(plan)
        self.assertEqual(p.tabla.filas,antes)
        self.assertFalse(list(p.carpeta.iterdir()))

    def test_original_protegido_no_puede_ser_destino(self):
        p=self.panel;self.elegir_destino(self.originales[1]);antes=copy.deepcopy(p.tabla.filas)
        with self.assertRaisesRegex(ValueError,'protegida'):self.plan('9052')
        self.assertEqual(p.tabla.filas,antes);self.assertFalse(list(p.carpeta.iterdir()))

    def test_copia_de_copia_puede_adoptar_original(self):
        p=self.panel
        otra=fila(9053,bpm=290,estrellas=6,filename='bkg2825',inicio='6.574')
        p.tabla.filas.append(otra);self.copias['9053']='9052';self.elegir_destino(otra)
        antes=copy.deepcopy(self.originales)
        p._aplicar_adopcion(self.plan())
        self.assertEqual(otra['ID'],'9053');self.assertEqual(otra['Filename'],'bkg2825')
        self.assertEqual(N.patron(otra['MissionID1'].split(',')[0]),[2,0,2,1])
        self.assertEqual(self.originales,antes)


if __name__=='__main__':unittest.main()
