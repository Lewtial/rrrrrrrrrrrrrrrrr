# Estudio LoveRitmo 2020 — mejoras v3

**ADOPTAR VERSIÓN** permite usar el chart que ya ajustaste en otra dificultad
existente de la misma canción. Copia su diseño de misiones, flechas y SPACE,
y limita el tamaño de los grupos según las estrellas y el BPM del destino.
Se conservan el ID y el archivo bkg de cada versión.

## Descargas

- [Actualización pequeña v3](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/estudio/mejoras-v3/actualizacion-v3.zip)
- [Estudio completo v3](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/Estudio_LoveRitmo_2020_mejorado_v3.zip)
- [Versión v2 conservada](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/tree/main/estudio/mejoras-v2)
- [Versión v1 conservada](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/tree/main/estudio/mejoras-v1)
- [ZIP original conservado](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/Estudio_LoveRitmo_2020.zip)

## Actualizar

1. Cierra el Estudio y guarda una copia de su carpeta, incluida tu configuración.
2. Extrae `actualizacion-v3.zip` y copia su carpeta **Crear musica** sobre la tuya.
   Acepta reemplazar los once módulos. Sirve sobre el original, v1 o v2 y conserva
   los audios, herramientas y ajustes del cliente existentes.
3. Abre `ESTUDIO.bat` como siempre.

La actualización pequeña necesita el resto del Estudio original. Si eliges el
paquete completo, extráelo en una carpeta nueva y revisa las rutas de tu cliente
con `CONFIGURAR.bat`.

## Adoptar el chart que ya te gusta

1. Termina de ajustar el origen. Si su mapa tiene cambios pendientes, pulsa allí
   **GENERAR EL CHART** para que el chart real incluya lo que ves.
2. En **Arreglar → Paso 2**, busca la **fila de destino**, por ejemplo la de
   6 estrellas, y pulsa su botón **ADOPTAR VERSIÓN…**.
3. Elige como origen la versión editada, por ejemplo la de 10 estrellas. Solo
   aparecen las otras dificultades con el mismo `Filename`/bkg. Comprueba los IDs.
4. Puedes cambiar manualmente las estrellas del destino antes de preparar.
   Su BPM es el efectivo que hayas elegido para esa fila en el Paso 2.
5. Pulsa **PREPARAR VISTA PREVIA**. Revisa el límite de flechas, los grupos
   reducidos y los ajustes u omisiones necesarios si los BPM son distintos.
6. Pulsa **APLICAR ADOPCIÓN**. Solo se sustituye el chart del destino; el origen
   queda como estaba. Los ajustes previos del destino se reemplazan por esta base.
7. Revisa el mapa y pulsa **ENVIAR AL JUEGO**. Cierra por completo `LoveRitmo.exe`
   y vuelve a abrirlo; reinicia el servidor si ya estaba corriendo.

La adopción queda lista para enviar, sin necesidad de generar otra vez. Al
aplicarla, la casilla **generar** queda seleccionada solo para el destino para
proteger el origen de una regeneración accidental. Puedes activar otras filas
manualmente cuando lo necesites.

## Límites de flechas

El límite se aplica por casillero, a ambas tandas. Cada SPACE continúa siendo
SPACE y cada grupo menor o igual al límite se conserva. Por ejemplo,
`3 · SPACE · 2 · 1` pasa a `2 · SPACE · 2 · 1` con límite de dos.

| Estrellas del destino | BPM | Máximo por casillero |
| --- | --- | --- |
| 1–3 | Cualquier BPM | 2 flechas |
| 4–6 | Hasta 220 inclusive | 3 flechas |
| 4–6 | Más de 220 | 2 flechas |
| 7–8 | Menos de 230 | 3 flechas |
| 7–8 | Desde 230 | 2 flechas |
| 9–10 | Cualquier BPM | 3 flechas |

Para 221–229 BPM se eligió el límite conservador de dos. Estas son reglas de
adopción; las opciones anteriores de generación normal conservan sus propias
referencias. Las estrellas manuales del diálogo determinan el límite al adoptar.

Se limita el tamaño de los grupos; se conservan la cantidad de misiones y la
distribución de SPACE siempre que el BPM permita la misma geometría. No se
redistribuye el chart al azar para hacerlo estadísticamente más fácil.

## Qué ocurre con el BPM

**Mismo BPM:** se conservan literalmente los inicios, largos, segunda tanda,
bolsa de direcciones, baile y cámaras del origen. Se recortan los grupos que
superen el límite del destino.

**BPM distinto:** se toman los tiempos absolutos del origen y se acercan al
compás del destino, anclado al arranque del origen. Se recalculan los largos.
La vista previa muestra desplazamientos, cambios de final y misiones omitidas
porque colisionan, no caben o invaden descansos. Si un destino dura menos de
16 tiempos, se retira su segunda tanda y se informa. Las flechas de cada tanda
pasan a seguir la separación de tiempos del BPM de destino.

Los descansos explícitos y las extensiones vacías se protegen durante la
adaptación. Revisa especialmente las adopciones con BPM muy distintos: pueden
necesitar más ajustes manuales que las versiones que comparten BPM.

## Guardado y edición posterior

La base adoptada se guarda como una instantánea en
`Crear musica/configuracion_secciones.json`. Cambiar después el origen no cambia
el destino automáticamente; puedes volver a adoptarlo cuando quieras.
**GENERAR**, escuchar y abrir el mapa conservan esa base. Las nuevas secciones y
las sustituciones de misiones se aplican encima; puedes editar un grupo
manualmente después de adoptar.

El modo adoptado conserva el diseño elegido. Los ajustes automáticos de sorteo,
distribución musical y menos SPACE corresponden a la generación normal. Los
controles manuales de SPACE, invertir, suave, repeticiones y nuevos descansos sí
se aplican sobre la base. Las marcas antiguas compartidas por la canción se
limpian al adoptar para que no vuelvan a modificar el resultado revisado.

**Deshacer/Rehacer** del mapa restaura los charts, estrellas y configuración de
adopción. **Quitar adopción** vuelve a la generación normal: el chart actual se
conserva hasta pulsar GENERAR. Las ediciones manuales posteriores se mantienen;
revísalas si cambias de cuadrícula.

La configuración v3 lee archivos v1/v2. Para volver a un programa anterior usa
la copia de carpeta que guardaste antes de actualizar, incluida su configuración.
Las funciones de copiar una misión, editar casilleros, BPM x1–x4 y descansos de
las versiones anteriores siguen incluidas.

## Validación

- 236 pruebas automatizadas, incluidas 16 del nuevo diálogo con Tk real.
- 43 comprobaciones completas de interfaz en Linux: cancelar, vista previa,
  datos modificados después de preparar, adopción, límites, SPACE, BPM distintos,
  descansos, envío interceptado, regeneración, recarga y deshacer/rehacer.
- Adopción real entre las filas 2558 (10 estrellas) y 2557 (6 estrellas), a
  256 BPM, sobre una copia temporal de la tabla: se redujeron 126 grupos.
  Tras escribir el SPAK y leerlo de nuevo, coincidieron sus 836 filas × 23 campos.
- ZIP original y versiones v1/v2 conservados; los demás archivos originales y
  ejecutables no se modificaron.

Las pruebas de interfaz usaron audio/tablas sintéticos y guardado interceptado.
La prueba SPAK escribió únicamente copias temporales. Falta probar dentro de tu
cliente y servidor Windows. Informes y capturas: `validacion/`.

Desde **Crear musica** de una instalación completa puedes ejecutar:

```bash
python -m unittest discover -s tests -v
```
