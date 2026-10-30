"""Editor de las misiones existentes: copiar y sustituir sin mover sus tiempos."""
import copy
import math
import tkinter as tk
from tkinter import messagebox, ttk

import nucleo as N
import tema as T


CASILLEROS = ("SPACE", "1 flecha", "2 flechas", "3 flechas")
BOLSAS = ("1 (repeticiones)", "2", "3", "4 (normal)")


def _numero(valor, nombre, positivo=False):
    try:
        if isinstance(valor, bool):
            raise ValueError()
        numero = float(valor)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("%s debe ser un número finito." % nombre) from error
    if not math.isfinite(numero) or numero < 0 or (positivo and numero == 0):
        raise ValueError("%s debe ser finito y %s." %
                         (nombre, "mayor que cero" if positivo else "no negativo"))
    return numero


def _entero(valor, nombre, minimo=1, maximo=None):
    numero = _numero(valor, nombre)
    if not numero.is_integer() or numero < minimo or (maximo is not None and numero > maximo):
        raise ValueError("%s tiene un valor fuera de rango." % nombre)
    return int(numero)


def _tanda(valores):
    if not isinstance(valores, (list, tuple)) or len(valores) != 4:
        raise ValueError("Cada tanda necesita cuatro casilleros.")
    return [_entero(v, "El casillero", minimo=0, maximo=3) for v in valores]


def contenido_mision(mision):
    """Copia solo lo que se puede pegar; deja fuera el tiempo y el largo."""
    primera = _tanda(mision["primera"])
    segunda = mision.get("segunda")
    return dict(primera=primera, segunda=None if segunda is None else _tanda(segunda),
                bolsa=_entero(mision["bolsa"], "La bolsa", maximo=4))


def listar_misiones(listas, inicio, bpm):
    """Lista todas las entradas reales. t está en segundos y largo en tiempos."""
    bpm = _numero(bpm, "El BPM", positivo=True)
    t = _numero(listas.get("StartDelayTime", inicio), "El arranque")
    columnas = {}
    for nombre in ("Length", "MissionID1", "MissionID2", "KeyPatternID"):
        valor = listas.get(nombre)
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError("Falta la lista %s del chart." % nombre)
        columnas[nombre] = [v.strip() for v in valor.split(",")]
        if any(not v for v in columnas[nombre]):
            raise ValueError("La lista %s tiene una misión vacía." % nombre)
    cantidad = len(columnas["Length"])
    if any(len(valores) != cantidad for valores in columnas.values()):
        raise ValueError("Las listas del chart no tienen la misma cantidad de misiones.")
    resultado = []
    for i in range(cantidad):
        largo = _entero(columnas["Length"][i], "El largo de la misión")
        mid1 = _entero(columnas["MissionID1"][i], "La primera tanda", maximo=625)
        mid2 = _entero(columnas["MissionID2"][i], "La segunda tanda", minimo=0, maximo=625)
        bolsa = _entero(columnas["KeyPatternID"][i], "La bolsa", maximo=4)
        resultado.append(dict(n=i + 1, t=t, largo=largo, primera=N.patron(mid1),
                              segunda=None if mid2 == 0 else N.patron(mid2), bolsa=bolsa))
        t += largo * 60.0 / bpm
    return resultado


def accion_reemplazo(destino, contenido):
    """Prepara una sustitución de contenido, sin cambiar el largo del destino."""
    copia = contenido_mision(contenido)
    largo = _entero(destino["largo"], "El largo del destino")
    if copia["segunda"] is not None and largo < 16:
        raise ValueError("Esta misión dura %d tiempos y no admite una segunda tanda. "
                         "Elegí una misión de al menos 16 tiempos o quitá la segunda "
                         "tanda; el largo del destino se conserva." % largo)
    return dict(tipo="reemplazar", tiempo=_numero(destino["t"], "El tiempo del destino"),
                **copia)


def _reloj(segundos):
    total = int(round(float(segundos) * 1000))
    minutos, resto = divmod(total, 60000)
    segundos, milisegundos = divmod(resto, 1000)
    return "%d:%02d.%03d" % (minutos, segundos, milisegundos)


def _texto_tanda(tanda):
    return "Sin segunda tanda" if tanda is None else " · ".join(
        "SPACE" if x == 0 else str(x) for x in tanda)


class EditorMisiones(tk.Toplevel):
    """Edita misiones existentes y entrega acciones al mapa, sin escribir archivos."""

    def __init__(self, padre, fila, listas, inicio, bpm, al_aplicar, abrir_secciones=None):
        super().__init__(padre)
        self.padre = padre
        self.al_aplicar = al_aplicar
        self.abrir_secciones = abrir_secciones
        self.portapapeles = None
        self._tiempo_seleccionado = None
        self._refrescando = False
        self.title("Misiones: copiar y sustituir")
        self.configure(background=T.FONDO)
        self.geometry("900x560")
        self.minsize(760, 460)
        self.transient(padre)

        cont = T.Desplazable(self, padding=12)
        cont.pack(fill="both", expand=True)
        m = cont.dentro
        self.lbl_identidad = ttk.Label(m, style="Titulo.TLabel", wraplength=820,
                                       justify="left")
        self.lbl_identidad.pack(anchor="w")
        ttk.Label(m, text="Elegí una misión que te guste y pulsá TOMAR MISIÓN. "
                           "Después elegí el destino y pulsá PONER EN ESTA MISIÓN.",
                  wraplength=820, justify="left").pack(anchor="w", pady=(5, 8))

        marco_tabla = ttk.Frame(m)
        marco_tabla.pack(fill="x")
        columnas = ("n", "inicio", "largo", "primera", "segunda", "bolsa")
        self.tabla = ttk.Treeview(marco_tabla, columns=columnas, show="headings",
                                  height=8, selectmode="browse")
        for clave, titulo, ancho in (("n", "Misión", 58), ("inicio", "Inicio", 100),
                                      ("largo", "Largo", 86),
                                      ("primera", "Primera tanda", 194),
                                      ("segunda", "Segunda tanda", 194),
                                      ("bolsa", "Bolsa", 76)):
            self.tabla.heading(clave, text=titulo)
            self.tabla.column(clave, width=ancho, minwidth=ancho, anchor="center")
        vertical = ttk.Scrollbar(marco_tabla, orient="vertical", command=self.tabla.yview)
        horizontal = ttk.Scrollbar(marco_tabla, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        marco_tabla.columnconfigure(0, weight=1)
        self.tabla.bind("<<TreeviewSelect>>", self._seleccionar)

        copia = ttk.Frame(m)
        copia.pack(fill="x", pady=(8, 0))
        self.b_tomar = ttk.Button(copia, text="TOMAR MISIÓN", command=self._tomar)
        self.b_tomar.pack(side="left")
        self.b_poner = ttk.Button(copia, text="PONER EN ESTA MISIÓN", command=self._poner,
                                  state="disabled")
        self.b_poner.pack(side="left", padx=8)
        self.lbl_portapapeles = ttk.Label(m, text="Todavía no tomaste una misión.",
                                          wraplength=820, style="Sub.TLabel")
        self.lbl_portapapeles.pack(anchor="w", pady=(4, 8))

        edicion = ttk.LabelFrame(m, text=" Contenido de la misión seleccionada ", padding=8)
        edicion.pack(fill="x")
        self.lbl_destino = ttk.Label(edicion, text="", wraplength=800)
        self.lbl_destino.pack(anchor="w", pady=(0, 5))
        self.v_primera = [tk.StringVar(value="SPACE") for _ in range(4)]
        self.v_segunda = [tk.StringVar(value="SPACE") for _ in range(4)]
        self.v_dos_tandas = tk.BooleanVar(value=False)
        self.v_bolsa = tk.StringVar(value=BOLSAS[3])
        self._combos_segunda = []
        for numero, variables in enumerate((self.v_primera, self.v_segunda), 1):
            fila_tanda = ttk.Frame(edicion)
            fila_tanda.pack(fill="x", pady=2)
            if numero == 1:
                ttk.Label(fila_tanda, text="Primera tanda:", width=20).pack(side="left")
            else:
                ttk.Checkbutton(fila_tanda, text="Segunda tanda", variable=self.v_dos_tandas,
                                command=self._cambiar_segunda, width=20).pack(side="left")
            for variable in variables:
                combo = ttk.Combobox(fila_tanda, textvariable=variable,
                                     values=CASILLEROS, state="readonly", width=11)
                combo.pack(side="left", padx=(0, 5))
                if numero == 2:
                    self._combos_segunda.append(combo)
        bolsa = ttk.Frame(edicion)
        bolsa.pack(fill="x", pady=(5, 0))
        ttk.Label(bolsa, text="Bolsa de direcciones:", width=20).pack(side="left")
        ttk.Combobox(bolsa, textvariable=self.v_bolsa, values=BOLSAS,
                     state="readonly", width=18).pack(side="left")
        self.b_aplicar = ttk.Button(bolsa, text="APLICAR EDICIÓN", command=self._aplicar)
        self.b_aplicar.pack(side="left", padx=12)
        ttk.Label(edicion, text="Se sustituye el contenido de la misión: su inicio y "
                               "su largo se conservan. SPACE ocupa un casillero sin flechas.",
                  wraplength=800, justify="left", style="Sub.TLabel").pack(
                      anchor="w", pady=(6, 0))

        pie = ttk.Frame(m)
        pie.pack(fill="x", pady=(8, 0))
        if abrir_secciones is not None:
            ttk.Button(pie, text="EDITAR SECCIONES POR TRAMO",
                       command=self._abrir_secciones).pack(side="left")
        ttk.Button(pie, text="Cerrar", command=self.destroy).pack(side="right")
        self.lbl_estado = ttk.Label(m, text="", wraplength=820, justify="left",
                                    style="Sub.TLabel")
        self.lbl_estado.pack(anchor="w", pady=(6, 0))
        self.actualizar(fila, listas, inicio, bpm)

    def actualizar(self, fila, listas, inicio, bpm):
        """Refresca el chart confirmado y mantiene destino y misión tomada."""
        misiones = listar_misiones(listas, inicio, bpm)
        tiempo = self._tiempo_seleccionado
        self.fila, self.listas = dict(fila), copy.deepcopy(listas)
        self.inicio, self.bpm = inicio, float(bpm)
        self.misiones = misiones
        self.lbl_identidad.config(
            text="%s\nID %s  ·  Archivo %s  ·  %s estrellas  ·  %.2f BPM" %
                 (fila.get("Title", "Canción"), fila.get("ID", "?"),
                  fila.get("Filename", "?"), fila.get("Difficulty", "?"), self.bpm))
        self._refrescando = True
        try:
            self.tabla.delete(*self.tabla.get_children())
            self._por_iid = {}
            for mision in misiones:
                iid = str(mision["n"])
                self._por_iid[iid] = mision
                self.tabla.insert("", "end", iid=iid, values=(
                    mision["n"], _reloj(mision["t"]), "%d tiempos" % mision["largo"],
                    _texto_tanda(mision["primera"]), _texto_tanda(mision["segunda"]),
                    mision["bolsa"]))
            elegida = (min(misiones, key=lambda m: abs(m["t"] - tiempo))
                       if tiempo is not None else misiones[0])
            iid = str(elegida["n"])
            self.tabla.selection_set(iid)
            self.tabla.focus(iid)
            self.tabla.see(iid)
        finally:
            self._refrescando = False
        self._seleccionar()

    def _mision_actual(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            raise ValueError("Elegí una misión de la lista.")
        return self._por_iid[seleccion[0]]

    def _seleccionar(self, _evento=None):
        if self._refrescando or not self.tabla.selection():
            return
        mision = self._mision_actual()
        self._tiempo_seleccionado = mision["t"]
        self.lbl_destino.config(text="Destino: misión %d  ·  %s  ·  %d tiempos" %
                                (mision["n"], _reloj(mision["t"]), mision["largo"]))
        for variable, numero in zip(self.v_primera, mision["primera"]):
            variable.set(CASILLEROS[numero] if numero < len(CASILLEROS) else str(numero))
        segunda = mision["segunda"]
        self.v_dos_tandas.set(segunda is not None)
        for variable, numero in zip(self.v_segunda, segunda or [0] * 4):
            variable.set(CASILLEROS[numero] if numero < len(CASILLEROS) else str(numero))
        self.v_bolsa.set(BOLSAS[mision["bolsa"] - 1])
        self._cambiar_segunda()
        self.lbl_estado.config(text="Editá esta misión o elegila como destino de la que tomaste.")

    def _cambiar_segunda(self):
        estado = "readonly" if self.v_dos_tandas.get() else "disabled"
        for combo in self._combos_segunda:
            combo.config(state=estado)

    def _ocupado(self):
        padre, vistos = self.padre, set()
        while padre is not None and id(padre) not in vistos:
            vistos.add(id(padre))
            if getattr(padre, "trabajando", False):
                return True
            padre = getattr(padre, "padre", None)
        return False

    def _tomar(self):
        try:
            mision = self._mision_actual()
            self.portapapeles = contenido_mision(mision)
        except ValueError as error:
            messagebox.showerror("Tomar misión", str(error), parent=self)
            return
        self.lbl_portapapeles.config(text="Tomada: misión %d (%s), ID %s. "
                                          "Elegí otra misión para sustituirla." %
                                     (mision["n"], _reloj(mision["t"]), self.fila.get("ID", "?")))
        self.b_poner.config(state="normal")

    def _enviar_contenido(self, contenido):
        if self._ocupado():
            self.lbl_estado.config(text="Esperá a que termine el trabajo antes de aplicar otra misión.")
            return False
        try:
            accion = accion_reemplazo(self._mision_actual(), contenido)
            self.al_aplicar([accion])
        except (ValueError, OSError, RuntimeError) as error:
            messagebox.showerror("Sustituir misión", str(error), parent=self)
            return False
        # El mapa confirma el resultado mediante actualizar. El callback puede
        # ser asíncrono: no cerrar ni inventar aquí una vista previa confirmada.
        self.lbl_estado.config(text="Cambio solicitado. La lista se actualizará al terminar.")
        return True

    def _aplicar(self):
        try:
            primera = [CASILLEROS.index(v.get()) for v in self.v_primera]
            segunda = ([CASILLEROS.index(v.get()) for v in self.v_segunda]
                       if self.v_dos_tandas.get() else None)
            bolsa = BOLSAS.index(self.v_bolsa.get()) + 1
        except ValueError:
            messagebox.showerror("Editar misión", "Elegí SPACE o de una a tres flechas "
                                 "en cada casillero y una bolsa de 1 a 4.", parent=self)
            return False
        return self._enviar_contenido(dict(primera=primera, segunda=segunda, bolsa=bolsa))

    def _poner(self):
        if self.portapapeles is None:
            self.lbl_estado.config(text="Primero elegí el origen y pulsá TOMAR MISIÓN.")
            return False
        return self._enviar_contenido(self.portapapeles)

    def _abrir_secciones(self):
        if self._ocupado():
            self.lbl_estado.config(text="Esperá a que termine el trabajo antes de editar las secciones.")
            return
        if self.abrir_secciones is not None:
            self.abrir_secciones()
