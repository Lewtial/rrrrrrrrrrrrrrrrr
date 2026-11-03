# Validación de interfaz — adoptar versión

43 comprobaciones aprobadas con Tk real en Linux, usando `DISPLAY=:90`.
La tabla, el audio y la cuadrícula son sintéticos. El guardado al juego está
interceptado: se comprueban las filas que recibe, sin escribir al cliente ni al
servidor. Las escrituras se restringieron a `/tmp`; los ejecutables de Windows
quedaron bloqueados por el arnés.

Se verificaron selección por ID/bkg, cancelación, vista previa sin modificaciones,
rechazo de una fuente cambiada después de revisar, niveles manuales, adopción con
BPM iguales, límites de flechas, casilleros SPACE, persistencia, envío del chart,
regeneración y reapertura del mapa/editor. También adaptación 240→120 BPM,
misiones conservadas y segundas tandas retiradas, descanso 16–24 s sin entradas,
y deshacer/rehacer con actualización de las estrellas y las filas reales.

Dos errores deliberados se mostraron y verificaron: fuente modificada tras la
vista previa y repetición de origen todavía sin generar. No hubo mensajes de
error imprevistos ni excepciones de callbacks Tk.

Las regresiones finales cubren las marcas antiguas de repetición, SPACE,
inversión, suavizado, silencios y frases: se limpian al adoptar y no vuelven a
alterar el resultado al regenerar. Después de GENERAR, un mapa de origen con
repeticiones queda sincronizado y se puede adoptar sin cerrarlo.

Capturas:

- `adoptar-mismo-bpm-vista-previa.png`: vista previa a 900×560, aplicar visible.
- `adoptar-distinto-bpm-vista-previa.png`: aviso y resumen de adaptación del BPM.
- `adoptar-editor-destino.png`: misiones efectivamente copiadas y limitadas.

Además se inspeccionó el diálogo mínimo 760×520: las etiquetas ajustan sus líneas
al ancho disponible y los controles principales permanecen dentro de la ventana.

El cliente y servidor Windows quedan pendientes de prueba por el usuario.
