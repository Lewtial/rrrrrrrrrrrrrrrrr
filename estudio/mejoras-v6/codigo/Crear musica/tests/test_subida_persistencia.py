"""Subir una adopción de nivel se conserva, sin cambiar adopciones anteriores."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nucleo as N
import secciones as S
from test_adopcion_generacion import fuente


def snapshot(ajustar=None):
    origen=fuente('240')
    origen.update(Difficulty='6', MissionID1='262,1,157', MissionID2='262,0,1')
    resultado=dict(version=1,origen=origen,inicio=4.,
                   descansos=[dict(tipo='descanso',desde=12.,hasta=16.)])
    if ajustar is not None:resultado['ajustar_nivel']=ajustar
    return resultado


class PersistenciaSubidaTest(unittest.TestCase):
    def test_snapshot_antiguo_conserva_formato_sin_activar_opcion(self):
        cfg=snapshot()
        self.assertEqual(S.validar_adopcion(cfg),cfg)
        self.assertNotIn('ajustar_nivel',S.validar_adopcion(cfg))
        with tempfile.TemporaryDirectory() as carpeta:
            S.guardar_configuracion(carpeta,'bkgprueba:200',[],inicio=4.,adopcion=cfg)
            leido=S.cargar_configuracion(carpeta,'bkgprueba:200')['adopcion']
            self.assertEqual(leido,cfg)
            self.assertNotIn('ajustar_nivel',leido)

    def test_opcion_true_y_false_se_guardan_sin_cambiar_de_version(self):
        for valor in (True,False):
            with self.subTest(valor=valor),tempfile.TemporaryDirectory() as carpeta:
                cfg=snapshot(valor);antes=copy.deepcopy(cfg)
                S.guardar_configuracion(carpeta,'bkgprueba:200',[],inicio=4.,adopcion=cfg)
                S.guardar_configuracion(carpeta,'bkgprueba:200',[],inicio=4.,misiones=[])
                leido=S.cargar_configuracion(carpeta,'bkgprueba:200')['adopcion']
                self.assertEqual(leido,antes)
                self.assertIs(leido['ajustar_nivel'],valor)
                datos=json.loads((Path(carpeta)/S.ARCHIVO).read_text())
                self.assertEqual(datos['version'],3)
                self.assertEqual(cfg,antes)

    def test_opcion_no_booleana_se_rechaza_sin_pisar_preferencias(self):
        with tempfile.TemporaryDirectory() as carpeta:
            S.guardar_configuracion(carpeta,'bkgprueba:200',[],adopcion=snapshot())
            ruta=Path(carpeta)/S.ARCHIVO;antes=ruta.read_bytes()
            for valor in (None,0,1,'true','false',[],{}):
                with self.subTest(valor=valor),self.assertRaisesRegex(ValueError,'nivel'):
                    cfg=snapshot();cfg['ajustar_nivel']=valor
                    S.guardar_configuracion(carpeta,'bkgprueba:200',[],adopcion=cfg)
                self.assertEqual(ruta.read_bytes(),antes)

    def test_opcion_corrupta_al_leer_no_se_reemplaza_silenciosamente(self):
        with tempfile.TemporaryDirectory() as carpeta:
            S.guardar_configuracion(carpeta,'bkgprueba:200',[],adopcion=snapshot(True))
            ruta=Path(carpeta)/S.ARCHIVO;datos=json.loads(ruta.read_text())
            datos['charts']['bkgprueba:200']['adopcion']['ajustar_nivel']='true'
            ruta.write_text(json.dumps(datos));antes=ruta.read_bytes()
            with self.assertRaisesRegex(ValueError,'No pude leer'):
                S.guardar_configuracion(carpeta,'bkgprueba:200',[],adopcion=None)
            self.assertEqual(ruta.read_bytes(),antes)

    def test_nivel_origen_se_exige_solo_para_la_opcion_nueva(self):
        for valor in (None,'','0','11','6.5','NaN'):
            with self.subTest(valor=valor):
                cfg=snapshot(True)
                if valor is None:cfg['origen'].pop('Difficulty')
                else:cfg['origen']['Difficulty']=valor
                with self.assertRaisesRegex(ValueError,'estrellas'):S.validar_adopcion(cfg)
                cfg.pop('ajustar_nivel')
                self.assertEqual(S.validar_adopcion(cfg),cfg)


class GeneracionSubidaTest(unittest.TestCase):
    def setUp(self):
        self.destino=dict(fuente('240'),ID='200',Difficulty='10')
        self.rej=dict(bpm=240.,dur=100.,ogg=None)

    def generar(self,cfg,**opciones):
        return N.generar(self.destino,self.rej,10,4.,bpm=240.,adopcion=cfg,**opciones)

    def test_sin_opcion_y_false_conservan_cantidades_anteriores(self):
        antiguo,_=self.generar(snapshot())
        apagado,_=self.generar(snapshot(False))
        self.assertEqual(antiguo,apagado)
        for columna in ('MissionID1','MissionID2'):
            self.assertEqual(antiguo[columna],snapshot()['origen'][columna])

    def test_subida_regenerada_es_estable_y_conserva_space_y_geometria(self):
        cfg=snapshot(True);antes=copy.deepcopy(cfg)
        antiguo,_=self.generar(snapshot())
        nuevos,info=self.generar(cfg)
        repetido,otro_info=self.generar(cfg)
        self.assertEqual((nuevos,info),(repetido,otro_info))
        viejos_eventos=N.golpes(antiguo,4.,240.)
        eventos=N.golpes(nuevos,4.,240.)
        self.assertEqual([(e['t'],e['space']) for e in eventos],
                         [(e['t'],e['space']) for e in viejos_eventos])
        self.assertGreater(sum(e['flechas'] for e in eventos),sum(e['flechas'] for e in viejos_eventos))
        self.assertTrue(any(e['flechas']==3 for e in eventos))
        self.assertFalse(any(12.<=e['t']<16. for e in eventos))
        self.assertEqual(nuevos['Length'],antiguo['Length'])
        self.assertEqual(nuevos['StartDelayTime'],antiguo['StartDelayTime'])
        self.assertEqual(nuevos['Difficulty'],'10')
        for c in S.LISTAS:
            if c not in ('MissionID1','MissionID2'):self.assertEqual(nuevos[c],antiguo[c],c)
        self.assertEqual(cfg,antes)

    def test_edicion_manual_posterior_tiene_prioridad_sobre_subida(self):
        cfg=snapshot(True)
        accion=dict(tipo='reemplazar',tiempo=4.,primera=[1,0,1,0],segunda=None,bolsa=1)
        nuevo,_=self.generar(cfg,misiones=[accion])
        self.assertEqual(N.patron(nuevo['MissionID1'].split(',')[0]),[1,0,1,0])
        self.assertEqual(nuevo['MissionID2'].split(',')[0],'0')
        self.assertEqual(nuevo['KeyPatternID'].split(',')[0],'1')

    def test_escucha_recibe_las_mismas_cantidades_que_generar(self):
        cfg=snapshot(True);nuevo,_=self.generar(cfg)
        with tempfile.TemporaryDirectory() as carpeta:
            audio=Path(carpeta)/'audio.ogg';audio.touch()
            with mock.patch.object(N,'armar_escucha') as escuchar:
                N.previo(self.destino,dict(self.rej,ogg=audio),10,4.,bpm=240.,
                         segundos=20.,salida=Path(carpeta)/'previo.wav',adopcion=cfg)
            eventos=escuchar.call_args.args[1]
            self.assertEqual(eventos,N.golpes(nuevo,4.,240.))

    def test_copia_de_cancion_conserva_opcion_de_subida_y_original(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as carpeta:
            base=Path(carpeta);audio=base/'audio.ogg';audio.write_bytes(b'fixture')
            cfg=snapshot(True)
            S.guardar_configuracion(base,'bkgprueba:200',[],inicio=4.,adopcion=cfg)
            tabla=SimpleNamespace(filas=[copy.deepcopy(self.destino)])
            funciones=dict(buscar_ogg=audio,_nombres_ocupados=set(),anotar_mia=None,
                           anotar_estilo=None,anotar_partes=None,anotar_menos_space=None,
                           anotar_copias=None,estilo_de='clasico',partes_de=False,menos_space_de=False,
                           correr_snb_local=SimpleNamespace(returncode=0,stdout='',stderr=''))
            with ExitStack() as pila:
                for nombre,valor in dict(ESTUDIO=base,OGG_NUEVOS=base/'ogg',BKG_SNB=base/'snb').items():
                    pila.enter_context(mock.patch.object(N,nombre,valor))
                for nombre,valor in funciones.items():
                    pila.enter_context(mock.patch.object(N,nombre,return_value=valor))
                N.copiar_cancion(tabla,tabla.filas[:])
            nueva=tabla.filas[-1]
            leida=S.cargar_configuracion(base,'%s:%s'%(nueva['Filename'],nueva['ID']))['adopcion']
            self.assertIs(leida['ajustar_nivel'],True)
            self.assertEqual(leida['origen']['Filename'],nueva['Filename'])
            self.assertEqual(S.cargar_configuracion(base,'bkgprueba:200')['adopcion'],cfg)


if __name__=='__main__':unittest.main()
