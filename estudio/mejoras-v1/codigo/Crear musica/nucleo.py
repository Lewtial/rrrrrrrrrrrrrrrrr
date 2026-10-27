#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
nucleo.py - toda la logica del Estudio. Sin ventanas: solo cuentas.

Junta en un solo lugar lo que antes estaba repartido en ocho scripts sueltos
(rejilla_vdj, rejilla, analizar_bpm, editar_cancion, chart_softnyx, probar_inicio,
snb_local). La ventana (estudio.py) no calcula nada: llama a esto.

LO QUE ESTA COMPROBADO Y POR QUE (el detalle esta en la carpeta
"INFORMACION CORRECTO PARA CREAR MUSICA EN EL JUEGO"):

  * El arranque sale de la rejilla:   StartDelayTime = fase + n * 4 * (60/BPM)
    La fase se lee de Virtual DJ si la tiene; si no, se mide con los GRAVES
    (40-160 Hz). Con la envolvente de banda ancha se engancha en el contratiempo.
  * MissionID1 son las flechas de los 4 casilleros de la mision. MissionID2 es la
    SEGUNDA TANDA: otros 4 casilleros que llegan apenas se tipea la primera
    ("0" = no hay). Corregido el 2/10/2026: antes decia "el SPACE" y despues
    "no hace nada". Ver TANDA2_*.
  * Softnyx nunca pone 4 flechas en un tiempo. Ni 3 antes de las 4 estrellas.
  * Los repartos no se inventan: se sortean del pozo real de los 1038 charts.
"""
import csv, json, math, os, random, re, shutil, subprocess, sys, time
from pathlib import Path

# ---------------------------------------------------------------- rutas
# UN SOLO PROGRAMA PARA LOS DOS CLIENTES (22/9/2026). Hasta ese dia habia dos
# copias de este archivo que se diferenciaban en 15 lineas, todas rutas, y cada
# arreglo habia que hacerlo dos veces -- y una vez se hizo en una sola.
#
# Ahora el codigo es UNO. Lo que cambia de un cliente al otro va en un
# `cliente.json` AL LADO de este archivo; si no esta, son las rutas del 2016 de
# siempre. Para actualizar el otro Estudio alcanza con copiar los .py: su
# cliente.json se queda.
ESTUDIO   = Path(__file__).resolve().parent      # la carpeta donde esta esto
CLIENTE   = "2016"
JUEGO     = Path(r"C:\Game\SoftnyxGame\LoveRitmoLS")
PRIV      = Path(r"C:\Game\LoveRitmoPriv")
MANA      = Path(r"C:\Game\LoveRitmoPriv\musictable_mana")
REGISTRO  = "snb_local.json"      # el registro de claves de los .snb que hicimos
_CFG = ESTUDIO / "cliente.json"
if _CFG.exists():
    _c = json.loads(_CFG.read_text(encoding="utf-8"))
    CLIENTE = str(_c.get("cliente", CLIENTE))
    JUEGO = Path(_c.get("juego", JUEGO))
    PRIV = Path(_c.get("privado", PRIV))
    REGISTRO = _c.get("registro", REGISTRO)
EXE       = JUEGO / "LoveRitmo.exe"
try:                              # (10/10/2026) o LoveBeat.exe (Steam/KR) u otro nombre: juegos.buscar_exe
    import juegos as _J
    EXE = _J.buscar_exe(JUEGO) or EXE
except Exception:
    pass
TABLA     = JUEGO / r"MediaPath\PARAM\musictable.slk.spak"
MOTOR     = ESTUDIO / "motor"
RESPALDOS = ESTUDIO / "respaldos"
CACHE     = ESTUDIO / "_cache"
MT_TOOL   = Path(r"C:\Users\jhon_\OneDrive\Escritorio\MusictableTool")
VDJ       = Path(os.path.expanduser(r"~\AppData\Local\VirtualDJ\database.xml"))
# LAS CARPETAS DE AUDIO, en orden: la primera donde aparezca el .ogg, gana.
#
# CORREGIDO el 22/9/2026. La lista tenia `Music\LoveRitmoLS_OGG`, que YA NO
# EXISTE: el 21/9 la metieron adentro de `Music\LoveRitmoLS2020_OGG\`. Nadie se
# entero porque el paquete 2020 tambien habia dejado copias en `Elton\mana`, y
# el programa las encontraba ahi de casualidad. Y habia una carpeta que nunca
# estuvo en la lista: `Music\LR2016_OGG`, con 647 audios del 2016.
#
# Cada cliente mira PRIMERO su propia carpeta oficial: el mismo `bkgNN` puede
# ser otra cosa en la otra version. Se puede cambiar en cliente.json ("audios").
OGG_DIRS  = [Path(r"C:\Users\jhon_\Music\Elton\mana"),
             Path(r"C:\Users\jhon_\Music\LR2016_OGG"),
             Path(r"C:\Users\jhon_\Music\LoveRitmoLS2020_OGG\LoveRitmoLS_OGG")]
if _CFG.exists() and _c.get("audios"):
    OGG_DIRS = [Path(p) for p in _c["audios"]]
OGG_NUEVOS = OGG_DIRS[0]

# EL PROGRAMA SE VALE SOLO (22/9/2026, pedido de Joel: "que este programa no
# dependa mucho de otras cosas, que sea independiente").
#
# El motor entero -- la rejilla, el analizador, el lector del musictable y el
# Blowfish -- vive en `motor\`, al lado de esto, para que todo sea UNA SOLA COSA
# que se pueda copiar o mover.
#
# ANTES aca tambien se colgaban del sys.path la carpeta del Escritorio
# (MusictableTool, que ademas esta DENTRO de OneDrive) y `musictable_mana`, por
# si faltaba algo. MEDIDO ese dia: no se cargaba NADA de ahi, los cinco modulos
# salian de `motor\`. Y la copia del Escritorio tiene un `musictable_tool`
# VIEJO, de antes de los arreglos de hoy. Un respaldo que puede tapar al bueno
# no es un respaldo, es una trampa. Queda solo `motor\`.
sys.path.insert(0, str(MOTOR))

from programas import FFMPEG, FFPROBE     # ffmpeg, con su ruta

LISTAS = ["Length", "KeyPatternID", "KeySoundID", "MissionID1", "MissionID2",
          "MissionDanceID", "MissionSuccessDanceID", "MissionFailDanceID",
          "MissionCameraID", "DanceCameraID"]

for _d in (RESPALDOS, CACHE):
    _d.mkdir(parents=True, exist_ok=True)


# ================================================================ la tabla
class Tabla(object):
    """El musictable instalado, en memoria."""

    def __init__(self):
        self.cab = []              # los nombres recortados, los que se usan aca
        self.cab_juego = []        # los nombres tal cual los tiene el juego
        self.filas = []
        self.csv = ESTUDIO / "_tabla.csv"
        self.cargar()

    def cargar(self):
        """Trae el musictable del juego a memoria.

        LOS NOMBRES DE LAS COLUMNAS VIENEN COMO ESTAN EN EL JUEGO, y no todos
        los clientes los escriben igual: en el musictable del 2020 la columna
        se llama "Genre " CON UN ESPACIO AL FINAL. Las otras 22 son iguales.

        Eso rompia la copia del Estudio del 2020 el 22/9/2026: "Agregar
        cancion" hace f["Genre"] = ..., la fila quedaba con una columna 24 que
        no existia en la cabecera, y al guardar saltaba
        `ValueError: dict contains fields not in fieldnames: 'Genre'`.

        Adentro del Estudio se usan SIN espacios, asi el mismo codigo sirve
        para los dos clientes y no hay que acordarse de cual es cual. Al
        guardar se escriben tal cual estaban en el juego: el importador va por
        POSICION y compara valor por valor, asi que renombrarle una columna a
        la tabla del juego seria un cambio mas, y de los que no se piden.
        """
        import musictable_tool as mt
        mt.exportar(str(EXE), str(TABLA), str(self.csv))
        with open(self.csv, encoding="utf-8-sig", newline="") as f:
            r = csv.DictReader(f, delimiter=";")
            self.cab_juego = list(r.fieldnames or [])
            self.cab = [c.strip() for c in self.cab_juego]
            self.filas = []
            for x in r:
                fila = dict((c.strip(), v) for c, v in x.items()
                            if isinstance(c, str))
                if (fila.get("ID") or "").strip():
                    self.filas.append(fila)
        # la primera vez, la lista de lo nuestro arranca mirando ESTA tabla
        # (ver `mias`). Despues ya queda en mias.json y esto no hace nada.
        mias(self)
        self.huella = self._huella()

    def _huella(self):
        """Tamano y hora del musictable del juego: para saber si lo tocaron."""
        try:
            st = TABLA.stat()
            return (st.st_size, int(st.st_mtime))
        except OSError:
            return None

    def por_id(self, id_):
        return next((f for f in self.filas if f["ID"] == str(id_)), None)

    def ids_libres(self, desde=2000, cuantos=2):
        usados = set(int(f["ID"]) for f in self.filas if f["ID"].isdigit())
        # (7/10/2026) y los del mapa del SERVIDOR: con el selector de juegos, el 2020 y el
        # de amigos comparten musictable_sn.json; un ID libre en esta tabla puede estar
        # usado por el otro juego, y el servidor haria sonar la cancion equivocada.
        try:
            usados |= set(int(k) for k in json.loads(
                (PRIV / "musictable_sn.json").read_text(encoding="utf-8")) if str(k).isdigit())
        except Exception:
            pass
        libres, n = [], desde
        while len(libres) < cuantos:
            if n not in usados:
                libres.append(n)
            n += 1
        return libres

    def guardar(self, etiqueta="cambio"):
        """Escribe la tabla en el juego, con respaldo fechado."""
        # LA TRABA (22/9/2026). Esto escribe la tabla ENTERA que hay en memoria.
        # Si el musictable del juego cambio desde que se abrio -- otra ventana
        # del Estudio, un arreglo hecho por fuera --, escribir ahora PISARIA esos
        # cambios sin avisar: una ventana vieja abierta toda la tarde devolveria
        # canciones borradas y desharia los arreglos. Asi que se niega.
        ahora = self._huella()
        if getattr(self, "huella", None) and ahora and ahora != self.huella:
            raise RuntimeError(
                "NO ENVIE NADA: el musictable del juego cambio desde que abriste "
                "esta ventana (otra ventana del Estudio, o un arreglo hecho por "
                "fuera). Si envio lo que tengo en memoria, piso esos cambios.\n\n"
                "Cerra el Estudio, volvelo a abrir y rehace lo que estabas haciendo.")
        import musictable_tool as mt
        # LOS NOMBRES QUE EL JUEGO NO PUEDE GUARDAR SE LIMPIAN ACA, en vez de
        # frenar el envio entero (23/9/2026: "훗 Hoot" trabo toda la tabla).
        # Lo que ya se podia guardar no cambia ni un caracter.
        self.limpiados = []
        for fila in self.filas:
            for c, v in list(fila.items()):
                if isinstance(v, str):
                    nuevo = texto_para_juego(v)
                    if nuevo != v:
                        fila[c] = nuevo
                        self.limpiados.append((fila.get("ID"), c, v, nuevo))
        sello = time.strftime("%Y%m%d_%H%M%S")
        respaldo = RESPALDOS / ("musictable_%s_%s.slk.spak" % (sello, etiqueta))
        shutil.copy2(str(TABLA), str(respaldo))
        with open(self.csv, "w", encoding="utf-8", newline="") as f:
            # con los nombres TAL CUAL los tiene el juego, espacios incluidos:
            # ver `cargar`. Adentro las filas los tienen recortados.
            w = csv.DictWriter(f, fieldnames=self.cab_juego, delimiter=";")
            w.writeheader()
            w.writerows([dict((c, fila.get(c.strip(), "")) for c in self.cab_juego)
                         for fila in self.filas])
        mt.importar(str(EXE), str(self.csv), str(TABLA), str(respaldo))
        self.huella = self._huella()
        return respaldo


# (7/10/2026) EL snb_local.py ES EL DEL ESTUDIO (para_el_servidor\), no el que
# este suelto en la carpeta del servidor: con el selector de juegos cada uno tiene
# sus rutas, y en algunas PC la carpeta del servidor ya tenia OTRO snb_local.py
# (viejo, con rutas de otra maquina). Las rutas van por variables de entorno.
SNB_LOCAL = ESTUDIO / "para_el_servidor" / "snb_local.py"


def entorno_snb():
    e = dict(os.environ)
    e.update(ESTUDIO_PRIVADO=str(PRIV), ESTUDIO_JUEGO=str(JUEGO),
             ESTUDIO_OGGS=str(OGG_NUEVOS), ESTUDIO_REGISTRO=str(REGISTRO),
             ESTUDIO_MOTOR=str(MOTOR))
    return e


def correr_snb_local(*args):
    """snb_local.py del Estudio con las rutas del juego elegido."""
    return subprocess.run([sys.executable, str(SNB_LOCAL)] + [str(a) for a in args],
                          capture_output=True, text=True, cwd=str(PRIV),
                          env=entorno_snb())


def _nombres_ocupados(tabla):
    """(7/10/2026) Los bkgNNNN que NO se pueden usar para una cancion nueva: los de esta
    tabla Y los del registro de claves y el mapa del servidor, que pueden ser de OTRO
    juego del mismo servidor (el 2020 y el de amigos comparten los dos). Con el mismo
    nombre, el registro guardaria la clave de una y el servidor romperia la otra."""
    usados = set(f["Filename"] for f in tabla.filas)
    for arch in (PRIV / REGISTRO, PRIV / "musictable_sn.json"):
        try:
            d = json.loads(arch.read_text(encoding="utf-8"))
            usados |= set(d.keys() if arch.name == REGISTRO else d.values())
        except Exception:
            pass
    return usados


def mapa_sn():
    """Rehace SoundSourceSN -> Filename. OBLIGATORIO tras tocar el musictable.
    (7/10/2026) combina con el musictable_sn.json que ya hay, no lo pisa."""
    r = correr_snb_local("--mapa")
    return ((r.stdout or "") + (r.stderr or "")).strip()


# ================================================================ el audio
def buscar_ogg(nombre):
    for d in OGG_DIRS:
        p = d / (nombre + ".ogg")
        if p.exists():
            return p
    return None


def _cache_de(ogg):
    return CACHE / ("%s_%d.json" % (ogg.stem, int(ogg.stat().st_mtime)))


def _md5(ruta):
    import hashlib
    m = hashlib.md5()
    with open(ruta, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            m.update(b)
    return m.hexdigest()


_HASHES = ESTUDIO / "_hashes.json"


def _hash_con_cache(ruta, cache):
    ruta = str(ruta)
    try:
        st = os.stat(ruta)
    except OSError:
        return None
    clave = "%s|%d|%d" % (ruta, st.st_mtime_ns, st.st_size)
    if clave in cache:
        return cache[clave]
    try:
        cache[clave] = _md5(ruta)
    except OSError:
        return None
    return cache[clave]


def _leer_vdj(ruta):
    """Lee la base de Virtual DJ. {nombre: {bpm, periodo, fase, largo, ruta, bytes}}

    Se parsea aca adentro en vez de usar `rejilla_vdj.py` porque hace falta un
    campo que aquel no sacaba: `FileSize`. Ver _indice_vdj.
    """
    import re
    with open(ruta, encoding="utf-8", errors="replace") as f:
        d = f.read()
    out = {}
    for m in re.finditer(r'<Song FilePath="([^"]+)"([^>]*)>(.*?)</Song>', d, re.S):
        camino, atrib, cuerpo = m.group(1), m.group(2), m.group(3)
        s = re.search(r"<Scan ([^>]*?)/>", cuerpo)
        if not s:
            continue
        at = dict(re.findall(r'(\w+)="([^"]*)"', s.group(1)))
        try:
            per = float(at.get("Bpm", 0) or 0)
            fase = float(at.get("Phase", 0) or 0)
        except ValueError:
            continue
        if per <= 0:
            continue
        largo = re.search(r'SongLength="([\d.]+)"', cuerpo)
        tam = re.search(r'FileSize="(\d+)"', atrib)
        nom = os.path.splitext(os.path.basename(camino.replace("\\", "/")))[0]
        out[nom] = dict(bpm=60.0 / per, periodo=per, fase=fase,
                        largo=float(largo.group(1)) if largo else 0.0,
                        ruta=camino, bytes=int(tam.group(1)) if tam else 0)
    return out


def _indice_vdj():
    """{nombre_en_vdj: info}, {md5: info}, {tamano_en_bytes: info}.

    POR QUE NO ALCANZA CON EL NOMBRE: Virtual DJ analiza los .ogg con el nombre
    que tienen EN EL DISCO (bkg193.ogg en "Nueva carpeta (7)"), pero en el juego
    esa misma cancion vive con un nombre nuevo (bkg2867). Buscando solo por
    nombre no aparecia ninguna y todo se medía a mano.

    COMPROBADO el 16/9/2026: de las 9 canciones que Virtual DJ sí tenía (bajo el
    nombre viejo), LAS 9 tienen su arranque aprobado justo en un "1" de compás de
    Virtual DJ, 7 de ellas a 0 ms. Las mismas dos que mi medición daba corridas
    (Play it sweet 458 ms, The soldier dream 731 ms) caen a 0 y 19 ms con la
    cuadrícula de Virtual DJ. Virtual DJ tiene razón; mi medición es la que se
    corre.

    POR QUE TAMBIEN POR TAMANO (19/9/2026): el md5 exige tener el archivo que
    Virtual DJ analizó, y esa carpeta se borró. Pero la base guarda `FileSize`,
    y los .ogg recuperados del juego son IDENTICOS a los originales, así que el
    tamaño en bytes los empareja igual. Se cruza con la duración (± 0.5 s) para
    que no haya casualidades.

    ESE CRUCE FALTABA y se puso el 21/9/2026: hasta ese día `rejilla_vdj` se
    quedaba con la primera entrada del mismo tamaño sin mirar nada más, así que
    dos canciones distintas que pesaran los mismos bytes exactos se emparejaban
    en silencio y con confianza 100, y de ahí salía el StartDelayTime. Ahora se
    compara de verdad contra `dur` (el `SongLength` de la base). COMPROBADO
    sobre las 247 filas del musictable: 4 emparejan por tamaño (bkg2877 y
    bkg2878, dos filas cada una) y a las 4 les cuadra la duración al centésimo,
    así que ninguna se queda sin cuadrícula. De las 593 entradas de la base, las
    593 traen `FileSize` y `SongLength`, y los 22 tamaños repetidos que hay son
    siempre la misma canción guardada con dos nombres.
    """
    if not VDJ.exists():
        return {}, {}, {}
    try:
        d = _leer_vdj(str(VDJ))
    except Exception:
        return {}, {}, {}
    por_nombre = {}
    for n, i in d.items():
        por_nombre[n] = dict(origen="Virtual DJ", bpm=i["bpm"], per=i["periodo"],
                             fase=i["fase"], dur=i["largo"], confianza=100.0,
                             vdj_nombre=n, bytes=i.get("bytes", 0))
    cache = {}
    if _HASHES.exists():
        try:
            cache = json.loads(_HASHES.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    antes = len(cache)
    por_hash, por_tam = {}, {}
    for n, i in d.items():
        tam = i.get("bytes", 0)
        if tam:
            por_tam.setdefault(tam, por_nombre[n])
        ruta = i.get("ruta", "").replace("/", os.sep)
        if ruta and os.path.exists(ruta):
            h = _hash_con_cache(ruta, cache)
            if h:
                por_hash[h] = por_nombre[n]
    if len(cache) != antes:
        try:
            _HASHES.write_text(json.dumps(cache), encoding="utf-8")
        except Exception:
            pass
    _indice_vdj.cache = cache
    return por_nombre, por_hash, por_tam


# Cuanto se le permite discrepar a la duracion para dar por buena una pareja
# hecha por tamano. Medio segundo: el .ogg del juego y el que analizo Virtual DJ
# son el mismo archivo, asi que en la practica coinciden al centesimo; el margen
# es solo para el redondeo de SongLength.
TOL_DUR_TAM = 0.5


def _dur_de_archivo(ogg):
    """Cuanto dura el archivo, sin analizarlo entero. None si no se sabe.

    Primero mira la cache de `perfil_audio`: si la cancion ya se midio alguna
    vez, la duracion ya esta guardada ahi y no cuesta nada. Si no esta, se la
    pregunta a ffprobe, que solo lee las cabeceras.
    """
    ogg = Path(ogg)
    try:
        cach = _cache_de(ogg)
        if cach.exists():
            d = json.loads(cach.read_text(encoding="utf-8"))
            if d.get("dur"):
                return float(d["dur"])
    except Exception:
        pass
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                            "format=duration", "-of", "default=nw=1:nk=1",
                            str(ogg)], capture_output=True, text=True)
        return float((r.stdout or "").strip())
    except Exception:
        return None


def rejilla_vdj(nombre, ogg=None):
    """La cuadricula de Virtual DJ, si la tiene. Es la fuente preferida.

    Busca por nombre, por contenido (md5) y por tamaño del archivo. Ver
    _indice_vdj para el porqué de cada una. El nombre y el md5 son exactos; la
    del tamaño no lo es, y por eso esa última se cruza con la duración.
    """
    por_nombre, por_hash, por_tam = _indice_vdj()
    i = por_nombre.get(nombre)
    if i:
        return dict(i)
    if ogg is None:
        return None
    cache = getattr(_indice_vdj, "cache", {})
    if por_hash:
        h = _hash_con_cache(ogg, cache)
        if h and h in por_hash:
            r = dict(por_hash[h])
            r["origen"] = "Virtual DJ (analizado como %s)" % r["vdj_nombre"]
            try:
                _HASHES.write_text(json.dumps(cache), encoding="utf-8")
            except Exception:
                pass
            return r
    try:
        tam = os.path.getsize(ogg)
    except OSError:
        return None
    r = por_tam.get(tam)
    if r:
        # EL TAMANO SOLO NO ALCANZA. Que dos canciones distintas pesen los mismos
        # bytes exactos es raro, pero si pasa el fallo es MUDO: se le da la
        # cuadricula de otra cancion con confianza 100 y de ahi sale el arranque.
        # Asi que se cruza con la duracion, como dice _indice_vdj. Si alguna de
        # las dos duraciones no se puede saber, TAMPOCO se empareja: sin la
        # comprobacion el tamano es una corazonada, y devolver None solo cuesta
        # que se mida el audio, que es lo que se hacia antes de tener la base.
        dur_vdj = float(r.get("dur") or 0.0)
        dur_ogg = _dur_de_archivo(ogg)
        if (dur_vdj > 0 and dur_ogg is not None
                and abs(dur_vdj - dur_ogg) <= TOL_DUR_TAM):
            r = dict(r)
            r["origen"] = "Virtual DJ (analizado como %s)" % r["vdj_nombre"]
            return r
    return None


def rejilla_medida(ogg, bpm_nominal, buscar=False):
    """La cuadricula medida del audio, con la fase decidida por los GRAVES.

    Con `buscar=True` el BPM sale del AUDIO en vez del nominal. Eso es lo que
    hace falta para una cancion NUEVA, que no tiene BPM propio: ver el
    docstring de `rejilla.medir`.
    """
    import rejilla
    r = rejilla.medir(str(ogg), bpm_nominal, buscar=buscar)
    return dict(origen="medido del audio" + (" (el BPM tambien)" if buscar else ""),
                bpm=float(r["bpm"]), per=float(r["per"]),
                fase=float(r["t0_compas"]), dur=float(r["dur"]),
                confianza=float(r["ventaja"]),
                bpm_audio=float(r.get("bpm_audio") or 0.0),
                nitidez=float(r.get("nitidez") or 0.0))


def perfil_audio(ogg):
    """Graves por segundo, fin del beat y duracion. Va a cache: es lento."""
    cach = _cache_de(ogg)
    if cach.exists():
        try:
            d = json.loads(cach.read_text(encoding="utf-8"))
            if "novedad" in d:
                return d
        except Exception:
            pass
    import numpy as np
    import analizar_bpm as ab
    x = ab.pcm(str(ogg))
    dur = len(x) / ab.SR
    N, H = ab.NFFT, ab.HOP
    w = np.hanning(N).astype(np.float32)
    nf = (len(x) - N) // H
    gr = np.empty(nf, dtype=np.float32)
    f = np.fft.rfftfreq(N, 1.0 / ab.SR)
    banda = (f >= 40) & (f < 160)
    paso = 2048
    for a in range(0, nf, paso):
        b = min(nf, a + paso)
        idx = np.arange(N)[None, :] + H * np.arange(a, b)[:, None]
        S = np.abs(np.fft.rfft(x[idx] * w, axis=1))
        gr[a:b] = S[:, banda].mean(axis=1)
    fps = ab.SR / H
    seg = [float(gr[int(i * fps):int((i + 1) * fps)].mean() or 0.0)
           for i in range(int(dur))]
    mx = max(seg) or 1.0
    graves = [100.0 * v / mx for v in seg]
    k = int(fps * 1.0) | 1
    suave = np.convolve(gr, np.ones(k) / k, mode="same")
    a, b = int(fps * 20), int(fps * max(21, dur - 20))
    ref = float(np.percentile(suave[a:b], 60)) if b > a else float(suave.mean())
    ix = np.where(suave > 0.15 * ref)[0]
    fin_beat = float(ix[-1] / fps) if len(ix) else dur
    entra = entra_el_ritmo(graves)

    # NOVEDAD: cuanto cambia el sonido en cada instante. Los cambios de seccion
    # (entra la voz, entra el coro, se va la banda) caen casi siempre en el
    # principio de una frase de 4 compases, que es justo lo que dura una mision.
    # Sirve para elegir CUAL de los 4 compases posibles es el "1" de la frase.
    # OJO: separa poco. Se usa solo como desempate, nunca como unico criterio.
    Sl = np.log1p(np.abs(np.fft.rfft(
        (x[np.arange(N)[None, :] + H * np.arange(0, nf, 4)[:, None]] * w), axis=1)))
    nn = Sl.shape[0]
    fps4 = fps / 4.0
    lag = max(2, int(fps4 * 2.0))
    nov = np.zeros(nn, dtype=np.float32)
    if nn > 2 * lag + 2:
        ac = np.cumsum(Sl, axis=0)
        for i in range(lag, nn - lag):
            a1 = (ac[i + lag] - ac[i]) / lag
            a0 = (ac[i] - ac[i - lag]) / lag
            nov[i] = np.abs(a1 - a0).sum()
        nov = (nov - nov.mean()) / (nov.std() + 1e-9)
    d = dict(dur=dur, graves=graves, fin_beat=fin_beat, entra_beat=entra,
             novedad=[round(float(v), 3) for v in nov], nov_fps=fps4)
    try:
        cach.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass
    return d


# El ritmo se da por entrado cuando los graves llegan al 20% del nivel tipico de
# la cancion y se mantienen 3 de cada 4 segundos. Los dos numeros estan MEDIDOS
# el 19/9/2026 contra las 14 canciones que el programa marcaba como "flechas
# antes del ritmo", leyendo a mano en que segundo entra la bateria en su perfil
# de graves. Error medio contra lo que se oye:
#
#     0.45 del nivel, los 4 segundos (lo que habia)  -> 15.0 s,  2 de 14 bien
#     0.30 del nivel, 3 de cada 4                    ->  4.6 s,  8 de 14 bien
#     0.20 del nivel, 3 de cada 4 (esto)             ->  1.4 s, 13 de 14 bien
#
# Los dos cambios arreglan cosas distintas. El 0.45 daba por "sin ritmo" un tema
# cuyo estribillo es mucho mas fuerte que su estrofa: "Burn Brighter" tiene la
# bateria puesta desde el segundo 5 y decia 18. Y pedir los 4 segundos se rompia
# con un solo segundo flojo: "Sacred Organs" entra en el 26 y decia 39.
GRAVES_RITMO, GRAVES_SEGUIDOS = 0.20, 3


def entra_el_ritmo(graves):
    """En que segundo entra la bateria de verdad.

    Se compara contra el nivel TIPICO de la propia cancion (la mediana del
    cuerpo), no contra su pico. CORREGIDO el 16/9/2026: con el pico como
    referencia, un tema con estribillo mucho mas fuerte que la intro daba falsos
    positivos - "Arabian Nights" decia que el ritmo entraba en el segundo 31
    cuando entra en el 2, y "Sao Paulo" decia 38 cuando entra en el 0.

    AJUSTADO el 19/9/2026 (ver GRAVES_RITMO arriba): la correccion de septiembre
    se quedo corta y seguia llegando tarde una media de 15 segundos.

    ESTO NO TIENE RESPALDO EN SOFTNYX y no lo va a tener: los .snb que vinieron
    con el juego estan cifrados con una clave que mandaba el servidor de Softnyx
    y se perdio, asi que de sus 1038 charts no se puede medir ni un segundo de
    audio. Por eso lo que salga de aqui avisa, pero nunca manda.
    """
    if not graves:
        return 0.0
    cuerpo = graves[int(len(graves) * 0.2):int(len(graves) * 0.8)] or graves
    orden = sorted(cuerpo)
    med = orden[len(orden) // 2]
    u = GRAVES_RITMO * med
    for i in range(max(0, len(graves) - 4)):
        if sum(1 for v in graves[i:i + 4] if v >= u) >= GRAVES_SEGUIDOS:
            return float(i)
    return 0.0


def rejilla_de(fila, forzar_medida=False, buscar_bpm=False):
    """La cuadricula de una fila: Virtual DJ si la tiene, si no medida.

    `buscar_bpm` es para las canciones NUEVAS, que no tienen BPM propio: sin
    eso heredan el de la fila que se copio como molde y la cuadricula sale de
    cualquier lado (22/9/2026, ver `rejilla.medir`). Para una fila que ya
    existe va en False a proposito: el BPM de la tabla es lo que usa el juego y
    no se toca solo.
    """
    nombre = fila["Filename"]
    ogg = buscar_ogg(nombre)
    if ogg is None:
        # (7/10/2026) sin el .ogg no se puede medir NADA, y antes solo se rehacian los de
        # "tus" canciones (Recuperar audios). Si el .snb esta en el juego y su clave en el
        # registro, se rearma ahora mismo, para cualquier cancion (la Kasai, las traidas).
        try:
            hechos, _f = recuperar_audios([nombre])
            if hechos:
                ogg = buscar_ogg(nombre)
        except Exception:
            pass
    r = None if forzar_medida else rejilla_vdj(nombre, ogg)
    if r is None:
        if ogg is None:
            return None
        try:
            bpm_nom = float(fila["BPM"])
        except Exception:
            bpm_nom = 0.0
        r = rejilla_medida(ogg, bpm_nom, buscar=buscar_bpm)
    if ogg is not None:
        p = perfil_audio(ogg)
        r["dur"] = r.get("dur") or p["dur"]
        r["fin_beat"] = p["fin_beat"]
        r["graves"] = p["graves"]
        # se recalcula siempre: la cache vieja guardaba la version con falsos positivos
        r["entra_beat"] = entra_el_ritmo(p["graves"])
        r["novedad"] = p.get("novedad") or []
        r["nov_fps"] = p.get("nov_fps") or 0.0
    r["compas"] = 4 * r["per"]
    r["ogg"] = str(ogg) if ogg else None
    return r


def downbeats(rej, desde=None, hasta=None):
    """Los '1' de compas de la cuadricula, con su % de la cancion."""
    dur = rej.get("dur") or 0.0
    desde = 0.0 if desde is None else desde
    hasta = dur if hasta is None else hasta
    paso = rej["compas"]
    n = math.floor((desde - rej["fase"]) / paso)
    t = rej["fase"] + n * paso
    out = []
    while t <= hasta:
        if t >= desde and t > 0:
            out.append(dict(t=round(t, 4), pct=100.0 * t / (dur or 1),
                            graves=graves_en(rej, t)))
        t += paso
    return out


def graves_en(rej, t):
    g = rej.get("graves") or []
    i = int(t)
    return g[i] if 0 <= i < len(g) else 0.0


def pegar_a_compas(rej, t):
    return rej["fase"] + round((t - rej["fase"]) / rej["compas"]) * rej["compas"]


def pegar_a_tiempo(rej, t):
    return rej["fase"] + round((t - rej["fase"]) / rej["per"]) * rej["per"]


# ============================================== inicio recomendado (automatico)
# MEDIDO en los 1038 charts de Softnyx: StartDelayTime / Second va del 2.4% al
# 20.2%, mediana 6.9%, el 90% entre 3.6% y 12.1%.
# RECALIBRADO el 20/9/2026 sobre los 3912 charts de las CUATRO tablas oficiales
# (antes eran los 1038 de 2016): p1 2.9%, p5 3.7%, mediana 6.8%, p95 11.7%,
# p99 14.4%. Cambia casi nada, que es justamente la noticia: las cuatro
# versiones del juego arrancan en el mismo lugar.
#
# El tope va en el p99 y no en el p95 a proposito: el aviso dice "casi nunca
# pasa del", y con el p95 esa frase seria falsa para 1 de cada 20 charts
# oficiales.
# ===================== LA NITIDEZ DE LA CUADRICULA (22/9/2026) =====================
# Cuanto sobresale la mejor fase contra el promedio de todas (`rejilla.medir`).
# Dicho facil: si la rejilla esta en el tempo bueno, el bombo se amontona en una
# sola fase y esto se va a 3 o 5. Si el tempo esta errado, todas las fases dan
# parecido y queda pegado a 1.
#
# MEDIDO sobre los 117 charts oficiales que tienen su .ogg, midiendo cada uno
# con EL BPM QUE USA EL JUEGO -- o sea, cuadriculas que funcionan:
#
#     la peor .............. 1.75
#     p1 ................... 1.78
#     p5 ................... 2.08
#     mediana .............. 3.44
#     la mejor ............. 7.62
#     por debajo de 1.5 .... NINGUNA
#
# Y la cuadricula que le salio a Physical con el BPM heredado de la fila de al
# lado (282.72 en vez de 147) da 1.05. Por eso el rojo va en 1.5: por debajo de
# ahi no hay ni un chart oficial, y si hay algo es que el BPM no es de esa
# cancion.
NITIDEZ_MAL = 1.5
NITIDEZ_AVISO = 2.08

PCT_MIN, PCT_IDEAL, PCT_MAX = 3.7, 6.8, 14.4
# el minimo ABSOLUTO visto en esos 1038 charts. Se usa solo para NO mover un
# arranque que el usuario ya eligio: mover lo que ya funciona salio caro.
PCT_ABS_MIN = 2.4


def fase_de_frase(rej, desde=None):
    """De los 4 compases posibles, cual empieza la frase de 4 compases.

    Se puntua cada uno con la NOVEDAD del sonido en las fronteras de mision: si
    las misiones arrancan donde la cancion cambia, la frase esta bien agarrada.

    Devuelve (offset 0-3, margen en %, puntajes). MARGEN CHICO = no se puede
    decidir midiendo, hay que escuchar. Es la unica parte que no se resuelve sola,
    y siempre fue asi: probando las 4 opciones una tiene que ser la buena.
    """
    nov = rej.get("novedad") or []
    fps = rej.get("nov_fps") or 0.0
    dur = rej.get("dur") or 0.0
    if not nov or not fps or not dur:
        return 0, 0.0, [0.0] * 4
    base = desde if desde is not None else rej["fase"]
    mis = 16 * rej["per"]
    puntos = []
    for k in range(4):
        t = base + k * rej["compas"]
        vals = []
        while t < dur - mis:
            i = int(t * fps)
            if 0 <= i < len(nov):
                vals.append(nov[i])
            t += mis
        puntos.append(sum(vals) / len(vals) if vals else 0.0)
    orden = sorted(range(4), key=lambda k: puntos[k], reverse=True)
    mejor = orden[0]
    seg = puntos[orden[1]]
    margen = 100.0 * (puntos[mejor] - seg) / (abs(seg) + 0.3)
    return mejor, margen, puntos


def inicio_recomendado(rej, cerca=None):
    """Elige el '1' de compas donde arrancar. Devuelve (t, motivo).

    Si `cerca` viene (el arranque que ya tenia la fila) y pegarlo al compas mas
    cercano cae dentro de la banda que usa Softnyx, se respeta eso: mover un
    arranque que ya funciona es el error que mas caro salio.
    """
    dur = rej.get("dur") or 0.0
    if not dur:
        return None, "no se pudo medir la duracion"
    entra = rej.get("entra_beat") or 0.0
    if cerca:
        t = pegar_a_compas(rej, cerca)
        pct = 100.0 * t / dur
        if PCT_ABS_MIN <= pct <= PCT_MAX and t >= entra - 1:
            return t, ("es el '1' de compas mas cercano al que ya tenia (%.4f), "
                       "%.1f%% de la cancion" % (cerca, pct))
    cands = arranques_opciones(rej, cuantos=1)
    if not cands:
        return None, "la cuadricula no da ningun compas en el rango"
    mejor = cands[0]
    return mejor["t"], ("%.1f%% de la cancion, donde la musica cambia de seccion. "
                        "Es la opcion mas parecida a Softnyx (%.0f%% de chance de ser "
                        "su compas); las otras estan en la lista." % (mejor["pct"],
                                                                       mejor["prob"]))


# ============================ DONDE ARRANCA SOFTNYX, APRENDIDO (22/9/2026, noche)
# Joel: "el comienzo que me recomienda de algunas canciones son pesimas". Tenia
# razon, y MEDIDO: sobre 619 charts oficiales con audio, y dandole la
# cuadricula PERFECTA (anclada en el arranque oficial), el metodo de antes
# (el '1' mas cerca del 7% de la cancion) elegia el mismo compas que Softnyx
# el 19% de las veces, con 3.5 s de error mediano.
#
# Lo que mira Softnyx, medido rasgo por rasgo (percentil del compas oficial
# entre todos los posibles del 1.5% al 20%; 50 = al azar):
#
#     novedad del sonido en ese compas (cambia la seccion) ... 83
#     novedad en las fronteras de mision que deja ........... 82
#     subida de graves (entra la banda fuerte) ............... 67
#
# Combinado con lo tipico de Softnyx (donde suele caer, `_arranques_softnyx.json`)
# y VALIDADO MITAD Y MITAD (pesos elegidos en una mitad, puntuados en la otra):
#
#                                   antes   ahora
#     el mismo compas que Softnyx    19%     55%
#     a un compas o menos            45%     66%
#     en la fase de frase buena      32%     77%
#     entre las 3 primeras            -      80%
#     entre las 5 primeras            -      89%
#
# Por eso el panel muestra la LISTA ordenada y no una sola: 8 de cada 10 veces
# la buena esta entre las 3 primeras, y se elige escuchando.
ARRANQUE_PESOS = dict(nov=1.0, rise=1.0, nov_frase=1.0, nov_frase4=0.5, antes=1.0)
ARRANQUE_PRIOR = 2.2
ARRANQUE_T = 1.5
_PRIOR_ARR = []


def _prior_arranque(p):
    """Log de cuanto usa Softnyx arrancar en ese % (0-1) de la cancion."""
    if not _PRIOR_ARR:
        import numpy as np
        try:
            pcts = json.loads((MOTOR / "_arranques_softnyx.json").read_text(
                encoding="utf-8"))["pcts"]
        except Exception:
            pcts = [PCT_IDEAL / 100.0]
        xs = np.linspace(0, 0.25, 251)
        d = np.zeros_like(xs)
        for q in pcts:
            d += np.exp(-0.5 * ((xs - q) / 0.008) ** 2)
        d /= d.sum()
        _PRIOR_ARR.extend(float(v) for v in d)
    return math.log(_PRIOR_ARR[min(250, max(0, int(round(p * 1000))))] + 1e-6)


ARRANQUE_BONO_UNO = 1.5   # cuanto se prefiere el "1" de la cuadricula a otro tiempo


def arranques_opciones(rej, cuantos=5):
    """La LISTA de arranques que se le ofrece al usuario.

    La primera es la mejor sobre los "1" de compas (`arranques_candidatos`). Las
    demas salen de TODOS los tiempos, con un empujon a los "1": sin
    Virtual DJ el "1" de la cuadricula propia esta bien el 64% de las veces, y
    cuando esta corrido el compas de Softnyx no podia aparecer en la lista.
    MEDIDO sin Virtual DJ, en 120 oficiales no usadas para ajustar (el bono se
    eligio en otras 120):

                               1a opcion   entre 3   entre 5
        solo los "1"             37%         52%       60%
        esta mezcla              37%         57%       68%
    """
    A = arranques_candidatos(rej, cuantos=1)
    if not A:
        return []
    r2 = dict(rej)
    r2["compas"] = rej["per"]
    B = arranques_candidatos(r2, cuantos=200)
    for x in B:
        k = int(round((x["t"] - rej["fase"]) / rej["per"])) % 4
        x["en_el_uno"] = (k == 0)
        x["s"] = math.log(max(x["prob"], 1e-12)) / 1.0 + (ARRANQUE_BONO_UNO if k == 0 else 0.0)
        if k != 0:
            x["motivo"] = (x["motivo"] + ", " if x["motivo"] != "-" else "") + \
                "fuera del '1'"
    mx = max(x["s"] for x in B)
    tot = sum(math.exp(x["s"] - mx) for x in B)
    for x in B:
        x["prob"] = 100.0 * math.exp(x["s"] - mx) / tot
    B.sort(key=lambda x: -x["s"])
    primera = min(B, key=lambda x: abs(x["t"] - A[0]["t"]))
    out = [primera]
    for x in B:
        if all(abs(x["t"] - y["t"]) > 0.05 for y in out):
            out.append(x)
        if len(out) >= cuantos:
            break
    return out


def arranques_candidatos(rej, cuantos=6):
    """Los '1' de compas del 1.5% al 20% de la cancion, del mas parecido a
    Softnyx al menos. Cada uno: t, pct, prob (en %, entre todos) y por que."""
    dur = rej.get("dur") or 0.0
    nov = rej.get("novedad") or []
    fps = rej.get("nov_fps") or 0.0
    g = rej.get("graves") or []
    if not dur:
        return []
    cands = downbeats(rej, dur * 0.015, dur * 0.20)
    if not cands:
        return []

    def nov_en(t, ven=0.3):
        if not nov or not fps:
            return 0.0
        a, b = int((t - ven) * fps), int((t + ven) * fps) + 1
        s = nov[max(0, a):max(0, b)]
        return max(s) if s else 0.0

    def gm(a, b):
        s = g[max(0, int(a)):max(0, int(b))]
        return sum(s) / len(s) if s else 0.0

    orden_g = sorted(g)
    med = (orden_g[len(orden_g) // 2] if orden_g else 1.0) or 1.0
    mis = 16 * rej["per"]
    filas = []
    for c in cands:
        t = c["t"]
        filas.append(dict(
            nov=nov_en(t),
            rise=(gm(t, t + 4) - gm(t - 4, t)) / med,
            nov_frase=sum(nov_en(t + m * mis) for m in range(12)) / 12.0,
            nov_frase4=sum(nov_en(t + m * mis) for m in range(1, 5)) / 4.0,
            antes=gm(t - 6, t) / med))
    # cada rasgo se compara contra los otros compases de LA MISMA cancion
    punt = [ARRANQUE_PRIOR * _prior_arranque(c["t"] / dur) for c in cands]
    for k, w in ARRANQUE_PESOS.items():
        vals = [f[k] for f in filas]
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 + 1e-9
        for i, v in enumerate(vals):
            punt[i] += w * (v - mu) / sd
    # la chance que se muestra esta CALIBRADA (T = 1.5): sobre los 619 oficiales,
    # la primera dice 57% en promedio y acierta el 56%. Con T = 1 decia 71%.
    mx = max(punt)
    ex = [math.exp((p - mx) / ARRANQUE_T) for p in punt]
    tot = sum(ex)
    out = []
    for i in sorted(range(len(cands)), key=lambda i: -punt[i]):
        c, f = cands[i], filas[i]
        por = []
        if f["nov"] > 1.0:
            por.append("cambia la sección")
        if f["rise"] > 0.3:
            por.append("entra la banda fuerte")
        if f["nov_frase"] > 0.6:
            por.append("las misiones caen con las frases")
        out.append(dict(t=c["t"], pct=c["pct"], prob=100.0 * ex[i] / tot,
                        graves=c["graves"], motivo=", ".join(por) or "-"))
    return out[:cuantos]


# ================================================== flechas y SPACE (Softnyx)
def patron(mid):
    i = int(float(mid)) - 1
    return [0, 0, 0, 0] if i < 0 else [i // 125, (i // 25) % 5, (i // 5) % 5, i % 5]


_POZOS = {}


def pozo(archivo, estrellas):
    if archivo not in _POZOS:
        ruta = MOTOR / archivo
        if not ruta.exists():
            raise RuntimeError(
                "falta %s en la carpeta motor. Ahi estan los repartos reales de "
                "Softnyx y sin eso no se puede generar ningun chart." % archivo)
        _POZOS[archivo] = json.loads(ruta.read_text(encoding="utf-8"))
    d = _POZOS[archivo]
    k = str(estrellas)
    if k not in d:
        k = min(d, key=lambda x: abs(int(x) - estrellas))
    return d[k]


def sortear(p, n, semilla):
    ids = list(p.keys())
    pesos = [p[k] for k in ids]
    r = random.Random(semilla)
    return [r.choices(ids, weights=pesos)[0] for _ in range(n)]


# CUANTAS FLECHAS CAEN EN UN TIEMPO, SEGUN LAS ESTRELLAS. % de tiempos con 0,
# 1, 2 y 3 flechas. RECALIBRADO el 20/9/2026 contra los 3912 charts de las CUATRO
# tablas oficiales (2016, LoveBeat KR, LoveBeat Steam y LoveRitmo 2020). Antes
# salia solo de los 1038 de 2016, y la diferencia no es cosmetica: en 8
# estrellas el cubo de 2 flechas pasa de 37.1% a 24.5% y el de 3 de 30.9% a
# 41.4%. O sea que el Estudio venia generando los charts dificiles mas blandos
# de lo que hace el juego.
REF_FLECHAS = {
     1: (7.7, 70.0, 22.2, 0.0),
     2: (8.8, 60.6, 30.6, 0.0),
     3: (16.0, 38.4, 45.6, 0.0),
     4: (18.2, 26.2, 55.5, 0.1),
     5: (18.3, 21.5, 55.8, 4.4),
     6: (21.1, 17.9, 54.2, 6.8),
     7: (20.5, 13.9, 41.8, 23.8),
     8: (23.6, 10.5, 24.5, 41.4),
     9: (22.6, 10.3, 21.5, 45.6),
    10: (24.2, 9.4, 17.9, 48.5),
}
# flechas por mision (la mediana de cada dificultad, en los mismos 3912)
FLECHAS_POR_MISION = {1: 4.5, 2: 4.8, 3: 5.3, 4: 5.5, 5: 5.8, 6: 5.9, 7: 6.8, 8: 7.3, 9: 7.6, 10: 7.6}
# EL MissionID2 = LA SEGUNDA TANDA (2/10/2026, ver TANDA2_*). Este es su reparto
# por casillero en los charts de Softnyx, CEROS INCLUIDOS: el cubo del 0 junta
# los casilleros vacios de las segundas tandas y las misiones sin segunda tanda
# ("0" cuenta como cuatro ceros). Se escribio creyendo que era "el SPACE" y
# despues que "no hacia nada"; los numeros siguen valiendo para comparar.
# EL SPACE QUE SE VE son los casilleros sin flechas: el juego pone uno en cada
# uno (6.3.1.1), en las dos tandas.
REF_SPACE = {
     1: (41.9, 44.9, 13.2, 0.0),
     2: (40.5, 40.5, 19.0, 0.0),
     3: (41.1, 25.1, 33.8, 0.0),
     4: (40.0, 15.5, 44.3, 0.1),
     5: (42.1, 11.2, 42.9, 3.8),
     6: (44.4, 9.0, 40.8, 5.8),
     7: (44.8, 5.6, 29.0, 20.5),
     8: (47.4, 4.2, 14.3, 34.1),
     9: (47.2, 4.0, 12.1, 36.7),
    10: (46.2, 3.5, 11.0, 39.3),
}
# CUANTO SE PUEDE APARTAR UN CHART DE ESE REPARTO. Se toma, de los cuatro cubos
# (0, 1, 2 y 3), el que mas se aparta de la referencia, y se mira esa distancia
# en puntos de porcentaje. MEDIDO sobre los 3912 charts oficiales:
#
#     flechas:     mediana 11.9, p75 16.8, p90 22.8, p95 26.7, el peor 84.0
#     MissionID2:  mediana 10.9, p75 16.0, p90 21.6, p95 25.7, el peor 60.0
#
# Verde hasta el p95 (lo que el juego hace normalmente), amarillo de ahi hasta
# el peor de los 3912, y rojo solo mas alla: rojo quiere decir "esto no lo hace
# ninguna version del juego", no "esto no me gusta".
#
# LOS UMBRALES ANTERIORES (21.5 y 47.6) SALIAN DE LOS 1038 Y QUEDARON CORTOS:
# con ellos el 12.2% de los 3912 charts oficiales caia en amarillo y el 0.4%
# en rojo. Y los de antes de esos (12 y 22) dejaban al 31.5% en amarillo.
DIF_FLECHAS_OK, DIF_FLECHAS_MAL = 26.7, 84.0
DIF_SPACE_OK, DIF_SPACE_MAL = 25.7, 60.0

# EL FINAL DEL CHART. MEDIDO en los 1038: los segundos de cancion que quedan
# despues del ultimo tiempo del chart (Second - fin del chart) van de -9.7 s a
# +47.2 s, mediana 3.8 s, p95 12.9 s. Los dos extremos importan:
#
#   * Softnyx SE PASA del final del audio en el 5.2% de sus charts, y hasta por
#     9.7 s. Asi que pasarse un poco no puede ser rojo.
#   * corta mas de 12.9 s antes del final en el 5% de los charts.
FIN_PASADO_MAL = 10.0
FIN_CORTO_AVISO = 13.3

# ============ MEDIDO EL 20/9/2026 SOBRE AUDIO OFICIAL (876 charts) ============
# Estos dos umbrales eran los unicos del Estudio apoyados en una medicion propia
# SIN NADA CON QUE CONTRASTARLA: de Softnyx no se puede medir audio. Con el
# musictable del LoveRitmo 2020 y sus 441 .ogg ya se puede, y las dos reglas que
# habia escritas resultaron falsas.
#
# 1) "NUNCA ANTES DE QUE ENTRE LA BATERIA" (regla 3). FALSO:
#
#        arranque - entrada de la bateria, en los 876 charts oficiales
#        min -31.9 | p1 -18.9 | p5 -11.2 | mediana +10.0 | p95 +19.8 | max +44.9
#        ARRANCAN ANTES DE LA BATERIA: 91 de 876 (10.4%)
#
#    O sea que uno de cada diez charts oficiales arranca antes de que mi
#    detector vea la bateria. Puede ser que lo hagan a proposito o que mi
#    detector llegue tarde en esas canciones (ya se sabe que le pasa, ver
#    GRAVES_RITMO). En cualquier caso, avisar apenas se adelanta 1 segundo
#    estaba MAL: el aviso salta recien pasado el p5.
#
#    Y el informe decia "Softnyx arranca entre +7 y +15 s despues de la
#    bateria", medido sobre CUATRO charts. En los 876: solo el 35% cae ahi.
RITMO_ANTES_AVISO = 11.2
#
# 2) EL FINAL. Lo que si se confirma, y lo que no:
#
#        fin del chart - duracion REAL del audio
#        p1 -16.8 | p5 -13.0 | mediana -4.6 | p95 +0.3 | p99 +2.9 | max +6.3
#        SE PASAN del final: 54 de 876 (6.2%), el que mas por 6.3 s
#
#    Confirma lo de los 1038 (5.2% se pasan) y deja el rojo holgado en 10 s.
#    Y el p95 de lo que cortan antes da 13.3 s, contra 12.9 medido en los 1038:
#    dos fuentes distintas, el mismo numero.
#
# 3) `fin_beat` NO SIRVE PARA AVISAR. El chart pasa por mas de 2 s el punto
#    donde mi medidor deja de ver graves en 193 de 876 charts OFICIALES (22%).
#    Avisar con 2 s de margen era marcar uno de cada cinco charts buenos. El p95
#    da +10.5 s, asi que el aviso pasa a saltar recien ahi.
FIN_BEAT_AVISO = 10.5
#
# 4) De paso: `Second` de la tabla contra la duracion real del audio da -0.4 s
#    de mediana (p5 -1.0, p95 -0.0). O sea que `Second` ES la duracion, redondeada
#    para abajo. Se puede confiar en ella cuando no hay audio.

# ============ EL ARRANQUE Y EL BPM (calibrado el 20/9/2026) ============
# DE SOFTNYX NO HAY REFERENCIA PARA ESTO Y NO LA VA A HABER. Sus .snb estan
# cifrados con una clave que mandaba su servidor y se perdio, asi que de sus
# 1038 charts no se puede medir ni un segundo de audio (15B.3). Se probo ademas
# si su StartDelayTime caia en la cuadricula contada desde el segundo 0: NO. El
# desvio se reparte parejo entre 0 y medio tiempo (mediana 0.236 tiempos, p95
# 0.478, 59 de 1038 a menos de 0.02), que es exactamente lo que da el azar.
#
# La referencia que SI hay son los charts QUE FUNCIONAN, medidos contra la
# cuadricula de Virtual DJ (desvio del StartDelayTime al tiempo mas cercano):
#
#   Not Your Baby  -66.7 ms | Arabian Nights -56.9 | Light it up    -44.4
#   In The City    -42.8    | Na Na Na       -40.9 | For you no way -27.4
#   Baby~ ye~ ye   -25.5    | Hoot (aprobado)-22.2 | APT (aprobado)   0.0
#   Play it sweet    0.0
#
# EL UMBRAL VIEJO ERA 40 ms Y ESTABA MAL: dejaba en ROJO a seis de esos diez,
# entre ellos los tres que Joel dijo que le funcionan (In The City, Light it up,
# Not Your Baby). Ya estaba escrito en la PARTE 12 del informe, midiendo lo
# mismo contra otra cuadricula: "los charts originales no son una rejilla
# perfecta, asi que calibrar umbrales al milisegundo contra ellos no tiene
# sentido; sirven como referencia de lo GRUESO, no de lo fino".
#
# CONFIRMADO el 20/9/2026 sobre 876 CHARTS OFICIALES, no diez. Joel trajo el
# musictable del LoveRitmo 2020, y sus 441 .ogg estan en el disco: 435 canciones
# cruzan, o sea 876 filas de charts oficiales CON SU AUDIO AL LADO. Es la unica
# fuente que permite medir esto (de Softnyx no se puede: sus .snb estan cifrados
# con una clave perdida). Desvio del StartDelayTime al tiempo del chart:
#
#     mediana 53 ms | p75 65 | p90 111 | p95 173 | el peor 324
#     a menos de  70 ms: 702 de 876  (80%)
#     a menos de 150 ms: 822 de 876  (94%)
#
# Y ESO ES UN TECHO, no el numero fino: la cuadricula la medi yo, y mi medicion
# se corre (hasta 731 ms en un caso de 9 contra Virtual DJ). O sea que el
# desprolijo real de los charts es MENOR que esto. Con 80% por debajo de 70 ms
# midiendo mal, el umbral de 70 ms queda holgado, no apretado.
ARR_OK_MS = 70.0

# ================== EL DESFASE DE 58 ms (medido el 20/9/2026) ==================
# LOS CHARTS OFICIALES NO ARRANCAN SOBRE EL "1" DE VIRTUAL DJ: ARRANCAN 58 ms
# ANTES. Medido sobre los 876 charts del LoveRitmo 2020 que tienen su .ogg en el
# disco, con las 441 canciones analizadas por Virtual DJ:
#
#     desvio con signo al tiempo del chart
#     p5 -80 | p25 -66 | MEDIANA -59 | p75 -54 | p95 -34 ms
#     862 de 876 (98.4%) arrancan ANTES
#
# Se midio primero con 786 (Virtual DJ llevaba 396 de 441) y despues con las 876:
# no se movio ni un decimal. Eso es lo que la hace creible.
#
# Y NO ES UNA COSTUMBRE DE LA CUADRICULA, ES UN RETARDO FIJO. Partido por la
# duracion del tiempo del chart:
#
#     tiempo de 200-300 ms  (223 charts)  ->  -59 ms   (-23.6% del tiempo)
#     tiempo de 300-400 ms  (289 charts)  ->  -58 ms   (-17.1%)
#     tiempo de 400-600 ms  (303 charts)  ->  -59 ms   (-13.1%)
#     tiempo de 600-1200 ms  (49 charts)  ->  -58 ms   ( -8.9%)
#
# En milisegundos es el mismo numero en todo el rango de BPM, y en porcentaje
# varia del 9% al 23%. Eso solo lo explica un retardo fijo.
#
# NO SE SABE de que lado esta: puede ser que Virtual DJ marque el "1" 58 ms
# tarde, o que el juego arranque el chart 58 ms antes del golpe a proposito. Da
# igual para usarlo: contra la cuadricula de Virtual DJ, lo oficial es -58 ms.
#
# LO QUE ESTO SIGNIFICA PARA EL ESTUDIO: "Pegar a la cuadricula" deja el
# arranque en 0 ms, o sea 58 ms MAS TARDE que lo que hace el juego. Y explica
# algo que aparecio esta manana sin explicacion: la tanda vieja de Joel
# (bkg2800..bkg2846) estaba entre -15 y -67 ms, mediana -37, y se penso que era
# un defecto del metodo con que se hizo. NO LO ERA: ese metodo estaba MAS CERCA
# de la costumbre oficial que el Estudio.
#
# PROBADO JUGANDO EL 20/9/2026, Y NO CAMBIA NADA. 12 partidas de la misma
# cancion en dos rondas con el orden invertido, a 268 BPM (donde 58 ms son el
# 26% de un tiempo):
#
#     A (el "1" de Virtual DJ): 20684 por mision de media, 18 misiones en 0
#     B (58 ms antes)         : 20533 por mision de media, 19 misiones en 0
#     diferencia: -152 por mision, o sea el 0.7% A FAVOR DE A
#
# En la primera ronda B parecia mucho mejor (2 misiones en 0 contra 8), pero esa
# ronda tenia a la A jugandose siempre primero, en frio. Al invertir el orden el
# efecto se dio vuelta. Era el calentamiento, no los 58 ms.
#
# ASI QUE ESTO NO SE APLICA: el Estudio sigue poniendo el arranque en el "1", y
# el desfase se INFORMA en el punto "Contra lo oficial" y nada mas. Es un dato
# medido sobre 876 charts oficiales, no una regla para seguir.
DESFASE_OFICIAL = 0.058
# El rojo queda para otra cosa: que el arranque NO ESTE SOBRE LA CUADRICULA DEL
# PROPIO CHART. Pasada la cuarta parte de un tiempo ya esta mas cerca de la
# contra que del tiempo, y las flechas caen entre los golpes de la musica.
# TIENE QUE FALLAR POR LOS DOS LADOS (ms y %) para ser rojo: si solo mirara el
# %, un chart de 346 BPM (tiempo de 173 ms) seria rojo por 45 ms, menos de lo
# que se corre Not Your Baby.
ARR_MAL_PCT = 25.0
# Si el BPM de la tabla no es un multiplo limpio del de la cuadricula, las dos
# cuadriculas no son comparables y el arranque pasa a ser un aviso: no se sabe
# cual de las dos esta corrida.
RATIO_LIMPIO = 0.005
# Cuanto resuelve NUESTRA medicion independiente del BPM (`candidatos_bpm`).
# MEDIDO sobre las 119 canciones con .ogg: apoya al BPM de la tabla con 0.31%
# de error (mediana), 0.77% (p95) y 1.00% (la peor de las 119). O sea que no
# puede arbitrar una discusion mas fina que el 1%: si la tabla y Virtual DJ
# discrepan por menos que eso, esto no dice nada y la diferencia se avisa.
BPM_APOYO_MAX = 1.0


def racional_simple(ratio, qmax=4):
    """El p/q mas cercano a `ratio` con q <= qmax. Devuelve (p, q, error relativo).

    Separa dos cosas que el chequeo viejo del BPM mezclaba:

      * que el BPM de la tabla sea OTRO NIVEL METRICO del mismo pulso (x2, x4,
        x4/3...). Ahi el chart NO se corre nunca: las flechas caen igual sobre
        la musica, solo que mas juntas. Es lo que hace Softnyx con el x2 (18.4%
        de los pares) y con el x4 (In The City corre a 300 sobre una cancion de
        75 BPM; Light it up a 256 sobre una de 64).
      * que el BPM este MAL POR POCO (1.9742 en vez de 2). Ahi si se va
        corriendo, y cuanto mas larga la cancion, peor.
    """
    mejor = None
    for q in range(1, qmax + 1):
        p = int(round(ratio * q))
        if p < 1:
            continue
        e = abs(ratio - p / float(q))
        if mejor is None or e < mejor[2]:
            mejor = (p, q, e)
    if mejor is None:
        return 1, 1, 1.0
    p, q, e = mejor
    return p, q, e / (p / float(q))


def apoyo_bpm(ogg, bpm):
    """Cuanto apoya MI medicion del audio a este BPM (error relativo, en %).

    Es el tercero en discordia cuando la tabla y Virtual DJ no coinciden. No
    decide solo: ver BPM_APOYO_MAX. Se admite que el analizador haya enganchado
    la mitad, el doble, el triple o el cuadruple, que es lo que suele pasar.
    """
    if not ogg:
        return None
    try:
        cands = candidatos_bpm(str(ogg), 3)
    except Exception:
        return None
    if not cands or not bpm:
        return None
    return 100.0 * min(abs(c["bpm"] * k - bpm) / bpm
                       for c in cands for k in (0.5, 1.0, 2.0, 3.0, 4.0))


def bpm_que_cierran(pulso, largo_mision, cuantos=3, cerca=None):
    """Los BPM de tabla con los que CADA MISION arranca sobre una pulsacion.

    8.7: la mision dura `largo_mision x 60/BPM` y la pulsacion `60/pulso`, asi
    que la condicion es `BPM = largo_mision x pulso / k` con k entero. Se
    devuelven los que caen en el rango jugable: la ventana de tipeo no baja de
    VENTANA_MAL, que es la mas rapida de los 3912 charts oficiales (0.661 s,
    363 BPM, del LoveRitmo 2020). Antes el tope era 256 BPM y dejaba afuera
    opciones que el propio juego usa.
    """
    out = []
    tope = 240.0 / VENTANA_MAL          # 4 x 60 / ventana
    for k in range(1, 4 * largo_mision + 1):
        b = largo_mision * pulso / float(k)
        if 60.0 <= b <= tope:
            out.append(round(b, 2))
    out = sorted(set(out))
    if cerca:
        out.sort(key=lambda b: abs(b - cerca))
    return out[:cuantos]

# que dificultades usa Softnyx segun el BPM (medido en los 1038 charts)
DIF_POR_BPM = [(0, 100, (1, 4)), (100, 130, (2, 7)), (130, 160, (3, 8)),
               (160, 200, (4, 10)), (200, 400, (4, 10))]
NIVELES = [(1, 3, "inicial"), (4, 6, "basico"), (7, 10, "profesional")]


def nivel_de(est):
    for a, b, n in NIVELES:
        if a <= est <= b:
            return n
    return "?"


# EL CUTOFF. CORREGIDO EL 20/9/2026 con las tablas de LoveBeat KR y Steam, y da
# vuelta la lectura anterior: EL JUEGO ORIGINAL NO USA TRES VALORES REDONDOS.
#
#     tabla             valores distintos   con numeros grandes
#     LoveBeat KR            1156 de 1157        1157 de 1157
#     LoveBeat Steam          771 de  771         771 de  771
#     musictable 2016           3 de 1038           0 de 1038
#
# O sea que KR y Steam le ponen a CADA chart su propio numero, y el 2016 es la
# excepcion. Lo redondo es la costumbre de ESA version, no del juego.
#
# Y el numero grande no es cualquiera: va con CUANTO HAY QUE TOCAR. Medido sobre
# los 1928 charts de KR y Steam, `CutOff / (flechas + SPACE)` da 5730 y 5697 de
# mediana (las dos tablas casi iguales), y lo que menos se dispersa es
# `CutOff / cosas^1.15`, con 2530 y 2567. Igual queda +-33% de dispersion, asi
# que NO ES UNA FORMULA EXACTA: se comporta como un PUNTAJE, no como un codigo.
#
# SIGUE SIN ESTAR COMPROBADO que sea un puntaje, y no se puede comprobar hasta
# que el resumen del final deje de salir en 0 (15.2). Para una cancion nueva se
# sigue poniendo lo del 2016, que es la version que corre el juego de Joel.
#
# Lo de abajo es lo que hace el musictable 2016, uno por nivel:
#
#     inicial (1-3*)      30000   216 de 218
#     basico  (4-6*)      50000   455 de 460
#     profesional (7-10*) 70000   357 de 360
#
# PERO los charts del LoveRitmo 2020 que hay instalados (In The City, Light it
# up, Not Your Baby, Arabian Nights, Everlasting, NATURE, MUSIC WISADEL) ponen
# ahi numeros GRANDES, de 680.364 a 3.314.286. Y no son al azar: MEDIDO el
# 20/9/2026 sobre esas 15 filas, el valor sale a **unos 7.500 por FLECHA**
# (6.905 a 8.952 en 13 de las 15; las dos flojas son NATURE 4* y 6*). Contra
# los TIEMPOS no correlaciona (8.100 a 14.800).
#
# O sea que ahi el CutOff parece ser un PUNTAJE, no un codigo. NO ESTA
# COMPROBADO y no se puede comprobar todavia: el resumen del final sale con el
# puntaje en 0 (15.2). Hasta que eso se arregle, esto es una sospecha medida,
# no un hecho, y el programa solo AVISA.
CUTOFF_POR_COSA = 5700.0

# LA VENTANA PARA TIPEAR: los 4 PRIMEROS tiempos de cada mision (7.1), o sea
# `4 x 60 / BPM_de_la_fila`. Los otros 12 el personaje baila.
#
# LA REGLA VIEJA ERA "no bajar de 0.94 s (BPM <= 256)" y estaba puesta por
# prudencia, no medida: 8.4.1 dice textualmente "entre esos dos valores no hay
# medicion; lo seguro es no bajar de 0.94". MEDIDO el 20/9/2026 contra los 1038
# charts de Softnyx, que es lo que faltaba mirar:
#
#     la mas rapida de las 1038 .... 0.727 s (330 BPM)
#     p1 ........................... 0.918 s
#     p5 ........................... 1.000 s
#     mediana ...................... 1.714 s
#     por debajo de 0.94 s ......... 36 de 1038 (3.5%)
#     por debajo de 0.80 s ......... 3 de 1038
#
# O sea que Softnyx SI baja de 0.94, y el liston estaba por encima de lo que
# hace el propio juego. Y hay charts instalados que Joel dice que le funcionan
# con la ventana en 0.800 s (In The City y Not Your Baby, los dos a 300 BPM).
#
# LO QUE SIGUE SIENDO CIERTO, y es lo unico medido JUGANDO: Gee a 400 BPM
# (ventana 0.600 s) saco 0 PUNTOS EN 75 DE 75 MISIONES.
#
# Entre 0.727 y 0.918 hay evidencia para los dos lados: In The City y Not Your
# Baby andan a 0.800, pero APT a 0.805 Joel la rechazo. Por eso esa franja es
# amarilla: se decide jugando, no con una tabla.
#
# RECALIBRADO el 20/9/2026 con TRES tablas oficiales, no una. Joel trajo los
# musictable de LoveBeat KR (1157 filas) y de LoveBeat Steam (771). Con los 1038
# de 2016 son 2966 charts, y el piso baja:
#
#     tabla              mas rapida    p1
#     2016                 0.727 s    0.918 s
#     LoveBeat Steam       0.795 s    0.833 s
#     LoveBeat KR          0.690 s    0.732 s
#     LoveRitmo 2020       0.661 s    0.750 s   <- el piso de verdad (363 BPM)
#     LAS CUATRO JUNTAS    0.661 s    0.750 s
#
# Y en LB KR hay un chart a 346 BPM / 0.6936 s en 6 y en 10 estrellas: ES MUSIC
# WISADEL, la misma que el Estudio marcaba en rojo por rapida. O sea que el
# juego original la publica tal cual. El rojo estaba mal puesto.
VENTANA_OK = 0.750        # el p1 de los 3912: arriba esta el 99% de lo oficial
VENTANA_MAL = 0.660       # por debajo del mas rapido de los 3912 (0.661)


def cutoff_de(est):
    return 30000 if est <= 3 else (50000 if est <= 6 else 70000)


_CONVERTIDAS = None


def convertidas():
    """Los nombres que convertimos nosotros, segun el registro de claves."""
    global _CONVERTIDAS
    if _CONVERTIDAS is None:
        try:
            _CONVERTIDAS = set(json.loads(
                (PRIV / REGISTRO).read_text(encoding="utf-8")))
        except Exception:
            _CONVERTIDAS = set()
    return _CONVERTIDAS


# ================== LO QUE CREO EL ESTUDIO: `mias.json` (22/9/2026) ==================
# LA PROTECCION NO ANDABA EN EL CLIENTE 2020: protegia 8 filas de 251. Las dos
# senales que se usaban fallan ahi, y por la misma razon: el paquete 2020 metio
# el audio de SUS canciones en la misma carpeta que las nuestras (`Elton\mana`)
# y las registro con la misma clave (`snb_local_2020.json`, 566 nombres). Para
# el programa, Head Down o Loverholic eran "de Joel", y se les podia regenerar
# el chart y perderlo.
#
# LA UNICA SENAL LIMPIA HOY ES EL NUMERO: `agregar_ogg` y `copiar_cancion`
# nombran desde bkg2800 para arriba. Medido: en las dos tablas instaladas, lo
# que cae en 2800-9999 es exactamente lo de Joel. PERO no sirve como regla para
# siempre: LoveBeat KR usa 391 nombres en ese rango (bkg2831, bkg2891, bkg2900),
# y el dia que se instale una de esas pasaria por nuestra.
#
# Asi que el numero se usa UNA vez, para arrancar, y de ahi en mas manda un
# registro EXPLICITO: `mias.json`, al lado del programa, con cada nombre que
# crea el Estudio. Lo que no esta ahi, vino con el juego y no se toca.
MIAS = ESTUDIO / "mias.json"
_MIAS = None


def _es_del_rango(nombre):
    import re as _re
    m = _re.match(r"bkg(\d+)$", nombre or "")
    return bool(m) and 2800 <= int(m.group(1)) < 10000


def mias(tabla=None):
    """Los nombres de las canciones que creo el Estudio. Se arma una vez."""
    global _MIAS
    if _MIAS is not None:
        return _MIAS
    if MIAS.exists():
        try:
            _MIAS = set(json.loads(MIAS.read_text(encoding="utf-8"))["nombres"])
            return _MIAS
        except Exception:
            pass
    # ARRANQUE: lo de la tabla en el rango del Estudio, mas los .ogg del rango
    # que haya en la carpeta de audios nuevos (una cancion creada con una
    # ventana vieja, que no llego a anotarse).
    semilla = set()
    if tabla is not None:
        semilla |= set(f["Filename"] for f in tabla.filas
                       if _es_del_rango(f["Filename"]))
    if OGG_NUEVOS.is_dir():
        semilla |= set(p.stem for p in OGG_NUEVOS.glob("bkg*.ogg")
                       if _es_del_rango(p.stem))
    _MIAS = semilla
    _guardar_mias()
    return _MIAS


def _guardar_mias():
    try:
        MIAS.write_text(json.dumps(
            {"nombres": sorted(_MIAS),
             "_nota": "Las canciones que creo el Estudio. Lo que NO esta aca "
                      "vino con el juego y el programa no lo deja tocar."},
            indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def anotar_mia(nombre):
    """El Estudio acaba de crear esta cancion: queda anotada como nuestra."""
    m = mias()
    if nombre not in m:
        m.add(nombre)
        _guardar_mias()


def es_original(fila):
    """True si la cancion vino con el juego. REGLA: esas no se tocan nunca.

    Desde el 22/9/2026 lo decide `mias.json` (ver arriba). Antes se miraba el
    registro de claves y la carpeta de audios, y en el cliente 2020 las dos
    decian que TODO era nuestro.
    """
    return fila["Filename"] not in mias()


# ===================== DE DONDE SALIO EL CHART (20/9/2026) =====================
# `es_original()` contesta "convertimos nosotros el audio de esta cancion?", que
# es lo que hace falta para saber si se le puede tocar el .ogg. NO contesta
# "este chart lo hicimos nosotros?", y durante meses se uso como si contestara
# las dos cosas. Por eso MUSIC WISADEL, que es un chart de LoveBeat KR, sale
# como "tuya": le convertimos el audio nosotros.
#
# Esto contesta la otra pregunta, y la contesta bien: compara el CHART ENTERO
# (`MissionID1` + `Length`) contra las cuatro tablas oficiales. No depende del
# nombre del archivo ni del titulo, asi que sobrevive a que lo hayamos renombrado
# - que es justo lo que hizo fallar la comparacion de 15B.2, que dio 0 porque
# comparaba los `bkgNNNN` que renombramos nosotros.
VERSIONES = [
    ("musictable_2016", "el musictable de 2016"),
    ("musictable_LB_KR", "LoveBeat KR"),
    ("musictable_LB_STEAM", "LoveBeat Steam"),
    ("musictablel2020", "el LoveRitmo 2020"),
]
_ORIGENES = None


def _indice_oficial():
    r"""{(MissionID1, Length): (version, titulo)} de las tablas que haya.

    Se arma una sola vez y se guarda en `_cache`. Si no hay tablas de referencia
    en `musictables_referencia\`, queda vacio y todo sigue andando igual: el
    origen pasa a ser "no se".
    """
    global _ORIGENES
    if _ORIGENES is not None:
        return _ORIGENES
    cach = CACHE / "_origenes.json"
    try:
        if cach.exists():
            d = json.loads(cach.read_text(encoding="utf-8"))
            _ORIGENES = dict((tuple(k.split("\x00")), tuple(v))
                             for k, v in d.items())
            return _ORIGENES
    except Exception:
        pass
    _ORIGENES = {}
    try:
        sys.path.insert(0, str(ESTUDIO))
        import referencias as _R
        tablas, _p, _r = _R.todas()
    except Exception:
        return _ORIGENES
    for clave, etiqueta in VERSIONES:
        filas = tablas.get(clave)
        if not filas:
            continue
        for f in filas:
            m1 = str(f.get("MissionID1") or "").strip()
            lg = str(f.get("Length") or "").strip()
            if len(m1) < 20:            # charts de juguete: no identifican nada
                continue
            _ORIGENES.setdefault((m1, lg), (etiqueta, (f.get("Title") or "").strip()))
    try:
        cach.write_text(json.dumps(dict(("\x00".join(k), list(v))
                                        for k, v in _ORIGENES.items())),
                        encoding="utf-8")
    except Exception:
        pass
    return _ORIGENES


def origen_del_chart(fila):
    """De que version del juego salio este chart, o None si es nuestro.

    Devuelve (version, titulo_alla) o None.
    """
    idx = _indice_oficial()
    if not idx:
        return None
    clave = (str(fila.get("MissionID1") or "").strip(),
             str(fila.get("Length") or "").strip())
    if len(clave[0]) < 20:
        return None
    return idx.get(clave)



# ============ QUE ESTRELLAS USA SOFTNYX EN CADA NIVEL (22/9/2026) ============
# Hasta hoy el programa sabia dos cosas: la mediana de la "facil" y la de la
# "dificil" a cada BPM. Joel pidio elegir por NIVEL, asi que se midio la mediana
# DE CADA NIVEL por separado, sobre los 3912 charts oficiales de las cuatro
# tablas juntas (2016, LoveBeat KR, Steam y LoveRitmo 2020):
#
#     BPM          inicial      basico    profesional
#     0-100        2 (240)      5 (59)       7 (4)
#     100-130      3 (304)      5 (361)      7 (114)
#     130-160      3 (113)      4 (495)      8 (274)
#     160-200      3 (15)       4 (404)      8 (358)
#     200-400      NINGUNA      6 (506)     10 (665)
#
# (entre parentesis, cuantos charts sostienen cada numero)
#
# OJO CON LA ULTIMA FILA: de 200 BPM para arriba Softnyx **no hace ni una sola
# version inicial**, en 1171 charts. Tiene sentido: a esa velocidad la ventana
# para tipear dura menos de 1.2 s y una version de 1-3 estrellas no entra. Por
# eso ahi se devuelve None y el programa lo dice en vez de inventar un numero.
#
# Y SE PUEDEN HACER LAS TRES: no es un invento nuestro. En el musictable 2016,
# que es el que corre este juego, hay 11 canciones con los tres niveles; en
# LoveBeat KR son 123. El juego acepta cuantas filas quiera una cancion.
ESTRELLA_POR_NIVEL = [
    (0, 100, {"inicial": 2, "basico": 5, "profesional": 7}),
    (100, 130, {"inicial": 3, "basico": 5, "profesional": 7}),
    (130, 160, {"inicial": 3, "basico": 4, "profesional": 8}),
    (160, 200, {"inicial": 3, "basico": 4, "profesional": 8}),
    (200, 400, {"inicial": None, "basico": 6, "profesional": 10}),
]


def estrellas_de_nivel(bpm, nivel):
    """Las estrellas que pone Softnyx en ese nivel a ese BPM, o None.

    None quiere decir "a esta velocidad Softnyx no hace esa version", y no es
    una falta de datos: de 200 BPM para arriba no hay NI UNA de 1-3 estrellas
    en 1171 charts oficiales.
    """
    d = next((v for a, b, v in ESTRELLA_POR_NIVEL if a <= bpm < b), None)
    if not d:
        d = ESTRELLA_POR_NIVEL[-1][2]
    est = d.get(nivel)
    if est is None:
        return None
    lo, hi = rango_estrellas(bpm)
    a, z = next(((a, z) for a, z, n in NIVELES if n == nivel), (1, 10))
    return max(a, min(z, max(lo, min(hi, est))))

def rango_estrellas(bpm):
    return next((v for a, b, v in DIF_POR_BPM if a <= bpm < b), (1, 10))


def bolsas_keypattern(n, dificultad, semilla=None):
    """KeyPatternID de cada mision.

    MEDIDO en las 1038 filas: la bolsa 4 domina en TODAS las dificultades (64.6%
    en dif 1, 78.8% en dif 10). Lo que cambia con la dificultad es la bolsa 1 (la
    de las repeticiones), que baja de 16.4% a 4.6%.
    """
    r = random.Random((1000 + dificultad) if semilla is None else semilla)
    b1 = 16.4 - (dificultad - 1) * (16.4 - 4.6) / 9.0
    b4 = 64.6 + (dificultad - 1) * (78.8 - 64.6) / 9.0
    resto = max(0.0, 100.0 - b1 - b4)
    pesos = {1: b1, 2: resto * 0.35, 3: resto * 0.65, 4: b4}
    op = list(pesos)
    return [r.choices(op, weights=[pesos[o] for o in op])[0] for _ in range(n)]


def _ciclar(vals, n):
    if not vals:
        return ["0"] * n
    return [vals[i % len(vals)] for i in range(n)]


# ================================= LAS MISIONES LARGAS: SEGUIR LAS FRASES (22/9/2026)
# Softnyx NO hace todas las misiones de 16 tiempos. MEDIDO:
#
#     charts oficiales con alguna mision de 20, 24, 28 o 32 ...... 711 de 1038 (68%)
#     en el musictable del 2020 ................................. 146 de 247
#     el Estudio hasta hoy ...................................... 0: todas de 16
#
# Y no las pone al azar. Midiendo el audio de 732 charts oficiales, la mision
# que ARRANCA DESPUES DE UNA LARGA cae donde la cancion cambia de seccion: la
# novedad del sonido ahi es 1.73, contra 0.63 en un arranque comun. Si esos
# charts hubieran seguido todo en 16, sus arranques caerian en 0.42. O sea: la
# mision larga es como Softnyx VUELVE A AGARRAR LA FRASE cuando la cancion mete
# un compas de mas (un puente, un corte, una intro del coro). Es lo que se oye
# en Everlasting: 16,16,32,...,24,...
#
# ADIVINARLO SOLO, validado mitad y mitad (elegir el castigo en una mitad,
# puntuar en la otra), sobre 569 charts oficiales:
#
#     arranques oficiales que acierta ... todo en 16: 75%   con esto: 80.5%
#     charts que mejoran / empeoran ..... 147 / 105
#     misiones largas que pone .......... 237, y el 45% cae donde Softnyx puso una
#
# Mejora, pero la mitad de las largas que pone no son las de Softnyx. Por eso es
# una PROPUESTA: el mapa las muestra y se corrigen a mano (Shift + clic).
LARGOS_FRASE = (16, 20, 24, 28, 32)
FRASE_CASTIGO = 6.0      # lo que tiene que ganar una larga para ponerse (4 a 8 dan igual)


def _novedad_en(rej, t, ven=0.25):
    nov = rej.get("novedad") or []
    fps = rej.get("nov_fps") or 0.0
    if not nov or not fps:
        return 0.0
    a, b = int((t - ven) * fps), int((t + ven) * fps) + 1
    s = nov[max(0, a):max(0, b)]
    return max(s) if s else 0.0


def largos_auto(rej, inicio, bpm, fin):
    """Los largos de mision que hacen caer cada arranque donde la cancion cambia.

    Programacion dinamica: de todas las formas de cubrir la cancion con misiones
    de 16 a 32 tiempos, la que suma mas novedad en los arranques, pagando
    FRASE_CASTIGO por cada una que no mida 16. El final queda como con todas de
    16: la ultima mision entra entera y sobran menos de 16 tiempos.
    """
    per = 60.0 / bpm
    total = int((fin - inicio) / per + 1e-6)
    ultimo = total - 16                      # donde puede arrancar la ultima
    if ultimo < 16 or not rej.get("novedad"):
        return [16] * max(1, total // 16)
    NEG = -1e18
    best = [NEG] * (ultimo + 1)
    prev = [None] * (ultimo + 1)
    best[0] = 0.0
    for pos in range(0, ultimo + 1, 4):
        if best[pos] == NEG:
            continue
        for L in LARGOS_FRASE:
            q = pos + L
            if q > ultimo:
                break
            sc = (best[pos] - (FRASE_CASTIGO if L != 16 else 0.0)
                  + _novedad_en(rej, inicio + q * per))
            if sc > best[q]:
                best[q], prev[q] = sc, (pos, L)
    finales = [q for q in range(max(0, ultimo - 15), ultimo + 1) if best[q] > NEG]
    q = max(finales, key=lambda k: best[k])
    out = [16]                               # la ultima
    while q > 0:
        pos, L = prev[q]
        out.append(L)
        q = pos
    return out[::-1]


def largos_por_frases(inicio, bpm, fin, frases, ritmos=()):
    """Los largos de mision para que una mision ARRANQUE en cada frase pedida.

    `frases` son SEGUNDOS, no numeros de mision: asi valen igual para la facil y
    para la dificil aunque una este al doble de BPM (el caso del x2). Cada frase
    se redondea al tiempo multiplo de 4 mas cercano, y si queda a menos de 16
    tiempos de la mision anterior no se puede alcanzar y se saltea.

    `ritmos` (27/9/2026, "el ritmo sigue desde aca"): segundos donde la cancion
    se CORRE y el compas vuelve a contar desde ahi. Esos se redondean al TIEMPO
    mas cercano (no al multiplo de 4), y las frases que vienen despues cuentan
    de a 4 desde el ultimo ritmo, no desde el arranque. Es lo que hace Softnyx
    con sus misiones de 18, 21 y 26 tiempos (12 de 237 charts oficiales).
    """
    per = 60.0 / bpm
    total = int((fin - inicio) / per + 1e-6)
    origenes = []
    for x in sorted(ritmos or ()):
        b = int(round((x - inicio) / per))
        # hace falta una mision entera antes, y dos ritmos a menos de una
        # mision no se pueden cumplir los dos: queda el primero
        if b >= 16 and (not origenes or b - origenes[-1] >= 16):
            origenes.append(b)
    objetivos = set(origenes)
    for f in frases:
        if f <= inicio:
            continue
        fb = (f - inicio) / per
        o = max([0] + [b for b in origenes if b <= fb + 0.5])
        objetivos.add(o + int(round((fb - o) / 4.0)) * 4)
    # una frase comun a menos de una mision ANTES de un ritmo haria que el ritmo
    # quede inalcanzable: manda el ritmo
    objetivos = sorted(b for b in objetivos
                       if b in origenes or not any(0 < o - b < 16 for o in origenes))
    pos, out = 0, []
    while pos + 16 <= total:
        L = 16
        for b in objetivos:
            g = b - pos
            if g < 16:
                continue
            # se alarga LA DE JUSTO ANTES de la frase. Si faltan 32 o mas, esta
            # va de 16 y se llega despues: una de 32 llega al mismo lugar que
            # dos de 16 pero se come una ventana de flechas (eso es una PAUSA,
            # y para eso esta "quitar la mision").
            if g < 32:
                L = g
            break
        if pos + L + 16 > total and pos + 16 <= total:
            L = 16                  # la ultima entra entera, como siempre
        out.append(L)
        pos += L
    return out or [16]


# ============================ QUE EL PERSONAJE NO SE QUEDE CAMINANDO (23/9/2026)
# Joel: "algunas partes en vez de bailar se queda caminando, y hasta que salga la
# siguiente tabla de flechas ahi baila". Empezo cuando el Estudio empezo a hacer
# misiones largas (6.3.23).
#
# LA CAUSA: los bailes estan hechos a medida de una mision de 16 tiempos. En
# `DanceTable\<bpm>\*_dancetable_dance` cada numero de baile tiene animaciones
# llamadas D_M_2_6 / D_S_2_6 (511/611) y D_M_1_7 / D_S_1_7 (501/601): tipeo +
# baile = 2+6 o 1+7 = 8 partes = 16 tiempos. MEDIDO por el tamano de los .ab:
# descontando la parte fija, D_S_1_7 / D_S_2_6 = 1.12 (7/6 = 1.17) y D_M_2_6 es
# el doble de D_M_1_7. No hay ningun baile mas largo, y Softnyx usa los mismos
# numeros en sus misiones largas (79% 511/611, igual que en las de 16). O sea que
# en una mision de 24 el baile termina a los 16 y el personaje camina 8.
#
# EL ARREGLO: la frase se sigue igual, pero la mision larga se PARTE en piezas
# de 8 a 16 (24 = 16 + 8, 20 = 12 + 8, 28 = 16 + 12, 32 = 16 + 16). Cada pieza
# trae su baile entero. Las misiones de 8 funcionan: Joel las jugo y le gustaron
# (Don't Stop K "rafagas", 15/9/2026). La de 12 no se jugo nunca.
# Lo que agrega: la pieza corta tiene su ventana de flechas.
#
# LOS DESCANSOS NO SE PARTEN: ahi no tiene que salir nada, y una ventana vacia
# el juego la llena de SPACE. En un descanso el personaje camina, igual que en las
# pausas de Softnyx.
SIN_CAMINAR = True       # lo cambia la casilla del Estudio


def partir_largas(largos):
    """Cada mision de mas de 16 tiempos, partida en piezas de 8 a 16."""
    out = []
    for L in largos:
        while L > 16:
            if L - 16 >= 8:
                out.append(16)
                L -= 16
            else:
                out.append(L - 8)       # 20 -> 12 + 8
                L = 8
        out.append(L)
    return out


def agrupar_largos(largos):
    """Al reves, para MOSTRAR: junta las piezas cortas con su mision.

    Devuelve listas de indices. [16, 8] es un grupo de 24; [12, 8] uno de 20;
    [16, 12] uno de 28. Una corta sola que no llega a 16 se pega a la de antes.
    """
    grupos, i, n = [], 0, len(largos)
    while i < n:
        if largos[i] < 16:
            j, s = i, 0
            while j < n and largos[j] < 16:
                s += largos[j]
                j += 1
            run = list(range(i, j))
            if s < 16 and grupos:
                grupos[-1].extend(run)
            else:
                grupos.append(run)
            i = j
        else:
            grupos.append([i])
            i += 1
    return grupos


def frases_de_largos(inicio, bpm, largos):
    """Al reves: en que segundo arranca cada mision que viene despues de una larga
    (las piezas partidas cuentan como una sola)."""
    per = 60.0 / bpm
    t, out = float(inicio), []
    grupos = agrupar_largos(largos)
    for g in grupos[:-1]:
        L = sum(largos[i] for i in g)
        t += L * per
        if L != 16:
            out.append(round(t, 4))
    return out


# ================================== LOS DESCANSOS: QUE NO SALGA NADA (22/9/2026)
# Pedido de Joel: donde la cancion se corta o el ritmo para, que no venga ni
# flecha ni SPACE.
#
# VACIAR LA MISION NO SIRVE: el juego pone un SPACE en cada tiempo sin flechas
# (6.3.1.1, comprobado jugando), asi que una mision vacia sale con 4 SPACE. Lo
# unico que deja la pantalla limpia es que en ese tramo NO ARRANQUE NINGUNA
# MISION: la de antes se alarga y el personaje baila por encima. Es lo que hace
# Softnyx con sus misiones de 32 a 96 tiempos, y a Joel las pausas de 32 le
# gustaron jugando (15/9/2026).
#
# Se saltean las misiones cuya ventana cae en el tramo, y nada mas: la que
# sigue arranca donde iba a arrancar, asi no se pierde la frase. (El viejo
# `--descanso` de editar_cancion.py dimensionaba la larga para cubrir el tramo
# entero y a BPM alto salian misiones de 40 a 48 tiempos con musica fuerte.)
LARGO_MAX = 96           # la mas larga que usa Softnyx


def _pisa(t, largo, tramos):
    """La ventana [t, t+largo) cae en alguno de los tramos (mas del 25%)."""
    for a, b in tramos:
        solape = min(t + largo, b) - max(t, a)
        if solape > 0.25 * min(largo, b - a):
            return True
    return False


def saltar_descansos(largos, inicio, bpm, tramos):
    """Quita las misiones cuya ventana cae en un descanso y alarga la de antes."""
    out, n, _idx = saltar_descansos_idx(largos, inicio, bpm, tramos)
    return out, n


def saltar_descansos_idx(largos, inicio, bpm, tramos):
    """Igual, pero dice ademas QUE MISION VIEJA quedo en cada lugar.

    Hace falta para aplicar los descansos a un chart YA HECHO sin volver a
    sortear las flechas (`aplicar_descansos`): cada mision que sobrevive se
    queda con las flechas que ya tenia.
    """
    per = 60.0 / bpm
    arr, a = [], 0
    for L in largos:
        arr.append(a)
        a += L
    fin_total = a
    quedan = [0]                      # la primera no tiene a quien alargar
    salteadas = []
    for s in arr[1:]:
        if _pisa(inicio + s * per, 4 * per, tramos):
            salteadas.append(s)
            continue
        # tope: si el hueco pasa de LARGO_MAX, se deja alguna salteada
        while s - quedan[-1] > LARGO_MAX:
            r = [x for x in salteadas if quedan[-1] + 16 <= x <= quedan[-1] + LARGO_MAX]
            if not r:
                break
            quedan.append(max(r))
        quedan.append(s)
    out = [q2 - q1 for q1, q2 in zip(quedan, quedan[1:])]
    ultimo = quedan[-1]
    out.append(largos[arr.index(ultimo)] if ultimo in arr else 16)
    idx = [arr.index(q) for q in quedan]
    return out, len(arr) - len(quedan), idx


# Donde se corta el ritmo: los graves por debajo del 30% de lo normal de la
# cancion durante 1.5 s o mas. Es la regla de los bajones que ya se usaba a mano
# (9.0 paso 6: 30% y 1.2 s); el 1.5 es para no marcar un golpe de platillo.
# Es una PROPUESTA: el mapa la muestra y cada una se saca con un clic.
CORTE_GRAVES, CORTE_SEG = 0.30, 1.5


def cortes_de_ritmo(rej, desde, hasta):
    """Los tramos (segundos) donde el ritmo se va, entre `desde` y `hasta`."""
    g = rej.get("graves") or []
    if not g:
        return []
    a, b = max(0, int(desde)), min(len(g), int(hasta) + 1)
    cuerpo = sorted(g[a:b]) or sorted(g)
    med = cuerpo[len(cuerpo) // 2] or 1.0
    out, ini = [], None
    for i in range(a, b):
        bajo = g[i] < CORTE_GRAVES * med
        if bajo and ini is None:
            ini = i
        elif not bajo and ini is not None:
            if i - ini >= CORTE_SEG:
                out.append((float(ini), float(i)))
            ini = None
    if ini is not None and b - ini >= CORTE_SEG:
        out.append((float(ini), float(b)))
    return out


BAILE_MISION, BAILE_BIEN = "511", "611"     # los que no hacen caminar (6.3.39)
BAILE_CAMBIO = {"MissionDanceID": ("501", BAILE_MISION),
                "MissionSuccessDanceID": ("601", BAILE_BIEN)}


BAILE_MODOS = ("todo", "sin_flechas", "solo501")


def aplicar_descansos(fila, mudos, descanso, bpm=None):
    """Pone los descansos en el chart QUE YA ESTA, sin volver a sortear nada.

    Pedido de Joel (25/9/2026): *"¿podrás crear una opción que solo la música
    que se modifique lo de los descansos y enviar así nomás?"*. GENERAR EL CHART
    rehace las flechas de toda la cancion, y aunque el sorteo usa semilla fija,
    en 6 de 23 filas salio distinto (6.3.32). Si la cancion ya gusta, eso es un
    riesgo que no hace falta correr para sacar un pedazo.

    Es el mismo camino que `arreglar_baile` y `recortar_filas`: se toma el chart
    tal como esta y se lo transforma. Los dos modos del paso 3 del mapa:

      * `descanso=True`  ("no sale nada, camina"): se saltean las misiones cuya
        ventana cae en el tramo y se alarga la de antes (`saltar_descansos_idx`).
        Cada mision que sobrevive **se queda con SUS flechas**.
      * `descanso=False` ("sigue bailando, salen SPACE"): las misiones que se
        solapan con el tramo se vacian (MissionID1 en "1" = 4 SPACE, y sin
        segunda tanda: MissionID2 en "0") y no se mueve ningun tiempo. Es el
        mismo criterio de solape del 25% que usa `generar`, para que un tramo
        valga igual en la facil y en la dificil.

    NO toca el arranque, ni el BPM, ni las estrellas, ni `Second`. Devuelve
    (listas nuevas o None si no hay nada que hacer, un resumen para el log).
    """
    if not mudos:
        return None, "no hay ningun tramo marcado"
    bpm = float(bpm or fila["BPM"])
    per = 60.0 / bpm
    inicio = float(fila["StartDelayTime"] or 0)
    listas = dict((c, [v for v in str(fila.get(c) or "").split(",") if v.strip()])
                  for c in LISTAS)
    L = [int(float(x)) for x in listas["Length"]]
    if not L:
        return None, "esta fila no tiene chart"

    if descanso:
        nuevos_largos, saltadas, idx = saltar_descansos_idx(L, inicio, bpm, mudos)
        if not saltadas:
            return None, "los tramos no pisan ninguna mision"
        nuevas = dict((c, [listas[c][i] if i < len(listas[c]) else "0" for i in idx])
                      for c in LISTAS)
        nuevas["Length"] = [str(x) for x in nuevos_largos]
        resumen = ("%d misiones salteadas: quedan %d (antes %d)"
                   % (saltadas, len(nuevos_largos), len(L)))
    else:
        arr, a = [], 0
        for x in L:
            arr.append(a)
            a += x
        nuevas = dict((c, list(v)) for c, v in listas.items())
        calladas = 0
        for i, x in enumerate(L):
            t = inicio + arr[i] * per
            largo = x * per
            for aa, bb in mudos:
                solape = min(t + largo, bb) - max(t, aa)
                if solape > 0.25 * min(largo, bb - aa):
                    if i < len(nuevas["MissionID1"]) and nuevas["MissionID1"][i] != "1":
                        calladas += 1
                    if i < len(nuevas["MissionID1"]):
                        nuevas["MissionID1"][i] = "1"
                    if i < len(nuevas["MissionID2"]):
                        # sin segunda tanda ("1" serian otros 4 SPACE, 2/10/2026)
                        nuevas["MissionID2"][i] = "0"
                    break
        if not calladas:
            return None, "los tramos no pisan ninguna mision"
        resumen = "%d misiones vaciadas (siguen bailando, con SPACE)" % calladas

    # la camara del final va en la ultima, como en `generar` y `recortar_filas`
    if nuevas["DanceCameraID"]:
        nuevas["DanceCameraID"][-1] = "241"
    if nuevas["MissionCameraID"]:
        nuevas["MissionCameraID"][0] = "101"
    n = len(nuevas["Length"])
    for c in LISTAS:                      # que las 10 midan lo mismo
        v = nuevas[c]
        nuevas[c] = (v + [v[-1] if v else "0"] * (n - len(v)))[:n]
    return dict((c, ",".join(v)) for c, v in nuevas.items()), resumen


def arreglar_baile(fila, modo="todo"):
    """Que el personaje no camine, SIN volver a generar el chart (24/9/2026).

    `modo` (25/9/2026, pedido de Joel: "sin alterar el orden de las flechas"):
      * "todo"        -> lo de abajo;
      * "sin_flechas" -> igual, pero TODA pieza nueva va sin flechas (SPACE),
                         tambien en las frases: no aparece ninguna flecha nueva;
      * "solo501"     -> no parte nada: solo cambia el baile 501/601 -> 511/611.
                         Lo que se juega queda 100% igual.

    Joel ya tenia canciones "perfectas en sincronizacion" con descansos o frases
    largas viejas, y el personaje caminaba ahi (6.3.28 / 6.3.30). Regenerarlas
    no sirve: en 6 de 23 filas el sorteo sale distinto. Esto toma el chart TAL
    COMO ESTA y solo parte cada mision de mas de 16 tiempos (`partir_largas`):

      * un DESCANSO (32 o mas) -> piezas SIN flechas: el juego pone SPACE y el
        personaje sigue bailando;
      * una FRASE vieja (20 a 28) -> la pieza nueva repite las flechas de esa
        misma mision.

    Todas las demas misiones quedan identicas y ningun tiempo se mueve (la suma
    de los Length no cambia). Devuelve (listas nuevas o None, que se hizo).
    """
    listas = dict((c, [v for v in str(fila.get(c) or "").split(",") if v.strip()])
                  for c in LISTAS)
    L = [int(float(x)) for x in listas["Length"]]
    assert modo in BAILE_MODOS, modo
    n501 = sum(1 for v in listas["MissionDanceID"] if v.strip() == "501")
    partir = modo != "solo501"
    if not (partir and any(x > 16 for x in L)) and not n501:
        return None, []
    per = 60.0 / float(fila["BPM"])
    nuevas = dict((c, []) for c in LISTAS)
    hecho = []
    for i, x in enumerate(L):
        vals = dict((c, listas[c][i]) for c in LISTAS)
        if x <= 16 or not partir:
            for c in LISTAS:
                nuevas[c].append(vals[c])
            continue
        piezas = partir_largas([x])
        descanso = x >= 32
        vacias = descanso or modo == "sin_flechas"
        hecho.append((i + 1, x, "descanso" if descanso else "frase",
                      (x - 16) * per, "+".join(str(p) for p in piezas)))
        ultima_de_todas = (i == len(L) - 1)
        for k, pz in enumerate(piezas):
            for c in LISTAS:
                v = vals[c]
                if k > 0:
                    if c == "MissionID1" and vacias:
                        v = "1"                 # sin flechas: el juego pone SPACE
                    elif c == "MissionID2" and vacias:
                        v = "0"                 # y sin segunda tanda (2/10/2026)
                    elif c == "MissionCameraID":
                        v = "0"
                    elif c == "DanceCameraID":
                        v = "0"
                if c == "DanceCameraID" and ultima_de_todas:
                    # la camara del final (241) va en la ULTIMA pieza
                    v = vals[c] if k == len(piezas) - 1 else "0"
                if c == "Length":
                    v = str(pz)
                nuevas[c].append(v)
    assert sum(int(v) for v in nuevas["Length"]) == sum(L)
    # y los bailes 501/601, que hacen caminar al personaje en medio de la mision
    for c, (viejo, nuevo) in BAILE_CAMBIO.items():
        nuevas[c] = [nuevo if v.strip() == viejo else v for v in nuevas[c]]
    if n501:
        hecho.append((0, 0, "baile501", 0.0, "%d misiones con el baile 501" % n501))
    return dict((c, ",".join(v)) for c, v in nuevas.items()), hecho


def bajar_tres(fila):
    """En una rapida (ver BPM_SIN_TRES), cada tiempo con 3 flechas pasa a 2, SIN
    regenerar: en el mismo tiempo y con el mismo orden (27/9/2026). Desde el
    2/10/2026 tambien en la segunda tanda (MissionID2), que antes se salteaba.
    Devuelve (listas nuevas o None, cuantas tandas cambiaron)."""
    try:
        est = int(float(fila.get("Difficulty") or 0))
    except ValueError:
        return None, 0
    if not tope_por_bpm(fila.get("BPM"), est):
        return None, 0
    out, n = {}, 0
    for col in ("MissionID1", "MissionID2"):
        vals = [v.strip() for v in str(fila.get(col) or "").split(",") if v.strip()]
        nuevo, cambio = [], 0
        for v in vals:
            c = patron(v)
            if max(c) >= 3:
                c = [min(x, 2) for x in c]
                v = str(1 + c[0] * 125 + c[1] * 25 + c[2] * 5 + c[3])
                cambio += 1
            nuevo.append(v)
        if cambio:
            out[col] = ",".join(nuevo)
            n += cambio
    if not n:
        return None, 0
    return out, n


MEZCLA_501 = (15, 25, 35)     # los % que ofrece el menu; Softnyx usa 20-30%


def mezclar_bailes(fila, porcentaje):
    """Mas variedad de baile: pasa una parte de las misiones al 501/601 (27/9/2026).

    Joel: *"baila un mismo baile, como puedo utilizar mas bailes?"*. El numero del
    chart no elige el baile: es el TIPO. Al empezar cada mision el juego sortea uno
    de ese tipo (log del 27/9: 27 bailes distintos en 31 misiones de Kulipandeo).
    Todos los 511 (D_M_2_6) arrancan con la misma pose; el 501 (D_M_1_7) es la
    otra familia de pasos. Softnyx lo usa en el 20-30% de sus misiones.

    RIESGO: en Feather (247 BPM) las 13 veces que el personaje camino fueron en
    misiones 501 (6.3.39). Por eso es una eleccion, no lo que hace `generar`.

    Solo toca MissionDanceID y MissionSuccessDanceID: las flechas, los SPACE y
    los tiempos quedan iguales. Primero vuelve todo a 511/611, asi repetirlo con
    otro % no acumula, y `porcentaje` 0 saca la mezcla. Van al 501 solo misiones
    de 16 tiempos con flechas (no descansos ni piezas cortas), repartidas por la
    cancion y siempre las mismas para una fila (semilla = ID).
    Devuelve (listas nuevas o None si no cambia nada, cuantas quedaron en 501).
    """
    import random
    listas = dict((c, [v.strip() for v in str(fila.get(c) or "").split(",") if v.strip()])
                  for c in LISTAS)
    L = [int(float(x)) for x in listas["Length"]]
    if not L:
        return None, 0
    danza = [BAILE_MISION if v == "501" else v for v in listas["MissionDanceID"]]
    bien = [BAILE_BIEN if v == "601" else v for v in listas["MissionSuccessDanceID"]]
    aptas = [i for i, x in enumerate(L)
             if x == 16 and i < len(danza) and i < len(bien)
             and danza[i] == BAILE_MISION and bien[i] == BAILE_BIEN
             and i < len(listas["MissionID1"]) and listas["MissionID1"][i] != "1"]
    cuantas = int(round(len(aptas) * porcentaje / 100.0))
    if cuantas and aptas:
        # repartidas: una por tramo, y dentro del tramo al azar (semilla fija)
        rnd = random.Random(int(float(fila.get("ID") or 0)) * 7 + 501)
        paso = len(aptas) / float(cuantas)
        for k in range(cuantas):
            tramo = aptas[int(k * paso):max(int((k + 1) * paso), int(k * paso) + 1)]
            i = rnd.choice(tramo)
            danza[i], bien[i] = "501", "601"
    if danza == listas["MissionDanceID"] and bien == listas["MissionSuccessDanceID"]:
        return None, danza.count("501")
    return ({"MissionDanceID": ",".join(danza),
             "MissionSuccessDanceID": ",".join(bien)}, danza.count("501"))


def ritmos_guardados(fila):
    """Los "el ritmo sigue desde aca" que YA TIENE una fila guardada, en segundos.

    Sin ritmos, toda frase del Estudio arranca a un multiplo de 4 tiempos del
    arranque (o del ritmo anterior). Una que no, es un ritmo. Asi, al volver a
    abrir el Estudio, un cambio en el mapa no los desarma (27/9/2026).
    """
    if es_original(fila):
        return []
    try:
        per = 60.0 / float(fila["BPM"])
        t0 = float(fila["StartDelayTime"])
        largos = [int(float(x)) for x in fila["Length"].split(",") if x.strip()]
    except (ValueError, KeyError, ZeroDivisionError):
        return []
    out, pos, origen = [], 0, 0
    for g in agrupar_largos(largos)[:-1]:
        pos += sum(largos[i] for i in g)
        if (pos - origen) % 4:
            out.append(round(t0 + pos * per, 4))
            origen = pos
    return out


def pulso_de(rej, bpm):
    """Cada cuantos tiempos de tabla va el pulso: 1, 2, 3 o 4 segun su BPM."""
    try:
        r = float(bpm) / float(rej.get("bpm_audio") or 0.0)
    except (TypeError, ValueError, ZeroDivisionError):
        return 1
    for k in (4, 3, 2):
        if 0.9 * k <= r <= 1.1 * k:
            return k
    return 1


def config_guardada(fila):
    """Como se configuro una fila guardada, leido de su chart (27/9/2026).

    Joel dejo Kulipandeo con sus frases a mano (24, 28, 24, 20) y, al volver a
    abrir el Estudio, el mapa mostraba otra cosa: las frases marcadas viven solo
    en memoria. Ahora se sacan del chart guardado:
      frases       -> donde arranca cada mision que sigue a una no-16
      sin_caminar  -> False si tiene misiones de 17 a 31 SIN partir (se genero
                      con "que no se quede caminando" apagado); None si no se sabe
    """
    try:
        ini = float(fila["StartDelayTime"])
        bpm = float(fila["BPM"])
        largos = [int(float(x)) for x in fila["Length"].split(",") if x.strip()]
    except (ValueError, KeyError):
        return dict(frases=None, sin_caminar=None)
    fr = frases_de_largos(ini, bpm, largos)
    sin_caminar = False if any(16 < L < 32 for L in largos) else None
    return dict(frases=fr or None, sin_caminar=sin_caminar)


def enganchar_ritmo(x, sr, t, bpm, exacto=False, ventana=12.0, pulso=1):
    """Donde arranca una mision si "el ritmo sigue desde aca" en el segundo `t`.

    Mide el pulso de ESA PARTE de la cancion (de t a t+12 s), no el de toda la
    cancion: si la musica se corrio, el pulso de aca no es el del arranque.
    La fase sale de las varias bandas, igual que la cuadricula (`rejilla.medir`).

    `exacto` (el mapa con zoom, donde se ven las guias): el tiempo medido mas
    cercano al clic. Si no, el PULSO mas cercano al clic (un poco antes, porque
    uno reacciona tarde). `pulso` (ver `pulso_de`): en una fila al doble de BPM
    el pulso es cada DOS tiempos, y de los dos se elige el que pega mas, asi no
    cae en el contratiempo (27/9: en Take On Me el bajo del hardstyle va a
    contratiempo y "donde hay mas bombo" elegia mal). NO se adivina del audio:
    en una fila normal el bombo y el redoblante tambien se alternan, y medido
    contra los 14 charts oficiales que corren el compas, adivinarlo erraba.

    Devuelve dict(t, nitidez, pulso).
    """
    import numpy as np
    sys.path.insert(0, str(MOTOR))
    import rejilla as REJ
    per = 60.0 / float(bpm)
    a = max(0.0, t - 0.5)
    b = min(len(x) / float(sr), t + ventana)
    trozo = x[int(a * sr):int(b * sr)]
    if b - a < 3 * per or len(trozo) < sr:
        return dict(t=t, nitidez=0.0, pulso=1)
    S, f, tt = REJ._bandas(trozo, sr)
    tt = tt + a
    senal = REJ._pulso_bandas(S, f)
    dt = tt[1] - tt[0]

    def en(sen, ts):
        idx = np.round((np.asarray(ts) - tt[0]) / dt).astype(int)
        idx = idx[(idx >= 1) & (idx < len(sen) - 1)]
        if not len(idx):
            return 0.0
        return float(np.maximum.reduce([sen[idx - 1], sen[idx], sen[idx + 1]]).mean())

    fases = np.arange(0.0, per, dt / 2.0)
    vals = np.array([en(senal, np.arange(a + ph, b, per)) for ph in fases])
    fase = a + fases[int(np.argmax(vals))]
    nitidez = float(vals.max() / (vals.mean() + 1e-9))
    k0 = int(round((t - fase) / per))
    if exacto:
        return dict(t=round(fase + k0 * per, 4), nitidez=nitidez, pulso=1)
    paso = max(1, int(pulso))
    if paso > 1:
        # de los `paso` tiempos, el que pega mas es el pulso
        fase += per * max(range(paso), key=lambda j: en(senal, np.arange(
            fase + j * per, b, paso * per)))
    tc = t - 0.08
    k = int(round((tc - fase) / (paso * per)))
    return dict(t=round(fase + k * paso * per, 4), nitidez=nitidez, pulso=paso)


def descansos_guardados(fila):
    """Los descansos que YA TIENE una fila guardada, en segundos (a, b).

    Un descanso es una mision de 32 o mas: la frase mas larga que arma el
    Estudio es de 28, y desde el 23/9 esas se parten (6.3.28). Sin esto, al
    volver a abrir el Estudio el mapa no mostraba los descansos de una cancion ya
    enviada y un GENERAR los borraba sin avisar (24/9/2026).
    """
    try:
        per = 60.0 / float(fila["BPM"])
        t = float(fila["StartDelayTime"])
        largos = [int(float(x)) for x in fila["Length"].split(",") if x.strip()]
    except (ValueError, KeyError, ZeroDivisionError):
        return []
    out = []
    for L in largos:
        if L >= 32:
            out.append((round(t + 16 * per, 4), round(t + L * per, 4)))
        t += L * per
    return out


def invertir_patron(mid, tipico=2, tope=3):
    """Da vuelta una ventana: los tiempos con flechas quedan vacios (SPACE) y los
    vacios reciben flechas.

    Cuantas flechas van en cada tiempo que se llena: las mismas que tenia el
    tiempo mas cargado de la ventana (asi se mantiene la intensidad), o las mas
    comunes de esa dificultad si la ventana estaba vacia. Nunca mas de `tope`:
    Softnyx nunca pone 4 en un tiempo y 3 recien desde las 5 estrellas (6.3.1).
    Una ventana llena del todo queda puro SPACE; una vacia, llena de flechas.
    """
    c = patron(mid)
    m = max(c) or tipico
    m = max(1, min(m, tope))
    nuevo = [0 if x > 0 else m for x in c]
    return str(1 + nuevo[0] * 125 + nuevo[1] * 25 + nuevo[2] * 5 + nuevo[3])


# "SUAVE" (27/9/2026). Joel, con Take On Me: *"cuando baja el ritmo, solo canta,
# como coro, ahi poner flechas de 1 o 2 pero con ritmo a la musica"*. En las
# partes calmas los graves bajan y el sorteo pone lo mismo que en las fuertes.
# Lo que marca el ritmo ahi es la VOZ (o la melodia): se mide cuanto ATACA la
# banda media (300-3500 Hz, donde vive la voz) en cada uno de los 4 tiempos de la
# ventana. Donde ataca van flechas (1, y 2 en el golpe mas fuerte); donde no
# ataca queda vacio y el juego pone SPACE (6.3.1.1). Asi las flechas caen con lo
# que se canta y los SPACE en los respiros.
SUAVE_UMBRAL = 0.5       # un tiempo "ataca" si llega al 50% del mas fuerte de la ventana
_VOZ = {}


def _envolvente_voz(ogg):
    """Ataques de la banda de la voz (flujo espectral 300-3500 Hz), por cuadro."""
    import numpy as np
    import analizar_bpm as ab
    clave = (str(ogg), Path(ogg).stat().st_mtime)
    if clave in _VOZ:
        return _VOZ[clave]
    x = ab.pcm(str(ogg))
    N, H = ab.NFFT, ab.HOP
    w = np.hanning(N).astype(np.float32)
    nf = max(0, (len(x) - N) // H)
    f = np.fft.rfftfreq(N, 1.0 / ab.SR)
    banda = (f >= 300) & (f < 3500)
    env = np.zeros(nf, dtype=np.float32)
    prev = None
    paso = 2048
    for a in range(0, nf, paso):
        b = min(nf, a + paso)
        idx = np.arange(N)[None, :] + H * np.arange(a, b)[:, None]
        S = np.log1p(np.abs(np.fft.rfft(x[idx] * w, axis=1))[:, banda])
        d = np.diff(S, axis=0, prepend=S[:1] if prev is None else prev[None, :])
        env[a:b] = np.maximum(d, 0).sum(axis=1)
        prev = S[-1]
    _VOZ.clear()                 # una cancion por vez alcanza
    _VOZ[clave] = (env, ab.SR / H)
    return _VOZ[clave]


def voz_por_tiempo(ogg, tiempos, per):
    """Cuanto ataca la voz en cada tiempo (segundos): el pico cerca del golpe."""
    env, fps = _envolvente_voz(ogg)
    out = []
    for t in tiempos:
        a = max(0, int((t - 0.2 * per) * fps))
        b = min(len(env), int((t + 0.35 * per) * fps) + 1)
        out.append(float(env[a:b].max()) if b > a else 0.0)
    return out


def golpe_por_tiempo(ogg, tiempos, per):
    """Cuanto GOLPEA la musica en cada tiempo (flujo 300-3500 Hz: caja, palmas,
    ataques; el pico entre -0.1 y +0.25 de tiempo). Para poner el SPACE ahi."""
    env, fps = _envolvente_voz(ogg)
    out = []
    for t in tiempos:
        a = max(0, int((t - 0.1 * per) * fps))
        b = min(len(env), int((t + 0.25 * per) * fps) + 1)
        out.append(float(env[a:b].max()) if b > a else 0.0)
    return out


def _con_space_en(c, donde, fuerza, tope):
    """El patron `c` (del sorteo) con SPACE solo en los tiempos `donde` y flechas
    en los otros: los grupos del sorteo (sin sus huecos) van a los tiempos con mas
    graves; si faltan, 1 flecha; si sobran, se juntan en el mas chico (sin pasar
    del grupo mas grande que ya traia el sorteo)."""
    libres = [k for k in range(4) if k not in donde]
    vals = sorted([x for x in c if x], reverse=True) or [1]
    cap = min(tope, max(vals))           # nunca un grupo mas grande que los del sorteo
    while len(vals) > len(libres):
        v = vals.pop()
        vals[-1] = min(cap, vals[-1] + v)
    while len(vals) < len(libres):
        vals.append(1)
    nc = [0, 0, 0, 0]
    for k, v in zip(sorted(libres, key=lambda k: (-fuerza[k], k)), vals):
        nc[k] = v
    return nc


def patron_suave(fuerza, dos=True):
    """El MissionID1 de una ventana suave: 1 flecha donde ataca la voz, 2 en el
    golpe mas fuerte (si `dos`), SPACE donde no ataca. Siempre 2 a 4 tiempos
    con flechas: con uno solo serian 3 SPACE seguidos, y eso ya no es suave."""
    mx = max(fuerza) if fuerza else 0.0
    if mx <= 0:
        c = [1, 0, 1, 0]
    else:
        orden = sorted(range(4), key=lambda k: (-fuerza[k], k))
        con = [k for k in orden if fuerza[k] >= SUAVE_UMBRAL * mx]
        con = orden[:max(2, len(con))]
        c = [1 if k in con else 0 for k in range(4)]
        if dos:
            c[orden[0]] = 2
    return str(1 + c[0] * 125 + c[1] * 25 + c[2] * 5 + c[3])


# FLECHAS POR PARTES (27/9/2026, 6.3.54). Joel: *"las flechas que lanza al azar
# lanzan donde no debe... ya no deberiamos depender de Softnyx?"*. El sorteo copia
# CUANTAS flechas pone Softnyx, pero el DONDE lo tira casi sin escuchar. Esto es
# lo que se le hizo a mano a Take On Me y le gusto ("lo interpretaste de la mejor
# manera"), generalizado: la musica decide donde; Softnyx solo pone los topes.
#   FUERTE (los graves de la mision cerca del maximo de la cancion): flechas en
#     los tiempos donde pega el bombo, SPACE entre golpe y golpe. Si los 4 pegan
#     igual (bombo en todos), queda el sorteo acomodado a la musica.
#   SUAVE (graves muy abajo: solo canta): "1 flecha 1 space", con la voz.
#   SUBIDA (las 2 misiones antes de entrar a una fuerte): flechas seguidas.
#   MEDIA: el sorteo de Softnyx, con los SPACE en los tiempos mas flojos.
#   Un GOLPE al arrancar la ventana (explosion): ese tiempo es SPACE.
PARTE_FUERTE, PARTE_SUAVE = 0.75, 0.30   # graves de la mision / los de las mas fuertes
SUBIDA_SALTO = 1.4                       # la fuerte tiene que pegar un 40% mas
# Flecha / SPACE alternados en lo fuerte SOLO si cada tiempo dura poco (los x2,
# 165 BPM o mas). En una normal cada tiempo dura medio segundo o mas: alternar
# dejaba 2 SPACE por mision (Softnyx 0.7) y la de 3* bajaba de 5.5 a 3 flechas.
ALTERNAR_MAX_SEG = 0.365
ALTERNAR_CONTRASTE = 0.72    # el par flojo pega como mucho el 72% del fuerte
# CUANTAS ALTERNAN, COMO MUCHO (2/10/2026). Right Back! 10* (242 BPM, x2) salio con
# el 62% de las tandas en "3 SPACE 3 SPACE" / "SPACE 3 SPACE 3" y Joel la sintio
# "rara, no como una musica normal". MEDIDO en 380 charts de Softnyx de 10* a 220
# BPM o mas: las tandas alternadas son el 11% (mediana), 27% (p90), 45% el maximo.
# Ahora alternan solo las de golpe MAS claro, hasta este tope; las demas van como
# "media" (el sorteo, con el SPACE en el golpe). Y las que alternan llevan los
# grupos del sorteo (3-0-2-0, 2-0-3-0...), no siempre el maximo en los dos.
ALTERNAR_MAX_FRAC = 0.25
# EL SPACE EN EL GOLPE (27/9/2026, Joel: "el space de LoveRitmo 2020 tiene mucho
# space, puede adaptarse al ritmo?"). MEDIDO en los 237 charts oficiales del 2020
# con audio: Softnyx pone el SPACE en el tiempo mas golpeado de la ventana el 40%
# de las veces (al azar ~1 de 3): casi no lo persigue. Aca, en lo que no alterna,
# va UN SPACE en el tiempo que mas golpea, y solo en las ventanas donde el golpe
# se destaca mas en esa cancion; en las demas, flechas en los 4. Cuantas ventanas
# llevan SPACE: SPACE_POR_MISION (Softnyx 2020: 0.68 por mision).
SPACE_POR_MISION = 0.6


def flechas_por_partes(ogg, inicio, bpm, largos, estrellas, m1):
    """Rehace el MissionID1 `m1` escuchando la cancion. No toca los tiempos.
    Devuelve (m1 nuevo, lista con la parte de cada mision)."""
    per = 60.0 / float(bpm)
    n = len(largos)
    arr = [sum(largos[:i]) for i in range(n)]
    e = energia_por_beat(ogg, inicio, bpm, sum(largos) + 8)
    voz = voz_por_tiempo(ogg, [inicio + (a + k) * per for a in arr for k in range(4)], per)
    graves = [sum(e[a:a + min(L, 16)]) / float(min(L, 16)) for a, L in zip(arr, largos)]
    orden = sorted(graves)
    ref = orden[int(0.9 * (n - 1))] or 1.0
    parte = ["fuerte" if g >= PARTE_FUERTE * ref else
             "suave" if g <= PARTE_SUAVE * ref else "media" for g in graves]
    for i in range(1, n):                 # la subida: las 2 antes de una entrada fuerte
        if parte[i] == "fuerte" and parte[i - 1] != "fuerte":
            antes = [graves[j] for j in (i - 1, i - 2) if j >= 0]
            if graves[i] >= SUBIDA_SALTO * (sum(antes) / len(antes)):
                for j in (i - 1, i - 2):
                    if j >= 0 and parte[j] == "media":
                        parte[j] = "subida"
    golpes = golpe_por_tiempo(ogg, [inicio + (a + k) * per for a in arr for k in range(4)],
                              per)
    realce = []                        # cuanto se destaca el golpe mas fuerte de cada ventana
    for i in range(n):
        o = golpes[4 * i:4 * i + 4]
        mu = sum(o) / 4.0 or 1.0
        realce.append(max(o) / mu)
    candidatas = sorted((realce[i] for i in range(n) if parte[i] in ("fuerte", "media")),
                        reverse=True)
    corte = (candidatas[min(len(candidatas) - 1, int(SPACE_POR_MISION * len(candidatas)))]
             if candidatas else 9e9)
    rapida = tope_por_bpm(bpm, estrellas)
    tope = 2 if (rapida or estrellas <= 3) else 3
    alto = min(tope, 1 if estrellas <= 2 else 2 if estrellas <= 6 else 3)
    if estrellas <= 2:
        seguidas = [1, 1, 1, 1]
    elif estrellas <= 5:
        seguidas = [1, 2, 1, 2]
    elif estrellas <= 8:
        seguidas = [2, 2, 2, 2]
    else:
        seguidas = [2, 3, 2, 3]
    seguidas = [min(x, tope) for x in seguidas]
    # las que pueden alternar (fuerte, tiempo corto, golpe claro), y de esas solo
    # las de contraste mas marcado, hasta ALTERNAR_MAX_FRAC de las misiones
    contraste = {}
    if per <= ALTERNAR_MAX_SEG:
        for i, a in enumerate(arr):
            if i >= len(m1) or m1[i] == "1" or parte[i] != "fuerte":
                continue
            w = list(e[a:a + 4]) + [0.0] * (4 - len(e[a:a + 4]))
            pa, pb = w[0] + w[2], w[1] + w[3]
            r = min(pa, pb) / max(pa, pb, 1e-6)
            if r <= ALTERNAR_CONTRASTE:
                contraste[i] = r
    cupo = int(ALTERNAR_MAX_FRAC * sum(1 for v in m1[:n] if v != "1"))
    alternan = set(sorted(contraste, key=lambda i: contraste[i])[:cupo])
    nuevo = []
    for i, a in enumerate(arr):
        if i >= len(m1) or m1[i] == "1":          # callada: se respeta
            nuevo.append(m1[i] if i < len(m1) else "1")
            continue
        c = patron(m1[i])
        w = list(e[a:a + 4]) + [0.0] * (4 - len(e[a:a + 4]))
        v = voz[4 * i:4 * i + 4]
        otros = sorted(w[1:])
        # GOLPE = explosion: pega mas que el resto de la ventana Y bastante mas que
        # el MISMO tiempo de la mision de antes. Si no, el bombo del 1 de cualquier
        # compas contaba (Carmesi: 11 de 20 misiones perdian una flecha).
        golpe = (w[0] > 0 and w[0] >= 1.6 * max(otros[1], 1e-6)
                 and (i == 0 or w[0] >= 1.5 * max(e[arr[i - 1]] if arr[i - 1] < len(e)
                                                  else 0.0, 1e-6)))
        # alternar SOLO si el golpe es claro y parejo: un par de tiempos (1-3 o
        # 2-4) pega bastante mas que el otro. En Take On Me 184 contra 110 (0.60);
        # en Into The New World los graves cambian de lugar en cada mision y
        # alternar dejaba "flecha flecha SPACE SPACE" sin sentido (Joel, 27/9).
        par_a, par_b = w[0] + w[2], w[1] + w[3]
        if i in alternan:              # (fuerte + golpe claro + dentro del cupo)
            pega = [0, 2] if par_a > par_b else [1, 3]
            # (sin tocar por la explosion: sacarle la flecha del 1 dejaba 0-0-2-0,
            # una flecha y 3 SPACE; ya hay SPACE entre golpe y golpe)
            # los dos grupos mas grandes del sorteo, el mayor en el golpe mas fuerte
            g = sorted([x for x in c if x], reverse=True) + [alto, alto]
            g = [max(1, min(x, tope)) for x in g[:2]]
            fuerte_k = max(pega, key=lambda k: w[k])
            nc = [0, 0, 0, 0]
            nc[fuerte_k] = g[0]
            nc[[k for k in pega if k != fuerte_k][0]] = g[1]
        elif parte[i] == "suave":
            fase = [0, 2] if v[0] + v[2] >= v[1] + v[3] else [1, 3]
            if golpe:
                fase = [1, 3]
            fuerte_v = max(fase, key=lambda k: v[k])
            nc = [(2 if (k == fuerte_v and estrellas >= 7) else 1) if k in fase else 0
                  for k in range(4)]
        elif parte[i] == "subida":
            nc = list(seguidas)
        else:
            # media (o fuerte sin un golpe parejo): el SPACE en el golpe (ver
            # SPACE_POR_MISION), las flechas del sorteo en los otros tiempos
            o = golpes[4 * i:4 * i + 4]
            if golpe:
                donde = [0]                          # la explosion del 1
            elif realce[i] > corte:
                donde = [max(range(4), key=lambda k: o[k])]
            else:
                donde = []
            nc = _con_space_en(c, donde, w, tope)
        nc = [min(x, tope) for x in nc]
        nuevo.append(str(1 + nc[0] * 125 + nc[1] * 25 + nc[2] * 5 + nc[3]))
    return nuevo, parte


def partes_de(nombre):
    """Si esa cancion se genera con las flechas por partes (estilos.json)."""
    try:
        return bool(json.loads(ESTILOS.read_text(encoding="utf-8"))
                    .get("partes", {}).get(nombre))
    except Exception:
        return False


# MENOS SPACE (2/10/2026, pedido de Joel "por si acaso"; viene APAGADO). Softnyx en
# 10* rapidas deja 1.9 SPACE por mision (28% de los casilleros). Con esto cada
# tanda deja COMO MUCHO 1 SPACE (el primero, que es el que cae en el golpe) y los
# otros casilleros vacios reciben flechas. No toca lo marcado a mano (Solo SPACE,
# Suave, descansos) ni las tandas enteras de SPACE ("1"). Se guarda por cancion
# en estilos.json, como "partes", asi escuchar/simular/el mapa lo respetan solos.
MENOS_SPACE_MAX = 1


def menos_space_de(nombre):
    try:
        return bool(json.loads(ESTILOS.read_text(encoding="utf-8"))
                    .get("menos_space", {}).get(nombre))
    except Exception:
        return False


def anotar_menos_space(nombre, si):
    try:
        todo = json.loads(ESTILOS.read_text(encoding="utf-8"))
    except Exception:
        todo = dict(estilos={})
    d = todo.setdefault("menos_space", {})
    if bool(d.get(nombre)) == bool(si):
        return
    if si:
        d[nombre] = True
    else:
        d.pop(nombre, None)
    ESTILOS.write_text(json.dumps(todo, indent=1, ensure_ascii=False), encoding="utf-8")


def con_menos_space(mid, relleno, tope):
    """Una tanda con como mucho MENOS_SPACE_MAX casilleros vacios."""
    c = patron(mid)
    ceros = [k for k in range(4) if c[k] == 0]
    if len(ceros) <= MENOS_SPACE_MAX:
        return mid
    for k in ceros[MENOS_SPACE_MAX:]:
        c[k] = max(1, min(relleno, tope))
    return str(1 + c[0] * 125 + c[1] * 25 + c[2] * 5 + c[3])


def anotar_partes(nombre, si):
    try:
        todo = json.loads(ESTILOS.read_text(encoding="utf-8"))
    except Exception:
        todo = dict(estilos={})
    d = todo.setdefault("partes", {})
    if bool(d.get(nombre)) == bool(si):
        return
    if si:
        d[nombre] = True
    else:
        d.pop(nombre, None)
    ESTILOS.write_text(json.dumps(todo, indent=1, ensure_ascii=False), encoding="utf-8")


# CANCIONES RAPIDAS: NUNCA 3 FLECHAS JUNTAS (27/9/2026). Joel: *"cuando la musica
# es de 240 o 250 hacia arriba ya viene todo en 2 flechas, en 6, 5 o 4
# estrellas"*. MEDIDO en las cuatro tablas oficiales (charts unicos), % de tiempos
# con 3 flechas a 230 BPM o mas: 4* 0.0 (35 charts), 5* 0.8 (7), 6* 0.1 (242),
# 7* 0.7 (66), 8* 0.0 (1). Por debajo de 230, en 6* es 17.8 y en 7* 32.4. En 9 y 10
# estrellas rapidas SI hay (44% y 50%, 364 charts): ahi no se toca.
# Como: se sacan del sorteo los patrones que traen un 3 (el reparto de 0/1/2 que
# queda da 21/20/59 en 6*, contra 21.5/19.3/59.1 oficial; pasar cada 3 a 2 daba
# 21/18/61 y en 7* se alejaba el doble).
BPM_SIN_TRES = 230.0
ESTRELLAS_CON_TRES_RAPIDAS = 9
# AMPLIADO el mismo dia (Joel: "en 4, 5 o 6 estrellas no deberia venir de x3, solo
# x2 x1"; lo vio en Into The New World, 216 BPM). % de tiempos con 3, charts unicos
# de las cuatro tablas, por BPM: 4* 0.0-0.3 a CUALQUIER velocidad; 5* 5-12 bajo 200,
# 0.9 entre 200 y 230; 6* 14-31 bajo 200, 3.9 entre 200 y 230; 7* 14 entre 200 y 230.
# Desde (estrellas: BPM) no van 3 juntas:
SIN_TRES_DESDE = {4: 0.0, 5: 200.0, 6: 200.0, 7: BPM_SIN_TRES, 8: BPM_SIN_TRES}


def tope_por_bpm(bpm, estrellas):
    """2 si a esa velocidad y dificultad no van 3 flechas juntas; si no, None."""
    try:
        desde = SIN_TRES_DESDE.get(int(estrellas))
        return 2 if (desde is not None and float(bpm) >= desde) else None
    except (TypeError, ValueError):
        return None


def sin_tres(p):
    """El pozo sin los patrones que tienen algun tiempo con 3 o mas flechas."""
    q = dict((k, w) for k, w in p.items() if max(patron(k)) <= 2)
    if q:
        return q
    out = {}                          # (no pasa con los pozos de hoy) 3 -> 2
    for k, w in p.items():
        c = [min(x, 2) for x in patron(k)]
        k2 = str(1 + c[0] * 125 + c[1] * 25 + c[2] * 5 + c[3])
        out[k2] = out.get(k2, 0) + w
    return out


# ============================================== LA SEGUNDA TANDA (2/10/2026)
# El MissionID2 NO es el SPACE ni "no hace nada" (6.3.1 y 6.3.1.1 estaban mal):
# es la SEGUNDA TANDA de 4 casilleros, que llega apenas se tipea la primera (la
# barra "se rellena"). Mismo codigo que el MissionID1; "0" = sin segunda tanda;
# "1" = una tanda de 4 SPACE.
#   Visto en el juego con *La chica de la vespa amarilla* (video de All Wow y las
#   partidas de Joel: MissionID2 62 -> SPACE ←→ ←← ↓, 313 -> 2-2-2-2, 0 -> nada).
#   Y en los logs del servidor 2020: cada segunda tanda manda un juicio (op 72)
#   con ff ff en los bytes 7-8, 4 tiempos antes del de la mision. En 70+ canciones
#   de 84 a 348 BPM hay uno por cada mision con MissionID2 != 0: NO depende del BPM.
# MEDIDO en 118.000 misiones de 2016, 2020, KR y Steam:
#   * el 74% de las misiones la lleva (el pozo del Estudio ya daba eso);
#   * la PRIMERA mision de la cancion solo el 22% (las del medio, 77%);
#   * pesa lo mismo que la primera (6.27 flechas contra 6.32) y en las rapidas
#     tampoco junta 3 (0.8% de los tiempos, igual que la primera);
#   * el 48% de sus patrones ya estan en la primera tanda de ESA cancion (contra
#     14% si se los compara con otra cancion al azar): usa el vocabulario de la
#     cancion.
TANDA2_PRIMERA = 0.22          # la primera mision con segunda tanda (Softnyx)
TANDA2_RESTO = 0.74            # las demas (el pozo ya lo da)
TANDA2_DEL_VOCABULARIO = 0.48  # patrones de la segunda tanda sacados de la primera


# EL ARRANQUE DE LA CANCION (2/10/2026, Joel: "es raro empezar la partida con
# space y flechas, por lo general se empieza suave"). MEDIDO en las cuatro tablas
# oficiales (charts de 16 misiones o mas), misiones 1, 2, 3, 4 contra el resto:
#                 SPACE/mision    alternadas     con 2a tanda
#   normales      .28 .35 .60 .63 / .82    1 2 4 5 / 7%   22 28 71 76 / 78%
#   >= 200 BPM    .39 .38 .58 .63 / .91    4 4 6 8 / 10%  24 26 43 46 / 79%
# Las flechas son las mismas (6.1-6.8): Softnyx no empieza con MENOS flechas,
# empieza LLANO: casi sin SPACE, sin "flecha SPACE flecha SPACE", y casi sin
# segunda tanda en las dos primeras. Right Back! 6* arrancaba con 2-0-2-0.
TANDA2_INICIO = (0.22, 0.27, 0.71, 0.76)         # misiones 1-4, normales
TANDA2_INICIO_RAPIDA = (0.24, 0.26, 0.43, 0.46)  # misiones 1-4, >= 200 BPM
INICIO_SIN_SPACE = 2      # las 2 primeras misiones: la primera tanda sin SPACE
INICIO_UN_SPACE = 4       # hasta la 4: como mucho 1 SPACE, y no en el casillero 1


def tanda2_como_softnyx(m1, m2, semilla, bpm=None):
    """El MissionID2 sorteado, acomodado a lo que hace Softnyx: pocas segundas
    tandas en las primeras misiones (TANDA2_INICIO), y la mitad de las veces con
    un patron que la cancion ya usa en su primera tanda. No agrega ni saca
    segundas tandas despues de la mision 4."""
    r = random.Random(int(semilla) + 4242)
    voc = [v for v in m1 if v not in ("0", "1")]
    out = list(m2)
    for i, v in enumerate(out):
        if v in ("0", "1") or not voc:
            continue
        if r.random() < TANDA2_DEL_VOCABULARIO:
            out[i] = r.choice(voc)
    tabla = TANDA2_INICIO_RAPIDA if (bpm and float(bpm) >= 200) else TANDA2_INICIO
    for i, p in enumerate(tabla):
        if i < len(out) and out[i] != "0" and r.random() >= p / TANDA2_RESTO:
            out[i] = "0"
    return out


def arranque_como_softnyx(m1, m2, tocadas, tope):
    """Las primeras misiones como las empieza Softnyx (ver TANDA2_INICIO): en las
    INICIO_SIN_SPACE primeras la primera tanda no deja casilleros vacios; hasta la
    INICIO_UN_SPACE deja como mucho uno y nunca el primero; las segundas tandas de
    esas misiones, como mucho un SPACE. Un casillero vacio recibe el grupo mas
    grande de la tanda menos uno (2-0-2-0 -> 2-1-2-1, 3-0-3-0 -> 3-2-3-2), que es
    lo que mas usa Softnyx. No toca lo marcado a mano (`tocadas`) ni las tandas
    vacias ("0" / "1"). Devuelve cuantas tandas cambio."""
    n = 0
    for i in range(min(INICIO_UN_SPACE, len(m1))):
        if i in tocadas:
            continue
        for lista, primera in ((m1, True), (m2, False)):
            if i >= len(lista) or lista[i] in ("0", "1"):
                continue
            c = patron(lista[i])
            relleno = max(1, min(tope, max(c) - 1))
            ceros = [k for k in range(4) if c[k] == 0]
            if primera and i < INICIO_SIN_SPACE:
                deja = []
            else:
                deja = [k for k in ceros if k != 0][:1] if primera else ceros[:1]
            for k in ceros:
                if k not in deja:
                    c[k] = relleno
            nuevo = str(1 + c[0] * 125 + c[1] * 25 + c[2] * 5 + c[3])
            if nuevo != lista[i]:
                lista[i] = nuevo
                n += 1
    return n


def tanda2_por_partes(ogg, inicio, bpm, largos, estrellas, m2):
    """Las flechas por partes (ver `flechas_por_partes`) para la segunda tanda:
    la misma cuenta, corrida 4 tiempos (sus casilleros caen en los tiempos 5 a
    8 de la mision). Donde no hay segunda tanda ("0") sigue sin haber, y la de 4
    SPACE ("1") queda como esta."""
    per = 60.0 / float(bpm)
    tmp = ["1" if v == "0" else v for v in m2]      # "1" = callada: no la toca
    nuevo, _p = flechas_por_partes(ogg, float(inicio) + 4 * per, bpm, largos,
                                   estrellas, tmp)
    return [v if v in ("0", "1") else nuevo[i] for i, v in enumerate(m2)]


def largos_de(rej, inicio, bpm, fin, frases=None, ritmos=()):
    """None = todas de 16 (lo de antes). "auto" = las propone la musica.
    Una lista de segundos = las que marco el usuario en el mapa.

    Con `ritmos` (ver `largos_por_frases`) todo pasa por las frases: "auto" se
    calcula de a tramos, cada uno desde su propio ritmo."""
    if ritmos:
        per = 60.0 / bpm
        if frases == "auto":
            cortes = sorted(float(inicio) + int(round((x - inicio) / per)) * per
                            for x in ritmos if x > inicio)
            normales = []
            for k, a in enumerate([float(inicio)] + cortes):
                b = cortes[k] if k < len(cortes) else fin
                la = largos_auto(rej, a, bpm, fin)
                normales += [x for x in frases_de_largos(a, bpm, la) if x < b - 0.01]
        else:
            normales = list(frases or ())
        return largos_por_frases(inicio, bpm, fin, normales, ritmos)
    if frases == "auto":
        return largos_auto(rej, inicio, bpm, fin)
    if frases:
        return largos_por_frases(inicio, bpm, fin, frases)
    per = 60.0 / bpm
    return [16] * max(1, int((fin - inicio) / per + 1e-6) // 16)


def generar(fila, rej, estrellas, inicio, bpm=None, fin=None, semilla=None,
            por_musica=False, mudos=(), space="softnyx", mudo_sin_space=False,
            repetir=(), frases=None, descanso=False, solo_space=(), invertir=(),
            ritmos=(), space_estilo="clasico", suave=(), por_partes=False,
            menos_space=None, secciones=()):
    """Rehace las 10 listas de una fila. Devuelve (nuevos, informe).

    `secciones`: patrones y descansos en segundos absolutos del audio. Se aplican
    al final para respetar exactamente la eleccion manual (ver secciones.py).

    `menos_space` (2/10/2026): None = lo que diga estilos.json para esa cancion
    (`menos_space_de`); True/False lo fuerza. Ver MENOS_SPACE_MAX.

    `por_partes` (27/9/2026): las flechas las acomoda la musica (fuerte / suave /
    subida / media), ver `flechas_por_partes`. Softnyx pone solo los topes.

    `suave` (27/9/2026): tramos (segundos) marcados en el mapa donde la cancion
    baja y solo canta: flechas de 1 o 2 donde ataca la voz (ver `patron_suave`).

    `space_estilo` (27/9/2026): "2020" sortea las flechas como los charts de
    LoveRitmo 2020 y reparte los SPACE segun la musica (ver `repartir_space`);
    "clasico" es lo de siempre (promedio de los cuatro juegos).

    `ritmos`: segundos donde "el ritmo sigue desde aca" (ver `largos_por_frases`).

    `solo_space` e `invertir` son tramos (segundos) marcados en el mapa: en los
    primeros la mision queda SIN flechas (el juego pone 4 SPACE y el personaje
    sigue bailando); en los segundos se da vuelta el patron: donde habia
    flechas va SPACE y donde habia SPACE van flechas (ver `invertir_patron`).

    `frases`: None deja todas las misiones de 16 tiempos; "auto" alarga las que
    hagan falta para seguir las frases de la cancion, como Softnyx; una lista de
    segundos pone una mision arrancando en cada uno (ver `largos_de`).

    `descanso`: con True, los tramos de `mudos` son DESCANSOS (no sale nada: la
    mision de antes se alarga, ver `saltar_descansos`). Con False quedan como
    siempre: misiones sin flechas, que el juego llena de SPACE.
    """
    from secciones import validar_secciones
    secciones = validar_secciones(secciones)
    bpm = float(bpm or rej["bpm"])
    per = 60.0 / bpm
    dur = rej.get("dur") or float(fila.get("Second") or 0)
    if fin is None:
        fin = min(rej.get("fin_beat") or dur, dur)
    beats = (fin - inicio) * bpm / 60.0
    largos = largos_de(rej, inicio, bpm, fin, frases, ritmos)
    if SIN_CAMINAR:
        largos = partir_largas(largos)      # antes de los descansos: esos no
    n_descansos = 0
    if descanso and mudos:
        largos, n_descansos = saltar_descansos(largos, inicio, bpm, mudos)
        mudos = ()               # ya estan resueltos: no queda nada que vaciar
    n = len(largos)
    # donde arranca cada mision, en tiempos desde el inicio
    arr = [sum(largos[:i]) for i in range(n)]
    cobertura = sum(largos) / beats if beats else 0.0

    # la semilla es la de la fila ORIGINAL si esta es una copia (copias.json):
    # asi la copia, regenerada con los mismos ajustes, da las mismas flechas
    sem = (int(id_de_semilla(fila["ID"])) * 100 + estrellas
           if semilla is None else semilla)
    estilo2020 = (space_estilo == "2020")
    pf = pozo("_flechas_2020.json" if estilo2020 else "_flechas_softnyx.json",
              estrellas)
    if estilo2020:
        # sin la mision VACIA ("1" = 4 SPACE): en los charts de Softnyx esas
        # estan puestas a proposito (pausas), y sorteadas al azar caen en medio
        # de una parte fuerte. Una semilla de Kulipandeo saco 5 de 37 (27/9).
        # Los 4 SPACE quedan para lo que se marca: descanso, "Solo SPACE".
        pf = dict((k, v) for k, v in pf.items() if k != "1")
        pf = con_vocabulario(pf, estrellas, sem)
    tope_rapida = tope_por_bpm(bpm, estrellas)
    if tope_rapida:
        pf = sin_tres(pf)             # rapidas: nunca 3 juntas (ver BPM_SIN_TRES)
    # LA SEGUNDA TANDA (MissionID2) sale del reparto real de Softnyx, y en las
    # rapidas tambien sin 3 juntas: Softnyx las evita igual en las dos tandas
    # (0.8% de los tiempos en cada una, >=230 BPM y 4-8 estrellas). Ver TANDA2_*.
    ps = pozo("_spaces_softnyx.json", estrellas)
    if tope_rapida:
        ps = sin_tres(ps)
    energias = None
    if estilo2020 and rej.get("ogg"):
        try:
            energias = energia_de_misiones(rej["ogg"], inicio, bpm, largos)
        except Exception:
            energias = None
    plan = calladas = None
    umbral_space = SPACE_UMBRAL.get(space)
    # el plan hace falta para acomodar las flechas Y para recortar el SPACE
    if (por_musica or umbral_space is not None) and rej.get("ogg"):
        try:
            plan = plan_musical(rej["ogg"], inicio, bpm, n, arranques=arr)
        except Exception:
            plan = None
    if plan:
        # la CANTIDAD la sigue eligiendo el sorteo de siempre; la musica solo
        # decide en que tiempo de la ventana cae cada grupo
        crudo1 = sortear(pf, n, sem)
        if energias:
            crudo1 = repartir_space(crudo1, energias, sem)
        crudo2 = sortear(ps, n, sem + 7777)
        m1, m2, calladas = [], [], 0
        for i, pm in enumerate(plan):
            if por_musica and pm["callada"]:
                m1.append("1")          # el patron vacio: ni una flecha
                m2.append("0")          # y sin segunda tanda ("1" serian 4 SPACE mas)
                calladas += 1
                continue
            v1 = _acomodar(crudo1[i], pm["fuerza"]) if por_musica else crudo1[i]
            v2 = _acomodar(crudo2[i], pm["subida"]) if por_musica else crudo2[i]
            if umbral_space is not None:
                v2 = _space_justo(v2, pm["subida"], umbral_space)
            m1.append(v1)
            m2.append(v2)
    else:
        m1 = sortear(pf, n, sem)
        if energias:
            m1 = repartir_space(m1, energias, sem)
        m2 = sortear(ps, n, sem + 7777)
    # la segunda tanda con el vocabulario de la cancion y casi nunca en la
    # primera mision, como Softnyx (ver tanda2_como_softnyx)
    m2 = tanda2_como_softnyx(m1, m2, sem, bpm)

    # MISION SIN NI UNA FLECHA -> SIN SEGUNDA TANDA (casilla, apagada por defecto).
    #
    # CORREGIDO el 2/10/2026. Esto se escribio creyendo que el MissionID2 era "el
    # SPACE" y despues que "no hacia nada". Es la SEGUNDA TANDA: con "1" el juego
    # muestra otros 4 casilleros, todos SPACE. Una mision con la primera tanda
    # vacia y la segunda cargada es justo la "CERO flechas y NUEVE space" que vio
    # Joel. Softnyx tambien las tiene (con la primera vacia, la segunda es 4 SPACE
    # el 51%, flechas el 39% y nada el 11%), por eso sigue siendo una casilla.
    if mudo_sin_space:
        for i in range(n):
            if m1[i] == "1":
                m2[i] = "0"

    partes = None
    if por_partes and rej.get("ogg"):
        try:
            m1, partes = flechas_por_partes(rej["ogg"], inicio, bpm, largos,
                                            estrellas, m1)
            # la segunda tanda tambien escucha la cancion: la misma parte, 4
            # tiempos mas adelante. Donde no hay segunda tanda sigue sin haber.
            m2 = tanda2_por_partes(rej["ogg"], inicio, bpm, largos, estrellas, m2)
        except Exception:
            partes = None

    # tramos que el usuario callo A MANO en el mapa. Van por TIEMPO y no por
    # numero de mision, asi valen igual para la facil y para la dificil aunque
    # tengan distinta cantidad de misiones (el caso del x2).
    if mudos:
        calladas = calladas or 0
        # SE MIRA EL SOLAPE, no si el arranque cae adentro.
        #
        # Por que: la facil y la dificil pueden tener misiones de distinto largo
        # (en un par x2, 7.82 s contra 3.91 s). Comparando arranques, un tramo
        # quitado mirando la fila dificil le llegaba a la facil solo cuando los
        # numeros coincidian justo: de tres misiones seguidas, una si y dos no.
        # Era una moneda. Con el solape, un tramo quitado vale para las dos
        # filas, que es lo que uno espera al sacar un pedazo de la cancion.
        #
        # El 25% es para que dos misiones que apenas se tocan en el borde no se
        # arrastren entre si.
        for i in range(n):
            t = inicio + arr[i] * per
            largo = largos[i] * per
            for a, b in mudos:
                solape = min(t + largo, b) - max(t, a)
                if solape > 0.25 * min(largo, b - a):
                    if m1[i] != "1":
                        calladas += 1
                    m1[i] = "1"
                    m2[i] = "0"          # sin segunda tanda: "1" serian 4 SPACE mas
                    break

    # TRAMOS DONDE EL USUARIO PIDIO REPETICIONES (la bolsa 1).
    #
    # La bolsa NO cambia CUANTAS flechas hay: eso lo decide el MissionID1. Lo que
    # cambia es que combinaciones de direcciones puede sacar. Para un racimo de
    # 3, la bolsa 1 tiene SOLO CUATRO y las cuatro son repeticiones:
    # izq-izq-izq, aba-aba-aba, arr-arr-arr, der-der-der. Por eso se siente
    # "repite" (6.3).
    #
    # NO SE PUEDE GARANTIZAR una repeticion en un momento exacto: el sorteo lo
    # hace el juego en CADA partida, asi que dos veces la misma cancion no dan
    # las mismas flechas. Lo unico que se puede hacer es CARGAR LOS DADOS.
    # MEDIDO: con ~3 tiradas por mision, la probabilidad de no ver ninguna
    # repeticion es 18% con 2 misiones, 7% con 3 y 3% con 4. De ahi la regla de
    # usar TRES misiones seguidas por tanda.
    #
    # Va por TIEMPO y no por numero de mision, por lo mismo que los mudos: la
    # facil y la dificil pueden tener distinta cantidad de misiones.
    bolsas = bolsas_keypattern(n, estrellas)
    n_repes = 0
    if repetir:
        # CUANTAS FLECHAS POR TIEMPO se ponen en un tramo de repeticiones.
        #
        # CORREGIDO el 21/9/2026, porque la primera version salia MEZCLADA CON
        # SPACE y Joel lo vio enseguida. El motivo: la bolsa solo decide las
        # DIRECCIONES. Cuantas flechas hay en cada tiempo lo decide el
        # MissionID1, y el juego pone un SPACE en CADA TIEMPO QUE QUEDA SIN
        # FLECHAS (6.3.1.1, comprobado jugando). Si la mision sorteada tenia
        # tiempos vacios, ahi salian SPACE en medio de la repeticion.
        #
        # Asi que para una fila MACIZA hay que hacer las dos cosas: la bolsa 1
        # Y un MissionID1 con los CUATRO tiempos ocupados. Ya estaba escrito en
        # el informe: "para tener menos SPACE hay que tener menos tiempos
        # vacios, o sea mas flechas. No se regula por otro lado".
        #
        # Cuantas por tiempo sale del reparto real de cada dificultad
        # (REF_FLECHAS): lo mas comun sin contar el cubo del 0. Ademas se
        # respetan las dos reglas duras: nunca 4 en un tiempo (0 de 474.532
        # tiempos oficiales) y nunca 3 en 1-3 estrellas.
        ref = REF_FLECHAS.get(estrellas)
        if ref:
            cuantas = max(range(1, 4), key=lambda k: ref[k])
        else:
            cuantas = 2
        if estrellas <= 3 or tope_rapida:
            cuantas = min(cuantas, 2)
        macizo = str(1 + cuantas * 125 + cuantas * 25 + cuantas * 5 + cuantas)
        pedidas = set()
        for i in range(n):
            t = inicio + arr[i] * per
            largo_m = largos[i] * per
            for a, b in repetir:
                solape = min(t + largo_m, b) - max(t, a)
                if solape > 0.25 * min(largo_m, b - a):
                    bolsas[i] = 1
                    m1[i] = macizo          # los 4 tiempos con flechas: sin SPACE
                    if m2[i] != "0":        # y la segunda tanda igual de maciza
                        m2[i] = macizo
                    pedidas.add(i)
                    n_repes += 1
                    break

        # BORDES LIMPIOS. Joel probo y seguia viendo SPACE en medio de la
        # repeticion, y no era de las misiones marcadas: era de la de AL LADO.
        #
        # El sorteo general reparte bolsa 1 al azar (del 16% en 1 estrella al
        # 4.6% en 10), asi que es normal que a la mision pegada a la tanda le
        # toque bolsa 1 por casualidad. Esa no pasa por aca, asi que conserva
        # sus tiempos vacios -> el juego los llena de SPACE, y se oye como si la
        # repeticion se ensuciara al final.
        #
        # MEDIDO: la bolsa 1 es 100% repeticiones en TODOS los tamanos de racimo
        # (4 combinaciones y las 4 puras, para 1, 2, 3 y 4 flechas). O sea que
        # una vecina con bolsa 1 SE OYE como parte de la tanda aunque no lo sea.
        #
        # Por eso a las vecinas se les saca la bolsa 1: la tanda queda siendo
        # EXACTAMENTE la que se marco, ni mas larga ni sucia. Se les pone la
        # bolsa 4, que es la que domina en todas las dificultades (64.6% a
        # 78.8%), asi que el cambio no desentona.
        for i in sorted(pedidas):
            for v in (i - 1, i + 1):
                if 0 <= v < n and v not in pedidas and bolsas[v] == 1:
                    bolsas[v] = 4

    # SOLO SPACE e INVERTIR, pedidos por Joel el 24/9/2026 como herramientas
    # del mapa. Van por TIEMPO como todo lo demas, asi valen para las dos filas.
    n_solo = n_inv = 0
    if solo_space or invertir:
        tope = 3 if (estrellas >= 5 and not tope_rapida) else 2
        ref = REF_FLECHAS.get(estrellas)
        tipico = max(range(1, 4), key=lambda k: ref[k]) if ref else 2
        tipico = min(tipico, tope)
        for i in range(n):
            t = inicio + arr[i] * per
            # la segunda tanda (si la hay) sigue a la primera: puro SPACE en "Solo
            # SPACE" (4 SPACE, lo que Softnyx pone el 51% de las veces cuando la
            # primera es puro SPACE), y dada vuelta en "Invertir"
            if solo_space and _pisa(t, 4 * per, solo_space):
                m1[i] = "1"
                if m2[i] != "0":
                    m2[i] = "1"
                n_solo += 1
            elif invertir and _pisa(t, 4 * per, invertir):
                m1[i] = invertir_patron(m1[i], tipico, tope)
                if m2[i] != "0":
                    m2[i] = invertir_patron(m2[i], tipico, tope)
                n_inv += 1
    n_suave = 0
    if suave:
        cuales = [i for i in range(n) if _pisa(inicio + arr[i] * per, 4 * per, suave)
                  and not (solo_space and _pisa(inicio + arr[i] * per, 4 * per,
                                                solo_space))
                  and not (invertir and _pisa(inicio + arr[i] * per, 4 * per,
                                              invertir))]
        voz = None
        if cuales and rej.get("ogg"):
            try:
                # 8 tiempos por mision: los de la primera tanda y los de la segunda
                voz = voz_por_tiempo(rej["ogg"], [inicio + (arr[i] + k) * per
                                                  for i in cuales for k in range(8)],
                                     per)
            except Exception:
                voz = None
        for j, i in enumerate(cuales):
            m1[i] = patron_suave(voz[8 * j:8 * j + 4] if voz else [])
            if m2[i] != "0":            # la segunda tanda tambien suave, con la voz
                m2[i] = patron_suave(voz[8 * j + 4:8 * j + 8] if voz else [])
            n_suave += 1

    # EL ARRANQUE COMO SOFTNYX (ver TANDA2_INICIO): las primeras misiones llanas,
    # salvo las que se marcaron a mano (Solo SPACE, Suave, Invertir, callar,
    # repeticiones) o las vacias
    tocadas = set()
    for i in range(min(INICIO_UN_SPACE, n)):
        t = inicio + arr[i] * per
        if (any(x and _pisa(t, 4 * per, x) for x in (solo_space, suave, invertir, mudos))
                or (repetir and _pisa(t, 4 * per, repetir))):
            tocadas.add(i)
    antes_inicio = (list(m1), list(m2)) if secciones else None
    n_inicio = arranque_como_softnyx(
        m1, m2, tocadas, 2 if (tope_rapida or estrellas <= 3) else 3)
    cambios_inicio = ({(i, j) for j, lista in enumerate((m1, m2))
                       for i in range(n) if lista[i] != antes_inicio[j][i]}
                      if antes_inicio is not None else set())

    # MENOS SPACE (casilla, apagada por defecto; ver MENOS_SPACE_MAX)
    if menos_space is None:
        menos_space = menos_space_de(fila.get("Filename", ""))
    n_menos = 0
    cambios_menos = set()
    if menos_space:
        relleno = 1 if estrellas <= 4 else 2
        tope_ms = 2 if (tope_rapida or estrellas <= 3) else 3
        for i in range(n):
            t = inicio + arr[i] * per
            if any(x and _pisa(t, 4 * per, x) for x in (solo_space, suave, mudos)):
                continue                 # lo marcado a mano se respeta
            for j, lista in enumerate((m1, m2)):
                if lista[i] in ("0", "1"):
                    continue
                nv = con_menos_space(lista[i], relleno, tope_ms)
                if nv != lista[i]:
                    lista[i] = nv
                    n_menos += 1
                    cambios_menos.add((i, j))

    # MISION CORTA = SIN SEGUNDA TANDA (2/10/2026). Joel marco una frase en
    # Whiplash y la mision de antes quedo de 8 tiempos CON segunda tanda: los 8
    # tiempos tipeando, sin respiro, y la siguiente encima ("sale muy junto").
    # En la vespa de Softnyx las dos misiones de 8 (M4 y M18) no la tienen.
    for i in range(n):
        if largos[i] < 16 and m2[i] != "0":
            m2[i] = "0"

    nuevos = {}
    nuevos["Length"] = ",".join(str(L) for L in largos)
    nuevos["KeyPatternID"] = ",".join(str(v) for v in bolsas)
    nuevos["KeySoundID"] = ",".join(["0"] * n)
    nuevos["MissionID1"] = ",".join(m1)
    nuevos["MissionID2"] = ",".join(m2)
    # EL BAILE: SIEMPRE 511/611 (24/9/2026). Antes se ciclaban los de la fila
    # que se uso de molde, y Joel saco 13 capturas de Feather (10 estrellas, 247
    # BPM) con el personaje CAMINANDO en medio de la mision: las 13 caian en
    # misiones con el baile 501/601, que en esa fila eran 18 de 42; ninguna en
    # una 511/611. El 511/611 es el que mas usa Softnyx (75-80%) y tiene 219
    # animaciones para sortear, asi que variedad no se pierde. El 201 (fallar)
    # no cambia. Ver BAILE_MISION.
    nuevos["MissionDanceID"] = ",".join([BAILE_MISION] * n)
    nuevos["MissionSuccessDanceID"] = ",".join([BAILE_BIEN] * n)
    nuevos["MissionFailDanceID"] = ",".join(
        _ciclar([v for v in fila["MissionFailDanceID"].split(",") if v.strip()], n))
    nuevos["MissionCameraID"] = ",".join(["101"] + ["0"] * (n - 1))
    ciclo = ["0", "111", "0", "111", "0", "201"]
    dc = [ciclo[i % len(ciclo)] for i in range(n)]
    dc[-1] = "241"
    nuevos["DanceCameraID"] = ",".join(dc)
    nuevos["BPM"] = "%g" % round(bpm, 2)
    nuevos["Difficulty"] = str(estrellas)
    nuevos["StartDelayTime"] = "%g" % round(inicio, 4)
    nuevos["CutOff"] = str(cutoff_de(estrellas))
    if dur:
        nuevos["Second"] = str(int(round(dur)))

    n_manuales = n_descansos_seccion = 0
    if secciones:
        from secciones import aplicar_secciones
        tramos = validar_secciones(secciones)
        n_anterior, inicio_anterior, arr_anterior = n, inicio, arr
        largos_anteriores = largos
        nuevos = aplicar_secciones(fila, nuevos, inicio, bpm, tramos)
        inicio = float(nuevos["StartDelayTime"])
        largos = [int(v) for v in nuevos["Length"].split(",")]
        m1, m2 = [nuevos[c].split(",") for c in ("MissionID1", "MissionID2")]
        bolsas = [int(v) for v in nuevos["KeyPatternID"].split(",")]
        n = len(largos)
        # Recuperar los indices originales permite contar solo las operaciones
        # que siguen presentes despues de quitar misiones o imponer patrones.
        arr = [sum(largos[:i]) for i in range(n)]
        desplazamiento = int(round((inicio - inicio_anterior) / per))
        indice_beat = dict((beat, i) for i, beat in enumerate(arr_anterior))
        indices = [indice_beat[desplazamiento + beat] for beat in arr]
        supervivientes = set(indices)
        manuales = {i for i in indices if any(
            s["tipo"] == "patron" and s["desde"] <= inicio_anterior + arr_anterior[i] * per < s["hasta"]
            for s in tramos)}
        automaticas = supervivientes - manuales
        n_manuales = len(manuales)
        n_descansos_seccion = n_anterior - n
        n_descansos += n_descansos_seccion
        n_inicio = sum(i in automaticas for i, _j in cambios_inicio)
        n_menos = sum(i in automaticas for i, _j in cambios_menos)
        def pisa_original(i, intervalos, ventana=4):
            return bool(intervalos) and _pisa(
                inicio_anterior + arr_anterior[i] * per, ventana * per, intervalos)
        n_solo = sum(pisa_original(i, solo_space) for i in automaticas)
        n_inv = sum(pisa_original(i, invertir) and not pisa_original(i, solo_space)
                    for i in automaticas)
        n_suave = sum(pisa_original(i, suave) and not pisa_original(i, solo_space)
                      and not pisa_original(i, invertir) for i in automaticas)
        n_repes = sum(pisa_original(i, repetir, largos_anteriores[i])
                      for i in automaticas)
        if partes:
            partes = [partes[i] for i in indices]
        if calladas is not None:
            calladas = sum(v == "1" and m2[i] == "0" for i, v in enumerate(m1))
        beats = (fin - inicio) * bpm / 60.0
        cobertura = sum(largos) / beats if beats else 0.0

    fl = [sum(patron(v)) for v in m1]
    # el SPACE que se VE es uno por cada tiempo sin flechas (de la primera tanda;
    # la comparacion con Softnyx, 0.73 por mision, se midio asi)
    sp = [sum(1 for x in patron(v) if x == 0) for v in m1]
    porT = [q for v in m1 for q in patron(v)]
    rep = [100.0 * porT.count(k) / len(porT) for k in range(4)]
    con2 = [v for v in m2 if v != "0"]
    informe = dict(misiones=n, cobertura=cobertura, flechas=sum(fl) / n,
                   tandas2=len(con2),
                   flechas2=(sum(sum(patron(v)) for v in con2) / float(len(con2))
                             if con2 else 0.0),
                   space=sum(sp) / n, sin_space=sp.count(0), reparto=rep,
                   fin_chart=inicio + sum(largos) * per, fin_musica=fin, ventana=4 * per,
                   largas=sum(1 for g in agrupar_largos(largos)
                              if sum(largos[i] for i in g) != 16),
                   partidas=sum(1 for L in largos if L < 16),
                   descansos=n_descansos, descansos_seccion=n_descansos_seccion,
                   secciones_patron=n_manuales,
                   puro_space=n_solo, invertidas=n_inv,
                   suaves=n_suave, menos_space=n_menos, inicio_llano=n_inicio,
                   partes=(dict((k, partes.count(k)) for k in
                                ("fuerte", "media", "subida", "suave"))
                           if partes else None),
                   frases=frases_de_largos(inicio, bpm, largos),
                   calladas=calladas, por_musica=bool(plan),
                   repes=n_repes, repes_pedidas=len(repetir or ()),
                   repes_por_tiempo=(cuantas if repetir else 0),
                   mudos_a_mano=len(mudos or ()), modo_space=space,
                   sin_flechas=m1.count("1"),
                   # sin flechas en la primera tanda pero con flechas en la segunda
                   solo_space=sum(1 for i in range(n)
                                  if m1[i] == "1" and m2[i] not in ("0", "1")))
    return nuevos, informe


# ================================================================ diagnostico
OK, AVISO, MAL = "ok", "aviso", "mal"


def _p(estado, titulo, detalle):
    return dict(estado=estado, titulo=titulo, detalle=detalle)


def revisar(fila, rej):
    """Lo que esta bien y lo que no en una fila."""
    out = []
    try:
        est = int(float(fila["Difficulty"]))
    except Exception:
        est = 0
    bpm_t = float(fila["BPM"] or 0)
    ini = float(fila["StartDelayTime"] or 0)
    sec = float(fila["Second"] or 0)

    if rej is None:
        out.append(_p(MAL, "El audio", "no encuentro %s.ogg" % fila["Filename"]))
        return out
    dur = rej.get("dur") or sec

    ofi = origen_del_chart(fila)
    if ofi:
        out.append(_p(OK, "De donde salio",
                      "este chart es de %s, donde figura como '%s'. NO LO HICIMOS "
                      "NOSOTROS: si lo regeneras, lo perdes. (Se compara el chart "
                      "entero, no el nombre del archivo.)" % (ofi[0], ofi[1][:40])))
    if rej["origen"].startswith("Virtual"):
        out.append(_p(OK, "La cuadricula", "la trae %s. Es la buena." % rej["origen"]))
    else:
        c = rej.get("confianza", 0)
        nit = rej.get("nitidez") or 0.0
        bpm_a = rej.get("bpm_audio") or 0.0
        if nit and nit < NITIDEZ_MAL:
            out.append(_p(MAL, "La cuadricula",
                          "NO esta apoyada en la musica: nitidez %.2f. De los 117 "
                          "charts oficiales con audio, el peor da 1.75 y ninguno "
                          "baja de 1.5. Casi seguro el BPM no es el de esta "
                          "cancion%s. Las flechas van a caer donde no hay nada."
                          % (nit, (": el audio da %.2f" % bpm_a) if bpm_a else "")))
        elif nit and nit < NITIDEZ_AVISO:
            out.append(_p(AVISO, "La cuadricula",
                          "la mido yo y apoya JUSTITO (nitidez %.2f; el 5%% mas "
                          "flojo de los oficiales da 2.08). Escuchala antes de "
                          "darla por buena." % nit))
        else:
            out.append(_p(AVISO, "La cuadricula",
                          "la mido yo, sin Virtual DJ (confianza %.0f%%%s). Medido "
                          "contra 120 oficiales: el pulso sale bien 9 de cada 10 "
                          "veces y el '1' del compas 2 de cada 3. Escuchala. Si "
                          "algun dia Virtual DJ la analiza, pasa a verde (no hace "
                          "falta para crear)."
                          % (c, (", nitidez %.2f" % nit) if nit else "")))

    # ===================== EL BPM CONTRA EL AUDIO =====================
    # El BPM de la fila es el que usa el juego; el del audio sale de medirlo sin
    # mirar la tabla. Si no se parecen ni por un x2, el chart se escribio sobre
    # una cuadricula que no es la de la cancion.
    #
    # AVISO y no rojo, y esta medido por que: de los 117 oficiales, 7 (el 6%)
    # dan un multiplo raro (x4/3 casi siempre) y sin embargo funcionan. El rojo
    # queda para la nitidez, que ahi si no falla ninguno.
    bpm_a = rej.get("bpm_audio") or 0.0
    if bpm_a and bpm_t:
        rel = bpm_t / bpm_a
        mult = min((0.25, 1.0 / 3.0, 0.5, 1.0, 2.0, 3.0, 4.0), key=lambda m: abs(rel - m))
        if abs(rel - mult) / mult <= 0.03:
            out.append(_p(OK, "El BPM contra el audio",
                          "la fila dice %g y el audio da %.2f%s. Coinciden."
                          % (bpm_t, bpm_a,
                             "" if mult == 1.0 else (" (x%g)" % (1.0 / mult)
                                                     if mult < 1 else " (x%g)" % mult))))
        else:
            out.append(_p(AVISO, "El BPM contra el audio",
                          "la fila dice %g y midiendo el audio da %.2f, que no es "
                          "ni el mismo ni el doble ni la mitad (x%.2f). O el BPM "
                          "esta mal, o esta cancion es de las raras: 7 de los 117 "
                          "oficiales tambien dan un multiplo raro y andan bien. "
                          "Escuchala." % (bpm_t, bpm_a, rel)))

    # =============================== EL BPM ===============================
    # CORREGIDO el 20/9/2026. Antes se aceptaba el x1 y el x2, se avisaba el
    # x1/2 y TODO LO DEMAS era rojo "el chart se va corriendo". Eso mezclaba dos
    # cosas que no son la misma y dejaba 22 filas sanas en rojo: un x4 o un x4/3
    # no se corre ni un milisegundo (8.7: BPM = largo x pulso / k), y en cambio
    # un x1 que este 0.25% flojo se corre medio segundo en tres minutos. Lo que
    # se mide ahora es la DERIVA de punta a punta del chart, que es lo unico que
    # se oye.
    per_c = (60.0 / bpm_t) if bpm_t else 0.0    # el tiempo del CHART: ahi caen las flechas
    per_v = rej["per"] or 0.0                   # la pulsacion de la musica
    lens = []
    for v in str(fila["Length"]).split(","):
        v = v.strip()
        if v:
            try:
                lens.append(int(float(v)))
            except ValueError:
                pass
    tot = sum(lens)
    largo_chart = tot * per_c
    ratio = (bpm_t / rej["bpm"]) if (bpm_t and rej["bpm"]) else 0.0
    p_m, q_m, err_m = racional_simple(ratio) if ratio else (1, 1, 1.0)
    comomult = ("x%d" % p_m) if q_m == 1 else ("x%d/%d" % (p_m, q_m))
    deriva = err_m * (largo_chart or max(dur - ini, 0.0))
    if not bpm_t:
        out.append(_p(MAL, "El BPM", "la fila no tiene BPM"))
    elif deriva * 1000 <= ARR_OK_MS:
        out.append(_p(OK, "El BPM",
                      "%.2f, que es %s la pulsacion de la cuadricula (%.2f). De "
                      "punta a punta el chart se corre %.0f ms: nada."
                      % (bpm_t, comomult, rej["bpm"], deriva * 1000)))
    else:
        ap_t = apoyo_bpm(rej.get("ogg"), bpm_t)
        ap_v = apoyo_bpm(rej.get("ogg"), rej["bpm"])
        if ap_t is None or ap_v is None:
            tercero = ""
        else:
            tercero = ("  Mi medicion del audio apoya al BPM de la tabla con %.2f%% "
                       "de error y al de Virtual DJ con %.2f%%; resuelve hasta el "
                       "%.1f%%, asi que mas fino que eso no desempata."
                       % (ap_t, ap_v, BPM_APOYO_MAX))
        # ROJO solo cuando las flechas terminan mas cerca de la contra que del
        # tiempo Y ADEMAS mi propia medicion tampoco apoya al BPM de la tabla.
        # Si lo apoya, el que puede estar equivocado es Virtual DJ: le pasa.
        grave = (per_c and deriva > per_c / 2
                 and ap_t is not None and ap_t > BPM_APOYO_MAX)
        out.append(_p(MAL if grave else AVISO, "El BPM",
                      "la tabla dice %.2f y la cuadricula %.2f. El multiplo limpio "
                      "mas parecido es %s (seria %.2f), asi que el chart se va "
                      "corriendo %.2f s de punta a punta y un tiempo dura %.2f s."
                      "%s" % (bpm_t, rej["bpm"], comomult,
                              rej["bpm"] * p_m / float(q_m), deriva, per_c, tercero)))

    # ============================= EL MULTIPLO =============================
    # 8.7: el arranque de CADA MISION cae sobre una pulsacion de la musica solo
    # si la mision dura un numero entero de pulsaciones. No es rojo nunca: no
    # esta roto, es como suena. Softnyx solo usa k=4 (x4) y k=8 (x2).
    comun = max(set(lens), key=lens.count) if lens else 0
    pulsos = (comun * per_c / per_v) if (comun and per_v) else 0.0
    cierra_compas = bool(pulsos) and abs(pulsos / 4.0 - round(pulsos / 4.0)) < 0.02
    if bpm_t and pulsos:
        k = int(round(pulsos))
        if abs(pulsos - k) < 0.02 and k >= 1:
            if k % 4 == 0:
                out.append(_p(OK, "El multiplo",
                              "cada mision dura %d pulsaciones = %d %s justo%s, asi "
                              "que todas arrancan en un '1'."
                              % (k, k // 4, "compas" if k == 4 else "compases",
                                 "" if k == 4 else "s")))
            else:
                out.append(_p(OK, "El multiplo",
                              "cada mision dura %d pulsaciones (%.2f compases): "
                              "arranca siempre SOBRE una pulsacion, pero va rotando "
                              "por las cuatro posiciones del compas. Softnyx no lo "
                              "hace (solo usa x2 y x4), pero no esta mal: en un tema "
                              "con bombo en los cuatro tiempos cualquier pulsacion es "
                              "un golpe (8.7)." % (k, k / 4.0)))
        else:
            ops = bpm_que_cierran(rej["bpm"], comun, 3, bpm_t)
            porx3 = ("  Este es el caso del x3: Softnyx usa x2 y x4 y nunca x3 "
                     "(8.7)." if (p_m, q_m) == (3, 1) else "")
            out.append(_p(AVISO, "El multiplo",
                          "cada mision dura %.2f pulsaciones de la musica, que no es "
                          "un numero entero: el arranque de cada mision va cayendo en "
                          "un punto distinto entre golpe y golpe (8.7). Con esta "
                          "pulsacion los BPM que cierran son %s.%s"
                          % (pulsos, ", ".join("%.2f" % b for b in ops) or "ninguno",
                             porx3)))

    # ============================= EL ARRANQUE =============================
    # CORREGIDO el 20/9/2026 (ver ARR_OK_MS). Tres cambios:
    #   1. se mide contra el tiempo DEL CHART (60/BPM de la fila), que es donde
    #      caen las flechas (ver `golpes`), y no contra el de la cuadricula. Con
    #      el de la cuadricula, toda fila x2 o x4 que arranque en la contra salia
    #      "fuera de la cuadricula" estando bien: Gee daba 276 ms de error y
    #      contra su propio tiempo da 24; "Various Artist" daba 361 y da 2.
    #   2. el liston ya no es 40 ms puestos a ojo sino lo que hacen los charts
    #      que funcionan (ARR_OK_MS).
    #   3. "no arranca en el '1' del compas" deja de ser rojo. El chart original
    #      "Baby~ ye~ ye" arranca a medio compas del '1' y anda.
    dif = ini - rej["fase"]

    def _resto(paso):
        if not paso:
            return 0.0
        n = dif / paso
        return abs(n - round(n)) * paso

    eps = _resto(per_c) * 1000.0                 # ms al tiempo del chart mas cercano
    eps_pct = (100.0 * eps / (per_c * 1000.0)) if per_c else 0.0
    d_pulso = _resto(per_v) * 1000.0             # ms a la pulsacion de la musica
    d_compas = _resto(4 * per_v) * 1000.0        # ms al '1' del compas
    pct = 100.0 * ini / (dur or 1)
    pegado = (rej["fase"] + round(dif / per_c) * per_c) if per_c else ini
    # Si la cuadricula esta MEDIDA (no viene de Virtual DJ) puede estar corrida
    # ella. COMPROBADO: de 6 canciones que ya sonaban bien, en 2 la medicion
    # discrepaba 458 y 731 ms del arranque bueno. Por eso ahi solo se avisa. Y
    # si el BPM de la tabla no es un multiplo limpio del de la cuadricula,
    # tampoco se puede mandar: las dos cuadriculas no son comparables.
    if not rej["origen"].startswith("Virtual"):
        duro = AVISO
        coletilla = ("  OJO: esto lo mido yo, no es de Virtual DJ, y MI MEDICION ES "
                     "LA QUE SE CORRE: de 9 canciones tuyas que Virtual DJ si tenia, "
                     "las 9 arrancan justo en su compas (7 a 0 ms), y en dos de ellas "
                     "mi medicion daba 458 y 731 ms de error. Arrastra la carpeta "
                     "Music/Elton/mana a Virtual DJ, deja que los analice y volve a "
                     "revisar: el programa los reconoce solos aunque tengan otro "
                     "nombre. Mientras tanto, si la cancion YA suena bien, no la "
                     "muevas.")
    elif err_m > RATIO_LIMPIO:
        duro = AVISO
        coletilla = ("  OJO: el BPM de la tabla (%.2f) no es un multiplo limpio del "
                     "de la cuadricula (%.2f), asi que las dos cuadriculas no se "
                     "pueden comparar y no se sabe cual de las dos se corre. Mira "
                     "primero El BPM." % (bpm_t, rej["bpm"]))
    else:
        duro, coletilla = MAL, ""
    if eps > ARR_OK_MS and eps_pct > ARR_MAL_PCT:
        out.append(_p(duro, "El arranque",
                      "%.4f s NO cae en la cuadricula del propio chart: esta a %.0f "
                      "ms del tiempo mas cercano, o sea el %.0f%% de un tiempo (un "
                      "tiempo dura %.0f ms). Las flechas caen entre los golpes de la "
                      "musica. Lo que hay que probar es un salto, no un retoque: el "
                      "tiempo mas cercano es %.4f. ESCUCHALO antes de cambiar nada.%s"
                      % (ini, eps, eps_pct, per_c * 1000, pegado, coletilla)))
    elif eps > ARR_OK_MS or eps_pct > ARR_MAL_PCT:
        out.append(_p(AVISO, "El arranque",
                      "%.4f s cae a %.0f ms del tiempo del chart (%.0f%% de un "
                      "tiempo), al %.1f%% de la cancion. Los charts que funcionan no "
                      "se pasan de %.0f ms (el peor es Not Your Baby, 67). Si la "
                      "cancion ya suena bien NO LA MUEVAS.%s"
                      % (ini, eps, eps_pct, pct, ARR_OK_MS, coletilla)))
    else:
        out.append(_p(OK, "El arranque",
                      "%.4f s cae sobre la cuadricula (a %.0f ms del tiempo del "
                      "chart), al %.1f%% de la cancion" % (ini, eps, pct)))
    # EL DESFASE DE 58 ms: cuanto se aparta de la costumbre oficial, que NO es
    # el "1" de Virtual DJ sino 58 ms antes (ver DESFASE_OFICIAL).
    if per_c and rej["origen"].startswith("Virtual"):
        d2 = (ini + DESFASE_OFICIAL - rej["fase"]) / per_c
        eps_of = abs(d2 - round(d2)) * per_c * 1000.0
        out.append(_p(OK if eps_of <= ARR_OK_MS else AVISO, "Contra lo oficial",
                      "los 876 charts oficiales del LoveRitmo 2020 arrancan %.0f ms "
                      "ANTES del '1' de Virtual DJ, y el mismo numero en todo el "
                      "rango de BPM (es un retardo fijo, no un porcentaje). Contra "
                      "esa costumbre, este arranque esta a %.0f ms. Lo oficial seria "
                      "%.4f. NO SE PROBO JUGANDO: es para mirar, no para correr "
                      "nada todavia."
                      % (DESFASE_OFICIAL * 1000, eps_of,
                         rej["fase"] + round(d2) * per_c - DESFASE_OFICIAL)))
    # Donde cae dentro del compas. Aparte, y nunca rojo: son dos preguntas
    # distintas y esta es la de la regla 6 (el acento va en el arranque de la
    # mision), no la de si las flechas caen sobre la musica.
    #
    # RESPALDADO el 20/9/2026 sobre los 876 charts del LoveRitmo 2020 medidos
    # contra su audio: al tiempo caen 702 de 876 dentro de 70 ms (80%), pero al
    # "1" DEL COMPAS solo 550 (63%). O sea que UNO DE CADA TRES charts oficiales
    # NO arranca en el "1". Era aviso desde antes por "Baby~ ye~ ye"; ahora son
    # 326 casos. (El "1" lo detecto yo y es la parte mas floja de mi medicion,
    # asi que el numero puede ser peor de lo que es; el sentido no cambia.)
    if eps <= ARR_OK_MS and per_v and rej["origen"].startswith("Virtual"):
        if d_pulso > ARR_OK_MS:
            out.append(_p(AVISO, "En el compas",
                          "el arranque cae en la CONTRA: esta a %.0f ms de la "
                          "pulsacion mas cercana de la musica (la pulsacion dura "
                          "%.0f ms). Las flechas caen igual sobre el chart, pero el "
                          "acento de cada mision no cae sobre un golpe (regla 6). Es "
                          "lo que le pasa a Gee, que Joel rechazo; pero tambien al "
                          "chart original 'Various Artist', asi que miralo con "
                          "ESCUCHAR antes de moverlo." % (d_pulso, per_v * 1000)))
        elif d_compas > ARR_OK_MS and cierra_compas:
            t_comp = int(round((dif / per_v) % 4)) % 4
            out.append(_p(AVISO, "En el compas",
                          "arranca en un tiempo de la musica pero en el %d del "
                          "compas, no en el '1' (a %.0f ms). El chart original "
                          "'Baby~ ye~ ye' tambien arranca a medio compas y anda, asi "
                          "que no es imposible; pero el '1' es lo que conviene buscar "
                          "(regla 6). Probalo con ESCUCHAR."
                          % (t_comp + 1, d_compas)))
    if pct < PCT_MIN:
        out.append(_p(AVISO, "Cuando empieza",
                      "al %.1f%% de la cancion; el 95%% de los 3912 charts "
                      "oficiales arranca despues del %.1f%%" % (pct, PCT_MIN)))
    elif pct > PCT_MAX:
        out.append(_p(AVISO, "Cuando empieza",
                      "al %.1f%% de la cancion; el 99%% de los 3912 charts "
                      "oficiales arranca antes del %.1f%% (la mediana es %.1f%%)"
                      % (pct, PCT_MAX, PCT_IDEAL)))
    # AVISO Y NO MAL, decidido el 19/9/2026. El unico dato aqui es una medicion
    # nuestra del audio, y de Softnyx no hay con que compararla: sus .snb estan
    # cifrados con una clave perdida, asi que de sus 1038 charts no se puede
    # medir el audio. Ademas el detector se equivocaba: de las 14 canciones que
    # marcaba, en 5 la bateria ya estaba sonando cuando arrancaba el chart
    # ("Burn Brighter" entra en el segundo 5 y decia 18). Eso ya esta arreglado
    # (ver GRAVES_RITMO), pero una medicion propia sin respaldo avisa, no manda.
    # Es el mismo criterio que "El arranque" cuando la cuadricula no es de
    # Virtual DJ.
    # RECALIBRADO el 20/9/2026 (ver RITMO_ANTES_AVISO). Antes avisaba apenas el
    # arranque se adelantaba 1 segundo a la bateria, y eso marca al 10% de los
    # charts OFICIALES. Ahora salta recien pasado el p5 de los 876.
    eb = rej.get("entra_beat") or 0
    if eb and ini < eb - RITMO_ANTES_AVISO:
        out.append(_p(AVISO, "Antes del ritmo",
                      "arranca en %.1f s y la bateria entra en %.0f s: se adelanta "
                      "%.1f s. Uno de cada diez charts oficiales arranca antes de "
                      "la bateria, asi que eso solo no esta mal, pero %.1f s es mas "
                      "de lo que hace el 95%% de ellos. OJO: el segundo %.0f lo mido "
                      "yo y me puedo equivocar. Escuchala antes de mover nada."
                      % (ini, eb, eb - ini, eb - ini, eb)))
    elif eb and ini < eb:
        out.append(_p(OK, "Antes del ritmo",
                      "arranca %.1f s antes de que yo vea entrar la bateria (en el "
                      "%.0f). No es raro: 91 de los 876 charts oficiales medidos "
                      "hacen lo mismo." % (eb - ini, eb)))

    largos = dict((c, len([v for v in fila[c].split(",") if v.strip()])) for c in LISTAS)
    n = largos["Length"]
    if len(set(largos.values())) != 1:
        malas = [c for c in LISTAS if largos[c] != n]
        out.append(_p(MAL, "Las listas",
                      "no miden todas lo mismo (Length=%d, distinto en: %s)"
                      % (n, ", ".join(malas))))
    else:
        out.append(_p(OK, "Las listas", "las 10 miden %d (una por mision)" % n))

    # EL BAILE: los bailes del juego duran 16 tiempos. Lo que una mision pasa de
    # 16, el personaje lo camina (6.3.28). En las nuestras eso son los descansos.
    try:
        _per = 60.0 / float(fila["BPM"])
        _cam = [(i + 1, (int(float(x)) - 16) * _per)
                for i, x in enumerate(fila["Length"].split(","))
                if x.strip() and int(float(x)) > 16]
    except (ValueError, ZeroDivisionError):
        _cam = []
    if _cam and not es_original(fila):
        out.append(_p(AVISO, "El baile",
                      "el personaje CAMINA %.0f s en total (%s): son descansos, "
                      "donde no sale nada y el baile de 16 tiempos se termina. Si "
                      "preferis que siga bailando: clic derecho en la lista > "
                      "'Arreglar el baile' (no toca las flechas)."
                      % (sum(x for _i, x in _cam),
                         ", ".join("mision %d: %.0f s" % c for c in _cam[:4]))))
    elif not _cam:
        out.append(_p(OK, "El baile", "ninguna mision pasa de 16 tiempos"))
    # rapidas con 3 flechas juntas: Softnyx no lo hace (ver BPM_SIN_TRES)
    if not es_original(fila) and tope_por_bpm(fila.get("BPM"), est):
        # las dos tandas (la segunda es el MissionID2, ver TANDA2_*)
        _n3 = sum(1 for c in ("MissionID1", "MissionID2")
                  for v in str(fila.get(c) or "").split(",")
                  if v.strip() and max(patron(v)) >= 3)
        if _n3:
            out.append(_p(AVISO, "3 flechas en una rapida",
                          "%d tandas tienen 3 flechas juntas. A %s BPM con %d "
                          "estrellas van como mucho 2 (Softnyx: 0 a 4%% de los "
                          "tiempos). GENERAR EL CHART ya no las pone; clic derecho > "
                          "'Rapida: pasar las 3 flechas a 2' las arregla sin regenerar."
                          % (_n3, fila.get("BPM"), est)))
    _n501 = sum(1 for v in str(fila.get("MissionDanceID") or "").split(",")
                if v.strip() == "501")
    if _n501 and not es_original(fila):
        out.append(_p(AVISO, "El baile 501",
                      "%d misiones usan el baile 501/601, y en esas el personaje "
                      "camina en medio de la mision (13 de 13 capturas de Feather). "
                      "Si lo pusiste vos para tener mas variedad, esta bien; si "
                      "camina, clic derecho en la lista > 'Mas variedad de baile' > "
                      "'Sacar la mezcla' (o 'Arreglar SOLO el baile 501') las pasa "
                      "al 511/611 sin tocar las flechas." % _n501))

    if bpm_t and tot:
        # CORREGIDO el 19/9/2026. Antes se comparaba contra `fin_beat`, que es
        # donde MI medidor deja de ver graves, y se declaraba MAL si el chart lo
        # pasaba por 2 segundos. Eso no aguanta: fin_beat se adelanta hasta 16.6 s
        # al final real del audio en los temas que se apagan de a poco, y ahi
        # queda "quedan flechas sin musica" cuando la musica sigue sonando. La
        # referencia dura pasa a ser la DURACION del audio, que no es opinable, y
        # el margen sale de los 1038 (ver FIN_PASADO_MAL / FIN_CORTO_AVISO).
        fin_chart = ini + tot * 60.0 / bpm_t
        fb = rej.get("fin_beat") or sec
        cob = tot / (max(dur - ini, 1e-9) * bpm_t / 60.0)
        pasa = fin_chart - dur
        if pasa > FIN_PASADO_MAL:
            out.append(_p(MAL, "El final",
                          "el chart llega a %.1f s y la cancion dura %.1f s: se pasa "
                          "%.1f s. Los charts oficiales se pasan en el 6%% de los "
                          "casos, pero lo mas que se pasan son 9.7 s (y en los 876 "
                          "del 2020, 6.3 s): pasado eso quedan flechas sin musica."
                          % (fin_chart, dur, pasa)))
        elif pasa > 0:
            out.append(_p(AVISO, "El final",
                          "el chart llega a %.1f s y la cancion dura %.1f s: se pasa "
                          "%.1f s. Softnyx tambien se pasa (en el 5.2%% de sus charts, "
                          "hasta 9.7 s), asi que no es grave, pero miralo."
                          % (fin_chart, dur, pasa)))
        elif dur - fin_chart > FIN_CORTO_AVISO:
            out.append(_p(AVISO, "El final",
                          "el chart corta en %.1f s y la cancion sigue hasta %.1f s: "
                          "%.0f s sin flechas. Los charts oficiales dejan mas de "
                          "%.1f s solo en el 5%% de los casos (medido en los 1038 de "
                          "2016 y otra vez en los 876 del 2020: el mismo numero)."
                          % (fin_chart, dur, dur - fin_chart, FIN_CORTO_AVISO)))
        elif fin_chart > fb + FIN_BEAT_AVISO:
            out.append(_p(AVISO, "El final",
                          "el chart llega a %.1f s, la cancion dura %.1f s y hasta ahi "
                          "llega bien, pero el ritmo que YO mido se apaga en %.1f s: "
                          "%.0f s antes. Puede ser un final que se desvanece o puede "
                          "ser mi medicion; el 5%% de los charts oficiales se pasa "
                          "tanto como esto."
                          % (fin_chart, dur, fb, fin_chart - fb)))
        else:
            out.append(_p(OK, "El final",
                          "llega a %.1f s y la cancion dura %.1f s (cobertura %.0f%%)"
                          % (fin_chart, dur, 100 * cob)))

    # Las estrellas se juzgan contra el BPM DE LA FILA, no contra el de la
    # cuadricula: si la fila va a x2 (que es lo que hace Softnyx en el 18.4% de
    # los pares), la ventana para tipear dura la mitad y admite mas estrellas.
    # Con el BPM de la cuadricula, toda fila x2 salia marcada en amarillo.
    #
    # CORREGIDO el 20/9/2026: la lista de multiplos aceptados era (0.5, 1, 2) y
    # dejaba afuera el x4, que el juego usa (In The City corre a 300 sobre una
    # cancion de 75). MUSIC WISADEL, que va a x4, salia juzgada contra 86 BPM
    # cuando el chart corre a 346. Ahora se usa el mismo criterio que El BPM:
    # si la relacion es un multiplo limpio, manda el BPM de la fila.
    bpm_est = bpm_t if (bpm_t and err_m <= RATIO_LIMPIO) else rej["bpm"]
    lo, hi = rango_estrellas(bpm_est)
    if est:
        doble = bpm_est > rej["bpm"] * 1.5
        # el multiplo de verdad, no siempre "x2": desde el 20/9/2026 tambien se
        # reconoce el x4 (MUSIC WISADEL corre a x4 y decia "(x2)")
        comoes = "%.0f BPM%s" % (bpm_est, (" (%s)" % comomult) if doble else "")
        if lo <= est <= hi:
            out.append(_p(OK, "Las estrellas", "%d (%s). A %s Softnyx usa de %d a %d"
                          % (est, nivel_de(est), comoes, lo, hi)))
        elif est > hi and not doble:
            out.append(_p(AVISO, "Las estrellas",
                          "%d a %s. Softnyx a esa velocidad usa de %d a %d. Para "
                          "hacerla mas dificil su recurso NO es subir estrellas: es "
                          "MULTIPLICAR el BPM de la fila (x2 = %.0f, x4 = %.0f). El "
                          "x2 lo usa en el %d%% de las canciones a esta velocidad."
                          % (est, comoes, lo, hi, rej["bpm"] * 2, rej["bpm"] * 4,
                             chance_x2(rej["bpm"]))))
        else:
            out.append(_p(AVISO, "Las estrellas",
                          "%d a %s. Softnyx a esa velocidad usa de %d a %d"
                          % (est, comoes, lo, hi)))

    # ----------------------------- LA VELOCIDAD (agregado el 20/9/2026)
    # Es el unico limite que se midio JUGANDO (Gee a 400 BPM, 0 puntos en 75 de
    # 75 misiones), pero el numero que estaba escrito (0.94 s) era mas estricto
    # que el propio juego. Ver VENTANA_OK / VENTANA_MAL.
    if bpm_t:
        vent = 4 * 60.0 / bpm_t
        if vent >= VENTANA_OK:
            out.append(_p(OK, "La velocidad",
                          "la ventana para tipear dura %.3f s (los 4 primeros "
                          "tiempos de cada mision). El 99%% de los 3912 charts "
                          "oficiales esta de %.3f s para arriba."
                          % (vent, VENTANA_OK)))
        elif vent >= VENTANA_MAL:
            out.append(_p(AVISO, "La velocidad",
                          "la ventana para tipear dura %.3f s: el 1%% mas rapido de "
                          "lo oficial. El chart mas rapido que existe llega a %.3f s "
                          "(LoveRitmo 2020, 363 BPM), asi que se puede. In The City "
                          "y Not Your Baby van a 0.800 y Joel las juega; APT a 0.805 "
                          "la rechazo. Esto se decide JUGANDO, no con una tabla."
                          % (vent, VENTANA_MAL)))
        else:
            out.append(_p(MAL, "La velocidad",
                          "la ventana para tipear dura %.3f s: mas rapido que los "
                          "3912 charts oficiales (2016, LoveBeat KR, Steam y "
                          "LoveRitmo 2020), que no bajan de %.3f s. Y a 0.600 s esta "
                          "MEDIDO JUGANDO que no se puede: Gee a 400 BPM saco 0 "
                          "puntos en 75 de 75 misiones (8.4.1). Bajale el BPM de la "
                          "fila." % (vent, VENTANA_MAL)))

    # ----------------------------- EL CUTOFF (agregado el 20/9/2026)
    # Avisa y nunca manda: se sabe QUE VALOR pone Softnyx, no QUE HACE.
    cut = str(fila.get("CutOff") or "").strip()
    debe = cutoff_de(est) if est else 0
    if est and cut != str(debe):
        flechas_tot = sum(sum(patron(v))
                          for v in fila["MissionID1"].split(",") if v.strip())
        try:
            cv = int(float(cut))
        except ValueError:
            cv = 0
        if cv > 100000 and flechas_tot:
            extra = ("  PERO es un numero de los grandes, y asi le pone el juego "
                     "ORIGINAL a todos sus charts: en LoveBeat KR son 1156 valores "
                     "distintos en 1157 filas, y en Steam 771 de 771. Va con cuanto "
                     "hay que tocar (unos %d por flecha+SPACE; este da %d). O sea "
                     "que esta fila viene del juego original y el valor es el suyo: "
                     "NO LO TOQUES."
                     % (CUTOFF_POR_COSA, cv / max(flechas_tot, 1)))
        else:
            extra = ""
        out.append(_p(AVISO, "El CutOff",
                      "dice %s y a %d estrellas el musictable de 2016 pone %d (usa "
                      "solo 30000 / 50000 / 70000, uno por nivel). No se sabe que "
                      "controla, asi que esto avisa nomas.%s"
                      % (cut or "nada", est, debe, extra)))
    elif est:
        out.append(_p(OK, "El CutOff",
                      "%s, que es el que Softnyx usa en %s" % (cut, nivel_de(est))))

    m1 = [v for v in fila["MissionID1"].split(",") if v.strip()]
    m2 = [v for v in fila["MissionID2"].split(",") if v.strip()]
    if m1:
        porT = [q for v in m1 for q in patron(v)]
        rep = [100.0 * porT.count(k) / len(porT) for k in range(5)]
        fl = sum(sum(patron(v)) for v in m1) / float(len(m1))
        ref = REF_FLECHAS.get(est)
        if rep[4] > 0:
            out.append(_p(MAL, "Las flechas",
                          "hay tiempos con 4 flechas (%.0f%%). No lo hace NUNCA "
                          "ninguna version: 0 de 474.532 tiempos en los 3912 charts "
                          "de 2016, LoveBeat KR, Steam y LoveRitmo 2020." % rep[4]))
        elif ref:
            peor = max(range(4), key=lambda k: abs(rep[k] - ref[k]))
            dif = abs(rep[peor] - ref[peor])
            txt = ("%.1f por mision. Por tiempo: %s   (Softnyx en %d estrellas: %s)"
                   % (fl, " ".join("%d->%.0f%%" % (k, rep[k]) for k in range(4)),
                      est, " ".join("%d->%.0f%%" % (k, ref[k]) for k in range(4))))
            out.append(_p(OK if dif <= DIF_FLECHAS_OK else
                          (AVISO if dif <= DIF_FLECHAS_MAL else MAL),
                          "Las flechas", txt))
        if est and est <= 3 and rep[3] > 0:
            out.append(_p(MAL, "Tres flechas en inicial",
                          "%.0f%% de los tiempos llevan 3. En 1-3 estrellas no va ninguna."
                          % rep[3]))
    if m2:
        # EL MissionID2 ES LA SEGUNDA TANDA (2/10/2026, ver TANDA2_*): otros 4
        # casilleros que llegan apenas se tipea la primera. "0" = no hay.
        # REF_SPACE es el reparto del MissionID2 de Softnyx, ceros incluidos.
        spT = [q for v in m2 for q in patron(v)]
        rs = [100.0 * spT.count(k) / len(spT) for k in range(5)]
        refs = REF_SPACE.get(est)
        con2 = [v for v in m2 if v != "0"]
        cuantas = ("%d de %d misiones la tienen (Softnyx: 74%%)"
                   % (len(con2), len(m2)))
        if all(int(float(v)) <= 1 for v in m2):
            # 1 de los 1038 charts de 2016 lo hace ("My first love story", 1
            # estrella, MissionID2 todo en 0), asi que raro si, imposible no.
            out.append(_p(AVISO, "La segunda tanda",
                          "no hay ninguna (MissionID2 todo en 0 o 1): todas las "
                          "misiones son de 4 casilleros. Softnyx lo hace 1 vez en "
                          "1038 charts; lo normal es que 3 de cada 4 misiones la "
                          "tengan."))
        elif rs[4] > 0:
            out.append(_p(MAL, "La segunda tanda",
                          "hay casilleros con 4 flechas (%.0f%%). Ninguna version "
                          "del juego lo hace." % rs[4]))
        elif refs:
            peor = max(range(4), key=lambda k: abs(rs[k] - refs[k]))
            d2 = abs(rs[peor] - refs[peor])
            out.append(_p(OK if d2 <= DIF_SPACE_OK else
                          (AVISO if d2 <= DIF_SPACE_MAL else MAL), "La segunda tanda",
                          "%s. Por casillero (MissionID2): %s   (Softnyx en %d "
                          "estrellas: %s)"
                          % (cuantas,
                             " ".join("%d->%.0f%%" % (k, rs[k]) for k in range(4)),
                             est, " ".join("%d->%.0f%%" % (k, refs[k]) for k in range(4)))))
        else:
            out.append(_p(OK, "La segunda tanda", "%s; sin referencia para %d "
                                                  "estrellas" % (cuantas, est)))
    # EL SPACE QUE SE VE son los tiempos SIN flechas: el juego pone uno en cada
    # uno (6.3.1.1). Sale del mismo reparto que las flechas, no del MissionID2.
    if m1 and est in REF_FLECHAS:
        vacios = rep[0]
        out.append(_p(OK, "El SPACE que se ve",
                      "%.0f%% de los tiempos no tienen flechas, y el juego pone un "
                      "SPACE en cada uno: son %.1f por mision. El juego en %d "
                      "estrellas deja %.0f%% vacios."
                      % (vacios, 4 * vacios / 100.0, est, REF_FLECHAS[est][0])))
    return out


def nota(puntos):
    if any(p["estado"] == MAL for p in puntos):
        return MAL
    if any(p["estado"] == AVISO for p in puntos):
        return AVISO
    return OK


# ======================================================== recuperar audios
BKG_SNB = JUEGO / r"MediaPath\Sound\BKG"
INDICE_SNB = PRIV / REGISTRO


def audios_perdidos(tabla):
    """Canciones tuyas cuyo .ogg ya no esta en el disco pero SI se puede rehacer.

    POR QUE PASA: el .ogg solo hace falta para MEDIR. El juego suena con el .snb,
    asi que si la carpeta de audios se vacia el juego sigue andando y no se nota
    hasta que el Estudio quiere analizar algo. Paso el 19/9/2026: de 117 archivos
    del musictable quedaban 55 en el disco.

    SE PUEDE REHACER porque el .snb es el .ogg cifrado con una clave que elegimos
    nosotros, y esta guardada en `snb_local.json`:

        ogg = descifrar(prefijo) + descifrar(snb[0:768]) + snb[768:]

    COMPROBADO el 19/9/2026 contra un .ogg que todavia existia: sale IDENTICO,
    mismo md5, 3271684 bytes.
    """
    try:
        idx = json.loads(INDICE_SNB.read_text(encoding="utf-8"))
    except Exception:
        return [], []
    puedo, no_puedo, vistos = [], [], set()
    for f in tabla.filas:
        n = f["Filename"]
        if n in vistos or es_original(f):
            continue
        vistos.add(n)
        if buscar_ogg(n) is not None:
            continue
        if n in idx and (BKG_SNB / (n + ".snb")).exists():
            puedo.append((n, f["Title"]))
        else:
            no_puedo.append((n, f["Title"]))
    return puedo, no_puedo


def recuperar_audios(nombres, aviso=None):
    """Rehace los .ogg a partir de los .snb del juego. Devuelve (hechos, fallados)."""
    # (7/10/2026) el snb_local del Estudio con las rutas de este juego (ver correr_snb_local)
    os.environ.update({k: v for k, v in entorno_snb().items() if k.startswith("ESTUDIO_")})
    import importlib.util
    spec = importlib.util.spec_from_file_location("snb_local_estudio", str(SNB_LOCAL))
    S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(S)
    dec, _enc = S.motor()
    idx = json.loads(INDICE_SNB.read_text(encoding="utf-8"))
    OGG_NUEVOS.mkdir(parents=True, exist_ok=True)
    hechos, fallados = [], []
    for i, n in enumerate(nombres):
        if aviso:
            aviso("%d de %d: %s" % (i + 1, len(nombres), n))
        try:
            pre = bytes.fromhex(idx[n]["prefijo"])
            snb = (BKG_SNB / (n + ".snb")).read_bytes()
            ogg = S.cifrar(dec, pre) + S.cifrar(dec, snb[:768]) + snb[768:]
            if ogg[:4] != b"OggS":
                raise ValueError("lo que sale no es un Ogg")
            (OGG_NUEVOS / (n + ".ogg")).write_bytes(ogg)
            hechos.append(n)
        except Exception as e:
            fallados.append((n, str(e)[:70]))
    return hechos, fallados


# ============================================================ Virtual DJ
def falta_en_vdj(tabla):
    """Que canciones tuyas NO tienen cuadricula de Virtual DJ.

    POR QUE NO SE AUTOMATIZA ABRIENDO VIRTUAL DJ POR CADA TEMA (probado el
    16/9/2026): Virtual DJ **escribe `database.xml` cuando se cierra**, no cuando
    analiza. Comprobado: el proceso llevaba 8 minutos abierto y el `database.xml`
    seguia siendo el de la sesion anterior (05:41). Para sacarle el dato a una
    cancion habria que abrir y cerrar Virtual DJ una vez por cancion.

    No hace falta: en la configuracion de Joel `analyzeSongsOnView = yes`, o sea
    que **Virtual DJ analiza solo con ver la carpeta en su navegador**. Con pasar
    una vez por la carpeta y cerrar Virtual DJ quedan todas.
    """
    faltan, tienen, vistos = [], [], set()
    for f in tabla.filas:
        n = f["Filename"]
        if n in vistos or es_original(f):
            continue
        vistos.add(n)
        ogg = buscar_ogg(n)
        if ogg is None:
            continue
        r = rejilla_vdj(n, ogg)
        if r:
            tienen.append((n, f["Title"], r.get("vdj_nombre", n)))
        else:
            faltan.append((n, f["Title"], str(ogg)))
    return faltan, tienen


# ============================================================ agregar cancion
# ================================= LAS COPIAS SORTEAN COMO SU ORIGINAL (24/9/2026)
# Joel: "cuando creo una copia, se cambia, no se replica exacto". La copia SI se
# duplica tal cual (`dict(vieja)`), pero el sorteo de flechas usa el numero de
# FILA como semilla (`ID*100 + estrellas`) y la copia tiene numeros nuevos: al
# regenerarla con los mismos ajustes salian otras flechas. `copias.json` guarda
# {fila copia: fila original} y `generar` usa la semilla de la original.
COPIAS = ESTUDIO / "copias.json"

# ============================ LOS SPACE COMO LOVERITMO 2020 (27/9/2026, 6.3.48)
# El SPACE lo pone el juego en cada tiempo sin flechas (6.3.1.1), asi que cuantos
# salen y donde lo decide el patron de flechas (MissionID1). Medido contra los
# 234 charts oficiales del 2020 con su audio:
#   * el pozo de siempre (`_flechas_softnyx.json`, promedio de los 4 juegos) da
#     mas SPACE en las dificiles (10*: 1.03 por mision contra 0.70) y deja vacio
#     el tiempo 1 de la ventana el 26-28% de las veces (Softnyx 2020: 15-20%);
#   * Softnyx pone MAS SPACE donde la musica pega fuerte (0.80 por mision) que
#     donde esta floja (0.53), con las mismas flechas: las agrupa. El sorteo de
#     siempre los tira al azar (0.86 / 0.78).
# `_flechas_2020.json` es el pozo de los 237 charts del 2020 (estrellas con
# menos de 800 misiones suman las vecinas a mitad de peso) y `repartir_space`
# lleva los patrones con mas huecos a las misiones mas fuertes. VALIDADO mitad y
# mitad (aprender en una mitad, comparar con la otra): SPACE por mision 0.68
# (real 0.69 / 0.64), tiempo vacio 1-4 = 15/21/9/23% (real 20/19/11/19), y con
# REPARTO_W = 0.25 la correlacion con la intensidad queda como la de Softnyx
# (+0.24 contra +0.15/+0.24; flojas 0.49 fuertes 0.84 contra 0.56 / 0.80).
ESTILOS = ESTUDIO / "estilos.json"
REPARTO_W = 0.25
_ENERGIA = {}


def estilo_de(nombre):
    """Con que estilo de SPACE se genera esa cancion: "2020" o "clasico".
    Las que ya estaban antes del 27/9 son "clasico": asi, al regenerarlas con los
    mismos ajustes salen las MISMAS flechas que ya estan aprobadas."""
    try:
        d = json.loads(ESTILOS.read_text(encoding="utf-8")).get("estilos", {})
    except Exception:
        d = {}
    return d.get(nombre, "clasico")


def anotar_estilo(nombre, estilo):
    try:
        todo = json.loads(ESTILOS.read_text(encoding="utf-8"))
    except Exception:
        todo = {}
    d = todo.get("estilos", {})
    if d.get(nombre, "clasico") == estilo:
        return
    if estilo == "clasico":
        d.pop(nombre, None)
    else:
        d[nombre] = estilo
    # se conserva lo demas del archivo ("partes", 6.3.54)
    todo["_nota"] = ("Filename -> estilo de SPACE con que se genera (nucleo.estilo_de). "
                     "Lo que no esta aca es 'clasico'. 'partes': las que se generan "
                     "con las flechas por partes (nucleo.partes_de).")
    todo["estilos"] = d
    ESTILOS.write_text(json.dumps(todo, indent=1, ensure_ascii=False), encoding="utf-8")


def energia_de_misiones(ogg, inicio, bpm, largos):
    """La intensidad (dB medios) de cada mision entera."""
    import numpy as np
    clave = str(ogg)
    if clave not in _ENERGIA:
        sys.path.insert(0, str(MOTOR))
        import analizar_bpm as ab
        x = ab.pcm(clave)
        h = int(ab.SR * 0.05)
        n = len(x) // h
        _ENERGIA.clear()                       # una cancion a la vez alcanza
        _ENERGIA[clave] = 10 * np.log10(
            (x[:n * h].reshape(n, h) ** 2).mean(axis=1) + 1e-10)
    e = _ENERGIA[clave]
    per = 60.0 / float(bpm)
    out, t = [], float(inicio)
    for L in largos:
        a, b = int(t / 0.05), int((t + L * per) / 0.05)
        a, b = max(0, min(a, len(e) - 1)), max(1, min(b, len(e)))
        out.append(float(np.mean(e[a:max(b, a + 1)])))
        t += L * per
    return out


# EL VOCABULARIO DE CADA CANCION (27/9/2026, 6.3.49). Softnyx sortea mision por
# mision (no encadena patrones ni sube la dificultad: medido, igual que al
# azar), PERO cada chart usa pocos patrones: 16 distintos en 28 misiones, y sus
# 5 favoritos cubren el 57%. Sorteando del pozo entero salen 21 y 40%: cada
# cancion quedaba mas variada que las de Softnyx y sin "personalidad".
# `con_vocabulario` elige (por la semilla) un chart real del 2020 de esas
# estrellas y sortea 70% de sus patrones y 30% del pozo. VALIDADO mitad y
# mitad: 16.2 y 16.0 distintos / 57% y 59% (real 16.0 y 16.5 / 57%), sin mover
# la cantidad de SPACE ni su reparto.
VOCABULARIO = 0.70
_PLANTILLAS = {}


def con_vocabulario(pf, estrellas, semilla, peso=None):
    peso = VOCABULARIO if peso is None else peso
    if not _PLANTILLAS:
        ruta = MOTOR / "_charts_2020.json"
        if not ruta.exists():
            return pf
        _PLANTILLAS.update(json.loads(ruta.read_text(encoding="utf-8")))
    k = str(estrellas)
    if k not in _PLANTILLAS:
        k = min(_PLANTILLAS, key=lambda x: abs(int(x) - estrellas))
    pl = random.Random(semilla + 1717).choice(_PLANTILLAS[k])
    tb, tp = float(sum(pf.values())) or 1.0, float(sum(pl.values())) or 1.0
    out = dict((x, (1 - peso) * v / tb) for x, v in pf.items())
    for x, v in pl.items():
        out[x] = out.get(x, 0.0) + peso * v / tp
    return out


def repartir_space(pats, energias, semilla, w=None):
    """Los MISMOS patrones, reordenados: los que tienen mas tiempos vacios (mas
    SPACE) van a las misiones donde la musica pega mas fuerte, como Softnyx.

    No es un orden estricto: con REPARTO_W la tendencia queda igual de fuerte
    que la de Softnyx (medido). Cuantas flechas hay en total no cambia."""
    import numpy as np
    n = len(pats)
    if n < 2 or len(energias) != n:
        return list(pats)
    w = REPARTO_W if w is None else w
    rnd = random.Random(semilla + 4242)
    en = np.asarray(energias, dtype=float)
    z = (en - en.mean()) / (en.std() + 1e-9)
    clave = w * z + np.array([rnd.gauss(0.0, 1.0) for _ in range(n)])
    orden_m = np.argsort(clave, kind="stable")
    huecos = [sum(1 for v in patron(p) if v == 0) for p in pats]
    orden_p = sorted(range(n), key=lambda j: (huecos[j], rnd.random()))
    out = [None] * n
    for k in range(n):
        out[int(orden_m[k])] = pats[orden_p[k]]
    return out


def _copias():
    try:
        return json.loads(COPIAS.read_text(encoding="utf-8")).get("copias", {})
    except Exception:
        return {}


def id_de_semilla(id_fila):
    """El ID cuya semilla usa esta fila: el de su original (y la original de la
    original, si es copia de una copia)."""
    c = _copias()
    visto, i = set(), str(id_fila)
    while i in c and i not in visto:
        visto.add(i)
        i = str(c[i])
    return i


def anotar_copias(pares):
    """Agrega {copia: original} a copias.json."""
    c = _copias()
    c.update(dict((str(a), str(b)) for a, b in pares))
    COPIAS.write_text(json.dumps(dict(
        _nota="Filas copia -> fila original. La copia sortea sus flechas con la "
              "semilla de la original (nucleo.id_de_semilla).", copias=c),
        indent=1, ensure_ascii=False), encoding="utf-8")


def copiar_cancion(tabla, filas, aviso=None):
    """Duplica una cancion entera en filas NUEVAS, para poder experimentar.

    POR QUE HACE FALTA UN AUDIO NUEVO. Las filas de una cancion se agrupan por
    `Filename`: si la copia compartiera el archivo con el original, el Estudio
    las tomaria como UNA sola cancion de cuatro filas y generar sobre la copia
    tocaria tambien el original, que es justo lo que se quiere evitar. Asi que
    la copia se lleva su propio `bkgNNNN`, con su .ogg y su .snb.

    No toca NADA de las filas originales. Devuelve (ids_nuevos, mensaje).
    """
    def di(t):
        if aviso:
            aviso(t)

    filas = list(filas)
    if not filas:
        return None, "no hay ninguna cancion elegida"
    viejo = filas[0]["Filename"]
    ogg = buscar_ogg(viejo)
    if ogg is None:
        return None, ("no encuentro el .ogg de %s, y hace falta para la copia.\n"
                      "Proba primero el boton 'Recuperar audios'." % viejo)

    # Los ajustes manuales pertenecen a cada version, no al archivo de audio.
    # Se leen antes de crear la copia: un JSON danado debe avisar sin dejar
    # archivos o filas nuevos a medias.
    from secciones import cargar_configuracion, guardar_configuracion
    configuraciones = [cargar_configuracion(
        ESTUDIO, "%s:%s" % (f["Filename"], f["ID"])) for f in filas]

    # EL NOMBRE NUEVO: se mira la tabla, el .ogg Y EL .snb DEL JUEGO. Lo tercero
    # se agrego el 20/9/2026: el .ogg solo hace falta para medir y esa carpeta
    # ya se vacio una vez (6.3.3), asi que de haber agregado una cancion justo
    # entonces se habria pisado el audio de otra que seguia instalada.
    # COMPROBADO que hace falta: bkg2847.snb existe y NINGUNA fila lo nombra.
    usados = _nombres_ocupados(tabla)
    n = 2800
    while (("bkg%d" % n) in usados
           or (OGG_NUEVOS / ("bkg%d.ogg" % n)).exists()
           or (BKG_SNB / ("bkg%d.snb" % n)).exists()):
        n += 1
    nombre = "bkg%d" % n
    anotar_mia(nombre)
    # la copia sortea como la original: tambien con su estilo de SPACE
    anotar_estilo(nombre, estilo_de(viejo))
    anotar_partes(nombre, partes_de(viejo))
    anotar_menos_space(nombre, menos_space_de(viejo))

    OGG_NUEVOS.mkdir(parents=True, exist_ok=True)
    destino = OGG_NUEVOS / (nombre + ".ogg")
    shutil.copy2(str(ogg), str(destino))
    di("audio copiado como %s" % destino.name)

    di("convirtiendo el audio...")
    r = correr_snb_local(destino, nombre)
    if r.returncode != 0:
        return None, "no pude convertir el audio:\n" + (r.stdout or "") + (r.stderr or "")

    titulos = set(f["Title"] for f in tabla.filas)
    base = filas[0]["Title"]
    titulo, k = base + " (copia)", 2
    while titulo in titulos:
        titulo, k = "%s (copia %d)" % (base, k), k + 1

    tope = max(int(f["ID"]) for f in tabla.filas if f["ID"].isdigit())
    nuevas = []
    for j, vieja in enumerate(filas):
        f = dict(vieja)                      # el chart entero, tal cual
        f["ID"] = f["SoundSourceSN"] = str(tope + 1 + j)
        f["Filename"] = nombre
        f["Title"] = titulo
        f["Newsong"] = "1"
        f["Popularity"] = "0"
        nuevas.append(f)
    for f, cfg in zip(nuevas, configuraciones):
        if cfg["secciones"] or cfg["inicio"] is not None:
            guardar_configuracion(ESTUDIO, "%s:%s" % (f["Filename"], f["ID"]),
                                  cfg["secciones"], inicio=cfg["inicio"])
    anotar_copias((n["ID"], v["ID"]) for n, v in zip(nuevas, filas))
    tabla.filas.extend(nuevas)

    return ([f["ID"] for f in nuevas],
            "Copia lista: %r, filas %s (%s).\n\n"
            "Es una cancion aparte, con su propio audio (%s): lo que hagas ahi NO "
            "toca a %r.\n\n"
            "Todavia NO esta en el juego: para eso el boton ENVIAR AL JUEGO."
            % (titulo, " y ".join(f["ID"] for f in nuevas),
               " y ".join(f["Difficulty"] + " estrellas" for f in nuevas),
               nombre, base))


def filas_para_pisar(tabla):
    """Filas que se pueden reemplazar: las que siguen siendo del juego.

    Vienen por ID descendente, que es el criterio que se viene usando (las del
    final son las que menos se extrañan). NUNCA devuelve filas propias.
    """
    return sorted((f for f in tabla.filas if es_original(f)),
                  key=lambda f: -int(f["ID"]))


# ===================================================== traer otros formatos
# QUE PUEDE ENTRAR AL ESTUDIO (21/9/2026, pedido de Joel: "lo puedes poner para
# seleccionar una cancion, asi sea flac o mp3, y lo convierta a un .ogg?").
#
# El juego suena con .snb, que es un .ogg cifrado, asi que .ogg es el unico
# formato que importa AL FINAL. Pero lo que uno tiene a mano casi nunca es .ogg:
# es .mp3 o .flac. Antes habia que convertirlo aparte, con otro programa, y
# recien despues traerlo. Ahora lo convierte el Estudio con ffmpeg, que ya
# estaba instalado y ya se usaba para medir y para ESCUCHAR.
FORMATOS = (".ogg", ".oga", ".mp3", ".flac", ".wav", ".m4a", ".aac", ".wma",
            ".opus", ".aiff", ".aif", ".mp4", ".m4b", ".webm", ".mkv")

# SIN PERDIDA. De estos, lo que sale del decodificador es EXACTAMENTE las mismas
# muestras que analizo Virtual DJ, asi que su cuadricula sigue valiendo despues
# de convertir y se puede heredar.
#
# MEDIDO el 21/9/2026 convirtiendo la misma cancion por los cuatro caminos y
# cruzandola contra el .ogg original (correlacion sobre los primeros 30 s):
#
#     flac -> ogg                  0.0 ms
#     wav  -> ogg                  0.0 ms
#     m4a  -> ogg                  0.0 ms
#     mp3 CON marca de gapless     0.0 ms
#     mp3 SIN marca de gapless   +25.1 ms   <-- 1105 muestras, el retardo del
#                                               codificador que nadie recorto
#
# Por eso el .mp3 no hereda: no se puede saber de antemano si el que trajo Joel
# tiene la marca, y 25 ms de duda es mucho para un arranque que se aprueba con
# 70 ms de margen (15 TER). Ahi se mide el .ogg nuevo y listo.
#
# OJO que el corrimiento NO rompe nada por si solo: el arranque se mide sobre el
# .ogg que sale de aca, y el juego suena con el .snb hecho de ESE .ogg. Todo
# queda medido contra lo mismo. Solo molesta si se trae una cuadricula de
# AFUERA, que es justo lo que se esta decidiendo aca.
SIN_PERDIDA = (".flac", ".wav", ".aiff", ".aif")

# LA CALIDAD, y por que esa. Medido sobre los 441 .ogg oficiales del LoveRitmo
# 2020: todos Vorbis estereo, 128 kbps, y 48 de cada 50 a 44100 Hz. Los .ogg que
# ya tenia Joel andan en 192. Se usa q6 (~192 kbps): es lo de Joel y queda por
# encima de lo del juego, asi la conversion nunca es la parte mas debil.
#
# NO se tocan ni el muestreo ni los canales. Remuestrear es un paso de mas que
# no hace falta (el juego acepta las dos frecuencias: hay oficiales a 48000) y
# aca el que sobra molesta, porque lo que se mide son milisegundos.
CALIDAD_OGG = "6"


def convertir_a_ogg(origen, destino):
    """Pasa cualquier audio a .ogg Vorbis. None si salio bien, o el error.

    `-vn -map 0:a:0` deja afuera la tapa del disco (en un .mp3 viaja como si
    fuera video, y en un .ogg no pinta nada) y se queda con la primera pista de
    audio. `-map_metadata -1` tira las etiquetas: el titulo y el cantante ya se
    preguntan en la ventana y van a la tabla, no al archivo.
    """
    origen, destino = Path(origen), Path(destino)
    orden = [FFMPEG, "-v", "error", "-y", "-i", str(origen),
             "-vn", "-map", "0:a:0", "-map_metadata", "-1",
             "-c:a", "libvorbis", "-q:a", CALIDAD_OGG, str(destino)]
    try:
        r = subprocess.run(orden, capture_output=True, text=True)
    except OSError:
        return ("no encuentro ffmpeg. Es el mismo que usa el Estudio para medir "
                "y para ESCUCHAR, asi que tiene que estar en el PATH.")
    if r.returncode != 0:
        return ("ffmpeg no pudo convertir %s:\n\n%s"
                % (origen.name, (r.stderr or r.stdout or "")[-600:]))
    if not destino.exists() or destino.stat().st_size < 1024:
        return "la conversion de %s salio vacia" % origen.name
    return None


# ================================== RECORTAR EL AUDIO (24/9/2026, pedido de Joel)
# "Todo ese espacio libre solo habla mandando saludos": el final de EoO (copia)
# son ~20 s sin ritmo. Se recorta la cancion a [ini, fin] del audio original.
#
# QUE SE TOCA Y CUANDO. Nada hasta ENVIAR AL JUEGO: el recorte queda pendiente
# y se ve en el mapa. Al enviar: 1) se prepara el .ogg recortado aparte (si
# ffmpeg falla, no se envia nada), 2) se ajustan TODAS las filas de esa cancion
# (`recortar_filas`), 3) se escribe la tabla, 4) recien ahi se instala el audio
# nuevo y se rehace el .snb (snb_local.py, que tambien pone al dia la tabla de
# verificacion del juego). El .ogg y el .snb de antes quedan en la papelera.
# Las canciones originales del juego no se recortan.
FUNDIDO = 2.0            # segundos de fundido al final del recorte


def recorte_recomendado(rej, fila, fin_flechas=None):
    """Donde conviene cortar. Devuelve dict(ini, fin, motivo); None = no hace falta.

    * FINAL: si el ultimo corte del ritmo (`cortes_de_ritmo`) llega hasta el final
      del audio y dura 5 s o mas, se corta 1 s despues de que empieza (el fundido
      cubre ese segundo). Si no, si el ritmo termina 5 s o mas antes del final.
    * INICIO: solo si la cancion ARRANCA con un corte de 8 s o mas que termina
      antes del arranque del chart; se deja 2 s antes de que entre el ritmo.
    """
    dur = float(rej.get("dur") or 0)
    if not dur:
        return dict(ini=None, fin=None, motivo="no se pudo medir el audio")
    ini_chart = float(fila.get("StartDelayTime") or 0)
    cortes = cortes_de_ritmo(rej, 0.0, dur)
    fin = ini = None
    motivos = []
    # LO PRIMERO: donde terminan las ultimas flechas del chart (con los descansos
    # que marco el usuario). En EoO el final hablado tiene un ritmo de fondo (el
    # pulso mide 3-4, como en el medio de la cancion): midiendo no se distingue,
    # pero Joel ya lo habia marcado como descanso.
    if fin_flechas is not None and dur - fin_flechas >= 8.0:
        fin = round(fin_flechas + 1.0, 2)
        motivos.append("después de las últimas flechas (%d:%02d) quedan %.0f s de "
                       "audio sin nada que tocar"
                       % (int(fin_flechas) // 60, int(fin_flechas) % 60,
                          dur - fin_flechas))
    elif cortes and cortes[-1][1] >= dur - 2.0 and dur - cortes[-1][0] >= 5.0:
        fin = round(cortes[-1][0] + 1.0, 2)
        motivos.append("desde %d:%02d no hay ritmo hasta el final (%.0f s)"
                       % (int(cortes[-1][0]) // 60, int(cortes[-1][0]) % 60,
                          dur - cortes[-1][0]))
    elif rej.get("fin_beat") and dur - float(rej["fin_beat"]) >= 5.0:
        fin = round(float(rej["fin_beat"]) + 1.0, 2)
        motivos.append("el ritmo termina %.0f s antes del final"
                       % (dur - float(rej["fin_beat"])))
    if (cortes and cortes[0][0] <= 1.0 and cortes[0][1] - cortes[0][0] >= 8.0
            and cortes[0][1] < ini_chart - 2.0):
        ini = round(max(0.0, cortes[0][1] - 2.0), 2)
        motivos.append("la cancion arranca con %.0f s sin ritmo" % cortes[0][1])
    return dict(ini=ini, fin=fin, motivo="; ".join(motivos) or
                "no hace falta: el ritmo sigue hasta el final")


# ---- EL ECO DEL FINAL (25/9/2026, pedido de Joel) -------------------------
# `aecho=in_gain:out_gain:delays:decays`. Cada grupo de delays/decays es un
# rebote: mas rebotes y mas separados = mas cola, mas parecido a una reverb.
# ffmpeg no trae reverb de verdad (no hay `areverb`), asi que la cola se arma
# con varios ecos encadenados, que es lo que se puede hacer sin plugins.
#
# LA COLA SE METE EN EL SILENCIO, y eso es lo que se buscaba (Joel, 25/9/2026:
# "¿el eco puede formar en el silencio el eco que rebota? ... le puede dar como
# una forma de que ahí termina la música"). MEDIDO con un tono de 1 s: `aecho`
# alarga el sonido EXACTAMENTE lo que dura su rebote mas largo. Los primeros
# valores daban colas de 0.15 a 0.54 s -- demasiado corto para que se sienta.
# Encadenar dos `aecho` multiplica los rebotes y estira la cola:
#
#     0.9:0.35:150:0.22                             -> 0.15 s de cola
#     0.8:0.75:180|360|540:...                      -> 0.54 s
#     0.8:0.8:400|800|1200:...                      -> 1.20 s
#     aecho 300|600 + aecho 900|1800                -> 2.40 s
#
# Los de abajo son el resultado de esa medicion. El valor es el FILTRO ENTERO
# (no solo los parametros) porque "largo" son dos ecos encadenados.
#
# LOS DOS PRIMEROS NUMEROS VAN EN 1, Y NO ES UN DETALLE. En `aecho` son
# `in_gain` y `out_gain`: el primero multiplica la señal que ENTRA y el segundo
# todo lo que SALE. Con 0.8 y 0.8 el sonido original quedaba en 0.64 de su
# volumen -- MEDIDO: 2 dB menos de RMS. Y como el eco va solo en el tramo final,
# eso metia un ESCALON de volumen justo ahi. Joel: "cuando le activo el eco se
# baja el volumen, ya me arruinó el final". Con 1 y 1 la señal original pasa
# INTACTA y el eco se suma encima: medido, +0.26 / +0.43 / +0.69 dB, que es la
# energia del propio eco y no se oye como corte.
ECOS = {
    "no": None,
    "suave": "aecho=1:1:200|400:0.25|0.15",
    "medio": "aecho=1:1:400|800|1200:0.3|0.2|0.12",
    "largo": "aecho=1:1:300|600:0.3|0.2,aecho=1:1:900|1800:0.25|0.15",
}
# Cuanto se pasa del final cada uno, en segundos (medido). Sirve para avisar
# cuanto silencio conviene dejar para que la cola no quede cortada.
ECO_COLA = {"no": 0.0, "suave": 0.4, "medio": 1.2, "largo": 2.4}
# Las curvas del fundido de salida que entiende `afade`. La de ffmpeg por
# defecto (`tri`) es una recta y se escucha como un corte que baja parejo; las
# otras dos aflojan al final, que es lo que suena a "se apaga solo".
CURVAS = {"pareja": "tri", "suave": "qsin", "muy suave": "exp"}
ECO_SEG = 8.0            # cuantos segundos del final lleva el eco, por defecto


def edicion_de(ed, dur):
    """La edicion completa del audio.

    {ini, fin, sil_ini, sil_fin, fade_in, fade_out, curva, eco, eco_seg}

    Acepta la forma vieja (ini, fin). El audio nuevo es: `sil_ini` segundos de
    silencio + el audio original de `ini` a `fin` (con el eco en sus ultimos
    `eco_seg` y los fundidos) + `sil_fin` de silencio. Sin `fade_out` explicito,
    se funde 2 s solo si se corto el final.
    """
    if ed is None:
        return None
    if isinstance(ed, (tuple, list)):
        ed = dict(ini=ed[0], fin=ed[1])
    d = dict(ini=0.0, fin=float(dur), sil_ini=0.0, sil_fin=0.0, fade_in=0.0)
    d.update(dict((k, v) for k, v in ed.items() if v is not None))
    if "fade_out" not in ed or ed.get("fade_out") is None:
        d["fade_out"] = FUNDIDO if d["fin"] < float(dur) - 0.05 else 0.0
    curva = str(d.pop("curva", "pareja") or "pareja")
    eco = str(d.pop("eco", "no") or "no")
    eco_seg = d.pop("eco_seg", ECO_SEG)
    for k in d:
        d[k] = round(float(d[k]), 3)
    d["curva"] = curva if curva in CURVAS else "pareja"
    d["eco"] = eco if eco in ECOS else "no"
    d["eco_seg"] = round(float(eco_seg or 0), 3)
    return d


def edicion_vacia(ed, dur):
    """True si la edicion no cambia nada del audio."""
    d = edicion_de(ed, dur)
    return (d["ini"] <= 0.001 and d["fin"] >= float(dur) - 0.05 and not d["sil_ini"]
            and not d["sil_fin"] and not d["fade_in"] and not d["fade_out"]
            and d["eco"] == "no")


def recortar_filas(fila, ed, t_fin=None):
    """Las listas de UNA fila para el audio editado (ver `edicion_de`).

    El arranque se corre lo que se corto del inicio MENOS el silencio que se
    agrego (asi las flechas siguen cayendo en el mismo lugar de la musica) y se
    sacan las misiones cuya ventana de flechas no termina antes del final
    nuevo. La camara del final (241) pasa a la ultima. Acepta tambien la forma
    vieja `recortar_filas(fila, t_ini, t_fin)`.
    """
    if not isinstance(ed, dict):
        ed = dict(ini=ed, fin=t_fin)
    t_ini = float(ed.get("ini") or 0.0)
    t_fin = float(ed["fin"])
    sil_ini = round(float(ed.get("sil_ini") or 0.0), 3)
    sil_fin = float(ed.get("sil_fin") or 0.0)
    per = 60.0 / float(fila["BPM"])
    t0 = float(fila["StartDelayTime"])
    if t_ini >= t0 - 0.5:
        raise RuntimeError("El inicio del recorte (%.1f s) cae despues del arranque "
                           "de las flechas (%.1f s): se perderia el principio del "
                           "chart." % (t_ini, t0))
    listas = dict((c, [v for v in str(fila.get(c) or "").split(",") if v.strip()])
                  for c in LISTAS)
    L = [int(float(x)) for x in listas["Length"]]
    k, t = 0, t0
    for x in L:
        if t + 4 * per > t_fin - 0.3:
            break
        k += 1
        t += x * per
    if k == 0:
        raise RuntimeError("Con ese recorte no queda ninguna mision.")
    fin_cam = listas["DanceCameraID"][-1] if listas["DanceCameraID"] else "241"
    nuevos = dict((c, listas[c][:k]) for c in LISTAS)
    nuevos["DanceCameraID"][-1] = fin_cam
    nuevos = dict((c, ",".join(v)) for c, v in nuevos.items())
    nuevos["StartDelayTime"] = "%g" % round(t0 - t_ini + sil_ini, 4)
    nuevos["Second"] = str(int(round(sil_ini + (t_fin - t_ini) + sil_fin)))
    return nuevos, len(L) - k


def preparar_recorte_audio(filename, ed, t_fin=None, salida=None):
    """El .ogg editado (recorte, silencios y fundidos), APARTE: no instala nada.

    `salida` es para escuchar el resultado antes de enviar; sin eso va al
    archivo temporal que usa ENVIAR. Acepta la forma vieja (filename, ini, fin).
    """
    if not isinstance(ed, dict):
        ed = dict(ini=ed, fin=t_fin)
    ogg = OGG_DIRS[0] / (filename + ".ogg")
    if not ogg.exists():
        raise RuntimeError("No encuentro %s en la carpeta de audios nuevos." % ogg.name)
    ed = edicion_de(ed, _dur_de_archivo(ogg) or float(ed["fin"]))
    tmp = Path(salida) if salida else ogg.with_name(filename + "_recorte_tmp.ogg")
    largo = ed["fin"] - ed["ini"]
    # EL RECORTE VA ADENTRO DE LA CADENA (atrim), no con -ss/-t: con -t el
    # silencio agregado (adelay/apad) quedaba afuera del largo y se perdia el final
    eco = ECOS.get(ed["eco"])
    seg = min(float(ed["eco_seg"] or 0), largo)
    con_eco = bool(eco) and seg > 0.2
    if con_eco:
        # EL FUNDIDO DE SALIDA VA ANTES DEL ECO, NO DESPUES. MEDIDO el
        # 25/9/2026: `afade=t=out` pone la ganancia en CERO a partir de que
        # termina, asi que aplicado despues del eco le borra la cola entera
        # (el sonido terminaba en 0.996 s en vez de 3.400 s). Puesto antes, la
        # musica baja y el eco de esa musica se va apagando solo, que es lo que
        # se busca. Por eso el tramo con eco se estira, si hace falta, para que
        # el fundido entre entero adentro.
        seg = min(max(seg, ed["fade_out"]), largo)

    # Lo que va DESPUES (sobre la cancion ya armada): entrada y silencios.
    cola = []
    if ed["fade_in"] > 0:
        cola.append("afade=t=in:st=0:d=%.3f" % ed["fade_in"])
    if ed["fade_out"] > 0 and not con_eco:
        cola.append("afade=t=out:st=%.3f:d=%.3f:curve=%s"
                    % (max(0.0, largo - ed["fade_out"]), ed["fade_out"],
                       CURVAS.get(ed["curva"], "tri")))
    if ed["sil_ini"] > 0:
        cola.append("adelay=delays=%d:all=1" % int(round(ed["sil_ini"] * 1000)))
    if ed["sil_fin"] > 0:
        cola.append("apad=pad_dur=%.3f" % ed["sil_fin"])

    if con_eco:
        # EL ECO VA SOLO EN LOS ULTIMOS `seg` SEGUNDOS, no en toda la cancion.
        # Por eso hace falta un filter_complex y no alcanza con -af: se parte el
        # tramo en cuerpo + cola, se le pone `aecho` SOLO a la cola y se pegan.
        # La colita del eco se pasa un poco del final (es lo que se quiere): si
        # se corto el final conviene dejar algo de "Silencio al final" para que
        # no quede cortada.
        corte = largo - seg
        # el fundido, adentro del tramo con eco y ANTES de los rebotes
        baja = ""
        if ed["fade_out"] > 0:
            baja = ",afade=t=out:st=%.3f:d=%.3f:curve=%s" % (
                max(0.0, seg - ed["fade_out"]), ed["fade_out"],
                CURVAS.get(ed["curva"], "tri"))
        # `eco` ya es el filtro entero (puede ser dos `aecho` encadenados).
        fc = ("[0:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,asplit=2[c][t];"
              "[c]atrim=end=%.3f,asetpts=PTS-STARTPTS[c2];"
              "[t]atrim=start=%.3f,asetpts=PTS-STARTPTS%s,%s[t2];"
              "[c2][t2]concat=n=2:v=0:a=1%s[out]"
              % (ed["ini"], ed["fin"], corte, corte, baja, eco,
                 ("," + ",".join(cola)) if cola else ""))
        orden = [FFMPEG, "-v", "error", "-y", "-i", str(ogg),
                 "-filter_complex", fc, "-map", "[out]", "-map_metadata", "-1",
                 "-c:a", "libvorbis", "-q:a", CALIDAD_OGG, str(tmp)]
    else:
        filtros = ["atrim=start=%.3f:end=%.3f" % (ed["ini"], ed["fin"]),
                   "asetpts=PTS-STARTPTS"] + cola
        orden = [FFMPEG, "-v", "error", "-y", "-i", str(ogg),
                 "-map", "0:a:0", "-map_metadata", "-1",
                 "-af", ",".join(filtros),
                 "-c:a", "libvorbis", "-q:a", CALIDAD_OGG, str(tmp)]
    r = subprocess.run(orden, capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 1024:
        raise RuntimeError("ffmpeg no pudo recortar %s:\n%s"
                           % (ogg.name, (r.stderr or r.stdout or "")[-500:]))
    return tmp


def instalar_recorte_audio(filename, tmp):
    """Pone el .ogg recortado en su lugar y rehace el .snb. Lo de antes, a la papelera."""
    ogg = OGG_DIRS[0] / (filename + ".ogg")
    snb = BKG_SNB / (filename + ".snb")
    resp = PAPELERA / (time.strftime("%Y%m%d_%H%M%S") + "_antes_del_recorte_" + filename)
    resp.mkdir(parents=True, exist_ok=True)
    for f in (ogg, snb):
        if f.exists():
            shutil.copy2(str(f), str(resp / f.name))
    os.replace(str(tmp), str(ogg))
    r = correr_snb_local(ogg, filename)
    if r.returncode != 0:
        # se devuelve el audio de antes: mejor largo que roto
        shutil.copy2(str(resp / ogg.name), str(ogg))
        if (resp / snb.name).exists():
            shutil.copy2(str(resp / snb.name), str(snb))
        raise RuntimeError("no pude rehacer el .snb de %s (volvi al audio de antes):\n%s"
                           % (filename, (r.stdout or "") + (r.stderr or "")))
    return resp


# ============================= NOMBRES QUE EL JUEGO PUEDE GUARDAR (23/9/2026)
# El musictable guarda el texto en cp1252 (letras occidentales). Joel agrego
# "훗 Hoot" y "다시 만난 세계 Into The New World" (Girls' Generation) y el ENVIAR
# se freno con UnicodeEncodeError: UN nombre malo trababa el envio de TODA la
# tabla. Ademas se veian como "í›— Hoot": `datos_del_audio` leia la salida de
# ffprobe (UTF-8) con la codificacion de Windows.
def texto_para_juego(s):
    """El texto tal como lo puede guardar el juego. Lo que ya se puede, no se toca.

    Si no se puede: 1) se deshace el mojibake (UTF-8 leido como cp1252), 2) se
    quedan solo las letras que existen en cp1252 (el coreano se va), 3) se
    ordenan los espacios. Devuelve la forma interna del programa (latin1 byte
    a byte, ver musictable_tool.CODIF).
    """
    s = "" if s is None else str(s)
    try:
        s.encode("latin1")
        return s
    except UnicodeEncodeError:
        pass
    try:
        arreglado = s.encode("cp1252").decode("utf-8")
        s = arreglado
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    t = s.encode("cp1252", errors="ignore").decode("latin1")
    t = re.sub(r"\s+", " ", t).strip(" -_|·—–")
    return t.strip()


PAPELERA = ESTUDIO / "papelera"


def borrar_cancion(tabla, filename):
    """Saca de la tabla (en memoria) TODAS las filas de una cancion nuestra.

    Pedido de Joel (24/9/2026): clic derecho > "Eliminar canción". Llega al juego
    con ENVIAR, como todo. Las originales no se tocan. Devuelve los IDs sacados.
    """
    filas = [f for f in tabla.filas if f["Filename"] == filename]
    if not filas:
        raise RuntimeError("No encuentro la cancion %s." % filename)
    if any(es_original(f) for f in filas):
        raise RuntimeError("Esa cancion vino con el juego: no se borra.")
    tabla.filas = [f for f in tabla.filas if f["Filename"] != filename]
    return [f["ID"] for f in filas]


def olvidar_copias(ids):
    """Saca esos IDs de copias.json, como copia y como original.

    Si se borra una fila que era la ORIGINAL de una copia, la copia se queda
    apuntando a una fila que ya no existe y `id_de_semilla` devolveria un ID
    fantasma. Como la copia ya tiene sus flechas generadas, lo unico que cambia
    es que a partir de ahora sortea con su propia semilla.
    """
    c = _copias()
    fuera = set(str(i) for i in ids)
    nuevo = dict((k, v) for k, v in c.items()
                 if k not in fuera and str(v) not in fuera)
    if nuevo != c:
        COPIAS.write_text(json.dumps(dict(
            _nota="Filas copia -> fila original. La copia sortea sus flechas con la "
                  "semilla de la original (nucleo.id_de_semilla).", copias=nuevo),
            indent=1, ensure_ascii=False), encoding="utf-8")
    return len(c) - len(nuevo)


def borrar_version(tabla, id_fila):
    """Saca UNA fila (una dificultad) y deja las demas de esa cancion.

    Pedido de Joel (25/9/2026): `borrar_cancion` se lleva las tres versiones
    juntas porque agrupa por `Filename`, y a veces se quiere tirar solo una.

    EL AUDIO NO SE TOCA NUNCA: las versiones que quedan lo siguen usando. Por eso
    esto no pregunta por la papelera, a diferencia de `borrar_cancion`.

    Se niega si es la UNICA que queda: eso ya es borrar la cancion entera, y hay
    que hacerlo por el otro camino para que pregunte que hacer con el audio.
    """
    f = next((x for x in tabla.filas if str(x["ID"]) == str(id_fila)), None)
    if f is None:
        raise RuntimeError("No encuentro la fila %s." % id_fila)
    if es_original(f):
        raise RuntimeError("Esa cancion vino con el juego: no se borra.")
    hermanas = [x for x in tabla.filas if x["Filename"] == f["Filename"]]
    if len(hermanas) <= 1:
        raise RuntimeError(
            "Es la unica version de \"%s\". Para sacarla usa \"Eliminar "
            "cancion...\", que ademas pregunta que hacer con el audio."
            % f["Title"])
    tabla.filas = [x for x in tabla.filas if str(x["ID"]) != str(id_fila)]
    olvidar_copias([f["ID"]])
    return f, len(hermanas) - 1


def audio_a_la_papelera(filename):
    """Mueve el .ogg (del Estudio) y el .snb (del juego) a `papelera\\<fecha>\\`.

    NO BORRA NADA: si hubo un error, se devuelven a mano desde ahi. Se llama
    DESPUES de ENVIAR, cuando la tabla del juego ya no nombra ese archivo: antes
    dejaria una cancion en el juego sin su audio. El registro de claves y
    `mias.json` se dejan como estan (un nombre de mas no molesta, y sirve si se
    devuelve el audio). Devuelve lo que movio.
    """
    destino = PAPELERA / time.strftime("%Y%m%d_%H%M%S")
    movidos = []
    ogg = OGG_DIRS[0] / (filename + ".ogg")     # solo la de NUESTRA carpeta
    for origen in (ogg, BKG_SNB / (filename + ".snb")):
        if origen and Path(origen).exists():
            destino.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origen), str(destino / Path(origen).name))
            movidos.append(str(destino / Path(origen).name))
    return movidos


def renombrar(tabla, filename, titulo, cantante):
    """Cambia el titulo y el cantante de TODAS las filas de una cancion nuestra.

    Pedido de Joel (23/9/2026): clic derecho > "Cambiar nombre". Las originales
    del juego no se tocan. Devuelve (ids cambiados, titulo y cantante finales).
    """
    filas = [f for f in tabla.filas if f["Filename"] == filename]
    if not filas:
        raise RuntimeError("No encuentro la cancion %s." % filename)
    if any(es_original(f) for f in filas):
        raise RuntimeError("Esa cancion vino con el juego: su nombre no se toca.")
    tit = texto_para_juego(titulo)
    can = texto_para_juego(cantante)
    if not tit:
        raise RuntimeError("El titulo quedo vacio: el juego solo guarda letras "
                           "occidentales (con acentos si, coreano o japones no).")
    for f in filas:
        f["Title"] = tit
        f["Singer"] = can
    return [f["ID"] for f in filas], tit, can


def datos_del_audio(ruta):
    """Titulo y cantante, de las etiquetas del archivo o del nombre.

    Un .mp3 o un .flac casi siempre los traen adentro, asi que la ventana llega
    con los campos ya llenos. Si no los trae, se prueba con el nombre
    "Cantante - Titulo", que es como viene casi todo lo que uno baja.

    Se miran las etiquetas del CONTENEDOR y las de la PISTA: en un .mp3 estan en
    el contenedor y en un .ogg en la pista (comprobado con ffprobe).
    """
    ruta = Path(ruta)
    baja = {}
    try:
        # encoding="utf-8": ffprobe escribe UTF-8. Sin esto Python lo leia con la
        # codificacion de Windows y "훗 Hoot" llegaba como "í›— Hoot".
        r = subprocess.run([FFPROBE, "-v", "error", "-show_format",
                            "-show_streams", "-of", "json", str(ruta)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        d = json.loads(r.stdout or "{}")
        crudas = dict(d.get("format", {}).get("tags", {}) or {})
        for s in d.get("streams", []):
            crudas.update(s.get("tags", {}) or {})
        baja = dict((k.lower(), (v or "").strip()) for k, v in crudas.items()
                    if isinstance(v, str))
    except Exception:
        pass
    tit = baja.get("title", "")
    can = baja.get("artist", "") or baja.get("album_artist", "")
    if not tit:
        tit = ruta.stem
        if not can and " - " in tit:
            can, tit = [p.strip() for p in tit.split(" - ", 1)]
    # lo que el juego no puede guardar (coreano, japones...) se saca ya aca, asi
    # la ventana de agregar muestra el nombre que va a quedar
    tit_j = texto_para_juego(tit.strip())
    can_j = texto_para_juego(can.strip())
    if not tit_j:
        tit_j = texto_para_juego(ruta.stem) or "Cancion nueva"
    return dict(titulo=tit_j, cantante=can_j,
                titulo_original=tit.strip(), cantante_original=can.strip())


def agregar_ogg(ruta_audio, tabla, titulo, cantante, estrellas_a=3,
                estrellas_b=7, genero="Dance", aviso=None, auto=True,
                por_musica=False, destino=None, niveles=None, frases="auto"):
    """Trae una cancion, le da un bkg nuevo y crea las dos filas ya generadas.

    ACEPTA CUALQUIER FORMATO desde el 21/9/2026 (FORMATOS): si no es .ogg lo
    convierte con ffmpeg en el mismo paso. Antes habia que convertirlo afuera.

    Con `auto=True` (lo normal) NO usa las estrellas que le pasan: las elige
    despues de medir la cancion, con la misma regla que el boton "Arreglar las
    estrellas" — la mediana de Softnyx para el BPM de cada fila. Antes ponia 3 y
    7 fijos sin mirar el BPM, y a 200 BPM eso se queda corto (ahi Softnyx usa 5
    y 10) mientras que a 88 BPM el 7 esta directamente fuera de rango.

    Y si la cancion es lenta le pone el x2 a la dificil, que es lo que hace
    Softnyx: por debajo de 100 BPM lo usa en la mayoria de los casos, y es la
    unica forma de que una cancion asi tenga una version de 10 estrellas.

    AGREGA DOS FILAS AL FINAL. No hace falta pisar ninguna cancion.

    COMPROBADO EN EL JUEGO el 19/9/2026. Se creia que el musictable tenia 230
    filas FIJAS. Es falso: el cliente acepto una tabla de 231 filas, la cancion
    nueva salio en la lista y se jugo entera. El crash que habia dado origen a
    la regla fue por PERDER coordenadas ;X, no por agregar filas (PARTE 13 del
    informe). Ademas este mismo cliente ya carga itemtable.slk con 12513 filas.

    Hasta ese dia esta funcion hacia `tabla.filas.append(...)` y el escritor las
    DESCARTABA en silencio, asi que "Agregar cancion" decia "listo" y al juego
    no llegaba nada. Ahora `musictable_tool.importar` sabe agregarlas.

    `destino` sigue existiendo para REEMPLAZAR dos filas en vez de agregar (por
    ejemplo para recuperar una fila de prueba). Nunca pisa una cancion propia, y
    conserva el `ID` y el `SoundSourceSN` de la fila destino.

    NO ESCRIBE EL MUSICTABLE. Deja los cambios en memoria; al juego llegan
    recien con `tabla.guardar()` (el boton ENVIAR AL JUEGO), que ademas hace el
    respaldo fechado. Lo que si deja en el disco son el .ogg y el .snb.
    """
    def di(t):
        if aviso:
            aviso(t)
    ruta_audio = Path(ruta_audio)
    # CUANTAS FILAS SE CREAN (22/9/2026, pedido de Joel). `niveles` es una lista
    # de (nivel, estrellas): una fila por nivel pedido, ordenadas de la mas facil
    # a la mas dificil. Sin `niveles`, las dos de siempre. Pisar filas que ya
    # existen sigue siendo de a dos: es lo unico que `destino` sabe hacer.
    _orden = [n for _a, _z, n in NIVELES]
    pedidos = sorted([(n, e) for n, e in (niveles or []) if n in _orden],
                     key=lambda p: _orden.index(p[0]))
    if destino:
        pedidos = []
    cuantas = len(pedidos) if pedidos else 2
    ests = [e for _n, e in pedidos] if pedidos else [estrellas_a, estrellas_b]
    # EL NOMBRE NUEVO: se mira la tabla, el .ogg Y EL .snb DEL JUEGO. Lo tercero
    # se agrego el 20/9/2026: el .ogg solo hace falta para medir y esa carpeta
    # ya se vacio una vez (6.3.3), asi que de haber agregado una cancion justo
    # entonces se habria pisado el audio de otra que seguia instalada.
    # COMPROBADO que hace falta: bkg2847.snb existe y NINGUNA fila lo nombra.
    usados = _nombres_ocupados(tabla)
    n = 2800
    while (("bkg%d" % n) in usados
           or (OGG_NUEVOS / ("bkg%d.ogg" % n)).exists()
           or (BKG_SNB / ("bkg%d.snb" % n)).exists()):
        n += 1
    nombre = "bkg%d" % n
    anotar_mia(nombre)
    anotar_estilo(nombre, "2020")      # las nuevas: SPACE como LoveRitmo 2020
    anotar_partes(nombre, True)        # y las flechas por partes (6.3.54)
    OGG_NUEVOS.mkdir(parents=True, exist_ok=True)
    # OJO: `destino` es el parametro (que filas pisar). El .ogg copiado va en
    # `copia`, que antes tambien se llamaba `destino` y se pisaban entre si.
    copia = OGG_NUEVOS / (nombre + ".ogg")
    ext = ruta_audio.suffix.lower()
    rej_fuente = None
    if ext in (".ogg", ".oga"):
        shutil.copy2(str(ruta_audio), str(copia))
        di("copiado como %s" % copia.name)
    else:
        di("convirtiendo el %s a .ogg..." % ext.lstrip("."))
        # LA CUADRICULA DEL ARCHIVO ORIGINAL, antes de convertirlo. Si Virtual
        # DJ ya habia analizado el .flac, esa cuadricula es la buena y se pierde
        # al convertir (el .ogg nuevo no tiene ni el nombre ni el tamano ni el
        # md5 del fuente, que son las tres formas de encontrarla). Solo para los
        # formatos SIN PERDIDA: ver el comentario ahi arriba.
        if ext in SIN_PERDIDA:
            rej_fuente = rejilla_vdj(ruta_audio.stem, ruta_audio)
        err = convertir_a_ogg(ruta_audio, copia)
        if err:
            return None, err
        di("convertido a %s" % copia.name)

    di("convirtiendo el audio...")
    r = correr_snb_local(copia, nombre)
    if r.returncode != 0:
        return None, "no pude convertir el audio:\n" + (r.stdout or "") + (r.stderr or "")

    if destino:
        nuevas = [tabla.por_id(i) for i in destino]
        if any(f is None for f in nuevas):
            return None, "no encontre alguna de las filas %s" % (destino,)
        propias = [f["ID"] for f in nuevas if not es_original(f)]
        if propias:
            return None, ("las filas %s son canciones tuyas y no las voy a pisar"
                          % ", ".join(propias))
        pisadas = ["%s (%s)" % (f["ID"], f["Title"]) for f in nuevas]
    else:
        # filas NUEVAS al final. Los IDs siguen al mayor que haya, y el
        # SoundSourceSN va igual al ID, como en todas las demas.
        tope = max(int(f["ID"]) for f in tabla.filas if f["ID"].isdigit())
        molde = tabla.filas[-1]
        nuevas = []
        for k in range(cuantas):
            f = dict(molde)
            f["ID"] = f["SoundSourceSN"] = str(tope + 1 + k)
            tabla.filas.append(f)
            nuevas.append(f)
        pisadas = []

    for f, est in zip(nuevas, ests):
        # el ID y el SoundSourceSN se CONSERVAN: son los que pide el cliente
        f["Title"] = texto_para_juego(titulo) or "Cancion nueva"
        f["Singer"] = texto_para_juego(cantante)
        f["Genre"] = genero
        f["Filename"] = nombre
        f["Popularity"] = "0"
        f["Newsong"] = "1"
        f["Difficulty"] = str(est)
        f["CutOff"] = str(cutoff_de(est))

    di("midiendo la cuadricula y el tempo...")
    # buscar_bpm: la fila es una COPIA de un molde, asi que su BPM es el de otra
    # cancion. Sin esto la cuadricula sale con el tempo del vecino (22/9/2026).
    rej = rejilla_de(nuevas[0], buscar_bpm=True)
    if rej is None:
        return [f["ID"] for f in nuevas], "filas creadas, pero no pude medir el audio"
    if rej_fuente and not str(rej.get("origen", "")).startswith("Virtual DJ"):
        rej.update(bpm=rej_fuente["bpm"], per=rej_fuente["per"],
                   fase=rej_fuente["fase"], confianza=100.0,
                   origen="Virtual DJ (analizado como %s)" % rej_fuente["vdj_nombre"])
        rej["compas"] = 4 * rej["per"]
    ini, _m = inicio_recomendado(rej)

    base = rej["bpm"]
    bpms = [base] * len(nuevas)
    extra = ""
    if auto:
        # el x2 para la MAS DIFICIL solo donde Softnyx lo hace en la mayoria de
        # los casos, o sea por debajo de 100 BPM (100% hasta 90, 74% de 90 a 100)
        # CORREGIDO el 22/9/2026: con los niveles, "la ultima fila" puede ser
        # la UNICA, y tildando solo "Inicial" en una cancion de 92 BPM esa
        # inicial salia al DOBLE de velocidad. El x2 de Softnyx es para la
        # version dificil, asi que va solo si hay al menos dos filas y la
        # ultima es la profesional (sin niveles, la segunda de siempre).
        hay_dificil = len(nuevas) >= 2 and (not pedidos
                                            or pedidos[-1][0] == "profesional")
        if chance_x2(base) >= 50 and hay_dificil:
            bpms[-1] = base * 2
            extra = (" Le puse el x2 a la mas dificil: a %.0f BPM Softnyx lo hace "
                     "en el %d%% de las canciones." % (base, chance_x2(base)))
        if pedidos:
            # una fila por NIVEL, con las estrellas que usa Softnyx en ese nivel
            # a ESE BPM (la del x2 se calcula a su propio BPM)
            ests = []
            for (niv, _e), bpm in zip(pedidos, bpms):
                v = estrellas_de_nivel(bpm, niv)
                if v is None:
                    v = max(1, min(10, estrellas_tipicas(bpm)))
                    extra += (" OJO: a %.0f BPM Softnyx NO hace version %s (ni una "
                              "en 1171 charts). Le puse %d igual, pero esa fila va "
                              "a quedar rara." % (bpm, niv, v))
                ests.append(v)
            extra = (" Las estrellas las elegi yo, que es lo que usa Softnyx en "
                     "cada nivel a ese BPM." + extra)
        else:
            ests = estrellas_sugeridas(bpms)
            extra = (" Las estrellas las elegi yo, que es lo que usa Softnyx a ese "
                     "BPM." + extra)

    for f, est, bpm in zip(nuevas, ests, bpms):
        f["Difficulty"] = str(est)
        f["CutOff"] = str(cutoff_de(est))
        # las canciones NUEVAS salen con los SPACE como LoveRitmo 2020 (6.3.48)
        nv, inf_g = generar(f, rej, est, ini, bpm=bpm, por_musica=por_musica,
                            frases=frases, space_estilo="2020", por_partes=True)
        f.update(nv)
        if inf_g.get("calladas"):
            extra += (" Calle las flechas en %d misiones donde la cancion baja."
                      % inf_g["calladas"])
    if ext not in (".ogg", ".oga"):
        extra += " Converti el %s a .ogg yo mismo." % ext.lstrip(".")
        if not str(rej.get("origen", "")).startswith("Virtual DJ"):
            extra += (" Virtual DJ todavia no conoce ese audio, asi que la "
                      "cuadricula es la mia, que es la peor de las dos: si el "
                      "arranque no te convence, pasale Virtual DJ a %s.ogg y "
                      "genera de nuevo." % nombre)
    return ([f["ID"] for f in nuevas],
            "%s listo en las filas %s (%s), %s BPM, arranque "
            "%.4f s.%s\n\n%s\n\n"
            "Todavia NO esta en el juego: para eso el boton ENVIAR AL JUEGO."
            % (nombre, " y ".join(f["ID"] for f in nuevas),
               ", ".join("%s estrellas (%s)"
                         % (f["Difficulty"],
                            nivel_de(int(float(f["Difficulty"] or 0))))
                         for f in nuevas),
               # con los niveles puede haber UNA sola fila: antes esto
               # comparaba bpms[0] con bpms[1] y reventaba al final, con el
               # audio ya convertido (encontrado en la auditoria del 22/9/2026)
               ("%g" % round(base, 2)) if len(set(bpms)) == 1 else
               " y ".join("%g" % round(b, 2) for b in bpms),
               ini, extra,
               ("Reemplazo a: %s." % " y ".join(pisadas)) if pisadas else
               "Son filas NUEVAS: no se piso ninguna cancion."))


# ================================================================ escuchar
# Oir la cancion con un tic en cada flecha, ANTES de abrir el juego.
#
# POR QUE: de todo lo que hace falta acertar, lo unico que no se resuelve
# midiendo es CUAL DE LOS CUATRO COMPASES (documento 1). Las cuatro opciones
# caen igual de bien en la cuadricula y solo se distinguen escuchando. Hasta
# ahora eso costaba abrir el juego una vez por opcion.
#
# No hace falta instalar nada: el audio lo abre ffmpeg (el mismo que ya usa el
# analizador) y lo reproduce winsound, que viene con Windows.
SR_ESCUCHA = 44100
_PCM_CACHE = {}


def pcm_entero(ogg, sr=SR_ESCUCHA):
    """La cancion entera en memoria. Guarda la ultima: escuchar de nuevo es
    instantaneo. No se usa `ffmpeg -ss` porque en Vorbis el corte por tiempo no
    siempre cae en la muestra exacta, y aca el desfase es justo lo que se mide."""
    k = (str(ogg), sr)
    if k not in _PCM_CACHE:
        import numpy as np
        r = subprocess.run([FFMPEG, "-v", "error", "-i", str(ogg), "-ac", "1",
                            "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
        if r.returncode:
            raise RuntimeError(r.stderr.decode("utf8", "replace")[:300])
        _PCM_CACHE.clear()
        _PCM_CACHE[k] = np.frombuffer(r.stdout, dtype="<f4")
    return _PCM_CACHE[k]


def tandas_de(m1, m2, i):
    """Los casilleros de la mision i: [(tiempo 0..7, cuantas flechas), ...].

    Los 4 primeros salen del MissionID1. Si el MissionID2 no es "0", vienen 4
    mas (tiempos 4 a 7): es la SEGUNDA TANDA, la barra que se rellena (ver
    TANDA2_*). En cada casillero sin flechas el juego pone un SPACE (6.3.1.1).
    """
    a = patron(m1[i]) if i < len(m1) else [0, 0, 0, 0]
    out = [(k, a[k]) for k in range(4)]
    if i < len(m2) and str(m2[i]).strip() not in ("0", ""):
        b = patron(m2[i])
        out += [(4 + k, b[k]) for k in range(4)]
    return out


def golpes(listas, inicio, bpm):
    """Cuando cae cada flecha y cada SPACE, en segundos.

    Cada mision se tipea en sus primeros 4 tiempos (MissionID1) y, si tiene
    SEGUNDA TANDA (MissionID2 distinto de 0), en los 4 siguientes. El resto de
    la mision el personaje baila. Ver `tandas_de`.

    EL SPACE lo pone el juego en cada casillero QUE NO TIENE FLECHAS
    (comprobado el 20/9/2026). Aquella prueba concluyo ademas que "el MissionID2
    no cambia nada": eso estaba MAL (2/10/2026). Se miraron solo los primeros 4
    casilleros; la segunda tanda viene despues.

    Devuelve [dict(t, flechas, space, tiempo, mision, tanda), ...] ordenado por t.
    """
    inicio = float(listas.get("StartDelayTime", inicio))
    per = 60.0 / float(bpm)
    largos = [int(float(v)) for v in str(listas.get("Length") or "").split(",")
              if v.strip()]
    m1 = [v for v in str(listas.get("MissionID1") or "").split(",") if v.strip()]
    m2 = [v for v in str(listas.get("MissionID2") or "").split(",") if v.strip()]
    out, t0 = [], float(inicio)
    for i, largo in enumerate(largos):
        for k, cuantas in tandas_de(m1, m2, i):
            # el SPACE lo pone el juego donde NO hay flechas
            sp = 1 if cuantas == 0 else 0
            out.append(dict(t=t0 + k * per, flechas=cuantas, space=sp,
                            tiempo=k, mision=i, tanda=1 + k // 4))
        t0 += largo * per
    return out


def _tic(sr, hz, ms, caida=6.0):
    import numpy as np
    n = max(1, int(sr * ms / 1000.0))
    t = np.arange(n, dtype="float32") / sr
    env = np.exp(-caida * t / (ms / 1000.0)).astype("float32")
    # un pelin de ataque para que no chasquee
    ata = min(n, int(sr * 0.002))
    if ata > 1:
        env[:ata] *= np.linspace(0.0, 1.0, ata, dtype="float32")
    return (np.sin(2 * np.pi * hz * t).astype("float32") * env)


_TICS = {}
_SONIDOS_JUEGO = {}


def sonido_del_juego(nombre, sr=44100):
    """Un .wav sacado del juego, en mono y al ritmo de muestreo que se use.

    Los del juego vienen a 44100 y en estereo; se pasan a mono promediando y,
    si hiciera falta, se remuestrea a lo bruto (vale: son golpes cortos).
    """
    k = (nombre, sr)
    if k in _SONIDOS_JUEGO:
        return _SONIDOS_JUEGO[k]
    import numpy as np
    import wave
    ruta = SACADO / nombre
    if not ruta.exists():
        return None
    with wave.open(str(ruta), "rb") as w:
        n, canales, ancho, sr0 = (w.getnframes(), w.getnchannels(),
                                  w.getsampwidth(), w.getframerate())
        crudo = w.readframes(n)
    if ancho != 2:
        return None
    x = np.frombuffer(crudo, dtype="<i2").astype("float32") / 32768.0
    if canales > 1:
        x = x.reshape(-1, canales).mean(axis=1)
    if sr0 != sr:
        idx = (np.arange(int(len(x) * sr / float(sr0))) * sr0 / float(sr))
        x = x[np.clip(idx.astype(int), 0, len(x) - 1)]
    x = x / (np.abs(x).max() or 1.0)
    _SONIDOS_JUEGO[k] = x.astype("float32")
    return _SONIDOS_JUEGO[k]


def _tic_cache(sr, clave, hz, ms, caida=6.0):
    k = (sr, clave)
    if k not in _TICS:
        _TICS[k] = _tic(sr, hz, ms, caida)
    return _TICS[k]


def armar_escucha(ogg, marcas, desde, segundos, salida, musica=True,
                  marcar_misiones=True, inicios_mision=(), vol_musica=0.55,
                  vol_tic=0.85, sr=SR_ESCUCHA, sonidos_juego=False):
    """Escribe un .wav con el tramo pedido de la cancion y los tics encima.

    flecha  -> tic agudo (mas agudo y mas fuerte cuantas mas flechas)
    SPACE   -> tic grave, mas corto
    mision  -> golpe seco al empezar cada mision, para oir la frase de 16 tiempos
    """
    import numpy as np
    import wave

    desde = max(0.0, float(desde))
    n = int(segundos * sr)
    mezcla = np.zeros(n + sr, dtype="float32")   # un colchon para el ultimo tic

    if musica:
        x = pcm_entero(ogg, sr)
        a = int(desde * sr)
        tramo = x[a:a + n]
        mezcla[:len(tramo)] += tramo * vol_musica

    def poner(t, onda, vol):
        i = int((t - desde) * sr)
        if i < 0 or i >= n:
            return
        j = min(len(mezcla), i + len(onda))
        mezcla[i:j] += onda[:j - i] * vol

    if marcar_misiones:
        golpe = _tic_cache(sr, "mision", 150.0, 90, caida=5.0)
        for t in inicios_mision:
            poner(t, golpe, 0.45 * vol_tic)

    # los sonidos DEL JUEGO si se pidieron y estan extraidos; si no, los tics
    # sinteticos de siempre
    son_fl = sonido_del_juego("tecla.wav", sr) if sonidos_juego else None
    son_sp = sonido_del_juego("space.wav", sr) if sonidos_juego else None
    for g in marcas:
        k = min(3, max(1, g["flechas"]))
        if g["flechas"]:
            if son_fl is not None:
                poner(g["t"], son_fl, (0.45 + 0.15 * k) * vol_tic)
            else:
                hz = {1: 1568.0, 2: 1976.0, 3: 2349.0}[k]
                poner(g["t"], _tic_cache(sr, ("fl", k), hz, 55),
                      (0.5 + 0.18 * k) * vol_tic)
        if g["space"]:
            if son_sp is not None:
                poner(g["t"], son_sp, (0.35 + 0.08 * min(3, g["space"])) * vol_tic)
            else:
                poner(g["t"], _tic_cache(sr, "sp", 523.0, 70, caida=5.0),
                      (0.30 + 0.08 * min(3, g["space"])) * vol_tic)

    mezcla = np.clip(mezcla[:n], -1.0, 1.0)
    datos = (mezcla * 32000.0).astype("<i2")
    salida = Path(salida)
    with wave.open(str(salida), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(datos.tobytes())
    return salida


def previo(fila, rej, estrellas, inicio, segundos=20.0, bpm=None, antes=1.5,
           musica=True, marcar_misiones=True, salida=None, por_musica=False,
           desde=None, mudos=(), space="softnyx", sonidos_juego=False,
           mudo_sin_space=True, frases=None, descanso=False, solo_space=(),
           invertir=(), ritmos=(), space_estilo="clasico", suave=(),
           por_partes=False, secciones=()):
    """El .wav de como va a sonar ESTE arranque con ESTAS estrellas.

    No toca la fila: genera el chart aparte, con la misma semilla que usaria
    GENERAR, asi lo que se escucha es exactamente lo que va a quedar.
    """
    ogg = rej.get("ogg")
    if not ogg or not Path(ogg).exists():
        raise RuntimeError("No tengo el .ogg de esta cancion. Probá 'Recuperar audios'.")
    bpm = float(bpm or rej["bpm"])
    nuevos, inf = generar(fila, rej, estrellas, inicio, bpm=bpm,
                          por_musica=por_musica, mudos=mudos, space=space,
                          mudo_sin_space=mudo_sin_space, frases=frases,
                          descanso=descanso, solo_space=solo_space,
                          invertir=invertir, ritmos=ritmos,
                          space_estilo=space_estilo, suave=suave,
                          por_partes=por_partes, secciones=secciones)
    inicio = float(nuevos["StartDelayTime"])
    marcas = golpes(nuevos, inicio, bpm)
    per = 60.0 / bpm
    largos = [int(float(v)) for v in nuevos["Length"].split(",") if v.strip()]
    arranques, t0 = [], float(inicio)
    for largo in largos:
        arranques.append(t0)
        t0 += largo * per
    desde = max(0.0, float(inicio) - antes if desde is None else float(desde))
    salida = Path(salida or (CACHE / "_escuchar.wav"))
    armar_escucha(ogg, marcas, desde, segundos, salida, musica=musica,
                  marcar_misiones=marcar_misiones, inicios_mision=arranques,
                  sonidos_juego=sonidos_juego)
    dentro = [g for g in marcas if desde <= g["t"] < desde + segundos]
    return salida, dict(desde=desde, segundos=segundos, marcas=len(dentro),
                        misiones=inf["misiones"], bpm=bpm, arranques=arranques,
                        ventana=4 * per, calladas=inf.get("calladas"),
                        flechas=sum(g["flechas"] for g in dentro),
                        space=sum(g["space"] for g in dentro))



def probar_los_cuatro(fila, rej, estrellas, inicios, segundos=12.0, bpm=None,
                      por_musica=False, mudos=(), space="softnyx",
                      salida=None, sonidos_juego=True, frases=None,
                      descanso=False, solo_space=(), invertir=(), ritmos=(),
                      space_estilo="clasico", suave=(), por_partes=False,
                      secciones=()):
    """Un .wav con los CUATRO compases posibles, uno detras del otro.

    Cada tramo viene anunciado por su numero de pitidos -- uno, dos, tres o
    cuatro -- asi no hay que acordarse de cual esta sonando.

    POR QUE EXISTE: de las diez formas de elegir el compas MIDIENDO que se
    probaron el 22/9/2026 contra los 117 charts oficiales, ninguna le gano a la
    que ya estaba (66%), y la mejor mezcla resulto ser sobreajuste: elegida en
    media lista y puntuada en la otra media da 56%. El compas no se resuelve
    midiendo. Se resuelve escuchando, y esto hace que escuchar cueste una sola
    vez en vez de cuatro.
    """
    import numpy as np
    import wave

    sr = SR_ESCUCHA
    partes = []
    for k, ini in enumerate(inicios):
        tmp = CACHE / ("_compas%d.wav" % (k + 1))
        previo(fila, rej, estrellas, float(ini), segundos=segundos, bpm=bpm,
               por_musica=por_musica, mudos=mudos, space=space, salida=tmp,
               marcar_misiones=True, sonidos_juego=sonidos_juego, frases=frases,
               descanso=descanso, solo_space=solo_space, invertir=invertir,
               ritmos=ritmos, space_estilo=space_estilo, suave=suave,
               por_partes=por_partes, secciones=secciones, antes=0.4)
        with wave.open(str(tmp), "rb") as w:
            datos = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        # el anuncio: k+1 pitidos cortos, y despues un silencio para que se
        # entienda que empieza el tramo
        aviso = []
        t = np.arange(int(0.09 * sr)) / float(sr)
        pip = (np.sin(2 * np.pi * 1320 * t) * 9000).astype("<i2")
        for _ in range(k + 1):
            aviso.append(pip)
            aviso.append(np.zeros(int(0.07 * sr), dtype="<i2"))
        aviso.append(np.zeros(int(0.35 * sr), dtype="<i2"))
        partes.append(np.concatenate(aviso))
        partes.append(datos)
        partes.append(np.zeros(int(0.6 * sr), dtype="<i2"))

    todo = np.concatenate(partes)
    salida = Path(salida or (CACHE / "_cuatro.wav"))
    with wave.open(str(salida), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(todo.tobytes())
    return salida, dict(tramos=len(inicios), segundos=segundos,
                        total=len(todo) / float(sr))

def reproducir(ruta):
    """Suena de fondo: la ventana no se queda colgada."""
    import winsound
    winsound.PlaySound(str(ruta), winsound.SND_FILENAME | winsound.SND_ASYNC)


def parar_sonido():
    import winsound
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


def previo_de_fila(fila, rej, segundos=20.0, antes=1.5, musica=True,
                   marcar_misiones=True, salida=None, desde=None, sonidos_juego=False):
    """Igual que `previo`, pero con las flechas QUE YA TIENE la fila.

    Es la unica forma de oir un chart de Softnyx tal cual lo hizo Softnyx, que
    es contra lo que conviene comparar los propios.
    """
    ogg = rej.get("ogg")
    if not ogg or not Path(ogg).exists():
        raise RuntimeError("No tengo el .ogg de esta cancion. Probá 'Recuperar audios'.")
    bpm = float(fila["BPM"] or rej["bpm"])
    inicio = float(fila["StartDelayTime"] or 0)
    per = 60.0 / bpm
    marcas = golpes(fila, inicio, bpm)
    largos = [int(float(v)) for v in str(fila["Length"]).split(",") if v.strip()]
    arranques, t0 = [], inicio
    for largo in largos:
        arranques.append(t0)
        t0 += largo * per
    desde = max(0.0, inicio - antes if desde is None else float(desde))
    salida = Path(salida or (CACHE / "_escuchar.wav"))
    armar_escucha(ogg, marcas, desde, segundos, salida, musica=musica,
                  marcar_misiones=marcar_misiones, inicios_mision=arranques,
                  sonidos_juego=sonidos_juego)
    dentro = [g for g in marcas if desde <= g["t"] < desde + segundos]
    return salida, dict(desde=desde, segundos=segundos, marcas=len(dentro),
                        misiones=len(largos), bpm=bpm, arranques=arranques,
                        ventana=4 * per,
                        flechas=sum(g["flechas"] for g in dentro),
                        space=sum(g["space"] for g in dentro))


# ============================================ que BPM poner y cuantas estrellas
# TODO ESTO ESTA MEDIDO en los 1038 charts de Softnyx (musictable_2016), sobre
# las 512 canciones que tienen dos versiones. Nada esta inventado.
#
# EL HALLAZGO: la unica velocidad alternativa que usa Softnyx es EXACTAMENTE EL
# DOBLE. De las 512 canciones con dos filas, 418 llevan el mismo BPM en las dos
# (81.6%) y 94 llevan el doble (18.4%). NO existe ni una sola a x1.5, x3 ni x4.
#
# Y cuando lo usa depende del BPM de la cancion: cuanto mas lenta, mas falta le
# hace. Por debajo de 90 BPM lo hace SIEMPRE (9 de 9); por encima de 160, casi
# nunca (1%).
X2_POR_BPM = [(0, 90, 100), (90, 100, 74), (100, 110, 40), (110, 120, 39),
              (120, 130, 19), (130, 140, 12), (140, 160, 5), (160, 400, 1)]

# Las estrellas de cada fila salen del BPM DE ESA FILA, no de si es x2 o no.
# MEDIDO sobre los 512 pares, separando la facil de la dificil y mirando el BPM
# propio de cada una. Es la mediana de cada tramo.
#
# CORREGIDO el 19/9/2026. Antes habia una sola pareja fija para los x2 (3 y 10),
# sacada de la moda global, y eso ponia 10 estrellas a CUALQUIER fila x2. Estaba
# mal: a 164 BPM la mediana de Softnyx es 8, no 10. Las de 7, 8 y 9 existen y son
# justamente lo que usa entre 140 y 200 BPM.
FACIL_POR_BPM = [(0, 90, 1), (90, 100, 2), (100, 140, 3), (140, 200, 4),
                 (200, 400, 5)]
DIFICIL_POR_BPM = [(0, 100, 4), (100, 110, 5), (110, 130, 6), (130, 150, 7),
                   (150, 180, 8), (180, 200, 9), (200, 400, 10)]


def estrellas_tipicas(bpm, dificil=False):
    """La mediana de Softnyx para una fila a ese BPM, como facil o como dificil."""
    t = DIFICIL_POR_BPM if dificil else FACIL_POR_BPM
    v = next((v for a, b, v in t if a <= bpm < b), 10 if dificil else 5)
    lo, hi = rango_estrellas(bpm)
    return max(lo, min(hi, v))


def chance_x2(bpm):
    """% de canciones a este BPM a las que Softnyx les hace la dificil al doble."""
    return next((v for a, b, v in X2_POR_BPM if a <= bpm < b), 1)


def par_tipico(bpm):
    """Las estrellas (facil, dificil) que pone Softnyx a una fila a este BPM."""
    return (estrellas_tipicas(bpm), estrellas_tipicas(bpm, True))


def estrellas_sugeridas(bpms):
    """Que estrellas ponerle a cada fila, en el orden en que vienen.

    `bpms` es el BPM DE CADA FILA (distinto si alguna va a x2).

    La regla, medida en los 512 pares de Softnyx: la mas facil lleva la mediana
    de las faciles A SU BPM, la mas dificil la de las dificiles A SU BPM, y las
    del medio se reparten entre las dos. Cada una se mete despues en el rango
    que Softnyx usa a su propia velocidad.

    Asi una fila a 164 BPM saca 8 estrellas, que es lo que pone Softnyx ahi, en
    vez del 10 fijo que salia antes.
    """
    n = len(bpms)
    if n == 0:
        return []
    if n == 1:
        b = bpms[0]
        return [int(round((estrellas_tipicas(b) + estrellas_tipicas(b, True)) / 2.0))]

    orden = sorted(range(n), key=lambda i: bpms[i])   # la lenta es la facil
    facil = estrellas_tipicas(bpms[orden[0]])
    dificil = estrellas_tipicas(bpms[orden[-1]], True)
    out = [0] * n
    for j, i in enumerate(orden):
        v = facil + (dificil - facil) * j / (n - 1.0)
        lo, hi = rango_estrellas(bpms[i])
        out[i] = max(lo, min(hi, int(round(v))))
    return out


def candidatos_bpm(ogg, cuantos=3):
    """Los BPM que mejor encajan con el audio, con cuanto pesa cada uno.

    ES UN CONTROL, NO LA FUENTE. La cuadricula buena es la de Virtual DJ (ver el
    documento 1: 6 de 10 charts reales caen a menos de 55 ms de un '1' suyo, y
    la medicion propia llego a errar 731 ms). Esto sirve para UNA cosa: pescar
    el caso conocido de que Virtual DJ haya detectado la MITAD del BPM, que es
    lo que le pasa con los temas rapidos.
    """
    ogg = Path(ogg)
    cach = CACHE / ("%s_%d_bpm.json" % (ogg.stem, int(ogg.stat().st_mtime)))
    if cach.exists():
        try:
            return json.loads(cach.read_text(encoding="utf-8"))
        except Exception:
            pass
    import analizar_bpm as ab
    e = ab.envolvente(ab.pcm(str(ogg)))
    _b, sc, lags, _ac = ab.tempo(e)
    bpms = ab.FPS * 60.0 / lags
    picos = [i for i in range(1, len(sc) - 1) if sc[i] >= sc[i - 1] and sc[i] > sc[i + 1]]
    picos.sort(key=lambda i: -sc[i])
    eleg = []
    for i in picos:
        if all(abs(bpms[i] - bpms[j]) / bpms[j] > 0.03 for j in eleg):
            eleg.append(i)
        if len(eleg) >= cuantos:
            break
    tot = sum(max(0.0, float(sc[i])) for i in eleg) or 1.0
    out = [dict(bpm=round(float(bpms[i]), 2),
                peso=round(100.0 * max(0.0, float(sc[i])) / tot, 1)) for i in eleg]
    try:
        cach.write_text(json.dumps(out), encoding="utf-8")
    except Exception:
        pass
    return out


def consejo_bpm(rej, bpm_tabla=None, con_medicion=True):
    """Que BPM conviene poner, y que implica cada opcion.

    Devuelve un dict listo para mostrar. No decide nada: informa.
    """
    base = float(rej["bpm"])
    op = []
    for factor, nombre in ((1.0, "x1 (normal)"), (2.0, "x2 (rapida)"),
                           (3.0, "x3"), (4.0, "x4")):
        b = base * factor
        lo, hi = rango_estrellas(b)
        op.append(dict(factor=factor, nombre=nombre, bpm=b, ventana=4 * 60.0 / b,
                       lo=lo, hi=hi, mision=16 * 60.0 / b, encaje=None, usada=False,
                       tipico=par_tipico(b)))
    d = dict(base=base, origen=rej.get("origen", "?"), opciones=op,
             chance=chance_x2(base), candidatos=[], avisos=[])

    try:
        bpm_tabla = float(bpm_tabla)
    except (TypeError, ValueError):
        bpm_tabla = 0.0
    if bpm_tabla > 0:
        for o in op:
            if math.isclose(round(o["bpm"], 2), bpm_tabla, rel_tol=1e-9, abs_tol=1e-7):
                o["usada"] = True
        r = bpm_tabla / base
        multiplo = min((0.25, 1.0 / 3.0, 0.5, 1.0, 2.0, 3.0, 4.0), key=lambda m: abs(r - m))
        if abs(r - multiplo) / multiplo > 0.03:
            d["avisos"].append(
                "La fila dice %g BPM y la cuadricula mide %.2f. No coincide con la "
                "mitad ni con x1, x2, x3 o x4; revisa el tempo y la sincronizacion."
                % (bpm_tabla, base))
        # CORREGIDO el 22/9/2026. Lo de arriba no alcanza cuando la cuadricula
        # se MIDIO: se mide alrededor del BPM de la fila, asi que si ese BPM
        # esta mal, la cuadricula sale igual de mal y los dos coinciden. Por
        # eso ademas se compara contra lo que da el AUDIO medido solo.
        bpm_a = float(rej.get("bpm_audio") or 0.0)
        if bpm_a > 0:
            ra = bpm_tabla / bpm_a
            mult = min((0.25, 1.0 / 3.0, 0.5, 1.0, 2.0, 3.0, 4.0), key=lambda m: abs(ra - m))
            if abs(ra - mult) / mult > 0.03:
                d["avisos"].append(
                    "El AUDIO, medido sin mirar la fila, da %.2f BPM, y la fila "
                    "dice %g (x%.2f): no coincide con mitad, x1, x2, x3 o x4. "
                    "Si la nitidez es baja, el BPM de la fila esta mal: apreta "
                    "'Medir el BPM del audio'." % (bpm_a, bpm_tabla, ra))

    ogg = rej.get("ogg")
    if con_medicion and ogg and Path(ogg).exists():
        try:
            d["candidatos"] = candidatos_bpm(ogg)
        except Exception as e:
            d["avisos"].append("No pude medir el BPM del audio: %s" % e)
    for o in op:
        cerca = [c for c in d["candidatos"]
                 if abs(c["bpm"] - o["bpm"]) / o["bpm"] < 0.03]
        o["encaje"] = max((c["peso"] for c in cerca), default=0.0)
    if op[0]["encaje"] >= 15 and op[1]["encaje"] >= 15:
        d["avisos"].append(
            "El audio admite las DOS: %.0f BPM (%.0f%%) y %.0f BPM (%.0f%%). Es la "
            "ambiguedad clasica de mitad/doble, y midiendo no se resuelve. Si la "
            "fila ya suena bien, no la muevas."
            % (op[0]["bpm"], op[0]["encaje"], op[1]["bpm"], op[1]["encaje"]))
    if bpm_tabla > 0 and not any(o["usada"] for o in op):
        d["avisos"].append(
            "La fila esta a %g BPM y ninguna de las cuatro opciones es esa." % bpm_tabla)
    if d["candidatos"]:
        mejor = d["candidatos"][0]["bpm"]
        if abs(mejor - base * 2) / (base * 2) < 0.03:
            d["avisos"].append(
                "OJO: midiendo el audio da %.2f, que es el DOBLE de lo que dice la "
                "cuadricula. Es el fallo conocido de Virtual DJ con los temas "
                "rapidos (a 'You wear me out' le puso 89.9 en vez de 179.74). "
                "Conviene mirarlo a mano." % mejor)
        elif abs(mejor - base / 2) / (base / 2) < 0.03:
            d["avisos"].append(
                "Midiendo el audio da %.2f, la mitad de la cuadricula. Suele ser al "
                "reves (que la medicion propia se enganche en el contratiempo), asi "
                "que lo mas probable es que la buena sea la cuadricula." % mejor)
    return d


# ====================================== que las flechas sigan a la musica
# LO QUE SE PUEDE Y LO QUE NO. Una mision son 16 tiempos y las flechas caen
# solo en los 4 primeros, siempre. No se pueden correr ni poner en otro lado:
# lo UNICO que se elige es QUE PATRON va en cada mision, y los patrones salen
# del pozo real de Softnyx. Asi que "seguir la musica" aca significa:
#
#   * en una mision que cae sobre un tramo callado -> el patron VACIO (ID 1),
#     que existe y Softnyx lo usa;
#   * en las demas -> de varios candidatos sorteados del pozo, quedarse con el
#     que mejor cae sobre los golpes fuertes;
#   * el SPACE, con el que mejor cae sobre las SUBIDAS (el tiempo que pega
#     fuerte viniendo de uno flojo).
#
# El pozo y sus frecuencias NO se tocan: se sortean K candidatos como siempre y
# se elige entre ellos. Por eso el reparto global sigue pareciendose al de
# Softnyx.
#
# OJO, ESTO NO ES LO DE ANTES. El viejo `--por-musica` de editar_cancion.py
# cambiaba el LARGO de las misiones (32 tiempos para tapar un bajon), y eso
# dejaba 15 segundos sin flechas y no gusto. Aca todas las misiones siguen
# midiendo 16.
def energia_por_beat(ogg, inicio, bpm, cuantos, sr=22050):
    """Graves (40-160 Hz) de cada tiempo, en 0..100 sobre esta misma cancion."""
    import numpy as np
    import analizar_bpm as ab
    x = ab.pcm(str(ogg))
    N, H = ab.NFFT, ab.HOP
    w = np.hanning(N).astype(np.float32)
    nf = max(0, (len(x) - N) // H)
    if nf <= 0:
        return [0.0] * cuantos
    f = np.fft.rfftfreq(N, 1.0 / ab.SR)
    banda = (f >= 40) & (f < 160)
    env = np.empty(nf, dtype=np.float32)
    paso = 2048
    for a in range(0, nf, paso):
        b = min(nf, a + paso)
        idx = np.arange(N)[None, :] + H * np.arange(a, b)[:, None]
        S = np.abs(np.fft.rfft(x[idx] * w, axis=1))
        env[a:b] = S[:, banda].mean(axis=1)
    fps = ab.SR / H
    per = 60.0 / float(bpm)
    out = []
    for i in range(cuantos):
        a = int((inicio + i * per) * fps)
        b = int((inicio + (i + 1) * per) * fps)
        out.append(float(env[a:b].mean()) if 0 <= a < nf and b > a else 0.0)
    tope = float(np.percentile(env, 99)) or 1.0
    return [min(100.0, 100.0 * v / tope) for v in out]


def _acomodar(mid, perfil):
    """Reordena los 4 valores del patron para que caigan sobre los tiempos fuertes.

    NO cambia cuantas flechas hay ni cuantas caen juntas: solo EN QUE TIEMPO de
    la ventana cae cada grupo. O sea que el reparto medido de Softnyx (% de
    tiempos con 0, 1, 2 y 3) queda EXACTAMENTE igual.

    DOS INTENTOS ANTERIORES QUE FALLARON, por si alguien los quiere repetir:

      1. Puntuar `cantidad x energia` y quedarse con el mejor de 24 sorteados.
         Gana siempre el patron con mas flechas. En Play it sweet la densidad
         se iba de 4.5 a 5.9 por mision y los tiempos de 2 flechas del 29% al
         58%.
      2. Lo mismo pero dividiendo por la cantidad. Gana siempre el patron mas
         flojo, porque concentrar 1 flecha en el tiempo mas fuerte da el mejor
         promedio: los tiempos vacios se iban del 17% al 49%.

    La cantidad la tiene que seguir decidiendo el sorteo del pozo. Lo unico que
    mira la musica es el ORDEN.
    """
    c = patron(mid)
    if len(set(c)) == 1:          # 0,0,0,0 o 2,2,2,2: reordenar no cambia nada
        return mid
    orden = sorted(range(4), key=lambda k: (-perfil[k], k))
    vals = sorted(c, reverse=True)
    nuevo = [0, 0, 0, 0]
    for k, v in zip(orden, vals):
        nuevo[k] = v
    return str(1 + nuevo[0] * 125 + nuevo[1] * 25 + nuevo[2] * 5 + nuevo[3])


# Cuanto SPACE dejar. MEDIDO en Rihanna - Don't Stop The Music (3 estrellas):
#     como Softnyx          3.7 SPACE por mision
#     solo en las subidas   2.3
#     solo en los fuertes   1.6
# "Como Softnyx" es lo que hace el juego de verdad (en inicial, 3.2 por mision),
# pero es MUCHO si lo que se quiere es que el SPACE marque un momento concreto.
# Las otras dos se apartan del reparto medido A PROPOSITO: se pidieron asi.
SPACE_UMBRAL = {"softnyx": None, "subidas": 0.0, "justos": 0.6}


def _space_justo(mid, subida, umbral):
    """Deja el SPACE solo en los tiempos que SUBEN, y borra el resto.

    `umbral` es respecto del tiempo que mas sube de esa ventana: con 0.0 quedan
    todos los que suben algo, con 0.6 solo los que suben casi tanto como el pico.
    """
    c = patron(mid)
    mx = max(subida)
    if mx <= 0:
        return "1"
    nuevo = [c[k] if (subida[k] > 0 and subida[k] >= umbral * mx) else 0
             for k in range(4)]
    return str(1 + nuevo[0] * 125 + nuevo[1] * 25 + nuevo[2] * 5 + nuevo[3])


def plan_musical(ogg, inicio, bpm, n, umbral=0.30, arranques=None):
    """Que hacer en cada mision, mirando el audio.

    `arranques` es donde empieza cada mision, en tiempos desde el inicio. Sin
    eso se supone que todas miden 16.

    Devuelve una lista de n diccionarios con:
        callada  -> True si ese tramo esta en silencio (no van flechas)
        fuerza   -> los 4 tiempos de la ventana, 0..100
        subida   -> cuanto sube cada tiempo respecto de lo que venia
    """
    arranques = list(arranques) if arranques else [m * 16 for m in range(n)]
    e = energia_por_beat(ogg, inicio, bpm, arranques[-1] + 16 + 4)
    if not any(e):
        return None
    medio = sorted(v for v in e if v > 0)
    medio = medio[len(medio) // 2] if medio else 1.0
    plan = []
    for m in range(n):
        base = arranques[m]
        fuerza = e[base:base + 4]
        antes = e[max(0, base - 2):base] or [0.0]
        prev = sum(antes) / len(antes)
        subida = []
        for k, v in enumerate(fuerza):
            ref = prev if k == 0 else fuerza[k - 1]
            subida.append(v - ref)
        # callada = toda la ventana muy por debajo de lo normal de la cancion
        callada = (sum(fuerza) / 4.0) < umbral * medio
        plan.append(dict(callada=callada, fuerza=fuerza, subida=subida))
    return plan

# ============================================ lo que se saca del propio juego
# Las flechas, el SPACE y los sonidos de tecla salen del juego instalado, para
# que la simulacion se vea y suene como el juego de verdad y no como un dibujo.
#
# Los .spak del juego son QPACK SIN CIFRAR: adentro hay un .png o un .wav tal
# cual. (El musictable si esta cifrado con Blowfish, pero eso es aparte.)
JUEGO_MEDIA = JUEGO / "MediaPath"
SACADO = ESTUDIO / "juego"          # donde queda lo extraido
DIRECCIONES = ("left", "down", "up", "right",
               "leftdown", "leftup", "rightdown", "rightup")


def _sacar_spak(origen, destino):
    """Desempaca un .spak del juego. Devuelve el archivo que quedo."""
    import musictable_tool as mt
    nombre, contenido, _cab = mt.spak_desempacar(Path(origen).read_bytes())
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return destino


def extraer_del_juego(forzar=False):
    """Deja en la carpeta juego las flechas, el SPACE, la barra y los sonidos.

    Se hace UNA vez; despues ya estan. Devuelve (cuantos, que falto).
    """
    SACADO.mkdir(parents=True, exist_ok=True)
    piezas = []
    nk = JUEGO_MEDIA / "Game2D" / "NewKeyNote"
    for d in DIRECCIONES:
        piezas.append((nk / "nomal" / ("note2_key_%s.png.spak" % d),
                       SACADO / ("flecha_%s.png" % d)))
    piezas += [
        (nk / "note2_key_space.png.spak", SACADO / "space_punto.png"),
        # la placa azul que dice SPACE. En NewKeyNote solo esta el puntito de
        # 28x28; la placa vive en la carpeta Frozen, y es la misma que se ve en
        # la barra durante la partida.
        (JUEGO_MEDIA / "Game2D" / "Frozen" / "fever_key_space.png.spak",
         SACADO / "space.png"),
        (nk / "note2_base.png.spak", SACADO / "barra.png"),
        (nk / "note2_judge_good.png.spak", SACADO / "bien.png"),
    ]
    ks = JUEGO_MEDIA / "Sound" / "KeySound" / "Dance"
    piezas += [
        (ks / "ks_clap.wav.spak", SACADO / "tecla.wav"),
        (ks / "ks_note2_space.wav.spak", SACADO / "space.wav"),
        (ks / "ks_kick.wav.spak", SACADO / "bombo.wav"),
    ]
    hechos, faltan = 0, []
    for origen, destino in piezas:
        if destino.exists() and not forzar:
            hechos += 1
            continue
        if not origen.exists():
            faltan.append(origen.name)
            continue
        try:
            _sacar_spak(origen, destino)
            hechos += 1
        except Exception as e:
            faltan.append("%s (%s)" % (origen.name, e))
    return hechos, faltan


_KEYPAT = None


def keypatterns():
    """Las direcciones REALES que usa el juego, del keypatterntable_4key.

    La tabla trae, por cada bolsa (`ID`) y cada cantidad de teclas (`Key`), las
    direcciones concretas: `1st Key`..`4th Key`, con 1..4 = izquierda, abajo,
    arriba, derecha.

    Devuelve {bolsa: {cuantas: [(dir, dir, ...), ...]}}.
    """
    global _KEYPAT
    if _KEYPAT is not None:
        return _KEYPAT
    cach = CACHE / "_keypatterns.json"
    if cach.exists():
        try:
            d = json.loads(cach.read_text(encoding="utf-8"))
            _KEYPAT = {int(k): {int(n): [tuple(x) for x in v]
                                for n, v in sub.items()} for k, sub in d.items()}
            return _KEYPAT
        except Exception:
            pass
    import musictable_tool as mt
    src = JUEGO_MEDIA / "PARAM" / "KeyPattern" / "keypatterntable_4key.slk.spak"
    tmp = CACHE / "_keypat.csv"
    mt.exportar(str(EXE), str(src), str(tmp))
    out = {}
    with open(tmp, encoding="utf-8-sig", newline="") as fh:
        for fila in csv.DictReader(fh, delimiter=";"):
            try:
                bolsa = int(fila["ID"])
                cuantas = int(fila["Key"])
            except (TypeError, ValueError):
                continue
            dirs = []
            for c in ("1st Key", "2nd Key", "3rd Key", "4th Key"):
                v = (fila.get(c) or "").strip()
                if v:
                    dirs.append(int(float(v)))
            if len(dirs) != cuantas:
                continue
            out.setdefault(bolsa, {}).setdefault(cuantas, []).append(tuple(dirs))
    try:
        cach.write_text(json.dumps({str(k): {str(n): [list(x) for x in v]
                                             for n, v in sub.items()}
                                    for k, sub in out.items()}), encoding="utf-8")
    except Exception:
        pass
    _KEYPAT = out
    return out


# 1..4 en la tabla del juego son las cuatro flechas, en este orden.
# CORREGIDO el 2/10/2026: decia 1 izq, 2 aba, 3 arr, 4 der. Con unas bolsas
# hechas a medida para La chica de la vespa amarilla, el juego mostro cada
# "arriba" como derecha, cada "abajo" como arriba y cada "derecha" como abajo
# (dos partidas de Joel, misión por misión): el orden real es el de las agujas
# del reloj. Con las bolsas del juego no se notaba porque son simetricas.
FLECHA_DE_CODIGO = {1: "left", 2: "up", 3: "right", 4: "down"}


def flechas_del_chart(listas, inicio, bpm, semilla=0):
    """Que flechas concretas caen, y cuando. Para la simulacion.

    Devuelve [dict(t, mision, tiempo 1..8, tanda 1|2, flechas=[nombre,...],
    space=n), ...] donde `flechas` son direcciones de verdad, sacadas de la
    tabla del juego segun el KeyPatternID de esa mision (las dos tandas usan la
    misma bolsa). Los tiempos 5 a 8 son la segunda tanda (ver `tandas_de`).
    """
    inicio = float(listas.get("StartDelayTime", inicio))
    per = 60.0 / float(bpm)
    kp = keypatterns()
    largos = [int(float(v)) for v in str(listas.get("Length") or "").split(",")
              if v.strip()]
    m1 = [v for v in str(listas.get("MissionID1") or "").split(",") if v.strip()]
    m2 = [v for v in str(listas.get("MissionID2") or "").split(",") if v.strip()]
    bolsas = [int(float(v)) for v in str(listas.get("KeyPatternID") or "").split(",")
              if v.strip()]
    r = random.Random(semilla)
    out, t0 = [], float(inicio)
    for i, largo in enumerate(largos):
        bolsa = bolsas[i] if i < len(bolsas) else 4
        for k, cuantas in tandas_de(m1, m2, i):
            # un SPACE en cada casillero sin flechas: asi lo hace el juego
            sp = 1 if cuantas == 0 else 0
            dirs = []
            if cuantas:
                opciones = kp.get(bolsa, {}).get(cuantas) or kp.get(4, {}).get(cuantas)
                if opciones:
                    dirs = [FLECHA_DE_CODIGO.get(c, "right")
                            for c in r.choice(opciones)]
                else:
                    dirs = [r.choice(list(FLECHA_DE_CODIGO.values()))
                            for _ in range(cuantas)]
            out.append(dict(t=t0 + k * per, mision=i + 1, tiempo=k + 1,
                            tanda=1 + k // 4, flechas=dirs, space=sp))
        t0 += largo * per
    return out


# ======================================================== la ficha de una fila
# TODO lo que el musictable guarda de una cancion, explicado. La ventana no
# calcula nada: solo pinta esto. Las 23 columnas estan en el documento 5
# ("QUE HACE CADA FLECHA") y lo que se sabe de cada una esta ahi.
COLUMNAS = [
    ("ID", "el numero de fila. NUNCA se cambia al reemplazar una cancion"),
    ("Title", "el titulo que se ve en la lista del juego"),
    ("Singer", "el interprete"),
    ("Difficulty", "las estrellas, de 1 a 10"),
    ("BPM", "cuantos tiempos por minuto. Un tiempo dura 60/BPM"),
    ("Filename", "el bkgNNNN del audio. Las dos filas del par comparten el mismo"),
    ("SoundSourceSN", "con esto el cliente pide la cancion. Va igual al ID"),
    ("Genre", "siempre Dance"),
    ("Popularity", "cosmetico"),
    ("Newsong", "el cartelito de 'nueva'"),
    ("Second", "cuanto dura la cancion, en segundos redondeados"),
    ("StartDelayTime", "en que segundo arranca la mision 1. ES LO UNICO QUE HAY "
                       "QUE ACERTAR"),
    ("Length", "cuantos tiempos dura cada mision. Casi siempre 16"),
    ("KeyPatternID", "de que bolsa de direcciones saca las flechas"),
    ("KeySoundID", "NO SE USA en este juego. Esta en 0 en las cinco tablas "
                   "que hay (134.404 valores), y poniendole 1, 2, 3, 10 y 100 no "
                   "cambio nada: ni sonido, ni pantalla, ni puntaje (probado "
                   "jugando el 22/9/2026). Nosotros ponemos 0"),
    ("MissionID1", "cuantas FLECHAS en cada uno de los 4 casilleros de la mision"),
    ("MissionID2", "la SEGUNDA TANDA: otros 4 casilleros que llegan apenas se "
                   "tipea la primera (la barra se rellena). 0 = no hay; 1 = 4 "
                   "SPACE. Softnyx la pone en 3 de cada 4 misiones (visto jugando "
                   "y en los logs del servidor el 2/10/2026)"),
    ("MissionDanceID", "el baile mientras se tipea"),
    ("MissionSuccessDanceID", "el baile si sale bien"),
    ("MissionFailDanceID", "el baile si sale mal"),
    ("MissionCameraID", "la camara de la mision"),
    ("DanceCameraID", "la camara del baile"),
    ("CutOff", "30000 (1-3*), 50000 (4-6*), 70000 (7-10*). NO SE USA en este "
               "juego: con 1 y con 9.999.999 la misma cancion dio el mismo "
               "puntaje mision por mision y no desaprobo ninguna (probado jugando "
               "el 22/9/2026, con el resumen ya funcionando). En KR, Steam y 2020 "
               "es un numero por chart; aca se pone el de su nivel"),
]

# que puede sacar cada bolsa de direcciones, leido del keypatterntable_4key
BOLSAS = {
    1: "la aburrida: para un grupo de 3 solo tiene 4 combinaciones, y las cuatro "
       "son repeticiones (<<<, vvv, ^^^, >>>). Es la que se siente como "
       "'repite'. Softnyx la usa el 16% en 1 estrella y el 4.6% en 10",
    2: "4 combinaciones para un grupo de 3",
    3: "24 combinaciones para un grupo de 3",
    4: "la del juego: 38 combinaciones para un grupo de 3. Domina en todas las "
       "dificultades (64.6% en 1 estrella, 78.8% en 10)",
}


def _lista(fila, col):
    return [v.strip() for v in str(fila.get(col) or "").split(",") if v.strip()]


def _enteros(fila, col):
    out = []
    for v in _lista(fila, col):
        try:
            out.append(int(float(v)))
        except ValueError:
            pass
    return out


def _reparto(vals):
    """Cuantos tiempos llevan 0, 1, 2, 3 y 4 cosas, en %."""
    por_t = [q for v in vals for q in patron(v)]
    if not por_t:
        return [0.0] * 5, 0
    return [100.0 * por_t.count(k) / len(por_t) for k in range(5)], len(por_t)


def ficha(fila, rej, tabla=None):
    """TODO lo que se sabe de esta fila, listo para pintar.

    Devuelve [dict(titulo, filas=[(etiqueta, valor, aclaracion), ...]), ...].
    No mide nada nuevo: se apoya en la cuadricula que ya se midio.
    """
    secs = []
    est = 0
    try:
        est = int(float(fila["Difficulty"]))
    except Exception:
        pass
    bpm_t = float(fila["BPM"] or 0)
    ini = float(fila["StartDelayTime"] or 0)
    sec = float(fila["Second"] or 0)
    per_c = (60.0 / bpm_t) if bpm_t else 0.0
    dur = (rej.get("dur") if rej else 0) or sec
    ogg = buscar_ogg(fila["Filename"])

    # ------------------------------------------------ la cancion
    f = []
    f.append(("Titulo", fila["Title"], ""))
    f.append(("Cantante", fila["Singer"], ""))
    f.append(("Archivo", "%s.ogg" % fila["Filename"],
              str(ogg) if ogg else "NO ESTA EN EL DISCO - el juego igual suena "
                                   "con el .snb, pero no se puede medir nada. "
                                   "Boton 'Recuperar audios'"))
    f.append(("Dura", "%.1f s (%d:%02d)" % (dur, int(dur) // 60, int(dur) % 60),
              "la tabla dice %d s en la columna Second" % sec))
    f.append(("Suena el .snb", fila.get("SoundSourceSN") or "?",
              "con este numero el cliente pide la cancion; va igual al ID (%s)%s"
              % (fila["ID"], "" if str(fila.get("SoundSourceSN")) == str(fila["ID"])
                 else "  ** NO COINCIDE CON EL ID: puede sonar otra cancion **")))
    f.append(("Genero", fila.get("Genre") or "", "siempre Dance"))
    f.append(("Popularidad", fila.get("Popularity") or "", "cosmetico"))
    f.append(("Nueva", fila.get("Newsong") or "", "el cartelito de 'nueva'"))
    f.append(("El audio lo convertimos", "no" if es_original(fila) else "si",
              "sale de snb_local.json. Esto dice si se le puede tocar el .ogg, "
              "NO si el chart es nuestro: son dos cosas distintas"))
    ofi = origen_del_chart(fila)
    f.append(("El chart salio de", ofi[0] if ofi else "no figura en ninguna tabla "
              "oficial: es nuestro",
              ("alla se llama '%s'. Se compara el chart entero (MissionID1 + "
               "Length), no el nombre" % ofi[1][:44]) if ofi else
              "se comparo contra las cuatro tablas oficiales (2016, LoveBeat KR, "
              "Steam y LoveRitmo 2020)"))
    secs.append(dict(titulo="LA CANCION", filas=f))

    # ------------------------------------------------ la cuadricula
    f = []
    if rej is None:
        f.append(("Cuadricula", "NO HAY", "falta el .ogg: no se puede medir nada"))
    else:
        f.append(("De donde sale", rej["origen"],
                  "Virtual DJ es la buena; la mia avisa pero no manda (6.3.2)"))
        if not rej["origen"].startswith("Virtual"):
            f.append(("Confianza", "%.0f%%" % rej.get("confianza", 0),
                      "arrastra la carpeta a Virtual DJ y esto deja de hacer falta"))
        f.append(("Pulsacion", "%.2f BPM" % rej["bpm"],
                  "un tiempo de la MUSICA dura %.0f ms" % (rej["per"] * 1000)))
        f.append(("Un compas", "%.3f s" % rej["compas"], "cuatro tiempos"))
        f.append(("Fase", "%.4f s" % rej["fase"],
                  "el primer '1' de compas. Los demas caen en fase + n x compas"))
        eb = rej.get("entra_beat") or 0
        f.append(("Entra la bateria", "%.0f s" % eb,
                  "medido por mi de los graves; NO hay con que compararlo en "
                  "Softnyx, asi que avisa pero no manda"))
        fb = rej.get("fin_beat") or 0
        f.append(("Se apaga el ritmo", "%.0f s" % fb,
                  "idem. En temas que se desvanecen se adelanta hasta 16 s al "
                  "final real"))
    secs.append(dict(titulo="LA CUADRICULA DE LA MUSICA", filas=f))

    # ------------------------------------------------ el chart de esta fila
    f = []
    f.append(("Fila", fila["ID"], "el ID. Nunca se cambia"))
    f.append(("Estrellas", "%d (%s)" % (est, nivel_de(est)),
              "1-3 inicial, 4-6 basico, 7-10 profesional"))
    cut = str(fila.get("CutOff") or "")
    debe = cutoff_de(est)
    flechas_tot = sum(sum(patron(v)) for v in _lista(fila, "MissionID1"))
    if str(cut) == str(debe):
        nota_cut = ("el que el musictable de 2016 usa en %s. Esa version usa "
                    "solo 30000 / 50000 / 70000; LoveBeat KR y Steam le ponen a "
                    "cada chart su propio numero. NO SE SABE que controla"
                    % nivel_de(est))
    else:
        try:
            cv = int(float(cut))
        except ValueError:
            cv = 0
        nota_cut = ("a %d estrellas Softnyx pone %d - ESTA PUESTO OTRO. " % (est, debe))
        if cv > 100000 and flechas_tot:
            nota_cut += ("pero es de los GRANDES, como los pone el juego original "
                         "(1156 valores distintos en 1157 filas de LoveBeat KR). Va "
                         "con cuanto hay que tocar: unos %d por flecha+SPACE, y este "
                         "da %d. Esta fila viene del juego original: no lo toques"
                         % (CUTOFF_POR_COSA, cv / max(flechas_tot, 1)))
        else:
            nota_cut += "NO SE SABE que controla"
    f.append(("CutOff", cut, nota_cut))
    f.append(("BPM de la tabla", "%.2f" % bpm_t,
              "un tiempo del CHART dura %.0f ms. Ahi caen las flechas"
              % (per_c * 1000)))
    if rej and rej["bpm"]:
        p_m, q_m, err_m = racional_simple(bpm_t / rej["bpm"])
        mult = ("x%d" % p_m) if q_m == 1 else ("x%d/%d" % (p_m, q_m))
        f.append(("Respecto de la musica", mult,
                  "Softnyx usa x2 (18.4% de los pares) y x4, y nunca x3 (8.7)"))
    ventana = 4 * per_c
    if ventana < VENTANA_MAL:
        que = ("** MAS RAPIDA QUE LOS 3912 CHARTS OFICIALES, que no bajan de "
               "%.3f s. Y a 0.600 s esta medido JUGANDO que no se puede: Gee a "
               "400 BPM saco 0 puntos en 75 de 75 misiones **" % VENTANA_MAL)
    elif ventana < VENTANA_OK:
        que = ("el 1%% mas rapido de lo oficial. El chart mas rapido que existe "
               "llega a %.3f s (LoveRitmo 2020, 363 BPM), asi que se puede; pero "
               "se decide jugando" % VENTANA_MAL)
    else:
        que = ("comoda: el 99%% de los 3912 charts oficiales esta de %.3f s para "
               "arriba, y la mediana es 1.509 s" % VENTANA_OK)
    f.append(("Ventana para tipear", "%.3f s" % ventana,
              "son los 4 PRIMEROS tiempos de la mision; los otros 12 el "
              "personaje baila. %s" % que))
    f.append(("Arranque", "%.4f s" % ini,
              "el %.1f%% de la cancion (Softnyx: del 3.6%% al 12.1%%, mediana 6.9%%)"
              % (100.0 * ini / (dur or 1))))
    if rej:
        dif = ini - rej["fase"]
        n = dif / per_c if per_c else 0
        f.append(("...sobre la cuadricula", "a %.0f ms del tiempo del chart"
                  % (abs(n - round(n)) * per_c * 1000),
                  "el peor de los charts que funcionan esta a 67 ms (Not Your Baby)"))
    largos = _enteros(fila, "Length")
    tot = sum(largos)
    fin = ini + tot * per_c
    f.append(("Misiones", "%d" % len(largos),
              "de %s tiempos%s" % ("/".join(str(x) for x in sorted(set(largos))),
                                   "" if len(set(largos)) == 1 else
                                   "  (mezcla largos: Softnyx usa 16 y sube a "
                                   "20, 24, 28 o 32, nunca menos de 16)")))
    f.append(("El chart termina en", "%.1f s" % fin,
              "la cancion dura %.1f s: %s %.1f s"
              % (dur, "se pasa" if fin > dur else "quedan", abs(dur - fin))))
    f.append(("Cobertura", "%.0f%%" % (100.0 * (tot * per_c) /
                                       max(dur - ini, 1e-9)),
              "Softnyx: mediana 98%"))
    secs.append(dict(titulo="EL CHART (fila %s)" % fila["ID"], filas=f))

    # ------------------------------------------------ las flechas
    f = []
    m1 = _lista(fila, "MissionID1")
    rep, ntiempos = _reparto(m1)
    flechas = sum(sum(patron(v)) for v in m1)
    f.append(("Flechas en total", "%d" % flechas,
              "%.1f por mision (Softnyx a %d estrellas: %.1f)"
              % (flechas / float(len(m1) or 1), est,
                 FLECHAS_POR_MISION.get(est, 0))))
    ref = REF_FLECHAS.get(est)
    for k in range(4):
        f.append(("Tiempos con %d flecha%s" % (k, "" if k == 1 else "s"),
                  "%.0f%%" % rep[k],
                  ("Softnyx a %d estrellas: %.0f%%" % (est, ref[k])) if ref else ""))
    if rep[4] > 0:
        f.append(("Tiempos con 4 flechas", "%.0f%%" % rep[4],
                  "** SOFTNYX NO LO HACE NUNCA, cero veces en 1038 charts **"))
    f.append(("SPACE que se ve", "%d" % int(round(ntiempos * rep[0] / 100.0)),
              "en la primera tanda: el juego pone UN SPACE en cada casillero SIN "
              "flechas (comprobado jugando el 20/9/2026). Softnyx: 0.73 por mision"))
    bolsas = _enteros(fila, "KeyPatternID")
    cuenta = {}
    for b in bolsas:
        cuenta[b] = cuenta.get(b, 0) + 1
    for b in sorted(cuenta):
        f.append(("Bolsa %d" % b, "%d misiones (%.0f%%)"
                  % (cuenta[b], 100.0 * cuenta[b] / (len(bolsas) or 1)),
                  BOLSAS.get(b, "no esta en la tabla del juego")))
    ks = set(_lista(fila, "KeySoundID"))
    f.append(("KeySoundID", ", ".join(sorted(ks)) or "-",
              "el sonido de cada tecla. NO SE SABE que hace cada valor"))
    m2 = _lista(fila, "MissionID2")
    con2 = [v for v in m2 if v != "0"]
    f.append(("Segunda tanda (MissionID2)",
              "%d de %d misiones" % (len(con2), len(m2)),
              "otros 4 casilleros que llegan apenas se tipea la primera tanda (la "
              "barra se rellena), con %d flechas en total. Softnyx: 3 de cada 4 "
              "misiones, casi nunca la primera" % sum(sum(patron(v)) for v in con2)))
    secs.append(dict(titulo="LAS FLECHAS Y EL SPACE (fila %s)" % fila["ID"],
                     filas=f))

    # ------------------------------------------------ el baile
    f = []
    for col, que in (("MissionDanceID", "el baile mientras se tipea"),
                     ("MissionSuccessDanceID", "el baile si sale bien"),
                     ("MissionFailDanceID", "el baile si sale mal"),
                     ("MissionCameraID", "la camara de la mision"),
                     ("DanceCameraID", "la camara del baile")):
        vals = sorted(set(_lista(fila, col)))
        f.append((col, ", ".join(vals[:8]) + (" ..." if len(vals) > 8 else ""),
                  que))
    f.append(("Las 10 listas", "miden %s"
              % ("/".join(str(len(_lista(fila, c))) for c in LISTAS)),
              "TIENEN QUE MEDIR TODAS LO MISMO (una entrada por mision). Si una "
              "mide distinto, el chart esta roto"))
    secs.append(dict(titulo="EL BAILE Y LAS CAMARAS (fila %s)" % fila["ID"],
                     filas=f))
    return secs


def ficha_de_par(pareja, rej, tabla=None):
    """La ficha de una cancion entera: lo comun una vez, y el chart de cada fila."""
    if not pareja:
        return []
    out = ficha(pareja[0], rej, tabla)[:2]          # la cancion y la cuadricula
    for fila in pareja:
        out += ficha(fila, rej, tabla)[2:]
    out.append(dict(titulo="LO QUE NO SE SABE", filas=[
        ("KeySoundID", "que hace cada valor",
         "hay una tabla keysoundtable.slk.spak y once sonidos en "
         "Sound\\KeySound\\Dance, pero no se probo"),
        ("CutOff", "que controla",
         "se sabe QUE VALOR va segun las estrellas porque asi lo hace Softnyx, "
         "no que hace"),
        ("Las direcciones", "si el codigo 1 es izquierda",
         "se asume 1-2-3-4 = izquierda, abajo, arriba, derecha. No se comprobo "
         "contra el juego. Si estuviera cambiado se ven las mismas flechas en "
         "otro orden: la cantidad y el tiempo siguen bien"),
        ("La regla del proyecto", "nada se da por cerrado hasta probarlo jugando",
         "ya hubo TRES casos de una conclusion sacada de una coincidencia, "
         "escrita como comprobada y respetada durante meses"),
    ]))
    return out


def inventario(tabla):
    """Como esta el musictable hoy: cuanto hay, que falta y donde poner lo nuevo.

    SE PUEDEN AGREGAR FILAS (6.7): la regla que decia lo contrario era falsa y
    se comprobo JUGANDO el 19/9/2026. Venia de un crash cuya causa real era otra.
    """
    filas = tabla.filas
    nombres, mias, orig = set(), set(), set()
    for f in filas:
        nombres.add(f["Filename"])
        (orig if es_original(f) else mias).add(f["Filename"])
    # EL PROXIMO bkg LIBRE. OJO: no alcanza con mirar la tabla. COMPROBADO el
    # 20/9/2026: `bkg2847.snb` y `bkg2847.ogg` existen en el disco y NINGUNA
    # fila del musictable los nombra. Si se eligiera el nombre mirando solo la
    # tabla se pisaria el audio de una cancion que quedo suelta. Se miran las
    # tres cosas: la tabla, los .snb del juego y los .ogg.
    usados = set()

    def _anotar(nom):
        if nom.startswith("bkg") and nom[3:].isdigit():
            usados.add(int(nom[3:]))

    for n in nombres:
        _anotar(n)
    try:
        for p in BKG_SNB.glob("bkg*.snb"):
            _anotar(p.stem)
    except Exception:
        pass
    for d in OGG_DIRS:
        try:
            for p in d.glob("bkg*.ogg"):
                _anotar(p.stem)
        except Exception:
            pass
    prox = 2800
    while prox in usados:
        prox += 1
    libres = tabla.ids_libres(2000, 6)
    puedo, no_puedo = audios_perdidos(tabla)
    faltan_vdj, tienen_vdj = falta_en_vdj(tabla)
    return [
        ("Filas en el musictable", "%d" % len(filas),
         "SE PUEDEN AGREGAR (6.7). La regla que decia que no era falsa y se "
         "comprobo jugando el 19/9/2026"),
        ("Canciones distintas", "%d" % len(nombres),
         "%d tuyas y %d originales del juego" % (len(mias), len(orig))),
        ("Proximo ID libre", ", ".join(str(x) for x in libres),
         "una cancion son DOS filas: la facil y la dificil"),
        ("Proximo nombre de archivo", "bkg%d" % prox,
         "asi se va a llamar el .ogg y el .snb de la proxima. Se mira la tabla "
         "Y el disco: hay .snb sueltos que ninguna fila nombra (bkg2847), y "
         "elegir por la tabla sola los pisaria"),
        ("Audios que faltan en el disco", "%d" % len(puedo),
         ("se pueden rehacer desde el .snb del juego: boton 'Recuperar audios'"
          if puedo else "ninguno") +
         ("  (y %d que NO se pueden: no estan en snb_local.json)" % len(no_puedo)
          if no_puedo else "")),
        ("Con cuadricula de Virtual DJ", "%d de %d"
         % (len(tienen_vdj), len(tienen_vdj) + len(faltan_vdj)),
         "las que faltan se arreglan pasando la carpeta por Virtual DJ UNA vez "
         "y CERRANDOLO: boton 'Virtual DJ...'"),
    ]


# ======================================================== el manual, adentro
def _texto_columnas():
    """Las 23 columnas, una por linea, para el manual."""
    out = ["Una cancion son DOS filas del musictable (la facil y la dificil),",
           "cada una con 23 columnas. De la 13 a la 22 son LISTAS separadas por",
           "comas, una entrada por mision, y las diez TIENEN QUE MEDIR LO MISMO.",
           ""]
    for i, (col, que) in enumerate(COLUMNAS, 1):
        out.append("%2d. %-22s %s" % (i, col, que[:52]))
        resto = que[52:]
        while resto:
            out.append("    %-22s %s" % ("", resto[:52].lstrip()))
            resto = resto[52:]
    return out


def manual():
    """Todo lo que hay que saber para hacer una cancion, sin salir del programa.

    Es el resumen de los cinco documentos de
    `INFORMACION CORRECTO PARA CREAR MUSICA EN EL JUEGO` y de las PARTES 6 a 9
    del informe maestro. Si algo de aca cambia, cambiarlo TAMBIEN alla.
    """
    return [
        ("LA IDEA, EN CINCO LINEAS", [
            "1. EL ARRANQUE sale de la cuadricula:  fase + n x 4 x (60/BPM).",
            "   Se elige el n donde entran los graves, entre el 4% y el 12%.",
            "2. LAS MISIONES se encadenan solas: 16 tiempos cada una desde ahi.",
            "3. LAS FLECHAS se copian de los patrones reales del juego. No se",
            "   inventan.",
            "4. LA CANTIDAD depende de las estrellas Y DEL BPM, porque la ventana",
            "   para tipear dura 4 x 60/BPM y se acorta cuando el tema es rapido.",
            "5. NUNCA mas de 3 flechas en un tiempo, ni 2 en las de 1-3 estrellas.",
        ]),
        ("UNA MISION: 16 TIEMPOS, PERO SOLO SE TIPEAN 4", [
            "   |  1  2  3  4  |  5  6  7 ... 16  |",
            "      SE TIPEA        EL PERSONAJE BAILA",
            "",
            "La ventana para tipear dura 4 x 60/BPM y la mision entera 16 x 60/BPM.",
            "A 127 BPM son 1.89 s de tipeo cada 7.6 s. A 245 (un x2) son 0.98 s",
            "cada 3.9 s, y ahi adentro entran unas 14 cosas: por eso un 10",
            "estrellas rapido se siente brutal.",
            "",
            "EL TOPE (corregido el 20/9/2026): Softnyx no baja de 0.727 s en sus",
            "1038 charts, y su mediana es 1.714 s. El 99% esta de 0.918 s para",
            "arriba. Lo unico medido JUGANDO es el otro extremo: a 0.600 s (Gee a",
            "400 BPM) el chart es injugable, 0 puntos en 75 de 75 misiones.",
            "",
            "Entre 0.727 y 0.918 hay evidencia para los dos lados: In The City y",
            "Not Your Baby andan a 0.800 y Joel las juega, pero APT a 0.805 la",
            "rechazo. Ahi se decide JUGANDO, no con una tabla.",
            "",
            "El numero viejo era 0.94 s (BPM <= 256) y estaba puesto por prudencia,",
            "no medido: dejaba afuera 36 de los 1038 charts del propio juego.",
        ]),
        ("EL DESFASE DE 58 ms (medido el 20/9/2026, SIN PROBAR JUGANDO)", [
            "LOS CHARTS OFICIALES NO ARRANCAN SOBRE EL '1' DE VIRTUAL DJ:",
            "ARRANCAN 58 ms ANTES.",
            "",
            "Medido en los 876 charts del LoveRitmo 2020 que tienen su .ogg:",
            "   862 de 876 (98.4%) arrancan antes, mediana -59 ms",
            "",
            "Y es un RETARDO FIJO, no una costumbre de la cuadricula:",
            "   tiempo de 200-300 ms  ->  -58 ms  (-23.1% del tiempo)",
            "   tiempo de 300-400 ms  ->  -58 ms  (-17.1%)",
            "   tiempo de 400-600 ms  ->  -59 ms  (-13.1%)",
            "   tiempo de 600-1000 ms ->  -58 ms  ( -8.9%)",
            "En ms es el mismo numero en todo el rango; en porcentaje va del 9%",
            "al 23%. Eso solo lo explica un retardo fijo.",
            "",
            "QUE QUIERE DECIR PARA VOS: el boton 'Pegar a la cuadricula' deja el",
            "arranque justo en el '1', o sea 58 ms MAS TARDE que lo que hace el",
            "juego original.",
            "",
            "OJO: ESTO NO SE PROBO JUGANDO. El programa te lo muestra en el punto",
            "'Contra lo oficial' y NO mueve nada solo. Antes de adoptarlo hay que",
            "hacer una cancion de las dos maneras y jugar las dos.",
        ]),
        ("LAS 7 REGLAS", [
            "1. El BPM de la tabla es el del archivo, no el que dice songbpm.",
            "2. El arranque cae SOBRE un tiempo de la cuadricula. Margen: hasta",
            "   70 ms (el peor de los charts que funcionan, Not Your Baby, esta",
            "   a 67).",
            "3. Nunca antes de que entre la bateria, y conviene el '1' del compas.",
            "   Tope absoluto: nunca mas del 12% de la cancion.",
            "4. Nunca terminar despues de la musica. Softnyx igual se pasa en el",
            "   5.2% de sus charts, hasta 9.7 s.",
            "5. La mezcla de bolsas: la 4 domina, la 1 es la de las repeticiones.",
            "6. El acento va en el ARRANQUE DE LA MISION, no en el SPACE.",
            "7. El BPM de tabla va a un multiplo del pulso sentido:",
            "      BPM = largo_de_mision x pulso / k,  con k entero",
            "   Con k multiplo de 4 la mision cierra con el compas. Softnyx usa",
            "   x2 y x4 y NUNCA x3.",
        ]),
        ("LOS NUMEROS DE REFERENCIA", [
            "Medidos en 2966 charts OFICIALES de tres versiones: el musictable de",
            "2016 (1038), LoveBeat KR (1157) y LoveBeat Steam (771). Son 359.524",
            "tiempos.",
            "",
            "arranque sobre la cuadricula ... hasta 70 ms (charts que funcionan)",
            "arranque, % de la cancion ...... p5 3.7%, mediana 6.7%, p95 11.4%",
            "                                 (las tres versiones dan casi lo mismo)",
            "flechas en un tiempo ........... 0:19.6%  1:21.1%  2:40.8%  3:18.5%",
            "                                 4 flechas: CERO VECES en 359.524",
            "                                 tiempos, en las tres versiones",
            "ventana para tipear ............ la mas rapida que existe: 0.690 s",
            "                                 (348 BPM, LoveBeat KR). p1 0.750 s,",
            "                                 mediana 1.548 s",
            "SPACE que se ve ................ 0.73 por mision; la mitad de las",
            "                                 misiones no tiene ninguno",
            "bolsa 4 ........................ 64% a 82% segun dificultad",
            "bolsa 1 (repeticiones) ......... 16% en 1 estrella, 4.6% en 10",
            "largos de mision ............... 16 domina. Steam usa 11, 12 y 14 en",
            "                                 17 de 89.881: practicamente nunca",
            "                                 baja de 16, pero 'nunca' es falso",
            "cobertura ...................... mediana 98%",
            "margen al final ................ de -9.7 s (se pasa) a +12.9 s",
            "el x2 .......................... 94 de 512 pares (18.4%)",
            "CutOff ......................... KR y Steam le ponen a CADA chart su",
            "                                 propio numero (1156 distintos en",
            "                                 1157 filas). El 2016 usa 3 redondos",
        ]),
        ("LAS 23 COLUMNAS DEL MUSICTABLE", _texto_columnas()),
        ("COMO SE LEE UN MissionID", [
            "Un MissionID es UN SOLO NUMERO que guarda cuatro: cuantas cosas caen",
            "en cada uno de los 4 tiempos de la ventana.",
            "",
            "      ID = 1 + t1x125 + t2x25 + t3x5 + t4",
            "",
            "Y al reves, que es como se lee:",
            "      i = ID - 1",
            "      t1 = i // 125      t2 = (i // 25) % 5",
            "      t3 = (i // 5) % 5  t4 = i % 5",
            "",
            "      287 -> [2,1,2,1]      157 -> [1,1,1,1]",
            "      313 -> [2,2,2,2]        2 -> [0,0,0,1]",
            "        1 -> [0,0,0,0]: 4 casilleros, los 4 con SPACE",
        ]),
        ("LAS DOS TANDAS: MissionID1 Y MissionID2", [
            "Cada mision tiene 4 casilleros (MissionID1). Si el MissionID2 no es",
            "0, apenas se tipean llegan OTROS 4 (la barra 'se rellena'): es la",
            "SEGUNDA TANDA, con el mismo codigo.",
            "",
            "      MissionID2 = 0   -> no hay segunda tanda",
            "      MissionID2 = 1   -> segunda tanda de 4 SPACE",
            "      MissionID2 = 287 -> segunda tanda [2,1,2,1]",
            "",
            "Softnyx la pone en 3 de cada 4 misiones (casi nunca en la primera de",
            "la cancion) y la arma con los patrones de la primera tanda la mitad",
            "de las veces. Descubierto el 2/10/2026 copiando La chica de la vespa",
            "amarilla de un video; antes se creia que no hacia nada.",
        ]),
        ("EL SPACE LO PONE EL JUEGO, NO LA TABLA", [
            "Comprobado JUGANDO el 20/9/2026: el juego pone un SPACE en cada",
            "casillero QUE NO TIENE FLECHAS, en las dos tandas.",
            "",
            "Consecuencias:",
            " * para tener menos SPACE hay que tener MAS FLECHAS. No se regula",
            "   por otro lado.",
            " * quitar una mision no la deja vacia: la deja sin flechas, y el",
            "   juego la llena con cuatro SPACE (y sin segunda tanda).",
        ]),
        ("LAS BOLSAS DE DIRECCIONES (KeyPatternID)", [
            "La tabla del musictable dice CUANDO y CUANTAS. No dice CUAL.",
            "La direccion sale de keypatterntable_4key.slk.spak, 154 filas.",
            "",
            "La bolsa NO cambia cuantas flechas hay. Cambia cuantas combinaciones",
            "de direcciones distintas puede sacar:",
            "",
            "   bolsa 1 ->  4 combinaciones para un grupo de 3, y las cuatro son",
            "               repeticiones (<<<, vvv, ^^^, >>>)",
            "   bolsa 2 ->  4",
            "   bolsa 3 -> 24",
            "   bolsa 4 -> 38   <- la que se siente 'del juego'",
            "",
            "Las dos tandas de una mision sacan de la MISMA bolsa. En la tabla,",
            "1 = izquierda, 2 = arriba, 3 = derecha, 4 = abajo (2/10/2026).",
            "",
            "El sorteo es AL AZAR EN CADA PARTIDA: dos veces la misma cancion no",
            "dan las mismas flechas. Para que se note una repeticion hay que",
            "poner la bolsa 1 en TRES misiones seguidas (con dos, en uno de cada",
            "tres golpes no sale).",
        ]),
        ("DE DONDE SALE CADA UMBRAL DEL SEMAFORO", [
            "No todos los puntos de la Revision pesan lo mismo:",
            "",
            " * LAS FLECHAS, EL SPACE, EL FINAL, CUANDO EMPIEZA, LAS ESTRELLAS",
            "   y LA VELOCIDAD se comparan contra los charts OFICIALES: 2966 de",
            "   tres versiones (2016, LoveBeat KR y Steam). La X ahi quiere",
            "   decir: esto el juego no lo hace NUNCA.",
            "",
            " * EL ARRANQUE, EL BPM y EL MULTIPLO no tienen con que compararse en",
            "   Softnyx: su musica esta cifrada con una clave que mandaba su",
            "   servidor y se perdio, asi que de su audio no se puede medir nada.",
            "   Se comparan contra LOS CHARTS QUE FUNCIONAN.",
            "",
            " * LO QUE MIDO YO DEL AUDIO (cuando entra la bateria, la cuadricula",
            "   cuando Virtual DJ no tiene el tema) AVISA, PERO NUNCA MANDA.",
            "",
            "La X del arranque NO quiere decir 'esta corrido unos milisegundos'.",
            "Quiere decir que las flechas caen ENTRE los golpes de la musica. Eso",
            "se arregla saltando al tiempo de al lado, no retocando 30 ms.",
        ]),
        ("LO QUE NO SE SABE", [
            "1. (resuelto el 2/10/2026: el MissionID2 es la segunda tanda)",
            "1b. De donde salieron In The City, Light it up, Not Your Baby y",
            "    Arabian Nights: tienen el CutOff grande del juego original pero",
            "    no estan en ninguna de las tres tablas oficiales.",
            "2. Que hace cada valor de KeySoundID.",
            "3. Que controla el CutOff. El JUEGO ORIGINAL (LoveBeat KR y Steam)",
            "   le pone a CADA chart su propio numero, que va con cuanto hay que",
            "   tocar: unos 5.700 por flecha+SPACE. El musictable de 2016 es la",
            "   excepcion, con tres valores redondos por nivel. Parece un",
            "   PUNTAJE, pero no se puede comprobar hasta que el resumen del",
            "   final deje de salir en 0 (15.2).",
            "4. Si el codigo 1 de la tabla de patrones es izquierda.",
            "5. Cual de los cuatro compases es el bueno: eso no se resuelve",
            "   midiendo. Se decide ESCUCHANDO, con 'Mapa y los 4 compases'.",
        ]),
        ("LA REGLA QUE VALE MAS QUE TODAS", [
            "NADA SE DA POR CERRADO HASTA PROBARLO EN EL JUEGO.",
            "",
            "Este proyecto ya tuvo TRES reglas falsas escritas como comprobadas y",
            "respetadas durante meses, sacadas de una coincidencia. Una decia que",
            "no se podian agregar filas al musictable, y era mentira.",
            "",
            "Y la otra cara: SI UNA CANCION YA SUENA BIEN, NO LA MUEVAS, aunque",
            "el numero no sea redondo. Mover arranques que ya funcionaban salio",
            "caro tres veces.",
        ]),
    ]


def dependencias():
    """De que se cuelga el Estudio y si esta cada cosa. (nombre, ok, detalle).

    La idea es que esto sea CORTO. Todo lo que se pueda tener adentro, adentro:
    el motor esta en `motor\\`, los repartos de Softnyx tambien, y el .snb lo
    hace el snb_local que le decimos nosotros. Lo unico que de verdad no se
    puede reemplazar es ffmpeg (abrir un .ogg o un .mp3) y numpy (las cuentas).
    """
    import programas
    out = []

    hay, donde = programas.hay("ffmpeg")
    out.append(("ffmpeg", hay, donde if hay else
                "NO ESTA. Sin esto no se puede medir ni escuchar ni convertir. "
                "Poner ffmpeg.exe en una carpeta ffmpeg\\bin al lado del "
                "programa, o instalarlo y dejarlo en el PATH."))
    hay, donde = programas.hay("ffprobe")
    out.append(("ffprobe", hay, donde if hay else
                "NO ESTA. Viene con ffmpeg. Sin el no se leen las etiquetas de "
                "los .mp3, lo demas anda igual."))
    try:
        import numpy
        out.append(("numpy", True, "version " + numpy.__version__))
    except Exception:
        out.append(("numpy", False, "NO ESTA. `pip install numpy`."))

    faltan = [a for a in ("_flechas_softnyx.json", "_spaces_softnyx.json")
              if not (MOTOR / a).exists()]
    out.append(("el motor (motor\\)", not faltan,
                "completo, %d archivos" % len(list(MOTOR.glob("*.py")))
                if not faltan else "faltan: " + ", ".join(faltan)))

    out.append(("el juego", EXE.exists(),
                str(JUEGO) if EXE.exists() else "no encuentro %s" % EXE))
    out.append(("el musictable", TABLA.exists(),
                str(TABLA) if TABLA.exists() else "no encuentro %s" % TABLA))
    snb = SNB_LOCAL
    out.append(("snb_local.py", snb.exists(),
                str(snb) if snb.exists() else
                "no encuentro %s: sin el no se puede meter audio en el juego" % snb))
    # cada carpeta por separado: el 22/9/2026 una se habia movido y el
    # chequeo decia "ok" igual, porque alcanzaba con que existiera cualquiera
    for i, d in enumerate(OGG_DIRS):
        n = len(list(d.glob("*.ogg"))) if d.is_dir() else 0
        out.append(("audios %d" % (i + 1), d.is_dir(),
                    "%s  (%d .ogg)%s" % (d, n, "  <- aca van las nuevas" if i == 0 else "")
                    if d.is_dir() else
                    "NO EXISTE: %s. Si la moviste, corregila en cliente.json "
                    "(\"audios\")." % d))
    out.append(("Virtual DJ", VDJ.exists(),
                "%s (su cuadricula es la mejor, pero el programa mide solo si "
                "no esta)" % VDJ if VDJ.exists() else
                "no esta, y NO HACE FALTA: se mide del audio"))
    return out
