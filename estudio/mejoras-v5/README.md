# Estudio LoveRitmo 2020 — mejoras v5

Ahora **ADOPTAR VERSIÓN** reconoce también el original de una copia creada por
el Estudio, aunque cada una use su propio bkg. La copia conserva su ID y archivo
de audio y puede tomar el chart de la versión original de diez estrellas,
adaptándolo al nivel y BPM del destino.

## Descargas

- [Actualización pequeña v5](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/estudio/mejoras-v5/actualizacion-v5.zip)
- [Estudio completo v5](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/Estudio_LoveRitmo_2020_mejorado_v5.zip)
- [Versión v4 conservada](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/tree/main/estudio/mejoras-v4)
- [Reglas de adaptación por estrellas y BPM](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/blob/main/estudio/mejoras-v3/README.md)

## Actualizar tu instalación actual

1. Cierra el Estudio y guarda una copia de su carpeta.
2. Extrae `actualizacion-v5.zip`. Copia **Crear musica** sobre tu carpeta actual,
   reemplazando los archivos de código.
3. Conserva **copias.json**, **mias.json** y **configuracion_secciones.json** de
   tu instalación. El ZIP pequeño contiene los doce módulos y sus pruebas y
   deja esos archivos de configuración existentes en su lugar.
4. Abre `ESTUDIO.bat` y selecciona la copia que quieres adaptar.

Si usas el ZIP completo en una carpeta nueva, lleva también la configuración de
la instalación que ya utilizabas, en particular `copias.json`: contiene el
vínculo entre tus copias y sus originales. Revisa las rutas con `CONFIGURAR.bat`.

## Caso de las capturas: Trapped, diez estrellas → copia de seis

1. Selecciona **Trapped (copia), fila 9052**, que usa `bkg2824`.
2. En **Arreglar → Paso 2**, pulsa su botón **ADOPTAR VERSIÓN…**.
3. Elige **10 estrellas · 290 BPM · ID 4153 · bkg10213** como origen.
4. Deja **6 estrellas** en el destino y pulsa **PREPARAR VISTA PREVIA**.
5. Revisa y pulsa **APLICAR ADOPCIÓN**, después **ENVIAR AL JUEGO**.

El origen 4153 se conserva y el destino sigue siendo 9052/bkg2824. Como ambos
charts están a 290 BPM, se conservan sus inicios y largos y se limitan los grupos
a dos flechas para seis estrellas. Los casilleros SPACE permanecen como SPACE.
El límite se aplica también a la segunda tanda.

La copia también puede adoptar la versión 4152 de 145 BPM; en ese caso la vista
previa informa los ajustes de tiempo necesarios. La versión original protegida
permanece disponible como fuente de lectura, con su protección como destino.

## Cómo se relacionan las versiones

Se ofrecen las dificultades con el mismo bkg y los originales, copias hermanas
y copias de copias vinculados por el registro que guarda el Estudio al copiarlas.
Cada opción muestra su ID, BPM, estrellas y bkg. Coincidir en el título no agrega
una canción a esta familia.

Las relaciones incompletas, circulares o ambiguas no habilitan cruces entre
canciones. Las otras dificultades del mismo bkg siguen disponibles cuando el
registro de copias está dañado. Si una copia aislada no tiene un origen
comprobable, se explica el problema del registro.

La adopción se guarda como una instantánea independiente. Generar, escuchar y
recargar conservan el diseño adoptado aunque el original cambie después. La
configuración sigue usando el formato v3. Se incluye la corrección v4 para que
las misiones de solo SPACE aparezcan en turquesa y con su etiqueta correcta.

## Validación

286 pruebas aprobadas y 37 comprobaciones con Tk real en
Linux. El caso de interfaz reproduce las identidades y BPM de las capturas con
audio/tablas sintéticos: original protegido 4153/bkg10213 y copia única
9052/bkg2824. Se comprobaron el botón habilitado, ambas dificultades originales,
la exclusión de otra canción con el mismo título, el límite de dos flechas,
SPACE, regeneración, recarga y que los originales conservaran todos sus campos.

El envío fue interceptado; el cliente y el servidor Windows no se ejecutaron.
Los informes y capturas están en `validacion/`. El original y las versiones
v1, v2, v3 y v4 se conservan con sus nombres anteriores.

Desde **Crear musica** de una instalación completa:

```bash
python -m unittest discover -s tests -v
```
