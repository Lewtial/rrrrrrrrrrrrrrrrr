#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vista previa y aplicación de un chart de otra dificultad de la misma canción."""
import copy
import math
import tkinter as tk
from tkinter import messagebox, ttk

import tema as T


def validar_estrellas(valor):
    """Lee las estrellas del destino sin aceptar decimales ni valores fuera de rango."""
    texto = str(valor).strip()
    if not texto.isascii() or not texto.isdigit() or not 1 <= int(texto) <= 10:
        raise ValueError("Elegí un número entero de estrellas entre 1 y 10.")
    return int(texto)


def _bpm(fila):
    try:
        bpm = float(fila["BPM"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("La versión necesita un BPM válido.") from error
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("La versión necesita un BPM finito y mayor que cero.")
    return bpm


def preparar_fuentes(fuentes, destino, *, permitir_otro_bkg=False):
    """Identifica fuentes sin ambigüedad y devuelve copias independientes.

    El controlador puede habilitar otros bkg después de comprobar el vínculo
    entre original y copias. Este diálogo no deduce parentesco por el título.
    """
    if type(permitir_otro_bkg) is not bool:
        raise ValueError("La autorización de otros bkg debe ser explícita.")
    if not isinstance(destino, dict) or not destino.get("Filename") or not str(destino.get("ID", "")).strip():
        raise ValueError("El destino necesita un archivo de canción y un ID.")
    _bpm(destino)
    if not isinstance(fuentes, (list, tuple)) or not fuentes:
        raise ValueError("No hay otra dificultad de esta canción para adoptar.")
    resultado, identificadores = [], set()
    for fila in fuentes:
        if (not isinstance(fila, dict) or not isinstance(fila.get("Filename"), str)
                or not fila["Filename"].strip()):
            raise ValueError("La versión de origen necesita un archivo bkg.")
        if not permitir_otro_bkg and fila["Filename"] != destino["Filename"]:
            raise ValueError("Solo se puede adoptar otra versión de la misma canción (mismo bkg).")
        identificador = str(fila.get("ID", "")).strip()
        if not identificador or identificador == str(destino["ID"]):
            raise ValueError("Elegí una versión de origen distinta del destino.")
        if identificador in identificadores:
            raise ValueError("Las versiones de origen deben tener IDs distintos.")
        identificadores.add(identificador)
        validar_estrellas(fila.get("Difficulty", ""))
        _bpm(fila)
        resultado.append(copy.deepcopy(fila))
    return sorted(resultado, key=lambda fila: (-int(fila["Difficulty"]), str(fila["ID"])))


def etiqueta_fuente(fila):
    return "%s estrellas  ·  %g BPM  ·  ID %s  ·  %s" % (
        fila["Difficulty"], _bpm(fila), fila["ID"], fila["Filename"])


class DialogoAdoptar(tk.Toplevel):
    """Prepara un plan sin escribir y solo entrega el plan que se llegó a revisar.

    preparar(origen_id, estrellas) devuelve un dict con ``texto_resumen`` y los
    demás datos necesarios para aplicar. al_aplicar(plan) recibe ese mismo dict;
    devolver False mantiene el diálogo abierto para corregir o volver a preparar.
    La aplicación debe comprobar que las filas no cambiaron desde la vista previa.
    """

    def __init__(self, padre, fuentes, destino, preparar, al_aplicar, estrellas=None,
                 *, permitir_otro_bkg=False):
        fuentes = preparar_fuentes(fuentes, destino, permitir_otro_bkg=permitir_otro_bkg)
        estrellas = validar_estrellas(destino["Difficulty"] if estrellas is None else estrellas)
        super().__init__(padre)
        self.padre = padre
        self.fuentes, self.destino = fuentes, copy.deepcopy(destino)
        self.preparar, self.al_aplicar = preparar, al_aplicar
        self.plan_actual, self._firma_plan = None, None
        self._preparando = False
        self._por_etiqueta = {etiqueta_fuente(fila): fila for fila in fuentes}
        self.title("Adoptar versión de la misma canción")
        self.configure(background=T.FONDO)
        self.transient(padre)
        self.geometry("900x610")
        self.minsize(760, 520)

        self.v_fuente = tk.StringVar(self, value=etiqueta_fuente(fuentes[0]))
        self.v_estrellas = tk.StringVar(self, value=str(estrellas))
        self.v_estado = tk.StringVar(self, value="Elegí el origen y revisá la vista previa antes de aplicar.")

        exterior = ttk.Frame(self, padding=12)
        exterior.pack(fill="both", expand=True)
        contenido = T.Desplazable(exterior)
        contenido.pack(fill="both", expand=True)
        m = contenido.dentro
        self.lbl_identidad = ttk.Label(
            m, text="Destino: %s\nID %s  ·  Archivo %s  ·  %g BPM" %
            (destino.get("Title", "Canción"), destino["ID"], destino["Filename"], _bpm(destino)),
            style="Titulo.TLabel", wraplength=820, justify="left")
        self.lbl_identidad.pack(anchor="w")
        self.lbl_intro = ttk.Label(m, text="Esta dificultad tomará como base el chart que elegís abajo. "
                                  "Se ajustan las flechas al nivel del destino y se conservan "
                                  "sus espacios y descansos cuando el BPM lo permite." +
                                  (" Las fuentes incluyen el original y las copias vinculadas "
                                   "a esta canción." if any(f["Filename"] != destino["Filename"]
                                                           for f in fuentes) else ""),
                                  wraplength=820, justify="left")
        self.lbl_intro.pack(anchor="w", pady=(6, 10))

        opciones = ttk.LabelFrame(m, text=" Versión de origen y nivel de destino ", padding=10)
        opciones.pack(fill="x")
        ttk.Label(opciones, text="Tomar el chart de:").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.combo_fuente = ttk.Combobox(opciones, textvariable=self.v_fuente,
                                         values=list(self._por_etiqueta), state="readonly", width=58)
        self.combo_fuente.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(opciones, text="Estrellas del destino:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        fila_estrellas = ttk.Frame(opciones)
        fila_estrellas.grid(row=1, column=1, sticky="w", pady=4)
        self.spin_estrellas = ttk.Spinbox(fila_estrellas, textvariable=self.v_estrellas,
                                         from_=1, to=10, width=5)
        self.spin_estrellas.pack(side="left")
        ttk.Label(fila_estrellas, text=" Podés cambiarlas antes de preparar.", style="Sub.TLabel").pack(side="left", padx=8)
        opciones.columnconfigure(1, weight=1)
        self.lbl_bpm = ttk.Label(m, text="", foreground=T.AMBAR, wraplength=820, justify="left")
        self.lbl_bpm.pack(anchor="w", pady=(8, 4))
        self.b_previsualizar = ttk.Button(m, text="PREPARAR VISTA PREVIA", command=self._previsualizar)
        self.b_previsualizar.pack(anchor="w", pady=(4, 10))

        marco_resumen = ttk.LabelFrame(m, text=" Resultado que se aplicaría ", padding=8)
        marco_resumen.pack(fill="both", expand=True)
        self.texto_resumen = tk.Text(marco_resumen, height=11, wrap="word", state="disabled",
                                     background=T.CAJA, foreground=T.TEXTO,
                                     insertbackground=T.TEXTO, relief="flat", padx=8, pady=6)
        barra = ttk.Scrollbar(marco_resumen, orient="vertical", command=self.texto_resumen.yview)
        self.texto_resumen.configure(yscrollcommand=barra.set)
        self.texto_resumen.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self._mostrar_resumen("Todavía no se preparó la adopción. La vista previa mostrará las misiones, "
                              "el límite de flechas y los ajustes de tiempo que hagan falta.")

        pie = ttk.Frame(exterior)
        pie.pack(fill="x", pady=(10, 0))
        self.b_aplicar = ttk.Button(pie, text="APLICAR ADOPCIÓN", command=self._aplicar, state="disabled")
        self.b_aplicar.pack(side="left")
        ttk.Button(pie, text="Cancelar", command=self.destroy).pack(side="right")
        self.lbl_estado = ttk.Label(exterior, textvariable=self.v_estado, wraplength=820,
                                    justify="left", style="Sub.TLabel")
        self.lbl_estado.pack(anchor="w", pady=(6, 0))
        self.v_fuente.trace_add("write", self._invalidar)
        self.v_estrellas.trace_add("write", self._invalidar)
        self._aviso_bpm()
        self._ancho_wrap = None
        m.bind("<Configure>", self._ajustar_ancho, add="+")

    def _ajustar_ancho(self, evento):
        ancho = max(180, evento.width - 12)
        if ancho == self._ancho_wrap:
            return
        self._ancho_wrap = ancho
        for etiqueta in (self.lbl_identidad, self.lbl_intro, self.lbl_bpm, self.lbl_estado):
            etiqueta.config(wraplength=ancho)

    def _mostrar_resumen(self, texto):
        self.texto_resumen.config(state="normal")
        self.texto_resumen.delete("1.0", "end")
        self.texto_resumen.insert("1.0", texto)
        self.texto_resumen.config(state="disabled")
        self.texto_resumen.yview_moveto(0)

    def _firma_actual(self):
        fila = self._por_etiqueta.get(self.v_fuente.get())
        if fila is None:
            raise ValueError("Elegí una versión de origen de la lista.")
        return str(fila["ID"]), validar_estrellas(self.v_estrellas.get())

    def _aviso_bpm(self):
        fila = self._por_etiqueta.get(self.v_fuente.get())
        if fila is None:
            self.lbl_bpm.config(text="")
        elif math.isclose(_bpm(fila), _bpm(self.destino), rel_tol=0, abs_tol=1e-8):
            self.lbl_bpm.config(text="Mismo BPM: se puede conservar la ubicación y el largo de las misiones.",
                                foreground=T.VERDE)
        else:
            self.lbl_bpm.config(text="BPM distintos (%g → %g): los tiempos necesitan adaptarse. "
                                    "Revisá en la vista previa qué misiones se mueven o no caben." %
                                    (_bpm(fila), _bpm(self.destino)), foreground=T.AMBAR)

    def _invalidar(self, *_args):
        self.plan_actual, self._firma_plan = None, None
        self.b_aplicar.config(state="disabled")
        self.v_estado.set("Cambiaste las opciones. Prepará otra vista previa antes de aplicar.")
        self._mostrar_resumen("Vista previa pendiente para las opciones actuales.")
        self._aviso_bpm()

    def _ocupado(self):
        padre, vistos = self.padre, set()
        while padre is not None and id(padre) not in vistos:
            vistos.add(id(padre))
            if getattr(padre, "trabajando", False):
                return True
            padre = getattr(padre, "padre", None)
        return self._preparando

    def _previsualizar(self):
        if self._ocupado():
            self.v_estado.set("Esperá a que termine el trabajo antes de preparar la adopción.")
            return False
        self.plan_actual, self._firma_plan = None, None
        self.b_aplicar.config(state="disabled")
        try:
            firma = self._firma_actual()
            self._preparando = True
            plan = self.preparar(*firma)
            if not isinstance(plan, dict) or not isinstance(plan.get("texto_resumen"), str) or not plan["texto_resumen"].strip():
                raise ValueError("No se pudo obtener el resumen de la vista previa.")
            if firma != self._firma_actual():
                self.v_estado.set("Las opciones cambiaron durante la preparación. Prepará otra vista previa.")
                return False
            self.plan_actual, self._firma_plan = plan, firma
            self._mostrar_resumen(plan["texto_resumen"])
            self.b_aplicar.config(state="normal")
            self.v_estado.set("Vista previa lista. Aplicar cambiará solo la dificultad de destino; después podés enviarla al juego.")
            return True
        except (ValueError, OSError, RuntimeError) as error:
            self._mostrar_resumen("No se preparó la adopción. Corregí las opciones y volvé a intentarlo.")
            messagebox.showerror("Adoptar versión", str(error), parent=self)
            return False
        finally:
            self._preparando = False

    def _aplicar(self):
        if self._ocupado():
            self.v_estado.set("Esperá a que termine el trabajo antes de aplicar la adopción.")
            return False
        try:
            if self.plan_actual is None or self._firma_plan != self._firma_actual():
                self._invalidar()
                self.v_estado.set("Primero prepará y revisá la vista previa con estas opciones.")
                return False
            resultado = self.al_aplicar(self.plan_actual)
            if resultado is False:
                self.v_estado.set("No se aplicó la adopción. Revisá el aviso y prepará otra vista previa si cambió el chart.")
                return False
        except (ValueError, OSError, RuntimeError) as error:
            messagebox.showerror("Adoptar versión", str(error), parent=self)
            self.v_estado.set("No se aplicó la adopción. Corregí el problema y volvé a preparar la vista previa.")
            return False
        self.destroy()
        return True
