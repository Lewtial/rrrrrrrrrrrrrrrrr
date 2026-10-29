"""Cifrado SLK del paquete aportado. No ejecuta ningún cliente del juego."""
import struct
from pathlib import Path

POST_XOR = [
    0xED41, 0xF319, 0xF87B, 0xE3D1, 0xDAC3, 0xDB67, 0xD489, 0xC829,
    0xA49B, 0x74A7, 0x5A7F, 0x1AD7, 0x0305, 0xE545, 0xFEE9, 0x5597,
]

CLAVE_RESERVA = b"Lovebeat!@#$()"

def _motor(p0, s0, key):
    p, s = p0[:], s0[:]
    k = 0
    def f(x):
        return ((((s[(x >> 24) & 255] + s[256 + ((x >> 16) & 255)]) & 0xFFFFFFFF)
                 ^ s[512 + ((x >> 8) & 255)]) + s[768 + (x & 255)]) & 0xFFFFFFFF
    for i in range(18):
        v = 0
        for _ in range(4):
            v = (v << 8) | key[k]; k = (k + 1) % len(key)
        p[i] ^= v
    def enc_par(l, r):
        for i in range(16):
            l = (l ^ p[i]) & 0xFFFFFFFF
            r = (r ^ f(l)) & 0xFFFFFFFF
            l, r = r, l
        l, r = r, l
        return (l ^ p[17]) & 0xFFFFFFFF, (r ^ p[16]) & 0xFFFFFFFF
    l = r = 0
    for i in range(0, 18, 2):
        l, r = enc_par(l, r); p[i], p[i + 1] = l, r
    for i in range(0, 1024, 2):
        l, r = enc_par(l, r); s[i], s[i + 1] = l, r

    def descifrar_bloque(b):
        l, r = struct.unpack(">II", b)
        for i in range(17, 1, -1):
            l = (l ^ p[i]) & 0xFFFFFFFF
            r = (r ^ f(l)) & 0xFFFFFFFF
            l, r = r, l
        l, r = r, l
        return struct.pack(">II", (l ^ p[0]) & 0xFFFFFFFF, (r ^ p[1]) & 0xFFFFFFFF)

    def cifrar_bloque(b):
        l, r = struct.unpack(">II", b)
        for i in range(16):
            l = (l ^ p[i]) & 0xFFFFFFFF
            r = (r ^ f(l)) & 0xFFFFFFFF
            l, r = r, l
        l, r = r, l
        return struct.pack(">II", (l ^ p[17]) & 0xFFFFFFFF, (r ^ p[16]) & 0xFFFFFFFF)

    return descifrar_bloque, cifrar_bloque

def crear_motor():
    tablas = Path(__file__).with_name('blowfish_reserva.bin').read_bytes()
    if len(tablas) != 4168:
        raise ValueError('Las tablas Blowfish no tienen el tamaño esperado.')
    p = list(struct.unpack_from('<18I', tablas))
    s = list(struct.unpack_from('<1024I', tablas, 72))
    return _motor(p, s, CLAVE_RESERVA.ljust(56, b'\0'))


def xor_slk(datos):
    # En estos SLK la última palabra de 16 bits queda fuera de la capa XOR.
    # Incluirla altera el final E\r\n/padding; se comprobó en las 30 entradas.
    salida = bytearray(datos)
    contador = int(f'{len(salida):032b}'[::-1], 2)
    for off in range(0, len(salida) - 2, 2):
        mascara = 0
        for bit, valor in enumerate(POST_XOR):
            if contador & (1 << bit):
                mascara ^= valor
        palabra = int.from_bytes(salida[off:off+2], 'little') ^ mascara
        salida[off:off+2] = palabra.to_bytes(2, 'little')
        contador = (contador + 1) & 0xffffffff
    return bytes(salida)
