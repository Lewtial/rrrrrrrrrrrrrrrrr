#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patrones por tramo y descansos reales, independientes de la interfaz.

Los tiempos de las secciones son segundos absolutos del audio. Los ceros de un
patron son casilleros SPACE; una segunda tanda ausente se representa con None.
La configuracion del editor se guarda aparte de las columnas del musictable.
"""
import json
import math
import os
import tempfile
from numbers import Real
from pathlib import Path


LISTAS = ("Length", "KeyPatternID", "KeySoundID", "MissionID1", "MissionID2",
          "MissionDanceID", "MissionSuccessDanceID", "MissionFailDanceID",
          "MissionCameraID", "DanceCameraID")
ARCHIVO = "configuracion_secciones.json"
VERSION = 2


def _numero(valor, nombre, minimo=0.0, positivo=False):
    if isinstance(valor, bool) or not isinstance(valor, Real):
        raise ValueError("%s debe ser un numero." % nombre)
    try:
        valor = float(valor)
    except OverflowError as e:
        raise ValueError("%s debe ser un numero finito." % nombre) from e
    if not math.isfinite(valor) or valor < minimo or (positivo and valor == 0):
        raise ValueError("%s debe ser finito y %s." %
                         (nombre, "mayor que cero" if positivo else "no negativo"))
    return valor


def _patron(valor, nombre):
    if (not isinstance(valor, (list, tuple)) or len(valor) != 4
            or any(isinstance(x, bool) or not isinstance(x, int)
                   or not 0 <= x <= 3 for x in valor)):
        raise ValueError("%s debe tener cuatro cantidades enteras entre 0 y 3." % nombre)
    return list(valor)


def validar_secciones(secciones):
    """Valida y devuelve una copia normalizada, sin modificar lo recibido."""
    if not isinstance(secciones, (list, tuple)):
        raise ValueError("Las secciones deben ser una lista de tramos.")
    resultado = []
    for i, seccion in enumerate(secciones, 1):
        if not isinstance(seccion, dict):
            raise ValueError("La seccion %d debe ser un objeto." % i)
        nombre = "Seccion %d" % i
        try:
            desde = _numero(seccion["desde"], nombre + ": desde")
            hasta = _numero(seccion["hasta"], nombre + ": hasta")
            tipo = seccion["tipo"]
        except KeyError as e:
            raise ValueError("%s: falta el campo %s." % (nombre, e.args[0])) from e
        if hasta <= desde:
            raise ValueError("%s: hasta debe ser mayor que desde." % nombre)
        if tipo not in ("patron", "descanso"):
            raise ValueError("%s: tipo debe ser patron o descanso." % nombre)
        nueva = dict(desde=desde, hasta=hasta, tipo=tipo)
        if tipo == "patron":
            if "primera" not in seccion or "bolsa" not in seccion:
                raise ValueError("%s: un patron necesita primera y bolsa." % nombre)
            nueva["primera"] = _patron(seccion["primera"], nombre + ": primera tanda")
            segunda = seccion.get("segunda")
            nueva["segunda"] = (None if segunda is None else
                                _patron(segunda, nombre + ": segunda tanda"))
            bolsa = seccion["bolsa"]
            if isinstance(bolsa, bool) or not isinstance(bolsa, int) or not 1 <= bolsa <= 4:
                raise ValueError("%s: bolsa debe ser un entero entre 1 y 4." % nombre)
            nueva["bolsa"] = bolsa
        resultado.append(nueva)
    return resultado


def _codificar(patron):
    return str(1 + sum(x * peso for x, peso in zip(patron, (125, 25, 5, 1))))


def _leer_listas(datos):
    resultado = {}
    for columna in LISTAS:
        valor = datos.get(columna)
        if not isinstance(valor, str):
            raise ValueError("El chart necesita la lista %s en formato de texto." % columna)
        valores = [x.strip() for x in valor.split(",")]
        if not valor or any(not x for x in valores):
            raise ValueError("La lista %s esta vacia o tiene elementos vacios." % columna)
        resultado[columna] = valores
    n = len(resultado["Length"])
    if any(len(x) != n for x in resultado.values()):
        raise ValueError("Las diez listas del chart deben tener la misma cantidad de misiones.")
    largos = []
    for valor in resultado["Length"]:
        try:
            numero = float(valor)
            if not math.isfinite(numero) or numero <= 0 or not numero.is_integer():
                raise ValueError()
            largos.append(int(numero))
        except (ValueError, OverflowError) as e:
            raise ValueError("Length debe contener largos enteros mayores que cero.") from e
    return resultado, largos


def aplicar_secciones(fila, listas, inicio, bpm, secciones):
    """Aplica patrones y elimina entradas que se solapan con descansos.

    La ultima seccion de patron selecciona el contenido de una mision por su
    inicio. Los descansos tienen prioridad y miran sus 4 u 8 tiempos de entrada.
    Las misiones supervivientes conservan sus segundos absolutos; los largos
    absorben los huecos y la cola, incluso si superan los 96 tiempos.
    """
    secciones = validar_secciones(secciones)
    resultado = dict(listas)
    if not secciones:
        return resultado
    inicio = _numero(inicio, "El arranque")
    bpm = _numero(bpm, "El BPM", positivo=True)
    datos = dict(fila)
    datos.update(listas)
    valores, largos = _leer_listas(datos)
    per = 60.0 / bpm
    if not math.isfinite(per):
        raise ValueError("El BPM es demasiado pequeno para calcular los tiempos del chart.")
    posiciones, pos = [], 0
    for largo in largos:
        posiciones.append(pos)
        pos += largo
    fin = pos
    descansos = [s for s in secciones if s["tipo"] == "descanso"]
    patrones = [s for s in secciones if s["tipo"] == "patron"]
    supervivientes = []
    for i, beat in enumerate(posiciones):
        tiempo = inicio + beat * per
        patron = next((s for s in reversed(patrones)
                       if s["desde"] <= tiempo < s["hasta"]), None)
        if patron is not None:
            valores["MissionID1"][i] = _codificar(patron["primera"])
            valores["MissionID2"][i] = ("0" if patron["segunda"] is None else
                                       _codificar(patron["segunda"]))
            valores["KeyPatternID"][i] = str(patron["bolsa"])
        segunda = valores["MissionID2"][i] not in ("0", "0.0")
        fin_entrada = tiempo + (8 if segunda else 4) * per
        if any(min(fin_entrada, s["hasta"]) > max(tiempo, s["desde"])
               for s in descansos):
            continue
        if patron is not None and patron["segunda"] is not None and largos[i] < 16:
            raise ValueError("La mision %d dura menos de 16 tiempos: no admite una "
                             "segunda tanda. Elegi sin segunda tanda para ese tramo." % (i + 1))
        supervivientes.append(i)
    if not supervivientes:
        raise ValueError("Los descansos eliminan todas las misiones. Deja al menos "
                         "una mision fuera de los descansos.")
    for columna in LISTAS:
        valores[columna] = [valores[columna][i] for i in supervivientes]
    puntos = [posiciones[i] for i in supervivientes] + [fin]
    valores["Length"] = [str(b - a) for a, b in zip(puntos, puntos[1:])]
    # Las marcas de camara pertenecen a la primera y ultima mision presentes.
    valores["MissionCameraID"][0] = "101"
    valores["DanceCameraID"][-1] = "241"
    resultado.update((columna, ",".join(valores[columna])) for columna in LISTAS)
    if supervivientes[0] != 0:
        resultado["StartDelayTime"] = "%.12g" % (inicio + puntos[0] * per)
    return resultado


def _clave(clave):
    if not isinstance(clave, str) or not clave.strip():
        raise ValueError("La clave de configuracion debe ser un texto no vacio (Filename:ID).")
    return clave


def _leer_configuracion(carpeta):
    ruta = Path(carpeta) / ARCHIVO
    if not ruta.exists():
        return dict(version=VERSION, charts={})
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if (not isinstance(datos, dict) or type(datos.get("version")) is not int
                or datos.get("version") not in (1, VERSION)
                or not isinstance(datos.get("charts"), dict)):
            raise ValueError("formato o version desconocida")
        for clave, cfg in datos["charts"].items():
            _clave(clave)
            if not isinstance(cfg, dict) or "secciones" not in cfg:
                raise ValueError("la configuracion de %s no es valida" % clave)
            cfg["secciones"] = validar_secciones(cfg["secciones"])
            inicio = cfg.get("inicio")
            cfg["inicio"] = None if inicio is None else _numero(inicio, "El arranque guardado")
            from misiones import validar_misiones
            cfg["misiones"] = validar_misiones(cfg.get("misiones", []))
        datos["version"] = VERSION
        return datos
    except (OSError, UnicodeError, ValueError, TypeError) as e:
        raise ValueError("No pude leer %s: %s. Conserva el archivo para recuperar "
                         "la configuracion antes de reemplazarlo." % (ruta, e)) from e


def cargar_configuracion(carpeta, clave):
    """Devuelve secciones, ancla original y reemplazos de misiones de una fila."""
    clave = _clave(clave)
    cfg = _leer_configuracion(carpeta)["charts"].get(clave)
    if cfg is None:
        return dict(secciones=[], inicio=None, misiones=[])
    from misiones import validar_misiones
    return dict(secciones=validar_secciones(cfg["secciones"]), inicio=cfg["inicio"],
                misiones=validar_misiones(cfg["misiones"]))


def guardar_configuracion(carpeta, clave, secciones, inicio=None, misiones=None):
    """Guarda atomicamente; misiones=None conserva las ediciones anteriores."""
    clave = _clave(clave)
    secciones = validar_secciones(secciones)
    inicio = None if inicio is None else _numero(inicio, "El arranque guardado")
    datos = _leer_configuracion(carpeta)
    from misiones import validar_misiones
    if misiones is None:
        misiones = datos["charts"].get(clave, {}).get("misiones", [])
    misiones = validar_misiones(misiones)
    datos["charts"][clave] = dict(secciones=secciones, inicio=inicio, misiones=misiones)
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(carpeta),
                                         prefix=".secciones-", suffix=".tmp", delete=False) as f:
            temporal = Path(f.name)
            json.dump(datos, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(temporal), str(carpeta / ARCHIVO))
    finally:
        if temporal is not None and temporal.exists():
            temporal.unlink()
