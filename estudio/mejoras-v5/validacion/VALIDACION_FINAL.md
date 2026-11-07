# Validación GUI — adopción entre original y copia registrada

Se realizaron **37 comprobaciones con Tk real en Linux**, usando audio y tabla
sintéticos y guardado al juego interceptado. No se ejecutó ningún EXE Windows.

El caso reproduce las identidades de la captura del usuario:

- Original 4152: 4 estrellas, 145 BPM, `bkg10213`.
- Original 4153: 10 estrellas, 290 BPM, `bkg10213`.
- Copia 9052: 6 estrellas, 290 BPM, `bkg2824`, única fila de ese bkg.
- Registro de copia: `9052 → 4153` en `copias.json`.
- Otra grabación no vinculada, también llamada Trapped, ID 9990 y `bkg9999`.

La copia puede abrir ADOPTAR VERSIÓN. Se ofrecen las dos dificultades originales
con ID y bkg visibles; se selecciona por defecto la de diez estrellas. La
canción no vinculada queda fuera de la lista. Los botones del original protegido
permanecen deshabilitados.

Preparar no cambia filas. Aplicar mantiene el ID 9052 y su `bkg2824`, conserva
los inicios y largos del chart de 4153, limita los grupos a dos flechas para seis
estrellas a 290 BPM y conserva los SPACE de ambas tandas. Solo la copia queda
pendiente de envío. Las filas de los originales y de la grabación ajena conservan
todos sus campos.

Generar y recargar conservan la adopción. El envío interceptado recibe la copia
ajustada y los originales sin cambios; la configuración se recupera tras volver
a abrir el programa. El mapa muestra como activas las misiones de cuatro y ocho
SPACE. No hubo errores inesperados ni fallos de callbacks.

Evidencias: `smoke-results.json`, `smoke-log.txt` y tres capturas PNG. Las rutas
`/tmp` de los informes corresponden al entorno de pruebas.
