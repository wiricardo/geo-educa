"""Sobre este proyecto: qué es, cómo está hecho y quién lo hizo.

Separada de Notas sobre los datos a propósito. Allí va la ficha técnica de la
evaluación, que sirve para entender una cifra concreta; aquí va el proyecto, que
interesa a quien llega de fuera y quiere saber de qué va esto antes de meterse en los
datos.

No se escribe como las demás. Las páginas de análisis llevan controles y gráficos; esta
es de lectura, así que lo que la ordena son las cifras de arriba y los bloques cortos,
no un muro de párrafos dentro de cajas.
"""

from __future__ import annotations

import streamlit as st

from core import componentes as cp
from core import config, theme

GITHUB = "https://github.com/wiricardo"

#: Qué responde cada sección, con el mismo texto que el aviso de bienvenida.
SECCIONES = (
    ("Panorama", "Cómo le va al país en los tres grados, y qué distancias separan a "
                 "los grupos."),
    ("Mapa", "En qué regiones, UGEL o distritos se concentran los niveles críticos."),
    ("Brechas", "Cuánto separa a los grupos, y si la distancia es mayor que su margen "
                "de error."),
    ("Análisis espacial", "Si las zonas con más rezago están pegadas unas a otras o "
                          "repartidas al azar."),
    ("Focalización", "Por dónde empezar, con tres criterios que no dan el mismo "
                     "orden."),
    ("Notas sobre los datos", "La fuente, el método de cálculo y los límites."),
)

cp.encabezado(
    "Sobre este proyecto",
    "Qué es GEO_EDUCA, cómo está hecho y quién lo hizo",
)


# 1. La idea, en dos frases y con cuerpo de lectura -----------------------------------

st.markdown(
    f"""<div style='font-size:1.02rem;line-height:1.65;color:{theme.TEXTO};
            max-width:760px;margin:2px 0 6px'>
        Los microdatos de la ENLA 2025 son públicos: cualquiera puede descargarlos del
        portal de la UMC. Lo que no es público, en la práctica, es lo que dicen.
    </div>
    <div style='font-size:0.92rem;line-height:1.65;color:{theme.TEXTO_SECUNDARIO};
            max-width:760px'>
        Llegan en bases con pesos muestrales, estratos y conglomerados. Un promedio
        calculado sin los pesos no da ningún error: devuelve un número equivocado con
        total naturalidad. Eso deja fuera a direcciones regionales, UGEL, docentes y
        periodistas, que son justo quienes tendrían que poder mirarlos. Esta plataforma
        hace ese trabajo una vez y deja las cifras a la vista.
    </div>""",
    unsafe_allow_html=True,
)

st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)

cp.igualar_tarjetas()
col_a, col_b, col_c, col_d = st.columns(4, gap="medium")
with col_a:
    cp.tarjeta_metrica("Estudiantes", "247 668", "Con resultado en los tres grados")
with col_b:
    cp.tarjeta_metrica("Distritos", "1 321", "Con al menos una escuela")
with col_c:
    cp.tarjeta_metrica("Controles", "35", "Contra las cifras que publica la UMC")
with col_d:
    cp.tarjeta_metrica("Pruebas", "198", "Que corren con cada cambio")


# 2. Las seis secciones, en lista y no en un párrafo ----------------------------------

cp.seccion(
    "Qué hay dentro",
    "Cada sección responde un tipo de pregunta distinto sobre los mismos datos.",
)

st.markdown(
    "".join(
        f"<div style='display:flex;gap:14px;align-items:baseline;padding:7px 0;"
        f"border-bottom:1px solid {theme.BORDE_SUAVE}'>"
        f"<div style='flex:0 0 170px;color:{theme.ACENTO};font-weight:600;"
        f"font-size:0.9rem'>{titulo}</div>"
        f"<div style='flex:1 1 auto;font-size:0.87rem;color:{theme.TEXTO_SECUNDARIO};"
        f"line-height:1.5'>{detalle}</div></div>"
        for titulo, detalle in SECCIONES
    ),
    unsafe_allow_html=True,
)


# 3. El método y sus límites ----------------------------------------------------------

cp.seccion(
    "Cómo está hecho",
    "Lo que sostiene cada cifra, y lo que esta plataforma no puede decir.",
)

st.markdown(
    cp.glosario([
        (
            "Las cifras",
            "Todas se calculan con los pesos del diseño muestral. Las que la UMC "
            "publica se usan como control: el mayor desvío es de 0,05 puntos "
            "porcentuales, que es redondeo.",
        ),
        (
            "Las diferencias",
            "Cada una lleva su intervalo de confianza, calculado con el diseño de la "
            "evaluación y no como si fuera una muestra simple, que daría un margen "
            "más estrecho que el real.",
        ),
        (
            "El territorio",
            "Índice de Moran y conglomerados locales sobre contigüidad entre unidades, "
            "para medir si el rezago se agrupa o se reparte al azar.",
        ),
        (
            "Lo que no hace",
            "La evaluación mide qué aprendieron los estudiantes, no por qué. La "
            "plataforma no atribuye causas ni decide dónde intervenir: ordena y "
            "muestra, y deja la decisión donde corresponde.",
        ),
    ]),
    unsafe_allow_html=True,
)


# 4. El asistente, con su límite a la vista -------------------------------------------

cp.seccion(
    "El asistente",
    "Responde preguntas sobre los datos y mueve la vista según lo que se le pida.",
)

izquierda, derecha = st.columns([1.45, 1], gap="medium")
with izquierda:
    with st.container(border=True):
        st.markdown("**Lo que garantiza**")
        st.markdown(
            "<div class='nota'>Toda cifra que da sale de una consulta hecha en el "
            "momento, nunca de su memoria. Cuando escribe una consulta, esta pasa por "
            "un validador que rechaza las agregaciones que olvidan el peso muestral, "
            "que es el error que no se nota porque no da ningún mensaje. Si una "
            "respuesta trae cifras que ninguna herramienta devolvió, la propia "
            "respuesta lo advierte.</div>",
            unsafe_allow_html=True,
        )
with derecha:
    with st.container(border=True):
        st.markdown("**Lo que no**")
        st.markdown(
            f"<div class='nota'>Usa inteligencia artificial, y la inteligencia "
            f"artificial se equivoca. Conviene comprobar lo que vaya a usarse para "
            f"algo.</div>"
            f"<div class='nota' style='margin-top:10px'>Funciona con una clave propia "
            f"de DeepSeek, OpenAI, Anthropic o Google, que se pone en Configuración y "
            f"vive solo mientras dure la sesión.</div>",
            unsafe_allow_html=True,
        )


# 5. Quién lo hizo --------------------------------------------------------------------

cp.seccion("Quién lo hizo", "")

with st.container(border=True):
    autor, enlace = st.columns([3, 1], gap="medium")
    with autor:
        st.markdown(
            f"""<div style='font-size:1.15rem;font-weight:700;color:{theme.TEXTO}'>
                Ricardo Pacheco</div>
            <div style='font-size:0.88rem;line-height:1.6;
                    color:{theme.TEXTO_SECUNDARIO};margin-top:6px;max-width:620px'>
                Trabajo en evaluación educativa: leer lo que dicen los datos de las
                evaluaciones nacionales y convertirlos en algo con lo que se pueda
                decidir.<br>
                GEO_EDUCA salió de esa idea. La ENLA mide bien y publica sus bases; lo
                que faltaba era un sitio donde mirarlas sin tener que reconstruir el
                diseño muestral cada vez.
            </div>""",
            unsafe_allow_html=True,
        )
    with enlace:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.link_button("Ver en GitHub", GITHUB, width="stretch")


# 6. De dónde salen los datos ---------------------------------------------------------

cp.seccion("Fuentes y licencia", "")

st.markdown(
    cp.glosario([
        (
            "Los resultados",
            "Microdatos de la ENLA 2025, distribuidos por la Oficina de Medición de la "
            "Calidad de los Aprendizajes del Ministerio de Educación del Perú.",
        ),
        (
            "Las geometrías",
            "Fronteras administrativas del Perú publicadas por OCHA, con licencia "
            "CC BY-IGO.",
        ),
        (
            "Se puede comprobar",
            "El código y el almacén están publicados, y los microdatos se descargan de "
            "la fuente, así que cualquiera puede reconstruirlo y revisar cada número.",
        ),
    ])
    + "<div class='nota' style='margin-top:12px'>Este proyecto no está afiliado al "
    "Ministerio de Educación del Perú ni a la UMC.</div>",
    unsafe_allow_html=True,
)

st.caption(f"Fuente de datos: {config.FUENTE}")
