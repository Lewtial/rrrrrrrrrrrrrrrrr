#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jugar.py - PROBAR AL INSTANTE: la cancion se juega ACA, sin abrir el juego (7/10/2026).

Pedido de la usuaria: "forzar la cancion para probarla no es entrar en el sv, sino que de
frente salga la cancion, porque si no es demasiado lenta para probarla en vivo". El boton
"En el juego real..." (probar.py) sigue estando, pero tarda un minuto; esto arranca en un
segundo.

QUE ES: la barra dorada de 4 casilleros como en el juego, con las flechas que salen de la
tabla de patrones del juego (`nucleo.flechas_del_chart`, la misma que usa Simular), una
rayita que barre los casilleros al compas, y el teclado: flechas + ESPACIO. Cada casillero
se aprieta en SU tiempo (todas sus flechas, en cualquier orden, y el SPACE si lo tiene).

QUE NO ES: el juez del juego. Las ventanas de PERFECT/GREAT/COOL/BAD son nuestras (abajo, en
JUICIOS); sirven para sentir si el chart se puede jugar y si cae en la musica, no para
calcar el puntaje del servidor.

EL RELOJ es la posicion REAL del audio (MCI de Windows: `status ... position`), no
time.time(): si la maquina se traba un momento, las flechas no se adelantan a la musica.
Con MCI tambien suenan las teclas encima de la musica (winsound no mezcla).
"""
import ctypes
import threading
import time
import tkinter as tk
from tkinter import ttk

import nucleo as N
import tema as T

# (nombre, desfase maximo en segundos, puntos, peso para la precision, color)
JUICIOS = [("PERFECT", 0.045, 1000, 1.0, "#7fe9ff"),
           ("GREAT", 0.085, 700, 0.8, T.VERDE),
           ("COOL", 0.130, 400, 0.5, T.AMBAR),
           ("BAD", 9.9, 100, 0.2, "#ff9f5a")]
MISS_COLOR = T.ROJO
TECLAS = {"Left": "left", "Right": "right", "Up": "up", "Down": "down", "space": "space",
          "KP_Left": "left", "KP_Right": "right", "KP_Up": "up", "KP_Down": "down"}


# ------------------------------------------------------------------- sonido con MCI
class Mci:
    """Lo minimo de winmm: abrir/tocar/posicion. Cada alias es un sonido independiente,
    asi la musica y los golpes de tecla suenan a la vez."""

    def __init__(self):
        self.ok = True
        try:
            self._f = ctypes.windll.winmm.mciSendStringW
        except Exception:
            self.ok = False

    def __call__(self, cmd):
        if not self.ok:
            return None
        buf = ctypes.create_unicode_buffer(256)
        err = self._f(cmd, buf, 255, 0)
        return None if err else buf.value

    def abrir(self, alias, ruta):
        self("close %s" % alias)
        return self('open "%s" type waveaudio alias %s' % (ruta, alias)) is not None


class VentanaJugar(tk.Toplevel):
    ANCHO, ALTO = 900, 380
    CELDA, SEP = 196, 6
    FLECHA, ANCHO_SPACE = 45, 62

    def __init__(self, padre, fila, listas, bpm, inicio, estrellas):
        tk.Toplevel.__init__(self, padre)
        self.padre, self.fila, self.listas = padre, fila, listas
        self.bpm, self.inicio, self.estrellas = float(bpm), float(inicio), estrellas
        self.inicio = float(listas.get("StartDelayTime") or inicio)
        self.per = 60.0 / self.bpm
        self.rej = padre.rej
        self.dur = float(self.rej.get("dur") or 1)
        self.mci = Mci()
        self.jugando = self.pausa = self.usa_mci = False
        self._token = None
        self._ancla = (0.0, 0.0)
        self._ultima_pos = None
        self._apretadas = set()
        self._wav = None
        self.title("Probar: %s" % fila["Title"])
        self.configure(background=T.FONDO)
        self.transient(padre)

        golpes = N.flechas_del_chart(listas, inicio, self.bpm, semilla=int(fila["ID"]))
        self.grupos = [dict(g, faltan=list(g["flechas"]) + (["space"] if g["space"] else []))
                       for g in golpes]
        largos = [int(float(v)) for v in str(listas["Length"]).split(",") if v.strip()]
        self.misiones, t = [], self.inicio
        for largo in largos:
            self.misiones.append(t)
            t += largo * self.per
        # las tandas (4 casilleros cada una) en orden; cuando se deja de verlas
        tandas = {}
        for g in self.grupos:
            tandas.setdefault((g["mision"], g["tanda"]), []).append(g)
        self.tandas = []
        for (m, tn), gs in sorted(tandas.items()):
            gs.sort(key=lambda g: g["tiempo"])
            self.tandas.append(dict(mision=m, tanda=tn, t0=gs[0]["t"], grupos=gs))
        for i, td in enumerate(self.tandas):
            fin = td["t0"] + 3.5 * self.per
            sig = self.tandas[i + 1]["t0"] if i + 1 < len(self.tandas) else 1e9
            if sig - 2.5 * self.per > fin + 1.5 * self.per:
                fin += 1.5 * self.per        # que se vea un ratito como te fue
            td["fin"] = fin

        self.imgs = {}
        for d in ("left", "right", "up", "down"):
            self._img("flecha_" + d, N.SACADO / ("flecha_%s.png" % d))
        self._img("space", N.SACADO / "space.png")
        self._armar()
        self._reiniciar_cuenta()
        self._dibujar(0.0)
        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.after(150, self.jugar)

    def _img(self, clave, ruta):
        try:
            self.imgs[clave] = tk.PhotoImage(file=str(ruta))
        except Exception:
            self.imgs[clave] = None

    # ------------------------------------------------------------------ ventana
    def _armar(self):
        m = ttk.Frame(self, padding=(12, 10))
        m.pack(fill="both", expand=True)
        cab = ttk.Frame(m)
        cab.pack(fill="x")
        ttk.Label(cab, text=self.fila["Title"], style="Titulo.TLabel").pack(side="left")
        ttk.Label(cab, style="Sub.TLabel",
                  text="   %.0f BPM  |  %d ★  |  %d misiones"
                       % (self.bpm, self.estrellas, len(self.misiones))).pack(side="left")

        self.lienzo = tk.Canvas(m, width=self.ANCHO, height=self.ALTO, background="#0f1116",
                                highlightthickness=0, takefocus=1)
        self.lienzo.pack(pady=(8, 8))
        for k in TECLAS:
            self.lienzo.bind("<KeyPress-%s>" % k, self._tecla)
            self.lienzo.bind("<KeyRelease-%s>" % k, self._soltar)
        self.lienzo.bind("<Escape>", lambda _e: self.pausar())
        self.lienzo.bind("<Return>", lambda _e: self.jugar())
        self.lienzo.bind("<Button-1>", lambda _e: self.lienzo.focus_set())

        f = ttk.Frame(m)
        f.pack(fill="x")
        ttk.Button(f, text="▶  Jugar de nuevo  (Enter)", style="Probar.TButton",
                   takefocus=0, command=self.jugar).pack(side="left")
        ttk.Button(f, text="Pausa  (Esc)", takefocus=0,
                   command=self.pausar).pack(side="left", padx=6)
        ttk.Label(f, text="  desde la misión").pack(side="left")
        self.v_desde = tk.StringVar(value="1")
        ttk.Spinbox(f, from_=1, to=max(1, len(self.misiones)), width=4,
                    textvariable=self.v_desde, takefocus=0).pack(side="left", padx=(4, 10))
        self.v_tics = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="tics de guía", variable=self.v_tics,
                        takefocus=0).pack(side="left")
        self.v_sonido = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="sonido al apretar", variable=self.v_sonido,
                        takefocus=0).pack(side="left", padx=(8, 0))
        ttk.Label(f, text="   ajuste ms").pack(side="left")
        self.v_ajuste = tk.StringVar(value="0")
        ttk.Spinbox(f, from_=-300, to=300, increment=10, width=5,
                    textvariable=self.v_ajuste, takefocus=0).pack(side="left", padx=4)
        ttk.Button(f, text="Cerrar", takefocus=0, command=self.cerrar).pack(side="right")

        self.info = ttk.Label(m, style="Sub.TLabel", justify="left", wraplength=self.ANCHO,
                              text="Flechas del teclado + ESPACIO. Cada casillero se aprieta "
                                   "cuando la raya pasa por él (todas sus flechas, en "
                                   "cualquier orden). Esc = pausa, Enter = de nuevo. Si "
                                   "sentís que todo llega tarde o temprano, mirá el "
                                   "'vas X ms' y corregilo con 'ajuste ms'.")
        self.info.pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------- partida
    def _reiniciar_cuenta(self):
        self.puntos = self.combo = self.combo_max = 0
        self.cuenta = {n: 0 for n, *_ in JUICIOS}
        self.cuenta["MISS"] = 0
        self.desfases = []
        self.ultimo = None              # (texto, color, cuando)
        for g in self.grupos:
            g["faltan"] = list(g["flechas"]) + (["space"] if g["space"] else [])
            g["res"] = None
            g["off"] = []

    def jugar(self):
        self.parar()
        try:
            n = max(1, min(len(self.misiones), int(self.v_desde.get())))
        except ValueError:
            n = 1
        t_m = self.misiones[n - 1] if self.misiones else self.inicio
        desde = max(0.0, t_m - max(2.0, 4 * self.per))
        self._reiniciar_cuenta()
        for g in self.grupos:
            if g["t"] < desde + 0.5:
                g["res"] = "-"          # quedo antes del arranque: no cuenta
        self.desde = desde
        tics = bool(self.v_tics.get())
        self._estado("Preparando el audio...")
        self._token = object()
        tok = self._token

        def trabajo():
            try:
                marcas = N.golpes(self.listas, self.inicio, self.bpm) if tics else []
                salida = N.CACHE / "_jugar.wav"
                N.CACHE.mkdir(parents=True, exist_ok=True)
                N.armar_escucha(self.rej["ogg"], marcas, desde, self.dur - desde + 1.0,
                                salida, musica=True, marcar_misiones=False,
                                vol_musica=0.85, vol_tic=0.7, sonidos_juego=True)
                r = salida
            except Exception as e:
                r = e
            caja.append(r)             # tkinter no se toca desde el hilo
        caja = []
        threading.Thread(target=trabajo, daemon=True).start()

        def esperar():
            if tok is not self._token:
                return
            if caja:
                self._arrancar(tok, caja[0])
            else:
                self.after(40, esperar)
        self.after(40, esperar)

    def _arrancar(self, tok, r):
        if tok is not self._token or not self.winfo_exists():
            return
        if isinstance(r, Exception):
            self._estado("No pude preparar el audio: %s" % r)
            return
        self._wav = r
        self.lienzo.focus_force()
        if self.mci.ok and self.mci.abrir("lrmus", r):
            self.mci("set lrmus time format milliseconds")
            for i in range(4):
                self.mci.abrir("lrtec%d" % i, N.SACADO / "tecla.wav")
            for i in range(2):
                self.mci.abrir("lrspc%d" % i, N.SACADO / "space.wav")
            self._tec = self._spc = 0
            self.mci("play lrmus")
            self.usa_mci = True
        else:
            N.reproducir(r)
            self.usa_mci = False
        self._ancla = (time.perf_counter(), 0.0)
        self._ultima_pos = None
        self.jugando, self.pausa = True, False
        self._estado("")
        self._cuadro()

    def reloj(self):
        """Segundos de la cancion (posicion real del audio + el ajuste)."""
        ahora = time.perf_counter()
        if self.usa_mci and not self.pausa:
            p = self.mci("status lrmus position")
            if p and p.isdigit() and p != self._ultima_pos:
                self._ultima_pos = p
                self._ancla = (ahora, int(p) / 1000.0)
        t_a, pos = self._ancla
        dt = 0.0 if self.pausa else ahora - t_a
        try:
            aj = float(self.v_ajuste.get()) / 1000.0
        except ValueError:
            aj = 0.0
        return self.desde + pos + dt - aj

    def _cuadro(self):
        if not self.jugando:
            return
        if self.pausa:
            self.after(50, self._cuadro)
            return
        c = self.reloj()
        vent = self._ventana()
        for g in self.grupos:
            if g["res"] is None and c > g["t"] + vent:
                self._juzgar(g, None, c)
        terminado = c >= self.dur - 0.2
        if self.usa_mci:
            terminado = terminado or self.mci("status lrmus mode") == "stopped"
        if terminado:
            self.jugando = False
            self._dibujar(c, final=True)
            return
        self._dibujar(c)
        self.after(15, self._cuadro)

    def _ventana(self):
        return min(0.22, 0.45 * self.per)

    def _tecla(self, e):
        k = TECLAS.get(e.keysym)
        if k is None or k in self._apretadas:
            return "break"              # autorrepeticion del teclado
        self._apretadas.add(k)
        self._luz = getattr(self, "_luz", {})
        self._luz[k] = time.perf_counter()
        if not self.jugando or self.pausa:
            return "break"
        c = self.reloj()
        if self.v_sonido.get() and self.usa_mci:
            if k == "space":
                self.mci("play lrspc%d from 0" % self._spc)
                self._spc = (self._spc + 1) % 2
            else:
                self.mci("play lrtec%d from 0" % self._tec)
                self._tec = (self._tec + 1) % 4
        vent = self._ventana()
        cerca = [g for g in self.grupos if g["res"] is None and abs(c - g["t"]) <= vent]
        if not cerca:
            return "break"              # apretar en el aire no castiga
        cerca.sort(key=lambda g: g["t"])
        g = next((g for g in cerca if k in g["faltan"]), None)
        if g is None:
            self._juzgar(cerca[0], "ERROR", c)
            return "break"
        g["faltan"].remove(k)
        g["off"].append(c - g["t"])
        if not g["faltan"]:
            self._juzgar(g, "ok", c)
        return "break"

    def _soltar(self, e):
        self._apretadas.discard(TECLAS.get(e.keysym))
        return "break"

    def _juzgar(self, g, como, c):
        if como == "ok":
            peor = max(abs(o) for o in g["off"])
            nombre, _lim, pts, _peso, color = next(j for j in JUICIOS if peor <= j[1])
            self.desfases.extend(g["off"])
            self.combo += 1
            self.combo_max = max(self.combo_max, self.combo)
            n = len(g["flechas"]) + (1 if g["space"] else 0)
            self.puntos += int(pts * n * (1 + min(self.combo, 50) / 100.0))
            g["res"] = nombre
            self.cuenta[nombre] += 1
            self.ultimo = (nombre, color, c)
        else:
            g["res"] = "MISS"
            self.cuenta["MISS"] += 1
            self.combo = 0
            self.ultimo = ("MISS" if como is None else "ERROR", MISS_COLOR, c)

    def precision(self):
        pesos = {n: p for n, _l, _pt, p, _c in JUICIOS}
        pesos["MISS"] = 0.0
        tot = sum(self.cuenta.values())
        if not tot:
            return 100.0
        return 100.0 * sum(pesos[n] * v for n, v in self.cuenta.items()) / tot

    def pausar(self):
        if not self.jugando:
            return
        if self.pausa:
            if self.usa_mci:
                self.mci("resume lrmus")
                self._ultima_pos = None
                p = self.mci("status lrmus position")
                self._ancla = (time.perf_counter(), int(p) / 1000.0 if p and p.isdigit()
                               else self._ancla[1])
            self.pausa = False
            self._estado("")
        else:
            if not self.usa_mci:
                return                  # sin MCI no se puede pausar el audio
            self._ancla = (time.perf_counter(), self.reloj() - self.desde +
                           self._ajuste_s())
            self.mci("pause lrmus")
            self.pausa = True
            self._estado("PAUSA  (Esc para seguir)")

    def _ajuste_s(self):
        try:
            return float(self.v_ajuste.get()) / 1000.0
        except ValueError:
            return 0.0

    def _estado(self, txt):
        self._aviso = txt
        if not self.jugando:
            self._dibujar(getattr(self, "desde", 0.0))

    # -------------------------------------------------------------------- dibujo
    def _dibujar(self, c, final=False):
        cv = self.lienzo
        cv.delete("all")
        W = self.ANCHO
        cx, cy = W // 2, 168
        # arriba: mision, puntos, combo
        mis = sum(1 for t in self.misiones if t <= c + 1e-6)
        cv.create_text(18, 16, anchor="nw", fill=T.SUAVE, font=("Segoe UI", 10, "bold"),
                       text="MISIÓN %d / %d" % (max(1, mis), len(self.misiones)))
        cv.create_text(W - 18, 14, anchor="ne", fill=T.TEXTO,
                       font=("Segoe UI", 16, "bold"), text="%d" % self.puntos)
        cv.create_text(W - 18, 42, anchor="ne", fill=T.SUAVE, font=("Segoe UI", 9),
                       text="precisión %.1f%%" % self.precision())
        if self.combo >= 2:
            cv.create_text(cx, 34, fill=T.ACENTO, font=("Segoe UI", 13, "bold"),
                           text="%d COMBO" % self.combo)
        if self.ultimo and c - self.ultimo[2] < 0.7:
            cv.create_text(cx, 78, fill=self.ultimo[1], font=("Segoe UI", 24, "bold italic"),
                           text=self.ultimo[0])

        vis = next((td for td in self.tandas if c < td["fin"]), None)
        if final:
            self._resumen(cv, cx)
        elif vis is not None and c >= vis["t0"] - 2.5 * self.per:
            self._barra(cv, vis, c, cx, cy)
        else:
            if vis is not None:
                falta = vis["t0"] - c
                cv.create_text(cx, cy - 6, fill=T.SUAVE, font=("Segoe UI", 15),
                               text="bailando...")
                cv.create_text(cx, cy + 26, fill="#6b7385", font=("Segoe UI", 10),
                               text="la próxima barra en %.1f s" % max(0.0, falta))
            elif self.jugando:
                cv.create_text(cx, cy, fill=T.SUAVE, font=("Segoe UI", 15),
                               text="sin más misiones")
        # abajo: las teclas que se estan apretando
        luz = getattr(self, "_luz", {})
        ahora = time.perf_counter()
        for i, (k, txt) in enumerate((("left", "←"), ("down", "↓"), ("up", "↑"),
                                      ("right", "→"), ("space", "SPACE"))):
            x = cx - 190 + i * 76 + (24 if k == "space" else 0)
            on = ahora - luz.get(k, -9) < 0.12
            w = 60 if k == "space" else 26
            cv.create_rectangle(x - w, 292, x + w if k == "space" else x + 26, 326,
                                fill="#3b3f66" if on else "#1a1d24",
                                outline=T.ACENTO if on else "#323744", width=2)
            cv.create_text(x + (0 if k != "space" else 0), 309, fill=T.TEXTO if on else T.SUAVE,
                           font=("Segoe UI", 12 if k != "space" else 10, "bold"), text=txt)
        # la cancion
        p = max(0.0, min(1.0, c / self.dur)) if self.dur else 0
        cv.create_rectangle(18, 352, W - 18, 358, fill="#1a1d24", outline="")
        cv.create_rectangle(18, 352, 18 + (W - 36) * p, 358, fill=T.ACENTO, outline="")
        cv.create_text(18, 366, anchor="nw", fill="#6b7385", font=("Segoe UI", 8),
                       text="%d:%02d / %d:%02d" % (int(c) // 60, int(c) % 60,
                                                    int(self.dur) // 60, int(self.dur) % 60))
        if self.desfases:
            med = 1000.0 * sum(self.desfases) / len(self.desfases)
            cv.create_text(W - 18, 366, anchor="ne", fill="#6b7385", font=("Segoe UI", 8),
                           text="vas %+.0f ms %s" % (med, "(tarde)" if med > 15 else
                                                      "(temprano)" if med < -15 else "(justo)"))
        aviso = getattr(self, "_aviso", "")
        if aviso:
            cv.create_rectangle(cx - 220, cy - 26, cx + 220, cy + 26, fill="#0f1116",
                                outline=T.ACENTO)
            cv.create_text(cx, cy, fill=T.TEXTO, font=("Segoe UI", 12, "bold"), text=aviso)

    def _barra(self, cv, td, c, cx, cy):
        ancho = 4 * self.CELDA + 3 * self.SEP
        x0 = cx - ancho // 2
        cv.create_rectangle(x0 - 26, cy - 40, x0 + ancho + 26, cy + 40, fill="#2a2016",
                            outline="#c9a227", width=3)
        cv.create_oval(x0 - 38, cy - 32, x0 - 10, cy + 32, fill="#e8c65a", outline="#8a6d12")
        cv.create_oval(x0 + ancho + 10, cy - 32, x0 + ancho + 38, cy + 32, fill="#e8c65a",
                       outline="#8a6d12")
        if td["tanda"] == 2:
            cv.create_text(x0 - 26, cy - 54, anchor="w", fill=T.AMBAR,
                           font=("Segoe UI", 9, "bold"), text="2ª TANDA")
        por = {g["tiempo"] - 4 * (td["tanda"] - 1): g for g in td["grupos"]}
        for k in range(1, 5):
            x = x0 + (k - 1) * (self.CELDA + self.SEP)
            g = por.get(k)
            res = g["res"] if g else None
            fondo = "#3a2d1c"
            if res in ("PERFECT", "GREAT", "COOL", "BAD"):
                fondo = "#1d3a2a"
            elif res == "MISS":
                fondo = "#4a1f22"
            cv.create_rectangle(x + 2, cy - 32, x + self.CELDA - 2, cy + 32, fill=fondo,
                                outline="")
            if k < 4:
                xs = x + self.CELDA + self.SEP // 2
                cv.create_line(xs, cy - 32, xs, cy + 32, fill="#6b5a2a")
            if not g:
                continue
            piezas = list(g["flechas"]) + (["space"] if g["space"] else [])
            w = sum(self.ANCHO_SPACE if p == "space" else self.FLECHA for p in piezas)
            xx = x + (self.CELDA - w) // 2
            quedan = list(g["faltan"])
            for p in piezas:
                ancho_p = self.ANCHO_SPACE if p == "space" else self.FLECHA
                if res is None or res == "-":
                    # sin juzgar: se ve la flecha si todavia falta apretarla
                    hecha = p not in quedan if res is None else False
                    if p in quedan:
                        quedan.remove(p)
                else:
                    hecha = True
                xm = xx + ancho_p // 2
                im = self.imgs.get("space" if p == "space" else "flecha_" + p)
                if not hecha:
                    if im is not None:
                        cv.create_image(xm, cy, image=im)
                    else:
                        cv.create_text(xm, cy, fill=T.TEXTO, font=("Segoe UI", 16, "bold"),
                                       text=p)
                else:
                    col = MISS_COLOR if res == "MISS" else T.VERDE
                    cv.create_oval(xm - 9, cy - 9, xm + 9, cy + 9, outline=col, width=2)
                xx += ancho_p
            if res and res != "-":
                col = next((j[4] for j in JUICIOS if j[0] == res), MISS_COLOR)
                cv.create_text(x + self.CELDA // 2, cy + 50, fill=col,
                               font=("Segoe UI", 9, "bold"), text=res)
        # la raya que barre: pasa por el centro del casillero k justo en su tiempo
        pos = (c - td["t0"]) / self.per
        xr = x0 + self.CELDA / 2.0 + pos * (self.CELDA + self.SEP)
        if pos < -0.5:
            # todavia no llega: la raya espera a la izquierda y se cuentan los tiempos
            cv.create_line(x0 - 6, cy - 46, x0 - 6, cy + 46, fill="#8a7a4a", width=3)
            cv.create_text(cx, cy - 58, fill=T.AMBAR, font=("Segoe UI", 16, "bold"),
                           text="%d" % int(-pos + 0.5))
        elif xr <= x0 + ancho + 30:
            cv.create_line(xr, cy - 46, xr, cy + 46, fill="#fff3c4", width=3)
        for k in range(4):           # los 4 tiempos, como un metronomo
            xx = cx - 45 + k * 30
            on = 0 <= pos - k < 1
            cv.create_oval(xx - 6, cy + 66, xx + 6, cy + 78, outline="#4a5361",
                           fill="#e8c65a" if on else "#2a303a")

    def _resumen(self, cv, cx):
        cv.create_rectangle(cx - 260, 100, cx + 260, 270, fill="#1a1d24", outline=T.ACENTO,
                            width=2)
        cv.create_text(cx, 122, fill=T.ACENTO, font=("Segoe UI", 15, "bold"), text="RESULTADO")
        filas = ["%s %d" % (n, self.cuenta[n]) for n, *_ in JUICIOS] + \
                ["MISS %d" % self.cuenta["MISS"]]
        cv.create_text(cx, 158, fill=T.TEXTO, font=("Segoe UI", 11), text="   ".join(filas))
        cv.create_text(cx, 192, fill=T.TEXTO, font=("Segoe UI", 12, "bold"),
                       text="%d puntos  |  precisión %.1f%%  |  combo máx %d"
                            % (self.puntos, self.precision(), self.combo_max))
        cv.create_text(cx, 236, fill=T.SUAVE, font=("Segoe UI", 9),
                       text="Enter = jugar de nuevo")

    # ------------------------------------------------------------------- cerrar
    def parar(self):
        self.jugando = self.pausa = False
        self._token = object()
        if self.mci.ok:
            for a in ["lrmus"] + ["lrtec%d" % i for i in range(4)] + ["lrspc%d" % i
                                                                     for i in range(2)]:
                self.mci("close %s" % a)
        N.parar_sonido()

    def cerrar(self):
        self.parar()
        self.destroy()
