# Validación GUI — adoptar seis estrellas hacia diez

Se realizaron **31 comprobaciones con Tk real en Linux**, con tabla y audio
sintéticos y guardado al juego interceptado. No se ejecutó ningún cliente ni
servidor Windows y todas las escrituras de la aplicación quedaron en `/tmp`.

El origen de seis estrellas es la fila 9052, `bkg2824`, a 290 BPM. Contiene
misiones con grupos de una o dos flechas y misiones de cuatro y ocho SPACE.
El destino es una copia vinculada, fila 9053, `bkg2825`, de diez estrellas y
290 BPM. Los originales protegidos y otra canción no vinculada permanecen
intactos.

La casilla **Aumentar flechas al subir de estrellas** aparece activada por
defecto. La vista previa con destino diez estrellas aumenta 22 grupos y añade
30 flechas: las misiones conservadas pasan de 32 a 62 flechas, con 16 casilleros
de tres. Se mantienen los casilleros SPACE, la ausencia de segunda tanda donde
corresponde, los inicios y los largos de las misiones.

Desactivar la casilla invalida el plan anterior. Al preparar de nuevo se copia
exactamente el contenido de flechas del origen, sin aumentos. Volver a activarla,
preparar y aplicar mantiene el destino con diez estrellas tanto en la fila como
en los controles del panel, y escribe las cantidades aumentadas reales.

Se comprobaron también:

- Configuración con `ajustar_nivel=True` y conservación tras regenerar.
- Edición manual posterior de una misión, que tiene prioridad al regenerar.
- Envío interceptado del chart adaptado y originales sin cambios.
- Recarga de identidad, estrellas, cantidades, configuración y edición manual.
- Mapa con misiones SPACE activas y etiqueta SOLO SPACE.
- Cero errores inesperados o fallos de callbacks de Tk.

Evidencias: `smoke-results.json`, `smoke-log.txt` y tres capturas PNG de la vista
previa con ajuste, la copia exacta desactivada y el mapa del chart adaptado.
