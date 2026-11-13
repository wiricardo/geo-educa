"""Focalización: con recursos limitados, ¿por dónde empezar?

La página no decide. Ordena el mismo conjunto de unidades según tres criterios y deja ver
que el orden cambia según cuál se elija. Esa discrepancia no es un defecto del dato: es
la decisión de política que el dato no puede tomar, y esconderla detrás de un solo orden
sería hacerla pasar por un resultado técnico.

El caso que la página tiene que dejar visible, con los umbrales de entrada: la UGEL de
Alto Amazonas - Yurimaguas tiene el porcentaje en niveles críticos más bajo de las ocho
priorizadas y la población más alta, así que concentra más estudiantes en niveles
críticos que ninguna otra. Ordenada por intensidad queda última; ordenada por
alcance, primera.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import componentes as cp
from core import config, estado, theme
from geoeduca import focalizacion

# Umbrales de política con los que abre la página. No son del dato, son una decisión:
# por eso están a la vista y se pueden mover.
POBLACION_MINIMA = 500
INTENSIDAD_MINIMA = 70

# Qué hace cada criterio, en una línea. El texto largo vive en el motor; aquí va la
# versión que cabe debajo de un botón.
EXPLICACION = {
    "intensidad": "Qué proporción de la unidad está en niveles críticos. "
    "Favorece unidades chicas.",
    "alcance": "A cuántos estudiantes llega la intervención. "
    "Favorece unidades grandes.",
    "combinado": "Exige las dos cosas: quedar muy abajo en una hunde el resultado "
    "aunque la otra sea alta.",
}

ROTULO_CRITERIO = {
    "intensidad": "Por intensidad",
    "alcance": "Por alcance",
    "combinado": "Combinado",
}

ORDEN_CRITERIO = {
    "intensidad": "ordenadas por intensidad",
    "alcance": "ordenadas por alcance",
    "combinado": "ordenadas por el índice combinado",
}

# Plural de cada nivel geográfico, que el catálogo de `config` trae solo en singular.
# UGEL y DRE son siglas y no se pluralizan.
PLURAL_NIVEL = {
    "departamento": "departamentos",
    "dre": "DRE",
    "provincia": "provincias",
    "ugel": "UGEL",
    "distrito": "distritos",
}

# Columnas de la hoja de descartes que se muestran, con su rótulo.
COLUMNAS_DESCARTE = {
    "nombre": "Unidad",
    "ambito": "Pertenece a",
    "muestra": "Evaluados",
    "poblacion": "Estudiantes estimados",
    "intensidad": "% en niveles críticos",
    "alcance": "Estudiantes en niveles críticos",
    "motivo": "Motivo",
}

FORMATO_DESCARTE = {
    "Evaluados": cp.entero,
    "Estudiantes estimados": cp.entero,
    "% en niveles críticos": lambda v: cp.formato(v, 1, " %"),
    "Estudiantes en niveles críticos": cp.entero,
}

# Columna que manda en la tabla según el criterio elegido.
COLUMNA_QUE_MANDA = {
    "intensidad": "% en niveles críticos",
    "alcance": "Estudiantes en niveles críticos",
    "combinado": "Índice combinado",
}


@st.cache_data(show_spinner=False)
def priorizacion(
    nivel: str,
    grado: str,
    area: str,
    criterio: str,
    muestra_minima: int,
    poblacion_minima: float | None,
    intensidad_minima: float | None,
) -> focalizacion.Priorizacion:
    """Priorización de una vista, con caché.

    Los percentiles y el índice combinado se calculan sobre el universo completo y no
    sobre la lista corta: es el propio motor el que se encarga de ese orden, y por eso
    aquí se le pasan los umbrales en lugar de filtrar antes.
    """
    datos = estado.resultados(nivel, grado, area)
    return focalizacion.priorizar(
        datos,
        criterio=criterio,
        muestra_minima=muestra_minima,
        poblacion_minima=poblacion_minima,
        intensidad_minima=intensidad_minima,
    )


def figura_dispersion(
    universo: pd.DataFrame,
    seleccionadas: set[str],
    destacada: pd.Series | None,
    poblacion_minima: float | None,
    intensidad_minima: float | None,
    primera: pd.Series | None = None,
) -> go.Figure:
    """Intensidad frente a alcance: por qué el criterio importa.

    Cada punto es una unidad: la posición horizontal es su población estimada, la
    vertical el porcentaje en niveles críticos y el área del punto los estudiantes en
    niveles críticos, que es el producto de las dos. Así se ve que los dos criterios no
    ordenan igual: hay unidades chicas muy arriba y unidades grandes a media altura con
    más estudiantes en niveles críticos que ellas.

    El eje horizontal va en escala logarítmica porque la población va de unas decenas a
    más de veinte mil estudiantes estimados: en escala lineal, las unidades grandes
    aplastarían a todas las demás contra el eje.
    """
    # El eje logarítmico no admite ceros: una unidad sin población estimada no tiene
    # lugar en este gráfico y se queda fuera de él, no del cálculo.
    universo = universo[universo["poblacion"] > 0].copy()
    universo["es_seleccionada"] = universo["codigo"].isin(seleccionadas)
    maximo = float(universo["alcance"].max())
    referencia = 2.0 * maximo / (34.0**2) if maximo > 0 else 1.0

    def etiquetas(tabla: pd.DataFrame) -> list[list[str]]:
        return [
            [
                str(nombre),
                str(ambito) if ambito is not None else "",
                cp.formato(intensidad, 1, " %"),
                cp.entero(poblacion),
                cp.entero(alcance),
            ]
            for nombre, ambito, intensidad, poblacion, alcance in zip(
                tabla.get("nombre", tabla["codigo"]),
                tabla.get("ambito", pd.Series([None] * len(tabla), index=tabla.index)),
                tabla["intensidad"],
                tabla["poblacion"],
                tabla["alcance"],
            )
        ]

    plantilla = (
        "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
        "En niveles críticos: %{customdata[2]}<br>"
        "Población estimada: %{customdata[3]}<br>"
        "Estudiantes en niveles críticos: %{customdata[4]}<extra></extra>"
    )

    figura = go.Figure()

    for seleccionada, nombre_serie, color, opacidad in (
        (False, "Resto del universo evaluado", theme.SIN_DATO_BORDE, 0.65),
        (True, "Unidades priorizadas", theme.ACENTO, 0.9),
    ):
        parte = universo[universo["es_seleccionada"] == seleccionada]
        if not len(parte):
            continue
        figura.add_trace(
            go.Scatter(
                x=parte["poblacion"],
                y=parte["intensidad"],
                mode="markers",
                name=nombre_serie,
                customdata=etiquetas(parte),
                hovertemplate=plantilla,
                marker=dict(
                    size=parte["alcance"],
                    sizemode="area",
                    sizeref=referencia,
                    sizemin=3,
                    color=color,
                    opacity=opacidad,
                    line=dict(width=0.6, color=theme.SUPERFICIE),
                ),
            )
        )

    # Los dos puntos que el texto nombra se dibujan aparte, con su nombre al lado: la
    # que encabeza la lista y la que más cambia de puesto al cambiar el criterio.
    # Cuando son la misma unidad se dibuja una sola vez, la de la lista, porque es la
    # que el lector viene buscando.
    # El rótulo va al lado que le deje sitio. Con el nombre siempre a la derecha, una
    # unidad grande lo empuja fuera del área de datos y se corta contra el borde.
    izquierda = math.log10(max(float(universo["poblacion"].min()), 1.0))
    derecha = math.log10(max(float(universo["poblacion"].max()), 10.0))

    def lado(fila: pd.Series, vertical: str) -> str:
        if derecha <= izquierda:
            return f"{vertical} right"
        avance = (math.log10(max(float(fila["poblacion"]), 1.0)) - izquierda) / (
            derecha - izquierda
        )
        return f"{vertical} left" if avance > 0.62 else f"{vertical} right"

    codigo_primera = None if primera is None else primera["codigo"]
    con_nombre = [
        (primera, "Primera de la lista", theme.TERCERO, "top"),
    ]
    if destacada is not None and destacada["codigo"] != codigo_primera:
        con_nombre.append(
            (
                destacada,
                "Mayor desacuerdo entre criterios",
                theme.CONTRASTE,
                "middle",
            )
        )
    elif destacada is not None:
        # Es la misma unidad: un solo punto con un rótulo que diga las dos cosas, y en
        # rojo, porque el bloque de abajo escribe ese nombre en rojo y refiere a este
        # punto. Si aquí saliera celeste, el color dejaría de querer decir nada.
        con_nombre = [
            (
                primera,
                "Primera de la lista y mayor desacuerdo",
                theme.CONTRASTE,
                "top",
            )
        ]

    for fila, nombre_serie, color, vertical in con_nombre:
        if fila is None:
            continue
        posicion = lado(fila, vertical)
        marco = pd.DataFrame([fila])
        figura.add_trace(
            go.Scatter(
                x=marco["poblacion"],
                y=marco["intensidad"],
                mode="markers+text",
                name=nombre_serie,
                customdata=etiquetas(marco),
                hovertemplate=plantilla,
                text=[str(fila.get("nombre", fila["codigo"]))],
                textposition=posicion,
                textfont=dict(size=12, color=color, family=theme.FUENTE),
                marker=dict(
                    size=marco["alcance"],
                    sizemode="area",
                    sizeref=referencia,
                    sizemin=6,
                    color=color,
                    opacity=0.95,
                    line=dict(width=1.4, color=theme.SUPERFICIE),
                ),
            )
        )

    if intensidad_minima:
        figura.add_hline(
            y=intensidad_minima,
            line=dict(color=theme.TEXTO_TENUE, width=1, dash="dot"),
            annotation_text=(
                f"Mínimo {cp.formato(intensidad_minima, 0, ' %')} en niveles críticos"
            ),
            annotation_position="top left",
            annotation_font=dict(size=11, color=theme.TEXTO_TENUE),
        )
    if poblacion_minima and poblacion_minima > 0:
        # El eje es logarítmico, así que la línea vertical se ubica en el logaritmo de
        # la posición y no en la posición misma.
        figura.add_vline(
            x=math.log10(poblacion_minima),
            line=dict(color=theme.TEXTO_TENUE, width=1, dash="dot"),
            annotation_text=f"Población mínima {cp.entero(poblacion_minima)}",
            annotation_position="bottom right",
            annotation_font=dict(size=11, color=theme.TEXTO_TENUE),
        )

    marcas = [50, 100, 500, 1000, 5000, 10000, 25000]
    figura.update_layout(
        height=430,
        margin=dict(l=10, r=10, t=44, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=theme.FUENTE, size=12, color=theme.TEXTO_SECUNDARIO),
        hoverlabel=dict(
            bgcolor=theme.SUPERFICIE,
            bordercolor=theme.BORDE,
            font=dict(family=theme.FUENTE, size=12, color=theme.TEXTO),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            itemsizing="constant",
            font=dict(size=11),
        ),
        xaxis=dict(
            title="Estudiantes que tiene la unidad (escala logarítmica)",
            type="log",
            tickvals=marcas,
            ticktext=[cp.entero(m) for m in marcas],
            gridcolor=theme.BORDE_SUAVE,
            zeroline=False,
            linecolor=theme.BORDE,
        ),
        yaxis=dict(
            title="% en niveles críticos (intensidad)",
            ticksuffix=" %",
            gridcolor=theme.BORDE_SUAVE,
            zeroline=False,
            linecolor=theme.BORDE,
        ),
    )
    return figura


#: Columna por la que ordena cada criterio y cómo se escribe su cifra. El orden que
#: produce ordenar por estas columnas es el mismo que devuelve el motor, de modo que
#: los tres encabezados salen de la tabla que ya está en pantalla.
CIFRA_DEL_CRITERIO = {
    "intensidad": (
        "intensidad",
        lambda v: f"{cp.formato(v, 1, ' %')} en niveles críticos",
    ),
    "alcance": (
        "alcance",
        lambda v: f"{cp.entero(v)} estudiantes en niveles críticos",
    ),
    "combinado": ("indice_combinado", lambda v: f"índice {cp.formato(v, 3)}"),
}


#: Cómo se nombra cada criterio dentro de una frase.
EN_FRASE = {
    "intensidad": "por intensidad",
    "alcance": "por alcance",
    "combinado": "por el índice combinado",
}


def nombrar_las_primeras(nombres: list[str], de_la_lista_entera: bool) -> str:
    """Las primeras unidades del orden, sin convertirse en una lista de ocho nombres.

    Enumerarlas todas llenaba tres renglones y el gráfico de abajo ya rotula una por
    una. Pasadas cuatro se nombran los extremos, que es lo que ubica el tramo.
    """
    if de_la_lista_entera:
        return "Son todas las de la lista."
    if len(nombres) == 1:
        return f"Es {nombres[0]}."
    if len(nombres) <= 4:
        return f"Son {', '.join(nombres[:-1])} y {nombres[-1]}."
    return f"Son las {cp.unidades(len(nombres))} que van de {nombres[0]} a {nombres[-1]}."


def alcance_de_las_primeras(tabla: pd.DataFrame, criterio: str, cuantas: int) -> float:
    """Estudiantes en niveles críticos de las primeras N con un criterio dado."""
    columna = CIFRA_DEL_CRITERIO[criterio][0]
    orden = tabla.sort_values(columna, ascending=False, kind="mergesort")
    return float(orden["alcance"].head(cuantas).sum())


def criterio_que_alcanza_mas(
    tabla: pd.DataFrame, criterio: str, cuantas: int
) -> tuple[str | None, float]:
    """Cuál de los otros criterios llega a más estudiantes con las mismas N unidades.

    Es lo que convierte la curva de cobertura en algo que se conecta con el criterio:
    atender tres unidades no alcanza a lo mismo según cuáles sean esas tres.
    """
    mejor = alcance_de_las_primeras(tabla, criterio, cuantas)
    rival = None
    for otro in CIFRA_DEL_CRITERIO:
        if otro == criterio:
            continue
        valor = alcance_de_las_primeras(tabla, otro, cuantas)
        if valor > mejor + 0.5:
            rival, mejor = otro, valor
    return rival, mejor


def quien_encabeza(tabla: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Quién queda primera con cada uno de los tres criterios.

    La pantalla muestra un orden por vez, así que para descubrir que un criterio
    encabeza distinto había que probar los tres. Esto los pone a la vista juntos, con
    la cifra por la que cada uno ordena, que es lo que explica la diferencia.
    """
    resumen = []
    for criterio, (columna, formato) in CIFRA_DEL_CRITERIO.items():
        primera = tabla.sort_values(columna, ascending=False, kind="mergesort").iloc[0]
        resumen.append((criterio, str(primera["nombre"]), formato(primera[columna])))
    return resumen


def lectura_de_la_lista(tabla: pd.DataFrame, criterio: str) -> str:
    """Lee los dos extremos de la lista con nombres y cifras.

    Encima de la tabla iba un manual de sus columnas, que sobra: qué es cada columna se
    deduce de su nombre. Lo que no se deduce es por qué el orden quedó así, y de eso
    hablan estas frases. Cambian con el criterio porque cada uno ordena por una cifra
    distinta, y cada versión nombra justamente esa.
    """
    primera, ultima = tabla.iloc[0], tabla.iloc[-1]
    nombre_p, nombre_u = primera["nombre"], ultima["nombre"]
    pct_p = cp.formato(primera["intensidad"], 1, " %")
    pct_u = cp.formato(ultima["intensidad"], 1, " %")
    alcance_p = cp.entero(primera["alcance"])
    alcance_u = cp.entero(ultima["alcance"])

    if criterio == "intensidad":
        texto = (
            f"<b>{nombre_p}</b> llega a {pct_p} de sus estudiantes en niveles críticos "
            f"y <b>{nombre_u}</b>, al final de la lista, a {pct_u}."
        )
        # El caso que justifica que la página exista: con este criterio la última puede
        # tener más estudiantes en niveles críticos que la primera. Pide un margen del
        # 10 % porque con una diferencia de sesenta estudiantes la frase sigue siendo
        # cierta pero ya no ilustra nada, y presentarla como hallazgo chirría.
        if float(ultima["alcance"]) > float(primera["alcance"]) * 1.1:
            texto += (
                f" Aun así tiene más estudiantes en esa situación, {alcance_u} "
                f"contra {alcance_p}."
            )
        return texto

    if criterio == "alcance":
        return (
            f"<b>{nombre_p}</b> reúne {alcance_p} estudiantes en niveles críticos y "
            f"<b>{nombre_u}</b>, al final de la lista, {alcance_u}. Entre todas suman "
            f"{cp.entero(tabla['alcance'].sum())}."
        )

    # Combinado. El valor del índice no dice nada por sí solo, así que la frase muestra
    # las dos cifras de las que sale, en los dos extremos de la lista.
    return (
        f"<b>{nombre_p}</b> junta {pct_p} en niveles críticos con {alcance_p} "
        f"estudiantes en esa situación. <b>{nombre_u}</b> cierra la lista con {pct_u} "
        f"y {alcance_u} estudiantes."
    )


def tabla_descartes(descartadas: pd.DataFrame):
    """Hoja de descartes con los rótulos y el formato de la aplicación."""
    presentes = [c for c in COLUMNAS_DESCARTE if c in descartadas.columns]
    vista = descartadas[presentes].rename(columns=COLUMNAS_DESCARTE)
    formatos = {k: v for k, v in FORMATO_DESCARTE.items() if k in vista.columns}
    return vista.style.format(formatos)


def marcas_del_eje(tope: float) -> list[float]:
    """Marcas redondas para un eje que llega hasta `tope`.

    Se calculan a mano porque Plotly abrevia los millares como "10k" y la aplicación
    escribe las cifras en formato peruano. El paso sale de la serie 1, 2, 5: se toma el
    primero que deja seis marcas o menos.
    """
    if tope <= 0:
        return [0.0]
    exponente = math.floor(math.log10(tope))
    paso = 10.0**exponente
    for multiplo in (1, 2, 5, 10, 20, 50, 100):
        paso = multiplo * 10.0 ** (exponente - 1)
        if tope / paso <= 6:
            break
    return [i * paso for i in range(int(tope // paso) + 2)]


def figura_cobertura(cobertura: pd.DataFrame, atendidas: int) -> go.Figure:
    """Estudiantes en niveles críticos acumulados al atender las primeras N unidades."""
    # Con muchas unidades no caben ni los nombres ni las cifras sobre cada barra: el
    # eje pasa a numerar las unidades y el detalle queda en el cursor.
    detallado = len(cobertura) <= 15
    usar_nombres = "nombre" in cobertura.columns and detallado
    ejes = (
        [str(n) for n in cobertura["nombre"]]
        if usar_nombres
        else [cp.entero(n) for n in cobertura["n_unidades"]]
    )
    colores = [
        theme.ACENTO if n <= atendidas else theme.ACENTO_SUAVE
        for n in cobertura["n_unidades"]
    ]
    marcas_y = marcas_del_eje(float(cobertura["acum_criticos"].max()))
    detalle = [
        [str(nombre), cp.entero(criticos), cp.formato(pct, 1, " %"), cp.entero(acum)]
        for nombre, criticos, pct, acum in zip(
            cobertura.get("nombre", cobertura["n_unidades"]),
            cobertura["criticos"],
            cobertura["pct_cobertura"],
            cobertura["acum_criticos"],
        )
    ]

    figura = go.Figure(
        go.Bar(
            x=ejes,
            y=cobertura["acum_criticos"],
            marker=dict(color=colores, line=dict(width=0)),
            text=(
                [cp.entero(v) for v in cobertura["acum_criticos"]]
                if detallado
                else None
            ),
            textposition="outside",
            textfont=dict(size=11, color=theme.TEXTO_SECUNDARIO),
            cliponaxis=False,
            customdata=detalle,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Aporta %{customdata[1]} estudiantes<br>"
                "Acumulado: %{customdata[3]}<br>"
                "Cobertura del universo evaluado: %{customdata[2]}<extra></extra>"
            ),
        )
    )
    figura.update_layout(
        # Más alto de lo que pide el dato: los nombres de las unidades van en diagonal
        # y se comen la mitad de abajo, así que con 330 el área de datos quedaba en
        # 154 píxeles y el rótulo del eje vertical, que mide más que eso, se salía por
        # arriba del gráfico y terminaba debajo de la tarjeta.
        height=400,
        margin=dict(l=10, r=10, t=14, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=theme.FUENTE, size=12, color=theme.TEXTO_SECUNDARIO),
        hoverlabel=dict(
            bgcolor=theme.SUPERFICIE,
            bordercolor=theme.BORDE,
            font=dict(family=theme.FUENTE, size=12, color=theme.TEXTO),
        ),
        showlegend=False,
        xaxis=dict(
            title="Unidades atendidas, en el orden del criterio",
            tickangle=-30 if usar_nombres else 0,
            linecolor=theme.BORDE,
        ),
        yaxis=dict(
            # Sin "(acumulado)": lo dicen el título del bloque y el globo de cada
            # barra, y aquí solo servía para que el rótulo no cupiera.
            title="Estudiantes alcanzados",
            tickvals=marcas_y,
            ticktext=[cp.entero(m) for m in marcas_y],
            gridcolor=theme.BORDE_SUAVE,
            zeroline=False,
            rangemode="tozero",
        ),
    )
    return figura


f = estado.filtros()

cp.encabezado(
    "¿Por dónde empezar?",
    f"Dónde concentrar los esfuerzos en {f.descripcion()}",
)

# Los controles hacen dos cosas distintas y por eso van en dos bloques: cuatro deciden
# qué unidades son candidatas y el quinto decide en qué orden se miran. Antes el
# criterio ocupaba una columna propia a la izquierda, tan alta como sus tres
# descripciones juntas, y dejaba vacía media pantalla a su derecha.

# Claves propias y sin `index` ni `value`, por lo mismo que en el mapa: ver
# `estado.sembrar`.
estado.sembrar("focal_nivel", "nivel_geografico")
estado.sembrar("focal_muestra_minima", "muestra_minima")
estado.sembrar("focal_criterio", "criterio")

cp.igualar_tarjetas()

st.markdown("<div class='rotulo'>Qué unidades entran</div>", unsafe_allow_html=True)
col_nivel, col_muestra, col_poblacion, col_intensidad = st.columns(4)

with col_nivel:
    nivel = st.selectbox(
        "Nivel geográfico",
        options=list(config.NIVELES_GEOGRAFICOS),
        format_func=lambda c: config.NIVELES_GEOGRAFICOS[c],
        key="focal_nivel",
    )

with col_muestra:
    muestra_minima = st.number_input(
        "Muestra mínima",
        min_value=0,
        max_value=200,
        step=10,
        key="focal_muestra_minima",
        help=(
            "Estudiantes evaluados mínimos para entrar. Es un filtro de calidad del "
            "dato, no de política: un porcentaje calculado sobre quince estudiantes "
            "no sostiene una decisión de focalización.\n\n"
            "Treinta es el corte que usa el resto de la plataforma. Bajarlo deja "
            "entrar unidades cuya cifra es casi ruido muestral, y suelen colarse "
            "arriba del orden justo por eso."
        ),
    )

with col_poblacion:
    poblacion_minima = st.number_input(
        "Población mínima",
        min_value=0,
        max_value=20000,
        value=POBLACION_MINIMA,
        step=100,
        key="focal_poblacion_minima",
        help="Estudiantes estimados mínimos de la unidad. Con 0 no se aplica.",
    )

with col_intensidad:
    intensidad_minima = st.number_input(
        "Mínimo en niveles críticos (%)",
        min_value=0,
        max_value=100,
        value=INTENSIDAD_MINIMA,
        step=5,
        key="focal_intensidad_minima",
        help="Porcentaje mínimo en niveles críticos para que la unidad sea candidata. "
        "Con 0 no se aplica.",
    )

st.markdown(
    "<div class='rotulo' style='margin-top:14px'>Cómo se ordenan</div>",
    unsafe_allow_html=True,
)
criterio = st.radio(
    "Criterio de priorización",
    options=list(focalizacion.CRITERIOS),
    format_func=lambda c: ROTULO_CRITERIO[c],
    key="focal_criterio",
    label_visibility="collapsed",
    # Sin `horizontal`: Streamlit lo ignora en cuanto hay captions, y dejarlo puesto
    # haría pensar que las opciones salen en fila. En columna, con una línea de
    # descripción cada una, el bloque ocupa menos que el ancho de tres columnas.
    captions=[EXPLICACION[c] for c in focalizacion.CRITERIOS],
    help="Cambiar el criterio reordena todo lo de abajo. Los tres usan el mismo "
    "dato y responden preguntas distintas.",
)

estado.actualizar(
    nivel_geografico=nivel, muestra_minima=muestra_minima, criterio=criterio
)
f = estado.filtros()

cp.aviso_representatividad(f.grado, nivel)

try:
    prioridad = priorizacion(
        nivel,
        f.grado,
        f.area,
        criterio,
        muestra_minima,
        float(poblacion_minima) if poblacion_minima else None,
        float(intensidad_minima) if intensidad_minima else None,
    )
except (ValueError, KeyError) as error:
    st.warning(f"No se puede priorizar con la selección actual: {error}")
    st.stop()

tabla = prioridad.tabla
n_priorizadas = prioridad.n_unidades
nombre_nivel = config.NIVELES_GEOGRAFICOS[nivel]

if n_priorizadas == 0:
    st.warning(
        f"Ninguna unidad de nivel {nombre_nivel} cumple los umbrales a la vez. "
        "Baja el mínimo de niveles críticos o la población mínima para ver "
        "candidatas."
    )
    with st.expander(
        f"Ver las {cp.entero(len(prioridad.descartadas))} unidades descartadas y su "
        "motivo"
    ):
        st.dataframe(
            tabla_descartes(prioridad.descartadas),
            width="stretch",
            hide_index=True,
            height=320,
        )
    cp.pie_de_pagina()
    st.stop()

# Posiciones recalculadas dentro de la selección: es lo que hace falta para decir que
# una unidad es la octava por intensidad y la primera por alcance entre las ocho.
comparacion = focalizacion.comparar_criterios(prioridad, orden=criterio)
desacuerdos = focalizacion.comparar_criterios(prioridad, orden="desacuerdo")
destacada = None
if len(desacuerdos) > 1 and int(desacuerdos.iloc[0]["desacuerdo"]) != 0:
    destacada = desacuerdos.iloc[0]

# El criterio solo cambia el orden, así que todo lo de abajo sale igual con los tres y
# parece que el control no hace nada. Aquí se ven los tres a la vez: con cuál encabeza
# cada uno y por qué cifra. Con una sola unidad no hay orden que comparar y basta
# nombrarla.
if n_priorizadas == 1:
    st.markdown(
        f"<div class='nota' style='margin:6px 0 2px'>La única que cumple los umbrales "
        f"es <b style='color:{theme.TEXTO}'>{tabla['nombre'].iloc[0]}</b>.</div>",
        unsafe_allow_html=True,
    )
elif len(tabla):
    filas = "".join(
        f"<div style='display:flex;align-items:baseline;gap:4px 14px;flex-wrap:wrap;"
        f"padding:7px 11px;border-radius:7px;margin-bottom:3px;"
        f"background:{theme.ACENTO_SUAVE if marcada else 'transparent'}'>"
        f"<div style='flex:0 0 118px;font-size:0.78rem;"
        f"color:{theme.ACENTO if marcada else theme.TEXTO_TENUE}'>"
        f"{ROTULO_CRITERIO[clave]}</div>"
        f"<div style='flex:1 1 180px;color:{theme.TEXTO};"
        f"font-weight:{700 if marcada else 500}'>{nombre}</div>"
        f"<div style='flex:0 0 auto;font-size:0.82rem;"
        f"color:{theme.TEXTO_SECUNDARIO}'>{cifra}</div></div>"
        for clave, nombre, cifra in quien_encabeza(tabla)
        for marcada in [clave == criterio]
    )
    plural_nivel = PLURAL_NIVEL[nivel]
    st.markdown(
        "<div class='rotulo' style='margin:10px 0 6px'>Con cada criterio encabeza"
        f"</div>{filas}"
        f"<div class='nota' style='margin-top:6px'>Son las mismas "
        f"{cp.entero(n_priorizadas)} {plural_nivel} con los tres criterios, solo "
        "cambia el orden.</div>",
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
col_a, col_b, col_c = st.columns(3, gap="medium")

# Los tres pies van cortos a propósito. Con uno de tres renglones y otro de uno, las
# tarjetas se estiran al más alto y a las demás les queda un hueco en medio: los
# umbrales exactos están en los controles de arriba y el denominador, en Notas.
with col_a:
    cp.tarjeta_metrica(
        "Unidades priorizadas",
        f"{cp.entero(n_priorizadas)} "
        f"{nombre_nivel if n_priorizadas == 1 else PLURAL_NIVEL[nivel]}",
        f"De {cp.entero(prioridad.n_universo)} con muestra suficiente, aplicando los "
        "umbrales de arriba.",
    )

with col_b:
    parte_universo = (
        100.0 * prioridad.alcance_total / prioridad.alcance_universo
        if prioridad.alcance_universo > 0
        else 0.0
    )
    cp.tarjeta_metrica(
        "Estudiantes que alcanzarían",
        cp.entero(prioridad.alcance_total),
        f"En niveles críticos, el {cp.formato(parte_universo, 1, ' %')} de todos los "
        "del universo evaluado.",
    )

with col_c:
    if "ambito" in tabla.columns and tabla["ambito"].notna().any():
        cuentas = tabla["ambito"].value_counts()
        # Con dos o tres se nombran; contarlas obliga a atar cabos entre el titular,
        # que ya dice una, y un recuento que no dice cuáles son las otras.
        otras = list(cuentas.index[1:])
        if not otras:
            reparto = "No hay ninguna fuera de ahí."
        elif len(otras) <= 3:
            resto = int(cuentas.iloc[1:].sum())
            reparto = (
                f"{'La otra está' if resto == 1 else f'Las otras {resto} están'} en "
                + (" y ".join([", ".join(otras[:-1]), otras[-1]] if len(otras) > 1
                               else otras))
                + "."
            )
        else:
            donde = config.NIVEL_PADRE.get(f.nivel_geografico, "unidades")
            reparto = f"Las demás se reparten entre {cp.entero(len(otras))} {donde}."
        cp.tarjeta_metrica(
            "Concentración geográfica",
            f"{cp.entero(int(cuentas.iloc[0]))} de {cp.entero(n_priorizadas)} "
            f"en {cuentas.index[0]}",
            reparto,
        )
    else:
        cp.tarjeta_metrica(
            "Concentración geográfica",
            "sin dato",
            "Este nivel no pertenece a ninguna unidad mayor.",
        )

cp.separador()

columna_manda = COLUMNA_QUE_MANDA[criterio]

# Las filas y su orden salen de `prioridad.tabla`, que es la selección tal como la
# ordenó el motor. Los dos puestos de comparación salen de `comparar_criterios`, que los
# recalcula dentro de la selección: son dos cosas distintas y mezclarlas cambiaría el
# orden. El índice combinado, en cambio, se calcula sobre el universo completo, así que
# el que vale es el de la selección y no el que `comparar_criterios` recalcula sobre
# ocho unidades.
puestos = comparacion.set_index("codigo")
base_tabla = tabla.assign(
    puesto_intensidad=tabla["codigo"].map(puestos["pos_intensidad"]),
    puesto_alcance=tabla["codigo"].map(puestos["pos_alcance"]),
)

presentacion = pd.DataFrame(
    {
        "#": base_tabla["posicion"].astype(int),
        "Unidad": base_tabla.get("nombre", base_tabla["codigo"]),
        "Pertenece a": base_tabla.get(
            "ambito", pd.Series([""] * len(base_tabla), index=base_tabla.index)
        ),
        "% en niveles críticos": base_tabla["intensidad"],
        "Estudiantes estimados": base_tabla["poblacion"],
        "Estudiantes en niveles críticos": base_tabla["alcance"],
        "Índice combinado": base_tabla["indice_combinado"],
        "Por intensidad": base_tabla["puesto_intensidad"].astype(int),
        "Por alcance": base_tabla["puesto_alcance"].astype(int),
    }
)

estilo = presentacion.style.format(
    {
        "% en niveles críticos": lambda v: cp.formato(v, 1, " %"),
        "Estudiantes estimados": cp.entero,
        "Estudiantes en niveles críticos": cp.entero,
        "Índice combinado": lambda v: cp.formato(v, 3),
    }
).set_properties(
    subset=[columna_manda],
    **{"background-color": theme.ACENTO_SUAVE, "font-weight": "700"},
)

with st.container(border=True):
    st.markdown(f"**Unidades priorizadas, {ORDEN_CRITERIO[criterio]}**")
    if n_priorizadas > 1:
        st.markdown(
            f"<div class='nota' style='margin-bottom:10px'>"
            f"{lectura_de_la_lista(tabla, criterio)}</div>",
            unsafe_allow_html=True,
        )
    st.dataframe(
        estilo,
        width="stretch",
        hide_index=True,
        height=min(60 + 35 * len(presentacion), 420),
    )
    st.caption(
        "La evaluación solo declara representatividad hasta el nivel de región. Estas "
        "cifras valen para decidir por dónde empezar, no como dato oficial de cada "
        "unidad."
    )

# Sin separador antes de este bloque: el gráfico dibuja las mismas unidades de la
# tabla de arriba, y la línea los hacía pasar por dos temas distintos.
#
# El gráfico a todo el ancho: en una columna del sesenta por ciento, las marcas del
# eje salían rotadas en diagonal y la leyenda se apilaba dentro del área de datos.
with st.container(border=True):
    # Se lee el dibujo, sin hablar de ejes ni de columnas. La última frase es el caso
    # que la lista acaba de contar, dicho ahora en términos del gráfico; quién está
    # marcado con nombre lo dice la leyenda, y repetirlo aquí sobraba.
    st.markdown(
        "<div class='rotulo'>Intensidad frente a alcance</div>"
        "<div class='nota' style='margin-bottom:4px'>Cada punto es una unidad. Cuanto "
        "más arriba, mayor es su porcentaje en niveles críticos; cuanto más a la "
        "derecha, más estudiantes tiene. El tamaño del punto son los estudiantes en "
        "niveles críticos, que es el alcance, y por eso un punto más abajo que otro "
        "puede ser más grande.</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        figura_dispersion(
            prioridad.universo,
            set(tabla["codigo"]),
            destacada,
            float(poblacion_minima) if poblacion_minima else None,
            float(intensidad_minima) if intensidad_minima else None,
            tabla.iloc[0] if len(tabla) else None,
        ),
        width="stretch",
        config={"displayModeBar": False},
    )

    if destacada is not None:
        # El caso del desacuerdo, en cifras y no en un párrafo: lo que importa de él
        # es el contraste entre los dos puestos, que antes había que ir a buscar a la
        # tercera línea del texto.
        sube = int(destacada["desacuerdo"]) > 0
        cifras_tension = "".join(
            f"<div style='flex:0 0 auto'>"
            f"<div style='font-size:1.5rem;font-weight:700;line-height:1.1;"
            f"color:{color}'>{valor}</div>"
            f"<div class='nota' style='font-size:0.74rem'>{rotulo}</div></div>"
            for valor, rotulo, color in (
                (
                    f"{int(destacada['pos_intensidad'])}.ª",
                    "por intensidad",
                    theme.TEXTO if sube else theme.ACENTO,
                ),
                (
                    f"{int(destacada['pos_alcance'])}.ª",
                    "por alcance",
                    theme.ACENTO if sube else theme.TEXTO,
                ),
                (
                    cp.formato(destacada["intensidad"], 1, " %"),
                    "en niveles críticos",
                    theme.TEXTO,
                ),
                (
                    cp.entero(destacada["alcance"]),
                    "estudiantes en niveles críticos",
                    theme.TEXTO,
                ),
            )
        )
        st.markdown(
            f"<div style='margin-top:14px;padding-top:14px;"
            f"border-top:1px solid {theme.BORDE_SUAVE}'>"
            "<div class='rotulo'>Donde los dos criterios no coinciden</div>"
            f"<div style='font-weight:700;font-size:1rem;"
            f"color:{theme.CONTRASTE}'>{destacada['nombre']}</div>"
            f"<div class='nota' style='margin-bottom:12px'>{destacada['ambito']}, "
            f"{cp.entero(destacada['poblacion'])} estudiantes estimados</div>"
            f"<div style='display:flex;gap:34px;flex-wrap:wrap'>{cifras_tension}</div>"
            # El porqué del desacuerdo es el tamaño, y eso no se deducía de la frase
            # anterior, que describía los dos órdenes en abstracto. Se cuenta con las
            # cifras de esta unidad, que son las que lo explican.
            f"<div class='nota' style='margin-top:12px'>"
            f"Su {cp.formato(destacada['intensidad'], 1, ' %')} la deja "
            f"{int(destacada['pos_intensidad'])}.ª por intensidad, pero sobre "
            f"{cp.entero(destacada['poblacion'])} estudiantes ese porcentaje son "
            f"{cp.entero(destacada['alcance'])}, y eso la pone "
            f"{int(destacada['pos_alcance'])}.ª por alcance.</div>"
            # Hasta aquí el bloque contaba el desacuerdo y lo dejaba ahí, y faltaba
            # decir qué se hace con él. Lo que falta no es una recomendación: cuál de
            # los dos órdenes vale es una decisión de política, y resolverla desde la
            # pantalla la haría pasar por un resultado del dato. Lo que sí se puede
            # decir es con qué se decide, y dónde queda esta unidad según cada
            # medida. Que el dato no elige entre las dos no hace falta escribirlo:
            # la frase lo deja claro al poner las dos a la par.
            f"<div style='margin-top:12px;margin-bottom:14px;padding:11px 13px;"
            f"background:{theme.SUPERFICIE_HUNDIDA};border-radius:8px'>"
            "<div class='rotulo'>Qué hay que decidir</div>"
            f"<div class='nota'>Si el programa se mide por estudiantes atendidos, "
            f"esta unidad es la {int(destacada['pos_alcance'])}.ª de las "
            f"{cp.entero(n_priorizadas)}; si se mide por la proporción en niveles "
            f"críticos, la {int(destacada['pos_intensidad'])}.ª.</div></div></div>",
            unsafe_allow_html=True,
        )

cp.separador()

cobertura = focalizacion.cobertura_acumulada(prioridad)

with st.container(border=True):
    st.markdown("**Cobertura acumulada**")
    st.markdown(
        "<div class='nota'>¿Hasta dónde llega una intervención que no alcanza a "
        "todas las unidades de la lista? El control de abajo elige cuántas de las "
        "primeras se atienden, y cada barra es a cuántos estudiantes en niveles "
        "críticos se llega con esas.</div>",
        unsafe_allow_html=True,
    )

    if n_priorizadas > 1:
        atendidas = st.slider(
            "Unidades atendidas",
            min_value=1,
            max_value=n_priorizadas,
            value=min(3, n_priorizadas),
            help="Mueve el corte para ver cuántos estudiantes alcanza atender las "
                 "primeras "
            "unidades del orden.",
        )
    else:
        atendidas = 1
        st.caption("Con una sola unidad priorizada no hay corte que mover.")

    fila = cobertura.iloc[atendidas - 1]
    alcanzados = focalizacion.ninos_alcanzados(prioridad, atendidas)
    parte_seleccion = (
        100.0 * alcanzados / prioridad.alcance_total
        if prioridad.alcance_total > 0
        else 0.0
    )

    col_cifra, col_lectura = st.columns([1, 2], gap="medium")
    with col_cifra:
        cp.tarjeta_metrica(
            f"Estudiantes alcanzados con {cp.entero(atendidas)} "
            + ("unidad" if atendidas == 1 else "unidades"),
            cp.entero(alcanzados),
            f"{cp.formato(parte_seleccion, 1, ' %')} de los "
            f"{cp.entero(prioridad.alcance_total)} de la selección",
        )
    with col_lectura:
        # La cifra y su parte de la selección ya están en la tarjeta de al lado, así
        # que aquí va lo que ella no puede decir: qué unidades son, cuánto cambia esa
        # cifra con otro criterio, y las otras dos lecturas de "alcanzar". Antes las
        # tres iban en un párrafo que terminaba advirtiendo que no se confundieran,
        # que es pedirle al lector el trabajo de separarlas.
        nombres = nombrar_las_primeras(
            [str(n) for n in cobertura["nombre"].head(atendidas)],
            atendidas == n_priorizadas,
        )
        rival, mejor = criterio_que_alcanza_mas(tabla, criterio, atendidas)
        if atendidas == n_priorizadas:
            # Con la lista entera atendida, los tres criterios suman lo mismo. Decirlo
            # evita que la ausencia de comparación parezca un olvido.
            contraste = (
                " Es la lista completa, así que aquí los tres criterios suman lo "
                "mismo: el orden decide por cuál se empieza, no cuántas se atienden."
            )
        elif rival:
            contraste = (
                f" Con las mismas {cp.unidades(atendidas)}, el orden {EN_FRASE[rival]} "
                f"llegaría a {cp.entero(mejor)}."
            )
        else:
            contraste = (
                " Ningún otro criterio alcanza a más estudiantes con "
                f"{cp.unidades(atendidas)}."
            )
        st.markdown(
            f"<div class='nota'>{nombres}{contraste}</div>"
            f"<div class='nota' style='margin-top:10px'>Entre las "
            f"{cp.entero(atendidas)} reúnen {cp.entero(fila['acum_poblacion'])} "
            f"estudiantes en total, y los {cp.entero(alcanzados)} en niveles críticos "
            f"son el {cp.formato(fila['pct_cobertura'], 1, ' %')} de todos los del "
            "universo evaluado.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.plotly_chart(
        figura_cobertura(cobertura, atendidas),
        width="stretch",
        config={"displayModeBar": False},
    )

with st.expander(
    f"Ver las {cp.entero(len(prioridad.descartadas))} unidades que quedaron fuera y su "
    "motivo"
):
    st.dataframe(
        tabla_descartes(prioridad.descartadas),
        width="stretch",
        hide_index=True,
        height=320,
    )
    st.caption(
        "Los umbrales de niveles críticos y de población son decisiones de política: "
        "moverlos "
        "cambia la lista."
    )

cp.pie_de_pagina()
