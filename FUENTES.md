# Fuentes de datos

Los microdatos de origen no se versionan: son públicos y se descargan de las fuentes
que se indican abajo. Sí se versionan las geometrías y el almacén analítico que se
construye a partir de todo ello, porque el servicio que publica la aplicación clona este
repositorio y no puede reconstruirlos.

## ENLA 2025

Evaluación Nacional de Logros de Aprendizaje de Estudiantes, aplicada en 2025 por la
**Oficina de Medición de la Calidad de los Aprendizajes (UMC)** del Ministerio de
Educación del Perú.

Portal de la evaluación: http://umc.minedu.gob.pe/enla2025

Se usan las tres bases de datos de la evaluación muestral, que la UMC distribuye en
archivos comprimidos junto con los scripts de cálculo oficiales en R:

| Archivo | Grado | Registros | Áreas evaluadas |
|---|---|---|---|
| `BD_4P ENLA 2025.xlsx` | 4.° de primaria | 129 482 | Lectura, Matemática |
| `BD_2S ENLA 2025.xlsx` | 2.° de secundaria | 106 173 | Lectura, Matemática, Ciencia y Tecnología |
| `BD_5S ENLA 2025.xlsx` | 5.° de secundaria | 12 013 | Lectura, Matemática, Ciencia y Tecnología, Ciudadanía |

Cada archivo trae una hoja `BD` con los microdatos y una hoja
`Diccionario de variables` con la descripción de cada columna.

**Ubicación local:** `DATA/` (no versionada).

### Sobre los pesos muestrales

La ENLA es una evaluación muestral, no censal. Cada base trae un peso por área evaluada
(`peso_L`, `peso_M`, `peso_CN`, `peso_CI`). Las estimaciones nacionales y regionales solo
coinciden con las cifras oficiales si se aplican esos pesos. Cuánto cambia sin ponderar
depende del corte: 2,0 puntos porcentuales en Lectura de 4.° de primaria (32,7 % frente
a 30,6 %) y 1,9 en Lectura de 2.° de secundaria, pero entre 0,1 y 0,7 en las otras siete
combinaciones de grado y área. En los cuatro cortes de 5.° de secundaria el signo se
invierte y sin ponderar sale más alto.

Los pesos están diseñados para representatividad nacional, regional y por estratos. No
garantizan representatividad distrital.

## Resumen ejecutivo ENLA 2025

Documento de la UMC con los resultados oficiales. Se usa como referencia para validar los
cálculos del pipeline.

Repositorio institucional: https://repositorio.minedu.gob.pe/handle/20.500.12799/12773

**Ubicación local:** `CONTEXT/` (no versionada).

## Límites geográficos

Capas administrativas del Perú en formato GeoJSON, nivel 0 a 3.

Fuente: **Peru - Subnational Administrative Boundaries (COD-AB)**, publicada por OCHA
Field Information Services Section en Humanitarian Data Exchange.

https://data.humdata.org/dataset/cod-ab-per

Licencia: Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO).

| Nivel | Unidades |
|---|---|
| Admin 1 | 25 departamentos |
| Admin 2 | 196 provincias |
| Admin 3 | 1 873 distritos |

El código de cada unidad (`adm3_pcode`) es el prefijo `PE` seguido del ubigeo de seis
dígitos. Para cruzarlo con la columna `codgeo` de las bases ENLA hay que normalizar esta
última a seis dígitos, porque viene como entero y pierde el cero inicial.

Las geometrías vienen en CRS84, equivalente a EPSG:4326 en orden longitud, latitud. Se
mantienen en ese sistema de referencia en todo el proyecto.

**Ubicación local:** `geo/` (versionada; los descargables en bruto, no).

## Cómo reconstruir los datos locales

1. Descargar las tres bases de la ENLA 2025 del portal de la UMC y colocarlas en `DATA/`.
2. Descargar el resumen ejecutivo del repositorio del Minedu y colocarlo en `CONTEXT/`.
3. Ejecutar los scripts de `ingest/`, que descargan las geometrías y construyen el almacén
   analítico en `processed/geoeduca.duckdb`, sobrescribiendo el que trae el repositorio.
