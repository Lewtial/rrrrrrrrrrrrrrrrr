"""Fuentes de adopción vinculadas por el registro de copias del Estudio.

El nombre visible de una canción nunca acredita que comparta audio con otra.
Solo el mismo Filename o una cadena completa de copias registradas permite
ofrecer el chart como fuente. Este módulo no lee ni escribe archivos.
"""
import copy
from collections import defaultdict, deque


def _identificador(valor):
    if isinstance(valor, bool) or not isinstance(valor, (str, int)):
        raise ValueError("El ID debe ser un número entero escrito como texto.")
    texto = str(valor)
    if not texto or not texto.isascii() or not texto.isdecimal():
        raise ValueError("El ID debe contener únicamente dígitos decimales.")
    return texto


def fuentes_relacionadas(filas, destino, copias):
    """Devuelve otras filas de la familia de audio, como copias independientes.

    ``copias`` es el diccionario ``{ID_copia: ID_original}`` de copias.json.
    Se incluyen las dificultades del mismo bkg y los bkg conectados mediante
    cadenas registradas cuyo extremo original todavía existe en ``filas``.
    No se incluyen enlaces incompletos, circulares o ambiguos. Si el linaje del
    destino está dañado se conservan las fuentes del mismo bkg. Cuando no hay
    ninguna, se avisa en vez de adivinar un origen. Los errores de registros
    ajenos al destino no impiden utilizar otras familias válidas.
    """
    if not isinstance(filas, (list, tuple)) or not isinstance(destino, dict):
        raise ValueError("La adopción necesita una tabla de filas y una versión de destino.")
    por_id = {}
    for fila in filas:
        if not isinstance(fila, dict):
            raise ValueError("Cada versión de la tabla debe ser una fila con ID y archivo bkg.")
        identificador = _identificador(fila.get("ID"))
        nombre = fila.get("Filename")
        if not isinstance(nombre, str) or not nombre.strip():
            raise ValueError("La fila %s necesita un archivo bkg válido." % identificador)
        if identificador in por_id:
            raise ValueError("El ID %s aparece más de una vez; no puedo identificar su versión." % identificador)
        por_id[identificador] = fila

    destino_id = _identificador(destino.get("ID"))
    if destino_id not in por_id or destino.get("Filename") != por_id[destino_id]["Filename"]:
        raise ValueError("La versión de destino ya no coincide con la tabla actual.")
    mismas = [f for i, f in por_id.items()
              if i != destino_id and f["Filename"] == destino["Filename"]]

    def sin_cruzar(motivo):
        if mismas:
            return copy.deepcopy(mismas)
        raise ValueError("No pude comprobar el origen de esta copia: %s. Revisá copias.json." % motivo)

    if not isinstance(copias, dict):
        return sin_cruzar("el registro de copias tiene un formato inválido")

    # Una clave JSON habitual es texto. También admitimos enteros de versiones
    # anteriores, rechazando duplicados normalizados que indiquen padres distintos.
    padres, invalidos = {}, {}
    for clave, valor in copias.items():
        try:
            identificador = _identificador(clave)
        except ValueError:
            continue
        if identificador not in por_id:
            continue
        try:
            padre = _identificador(valor)
        except ValueError:
            invalidos[identificador] = "el ID original no es válido"
            continue
        if identificador in padres and padres[identificador] != padre:
            invalidos[identificador] = "hay más de un original registrado"
        else:
            padres[identificador] = padre

    estados = {}

    def linaje(identificador):
        """Resuelve iterativamente para admitir cadenas largas y detectar ciclos."""
        if identificador in estados:
            return estados[identificador]
        camino, posiciones, actual = [], set(), identificador
        while True:
            if actual in estados:
                resultado = estados[actual]
                break
            if actual in posiciones:
                resultado = "el registro de copias contiene un ciclo"
                break
            if actual not in por_id:
                resultado = "falta la fila original %s" % actual
                break
            if actual in invalidos:
                resultado = invalidos[actual]
                break
            if actual not in padres:
                resultado = None
                break
            posiciones.add(actual)
            camino.append(actual)
            actual = padres[actual]
        for elemento in camino:
            estados[elemento] = resultado
        estados.setdefault(identificador, resultado)
        return resultado

    problema = linaje(destino_id)
    if problema:
        return sin_cruzar(problema)

    # Todas las dificultades de un bkg comparten audio. Sus enlaces de copia
    # deben converger al mismo bkg original: dos padres distintos no prueban
    # parentesco entre dos canciones. Procesar desde las raíces también permite
    # copias de copias y familias con enlaces transitivos sin recurrencia.
    padres_bkg = {f["Filename"]: set() for f in por_id.values()}
    enlaces = []
    for copia_id, original_id in padres.items():
        if linaje(copia_id) is None:
            copia_bkg = por_id[copia_id]["Filename"]
            original_bkg = por_id[original_id]["Filename"]
            if copia_bkg != original_bkg:
                padres_bkg[copia_bkg].add(original_bkg)
                enlaces.append((copia_bkg, original_bkg))
    hijos = defaultdict(set)
    restantes = {nombre: len(padres) for nombre, padres in padres_bkg.items()}
    for hijo, padres in padres_bkg.items():
        for padre in padres:
            hijos[padre].add(hijo)
    pendientes = deque(nombre for nombre, n in restantes.items() if n == 0)
    raices, problemas_bkg = {}, {}
    for nombre in pendientes:
        raices[nombre] = {nombre}
    while pendientes:
        nombre = pendientes.popleft()
        for hijo in hijos[nombre]:
            raices.setdefault(hijo, set()).update(raices[nombre])
            if nombre in problemas_bkg:
                problemas_bkg[hijo] = problemas_bkg[nombre]
            restantes[hijo] -= 1
            if restantes[hijo] == 0:
                if len(raices[hijo]) > 1:
                    problemas_bkg[hijo] = "el bkg está vinculado a originales de canciones distintas"
                pendientes.append(hijo)
    for nombre, n in restantes.items():
        if n:
            problemas_bkg[nombre] = "el parentesco entre archivos bkg contiene un ciclo"
    if destino["Filename"] in problemas_bkg:
        return sin_cruzar(problemas_bkg[destino["Filename"]])

    vecinos = defaultdict(set)
    for copia_bkg, original_bkg in enlaces:
        if copia_bkg in problemas_bkg or original_bkg in problemas_bkg:
            continue
        vecinos[copia_bkg].add(original_bkg)
        vecinos[original_bkg].add(copia_bkg)

    nombres, pendientes = set(), [destino["Filename"]]
    while pendientes:
        nombre = pendientes.pop()
        if nombre in nombres:
            continue
        nombres.add(nombre)
        pendientes.extend(vecinos[nombre] - nombres)

    return [copy.deepcopy(fila) for identificador, fila in por_id.items()
            if identificador != destino_id and fila["Filename"] in nombres]
