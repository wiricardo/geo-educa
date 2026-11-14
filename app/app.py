"""Punto de entrada de GEO_EDUCA.

Ejecutar con:  .venv/bin/streamlit run app/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
for ruta in (RAIZ / "src", RAIZ / "app"):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

from core import componentes, config, estado, theme  # noqa: E402

st.set_page_config(
    page_title=config.TITULO,
    page_icon=":material/public:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(theme.CSS, unsafe_allow_html=True)

if not estado.hay_almacen():
    st.error(
        "El almacén de datos no existe todavía. Ejecuta la ingesta antes de abrir "
        "la aplicación:"
    )
    st.code(
        ".venv/bin/python ingest/build_warehouse.py\n"
        ".venv/bin/python ingest/build_geo.py",
        language="bash",
    )
    st.stop()

PAGINAS = {
    "Explorar": [
        # La página por omisión se sirve en la raíz y solo ahí: darle un url_path propio
        # hace que esa ruta devuelva un 404. Panorama es, por tanto, la raíz, que es
        # donde tiene que estar: da la lectura de conjunto antes de entrar al mapa.
        st.Page(
            "paginas/panorama.py",
            title="Panorama",
            icon=":material/monitoring:",
            default=True,
        ),
        st.Page("paginas/mapa.py", title="Mapa", icon=":material/map:"),
        st.Page("paginas/brechas.py", title="Brechas", icon=":material/compare_arrows:"),
    ],
    "Analizar": [
        st.Page("paginas/espacial.py", title="Análisis espacial", icon=":material/hub:"),
        st.Page("paginas/focalizacion.py", title="Focalización", icon=":material/target:"),
    ],
    "Ajustes": [
        st.Page("paginas/configuracion.py", title="Configuración", icon=":material/key:"),
        st.Page(
            "paginas/metodologia.py",
            title="Notas sobre los datos",
            icon=":material/help:",
        ),
        st.Page(
            "paginas/proyecto.py",
            title="Sobre este proyecto",
            icon=":material/info:",
        ),
    ],
}

# Panorama resume los tres grados a la vez y las de ajustes no analizan datos: en
# ninguna tiene sentido elegir un grado y un área.
SIN_FILTROS = {
    "Panorama",
    "Configuración",
    "Notas sobre los datos",
    "Sobre este proyecto",
}

# El asistente sí acompaña a Panorama, que es una página de datos. Sobra solo donde no
# hay nada que consultar.
SIN_ASISTENTE = {"Configuración", "Notas sobre los datos", "Sobre este proyecto"}


@st.dialog("GEO_EDUCA", width="large")
def bienvenida() -> None:
    """Aviso de apertura, una sola vez por sesión.

    Es lo primero que ve quien llega, así que dice qué es esto, de dónde salen los datos
    y en qué condiciones funciona el asistente. Un aviso que reaparece es lo primero que
    hace cerrar una demostración, de modo que se enseña una vez por sesión.

    Las cuatro secciones de análisis van en lista y no dentro de una frase: enumeradas
    seguidas había que releer el párrafo para saber qué hay en la plataforma, que es
    justo lo que este aviso tiene que evitar.
    """
    st.markdown(
        f"<div style='font-size:0.95rem;color:{theme.TEXTO_SECUNDARIO};"
        f"margin:-6px 0 16px'>Quiénes no alcanzan lo esperado para su grado, y "
        "dónde están</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
Resultados de la **ENLA 2025**, la evaluación que la UMC del Ministerio de Educación
aplicó a 248 294 estudiantes de tres grados en todo el Perú. Las cifras están
ponderadas con el diseño muestral y coinciden con las oficiales.
        """
    )

    # Las cuatro secciones de análisis, con lo que contesta cada una. Enumerarlas en
    # una frase seguida, como estaban, obliga a releerla para saber qué hay dentro.
    st.markdown(
        "<div class='rotulo' style='margin:14px 0 10px'>Qué puedes hacer aquí</div>"
        + "".join(
            f"<div style='display:flex;gap:10px;align-items:baseline;"
            f"padding:6px 0'>"
            f"<div style='flex:0 0 150px;color:{theme.ACENTO};font-weight:600;"
            f"font-size:0.86rem'>{titulo}</div>"
            f"<div style='flex:1 1 auto;font-size:0.84rem;"
            f"color:{theme.TEXTO_SECUNDARIO};line-height:1.45'>{detalle}</div></div>"
            for titulo, detalle in (
                ("Ver dónde", "En qué regiones, UGEL o distritos se concentran los "
                              "niveles críticos."),
                ("Medir diferencias", "Cuánto separa a los grupos, y si la distancia "
                                      "es mayor que su margen de error."),
                ("Ver si se agrupan", "Si las zonas con más estudiantes en niveles "
                                      "críticos están pegadas unas a otras o "
                                      "repartidas al azar."),
                ("Ordenar", "Por dónde empezar, con tres criterios que no dan el "
                            "mismo orden."),
            )
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div style='margin-top:16px;padding-top:14px;"
        f"border-top:1px solid {theme.BORDE}'>"
        f"<div style='font-size:0.88rem;color:{theme.TEXTO};line-height:1.55'>"
        "El <b>asistente</b> usa inteligencia artificial para consultar los datos y "
        "mover la vista según lo que se le pregunte. Toda cifra que da sale de una "
        "consulta hecha en el momento, nunca de su memoria."
        "</div>"
        f"<div class='nota' style='margin-top:6px'>(Aun así, la inteligencia artificial "
        "se equivoca: conviene comprobar lo que vaya a usarse para algo.) Usa una clave "
        "compartida con tope por sesión; para usarlo sin límite, se puede poner una "
        "propia en Configuración.</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    if st.button("Entendido", type="primary", width="stretch"):
        st.session_state.bienvenida_vista = True
        st.rerun()


componentes.barra_lateral()

if not st.session_state.get("bienvenida_vista"):
    bienvenida()

pagina = st.navigation(PAGINAS)

# En qué sección está el visitante. El asistente lo recibe junto con los filtros: esos
# son los mismos en todas, así que por sí solos no dicen desde dónde se pregunta.
st.session_state["pagina_actual"] = pagina.title

# Si el asistente quedó encargado de abrir otra sección, se atiende aquí, antes de
# dibujar nada. No se hace en el momento de aplicar la acción porque entonces la
# respuesta aún no estaba guardada y el salto se la habría llevado por delante.
POR_TITULO = {p.title: p for grupo in PAGINAS.values() for p in grupo}
_destino = st.session_state.pop("seccion_pedida", None)
if _destino and _destino != pagina.title and _destino in POR_TITULO:
    st.switch_page(POR_TITULO[_destino])

# La barra superior se dibuja antes de la página, de modo que los filtros globales
# queden siempre arriba y en el mismo sitio, sea cual sea la sección abierta.
if pagina.title not in SIN_FILTROS:
    componentes.barra_superior()

pagina.run()

# El asistente se dibuja una vez, al final, y el CSS lo ancla a la derecha. Así está en
# todas las páginas de análisis sin que ninguna tenga que incluirlo, y conserva su
# conversación al cambiar de sección porque el historial vive en el estado.
from core import chat  # noqa: E402

if pagina.title not in SIN_ASISTENTE:
    with st.container(key="panel_asistente"):
        chat.panel(alto=460)
