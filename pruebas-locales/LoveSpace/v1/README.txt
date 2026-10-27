LoveSpace - tabla de prueba local v1
==================================

Preparada para el LoveRitmo.exe aportado, SHA-256:
2ff8f56e06b3c358bfa2f0ba0aa3e79d74386dde1e38eb3f9cef38225e49c0cd

Contenido:
- LoveSpace_local_test_v1.CT: tabla nueva con dos entradas independientes.
- LoveSpace_original.CT: copia intacta de la tabla recibida.
- patch_manifest.json: offsets, instrucciones y bytes de ambos estados.
- validation.json: resultados de las comprobaciones estaticas y resumen.
- emulation-tests.json: resultados de emulacion aislada de CPU.
- SHA256SUMS.txt: hashes de los archivos de este paquete.

Uso en tu servidor local:
1. Abre el cliente que utiliza ese EXE y conectalo a tu servidor local.
2. En Cheat Engine selecciona manualmente el proceso LoveRitmo.exe.
3. Abre LoveSpace_local_test_v1.CT. Las dos entradas empiezan desactivadas.
4. Para la ruta Audition/Espacio, prueba primero solo la primera entrada.
   La segunda corresponde al controlador base compartido por Classic,
   Ladder, Meeting y derivados; pruebala por separado en esos modos.
5. Compara aciertos centrales, intermedios y fallos con la entrada
   desactivada y activada. Los intermedios pasan a (4000,6,8).
   Los umbrales temporales y el bloque cero/fallo permanecen intactos.
6. Desactiva la entrada para restaurar los bytes originales.

Comprobaciones de estado:
Cada entrada comprueba las nueve instrucciones originales completas
antes de activar, y el estado parcheado antes de restaurar. Un error
de assert indica que los bytes del proceso no coinciden con el estado
esperado; no se debe eliminar esa comprobacion para forzar la escritura.

Alcance de la validacion:
Se verificaron los offsets, instrucciones, activacion y restauracion
contra el EXE recibido. Tambien pasaron 36 combinaciones por entrada
en emulacion aislada de CPU (72 casos en total), comparando resultados
originales, parcheados y restaurados. Los aciertos intermedios cambian
a WOW; el resultado central y los fallos permanecen intactos.
Consulta validation.json y emulation-tests.json para los detalles.
No se probo Cheat Engine con el juego y el servidor real en Windows.
No se ejecuto ni se modifico el EXE original.

Para comprobar despues la correccion del servidor, repite los mismos
casos y verifica que valide los juicios y puntuaciones frente al tiempo
de cada nota, en vez de confiar unicamente en el resultado del cliente.
