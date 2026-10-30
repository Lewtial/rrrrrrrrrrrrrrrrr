# Estudio LoveRitmo 2020 — mejoras v2

Ahora puedes editar las misiones existentes desde una lista completa, tomar una
misión que te guste y copiar su contenido sobre otra. Se conservan el inicio y
la duración de la misión de destino. Esta versión incluye las mejoras v1 de
flechas y SPACE por tramo, BPM x1–x4 y descansos.

## Descargas

- [Actualización pequeña v2](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/estudio/mejoras-v2/actualizacion-v2.zip)
- [Estudio completo v2](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/Estudio_LoveRitmo_2020_mejorado_v2.zip)
- [Versión v1 conservada](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/tree/main/estudio/mejoras-v1)
- [ZIP original conservado](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/Estudio_LoveRitmo_2020.zip)

## Instalar

1. Cierra el Estudio y guarda una copia de tu carpeta actual.
2. Extrae `actualizacion-v2.zip` y copia su carpeta `Crear musica` sobre la de tu
   Estudio. Acepta reemplazar los ocho módulos de código.
3. Abre `ESTUDIO.bat` como siempre. La actualización sirve tanto sobre el ZIP
   original como sobre v1; conserva los audios y la configuración existente.

La actualización pequeña necesita los demás archivos del programa original.
Si eliges el paquete completo, extráelo en una carpeta nueva y abre `ESTUDIO.bat`.
Revisa tus rutas con `CONFIGURAR.bat` si la instalación cambió de ubicación.

## Tomar una misión y ponerla en otra

1. Selecciona la canción y la dificultad. En **Arreglar**, abre **ABRIR EL MAPA**.
2. Pulsa **Secciones: flechas, SPACE y descansos...**. Ahora se abre la lista de
   todas las misiones actuales, con su número, inicio, largo, tandas y bolsa.
3. Comprueba el ID, nombre de archivo y estrellas que aparecen arriba. Dos
   canciones pueden tener el mismo título.
4. Selecciona la misión de origen y pulsa **TOMAR MISIÓN**.
5. Selecciona otra misión y pulsa **PONER EN ESTA MISIÓN**.
6. Revisa el mapa y pulsa **ENVIAR AL JUEGO**. La edición ya queda en la fila que
   se envía; si usas **GENERAR EL CHART**, se vuelve a aplicar la copia guardada.
7. Cierra por completo `LoveRitmo.exe` y vuelve a abrirlo para probar. Reinicia
   también el servidor si ya estaba abierto.

La copia sustituye las cantidades de flechas y SPACE de los cuatro casilleros,
la segunda tanda si existe y la bolsa de direcciones. El juego sigue sorteando
las direcciones concretas. No copia el baile, la cámara, el inicio ni la duración;
tampoco modifica la misión de origen ni la otra dificultad.

Puedes reutilizar la misma misión tomada en varios destinos. El portapapeles dura
mientras esa ventana permanece abierta. Los cambios aplicados sí se guardan por
canción y dificultad en `Crear musica/configuracion_secciones.json`.

## Editar una misión directamente

Selecciona una fila, ajusta los cuatro casilleros de **Primera tanda**, activa
**Segunda tanda** si corresponde y pulsa **APLICAR EDICIÓN**. Cada casillero admite
SPACE o de una a tres flechas. La bolsa 1 favorece repeticiones de una dirección;
la bolsa 4 es la normal. Una segunda tanda requiere un destino de al menos 16
tiempos: si el destino es más corto, se muestra el motivo y se conserva su largo.

**Deshacer** y **Rehacer** del mapa restauran tanto la configuración como las
filas reales listas para enviar. Si deshaces después de enviar, el cambio vuelve
a quedar pendiente de envío.

Crear misiones nuevas queda pendiente para otra versión. Esta entrega permite
editar y sustituir las existentes, como se acordó.

## Secciones, descansos y BPM

Desde la lista puedes abrir **EDITAR SECCIONES POR TRAMO** para configurar varias
misiones por tiempo. Se conservan las opciones de v1, incluido BPM hasta x4.
Los patrones de misión guardados se aplican después de los patrones por tramo;
los descansos tienen prioridad. Una copia cubierta por un descanso queda
inactiva y se recupera al quitar ese descanso y regenerar.

Al editar un tramo, el resultado queda en las filas reales que se envían.
La casilla para aplicar a ambas dificultades se respeta también al marcar un
descanso en la barra del mapa; las demás preferencias de cada dificultad se
conservan.

Al enviar, el Estudio hace un respaldo fechado, escribe el SPAK y vuelve a leerlo
para comparar todas sus filas y campos con lo esperado. Si no coinciden, restaura
la tabla anterior y mantiene los cambios pendientes.

## Validación

- 155 pruebas automatizadas de patrones, copia, persistencia, BPM, descansos,
  ámbito por dificultad, guardado, verificación y restauración ante fallos.
- 24 comprobaciones con la interfaz Tk real en Linux: edición, tomar/poner,
  tiempos, deshacer/rehacer, regeneración, recarga y entrega del chart al guardado.
  Esa prueba usa audio y tabla sintéticos, y el envío al juego está interceptado.
- Escritura y lectura reales de un SPAK de prueba: 836 filas y 23 columnas
  coincidieron, con respaldo idéntico. Se usaron copias temporales y se comprobaron
  los hashes originales.
- ZIP original, v1 y todos los archivos originales sin cambios de código
  conservados. Los ejecutables originales no se modificaron ni ejecutaron.

Falta comprobar el comportamiento dentro de tu cliente y servidor en Windows.
Las capturas e informes están en `validacion/`. Para ejecutar las pruebas desde
`Crear musica` de una instalación completa:

```bash
python -m unittest discover -s tests -v
```
