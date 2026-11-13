"""Ficha técnica de los datos: fuente, método, alcance y límites.

Recoge lo que antes estaba repartido por las pantallas de análisis. Los textos van al
grano: quien llega aquí busca un dato concreto, no una explicación.
"""

from __future__ import annotations

import streamlit as st

from core import componentes as cp
from core import config, theme

cp.encabezado(
    "Notas sobre los datos",
    "Fuente, método de cálculo y límites de lo que se puede concluir",
)


def _ficha(titulo: str, cuerpo: str) -> None:
    """Un bloque a ancho completo, con su título y su contenido."""
    st.markdown(
        f"""<div style='background:{theme.SUPERFICIE};border-radius:{theme.RADIO_PANEL};
                padding:20px 24px;margin-bottom:12px'>
            <div style='font-size:0.7rem;font-weight:600;letter-spacing:0.06em;
                    text-transform:uppercase;color:{theme.TEXTO_SECUNDARIO};
                    margin-bottom:10px'>{titulo}</div>
            <div style='font-size:0.87rem;line-height:1.7;color:{theme.TEXTO}'>{cuerpo}</div>
        </div>""",
        unsafe_allow_html=True,
    )


_ficha(
    "Fuente",
    "Evaluación Nacional de Logros de Aprendizaje 2025, de la Oficina de Medición de la "
    "Calidad de los Aprendizajes del Ministerio de Educación del Perú, en 4.° de "
    "primaria y 2.° y 5.° de secundaria de las 25 regiones.<br>"
    "La UMC informa 248 294 estudiantes evaluados en 7 914 escuelas. Las bases de "
    "microdatos publicadas traen 247 668, que son los que analiza esta plataforma. "
    "Las escuelas se cuentan por grado, porque las tres bases no comparten un "
    "identificador de escuela: 7 913 en total.<br>"
    "Límites geográficos: fronteras administrativas del Perú publicadas por OCHA, "
    "licencia CC BY-IGO.",
)

_ficha(
    "Ponderación",
    "La evaluación es muestral. Cada estudiante trae un peso que indica a cuántos "
    "representa, y todas las cifras se calculan aplicando esos pesos.<br>"
    "Sin ponderar, el porcentaje en nivel Satisfactorio de 4.° de primaria en Lectura "
    "daría 30,6 % en lugar de 32,7 %.",
)

_ficha(
    "Cifras de tamaño",
    cp.glosario([
        ("Evaluados", "Estudiantes que rindieron la prueba."),
        ("Estimados", "Población que representan al aplicar los pesos."),
        ("En niveles críticos", "Cuántos de esa población están en Previo al inicio o En inicio."),
    ]),
)

_ficha(
    "Niveles de logro",
    cp.glosario([
        ("Previo al inicio", "No alcanzó los aprendizajes necesarios para el nivel En inicio."),
        ("En inicio", "Logró aprendizajes elementales respecto de lo esperado para su ciclo."),
        ("En proceso", "Logró parcialmente los aprendizajes esperados."),
        ("Satisfactorio", "Logró los aprendizajes esperados para el ciclo."),
    ])
    + "<div style='margin-top:10px'>Esta plataforma llama niveles críticos a la suma "
      "de los dos primeros.</div>",
)

_ficha(
    "Muestra mínima",
    f"Las unidades con menos de {config.MUESTRA_MINIMA} estudiantes evaluados se pintan "
    "en negro: con esa cantidad, la cifra depende demasiado de quién entró en la "
    "muestra. El mapa lo deja fijo; en Análisis espacial y en Focalización se puede "
    "mover, para ver cuánto depende de él lo que se está mirando.<br>"
    "Con 30 quedan por debajo 482 de los 1 165 distritos con dato en 4.° de "
    "primaria, 262 de 932 en 2.° de secundaria y 69 de 200 en 5.° de secundaria. "
    "Son las cifras de Matemática; en las otras áreas cambian por unidades.<br>"
    "Moverlo cambia cuánto territorio entra, no el hallazgo. En UGEL de Matemática en "
    "4.° de primaria, el índice de Moran va de 0,52 sin ningún corte a 0,59 con el "
    "corte en 150, y es significativo en todo ese rango; lo que cambia es el número "
    "de unidades que quedan dentro, de 219 a 154.",
)

_ficha(
    "Comparaciones que no son válidas",
    cp.glosario([
        (
            "Medidas promedio entre grados",
            "Cada grado tiene su propia escala calibrada: un 490 en primaria y un 620 "
            "en secundaria no miden lo mismo. Entre grados solo se compara la "
            "distribución por niveles de logro.",
        ),
        (
            "Los tres grados como cohorte",
            "Se evaluaron el mismo año con muestras distintas. Las diferencias entre "
            "ellos describen el estado del sistema, no el avance de unos mismos "
            "estudiantes.",
        ),
    ]),
)

_ficha(
    "Representatividad",
    "4.° de primaria y 2.° de secundaria: resultados nacionales, regionales y por "
    "estrato.<br>"
    "5.° de secundaria: nacionales y por estrato. Sus cifras regionales se pueden "
    "calcular pero no tienen el mismo respaldo, y la plataforma lo advierte cuando ese "
    "corte está activo.",
)

_ficha(
    "Cómo se estima una región",
    "Las cifras de una región se calculan como dominio sobre la muestra completa del "
    "país, no recortando la muestra a esa región. Es la diferencia entre preguntar "
    "cuánto vale un pedazo del país y tratar ese pedazo como si fuera una muestra "
    "aparte: lo segundo pierde los conglomerados que el diseño pone fuera del corte y "
    "devuelve un margen más estrecho que el real.<br>"
    "Los márgenes de un porcentaje no quedan centrados en la cifra. Se construyen en "
    "una escala transformada para que nunca propongan un valor imposible, y por eso "
    "bajan y suben distinto cuando la cifra está cerca de 0 o de 100.<br>"
    f"Una región entra en el ranking si aporta al menos {config.MUESTRA_MINIMA} "
    f"estudiantes evaluados y {config.ESCUELAS_MINIMAS} escuelas. Las escuelas importan "
    "más: en un muestreo por conglomerados son ellas, y no los estudiantes, las que "
    "gobiernan la precisión.<br>"
    "Un margen ancho dice que esa región aporta pocas escuelas a la muestra, no que su "
    "resultado sea peor.",
)

_ficha(
    "Significancia",
    "Una diferencia significativa es demasiado grande para achacarla al azar de la "
    "muestra. No implica que sea grande en magnitud ni que un grupo cause el resultado "
    "del otro.<br>"
    "El ranking regional muestra el margen de cada cifra: la mayoría de las posiciones "
    "contiguas son indistinguibles entre sí, y solo los extremos resisten la "
    "comparación.<br>"
    "Que dos márgenes se toquen no prueba que las dos regiones tengan el mismo "
    "resultado: el solapamiento es un criterio conservador y una diferencia puede ser "
    "significativa aunque los márgenes se crucen. Lo contrario sí se puede afirmar, y "
    "por eso el gráfico permite comparar región contra región.",
)

_ficha(
    "Análisis espacial",
    "El <b>índice de Moran</b> mide si los niveles críticos se agrupan en el "
    "territorio o se reparten al azar. Cercano a cero indica reparto azaroso; alto y "
    "positivo, que las zonas con muchos estudiantes en niveles críticos tienden a "
    "tener vecinas en la misma situación.<br>"
    "Los <b>conglomerados locales</b> clasifican cada unidad según cómo se compara con "
    "sus vecinas. Alto y bajo son respecto del promedio de las unidades analizadas, no "
    "de un umbral de política.<br>"
    "Ambos usan contigüidad: dos unidades son vecinas si comparten frontera. Las que no "
    "tienen ninguna vecina quedan fuera del cálculo y se informan aparte.",
)

_ficha(
    "Cobertura del mapa",
    "Diez distritos con datos no tienen polígono, por ser posteriores a la fecha de "
    "validez de la cartografía oficial. Son el 0,13 % de la población estimada en "
    "4.° de primaria y el 0,77 % en 5.° de secundaria, que es donde más pesan. Sus "
    "estudiantes sí cuentan en los totales por UGEL, región y país.<br>"
    "Mazamari y Pangoa comparten un polígono, porque el límite entre ambos está en "
    "litigio y la cartografía no los separa. Sus cifras se suman.<br>"
    "La capa de UGEL cubre el 84 % del territorio: la evaluación no muestrea todos los "
    "distritos del país.",
)

_ficha(
    "Cuando el polígono no es el territorio",
    "Catorce distritos del país están atendidos por más de una UGEL. La cartografía no "
    "los puede partir, así que cada uno se asigna entero a la UGEL con más estudiantes "
    "y las demás conservan su cifra completa sobre un polígono que ya no los contiene. "
    "En el mapa de UGEL, las afectadas lo advierten al pasar el cursor.<br>"
    "El caso extremo es la UGEL 04 Trujillo Sur Este: su polígono es Moche y Salaverry, "
    "y el 78 % de sus estudiantes está en el distrito de Trujillo, que en el mapa "
    "pertenece a otra UGEL.<br>"
    "Pasa algo parecido con una DRE: el distrito de Máncora pertenece a Piura en el "
    "territorio y a la DRE Tumbes en la evaluación. El mapa de DRE lo dibuja en Piura y "
    "la cifra de Tumbes lo incluye.<br>"
    "Nada de esto afecta a los totales por región ni por país, ni al índice de Moran: "
    "quitar las unidades peor representadas lo mueve de 0,5501 a 0,5549.",
)

_ficha(
    "Cómo se prioriza",
    "Focalización ordena de tres maneras. Por <b>intensidad</b> manda el porcentaje en "
    "niveles críticos, que no depende del tamaño y favorece unidades chicas. Por "
    "<b>alcance</b> manda el número de estudiantes en niveles críticos, que favorece "
    "unidades grandes.<br>"
    "El <b>índice combinado</b> es la media geométrica de los percentiles de los dos: "
    "queda entre 0 y 1 y se hunde si una de las dos dimensiones está en el extremo "
    "bajo, de modo que exige las dos cosas a la vez. Se calcula sobre todas las "
    "unidades del país con muestra suficiente y no sobre la selección, porque un "
    "percentil solo significa algo contra el conjunto completo; las dos columnas de "
    "puesto de la tabla, en cambio, se recalculan dentro de la selección.<br>"
    "Los umbrales de población y de porcentaje son decisiones de política, no del "
    "dato: moverlos cambia la lista.",
)

_ficha(
    "Alcance del análisis",
    "La evaluación mide qué aprendieron los estudiantes, no por qué. La plataforma "
    "muestra dónde se concentran los niveles críticos y qué tan desigual es su "
    "distribución, pero "
    "no identifica causas ni permite atribuir resultados a políticas, escuelas o "
    "características de los estudiantes.",
)

st.caption(f"Fuente de datos: {config.FUENTE}")
