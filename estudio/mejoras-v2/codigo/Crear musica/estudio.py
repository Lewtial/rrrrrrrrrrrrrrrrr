#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
estudio.py - Estudio LoveRitmo. La ventana.

Todo con clics:
    * lista de las canciones con su estado (verde / amarillo / rojo)
    * revision de cada una, en castellano, diciendo QUE esta mal y POR QUE
    * el arranque se calcula solo (Virtual DJ si lo tiene, si no medido)
    * las flechas y los SPACE se sortean del pozo real de Softnyx
    * un boton para mandarlo todo al juego (con respaldo y mapa SN)

No calcula nada aca adentro: todo esta en nucleo.py.
"""
import copy, math, os, queue, subprocess, sys, threading, time, traceback
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Sin numpy no se puede medir nada. Pasaba de largo y reventaba mas adelante con
# un traceback ilegible, la primera vez que se le pedia analizar una cancion.
# (19/9/2026: el .bat arrancaba con el `pythonw` de la Microsoft Store, que es
# otra instalacion de Python y no tiene numpy.)
try:
    import numpy  # noqa: F401
except ImportError:
    r = tk.Tk()
    r.withdraw()
    messagebox.showerror(
        "Falta numpy",
        "Este Python no tiene numpy y sin eso no puedo medir las canciones.\n\n"
        "Python que se esta usando:\n%s\n\n"
        "Para instalarlo, abri una consola y pone:\n"
        "    \"%s\" -m pip install numpy\n\n"
        "Si tenes mas de un Python instalado, fijate que ESTUDIO.bat apunte al "
        "que ya tiene numpy." % (sys.executable, sys.executable))
    sys.exit(1)

import nucleo as N
import tema as T          # (7/10/2026) tema oscuro
import secciones as S
from mapa_secciones import EdicionSeccionesMapa

COLOR = {N.OK: T.VERDE, N.AVISO: T.AMBAR, N.MAL: T.ROJO}
ICONO = {N.OK: "OK ", N.AVISO: "!  ", N.MAL: "X  "}
FONDO = {N.OK: T.F_OK, N.AVISO: T.F_AVISO, N.MAL: T.F_MAL}
CAMPOS_CHART = tuple(N.LISTAS) + ("BPM", "StartDelayTime", "Difficulty", "CutOff", "Second")


def _descansos_legacy(inferidos, secciones):
    """Evita cargar como descansos antiguos los que ya gestiona el editor."""
    nuevos = [(s["desde"], s["hasta"]) for s in secciones
              if s["tipo"] == "descanso"]
    return tuple((a, b) for a, b in inferidos
                 if not any(a < hasta and b > desde for desde, hasta in nuevos))


class Estudio(tk.Tk):

    def __init__(self):
        tk.Tk.__init__(self)
        self.title("Estudio LoveRitmo  -  cliente %s" % N.CLIENTE)
        # La pestaña Arreglar crecio bastante (el arranque, las estrellas con su
        # velocidad, la escucha y el generar). Con 800 de alto el boton GENERAR
        # quedaba abajo del borde, asi que la ventana arranca mas alta y el
        # minimo sube en consecuencia.
        # (7/10/2026) el tamano sale de la pantalla y el minimo es chico: lo largo (Arreglar)
        # va con barra de desplazamiento, asi que ya no hace falta estirar la ventana
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry("%dx%d+%d+%d" % (min(1500, sw - 60), min(980, sh - 90), 20, 10))
        self.minsize(900, 560)

        self.tabla = None
        self.filas_enviadas = {}  # base del último archivo cargado/guardado
        self.rej = None            # cuadricula de la cancion elegida
        self.cargada = None        # Filename de la que ya esta medida y pintada
        self.ultimos_mudos = ()    # tramos quitados a mano en el ultimo GENERAR
        self.mudos_solo_fila = None  # ID de la fila a la que se le aplican, o
                                     # None = a todas las de la cancion
        self.gen_fila = {}           # ID -> casilla "generar" del paso 2
        self.ultimas_frases = None # None = las propone la musica; si no, los
                                   # segundos que se marcaron a mano en el mapa
        self.ultimas_repes = ()    # tramos (segundos) con REPETICIONES del mapa
        self.ultimos_spaces = ()   # tramos con SOLO SPACE (24/9/2026)
        self.ediciones_secciones = {}  # Filename:ID -> configuración por dificultad
        self.audio_por_borrar = set()  # Filename a mover a la papelera DESPUES de ENVIAR
        self.recortes = {}         # Filename -> (ini, fin): recortes que se aplican al ENVIAR
        self.ultimos_inv = ()      # tramos INVERTIDOS: flechas <-> SPACE
        self.ultimos_suave = ()    # tramos SUAVES: 1-2 flechas con la voz (27/9/2026)
        self.ultimos_ritmos = ()   # "el ritmo sigue desde aca" (segundos, 27/9/2026)
        self.pareja = []           # filas que comparten el mismo archivo
        self.sucias = set()        # IDs cambiados y todavia no enviados
        self.modificadas = set()   # IDs cuyo CHART se cambio en esta sesion (el mapa
                                   # ya no muestra lo guardado). Una copia recien
                                   # hecha esta en `sucias` pero NO aca.
        self.estados = {}          # Filename -> ok/aviso/mal
        self.cola = queue.Queue()
        self.trabajando = False

        self._estilos()
        self._barra()
        self._cuerpo()
        self._pie()
        self.after(80, self._bombear)
        self._en_hilo("Abriendo el musictable...", self._cargar_tabla, self._tabla_lista)

    # ------------------------------------------------------------ apariencia
    def _estilos(self):
        # (7/10/2026) TEMA OSCURO (tema.py) en vez del "vista" claro de Windows
        s = T.aplicar(self)
        s.configure("Titulo.TLabel", font=("Segoe UI", 13, "bold"), foreground=T.TEXTO)
        s.configure("Sub.TLabel", foreground=T.SUAVE)
        s.configure("Grande.TButton", font=("Segoe UI", 10, "bold"), padding=(10, 6))
        s.configure("Enviar.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 7),
                    background="#4b2f6b", foreground="#ffffff")
        s.map("Enviar.TButton", background=[("disabled", T.PANEL), ("active", "#5e3b86")],
              foreground=[("disabled", "#5c6170")])
        s.configure("Lista.Treeview", rowheight=24, font=("Segoe UI", 9))
        s.configure("Firma.TLabel", foreground=T.ACENTO,
                    font=("Segoe UI", 9, "bold"))

    def _barra(self):
        b = ttk.Frame(self, padding=(10, 8))
        b.pack(fill="x")
        ttk.Label(b, text="Estudio LoveRitmo", style="Titulo.TLabel").pack(side="left")
        ttk.Label(b, text="  crear y arreglar canciones  -  CLIENTE %s" % N.CLIENTE,
                  style="Sub.TLabel").pack(
            side="left", padx=(4, 0))

        self.b_enviar = ttk.Button(b, text="ENVIAR AL JUEGO", style="Enviar.TButton",
                                   command=self.enviar, state="disabled")
        self.b_enviar.pack(side="right")
        ttk.Button(b, text="Agregar cancion...", style="Grande.TButton",
                   command=self.agregar).pack(side="right", padx=6)
        ttk.Button(b, text="Descartar", style="Grande.TButton",
                   command=self.descartar).pack(side="right", padx=6)
        ttk.Button(b, text="Recuperar audios", style="Grande.TButton",
                   command=self.recuperar).pack(side="right", padx=6)
        ttk.Button(b, text="Revisar todas", style="Grande.TButton",
                   command=self.revisar_todas).pack(side="right", padx=6)
        ttk.Button(b, text="Virtual DJ...", style="Grande.TButton",
                   command=self.panel_vdj).pack(side="right", padx=6)

        # (7/10/2026) SEGUNDA FILA: con que juego se trabaja, PROBAR EN EL JUEGO y
        # trasladar canciones de un juego a otro. Ver juegos.py y probar.py.
        import juegos as J
        try:
            self.juegos = J.asegurar()
        except Exception:
            self.juegos = []
        b2 = ttk.Frame(self, padding=(10, 0, 10, 6))
        b2.pack(fill="x")
        ttk.Label(b2, text="Juego:", style="Titulo.TLabel").pack(side="left")
        nombres = [p["nombre"] for p in self.juegos]
        act = J.actual() or {}
        este = next((p["nombre"] for p in self.juegos
                     if J._misma(p["juego"], act.get("juego", ""))), act.get("nombre", ""))
        self.v_juego = tk.StringVar(value=este)
        cb = ttk.Combobox(b2, textvariable=self.v_juego, values=nombres, state="readonly",
                          width=34, font=("Segoe UI", 10, "bold"))
        cb.pack(side="left", padx=(8, 4))
        cb.bind("<<ComboboxSelected>>", self.cambiar_juego)
        ttk.Button(b2, text="Agregar otro juego...",
                   command=self.agregar_juego).pack(side="left", padx=4)
        ttk.Label(b2, text="  %s" % N.JUEGO, style="Sub.TLabel").pack(side="left")
        s = ttk.Style(self)
        s.configure("Probar.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 7),
                    background="#1f5c34", foreground="#ffffff")
        s.map("Probar.TButton", background=[("active", "#277a44"), ("pressed", "#1a4d2c")])
        # (7/10/2026) PROBAR = jugar la version ACA MISMO, al instante (jugar.py: las flechas del
        # juego, el teclado y el puntaje). "En el juego real" abre el LoveRitmo (tarda un minuto).
        self.b_probar = ttk.Button(b2, text="▶  PROBAR (jugarla aca)", style="Probar.TButton",
                                   command=self.probar_aqui)
        self.b_probar.pack(side="right")
        ttk.Button(b2, text="En el juego real...",
                   command=self.probar_en_juego).pack(side="right", padx=6)
        ttk.Button(b2, text="Trasladar canciones...",
                   command=self.trasladar).pack(side="right", padx=6)

    # ------------------------------------------------------------ juegos (7/10/2026)
    def _reabrir(self):
        """Vuelve a abrir el Estudio (nucleo.py lee las rutas del juego al arrancar)."""
        subprocess.Popen([sys.executable, os.path.abspath(__file__)],
                         cwd=os.path.dirname(os.path.abspath(__file__)))
        self.destroy()

    def cambiar_juego(self, _e=None):
        import juegos as J
        p = next((x for x in self.juegos if x["nombre"] == self.v_juego.get()), None)
        act = J.actual() or {}
        if p is None or J._misma(p["juego"], act.get("juego", "")):
            return
        volver = lambda: self.v_juego.set(act.get("nombre", ""))
        prob = J.problemas(p)
        if prob:
            messagebox.showerror("No puedo usar ese juego", "\n".join(prob), parent=self)
            volver()
            return
        if self.sucias and not messagebox.askyesno(
                "Cambiar de juego",
                "Hay cambios SIN ENVIAR en %s (%d versiones).\n\nSi cambias de juego se "
                "pierden. ¿Cambiar igual?" % (act.get("nombre", "este juego"), len(self.sucias)),
                parent=self):
            volver()
            return
        J.activar(p)
        self._reabrir()

    def agregar_juego(self):
        """Abre la ventana de las carpetas; al GUARDAR el juego queda en la lista y elegido."""
        self.withdraw()

        def esperar():
            r = subprocess.call([sys.executable, os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "configurar.py")])
            self.cola.put((lambda _r: self._reabrir() if r == 0 else self.deiconify(), None, None))
        threading.Thread(target=esperar, daemon=True).start()

    def probar_en_juego(self):
        """Abre el juego directo en la partida de la version elegida (probar.py)."""
        import juegos as J
        f = self.fila_actual()
        if f is None:
            messagebox.showinfo("Probar en el juego",
                                "Elegi en la lista la VERSION (la fila con las estrellas) "
                                "que queres jugar.", parent=self)
            return
        perfil = J.actual() or {}
        if not perfil.get("arrancar") or not os.path.exists(perfil["arrancar"]):
            messagebox.showerror(
                "Probar en el juego",
                "No se como abrir %s: falta el .bat que arranca el servidor y el juego "
                "(\"arrancar\" en juegos.json).\n\nProbar en el juego necesita un servidor "
                "privado en ESTA PC." % perfil.get("nombre", "este juego"), parent=self)
            return
        if str(f["ID"]) in set(str(x) for x in self.sucias):
            messagebox.showwarning(
                "Probar en el juego",
                "Esta version tiene cambios SIN ENVIAR: el juego tocaria la anterior "
                "(o ninguna, si es nueva).\n\nApreta ENVIAR AL JUEGO y despues proba.",
                parent=self)
            return
        if not messagebox.askyesno(
                "Probar en el juego",
                "Voy a cerrar el juego y el servidor si estan abiertos, y a abrir %s "
                "directo en la partida de:\n\n    %s  -  %s estrellas  (fila %s)\n\n"
                "Tarda un minuto. NO TOQUES EL MOUSE hasta que empiece la cancion (hago "
                "yo los clics: sala, cancion, JUGAR).\n\nCuando termines, cerra el juego "
                "como siempre.\n\n¿Empiezo?" % (perfil.get("nombre"), f["Title"],
                                                  f.get("Difficulty", "?"), f["ID"]),
                parent=self):
            return
        aqui = os.path.dirname(os.path.abspath(__file__))
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        subprocess.Popen([pyw if os.path.exists(pyw) else sys.executable,
                          os.path.join(aqui, "probar.py"), str(f["ID"])], cwd=aqui)
        self.estado.config(text="Abriendo el juego en %s (%s estrellas)... no toques el mouse. "
                                "Lo que va haciendo queda en probar.log" % (f["Title"], f.get("Difficulty")))

    def trasladar(self):
        aqui = os.path.dirname(os.path.abspath(__file__))
        subprocess.Popen([sys.executable, os.path.join(aqui, "trasladar.py")], cwd=aqui)

    def hacer_mia(self):
        """Deja editar una cancion que no se creo con el Estudio (la Kasai, las que se
        agregaron con otro programa). Las del juego original conviene no tocarlas."""
        f = self.fila_actual()
        if f is None:
            return
        if not N.es_original(f):
            messagebox.showinfo("Ya es tuya", "Esta cancion ya se puede editar.", parent=self)
            return
        if not messagebox.askyesno(
                "Permitir editarla",
                "%s (%s) quedo protegida porque no la creo el Estudio.\n\n"
                "Si la hiciste vos con otro programa, o la trajiste de otro juego, "
                "marcala como tuya y vas a poder arreglarla y generarla.\n\n"
                "Las canciones ORIGINALES del juego conviene NO tocarlas.\n\n"
                "¿Marcarla como tuya?" % (f["Title"], f["Filename"]), parent=self):
            return
        N.anotar_mia(f["Filename"])
        self.cargada = None
        self.pintar_lista()
        self.elegir()

    def _cuerpo(self):
        pan = ttk.PanedWindow(self, orient="horizontal")
        pan.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # ---------------- izquierda: la lista
        izq = ttk.Frame(pan)
        pan.add(izq, weight=1)

        f = ttk.Frame(izq)
        f.pack(fill="x", pady=(0, 5))
        ttk.Label(f, text="Buscar:").pack(side="left")
        self.busca = tk.StringVar()
        self.busca.trace_add("write", lambda *a: self.pintar_lista())
        ttk.Entry(f, textvariable=self.busca).pack(side="left", fill="x",
                                                   expand=True, padx=5)
        self.solo_mias = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="solo las mias", variable=self.solo_mias,
                        command=self.pintar_lista).pack(side="left")

        cols = ("estado", "id", "titulo", "est", "bpm", "inicio")
        self.lista = ttk.Treeview(izq, columns=cols, show="headings",
                                  style="Lista.Treeview", selectmode="browse")
        for c, t, w in (("estado", "", 34), ("id", "ID", 52), ("titulo", "Cancion", 250),
                        ("est", "Estrellas", 70), ("bpm", "BPM", 62),
                        ("inicio", "Arranque", 72)):
            self.lista.heading(c, text=t)
            self.lista.column(c, width=w, anchor="w" if c == "titulo" else "center")
        sb = ttk.Scrollbar(izq, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=sb.set)
        self.lista.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.lista.bind("<<TreeviewSelect>>", self.elegir)
        # CLIC DERECHO en una cancion: el menu (pedido de Joel, 23/9/2026)
        self.menu_lista = tk.Menu(self, tearoff=0)
        self.menu_lista.add_command(label="▶ Probar (jugarla acá)",
                                    command=self.probar_aqui)
        self.menu_lista.add_command(label="Probar en el juego real...",
                                    command=self.probar_en_juego)
        self.menu_lista.add_command(label="Permitir editarla (marcarla como mia)...",
                                    command=self.hacer_mia)
        self.menu_lista.add_separator()
        self.menu_lista.add_command(label="Cambiar nombre...",
                                    command=self.cambiar_nombre)
        self.menu_lista.add_separator()
        # tres maneras, de la que mas arregla a la que menos cambia (25/9/2026)
        modos = (("Arreglar el baile (parte las largas)...", "todo"),
                 ("Arreglar el baile SIN agregar flechas...", "sin_flechas"),
                 ("Arreglar SOLO el baile 501 (no cambia nada más)...", "solo501"))
        for texto, modo in modos:
            self.menu_lista.add_command(
                label=texto, command=lambda m=modo: self.arreglar_baile(False, m))
        self.menu_todas = tk.Menu(self.menu_lista, tearoff=0)
        for texto, modo in modos:
            self.menu_todas.add_command(
                label=texto, command=lambda m=modo: self.arreglar_baile(True, m))
        self.menu_lista.add_cascade(label="Arreglar el baile de TODAS mis canciones",
                                    menu=self.menu_todas)
        # mas variedad: una parte de las misiones al baile 501 (27/9/2026)
        self.menu_mezcla = tk.Menu(self.menu_lista, tearoff=0)
        for pc in N.MEZCLA_501:
            self.menu_mezcla.add_command(
                label="%d%% de las misiones con el baile 501" % pc,
                command=lambda p=pc: self.mezclar_bailes(p))
        self.menu_mezcla.add_separator()
        self.menu_mezcla.add_command(label="Sacar la mezcla (todo 511, como antes)",
                                     command=lambda: self.mezclar_bailes(0))
        self.menu_lista.add_cascade(label="Más variedad de baile (mezclar 501)",
                                    menu=self.menu_mezcla)
        self.menu_lista.add_command(label="Rápida: pasar las 3 flechas a 2...",
                                    command=self.bajar_tres)
        self.menu_lista.add_separator()
        self.menu_lista.add_command(label="Eliminar SOLO esta versión...",
                                    command=self.eliminar_version)
        self.menu_lista.add_command(label="Eliminar canción...",
                                    command=self.eliminar_cancion)
        self.lista.bind("<Button-3>", self._menu_de_lista)
        self.lista.tag_configure("ok", background=T.F_OK)
        self.lista.tag_configure("aviso", background=T.F_AVISO)
        self.lista.tag_configure("mal", background=T.F_MAL)
        self.lista.tag_configure("sucia", font=("Segoe UI", 9, "bold"))

        # ---------------- derecha
        der = ttk.Frame(pan)
        pan.add(der, weight=2)

        self.cabecera = ttk.Label(der, text="Elegi una cancion de la lista",
                                  style="Titulo.TLabel")
        self.cabecera.pack(anchor="w")
        self.subcab = ttk.Label(der, text="", style="Sub.TLabel")
        self.subcab.pack(anchor="w", pady=(0, 6))

        nb = ttk.Notebook(der)
        nb.pack(fill="both", expand=True)
        self.tab_rev = ttk.Frame(nb, padding=8)
        self.tab_arr = ttk.Frame(nb, padding=8)
        self.tab_fic = ttk.Frame(nb, padding=8)
        self.tab_man = ttk.Frame(nb, padding=8)
        nb.add(self.tab_rev, text="  Revision  ")
        nb.add(self.tab_arr, text="  Arreglar  ")
        nb.add(self.tab_fic, text="  La ficha  ")
        nb.add(self.tab_man, text="  El manual  ")
        self.nb = nb

        # revision
        self.revbox = tk.Text(self.tab_rev, wrap="word", font=("Segoe UI", 9),
                              relief="flat", background=T.CAJA, padx=8, pady=6)
        rb = ttk.Scrollbar(self.tab_rev, orient="vertical", command=self.revbox.yview)
        self.revbox.configure(yscrollcommand=rb.set, state="disabled")
        self.revbox.pack(side="left", fill="both", expand=True)
        rb.pack(side="right", fill="y")
        for e, c in COLOR.items():
            self.revbox.tag_configure(e, foreground=c,
                                      font=("Segoe UI", 9, "bold"))
            self.revbox.tag_configure(e + "_f", background=FONDO[e])
        self.revbox.tag_configure("det", lmargin1=26, lmargin2=26, spacing3=8)
        self.revbox.tag_configure("portada", justify="center", spacing1=40)
        self.revbox.tag_configure("firma", justify="center", spacing1=14,
                                  foreground=T.ACENTO,
                                  font=("Segoe UI", 10, "bold"))
        self._portada()

        # LA FICHA: todo lo que el musictable guarda de esta cancion, con lo que
        # significa cada numero. Las cuentas estan en nucleo.ficha_de_par(): la
        # ventana solo pinta.
        self.ficbox = self._caja(self.tab_fic)
        # EL MANUAL: lo mismo que los cinco documentos de
        # "INFORMACION CORRECTO PARA CREAR MUSICA EN EL JUEGO", adentro del
        # programa, para no tener que ir a buscarlo. Se llena una sola vez.
        self.manbox = self._caja(self.tab_man)
        self._pintar_manual()

        self._panel_arreglar()

    def _caja(self, padre):
        """Un cuadro de texto de solo lectura, con barra y los mismos colores."""
        caja = tk.Text(padre, wrap="word", font=("Segoe UI", 9), relief="flat",
                       background=T.CAJA, padx=8, pady=6)
        sb = ttk.Scrollbar(padre, orient="vertical", command=caja.yview)
        caja.configure(yscrollcommand=sb.set, state="disabled")
        caja.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        caja.tag_configure("seccion", foreground=T.ACENTO, spacing1=12, spacing3=4,
                           font=("Segoe UI", 10, "bold"))
        caja.tag_configure("etiqueta", font=("Segoe UI", 9, "bold"))
        caja.tag_configure("valor", font=("Consolas", 10))
        caja.tag_configure("nota", lmargin1=26, lmargin2=26, spacing3=6,
                           foreground=T.SUAVE)
        caja.tag_configure("ojo", lmargin1=26, lmargin2=26, spacing3=6,
                           foreground=T.ROJO, font=("Segoe UI", 9, "bold"))
        caja.tag_configure("fijo", font=("Consolas", 9))
        return caja

    def _pintar_manual(self):
        """Todo lo que hay que saber, sin salir del programa."""
        self.manbox.configure(state="normal")
        self.manbox.delete("1.0", "end")
        self.manbox.insert("end", "EL MANUAL\n", "seccion")
        self.manbox.insert(
            "end", "Esto es lo mismo que esta en los cinco documentos de "
            "INFORMACION CORRECTO PARA CREAR MUSICA EN EL JUEGO y en las PARTES "
            "6 a 9 del informe maestro. Esta aca para no tener que ir a "
            "buscarlo.\n", "nota")
        # COMO ESTA LA TABLA HOY. Solo se puede contar con el musictable ya
        # abierto, asi que esto se vuelve a pintar cuando termina de cargar
        # (ver _tabla_lista).
        if self.tabla is not None:
            self.manbox.insert("end", "\nCOMO ESTA EL MUSICTABLE HOY\n", "seccion")
            try:
                for etiqueta, valor, nota in N.inventario(self.tabla):
                    self.manbox.insert("end", "   %s: " % etiqueta, "etiqueta")
                    self.manbox.insert("end", "%s\n" % valor, "valor")
                    self.manbox.insert("end", nota + "\n", "nota")
            except Exception as e:
                self.manbox.insert("end", "   no lo pude contar: %s\n" % e,
                                   "nota")
        for titulo, lineas in N.manual():
            self.manbox.insert("end", "\n" + titulo + "\n", "seccion")
            for ln in lineas:
                self.manbox.insert("end", "   " + ln + "\n", "fijo")

        # DE QUE DEPENDE, y si esta. Va al final y se mira de un vistazo: lo que
        # falta sale en rojo con que hacer. El motor viaja adentro del programa;
        # de afuera queda ffmpeg, numpy, el juego y el snb_local (22/9/2026).
        self.manbox.insert("end", "\nDE QUE DEPENDE ESTE PROGRAMA\n", "seccion")
        try:
            for nombre, ok, detalle in N.dependencias():
                self.manbox.insert("end", "   %-14s " % nombre, "etiqueta")
                self.manbox.insert("end", "%s\n" % ("esta" if ok else "FALTA"),
                                   "valor" if ok else "ojo")
                self.manbox.insert("end", detalle + "\n",
                                   "nota" if ok else "ojo")
        except Exception as e:
            self.manbox.insert("end", "   no lo pude revisar: %s\n" % e, "nota")
        self.manbox.configure(state="disabled")

    def _pintar_ficha(self):
        """La ficha de la cancion elegida: las 23 columnas, explicadas."""
        self.ficbox.configure(state="normal")
        self.ficbox.delete("1.0", "end")
        if not self.pareja:
            self.ficbox.configure(state="disabled")
            return
        for sec in N.ficha_de_par(self.pareja, self.rej, self.tabla):
            self.ficbox.insert("end", sec["titulo"] + "\n", "seccion")
            for etiqueta, valor, nota in sec["filas"]:
                self.ficbox.insert("end", "   %s: " % etiqueta, "etiqueta")
                self.ficbox.insert("end", "%s\n" % valor, "valor")
                if nota:
                    grave = ("**" in nota or "NO ESTA" in nota
                             or "NO COINCIDE" in nota)
                    self.ficbox.insert("end", nota + "\n",
                                       "ojo" if grave else "nota")
        self.ficbox.configure(state="disabled")

    def _portada(self):
        """La imagen del arranque, mientras no hay ninguna cancion elegida.

        Va DENTRO del cuadro de la revision, asi que se borra sola en cuanto se
        elige una cancion: no tapa nada ni mueve ningun control. Si el .png no
        esta, no pasa nada — el programa sigue igual.
        """
        self.revbox.configure(state="normal")
        self.revbox.delete("1.0", "end")
        try:
            self.img_portada = tk.PhotoImage(file=str(N.ESTUDIO / "portada.png"))
            self.revbox.insert("end", "\n", "portada")
            self.revbox.image_create("end", image=self.img_portada)
            self.revbox.insert("end", "\n", "portada")
        except Exception:
            pass
        self.revbox.insert("end", "Estudio LoveRitmo\n", "firma")
        self.revbox.configure(state="disabled")

    def _panel_arreglar(self):
        """La pestaña Arreglar, en 4 pasos (23/9/2026).

        Antes no entraba en la ventana: 'Medir el BPM' y 'solo los tics' quedaban
        cortados a la derecha y el resultado de GENERAR abajo del borde. Ahora son
        los mismos 4 pasos que el mapa, con textos de una o dos lineas.
        """
        # (7/10/2026) con barra de desplazamiento: antes, con la ventana chica, el paso 2 y
        # GENERAR quedaban cortados abajo y solo se veian estirando la ventana
        cont = T.Desplazable(self.tab_arr)
        cont.pack(fill="both", expand=True)
        p = cont.dentro

        # --- PASO 1: el arranque
        g1 = ttk.LabelFrame(p, text=" Paso 1  ·  El arranque ", padding=6)
        g1.pack(fill="x", pady=(0, 6))
        f = ttk.Frame(g1)
        f.pack(fill="x")
        ttk.Label(f, text="Empieza en el segundo").pack(side="left")
        self.v_ini = tk.StringVar(value="")
        e = ttk.Entry(f, textvariable=self.v_ini, width=10,
                      font=("Consolas", 11, "bold"))
        e.pack(side="left", padx=6)
        ttk.Button(f, text="◂ un compás",
                   command=lambda: self.correr(-1)).pack(side="left", padx=2)
        ttk.Button(f, text="un compás ▸",
                   command=lambda: self.correr(+1)).pack(side="left", padx=2)
        ttk.Button(f, text="Pegar a la cuadrícula",
                   command=self.pegar).pack(side="left", padx=(8, 2))
        ttk.Button(f, text="Calcularlo solo",
                   command=self.auto_inicio).pack(side="left", padx=2)
        self.lbl_ini = ttk.Label(g1, text="", style="Sub.TLabel", wraplength=680,
                                 justify="left")
        self.lbl_ini.pack(anchor="w", pady=(4, 0))

        ttk.Label(g1, text="Arranques posibles, del más parecido a Softnyx al menos "
                           "(doble clic para usar uno):").pack(anchor="w", pady=(4, 0))
        self.cands = ttk.Treeview(g1, columns=("t", "pct", "prob", "por"),
                                  show="headings", height=5, selectmode="browse")
        for c, t, w, a in (("t", "segundo", 70, "center"),
                           ("pct", "% canción", 70, "center"),
                           ("prob", "chance", 60, "center"),
                           ("por", "por qué", 540, "w")):
            self.cands.heading(c, text=t)
            self.cands.column(c, width=w, anchor=a, stretch=(c == "por"))
        self.cands.pack(fill="x")
        self.cands.bind("<Double-1>", self.tomar_candidato)

        # --- PASO 2: las estrellas y el BPM
        g2 = ttk.LabelFrame(p, text=" Paso 2  ·  Las estrellas y el BPM ", padding=6)
        g2.pack(fill="x", pady=(0, 6))
        self.filas_est = ttk.Frame(g2)
        self.filas_est.pack(fill="x")
        fb = ttk.Frame(g2)
        fb.pack(fill="x", pady=(6, 0))
        ttk.Button(fb, text="Arreglar las estrellas",
                   command=self.arreglar_estrellas).pack(side="left")
        ttk.Button(fb, text="¿Qué BPM poner?...",
                   command=self.ventana_bpm).pack(side="left", padx=6)
        ttk.Button(fb, text="Medir el BPM del audio",
                   command=self.medir_bpm).pack(side="left")
        self.lbl_est = ttk.Label(g2, text="", style="Sub.TLabel", wraplength=680,
                                 justify="left")
        self.lbl_est.pack(anchor="w", pady=(4, 0))

        # --- PASO 3: escuchar y mirar
        g3 = ttk.LabelFrame(p, text=" Paso 3  ·  Escuchar y mirar ", padding=6)
        g3.pack(fill="x", pady=(0, 6))
        f3 = ttk.Frame(g3)
        f3.pack(fill="x")
        ttk.Button(f3, text="ABRIR EL MAPA", style="Enviar.TButton",
                   command=self.ventana_entera).pack(side="left")
        ttk.Button(f3, text="▶ ESCUCHAR", style="Grande.TButton",
                   command=self.escuchar).pack(side="left", padx=(8, 0))
        ttk.Button(f3, text="SIMULAR...", style="Grande.TButton",
                   command=self.ventana_simular).pack(side="left", padx=(6, 0))
        ttk.Button(f3, text="■ Parar", command=self.parar).pack(side="left", padx=6)
        f3b = ttk.Frame(g3)
        f3b.pack(fill="x", pady=(4, 0))
        ttk.Label(f3b, text="ESCUCHAR dura").pack(side="left")
        self.v_seg = tk.IntVar(value=20)
        ttk.Spinbox(f3b, from_=5, to=90, increment=5, textvariable=self.v_seg,
                    width=4).pack(side="left", padx=4)
        ttk.Label(f3b, text="segundos").pack(side="left")
        self.v_solotic = tk.BooleanVar(value=False)
        ttk.Checkbutton(f3b, text="solo los tics (sin música)",
                        variable=self.v_solotic).pack(side="left", padx=(12, 0))
        self.v_marcar = tk.BooleanVar(value=True)
        ttk.Checkbutton(f3b, text="marcar las misiones",
                        variable=self.v_marcar).pack(side="left", padx=(12, 0))
        self.lbl_oir = ttk.Label(
            g3, style="Sub.TLabel", wraplength=680, justify="left",
            text="Tic agudo = flecha  ·  tic grave = SPACE  ·  golpe seco = empieza una "
                 "misión.  En el MAPA se ve y se arregla todo: arranque, frases, "
                 "cortes y repeticiones.")
        self.lbl_oir.pack(anchor="w", pady=(4, 0))

        # --- PASO 4: generar
        g4f = ttk.LabelFrame(p, text=" Paso 4  ·  Generar ", padding=6)
        g4f.pack(fill="both", expand=True)
        g4 = ttk.Frame(g4f)
        g4.pack(fill="x")
        ttk.Button(g4, text="GENERAR EL CHART", style="Enviar.TButton",
                   command=self.generar).pack(side="left")
        ttk.Button(g4, text="Crear una copia para probar",
                   command=self.copiar).pack(side="left", padx=(8, 0))
        g4b = ttk.Frame(g4f)
        g4b.pack(fill="x", pady=(4, 0))
        self.v_musica = tk.BooleanVar(value=False)
        ttk.Checkbutton(g4b, variable=self.v_musica,
                        text="flechas sobre los golpes",
                        command=self._cambio_musica).pack(side="left")
        # LAS MISIONES LARGAS. Softnyx alarga una mision (20, 24, 28 o 32
        # tiempos) cuando la cancion mete un compas de mas, asi la siguiente
        # vuelve a arrancar con la frase. Lo hace en el 68% de sus charts. Ver
        # `nucleo.largos_auto`.
        self.v_frases = tk.BooleanVar(value=True)
        ttk.Checkbutton(g4b, variable=self.v_frases,
                        text="misiones que sigan las frases (como Softnyx)",
                        command=self._cambio_musica).pack(side="left", padx=(12, 0))
        # LOS SPACE COMO LOVERITMO 2020 (27/9/2026, 6.3.48): menos SPACE en las
        # dificiles y puestos donde la musica pega fuerte, como Softnyx. Se
        # prende sola en las canciones nuevas; en las que ya estaban queda como
        # se generaron (nucleo.estilo_de), asi no les cambian las flechas.
        self.v_estilo = tk.BooleanVar(value=False)
        # (7/10/2026) las 5 casillas en una sola fila se cortaban a la derecha: van en dos
        g4b = ttk.Frame(g4f)
        g4b.pack(fill="x", pady=(2, 0))
        ttk.Checkbutton(g4b, variable=self.v_estilo,
                        text="SPACE como LoveRitmo 2020",
                        command=self._cambio_musica).pack(side="left")
        # extras() se llama desde los hilos de fondo, y ahi no se puede leer
        # una variable de tkinter: se guarda una copia comun
        self._estilo2020 = False

        def _estilo_cambio(*_a):
            self._estilo2020 = bool(self.v_estilo.get())
            self._texto_musica()
        self.v_estilo.trace_add("write", _estilo_cambio)
        # FLECHAS POR PARTES (27/9/2026, 6.3.54): la musica decide donde van las
        # flechas (fuerte / suave / subida); Softnyx solo pone los topes. Como el
        # estilo de SPACE: prendida en las nuevas, en las viejas como se generaron
        # (nucleo.partes_de), asi regenerar una vieja no le cambia el estilo.
        self.v_partes = tk.BooleanVar(value=False)
        ttk.Checkbutton(g4b, variable=self.v_partes,
                        text="flechas por partes (la música decide)",
                        command=self._cambio_musica).pack(side="left", padx=(12, 0))
        self._partes = False

        def _partes_cambio(*_a):
            self._partes = bool(self.v_partes.get())
            self._texto_musica()
        self.v_partes.trace_add("write", _partes_cambio)
        # MENOS SPACE (2/10/2026): apagada por defecto (lo natural es como
        # Softnyx). Se guarda al toque por cancion (nucleo.anotar_menos_space),
        # asi ESCUCHAR, SIMULAR, el mapa y GENERAR la respetan sin pasarla.
        self.v_menos_sp = tk.BooleanVar(value=False)
        ttk.Checkbutton(g4b, variable=self.v_menos_sp,
                        text="menos SPACE (1 por tanda)",
                        command=self._cambio_menos_space).pack(side="left", padx=(12, 0))
        # NO hay control de SPACE, y no es un olvido: el SPACE que se ve lo pone
        # el juego en cada casillero SIN FLECHAS (comprobado el 20/9/2026). El
        # MissionID2 no es el SPACE: es la SEGUNDA TANDA (2/10/2026, ver
        # nucleo.TANDA2_*), y la sortea `generar` como Softnyx.
        self.v_space = tk.StringVar(value="como Softnyx")
        self.v_sinsp = tk.BooleanVar(value=False)
        # QUITAR = DESCANSO: lo quitado en el mapa no deja una mision vacia (que
        # el juego llena de SPACE) sino que alarga la de antes: no sale nada.
        # Ver `nucleo.saltar_descansos`. La casilla esta en el mapa.
        # POR DEFECTO EL PERSONAJE BAILA SIEMPRE (24/9/2026, pedido de Joel: "que
        # cada cancion que se cree ya salga bien los bailes"). Lo quitado queda
        # como mision sin flechas (salen SPACE). "No sale nada" hace caminar al
        # personaje (6.3.30) y ahora hay que elegirlo a proposito en el paso 3.
        self.v_descanso = tk.BooleanVar(value=False)
        # QUE NO SE QUEDE CAMINANDO: parte las misiones largas (nucleo.SIN_CAMINAR)
        self.v_sin_caminar = tk.BooleanVar(value=True)
        N.SIN_CAMINAR = True
        self.lbl_musica = ttk.Label(g4f, style="Sub.TLabel", justify="left",
                                    wraplength=680)
        self.lbl_musica.pack(anchor="w", pady=(4, 4))
        self._texto_musica()
        self.v_space.trace_add("write", lambda *a: self._texto_musica())

        self.result = tk.Text(g4f, height=6, wrap="word", font=("Consolas", 9),
                              relief="flat", background=T.CAJA2, padx=8, pady=6)
        self.result.pack(fill="both", expand=True)
        self.result.configure(state="disabled")

    def _pie(self):
        f = ttk.Frame(self, padding=(10, 4))
        f.pack(fill="x")
        self.estado = ttk.Label(f, text="", style="Sub.TLabel")
        self.estado.pack(side="left")
        self.barra = ttk.Progressbar(f, mode="indeterminate", length=160)

    # ------------------------------------------------------------- hilos
    def _en_hilo(self, texto, trabajo, despues):
        if self.trabajando:
            return
        self.trabajando = True
        self.estado.config(text=texto)
        self.barra.pack(side="right")
        self.barra.start(12)

        def correr():
            # BaseException, no Exception. El 22/9/2026 `musictable_tool` tiro un
            # `SystemExit` (que NO es Exception) y este hilo se murio sin decir
            # nada: ni cartel, ni "Listo", y `trabajando` quedaba en True, asi
            # que los botones pesados no andaban mas hasta reiniciar. Nada que
            # pase alla adentro puede volver a quedar mudo.
            try:
                r = trabajo()
                self.cola.put((despues, r, None))
            except BaseException:
                self.cola.put((despues, None, traceback.format_exc()))
        threading.Thread(target=correr, daemon=True).start()

    def _anotar_error(self, que, texto):
        """Deja el error en `errores.log`, al lado del Estudio.

        Con `pythonw` no hay consola: si algo revienta fuera de un cartel, el
        traceback se pierde y no queda ni rastro de por que. Esto es ese rastro.
        """
        try:
            with open(N.ESTUDIO / "errores.log", "a", encoding="utf-8") as f:
                f.write("\n%s  %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                            que, texto))
        except Exception:
            pass

    def _bombear(self):
        """Saca de la cola lo que terminaron los hilos y lo aplica en pantalla.

        POR QUE EL `finally` (25/9/2026): antes `fn(r)` estaba adentro de un
        `try` que solo atrapaba `queue.Empty`. Si el callback reventaba -- por
        ejemplo el que dibuja el mapa -- la excepcion se escapaba y el
        `self.after(80, ...)` del final NO se volvia a agendar: **el pump moria
        para siempre**. A partir de ahi cada accion de fondo arrancaba su hilo,
        terminaba, dejaba el resultado en la cola y nadie lo sacaba nunca: el
        cartel ("Preparando 3:24 de audio...") se quedaba puesto, la CPU en
        cero, la ventana respondiendo, y todo mudo. Le paso a Joel dos veces
        seguidas el 25/9, y con `pythonw` el traceback no iba a ningun lado.

        Ahora: el callback tiene su propio try (si falla, se avisa y el pump
        sigue vivo) y el `after` se re-agenda SIEMPRE.
        """
        try:
            while True:
                try:
                    fn, r, err = self.cola.get_nowait()
                except queue.Empty:
                    break
                self.trabajando = False
                self.barra.stop()
                self.barra.pack_forget()
                self.estado.config(text="")
                if err:
                    self._anotar_error("en el hilo de fondo", err)
                    messagebox.showerror("Algo se rompio", err)
                    continue
                try:
                    fn(r)
                except BaseException:
                    t = traceback.format_exc()
                    self._anotar_error("al aplicar el resultado en pantalla", t)
                    messagebox.showerror(
                        "Algo se rompio al mostrarlo",
                        "El trabajo termino bien, pero fallo al dibujarlo.\n\n"
                        "El Estudio SIGUE ANDANDO: no hace falta reiniciarlo.\n\n"
                        "Quedo anotado en errores.log\n\n%s" % t)
        finally:
            # Pase lo que pase, el pump se vuelve a agendar.
            self.after(80, self._bombear)

    # ------------------------------------------------------------- tabla
    def _cargar_tabla(self):
        return N.Tabla()

    def _tabla_lista(self, t):
        self.tabla = t
        self.filas_enviadas = {str(f["ID"]): copy.deepcopy(f) for f in t.filas}
        self.cargada = None
        self.rej = None
        self._portada()
        self.sucias.clear()
        self.b_enviar.config(state="disabled")
        # (7/10/2026) sin ninguna cancion propia todavia (Estudio recien instalado, o un juego
        # nuevo del selector) "solo las mias" dejaba la lista VACIA: se muestran todas
        if self.solo_mias.get() and not any(not N.es_original(f) for f in t.filas):
            self.solo_mias.set(False)
        self.pintar_lista()
        self.estado.config(text="%d filas en el musictable" % len(t.filas))
        self._pintar_manual()          # ahora el inventario se puede contar
        # si faltan audios, sin ellos no se puede medir nada: ofrecer rehacerlos
        self.after(200, lambda: self.recuperar(callado=True))

    def descartar(self):
        if self.sucias and not messagebox.askyesno(
                "Descartar", "Hay %d filas cambiadas sin enviar. Se pierden. Sigo?"
                % len(self.sucias)):
            return
        self.modificadas.clear()
        self.recortes.clear()
        self._en_hilo("Volviendo a leer el musictable...",
                      self._cargar_tabla, self._tabla_lista)

    def pintar_lista(self):
        if not self.tabla:
            return
        eleg = self.lista.selection()
        eleg = self.lista.item(eleg[0])["values"][1] if eleg else None
        self.lista.delete(*self.lista.get_children())
        txt = self.busca.get().strip().lower()
        for f in self.tabla.filas:
            if self.solo_mias.get() and N.es_original(f):
                continue
            if txt and txt not in (f["Title"] + " " + f["Singer"] + " " +
                                   f["Filename"] + " " + f["ID"]).lower():
                continue
            est = self.estados.get(f["ID"], "")
            tags = [est] if est else []
            if f["ID"] in self.sucias:
                tags.append("sucia")
            self.lista.insert("", "end", values=(
                {"": "", N.OK: "OK", N.AVISO: "!", N.MAL: "X"}.get(est, ""),
                f["ID"], f["Title"],
                "*" * min(int(float(f["Difficulty"] or 0)), 10),
                f["BPM"], f["StartDelayTime"]), tags=tags)
        if eleg:
            for i in self.lista.get_children():
                if str(self.lista.item(i)["values"][1]) == str(eleg):
                    self.lista.selection_set(i)
                    break

    # ------------------------------------------------------------ eleccion
    def fila_actual(self):
        s = self.lista.selection()
        if not s:
            return None
        return self.tabla.por_id(self.lista.item(s[0])["values"][1])

    def elegir(self, _e=None):
        """Se dispara al tocar una fila de la lista.

        OJO con el bucle: `_pintar_revision` termina llamando a `pintar_lista`,
        que rehace el arbol y vuelve a marcar la fila, y eso emite otra vez
        <<TreeviewSelect>>. Sin el corte de abajo el programa se queda midiendo
        la misma cancion para siempre, quemando CPU y con la barra parpadeando.
        """
        f = self.fila_actual()
        if f is None or self.trabajando:
            return
        if self.cargada == f["Filename"] and (self.rej is not None
                                              or getattr(self, "_medido", None) == f["Filename"]):
            # ya esta medida y pintada: no hay nada que hacer. (7/10/2026) TAMBIEN si la
            # medicion FALLO (sin audio): antes se volvia a medir en bucle y los cuadros
            # del paso 2 parpadeaban sin parar.
            return
        if self.cargada != f["Filename"]:
            # Un mapa conserva su fila y sus opciones. Hay que cerrarlo antes
            # de cargar otra canción para que no edite el nuevo panel.
            for ventana in list(self.winfo_children()):
                if isinstance(ventana, VentanaEntera):
                    ventana.cerrar()
        self.cargada = f["Filename"]
        self.ultimos_mudos = ()
        self.mudos_solo_fila = None
        self.ultimas_frases = None
        self.ultimas_repes = ()
        self.ultimos_spaces = ()
        self.ultimos_inv = ()
        self.ultimos_suave = ()
        self.ultimos_ritmos = ()
        self.parar()
        self.pareja = [x for x in self.tabla.filas if x["Filename"] == f["Filename"]]
        try:
            for version in self.pareja:
                self.config_secciones(version)
        except (OSError, ValueError) as error:
            messagebox.showerror("Configuración de secciones", str(error), parent=self)
            self.cargada = None
            return
        # los descansos que la cancion YA TIENE guardados: asi el mapa los muestra
        # y un GENERAR no los borra sin avisar
        if not N.es_original(f):
            fila_base = self.pareja[0]
            self.ultimos_mudos = _descansos_legacy(
                N.descansos_guardados(fila_base),
                self.config_secciones(fila_base)["secciones"])
            # y los "el ritmo sigue desde aca" que ya tiene: sin esto, un cambio
            # en el mapa los desarmaria
            self.ultimos_ritmos = tuple(N.ritmos_guardados(self.pareja[0]))
            # EL PASO 3 SE PONE COMO ESTA LA CANCION EN EL JUEGO (24/9/2026). Si ya
            # tiene descansos guardados, estan "sin nada" (asi se crearon): el mapa
            # tiene que mostrarlos asi. Antes quedaba "sigue bailando" (el defecto
            # para lo nuevo) y Joel vio SPACE en la Russian Roulette original, que
            # en el juego no los tiene. Sin descansos: el defecto, sigue bailando.
            self.v_descanso.set(bool(self.ultimos_mudos))
            # LO QUE SE CONFIGURO, LEIDO DEL CHART GUARDADO (27/9/2026). Joel dejo
            # Kulipandeo con frases a mano y, al reabrir, el mapa mostraba otra
            # cosa: las frases marcadas vivian solo en memoria. Con esto, las 68
            # filas de Joel se regeneran con los MISMOS largos que tienen.
            cfg = N.config_guardada(self.pareja[0])
            # con frases: esas; todas de 16: una lista VACIA (= todas de 16 para
            # esta cancion, sin apagar la casilla, que vale para las nuevas)
            self.ultimas_frases = tuple(cfg["frases"] or ())
            self.v_sin_caminar.set(cfg["sin_caminar"] is not False)
            N.SIN_CAMINAR = bool(self.v_sin_caminar.get())
        # el estilo de SPACE con que se genero (las viejas: el clasico)
        self.v_estilo.set(N.estilo_de(f["Filename"]) == "2020")
        self.v_partes.set(N.partes_de(f["Filename"]))
        self.v_menos_sp.set(N.menos_space_de(f["Filename"]))
        self.cabecera.config(text=f["Title"])
        self.subcab.config(text="%s  |  archivo %s  |  %s"
                           % (f["Singer"], f["Filename"],
                              "protegida (no la creo el Estudio) - si la hiciste vos: clic derecho > Permitir editarla"
                              if N.es_original(f) else
                              "tuya (%s)" % " y ".join(
                                  "%s estrellas" % x["Difficulty"] for x in self.pareja)))
        self._en_hilo("Midiendo %s..." % f["Filename"],
                      lambda: N.rejilla_de(f), self._rejilla_elegida)

    def _rejilla_elegida(self, rej):
        """La cuadricula recien medida de la cancion elegida, con lo guardado.

        EL BPM: la cuadricula refina el BPM de la tabla (+-0.6%) y puede dar
        otro por centesimas. Kulipandeo esta guardada a 183.94 y la medicion da
        183.92: el mapa no la reconocia como la guardada (pide 0.01) y mostraba
        una vista previa con lo que viene por defecto; y un GENERAR le habria
        cambiado el BPM a Joel sin avisar. Si la fila es nuestra y su BPM esta a
        menos del 0.3% de lo medido (a x1, x2, x3 o x4), manda el de la fila.

        EL FINAL: si el chart guardado termina una mision o mas antes de que se
        acabe el ritmo, ese final quedo sin misiones a proposito: se carga como
        descanso, asi un GENERAR no le agrega misiones de SPACE al final.
        """
        if self.pareja and not any(N.es_original(x) for x in self.pareja):
            base = float(rej["bpm"])
            for fila in self.pareja:
                try:
                    b = float(fila["BPM"])
                except (TypeError, ValueError):
                    continue
                if not (math.isfinite(base) and base > 0 and
                        math.isfinite(b) and b > 0):
                    continue
                factor = min(range(1, 5), key=lambda k: abs(b / base - k))
                b1 = b / factor
                if abs(b1 - base) / base < 0.003:
                    rej["bpm"] = b1
                    rej["per"] = 60.0 / b1
                    rej["compas"] = 4 * rej["per"]
                    break
            try:
                f0 = self.pareja[0]
                per0 = 60.0 / float(f0["BPM"])
                largos = [int(float(x)) for x in f0["Length"].split(",") if x.strip()]
                fin_chart = float(f0["StartDelayTime"]) + sum(largos) * per0
                dur = float(rej.get("dur") or 0)
                fb = min(rej.get("fin_beat") or dur, dur)
                if dur and fb - fin_chart > 16 * per0 - 0.05:
                    self.ultimos_mudos = tuple(self.ultimos_mudos) + (
                        (round(fin_chart, 4), round(dur, 4)),)
                    self.v_descanso.set(True)
            except (KeyError, ValueError, ZeroDivisionError):
                pass
        self._rejilla_lista(rej)

    def medir_bpm(self):
        """Vuelve a medir la cuadricula sacando el BPM DEL AUDIO.

        Para que existe (22/9/2026): `agregar_ogg` copiaba una fila como molde y
        la cancion nueva heredaba SU BPM, porque `ab.refinar` no busca el tempo,
        lo afina +-0.6% alrededor del que se le pase. Physical quedo en 282.72
        porque Everlasting, la fila de al lado, tiene 284; su tempo real es 147.

        Las canciones nuevas ya salen bien. Esto es para las que quedaron mal
        antes del arreglo. NO se hace solo: el BPM de la tabla es el que usa el
        juego, y eso no se cambia sin que lo pidas.
        """
        f = self.fila_actual()
        if f is None or not self.pareja:
            return
        if not messagebox.askyesno(
                "Medir el BPM del audio",
                "Voy a medir la cancion SIN mirar el BPM de la fila (%s).\n\n"
                "Si sale distinto, el chart hay que rehacerlo con GENERAR EL "
                "CHART: el que tenes ahora esta escrito sobre la cuadricula "
                "vieja.\n\nSigo?" % f.get("BPM")):
            return

        def trabajo():
            return N.rejilla_de(f, forzar_medida=True, buscar_bpm=True)

        def despues(rej):
            if rej is None:
                messagebox.showerror("Medir el BPM del audio",
                                     "No pude medir el audio.")
                return
            viejo = f.get("BPM")
            self._rejilla_lista(rej)
            messagebox.showinfo(
                "Medir el BPM del audio",
                "El audio da %.2f BPM (la fila dice %s).\n\n"
                "Nitidez de la cuadricula: %.2f. De los 117 charts oficiales "
                "con audio, el peor da 1.75 y ninguno baja de 1.5; por debajo "
                "de ahi la rejilla no esta apoyada en la musica.\n\n"
                "La ventana para tipear pasa a durar %.2f s.\n\n"
                "Si te convence: elegi el arranque y APRETA GENERAR EL CHART. "
                "Hasta que no generes, la fila sigue como estaba."
                % (rej["bpm"], viejo, rej.get("nitidez") or 0,
                   4 * 60.0 / rej["bpm"]))
        self._en_hilo("Midiendo el tempo de %s..." % f["Filename"], trabajo, despues)

    def _rejilla_lista(self, rej):
        self.rej = rej
        self._medido = self.cargada
        f = self.fila_actual()
        if f is None:
            return
        self._pintar_revision()
        self._pintar_arreglar()
        self._pintar_ficha()

    def _pintar_revision(self):
        self.revbox.configure(state="normal")
        self.revbox.delete("1.0", "end")
        for fila in self.pareja:
            pts = N.revisar(fila, self.rej)
            self.estados[fila["ID"]] = N.nota(pts)
            self.revbox.insert("end", "%s  -  %s estrellas (%s)\n"
                               % (fila["ID"], fila["Difficulty"],
                                  N.nivel_de(int(float(fila["Difficulty"] or 0)))),
                               "det")
            for p in pts:
                self.revbox.insert("end", ICONO[p["estado"]] + p["titulo"] + "\n",
                                   p["estado"])
                self.revbox.insert("end", p["detalle"] + "\n", "det")
            self.revbox.insert("end", "\n")
        self.revbox.configure(state="disabled")
        self.pintar_lista()

    def _pintar_arreglar(self):
        # Repintar al generar no debe perder la velocidad que se eligió para
        # otra versión. Una canción o una cuadrícula nueva se leen del chart.
        clave = (tuple(str(f["Filename"]) for f in self.pareja),
                 float(self.rej["bpm"]) if self.rej else None)
        anteriores = {}
        if getattr(self, "_panel_bpm_clave", None) == clave:
            for id_, (v, _lb, vel) in getattr(self, "spins", {}).items():
                try:
                    anteriores[str(id_)] = (v.get(), vel.get())
                except (tk.TclError, ValueError):
                    pass
        self._panel_bpm_clave = clave
        for w in self.filas_est.winfo_children():
            w.destroy()
        self.spins = {}
        # QUE VERSIONES REHACE GENERAR (2/10/2026, pedido de Joel: cambiar la de 3
        # estrellas a 6 sin perder la de 10 ya generada). Tildadas todas por
        # defecto; la que se destilda queda como esta guardada.
        antes = dict((k, v.get()) for k, v in self.gen_fila.items())
        self.gen_fila = {}
        for fila in self.pareja:
            fila_panel = ttk.Frame(self.filas_est)
            fila_panel.pack(fill="x", pady=(2, 5))
            f = ttk.Frame(fila_panel)
            f.pack(fill="x")
            g = tk.BooleanVar(value=antes.get(fila["ID"], True))
            ttk.Checkbutton(f, text="generar", variable=g).pack(side="left")
            self.gen_fila[fila["ID"]] = g
            ttk.Label(f, text="Fila %s:" % fila["ID"]).pack(side="left", padx=(3, 0))
            anterior = anteriores.get(str(fila["ID"]))
            v = tk.IntVar(value=(anterior[0] if anterior else
                                 int(float(fila["Difficulty"] or 3))))
            ttk.Spinbox(f, from_=1, to=10, textvariable=v, width=5,
                        command=self._texto_estrellas).pack(side="left")
            # x1..x4 cambian el BPM del chart, sin acelerar el audio. Un BPM
            # guardado distinto queda disponible para conservarlo sin cambios.
            velocidad = anterior[1] if anterior else self._velocidad_de(fila)
            vel = tk.StringVar(value=velocidad)
            opciones = ("x1", "x2", "x3", "x4")
            if velocidad not in opciones:
                opciones += (velocidad,)
            cb = ttk.Combobox(f, textvariable=vel, width=15, state="readonly",
                              values=opciones)
            cb.pack(side="left", padx=(8, 0))
            cb.bind("<<ComboboxSelected>>", lambda _e: self._texto_estrellas())
            # El panel derecho mide unos 390 px en la ventana mínima. El BPM
            # efectivo y la recomendación necesitan su propia línea, con ajuste
            # al ancho disponible, para que sigan visibles junto a cada fila.
            lb = ttk.Label(fila_panel, text="", wraplength=340, justify="left")
            lb.pack(fill="x", anchor="w", padx=(4, 0), pady=(3, 0))
            self.spins[fila["ID"]] = (v, lb, vel)
        self.lbl_est.config(wraplength=340)

        def ajustar_consejos(e):
            ancho = max(120, e.width - 16)
            self.lbl_est.config(wraplength=ancho)
            for _v, etiqueta, _vel in self.spins.values():
                etiqueta.config(wraplength=ancho)
        self.filas_est.bind("<Configure>", ajustar_consejos)
        self._texto_estrellas()

        if self.rej:
            cfg = self.config_secciones(self.pareja[0])
            ancla = cfg["inicio"]
            self.v_ini.set("%.4f" % (ancla if ancla is not None else
                                   float(self.pareja[0]["StartDelayTime"])))
            self._texto_inicio()
            self._llenar_candidatos()

    def _velocidad_de(self, fila):
        """Reconoce x1..x4 o muestra el BPM real que ya tiene esta fila."""
        try:
            b = float(fila["BPM"])
            base = float(self.rej["bpm"]) if self.rej else 0.0
        except (TypeError, ValueError):
            return "x1"
        if not math.isfinite(b) or b <= 0:
            return "x1"
        if math.isfinite(base) and base > 0:
            for factor in range(1, 5):
                # GENERAR guarda el BPM con dos decimales.
                if math.isclose(b, round(base * factor, 2),
                                rel_tol=1e-9, abs_tol=1e-7):
                    return "x%d" % factor
        return "%g BPM (actual)" % b

    def bpm_de_fila(self, id_):
        """BPM efectivo de ESA fila; conserva BPM ajenos a x1..x4."""
        base = float(self.rej["bpm"])
        v = self.spins.get(str(id_))
        modo = v[2].get() if v else None
        if modo in ("x1", "x2", "x3", "x4"):
            return base * int(modo[1:])
        fila = next((f for f in self.pareja if str(f["ID"]) == str(id_)), None)
        if fila:
            try:
                actual = float(fila["BPM"])
                if math.isfinite(actual) and actual > 0:
                    return actual
            except (TypeError, ValueError):
                pass
        return base

    def _cambio_musica(self):
        self._texto_estrellas()
        self._texto_musica()

    def _cambio_menos_space(self):
        if self.pareja and not N.es_original(self.pareja[0]):
            N.anotar_menos_space(self.pareja[0]["Filename"], bool(self.v_menos_sp.get()))
        elif self.v_menos_sp.get():
            self.v_menos_sp.set(False)
        self._cambio_musica()

    def mudos_de(self, fila):
        """Los tramos quitados que le corresponden a ESA fila."""
        if not self.ultimos_mudos:
            return ()
        if self.mudos_solo_fila and fila["ID"] != self.mudos_solo_fila:
            return ()
        return self.ultimos_mudos

    def config_secciones(self, fila):
        """Preferencias por fila; nunca se añaden columnas al musictable."""
        clave = "%s:%s" % (fila["Filename"], fila["ID"])
        if clave not in self.ediciones_secciones:
            self.ediciones_secciones[clave] = S.cargar_configuracion(N.ESTUDIO, clave)
        return self.ediciones_secciones[clave]

    def guardar_secciones(self, fila, secciones, inicio, misiones=None):
        clave = "%s:%s" % (fila["Filename"], fila["ID"])
        S.guardar_configuracion(N.ESTUDIO, clave, secciones, inicio=inicio, misiones=misiones)
        self.ediciones_secciones[clave] = S.cargar_configuracion(N.ESTUDIO, clave)

    def extras(self, fila=None):
        """Lo que se marco en el mapa con 'Solo SPACE' e 'Invertir'. Se pasa a
        TODO lo que genera (escuchar, simular, mapa y los dos GENERAR)."""
        fila = fila or self.pareja[0]
        return dict(secciones=copy.deepcopy(self.config_secciones(fila)["secciones"]),
                    misiones=copy.deepcopy(self.config_secciones(fila).get("misiones", [])),
                    solo_space=tuple(self.ultimos_spaces),
                    invertir=tuple(self.ultimos_inv),
                    suave=tuple(self.ultimos_suave),
                    ritmos=tuple(self.ultimos_ritmos),
                    space_estilo="2020" if self._estilo2020 else "clasico",
                    por_partes=self._partes)

    def frases_de(self):
        """Que misiones alargar: None (todas de 16), "auto" o los segundos
        marcados a mano en el mapa. Se lee en el hilo de la ventana."""
        if not self.v_frases.get():
            return None
        return self.ultimas_frases if self.ultimas_frases is not None else "auto"

    def modo_space(self):
        return {"como Softnyx": "softnyx", "solo en las subidas": "subidas",
                "solo en los golpes fuertes": "justos"}.get(
                    self.v_space.get(), "softnyx")

    def _texto_musica(self):
        """Explica la casilla y de donde sale el SPACE de verdad."""
        if not hasattr(self, "lbl_musica"):
            return
        por_partes = getattr(self, "v_partes", None) is not None and self.v_partes.get()
        partes = [] if por_partes else [
            "Flechas: " + ("sobre los golpes; donde la canción se calla no hay."
                           if self.v_musica.get() else "sorteadas como Softnyx.")]
        if getattr(self, "v_frases", None) is not None and self.v_frases.get():
            if self.ultimas_frases is not None:
                partes.append("Frases: las que marcaste en el mapa (%d)."
                              % len(self.ultimas_frases))
            else:
                partes.append("Frases: las elige la música (miralas en el MAPA).")
        else:
            partes.append("Frases: todas las misiones de 16.")
        if por_partes:
            partes.insert(0, "Flechas POR PARTES: en lo fuerte siguen el golpe, en lo "
                          "suave 1 flecha 1 SPACE con la voz, flechas seguidas antes "
                          "de cada explosión.")
        if getattr(self, "v_estilo", None) is not None and self.v_estilo.get():
            partes.append("SPACE: como LoveRitmo 2020 (menos en las difíciles, y "
                          "donde la música pega fuerte).")
        else:
            partes.append("SPACE: como antes (promedio de los 4 juegos).")
        self.lbl_musica.config(
            text="  ·  ".join(partes) + "\nEl SPACE lo pone el juego en cada tiempo "
                 "sin flechas: para menos SPACE, más flechas o más estrellas.")

    def _texto_estrellas(self):
        if not self.rej:
            return
        for _id, (v, lb, vel) in self.spins.items():
            e = max(1, min(10, int(v.get())))
            bpm = self.bpm_de_fila(_id)
            lo, hi = N.rango_estrellas(bpm)
            fuera = "" if lo <= e <= hi else "   FUERA (Softnyx usa %d a %d)" % (lo, hi)
            lb.config(text="%.2f BPM  -  %s  -  %.1f flechas/mision  -  CutOff %d%s"
                          % (bpm, N.nivel_de(e), N.FLECHAS_POR_MISION[e],
                             N.cutoff_de(e), fuera))
        base = self.rej["bpm"]
        lo, hi = N.rango_estrellas(base)
        self.lbl_est.config(
            text="A %.0f BPM Softnyx usa de %d a %d estrellas (inicial 1-3 · básico "
                 "4-6 · profesional 7-10). Podés elegir x1, x2, x3 o x4 por fila: "
                 "cambia el chart, el audio no se acelera. Softnyx usa x2 en el "
                 "%d%% de las canciones a esta velocidad."
                 % (base, lo, hi, N.chance_x2(base)))

    def _texto_inicio(self):
        if not self.rej:
            return
        try:
            t = float(self.v_ini.get())
        except ValueError:
            return
        dur = self.rej.get("dur") or 1
        dc = abs(t - N.pegar_a_compas(self.rej, t)) * 1000
        dt = abs(t - N.pegar_a_tiempo(self.rej, t)) * 1000
        if dc < 40:
            q = "cae en un '1' de compás (a %.0f ms)." % dc
        elif dt < 40:
            q = "cae en un tiempo, pero NO en el '1' del compás (a %.0f ms)." % dc
        else:
            q = "NO cae en la cuadrícula (a %.0f ms del tiempo más cercano)." % dt
        k, margen, _pts = N.fase_de_frase(self.rej)
        cae = int(round((t - self.rej["fase"]) / self.rej["compas"])) % 4
        pista = ("\nEl sonido cambia en el compás %d y vos estás en el %d."
                 % (k + 1, cae + 1)) if margen >= 60 else ""
        self.lbl_ini.config(
            text="%.1f%% de la canción (Softnyx: %.1f a %.1f%%)  ·  %s  ·  "
                 "cuadrícula %s, %.2f BPM%s"
                 % (100 * t / dur, N.PCT_MIN, N.PCT_MAX, q,
                    "de Virtual DJ" if "Virtual" in self.rej["origen"] else "propia",
                    self.rej["bpm"], pista))

    def _llenar_candidatos(self):
        self.cands.delete(*self.cands.get_children())
        dur = self.rej.get("dur") or 0
        for c in N.arranques_opciones(self.rej, cuantos=8):
            self.cands.insert("", "end", values=(
                "%.4f" % c["t"], "%.1f %%" % c["pct"], "%.0f %%" % c["prob"],
                c["motivo"]))

    # ------------------------------------------------------------ acciones
    def correr(self, n):
        if not self.rej:
            return
        try:
            t = float(self.v_ini.get())
        except ValueError:
            return
        self.v_ini.set("%.4f" % (t + n * self.rej["compas"]))
        self._texto_inicio()

    def pegar(self):
        if not self.rej:
            return
        try:
            t = float(self.v_ini.get())
        except ValueError:
            return
        self.v_ini.set("%.4f" % N.pegar_a_compas(self.rej, t))
        self._texto_inicio()

    def auto_inicio(self):
        if not self.rej:
            return
        try:
            actual = float(self.v_ini.get())
        except ValueError:
            actual = None
        # SIN `cerca`: si se aprieta el boton es porque se quiere la recomendacion
        # nueva. No pisa nada: el arranque recien vale al GENERAR y ENVIAR.
        t, motivo = N.inicio_recomendado(self.rej)
        if actual is not None and abs(t - actual) > 0.05:
            motivo += "  (antes tenía %.4f: si te gustaba, volvé a escribirlo)" % actual
        if t is None:
            messagebox.showwarning("Arranque", motivo)
            return
        self.v_ini.set("%.4f" % t)
        self._texto_inicio()
        self.lbl_ini.config(text=self.lbl_ini.cget("text") + "\nElegido solo: " + motivo)

    def tomar_candidato(self, _e=None):
        s = self.cands.selection()
        if s:
            self.v_ini.set(self.cands.item(s[0])["values"][0])
            self._texto_inicio()

    # ------------------------------------------------------------ escuchar
    def parar(self):
        N.parar_sonido()

    def escuchar(self, inicio=None, estrellas=None, nota=""):
        """Suena la cancion con un tic donde va a caer cada flecha.

        En una cancion NUESTRA se oye lo que va a poner GENERAR con el arranque
        y las estrellas que hay puestos ahora (no hace falta generar antes).
        En una ORIGINAL del juego se oye su chart tal cual, que es el patron
        contra el que conviene comparar.
        """
        if not self.rej or not self.pareja:
            return
        if self.trabajando:
            return
        fila = self.fila_actual() or self.pareja[0]
        seg = max(5, min(90, int(self.v_seg.get() or 20)))
        musica = not self.v_solotic.get()
        marcar = bool(self.v_marcar.get())
        original = N.es_original(fila)
        ini = est = bpm = None
        if not original:
            try:
                ini = float(self.v_ini.get()) if inicio is None else float(inicio)
            except ValueError:
                messagebox.showwarning("Arranque", "El arranque no es un numero.")
                return
            est = (int(estrellas) if estrellas is not None
                   else max(1, min(10, int(self.spins[fila["ID"]][0].get()))))
            # OJO: hay que leerlo ACA. Las variables de tkinter solo se pueden
            # tocar desde el hilo de la ventana; adentro de `trabajo` revienta
            # con "main thread is not in main loop".
            bpm = self.bpm_de_fila(fila["ID"])
        pormus = bool(self.v_musica.get())
        modosp = self.modo_space()
        mudos = self.mudos_de(fila)
        sinsp = bool(self.v_sinsp.get())
        frases = self.frases_de()
        descanso = bool(self.v_descanso.get())
        self.parar()

        def trabajo():
            if original:
                return N.previo_de_fila(fila, self.rej, segundos=seg,
                                        musica=musica, marcar_misiones=marcar)
            return N.previo(fila, self.rej, est, ini, segundos=seg, bpm=bpm,
                            musica=musica, marcar_misiones=marcar,
                            por_musica=pormus, space=modosp, mudos=mudos,
                            mudo_sin_space=sinsp, frases=frases,
                            descanso=descanso,
                **self.extras(fila))

        def despues(r):
            ruta, inf = r
            N.reproducir(ruta)
            self.lbl_oir.config(
                text="Sonando desde el segundo %.2f, %d segundos.  %d flechas y "
                     "%d SPACE en ese tramo.  %s%s\n"
                     "Tic agudo = flecha.  Tic grave = SPACE.  Golpe seco = "
                     "empieza una mision."
                     % (inf["desde"], inf["segundos"], inf["flechas"], inf["space"],
                        ("las flechas que YA TIENE (cancion del juego)" if original
                         else "arranque %.4f, %d estrellas, %g BPM%s"
                         % (ini, est, round(bpm, 2),
                            " (x%g de la cuadrícula)" % (bpm / self.rej["bpm"]))),
                        ("  -  " + nota) if nota else ""))
        self._en_hilo("Preparando la escucha...", trabajo, despues)

    def ventana_entera(self):
        """La cancion completa, con el mapa de donde cae cada mision."""
        if not self.rej or not self.pareja or self.trabajando:
            return
        fila = self.fila_actual() or self.pareja[0]
        original = N.es_original(fila)
        if original:
            ini = float(fila["StartDelayTime"] or 0)
            bpm = float(fila["BPM"] or self.rej["bpm"])
            est = int(float(fila["Difficulty"] or 3))
            pormus = False
        else:
            try:
                ini = float(self.v_ini.get())
            except ValueError:
                messagebox.showwarning("Arranque", "El arranque no es un numero.")
                return
            est = max(1, min(10, int(self.spins[fila["ID"]][0].get())))
            bpm = self.bpm_de_fila(fila["ID"])
            pormus = bool(self.v_musica.get())
        # las variables de tkinter se leen ACA, no adentro del hilo
        modosp = self.modo_space()
        frases = self.frases_de()
        mudos = self.mudos_de(fila)
        descanso = bool(self.v_descanso.get())
        repes = self.ultimas_repes
        # EL MAPA MUESTRA LO QUE ESTA EN EL JUEGO (24/9/2026). Si la fila no se
        # toco en esta sesion y el panel tiene su mismo arranque, estrellas y BPM,
        # se dibuja el chart GUARDADO. Antes se regeneraba, y en 6 de 23 filas el
        # sorteo no sale identico: Joel vio en la Russian Roulette original un
        # descanso de 64 que en el juego es de 52, y SPACE que no tiene.
        #
        # CORREGIDO el mismo dia: tambien si la fila SI se toco (GENERAR, Arreglar
        # el baile). Lo que hay en memoria es lo ultimo que el usuario hizo, y es
        # lo que va a mandar ENVIAR: eso es lo que hay que mostrar. Antes, despues
        # de "Arreglar el baile" en la copia de Feather, el mapa mostraba una
        # regeneracion con los ajustes por defecto ("0 frases", sin cortes) y
        # parecia que se habia perdido todo; un GENERAR ahi SI lo perdia.
        guardado = (not original
                    and not self.config_secciones(fila)["secciones"]
                    and self.config_secciones(fila)["inicio"] is None
                    and abs(ini - float(fila["StartDelayTime"] or 0)) < 0.0005
                    and est == int(float(fila["Difficulty"] or 0))
                    and abs(bpm - float(fila["BPM"] or 0)) < 0.01)

        def trabajo():
            if original or guardado:
                return dict(fila), bpm, ini, est, (False if original else pormus)
            nuevos, _inf = N.generar(fila, self.rej, est, ini, bpm=bpm,
                                     por_musica=pormus, space=modosp,
                                     frases=frases, mudos=mudos,
                                     descanso=descanso, repetir=repes,
                **self.extras(fila))
            return nuevos, bpm, ini, est, pormus

        def despues(r):
            v = VentanaEntera(self, fila, *r)
            v.guardado = guardado
            if v.historia:
                v.historia[0]["guardado"] = guardado    # la foto inicial lo sabe
            v._texto_cabecera()
        self._en_hilo("Armando el mapa de la cancion...", trabajo, despues)

    def arreglar_estrellas(self):
        """Pone en cada fila las estrellas que usa Softnyx a ese BPM. Un clic.

        No calcula nada: sale de la mediana de los 1038 charts. Y respeta el x2:
        una fila puesta a x2 admite (y pide) muchas mas estrellas que la misma
        cancion a velocidad normal.

        NO toca el CutOff ni el arranque: el CutOff recien cambia al GENERAR, y
        la regla del proyecto es que a una cancion que ya gusta no se le mueve.
        """
        if not self.rej or not self.pareja:
            return
        ids = [f["ID"] for f in self.pareja]
        bpms = [self.bpm_de_fila(i) for i in ids]
        antes = [int(self.spins[i][0].get()) for i in ids]
        # de mas facil a mas dificil, respetando el orden que ya tenian
        orden = sorted(range(len(ids)), key=lambda k: (antes[k], bpms[k]))
        sug = N.estrellas_sugeridas([bpms[k] for k in orden])
        for k, e in zip(orden, sug):
            self.spins[ids[k]][0].set(e)
        self._texto_estrellas()

        cambios = ["fila %s: %d -> %d" % (ids[k], antes[k], self.spins[ids[k]][0].get())
                   for k in range(len(ids))
                   if antes[k] != int(self.spins[ids[k]][0].get())]
        base = self.rej["bpm"]
        txt = ("Puestas las que usa Softnyx a este BPM.  " +
               (", ".join(cambios) if cambios else "no hizo falta cambiar nada") +
               "\nTodavia no se generaron: para que valga hay que apretar "
               "GENERAR EL CHART.")
        if any(self.spins[i][2].get() == "x1" for i in ids) and N.chance_x2(base) >= 30:
            txt += ("\nA %.0f BPM Softnyx hace la dificil al DOBLE en el %d%% de "
                    "los casos. Mira 'Que BPM poner?'." % (base, N.chance_x2(base)))
        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("end", txt)
        self.result.configure(state="disabled")

    def ventana_bpm(self):
        if not self.rej or not self.pareja:
            return
        fila = self.fila_actual() or self.pareja[0]

        def trabajo():
            return N.consejo_bpm(self.rej, bpm_tabla=fila.get("BPM"))

        def despues(d):
            VentanaBPM(self, d)
        self._en_hilo("Midiendo el BPM del audio...", trabajo, despues)

    def poner_velocidades(self, modo, solo_dificil=False):
        """Aplica x1..x4 a la difícil; normal permite volver todas a x1."""
        if not self.pareja or modo not in ("x1", "x2", "x3", "x4"):
            return
        ids = [f["ID"] for f in self.pareja]
        if modo == "x1" and not solo_dificil:
            for i in ids:
                self.spins[i][2].set("x1")
        else:
            dificil = max(ids, key=lambda i: int(self.spins[i][0].get()))
            self.spins[dificil][2].set(modo)
        self._texto_estrellas()

    def probar_aqui(self):
        """PROBAR al instante (7/10/2026): la fila elegida se juega en una ventana del
        Estudio, con el teclado, sin servidor ni sala (jugar.py). Si la fila es tuya y
        tiene cambios sin ENVIAR, se juega lo que se va a generar, igual que Simular."""
        if self.trabajando:
            return
        if not self.pareja:
            messagebox.showinfo("Probar", "Elegí primero una canción de la lista.")
            return
        if not self.rej:
            messagebox.showinfo("Probar", "Todavía estoy midiendo la canción (o falta su "
                                          "audio). Esperá un segundo y probá de nuevo.")
            return
        self.ventana_simular(jugar=True)

    def ventana_simular(self, jugar=False):
        """Abre la simulacion: las flechas del juego, con sus sonidos."""
        if not self.rej or not self.pareja or self.trabajando:
            return
        fila = self.fila_actual() or self.pareja[0]
        original = N.es_original(fila)
        if original:
            ini = float(fila["StartDelayTime"] or 0)
            bpm = float(fila["BPM"] or self.rej["bpm"])
            est = int(float(fila["Difficulty"] or 3))
            pormus = False
        else:
            try:
                ini = float(self.v_ini.get())
            except ValueError:
                messagebox.showwarning("Arranque", "El arranque no es un numero.")
                return
            est = max(1, min(10, int(self.spins[fila["ID"]][0].get())))
            bpm = self.bpm_de_fila(fila["ID"])
            pormus = bool(self.v_musica.get())
        modosp = self.modo_space()
        mudos = self.mudos_de(fila)
        sinsp = bool(self.v_sinsp.get())
        frases = self.frases_de()
        descanso = bool(self.v_descanso.get())

        def trabajo():
            hechos, faltan = N.extraer_del_juego()
            if original:
                listas = dict(fila)
            else:
                listas, _inf = N.generar(fila, self.rej, est, ini, bpm=bpm,
                                         por_musica=pormus, space=modosp,
                                         mudos=mudos, mudo_sin_space=sinsp,
                                         frases=frases, descanso=descanso,
                **self.extras(fila))
            return listas, bpm, ini, est, pormus, faltan

        def despues(r):
            listas, bpm2, ini2, est2, pm2, faltan = r
            if faltan:
                messagebox.showwarning(
                    "Simular",
                    "No pude sacar del juego: %s\n\nLa simulación va a "
                    "andar igual, pero con dibujos propios." % ", ".join(faltan[:5]))
            if jugar:
                import jugar as J
                J.VentanaJugar(self, fila, listas, bpm2, ini2, est2)
            else:
                VentanaSimular(self, fila, listas, bpm2, ini2, est2, pm2)
        self._en_hilo("Preparando..." if jugar else "Preparando la simulación...",
                      trabajo, despues)

    def copiar(self):
        """Duplica la cancion elegida, para poder probar sin arriesgarla.

        La copia se lleva su propio archivo de audio: si compartiera el
        `Filename` con la original, las dos serian LA MISMA cancion para el
        programa y generar sobre una tocaria la otra.
        """
        if not self.tabla or not self.pareja or self.trabajando:
            return
        origen = self.pareja[0]["Title"]
        if not messagebox.askyesno(
                "Crear una copia",
                "Voy a duplicar %r en filas nuevas, con su propio audio.\n\n"
                "La original no se toca: podés probar todo lo que quieras sobre la "
                "copia.\n\nSigo?" % origen):
            return
        filas = list(self.pareja)

        def trabajo():
            return N.copiar_cancion(self.tabla, filas, aviso=None)

        def despues(r):
            ids, msg = r
            if ids:
                self.sucias.update(ids)
                self.b_enviar.config(state="normal")
                self.cargada = None
                self.pintar_lista()
                # dejar elegida la copia
                for i in self.lista.get_children():
                    if str(self.lista.item(i)["values"][1]) == str(ids[0]):
                        self.lista.selection_set(i)
                        self.lista.see(i)
                        break
            messagebox.showinfo("Crear una copia", msg)
        self._en_hilo("Copiando la cancion...", trabajo, despues)

    _IGUAL = object()

    def generar(self, inicio=None, mudos=None, solo_fila=_IGUAL, repetir=None):
        """Rehace el chart de todas las filas de la cancion.

        `inicio` y `mudos` los manda la ventana del mapa cuando se genera desde
        alli. DESDE EL PANEL (sin argumentos) se usa LO ULTIMO QUE SE MARCO EN
        EL MAPA: descansos, a que filas van y repeticiones.

        CORREGIDO el 23/9/2026. Antes el GENERAR del panel generaba con
        `mudos=()` y `repetir=()`, o sea que BORRABA todo lo marcado en el mapa.
        Joel armo la copia de Don't Stop The Music con un descanso, apreto
        GENERAR en el panel y lo envio: el descanso desaparecio (se ve en los
        respaldos de las 18:23 y las 18:29).

        `solo_fila` es el ID de la unica fila a la que se le aplican los tramos
        quitados. Con None se le aplican a TODAS las de la cancion. Lo decide la
        casilla "aplicar a las dos versiones" del mapa: sacar un pedazo en la
        dificil no siempre se quiere tambien en la facil.

        `repetir` son los tramos donde se pidieron REPETICIONES con Ctrl+clic en
        el mapa. Esos van SIEMPRE a las dos versiones: no tiene sentido que un
        tramo repita en la dificil y no en la facil.
        """
        if not self.rej or not self.pareja:
            return
        if any(N.es_original(f) for f in self.pareja):
            messagebox.showwarning(
                "Cancion original",
                "Esta cancion esta protegida (no la creo el Estudio).\n\nSi la hiciste vos, clic derecho en la lista > Permitir editarla.")
            return
        # las versiones tildadas en el paso 2 ("generar"); las otras no se tocan
        elegidas = [f for f in self.pareja
                    if self.gen_fila.get(f["ID"]) is None
                    or self.gen_fila[f["ID"]].get()]
        if not elegidas:
            messagebox.showwarning(
                "Generar", "No hay ninguna versión tildada para generar (paso 2, "
                           "casilla 'generar').")
            return
        if inicio is None:
            try:
                ini = float(self.v_ini.get())
            except ValueError:
                messagebox.showwarning("Arranque", "El arranque no es un numero.")
                return
        else:
            ini = float(inicio)
            self.v_ini.set("%.4f" % ini)
            self._texto_inicio()
        if mudos is None:
            mudos = self.ultimos_mudos
        if solo_fila is Estudio._IGUAL:
            solo_fila = self.mudos_solo_fila
        if repetir is None:
            repetir = self.ultimas_repes
        # que ESCUCHAR y SIMULAR muestren lo mismo que acaba de quedar
        self.ultimos_mudos = tuple(mudos or ())
        self.mudos_solo_fila = solo_fila
        self.ultimas_repes = tuple(repetir or ())
        dc = abs(ini - N.pegar_a_compas(self.rej, ini)) * 1000
        if dc > 40 and not messagebox.askyesno(
                "El arranque no cae en el compas",
                "Ese arranque esta a %.0f ms del '1' de compas mas cercano.\n"
                "Las flechas van a entrar corridas.\n\nGenero igual?" % dc):
            return

        frases = self.frases_de()
        lineas = ["Fila %s: no se tocó (destildada en el paso 2)\n" % f["ID"]
                  for f in self.pareja if f not in elegidas]
        pendientes = []
        try:
            for fila in elegidas:
                est = max(1, min(10, int(self.spins[fila["ID"]][0].get())))
                bpm = self.bpm_de_fila(fila["ID"])
                suyos = mudos if (solo_fila is None or fila["ID"] == solo_fila) else ()
                nuevos, inf = N.generar(fila, self.rej, est, ini, bpm=bpm,
                                        por_musica=bool(self.v_musica.get()),
                                        mudos=suyos, space=self.modo_space(),
                                        mudo_sin_space=bool(self.v_sinsp.get()),
                                        repetir=repetir, frases=frases,
                                        descanso=bool(self.v_descanso.get()),
                                        **self.extras(fila))
                pendientes.append((fila, est, bpm, nuevos, inf))
            for fila, _est, _bpm, _nuevos, _inf in pendientes:
                cfg = self.config_secciones(fila)
                if cfg["secciones"]:
                    self.guardar_secciones(fila, cfg["secciones"], ini)
        except (ValueError, OSError) as error:
            messagebox.showerror("No se pudo generar", str(error), parent=self)
            return
        # Se valida toda la selección antes de cambiar cualquiera de sus filas.
        N.anotar_estilo(self.pareja[0]["Filename"],
                        "2020" if self.v_estilo.get() else "clasico")
        N.anotar_partes(self.pareja[0]["Filename"], bool(self.v_partes.get()))
        for fila, est, bpm, nuevos, inf in pendientes:
            fila.update(nuevos)
            self.modificadas.add(fila["ID"])
            self.sucias.add(fila["ID"])
            lineas.append(
                "Fila %s  -  %d estrellas (%s)\n"
                "   %d misiones, %s, cobertura %.0f%%\n"
                "   flechas : %.1f por mision   (Softnyx en %d estrellas: %.1f)\n"
                "   por tiempo: %s\n"
                "   2a tanda: %d de %d misiones (Softnyx: 74%%), %.1f flechas cada una\n"
                "   SPACE   : %.1f por mision, %d misiones sin ninguno%s\n"
                "   arranca en %.4f s y el chart llega a %.1f s "
                "(el ritmo termina en %.1f s)\n"
                "   BPM %g%s\n"
                "   misiones sin flechas: %d%s   |   %s\n"
                % (fila["ID"], est, N.nivel_de(est), inf["misiones"],
                   ("%d misiones largas (frases y descansos)" % inf["largas"])
                   if inf.get("largas") else "todas de 16 tiempos",
                   100 * inf["cobertura"], inf["flechas"], est,
                   N.FLECHAS_POR_MISION[est],
                   "  ".join("%d->%.0f%%" % (k, inf["reparto"][k]) for k in range(4)),
                   inf.get("tandas2", 0), inf["misiones"], inf.get("flechas2", 0.0),
                   inf["space"], inf["sin_space"],
                   ("  (menos SPACE: %d tandas con flechas de mas)" % inf["menos_space"])
                   if inf.get("menos_space") else "",
                   float(nuevos["StartDelayTime"]), inf["fin_chart"], inf["fin_musica"], round(bpm, 2),
                   "  (x%g de la cuadrícula)" % (bpm / self.rej["bpm"]),
                   inf.get("sin_flechas", 0),
                   ("  (%d las quitaste a mano)" % inf["mudos_a_mano"])
                   if inf.get("mudos_a_mano") else
                   ("  (%d en descanso: no sale nada)" % inf["descansos"])
                   if inf.get("descansos") else "",
                   "el SPACE lo pone el juego en los tiempos sin flechas"))

        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("end", "\n".join(lineas))
        self.result.insert("end", "\nListo en memoria. Todavia NO esta en el juego: "
                                  "para eso el boton ENVIAR AL JUEGO.")
        self.result.configure(state="disabled")
        self.b_enviar.config(state="normal")
        self._pintar_revision()
        self._pintar_arreglar()

    def revisar_todas(self):
        if not self.tabla:
            return

        def trabajo():
            hechas = []
            vistos = {}
            for f in self.tabla.filas:
                if N.es_original(f):
                    continue
                try:
                    if f["Filename"] not in vistos:
                        vistos[f["Filename"]] = N.rejilla_de(f)
                    hechas.append((f["ID"], N.nota(N.revisar(f, vistos[f["Filename"]]))))
                except Exception:
                    hechas.append((f["ID"], N.MAL))
            return hechas

        def despues(hechas):
            for id_, e in hechas:
                self.estados[id_] = e
            malas = sum(1 for _i, e in hechas if e == N.MAL)
            avisos = sum(1 for _i, e in hechas if e == N.AVISO)
            self.pintar_lista()
            messagebox.showinfo("Revision",
                                "%d filas revisadas.\n\n%d con algo mal\n%d con avisos\n"
                                "%d bien" % (len(hechas), malas, avisos,
                                             len(hechas) - malas - avisos))
        self._en_hilo("Revisando todas (la primera vez tarda)...", trabajo, despues)

    # ------------------------------------------------------ audios perdidos
    def recuperar(self, callado=False):
        """Rehace los .ogg que falten, sacandolos de los .snb del juego.

        El .ogg solo hace falta para MEDIR: el juego suena con el .snb. Por eso
        se puede vaciar la carpeta de audios sin que se note, hasta que el
        Estudio quiere analizar algo. Como el .snb es el .ogg cifrado con una
        clave nuestra, se rehace identico.
        """
        if not self.tabla:
            return
        puedo, no_puedo = N.audios_perdidos(self.tabla)
        if not puedo:
            if not callado:
                messagebox.showinfo(
                    "Recuperar audios",
                    "No falta ningun audio." if not no_puedo else
                    "Los %d que faltan no se pueden rehacer: no estan en "
                    "snb_local.json o no tienen .snb en el juego." % len(no_puedo))
            return
        if not messagebox.askyesno(
                "Recuperar audios",
                "Faltan %d audios en:\n%s\n\nLos puedo rehacer desde los .snb del "
                "juego: salen identicos al original.\n%s\nLos hago?"
                % (len(puedo), N.OGG_NUEVOS,
                   "" if not no_puedo else
                   "\n(%d no se pueden rehacer)\n" % len(no_puedo))):
            return

        def trabajo():
            return N.recuperar_audios([n for n, _t in puedo])

        def despues(r):
            hechos, fallados = r
            messagebox.showinfo("Recuperar audios",
                                "Recuperados: %d\nFallaron: %d" % (len(hechos),
                                                                   len(fallados)))
            self.estados.clear()
            self.pintar_lista()
        self._en_hilo("Rehaciendo %d audios..." % len(puedo), trabajo, despues)

    # ---------------------------------------------------------- Virtual DJ
    def panel_vdj(self):
        if not self.tabla:
            return

        def trabajo():
            return N.falta_en_vdj(self.tabla)

        def despues(r):
            faltan, tienen = r
            VentanaVDJ(self, faltan, tienen)
        self._en_hilo("Viendo que tiene Virtual DJ...", trabajo, despues)

    # ------------------------------------------------------------ agregar
    def agregar(self):
        """Trae una cancion nueva. Cualquier formato: lo convierte el Estudio.

        Desde el 21/9/2026 no hace falta que sea .ogg. Si es .mp3, .flac, .wav,
        .m4a... lo convierte ffmpeg en el mismo paso (N.convertir_a_ogg), y el
        titulo y el cantante vienen de las etiquetas del archivo cuando las
        tiene, asi no hay que escribirlos a mano.
        """
        ruta = filedialog.askopenfilename(
            title="Elegí la canción (ogg, mp3, flac, wav...)",
            filetypes=[("Canciones", " ".join("*" + e for e in N.FORMATOS)),
                       ("Todos los archivos", "*.*")])
        if not ruta:
            return
        dat = N.datos_del_audio(ruta)
        d = Dialogo(self, dat["titulo"], N.filas_para_pisar(self.tabla),
                    cantante=dat["cantante"])
        self.wait_window(d)
        if not d.ok:
            return
        frases = "auto" if self.v_frases.get() else None

        def trabajo():
            return N.agregar_ogg(ruta, self.tabla, d.titulo, d.cantante,
                                 d.est_a, d.est_b, d.genero, auto=d.auto,
                                 por_musica=d.por_musica, destino=d.destino,
                                 niveles=d.niveles, frases=frases)

        def despues(r):
            ids, msg = r
            if ids:
                self.cargada = None
                self.sucias.update(ids)
                self.b_enviar.config(state="normal")
                self.pintar_lista()
            messagebox.showinfo("Agregar cancion", msg)
        self._en_hilo("Convirtiendo y midiendo (tarda un poco)...", trabajo, despues)

    # ------------------------------------------------------------- enviar
    def _menu_de_lista(self, e):
        """Clic derecho: elige la fila que esta bajo el mouse y abre el menu."""
        item = self.lista.identify_row(e.y)
        if not item:
            return
        self.lista.selection_set(item)
        self.lista.focus(item)
        try:
            self.menu_lista.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu_lista.grab_release()

    def cambiar_nombre(self):
        """Cambia el titulo y el cantante de la cancion elegida (sus dos filas)."""
        if self.trabajando:
            return
        f = self.fila_actual()
        if f is None:
            return
        if N.es_original(f):
            messagebox.showwarning("Cambiar nombre",
                                   "Esta canción vino con el juego: su nombre no "
                                   "se toca.")
            return
        d = DialogoNombre(self, f["Title"], f["Singer"])
        self.wait_window(d)
        if not d.ok:
            return
        try:
            ids, tit, can = N.renombrar(self.tabla, f["Filename"], d.titulo, d.cantante)
        except RuntimeError as e:
            messagebox.showwarning("Cambiar nombre", str(e))
            return
        self.sucias.update(ids)
        self.b_enviar.config(state="normal")
        self.cargada = None
        self.pintar_lista()
        self.cabecera.config(text=tit)
        aviso = ""
        if tit != d.titulo.strip() or can != d.cantante.strip():
            aviso = ("\n\nOJO: el juego solo guarda letras occidentales, así que "
                     "quedó:\n  %s  -  %s" % (tit, can))
        messagebox.showinfo("Cambiar nombre",
                            "Listo: %d filas con el nombre nuevo.%s\n\nPara que "
                            "llegue al juego falta ENVIAR AL JUEGO." % (len(ids), aviso))

    def eliminar_version(self):
        """Saca UNA dificultad y deja las otras de la misma cancion.

        El audio no se toca: las que quedan lo siguen usando. Por eso, a
        diferencia de `eliminar_cancion`, esto no pregunta por la papelera.
        """
        if self.trabajando or not self.tabla:
            return
        f = self.fila_actual()
        if f is None:
            return
        if N.es_original(f):
            messagebox.showwarning("Eliminar versión",
                                   "Esta canción vino con el juego: no se borra.")
            return
        hermanas = [x for x in self.tabla.filas if x["Filename"] == f["Filename"]]
        quedan = [x for x in hermanas if x["ID"] != f["ID"]]
        if not quedan:
            messagebox.showwarning(
                "Eliminar versión",
                "Es la única versión de \"%s\".\n\nPara sacarla usá "
                "\"Eliminar canción...\", que además pregunta qué hacer con el "
                "audio." % f["Title"])
            return
        if not messagebox.askyesno(
                "Eliminar versión",
                "Voy a sacar SOLO la fila %s (%s estrellas) de \"%s\".\n\n"
                "Quedan:\n%s\n\n"
                "El AUDIO no se toca: lo siguen usando las que quedan.\n\n"
                "Se va de la lista ahora, y del juego cuando aprietes "
                "ENVIAR AL JUEGO."
                % (f["ID"], f["Difficulty"], f["Title"],
                   "\n".join("  fila %s  -  %s estrellas" % (x["ID"], x["Difficulty"])
                             for x in quedan))):
            return
        try:
            fila, restantes = N.borrar_version(self.tabla, f["ID"])
        except RuntimeError as e:
            messagebox.showwarning("Eliminar versión", str(e))
            return
        self.sucias.add("borrada:%s" % fila["ID"])
        self.b_enviar.config(state="normal")
        self.pareja = []
        self.cargada = None
        self.rej = None
        self.pintar_lista()
        self.cabecera.config(text="")
        messagebox.showinfo(
            "Eliminar versión",
            "Listo: salió la fila %s (%s estrellas) de \"%s\". Quedan %d "
            "versión(es).\n\nPara que se vaya del juego falta ENVIAR AL JUEGO."
            % (fila["ID"], fila["Difficulty"], fila["Title"], restantes))

    def eliminar_cancion(self):
        """Saca la cancion (todas sus versiones) de la lista y, al ENVIAR, del juego.

        El audio NO se borra: si se pide, se mueve a la papelera DESPUES de
        enviar (antes dejaria la cancion en el juego sin audio).
        """
        if self.trabajando or not self.tabla:
            return
        f = self.fila_actual()
        if f is None:
            return
        if N.es_original(f):
            messagebox.showwarning("Eliminar canción",
                                   "Esta canción vino con el juego: no se borra.")
            return
        filas = [x for x in self.tabla.filas if x["Filename"] == f["Filename"]]
        resp = messagebox.askyesnocancel(
            "Eliminar canción",
            "Voy a sacar \"%s\" (%s), con sus %d versiones:\n\n%s\n\n"
            "Se va de la lista ahora, y del juego cuando aprietes ENVIAR AL JUEGO.\n\n"
            "¿También saco su AUDIO?\n"
            "  SÍ = filas y audio. El audio no se borra: va a la papelera del "
            "Estudio (%s) después de enviar, y se puede recuperar.\n"
            "  NO = solo las filas; el audio queda donde está.\n"
            "  CANCELAR = no hago nada."
            % (f["Title"], f["Filename"], len(filas),
               "\n".join("  fila %s  -  %s estrellas" % (x["ID"], x["Difficulty"])
                         for x in filas), N.PAPELERA))
        if resp is None:
            return
        try:
            ids = N.borrar_cancion(self.tabla, f["Filename"])
        except RuntimeError as e:
            messagebox.showwarning("Eliminar canción", str(e))
            return
        if resp:
            self.audio_por_borrar.add(f["Filename"])
        self.sucias.update("borrada:%s" % i for i in ids)
        self.b_enviar.config(state="normal")
        self.pareja = []
        self.cargada = None
        self.rej = None
        self.pintar_lista()
        self.cabecera.config(text="")
        messagebox.showinfo("Eliminar canción",
                            "Listo: \"%s\" salió de la lista (%d filas).%s\n\n"
                            "Para que se vaya del juego falta ENVIAR AL JUEGO. Si "
                            "cerrás el Estudio sin enviar, la canción sigue en el "
                            "juego como estaba."
                            % (f["Title"], len(ids),
                               "\nEl audio va a la papelera al enviar." if resp else ""))

    def arreglar_baile(self, todas, modo="todo"):
        """Que el personaje no camine, sin regenerar (nucleo.arreglar_baile)."""
        if self.trabajando or not self.tabla:
            return
        if todas:
            filas = [f for f in self.tabla.filas if not N.es_original(f)]
        else:
            f = self.fila_actual()
            if f is None:
                return
            if N.es_original(f):
                messagebox.showwarning("Arreglar el baile",
                                       "Esta canción está protegida (no la creó el Estudio).\n\nSi la hiciste vos, clic derecho en la lista > Permitir editarla.")
                return
            filas = [x for x in self.tabla.filas if x["Filename"] == f["Filename"]]
        cambios, lineas = [], []
        for f in filas:
            nv, hecho = N.arreglar_baile(f, modo)
            if nv is None:
                continue
            cambios.append((f, nv))
            seg = sum(h[3] for h in hecho)
            lineas.append("  %s (fila %s): %s" % (
                f["Title"][:30], f["ID"],
                ", ".join(h[4] + " -> 511" if h[2] == "baile501" else
                          "misión %d %s (caminaba %.0f s)" % (
                              h[0], "descanso" if h[2] == "descanso" else "frase",
                              h[3]) for h in hecho)))
        if not cambios:
            if modo == "solo501":
                txt = ("No hay nada que arreglar: ninguna misión tiene el baile 501."
                       if not todas else
                       "No hay nada que arreglar: ninguna de tus canciones tiene "
                       "el baile 501.")
            else:
                txt = ("No hay nada que arreglar: el personaje ya baila "
                       "toda la canción." if not todas else
                       "No hay nada que arreglar: en todas tus canciones "
                       "el personaje ya baila todo el tiempo.")
            messagebox.showinfo("Arreglar el baile", txt)
            return
        if modo == "solo501":
            como = ("SOLO cambia el baile 501 (en esas misiones el personaje camina) "
                    "por el 511. No se parte ninguna misión.\n\n"
                    "Lo que se juega queda 100% IGUAL: las flechas, los SPACE, el "
                    "arranque y los tiempos. (Si hay frases largas o descansos, ahí "
                    "puede seguir caminando.)")
        elif modo == "sin_flechas":
            como = ("Las misiones largas se parten y los pedazos nuevos van SIN "
                    "flechas: salen SPACE y el personaje sigue bailando. No aparece "
                    "ninguna flecha nueva. El baile 501 pasa al 511.\n\n"
                    "Las flechas que ya tenías quedan IGUALES, en el mismo orden; "
                    "el arranque y los tiempos no se mueven.")
        else:
            como = ("Los DESCANSOS pasan a misiones sin flechas: salen SPACE y el "
                    "personaje sigue bailando. Las FRASES viejas se parten y la pieza "
                    "nueva repite las flechas de esa misión. El baile 501 (en esas "
                    "misiones el personaje camina) pasa al 511.\n\n"
                    "Todo lo demás queda IGUAL: las otras flechas, el arranque y los "
                    "tiempos no se mueven.")
        if not messagebox.askyesno(
                "Arreglar el baile",
                "Va a quedar así (%d filas):\n\n%s\n\n%s\n\n¿Lo hago?"
                % (len(cambios), "\n".join(lineas[:14]) +
                   ("\n  ..." if len(lineas) > 14 else ""), como)):
            return
        for f, nv in cambios:
            self.modificadas.add(f["ID"])
            f.update(nv)
            self.sucias.add(f["ID"])
        self.b_enviar.config(state="normal")
        self.cargada = None
        self.pintar_lista()
        messagebox.showinfo("Arreglar el baile",
                            "Listo: %d filas arregladas. Para que llegue al juego "
                            "falta ENVIAR AL JUEGO." % len(cambios))

    def bajar_tres(self):
        """Rapidas: 3 flechas -> 2 en lo guardado, sin regenerar (nucleo.bajar_tres)."""
        titulo = "Pasar las 3 flechas a 2"
        if self.trabajando or not self.tabla:
            return
        f = self.fila_actual()
        if f is None:
            return
        if N.es_original(f):
            messagebox.showwarning(titulo, "Esta canción está protegida (no la creó el Estudio).\n\nSi la hiciste vos, clic derecho en la lista > Permitir editarla.")
            return
        filas = [x for x in self.tabla.filas if x["Filename"] == f["Filename"]]
        cambios, lineas = [], []
        for x in filas:
            nv, n = N.bajar_tres(x)
            if nv:
                cambios.append((x, nv))
                # cuenta TANDAS: desde el 2/10/2026 tambien arregla la segunda
                lineas.append("  fila %s (%s estrellas, %s BPM): %d tandas"
                              % (x["ID"], x.get("Difficulty", "?"), x.get("BPM"), n))
        if not cambios:
            messagebox.showinfo(
                titulo, "No hay nada que cambiar: o no tiene 3 flechas juntas, o a esa "
                        "velocidad y dificultad sí van (4★ nunca; 5-6★ desde 200 BPM; "
                        "7-8★ desde 230 BPM; 9-10★ siempre pueden).")
            return
        if not messagebox.askyesno(
                titulo, "Va a quedar así:\n\n%s\n\nEn cada tiempo que tiene 3 flechas "
                        "quedan 2. Lo demás queda IGUAL: los otros tiempos, los SPACE, "
                        "el arranque y los tiempos de la canción.\n\n¿Lo hago?"
                        % "\n".join(lineas)):
            return
        for x, nv in cambios:
            self.modificadas.add(x["ID"])
            x.update(nv)
            self.sucias.add(x["ID"])
        self.b_enviar.config(state="normal")
        self.cargada = None
        self.pintar_lista()
        messagebox.showinfo(titulo, "Listo. Para que llegue al juego falta ENVIAR AL "
                                    "JUEGO (y reiniciar el juego).")

    def mezclar_bailes(self, porcentaje):
        """Mas variedad: parte de las misiones al baile 501 (nucleo.mezclar_bailes)."""
        titulo = "Más variedad de baile"
        if self.trabajando or not self.tabla:
            return
        f = self.fila_actual()
        if f is None:
            return
        if N.es_original(f):
            messagebox.showwarning(titulo, "Esta canción está protegida (no la creó el Estudio).\n\nSi la hiciste vos, clic derecho en la lista > Permitir editarla.")
            return
        filas = [x for x in self.tabla.filas if x["Filename"] == f["Filename"]]
        cambios, lineas = [], []
        for x in filas:
            nv, n501 = N.mezclar_bailes(x, porcentaje)
            total = len([v for v in str(x.get("Length") or "").split(",") if v.strip()])
            if nv is None:
                continue
            cambios.append((x, nv))
            lineas.append("  fila %s (%s estrellas): %d de %d misiones con el 501"
                          % (x["ID"], x.get("Difficulty", "?"), n501, total))
        if not cambios:
            messagebox.showinfo(titulo, "No cambia nada: esta canción ya está así.")
            return
        if porcentaje:
            como = ("En esas misiones el personaje hace la OTRA familia de pasos (el "
                    "501); en las demás sigue el 511. El juego sigue sorteando el baile "
                    "de cada misión dentro de cada familia.\n\n"
                    "Las flechas, los SPACE, el arranque y los tiempos quedan IGUALES.\n\n"
                    "OJO: en Feather (247 BPM) el personaje caminó en misiones 501. "
                    "Probalo jugando; si camina, volvé acá y elegí 'Sacar la mezcla'.")
        else:
            como = ("Todas las misiones vuelven al baile 511. Las flechas y los "
                    "tiempos quedan IGUALES.")
        if not messagebox.askyesno(
                titulo, "Va a quedar así:\n\n%s\n\n%s\n\n¿Lo hago?"
                % ("\n".join(lineas), como)):
            return
        for x, nv in cambios:
            self.modificadas.add(x["ID"])
            x.update(nv)
            self.sucias.add(x["ID"])
        self.b_enviar.config(state="normal")
        self.cargada = None
        self.pintar_lista()
        messagebox.showinfo(titulo, "Listo. Para que llegue al juego falta ENVIAR AL "
                                    "JUEGO (y reiniciar el juego).")

    def enviar(self):
        if not self.sucias:
            return
        try:
            for fila in self.tabla.filas:
                if fila["ID"] not in self.sucias:
                    continue
                resumen = N.resumen_descansos(fila, self.config_secciones(fila)["secciones"])
                if resumen["entradas_en_descanso"]:
                    conflicto = resumen["primer_conflicto"]
                    raise ValueError(
                        "La fila %s (%s estrellas) todavía tiene la misión %s dentro "
                        "de un descanso. Volvé a abrir el mapa y aplicá el descanso "
                        "antes de enviar." % (fila["ID"], fila["Difficulty"], conflicto["mision"]))
        except (OSError, ValueError) as error:
            messagebox.showerror("Cambios pendientes", str(error), parent=self)
            return
        if not messagebox.askyesno(
                "Enviar al juego",
                "Voy a escribir el musictable con %d filas cambiadas.\n\n"
                "Antes hago un respaldo con fecha en:\n%s\n\nSigo?"
                % (len(self.sucias), N.RESPALDOS)):
            return

        por_borrar = set(self.audio_por_borrar)
        recortes = dict(self.recortes)

        def trabajo():
            # LOS RECORTES (6.3.40): primero el audio APARTE (si falla, no se envia
            # nada); despues las filas; despues la tabla; y recien ahi el audio
            # nuevo se instala. Si algo falla en el medio, las filas vuelven.
            preparados, copias = {}, {}
            for fn, ed in recortes.items():
                preparados[fn] = N.preparar_recorte_audio(fn, ed)
            try:
                for fn, ed in recortes.items():
                    for f in [x for x in self.tabla.filas if x["Filename"] == fn]:
                        copias[f["ID"]] = dict(f)
                        nv, _quitadas = N.recortar_filas(f, ed)
                        f.update(nv)
                resp = self.tabla.guardar("estudio")
            except Exception:
                for f in self.tabla.filas:
                    if f["ID"] in copias:
                        f.clear()
                        f.update(copias[f["ID"]])
                for tmp in preparados.values():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                raise
            recortado = []
            for fn, tmp in preparados.items():
                try:
                    recortado.append("%s (lo de antes en %s)"
                                     % (fn, N.instalar_recorte_audio(fn, tmp)))
                except RuntimeError as e:
                    # el audio no se pudo instalar: las filas vuelven y se reescribe
                    for f in self.tabla.filas:
                        if f["ID"] in copias and f["Filename"] == fn:
                            f.clear()
                            f.update(copias[f["ID"]])
                    self.tabla.huella = self.tabla._huella()
                    self.tabla.guardar("estudio")
                    recortado.append("NO SE PUDO RECORTAR %s: %s" % (fn, e))
            salida = N.mapa_sn()
            if recortado:
                salida += "\n\nAudio recortado:\n" + "\n".join(recortado)
            # recien ahora, con la tabla del juego ya sin esas filas
            movidos = []
            for fn in por_borrar:
                movidos += N.audio_a_la_papelera(fn)
            if movidos:
                salida += "\n\nAudio movido a la papelera:\n" + "\n".join(movidos)
            return resp, salida

        def despues(r):
            resp, salida = r
            self.filas_enviadas = {str(f["ID"]): copy.deepcopy(f) for f in self.tabla.filas}
            self.sucias.clear()
            self.modificadas.clear()
            self.audio_por_borrar.clear()
            if self.recortes:
                # el audio cambio: la cancion se vuelve a medir la proxima vez
                self.recortes.clear()
                self.cargada = None
                self.rej = None
            self.b_enviar.config(state="disabled")
            self.pintar_lista()
            limp = getattr(self.tabla, "limpiados", [])
            nota = ""
            if limp:
                nota = ("\n\nNombres que el juego no podía guardar y limpié:\n" +
                        "\n".join("  fila %s: %s" % (i, n) for i, _c, _v, n in limp[:8]))
            messagebox.showinfo(
                "Listo",
                "El musictable se guardó y se verificó leyendo de nuevo sus filas.\n"
                "Destino:\n%s\n\nRespaldo:\n%s\n\n%s%s\n\nCerrá por completo "
                "LoveRitmo.exe y volvé a abrirlo antes de probar. Reiniciá también "
                "el servidor si estaba corriendo." % (N.TABLA, resp.name, salida, nota))
        self._en_hilo("Escribiendo el musictable y rehaciendo el mapa...",
                      trabajo, despues)


class DialogoNombre(tk.Toplevel):
    """La ventanita de "Cambiar nombre": titulo y cantante."""

    def __init__(self, padre, titulo, cantante):
        tk.Toplevel.__init__(self, padre)
        self.title("Cambiar nombre")
        self.transient(padre)
        self.resizable(False, False)
        self.ok = False
        m = ttk.Frame(self, padding=12)
        m.pack(fill="both", expand=True)
        ttk.Label(m, text="Título:").grid(row=0, column=0, sticky="w", pady=4)
        self.v_tit = tk.StringVar(value=titulo)
        e = ttk.Entry(m, textvariable=self.v_tit, width=48)
        e.grid(row=0, column=1, pady=4)
        ttk.Label(m, text="Cantante / estilo:").grid(row=1, column=0, sticky="w",
                                                    pady=4, padx=(0, 8))
        self.v_can = tk.StringVar(value=cantante)
        ttk.Entry(m, textvariable=self.v_can, width=48).grid(row=1, column=1, pady=4)
        ttk.Label(m, style="Sub.TLabel", wraplength=420, justify="left",
                  text="El juego guarda letras occidentales: acentos y ñ sí; "
                       "coreano, japonés o chino no (se quitan solos).").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 8))
        fb = ttk.Frame(m)
        fb.grid(row=3, column=0, columnspan=2, sticky="e")
        ttk.Button(fb, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(fb, text="Guardar", command=self.aceptar).pack(side="right",
                                                                  padx=6)
        self.bind("<Return>", lambda _e: self.aceptar())
        self.bind("<Escape>", lambda _e: self.destroy())
        e.focus_set()
        e.select_range(0, "end")
        self.grab_set()

    def aceptar(self):
        self.titulo = self.v_tit.get()
        self.cantante = self.v_can.get()
        self.ok = True
        self.destroy()


class VentanaVDJ(tk.Toplevel):
    """Que canciones le faltan a Virtual DJ, y como arreglarlo de una vez.

    NO se puede automatizar abriendo Virtual DJ por cada tema: Virtual DJ
    escribe su `database.xml` AL CERRARSE, no al analizar. Pero tiene
    `analyzeSongsOnView = yes`, o sea que analiza solo con ver la carpeta.
    """

    PASOS = ("1.  Abri Virtual DJ.\n"
             "2.  En su navegador de archivos, entra a la carpeta:\n"
             "        %s\n"
             "3.  Dejalo un rato: analiza solo con verla (esta en 'analyze on view').\n"
             "4.  CERRA Virtual DJ. Recien ahi guarda su base.\n"
             "5.  Volve aca y toca 'Volver a leer Virtual DJ'.")

    def __init__(self, padre, faltan, tienen):
        tk.Toplevel.__init__(self, padre)
        self.padre = padre
        self.title("Virtual DJ")
        self.geometry("720x560")
        T.ajustar_alto(self, 720)        # (7/10/2026) que no quede nada escondido abajo
        self.transient(padre)

        m = ttk.Frame(self, padding=12)
        m.pack(fill="both", expand=True)
        ttk.Label(m, text="Cuadrícula de Virtual DJ", style="Titulo.TLabel").pack(
            anchor="w")
        ttk.Label(m, text="%d canciones la tienen, %d no. Las que no la tienen las "
                          "mido yo, y mi medición es la peor de las dos."
                          % (len(tienen), len(faltan)),
                  style="Sub.TLabel", wraplength=680, justify="left").pack(
            anchor="w", pady=(2, 8))

        caja = tk.Text(m, height=9, wrap="word", font=("Segoe UI", 9),
                       relief="flat", background=T.CAJA2, padx=10, pady=8)
        caja.pack(fill="x")
        caja.insert("end",
                    "No se puede hacer que Virtual DJ analice una canción sola desde "
                    "acá: Virtual DJ guarda su base CUANDO SE CIERRA, no cuando "
                    "analiza. Habría que abrirlo y cerrarlo una vez por canción.\n\n"
                    "Pero no hace falta hacerlo de a una:\n\n"
                    + (self.PASOS % N.OGG_NUEVOS))
        caja.configure(state="disabled")

        f = ttk.Frame(m)
        f.pack(fill="x", pady=8)
        ttk.Button(f, text="Abrir la carpeta de las canciones",
                   command=self.abrir_carpeta).pack(side="left")
        ttk.Button(f, text="Volver a leer Virtual DJ",
                   command=self.releer).pack(side="left", padx=6)
        ttk.Button(f, text="Cerrar", command=self.destroy).pack(side="right")

        ttk.Label(m, text="Las que todavía le faltan a Virtual DJ:").pack(anchor="w")
        cols = ("archivo", "titulo")
        self.tv = ttk.Treeview(m, columns=cols, show="headings", height=11)
        self.tv.heading("archivo", text="Archivo")
        self.tv.heading("titulo", text="Canción")
        self.tv.column("archivo", width=110, anchor="w")
        self.tv.column("titulo", width=540, anchor="w")
        sb = ttk.Scrollbar(m, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.llenar(faltan)

    def llenar(self, faltan):
        self.tv.delete(*self.tv.get_children())
        for arch, tit, _ruta in faltan:
            self.tv.insert("", "end", values=(arch, tit))

    def abrir_carpeta(self):
        try:
            os.startfile(str(N.OGG_NUEVOS))
        except Exception as e:
            messagebox.showwarning("Carpeta", str(e))

    def releer(self):
        faltan, tienen = N.falta_en_vdj(self.padre.tabla)
        self.llenar(faltan)
        messagebox.showinfo("Virtual DJ",
                            "Ahora la tienen %d y le faltan %d.\n\n"
                            "Si no cambió, fijate que Virtual DJ esté CERRADO: "
                            "guarda su base al cerrarse."
                            % (len(tienen), len(faltan)), parent=self)


class Dialogo(tk.Toplevel):
    """Los datos de una cancion nueva."""

    def __init__(self, padre, sugerido, candidatos=(), cantante=""):
        tk.Toplevel.__init__(self, padre)
        self.title("Cancion nueva")
        self.resizable(False, False)
        self.ok = False
        self.transient(padre)
        self.grab_set()

        m = ttk.Frame(self, padding=14)
        m.pack(fill="both", expand=True)
        self.v = {}
        campos = [("titulo", "Titulo", sugerido),
                  ("cantante", "Cantante", cantante),
                  ("genero", "Genero", "Dance")]
        for i, (k, t, d) in enumerate(campos):
            ttk.Label(m, text=t + ":").grid(row=i, column=0, sticky="e", pady=3)
            v = tk.StringVar(value=d)
            ttk.Entry(m, textvariable=v, width=38).grid(row=i, column=1, columnspan=3,
                                                        sticky="w", padx=6)
            self.v[k] = v
        # QUE VERSIONES SE CREAN. Una fila por nivel tildado (22/9/2026).
        # No es un invento: en el musictable 2016, que es el que corre este
        # juego, hay 11 canciones con los tres niveles, y en LoveBeat KR son
        # 123. Los numeros de al lado son lo que pone Softnyx en cada nivel,
        # medido en los 3912 charts oficiales; con "Elegirlas solas" tildado se
        # recalculan despues de medir el BPM de verdad.
        ttk.Label(m, text="Versiones:").grid(row=3, column=0, sticky="ne",
                                             pady=(10, 3))
        cn = ttk.Frame(m)
        cn.grid(row=3, column=1, columnspan=3, sticky="w", padx=6, pady=(10, 3))
        self.niv_v, self.niv_e = {}, {}
        for i, (nom, etq, tildado, est) in enumerate(
                (("inicial", "Inicial  (1-3 estrellas)", False, 3),
                 ("basico", "Basico  (4-6)", True, 5),
                 ("profesional", "Profesional  (7-10)", True, 8))):
            v = tk.BooleanVar(value=tildado)
            ttk.Checkbutton(cn, variable=v, text=etq, width=22).grid(
                row=i, column=0, sticky="w")
            e = tk.IntVar(value=est)
            ttk.Spinbox(cn, from_=1, to=10, textvariable=e, width=5).grid(
                row=i, column=1, padx=6)
            self.niv_v[nom] = v
            self.niv_e[nom] = e
        self.auto_v = tk.BooleanVar(value=True)
        ttk.Checkbutton(m, variable=self.auto_v,
                        text="Elegirlas solas (lo que usa Softnyx a ese BPM)").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(m, style="Sub.TLabel", justify="left",
                  text="Con esto tildado no hace falta acertar los números: mide la "
                       "canción primero\ny después le pone a cada versión lo que usa "
                       "Softnyx EN ESE NIVEL a ese BPM,\nmedido en sus 3912 charts. "
                       "Si la canción es lenta (menos de 100 BPM) le pone\nademás el "
                       "x2 a la más difícil, que es lo que hace Softnyx ahí.\n"
                       "OJO: de 200 BPM para arriba Softnyx no hace NINGUNA versión "
                       "inicial.").grid(row=5, column=0, columnspan=4, sticky="w",
                                        padx=(22, 0))
        # QUE FILAS SE PISAN. El musictable tiene 230 filas FIJAS y el escritor
        # no sabe agregar: si le llegan filas nuevas las descarta sin decir nada
        # (avisa por consola, que con pythonw no existe). Por eso hay que elegir
        # cuales se reemplazan.
        self.cand = list(candidatos)
        etiquetas = ["%s  -  %s (%s*)" % (f["ID"], f["Title"][:36], f["Difficulty"])
                     for f in self.cand]
        self.agrega_v = tk.BooleanVar(value=True)
        ttk.Checkbutton(m, variable=self.agrega_v, command=self._cambio_modo,
                        text="Agregar al final, sin pisar ninguna canción").grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(12, 0))
        ttk.Label(m, style="Sub.TLabel", justify="left",
                  text="Comprobado en el juego el 19/9/2026: acepta filas nuevas "
                       "sin problema.\nDestildalo solo si querés pisar una "
                       "canción que ya existe.").grid(
            row=6, column=0, columnspan=4, sticky="w", padx=(22, 0))

        ttk.Label(m, text="Reemplazar:").grid(row=7, column=0, sticky="ne",
                                              pady=(8, 3))
        cajas = ttk.Frame(m)
        cajas.grid(row=7, column=1, columnspan=3, sticky="w", padx=6, pady=(8, 3))
        self.dest, self.combos = [], []
        for i, txt in enumerate(("la fácil   ->", "la difícil ->")):
            ttk.Label(cajas, text=txt).grid(row=i, column=0, sticky="e", pady=2)
            v = tk.StringVar(value=etiquetas[i] if i < len(etiquetas) else "")
            cb = ttk.Combobox(cajas, textvariable=v, values=etiquetas, width=42,
                              state="readonly")
            cb.grid(row=i, column=1, padx=4, pady=2)
            self.dest.append(v)
            self.combos.append(cb)
        self.lbl_dest = ttk.Label(
            m, style="Sub.TLabel", justify="left",
            text="Solo se ofrecen canciones del juego, nunca las tuyas. Se les "
                 "conserva el ID.")
        self.lbl_dest.grid(row=10, column=0, columnspan=4, sticky="w", padx=(6, 0))
        self._cambio_modo()

        self.mus_v = tk.BooleanVar(value=False)
        ttk.Checkbutton(m, variable=self.mus_v,
                        text="Que las flechas sigan la música").grid(
            row=10, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(m, style="Sub.TLabel", justify="left",
                  text="Los SPACE caen en las subidas y no entran flechas donde la"
                       "\ncanción se calla. Se puede probar después con "
                       "ESCUCHAR.").grid(row=11, column=0, columnspan=4, sticky="w",
                                         padx=(22, 0))
        ttk.Label(m, text="Se crean las dos versiones, con el mismo arranque.\n"
                          "Nada llega al juego hasta que aprietes ENVIAR AL JUEGO.",
                  style="Sub.TLabel").grid(row=12, column=0, columnspan=4,
                                           sticky="w", pady=(8, 10))
        bb = ttk.Frame(m)
        bb.grid(row=13, column=0, columnspan=4, sticky="e")
        ttk.Button(bb, text="Cancelar", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(bb, text="Crear", command=self.aceptar).pack(side="right")

    def _cambio_modo(self):
        modo = "disabled" if self.agrega_v.get() else "readonly"
        for cb in self.combos:
            cb.config(state=modo)
        self.lbl_dest.config(
            foreground="#999" if self.agrega_v.get() else "#555")

    def aceptar(self):
        self.titulo = self.v["titulo"].get().strip() or "Sin titulo"
        self.cantante = self.v["cantante"].get().strip() or "?"
        self.genero = self.v["genero"].get().strip() or "Dance"
        self.niveles = [(n, max(1, min(10, int(self.niv_e[n].get()))))
                        for n in ("inicial", "basico", "profesional")
                        if self.niv_v[n].get()]
        if not self.niveles:
            messagebox.showwarning("Versiones",
                                   "Tildá al menos una versión para crear.")
            return
        self.est_a = self.niveles[0][1]
        self.est_b = self.niveles[-1][1]
        self.auto = bool(self.auto_v.get())
        self.por_musica = bool(self.mus_v.get())
        if self.agrega_v.get():
            self.destino = None            # filas nuevas al final
        else:
            self.destino = [v.get().split(" ", 1)[0] for v in self.dest if v.get()]
            if len(set(self.destino)) != 2:
                messagebox.showwarning("Reemplazar",
                                       "Elegí dos filas distintas para reemplazar.")
                return
        self.ok = True
        self.destroy()


class VentanaBPM(tk.Toplevel):
    """Compara x1..x4 del chart y permite aplicarlo a la versión difícil."""

    def __init__(self, padre, d):
        tk.Toplevel.__init__(self, padre)
        self.padre = padre
        self.title("Que BPM poner")
        self.geometry("980x720")
        self.minsize(760, 500)
        self.transient(padre)

        cont = T.Desplazable(self, padding=12)
        cont.pack(fill="both", expand=True)
        m = cont.dentro
        ttk.Label(m, text="¿Qué BPM poner?", style="Titulo.TLabel").pack(anchor="w")

        # ------------------------------------------------ lo que mide cada uno
        g = ttk.LabelFrame(m, text=" Cuánto mide esta canción ", padding=8)
        g.pack(fill="x", pady=(8, 8))
        ttk.Label(g, font=("Consolas", 10),
                  text="Cuadrícula (%s):   %.3f BPM" % (d["origen"], d["base"])).pack(
            anchor="w")
        if d["candidatos"]:
            txt = "   ".join("#%d %.2f (%.0f%%)" % (i + 1, c["bpm"], c["peso"])
                             for i, c in enumerate(d["candidatos"]))
            ttk.Label(g, font=("Consolas", 10),
                      text="Midiendo el audio:   " + txt).pack(anchor="w")
        ttk.Label(g, style="Sub.TLabel", wraplength=700, justify="left",
                  text="La cuadrícula es la que vale: está comprobada contra charts "
                       "que funcionan. La medición de abajo es solo un control, para "
                       "pescar el caso conocido de que Virtual DJ haya detectado la "
                       "mitad del BPM.").pack(anchor="w", pady=(4, 0))
        for av in d["avisos"]:
            ttk.Label(g, foreground=T.AMBAR, wraplength=700, justify="left",
                      text="!  " + av).pack(anchor="w", pady=(4, 0))

        # ------------------------------------------------------- las opciones
        g2 = ttk.LabelFrame(m, text=" Velocidad del chart: x1 a x4 ", padding=8)
        g2.pack(fill="x", pady=(0, 8))
        cols = ("vel", "bpm", "enc", "vent", "mis", "est", "tip", "hoy")
        tv = ttk.Treeview(g2, columns=cols, show="headings", height=4)
        for c, t, w in (("vel", "velocidad", 82), ("bpm", "BPM", 70),
                        ("enc", "encaja con el audio", 120),
                        ("vent", "ventana p/ tipear", 110),
                        ("mis", "dura una misión", 100),
                        ("est", "estrellas que usa Softnyx", 150),
                        ("tip", "par típico", 80),
                        ("hoy", "", 100)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="center")
        for o in d["opciones"]:
            tip = o["tipico"]
            tv.insert("", "end", values=(
                o["nombre"], "%.2f" % o["bpm"], "%.0f %%" % (o["encaje"] or 0),
                "%.2f s" % o["ventana"], "%.1f s" % o["mision"],
                "%d a %d" % (o["lo"], o["hi"]), "%d y %d" % (tip[0], tip[1]),
                "<- la que tenés" if o["usada"] else ""))
        tv.pack(fill="x")
        barra = ttk.Scrollbar(g2, orient="horizontal", command=tv.xview)
        barra.pack(fill="x")
        tv.configure(xscrollcommand=barra.set)
        ttk.Label(g2, style="Sub.TLabel", wraplength=700, justify="left",
                  text="\"Encaja con el audio\" es cuánto pesa ese BPM en la "
                       "medición de arriba. Si varias opciones tienen un peso "
                       "parecido, la canción es ambigua de verdad y no hay forma de "
                       "decidirlo midiendo: se decide escuchando.\n"
                       "\"Par típico\" son las estrellas que Softnyx le pone a una "
                       "fila a ESE BPM: la fácil y la difícil.").pack(
            anchor="w", pady=(6, 0))

        ttk.Label(g2, style="Sub.TLabel", wraplength=700, justify="left",
                  text="El multiplicador cambia el BPM del chart; el audio no se "
                       "acelera. A x2, x3 y x4 hay dos, tres o cuatro tiempos del "
                       "chart por cada pulso de la cuadrícula, con menos tiempo "
                       "para tipear. El arranque se conserva. Probá cómo cae con "
                       "la música antes de generar; x3 y x4 pueden resultar "
                       "difíciles de jugar.").pack(anchor="w", pady=(6, 0))

        # ------------------------------------------------------ la recomendacion
        g3 = ttk.LabelFrame(m, text=" Qué hace Softnyx a esta velocidad ", padding=8)
        g3.pack(fill="x", pady=(0, 8))
        ch = d["chance"]
        if ch >= 60:
            reco = ("A %.0f BPM Softnyx le pone el x2 a la versión difícil en el "
                    "%d%% de las canciones. A esta velocidad es LO NORMAL: sin el "
                    "x2 no hay forma de que una canción así llegue a 10 estrellas."
                    % (d["base"], ch))
            color = "#1b8a3a"
        elif ch >= 25:
            reco = ("A %.0f BPM Softnyx usa el x2 en el %d%% de las canciones. Es "
                    "una opción real: si querés una versión de 10 estrellas, este "
                    "es el camino que usa el juego." % (d["base"], ch))
            color = "#b57600"
        else:
            reco = ("A %.0f BPM Softnyx casi no usa el x2 (%d%% de las canciones): "
                    "la canción ya es bastante rápida y a x2 la ventana quedaría en "
                    "%.2f s. Si igual la querés vertiginosa, se puede, pero no es lo "
                    "que hace el juego."
                    % (d["base"], ch, d["opciones"][1]["ventana"]))
            color = "#555555"
        ttk.Label(g3, wraplength=700, justify="left", foreground=color,
                  text=reco).pack(anchor="w")
        ttk.Label(g3, style="Sub.TLabel", wraplength=700, justify="left",
                  text="Medido en las 512 canciones de Softnyx que tienen dos "
                       "versiones: 418 al mismo BPM y 94 exactamente al doble. Ni "
                       "una a x1.5, x3 o x4; x3 y x4 son opciones manuales.\n"
                       "Por debajo de 90 BPM lo hace siempre (9 de 9); 90-100: 74%; "
                       "100-120: 40%; 120-130: 19%; 130-140: 12%; 140-160: 5%; "
                       "de 160 para arriba: 1%.\n"
                       "Y cuando lo usa, la lenta se queda en 3 estrellas y la "
                       "rápida se va a 10 (42 de 94).").pack(anchor="w", pady=(6, 0))

        # ------------------------------------------------------------ botones
        f = ttk.Frame(m)
        f.pack(fill="x", pady=(10, 0))
        ttk.Label(f, text="La difícil:").pack(side="left", padx=(0, 6))
        dificil = max(padre.pareja,
                      key=lambda fila: int(padre.spins[fila["ID"]][0].get()))
        seleccion = padre.spins[dificil["ID"]][2].get()
        self.v_factor = tk.StringVar(
            value=seleccion if seleccion in ("x1", "x2", "x3", "x4") else "x1")
        ttk.Combobox(f, textvariable=self.v_factor, values=("x1", "x2", "x3", "x4"),
                     state="readonly", width=4).pack(side="left")
        ttk.Button(f, text="Aplicar a la difícil", style="Grande.TButton",
                   command=lambda: self.aplicar(self.v_factor.get(),
                                                solo_dificil=True)).pack(
                                                    side="left", padx=(6, 0))
        ttk.Button(f, text="Todas a velocidad normal",
                   command=lambda: self.aplicar("x1")).pack(side="left", padx=8)
        ttk.Button(f, text="Cerrar", command=self.destroy).pack(side="right")
        ttk.Label(m, style="Sub.TLabel", wraplength=700, justify="left",
                  text="Aplicar a la difícil cambia solo esa fila y conserva las "
                       "otras versiones y sus estrellas. El BPM efectivo aparece "
                       "junto al selector del panel. Para que valga hay que "
                       "apretar GENERAR EL CHART, y para que "
                       "llegue al juego, ENVIAR AL JUEGO.").pack(anchor="w",
                                                                 pady=(8, 0))

    def aplicar(self, modo, solo_dificil=False):
        self.padre.poner_velocidades(modo, solo_dificil=solo_dificil)
        self.destroy()


class VentanaSimular(tk.Toplevel):
    """Ver el chart como se ve en el juego, sin abrir el juego.

    Las flechas, el SPACE y los sonidos de tecla SALEN DEL JUEGO INSTALADO
    (`nucleo.extraer_del_juego`), y las direcciones de cada grupo salen de su
    propia tabla, `keypatterntable_4key.slk.spak`, segun el `KeyPatternID` de
    cada mision. O sea que lo que se ve es lo que va a salir.

    LO QUE NO ES: un emulador. No hay puntaje, ni juicio, ni combo. La linea
    roja del tiempo va por reloj, no leyendo el audio.
    """
    ANCHO, ALTO = 940, 250
    FLECHA, SEP = 45, 6
    ANCHO_SPACE = 62

    def __init__(self, padre, fila, listas, bpm, inicio, estrellas, por_musica):
        tk.Toplevel.__init__(self, padre)
        self.padre = padre
        self.fila, self.listas = fila, listas
        self.bpm, self.inicio, self.estrellas = bpm, inicio, estrellas
        self.inicio = inicio = float(listas.get("StartDelayTime") or inicio)
        self.por_musica = por_musica
        self.rej = padre.rej
        self.dur = float(self.rej.get("dur") or 1)
        self.original = N.es_original(fila)
        self.sonando = False
        self.t0 = self.desde = 0.0

        self.title("Simular")
        self.geometry("%dx%d" % (self.ANCHO + 24, self.ALTO + 180))
        T.ajustar_alto(self, self.ANCHO + 24)
        self.transient(padre)
        self.configure(background="#20242b")

        self.per = 60.0 / bpm
        self.golpes = N.flechas_del_chart(listas, inicio, bpm,
                                          semilla=int(fila["ID"]))
        largos = [int(float(v)) for v in str(listas["Length"]).split(",") if v.strip()]
        self.misiones, t = [], float(inicio)
        for i, largo in enumerate(largos):
            self.misiones.append(dict(n=i + 1, t=t, fin=t + largo * self.per,
                                      ventana=4 * self.per))
            t += largo * self.per
        self.imgs = {}
        self._cargar_imagenes()

        m = ttk.Frame(self, padding=10)
        m.pack(fill="both", expand=True)
        ttk.Label(m, text=fila["Title"], style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(m, style="Sub.TLabel",
                  text="%.0f BPM  |  %d estrellas  |  %d misiones  |  las flechas y "
                       "los sonidos son los del juego; las direcciones salen de su "
                       "tabla de patrones"
                       % (bpm, estrellas, len(self.misiones))).pack(anchor="w",
                                                                   pady=(0, 8))

        self.lienzo = tk.Canvas(m, width=self.ANCHO, height=self.ALTO,
                                background="#151821", highlightthickness=0)
        self.lienzo.pack()

        f = ttk.Frame(m)
        f.pack(fill="x", pady=(10, 0))
        ttk.Button(f, text="SIMULAR", style="Enviar.TButton",
                   command=lambda: self.sonar(max(0.0, self.inicio - 2.0))).pack(
            side="left")
        ttk.Button(f, text="Desde el principio",
                   command=lambda: self.sonar(0.0)).pack(side="left", padx=6)
        ttk.Button(f, text="Parar", command=self.parar).pack(side="left", padx=6)
        ttk.Button(f, text="Cerrar", command=self.cerrar).pack(side="right")

        self.info = ttk.Label(m, style="Sub.TLabel", justify="left", wraplength=900,
                              text="Apretá SIMULAR: vas a ver las flechas de cada "
                                   "misión aparecer en su tiempo, con el sonido de "
                                   "tecla del juego.")
        self.info.pack(anchor="w", pady=(8, 0))
        self._fondo()
        self.protocol("WM_DELETE_WINDOW", self.cerrar)

    # ----------------------------------------------------------- imagenes
    def _cargar_imagenes(self):
        for d in N.DIRECCIONES:
            self._img("flecha_" + d, N.SACADO / ("flecha_%s.png" % d))
        self._img("space", N.SACADO / "space.png")

    def _img(self, clave, ruta):
        try:
            self.imgs[clave] = tk.PhotoImage(file=str(ruta))
        except Exception:
            self.imgs[clave] = None

    # ------------------------------------------------------------- dibujo
    def _fondo(self, mision=None, grupos=(), hasta_tiempo=4):
        """La barra como en el juego: CUATRO celdas, una por tiempo.

        POR QUE ASI. Una mision son 16 tiempos y se tipea en los 4 primeros (y,
        si tiene SEGUNDA TANDA, en los 4 siguientes: la barra se rellena con otros
        4 casilleros, ver `_mover` y nucleo.tandas_de).
        Cada uno de esos 4 es una CELDA: adentro va el grupo de flechas que hay
        que apretar juntas (1, 2 o 3) y, si lo hay, el SPACE. En el juego se ven
        separadas por una rayita, no todas seguidas.

        La primera version las ponia todas en fila, una al lado de la otra, y a
        10 estrellas quedaba un paredon de 19 casillas que no se parecia en nada
        a lo que se ve jugando. Joel lo marco y tenia razon.

        OJO CON EL SPACE. Esta comprobado que un SPACE de valor 1 en un tiempo
        aparece como UN space en el juego (documento 2). Que valga 2 o 3 NO se
        comprobo que sean dos o tres carteles: bien podria ser uno mas largo. Se
        dibuja UN cartel y al lado el numero, para no inventar.
        """
        c = self.lienzo
        c.delete("all")
        cx, cy = self.ANCHO // 2, 96
        por_tiempo = {}
        for g in grupos:
            por_tiempo[g["tiempo"]] = g

        # cuanto mide cada celda
        anchos = []
        for k in range(1, 5):
            g = por_tiempo.get(k)
            w = 16
            if g:
                w += self.FLECHA * len(g["flechas"])
                if g["space"]:
                    w += self.ANCHO_SPACE + (14 if g["space"] > 1 else 0)
            anchos.append(max(64, w))
        ancho = sum(anchos) + 3 * self.SEP

        x0, x1 = cx - ancho // 2 - 26, cx + ancho // 2 + 26
        c.create_rectangle(x0, cy - 36, x1, cy + 36, fill="#2a2016",
                           outline="#c9a227", width=3)
        c.create_oval(x0 - 12, cy - 30, x0 + 16, cy + 30, fill="#e8c65a",
                      outline="#8a6d12")
        c.create_oval(x1 - 16, cy - 30, x1 + 12, cy + 30, fill="#e8c65a",
                      outline="#8a6d12")

        x = cx - ancho // 2
        for k in range(1, 5):
            w = anchos[k - 1]
            activo = mision is not None and k <= hasta_tiempo
            if activo:
                c.create_rectangle(x + 2, cy - 30, x + w - 2, cy + 30,
                                   fill="#3a2d1c", outline="")
            g = por_tiempo.get(k) if activo else None
            xx = x + (w - (0 if not g else
                           self.FLECHA * len(g["flechas"]) +
                           (self.ANCHO_SPACE + (14 if g["space"] > 1 else 0)
                            if g["space"] else 0))) // 2
            if g:
                for d in g["flechas"]:
                    im = self.imgs.get("flecha_" + d)
                    if im is not None:
                        c.create_image(xx + self.FLECHA // 2, cy, image=im)
                    else:
                        c.create_oval(xx + 4, cy - 18, xx + self.FLECHA - 4,
                                      cy + 18, fill="#2f7fd4", outline="#8fb6e8")
                    xx += self.FLECHA
                if g["space"]:
                    im = self.imgs.get("space")
                    if im is not None:
                        c.create_image(xx + self.ANCHO_SPACE // 2, cy, image=im)
                    else:
                        c.create_rectangle(xx + 2, cy - 14, xx + self.ANCHO_SPACE - 2,
                                           cy + 14, fill="#1f6fc4", outline="#9fd0ff")
                    xx += self.ANCHO_SPACE
                    if g["space"] > 1:
                        c.create_text(xx + 6, cy, anchor="w", fill="#9fd0ff",
                                      font=("Segoe UI", 10, "bold"),
                                      text="x%d" % g["space"])
            elif activo:
                c.create_text(x + w // 2, cy, fill="#6b5a2a",
                              font=("Segoe UI", 12), text="-")
            c.create_text(x + w // 2, cy + 42, fill="#8a7a4a",
                          font=("Segoe UI", 8), text="tiempo %d" % k)
            x += w
            if k < 4:
                c.create_line(x + self.SEP // 2, cy - 30, x + self.SEP // 2, cy + 30,
                              fill="#6b5a2a")
                x += self.SEP

        if mision:
            c.create_text(28, 28, anchor="nw", fill="#9aa5b1",
                          font=("Segoe UI", 11, "bold"),
                          text="MISIÓN %d de %d" % (mision["n"], len(self.misiones)))
        else:
            c.create_text(cx, 28, fill="#6b7785", font=("Segoe UI", 10),
                          text="esperando...")
        for k in range(4):
            xx = cx - 90 + k * 60
            c.create_oval(xx - 7, 196, xx + 7, 210, outline="#4a5361",
                          fill="#2a303a", tags=("t%d" % k,))
        c.create_text(cx, 226, fill="#6b7785", font=("Segoe UI", 8),
                      text="los 4 tiempos de la ventana de tipeo")

    def _marcar_tiempos(self, cuantos):
        for k in range(4):
            self.lienzo.itemconfig("t%d" % k,
                                   fill="#e8c65a" if k < cuantos else "#2a303a")

    # ------------------------------------------------------------ acciones
    def sonar(self, desde):
        if self.padre.trabajando:
            return
        self.parar()
        segundos = max(2.0, self.dur - desde)
        modosp = self.padre.modo_space()
        mudos = self.padre.mudos_de(self.fila)
        frases = self.padre.frases_de()
        descanso = bool(self.padre.v_descanso.get())

        def trabajo():
            if self.original:
                return N.previo_de_fila(self.fila, self.rej, segundos=segundos,
                                        desde=desde, sonidos_juego=True)
            return N.previo(self.fila, self.rej, self.estrellas, self.inicio,
                            segundos=segundos, bpm=self.bpm, desde=desde,
                            por_musica=self.por_musica, space=modosp,
                            mudos=mudos, frases=frases, descanso=descanso,
                            marcar_misiones=False, sonidos_juego=True,
                **self.padre.extras(self.fila))

        def despues(r):
            ruta, _inf = r
            N.reproducir(ruta)
            self.desde, self.t0 = desde, time.time()
            self.sonando = True
            self._mover()
        self.padre._en_hilo("Preparando la simulación...", trabajo, despues)

    def _mover(self):
        if not self.sonando:
            return
        t = self.desde + (time.time() - self.t0)
        if t >= self.dur:
            self.parar()
            return
        cual = None
        for ms in self.misiones:
            if ms["t"] <= t < ms["fin"]:
                cual = ms
                break
        if cual is None:
            self._fondo()
            sig = [m for m in self.misiones if m["t"] > t]
            self.info.config(
                text="%s  ->  entre misiones (el personaje baila)%s"
                     % (self._reloj(t),
                        ("   |   la próxima entra en %.1f s" % (sig[0]["t"] - t))
                        if sig else ""))
        else:
            hasta = t - cual["t"]
            paso = int(hasta / self.per)
            # LA SEGUNDA TANDA (MissionID2, 2/10/2026): si la mision la tiene,
            # desde el tiempo 5 la barra muestra sus 4 casilleros, como el juego
            mios = [g for g in self.golpes if g["mision"] == cual["n"]]
            tanda = 2 if (paso >= 4 and any(g["tanda"] == 2 for g in mios)) else 1
            base = 4 * (tanda - 1)
            grupos = [dict(g, tiempo=g["tiempo"] - base) for g in mios
                      if g["tanda"] == tanda and (g["tiempo"] - 1) * self.per <= hasta]
            hoy = max(1, min(4, paso + 1 - base))
            self._fondo(cual, grupos, hasta_tiempo=hoy)
            self._marcar_tiempos(hoy)
            fl = sum(len(g["flechas"]) for g in grupos)
            sp = sum(g["space"] for g in grupos)
            self.info.config(
                text="%s  ->  MISIÓN %d de %d, %s, tiempo %d de 4   |   %d flechas y "
                     "%d SPACE en pantalla"
                     % (self._reloj(t), cual["n"], len(self.misiones),
                        "2ª tanda" if tanda == 2 else "1ª tanda", hoy, fl, sp))
        self.after(40, self._mover)

    def _reloj(self, t):
        return "%d:%02d" % (int(t) // 60, int(t) % 60)

    def parar(self):
        self.sonando = False
        N.parar_sonido()
        try:
            self._fondo()
        except Exception:
            pass

    def cerrar(self):
        self.parar()
        self.destroy()


class EditorAudio(tk.Toplevel):
    """El editor de audio, en una ventana aparte (24/9/2026, pedido de Joel: "tipo
    Audacity, con zoom, seleccionar bien, agregar segundos vacios y fundido").

    Muestra la onda del audio ORIGINAL de la cancion, con zoom y seleccion, y
    arma una EDICION: que parte queda (inicio y fin), segundos de silencio al
    principio y al final, y fundidos de entrada y de salida. No toca nada: al
    "Aplicar" la edicion pasa al mapa (Paso 5) y se hace de verdad al ENVIAR AL
    JUEGO (ver `nucleo.preparar_recorte_audio` / `recortar_filas`).

    Abajo de la onda van las ventanas de flechas del chart, para no cortar
    donde hay flechas.
    """
    ANCHO, ALTO = 1100, 288
    Y_ONDA = (22, 190)
    Y_MIS = (198, 212)
    # (25/9/2026) La tira de abajo: COMO QUEDA la cancion, con los silencios
    # agregados. El dibujo de arriba es el audio ORIGINAL y el silencio no
    # existe ahi, asi que no habia forma de verlo. Joel: "cuando le de a enter,
    # puede actualizarse el audio de la imagen? tipo que se estire".
    Y_RES = (238, 268)
    Y_REGLA = 218
    BLOQUE = 128                   # muestras por bloque de la envolvente

    def __init__(self, mapa):
        tk.Toplevel.__init__(self, mapa)
        self.mapa = mapa
        self.padre = mapa.padre
        self.fila = mapa.fila
        self.rej = mapa.rej
        self.dur = mapa.dur
        ed = mapa._recorte() or N.edicion_de(dict(ini=0.0, fin=self.dur), self.dur)
        self.ed = dict(ed)
        self.v0, self.v1 = 0.0, self.dur        # lo que se ve
        self.sel = None                         # (a, b) seleccion
        self.cursor = 0.0
        self.x = None                           # el audio (22050 Hz, mono)
        self.sonando = False
        self.t0 = self.desde = 0.0
        self._arrastre = None

        self.title("Editor de audio  -  %s" % self.fila["Title"])
        self.geometry("%dx610" % (self.ANCHO + 24))
        T.ajustar_alto(self, self.ANCHO + 24)
        self.transient(mapa)
        m = ttk.Frame(self, padding=10)
        m.pack(fill="both", expand=True)

        fcab = ttk.Frame(m)
        fcab.pack(fill="x")
        ttk.Label(fcab, text="Editor de audio  ·  " + self.fila["Title"],
                  style="Titulo.TLabel").pack(side="left")
        ttk.Button(fcab, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(fcab, text="APLICAR", style="Enviar.TButton",
                   command=self.aplicar).pack(side="right", padx=6)

        # ---- escuchar y zoom
        fb = ttk.Frame(m)
        fb.pack(fill="x", pady=(6, 4))
        ttk.Button(fb, text="▶ Escuchar la selección",
                   command=self.escuchar_seleccion).pack(side="left")
        ttk.Button(fb, text="▶ Desde el cursor",
                   command=lambda: self.escuchar_original(self.cursor, None)).pack(
            side="left", padx=4)
        ttk.Button(fb, text="■ Parar", command=self.parar).pack(side="left")
        ttk.Label(fb, text="   Zoom:").pack(side="left", padx=(12, 2))
        ttk.Button(fb, text="＋", width=3, command=lambda: self.zoom(0.5)).pack(side="left")
        ttk.Button(fb, text="－", width=3, command=lambda: self.zoom(2.0)).pack(side="left",
                                                                            padx=2)
        ttk.Button(fb, text="Ver todo", command=self.ver_todo).pack(side="left", padx=2)
        ttk.Button(fb, text="Zoom a la selección",
                   command=self.zoom_seleccion).pack(side="left", padx=2)
        self.v_compas = tk.BooleanVar(value=False)
        ttk.Checkbutton(fb, variable=self.v_compas,
                        text="pegar al compás").pack(side="left", padx=(12, 0))

        # ---- la onda
        self.lienzo = tk.Canvas(m, width=self.ANCHO, height=self.ALTO,
                                background="#14161b", highlightthickness=1,
                                highlightbackground="#323744")
        self.lienzo.pack()
        self.barra = ttk.Scrollbar(m, orient="horizontal", command=self._scroll)
        self.barra.pack(fill="x")
        self.lienzo.bind("<Button-1>", self._apretar)
        self.lienzo.bind("<B1-Motion>", self._arrastrar)
        self.lienzo.bind("<ButtonRelease-1>", self._soltar)
        self.lienzo.bind("<MouseWheel>", self._rueda)
        self.lienzo.bind("<Motion>", self._encima)

        self.lbl_sel = ttk.Label(m, style="Sub.TLabel")
        self.lbl_sel.pack(anchor="w", pady=(4, 0))

        # ---- que queda
        g1 = ttk.LabelFrame(m, text=" 1 · Qué parte queda ", padding=6)
        g1.pack(fill="x", pady=(6, 0))
        f1 = ttk.Frame(g1)
        f1.pack(fill="x")
        for texto, cmd in (("Queda la selección", self.queda_seleccion),
                           ("Cortar el inicio en el cursor", lambda: self._corte("ini")),
                           ("Cortar el final en el cursor", lambda: self._corte("fin")),
                           ("Lo recomendado", self.recomendado),
                           ("Entera (sin recorte)", self.entera)):
            ttk.Button(f1, text=texto, command=cmd).pack(side="left", padx=(0, 4))

        # ---- silencios y fundidos
        g2 = ttk.LabelFrame(m, text=" 2 · Silencio y fundidos ", padding=6)
        g2.pack(fill="x", pady=(6, 0))
        f2 = ttk.Frame(g2)
        f2.pack(fill="x")
        self.v_num = {}
        for clave, texto in (("sil_ini", "Silencio al inicio"),
                             ("sil_fin", "Silencio al final"),
                             ("fade_in", "Fundido de entrada (sube)"),
                             ("fade_out", "Fundido de salida (baja)")):
            ttk.Label(f2, text=texto + ":").pack(side="left", padx=(0, 3))
            v = tk.StringVar(value="%g" % self.ed[clave])
            sp = ttk.Spinbox(f2, from_=0, to=30, increment=0.5, width=5,
                             textvariable=v, command=self._numeros)
            sp.pack(side="left")
            sp.bind("<KeyRelease>", lambda _e: self._numeros())
            sp.bind("<Return>", lambda _e: self._numeros())      # Joel lo pidio
            sp.bind("<FocusOut>", lambda _e: self._numeros())
            ttk.Label(f2, text="s").pack(side="left", padx=(1, 14))
            self.v_num[clave] = v
        # ---- la curva del fundido y el eco del final (25/9/2026) ----
        f2c = ttk.Frame(g2)
        f2c.pack(fill="x", pady=(4, 0))
        ttk.Label(f2c, text="Curva del fundido de salida:").pack(side="left",
                                                                 padx=(0, 3))
        self.v_curva = tk.StringVar(value=self.ed.get("curva", "pareja"))
        cb = ttk.Combobox(f2c, textvariable=self.v_curva, width=10, state="readonly",
                          values=list(N.CURVAS))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda _e: self._numeros())
        ttk.Label(f2c, text="   Eco al final:").pack(side="left", padx=(14, 3))
        self.v_eco = tk.StringVar(value=self.ed.get("eco", "no"))
        cb2 = ttk.Combobox(f2c, textvariable=self.v_eco, width=8, state="readonly",
                           values=list(N.ECOS))
        cb2.pack(side="left")
        cb2.bind("<<ComboboxSelected>>", lambda _e: self._numeros())
        ttk.Label(f2c, text="sobre los últimos").pack(side="left", padx=(8, 3))
        self.v_ecoseg = tk.StringVar(value="%g" % self.ed.get("eco_seg", N.ECO_SEG))
        sp = ttk.Spinbox(f2c, from_=0, to=60, increment=1, width=5,
                         textvariable=self.v_ecoseg, command=self._numeros)
        sp.pack(side="left")
        sp.bind("<KeyRelease>", lambda _e: self._numeros())
        sp.bind("<Return>", lambda _e: self._numeros())
        sp.bind("<FocusOut>", lambda _e: self._numeros())
        ttk.Label(f2c, text="s").pack(side="left", padx=(1, 0))

        f2b = ttk.Frame(g2)
        f2b.pack(fill="x", pady=(4, 0))
        ttk.Button(f2b, text="Fundido de salida en la selección",
                   command=self.fundido_en_seleccion).pack(side="left")
        ttk.Button(f2b, text="▶ Escuchar cómo empieza",
                   command=lambda: self.escuchar_resultado("inicio")).pack(side="left",
                                                                           padx=(12, 4))
        ttk.Button(f2b, text="▶ Escuchar cómo termina",
                   command=lambda: self.escuchar_resultado("final")).pack(side="left")

        self.lbl_ed = ttk.Label(m, style="Sub.TLabel", wraplength=1090, justify="left")
        self.lbl_ed.pack(anchor="w", pady=(6, 0))
        self.info = ttk.Label(m, style="Sub.TLabel", wraplength=1090, justify="left",
                              text="Cargando el audio...")
        self.info.pack(anchor="w", pady=(2, 0))

        for tecla, fn in (("<space>", self._espacio), ("<Escape>", lambda _e: self.parar())):
            self.bind(tecla, fn)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._texto_ed()
        self.padre._en_hilo("Cargando el audio para el editor...", self._cargar,
                            self._cargado)

    # --------------------------------------------------------------- el audio
    def _cargar(self):
        import numpy as np
        import analizar_bpm as ab
        x = ab.pcm(str(self.rej["ogg"]))
        n = len(x) // self.BLOQUE
        bl = x[:n * self.BLOQUE].reshape(n, self.BLOQUE)
        return x, ab.SR, bl.min(axis=1), bl.max(axis=1)

    def _cargado(self, r):
        self.x, self.sr, self.bmin, self.bmax = r
        self.info.config(text="Arrastrá con el mouse para seleccionar.  Clic = poner el "
                              "cursor.  Rueda = moverse;  Ctrl + rueda = zoom.  "
                              "Barra espaciadora = escuchar / parar.")
        self._dibujar()

    # ------------------------------------------------------------ coordenadas
    def _x(self, t):
        return 8 + (self.ANCHO - 16) * (t - self.v0) / max(1e-6, self.v1 - self.v0)

    def _t(self, x):
        t = self.v0 + (x - 8) / float(self.ANCHO - 16) * (self.v1 - self.v0)
        return max(0.0, min(self.dur, t))

    def _pegar(self, t):
        if self.v_compas.get():
            return max(0.0, min(self.dur, N.pegar_a_compas(self.rej, t)))
        return t

    def _reloj(self, t):
        return "%d:%06.3f" % (int(t) // 60, t - 60 * (int(t) // 60))

    # ----------------------------------------------------------------- dibujo
    def _dibujar(self):
        import numpy as np
        c = self.lienzo
        c.delete("all")
        W = self.ANCHO - 16
        ya, yb = self.Y_ONDA
        mid = (ya + yb) / 2.0
        alto = (yb - ya) / 2.0
        ed = self.ed
        # lo que se va: gris rosado
        for a, b in ((0.0, ed["ini"]), (ed["fin"], self.dur)):
            if b > self.v0 and a < self.v1 and b - a > 0.001:
                c.create_rectangle(self._x(max(a, self.v0)), ya - 14,
                                   self._x(min(b, self.v1)), self.Y_MIS[1],
                                   fill="#4a2228", outline="")
        # la seleccion
        if self.sel:
            a, b = self.sel
            c.create_rectangle(self._x(a), ya - 14, self._x(b), yb,
                               fill="#2b3d5c", outline="#6a9bdc")
        # la onda: min/max por pixel
        if self.x is not None:
            fps = self.sr / float(self.BLOQUE)
            i0 = int(self.v0 * fps)
            i1 = max(i0 + 1, int(self.v1 * fps))
            cols = np.linspace(i0, i1, W + 1).astype(int)
            cols = np.clip(cols, 0, len(self.bmin) - 1)
            pico = float(max(1e-6, np.percentile(np.abs(self.bmax), 99.5)))
            pts = []
            for px in range(W):
                a, b = cols[px], max(cols[px] + 1, cols[px + 1])
                lo = float(self.bmin[a:b].min()) / pico
                hi = float(self.bmax[a:b].max()) / pico
                x = 8 + px
                t = self.v0 + px / float(W) * (self.v1 - self.v0)
                afuera = t < ed["ini"] or t > ed["fin"]
                c.create_line(x, mid - hi * alto, x, mid - lo * alto + 1,
                              fill="#c9a0a0" if afuera else "#3b6fb6")
            c.create_line(8, mid, self.ANCHO - 8, mid, fill="#9fb6d6")
        # el fundido: la curva del volumen
        for clave, desde, hasta in (("fade_in", ed["ini"], ed["ini"] + ed["fade_in"]),
                                    ("fade_out", ed["fin"] - ed["fade_out"], ed["fin"])):
            if ed[clave] > 0 and hasta > self.v0 and desde < self.v1:
                y0, y1 = (yb, ya) if clave == "fade_in" else (ya, yb)
                c.create_line(self._x(desde), y0, self._x(hasta), y1,
                              fill="#d07000", width=2)
        # los bordes de lo que queda
        for t, txt in ((ed["ini"], "empieza"), (ed["fin"], "termina")):
            if self.v0 <= t <= self.v1:
                c.create_line(self._x(t), ya - 14, self._x(t), self.Y_MIS[1],
                              fill="#c02020", width=2)
                c.create_text(self._x(t) + 3, ya - 13, text=txt, anchor="nw",
                              fill="#c02020", font=("Segoe UI", 8, "bold"))
        # las flechas del chart
        c.create_text(10, self.Y_MIS[0] - 1, text="flechas", anchor="sw",
                      fill="#6b7785", font=("Segoe UI", 7))
        for ms in self.mapa.misiones:
            if ms["t"] + ms["ventana"] < self.v0 or ms["t"] > self.v1:
                continue
            col = "#6f93d8" if ms["flechas"] else "#3a3f4b"
            c.create_rectangle(self._x(ms["t"]), self.Y_MIS[0],
                               max(self._x(ms["t"]) + 2, self._x(ms["t"] + ms["ventana"])),
                               self.Y_MIS[1], fill=col, outline="")
        # la regla
        span = self.v1 - self.v0
        paso = next(p for p in (0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60) if span / p <= 14)
        t = (int(self.v0 / paso) + 1) * paso
        while t < self.v1:
            x = self._x(t)
            c.create_line(x, self.Y_REGLA, x, self.Y_REGLA + 5, fill="#aab4c0")
            txt = ("%d:%02d" % (int(t) // 60, int(t) % 60)) if paso >= 1 else \
                  ("%d:%04.1f" % (int(t) // 60, t - 60 * (int(t) // 60)))
            c.create_text(x, self.Y_REGLA + 6, text=txt, anchor="n", fill="#77828f",
                          font=("Segoe UI", 7))
            t += paso
        # el cursor y la cabeza de reproduccion
        if self.v0 <= self.cursor <= self.v1:
            c.create_line(self._x(self.cursor), ya - 14, self._x(self.cursor), yb,
                          fill="#e7e9f0", dash=(2, 2))
        self.cabeza = c.create_line(0, ya - 14, 0, yb, fill="#d02020", width=2,
                                    state="hidden")
        self._dibujar_resultado()
        # la barra de desplazamiento
        self.barra.set(self.v0 / self.dur, self.v1 / self.dur)
        self._texto_sel()

    # ---------------------------------------------------------------- el mouse
    def _dibujar_resultado(self):
        """La tira de abajo: COMO QUEDA la canción, de punta a punta.

        El dibujo de arriba es el audio ORIGINAL, y el silencio que se agrega no
        existe ahí: por eso no se veía. Acá se dibuja el resultado completo
        —silencio + lo que queda + silencio— a escala, así se ve dónde van los
        segundos agregados y cuánto ocupan. Se redibuja con cada cambio.
        """
        c = self.lienzo
        ed = self.ed
        ya, yb = self.Y_RES
        x0, x1 = 8, self.ANCHO - 8
        util = ed["fin"] - ed["ini"]
        total = ed["sil_ini"] + util + ed["sil_fin"]
        if total <= 0.001:
            return
        ancho = float(x1 - x0)

        def px(seg):                       # segundos del RESULTADO -> pixel
            return x0 + ancho * seg / total

        c.create_text(10, ya - 12, anchor="nw", fill="#9ba1b5",
                      font=("Segoe UI", 7),
                      text="así queda la canción (%d:%02d en total)"
                           % (int(total) // 60, int(total) % 60))
        c.create_rectangle(x0, ya, x1, yb, fill="#1a1d24", outline="#323744")
        # los tres bloques
        a = 0.0
        for seg, col, bor, nom in ((ed["sil_ini"], "#262a33", "#3d4452", "silencio"),
                                   (util, "#2f4a70", "#5b86bd", "la canción"),
                                   (ed["sil_fin"], "#262a33", "#3d4452", "silencio")):
            if seg <= 0.001:
                a += seg
                continue
            xa, xb = px(a), px(a + seg)
            c.create_rectangle(xa, ya, xb, yb, fill=col, outline=bor)
            if xb - xa > 46:
                c.create_text((xa + xb) / 2, (ya + yb) / 2, text="%s  %gs" % (nom, seg),
                              fill="#c3c9d6", font=("Segoe UI", 7))
            elif xb - xa > 8:
                c.create_text((xa + xb) / 2, (ya + yb) / 2, text="%gs" % seg,
                              fill="#c3c9d6", font=("Segoe UI", 7))
            a += seg
        # el eco, sobre el final de la parte con música
        eco_s = min(float(ed.get("eco_seg") or 0), util)
        if ed.get("eco", "no") != "no" and eco_s > 0.2:
            xa = px(ed["sil_ini"] + util - eco_s)
            xb = px(ed["sil_ini"] + util)
            c.create_rectangle(xa, ya, xb, yb, fill="#f2b705", outline="#a67c00",
                               stipple="gray50")
            if xb - xa > 38:
                c.create_text((xa + xb) / 2, (ya + yb) / 2, text="eco", fill="#5c4600",
                              font=("Segoe UI", 7))
            # LA COLA, que se mete en el silencio: es el efecto que se busca.
            # Si no hay silencio suficiente, se dibuja hasta donde llega y se
            # ve que queda cortada.
            colas = N.ECO_COLA.get(ed["eco"], 0.0)
            if colas > 0.05:
                xc = px(min(ed["sil_ini"] + util + colas, total))
                c.create_rectangle(xb, ya + 7, xc, yb - 7, fill="#6b5a1e",
                                   outline="#c9a227")
                if xc - xb > 30:
                    c.create_text((xb + xc) / 2, (ya + yb) / 2, text="cola",
                                  fill="#6b5200", font=("Segoe UI", 7))
        # los fundidos: dos cuñas
        if ed["fade_in"] > 0:
            xa, xb = px(ed["sil_ini"]), px(ed["sil_ini"] + min(ed["fade_in"], util))
            c.create_polygon(xa, yb, xb, ya, xb, yb, fill="#7fa8dc", outline="")
        if ed["fade_out"] > 0:
            xb = px(ed["sil_ini"] + util)
            xa = px(ed["sil_ini"] + util - min(ed["fade_out"], util))
            c.create_polygon(xa, ya, xa, yb, xb, yb, fill="#7fa8dc", outline="")

    def _apretar(self, e):
        self._arrastre = self._pegar(self._t(e.x))
        self.sel = None

    def _arrastrar(self, e):
        if self._arrastre is None:
            return
        t = self._pegar(self._t(e.x))
        a, b = sorted((self._arrastre, t))
        self.sel = (a, b) if b - a > 0.01 else None
        self._dibujar()

    def _soltar(self, e):
        if self._arrastre is None:
            return
        t = self._pegar(self._t(e.x))
        a, b = sorted((self._arrastre, t))
        if b - a > 0.01:
            self.sel = (a, b)
        else:
            self.sel = None
            self.cursor = t
        self._arrastre = None
        self._dibujar()

    def _rueda(self, e):
        paso = -1 if e.delta > 0 else 1
        if e.state & 0x0004:                    # Ctrl: zoom donde esta el mouse
            self.zoom(0.7 if paso < 0 else 1.4, centro=self._t(e.x))
        else:
            self._mover(paso * 0.15 * (self.v1 - self.v0))

    def _encima(self, e):
        if not self.sonando:
            self.info.config(text="%s   ·   Arrastrá para seleccionar; clic = cursor; "
                                  "Ctrl + rueda = zoom; espacio = escuchar."
                                  % self._reloj(self._t(e.x)))

    def _espacio(self, _e):
        if self.sonando:
            self.parar()
        elif self.sel:
            self.escuchar_seleccion()
        else:
            self.escuchar_original(self.cursor, None)

    # ------------------------------------------------------------------- zoom
    def zoom(self, factor, centro=None):
        span = self.v1 - self.v0
        centro = centro if centro is not None else (self.v0 + self.v1) / 2.0
        nuevo = max(0.5, min(self.dur, span * factor))
        f = (centro - self.v0) / span if span else 0.5
        self.v0 = max(0.0, min(self.dur - nuevo, centro - f * nuevo))
        self.v1 = self.v0 + nuevo
        self._dibujar()

    def ver_todo(self):
        self.v0, self.v1 = 0.0, self.dur
        self._dibujar()

    def zoom_seleccion(self):
        if not self.sel:
            self.info.config(text="Primero seleccioná algo arrastrando con el mouse.")
            return
        a, b = self.sel
        margen = max(0.2, (b - a) * 0.1)
        self.v0, self.v1 = max(0.0, a - margen), min(self.dur, b + margen)
        self._dibujar()

    def _mover(self, dt):
        span = self.v1 - self.v0
        self.v0 = max(0.0, min(self.dur - span, self.v0 + dt))
        self.v1 = self.v0 + span
        self._dibujar()

    def _scroll(self, *args):
        span = self.v1 - self.v0
        if args[0] == "moveto":
            self.v0 = max(0.0, min(self.dur - span, float(args[1]) * self.dur))
            self.v1 = self.v0 + span
            self._dibujar()
        elif args[0] == "scroll":
            self._mover(int(args[1]) * (0.8 * span if args[2] == "pages" else 0.1 * span))

    # --------------------------------------------------------------- la edicion
    def _poner(self, **cambios):
        ed = dict(self.ed)
        ed.update(cambios)
        if ed["fin"] - ed["ini"] < 30.0:
            self.info.config(text="Así quedaría muy corta (%.0f s): no lo hago."
                                  % (ed["fin"] - ed["ini"]))
            return
        if ed["ini"] >= self.mapa.inicio - 0.5:
            self.info.config(text="El inicio tiene que quedar ANTES de las primeras "
                                  "flechas (%s)." % self._reloj(self.mapa.inicio))
            return
        self.ed = N.edicion_de(ed, self.dur)
        for k, v in self.v_num.items():
            if v.get() != "%g" % self.ed[k]:
                v.set("%g" % self.ed[k])
        self._texto_ed()
        self._dibujar()

    def queda_seleccion(self):
        if not self.sel:
            self.info.config(text="Primero seleccioná, arrastrando, la parte que queda.")
            return
        a, b = self.sel
        fade = self.ed["fade_out"] or (N.FUNDIDO if b < self.dur - 0.05 else 0.0)
        self._poner(ini=a, fin=b, fade_out=fade)

    def _corte(self, cual):
        t = self.cursor
        if cual == "ini":
            self._poner(ini=t)
        else:
            self._poner(fin=t, fade_out=self.ed["fade_out"] or N.FUNDIDO)

    def recomendado(self):
        rec = self.mapa.rec_recorte
        if rec.get("fin") is None and rec.get("ini") is None:
            self.info.config(text="No hace falta recortar: " + rec.get("motivo", ""))
            return
        cambios = {}
        if rec.get("ini") is not None:
            cambios["ini"] = rec["ini"]
        if rec.get("fin") is not None:
            cambios["fin"] = rec["fin"]
            cambios["fade_out"] = self.ed["fade_out"] or N.FUNDIDO
        self._poner(**cambios)
        self.info.config(text="Recomendado: " + rec["motivo"] + ".")

    def entera(self):
        self.ed = N.edicion_de(dict(ini=0.0, fin=self.dur, fade_out=0.0), self.dur)
        for k, v in self.v_num.items():
            v.set("%g" % self.ed[k])
        self._texto_ed()
        self._dibujar()

    def _numeros(self):
        """Lee las casillas y deja la edicion al dia.

        ANTES SE CONGELABA TODO (25/9/2026). Si UNA casilla quedaba vacia,
        `float("")` tiraba ValueError y la funcion hacia `return`: desde ahi
        nada de lo que se tocara se aplicaba -- ni el eco, ni los segundos --
        y sin ningun aviso. Joel lo vio con la casilla del fundido de salida
        vacia: los controles decian "largo / 2 s" y el resumen seguia en
        "suave / 0 s". Ahora una casilla vacia vale 0 y una que no se entiende
        deja ese campo como estaba, sin frenar a las demas.
        """
        cambios = {}
        for k, v in self.v_num.items():
            t = v.get().strip().replace(",", ".")
            if not t:
                cambios[k] = 0.0
                continue
            try:
                cambios[k] = max(0.0, min(30.0, float(t)))
            except ValueError:
                cambios[k] = float(self.ed.get(k, 0.0))
        largo = self.ed["fin"] - self.ed["ini"]
        if cambios["fade_in"] + cambios["fade_out"] > largo:
            # no se frena todo: se recortan los fundidos a lo que entra
            sobra = cambios["fade_in"] + cambios["fade_out"] - largo
            cambios["fade_out"] = max(0.0, cambios["fade_out"] - sobra)
        # la curva y el eco (25/9/2026)
        if hasattr(self, "v_curva"):
            cambios["curva"] = self.v_curva.get()
            cambios["eco"] = self.v_eco.get()
            try:
                cambios["eco_seg"] = max(0.0, min(60.0, float(
                    self.v_ecoseg.get().replace(",", "."))))
            except ValueError:
                cambios["eco_seg"] = self.ed.get("eco_seg", N.ECO_SEG)
        self.ed.update(cambios)
        self.ed = N.edicion_de(self.ed, self.dur)
        self._texto_ed()
        self._dibujar()

    def fundido_en_seleccion(self):
        """El fundido de salida ocupa la seleccion: la cancion termina donde termina
        la seleccion y va bajando desde donde empieza."""
        if not self.sel:
            self.info.config(text="Seleccioná el tramo donde querés que el sonido vaya "
                                  "bajando.")
            return
        a, b = self.sel
        self._poner(fin=b, fade_out=round(b - a, 3))

    def _texto_sel(self):
        if self.sel:
            a, b = self.sel
            self.lbl_sel.config(text="Selección: de %s a %s  (%.3f s)" % (
                self._reloj(a), self._reloj(b), b - a))
        else:
            self.lbl_sel.config(text="Cursor en %s   ·   se ve de %s a %s" % (
                self._reloj(self.cursor), self._reloj(self.v0), self._reloj(self.v1)))

    def _texto_ed(self):
        ed = self.ed
        largo = ed["sil_ini"] + (ed["fin"] - ed["ini"]) + ed["sil_fin"]
        per = 60.0 / self.mapa.bpm
        afuera = sum(1 for ms in self.mapa.misiones
                     if ms["flechas"] and ms["t"] + 4 * per > ed["fin"] - 0.3)
        partes = ["queda de %s a %s" % (self._reloj(ed["ini"]), self._reloj(ed["fin"]))]
        if ed["sil_ini"]:
            partes.append("%g s de silencio antes" % ed["sil_ini"])
        if ed["sil_fin"]:
            partes.append("%g s de silencio después" % ed["sil_fin"])
        if ed["fade_in"]:
            partes.append("sube en %g s" % ed["fade_in"])
        if ed["fade_out"]:
            partes.append("baja en %g s%s" % (ed["fade_out"],
                          "" if ed.get("curva", "pareja") == "pareja"
                          else " (%s)" % ed["curva"]))
        aviso_eco = ""
        if ed.get("eco", "no") != "no":
            cola = N.ECO_COLA.get(ed["eco"], 0.0)
            partes.append("eco %s en los últimos %g s (la cola sigue ~%g s "
                          "después, dentro del silencio)"
                          % (ed["eco"], ed["eco_seg"], cola))
            if ed["sil_fin"] < cola - 0.05:
                aviso_eco = ("  OJO: la cola del eco dura ~%g s y sólo hay %g s de "
                             "silencio al final: se va a cortar. Subí "
                             "\"Silencio al final\" a %g." % (cola, ed["sil_fin"],
                                                              max(cola, 1)))
        self.lbl_ed.config(
            text="LA CANCIÓN QUEDA ASÍ: %s.  Dura %d:%02d (antes %d:%02d).%s\n"
                 "No se toca nada todavía: APLICAR lo pasa al mapa, y se hace de verdad "
                 "al ENVIAR AL JUEGO (el audio de antes queda en la papelera)."
                 % (",  ".join(partes), int(largo) // 60, int(largo) % 60,
                    int(self.dur) // 60, int(self.dur) % 60,
                    (("  OJO: %d misiones con flechas quedan afuera." % afuera)
                     if afuera else "") + aviso_eco))

    def aplicar(self):
        self.parar()
        vacia = N.edicion_vacia(self.ed, self.dur)
        self.mapa._poner_edicion(None if vacia else dict(self.ed),
                                 "Editor: sin cambios en el audio." if vacia else
                                 "Editor aplicado. Se hace de verdad al ENVIAR AL JUEGO.")
        self.destroy()

    # ---------------------------------------------------------------- escuchar
    def _wav(self, origen, desde, segundos, salida):
        orden = [N.FFMPEG, "-v", "error", "-y", "-ss", "%.3f" % max(0.0, desde),
                 "-t", "%.3f" % segundos, "-i", str(origen), "-ac", "2", "-ar", "44100",
                 str(salida)]
        subprocess.run(orden, capture_output=True)
        return salida

    def escuchar_original(self, desde, hasta):
        if self.padre.trabajando:
            return
        self.parar()
        hasta = self.dur if hasta is None else hasta
        seg = max(0.3, hasta - desde)
        salida = N.CACHE / "_editor.wav"

        def trabajo():
            return self._wav(self.rej["ogg"], desde, seg, salida)

        def despues(ruta):
            N.reproducir(ruta)
            self.desde, self.hasta, self.t0 = desde, desde + seg, time.time()
            self.sonando = True
            self.lienzo.itemconfig(self.cabeza, state="normal")
            self._mover_cabeza()
        self.padre._en_hilo("Preparando el audio...", trabajo, despues)

    def escuchar_seleccion(self):
        if not self.sel:
            self.info.config(text="Seleccioná algo arrastrando con el mouse (o usá "
                                  "'Desde el cursor').")
            return
        self.escuchar_original(self.sel[0], self.sel[1])

    def escuchar_resultado(self, donde):
        """Arma el audio editado de verdad (aparte) y hace sonar el principio o el final."""
        if self.padre.trabajando:
            return
        self.parar()
        ed = dict(self.ed)
        fn = self.fila["Filename"]
        tmp = N.CACHE / "_editor_resultado.ogg"
        salida = N.CACHE / "_editor.wav"

        def trabajo():
            N.preparar_recorte_audio(fn, ed, salida=tmp)
            largo = ed["sil_ini"] + (ed["fin"] - ed["ini"]) + ed["sil_fin"]
            desde = 0.0 if donde == "inicio" else max(0.0, largo - 12.0)
            return self._wav(tmp, desde, 12.0, salida)

        def despues(ruta):
            N.reproducir(ruta)
            self.info.config(text="Sonando %s de la canción YA EDITADA (12 s)."
                                  % ("el principio" if donde == "inicio" else "el final"))
        self.padre._en_hilo("Armando el audio editado...", trabajo, despues)

    def _mover_cabeza(self):
        if not self.sonando:
            return
        t = self.desde + (time.time() - self.t0)
        if t >= self.hasta:
            self.parar()
            return
        if self.v0 <= t <= self.v1:
            x = self._x(t)
            self.lienzo.coords(self.cabeza, x, self.Y_ONDA[0] - 14, x, self.Y_ONDA[1])
            self.lienzo.itemconfig(self.cabeza, state="normal")
        else:
            self.lienzo.itemconfig(self.cabeza, state="hidden")
        self.info.config(text="Sonando  %s" % self._reloj(t))
        self.after(50, self._mover_cabeza)

    def parar(self):
        self.sonando = False
        N.parar_sonido()
        try:
            self.lienzo.itemconfig(self.cabeza, state="hidden")
        except Exception:
            pass

    def destroy(self):
        self.parar()
        tk.Toplevel.destroy(self)


class VentanaEntera(EdicionSeccionesMapa, tk.Toplevel):
    """La cancion entera: el mapa, los cuatro compases y la escucha, juntos.

    ANTES ERAN DOS VENTANAS. Una daba los cuatro arranques posibles y la otra el
    mapa, asi que para comparar un compas contra otro habia que cerrar y volver
    a abrir. Ahora los cuatro botones estan ACA: cada clic rehace el chart con
    ese arranque, redibuja el mapa y lo hace sonar.

    El mapa es la cancion de izquierda a derecha:
      * la silueta de arriba son los graves segundo a segundo, o sea donde la
        cancion pega fuerte y donde afloja;
      * cada bloque es la VENTANA DE TIPEO de una mision (sus 4 primeros
        tiempos, la unica parte donde caen flechas). Los otros 12 el personaje
        baila;
      * los bloques grises son misiones calladas, sin flechas;
      * la linea roja es donde esta sonando.

    Un clic en cualquier punto del mapa empieza a sonar desde ahi.
    """
    ANCHO, ALTO = 1120, 150
    Y_GRAVES = (12, 62)
    Y_MISION = (70, 104)
    Y_REGLA = 112

    def __init__(self, padre, fila, listas, bpm, inicio, estrellas, por_musica):
        tk.Toplevel.__init__(self, padre)
        self.padre = padre
        self.fila, self.listas = fila, listas
        self.bpm, self.estrellas = bpm, estrellas
        self.por_musica = por_musica
        self.rej = padre.rej
        self.dur = float(self.rej.get("dur") or 1)
        self.original = N.es_original(fila)
        self.sonando = False
        self.t0 = self.desde = 0.0

        # los cuatro arranques posibles salen SIEMPRE de este, el que vino del
        # panel, asi el 1 sigue siendo el 1 aunque se pruebe el 3 y se vuelva.
        self.base = float(inicio)
        self.base_de_antes = self.base   # para "Volver al arranque de antes"
        self.esperando_voz = False       # el proximo clic en el mapa marca la voz
        self.compas = float(self.rej["compas"])
        self.cual = 0
        self.inicio = self.base
        # lo que el usuario quito a mano, en SEGUNDOS (a, b). Antes eran numeros
        # de mision, pero con los descansos las misiones se reacomodan y el
        # numero deja de apuntar a la misma parte de la cancion.
        # SE ABRE CON LO QUE YA SE HABIA MARCADO: antes empezaba vacio y lo
        # marcado en una ventana anterior se perdia al volver a abrirla
        self.quitados = [] if self.original else list(padre.ultimos_mudos)
        self.repes = set()      # misiones donde pidio REPETICIONES (bolsa 1)
        self._repes_t = [] if self.original else list(padre.ultimas_repes)

        self.title("La cancion entera")
        self.geometry("%dx%d" % (self.ANCHO + 24, min(835, self.winfo_screenheight() - 80)))
        T.ajustar_alto(self, self.ANCHO + 24)
        self.transient(padre)

        # QUE HACE EL CLIC EN EL MAPA. Antes eran combinaciones de teclas (Shift,
        # Ctrl, Alt, clic derecho) que habia que recordar; ahora se elige la
        # herramienta con un boton y se hace clic normal. Las combinaciones
        # siguen andando para quien ya las sabe.
        self.v_herr = tk.StringVar(value="escuchar")

        m = ttk.Frame(self, padding=10)
        m.pack(fill="both", expand=True)

        # ------------------------------------------------------ titulo y escucha
        fcab = ttk.Frame(m)
        fcab.pack(fill="x")
        ttk.Label(fcab, text=fila["Title"], style="Titulo.TLabel").pack(side="left")
        ttk.Button(fcab, text="Cerrar", command=self.cerrar).pack(side="right")
        self.b_secciones = ttk.Button(fcab, text="Secciones: flechas, SPACE y descansos...",
                                     command=self.abrir_secciones)
        self.b_secciones.pack(side="right", padx=6)
        if self.original:
            self.b_secciones.config(state="disabled")
        ttk.Button(fcab, text="?  Cómo se usa",
                   command=lambda: self._ayuda("mapa")).pack(side="right", padx=6)
        self.lbl_cab = ttk.Label(m, style="Sub.TLabel")
        self.lbl_cab.pack(anchor="w", pady=(0, 6))

        fs = ttk.Frame(m)
        fs.pack(fill="x", pady=(0, 6))
        ttk.Button(fs, text="▶  ESCUCHAR ENTERA", style="Enviar.TButton",
                   command=lambda: self.sonar(0.0)).pack(side="left")
        ttk.Button(fs, text="▶  Desde el arranque",
                   command=lambda: self.sonar(max(0.0, self.inicio - 1.5))).pack(
            side="left", padx=6)
        ttk.Button(fs, text="■  Parar", command=self.parar).pack(side="left")
        # DESHACER / REHACER (24/9/2026, pedido de Joel). Guarda cada estado del
        # mapa DESPUES de cada cambio (`_anotar`, al final de `_rehacer_mapa`), asi
        # que vale para todo lo que cambia el chart aca. Ctrl+Z / Ctrl+Y.
        self.historia, self.i_hist, self._restaurando = [], -1, False
        self.b_deshacer = ttk.Button(fs, text="↶  Deshacer (Ctrl+Z)",
                                     command=self.deshacer, state="disabled")
        self.b_deshacer.pack(side="left", padx=(18, 4))
        self.b_rehacer = ttk.Button(fs, text="↷  Rehacer (Ctrl+Y)",
                                    command=self.rehacer, state="disabled")
        self.b_rehacer.pack(side="left")
        # EL ZOOM (27/9/2026, pedido de Joel: "un zoom, mas cerca, con guias para
        # poner cada palito"). Todas las herramientas usan el mismo mapa, asi
        # que con zoom TODAS ganan precision. De cerca aparecen la onda del
        # audio y una guia por cada tiempo.
        self.v0, self.v1 = 0.0, self.dur
        self.pcm = None                  # el audio, se carga al primer zoom
        ttk.Button(fs, text="Ver toda", command=self.ver_toda).pack(side="right")
        ttk.Button(fs, text="▶", width=3, command=lambda: self._correr(0.8)).pack(
            side="right", padx=(0, 6))
        ttk.Button(fs, text="◀", width=3, command=lambda: self._correr(-0.8)).pack(
            side="right")
        ttk.Button(fs, text="－", width=3, command=lambda: self.zoom(2.0)).pack(
            side="right", padx=(0, 6))
        ttk.Button(fs, text="＋", width=3, command=lambda: self.zoom(0.4)).pack(
            side="right")
        ttk.Label(fs, text="Zoom (Ctrl + rueda):").pack(side="right", padx=(0, 4))
        for tecla, fn in (("<Control-z>", self.deshacer), ("<Control-Z>", self.deshacer),
                          ("<Control-y>", self.rehacer), ("<Control-Y>", self.rehacer)):
            self.bind(tecla, lambda _e, f=fn: f())

        # ----------------------------------------------- la barra de herramientas
        fh = ttk.Frame(m)
        fh.pack(fill="x", pady=(0, 4))
        ttk.Label(fh, text="El clic en el mapa:").pack(side="left", padx=(0, 8))
        self.b_herr = {}
        # (7/10/2026) las 10 herramientas en una fila se cortaban a la derecha: van en dos
        fh1, fh2 = fh, ttk.Frame(m)
        fh2.pack(fill="x", pady=(0, 4), after=fh)
        ttk.Label(fh2, text="", width=18).pack(side="left", padx=(0, 8))
        for n, (clave, texto) in enumerate((("escuchar", "Escuchar desde ahí"),
                             ("voz", "Empezar acá"),
                             ("alargar", "Alargar la misión"),
                             ("frase", "Frase empieza acá"),
                             ("ritmo", "El ritmo sigue desde acá"),
                             ("descanso", "Descanso sin misiones"),
                             ("spaces", "Solo SPACE"),
                             ("invertir", "Invertir"),
                             ("suave", "Suave (1-2 flechas)"),
                             ("repes", "Repeticiones"))):
            b = ttk.Radiobutton(fh1 if n < 5 else fh2, text=texto, value=clave,
                                variable=self.v_herr,
                                command=self._cambio_herr)
            b.pack(side="left", padx=2)
            self.b_herr[clave] = b

        # ------------------------------------------------------------ el mapa
        self.lienzo = tk.Canvas(m, width=self.ANCHO, height=self.ALTO,
                                background="#14161b", highlightthickness=1,
                                highlightbackground="#323744")
        self.lienzo.pack()
        self.lienzo.bind("<Button-1>", self.clic)
        self.lienzo.bind("<Motion>", self.encima)
        self.lienzo.bind("<MouseWheel>", self._rueda)
        # los atajos de antes, por si alguien ya los sabe
        self.lienzo.bind("<Button-3>", self.quitar)
        self.lienzo.bind("<Double-Button-1>", self.quitar)
        self.lienzo.bind("<Control-Button-1>", self.repetir)
        self.lienzo.bind("<Shift-Button-1>", self.alargar)
        self.lienzo.bind("<Alt-Button-1>", self.empezar_aca)

        # la leyenda de colores
        fl = ttk.Frame(m)
        fl.pack(fill="x", pady=(4, 0))
        for color, texto in (("#6f93d8", "flechas"), ("#3a3f4b", "sin flechas"),
                             ("#7a3fb0", "arranca una frase"),
                             ("#12a150", "el ritmo sigue"),
                             ("#9aa3ad", "descanso"), ("#2bb3a3", "solo SPACE"),
                             ("#e05aa8", "invertida"), ("#9ccc3c", "suave"),
                             ("#f2b705", "repeticiones"),
                             ("#e04040", "se recorta"),
                             ("#d02020", "lo que está sonando")):
            tk.Label(fl, width=2, background=color, relief="flat").pack(
                side="left", padx=(8, 3))
            ttk.Label(fl, text=texto, style="Sub.TLabel").pack(side="left")

        self.info = ttk.Label(m, style="Sub.TLabel", justify="left", wraplength=1100,
                              text="Pasá el mouse por el mapa para ver qué hay en "
                                   "cada punto.")
        self.info.pack(anchor="w", pady=(4, 6))
        self.lienzo.bind("<Button-2>", self.abrir_secciones)

        # ------------------------------------------------ PASO 1: el arranque
        g = self._paso(m, "1", "El arranque", "arranque")
        fc = ttk.Frame(g)
        fc.pack(fill="x")
        self.b_compas = []
        for k in range(4):
            b = ttk.Button(fc, width=19,
                           command=lambda i=k: self.elegir_compas(i))
            b.pack(side="left", padx=(0, 4))
            self.b_compas.append(b)
        ttk.Button(fc, text="PROBAR LOS 4", command=self.probar_cuatro).pack(
            side="left", padx=(6, 0))
        fc2 = ttk.Frame(g)
        fc2.pack(fill="x", pady=(4, 0))
        self.b_otro = ttk.Button(fc2, text="Probar otro arranque ▸",
                                 command=self.otro_arranque)
        self.b_otro.pack(side="left")
        self.b_voz = ttk.Button(fc2, text="Empezar donde entra la voz",
                                command=self.pedir_voz)
        self.b_voz.pack(side="left", padx=(4, 0))
        self.b_volver = ttk.Button(fc2, text="Volver al de antes",
                                   command=self.volver_arranque)
        self.b_volver.pack(side="left", padx=(4, 0))
        self.lbl_pista = ttk.Label(g, style="Sub.TLabel", wraplength=1060,
                                   justify="left")
        self.lbl_pista.pack(anchor="w", pady=(4, 0))

        # ------------------------------------------------ PASO 2: las frases
        gf = self._paso(m, "2", "Las frases (misiones largas, como Softnyx)", "frases")
        ff = ttk.Frame(gf)
        ff.pack(fill="x")
        ttk.Button(ff, text="Que las elija la música",
                   command=lambda: self._poner_frases("auto")).pack(side="left")
        ttk.Button(ff, text="Todas de 16",
                   command=lambda: self._poner_frases(None)).pack(side="left",
                                                                 padx=4)
        ttk.Checkbutton(ff, variable=padre.v_sin_caminar,
                        command=self._cambio_caminar,
                        text="que no se quede caminando (parte las largas)").pack(
            side="left", padx=(12, 0))
        self.lbl_frases = ttk.Label(ff, style="Sub.TLabel")
        self.lbl_frases.pack(side="left", padx=(10, 0))

        # ------------------------------------------------ PASO 3: los cortes
        gd = self._paso(m, "3", "Los cortes y descansos", "cortes")
        fd = ttk.Frame(gd)
        fd.pack(fill="x")
        ttk.Button(fd, text="Marcar los cortes del ritmo",
                   command=self.marcar_cortes).pack(side="left")
        ttk.Button(fd, text="Devolver todo",
                   command=self.sacar_quitados).pack(side="left", padx=4)
        # LAS DOS OPCIONES, a la vista. No se pueden tener las dos cosas: el
        # personaje solo baila mientras corre una mision, y toda mision muestra
        # algo para tocar (sin flechas el juego pone SPACE). 24/9/2026: Joel vio
        # al personaje caminar en los descansos de Save Your Tears, EoO, Russian
        # Roulette...
        ttk.Label(fd, text="  En lo quitado:").pack(side="left", padx=(8, 4))
        ttk.Radiobutton(fd, variable=padre.v_descanso, value=True,
                        command=lambda: self._aplicar_quitados("Cambiado."),
                        text="no sale nada (camina)").pack(side="left")
        ttk.Radiobutton(fd, variable=padre.v_descanso, value=False,
                        command=lambda: self._aplicar_quitados("Cambiado."),
                        text="sigue bailando (salen SPACE)").pack(side="left",
                                                                  padx=(6, 0))
        self.lbl_cortes = ttk.Label(gd, style="Sub.TLabel")
        self.lbl_cortes.pack(anchor="w", pady=(4, 0))

        # ------------------------------------------------ PASO 5: recortar
        # (se arma aca pero se muestra DEBAJO del paso 4: ver el pack de mas abajo)
        g5 = ttk.LabelFrame(m, text=" Paso 5  ·  Recortar el audio ", padding=6)
        f5 = ttk.Frame(g5)
        f5.pack(fill="x")
        self.b_rec = []
        for texto, cmd in (("Abrir el editor de audio...", self.abrir_editor),
                           ("Usar lo recomendado", self.recorte_recomendado),
                           ("Marcar el final en el mapa", lambda: self._pedir_corte("fin")),
                           ("Marcar el inicio en el mapa", lambda: self._pedir_corte("ini")),
                           ("▶ Escuchar cómo termina", self.escuchar_final),
                           ("Sacar el recorte", self.sacar_recorte)):
            b = ttk.Button(f5, text=texto, command=cmd)
            b.pack(side="left", padx=(0, 4))
            self.b_rec.append(b)
        self.lbl_recorte = ttk.Label(g5, style="Sub.TLabel", wraplength=1060,
                                     justify="left")
        self.lbl_recorte.pack(anchor="w", pady=(4, 0))
        self.rec_recorte = dict(ini=None, fin=None, motivo="")

        # ------------------------------------------------ PASO 4: generar
        g2 = self._paso(m, "4", "Generar", "generar")
        fu = ttk.Frame(g2)
        fu.pack(fill="x")
        self.b_generar = ttk.Button(fu, text="GENERAR EL CHART",
                                    style="Enviar.TButton", command=self.generar)
        self.b_generar.pack(side="left")
        self.b_solodesc = ttk.Button(fu, text="Solo los descansos (no toca las flechas)",
                                     command=self.solo_descansos)
        self.b_solodesc.pack(side="left", padx=(8, 0))
        self.b_usar2 = ttk.Button(fu, text="Solo pasar el arranque al panel",
                                  command=self.usar_en_panel)
        self.b_usar2.pack(side="left", padx=(8, 0))
        ttk.Checkbutton(fu, variable=padre.v_musica,
                        text="flechas sobre los golpes").pack(side="left",
                                                              padx=(12, 0))
        ttk.Checkbutton(fu, variable=padre.v_partes, text="flechas por partes",
                        command=lambda: self._regenerar(
                            "Flechas por partes: %s." % (
                                "la música decide dónde (fuerte, suave, subida)"
                                if padre.v_partes.get() else
                                "apagado, sorteadas como Softnyx"))).pack(
                                    side="left", padx=(12, 0))
        ttk.Checkbutton(fu, variable=padre.v_estilo, text="SPACE como LoveRitmo 2020",
                        command=lambda: self._regenerar(
                            "SPACE como LoveRitmo 2020: %s." % (
                                "menos SPACE en las difíciles y puestos donde la "
                                "música pega fuerte" if padre.v_estilo.get() else
                                "apagado, como antes"))).pack(side="left",
                                                              padx=(12, 0))
        # TILDADA desde el 23/9/2026: un corte de la musica esta en las dos
        # versiones. Destildada, el descanso de la copia de Rihanna quedo solo en
        # la de 3 estrellas y la de 10 no lo tuvo nunca.
        self.v_ambas = tk.BooleanVar(
            value=padre.mudos_solo_fila is None or not padre.ultimos_mudos)
        ttk.Checkbutton(fu, variable=self.v_ambas, command=self._cambio_ambas,
                        text="lo quitado, a las dos versiones").pack(side="left",
                                                                     padx=(12, 0))
        self.lbl_gen = ttk.Label(g2, style="Sub.TLabel", justify="left",
                                 wraplength=1090)
        self.lbl_gen.pack(anchor="w", pady=(4, 0))
        self._texto_generar()
        g5.pack(fill="x", pady=(4, 0))
        b5 = ttk.Button(g5, text="?", width=3, command=lambda: self._ayuda("recortar"))
        b5.place(relx=1.0, x=-2, y=0, anchor="ne")
        self._botones_ayuda = getattr(self, "_botones_ayuda", []) + [b5]
        if self.original:
            for b in self.b_rec:
                b.config(state="disabled")
        self._texto_recorte()

        if self.original:
            for b in self.b_compas + [self.b_voz, self.b_volver, self.b_otro]:
                b.config(state="disabled")
            self.b_usar2.config(state="disabled")
            self.b_generar.config(state="disabled")
            self.b_solodesc.config(state="disabled")
            for clave, b in self.b_herr.items():
                if clave != "escuchar":
                    b.config(state="disabled")
            self.lbl_pista.config(
                text="Esta canción vino con el juego: no se toca. El mapa muestra su "
                     "chart tal como lo hizo Softnyx.")
        else:
            self._pista()
        self._rehacer_mapa()
        self._pintar_botones()
        for b in getattr(self, "_botones_ayuda", []):
            b.lift()
        self._anotar()
        self.protocol("WM_DELETE_WINDOW", self.cerrar)

    # ------------------------------------------------- la forma de la ventana
    def _paso(self, padre, num, titulo, ayuda):
        """Un recuadro de paso: 'PASO n  titulo' y el boton '?' a la derecha."""
        g = ttk.LabelFrame(padre, text=" Paso %s  ·  %s " % (num, titulo), padding=6)
        g.pack(fill="x", pady=(4, 0))
        b = ttk.Button(g, text="?", width=3, command=lambda: self._ayuda(ayuda))
        b.place(relx=1.0, x=-2, y=0, anchor="ne")
        # se levanta al final de __init__: lo que se empaqueta despues lo tapaba
        self._botones_ayuda = getattr(self, "_botones_ayuda", []) + [b]
        return g

    AYUDA = {
        "mapa": (
            "Cómo se usa el mapa",
            "El mapa es la canción de izquierda a derecha.\n\n"
            "• Arriba, la silueta gris son los graves: dónde la canción pega fuerte y "
            "dónde afloja.\n"
            "• Cada bloque azul es donde caen las flechas de una misión (sus 4 "
            "primeros tiempos). En el resto de la misión el personaje baila.\n"
            "• La línea roja es lo que está sonando.\n\n"
            "ARRIBA DEL MAPA elegís qué hace el clic:\n"
            "• Escuchar desde ahí: suena desde ese punto.\n"
            "• Empezar acá: el chart arranca en el compás más cercano (por ejemplo "
            "donde entra la voz).\n"
            "• Alargar la misión: cada clic la alarga un poco (16 > 20 > 24 > 28 > 16).\n"
            "• Frase empieza acá: clic donde vuelve el sonido o empieza una parte "
            "nueva; una misión arranca en el '1' de compás más cercano (si había un "
            "descanso ahí, se acorta).\n"
            "• El ritmo sigue desde acá: para las canciones que SE CORREN a mitad "
            "(dos partes pegadas, un cambio de ritmo). Clic donde empieza la parte "
            "nueva: desde ahí hasta el final las misiones siguen el golpe de ESA "
            "parte, no el del arranque. Queda una línea VERDE; otro clic en ella la "
            "saca. Es lo que hace Softnyx con misiones de 18, 21 o 26 tiempos.\n"
            "• Descanso: esa misión sin flechas; otro clic la devuelve. Cómo queda "
            "lo elegís en el paso 3: 'sigue bailando' (salen SPACE, lo normal) o "
            "'no sale nada' (el personaje camina).\n"
            "• Solo SPACE: esa misión sin flechas, solo SPACE; el personaje sigue "
            "bailando. Otro clic la devuelve.\n"
            "• Invertir: da vuelta la misión: donde había flechas va SPACE y donde "
            "había SPACE van flechas. Otro clic la devuelve.\n"
            "• Repeticiones: pide flechas repetidas ahí; otro clic lo saca.\n\n"
            "ZOOM: Ctrl + rueda del mouse sobre el mapa (o los botones ＋ －). De "
            "cerca aparecen la ONDA del audio y una GUÍA por cada tiempo: la azul "
            "fuerte es donde arranca cada misión (el palito), la gris cada 4 tiempos. "
            "Con zoom, 'Empezar acá' y 'El ritmo sigue desde acá' van JUSTO al tiempo "
            "que tocás. La rueda sola se mueve; 'Ver toda' vuelve.\n\n"
            "Atajos (para quien ya los sabe): clic derecho = descanso, Ctrl+clic = "
            "repeticiones, Shift+clic = alargar, Alt+clic = empezar acá.\n\n"
            "Nada llega al juego hasta que apretás GENERAR y después ENVIAR AL JUEGO "
            "en la ventana de atrás."),
        "arranque": (
            "Paso 1 · El arranque",
            "Dónde empiezan las flechas.\n\n"
            "• Los 4 botones de compás: las flechas caen sólo en el primer compás de "
            "cada misión. Los cuatro son válidos; cambia en qué parte de la frase "
            "entran. PROBAR LOS 4 los hace sonar seguidos (1 pitido = compás 1, 2 "
            "pitidos = compás 2...).\n\n"
            "• Probar otro arranque ▸: recorre las 5 opciones más parecidas a lo que "
            "hace Softnyx. Aprendido de 619 charts oficiales: Softnyx arranca donde "
            "la canción cambia de parte.\n\n"
            "• Empezar donde entra la voz: después hacé clic en el mapa donde canta. "
            "Si pasa del 12% de la canción te avisa, pero te deja.\n\n"
            "• Volver al de antes: deshace todo lo de este paso."),
        "frases": (
            "Paso 2 · Las frases",
            "Cuando la canción mete un compás de más (un puente, un corte, la entrada "
            "del coro), Softnyx alarga la misión de antes y la siguiente vuelve a "
            "arrancar con la frase. Lo hace en 7 de cada 10 charts oficiales.\n\n"
            "La línea VIOLETA en el mapa es donde arranca una frase nueva.\n\n"
            "• Que las elija la música: las pone el programa (acierta más o menos la "
            "mitad; escuchalas).\n"
            "• Todas de 16: sin misiones largas, como antes.\n"
            "• Que no se quede caminando: los bailes del juego duran 16 tiempos. "
            "Una misión de 24 deja al personaje caminando los últimos 8. Con esta "
            "casilla (viene tildada) la frase se arma con piezas de 16 + 8, cada "
            "una con su baile. La pieza corta trae unas flechas más.\n"
            "• Para corregir una: herramienta 'Alargar la misión' y clic en la misión "
            "de antes de donde empieza la frase. Se corre todo hasta la próxima línea "
            "violeta; lo que viene después queda donde está."),
        "cortes": (
            "Paso 3 · Los cortes",
            "Donde la canción se corta o el ritmo para, y no querés flechas.\n\n"
            "HAY QUE ELEGIR, porque no se pueden las dos cosas:\n"
            "• No sale nada (camina): el programa alarga la misión de antes y no "
            "aparece nada para tocar. Pero los bailes del juego duran 16 tiempos: "
            "cuando se terminan, el personaje CAMINA hasta la próxima barra de "
            "flechas. El cartel de abajo dice cuántos segundos.\n"
            "• Sigue bailando (salen SPACE): las misiones se quedan, sin flechas. El "
            "personaje baila siempre, pero el juego pone un SPACE en cada tiempo sin "
            "flechas (comprobado jugando).\n\n"
            "• Marcar los cortes del ritmo: los busca solo (donde los graves casi "
            "desaparecen más de 1.5 s). Mira el ritmo, no la voz.\n"
            "• Herramienta 'Descanso' y clic en una misión: la quitás a mano (franja "
            "gris). Otro clic la devuelve.\n"
            "• La primera misión no puede ir en descanso: para empezar más tarde usá "
            "el paso 1.\n\n"
            "Softnyx tiene lo mismo en sus pausas largas: no existe un baile de más "
            "de 16 tiempos."),
        "recortar": (
            "Paso 5 · Recortar el audio",
            "Para sacar partes de la canción que sobran: un final largo donde solo "
            "hablan o saludan, o una intro sin ritmo.\n\n"
            "• Abrir el editor de audio: una ventana aparte, tipo Audacity, con la "
            "onda del audio, zoom, selección con el mouse, silencio al inicio o al "
            "final, y fundidos de entrada (sube) y de salida (baja).\n"
            "• Usar lo recomendado: el programa busca dónde se termina el ritmo (o "
            "una intro larga sin ritmo) y propone dónde cortar.\n"
            "• Marcar el final / el inicio en el mapa: después hacé clic en el mapa "
            "donde querés cortar.\n"
            "• Escuchar cómo termina: suenan los últimos segundos antes del corte.\n"
            "• Sacar el recorte: vuelve a la canción entera.\n\n"
            "En el mapa, lo que se va queda tapado en rojo. Al final se hace un "
            "fundido de 2 segundos para que no corte seco.\n\n"
            "NO SE TOCA NADA hasta ENVIAR AL JUEGO. Ahí se corta el audio, se ajusta "
            "el chart (las flechas siguen cayendo en el mismo lugar de la música; las "
            "misiones que quedan afuera se sacan) y el audio de antes queda en la "
            "papelera del Estudio. Recomendado: probarlo primero en una COPIA."),
        "generar": (
            "Paso 4 · Generar",
            "GENERAR EL CHART rehace las flechas de la canción con todo lo de arriba. "
            "Queda en memoria: para que llegue al juego falta ENVIAR AL JUEGO en la "
            "ventana de atrás.\n\n"
            "• Solo pasar el arranque al panel: copia el arranque sin generar.\n"
            "• Flechas sobre los golpes: acomoda las flechas sobre los tiempos fuertes.\n"
            "• Lo quitado, a las dos versiones: los descansos van también a la otra "
            "dificultad (fácil/difícil). Las repeticiones van siempre a las dos.\n\n"
            "Sobre las REPETICIONES: piden flechas repetidas (izq-izq-izq...) y llenan "
            "los 4 tiempos para que no se mezclen con SPACE. No lo garantizan: el "
            "juego sortea en cada partida. Marcá TRES misiones seguidas para que se "
            "note."),
    }

    def _ayuda(self, clave):
        titulo, texto = self.AYUDA[clave]
        messagebox.showinfo(titulo, texto, parent=self)

    # ------------------------------------------------------- el recorte
    def _recorte(self):
        """La edicion del audio pendiente de esta cancion (dict completo), o None."""
        ed = self.padre.recortes.get(self.fila["Filename"])
        return N.edicion_de(ed, self.dur) if ed else None

    def _poner_recorte(self, ini, fin, aviso):
        """Cambia solo que parte queda; silencios y fundidos se conservan."""
        base = self._recorte() or N.edicion_de(dict(ini=0.0, fin=self.dur), self.dur)
        base["ini"] = max(0.0, float(ini or 0.0))
        base["fin"] = min(self.dur, float(fin if fin is not None else self.dur))
        if base["fin"] < self.dur - 0.05 and not base["fade_out"]:
            base["fade_out"] = N.FUNDIDO
        if base["fin"] >= self.dur - 0.05 and base["fade_out"] == N.FUNDIDO:
            base["fade_out"] = 0.0
        self._poner_edicion(base, aviso)

    def abrir_editor(self):
        if self.original or self.padre.trabajando:
            return
        if not self.rej.get("ogg"):
            self.info.config(text="No encuentro el audio de esta canción.")
            return
        EditorAudio(self)

    def _poner_edicion(self, ed, aviso):
        """Guarda la edicion (o la saca con None). Se hace de verdad al ENVIAR."""
        if self.original or self.padre.trabajando:
            return
        if ed is not None:
            ed = N.edicion_de(ed, self.dur)
            if ed["fin"] - ed["ini"] < 30.0:
                self.info.config(text="Así quedaría muy corta (%.0f s): no lo hago."
                                      % (ed["fin"] - ed["ini"]))
                return
            if ed["ini"] >= self.inicio - 0.5:
                self.info.config(text="El inicio del recorte tiene que quedar ANTES de "
                                      "las primeras flechas (%s)." % self._reloj(self.inicio))
                return
        if ed is None or N.edicion_vacia(ed, self.dur):
            self.padre.recortes.pop(self.fila["Filename"], None)
        else:
            self.padre.recortes[self.fila["Filename"]] = ed
        self.padre.sucias.add("recorte:%s" % self.fila["Filename"])
        self.padre.b_enviar.config(state="normal")
        self._texto_recorte()
        self._dibujar()
        self._anotar()
        self.info.config(text=aviso)

    def recorte_recomendado(self):
        rec = self.rec_recorte
        if not rec.get("fin") and not rec.get("ini"):
            self.info.config(text="No hace falta recortar: " + rec.get("motivo", ""))
            return
        actual = self._recorte() or dict(ini=0.0, fin=self.dur)
        self._poner_recorte(rec["ini"] if rec.get("ini") is not None else actual["ini"],
                            rec["fin"] if rec.get("fin") is not None else actual["fin"],
                            "Recorte recomendado: " + rec["motivo"] + ".")

    def _pedir_corte(self, cual):
        if self.original or self.padre.trabajando:
            return
        self.v_herr.set("corte" + cual)
        self.lienzo.config(cursor="hand2")
        self.info.config(text="Hacé clic en el mapa donde querés %s." % (
            "que TERMINE la canción" if cual == "fin" else "que EMPIECE la canción"))

    def _clic_corte(self, cual, e):
        t = self._t_de_x(e.x)
        self.v_herr.set("escuchar")
        self._cambio_herr()
        ed = self._recorte() or dict(ini=0.0, fin=self.dur)
        ini, fin = ed["ini"], ed["fin"]
        if cual == "fin":
            self._poner_recorte(ini, t, "La canción va a terminar en %s (con fundido "
                                        "de 2 s)." % self._reloj(t))
        else:
            self._poner_recorte(t, fin, "La canción va a empezar en %s." % self._reloj(t))

    def sacar_recorte(self):
        if self.original or self.padre.trabajando or not self._recorte():
            return
        self._poner_edicion(None, "Sin recorte: la canción queda entera.")

    def escuchar_final(self):
        fin = (self._recorte() or dict(fin=self.dur))["fin"]
        self.sonar(max(0.0, fin - 8.0), hasta=fin)

    def _fin_flechas(self):
        """Donde termina la ultima mision que tiene algo para tocar."""
        con = [ms for ms in getattr(self, "misiones", [])
               if ms["flechas"] > 0 and not self._quitada(ms)]
        return (con[-1]["t"] + con[-1]["largo"]) if con else None

    def _texto_recorte(self):
        if not hasattr(self, "lbl_recorte"):
            return
        if not self.original:
            self.rec_recorte = N.recorte_recomendado(self.rej, self.fila,
                                                     fin_flechas=self._fin_flechas())
        if self.original:
            self.lbl_recorte.config(text="Esta canción vino con el juego: no se recorta.")
            return
        rec = self.rec_recorte
        txt = "Recomendado: %s." % rec.get("motivo", "")
        if rec.get("fin") is not None:
            txt += " Cortar el final en %s." % self._reloj(rec["fin"])
        if rec.get("ini") is not None:
            txt += " Empezar en %s." % self._reloj(rec["ini"])
        rc = self._recorte()
        if rc:
            ini, fin = rc["ini"], rc["fin"]
            per = 60.0 / self.bpm
            # `getattr` y no `self.misiones` a secas: en el __init__ esto se
            # llama ANTES de `_rehacer_mapa()`, que es quien arma las misiones
            # (25/9/2026). Sin recorte pendiente no se llegaba hasta aca y no se
            # notaba; con uno puesto, reabrir el mapa tiraba AttributeError, el
            # mapa quedaba vacio y -- hasta que se arreglo el pump (6.3.42) -- el
            # Estudio se colgaba mudo para siempre. No hace falta recalcular
            # nada: `_rehacer_mapa` vuelve a llamar a este mismo metodo al
            # terminar, ya con las misiones puestas.
            afuera = sum(1 for ms in getattr(self, "misiones", [])
                         if ms["t"] + 4 * per > fin - 0.3)
            extra = []
            if rc["sil_ini"]:
                extra.append("%g s de silencio antes" % rc["sil_ini"])
            if rc["sil_fin"]:
                extra.append("%g s de silencio después" % rc["sil_fin"])
            if rc["fade_in"]:
                extra.append("sube en %g s" % rc["fade_in"])
            if rc["fade_out"]:
                extra.append("baja en %g s" % rc["fade_out"])
            txt += ("\nEDICIÓN PUESTA: queda de %s a %s (se van %.0f s)%s%s. Se aplica "
                    "al ENVIAR AL JUEGO, con respaldo del audio."
                    % (self._reloj(ini), self._reloj(fin), ini + (self.dur - fin),
                       (", " + ", ".join(extra)) if extra else "",
                       (", y %d misiones que quedan afuera" % afuera) if afuera else ""))
        self.lbl_recorte.config(text=txt)

    def _cambio_caminar(self):
        N.SIN_CAMINAR = bool(self.padre.v_sin_caminar.get())
        self._regenerar("Misiones largas %s." % (
            "partidas en piezas de 8 a 16: el personaje baila siempre"
            if N.SIN_CAMINAR else "enteras: el personaje camina al final de cada una"))

    def _cambio_herr(self):
        h = self.v_herr.get()
        self.lienzo.config(cursor="" if h == "escuchar" else "hand2")
        self.info.config(text={
            "escuchar": "Clic en el mapa = escuchar desde ahí.",
            "voz": "Clic en el mapa donde entra la voz = el chart empieza ahí.",
            "alargar": "Clic en una misión = alargarla (16 > 20 > 24 > 28 > 16).",
            "frase": "Clic donde VUELVE el sonido (o empieza una parte nueva) = una "
                     "misión arranca en el '1' de compás más cercano. Si había un "
                     "descanso ahí, se acorta.",
            "ritmo": "Clic donde la música SE CORRE o cambia = desde ahí hasta el "
                     "final las misiones siguen el golpe de ESA parte, no el del "
                     "arranque. Con zoom (Ctrl + rueda) se ven las guías y va justo "
                     "al golpe que tocás. Otro clic en la línea verde la saca.",
            "descanso": "Clic en una misión = descanso sin flechas ni SPACE. "
                        "Clic en el descanso lo devuelve. Para tiempos exactos, "
                        "abrí Secciones: flechas, SPACE y descansos.",
            "repes": "Clic en una misión = pedir repeticiones. Marcá tres seguidas.",
            "spaces": "Clic en una misión = sin flechas, solo SPACE (el personaje "
                      "sigue bailando). Otro clic la devuelve.",
            "invertir": "Clic en una misión = dar vuelta: donde había flechas va "
                        "SPACE y donde había SPACE van flechas. Otro clic la "
                        "devuelve.",
            "suave": "Clic en una misión = SUAVE, para donde baja y solo canta: "
                     "flechas de 1 (y 2 en el golpe más fuerte) en los tiempos "
                     "donde entra la voz; SPACE donde respira. Otro clic la "
                     "devuelve.",
        }[h])

    # --------------------------------------------------------- los compases
    def _opcion(self, k):
        return self.base + k * self.compas

    def _pista(self):
        k, margen, _pts = N.fase_de_frase(self.rej)
        cae = int(round((self.base - self.rej["fase"]) / self.compas)) % 4
        cual = (k - cae) % 4
        if margen >= 60:
            self.lbl_pista.config(
                text="Pista medida: el sonido cambia en el compás %d, o sea la opción "
                     "%d (margen %.0f%%). Igual escuchala: esta pista acierta 3 de 6."
                     % (k + 1, cual + 1, margen))
        else:
            self.lbl_pista.config(
                text="Pista medida: no distingue (margen %.0f%%). Esto no se resuelve "
                     "midiendo; hay que escucharlo." % margen)

    def _pintar_botones(self):
        for k, b in enumerate(self.b_compas):
            marca = "> " if k == self.cual else "   "
            b.config(text="%sCompás %d:  %.3f s" % (marca, k + 1, self._opcion(k)))

    def elegir_compas(self, k):
        if self.original or self.padre.trabajando:
            return
        self.parar()
        self.cual = k
        self.inicio = self._opcion(k)
        # Lo quitado y las repeticiones van en SEGUNDOS de la cancion, asi que
        # siguen valiendo con otro arranque. Antes se BORRABAN al cambiar el
        # compas o el arranque (23/9/2026: parte de lo que se perdio en Rihanna).
        modosp = self.padre.modo_space()
        frases = self.padre.frases_de()
        mudos = self.tramos_mudos()
        descanso = bool(self.padre.v_descanso.get())

        def trabajo():
            nuevos, _inf = N.generar(self.fila, self.rej, self.estrellas,
                                     self.inicio, bpm=self.bpm,
                                     por_musica=self.por_musica,
                                     space=modosp, frases=frases, mudos=mudos,
                                     descanso=descanso,
                **self.padre.extras(self.fila))
            return nuevos

        def despues(nuevos):
            self.listas = nuevos
            self.guardado = False
            self._rehacer_mapa()
            self._pintar_botones()
            self.sonar(max(0.0, self.inicio - 1.5))
        self.padre._en_hilo("Rehaciendo el chart en el compás %d..." % (k + 1),
                            trabajo, despues)

    def otro_arranque(self):
        """Boton: pasa a la siguiente de las 5 opciones mas parecidas a Softnyx.

        Salen de `nucleo.arranques_opciones`. Sin Virtual DJ, el compas de
        Softnyx esta entre estas 5 el 68% de las veces (con la cuadricula
        perfecta, el 89%), asi que esto es recorrerlas de oido. Cada una rehace
        el mapa y suena.
        """
        if self.original or self.padre.trabajando:
            return
        if not getattr(self, "opciones", None):
            self.opciones = N.arranques_opciones(self.rej, cuantos=5)
            self.i_opcion = -1
        if not self.opciones:
            self.lbl_pista.config(text="No encontré arranques posibles en esta canción.")
            return
        self.i_opcion = (self.i_opcion + 1) % len(self.opciones)
        op = self.opciones[self.i_opcion]
        self.base = op["t"]
        self.elegir_compas(0)
        self.lbl_pista.config(
            text="Opción %d de %d: %.3f s (%.1f%% de la canción), chance %.0f%% de ser "
                 "el de Softnyx. Por qué: %s.  Tocá otra vez para la siguiente; si "
                 "las flechas no caen con la frase, probá los compases 2, 3 y 4."
                 % (self.i_opcion + 1, len(self.opciones), op["t"], op["pct"],
                    op["prob"], op["motivo"]))

    def pedir_voz(self):
        """Boton: el proximo clic en el mapa pone el arranque ahi (como Alt+clic)."""
        if self.original or self.padre.trabajando:
            return
        self.v_herr.set("voz")
        self._cambio_herr()
        self.lbl_pista.config(
            text="Ahora hacé CLIC EN EL MAPA donde entra la voz. Si no sabés dónde "
                 "es, primero ESCUCHAR ENTERA y mirá el reloj de abajo; después "
                 "apretá este botón otra vez y marcá.")

    def volver_arranque(self):
        """Boton: deshace los Alt+clic y vuelve al arranque con que se abrio el mapa."""
        if self.original or self.padre.trabajando:
            return
        self.esperando_voz = False
        self.v_herr.set("escuchar")
        self._cambio_herr()
        self.base = self.base_de_antes
        self._pista()
        self.elegir_compas(0)

    def empezar_aca(self, e):
        """Alt + clic: el chart arranca en el '1' de compas mas cercano a ese punto.

        Lo pidio Joel el 22/9/2026: que las flechas empiecen donde entra la
        cantante y no en la intro, porque ahi se puede seguir el ritmo. El
        programa no lo elige solo porque no tiene como saber donde hay voz
        (solo tiene numpy: no hay separador de voces), asi que lo marca el oido.

        Se le restan 0.25 s al clic porque uno reacciona tarde a lo que oye.
        """
        if self.original:
            self.info.config(text="Esta canción vino con el juego: su arranque no se "
                                  "toca.")
            return
        if self.padre.trabajando:
            return
        if self._con_zoom():
            # con zoom se ven las guias: va al tiempo que se toco, sin restar
            # la demora de reaccion
            nuevo = N.pegar_a_tiempo(self.rej, self._t_de_x(e.x))
        else:
            t = max(0.0, self._t_de_x(e.x) - 0.25)
            nuevo = N.pegar_a_compas(self.rej, t)
        while nuevo < 0:
            nuevo += self.compas
        self.base = nuevo
        self.elegir_compas(0)
        pct = 100.0 * nuevo / self.dur
        txt = ("Arranque puesto en %.3f s (el '1' de compás más cercano a donde "
               "marcaste), el %.1f%% de la canción. Los cuatro botones cuentan desde "
               "acá: si las flechas no caen con la frase, probá el 2, 3 o 4."
               % (nuevo, pct))
        if pct > 12.0:
            txt += ("\nOJO: pasa del 12%. Softnyx casi nunca arranca tan tarde, y "
                    "Heartstrings (16.6%) y la primera Gee (13.7%) te parecieron "
                    "tarde. Si a esta la escuchás bien, dejala: manda tu oído.")
        self.lbl_pista.config(text=txt)

    def usar_en_panel(self):
        self.padre.v_ini.set("%.4f" % self.inicio)
        self.padre._texto_inicio()
        self.info.config(text="Listo: el panel quedó con el arranque %.4f s (compás "
                              "%d). Para que valga, apretá GENERAR EL CHART."
                              % (self.inicio, self.cual + 1))

    def _cambio_ambas(self):
        self.padre.mudos_solo_fila = (None if self.v_ambas.get()
                                      else self.fila["ID"])
        self._texto_generar()

    def _texto_generar(self):
        cual = ("las DOS versiones" if self.v_ambas.get() else
                "la fila %s (%s estrellas) nada más"
                % (self.fila["ID"], self.fila["Difficulty"]))
        self.lbl_gen.config(
            text="Rehace las flechas con todo lo de arriba (los descansos van a %s). "
                 "Después falta ENVIAR AL JUEGO en la ventana de atrás." % cual)

    # --------------------------------------------------- quitar a mano
    def _mision_en(self, x):
        """Que mision cae bajo ese pixel, para quitarla o devolverla.

        OJO: NO se usa la ventana de tipeo sino la mision ENTERA (16 tiempos).
        La ventana es solo el primer cuarto, asi que con 58 misiones en 4:27
        cada bloque dibujado mide 4 pixeles y un pixel vale 0.24 s: pedir que el
        clic cayera justo adentro de la ventana fallaba la mitad de las veces.
        Como las misiones son contiguas, con el tramo entero el clic SIEMPRE
        engancha una, y es la que se ve en ese punto.
        """
        t = self._t_de_x(x)
        for ms in self.misiones:
            if ms["t"] <= t < ms["t"] + ms["largo"]:
                return ms
        # antes del arranque o despues del final: la mas cercana, si esta cerca
        if self.misiones:
            cerca = min(self.misiones, key=lambda m: abs(m["t"] - t))
            if abs(cerca["t"] - t) <= 16 * 60.0 / self.bpm:
                return cerca
        return None

    def tramos_mudos(self):
        """Los tramos que el usuario quito, en SEGUNDOS.

        Van por tiempo y no por numero de mision para que valgan igual en la
        fila facil y en la dificil, que pueden tener distinta cantidad de
        misiones (el caso del x2).
        """
        return list(self.quitados)

    def _quitada(self, ms):
        """La ventana de esa mision cae en algo quitado (y quedo sin flechas)."""
        return N._pisa(ms["t"], ms["ventana"], self.quitados)

    def tramos_repes(self):
        """Los tramos donde se pidieron repeticiones, en SEGUNDOS.

        Van por tiempo y no por numero de mision, igual que los mudos: la fila
        facil y la dificil pueden tener distinta cantidad de misiones.
        """
        return [(ms["t"], ms["t"] + ms["largo"]) for ms in self.misiones
                if ms["n"] - 1 in self.repes]

    # ------------------------------------------------------- las frases
    def alargar(self, e):
        """Shift + clic: esa mision pasa a durar 4 tiempos mas (28 vuelve a 16).

        Las frases van por SEGUNDOS y cada una es un ancla: al alargar una
        mision se corre todo SOLO hasta la proxima linea violeta. La mision de
        antes de esa se acorta lo que haga falta, y de ahi en adelante nada
        cambia. Asi un arreglo en el minuto 1 no desarma el minuto 3.
        """
        if self.original:
            self.info.config(text="Esta canción vino con el juego: no se le toca "
                                  "nada.")
            return
        if self.padre.trabajando:
            return
        ms = self._mision_en(e.x)
        if ms is None:
            self.info.config(text="Ahí no hay ninguna misión: apuntá a uno de los "
                                  "bloques.")
            return
        per = 60.0 / self.bpm
        g = self.grupos[ms.get("grupo", ms["n"] - 1)]
        largos = [m["largo_t"] for m in self.misiones]
        anclas = N.frases_de_largos(self.inicio, self.bpm, largos)
        fin_viejo = g["t"] + g["largo"]
        anclas = [f for f in anclas if abs(f - fin_viejo) > 0.01]
        # hasta 28: una de 32 es lo mismo que dos de 16 sin la ventana del
        # medio, o sea una pausa, y eso ya lo hace "quitar la mision"
        nuevo = {16: 20, 20: 24, 24: 28}.get(g["largo_t"], 16)
        if nuevo != 16:
            anclas.append(round(g["t"] + nuevo * per, 4))
        self._poner_frases(sorted(anclas),
                           aviso="Misión %d: ahora dura %d tiempos%s."
                                 % (ms["n"], nuevo,
                                    "" if nuevo == 16 else
                                    " y la %d arranca con la frase" % (ms["n"] + 1)))

    def frase_aca(self, e):
        """Clic donde vuelve el sonido: una mision arranca en ese '1' de compas.

        Pedido de Joel (24/9/2026): despues de un descanso las flechas volvian
        un poco DESPUES de la musica, porque la mision siguiente arranca en el
        proximo punto de la cuadricula de frases (cada 16 tiempos desde el
        arranque), y eso no siempre coincide con el sonido. "Alargar" solo corre
        para mas tarde. Esto pone un ANCLA ahi.
        """
        if self.original:
            self.info.config(text="Esta canción vino con el juego: no se le toca "
                                  "nada.")
            return
        if self.padre.trabajando:
            return
        t = self._t_de_x(e.x) if self._con_zoom() else max(0.0, self._t_de_x(e.x) - 0.1)
        # despues de un "el ritmo sigue desde aca", el compas cuenta desde ahi
        per = 60.0 / self.bpm
        orig = [x for x in self.padre.ultimos_ritmos if x <= t + 2 * per]
        if orig:
            o = max(orig)
            self._anclar([o + round((t - o) / (4 * per)) * 4 * per], "Frase nueva")
            return
        self._anclar([N.pegar_a_compas(self.rej, t)], "Frase nueva")

    def ritmo_aca(self, e):
        """EL RITMO SIGUE DESDE ACA (27/9/2026, pedido de Joel).

        "Hay canciones que se pierden a mitad, o cambia el ritmo, y quiero seguir
        el ritmo de la musica ahi: una opcion que cuando le de clic arranque
        siguiendo a partir de ahi hacia el final su compas, ya no la del
        principio". Pasa en canciones armadas con partes pegadas: entre dos
        partes queda un numero de tiempos que no cierra con misiones de 16, y
        con un solo arranque una parte queda bien y la otra corrida (Take On Me:
        179 pulsos entre las dos partes fuertes).

        Mide el pulso de ESA parte (`nucleo.enganchar_ritmo`) y pone ahi un
        ritmo: la mision de antes se estira o se acorta lo que haga falta, y de
        ahi en adelante todo cuenta desde ese punto. Softnyx hace lo mismo con
        misiones de 18, 21 y 26 tiempos en 12 de sus 237 charts; contra esos 14
        puntos, el clic con zoom cae a menos de 40 ms del de Softnyx en 12 y el
        clic de oido en el mismo tiempo en 13.
        """
        if self.original:
            self.info.config(text="Esta canción vino con el juego: no se le toca "
                                  "nada.")
            return
        if self.padre.trabajando:
            return
        per = 60.0 / self.bpm
        t = self._t_de_x(e.x)
        ritmos = list(self.padre.ultimos_ritmos)
        # otro clic en una linea verde: se saca
        cerca = [x for x in ritmos if abs(x - t) <= max(0.35, 2 * per,
                                                         6 * self._seg_por_px())]
        if cerca:
            ritmos.remove(min(cerca, key=lambda x: abs(x - t)))
            self.padre.ultimos_ritmos = tuple(ritmos)
            self._regenerar("Sacado: ahí el ritmo vuelve a contar desde el anterior.")
            return
        exacto = self._con_zoom()
        pulso = N.pulso_de(self.rej, self.bpm)

        def trabajo():
            x, sr = self._pcm_cargado()
            return N.enganchar_ritmo(x, sr, t, self.bpm, exacto=exacto, pulso=pulso)

        def despues(r):
            ta = float(r["t"])
            if ta < self.inicio + 16 * per - 0.01:
                self.info.config(text="Ahí no se puede: tiene que haber por lo menos "
                                      "una misión entera después del arranque. Para "
                                      "mover el arranque usá 'Empezar acá'.")
                return
            nuevos = [x for x in self.padre.ultimos_ritmos
                      if abs(x - ta) >= 16 * per - 0.01]
            reemplazo = len(nuevos) < len(self.padre.ultimos_ritmos)
            self.padre.ultimos_ritmos = tuple(sorted(nuevos + [ta]))
            # el descanso que tapa el punto termina ahi, como en "Frase empieza aca"
            self.quitados = [(a, b if not (a < ta < b) else ta)
                             for a, b in self.quitados
                             if (b if not (a < ta < b) else ta) - a > 0.3]
            self.padre.ultimos_mudos = tuple(self.tramos_mudos())
            # cuanto se corrio contra lo que habia
            antes = [ms["t"] for ms in self.misiones]
            prev = max([x for x in antes if x <= ta + 0.01] or [self.inicio])
            corr = (ta - prev) / per
            d = int(round(corr)) % 16
            aviso = ("El ritmo sigue desde %s: de ahí al final las misiones van con el "
                     "golpe de esa parte%s.%s%s"
                     % (self._reloj_fino(ta),
                        " (ahí ya iban con el golpe: no cambia nada)" if d == 0 else
                        " (la misión de antes dura %d tiempos más; se parte para que "
                        "el personaje siga bailando)" % d,
                        "  Reemplaza al que estaba a menos de una misión." if reemplazo
                        else "",
                        "" if r["nitidez"] >= 1.3 else
                        "  OJO: ahí el golpe no se oye claro; escuchalo."))
            self._regenerar(aviso, luego=lambda: self.sonar(max(0.0, ta - 3.0)))
        self.padre._en_hilo("Escuchando el ritmo de esa parte...", trabajo, despues)

    def _anclar(self, tiempos, que):
        """Pone una mision arrancando en cada uno de esos segundos (ya pegados al
        compas). Saca las anclas que quedarian a menos de 16 tiempos (esas no se
        pueden cumplir las dos) y acorta los descansos que tapan el ancla."""
        per = 60.0 / self.bpm
        mis = 16 * per
        tiempos = [ta for ta in tiempos if ta >= self.inicio + mis - 0.01]
        if not tiempos:
            self.info.config(text="Ahí no se puede: una frase nueva tiene que estar "
                                  "por lo menos una misión después del arranque. "
                                  "Para mover el arranque usá 'Empezar acá'.")
            return False
        anclas = N.frases_de_largos(self.inicio, self.bpm,
                                    [m["largo_t"] for m in self.misiones])
        for ta in tiempos:
            anclas = [f for f in anclas if not (ta - mis + 0.01 < f < ta + mis - 0.01)]
        anclas = sorted(set(round(x, 4) for x in anclas + list(tiempos)))
        # el descanso que tapa el ancla termina en el ancla
        nuevos = []
        for a, b in self.quitados:
            for ta in tiempos:
                if a < ta < b:
                    b = ta
            if b - a > 0.3:
                nuevos.append((a, b))
        self.quitados = nuevos
        self.padre.ultimos_mudos = tuple(self.tramos_mudos())
        self._poner_frases(anclas, aviso="%s en %s (el '1' de compás más cercano)."
                                         % (que, ", ".join(self._reloj(x) + ".%d" %
                                                           int((x % 1) * 10)
                                                           for x in tiempos)))
        return True

    def _poner_frases(self, frases, aviso=""):
        """Rehace el chart con esas frases: "auto", None (todas de 16) o segundos."""
        if self.original or self.padre.trabajando:
            return
        self.parar()
        if frases == "auto":
            self.padre.ultimas_frases = None
            self.padre.v_frases.set(True)
        elif frases is None:
            self.padre.ultimas_frases = None
            self.padre.v_frases.set(False)
        else:
            self.padre.ultimas_frases = tuple(frases)
            self.padre.v_frases.set(True)
        self.padre._texto_musica()
        self._regenerar(aviso)

    def _regenerar(self, aviso="", luego=None):
        """Rehace el chart del mapa con todo lo que esta puesto ahora."""
        self.parar()
        usar = self.padre.frases_de()
        modosp = self.padre.modo_space()
        mudos = self.tramos_mudos()
        descanso = bool(self.padre.v_descanso.get())

        def trabajo():
            nuevos, _inf = N.generar(self.fila, self.rej, self.estrellas,
                                     self.inicio, bpm=self.bpm,
                                     por_musica=self.por_musica, mudos=mudos,
                                     space=modosp, frases=usar, descanso=descanso,
                **self.padre.extras(self.fila))
            return nuevos

        def despues(nuevos):
            self.listas = nuevos
            self.guardado = False
            self._rehacer_mapa()
            self.padre.ultimos_mudos = tuple(self.tramos_mudos())
            self.info.config(text=(aviso + "  " if aviso else "") +
                             "Escuchala con un clic en el mapa, y GENERAR EL CHART "
                             "cuando te guste.")
            if luego:
                self.after(60, luego)
        self.padre._en_hilo("Rehaciendo las misiones...", trabajo, despues)

    def repetir(self, e):
        """Ctrl + clic: pide REPETICIONES en esa mision (la bolsa 1).

        La bolsa 1 es la unica que, para un racimo de 3 flechas, solo tiene
        repeticiones: izq-izq-izq, aba-aba-aba, arr-arr-arr, der-der-der (6.3).

        Hace DOS cosas, y la segunda se aprendio a los golpes: ademas de la
        bolsa, LLENA LOS CUATRO TIEMPOS de flechas. Sin eso, los tiempos que
        quedaban vacios el juego los llenaba de SPACE (6.3.1.1) y la repeticion
        salia mezclada. Ver `nucleo.generar(repetir=...)`.

        NO GARANTIZA que salga una repeticion: el sorteo lo hace el juego en
        cada partida. Solo carga los dados. Por eso conviene marcar TRES
        misiones seguidas: con 2, una de cada tres veces no sale.
        """
        if self.original:
            self.info.config(text="Esta canción vino con el juego: no se le toca "
                                  "nada.")
            return
        ms = self._mision_en(e.x)
        if ms is None:
            self.info.config(text="Ahí no hay ninguna misión: apuntá a uno de los "
                                  "bloques.")
            return
        i = ms["n"] - 1
        if i in self.repes:
            self.repes.discard(i)
            que = "ya no pide repeticiones"
        else:
            self.repes.add(i)
            # una mision quitada no repite nada
            self.quitados = [q for q in self.quitados
                             if not N._pisa(ms["t"], ms["ventana"], [q])]
            que = "va a pedir repeticiones"
        self._repes_t = self.tramos_repes()
        self.padre.ultimas_repes = tuple(self._repes_t)
        self._dibujar()
        seguidas = self._tanda_mas_larga()
        aviso = ""
        if self.repes and seguidas < 3:
            aviso = ("  OJO: la tanda más larga es de %d misión(es). El sorteo lo "
                     "hace el juego en cada partida, así que con menos de 3 "
                     "seguidas hay 1 de cada 3 veces que no se nota."
                     % seguidas)
        self.info.config(text="Misión %d: %s.  Pedidas: %d.%s"
                              % (ms["n"], que, len(self.repes), aviso))
        self._anotar()

    # ------------------------------------------------------- deshacer / rehacer
    def _estado(self):
        """Todo lo que el mapa puede cambiar, en una foto."""
        p = self.padre
        return dict(
            inicio=self.inicio, base=self.base, cual=self.cual,
            quitados=tuple(self.quitados), repes_t=tuple(self.tramos_repes()),
            frases=p.ultimas_frases, v_frases=bool(p.v_frases.get()),
            spaces=tuple(p.ultimos_spaces), inv=tuple(p.ultimos_inv),
            suave=tuple(p.ultimos_suave),
            ritmos=tuple(p.ultimos_ritmos), estilo=bool(p.v_estilo.get()),
            partes=bool(p.v_partes.get()),
            descanso=bool(p.v_descanso.get()), caminar=bool(p.v_sin_caminar.get()),
            solo=p.mudos_solo_fila,
            recorte=(dict(p.recortes[self.fila["Filename"]])
                     if self.fila["Filename"] in p.recortes else None),
            ediciones=copy.deepcopy(p.ediciones_secciones),
            filas_mapa={str(f["ID"]): {c: f.get(c) for c in CAMPOS_CHART}
                        for f in p.pareja},
            listas=dict((c, self.listas.get(c)) for c in N.LISTAS + ["StartDelayTime"]),
            guardado=getattr(self, "guardado", False))

    def _anotar(self):
        if getattr(self, "_restaurando", True) or not hasattr(self, "historia"):
            return
        st = self._estado()
        if self.historia and self.i_hist >= 0 and self.historia[self.i_hist] == st:
            return
        del self.historia[self.i_hist + 1:]       # un cambio nuevo borra lo rehacible
        self.historia.append(st)
        if len(self.historia) > 100:
            self.historia.pop(0)
        self.i_hist = len(self.historia) - 1
        self._botones_historia()

    def _botones_historia(self):
        self.b_deshacer.config(state="normal" if self.i_hist > 0 else "disabled")
        self.b_rehacer.config(state="normal" if self.i_hist < len(self.historia) - 1
                              else "disabled")

    def deshacer(self):
        if self.padre.trabajando or self.i_hist <= 0:
            return
        self.i_hist -= 1
        self._restaurar(self.historia[self.i_hist], "Deshecho")

    def rehacer(self):
        if self.padre.trabajando or self.i_hist >= len(self.historia) - 1:
            return
        self.i_hist += 1
        self._restaurar(self.historia[self.i_hist], "Rehecho")

    def _restaurar(self, st, que):
        p = self.padre
        self.parar()
        self._restaurando = True
        try:
            self.inicio, self.base, self.cual = st["inicio"], st["base"], st["cual"]
            if "ediciones" in st:
                for fila in p.pareja:
                    clave = "%s:%s" % (fila["Filename"], fila["ID"])
                    cfg = st["ediciones"].get(clave, dict(secciones=[], inicio=None, misiones=[]))
                    p.guardar_secciones(fila, cfg["secciones"], cfg["inicio"],
                                        misiones=cfg.get("misiones", []))
            for fila in p.pareja:
                valores = st.get("filas_mapa", {}).get(str(fila["ID"]))
                if valores is None or all(fila.get(c) == v for c, v in valores.items()):
                    continue
                fila.update(valores)
                p.modificadas.add(fila["ID"])
                if fila == getattr(p, "filas_enviadas", {}).get(str(fila["ID"])):
                    p.sucias.discard(fila["ID"])
                else:
                    p.sucias.add(fila["ID"])
            p.b_enviar.config(state="normal" if p.sucias else "disabled")
            p.pintar_lista()
            self.quitados = list(st["quitados"])
            self.repes, self._repes_t = set(), list(st["repes_t"])
            p.ultimas_frases = st["frases"]
            p.v_frases.set(st["v_frases"])
            p.ultimos_spaces, p.ultimos_inv = st["spaces"], st["inv"]
            p.ultimos_suave = st.get("suave", ())
            p.ultimos_ritmos = st.get("ritmos", ())
            p.v_estilo.set(st.get("estilo", False))
            p.v_partes.set(st.get("partes", False))
            p.v_descanso.set(st["descanso"])
            p.v_sin_caminar.set(st["caminar"])
            N.SIN_CAMINAR = st["caminar"]
            p.mudos_solo_fila = st["solo"]
            if st.get("recorte"):
                p.recortes[self.fila["Filename"]] = dict(st["recorte"])
            else:
                p.recortes.pop(self.fila["Filename"], None)
            p.ultimos_mudos = tuple(self.quitados)
            p.ultimas_repes = tuple(self._repes_t)
            self.listas = dict(self.listas)
            self.listas.update(st["listas"])
            self.guardado = st["guardado"]
            self._rehacer_mapa()
            self._pintar_botones()
            self._texto_recorte()
            p._texto_musica()
        finally:
            self._restaurando = False
        self._botones_historia()
        self.info.config(text="%s (%d de %d). Los cambios en las misiones quedan "
                              "listos para ENVIAR AL JUEGO."
                              % (que, self.i_hist + 1, len(self.historia)))

    def _tanda_mas_larga(self):
        """Cuantas misiones seguidas tiene la tanda mas larga de repeticiones."""
        if not self.repes:
            return 0
        v = sorted(self.repes)
        mejor = actual = 1
        for a, b in zip(v, v[1:]):
            actual = actual + 1 if b == a + 1 else 1
            mejor = max(mejor, actual)
        return mejor

    def quitar(self, e):
        """Boton derecho o doble clic: saca o devuelve esa mision."""
        if self.original:
            self.info.config(text="Esta canción vino con el juego: no se le toca "
                                  "nada.")
            return
        if self.padre.trabajando:
            return
        t = self._t_de_x(e.x)
        ya = [q for q in self.quitados if q[0] <= t < q[1]]
        if ya:
            # clic sobre algo quitado: se devuelve
            self.quitados = [q for q in self.quitados if q not in ya]
            que = "Devuelto"
        else:
            ms = self._mision_en(e.x)
            if ms is None:
                self.info.config(text="Ahí no hay ninguna misión: apuntá a uno de "
                                      "los bloques.")
                return
            if ms["n"] == 1 and self.padre.v_descanso.get():
                self.info.config(text="La primera misión no se puede poner en "
                                      "descanso: no hay ninguna antes para alargar. "
                                      "Para empezar más tarde usá 'Empezar donde "
                                      "entra la voz'.")
                return
            self.quitados.append((ms["t"], ms["t"] + ms["largo"]))
            self.repes.discard(ms["n"] - 1)      # una mision quitada no repite nada
            self._repes_t = self.tramos_repes()
            self.padre.ultimas_repes = tuple(self._repes_t)
            que = ("En descanso (no sale nada)" if self.padre.v_descanso.get()
                   else "Quitada (sin flechas: el juego pone SPACE)")
        self._aplicar_quitados("%s.  Tramos quitados: %d." % (que, len(self.quitados)))

    def marcar_tramo(self, e, cual, nombre):
        """Solo SPACE o Invertir: marca o desmarca esa mision (por segundos)."""
        if self.original:
            self.info.config(text="Esta canción vino con el juego: no se le toca "
                                  "nada.")
            return
        if self.padre.trabajando:
            return
        ms = self._mision_en(e.x)
        if ms is None:
            self.info.config(text="Ahí no hay ninguna misión: apuntá a uno de los "
                                  "bloques.")
            return
        lista = list(getattr(self.padre, cual))
        ya = [q for q in lista if N._pisa(ms["t"], ms["ventana"], [q])]
        if ya:
            lista = [q for q in lista if q not in ya]
            que = "vuelve a lo normal"
        else:
            lista.append((ms["t"], ms["t"] + ms["largo"]))
            que = "queda %s" % nombre
            # una mision tiene UNA sola marca: se le sacan las otras
            for otra in ("ultimos_spaces", "ultimos_inv", "ultimos_suave"):
                if otra != cual:
                    setattr(self.padre, otra, tuple(
                        q for q in getattr(self.padre, otra)
                        if not N._pisa(ms["t"], ms["ventana"], [q])))
            self.repes.discard(ms["n"] - 1)
            self._repes_t = self.tramos_repes()
            self.padre.ultimas_repes = tuple(self._repes_t)
        setattr(self.padre, cual, tuple(lista))
        self._regenerar("Misión %d %s.  Solo SPACE: %d  ·  invertidas: %d  ·  "
                        "suaves: %d."
                        % (ms["n"], que, len(self.padre.ultimos_spaces),
                           len(self.padre.ultimos_inv), len(self.padre.ultimos_suave)))

    def _marca_de(self, ms):
        """'spaces', 'invertir', 'suave' o None, para dibujar y para el cartel."""
        if any(s["tipo"] == "patron" and s["desde"] <= ms["t"] < s["hasta"]
               for s in self.secciones_del_mapa()):
            return "manual"
        if N._pisa(ms["t"], ms["ventana"], self.padre.ultimos_spaces):
            return "spaces"
        if N._pisa(ms["t"], ms["ventana"], self.padre.ultimos_inv):
            return "invertir"
        if N._pisa(ms["t"], ms["ventana"], self.padre.ultimos_suave):
            return "suave"
        return None

    def _aplicar_quitados(self, aviso):
        """Guarda lo quitado para ESCUCHAR/SIMULAR/GENERAR y rehace el mapa."""
        if self.original or self.padre.trabajando:
            return
        self.padre.ultimas_repes = tuple(self.tramos_repes())
        self.padre.ultimos_mudos = tuple(self.tramos_mudos())
        self.padre.mudos_solo_fila = (None if self.v_ambas.get()
                                      else self.fila["ID"])
        self._regenerar(aviso)

    def marcar_cortes(self):
        """Boton: pone en descanso los tramos donde se corta el ritmo."""
        if self.original or self.padre.trabajando:
            return
        per = 60.0 / self.bpm
        fin = self.misiones[-1]["t"] + self.misiones[-1]["largo"] if self.misiones \
            else self.dur
        cortes = N.cortes_de_ritmo(self.rej, self.inicio + 16 * per, fin)
        nuevos = 0
        for a, b in cortes:
            # solo las misiones cuya VENTANA cae en el corte; la primera nunca
            for ms in self.misiones[1:]:
                if N._pisa(ms["t"], ms["ventana"], [(a, b)]) and not \
                        N._pisa(ms["t"], ms["ventana"], self.quitados):
                    self.quitados.append((ms["t"], ms["t"] + ms["largo"]))
                    self.repes.discard(ms["n"] - 1)
                    nuevos += 1
        if not cortes:
            self.info.config(text="No encontré cortes del ritmo: los graves no bajan "
                                  "del 30% por más de 1.5 s en ningún lado. Si vos "
                                  "oís uno, marcalo con clic derecho.")
            return
        if not nuevos:
            self.info.config(text="Encontré %d cortes, pero ninguno cae en la ventana "
                                  "de una misión: ya no sale nada ahí." % len(cortes))
            return
        aviso = ("Encontré %d cortes del ritmo y puse %d misiones en descanso: %s. "
                 "Las flechas vuelven en el '1' de compás donde vuelve el sonido."
                 % (len(cortes), nuevos,
                    ", ".join("%s-%s" % (self._reloj(a), self._reloj(b))
                              for a, b in cortes[:6])))
        # donde vuelve el sonido: el primer '1' de compas desde el final del corte
        # (los graves se miden de a 1 segundo, asi que se toma el mas cercano)
        vuelta = [N.pegar_a_compas(self.rej, b) for _a, b in cortes]
        if not self._anclar(vuelta, "Vuelta del sonido"):
            self._aplicar_quitados(aviso)

    def sacar_quitados(self):
        """Boton: devuelve todo lo quitado."""
        if self.original or self.padre.trabajando:
            return
        if not (self.secciones_del_mapa() or self.quitados or self.padre.ultimos_spaces or self.padre.ultimos_inv
                or self.padre.ultimos_suave):
            return
        self.padre.guardar_secciones(self.fila, [], self.inicio)
        self.quitados = []
        self.padre.ultimos_spaces = ()
        self.padre.ultimos_inv = ()
        self.padre.ultimos_suave = ()
        self._aplicar_quitados("Devuelto todo: descansos, solo SPACE, invertidas "
                               "y suaves.")

    def solo_descansos(self):
        """Pone los descansos en el chart que YA ESTA, sin rehacer las flechas.

        Pedido de Joel (25/9/2026). GENERAR rehace todo; esto solo saca (o
        vacia) las misiones de los tramos marcados y deja el resto intacto,
        igual que "Arreglar el baile". No toca arranque, BPM ni estrellas.
        """
        if self.original:
            messagebox.showwarning(
                "Canción original",
                "Esta canción vino con el juego. Esas no se tocan.")
            return
        if self.padre.trabajando:
            return
        self.parar()
        mudos = self.tramos_mudos()
        con_secciones = any(s["tipo"] == "descanso" for f in self.padre.pareja
                             for s in self.padre.config_secciones(f)["secciones"])
        if not mudos and not con_secciones:
            self.info.config(text="No hay ningún tramo marcado. Marcá los descansos "
                                  "en el mapa (o 'Marcar los cortes del ritmo').")
            return
        descanso = bool(self.padre.v_descanso.get())
        solo = None if self.v_ambas.get() else self.fila["ID"]
        objetivo = [f for f in self.padre.pareja
                    if solo is None or f["ID"] == solo]
        hechas, sin = [], []
        pendientes = []
        for f in objetivo:
            nuevos, resumen = N.aplicar_descansos(f, mudos, descanso)
            secciones = [s for s in self.padre.config_secciones(f)["secciones"]
                         if s["tipo"] == "descanso"]
            if secciones:
                base = dict(f)
                base.update(nuevos or {})
                try:
                    nuevos = S.aplicar_secciones(f, base, float(base["StartDelayTime"]),
                                                 float(base["BPM"]), secciones)
                except ValueError as error:
                    messagebox.showerror("Descansos", str(error), parent=self)
                    return
                resumen = "%d tramos sin misiones" % len(secciones)
            if nuevos is None:
                sin.append("fila %s: %s" % (f["ID"], resumen))
                continue
            pendientes.append((f, nuevos, resumen))
        for f, nuevos, resumen in pendientes:
            f.update(nuevos)
            self.padre.modificadas.add(f["ID"])
            self.padre.sucias.add(f["ID"])
            hechas.append("fila %s (%s estrellas): %s"
                          % (f["ID"], f["Difficulty"], resumen))
        if not hechas:
            messagebox.showinfo("Solo los descansos",
                                "No hubo nada que cambiar.\n\n" + "\n".join(sin))
            return
        self.padre.b_enviar.config(state="normal")
        self.padre.pintar_lista()
        self.guardado = True          # lo que se ve ahora ES lo guardado
        self.listas = dict(self.fila)
        self.bpm = float(self.fila["BPM"])
        self._rehacer_mapa()
        self.lbl_gen.config(
            text="DESCANSOS APLICADOS al chart que ya estaba, sin tocar las "
                 "flechas (%s):\n%s\nTodavía NO está en el juego: falta ENVIAR "
                 "AL JUEGO."
            % ("las secciones de descanso no muestran misiones" if con_secciones else
               "no sale nada, camina" if descanso else "sigue bailando, con SPACE",
               "\n".join(hechas + sin)))

    def generar(self):
        """Genera desde acá, con este compás y estos tramos quitados."""
        if self.original:
            messagebox.showwarning(
                "Cancion original",
                "Esta cancion esta protegida (no la creo el Estudio).\n\nSi la hiciste vos, clic derecho en la lista > Permitir editarla.")
            return
        if self.padre.trabajando:
            return
        self.parar()
        solo = None if self.v_ambas.get() else self.fila["ID"]
        self.padre.generar(inicio=self.inicio, mudos=self.tramos_mudos(),
                           solo_fila=solo, repetir=self.tramos_repes())
        self.lbl_gen.config(
            text="Generado con el compás %d (arranque %.4f s), %d tramos quitados y "
                 "%d con repeticiones, aplicados a %s.\nEl detalle está en la "
                 "ventana de atrás. Todavía NO está en el juego: falta ENVIAR AL "
                 "JUEGO."
                 % (self.cual + 1, self.inicio, len(self.quitados), len(self.repes),
                    "las dos versiones" if solo is None else
                    "la fila %s nada más" % solo))

    # ------------------------------------------------------------- el mapa
    def _rehacer_mapa(self):
        # las repeticiones se guardan por SEGUNDOS antes de rehacer: si un
        # descanso o un arranque nuevo corre las misiones, el numero de mision
        # ya no apunta al mismo lugar (antes quedaban una mision corridas)
        if getattr(self, "misiones", None) and self.repes:
            self._repes_t = [(ms["t"], ms["t"] + ms["largo"]) for ms in self.misiones
                             if ms["n"] - 1 in self.repes]
        per = 60.0 / self.bpm
        largos = [int(float(v)) for v in str(self.listas["Length"]).split(",")
                  if v.strip()]
        m1 = [v for v in str(self.listas["MissionID1"]).split(",") if v.strip()]
        m2 = [v for v in str(self.listas["MissionID2"]).split(",") if v.strip()]
        self.misiones, t = [], float(self.listas.get("StartDelayTime") or self.inicio)
        for i, largo in enumerate(largos):
            # las dos tandas (N.tandas_de): flechas de las dos, y un SPACE por
            # cada casillero vacio. Antes "space" sumaba el MissionID2 como si
            # fuera el SPACE (2/10/2026: es la segunda tanda)
            cas = N.tandas_de(m1, m2, i)
            fl = sum(x for _k, x in cas)
            sp = sum(1 for _k, x in cas if x == 0)
            self.misiones.append(dict(n=i + 1, t=t, ventana=4 * per,
                                      flechas=fl, space=sp, largo_t=largo,
                                      largo=largo * per, tanda2=len(cas) > 4))
            t += largo * per
        self.ventana = 4 * per
        if getattr(self, "_repes_t", None) is not None:
            self.repes = set(ms["n"] - 1 for ms in self.misiones
                             if N._pisa(ms["t"], ms["ventana"], self._repes_t))
        # LOS GRUPOS: una mision larga puede venir partida en piezas de 8 a 16
        # para que el personaje no camine (nucleo.partir_largas). En el mapa se
        # muestra y se edita como UNA frase.
        self.grupos = []
        for g in N.agrupar_largos(largos):
            ms0 = self.misiones[g[0]]
            tot = sum(largos[i] for i in g)
            self.grupos.append(dict(t=ms0["t"], largo_t=tot, largo=tot * per, idx=g))
            for i in g:
                self.misiones[i]["grupo"] = len(self.grupos) - 1
        # donde arranca una frase nueva: lo que sigue a un grupo que no mide 16
        self.frases = [self.grupos[k + 1]["t"] for k in range(len(self.grupos) - 1)
                       if self.grupos[k]["largo_t"] != 16]
        largas = sum(1 for g in self.grupos if g["largo_t"] != 16)
        # CUANTO CAMINA: el baile dura 16 tiempos; lo que pasa de 16 en una
        # mision, el personaje lo camina (6.3.28)
        self.camina = [(ms, (ms["largo_t"] - 16) * per) for ms in self.misiones
                       if ms["largo_t"] > 16]
        if hasattr(self, "lbl_cortes"):
            if self.camina:
                tot = sum(x for _m, x in self.camina)
                self.lbl_cortes.config(
                    foreground="#f2b54b",
                    text="El personaje CAMINA %.0f s en total (%s). Si preferís que "
                         "siga bailando, elegí 'sigue bailando', devolvé esos tramos, "
                         "o en la lista: clic derecho > 'Arreglar el baile'."
                         % (tot, ", ".join("misión %d: %.0f s" % (m["n"], x)
                                           for m, x in self.camina[:5])))
            elif self.quitados:
                self.lbl_cortes.config(
                    foreground="#9ba1b5",
                    text="Lo quitado sale con SPACE: el personaje sigue bailando.")
            else:
                self.lbl_cortes.config(foreground="#9ba1b5",
                                       text="Sin cortes: el personaje baila toda la "
                                            "canción.")
        if hasattr(self, "lbl_frases"):
            if self.original:
                que = "el chart de Softnyx"
            elif self.padre.v_frases.get() and self.padre.ultimas_frases is not None:
                que = "marcadas a mano"
            elif self.padre.v_frases.get():
                que = "elegidas por la música"
            else:
                que = "apagadas: todas de 16"
            self.lbl_frases.config(text="%d frases corridas (%s)" % (largas, que))
        self._texto_cabecera()
        self._texto_recorte()
        self._dibujar()
        self._anotar()
        self.refrescar_editor_misiones()

    def _texto_cabecera(self):
        per = 60.0 / self.bpm
        solas = sum(1 for x in self.misiones
                    if not x["flechas"] and not self._quitada(x))
        partes = []
        if solas:
            partes.append("%d calladas" % solas)
        if self.quitados:
            partes.append("%d tramos quitados (%s)" % (
                len(self.quitados), "en descanso" if self.padre.v_descanso.get()
                else "con SPACE"))
        if self.original:
            estado = "así está en el juego (vino con el juego)"
        elif getattr(self, "guardado", False) and self.fila["ID"] in self.padre.sucias:
            # lo que hay en memoria, todavia sin enviar (una copia recien hecha,
            # un GENERAR, un "Arreglar el baile"...)
            estado = "ASÍ VA A QUEDAR: falta ENVIAR AL JUEGO"
        elif getattr(self, "guardado", False):
            estado = "ASÍ ESTÁ EN EL JUEGO"
        else:
            estado = "VISTA PREVIA: todavía no está en el juego (GENERAR y ENVIAR)"
        self.lbl_cab.config(
            text="%s  |  %.0f BPM  |  arranque %.4f s  |  %d misiones%s  |  dura %s  "
                 "|  la ventana para tipear son %.2f s de cada %.1f s"
                 % (estado, self.bpm, self.inicio, len(self.misiones),
                    ("  (%s)" % ", ".join(partes)) if partes else "",
                    self._reloj(self.dur), self.ventana, 16 * per))

    def _x(self, t):
        v0, v1 = getattr(self, "v0", 0.0), getattr(self, "v1", self.dur)
        return 8 + (self.ANCHO - 16) * (min(max(t, 0.0), self.dur) - v0) / max(
            1e-6, v1 - v0)

    def _reloj(self, t):
        return "%d:%02d" % (int(t) // 60, int(t) % 60)

    def _reloj_fino(self, t):
        return "%d:%05.2f" % (int(t) // 60, t - 60 * (int(t) // 60))

    # ------------------------------------------------------------ el zoom
    ZOOM_GUIAS = 40.0          # con menos de esto a la vista: onda y guias

    def _con_zoom(self):
        return (self.v1 - self.v0) <= self.ZOOM_GUIAS

    def _seg_por_px(self):
        return (self.v1 - self.v0) / float(self.ANCHO - 16)

    def zoom(self, factor, centro=None):
        span = self.v1 - self.v0
        if centro is None:
            centro = (self.v0 + self.v1) / 2.0
        nuevo = max(2.0, min(self.dur, span * factor))
        f = (centro - self.v0) / span if span else 0.5
        self.v0 = max(0.0, min(self.dur - nuevo, centro - f * nuevo))
        self.v1 = self.v0 + nuevo
        if self._con_zoom() and self.pcm is None:
            self._pedir_pcm()
        self._dibujar()

    def ver_toda(self):
        self.v0, self.v1 = 0.0, self.dur
        self._dibujar()

    def _correr(self, fraccion):
        span = self.v1 - self.v0
        self.v0 = max(0.0, min(self.dur - span, self.v0 + fraccion * span))
        self.v1 = self.v0 + span
        self._dibujar()

    def _rueda(self, e):
        adentro = -1 if e.delta > 0 else 1
        if e.state & 0x0004:                       # Ctrl: zoom donde esta el mouse
            self.zoom(0.6 if adentro < 0 else 1.6, centro=self._t_de_x(e.x))
        elif self.v1 - self.v0 < self.dur - 0.01:  # sin Ctrl: moverse
            self._correr(0.15 * adentro)

    def _pcm_cargado(self):
        """El audio de la cancion (se usa en un hilo)."""
        if self.pcm is None:
            import analizar_bpm as ab
            x = ab.pcm(str(self.rej["ogg"]))
            n = len(x) // 128
            bl = x[:n * 128].reshape(n, 128)
            self.pcm = (x, ab.SR, bl.min(axis=1), bl.max(axis=1))
        return self.pcm[0], self.pcm[1]

    def _pedir_pcm(self):
        if self.padre.trabajando or not self.rej.get("ogg"):
            return
        self.padre._en_hilo("Cargando la onda del audio...", self._pcm_cargado,
                            lambda _r: self._dibujar())

    def _dibujar_onda(self, a, b):
        """La onda del audio entre a y b (px de alto), min/max por pixel."""
        import numpy as np
        _x, sr, bmin, bmax = self.pcm
        c = self.lienzo
        W = self.ANCHO - 16
        fps = sr / 128.0
        i0 = int(self.v0 * fps)
        i1 = max(i0 + 1, int(self.v1 * fps))
        cols = np.clip(np.linspace(i0, i1, W + 1).astype(int), 0, len(bmin) - 1)
        if not hasattr(self, "_pico"):
            self._pico = float(max(1e-6, np.percentile(np.abs(bmax), 99.5)))
        mid, alto = (a + b) / 2.0, (b - a) / 2.0
        for px in range(0, W, 1):
            i, j = cols[px], max(cols[px] + 1, cols[px + 1])
            lo = float(bmin[i:j].min()) / self._pico
            hi = float(bmax[i:j].max()) / self._pico
            c.create_line(8 + px, mid - min(1.0, hi) * alto, 8 + px,
                          mid - max(-1.0, lo) * alto + 1, fill="#9db4d3")

    def _dibujar_guias(self):
        """Una guia por cada tiempo: fuerte donde arranca una mision (el palito),
        media cada 4 tiempos, fina el resto. Antes del arranque, mas clarita."""
        c = self.lienzo
        per = 60.0 / self.bpm
        span = self.v1 - self.v0
        finas = span / per <= 260
        y0, y1 = self.Y_GRAVES[0], self.Y_MISION[1]

        def linea(t, col, w=1, desde=y0):
            if self.v0 <= t <= self.v1:
                c.create_line(self._x(t), desde, self._x(t), y1, fill=col, width=w)
        # antes del arranque
        k = 1
        while self.inicio - k * per >= max(0.0, self.v0 - per):
            if finas or k % 4 == 0:
                linea(self.inicio - k * per, "#262a33" if k % 4 else "#363c4a")
            k += 1
        for ms in self.misiones:
            if ms["t"] > self.v1 or ms["t"] + ms["largo"] < self.v0:
                continue
            for j in range(1, ms["largo_t"]):
                if finas or j % 4 == 0:
                    linea(ms["t"] + j * per, "#262a33" if j % 4 else "#3d4452")
            linea(ms["t"], "#2f5fa8", 2)
            if span < 12 and self.v0 <= ms["t"] <= self.v1:
                c.create_text(self._x(ms["t"]) + 3, y0, anchor="nw", fill="#2f5fa8",
                              font=("Segoe UI", 7, "bold"), text="M%d" % ms["n"])
        # despues de la ultima
        if self.misiones:
            fin = self.misiones[-1]["t"] + self.misiones[-1]["largo"]
            k = 0
            while fin + k * per <= self.v1:
                if finas or k % 4 == 0:
                    linea(fin + k * per, "#262a33" if k % 4 else "#363c4a")
                k += 1

    def _dibujar(self):
        c = self.lienzo
        c.delete("all")
        a, b = self.Y_GRAVES
        graves = self.rej.get("graves") or []
        zoom = self._con_zoom()
        if zoom and self.pcm is not None:
            self._dibujar_onda(a, b)
            graves = []
        if zoom:
            self._dibujar_guias()
        if graves:
            pts = []
            for i, v in enumerate(graves):
                pts += [self._x(i), b - (b - a) * min(100.0, v) / 100.0]
            pts = [8, b] + pts + [self._x(len(graves)), b]
            c.create_polygon(pts, fill="#343b4a", outline="#56607a")
        c.create_text(10, a - 2, text=("la onda del audio" if zoom and self.pcm
                                       is not None else "graves de la cancion"),
                      anchor="nw", fill="#9aa5b1", font=("Segoe UI", 7))

        ya, yb = self.Y_MISION
        # los descansos: una franja gris rayada donde no va a salir nada
        for seccion in self.secciones_del_mapa():
            es_descanso = seccion["tipo"] == "descanso"
            color = "#9aa3ad" if es_descanso else "#c98bff"
            c.create_rectangle(self._x(seccion["desde"]), ya + 2,
                               self._x(seccion["hasta"]), yb - 2,
                               fill=color, outline=color, stipple="gray25")
        for a, b in self.quitados:
            c.create_rectangle(self._x(a), ya + 6, self._x(b), yb - 6,
                               fill="#9aa3ad", outline="#6b7785", stipple="gray25")
        for ms in self.misiones:
            x1, x2 = self._x(ms["t"]), self._x(ms["t"] + ms["ventana"])
            if x2 - x1 < 2:
                x2 = x1 + 2
            if self._quitada(ms):
                col, bor = "#05060a", "#5c6170"          # quitada a mano: oscura
            elif self._marca_de(ms) == "manual":
                col, bor = "#b179e3", "#e1baff"
            elif self._marca_de(ms) == "spaces":
                col, bor = "#2bb3a3", "#17756b"          # solo SPACE: verde agua
            elif self._marca_de(ms) == "invertir":
                col, bor = "#e05aa8", "#9c2f6f"          # invertida: rosa
            elif self._marca_de(ms) == "suave":
                col, bor = "#9ccc3c", "#5f8a17"          # suave: verde claro
            elif ms["n"] - 1 in self.repes:
                col, bor = "#f2b705", "#a67c00"          # repeticiones: amarilla
            elif ms["flechas"] == 0:
                col, bor = "#3a3f4b", "#5c6170"
            else:
                fuerte = min(1.0, ms["flechas"] / 12.0)
                col = "#%02x%02x%02x" % (int(150 - 60 * fuerte),
                                         int(190 - 60 * fuerte), 235)
                bor = "#4a7ab5"
            c.create_rectangle(x1, ya, x2, yb, fill=col, outline=bor)
            if ms.get("tanda2") and not self._quitada(ms):
                # la SEGUNDA TANDA (MissionID2): sus 4 casilleros vienen pegados a
                # la primera; mas finita y punteada, del mismo color
                x3 = max(x2 + 2, self._x(ms["t"] + 2 * ms["ventana"]))
                c.create_rectangle(x2, ya + 5, x3, yb - 5, fill=col, outline=bor,
                                   stipple="gray50")
            if ms["n"] % 5 == 1 or len(self.misiones) < 22 or zoom:
                c.create_text(x1, yb + 2, text=str(ms["n"]), anchor="nw",
                              fill="#6b7785", font=("Segoe UI", 7))
        c.create_text(10, ya - 10, text="misiones (la ventana donde caen las flechas; "
                                       "punteada = segunda tanda)",
                      anchor="nw", fill="#4a7ab5", font=("Segoe UI", 7))
        # las frases: una linea violeta donde arranca la mision que sigue a
        # una larga, y la cola de la larga marcada abajo del bloque
        for g in getattr(self, "grupos", []):
            if g["largo_t"] != 16:
                x1 = self._x(g["t"] + min(16, g["largo_t"]) * 60.0 / self.bpm)
                x2 = self._x(g["t"] + g["largo"])
                c.create_line(x1, yb - 3, x2, yb - 3, fill="#7a3fb0", width=3)
        for tf in self.frases:
            if self.v0 <= tf <= self.v1:
                x = self._x(tf)
                c.create_line(x, self.Y_GRAVES[0], x, yb, fill="#7a3fb0", dash=(4, 2))
        for tr in getattr(self.padre, "ultimos_ritmos", ()):
            if self.v0 <= tr <= self.v1:
                x = self._x(tr)
                c.create_line(x, 4, x, yb, fill="#12a150", width=3)
                c.create_text(x + 4, 3, anchor="nw", fill="#0c7a3c",
                              font=("Segoe UI", 7, "bold"), text="el ritmo sigue")
        # (la leyenda de colores esta abajo del mapa, fuera del dibujo)
        rc = self._recorte() if hasattr(self, "padre") else None
        if rc:
            for a, b in ((0.0, rc["ini"]), (rc["fin"], self.dur)):
                if b - a > 0.05:
                    c.create_rectangle(self._x(a), 8, self._x(b), self.Y_REGLA,
                                       fill="#e04040", outline="#a02020", stipple="gray25")
        if self.repes:
            c.create_text(self.ANCHO - 10, ya - 10, anchor="ne", fill="#a67c00",
                          font=("Segoe UI", 7),
                          text="amarillo = repeticiones pedidas (%d)" % len(self.repes))

        span = self.v1 - self.v0
        paso = next(p for p in (0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120)
                    if span / p <= 16)
        t = math.ceil(self.v0 / paso) * paso
        while t <= self.v1 + 1e-6:
            x = self._x(t)
            c.create_line(x, self.Y_REGLA, x, self.Y_REGLA + 6, fill="#aab4c0")
            c.create_text(x, self.Y_REGLA + 8, anchor="n", fill="#77828f",
                          font=("Segoe UI", 7),
                          text=self._reloj(t) if paso >= 1 else self._reloj_fino(t))
            t += paso
        if span < self.dur - 0.01:
            # por donde anda: una barrita abajo con la parte que se ve
            W = self.ANCHO - 16
            c.create_rectangle(8, self.ALTO - 5, self.ANCHO - 8, self.ALTO - 2,
                               fill="#1f232b", outline="")
            c.create_rectangle(8 + W * self.v0 / self.dur, self.ALTO - 5,
                               8 + W * self.v1 / self.dur, self.ALTO - 2,
                               fill="#6f93d8", outline="")
        fin = self.rej.get("fin_beat")
        if fin and fin < self.dur and self.v0 <= fin <= self.v1:
            c.create_line(self._x(fin), 8, self._x(fin), self.Y_REGLA,
                          fill="#c08a00", dash=(3, 2))
            c.create_text(self._x(fin) - 3, 8, text="aca se termina el ritmo",
                          anchor="ne", fill="#c08a00", font=("Segoe UI", 7))
        self.cabeza = c.create_line(8, 6, 8, self.Y_REGLA, fill="#d02020", width=2,
                                    state="hidden")

    # ------------------------------------------------------------ acciones
    def _t_de_x(self, x):
        v0, v1 = getattr(self, "v0", 0.0), getattr(self, "v1", self.dur)
        return v0 + (v1 - v0) * max(0.0, min(1.0, (x - 8) / float(self.ANCHO - 16)))

    def encima(self, e):
        if self.sonando:
            return
        t = self._t_de_x(e.x)
        reloj = self._reloj_fino(t) if self._con_zoom() else self._reloj(t)
        if any(s["tipo"] == "descanso" and s["desde"] <= t < s["hasta"]
               for s in self.secciones_del_mapa()):
            self.info.config(text="%s — DESCANSO SIN MISIONES. El audio continúa; no "
                                  "salen flechas ni SPACE en este tramo." % reloj)
            return
        cual = [ms for ms in self.misiones if ms["t"] <= t < ms["t"] + ms["ventana"]]
        if cual:
            ms = cual[0]
            txt = ("%s  -  mision %d de %d: %d flechas y %d SPACE%s"
                   % (reloj, ms["n"], len(self.misiones),
                      ms["flechas"], ms["space"],
                      " (en 2 tandas)" if ms.get("tanda2") else ""))
            if ms["flechas"] == 0:
                txt += "   (callada: aca no entra ninguna)"
            if self._marca_de(ms) == "spaces":
                txt += "   |  SOLO SPACE"
            elif self._marca_de(ms) == "invertir":
                txt += "   |  INVERTIDA (flechas <-> SPACE)"
            elif self._marca_de(ms) == "suave":
                txt += "   |  SUAVE (1-2 flechas donde entra la voz)"
            if ms["largo_t"] > 16:
                txt += ("   |  acá el personaje CAMINA %.0f s (descanso)"
                        % ((ms["largo_t"] - 16) * 60.0 / self.bpm))
            g = self.grupos[ms.get("grupo", 0)] if getattr(self, "grupos", None) else None
            if g and g["largo_t"] != 16:
                partes = " + ".join(str(self.misiones[i]["largo_t"]) for i in g["idx"])
                txt += ("   |  frase de %d tiempos (%s)%s" % (
                    g["largo_t"], partes,
                    "" if len(g["idx"]) > 1 else ": acá el personaje camina al final"))
        else:
            sig = [ms for ms in self.misiones if ms["t"] > t]
            txt = "%s  -  entre misiones (el personaje baila)" % reloj
            if sig:
                txt += ".  La proxima empieza en %s" % self._reloj(sig[0]["t"])
        self.info.config(text=txt)

    def clic(self, e):
        """El clic en el mapa hace lo que diga la herramienta elegida arriba."""
        h = self.v_herr.get()
        if self.esperando_voz or h == "voz":
            self.esperando_voz = False
            self.v_herr.set("escuchar")
            self._cambio_herr()
            self.empezar_aca(e)
        elif h == "alargar":
            self.alargar(e)
        elif h == "frase":
            self.frase_aca(e)
        elif h == "ritmo":
            self.ritmo_aca(e)
        elif h in ("cortefin", "corteini"):
            self._clic_corte(h[5:], e)
        elif h == "descanso":
            self.descanso_seccion(e)
        elif h == "repes":
            self.repetir(e)
        elif h == "spaces":
            self.marcar_tramo(e, "ultimos_spaces", "solo SPACE")
        elif h == "invertir":
            self.marcar_tramo(e, "ultimos_inv", "invertida")
        elif h == "suave":
            self.marcar_tramo(e, "ultimos_suave", "suave")
        else:
            self.sonar(self._t_de_x(e.x))

    def probar_cuatro(self):
        """Los cuatro compases seguidos, anunciados por pitidos.

        Esto no elige por vos: no se puede. El 22/9/2026 se probaron diez
        formas de decidirlo midiendo contra los 117 charts oficiales y ninguna
        le gano a la que ya estaba; la mejor mezcla era sobreajuste (56% al
        probarla en canciones que no se usaron para elegirla). Lo que si se
        puede es que escuchar los cuatro cueste UNA vez en vez de cuatro.
        """
        if self.padre.trabajando or self.original:
            return
        self.parar()
        inicios = [self._opcion(k) for k in range(4)]
        modosp = self.padre.modo_space()
        # sin los tramos quitados: los cuatro tienen que sonar igual salvo por
        # la alineacion, que es lo unico que se esta comparando
        mudos = ()
        frases = self.padre.frases_de()

        def trabajo():
            return N.probar_los_cuatro(self.fila, self.rej, self.estrellas,
                                       inicios, segundos=12.0, bpm=self.bpm,
                                       por_musica=self.por_musica, mudos=mudos,
                                       space=modosp, frases=frases,
                **self.padre.extras(self.fila))

        def despues(r):
            ruta, inf = r
            N.reproducir(ruta)
            self.lbl_pista.config(
                text="Sonando los CUATRO seguidos, %.0f s cada uno. Un pitido = "
                     "compas 1, dos = compas 2, y asi. El bueno es aquel donde el "
                     "golpe seco de cada mision cae con la frase de la cancion, no "
                     "cuando el cantante esta en el medio de una palabra. Cuando lo "
                     "tengas, toca ese boton de arriba y GENERAR EL CHART."
                     % inf["segundos"])
        self.padre._en_hilo("Preparando los cuatro...", trabajo, despues)

    def sonar(self, desde, hasta=None):
        if self.padre.trabajando:
            return
        self.parar()
        segundos = max(2.0, (hasta if hasta is not None else self.dur) - desde)
        mudos = self.tramos_mudos()
        modosp = self.padre.modo_space()
        frases = self.padre.frases_de()
        descanso = bool(self.padre.v_descanso.get())

        guardado = self.original or getattr(self, "guardado", False)

        def trabajo():
            # lo que suena es lo que se ve: si el mapa muestra lo GUARDADO, suena
            # lo guardado, no una regeneracion
            if guardado:
                return N.previo_de_fila(self.fila, self.rej, segundos=segundos,
                                        desde=desde)
            return N.previo(self.fila, self.rej, self.estrellas, self.inicio,
                            segundos=segundos, bpm=self.bpm, desde=desde,
                            por_musica=self.por_musica, mudos=mudos,
                            space=modosp, frases=frases, descanso=descanso,
                **self.padre.extras(self.fila))

        def despues(r):
            ruta, _inf = r
            N.reproducir(ruta)
            self.desde, self.t0 = desde, time.time()
            self.sonando = True
            # si lo que suena arranca a la vista, la vista lo acompaña
            if not (self.v0 <= desde <= self.v1) and self.v1 - self.v0 < self.dur - 0.01:
                span = self.v1 - self.v0
                self.v0 = max(0.0, min(self.dur - span, desde - 0.1 * span))
                self.v1 = self.v0 + span
                self._dibujar()
            self._cabeza_vista = True
            self.lienzo.itemconfig(self.cabeza, state="normal")
            self._mover()
        self.padre._en_hilo("Preparando %s de audio..." % self._reloj(segundos),
                            trabajo, despues)

    def _mover(self):
        if not self.sonando:
            return
        t = self.desde + (time.time() - self.t0)
        if t >= self.dur:
            self.parar()
            return
        span = self.v1 - self.v0
        dentro = self.v0 <= t <= self.v1
        if (span < self.dur - 0.01 and not dentro and t > self.v1
                and getattr(self, "_cabeza_vista", False)):
            # con zoom, la vista acompaña a lo que suena, pero solo si se lo
            # estaba mirando: si se hizo zoom en otra parte, no salta
            self.v0 = max(0.0, min(self.dur - span, t - 0.1 * span))
            self.v1 = self.v0 + span
            self._dibujar()
            self.lienzo.itemconfig(self.cabeza, state="normal")
            dentro = True
        self._cabeza_vista = dentro
        x = self._x(t)
        self.lienzo.coords(self.cabeza, x, 6, x, self.Y_REGLA)
        cual = [ms for ms in self.misiones if ms["t"] <= t < ms["t"] + ms["ventana"]]
        if cual:
            ms = cual[0]
            self.info.config(text="%s  ->  MISION %d de %d: %d flechas, %d SPACE%s%s"
                                  % (self._reloj(t), ms["n"], len(self.misiones),
                                     ms["flechas"], ms["space"],
                                     " (en 2 tandas)" if ms.get("tanda2") else "",
                                     "   (callada)" if not ms["flechas"] else ""))
        else:
            self.info.config(text="%s  ->  bailando (entre misiones)"
                                  % self._reloj(t))
        self.after(80, self._mover)

    def parar(self):
        self.sonando = False
        N.parar_sonido()
        try:
            self.lienzo.itemconfig(self.cabeza, state="hidden")
        except Exception:
            pass

    def cerrar(self):
        if self.padre.trabajando:
            return
        self.parar()
        self.destroy()


if __name__ == "__main__":
    Estudio().mainloop()
