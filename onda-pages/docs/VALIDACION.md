# Validación · Onda para GitHub Pages

## Comprobado en Chromium

Se ejecutaron siete escenarios con audio real generado para las pruebas:

1. Página española y recursos relativos bajo una ruta de proyecto.
2. Conversión de dos MP3 mono de 22,05 kHz a WAV PCM de 24 bits, estéreo y
   48 kHz, con la conexión del navegador desactivada después de cargar la web.
3. Descargas WAV y ZIP con nombres UTF-8, CRC válido y las dos pistas correctas.
   No hubo peticiones HTTP durante la conversión ni se subió audio.
4. Recuperación de los WAV reales desde IndexedDB tras recargar y nueva
   descarga con contenido válido.
5. Borrado del historial y presentación móvil de 390 px sin desbordamiento.
6. El HTML único generó el ejemplo, lo convirtió a WAV de 16 bits y 44,1 kHz y
   permitió descargarlo estando sin conexión, sin recursos adicionales.
7. Un archivo corrupto produjo un error por pista; el archivo válido de su lote
   se convirtió y pudo descargarse.

No hubo errores de JavaScript. Python `wave` comprobó las cabeceras RIFF, tamaño,
bits, frecuencia y canales. Se midieron picos de **−1,00000 dBFS** en los WAV
normalizados. `zipfile` comprobó la integridad y el audio dentro del ZIP.

El motor también se probó con cancelación del worker, nombres duplicados en ZIP
y límite de espacio de salida. La revisión del código confirmó que no utiliza
API, servicios remotos, cargas de archivos ni bibliotecas alojadas en un CDN.

El [informe del navegador](browser-report.json) y la
[captura de pantalla](preview-desktop.png) corresponden a esta versión.

## Límites de la comprobación

- El navegador administrado bloqueó `file://` antes de ejecutar JavaScript
  (`ERR_BLOCKED_BY_ADMINISTRATOR`). No se modificó esa política. El mismo HTML
  se cargó por HTTP y se probó después sin conexión. Abrir un HTML directamente
  depende de que el navegador permita archivos locales; no se marcó como
  verificado en este entorno.
- No se probaron Safari, Firefox, dispositivos móviles reales ni archivos de
  larga duración. Los formatos de entrada dependen del decodificador del
  navegador; la salida de esta edición es exclusivamente WAV.
- No incluye descargas desde SoundCloud. La edición con servidor se conserva
  en una carpeta independiente.
- La rama de publicación preparada no habilita por sí sola GitHub Pages. La
  activación y la URL pública deben comprobarse en Settings → Pages de GitHub.
