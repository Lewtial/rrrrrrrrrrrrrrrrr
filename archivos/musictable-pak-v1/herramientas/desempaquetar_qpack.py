#!/usr/bin/env python3
"""Extrae este formato QPACK, descifra sus SLK y exporta CSV sin ejecutar el juego."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import struct

from crypto_slk import crear_motor, xor_slk


def sha(datos):
    return hashlib.sha256(datos).hexdigest()


def leer_indice(datos):
    if len(datos) < 21 or datos[:6] != b'QPACK\0':
        raise ValueError('No es la variante QPACK esperada.')
    version, cantidad = struct.unpack_from('<fI', datos, 6)
    if version != 1.0 or not cantidad or 21 + cantidad * 520 > len(datos):
        raise ValueError('Cabecera o cantidad de entradas no válida.')
    fin_indice = 21 + cantidad * 520
    entradas, nombres, cursor = [], set(), fin_indice
    for i in range(cantidad):
        posicion = 21 + i * 520
        campo = datos[posicion:posicion + 512]
        if b'\0' not in campo:
            raise ValueError('Nombre de entrada sin terminador.')
        nombre = campo.split(b'\0', 1)[0].decode('ascii')
        if (not nombre or nombre in ('.', '..') or nombre != nombre.strip()
                or any(c in nombre for c in '/\\:')
                or any(ord(c) < 32 for c in nombre)
                or nombre.casefold() in nombres):
            raise ValueError('Nombre inseguro o duplicado: %r' % nombre)
        nombres.add(nombre.casefold())
        tamano, offset = struct.unpack_from('<II', datos, posicion + 512)
        if not tamano or offset != cursor or offset + tamano > len(datos):
            raise ValueError('Contenido fuera de límites, solapado o no contiguo.')
        entradas.append(dict(nombre=nombre, bytes=tamano, offset=offset))
        cursor = offset + tamano
    if cursor != len(datos):
        raise ValueError('Hay datos sin identificar al final del paquete.')
    return entradas, fin_indice


def leer_sylk(datos):
    texto = datos.rstrip(b'\0').decode('cp949', errors='strict')
    if not texto.startswith('ID;') or not texto.endswith('\r\nE\r\n'):
        raise ValueError('El resultado no es un SYLK completo.')
    celdas, x, y = {}, 1, 1
    for linea in texto.splitlines():
        if not linea.startswith(('F;', 'C;')):
            continue
        prefijo, tiene_valor, valor = linea.partition(';K')
        my = re.search(r';Y(\d+)(?:;|$)', prefijo)
        mx = re.search(r';X(\d+)(?:;|$)', prefijo)
        if my:
            y, x = int(my[1]), 1
        if mx:
            x = int(mx[1])
        if linea.startswith('C;') and tiene_valor:
            if (y, x) in celdas or x < 1 or y < 1:
                raise ValueError('Coordenada SYLK repetida o no válida.')
            if valor.startswith('"') and valor.endswith('"'):
                valor = valor[1:-1].replace('""', '"')
            celdas[y, x] = valor
            x += 1
    if not celdas:
        raise ValueError('No hay celdas en la tabla.')
    columnas = max(x for y, x in celdas)
    filas = sorted({y for y, x in celdas})
    matriz = [[celdas.get((y, x), '') for x in range(1, columnas + 1)] for y in filas]
    return matriz, len(celdas), len(datos) - len(datos.rstrip(b'\0'))


def extraer(origen, destino):
    origen, destino = Path(origen), Path(destino)
    datos = origen.read_bytes()
    entradas, fin_indice = leer_indice(datos)
    if destino.exists():
        raise ValueError('La carpeta de salida ya existe; usa otra para conservarla.')
    dec, enc = crear_motor()
    preparados = []
    for entrada in entradas:
        cifrado = datos[entrada['offset']:entrada['offset'] + entrada['bytes']]
        if len(cifrado) % 8:
            raise ValueError('Una entrada SLK no es múltiplo de ocho bytes.')
        intermedio = b''.join(dec(cifrado[i:i+8]) for i in range(0, len(cifrado), 8))
        plano = xor_slk(intermedio)
        pre = xor_slk(plano)
        recifrado = b''.join(enc(pre[i:i+8]) for i in range(0, len(pre), 8))
        if recifrado != cifrado:
            raise ValueError('La comprobación de recifrado falló.')
        matriz, celdas, padding = leer_sylk(plano)
        preparados.append((entrada, cifrado, plano, matriz, celdas, padding))
    reconstruido = datos[:fin_indice] + b''.join(p[1] for p in preparados)
    if reconstruido != datos:
        raise ValueError('La reconstrucción del paquete no coincide con el original.')
    for nombre in ('original', 'extraidos_originales', 'slk', 'csv'):
        (destino/nombre).mkdir(parents=True, exist_ok=True)
    (destino/'original'/'musictable.PAK').write_bytes(datos)
    informe = dict(formato='QPACK 1.0', entradas=len(entradas),
                   sha256_original=sha(datos), bytes_original=len(datos),
                   cabecera_y_indice_bytes=fin_indice, codificacion_slk='cp949',
                   codificacion_csv='UTF-8 con BOM', paquete_reconstruido_identico=True,
                   recifrado_identico=True, archivos=[])
    for entrada, cifrado, plano, matriz, celdas, padding in preparados:
        nombre = entrada['nombre']
        (destino/'extraidos_originales'/nombre).write_bytes(cifrado)
        # Conserva el tamaño y padding del descifrado, sin normalizar el SYLK.
        (destino/'slk'/nombre).write_bytes(plano)
        csv_nombre = str(Path(nombre).with_suffix('.csv'))
        with (destino/'csv'/csv_nombre).open('w', encoding='utf-8-sig', newline='') as f:
            csv.writer(f, delimiter=';').writerows(matriz)
        informe['archivos'].append(dict(**entrada, sha256_extraido=sha(cifrado),
            sha256_slk=sha(plano), sha256_csv=sha((destino/'csv'/csv_nombre).read_bytes()),
            padding_cero_final=padding, filas_datos=len(matriz)-1,
            columnas=len(matriz[0]), celdas=celdas, cabecera=matriz[0]))
    (destino/'manifiesto.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (destino/'indice.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Archivo', 'Offset en PAK', 'Bytes', 'Filas de datos', 'Columnas', 'SHA-256 extraído'])
        for entrada in informe['archivos']:
            w.writerow([entrada[k] for k in ('nombre','offset','bytes','filas_datos','columnas','sha256_extraido')])
    return informe


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('pak', help='Archivo QPACK original')
    p.add_argument('salida', help='Carpeta nueva donde extraer')
    args = p.parse_args()
    try:
        resultado = extraer(args.pak, args.salida)
        print('%d archivos extraídos, descifrados y exportados a CSV.' % resultado['entradas'])
    except (ValueError, OSError, UnicodeError, struct.error) as error:
        p.exit(1, str(error)+'\n')
