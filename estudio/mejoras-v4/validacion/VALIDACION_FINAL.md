# Validación de la clasificación visual de SPACE

48 comprobaciones aprobadas con Tk real en Linux. El arnés usa tablas, audio y
cuadrícula sintéticos; intercepta el guardado al juego y bloquea ejecutables de
Windows. Todas las escrituras quedan dentro de `/tmp`.

La reproducción anterior, usando el módulo `estudio.py` conservado en v3, mostraba
una misión con 0 flechas y 4 SPACE en gris y con la etiqueta «callada». Los cuatro
SPACE existían en los datos. Las capturas `space-adoptado-antes.png` y
`space-adoptado-recargado-antes.png` conservan esa evidencia.

Con el módulo corregido, se comprobó adoptar una dificultad, abrir el mapa,
regenerar, enviar a la tabla simulada y volver a cargarla. Las misiones de cuatro
y ocho SPACE se ven turquesas y llevan la etiqueta SOLO SPACE en la cabecera,
al pasar el puntero y durante la reproducción. La segunda tanda sigue contando
como entrada activa. Los datos y tiempos se conservan.

También se creó un descanso explícito entre 12 y 13 segundos: la misión de ese
intervalo se retira, no quedan entradas y el puntero indica DESCANSO SIN MISIONES.
La misión SPACE vecina continúa activa. Si tiene una cola larga, el texto aclara
que el personaje camina después de teclear.

Capturas posteriores:

- `space-adoptado-despues.png`
- `space-y-descanso-real-despues.png`
- `space-adoptado-recargado-despues.png`

`smoke-results.json` registra las 48 comprobaciones y `smoke-log.txt` su ejecución.
No hubo errores imprevistos ni fallos de callbacks Tk. El juego y servidor Windows
no se ejecutaron.
