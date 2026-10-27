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

    def aplicar_editor_secciones(self, secciones, todas_versiones=False, al_terminar=None):
        """Valida todo antes de guardar preferencias o cambiar la vista previa."""
        if not self._secciones_disponibles():
            return False
        try:
            secciones = S.validar_secciones(secciones)
            if any(s["hasta"] > self.dur + 1e-6 for s in secciones):
                raise ValueError("Una sección termina después del final de la canción.")
        except ValueError as error:
            messagebox.showerror("Secciones", str(error), parent=self)
            return False
        self.parar()
        p = self.padre
        objetivos = list(p.pareja) if todas_versiones else [self.fila]
        planes = []
        for fila in objetivos:
            actual = str(fila["ID"]) == str(self.fila["ID"])
            est = self.estrellas if actual else max(1, min(10, int(p.spins[fila["ID"]][0].get())))
            bpm = self.bpm if actual else p.bpm_de_fila(fila["ID"])
            extras = p.extras(fila)
            extras["secciones"] = copy.deepcopy(secciones)
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
                    p.guardar_secciones(fila, secciones, inicio)
            except (OSError, ValueError) as error:
                for fila, cfg in anteriores:
                    try:
                        p.guardar_secciones(fila, cfg["secciones"], cfg["inicio"])
                    except (OSError, ValueError):
                        pass
                messagebox.showerror("Guardar secciones", str(error), parent=self)
                return
            self.listas = resultados[str(self.fila["ID"])]
            self.guardado = False
            self._rehacer_mapa()
            self.info.config(text="Secciones guardadas para %s. Revisá el mapa y luego "
                                  "GENERAR EL CHART y ENVIAR AL JUEGO."
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
        if existentes:
            secciones = [s for s in secciones if s not in existentes]
        else:
            ms = self._mision_en(evento.x)
            if ms is None:
                return
            secciones.append(dict(desde=ms["t"], hasta=min(self.dur, ms["t"] + ms["largo"]),
                                  tipo="descanso"))
        self.aplicar_editor_secciones(secciones)

    def secciones_del_mapa(self):
        return self.padre.config_secciones(self.fila)["secciones"]
