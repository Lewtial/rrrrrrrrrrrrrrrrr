"""La adopción entre copias exige una relación registrada, nunca solo el título."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from familia_copias import fuentes_relacionadas


def fila(identificador, bkg, estrellas=10, titulo="Trapped"):
    return dict(ID=str(identificador), Filename=bkg, Difficulty=str(estrellas),
                Title=titulo, BPM="290", StartDelayTime="6.574")


class FuentesRelacionadasTest(unittest.TestCase):
    def setUp(self):
        self.originales = [fila(4152, "bkg10213", 4), fila(4153, "bkg10213")]
        self.destino = fila(9052, "bkg2824", 6, "Trapped (copia)")
        self.filas = self.originales + [self.destino]

    def ids(self, filas=None, copias=None, destino=None):
        return [f["ID"] for f in fuentes_relacionadas(
            self.filas if filas is None else filas,
            self.destino if destino is None else destino,
            {"9052": "4153"} if copias is None else copias)]

    def test_copia_del_usuario_ofrece_las_dos_dificultades_originales(self):
        self.assertEqual(self.ids(), ["4152", "4153"])

    def test_original_tambien_puede_ver_sus_copias_sin_otorgar_permiso_de_edicion(self):
        self.assertEqual(self.ids(destino=self.originales[1]), ["4152", "9052"])
        # La protección del destino corresponde al controlador; aquí se ofrecen
        # filas sin mutarlas ni añadir marcas que habiliten su escritura.
        self.assertNotIn("editable", self.originales[1])

    def test_mismo_bkg_siempre_es_familia_sin_necesitar_registro(self):
        hermana=fila(9053,"bkg2824",9)
        self.assertEqual(self.ids(self.filas+[hermana],copias={}),["9053"])

    def test_el_mismo_titulo_no_relaciona_bkg_distintos(self):
        impostora=fila(9999,"otro-bkg",10)
        self.assertEqual(self.ids(self.filas+[impostora]),["4152","4153"])
        self.assertEqual(self.ids(copias={}),[])

    def test_cadena_de_copia_de_copia_y_hermana_del_otro_nivel(self):
        segunda=fila(9053,"bkg2825",6)
        tercera=fila(9054,"bkg2826",8)
        copias={"9052":"4153","9053":"4152","9054":"9052"}
        self.assertEqual(self.ids(self.filas+[segunda,tercera],copias,destino=tercera),
                         ["4152","4153","9052","9053"])

    def test_no_muta_tabla_destino_registro_ni_comparte_diccionarios(self):
        copias={"9052":"4153"}
        antes=copy.deepcopy((self.filas,self.destino,copias))
        resultado=fuentes_relacionadas(self.filas,self.destino,copias)
        resultado[0]["Title"]="Editado"
        self.assertEqual((self.filas,self.destino,copias),antes)

    def test_admite_ids_enteros_legacy_y_conserva_orden_de_tabla(self):
        self.assertEqual(self.ids(copias={9052:4153}),["4152","4153"])
        self.assertEqual(self.ids(list(reversed(self.filas))),["4153","4152"])

    def test_ciclo_en_linaje_del_destino_falla_claro(self):
        for copias in ({"9052":"9052"},{"9052":"4153","4153":"9052"}):
            with self.subTest(copias=copias),self.assertRaisesRegex(ValueError,"ciclo"):
                self.ids(copias=copias)

    def test_original_ausente_del_destino_falla_sin_inferir_por_titulo(self):
        with self.assertRaisesRegex(ValueError,"falta la fila original"):
            self.ids(copias={"9052":"999999"})

    def test_cadena_rota_en_intermedio_del_destino_falla(self):
        with self.assertRaisesRegex(ValueError,"falta la fila original"):
            self.ids(copias={"9052":"4153","4153":"999999"})

    def test_padre_malformado_del_destino_falla(self):
        for valor in (None,True,1.5,float("nan"),float("inf"),{},[],"", "4153.0"):
            with self.subTest(valor=valor),self.assertRaisesRegex(ValueError,"original no es válido"):
                self.ids(copias={"9052":valor})

    def test_registros_danados_ajenos_no_bloquean_ni_amplian_familia(self):
        ajenas=[fila(9000,"ajena"),fila(9001,"otra-ajena")]
        for extras in ({"9000":"9001","9001":"9000"},
                       {"9000":"999999"},{"9000":{}},{"invalid":"9052"}):
            with self.subTest(extras=extras):
                self.assertEqual(self.ids(self.filas+ajenas,dict({"9052":"4153"},**extras)),
                                 ["4152","4153"])

    def test_copia_incompleta_no_se_ofrece_al_original(self):
        otra=fila(9000,"otra-copia")
        copias={"9052":"4153","9000":"999999"}
        self.assertEqual(self.ids(self.filas+[otra],copias,destino=self.originales[1]),
                         ["4152","9052"])

    def test_normalizacion_ambigua_del_destino_falla(self):
        with self.assertRaisesRegex(ValueError,"más de un original"):
            self.ids(copias={"9052":"4153",9052:"4152"})

    def test_registro_de_tipo_incorrecto_falla_claro(self):
        for registro in (None,[],"copias"):
            with self.subTest(registro=registro),self.assertRaisesRegex(ValueError,"registro de copias"):
                fuentes_relacionadas(self.filas,self.destino,registro)

    def test_destino_debe_existir_y_conservar_su_bkg(self):
        for destino in (fila(9999,"bkg2824"),dict(self.destino,Filename="otro")):
            with self.subTest(destino=destino),self.assertRaisesRegex(ValueError,"destino"):
                self.ids(destino=destino)

    def test_ids_duplicados_y_filas_invalidas_no_se_eligen_arbitrariamente(self):
        for filas in (self.filas+[dict(self.originales[0],Filename="otro")],
                      self.filas+[dict(ID="NaN",Filename="otro")],
                      self.filas+[dict(ID="9999",Filename="")]):
            with self.subTest(filas=filas),self.assertRaises(ValueError):
                self.ids(filas=filas)

    def test_cadena_larga_no_depende_del_limite_de_recursion(self):
        filas=[fila(1,"base")]+[fila(i,"copia-%s"%i) for i in range(2,1502)]
        copias={str(i):str(i-1) for i in range(2,1502)}
        fuentes=fuentes_relacionadas(filas,filas[-1],copias)
        self.assertEqual(len(fuentes),1500)
        self.assertEqual(fuentes[0]["ID"],"1")

    def test_mismo_bkg_sigue_disponible_con_linaje_o_registro_danado(self):
        hermana=fila(9053,"bkg2824",9)
        for copias in ([],{"9052":"999999"},{"9052":"9052"},{"9052":{}}):
            with self.subTest(copias=copias):
                self.assertEqual(self.ids(self.filas+[hermana],copias),["9053"])

    def test_padres_de_bkg_incompatibles_no_unen_canciones_ajenas(self):
        otra_original=fila(8000,"otro-original")
        hermana=fila(9053,"bkg2824",9)
        filas=self.filas+[otra_original,hermana]
        copias={"9052":"4153","9053":"8000"}
        self.assertEqual(self.ids(filas,copias),["9053"])
        self.assertEqual(self.ids(filas,copias,destino=self.originales[1]),["4152"])
        self.assertEqual(self.ids(filas,copias,destino=otra_original),[])

    def test_enlaces_transitivos_no_son_ambiguos_por_filas_nuevas_sin_registro(self):
        manual=fila(9053,"bkg2824",9)
        tercera=fila(9054,"bkg2826",8)
        cuarta=fila(9055,"bkg2826",6)
        filas=self.filas+[manual,tercera,cuarta]
        copias={"9052":"4153","9054":"9053","9055":"4152"}
        self.assertEqual(self.ids(filas,copias,destino=tercera),
                         ["4152","4153","9052","9053","9055"])

    def test_ciclo_de_bkg_con_ids_individuales_aciclicos_no_amplia_fuentes(self):
        hermana=fila(9053,"bkg2824",9)
        copias={"9052":"4153","4152":"9053"}
        self.assertEqual(self.ids(self.filas+[hermana],copias),["9053"])
        self.assertEqual(self.ids(self.filas+[hermana],copias,destino=self.originales[1]),["4152"])


if __name__=="__main__":unittest.main()
