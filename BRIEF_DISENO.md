# GEO_EDUCA: brief estructural para diseño

> Este documento describe **qué** debe dibujarse y **por qué cada pieza existe**.
> La dirección de estilo va en la última sección, que completa Ricardo.

---

## 1. Qué es el producto

Una plataforma web que explora los resultados de la **ENLA 2025**, la Evaluación Nacional
de Logros de Aprendizaje del Ministerio de Educación del Perú. Combina tres cosas que
normalmente van separadas:

1. Un **dashboard** de indicadores educativos
2. Un **mapa coroplético** del Perú, que es la pieza central
3. Un **asistente conversacional** que no solo responde: reconfigura el mapa y las
   métricas según lo que se le pregunte

Los datos son reales: 247 668 estudiantes de 4.° de primaria, 2.° y 5.° de secundaria,
en 7 913 escuelas contadas por grado, de las 25 regiones del país.

**Audiencia:** gente de política educativa y análisis de datos. Es una herramienta de
trabajo, no una pieza de marketing. Debe transmitir rigor.

---

## 2. Restricciones técnicas (no negociables)

- Se implementa en **Streamlit** (Python). Evitar propuestas que dependan de animaciones
  complejas, scroll-telling, transiciones de página o layouts que requieran un framework
  de frontend completo.
- La navegación entre secciones ocurre en una **barra lateral izquierda persistente**.
- Debe funcionar a **ancho de teléfono**: los bloques se apilan, las tablas anchas
  scrollean horizontalmente dentro de su caja.
- Los gráficos se renderizan con Plotly o SVG. Nada que necesite WebGL.
- El tema claro/oscuro se maneja con el sistema nativo de Streamlit. Si se propone modo
  oscuro, debe definirse como un set de tokens paralelo, no como un diseño distinto.

---

## 3. Sistema de información (reglas que el estilo debe respetar)

Estas no son decisiones estéticas, son requisitos de lectura de datos:

**Niveles de logro.** Los estudiantes se clasifican en cuatro niveles ordenados, de peor
a mejor: *Previo al inicio → En inicio → En proceso → Satisfactorio*. Necesitan cuatro
pasos de color claramente ordenados, que se distingan **por luminosidad y no solo por
tono**. No usar semáforo rojo-verde: falla con daltonismo y tiñe los datos de juicio
moral.

**Mapa coroplético.** Escala secuencial de un solo tono, de 5 pasos. Más intensidad
equivale a más del indicador que se está mostrando. La leyenda siempre visible.

**Conglomerados espaciales (LISA).** Cinco categorías *cualitativas*, no ordenadas, que
deben distinguirse entre sí: rezago alto rodeado de alto, alto rodeado de bajo, bajo
rodeado de alto, bajo rodeado de bajo, y sin patrón. Conviene una pareja de tonos
opuestos (por ejemplo cálido contra frío) más un neutro.

**Cifras.** Números tabulares (ancho fijo) en tablas y métricas, para que las columnas
alineen. Formato peruano: coma decimal y espacio como separador de miles: `88,4 %`,
`129 482`.

**Contraste.** Texto 4.5:1 mínimo, incluido el gris pequeño de las etiquetas.

**Tres cifras de tamaño que no son lo mismo.** La evaluación es muestral, así que cada
unidad geográfica tiene: los estudiantes realmente evaluados (la muestra), la población
que representan al aplicar los pesos (estimados) y cuántos de esos están en niveles
críticos. La UGEL de Nauta, por ejemplo, evaluó a 428 estudiantes en 30 escuelas, que
representan a 1 622, de los cuales 1 434 están en niveles críticos. Los rótulos de la
interfaz tienen que distinguir las tres: confundirlas es el error de lectura más probable.

---

## 4. Las cinco pantallas

Todas comparten el mismo esqueleto:

```
┌──────────────────────────────────────────────────────────────┐
│  BARRA SUPERIOR: marca + filtros globales (grado, área)      │
├──────────┬────────────────────────────────────┬──────────────┤
│          │                                    │              │
│   NAV    │           CONTENIDO                │  ASISTENTE   │
│ lateral  │                                    │   (chat)     │
│  ~200px  │                                    │   ~320px     │
│          │                                    │              │
└──────────┴────────────────────────────────────┴──────────────┘
```

El asistente va **abierto** en Mapa y Panorama, y **colapsado** a una tira estrecha con
un botón en Brechas y Análisis espacial, donde el contenido necesita el ancho.

La nav tiene cinco entradas: Panorama · Mapa · Brechas · Análisis espacial · Focalización.
Al pie, un bloque pequeño con el tamaño de la muestra.

---

### Pantalla 1. MAPA (es la pantalla de entrada)

La más importante. El mapa debe **dominar visualmente**: es la razón de ser del proyecto.

**Fila de cuatro tarjetas de métrica**, cada una con una micro-visualización distinta
para que el ojo las diferencie:

| Métrica | Valor | Visual | Nota al pie |
|---|---|---|---|
| Satisfactorio | 30,0 % | dona de progreso | sin comparación interanual |
| Niveles críticos | 30,9 % | dona de progreso | Previo al inicio bajó 2,1 pp vs 2024 |
| Medida promedio | 474 | sparkline | aún bajo el pico de 2019 |
| Brecha urbano-rural | 56,2 | sparkline | puntos de diferencia |

**Bloque del mapa** (el más grande de la pantalla, ~60 % del área de contenido):
- Encabezado con título, subtítulo de contexto, y a la derecha dos controles: un
  desplegable de **indicador** (% en niveles críticos / % Satisfactorio / medida promedio
  / brecha urbano-rural) y un grupo de tres botones de **nivel geográfico** (DRE / UGEL /
  Distrito, con uno activo).
- El mapa del Perú con las unidades coloreadas. Al abrir muestra **el país completo**.
- Etiqueta flotante sobre la unidad seleccionada, con nombre y cifra.
- Leyenda sobrepuesta en una esquina, sobre fondo propio para que se lea encima del mapa.

**Columna derecha del mapa**, dos bloques apilados:
- *Unidad seleccionada*: nombre (Loreto - Nauta), contexto (1 622 estudiantes estimados, 428 en la
  muestra), un **anillo de distribución** por los cuatro niveles con la cifra principal
  grande al centro (88,4 % crítico), y debajo la lista de los cuatro niveles con su
  porcentaje.
- *Mayor rezago*: lista de seis UGEL con barra de progreso y porcentaje.

**Banda inferior**: barras verticales de medida promedio por región, doce columnas,
clicables para centrar el mapa.

---

### Pantalla 2. PANORAMA

Cuenta la historia general. Tres visualizaciones, cada una con un trabajo distinto:

**Fila de cuatro KPI** sobrios, solo cifra grande y etiqueta: 247 668 estudiantes ·
7 913 escuelas · 25 regiones · 1 321 distritos.

**Gráfico de pendientes** (el protagonista). Tres líneas que conectan tres momentos:
4.° primaria → 2.° secundaria → 5.° secundaria. Cada línea es un área evaluada y todas
bajan:

- Lectura: 32,7 → 18,5 → 11,3
- Matemática: 30,0 → 12,7 → 12,8
- Ciencia (solo dos puntos, línea punteada): 13,5 → 8,3

Etiquetas de valor en los extremos, nombre del área junto al primer punto. Titular:
*cuanto más avanza la escolaridad, menos alumnos alcanzan lo esperado*.

**Serie histórica** de 4.° de primaria, 2016 a 2025, dos líneas:
- Lectura: 481, 482, 489, 478, 479, 490, 490
- Matemática: 467, 480, 489, 451, 451, 471, 474

El punto a destacar visualmente es el pico de 2019 (489) frente al valor actual de
Matemática (474): seis años después aún no se recupera el nivel prepandemia.

**Barras divergentes.** Seis filas (dos áreas × tres grados), todas alineadas sobre una
**línea vertical compartida**: a la izquierda quienes no llegan (Previo al inicio + En
inicio), a la derecha quienes al menos están En proceso. Esa línea es el elemento clave:
permite ver de golpe cómo el sistema la cruza entre primaria y secundaria.

| Fila | No llega | Al menos en proceso |
|---|---|---|
| Lectura · 4.° primaria | 27,0 % | 73,0 % |
| Lectura · 2.° secundaria | 49,2 % | 50,8 % |
| Lectura · 5.° secundaria | 63,6 % | 36,4 % |
| Matemática · 4.° primaria | 30,9 % | 69,1 % |
| Matemática · 2.° secundaria | 69,0 % | 31,0 % |
| Matemática · 5.° secundaria | 65,6 % | 34,4 % |

---

### Pantalla 3. BRECHAS

**Tres tarjetas de comparación**, una por cada brecha. Cada una muestra dos barras
enfrentadas y la diferencia destacada como cifra grande:

| Brecha | Comparación | Diferencia |
|---|---|---|
| Área | Urbana 482,9 vs Rural 426,7 | **56,2** |
| Gestión | Privada 488,9 vs Pública 468,2 | **20,7** |
| Sexo | Hombre 483,9 vs Mujer 464,3 | **19,6** |

Cada tarjeta lleva una línea de contexto al pie.

**Ranking regional**: barras horizontales con el nombre a la izquierda, barra al centro y
valor a la derecha. Muestra las cinco mejores y las cinco con mayor desafío, con un
**separador explícito** en medio que dice "15 regiones intermedias". De Tacna (520) a
Loreto (432): 89 puntos de rango.

En la versión final cada barra lleva su **intervalo de confianza**, así que hay que
reservar espacio visual para ese elemento.

---

### Pantalla 4. ANÁLISIS ESPACIAL

Responde una pregunta: ¿el rezago se agrupa en el territorio o está repartido al azar?

**Mapa de conglomerados (LISA)** con sus cinco categorías cualitativas y la leyenda
completa en texto, porque los nombres son largos y necesitan explicarse:

- Rezago alto rodeado de rezago alto
- Rezago alto rodeado de rezago bajo
- Rezago bajo rodeado de rezago alto
- Rezago bajo rodeado de rezago bajo
- Sin patrón significativo

**Tarjeta del índice de Moran**: una cifra grande con su interpretación en texto debajo.
Debe soportar un estado de "pendiente de cálculo".

**Tarjeta explicativa** en texto: por qué importa saber si el rezago se agrupa.

**Vista previa** de las UGEL del conglomerado amazónico, con enlace a la pantalla 5. Es
solo el puente entre el hallazgo y la acción; la priorización completa vive aparte.

---

### Pantalla 5. FOCALIZACIÓN

Convierte el análisis en una decisión. Responde: con recursos limitados, ¿por dónde
empezar?

**Encabezado** con la pregunta como título y, a la derecha, un grupo de tres botones de
**criterio de priorización**: por intensidad (% crítico) · por alcance (estudiantes afectados) ·
combinado. Cambiar el criterio reordena todo lo de abajo. Ese control es el corazón de la
pantalla.

**Tres tarjetas de resumen**: 8 UGEL priorizadas · 8 813 estudiantes alcanzados si se atiende a
las ocho · 6 de 8 pertenecen a Loreto.

**Gráfico de dispersión "intensidad frente a alcance"**. Eje X: estudiantes evaluados.
Eje Y: porcentaje en niveles críticos. Tamaño del círculo: estudiantes afectados. Es la pieza
que explica visualmente por qué el criterio importa.

**Tabla priorizada** al lado, ordenada por estudiantes afectados. Columnas: UGEL, % crítico,
estimados y afectados, esta última con mini-barra y en tipografía más marcada porque es la
columna que manda.

| UGEL | Región | % crítico | Estimados | Estudiantes afectados |
|---|---|---|---|---|
| Alto Amazonas - Yurimaguas | Loreto | 70,3 % | 3 394 | **2 387** |
| Nauta | Loreto | 88,4 % | 1 622 | 1 434 |
| Ramón Castilla - Caballococha | Loreto | 83,2 % | 1 631 | 1 357 |
| Requena | Loreto | 73,2 % | 1 334 | 977 |
| Ucayali - Contamana | Loreto | 79,2 % | 1 159 | 918 |
| Atalaya | Ucayali | 71,7 % | 940 | 674 |
| Alto Amazonas - San Lorenzo | Loreto | 87,9 % | 626 | 551 |
| Huarmaca | Piura | 71,6 % | 719 | 515 |

**El punto de la pantalla:** Yurimaguas tiene el porcentaje más bajo de las ocho pero el
mayor número de estudiantes, así que concentra más estudiantes en niveles críticos que
ninguna otra de las ocho. En el país es la 14.ª, por detrás de UGEL de Lima y de Maynas
que tienen mucho más alumnado aunque su porcentaje sea menor. Si la lista se ordena por porcentaje cae al octavo lugar y
probablemente no entra al programa. El diseño tiene que dejar ver esa tensión entre
porcentaje y volumen, no esconderla.

---

## 5. El asistente

Es el diferenciador del producto y necesita tratamiento visual propio.

- Encabezado con nombre y una línea de qué hace.
- Historial de conversación: mensajes del usuario alineados a la derecha en burbuja;
  respuestas del asistente a la izquierda, sin burbuja, como texto corrido.
- **Chip de confirmación de acción.** Cuando el asistente modifica la vista, aparece un
  elemento distinto de un mensaje, con ícono y texto breve, que dice qué cambió:
  *"Mapa, tarjetas y ranking actualizados"*. Sin esto el usuario no entiende por qué la
  pantalla se movió sola. Necesita destacarse del flujo de la conversación sin gritar.
- Sugerencias de pregunta como píldoras clicables al pie.
- Campo de entrada fijo abajo con botón de envío.
- **Estado colapsado**: tira vertical angosta con un botón de ícono y la palabra
  "Asistente" en vertical.

---

## 6. Estados que hay que diseñar

- Carga de datos (el warehouse tarda en responder la primera vez)
- Sin resultados para el filtro elegido
- Unidad geográfica sin datos suficientes (hay 482 distritos con menos de 30 estudiantes:
  deben verse distintos, no simplemente vacíos)
- El asistente pensando
- Error de la consulta

---

## 7. Dirección de estilo

> **Esta sección la completa Ricardo.**
>
> Todo lo anterior es estructura y jerarquía de información. Lo que falta definir aquí es
> el carácter visual: paleta, tipografía, densidad, tratamiento de superficies, bordes y
> sombras, iconografía, y la sensación general que debe transmitir la plataforma.
>
> Lo único que el estilo no puede romper son las reglas de la sección 3, porque afectan la
> lectura correcta de los datos, y las restricciones de la sección 2, porque afectan si se
> puede construir.

<!-- PEGA AQUÍ LA DIRECCIÓN DE ESTILO -->
