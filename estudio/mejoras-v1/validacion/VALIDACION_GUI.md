# Validación GUI final

Resultado: **53 comprobaciones correctas**, **0 errores inesperados**, **2 errores esperados**.

Ejecución: `DISPLAY=:90 PYTHONDONTWRITEBYTECODE=1 python3 /tmp/estudio-gui/run_smoke.py`

La aplicación Tk, el motor de charts y la generación WAV con ffmpeg Linux se ejecutaron de verdad. La tabla y la rejilla usan dos versiones de una canción fixture con audio sintético propio. Solo la reproducción se intercepta. Una auditoría bloquea escrituras fuera de `/tmp` y procesos Windows; guardar en el juego está prohibido en la fixture.

Cobertura: BPM x1–x4 y BPM actual no múltiplo; aplicar solo a dificultad mayor y conservar estrellas; contenido manual SPACE/1/2/3, segunda tanda y bolsa de direcciones; descanso intermedio e inicial; tiempos reales del mapa, marcadores y audio; editar, cancelar y reintentar; persistencia por dificultad; cerrar/reabrir; deshacer/rehacer; regenerar; vista compacta de 900×560.

Regresiones finales verificadas:

- Un descanso que elimina todas las misiones produce el error esperado, conserva diálogo y formulario, y deja filas, preferencias y preview intactos.
- Tras recargar la tabla generada y vaciar la caché de preferencias, quitar un descanso devuelve la misión original y mantiene el patrón manual.
- Cambiar de canción cierra el mapa anterior y activa únicamente las filas de la nueva canción.
- Si la primera versión genera un resultado válido y la segunda falla, ninguna fila cambia. Preferencias y estado de pendientes se conservan.

Errores esperados: «Los descansos eliminan todas las misiones» y una excepción ValueError deliberada en la segunda versión para comprobar la aplicación atómica. Están separados en `expected_messages` del JSON; `messages` está vacío.

Artefactos principales:

- `smoke-results.json`: resultado completo y comprobaciones.
- `secciones-editor.png`: editor de patrones y descansos.
- `mapa-secciones-descanso.png`: vista previa con cuatro misiones.
- `mapa-descanso-eliminado-tras-recarga.png`: misión restaurada tras recarga.
- `secciones-error-preserva-formulario.png`: formulario conservado tras error esperado.
- `estudio-minimum-900-step2.png`: BPM y consejos visibles en ventana mínima.
- `bpm-x1-x4.png`: comparador de velocidades.
- `estudio-generado.png`: generación completada sin envío.
