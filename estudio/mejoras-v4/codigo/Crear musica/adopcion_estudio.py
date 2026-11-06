"""Adoptar otra dificultad de la misma canción desde el panel del Estudio."""
import copy
import math
from tkinter import messagebox, ttk

import nucleo as N


def descansos_configuracion(cfg):
    """Descansos actuales más los de la base adoptada, en segundos del audio."""
    resultado = [copy.deepcopy(s) for s in cfg.get("secciones", [])
                 if s["tipo"] == "descanso"]
    adopcion = cfg.get("adopcion")
    if adopcion:
        ancla = cfg.get("inicio")
        delta = (adopcion["inicio"] if ancla is None else ancla) - adopcion["inicio"]
        for seccion in adopcion["descansos"]:
            nueva = dict(tipo="descanso", desde=max(0., seccion["desde"] + delta),
                         hasta=seccion["hasta"] + delta)
            if nueva["hasta"] > nueva["desde"] and nueva not in resultado:
                resultado.append(nueva)
    return resultado


def texto_plan(origen, destino, resumen):
    lineas = [
        "Origen: ID %s · %s estrellas · %g BPM" %
        (origen["ID"], origen["Difficulty"], resumen["bpm_origen"]),
        "Destino: ID %s · %s · %d estrellas · %g BPM" %
        (destino["ID"], destino["Filename"], resumen["estrellas"], resumen["bpm_destino"]),
        "", resumen["regla"],
        "Misiones: %d → %d. Grupos reducidos: %d; flechas retiradas: %d." %
        (resumen["misiones_origen"], resumen["misiones_destino"],
         resumen["grupos_reducidos"], resumen["flechas_retiradas"]),
        "Se conservan los casilleros SPACE y el contenido de las misiones que caben.",
        "La versión de origen se conserva. Se reemplazan el chart y los ajustes previos del destino.",
        "La base queda guardada: GENERAR conserva el diseño adoptado y las nuevas ediciones."]
    if resumen["mismo_bpm"]:
        lineas += ["", "Mismo BPM: inicios y largos idénticos a los del origen."]
    else:
        lineas += ["", "BPM distintos: adaptación al compás del destino.",
                   "Desplazamiento máximo: %.3f s. Misiones omitidas: %d. Segundas tandas retiradas: %d." %
                   (resumen["error_max_segundos"], resumen["misiones_omitidas"],
                    resumen["segundas_retiradas"]),
                   "Final del chart: %.3f → %.3f s." %
                   (resumen["fin_origen"], resumen["fin_destino"])]
        for ajuste in resumen["ajustes"]:
            if abs(ajuste["desvio_segundos"]) > .0001 or ajuste.get("segunda_retirada"):
                lineas.append("  Misión %d: %.3f → %.3f s (%+.3f s)%s" %
                              (ajuste["mision_origen"], ajuste["inicio_origen"],
                               ajuste["inicio_destino"], ajuste["desvio_segundos"],
                               "; sin segunda tanda" if ajuste.get("segunda_retirada") else ""))
        for omision in resumen["omisiones"]:
            lineas.append("  Omitida misión %d (%.3f s): %s" %
                          (omision["mision_origen"], omision["inicio_origen"], omision["motivo"]))
    for aviso in resumen["advertencias"]:
        lineas.append("\n" + aviso)
    return "\n".join(lineas)


class AdopcionVersiones:
    def botones_adopcion(self, contenedor, fila):
        acciones = ttk.Frame(contenedor)
        acciones.pack(fill="x", pady=(3, 0))
        habilitado = (not N.es_original(fila) and
                      any(str(f["ID"]) != str(fila["ID"]) and
                          f["Filename"] == fila["Filename"] for f in self.pareja))
        ttk.Button(acciones, text="ADOPTAR VERSIÓN…",
                   command=lambda: self.abrir_adoptar_version(fila["ID"]),
                   state="normal" if habilitado else "disabled").pack(side="left")
        cfg = self.config_secciones(fila)
        if cfg.get("adopcion"):
            ttk.Button(acciones, text="Quitar adopción",
                       command=lambda: self.quitar_adopcion(fila["ID"])).pack(side="left", padx=6)
            fuente = cfg["adopcion"]["origen"]
            ttk.Label(contenedor, text="Base adoptada: ID %s (%s estrellas). Se conserva al generar." %
                      (fuente["ID"], fuente["Difficulty"]), wraplength=340,
                      style="Sub.TLabel").pack(fill="x", pady=(3, 0))

    def _fila_adopcion(self, identificador):
        fila = self.tabla.por_id(str(identificador)) if self.tabla else None
        if fila is None:
            raise ValueError("La versión ya no está en la tabla. Volvé a elegir la canción.")
        return fila

    def _mapas_adopcion(self):
        return [w for w in self.winfo_children()
                if hasattr(w, "historia") and hasattr(w, "listas") and hasattr(w, "fila")]

    def sincronizar_mapas_generados(self, ids, inicio):
        """El mapa abierto debe mostrar las filas que GENERAR acaba de preparar."""
        ids = {str(i) for i in ids}
        for mapa in self._mapas_adopcion():
            if str(mapa.fila["ID"]) in ids:
                mapa.listas = copy.deepcopy(mapa.fila)
                mapa.bpm = float(mapa.fila["BPM"])
                mapa.estrellas = int(mapa.fila["Difficulty"])
                mapa.inicio, mapa.guardado = inicio, True
                mapa._rehacer_mapa()

    def _comprobar_mapa_adopcion(self, fila):
        for mapa in self._mapas_adopcion():
            if str(mapa.fila["ID"]) != str(fila["ID"]):
                continue
            if (any(mapa.listas.get(c, fila.get(c)) != fila.get(c)
                    for c in tuple(N.LISTAS) + ("StartDelayTime",)) or
                    not math.isclose(mapa.bpm, float(fila["BPM"]), abs_tol=.00001) or
                    (getattr(mapa, "repes", set()) and not getattr(mapa, "guardado", False))):
                raise ValueError("El mapa de la fila %s tiene cambios sin generar. "
                                 "Pulsá GENERAR EL CHART en ese mapa antes de adoptar." % fila["ID"])

    def _preparar_adopcion(self, destino_id, origen_id, estrellas):
        if self.trabajando:
            raise ValueError("Esperá a que termine el trabajo actual.")
        origen, destino = self._fila_adopcion(origen_id), self._fila_adopcion(destino_id)
        if N.es_original(destino):
            raise ValueError("Esta canción está protegida. Primero habilitá su edición en el Estudio.")
        if not self.pareja or any(f["Filename"] != destino["Filename"] for f in self.pareja):
            raise ValueError("Cambiaste de canción. Abrí Adoptar versión desde la canción actual.")
        if destino["Filename"] in self.recortes:
            raise ValueError("Hay un recorte de audio pendiente. Enviá ese recorte antes de adoptar otra versión.")
        self._comprobar_mapa_adopcion(origen)
        self._comprobar_mapa_adopcion(destino)
        cfg_origen = copy.deepcopy(self.config_secciones(origen))
        cfg_destino = copy.deepcopy(self.config_secciones(destino))
        bpm = self.bpm_de_fila(destino["ID"])
        objetivo = copy.deepcopy(destino)
        objetivo["BPM"] = "%g" % round(bpm, 2)
        from adoptar_version import adoptar_version
        nuevos, resumen = adoptar_version(origen, objetivo, estrellas=estrellas,
                                          descansos=descansos_configuracion(cfg_origen))
        nuevos.update(BPM=objetivo["BPM"], CutOff=str(N.cutoff_de(estrellas)))
        adopcion = dict(version=1, origen=copy.deepcopy(origen),
                        descansos=copy.deepcopy(resumen["descansos"]),
                        inicio=float(origen["StartDelayTime"]))
        return dict(origen_id=str(origen["ID"]), destino_id=str(destino["ID"]),
                    origen_previo=copy.deepcopy(origen), destino_previo=copy.deepcopy(destino),
                    cfg_origen_previo=cfg_origen, cfg_destino_previo=cfg_destino,
                    estrellas_panel=int(self.spins[destino["ID"]][0].get()),
                    bpm_panel=bpm, nuevos=nuevos, resumen=resumen, adopcion=adopcion,
                    texto_resumen=texto_plan(origen, objetivo, resumen))

    def _aplicar_adopcion(self, plan):
        if self.trabajando:
            raise ValueError("Esperá a que termine el trabajo actual.")
        # Volver a preparar comprueba filas, configuración y controles actuales;
        # aplicar solo el mismo resultado que se revisó evita pisar otra edición.
        actual = self._preparar_adopcion(plan["destino_id"], plan["origen_id"],
                                        plan["resumen"]["estrellas"])
        if actual != plan:
            raise ValueError("El chart o sus opciones cambiaron desde la vista previa. Prepará otra antes de aplicar.")
        destino = self._fila_adopcion(plan["destino_id"])
        mapas = [m for m in self._mapas_adopcion() if m.fila["Filename"] == destino["Filename"]]
        for mapa in mapas:
            mapa._anotar()
        self.guardar_secciones(destino, [], plan["adopcion"]["inicio"], misiones=[],
                               adopcion=plan["adopcion"])
        destino.update(copy.deepcopy(plan["nuevos"]))
        # Estas marcas son compartidas por canción. El diseño ya está en la
        # instantánea: volver a aplicarlas alteraría la vista previa adoptada.
        self.ultimos_mudos, self.mudos_solo_fila = (), None
        self.ultimas_repes = self.ultimos_spaces = self.ultimos_inv = ()
        self.ultimos_suave = self.ultimos_ritmos = ()
        self.ultimas_frases = None
        for nombre in ("v_frases", "v_descanso"):
            variable = getattr(self, nombre, None)
            if variable is not None:
                variable.set(False)
        self._marcar_adopcion(destino)
        self.spins[destino["ID"]][0].set(plan["resumen"]["estrellas"])
        # Proteger el chart de origen cuando se pulse GENERAR después de adoptar.
        for identificador, variable in self.gen_fila.items():
            variable.set(str(identificador) == str(destino["ID"]))
        for mapa in mapas:
            mapa.quitados, mapa.repes, mapa._repes_t = [], set(), []
            if str(mapa.fila["ID"]) == str(destino["ID"]):
                mapa.listas = copy.deepcopy(destino)
                mapa.bpm, mapa.estrellas = float(destino["BPM"]), int(destino["Difficulty"])
                mapa.inicio = mapa.base = plan["adopcion"]["inicio"]
                mapa.cual, mapa.quitados, mapa.repes, mapa._repes_t = 0, [], set(), []
                mapa.guardado = True
                mapa._rehacer_mapa()
            else:
                mapa._rehacer_mapa()
        self._pintar_arreglar()
        self._pintar_revision()
        self.pintar_lista()
        self._resultado_adopcion(plan["texto_resumen"] +
                                 "\n\nListo para ENVIAR AL JUEGO. GENERAR quedó seleccionado solo para este destino.")
        return True

    def _marcar_adopcion(self, fila):
        self.modificadas.add(fila["ID"])
        if fila == self.filas_enviadas.get(str(fila["ID"])):
            self.sucias.discard(fila["ID"])
        else:
            self.sucias.add(fila["ID"])
        self.b_enviar.config(state="normal" if self.sucias else "disabled")

    def _resultado_adopcion(self, texto):
        self.result.config(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("end", texto)
        self.result.config(state="disabled")

    def abrir_adoptar_version(self, destino_id):
        if self.trabajando or not self.tabla or not self.rej:
            return
        try:
            destino = self._fila_adopcion(destino_id)
            if N.es_original(destino):
                raise ValueError("Esta canción está protegida. Primero habilitá su edición.")
            objetivo = dict(destino, BPM="%g" % round(self.bpm_de_fila(destino_id), 2))
            fuentes = [copy.deepcopy(f) for f in self.pareja
                       if str(f["ID"]) != str(destino_id) and f["Filename"] == destino["Filename"]]
            from dialogo_adoptar import DialogoAdoptar
            DialogoAdoptar(self, fuentes, objetivo,
                           lambda origen_id, estrellas: self._preparar_adopcion(destino_id, origen_id, estrellas),
                           self._aplicar_adopcion, estrellas=self.spins[destino["ID"]][0].get())
        except (ValueError, OSError) as error:
            messagebox.showerror("Adoptar versión", str(error), parent=self)

    def quitar_adopcion(self, destino_id):
        if self.trabajando:
            return
        try:
            fila = self._fila_adopcion(destino_id)
            if N.es_original(fila):
                return
            cfg = self.config_secciones(fila)
            if not cfg.get("adopcion"):
                return
            for mapa in self._mapas_adopcion():
                mapa._anotar()
            self.guardar_secciones(fila, cfg["secciones"], cfg["inicio"],
                                   misiones=cfg["misiones"], adopcion=None)
            for mapa in self._mapas_adopcion():
                mapa._anotar()
            self._pintar_arreglar()
            self._resultado_adopcion("La fila %s vuelve a la generación normal. Su chart actual sigue "
                                     "igual hasta que pulses GENERAR EL CHART. Se conservan las "
                                     "ediciones manuales posteriores; revisalas si cambias la cuadrícula." % fila["ID"])
        except (ValueError, OSError) as error:
            messagebox.showerror("Quitar adopción", str(error), parent=self)
