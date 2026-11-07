"""Subir de 6 a 10 cambia las flechas y el nivel real que se exporta."""
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
from test_adoptar_version import codificar, fila


def total_flechas(f):
    return sum(sum(N.patron(v)) for c in ('MissionID1','MissionID2')
               for v in f[c].split(',') if c=='MissionID1' or v!='0')


class SubidaEstudioTest(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.p=Panel(t.name)
        self.origen=fila(1,bpm=290,estrellas=6,
            primera=[codificar([2,0,1,2]),'1',codificar([1,2,2,0]),codificar([2,2,0,1])],
            segunda=[codificar([1,0,2,1]),'1','0',codificar([2,1,0,2])])
        self.destino=fila(2,bpm=290,estrellas=10)
        self.p.pareja=[self.origen,self.destino]
        self.p.tabla.filas=self.p.pareja
        self.p.spins['2'][0].set(10);self.p.bpms.update({'1':290.,'2':290.})
        self.p.filas_enviadas={f['ID']:copy.deepcopy(f) for f in self.p.pareja}
        for parche in (patch.object(N,'es_original',return_value=False),patch.object(N,'_copias',return_value={})):
            parche.start();self.addCleanup(parche.stop)

    def plan(self,modo=True):return self.p._preparar_adopcion('2','1',10,modo)

    def test_subida_por_defecto_aumenta_flechas_y_exporta_diez_estrellas(self):
        p=self.p;origen=copy.deepcopy(self.origen)
        plan=p._preparar_adopcion('2','1',10)
        self.assertTrue(plan['adopcion']['ajustar_nivel'])
        self.assertTrue(plan['resumen']['ajuste_subida'])
        self.assertGreater(plan['resumen']['grupos_aumentados'],0)
        self.assertGreater(plan['resumen']['triples_despues'],0)
        self.assertIn('Subida de 6 a 10 estrellas',plan['texto_resumen'])
        self.assertEqual(self.origen,origen)
        p._aplicar_adopcion(plan)
        self.assertEqual(self.destino['Difficulty'],'10');self.assertEqual(p.spins['2'][0].get(),10)
        self.assertEqual(self.destino['CutOff'],str(N.cutoff_de(10)))
        self.assertGreater(total_flechas(self.destino),total_flechas(origen))
        self.assertEqual(self.origen,origen)
        for c in ('MissionID1','MissionID2'):
            for a,b in zip(origen[c].split(','),self.destino[c].split(',')):
                if c=='MissionID2' and a=='0':self.assertEqual(b,'0')
                else:self.assertEqual([n==0 for n in N.patron(a)],[n==0 for n in N.patron(b)])
        self.assertEqual(p.sucias,{'2'})

    def test_desactivar_subida_copia_cantidades_sin_confundir_estrellas(self):
        p=self.p;plan=self.plan(False)
        self.assertFalse(plan['adopcion']['ajustar_nivel'])
        self.assertFalse(plan['resumen']['ajuste_subida'])
        self.assertIn('desactivado',plan['texto_resumen'])
        p._aplicar_adopcion(plan)
        self.assertEqual(self.destino['Difficulty'],'10')
        self.assertEqual(self.destino['MissionID1'],self.origen['MissionID1'])
        self.assertEqual(self.destino['MissionID2'],self.origen['MissionID2'])
        self.assertIs(p.config_secciones(self.destino)['adopcion']['ajustar_nivel'],False)

    def test_regenerar_conserva_subida_y_edicion_individual_posterior(self):
        p=self.p;p._aplicar_adopcion(self.plan())
        actual=copy.deepcopy(self.destino);cfg=p.config_secciones(self.destino)
        nuevo,_=N.generar(self.destino,dict(bpm=290.,dur=300.),10,cfg['inicio'],bpm=290.,adopcion=cfg['adopcion'])
        for c in S.LISTAS+('StartDelayTime',):self.assertEqual(nuevo[c],actual[c],c)
        accion=dict(tipo='reemplazar',tiempo=float(actual['StartDelayTime']),
                    primera=[1,0,1,1],segunda=None,bolsa=1)
        p.guardar_secciones(self.destino,[],cfg['inicio'],misiones=[accion])
        cfg=p.config_secciones(self.destino)
        nuevo,_=N.generar(self.destino,dict(bpm=290.,dur=300.),10,cfg['inicio'],bpm=290.,
                           adopcion=cfg['adopcion'],misiones=cfg['misiones'])
        self.assertEqual(N.patron(nuevo['MissionID1'].split(',')[0]),[1,0,1,1])
        self.assertEqual(nuevo['MissionID2'].split(',')[0],'0')

    def test_modo_no_booleano_se_rechaza_antes_de_guardar(self):
        for modo in (None,0,1,'true',[],{}):
            with self.subTest(modo=modo),self.assertRaisesRegex(ValueError,'aumentar'):
                self.plan(modo)
        self.assertFalse(list(self.p.carpeta.iterdir()))


if __name__=='__main__':unittest.main()
