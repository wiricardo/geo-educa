"""Panorama general de la ENLA 2025.

Da la lectura de conjunto antes de que el usuario entre al mapa: cuánto mide la
evaluación, dónde queda el nivel Satisfactorio en los tres grados, cómo se ha movido la
medida promedio de 4.° de primaria desde 2016 y qué proporción de estudiantes queda a
cada lado de la línea que separa los niveles críticos del resto.

Todas las cifras de esta página son nacionales, que es el nivel para el que los tres
grados tienen representatividad. Por eso no hace falta la advertencia de
representatividad, que solo aplica a los cortes por debajo del país. El grado y el área
de la barra lateral no recortan nada aquí: destacan la serie que les corresponde.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import componentes as cp
from core import config, estado, theme
from geoeduca import almacen

# Un color por área evaluada, estable en los dos gráficos de líneas de la página.
COLOR_AREA: dict[str, str] = {
    "L": theme.ACENTO,
    "M": theme.CONTRASTE,
    "CN": theme.TERCERO,
}

CONFIG_PLOTLY = {"displayModeBar": False, "scrollZoom": False}


def figura_base(alto: int, margen: dict) -> go.Figure:
    """Lienzo sobrio y sin plantilla, para que el tema de la aplicación sea el único."""
    figura = go.Figure()
    figura.update_layout(
        template="none",
        height=alto,
        margin=margen,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=theme.FUENTE, size=12, color=theme.TEXTO),
        hoverlabel=dict(
            font=dict(family=theme.FUENTE, size=13, color=theme.TEXTO),
            bgcolor=theme.SUPERFICIE,
            bordercolor=theme.BORDE,
        ),
        showlegend=False,
    )
    return figura


def separar_etiquetas(valores: list[float], separacion: float) -> list[float]:
    """Aparta las etiquetas que quedarían una encima de otra, conservando el orden.

    Devuelve la posición vertical en la que dibujar cada etiqueta, que no siempre es la
    del punto: cuando dos valores están muy juntos, el texto se desplaza lo mínimo para
    que ambos se lean. Los valores en sí no se tocan.
    """
    orden = sorted(range(len(valores)), key=lambda i: valores[i])
    posiciones = list(valores)
    for puesto, indice in enumerate(orden[1:], start=1):
        anterior = posiciones[orden[puesto - 1]]
        if posiciones[indice] - anterior < separacion:
            posiciones[indice] = anterior + separacion
    return posiciones


@st.cache_data(show_spinner=False)
def cifras_generales() -> dict[str, int]:
    """Tamaño de la evaluación, consultado al almacén en lugar de escrito a mano."""
    fila = almacen.consultar(
        """
        select
            (select count(distinct id_estudiante) from hechos_estudiante_area)
                as estudiantes,
            (select count(*) from dim_ie)           as escuelas,
            (select count(*) from dim_departamento) as regiones,
            (select count(*) from dim_distrito)     as distritos
        """
    ).iloc[0]
    return {clave: int(valor) for clave, valor in fila.items()}


@st.cache_data(show_spinner=False)
def extremos_regionales() -> pd.DataFrame:
    """La región que mejor y peor queda en cada grado y área, con el país en medio.

    Solo 4.° de primaria y 2.° de secundaria. La muestra de 5.° no se diseñó para dar
    resultados por región, así que poner aquí sus extremos sería afirmar algo que el
    dato no sostiene, y esta página no lleva la advertencia porque todo lo demás es
    nacional.
    """
    filas = []
    for grado in ("4P", "2S"):
        for area in ("L", "M"):
            tabla = estado.resultados("departamento", grado, area)
            tabla = tabla.dropna(subset=["pct_satisfactorio"])
            if tabla.empty:
                continue
            peor = tabla.loc[tabla["pct_satisfactorio"].idxmin()]
            mejor = tabla.loc[tabla["pct_satisfactorio"].idxmax()]
            pais = estado.nacional(grado, area)
            filas.append({
                "grado": grado,
                "cod_area": area,
                "peor_nombre": str(peor["nom_unidad"]).title(),
                "peor": float(peor["pct_satisfactorio"]),
                "mejor_nombre": str(mejor["nom_unidad"]).title(),
                "mejor": float(mejor["pct_satisfactorio"]),
                "pais": float(pais["pct_satisfactorio"]) if pais is not None else float("nan"),
            })
    return pd.DataFrame(filas)


def dibujar_mancuerna(
    filas: pd.DataFrame,
    izquierda: tuple[str, str, str],
    derecha: tuple[str, str, str],
    texto_izquierda,
    texto_derecha,
) -> go.Figure:
    """Dos puntos por fila unidos por una línea, donde el largo de la línea es el dato.

    Cada extremo llega como (columna, nombre de la serie, color). El texto de fuera se
    pasa como función de la fila, porque en unos bloques es la cifra y en otros el
    nombre de la región con su cifra.
    """
    eje = [
        [config.nombre_grado(g) for g in filas["grado"]],
        [config.nombre_area(a) for a in filas["cod_area"]],
    ]
    figura = figura_base(124 + 46 * len(filas), dict(l=208, r=120, t=48, b=40))

    for i, fila in filas.reset_index(drop=True).iterrows():
        figura.add_shape(
            type="line",
            x0=fila[izquierda[0]], x1=fila[derecha[0]], y0=i, y1=i,
            line=dict(color=theme.BORDE, width=3),
            layer="below",
        )
        # Las cifras van por fuera de los dos puntos: entre ellos no caben cuando la
        # distancia es corta y se solaparían con los propios marcadores.
        figura.add_annotation(
            x=fila[izquierda[0]], y=i, text=texto_izquierda(fila),
            showarrow=False, xanchor="right", xshift=-12,
            font=dict(size=11.5, color=izquierda[2]),
        )
        figura.add_annotation(
            x=fila[derecha[0]], y=i, text=texto_derecha(fila),
            showarrow=False, xanchor="left", xshift=12,
            font=dict(size=11.5, color=derecha[2]),
        )

    for columna, nombre, color in (izquierda, derecha):
        figura.add_trace(
            go.Scatter(
                x=list(filas[columna]), y=eje, mode="markers", name=nombre,
                marker=dict(color=color, size=13),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=[
                    f"{config.nombre_area(a)}, {config.nombre_grado(g)}, "
                    f"{nombre.lower()}: {cp.formato(v, 1, ' %')}"
                    for g, a, v in zip(filas["grado"], filas["cod_area"], filas[columna])
                ],
            )
        )

    # El aire de los lados se mide contra el propio eje y no en una cantidad fija: con
    # un punto cerca de cero, como el 2,1 % de Loreto, la etiqueta de fuera se metía
    # encima del nombre del área.
    tope = max(float(filas[izquierda[0]].max()), float(filas[derecha[0]].max()))
    # Las marcas se fijan a mano y desde cero: con el margen de la izquierda metido en
    # el rango, Plotly llegaba a rotular un "-10 %", que no quiere decir nada.
    marcas = list(range(0, int(tope) + 10, 10))
    figura.update_xaxes(
        range=[-0.19 * tope, tope * 1.26],
        tickvals=marcas,
        showgrid=False, zeroline=False, showline=True, linecolor=theme.BORDE,
        ticks="outside", tickcolor=theme.BORDE, ticklen=4, ticksuffix=" %",
        tickfont=dict(size=11.5, color=theme.TEXTO_SECUNDARIO),
    )
    figura.update_yaxes(
        autorange="reversed", showgrid=False, zeroline=False, showline=False,
        tickfont=dict(size=12, color=theme.TEXTO),
    )
    figura.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0,
            font=dict(size=11.5, color=theme.TEXTO_SECUNDARIO),
        ),
    )
    return figura


@st.cache_data(show_spinner=False)
def brecha_por_dimension(dimension: str) -> pd.DataFrame:
    """Nivel Satisfactorio de los dos grupos de una dimensión, por grado y área.

    Sale de la tabla `brechas`, que la ingesta construye ponderando con el diseño
    muestral. Solo Lectura y Matemática, que son las dos áreas evaluadas en los tres
    grados: incluir Ciencia y Tecnología, que falta en 4.° de primaria, dejaría filas
    huecas y rompería la comparación entre grados.

    Las columnas salen como `grupo_a` y `grupo_b` y no con el nombre de cada categoría,
    para que los tres cortes se dibujen con el mismo código.
    """
    tabla = almacen.consultar(
        """
        select grado, grado_etq, cod_area, area_evaluada,
               categoria_a, categoria_b,
               pct_satisfactorio_a as grupo_a,
               pct_satisfactorio_b as grupo_b
        from brechas
        where dimension = ? and cod_area in ('L', 'M')
        """,
        [dimension],
    )
    orden_grado = {g: i for i, g in enumerate(config.GRADOS)}
    orden_area = {a: i for i, a in enumerate(("L", "M"))}
    tabla["_orden"] = (
        tabla["grado"].map(orden_grado) * 10 + tabla["cod_area"].map(orden_area)
    )
    tabla = tabla.sort_values("_orden").reset_index(drop=True)
    tabla["etiqueta"] = [
        f"{config.nombre_area(a)}, {config.nombre_grado(g)}"
        for g, a in zip(tabla["grado"], tabla["cod_area"])
    ]
    return tabla


@st.cache_data(show_spinner=False)
def tabla_nacional() -> pd.DataFrame:
    """Una fila por grado y área con el resultado nacional."""
    filas = [
        estado.nacional(grado, area)
        for grado in config.GRADOS
        for area in config.areas_de(grado)
    ]
    return pd.DataFrame([fila for fila in filas if fila is not None]).reset_index(
        drop=True
    )


def valor_nacional(tabla: pd.DataFrame, grado: str, area: str, columna: str) -> float:
    """Una métrica nacional, sin redondear."""
    fila = tabla[(tabla["grado"] == grado) & (tabla["cod_area"] == area)]
    return float(fila.iloc[0][columna]) if len(fila) else float("nan")


cp.encabezado(
    "Panorama",
    "Resultados nacionales de 4.° de primaria, 2.° y 5.° de secundaria, "
    "evaluados en 2025",
)

nacionales = tabla_nacional()
if nacionales.empty:
    st.warning("No hay resultados nacionales disponibles.")
    st.stop()


# 1. Las cuatro cifras que dimensionan la evaluación ---------------------------------

# Sin encabezado: cada tarjeta trae su rótulo y su pie, así que un título encima solo
# repetiría lo que ya se lee, y la página gana que lo primero sean las cifras.
cifras = cifras_generales()

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

cp.igualar_tarjetas()
col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    cp.tarjeta_metrica(
        "Estudiantes evaluados",
        cp.entero(cifras["estudiantes"]),
        "En los tres grados",
    )
with col_b:
    cp.tarjeta_metrica(
        "Escuelas",
        cp.entero(cifras["escuelas"]),
        "Contadas por grado",
    )
with col_c:
    cp.tarjeta_metrica(
        "Regiones",
        cp.entero(cifras["regiones"]),
        "Todas con escuelas evaluadas",
    )
with col_d:
    cp.tarjeta_metrica(
        "Distritos",
        cp.entero(cifras["distritos"]),
        "Con al menos una escuela",
    )

st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)


# 2. El nivel Satisfactorio en los tres grados ---------------------------------------

cp.seccion(
    "Nivel Satisfactorio por grado",
    "Porcentaje de estudiantes que alcanza lo esperado para su ciclo, en cada grado y "
    "área evaluada.",
)

GRADOS_ORDEN = list(config.GRADOS)
POSICION = {grado: i for i, grado in enumerate(GRADOS_ORDEN)}

pendiente = figura_base(440, dict(l=120, r=120, t=46, b=30))

# Reglas verticales en cada grado: ayudan a leer la pendiente sin convertirse en una
# cuadrícula.
for grado in GRADOS_ORDEN:
    pendiente.add_shape(
        type="line",
        x0=POSICION[grado],
        x1=POSICION[grado],
        y0=0,
        y1=38,
        line=dict(color=theme.BORDE, width=1),
        layer="below",
    )

etiquetas_derecha: list[tuple[str, float, str]] = []

for area, color in COLOR_AREA.items():
    grados_area = [g for g in GRADOS_ORDEN if area in config.GRADOS[g].areas]
    puntos = [
        (POSICION[grado], valor_nacional(nacionales, grado, area, "pct_satisfactorio"))
        for grado in grados_area
    ]
    if len(puntos) < 2:
        continue

    destacada = False
    pendiente.add_trace(
        go.Scatter(
            x=[x for x, _ in puntos],
            y=[y for _, y in puntos],
            mode="lines+markers",
            name=config.nombre_area(area),
            line=dict(color=color, width=3.2 if destacada else 2),
            marker=dict(color=color, size=10 if destacada else 8),
            opacity=1 if destacada else 0.78,
            hovertemplate="%{customdata}<extra></extra>",
            customdata=[
                f"{config.nombre_area(area)}, {config.nombre_grado(grado)}: "
                f"{cp.formato(y, 1, ' %')}"
                for grado, (_, y) in zip(grados_area, puntos)
            ],
        )
    )

    x_inicio, y_inicio = puntos[0]
    if x_inicio == 0:
        # La línea arranca en el primer grado: la etiqueta cabe a su izquierda.
        pendiente.add_annotation(
            x=-0.06,
            y=y_inicio,
            text=f"<b>{config.nombre_area(area)}</b> {cp.formato(y_inicio, 1, ' %')}",
            showarrow=False,
            xanchor="right",
            font=dict(size=12, color=color),
        )
    else:
        # Empieza a mitad del gráfico, donde las otras dos líneas pasan cerca: la
        # etiqueta va encima del punto y sobre el color del fondo, para que el texto se
        # lea aunque una línea le pase por detrás.
        pendiente.add_annotation(
            x=x_inicio,
            y=y_inicio,
            yshift=20,
            text=f"<b>{config.nombre_area(area)}</b> {cp.formato(y_inicio, 1, ' %')}",
            showarrow=False,
            xanchor="center",
            font=dict(size=12, color=color),
            bgcolor=theme.FONDO,
            borderpad=3,
        )

    x_fin, y_fin = puntos[-1]
    etiquetas_derecha.append((cp.formato(y_fin, 1, " %"), y_fin, color))

# Los tres valores de 5.° de secundaria quedan muy juntos, así que sus etiquetas se
# apartan lo justo para leerse. El punto dibujado sigue en su sitio.
alturas = separar_etiquetas([y for _, y, _ in etiquetas_derecha], 1.9)
for (texto, _, color), altura in zip(etiquetas_derecha, alturas):
    pendiente.add_annotation(
        x=len(GRADOS_ORDEN) - 1 + 0.06,
        y=altura,
        text=texto,
        showarrow=False,
        xanchor="left",
        font=dict(size=12, color=color),
    )

pendiente.update_xaxes(
    tickvals=list(POSICION.values()),
    ticktext=[config.nombre_grado(g) for g in GRADOS_ORDEN],
    range=[-0.42, len(GRADOS_ORDEN) - 1 + 0.42],
    showgrid=False,
    zeroline=False,
    showline=False,
    ticks="",
    tickfont=dict(size=12.5, color=theme.TEXTO_SECUNDARIO),
)
pendiente.update_yaxes(
    range=[0, 38],
    showgrid=False,
    zeroline=False,
    showline=False,
    showticklabels=False,
)

st.plotly_chart(pendiente, config=CONFIG_PLOTLY, theme=None)

st.markdown(
    "<div class='aviso'>Son tres muestras distintas tomadas el mismo año. El gráfico "
    "compara grados entre sí, no mide progreso."
    "<div style='margin-top:9px'>Ciudadanía no aparece: solo se evaluó en 5.° de "
    "secundaria.</div></div>",
    unsafe_allow_html=True,
)

st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)


# 3. El mismo resultado, separado por ámbito de la escuela --------------------------

brechas_ambito = brecha_por_dimension("ambito")

cp.seccion(
    "Urbano y rural",
    "Cuántos alcanzan lo esperado según si su escuela está en zona urbana o rural.",
)

# Eje de dos niveles: el grado se escribe una vez por par en lugar de repetirse en
# cada fila. Con las seis etiquetas completas, este gráfico y el de abajo listaban lo
# mismo seguido y parecían el mismo gráfico dos veces.
eje_agrupado = [
    [config.nombre_grado(g) for g in brechas_ambito["grado"]],
    [config.nombre_area(a) for a in brechas_ambito["cod_area"]],
]

# El margen de arriba deja sitio a la leyenda, que va fuera del área de trazado.
mancuerna = figura_base(124 + 46 * len(brechas_ambito), dict(l=208, r=96, t=48, b=40))

for fila_i, fila in brechas_ambito.iterrows():
    # La línea que une los dos puntos es la brecha: su largo es el dato, no un adorno.
    mancuerna.add_shape(
        type="line",
        x0=fila["grupo_b"], x1=fila["grupo_a"], y0=fila_i, y1=fila_i,
        line=dict(color=theme.BORDE, width=3),
        layer="below",
    )
    # Las cifras van por fuera de los dos puntos y no entre ellos: donde la brecha es
    # estrecha no cabrían y se solaparían con los propios marcadores.
    mancuerna.add_annotation(
        x=fila["grupo_b"], y=fila_i, text=cp.formato(fila["grupo_b"], 1),
        showarrow=False, xanchor="right", xshift=-12,
        font=dict(size=11.5, color=theme.CONTRASTE),
    )
    mancuerna.add_annotation(
        x=fila["grupo_a"], y=fila_i, text=cp.formato(fila["grupo_a"], 1, " %"),
        showarrow=False, xanchor="left", xshift=12,
        font=dict(size=11.5, color=theme.ACENTO),
    )

for nombre, columna, color in (
    ("Escuela rural", "grupo_b", theme.CONTRASTE),
    ("Escuela urbana", "grupo_a", theme.ACENTO),
):
    mancuerna.add_trace(
        go.Scatter(
            x=list(brechas_ambito[columna]),
            y=eje_agrupado,
            mode="markers",
            name=nombre,
            marker=dict(color=color, size=13),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=[
                f"{etq}, {nombre.lower()}: {cp.formato(v, 1, ' %')}"
                for etq, v in zip(brechas_ambito["etiqueta"], brechas_ambito[columna])
            ],
        )
    )

mancuerna.update_xaxes(
    range=[-4, float(brechas_ambito["grupo_a"].max()) + 12],
    showgrid=False, zeroline=False, showline=True, linecolor=theme.BORDE,
    ticks="outside", tickcolor=theme.BORDE, ticklen=4, ticksuffix=" %",
    tickfont=dict(size=11.5, color=theme.TEXTO_SECUNDARIO),
)
mancuerna.update_yaxes(
    autorange="reversed",
    showgrid=False, zeroline=False, showline=False,
    tickfont=dict(size=12, color=theme.TEXTO),
)
# El lienzo base no dibuja leyenda, porque los demás gráficos de la página rotulan sus
# series dentro. Aquí sí hace falta: sin ella no se sabe qué punto es cuál.
mancuerna.update_layout(
    showlegend=True,
    legend=dict(
        orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0,
        font=dict(size=11.5, color=theme.TEXTO_SECUNDARIO),
    ),
)

st.plotly_chart(mancuerna, config=CONFIG_PLOTLY, theme=None)

peor = brechas_ambito.loc[brechas_ambito["grupo_b"].idxmin()]
st.caption(
    "La distancia entre los dos puntos es la brecha. En "
    f"{config.nombre_area(peor['cod_area'])} de {config.nombre_grado(peor['grado'])} "
    f"alcanza el nivel esperado el {cp.formato(peor['grupo_b'], 1, ' %')} de los "
    f"estudiantes de escuela rural, frente al {cp.formato(peor['grupo_a'], 1, ' %')} de "
    "los de escuela urbana. El margen de error de cada cifra está en Brechas."
)

st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)


# 4. Barras divergentes sobre la línea compartida ------------------------------------

cp.seccion(
    "Distribución por nivel de logro",
    "A la izquierda, quienes no llegan (Previo al inicio más En inicio). A la derecha, "
    "quienes al menos están En proceso.",
)

AREAS_COMUNES = ("L", "M")
filas = [
    (grado, area)
    for grado in GRADOS_ORDEN
    for area in AREAS_COMUNES
    if area in config.GRADOS[grado].areas
]

# Orden de izquierda a derecha dentro de cada barra: los niveles pegados a la línea son
# los que están más cerca de cruzarla, y la intensidad crece hacia afuera.
SEGMENTOS = [
    ("pct_en_inicio", 1, -1),
    ("pct_previo_inicio", 0, -1),
    ("pct_en_proceso", 2, 1),
    ("pct_satisfactorio", 3, 1),
]

# El mismo eje de dos niveles que el gráfico de arriba, y en el mismo orden, para que
# las dos lecturas se puedan seguir fila a fila.
eje_divergente = [
    [config.nombre_grado(grado) for grado, _ in filas],
    [config.nombre_area(area) for _, area in filas],
]
divergente = figura_base(60 + 46 * len(filas), dict(l=208, r=70, t=14, b=38))

for columna, nivel, signo in SEGMENTOS:
    valores = [valor_nacional(nacionales, g, a, columna) for g, a in filas]
    divergente.add_trace(
        go.Bar(
            orientation="h",
            y=eje_divergente,
            x=[signo * v for v in valores],
            name=config.NIVELES_LOGRO[nivel],
            marker=dict(
                color=theme.NIVELES[nivel],
                line=dict(color=theme.BORDE, width=0.5),
            ),
            customdata=[
                f"{config.NIVELES_LOGRO[nivel]}: {cp.formato(v, 1, ' %')}"
                for v in valores
            ],
            hovertemplate="%{customdata}<extra></extra>",
        )
    )

for posicion, (grado, area) in enumerate(filas):
    criticos = valor_nacional(nacionales, grado, area, "pct_critico")
    al_menos = valor_nacional(nacionales, grado, area, "pct_al_menos_proceso")
    divergente.add_annotation(
        x=-criticos,
        y=posicion,
        xshift=-6,
        text=cp.formato(criticos, 1, " %"),
        showarrow=False,
        xanchor="right",
        font=dict(size=11.5, color=theme.TEXTO_SECUNDARIO),
    )
    divergente.add_annotation(
        x=al_menos,
        y=posicion,
        xshift=6,
        text=cp.formato(al_menos, 1, " %"),
        showarrow=False,
        xanchor="left",
        font=dict(size=11.5, color=theme.TEXTO_SECUNDARIO),
    )

divergente.update_layout(barmode="relative", bargap=0.34)
divergente.add_vline(x=0, line_width=1.6, line_color=theme.TEXTO)
divergente.update_xaxes(
    range=[-96, 96],
    tickvals=[-80, -60, -40, -20, 0, 20, 40, 60, 80],
    ticktext=[cp.formato(abs(v), 0, " %") for v in (-80, -60, -40, -20, 0, 20, 40, 60, 80)],
    showgrid=False,
    zeroline=False,
    showline=False,
    ticks="",
    tickfont=dict(size=11, color=theme.TEXTO_TENUE),
)
divergente.update_yaxes(
    autorange="reversed",
    showgrid=False,
    zeroline=False,
    showline=False,
    ticks="",
    tickfont=dict(size=12, color=theme.TEXTO),
)

st.plotly_chart(divergente, config=CONFIG_PLOTLY, theme=None)
cp.leyenda_niveles()
st.caption(
    "Ciencia y Tecnología no se evalúa en 4.° de primaria, así que este gráfico y el "
    "anterior solo llevan Lectura y Matemática."
)


# 5. La distancia entre regiones, que es la mayor de todas -----------------------------

regiones = extremos_regionales()

cp.seccion(
    "De una región a otra",
    "La región donde menos estudiantes alcanzan lo esperado y la región donde más, en "
    "cada grado y área. El país queda en algún punto entre las dos.",
)

if not regiones.empty:
    rango = dibujar_mancuerna(
        regiones,
        ("peor", "Región con menos", theme.CONTRASTE),
        ("mejor", "Región con más", theme.ACENTO),
        lambda f: f"{f['peor_nombre']} {cp.formato(f['peor'], 1)}",
        lambda f: f"{cp.formato(f['mejor'], 1, ' %')} {f['mejor_nombre']}",
    )
    # El país, dentro del rango: sin él la línea no dice de qué lado cae la mayoría.
    rango.add_trace(
        go.Scatter(
            x=list(regiones["pais"]),
            y=[
                [config.nombre_grado(g) for g in regiones["grado"]],
                [config.nombre_area(a) for a in regiones["cod_area"]],
            ],
            mode="markers",
            name="País",
            marker=dict(color=theme.TEXTO, size=9, symbol="line-ns-open",
                        line=dict(color=theme.TEXTO, width=2.4)),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=[
                f"País: {cp.formato(v, 1, ' %')}" for v in regiones["pais"]
            ],
        )
    )
    st.plotly_chart(rango, config=CONFIG_PLOTLY, theme=None)

    ancho = regiones.loc[(regiones["mejor"] - regiones["peor"]).idxmax()]
    distancia = ancho["mejor"] - ancho["peor"]
    ambito_misma = brechas_ambito[
        (brechas_ambito["grado"] == ancho["grado"])
        & (brechas_ambito["cod_area"] == ancho["cod_area"])
    ]
    comparacion = ""
    if len(ambito_misma):
        hueco = abs(
            float(ambito_misma.iloc[0]["grupo_a"]) - float(ambito_misma.iloc[0]["grupo_b"])
        )
        comparacion = (
            f" Entre escuela urbana y rural, en ese mismo corte, hay "
            f"{cp.formato(hueco, 1)} puntos: la región pesa "
            f"{cp.formato(distancia / hueco, 1)} veces más."
        )
    st.caption(
        f"La distancia más larga está en {config.nombre_area(ancho['cod_area'])} de "
        f"{config.nombre_grado(ancho['grado'])}: {cp.formato(distancia, 1)} puntos "
        f"entre {ancho['peor_nombre']} y {ancho['mejor_nombre']}.{comparacion} "
        "5.° de secundaria no aparece aquí porque su evaluación se diseñó para dar la "
        "cifra del país, no la de cada región."
    )

st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)


# 6. La escuela pública y la privada ---------------------------------------------------

brechas_gestion = brecha_por_dimension("gestion")

cp.seccion(
    "Escuela pública y privada",
    "Cuántos alcanzan lo esperado en cada una. La distancia no es la misma en todos "
    "los grados.",
)

if not brechas_gestion.empty:
    st.plotly_chart(
        dibujar_mancuerna(
            brechas_gestion,
            ("grupo_b", "Escuela pública", theme.CONTRASTE),
            ("grupo_a", "Escuela privada", theme.ACENTO),
            lambda f: cp.formato(f["grupo_b"], 1),
            lambda f: cp.formato(f["grupo_a"], 1, " %"),
        ),
        config=CONFIG_PLOTLY,
        theme=None,
    )

    primaria = brechas_gestion[
        (brechas_gestion["grado"] == "4P") & (brechas_gestion["cod_area"] == "M")
    ]
    quinto = brechas_gestion[
        (brechas_gestion["grado"] == "5S") & (brechas_gestion["cod_area"] == "M")
    ]
    sexo = brecha_por_dimension("sexo")
    sexo_m = sexo[(sexo["grado"] == "4P") & (sexo["cod_area"] == "M")]
    sexo_l = sexo[(sexo["grado"] == "4P") & (sexo["cod_area"] == "L")]

    partes = []
    if len(primaria) and len(quinto):
        d4 = abs(float(primaria.iloc[0]["grupo_a"]) - float(primaria.iloc[0]["grupo_b"]))
        d5 = abs(float(quinto.iloc[0]["grupo_a"]) - float(quinto.iloc[0]["grupo_b"]))
        partes.append(
            f"En Matemática la distancia pasa de {cp.formato(d4, 1)} puntos en 4.° de "
            f"primaria a {cp.formato(d5, 1)} en 5.° de secundaria."
        )
    if len(sexo_m) and len(sexo_l):
        dm = abs(float(sexo_m.iloc[0]["grupo_a"]) - float(sexo_m.iloc[0]["grupo_b"]))
        dl = abs(float(sexo_l.iloc[0]["grupo_a"]) - float(sexo_l.iloc[0]["grupo_b"]))
        partes.append(
            f"Entre hombres y mujeres la distancia es mucho menor y cambia de signo "
            f"según el área: en 4.° de primaria son {cp.formato(dm, 1)} puntos a favor "
            f"de los hombres en Matemática y {cp.formato(dl, 1)} a favor de las mujeres "
            "en Lectura."
        )
    partes.append("El margen de error de cada cifra está en Brechas.")
    st.caption(" ".join(partes))


cp.pie_de_pagina()
