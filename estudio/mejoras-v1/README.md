# Estudio LoveRitmo 2020 — mejoras v1

Esta versión permite configurar el contenido de cada tramo, multiplicar el BPM
del chart hasta x4 y escoger descansos sin misiones. El ZIP original se conserva
en la raíz del repositorio.

## Descargas

- [Actualización pequeña para tu Estudio actual](actualizacion-v1.zip?raw=true)
- [Estudio completo actualizado](../../Estudio_LoveRitmo_2020_mejorado_v1.zip?raw=true)
- [ZIP original conservado](../../Estudio_LoveRitmo_2020.zip?raw=true)

## Actualizar tu copia actual

1. Cierra el Estudio.
2. Guarda una copia de tu carpeta `Estudio_LoveRitmo_2020`.
3. Extrae `actualizacion-v1.zip`. Copia su carpeta `Crear musica` sobre la carpeta
   `Crear musica` de tu Estudio y acepta reemplazar los archivos de código.
4. Abre `ESTUDIO.bat` como siempre.

La actualización contiene seis módulos y las pruebas. Conserva tus audios,
configuración del cliente, canciones, tablas, respaldos y herramientas existentes.
Necesita los demás archivos del Estudio original; no se ejecuta por separado.
Para usar el paquete completo, extráelo en una carpeta nueva y abre `ESTUDIO.bat`.
Si cambiaste las ubicaciones del programa o del juego, revísalas con `CONFIGURAR.bat`.

## Elegir flechas y SPACE por sección

1. Selecciona tu canción y dificultad. En **Arreglar**, abre **ABRIR EL MAPA**.
2. Pulsa **Secciones: flechas, SPACE y descansos...**, arriba del mapa.
3. Escribe el inicio y el final del tramo: segundos (`12,5`) o minutos (`1:02,500`).
   El inicio se incluye y el final queda fuera del tramo.
4. Escoge un perfil: Normales, Dobles, Triples, Seguidas, Repeticiones, Solo SPACE
   o Personalizado. Ajusta los cuatro casilleros con SPACE, 1, 2 o 3 flechas.
5. Activa **Segunda tanda** si quieres otros cuatro casilleros. Una misión de
   menos de 16 tiempos requiere dejarla desactivada.
6. Usa **Agregar sección** para crear más tramos. Para editar, selecciona uno
   en la tabla; para borrarlo, **Quitar selección**. **Aplicar al mapa** también
   recoge la edición que tengas pendiente en el formulario.
7. Elige si quieres aplicar la configuración a las otras dificultades. Por
   defecto se guarda solo para la dificultad que abriste.
8. Revisa la vista previa, pulsa **GENERAR EL CHART** y luego **ENVIAR AL JUEGO**.

Los perfiles fijan cantidades y casilleros; el juego sortea las direcciones.
Un casillero SPACE muestra la barra espaciadora. El perfil Repeticiones cambia
la bolsa de direcciones. Las secciones con patrones se reconocen en lila.
Si dos patrones se superponen, manda el último de la tabla. Los descansos
tienen prioridad sobre todos los patrones.

## BPM hasta x4

En **Arreglar → Paso 2**, cada dificultad tiene selector **x1, x2, x3 o x4** y
su BPM efectivo debajo. El multiplicador cambia la cuadrícula y la cantidad de
misiones del chart; el audio conserva su duración y velocidad.
**¿Qué BPM poner?** compara las cuatro opciones. **Aplicar a la difícil** solo
cambia esa fila; sus estrellas y las otras dificultades se conservan.
Después se aplica con **GENERAR EL CHART** y **ENVIAR AL JUEGO**.

## Descansos sin misiones

En el editor de secciones elige el perfil **Descanso** y escribe los límites.
También puedes usar **Descanso sin misiones** en la barra del mapa y hacer clic
en una misión. Otro clic dentro del descanso lo devuelve.

El descanso quita las misiones cuya ventana de entrada se cruza con el tramo:
no salen flechas ni SPACE dentro de él. Cuando un límite corta una ventana,
se retira la misión entera y el silencio puede extenderse hasta su borde.
El audio sigue sonando, las misiones que quedan conservan sus tiempos y los
descansos largos no reintroducen misiones intermedias. Si el descanso está al
inicio, la primera misión se retrasa. Debe quedar al menos una misión.

**Solo SPACE** sirve para tocar la barra sin flechas; **Descanso** quita también
la barra. Los controles antiguos de “En lo quitado” siguen aplicándose a las
marcas antiguas. Las nuevas secciones de descanso siempre quedan sin misiones.

Las preferencias se guardan automáticamente por canción y dificultad en
`Crear musica/configuracion_secciones.json`, incluido el arranque de origen.
Deshacer/rehacer actualiza estas preferencias. Al duplicar una canción se
copian a las nuevas filas. Cancelar el diálogo conserva la configuración previa.

## Validación

- 71 pruebas automatizadas de lógica, persistencia, copia, BPM y formularios.
- 53 comprobaciones de interfaz Tk en Linux con audio sintético, cuadrícula
  controlada y generación WAV real; dos errores deliberados también comprobados.
- 48 generaciones sin nuevas secciones comparadas con el núcleo original.
- 100 charts existentes comprobados para conservar tiempos y duración al
  retirar misiones.

El editor y su vista previa se probaron en Linux. Falta comprobar el resultado
con tu juego y servidor en Windows. Las pruebas no escribieron al juego.

Los resultados y capturas están en [validacion](validacion/VALIDACION_GUI.md).
Para ejecutar las pruebas desde `Crear musica` de una instalación completa:

```bash
python -m unittest discover -s tests -v
```

Los archivos de `codigo/Crear musica` son los seis módulos modificados y sus
pruebas; el resto del programa se conserva en el ZIP completo y en el original.
