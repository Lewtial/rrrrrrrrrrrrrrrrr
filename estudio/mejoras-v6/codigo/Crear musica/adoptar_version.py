#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adoptar un chart existente de la misma canción sin tocar archivos.

La geometría se conserva literalmente entre BPM iguales. Al cambiar el BPM,
los arranques absolutos se llevan al compás más cercano del destino, anclado
al primer arranque de la fuente. El informe describe cada ajuste u omisión.
"""
import hashlib
import math

from secciones import LISTAS, _leer_listas, validar_secciones


TOLERANCIA = 1e-4


def _numero(valor, nombre, positivo=False):
    if isinstance(valor, bool):
        raise ValueError("%s debe ser un número finito." % nombre)
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("%s debe ser un número finito." % nombre) from error
    if not math.isfinite(numero) or numero < 0 or (positivo and numero == 0):
        raise ValueError("%s debe ser finito y %s." %
                         (nombre, "mayor que cero" if positivo else "no negativo"))
    return numero


def _entero(valor, nombre, minimo, maximo):
    numero = _numero(valor, nombre)
    if not numero.is_integer() or not minimo <= numero <= maximo:
        raise ValueError("%s debe ser un entero entre %d y %d." %
                         (nombre, minimo, maximo))
    return int(numero)


def limite_por_nivel(estrellas, bpm):
    """Tope por casillero, siguiendo las reglas de adopción del usuario.

    El intervalo 221–229 BPM usa dos flechas de forma conservadora. Las
    estrellas 1–3 conservan el límite de dos de las referencias del Estudio.
    """
    estrellas = _entero(estrellas, "Las estrellas", 1, 10)
    bpm = _numero(bpm, "El BPM", positivo=True)
    if estrellas <= 3:
        return 2
    if estrellas <= 6:
        return 3 if bpm <= 220 else 2
    if estrellas <= 8:
        return 2 if bpm >= 230 else 3
    return 3


def _patron(valor, nombre):
    numero = _entero(valor, nombre, 0, 625)
    if numero == 0:
        return [0, 0, 0, 0]
    numero -= 1
    return [numero // 125, (numero // 25) % 5, (numero // 5) % 5, numero % 5]


def _codificar(patron):
    return str(1 + sum(x * peso for x, peso in zip(patron, (125, 25, 5, 1))))


def _compas(tiempos):
    """Redondeo al múltiplo de cuatro más próximo; mitades hacia delante."""
    if not math.isfinite(tiempos) or tiempos < 0:
        raise ValueError("Los tiempos del chart son demasiado grandes.")
    return int(math.floor(tiempos / 4.0 + 0.5)) * 4


def _solapa(desde, hasta, descansos):
    return any(min(hasta, s["hasta"]) - max(desde, s["desde"]) > TOLERANCIA
               for s in descansos)


def _estadisticas_entradas(listas):
    cantidades = []
    for columna in ("MissionID1", "MissionID2"):
        for valor in listas[columna]:
            if columna == "MissionID2" and float(valor) == 0:
                continue
            cantidades.extend(_patron(valor, columna))
    positivas = [x for x in cantidades if x > 0]
    return dict(flechas=sum(positivas), triples=positivas.count(3),
                positivas=len(positivas), spaces=cantidades.count(0))


def _cuotas_positivas(referencia, cantidad, tope):
    """Cuotas de 1..tope por restos mayores, conservando todos los SPACE."""
    pesos = [0.] * tope
    for numero in range(1, len(referencia)):
        pesos[min(numero, tope) - 1] += referencia[numero]
    total = sum(pesos)
    reales = [cantidad * peso / total for peso in pesos]
    cuotas = [int(math.floor(x)) for x in reales]
    orden = sorted(range(tope), key=lambda i: (reales[i] - cuotas[i], i), reverse=True)
    for i in orden[:cantidad - sum(cuotas)]:
        cuotas[i] += 1
    return cuotas


def _elevar_entradas(listas, nivel, tope, resumen):
    """Eleva grupos existentes con un reparto estable de las referencias reales.

    La primera y segunda tanda usan sus propias distribuciones condicionadas a
    casilleros positivos. La intensidad existente ordena las asignaciones; un
    hash estable distribuye los empates por el chart sin usar RNG, ID ni arranque.
    """
    from nucleo import REF_FLECHAS, REF_SPACE
    for columna, referencia, sufijo in (("MissionID1", REF_FLECHAS[nivel], "primera"),
                                        ("MissionID2", REF_SPACE[nivel], "segunda")):
        patrones, casilleros = {}, []
        for i, valor in enumerate(listas[columna]):
            if columna == "MissionID2" and float(valor) == 0:
                continue
            patron = _patron(valor, columna)
            patrones[i] = patron
            for k, numero in enumerate(patron):
                if numero > 0:
                    llave = ("%s:%d:%d" % (columna, i, k)).encode("ascii")
                    desempate = hashlib.blake2b(llave, digest_size=8).digest()
                    casilleros.append((numero, desempate, i, k))
        casilleros.sort()
        cuotas = _cuotas_positivas(referencia, len(casilleros), tope)
        objetivos = [numero for numero, cantidad in enumerate(cuotas, 1)
                     for _ in range(cantidad)]
        cambiadas = set()
        for (actual, _orden, i, k), objetivo in zip(casilleros, objetivos):
            nuevo = max(actual, objetivo)
            if nuevo == actual:
                continue
            patrones[i][k] = nuevo
            cambiadas.add(i)
            resumen["grupos_aumentados"] += 1
            resumen["flechas_agregadas"] += nuevo - actual
            resumen["grupos_aumentados_" + sufijo] += 1
            resumen["flechas_agregadas_" + sufijo] += nuevo - actual
        for i in cambiadas:
            listas[columna][i] = _codificar(patrones[i])


def adoptar_version(origen, destino, *, estrellas=None, descansos=(), limite_flechas=None,
                    ajustar_nivel=False):
    """Devuelve ``(nuevos, resumen)`` sin modificar ninguno de los argumentos.

    ``nuevos`` contiene las diez listas del chart y StartDelayTime; Difficulty
    solo se incluye cuando se indican estrellas explícitamente. ID, Filename,
    BPM, título, audio y demás metadatos del destino quedan fuera del resultado.
    Los SPACE se conservan. Se recortan los grupos sobre el tope; al indicar
    ajustar_nivel=True también se elevan grupos si el destino tiene más estrellas
    que el origen, manteniendo la distribución de casilleros y segunda tanda.
    ``descansos`` admite las secciones completas de la fuente y toma sus descansos.
    """
    if not isinstance(origen, dict) or not isinstance(destino, dict):
        raise ValueError("El origen y el destino deben ser filas de una canción.")
    if type(ajustar_nivel) is not bool:
        raise ValueError("Ajustar el nivel debe ser una opción booleana.")
    nombre = origen.get("Filename")
    if not isinstance(nombre, str) or not nombre.strip() or nombre != destino.get("Filename"):
        raise ValueError("Solo se puede adoptar otra versión con el mismo archivo bkg (Filename).")
    if (origen.get("ID") is not None and destino.get("ID") is not None
            and str(origen["ID"]) == str(destino["ID"])):
        raise ValueError("Elegí una versión de origen diferente del destino.")
    bpm_origen = _numero(origen.get("BPM"), "El BPM del origen", positivo=True)
    bpm_destino = _numero(destino.get("BPM"), "El BPM del destino", positivo=True)
    inicio = _numero(origen.get("StartDelayTime"), "El arranque del origen")
    nivel = _entero(destino.get("Difficulty") if estrellas is None else estrellas,
                    "Las estrellas del destino", 1, 10)
    nivel_origen = (_entero(origen.get("Difficulty"), "Las estrellas del origen", 1, 10)
                    if ajustar_nivel else None)
    tope = limite_por_nivel(nivel, bpm_destino)
    if limite_flechas is not None:
        elegido = _entero(limite_flechas, "El límite de flechas", 1, 3)
        if elegido > tope:
            raise ValueError("El límite elegido supera el máximo de %d flechas para este nivel y BPM." % tope)
        tope = elegido
    valores, largos = _leer_listas(origen)
    crudos = {col: origen[col].split(",") for col in LISTAS}
    if any(largo < 4 for largo in largos):
        raise ValueError("La fuente tiene una misión de menos de cuatro tiempos.")
    descansos = [s for s in validar_secciones(descansos) if s["tipo"] == "descanso"]
    mismo = math.isclose(bpm_origen, bpm_destino, rel_tol=0.0, abs_tol=1e-9)
    per_origen, per_destino = 60.0 / bpm_origen, 60.0 / bpm_destino
    if not all(math.isfinite(p) and p > 0 for p in (per_origen, per_destino)):
        raise ValueError("El BPM no permite calcular tiempos finitos.")
    posiciones, beat = [], 0
    for largo in largos:
        posiciones.append(beat)
        beat += largo
    fin_origen = inicio + beat * per_origen
    if not math.isfinite(fin_origen):
        raise ValueError("La duración del chart debe ser finita.")
    resumen = dict(bpm_origen=bpm_origen, bpm_destino=bpm_destino, mismo_bpm=mismo,
                   estrellas=nivel, tope_flechas=tope, misiones_origen=len(largos),
                   misiones_destino=0, grupos_reducidos=0, flechas_retiradas=0,
                   segundas_retiradas=0, misiones_omitidas=0, inicio_origen=inicio,
                   inicio_destino=inicio, fin_origen=fin_origen, fin_destino=fin_origen,
                   error_max_segundos=0.0, ajustes=[], omisiones=[], advertencias=[],
                   descansos=list(descansos), regla="Máximo %d flechas por casillero; %d estrellas a %.2f BPM." %
                   (tope, nivel, bpm_destino))
    resumen.update(ajuste_subida=bool(ajustar_nivel and nivel > nivel_origen),
                   origen_estrellas=nivel_origen, grupos_aumentados=0, flechas_agregadas=0,
                   grupos_aumentados_primera=0, grupos_aumentados_segunda=0,
                   flechas_agregadas_primera=0, flechas_agregadas_segunda=0)
    if 4 <= nivel <= 6 and 220 < bpm_destino < 230:
        resumen["advertencias"].append("Entre 220 y 230 BPM se usa el límite conservador de dos flechas.")
    contenidos = []
    for i, largo in enumerate(largos):
        primera_id = _entero(valores["MissionID1"][i], "MissionID1 de la misión %d" % (i + 1), 1, 625)
        primera = _patron(primera_id, "MissionID1 de la misión %d" % (i + 1))
        segunda_id = _entero(valores["MissionID2"][i], "MissionID2 de la misión %d" % (i + 1), 0, 625)
        segunda = None if segunda_id == 0 else _patron(segunda_id, "MissionID2")
        _entero(valores["KeyPatternID"][i], "La bolsa de la misión %d" % (i + 1), 1, 4)
        if segunda is not None and largo < 16:
            raise ValueError("La misión %d del origen tiene segunda tanda pero dura menos de 16 tiempos." % (i + 1))
        contenidos.append((primera, segunda))
    # Un largo superior a la misión habitual absorbe misiones retiradas. Esa
    # extensión es un hueco; el baile normal de 16 tiempos no se trata como descanso.
    huecos = list(descansos)
    if not mismo:
        for pos, largo in zip(posiciones, largos):
            if largo > 16:
                huecos.append(dict(tipo="descanso", desde=inicio+(pos+16)*per_origen,
                                   hasta=inicio+(pos+largo)*per_origen))
        resumen["descansos"] = huecos
        resumen["advertencias"].append("BPM distintos: se ajustan los inicios al compás del destino, anclado al arranque del origen.")
    fin_beat = beat if mismo else _compas(beat * bpm_destino / bpm_origen)
    # Evitar que el redondeo del último compás exceda la duración conocida del audio.
    if not mismo:
        for fila, nombre_duracion in ((origen, "origen"), (destino, "destino")):
            if fila.get("Second") not in (None, "", "0", 0):
                duracion = _numero(fila["Second"], "La duración del " + nombre_duracion, positivo=True)
                max_beat = int(math.floor((duracion - inicio) / (4 * per_destino) + 1e-10)) * 4
                fin_beat = min(fin_beat, max_beat)
    if fin_beat < 4:
        raise ValueError("No cabe una misión completa en la duración del destino.")
    candidatos = []
    ocupados = set()

    def omitir(i, motivo):
        resumen["omisiones"].append(dict(mision_origen=i + 1,
                                         inicio_origen=inicio + posiciones[i] * per_origen,
                                         motivo=motivo))

    for i, pos in enumerate(posiciones):
        posicion = pos if mismo else _compas(pos * bpm_destino / bpm_origen)
        if posicion in ocupados:
            omitir(i, "Comparte el mismo compás de destino con otra misión.")
            continue
        if posicion + 4 > fin_beat:
            omitir(i, "No quedan cuatro tiempos completos antes del final del chart.")
            continue
        ocupados.add(posicion)
        candidatos.append((i, posicion))
    conservados = []
    for k, (i, posicion) in enumerate(candidatos):
        siguiente = candidatos[k + 1][1] if k + 1 < len(candidatos) else fin_beat
        largo = siguiente - posicion
        primera, segunda = contenidos[i]
        desde = inicio + posicion * per_destino
        if segunda is not None and largo < 16:
            if mismo:
                raise ValueError("La misión de origen no admite su segunda tanda.")
            segunda = None
        fin_entrada = desde + (8 if segunda is not None else 4) * per_destino
        if _solapa(desde, fin_entrada, huecos):
            if mismo:
                raise ValueError("La misión %d del origen invade un descanso: aplicá el descanso en la fuente antes de adoptar." % (i + 1))
            omitir(i, "La ventana de entrada adaptada se cruza con un descanso del origen.")
            continue
        conservados.append((i, posicion, primera, segunda))
    if not conservados:
        raise ValueError("La adaptación no deja ninguna misión válida: revisá los BPM, la duración o los descansos.")
    nuevas = {col: [] for col in LISTAS}
    for k, (i, pos, primera, segunda) in enumerate(conservados):
        siguiente = conservados[k + 1][1] if k + 1 < len(conservados) else fin_beat
        for col in LISTAS:
            nuevas[col].append(crudos[col][i] if mismo else valores[col][i])
        nuevas["Length"][-1] = crudos["Length"][i] if mismo else str(siguiente-pos)
        for columna, tanda in (("MissionID1", primera), ("MissionID2", segunda)):
            if tanda is None:
                nuevas[columna][-1] = crudos[columna][i] if mismo else "0"
                continue
            recortada = [min(x, tope) for x in tanda]
            resumen["grupos_reducidos"] += sum(a != b for a, b in zip(tanda, recortada))
            resumen["flechas_retiradas"] += sum(a-b for a, b in zip(tanda, recortada))
            if recortada != tanda:
                nuevas[columna][-1] = _codificar(recortada)
        desde_origen = inicio + posiciones[i]*per_origen
        desde_destino = inicio + pos*per_destino
        desvio = desde_destino-desde_origen
        segunda_retirada = contenidos[i][1] is not None and segunda is None
        resumen["segundas_retiradas"] += int(segunda_retirada)
        resumen["ajustes"].append(dict(mision_origen=i+1, inicio_origen=desde_origen,
                                       inicio_destino=desde_destino, desvio_segundos=desvio,
                                       largo_origen=largos[i], largo_destino=siguiente-pos,
                                       segunda_retirada=segunda_retirada))
        resumen["error_max_segundos"] = max(resumen["error_max_segundos"], abs(desvio))
    if not mismo:
        nuevas["MissionCameraID"][0] = "101"
        nuevas["DanceCameraID"][-1] = "241"
    antes_subida = _estadisticas_entradas(nuevas)
    if resumen["ajuste_subida"]:
        _elevar_entradas(nuevas, nivel, tope, resumen)
    despues_subida = _estadisticas_entradas(nuevas)
    resumen.update(flechas_antes=antes_subida["flechas"], flechas_despues=despues_subida["flechas"],
                   triples_antes=antes_subida["triples"], triples_despues=despues_subida["triples"],
                   casilleros_positivos=antes_subida["positivas"],
                   spaces_antes=antes_subida["spaces"], spaces_despues=despues_subida["spaces"],
                   flechas_por_casillero_antes=(antes_subida["flechas"] / antes_subida["positivas"]
                                               if antes_subida["positivas"] else 0.),
                   flechas_por_casillero_despues=(despues_subida["flechas"] / despues_subida["positivas"]
                                                 if despues_subida["positivas"] else 0.))
    if resumen["ajuste_subida"] and not resumen["grupos_aumentados"]:
        if not antes_subida["positivas"]:
            resumen["advertencias"].append("La fuente solo contiene SPACE: se conservan sus casilleros y no hay grupos de flechas que aumentar.")
        elif antes_subida["flechas"] == antes_subida["positivas"] * tope:
            resumen["advertencias"].append("Los grupos existentes ya alcanzan el límite de %d flechas del destino; se conserva su contenido." % tope)
    nuevos = {col: ",".join(partes) for col, partes in nuevas.items()}
    nuevos["StartDelayTime"] = (origen["StartDelayTime"] if mismo else
                                  "%.12g" % (inicio+conservados[0][1]*per_destino))
    if estrellas is not None:
        nuevos["Difficulty"] = str(nivel)
    resumen["misiones_destino"] = len(conservados)
    resumen["misiones_omitidas"] = len(resumen["omisiones"])
    resumen["inicio_destino"] = float(nuevos["StartDelayTime"])
    resumen["fin_destino"] = inicio + fin_beat*per_destino
    resumen["error_fin_segundos"] = resumen["fin_destino"]-fin_origen
    resumen["misiones_ajustadas"] = sum(abs(a["desvio_segundos"]) > TOLERANCIA
                                        for a in resumen["ajustes"])
    resumen["duracion_origen"] = fin_origen-inicio
    resumen["duracion_destino"] = resumen["fin_destino"]-resumen["inicio_destino"]
    if resumen["misiones_ajustadas"]:
        resumen["advertencias"].append("Se ajustaron %d inicios; el mayor desvío es %.4f segundos." %
                                       (resumen["misiones_ajustadas"], resumen["error_max_segundos"]))
    if abs(resumen["error_fin_segundos"]) > TOLERANCIA:
        resumen["advertencias"].append("El final del chart cambia %.4f segundos al adaptarse al compás del destino." %
                                       resumen["error_fin_segundos"])
    if resumen["segundas_retiradas"]:
        resumen["advertencias"].append("Se retiraron %d segundas tandas porque el destino no llega a 16 tiempos." % resumen["segundas_retiradas"])
    if resumen["misiones_omitidas"]:
        resumen["advertencias"].append("Se omitieron %d misiones; revisá los motivos antes de aplicar." % resumen["misiones_omitidas"])
    return nuevos, resumen
