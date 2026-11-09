# Validación de Onda v1

## Comprobado

- Python 3.12.14, FFmpeg 7.1.5 y dependencias instaladas en un entorno virtual
  independiente. `pip check` no detecta conflictos.
- **30 pruebas de backend aprobadas**, con codificación real a WAV de 16/24 bits,
  MP3, FLAC, OGG Vorbis y AAC; frecuencias, normalización, ZIP y resultados
  parciales comprobados.
- Protección de URLs y redirecciones, UUID y rutas de descarga, rechazo de
  vistas previas, acceso de FFmpeg limitado a archivos locales, límites de carga
  antes del parser y cierre de archivos temporales comprobados.
- Estado persistido sin URLs firmadas de SoundCloud; tratamiento de reinicios y
  limpieza de trabajos caducados comprobados. Hay limpieza periódica cada minuto.
- Comprobación de Chromium con **7 escenarios aprobados**, sin errores de
  JavaScript. Se subieron dos MP3 reales, se convirtieron a WAV estéreo de 24 bits
  y 48 kHz con normalización y se analizaron los archivos descargados con FFprobe.
- Descarga individual, ZIP de dos pistas, historial tras recargar, rechazo de URL
  ajena a SoundCloud, acordeón de preguntas y vista móvil de 390 px comprobados.
- El servidor se detuvo y reinició con los comandos documentados; la prueba de
  navegador final se ejecutó contra la versión actual del backend y frontend.

El [informe del navegador](browser-report.json) detalla sus comprobaciones.
La [captura de pantalla](preview-desktop.png) procede del navegador real.

## Pendiente por acceso externo

- La política del entorno devuelve 403 al conectar con Songverter y SoundCloud.
  La prueba con un enlace público de SoundCloud finalizó como fallo y devolvió
  un mensaje seguro en español. **No se ha verificado una descarga real de
  SoundCloud ni de una playlist.**
- El extractor puede ocultar el motivo de transporte al no obtener el
  identificador público de cliente; la interfaz muestra un error general de
  descarga. Este fallo no se presenta como conversión correcta.
- Se guardaron los dominios necesarios en un borrador de configuración. Ese
  borrador no se ha aplicado ni publicado en esta comprobación. Tras habilitar
  el acceso hay que repetir una descarga real y revisar la referencia visual.
- No fue posible inspeccionar Songverter. El diseño de Onda es independiente y
  no se afirma igualdad visual ni paridad exhaustiva con esa web.

## No ejecutado

- Construcción de la imagen Docker y despliegue en un alojamiento público.
- Pruebas de carga prolongada o con archivos de varias horas.

El servidor de desarrollo está preparado; todavía no hay una URL pública
desplegada de esta aplicación.
