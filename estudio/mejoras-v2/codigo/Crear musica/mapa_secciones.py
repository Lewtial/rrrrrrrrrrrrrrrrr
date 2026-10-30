"""Integración del editor de secciones con el mapa de la canción."""
import copy
from tkinter import messagebox

import nucleo as N
import secciones as S


class EdicionSeccionesMapa:
    def _secciones_disponibles(self):
        return (not self.original and not self.padre.trabajando
                and self.padre.pareja
                and all(f["Filename"] == self.fila["Filename"] for f in self.padre.pareja))

    def abrir_secciones(self, evento=None, descanso=False):
        if descanso:
            return self.abrir_secciones_tramos(evento, descanso=True)
        if not self._secciones_disponibles():
            return
        anterior = getattr(self, "_editor_misiones", None)
        if anterior is not None and anterior.winfo_exists():
            anterior.lift()
            return
        from editor_misiones import EditorMisiones
        self._editor_misiones = EditorMisiones(
            self, self.fila, self.listas, self.inicio, self.bpm,
            self.aplicar_editor_misiones, abrir_secciones=self.abrir_secciones_tramos)

    def refrescar_editor_misiones(self):
        editor = getattr(self, "_editor_misiones", None)
        if editor is not None and editor.winfo_exists():
            editor.actualizar(self.fila, self.listas, self.inicio, self.bpm)

    def aplicar_editor_misiones(self, acciones):
        """Sustituye contenido de misiones existentes y lo conserva al regenerar."""
        if not self._secciones_disponibles():
            return False
        import misiones as M
        p = self.padre
        try:
            acciones = M.validar_misiones(acciones)
            cfg = copy.deepcopy(p.config_secciones(self.fila))
            base = dict(self.listas)
            inicio_real = float(base.get("StartDelayTime", self.inicio))
            nuevos = M.aplicar_misiones(self.fila, base, inicio_real, self.bpm,
                                        acciones, secciones=cfg["secciones"])
            guardadas = copy.deepcopy(cfg.get("misiones", []))
            for accion in acciones:
                guardadas = [a for a in guardadas
                             if abs(a["tiempo"] - accion["tiempo"]) > 1e-4]
                guardadas.append(copy.deepcopy(accion))
            p.guardar_secciones(self.fila, cfg["secciones"], self.inicio,
                                misiones=guardadas)
        except (ValueError, OSError) as error:
            messagebox.showerror("Editar misión", str(error), parent=self)
            return False
        self.fila.update(nuevos)
        p.modificadas.add(self.fila["ID"])
        p.sucias.add(self.fila["ID"])
        p.b_enviar.config(state="normal")
        self.listas = dict(nuevos)
        self.guardado = True
        self._rehacer_mapa()
        p.pintar_lista()
        self.info.config(text="Misión actualizada, sin mover su inicio ni duración. "
                              "Lista para ENVIAR AL JUEGO; la copia se conserva al generar.")
        return True

    def abrir_secciones_tramos(self, evento=None, descanso=False):
        if not self._secciones_disponibles():
            return
        from dialogo_secciones import DialogoSecciones
        desde = max(0.0, self.v0)
        hasta = min(self.dur, desde + 16 * 60.0 / self.bpm)
        if evento is not None:
            ms = self._mision_en(evento.x)
            if ms:
                desde, hasta = ms["t"], min(self.dur, ms["t"] + ms["largo"])
        if hasta <= desde:
            desde, hasta = 0.0, self.dur
        def aplicar(secciones, todas_versiones):
            return self.aplicar_editor_secciones(
                secciones, todas_versiones,
                al_terminar=lambda: dialogo.destroy() if dialogo.winfo_exists() else None)

        dialogo = DialogoSecciones(
            self, self.padre.config_secciones(self.fila)["secciones"],
            self.dur, desde, hasta, aplicar, descanso=descanso)
        if hasattr(self, "v_ambas"):
            dialogo.v_todas.set(bool(self.v_ambas.get()))

    def aplicar_editor_secciones(self, secciones, todas_versiones=False, al_terminar=None,
                                secciones_por_fila=None):
        """Valida y guarda todas las preferencias antes de preparar su envío.

        El diálogo puede copiar su configuración completa a otras versiones.
        La herramienta Descanso pasa una configuración por fila para conservar
        los patrones que cada dificultad ya tiene.
        """
        if not self._secciones_disponibles():
            return False
        p = self.padre
        objetivos = list(p.pareja) if todas_versiones else [self.fila]
        try:
            secciones = S.validar_secciones(secciones)
            if secciones_por_fila is not None and not isinstance(secciones_por_fila, dict):
                raise ValueError("La configuración por dificultad debe indicar sus secciones.")
            configuraciones = {}
            for fila in objetivos:
                id_ = str(fila["ID"])
                if secciones_por_fila is not None:
                    if id_ not in secciones_por_fila:
                        raise ValueError("Faltan las secciones de la fila %s." % id_)
                    propias = S.validar_secciones(secciones_por_fila[id_])
                else:
                    propias = copy.deepcopy(secciones)
                if any(s["hasta"] > self.dur + 1e-6 for s in propias):
                    raise ValueError("Una sección termina después del final de la canción.")
                configuraciones[id_] = propias
        except ValueError as error:
            messagebox.showerror("Secciones", str(error), parent=self)
            return False
        self.parar()
        planes = []
        for fila in objetivos:
            actual = str(fila["ID"]) == str(self.fila["ID"])
            est = self.estrellas if actual else max(1, min(10, int(p.spins[fila["ID"]][0].get())))
            bpm = self.bpm if actual else p.bpm_de_fila(fila["ID"])
            extras = p.extras(fila)
            extras["secciones"] = copy.deepcopy(configuraciones[str(fila["ID"])])
            planes.append((fila, est, bpm, extras,
                           self.tramos_mudos() if actual else p.mudos_de(fila)))
        frases, modo = p.frases_de(), p.modo_space()
        descanso, sinsp = bool(p.v_descanso.get()), bool(p.v_sinsp.get())
        repeticiones = tuple(p.ultimas_repes)
        inicio = self.inicio

        def trabajo():
            resultados = {}
            for fila, estrellas, bpm, extras, mudos in planes:
                nuevos, _ = N.generar(
                    fila, self.rej, estrellas, inicio, bpm=bpm,
                    por_musica=self.por_musica, space=modo, mudos=mudos,
                    frases=frases, descanso=descanso, mudo_sin_space=sinsp,
                    repetir=repeticiones, **extras)
                resultados[str(fila["ID"])] = nuevos
            return resultados

        def despues(resultados):
            anteriores = [(fila, copy.deepcopy(p.config_secciones(fila))) for fila in objetivos]
            try:
                for fila in objetivos:
                    p.guardar_secciones(fila, configuraciones[str(fila["ID"])], inicio)
            except (OSError, ValueError) as error:
                for fila, cfg in anteriores:
                    try:
                        p.guardar_secciones(fila, cfg["secciones"], cfg["inicio"])
                    except (OSError, ValueError):
                        pass
                messagebox.showerror("Guardar secciones", str(error), parent=self)
                return
            # ENVIAR escribe las filas de la tabla, no las listas privadas del
            # mapa. Lo que se acaba de mostrar debe quedar listo para exportar.
            for fila in objetivos:
                fila.update(resultados[str(fila["ID"])])
                p.modificadas.add(fila["ID"])
                p.sucias.add(fila["ID"])
            p.b_enviar.config(state="normal")
            self.listas = resultados[str(self.fila["ID"])]
            self.guardado = True
            self._rehacer_mapa()
            p.pintar_lista()
            self.info.config(text="Secciones aplicadas al chart de %s y listas para "
                                  "ENVIAR AL JUEGO. Después de enviar, reiniciá el "
                                  "cliente antes de volver a probar."
                                  % ("todas las versiones" if todas_versiones else "esta dificultad"))
            if al_terminar:
                al_terminar()
        p._en_hilo("Aplicando secciones y descansos...", trabajo, despues)
        return al_terminar is None

    def descanso_seccion(self, evento):
        if not self._secciones_disponibles():
            return
        t = self._t_de_x(evento.x)
        secciones = copy.deepcopy(self.padre.config_secciones(self.fila)["secciones"])
        existentes = [s for s in secciones if s["tipo"] == "descanso"
                       and s["desde"] <= t < s["hasta"]]
        nueva = None
        if not existentes:
            ms = self._mision_en(evento.x)
            if ms is None:
                return
            nueva = dict(desde=ms["t"], hasta=min(self.dur, ms["t"] + ms["largo"]),
                         tipo="descanso")
        todas = bool(self.v_ambas.get()) if hasattr(self, "v_ambas") else False
        objetivos = self.padre.pareja if todas else [self.fila]
        configuraciones = {}
        for fila in objetivos:
            propias = copy.deepcopy(self.padre.config_secciones(fila)["secciones"])
            if existentes:
                # Solo se quitan los mismos descansos que se quitaron acá; los
                # patrones y otros descansos de esa dificultad se conservan.
                propias = [s for s in propias if s not in existentes]
            elif nueva not in propias:
                propias.append(copy.deepcopy(nueva))
            configuraciones[str(fila["ID"])] = propias
        self.aplicar_editor_secciones(
            configuraciones[str(self.fila["ID"])], todas_versiones=todas,
            secciones_por_fila=configuraciones)

    def secciones_del_mapa(self):
        return self.padre.config_secciones(self.fila)["secciones"]
