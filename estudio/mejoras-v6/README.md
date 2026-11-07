# Estudio LoveRitmo 2020 — mejoras v6

**Adoptar versión ahora puede aumentar las flechas al subir de estrellas.**
Por ejemplo, al llevar un chart de seis a diez estrellas, aumenta una parte de
los grupos de una y dos flechas, incluidos grupos triples cuando el BPM y el
nivel lo permiten. Conserva los casilleros SPACE y el diseño de tus misiones.

## Descargas

- [Actualización pequeña v6](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/estudio/mejoras-v6/actualizacion-v6.zip)
- [Estudio completo v6](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/Estudio_LoveRitmo_2020_mejorado_v6.zip)
- [Versión v5 conservada](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/tree/main/estudio/mejoras-v5)

## Actualizar y volver a adaptar una versión de seis a diez

1. Cierra el Estudio y guarda una copia de su carpeta.
2. Extrae `actualizacion-v6.zip`. Copia **Crear musica** sobre tu carpeta actual,
   reemplazando los archivos de código y conservando tu configuración existente.
   Mantén `copias.json`, `mias.json` y `configuracion_secciones.json`.
3. Abre el Estudio y selecciona la **versión de destino** que quieres dejar en
   diez estrellas. En **Arreglar → Paso 2**, pulsa **ADOPTAR VERSIÓN…**.
4. Elige el origen de **6 estrellas** y escribe **10** en **Estrellas del destino**.
5. Deja marcada **Aumentar flechas al subir de estrellas**. Está activa por defecto.
6. Pulsa **PREPARAR VISTA PREVIA**. Verás cuántos grupos aumentaron, cuántas flechas
   se añadieron y los totales de flechas y triples antes y después.
7. Pulsa **APLICAR ADOPCIÓN** y **ENVIAR AL JUEGO**. Cierra completamente el cliente
   y vuelve a abrirlo para probar; reinicia el servidor si ya estaba abierto.

**Si ya habías hecho esta adopción con v5, vuelve a aplicarla con la casilla
activa.** Las adopciones anteriores se conservan tal como estaban hasta que
elijas activar el ajuste en una nueva adopción. Así se respetan los charts que
ya habías terminado.

## Cómo suben las flechas

La opción actúa cuando el destino tiene más estrellas que el origen. Ajusta
el tamaño de los grupos que ya contienen flechas, siguiendo las distribuciones
medidas del nivel de destino. La primera y segunda tanda usan sus propias
referencias. El reparto es estable: repetir GENERAR conserva el resultado.

- Un casillero con SPACE permanece SPACE en su posición.
- Las misiones de cuatro u ocho SPACE continúan completas y activas.
- Se mantienen las tandas existentes y la ausencia de segunda tanda.
- Los descansos y la geometría de las misiones se conservan con el mismo BPM;
  con BPM distintos se mantiene la adaptación temporal de las versiones anteriores.
- Al subir, los grupos que ya alcanzan el límite se conservan. Los demás aumentan
  selectivamente; se mantiene variedad entre grupos de una, dos y tres flechas.
- Los topes por estrellas y BPM siguen vigentes: seis estrellas a 290 BPM admite
  hasta dos flechas por grupo; diez estrellas a ese BPM admite hasta tres.

Si la fuente solo tiene SPACE o todos los grupos ya alcanzan el límite permitido,
la vista previa explica por qué no hay grupos que aumentar. La adaptación
conserva las posiciones de SPACE que elegiste; no crea misiones ni tandas nuevas.

Al bajar de diez a seis estrellas se sigue aplicando el límite del destino.
Desmarcar la nueva casilla conserva las cantidades del origen hasta ese límite,
como en las versiones anteriores.

## Guardado y edición posterior

El destino guarda su número real de estrellas y las nuevas cantidades de flechas.
La opción se conserva en la instantánea de adopción. Generar, escuchar y recargar
mantienen el diseño adaptado. Una edición manual posterior de una misión tiene
prioridad sobre el aumento automático.

La configuración continúa usando el formato v3. Los charts adoptados antes de v6
se leen sin activar esta opción automáticamente. La copia y el original siguen
vinculados por `copias.json`; cada destino conserva su ID y bkg.

La actualización pequeña incluye los doce módulos acumulados y sus pruebas.
Si utilizas el Estudio completo en una carpeta nueva, conserva también la
configuración de tu instalación anterior y revisa las rutas con `CONFIGURAR.bat`.

## Validación

319 pruebas aprobadas y 31 comprobaciones con Tk real en
Linux. En el caso de interfaz, el chart de seis estrellas pasó de 32 a 62 flechas,
con 16 casilleros triples, conservando SPACE, tiempos, largos y el origen.
Se comprobó que el destino queda en diez estrellas, que desactivar la opción
restaura la copia de cantidades y que generar, enviar y recargar conservan el
resultado y las ediciones manuales posteriores.

Los datos y el audio de la prueba GUI son sintéticos y el envío fue interceptado.
No se ejecutaron el cliente ni el servidor Windows. Informes y capturas:
`validacion/`. El ZIP original y las versiones v1–v5 se conservan.

Desde **Crear musica** de una instalación completa:

```bash
python -m unittest discover -s tests -v
```
