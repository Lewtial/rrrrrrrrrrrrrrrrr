#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Editor local de patrones por sección y descansos, sin modificar el audio."""
import copy
import math
import re
import tkinter as tk
from tkinter import messagebox, ttk

import tema as T


CASILLEROS = ("SPACE", "1 flecha", "2 flechas", "3 flechas")
PERFILES = {
    "Normales": ([1, 0, 1, 0], 4),
    "Dobles": ([2, 0, 2, 0], 4),
    "Triples": ([3, 0, 3, 0], 4),
    "Seguidas": ([1, 1, 1, 1], 4),
    "Repeticiones": ([2, 2, 2, 2], 1),
    "Solo SPACE": ([0, 0, 0, 0], 4),
}
BOLSAS = {
    "Normal: 4 direcciones": 4,
    "3 direcciones": 3,
    "2 direcciones": 2,
    "Repetir: 1 dirección": 1,
}
_DECIMAL = re.compile(r"\+?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def parsear_tiempo(texto):
    """Lee segundos o minutos:segundos; admite punto o coma decimal."""
    texto = str(texto).strip().replace(",", ".")
    partes = texto.split(":")
    if len(partes) == 1:
        if not _DECIMAL.fullmatch(texto):
            raise ValueError("Usá segundos decimales (12.5) o minutos:segundos (1:02.500).")
        valor = float(texto)
    elif (len(partes) == 2 and partes[0].isdigit()
          and _DECIMAL.fullmatch(partes[1])):
        segundos = float(partes[1])
        if not 0 <= segundos < 60:
            raise ValueError("Después de ':' los segundos deben estar entre 0 y menos de 60.")
        try:
            valor = int(partes[0]) * 60 + segundos
        except OverflowError as exc:
            raise ValueError("El tiempo debe ser un número finito y no negativo.") from exc
    else:
        raise ValueError("Usá segundos decimales (12.5) o minutos:segundos (1:02.500).")
    if not math.isfinite(valor) or valor < 0:
        raise ValueError("El tiempo debe ser un número finito y no negativo.")
    return valor


def formatear_tiempo(segundos):
    """Muestra m:ss.mmm, redondeando antes de separar los minutos."""
    segundos = float(segundos)
    if not math.isfinite(segundos) or segundos < 0:
        raise ValueError("El tiempo debe ser un número finito y no negativo.")
    completos = int(segundos)
    milisegundos = completos * 1000 + round((segundos - completos) * 1000)
    minutos, resto = divmod(milisegundos, 60000)
    enteros, milis = divmod(resto, 1000)
    return "%d:%02d.%03d" % (minutos, enteros, milis)


def _tiempo_editable(segundos):
    # Conservar todos los decimales evita mover límites al editar o redondear el
    # fin del audio por encima de su duración real.
    valor = float(segundos)
    mostrado = formatear_tiempo(valor)
    return mostrado if parsear_tiempo(mostrado) == valor else repr(valor)


def _normalizar_seccion(seccion, duracion):
    """Copia y valida una sección con límites dentro del audio."""
    if not isinstance(seccion, dict):
        raise ValueError("Cada sección debe contener un intervalo y un tipo de contenido.")
    try:
        desde, hasta = float(seccion["desde"]), float(seccion["hasta"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("La sección necesita un inicio y un fin válidos.") from exc
    if (not math.isfinite(desde) or not math.isfinite(hasta)
            or not 0 <= desde < hasta <= duracion):
        raise ValueError("El intervalo debe cumplir 0 ≤ desde < hasta ≤ duración del audio (%s)."
                         % formatear_tiempo(duracion))
    tipo = seccion.get("tipo")
    if tipo not in ("patron", "descanso"):
        raise ValueError("Elegí un patrón o un descanso para la sección.")
    resultado = dict(desde=desde, hasta=hasta, tipo=tipo)
    if tipo == "descanso":
        return resultado
    for campo, nombre in (("primera", "Primera tanda"), ("segunda", "Segunda tanda")):
        patron = seccion.get(campo)
        if campo == "segunda" and patron is None:
            resultado[campo] = None
        elif (isinstance(patron, (tuple, list)) and len(patron) == 4
              and all(type(x) is int and 0 <= x <= 3 for x in patron)):
            resultado[campo] = list(patron)
        else:
            raise ValueError("%s: elegí cuatro casilleros entre SPACE y 3 flechas." % nombre)
    bolsa = seccion.get("bolsa")
    if type(bolsa) is not int or not 1 <= bolsa <= 4:
        raise ValueError("Elegí entre 1 y 4 direcciones para el sorteo.")
    resultado["bolsa"] = bolsa
    return resultado


class DialogoSecciones(tk.Toplevel):
    """Mantiene una copia de las secciones hasta pulsar Aplicar al mapa.

    ``al_aplicar(secciones, todas_versiones)`` recibe una copia completa. Si
    devuelve False, el diálogo sigue abierto para poder corregir el contenido.
    """

    def __init__(self, padre, secciones, duracion, desde, hasta, al_aplicar, descanso=False):
        duracion = float(duracion)
        if not math.isfinite(duracion) or duracion <= 0:
            raise ValueError("La duración del audio debe ser finita y mayor que cero.")
        locales = [_normalizar_seccion(s, duracion) for s in copy.deepcopy(secciones)]
        desde, hasta = float(desde), float(hasta)
        _normalizar_seccion(dict(desde=desde, hasta=hasta, tipo="descanso"), duracion)

        super().__init__(padre)
        self.title("Contenido por sección y descansos")
        self.transient(padre)
        self.configure(background=T.FONDO)
        self.duracion = duracion
        self.secciones = locales
        self.al_aplicar = al_aplicar
        self._intervalo_inicial = (desde, hasta)
        self._seleccionado = None
        self._cargando = True
        self._nuevo_pendiente = True
        self._base_formulario = None
        self._combos_primera, self._combos_segunda = [], []

        self.v_desde = tk.StringVar(self)
        self.v_hasta = tk.StringVar(self)
        self.v_perfil = tk.StringVar(self)
        self.v_primera = [tk.StringVar(self) for _ in range(4)]
        self.v_segunda = [tk.StringVar(self) for _ in range(4)]
        self.v_dos_tandas = tk.BooleanVar(self, value=False)
        self.v_bolsa = tk.StringVar(self)
        self.v_todas = tk.BooleanVar(self, value=False)
        self.v_estado = tk.StringVar(self)

        exterior = ttk.Frame(self, padding=12)
        exterior.pack(fill="both", expand=True)
        ttk.Label(exterior, text="Editá los casilleros de cada tramo del audio.",
                  font=("Segoe UI", 11, "bold"), foreground=T.ACENTO).pack(anchor="w")
        ttk.Label(exterior, text="Duración: %s. Los cambios quedan locales hasta Aplicar al mapa."
                  % formatear_tiempo(duracion)).pack(anchor="w", pady=(2, 8))

        desplazable = T.Desplazable(exterior)
        desplazable.pack(fill="both", expand=True)
        contenido = desplazable.dentro
        contenido.columnconfigure(0, weight=1)
        formulario = ttk.LabelFrame(contenido, text="Sección seleccionada / nueva", padding=8)
        formulario.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        formulario.columnconfigure(1, weight=1)

        tiempos = ttk.Frame(formulario)
        tiempos.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(tiempos, text="Desde:").pack(side="left")
        entrada_desde = ttk.Entry(tiempos, textvariable=self.v_desde, width=15)
        entrada_desde.pack(side="left", padx=(5, 14))
        ttk.Label(tiempos, text="Hasta (fin exclusivo):").pack(side="left")
        ttk.Entry(tiempos, textvariable=self.v_hasta, width=15).pack(side="left", padx=5)
        ttk.Label(formulario, text="Tiempo en segundos (12.5) o m:ss.mmm (1:02.500).",
                  foreground=T.SUAVE).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 5))

        ttk.Label(formulario, text="Perfil:").grid(row=2, column=0, sticky="w")
        perfil = ttk.Combobox(formulario, textvariable=self.v_perfil,
                              values=tuple(PERFILES) + ("Personalizado", "Descanso"),
                              state="readonly", width=22)
        perfil.grid(row=2, column=1, sticky="w", pady=2)
        perfil.bind("<<ComboboxSelected>>", self._cambio_perfil)

        casilleros = ttk.Frame(formulario)
        casilleros.grid(row=3, column=0, columnspan=2, sticky="w", pady=(3, 1))
        for i in range(4):
            ttk.Label(casilleros, text="Casillero %d" % (i + 1)).grid(row=0, column=i + 1, padx=4)
        ttk.Label(casilleros, text="Primera tanda:").grid(row=1, column=0, sticky="w")
        self._segunda_check = ttk.Checkbutton(casilleros, text="Segunda tanda:",
                                            variable=self.v_dos_tandas,
                                            command=self._cambio_segunda)
        self._segunda_check.grid(row=2, column=0, sticky="w")
        for fila, variables, combos in ((1, self.v_primera, self._combos_primera),
                                         (2, self.v_segunda, self._combos_segunda)):
            for i, variable in enumerate(variables):
                combo = ttk.Combobox(casilleros, textvariable=variable, values=CASILLEROS,
                                     state="readonly", width=11)
                combo.grid(row=fila, column=i + 1, padx=4, pady=2)
                combo.bind("<<ComboboxSelected>>", self._personalizar)
                combos.append(combo)

        ttk.Label(formulario, text="Sorteo de direcciones:").grid(row=4, column=0, sticky="w", pady=(3, 0))
        self._bolsa_combo = ttk.Combobox(formulario, textvariable=self.v_bolsa,
                                        values=tuple(BOLSAS), state="readonly", width=24)
        self._bolsa_combo.grid(row=4, column=1, sticky="w", pady=(3, 0))
        self._bolsa_combo.bind("<<ComboboxSelected>>", self._personalizar)

        acciones = ttk.Frame(contenido)
        acciones.grid(row=1, column=0, sticky="ew", pady=(6, 2), padx=(0, 6))
        self._guardar_boton = ttk.Button(acciones, text="Agregar sección", command=self._guardar)
        self._guardar_boton.pack(side="left")
        ttk.Button(acciones, text="Nueva para otra", command=self._nueva).pack(side="left", padx=6)
        self._quitar_boton = ttk.Button(acciones, text="Quitar selección", command=self._quitar)
        self._quitar_boton.pack(side="left")
        ttk.Label(contenido, textvariable=self.v_estado, foreground=T.ACENTO2,
                  wraplength=790).grid(row=2, column=0, sticky="w", pady=(0, 5))

        tabla_marco = ttk.Frame(contenido)
        tabla_marco.grid(row=3, column=0, sticky="ew", padx=(0, 6))
        tabla_marco.columnconfigure(0, weight=1)
        columnas = ("orden", "desde", "hasta", "tipo", "primera", "segunda", "bolsa")
        self.tabla = ttk.Treeview(tabla_marco, columns=columnas, show="headings", height=5,
                                  selectmode="browse")
        for columna, titulo, ancho in (("orden", "Orden", 44), ("desde", "Desde", 88),
                                       ("hasta", "Hasta (excl.)", 88), ("tipo", "Tipo", 90),
                                       ("primera", "Primera tanda", 160),
                                       ("segunda", "Segunda tanda", 160),
                                       ("bolsa", "Direcciones", 80)):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, minwidth=ancho, stretch=columna in ("primera", "segunda"))
        self.tabla.grid(row=0, column=0, sticky="nsew")
        barra = ttk.Scrollbar(tabla_marco, orient="vertical", command=self.tabla.yview)
        barra.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(tabla_marco, orient="horizontal", command=self.tabla.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tabla.configure(yscrollcommand=barra.set, xscrollcommand=horizontal.set)
        self.tabla.bind("<<TreeviewSelect>>", self._seleccionar)

        ayuda = ("Orden de la tabla: si se superponen patrones, gana el último; los descansos tienen prioridad.\n"
                 "SPACE se elige en los casilleros; las direcciones las sortea el juego.\n"
                 "Los descansos eliminan misiones cuya ventana intersecta el tramo; pueden ampliar el silencio "
                 "en el borde. El audio no se recorta.")
        ttk.Label(contenido, text=ayuda, justify="left", foreground=T.SUAVE,
                  wraplength=790).grid(row=4, column=0, sticky="w", pady=(5, 2), padx=(0, 8))

        pie = ttk.Frame(exterior)
        pie.pack(fill="x", pady=(9, 0))
        ttk.Checkbutton(pie, text="Aplicar también a las otras dificultades de esta canción",
                        variable=self.v_todas).pack(anchor="w")
        ttk.Button(pie, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(pie, text="Aplicar al mapa", command=self._aplicar).pack(side="right")

        self._poner_formulario(dict(desde=desde, hasta=hasta,
                                    tipo="descanso" if descanso else "patron",
                                    primera=[1, 0, 1, 0], segunda=None, bolsa=4))
        self._refrescar_tabla()
        variables = [self.v_desde, self.v_hasta, self.v_perfil, self.v_dos_tandas,
                     self.v_bolsa] + self.v_primera + self.v_segunda
        for variable in variables:
            variable.trace_add("write", self._actualizar_estado)
        self._cargando = False
        self._base_formulario = self._firma_formulario()
        self._actualizar_estado()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        ancho = min(900, max(640, self.winfo_screenwidth() - 50))
        alto = min(560, max(400, self.winfo_screenheight() - 80))
        self.geometry("%dx%d" % (ancho, alto))
        self.minsize(min(680, ancho), min(420, alto))
        self.grab_set()
        entrada_desde.focus_set()

    def _firma_formulario(self):
        return (self.v_desde.get(), self.v_hasta.get(), self.v_perfil.get(),
                tuple(v.get() for v in self.v_primera), tuple(v.get() for v in self.v_segunda),
                self.v_dos_tandas.get(), self.v_bolsa.get())

    def _hay_pendiente(self):
        return self._nuevo_pendiente or self._firma_formulario() != self._base_formulario

    def _actualizar_estado(self, *_args):
        if self._cargando:
            return
        seleccionado = self._seleccionado is not None
        self._guardar_boton.configure(text="Actualizar sección" if seleccionado else "Agregar sección")
        self._quitar_boton.configure(state="normal" if seleccionado else "disabled")
        if self._hay_pendiente():
            texto = ("Cambios pendientes: Aplicar al mapa también actualiza esta sección."
                     if seleccionado else "Nueva sección pendiente: Aplicar al mapa también la agrega.")
        elif seleccionado:
            texto = "Editando la sección %d. Aplicar usa las secciones de la tabla." % (self._seleccionado + 1)
        else:
            texto = "Formulario nuevo sin cambios. Aplicar usa las secciones de la tabla."
        self.v_estado.set(texto)

    def _habilitar_contenido(self):
        es_descanso = self.v_perfil.get() == "Descanso"
        self._segunda_check.configure(state="disabled" if es_descanso else "normal")
        self._bolsa_combo.configure(state="disabled" if es_descanso else "readonly")
        for combo in self._combos_primera:
            combo.configure(state="disabled" if es_descanso else "readonly")
        for combo in self._combos_segunda:
            combo.configure(state="readonly" if not es_descanso and self.v_dos_tandas.get() else "disabled")

    def _cambio_perfil(self, _evento=None):
        perfil = PERFILES.get(self.v_perfil.get())
        if perfil is not None:
            patron, bolsa = perfil
            for i, cantidad in enumerate(patron):
                self.v_primera[i].set(CASILLEROS[cantidad])
                self.v_segunda[i].set(CASILLEROS[cantidad])
            self.v_bolsa.set(next(k for k, v in BOLSAS.items() if v == bolsa))
        self._habilitar_contenido()
        self._actualizar_estado()

    def _personalizar(self, _evento=None):
        self.v_perfil.set("Personalizado")
        self._actualizar_estado()

    def _cambio_segunda(self):
        self._habilitar_contenido()
        self._actualizar_estado()

    def _poner_formulario(self, seccion):
        estaba_cargando = self._cargando
        self._cargando = True
        self.v_desde.set(_tiempo_editable(seccion["desde"]))
        self.v_hasta.set(_tiempo_editable(seccion["hasta"]))
        primera = seccion.get("primera", [1, 0, 1, 0])
        segunda = seccion.get("segunda")
        bolsa = seccion.get("bolsa", 4)
        perfil = "Descanso" if seccion["tipo"] == "descanso" else "Personalizado"
        if seccion["tipo"] == "patron":
            for nombre, (patron, b) in PERFILES.items():
                if primera == patron and bolsa == b and (segunda is None or segunda == patron):
                    perfil = nombre
                    break
        self.v_perfil.set(perfil)
        self.v_dos_tandas.set(segunda is not None)
        for i in range(4):
            self.v_primera[i].set(CASILLEROS[primera[i]])
            self.v_segunda[i].set(CASILLEROS[(segunda or primera)[i]])
        self.v_bolsa.set(next(k for k, v in BOLSAS.items() if v == bolsa))
        self._habilitar_contenido()
        self._cargando = estaba_cargando
        self._base_formulario = self._firma_formulario()

    def _leer_formulario(self):
        try:
            desde = parsear_tiempo(self.v_desde.get())
        except ValueError as exc:
            raise ValueError("Desde: %s" % exc) from exc
        try:
            hasta = parsear_tiempo(self.v_hasta.get())
        except ValueError as exc:
            raise ValueError("Hasta: %s" % exc) from exc
        seccion = dict(desde=desde, hasta=hasta,
                       tipo="descanso" if self.v_perfil.get() == "Descanso" else "patron")
        if seccion["tipo"] == "patron":
            try:
                seccion["primera"] = [CASILLEROS.index(v.get()) for v in self.v_primera]
                seccion["segunda"] = ([CASILLEROS.index(v.get()) for v in self.v_segunda]
                                       if self.v_dos_tandas.get() else None)
                seccion["bolsa"] = BOLSAS[self.v_bolsa.get()]
            except (ValueError, KeyError) as exc:
                raise ValueError("Elegí los cuatro casilleros y el sorteo de direcciones.") from exc
        return _normalizar_seccion(seccion, self.duracion)

    @staticmethod
    def _texto_tanda(tanda):
        return " — ".join("SPACE" if x == 0 else str(x) for x in tanda)

    def _refrescar_tabla(self):
        self.tabla.delete(*self.tabla.get_children())
        for i, seccion in enumerate(self.secciones):
            descanso = seccion["tipo"] == "descanso"
            valores = (i + 1, formatear_tiempo(seccion["desde"]), formatear_tiempo(seccion["hasta"]),
                       "Descanso" if descanso else "Patrón",
                       "Sin misiones" if descanso else self._texto_tanda(seccion["primera"]),
                       "—" if descanso or seccion["segunda"] is None else self._texto_tanda(seccion["segunda"]),
                       "—" if descanso else seccion["bolsa"])
            self.tabla.insert("", "end", iid=str(i), values=valores)
        if self._seleccionado is not None:
            self.tabla.selection_set(str(self._seleccionado))
            self.tabla.see(str(self._seleccionado))

    def _seleccionar(self, _evento=None):
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        indice = int(seleccion[0])
        if indice == self._seleccionado:
            return
        self._seleccionado = indice
        self._nuevo_pendiente = False
        self._poner_formulario(self.secciones[indice])
        self._actualizar_estado()

    def _guardar(self):
        try:
            seccion = self._leer_formulario()
        except ValueError as exc:
            messagebox.showerror("Revisá la sección", str(exc), parent=self)
            return False
        if self._seleccionado is None:
            self.secciones.append(seccion)
            self._seleccionado = len(self.secciones) - 1
        else:
            self.secciones[self._seleccionado] = seccion
        self._nuevo_pendiente = False
        self._poner_formulario(seccion)
        self._refrescar_tabla()
        self._actualizar_estado()
        return True

    def _nueva(self):
        self._seleccionado = None
        self._nuevo_pendiente = False
        self.tabla.selection_remove(self.tabla.selection())
        desde, hasta = self._intervalo_inicial
        self._poner_formulario(dict(desde=desde, hasta=hasta, tipo="patron",
                                    primera=[1, 0, 1, 0], segunda=None, bolsa=4))
        self._actualizar_estado()

    def _quitar(self):
        if self._seleccionado is None:
            return
        del self.secciones[self._seleccionado]
        self._nueva()
        self._refrescar_tabla()

    def _aplicar(self):
        if self._hay_pendiente() and not self._guardar():
            return
        try:
            secciones = [_normalizar_seccion(s, self.duracion) for s in self.secciones]
            resultado = self.al_aplicar(copy.deepcopy(secciones), bool(self.v_todas.get()))
        except Exception as exc:
            messagebox.showerror("No se pudo aplicar", str(exc), parent=self)
            return
        if resultado is not False:
            self.destroy()
