"""Identidad visual: estilo Bosque.

Un solo lugar para toda decisión de color. Las páginas no escriben colores literales:
los piden aquí, de modo que cambiar la identidad es cambiar este archivo y
`.streamlit/config.toml`, sin tocar ninguna página.

El estilo es oscuro, de verdes profundos con acentos terracota y ámbar, tipografía Plus
Jakarta Sans y formas muy redondeadas: píldoras para los controles, radios amplios para
las superficies.

Tres reglas que el estilo no puede romper, porque no son estéticas sino de lectura:

1. Los cuatro niveles de logro están ordenados y tienen un umbral claro en medio, entre
   quienes no llegan y quienes al menos están en proceso. Por eso se pintan con una
   escala divergente, cálida de un lado y fría del otro, en lugar de cuatro pasos de un
   mismo tono: el corte importa más que la gradación.
2. La escala del mapa es secuencial de un tono, y sobre fondo oscuro la intensidad crece
   hacia el claro: más luminoso es más del indicador que se está mostrando.
3. Las categorías LISA son cualitativas, no una escala. Se distinguen con azul y
   terracota más un neutro, que es el par que sigue funcionando con daltonismo.
"""

from __future__ import annotations

# Superficies. Solo hay dos fondos: el de la página y el verde de la navegación, que se
# apoya encima. Un tercer tono por detrás del panel verde delataba su caja en lugar de
# dejar que flotara sobre la página.
FONDO_EXTERIOR = "#18201D"
MARCA = "#2C5747"
MARCA_CLARA = "#3B6D5B"
MARCA_SUAVE = "#23463A"
MARCA_BORDE = "#4A7565"

FONDO = "#18201D"
SUPERFICIE = "#202A26"
SUPERFICIE_HUNDIDA = "#27332F"
BORDE = "#33413B"
BORDE_SUAVE = "#27332F"

# Texto
TEXTO = "#E5EEE8"
TEXTO_SOBRE_MARCA = "#E6F2EB"
TEXTO_SECUNDARIO = "#ACBCB4"
TEXTO_TENUE = "#8FA399"

# Acentos. ACENTO es el que destaca una cifra sobre fondo oscuro, así que tiene que ser
# claro: el verde de marca no contrasta lo suficiente para eso.
ACENTO = "#99D8B6"
ACENTO_SUAVE = "#23463A"
ACENTO_OSCURO = "#2C5747"

# Acentos de datos, para series que deben distinguirse entre sí
CONTRASTE = "#C86556"
TERCERO = "#8DD1DD"
AVISO = "#E2A84B"

# Niveles de logro, del más bajo al más alto. Escala divergente: el umbral entre En
# inicio y En proceso separa a quienes no llegan de quienes al menos avanzan, y ese corte
# es lo que el ojo tiene que encontrar primero.
NIVELES = {
    0: "#C86556",
    1: "#E09B7E",
    2: "#7FB8C4",
    3: "#3097B3",
}

# Escala secuencial del mapa, de menos a más del indicador mostrado.
ESCALA_MAPA = ["#65433A", "#975D4F", "#C9765F", "#EB9B74", "#FBC99E"]
ESCALA_MAPA_INVERSA = list(reversed(ESCALA_MAPA))

# Conglomerados locales. Categorías, no escala.
LISA = {
    "alto_alto": "#DE7063",
    "alto_bajo": "#F8BBA0",
    "bajo_alto": "#8DD1DD",
    "bajo_bajo": "#3097B3",
    "sin_patron": "#646B68",
}

# Ausencia de dato. Tiene que leerse como ausencia, no como un valor bajo, así que es
# negro: el gris que había antes, #2E3A35, caía a un paso del lienzo del mapa, #27332F,
# y las unidades sin dato se perdían contra el fondo en lugar de distinguirse de él. Con
# el relleno en negro, además, el borde pasa a verse, que antes tampoco se distinguía.
SIN_DATO = "#000000"
SIN_DATO_BORDE = "#44544C"

FUENTE = "'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif"
FUENTE_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap"
)

# Radios. El sistema es muy redondeado: píldoras en los controles y curvas amplias en las
# superficies.
RADIO_PILDORA = "999px"
RADIO_PANEL = "28px"
RADIO_TARJETA = "22px"
RADIO_INTERNO = "16px"

# Ancho del panel del asistente cuando va anclado a la derecha.
ANCHO_ASISTENTE = "380px"


def escala_de(indicador_mas_es_peor: bool) -> list[str]:
    """Escala del mapa según la dirección del indicador.

    Si más es peor, la intensidad crece con el valor. Si más es mejor, se invierte, de
    forma que el tono encendido señale siempre el problema y no cambie de significado al
    cambiar de indicador.
    """
    return ESCALA_MAPA if indicador_mas_es_peor else ESCALA_MAPA_INVERSA


# Plantilla para los gráficos, de modo que Plotly no imponga su propio estilo claro.
PLOTLY = {
    "layout": {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": FUENTE, "color": TEXTO, "size": 12},
        "colorway": [ACENTO, CONTRASTE, TERCERO, AVISO, TEXTO_SECUNDARIO],
        "xaxis": {"gridcolor": BORDE, "linecolor": BORDE, "zerolinecolor": BORDE},
        "yaxis": {"gridcolor": BORDE, "linecolor": BORDE, "zerolinecolor": BORDE},
        "hoverlabel": {
            "bgcolor": SUPERFICIE_HUNDIDA,
            "bordercolor": BORDE,
            "font": {"family": FUENTE, "color": TEXTO},
        },
        "margin": {"l": 10, "r": 10, "t": 30, "b": 10},
    }
}


CSS = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="{FUENTE_URL}" rel="stylesheet">
<style>
    html, body, [class*="st-"], button, input, select, textarea {{
        font-family: {FUENTE} !important;
    }}
    /* Los iconos de Streamlit son una fuente propia: forzarles la tipografía los
       convierte en el texto de su nombre. Hay que devolvérsela. */
    [data-testid="stIconMaterial"], .material-symbols-rounded, span[translate="no"] {{
        font-family: "Material Symbols Rounded" !important;
    }}
    /* Todo lo que rodea a los paneles es un solo fondo. Si body y stApp llevan tonos
       distintos, aparece un rectángulo más oscuro por detrás de la navegación. */
    html, body, .stApp, [data-testid="stAppViewContainer"] {{
        background: {FONDO_EXTERIOR};
    }}

    /* La cabecera propia de Streamlit viene con el color del panel de contenido, así
       que abría una franja de otro tono por encima y alrededor de la navegación. Va
       transparente para que todo lo que rodea a los paneles sea un solo fondo. */
    [data-testid="stHeader"], [data-testid="stToolbar"] {{
        background: transparent;
    }}
    /* El tirador para redimensionar la navegación dibuja una línea vertical al pasar
       el ratón, por delante del panel. El ancho es fijo por diseño, así que sobra. */
    [data-testid="stSidebarResizeHandle"] {{ display: none; }}

    /* El mapa se sirve en un iframe con fondo propio. Sin esto queda una placa clara
       en medio del panel oscuro. */
    iframe[title="streamlit_folium.st_folium"] {{
        background: {SUPERFICIE_HUNDIDA};
        border-radius: {RADIO_TARJETA};
    }}

    /* El área de contenido se separa del fondo como un panel propio, igual que en el
       diseño, donde la navegación y el contenido viven en superficies distintas. */
    /* El contenido no necesita fondo propio: comparte el de la página, y lo que se
       apoya encima son las tarjetas y el panel de navegación. */
    .block-container {{
        padding: 1.4rem 2.2rem 2.4rem;
        max-width: 1560px;
    }}

    /* El asistente es un panel propio anclado a la derecha, no un desplegable: está
       presente en todas las páginas y acompaña a lo que se mira. El contenido deja sitio
       para él en lugar de quedar debajo. */
    @media (min-width: 1200px) {{
        /* El contenido reserva sitio para el asistente solo cuando el asistente está
           en la página: las de ajustes no lo dibujan y aprovechan todo el ancho. */
        .stApp:has(.st-key-panel_asistente) .block-container {{
            padding-right: calc(2.2rem + {ANCHO_ASISTENTE});
        }}
        .st-key-panel_asistente {{
            position: fixed;
            top: 76px;
            right: 18px;
            width: {ANCHO_ASISTENTE};
            max-height: calc(100vh - 96px);
            overflow-y: auto;
            background: {SUPERFICIE};
            border-radius: {RADIO_PANEL};
            padding: 18px;
            z-index: 10;
        }}
    }}
    /* Por debajo de ese ancho no hay sitio para dos columnas: el panel vuelve al flujo
       y se lee después del contenido. */
    @media (max-width: 1199px) {{
        .st-key-panel_asistente {{
            background: {SUPERFICIE};
            border-radius: {RADIO_PANEL};
            padding: 18px;
            margin-top: 18px;
        }}
    }}

    /* La navegación es el panel verde de marca. El contenedor exterior va transparente:
       si conserva su fondo, asoma como un rectángulo por detrás de las esquinas
       redondeadas y delata la caja. */
    [data-testid="stSidebar"] {{
        background: transparent;
        border-right: 0;
    }}
    [data-testid="stSidebar"] > div:first-child {{
        background: {MARCA};
        border-radius: {RADIO_PANEL};
        margin: 10px 0 10px 10px;
        padding-top: 1.2rem;
        height: calc(100vh - 20px);
    }}
    [data-testid="stSidebarContent"] {{ background: transparent; }}
    [data-testid="stSidebarHeader"] {{ background: transparent; }}
    [data-testid="stSidebar"] * {{ color: {TEXTO_SOBRE_MARCA}; }}
    [data-testid="stSidebarNav"] a {{
        border-radius: {RADIO_PILDORA};
        min-height: 44px;
        padding-left: 14px;
    }}
    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        background: {MARCA_CLARA};
        font-weight: 600;
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] > div {{
        background: {MARCA_SUAVE};
        border-color: {MARCA_BORDE};
        border-radius: {RADIO_PILDORA};
        min-height: 44px;
    }}

    h1, h2, h3, h4 {{ color: {TEXTO}; letter-spacing: -0.01em; font-weight: 700; }}
    p, span, label, li {{ color: {TEXTO}; }}

    /* Streamlit le pone -16px de margen inferior al contenedor del markdown, para
       cancelar el margen que trae el <p> con el que envuelve el texto. Cuando el
       contenido es un <div> propio no hay tal <p>, nadie cancela ese -16px y la última
       línea se sale del bloque hasta pegarse al borde. Se veía en todas las pantallas
       y se venía arreglando bloque a bloque; esto lo corta de raíz, solo donde hace
       falta: el último elemento de un contenedor con borde, cuando acaba en <div>.
       Una tabla no entra: su última fila ya trae relleno propio y sin el -16px el
       bloque se quedaba con el doble de aire abajo que arriba. */
    [data-testid="stVerticalBlock"][data-test-scroll-behavior]
    [data-testid="stElementContainer"]:last-child
    [data-testid="stMarkdownContainer"]:has(> div:last-child) {{
        margin-bottom: 0;
    }}
    /* El asistente vive en una columna estrecha, de unos doscientos píxeles de texto.
       Con el cuerpo de la página, 16 píxeles, tres frases ocupaban doscientos de alto
       y había que arrastrar mucho para leer una respuesta. */
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li,
    [data-testid="stChatMessage"] td,
    [data-testid="stChatMessage"] th {{
        font-size: 0.76rem;
        line-height: 1.5;
    }}
    [data-testid="stChatMessage"] [data-testid="stExpander"] summary p {{
        font-size: 0.74rem;
    }}

    /* Superficies: expansores y tarjetas de cifra. */
    [data-testid="stExpander"] details {{
        background: {SUPERFICIE};
        border: 0;
        border-radius: {RADIO_TARJETA};
    }}
    [data-testid="stMetric"] {{
        background: {SUPERFICIE};
        border-radius: {RADIO_TARJETA};
        padding: 14px 18px;
    }}
    /* La cifra se adapta al ancho disponible: en una columna estrecha, un tamaño fijo
       recorta los miles y deja un dato a medias, que es peor que uno más pequeño. */
    [data-testid="stMetricValue"] {{
        font-size: clamp(1.1rem, 2.1vw, 1.7rem);
        letter-spacing: -0.5px; color: {TEXTO}; white-space: nowrap;
    }}
    [data-testid="stMetricLabel"] {{
        font-size: 0.7rem; text-transform: uppercase;
        letter-spacing: 0.06em; color: {TEXTO_SECUNDARIO};
    }}

    /* Controles: píldoras, como en el diseño. */
    .stButton button, .stDownloadButton button, .stLinkButton a {{
        border-radius: {RADIO_PILDORA};
        border: 1px solid {BORDE};
        background: {SUPERFICIE_HUNDIDA};
        color: {TEXTO};
        min-height: 44px;
        font-weight: 500;
    }}
    /* Una etiqueta que no cabe se recortaba con puntos suspensivos y dejaba el botón
       ilegible. Que ocupe dos renglones y el botón crezca de alto. */
    .stButton button p {{ white-space: normal; line-height: 1.3; }}
    .stButton button {{ height: auto; padding-top: 9px; padding-bottom: 9px; }}
    .stButton button:hover {{ border-color: {ACENTO}; color: {ACENTO}; }}
    .stButton button[kind="primary"] {{
        background: {MARCA}; border-color: {MARCA}; color: {TEXTO_SOBRE_MARCA};
    }}
    [data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
        background: {SUPERFICIE_HUNDIDA};
        border-color: {BORDE};
        border-radius: {RADIO_PILDORA};
        color: {TEXTO};
        min-height: 44px;
    }}
    [data-testid="stChatInput"] {{
        background: {SUPERFICIE_HUNDIDA};
        border-radius: {RADIO_PILDORA};
        border-color: {BORDE};
    }}

    /* Piezas propias. */
    .tarjeta {{
        background: {SUPERFICIE}; border: 0;
        border-radius: {RADIO_PANEL}; padding: 18px 20px;
    }}
    .rotulo {{
        font-size: 0.68rem; font-weight: 600; letter-spacing: 0.06em;
        text-transform: uppercase; color: {TEXTO_SECUNDARIO}; margin-bottom: 6px;
    }}
    .nota {{ font-size: 0.78rem; color: {TEXTO_SECUNDARIO}; line-height: 1.55; }}
    .aviso {{
        background: {MARCA_SUAVE}; border: 1px solid {MARCA_BORDE};
        border-radius: {RADIO_TARJETA}; padding: 12px 15px;
        font-size: 0.8rem; color: {TEXTO_SOBRE_MARCA}; line-height: 1.5;
    }}
    .stDataFrame {{ font-variant-numeric: tabular-nums; }}
    hr {{ border-color: {BORDE}; }}

    /* Los avisos de Streamlit traen su propia paleta azul y roja, y una franja de color
       a la izquierda. Esa franja es un recurso gastado que no está en este sistema, así
       que se quita: el aviso es una superficie más, y lo que lo distingue es el texto. */
    [data-testid="stAlert"] {{
        border-radius: {RADIO_TARJETA};
        border: 1px solid {BORDE};
        background: {SUPERFICIE_HUNDIDA};
    }}
    [data-testid="stAlert"] p, [data-testid="stAlert"] span,
    [data-testid="stAlert"] div {{ color: {TEXTO}; }}
    [data-testid="stAlertContentInfo"],
    [data-testid="stAlertContentWarning"],
    [data-testid="stAlertContentError"],
    [data-testid="stAlertContentSuccess"] {{
        background: transparent;
        border: 0;
    }}
    [data-testid="stAlert"] svg {{ display: none; }}
</style>
"""
