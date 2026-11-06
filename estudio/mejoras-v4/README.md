# Estudio LoveRitmo 2020 — mejoras v4

Corrige la presentación de las misiones que contienen únicamente SPACE.
Al adoptar una versión, el mapa podía pintarlas en gris y llamarlas
«calladas», aunque conservaban sus entradas SPACE.

Ahora se reconocen por su contenido y aparecen como **SOLO SPACE**, también
cuando vienen de otro chart y al volver a abrir el Estudio. Se distinguen de
los descansos reales, donde no aparece ninguna misión.

## Descargas

- [Actualización pequeña v4](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/estudio/mejoras-v4/actualizacion-v4.zip)
- [Estudio completo v4](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/raw/refs/heads/main/Estudio_LoveRitmo_2020_mejorado_v4.zip)
- [Versión v3 conservada](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/tree/main/estudio/mejoras-v3)
- [Cómo usar Adoptar versión y sus límites](https://github.com/Lewtial/rrrrrrrrrrrrrrrrr/blob/main/estudio/mejoras-v3/README.md)

## Actualizar

1. Cierra el Estudio y guarda una copia de tu carpeta actual.
2. Extrae `actualizacion-v4.zip`. Copia su carpeta **Crear musica** sobre la tuya
   y acepta reemplazar los archivos de código.
3. Abre `ESTUDIO.bat` y vuelve a abrir el mapa de la canción.

Las misiones que adoptaste antes se muestran corregidas al volver a abrir el
mapa. Esta corrección es visual: basta actualizar el Estudio y reabrir el mapa.
La configuración sigue usando el formato v3.

La actualización pequeña contiene los once módulos acumulados y sus pruebas.
Sirve sobre el original o cualquiera de las versiones anteriores; necesita los
demás archivos de una instalación completa. Si eliges el ZIP completo, extráelo
en una carpeta nueva y revisa las rutas del cliente con `CONFIGURAR.bat`.

## Validación

252 pruebas aprobadas y 48 comprobaciones de interfaz real
registradas en `validacion/`. Se comprobó que la adopción, persistencia y
regeneración conservan los eventos SPACE, incluidas las misiones con dos tandas.
La interfaz se probó en Linux; el cliente y el servidor Windows no se ejecutaron.

Los módulos de datos y adopción se conservaron idénticos a v3. El original y las
versiones v1, v2 y v3 permanecen con sus nombres anteriores.

Desde **Crear musica** de una instalación completa:

```bash
python -m unittest discover -s tests -v
```
