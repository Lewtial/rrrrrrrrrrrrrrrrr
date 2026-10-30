# Validación v2

Las pruebas unitarias incluyen los casos de copia, regeneración, persistencia y
restauración ante errores. El informe GUI registra 24 comprobaciones con widgets
Tk reales y sus capturas. En esa prueba el guardado fue interceptado; no escribió
al cliente ni al servidor.

Los dos informes SPAK registran por separado la importación, exportación y
verificación real de 836 filas × 23 campos sobre copias temporales de una tabla.
Las rutas de esos informes son evidencias del entorno de prueba, no instrucciones
para configurar tu instalación. El ejecutable se leyó para el cifrado; no se abrió.
La prueba dentro del juego y servidor Windows queda pendiente.
