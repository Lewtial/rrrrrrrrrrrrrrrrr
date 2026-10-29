# musictable.PAK — desempaquetado v1

Se extrajeron las 30 entradas del QPACK y se descifraron sus tablas SLK.
El archivo original se conserva sin cambios.

- `csv/`: 30 tablas en CSV UTF-8 con BOM, separadas por punto y coma. Son la
  opción recomendada para leer los títulos coreanos en Excel o LibreOffice.
- `slk/`: 30 tablas SYLK descifradas en su codificación original coreana cp949;
  conservan formato, posiciones de celdas y relleno final.
- `extraidos_originales/`: los 30 contenidos extraídos literalmente del PAK,
  todavía cifrados, con sus nombres originales.
- `original/musictable.PAK`: copia intacta del archivo recibido.
- `indice.csv`: lista de archivos, posiciones, tamaños, filas y hashes.
- `manifiesto.json` y `SHA256SUMS.txt`: verificación de integridad.
- `herramientas/`: extractor reproducible en Python 3, sin dependencias externas.

Hay 29 listas musicales con columnas ID, Index, Title, Singer y Difficulty,
además de extramusictableinfo.slk con 13 filas de metadatos. Las listas contienen
460 registros musicales en total; un mismo tema puede aparecer en varias listas.

Comprobaciones realizadas: índices dentro de límites, archivos contiguos sin
solapamientos, reconstrucción del PAK idéntica al original, 30 recifrados idénticos,
30 SLK completos y conversión de las 2515 celdas a CSV sin pérdidas. No se ejecutó
el juego ni se modificó el archivo recibido.

Para repetir la extracción desde esta carpeta:

```bash
python herramientas/desempaquetar_qpack.py original/musictable.PAK salida_nueva
```

La carpeta de destino debe ser nueva. La herramienta soporta esta variante
QPACK 1.0; no es un desempaquetador universal para cualquier archivo .PAK.

SHA-256 del original:
431eadb575c1c97ada91ab6eb06221d95631bc7820201b61a9bcfdce6b2cf16b
