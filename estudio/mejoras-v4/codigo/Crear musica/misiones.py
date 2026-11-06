#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sustituir el contenido de misiones existentes sin cambiar sus tiempos.

Las acciones se identifican por el segundo absoluto de inicio del destino.
Solo cambian las dos tandas y la bolsa de direcciones: los largos, bailes,
camaras y el audio conservan sus valores.
"""
import math
from numbers import Real


TOLERANCIA_TIEMPO = 1e-4
_MARGEN_REDONDEO = 1e-10


def _cerca_tiempo(a, b):
    return math.isclose(a, b, rel_tol=0.0,
                        abs_tol=TOLERANCIA_TIEMPO + _MARGEN_REDONDEO)


def _numero(valor, nombre, positivo=False):
    if isinstance(valor, bool) or not isinstance(valor, Real):
        raise ValueError("%s debe ser un numero." % nombre)
    try:
        numero = float(valor)
    except OverflowError as e:
        raise ValueError("%s debe ser finito." % nombre) from e
    if not math.isfinite(numero) or numero < 0 or (positivo and numero == 0):
        raise ValueError("%s debe ser finito y %s." %
                         (nombre, "mayor que cero" if positivo else "no negativo"))
    return numero


def _patron(valor, nombre):
    if (not isinstance(valor, (list, tuple)) or len(valor) != 4
            or any(isinstance(x, bool) or not isinstance(x, int)
                   or not 0 <= x <= 3 for x in valor)):
        raise ValueError("%s debe tener cuatro cantidades enteras entre 0 y 3." % nombre)
    return list(valor)


def validar_misiones(acciones):
    """Valida acciones de reemplazo y devuelve copias normalizadas."""
    if not isinstance(acciones, (list, tuple)):
        raise ValueError("Las ediciones de misiones deben ser una lista.")
    resultado = []
    for i, accion in enumerate(acciones, 1):
        nombre = "Edicion de mision %d" % i
        if not isinstance(accion, dict):
            raise ValueError("%s debe ser un objeto." % nombre)
        if accion.get("tipo") != "reemplazar":
            raise ValueError("%s: solo se puede reemplazar una mision existente." % nombre)
        try:
            tiempo = _numero(accion["tiempo"], nombre + ": tiempo")
            primera = _patron(accion["primera"], nombre + ": primera tanda")
            bolsa = accion["bolsa"]
        except KeyError as e:
            raise ValueError("%s: falta el campo %s." % (nombre, e.args[0])) from e
        if isinstance(bolsa, bool) or not isinstance(bolsa, int) or not 1 <= bolsa <= 4:
            raise ValueError("%s: bolsa debe ser un entero entre 1 y 4." % nombre)
        segunda = accion.get("segunda")
        resultado.append(dict(tipo="reemplazar", tiempo=tiempo, primera=primera,
                              segunda=None if segunda is None else
                              _patron(segunda, nombre + ": segunda tanda"), bolsa=bolsa))
    return resultado


def _codificar(patron):
    return str(1 + sum(x * peso for x, peso in zip(patron, (125, 25, 5, 1))))


def _ultimas_por_tiempo(acciones):
    """La ultima edicion de cada destino, incluyendo redondeos sucesivos."""
    ordenadas = sorted(enumerate(acciones), key=lambda x: x[1]["tiempo"])
    grupos, grupo = [], []
    for item in ordenadas:
        if grupo and not _cerca_tiempo(item[1]["tiempo"], grupo[-1][1]["tiempo"]):
            grupos.append(max(grupo, key=lambda x: x[0]))
            grupo = []
        grupo.append(item)
    if grupo:
        grupos.append(max(grupo, key=lambda x: x[0]))
    return [accion for _i, accion in sorted(grupos)]


def aplicar_misiones(fila, listas, inicio, bpm, acciones, secciones=(),
                     permitir_inactivas=False):
    """Sustituye tandas y bolsa de destinos existentes, conservando la geometria.

    El inicio de cada destino debe coincidir dentro de 0.0001 segundos. Si hay
    varias acciones sobre el mismo destino manda la ultima. Un descanso siempre
    tiene prioridad: ninguna ventana nueva de cuatro u ocho tiempos puede
    cruzarlo. Una segunda tanda necesita una mision de al menos 16 tiempos.

    Durante la regeneracion, permitir_inactivas=True suspende las ediciones
    finales cubiertas por descansos, aunque su destino ya haya sido eliminado.
    La lista de acciones se conserva para recuperarlas al quitar el descanso.
    """
    acciones = validar_misiones(acciones)
    resultado = dict(listas)
    if not acciones:
        return resultado
    # Importacion local: secciones tambien usa esta validacion al persistir.
    from secciones import LISTAS, _leer_listas, validar_secciones
    secciones = validar_secciones(secciones)
    datos = dict(fila)
    datos.update(listas)
    valores, largos = _leer_listas(datos)
    inicio = _numero(inicio, "El arranque")
    if "StartDelayTime" in listas:
        try:
            if isinstance(listas["StartDelayTime"], bool):
                raise ValueError()
            inicio_guardado = float(listas["StartDelayTime"])
        except (TypeError, ValueError, OverflowError) as e:
            raise ValueError("El arranque del chart no es valido.") from e
        inicio = _numero(inicio_guardado, "El arranque del chart")
    bpm = _numero(bpm, "El BPM", positivo=True)
    per = 60.0 / bpm
    if not math.isfinite(per):
        raise ValueError("El BPM es demasiado pequeno para calcular los tiempos.")
    descansos = [s for s in secciones if s["tipo"] == "descanso"]
    if permitir_inactivas:
        activas = []
        for accion in _ultimas_por_tiempo(acciones):
            fin = accion["tiempo"] + (8 if accion["segunda"] is not None else 4) * per
            if not math.isfinite(fin):
                raise ValueError("La ventana de una edicion de mision no es finita.")
            if not any(min(fin, s["hasta"]) - max(accion["tiempo"], s["desde"])
                       > TOLERANCIA_TIEMPO + _MARGEN_REDONDEO for s in descansos):
                activas.append(accion)
        acciones = activas
    tiempos, beat = [], 0
    for largo in largos:
        try:
            tiempo = inicio + beat * per
        except OverflowError as e:
            raise ValueError("Los tiempos del chart son demasiado grandes.") from e
        if not math.isfinite(tiempo):
            raise ValueError("Los tiempos del chart deben ser finitos.")
        tiempos.append(tiempo)
        beat += largo
    destinos = {}
    for accion in acciones:
        coincidencias = [i for i, t in enumerate(tiempos)
                         if _cerca_tiempo(t, accion["tiempo"])]
        if not coincidencias:
            raise ValueError("No existe una mision que empiece en %.4f s. "
                             "Volve a elegir una mision existente en la lista."
                             % accion["tiempo"])
        if len(coincidencias) != 1:
            raise ValueError("Hay mas de una mision cerca de %.4f s; el destino "
                             "no se puede identificar con seguridad." % accion["tiempo"])
        destinos[coincidencias[0]] = accion
    for i, accion in destinos.items():
        if largos[i] < 4:
            raise ValueError("La mision %d dura menos de cuatro tiempos y no "
                             "puede recibir una tanda completa." % (i + 1))
        if accion["segunda"] is not None and largos[i] < 16:
            raise ValueError("La mision %d dura menos de 16 tiempos: no admite una "
                             "segunda tanda. Elegi sin segunda tanda." % (i + 1))
        fin_entrada = tiempos[i] + (8 if accion["segunda"] is not None else 4) * per
        if not math.isfinite(fin_entrada):
            raise ValueError("La ventana de la mision %d no es finita." % (i + 1))
        if any(min(fin_entrada, s["hasta"]) - max(tiempos[i], s["desde"])
               > TOLERANCIA_TIEMPO + _MARGEN_REDONDEO
               for s in descansos):
            raise ValueError("La mision %d se cruza con un descanso sin misiones. "
                             "Quita ese descanso o elegi otro destino." % (i + 1))
    # Conservar literalmente las columnas ajenas y los elementos no elegidos.
    for columna in LISTAS:
        resultado.setdefault(columna, datos[columna])
    for columna in ("MissionID1", "MissionID2", "KeyPatternID"):
        crudos = datos[columna].split(",")
        for i, accion in destinos.items():
            if columna == "MissionID1":
                crudos[i] = _codificar(accion["primera"])
            elif columna == "MissionID2":
                crudos[i] = "0" if accion["segunda"] is None else _codificar(accion["segunda"])
            else:
                crudos[i] = str(accion["bolsa"])
        resultado[columna] = ",".join(crudos)
    return resultado
