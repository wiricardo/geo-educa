# Glosario del almacén GEO_EDUCA

Contexto para escribir SQL contra `processed/geoeduca.duckdb` (DuckDB).
Lee la sección 3 antes de escribir cualquier consulta: ahí está la única forma
correcta de calcular un promedio o una proporción en estos datos.

---

## 1. Qué contiene el almacén

Microdatos de la **ENLA 2025** (Evaluación Nacional de Logros de Aprendizaje),
que aplica la Oficina de Medición de la Calidad de los Aprendizajes (UMC) del
Ministerio de Educación del Perú. Son tres bases independientes:

| Grado | Código | Estudiantes | Escuelas | Áreas evaluadas |
|---|---|---|---|---|
| 4.° de primaria | `4P` | 129 482 | 4 816 | Lectura, Matemática |
| 2.° de secundaria | `2S` | 106 173 | 2 792 | Lectura, Matemática, Ciencia y tecnología |
| 5.° de secundaria | `5S` | 12 013 | 305 | Lectura, Matemática, Ciencia y tecnología, Ciudadanía |

Es una evaluación **muestral**, no un censo. Cada estudiante trae un peso
muestral que indica a cuántos estudiantes del país representa.

---

## 2. Las cinco reglas que no se pueden romper

### 2.1 Siempre ponderar

Todo promedio y toda proporción se calculan con la columna `peso`. Sin ponderar,
las cifras no coinciden con las oficiales: el porcentaje satisfactorio de 4.° de
primaria en Lectura da 30,6 % sin pesos y 32,7 % con pesos. Nunca uses `AVG()`
sobre `medida500` ni `COUNT(*)` para una proporción.

### 2.2 Un peso por área evaluada, y no son intercambiables

En el Excel de origen cada área tenía su propio peso (`peso_L`, `peso_M`, …).
En el almacén eso se resolvió pasando los datos a formato largo: cada fila de
`hechos_estudiante_area` corresponde a **un estudiante en un área**, con una sola
columna `medida500` y una sola columna `peso`, que son siempre las del área de
esa fila. Por eso basta con filtrar por `cod_area` y usar `peso` sin pensar.

La consecuencia es que **cualquier consulta sobre el hecho debe filtrar o agrupar
por `cod_area`**. Si no lo haces, estarás mezclando Lectura con Matemática en un
mismo promedio, que no significa nada.

### 2.3 Las medidas no se comparan entre grados

`medida500` está en la escala calibrada de ese grado y esa área. Un 500 de 4.°
de primaria y un 500 de 5.° de secundaria no son el mismo nivel de logro. Nunca
restes, promedies ni ordenes medidas de grados distintos.

Lo que sí es comparable entre grados es el **porcentaje por nivel de logro**,
porque el nivel se define respecto de lo esperado para cada grado.

### 2.4 El distrito se identifica por `ubigeo`, nunca por nombre

Hay 1 224 nombres de distrito distintos para 1 321 ubigeos: los nombres se
repiten entre departamentos. Agrupa y une siempre por `ubigeo` (seis dígitos,
texto, con cero inicial). Lo mismo con `cod_dre` (cuatro dígitos) y `cod_ugel`
(seis dígitos): en el Excel venían como enteros y perdían el cero inicial, aquí
ya están normalizados como texto.

### 2.5 `id_ie` no cruza entre grados

El identificador de la institución educativa es un correlativo interno de cada
base de origen, no el código modular del Minedu. En el almacén se le antepuso el
grado (`4P-000001`) para que sea único, pero **las tres bases no se pueden cruzar
a nivel de escuela**. La única forma de relacionar grados es agregando por
geografía (ubigeo, UGEL, DRE, provincia, departamento).

---

## 3. Cómo se calcula bien

### Promedio ponderado de la medida

```sql
SUM(peso * medida500) / SUM(peso)
```

### Proporción ponderada de un nivel de logro, en porcentaje

```sql
100.0 * SUM(CASE WHEN cod_nivel = 3 THEN peso ELSE 0 END) / SUM(peso)
```

### Las tres cifras de tamaño, que miden cosas distintas

| Expresión | Qué es | Cómo se usa |
|---|---|---|
| `COUNT(*)` | estudiantes evaluados en la muestra | tamaño de muestra, para decidir si la cifra es reportable |
| `SUM(peso)` | población estimada | cuántos estudiantes del país representa esa muestra |
| `SUM(CASE WHEN es_critico THEN peso ELSE 0 END)` | población estimada en niveles críticos | cuántos estudiantes están en esa situación |

Si alguien pregunta "cuántos estudiantes" sin más, casi siempre quiere la
**población estimada** (`SUM(peso)`), no el tamaño de muestra. Por ejemplo, la
UGEL Loreto - Nauta tiene 428 estudiantes en la muestra, que representan 1 622
estudiantes, de los cuales 1 434 están en niveles críticos. Di siempre cuál de
las tres estás reportando.

### Ejemplo completo: porcentaje satisfactorio y medida promedio por DRE

```sql
SELECT
    nom_dre,
    COUNT(*)                                   AS n_muestra,
    ROUND(SUM(peso), 0)                        AS poblacion_estimada,
    ROUND(SUM(peso * medida500) / SUM(peso), 1) AS medida_promedio,
    ROUND(100.0 * SUM(CASE WHEN cod_nivel = 3 THEN peso ELSE 0 END) / SUM(peso), 1)
                                               AS pct_satisfactorio,
    ROUND(100.0 * SUM(CASE WHEN es_critico     THEN peso ELSE 0 END) / SUM(peso), 1)
                                               AS pct_critico
FROM hechos_estudiante_area
WHERE grado = '4P' AND cod_area = 'L'   -- filtrar grado y área es obligatorio
GROUP BY cod_dre, nom_dre
HAVING COUNT(*) >= 30                   -- no reportar unidades con muestra chica
ORDER BY pct_satisfactorio DESC;
```

Esa consulta reproduce la cifra oficial: a nivel nacional, 4.° de primaria en
Lectura da 32,7 % satisfactorio y medida promedio 490,1.

### Atajo: los agregados ya están calculados

No hace falta reescribir la ponderación para los cortes habituales. La tabla
`resultados_geograficos` ya trae esas mismas métricas por nivel nacional,
departamento, provincia, distrito, DRE y UGEL, y `resultados_desagregado` las
trae por sexo, gestión y ámbito. La consulta anterior equivale a:

```sql
SELECT nom_unidad, n_estudiantes, poblacion_estimada,
       ROUND(medida_promedio, 1) AS medida_promedio,
       ROUND(pct_satisfactorio, 1) AS pct_satisfactorio,
       ROUND(pct_critico, 1) AS pct_critico
FROM resultados_geograficos
WHERE nivel_geografico = 'dre' AND grado = '4P' AND cod_area = 'L'
  AND muestra_suficiente
ORDER BY pct_satisfactorio DESC;
```

Usa `resultados_geograficos` y `resultados_desagregado` para todo lo que calcen,
y baja a `hechos_estudiante_area` solo cuando el corte pedido no exista ahí (por
ejemplo, resultados por DRE **y** por sexo a la vez, o por tipo de gestión dentro
de un distrito).

### Errores frecuentes que hay que evitar

| Error | Por qué está mal |
|---|---|
| `AVG(medida500)` | ignora los pesos; da cifras que no son las oficiales |
| `COUNT(*) FILTER (WHERE cod_nivel = 3) * 100.0 / COUNT(*)` | proporción sin ponderar |
| Agrupar por `distrito` | el nombre se repite; se agrupa por `ubigeo` |
| Omitir `cod_area` | mezcla áreas con escalas distintas en un solo promedio |
| Comparar `medida500` entre grados | las escalas no son comparables |
| Unir `hechos_estudiante_area` consigo mismo por `id_ie` entre grados | `id_ie` no cruza entre bases |
| Reportar `SUM(peso)` como "estudiantes evaluados" | es la población estimada, no la muestra |
| Sumar `pct_satisfactorio` de varias unidades y dividir entre el número de unidades | promedio de porcentajes sin ponderar por población |

Para combinar unidades geográficas, vuelve a `hechos_estudiante_area` y pondera
de nuevo, o pondera por `poblacion_estimada`:
`SUM(pct_critico * poblacion_estimada) / SUM(poblacion_estimada)`.

---

## 4. Niveles de logro

Cuatro categorías ordenadas, de peor a mejor. La columna `cod_nivel` guarda el
código y `nivel_logro` la etiqueta.

| `cod_nivel` | `nivel_logro` | Qué significa |
|---|---|---|
| 0 | Previo al inicio | No logró los aprendizajes necesarios para estar en el nivel En inicio. |
| 1 | En inicio | Logró aprendizajes muy elementales respecto de lo esperado para el grado. |
| 2 | En proceso | Logró parcialmente los aprendizajes esperados para el grado. |
| 3 | Satisfactorio | Logró los aprendizajes esperados para el grado. |

Agrupaciones de uso corriente, ya disponibles como columnas:

- **Niveles críticos** = Previo al inicio + En inicio (`es_critico`, `pct_critico`).
  Es el indicador de rezago que usa la plataforma.
- **Al menos en proceso** = En proceso + Satisfactorio (`pct_al_menos_proceso`).
- **Satisfactorio** = solo el nivel 3 (`es_satisfactorio`, `pct_satisfactorio`).

Los cuatro porcentajes suman 100 dentro de cada combinación de grado, área y
unidad.

---

## 5. Tablas

### 5.1 `hechos_estudiante_area` (616 102 filas)

Tabla base. **Una fila por estudiante y área evaluada**, solo donde hay medida.
Un estudiante de 5.° de secundaria aparece hasta en cuatro filas, una por área.
Las filas sin medida en un área (ausentes o sin resultado válido) no entran: son
entre 25 y 4 437 según el grado y el área, y el procedimiento oficial de la UMC
también las excluye.

| Columna | Tipo | Descripción |
|---|---|---|
| `grado` | VARCHAR | `4P`, `2S` o `5S`. |
| `grado_etq` | VARCHAR | Nombre del grado. |
| `cod_area` | VARCHAR | `L` lectura, `M` matemática, `CN` ciencia y tecnología, `CI` ciudadanía. |
| `area_evaluada` | VARCHAR | Nombre del área. |
| `id_estudiante` | VARCHAR | Llave única de la fila dentro de su área. |
| `id_ie` | VARCHAR | Escuela, con el grado por delante (`4P-000001`). No es el código modular y no cruza entre grados. |
| `id_ie_base` | VARCHAR | Correlativo interno de la IE tal como viene en su base. |
| `id_seccion`, `cor_est` | VARCHAR | Sección dentro de la IE y correlativo del estudiante dentro de la sección. |
| `cod_dre` | VARCHAR(4) | Dirección Regional de Educación, con cero inicial. |
| `nom_dre` | VARCHAR | Nombre de la DRE. |
| `cod_ugel` | VARCHAR(6) | Unidad de Gestión Educativa Local, con cero inicial. |
| `nom_ugel` | VARCHAR | Nombre de la UGEL. |
| `ubigeo` | VARCHAR(6) | Código geográfico del distrito, normalizado. **Única llave válida de distrito.** |
| `distrito` | VARCHAR | Nombre del distrito. Se repite; no sirve de llave. |
| `cod_provincia` | VARCHAR(4) | Primeros cuatro dígitos del ubigeo. |
| `provincia` | VARCHAR | Nombre de la provincia. |
| `cod_departamento` | VARCHAR(2) | Primeros dos dígitos del ubigeo. |
| `departamento` | VARCHAR | Nombre del departamento. |
| `cod_estrato` | VARCHAR | Estrato del diseño muestral de la UMC. Ver 6.3. |
| `cod_gestion` | BIGINT | 1 pública, 2 privada. |
| `gestion` | VARCHAR | `Publica` o `Privada`. |
| `cod_ambito` | BIGINT | 1 urbana, 2 rural. |
| `ambito` | VARCHAR | `Urbana` o `Rural`. |
| `cod_sexo` | BIGINT | 0 hombre, 1 mujer. |
| `sexo` | VARCHAR | `Hombre` o `Mujer`. |
| `medida500` | DOUBLE | Medida de logro en la escala de ese grado y área. No comparable entre grados. |
| `cod_nivel` | TINYINT | 0 a 3. |
| `nivel_logro` | VARCHAR | Etiqueta del nivel. |
| `es_critico` | BOOLEAN | Verdadero si `cod_nivel` es 0 o 1. |
| `es_satisfactorio` | BOOLEAN | Verdadero si `cod_nivel` es 3. |
| `peso` | DOUBLE | **Peso muestral del estudiante para esa área.** Obligatorio en todo cálculo. |

> Ojo con el nombre: en el Excel original la columna urbana/rural se llamaba
> `area`, que se confundía con el área evaluada. Aquí se llama `ambito`.
> `area_evaluada` es la materia; `ambito` es urbana o rural.

### 5.2 `resultados_geograficos` (9 266 filas)

Agregado ponderado por unidad geográfica, grado y área. Es la tabla principal
para mapas, rankings y tarjetas. Los seis niveles conviven en la misma tabla,
así que **siempre hay que filtrar `nivel_geografico`**, o se suman unidades que
se contienen entre sí.

| `nivel_geografico` | `cod_unidad` | `nom_unidad` | `cod_padre` / `nom_padre` |
|---|---|---|---|
| `nacional` | `PE` | Perú | nulo |
| `departamento` | 2 dígitos | nombre del departamento | nulo |
| `provincia` | 4 dígitos | nombre de la provincia | departamento |
| `distrito` | ubigeo de 6 dígitos | nombre del distrito | provincia |
| `dre` | 4 dígitos | nombre de la DRE | nulo |
| `ugel` | 6 dígitos | nombre de la UGEL | DRE |

Hay dos jerarquías distintas que no se mezclan: la **política** (departamento →
provincia → distrito) y la **administrativa educativa** (DRE → UGEL). Las
columnas `cod_departamento` y `departamento` solo están llenas en los niveles de
la jerarquía política, porque una UGEL puede administrar distritos de otro
departamento (ver 7.3).

Métricas, idénticas en esta tabla y en `resultados_desagregado`:

| Columna | Descripción |
|---|---|
| `n_estudiantes` | Estudiantes evaluados en la muestra, sin ponderar. |
| `n_escuelas` | Escuelas distintas en la muestra. |
| `poblacion_estimada` | `SUM(peso)`: estudiantes que representa la muestra. |
| `medida_promedio` | Promedio ponderado de `medida500`. |
| `pct_previo_inicio`, `pct_en_inicio`, `pct_en_proceso`, `pct_satisfactorio` | Porcentajes ponderados por nivel. Suman 100. |
| `pct_critico` | Previo al inicio + En inicio. |
| `pct_al_menos_proceso` | En proceso + Satisfactorio. |
| `poblacion_critica` | `SUM(peso)` de los estudiantes en niveles críticos. |
| `poblacion_satisfactoria` | `SUM(peso)` de los estudiantes en Satisfactorio. |
| `muestra_suficiente` | Falso si `n_estudiantes < 30`. |

Filtra por `muestra_suficiente` en rankings y mapas. En 4.° de primaria y
Lectura, 482 de 1 165 distritos quedan por debajo del umbral.

### 5.3 `resultados_desagregado` (63 filas)

Las mismas métricas a nivel **nacional**, abiertas por una dimensión a la vez.
Reproduce la estructura de los cuadros oficiales de la UMC.

| Columna | Valores |
|---|---|
| `dimension` | `nacional`, `sexo`, `gestion`, `ambito` |
| `cod_categoria` | código de la categoría (nulo cuando `dimension = 'nacional'`) |
| `categoria` | `Nacional`, `Hombre`, `Mujer`, `Publica`, `Privada`, `Urbana`, `Rural` |
| `orden_categoria` | orden de presentación |

La fila con `dimension = 'nacional'` es la cifra país, la misma que
`resultados_geograficos` con `nivel_geografico = 'nacional'`.

### 5.4 `brechas` (27 filas)

Diferencias entre pares de categorías, por grado y área. La resta es siempre
`categoria_a` menos `categoria_b`, con el lado históricamente aventajado en `a`:
Urbana menos Rural, Privada menos Pública, Hombre menos Mujer. Un valor
positivo significa que `categoria_a` está por encima.

Columnas: `medida_a`, `medida_b`, `brecha_medida` (puntos de la escala del
grado), `pct_satisfactorio_a`, `pct_satisfactorio_b`, `brecha_pct_satisfactorio`,
`pct_critico_a`, `pct_critico_b`, `brecha_pct_critico` (puntos porcentuales),
`n_estudiantes_a`, `n_estudiantes_b`.

La brecha es una diferencia observada entre grupos. No es el efecto de
pertenecer a ese grupo: describe cuánto se separan los promedios, nada más.

### 5.5 Dimensiones

| Tabla | Filas | Llave | Contenido |
|---|---|---|---|
| `dim_grado` | 3 | `grado` | Etiqueta, archivo de origen, áreas evaluadas, hasta qué nivel el diseño muestral da estimaciones oficiales (`representatividad`) y `escala_comparable`, que siempre es falso. |
| `dim_area_evaluada` | 4 | `cod_area` | Nombre del área y en qué grados se evaluó. |
| `dim_nivel_logro` | 4 | `cod_nivel` | Etiqueta, orden, `es_critico` y descripción del nivel. |
| `dim_departamento` | 25 | `cod_departamento` | Nombre. |
| `dim_provincia` | 196 | `cod_provincia` | Nombre y departamento. |
| `dim_distrito` | 1 321 | `ubigeo` | Distrito, provincia y departamento. Úsala para unir con geometrías. |
| `dim_dre` | 26 | `cod_dre` | Nombre, número de UGEL y de distritos. |
| `dim_ugel` | 223 | `cod_ugel` | Nombre, DRE a la que pertenece y número de distritos. |
| `dim_ie` | 7 913 | `id_ie` | Escuela: UGEL, DRE, ubigeo, gestión, ámbito, estrato y número de estudiantes. Una fila por escuela **y grado**. |

### 5.6 Metadatos

| Tabla | Para qué sirve |
|---|---|
| `meta_almacen` | Pares clave/valor: fecha de construcción, fuente, grano y las reglas de uso en una línea cada una. |
| `meta_diccionario` | Descripción de cada columna (`tabla`, `columna`, `descripcion`). Este documento en forma de tabla consultable. |
| `meta_validacion` | Resultado de la validación contra las cifras oficiales: `esperado`, `obtenido`, `diferencia`, `pasa`. Sirve para mostrar la procedencia en la aplicación. |
| `meta_rango_medida` | Medida mínima y máxima observadas en cada grado, área y nivel. Delimita los puntos de corte **observados**, que no son los puntos de corte oficiales publicados. |

---

## 6. El diseño muestral

### 6.1 Qué representan los pesos

Cada peso indica a cuántos estudiantes del país representa el estudiante de esa
fila. Dentro de un grado, la suma de pesos es la misma para todas las áreas:
540 704 en 4.° de primaria, 573 752 en 2.° de secundaria y 486 219 en 5.° de
secundaria. Los pesos varían mucho (de 1 a 1 157 en 4.° de primaria) porque las
escuelas pequeñas y rurales se sobremuestrearon a propósito. Por eso ignorarlos
sesga los resultados hacia el ámbito rural y la gestión pública.

### 6.2 Hasta dónde llega cada muestra

| Grado | Representatividad oficial |
|---|---|
| 4.° de primaria | Nacional y por DRE. |
| 2.° de secundaria | Nacional y por DRE. |
| 5.° de secundaria | **Solo nacional.** |

La muestra de 5.° de secundaria son 305 escuelas en 200 distritos y se estratificó
en tres grupos (urbana pública, rural pública, privada) sin diseño por región.
El propio script oficial de la UMC calcula los resultados de 5.° solo a nivel
nacional y por sexo, gestión y ámbito, nunca por DRE.

El almacén sí calcula los agregados geográficos de 5.° de secundaria, porque la
aritmética es la misma, pero **no son estimaciones oficiales y hay que decirlo
cuando se reporten**. Los desagregados por DRE, UGEL o distrito de 5.° de
secundaria son indicativos. Los de 4.° de primaria y 2.° de secundaria, por DRE,
sí corresponden al diseño.

Por debajo de la DRE (UGEL, provincia, distrito) ningún grado tiene
representatividad declarada: son agregaciones de la muestra, útiles para
focalizar, no cifras oficiales. Filtra siempre por `muestra_suficiente` y di de
cuántos estudiantes evaluados sale la cifra.

### 6.3 `cod_estrato`

En 4.° de primaria y 2.° de secundaria es un código de cinco caracteres: los
cuatro primeros son el `cod_dre` y el último numera el estrato dentro de la DRE
(combinaciones de ámbito y gestión). 4.° de primaria tiene 123 estratos y 2.° de
secundaria 77.

En 5.° de secundaria es un solo dígito: `1` urbana pública, `2` rural pública,
`3` privada.

Esta columna solo importa para calcular errores estándar. Los promedios y las
proporciones no la necesitan: el diseño complejo afecta la precisión de la
estimación, no su valor.

### 6.4 Lo que el almacén no trae

**Errores estándar e intervalos de confianza.** La UMC los calcula con un diseño
de conglomerados (escuelas) estratificado (`cod_estrato`) usando `survey` en R.
Las tablas de este almacén reproducen los valores puntuales, que no dependen del
diseño, pero no la precisión. Si alguien pide un intervalo de confianza o quiere
saber si una diferencia es estadísticamente significativa, la respuesta correcta
es que el almacén no tiene esa información, no una estimación improvisada.

---

## 7. Calidad de los datos

### 7.1 Ubigeos con más de un nombre de distrito

Tres ubigeos aparecían con dos nombres distintos. Se resolvieron por mayoría de
filas al construir el almacén:

| Ubigeo | Nombre conservado | Nombre descartado |
|---|---|---|
| 120121 | HUAYUCACHI (227 filas) | CHILCA (41 filas) |
| 150135 | SAN MARTÍN DE PORRES (579 filas) | INDEPENDENCIA (53 filas) |
| 250101 | CALLERÍA (3 767 filas) | NUEVA REQUENA (4 filas) |

En los tres casos el nombre conservado es el que corresponde al ubigeo según el
código geográfico. Las filas afectadas siguen asignadas al ubigeo que traía el
origen, que es lo que no se puede cambiar sin inventar información.

### 7.2 Nombres repetidos

163 ubigeos comparten su nombre de distrito con al menos otro. Un nombre llega a
corresponder a ocho ubigeos distintos. Por eso la llave es el ubigeo.

### 7.3 Jurisdicciones que cruzan fronteras departamentales

La UGEL 240002 (Contralmirante Villar, de la DRE Tumbes) administra el distrito
de Máncora, que pertenece a la provincia de Talara, en Piura. Por eso agregar por
DRE no es lo mismo que agregar por departamento, y la tabla
`resultados_geograficos` deja `departamento` nulo en los niveles `dre` y `ugel`.

Además, 14 ubigeos son atendidos por más de una UGEL. La UGEL no está contenida
en el distrito ni al revés: son dos cortes distintos del territorio. Cada escuela
sí pertenece a una sola UGEL y a un solo distrito.

### 7.4 Estudiantes sin medida

No todos los evaluados tienen resultado en todas las áreas. En 2.° de secundaria,
4 437 estudiantes no tienen medida en Ciencia y tecnología. Esas filas no entran
al hecho, de modo que `n_estudiantes` cambia de un área a otra dentro de la misma
unidad geográfica. No es un error: así lo trata también el procedimiento oficial.

### 7.5 Medidas fuera del rango esperado

La escala se llama "medida 500" por su punto de referencia, pero los valores
observados se extienden bastante más allá: el mínimo del almacén es -254,7, en
Ciencia y tecnología de 2.° de secundaria, y el máximo 1 084,1, en Ciencia y
tecnología de 5.° de secundaria. Son valores válidos de la escala, no errores.

---

## 8. Validación

El script `ingest/build_warehouse.py` comprueba en cada corrida que el almacén
reproduce exactamente las cifras publicadas por la UMC, al primer decimal:

| Grado | Área | Previo al inicio | En inicio | En proceso | Satisfactorio | Medida promedio |
|---|---|---|---|---|---|---|
| 4.° primaria | Lectura | 2,1 | 24,9 | 40,4 | 32,7 | 490,1 |
| 4.° primaria | Matemática | 11,3 | 19,6 | 39,1 | 30,0 | 474,3 |
| 5.° secundaria | Lectura | 27,8 | 35,8 | 25,2 | 11,3 | |
| 5.° secundaria | Matemática | 35,2 | 30,4 | 21,7 | 12,8 | |

Más el porcentaje satisfactorio de 2.° de secundaria (18,5 Lectura, 12,7
Matemática, 13,5 Ciencia y tecnología), el de Ciencia y tecnología de 5.° de
secundaria (8,3), las seis medidas promedio por categoría de 4.° de primaria en
Matemática y siete controles internos de coherencia. Si algún control falla, el
script termina con código 1. El detalle queda guardado en `meta_validacion`.

El procedimiento replicado es el de los scripts oficiales de cálculo de la UMC,
que usan `survey::svydesign(id = ~ID_IE, strata = ~Estrato_DRE, weights = ~peso_X)`
seguido de `svymean`. El valor puntual de `svymean` es exactamente la media
ponderada, por eso una consulta SQL con `SUM(peso * x) / SUM(peso)` lo reproduce.
Lo que el diseño de conglomerados estratificado aporta, y SQL no puede dar, es el
error estándar.

---

## 9. Cómo reconstruir el almacén

```bash
.venv/bin/python ingest/build_warehouse.py
```

Lee los tres Excel de `DATA/`, que son de solo lectura, y reescribe
`processed/geoeduca.duckdb` desde cero. Es idempotente: dos corridas seguidas
producen el mismo archivo. Tarda unos 10 segundos y pesa unos 25 MB.

Fuente: Minedu - UMC. Evaluación Nacional de Logros de Aprendizaje (ENLA) 2025,
evaluación muestral de 4.° de primaria, 2.° y 5.° de secundaria.
