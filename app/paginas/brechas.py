"""Brechas entre grupos, con la precisión de la estimación a la vista.

Es la primera página que no se queda en el valor puntual. El almacén trae las cifras ya
ponderadas, pero no su error estándar: eso exige volver al microdato y estimarlo con el
diseño muestral real, que es lo que hace `geoeduca.muestreo`. De ahí salen las dos cosas
que esta página añade al resto de la aplicación: si una diferencia entre dos grupos es
estadísticamente significativa y qué margen acompaña al resultado de cada región.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import componentes as cp
from core import config, estado, theme
from geoeduca import muestreo

# Cada indicador del catálogo se calcula sobre una columna distinta del microdato: la
# medida promedio es una razón ponderada, y los otros dos son proporciones de una
# condición que el almacén ya trae marcada estudiante por estudiante.
MICRODATO: dict[str, tuple[str, bool]] = {
    "medida_promedio": ("medida500", False),
    "pct_satisfactorio": ("es_satisfactorio", True),
    "pct_critico": ("es_critico", True),
}

# Las tres comparaciones de la fila de tarjetas, con su rótulo, la columna del microdato
# y los dos grupos. El orden de la resta es el mismo que usa la tabla de brechas del
# almacén: primero el lado históricamente aventajado. La dimensión urbana o rural se
# llama ámbito y no área, para no confundirla con el área evaluada.
COMPARACIONES: tuple[tuple[str, str, str, str, str], ...] = (
    ("Ámbito", "Urbana o rural", "ambito", "Urbana", "Rural"),
    ("Gestión", "Pública o privada", "gestion", "Privada", "Publica"),
    ("Sexo", "Hombre o mujer", "sexo", "Hombre", "Mujer"),
)

# En el microdato las categorías vienen sin tildes. Para mostrarlas se corrigen aquí.
ETIQUETA_CATEGORIA: dict[str, str] = {"Publica": "Pública"}

# Cómo se nombra cada grupo dentro de una frase. «Rural» es una etiqueta de base de
# datos, no un sujeto: la tupla trae el sujeto con sus dos verbos y la forma con la que
# se menciona al grupo cuando es el término de la comparación.
GRUPO_EN_FRASE: dict[str, tuple[str, str, str, str]] = {
    "Urbana": ("La escuela urbana", "tiene", "obtiene", "la urbana"),
    "Rural": ("La escuela rural", "tiene", "obtiene", "la rural"),
    "Privada": ("La escuela privada", "tiene", "obtiene", "la privada"),
    "Publica": ("La escuela pública", "tiene", "obtiene", "la pública"),
    "Hombre": ("Los hombres", "tienen", "obtienen", "los hombres"),
    "Mujer": ("Las mujeres", "tienen", "obtienen", "las mujeres"),
}

# Con qué palabras se nombra el indicador dentro de esa frase. El nombre del catálogo
# lleva el signo de porcentaje delante y no se puede incrustar en una oración.
GLOSA_INDICADOR: dict[str, str] = {
    "pct_critico": "estudiantes en niveles críticos",
    "pct_satisfactorio": "estudiantes en nivel Satisfactorio",
    "medida_promedio": "puntos en la medida promedio",
}

# Un icono por comparación, en línea y monocromo. Para sexo se dibujan dos siluetas y
# no los símbolos de Venus y Marte, que sobre una tarjeta de datos pesan más de lo que
# aclaran.
ICONO_COMPARACION: dict[str, str] = {
    "ambito": (
        "<path d='M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11z'/>"
        "<circle cx='12' cy='10' r='2.5'/>"
    ),
    "gestion": (
        "<path d='M3 21h18'/><path d='M5 21V9l7-4.5L19 9v12'/>"
        "<path d='M10 21v-5h4v5'/>"
    ),
    "sexo": (
        "<circle cx='9' cy='8' r='3'/><path d='M3.4 20c0-3.1 2.5-5.6 5.6-5.6"
        "s5.6 2.5 5.6 5.6'/><circle cx='17.4' cy='9.6' r='2.3'/>"
        "<path d='M16.2 14.6c2.4.3 4.4 2.5 4.4 5.4'/>"
    ),
}


def icono(clave: str, color: str) -> str:
    """El icono de una comparación, como SVG en línea."""
    return (
        f"<svg width='36' height='36' viewBox='0 0 24 24' fill='none' stroke='{color}' "
        "stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'>"
        f"{ICONO_COMPARACION[clave]}</svg>"
    )


# Las tres tarjetas se estiran al alto de la más alta y el pie se queda abajo del todo.
# Sin esto, la que necesita un renglón más de intervalo crecía sola y las otras dos
# terminaban en una línea distinta. El `:has` limita la regla a estas columnas.
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
            font=dict(family=theme.FUENTE, size=12.5, color=theme.TEXTO),
            bgcolor=theme.SUPERFICIE,
            bordercolor=theme.BORDE,
            align="left",
        ),
        showlegend=False,
    )
    return figura


def etiqueta(categoria: str) -> str:
    return ETIQUETA_CATEGORIA.get(categoria, categoria)


def frase_de_brecha(
    indicador: config.Indicador, peor: str, mejor: str, magnitud: float
) -> str:
    """La brecha dicha en una oración, con el grupo que queda por detrás de sujeto.

    La cifra sola no dice quién está peor ni en qué, y el signo de la resta no sirve
    para deducirlo: cambia de sentido entre un indicador y otro, y entre Matemática y
    Lectura.
    """
    sujeto, tiene, obtiene, _ = GRUPO_EN_FRASE[peor]
    termino = GRUPO_EN_FRASE[mejor][3]
    cantidad = cp.formato(magnitud, 1)
    if not indicador.sufijo:
        # La medida promedio es un puntaje, no una proporción: no tiene puntos
        # porcentuales ni se puede hablar de estudiantes que la alcanzan.
        return (
            f"{sujeto} {obtiene} {cantidad} puntos menos en la medida promedio que "
            f"{termino}."
        )
    direccion = "más" if indicador.mas_es_peor else "menos"
    return (
        f"{sujeto} {tiene} {cantidad} puntos porcentuales {direccion} de "
        f"{GLOSA_INDICADOR[indicador.clave]} que {termino}."
    )


def texto_p(valor_p: float) -> str:
    """Valor p en formato peruano, con un piso por debajo del cual no se detalla."""
    return "p < 0,001" if valor_p < 0.001 else f"p = {cp.formato(valor_p, 3)}"


@st.cache_data(show_spinner=False)
def comparacion(
    grado: str, area: str, clave_indicador: str, columna: str, grupo_a: str, grupo_b: str
) -> muestreo.Brecha:
    """Diferencia entre dos grupos con su error estándar y su significancia."""
    numerador, es_proporcion = MICRODATO[clave_indicador]
    return muestreo.comparar_grupos(
        estado.microdatos(grado, area),
        columna,
        grupo_a,
        grupo_b,
        numerador=numerador,
        es_proporcion=es_proporcion,
    )


@st.cache_data(show_spinner=False)
def ranking_regional(grado: str, area: str, clave_indicador: str) -> pd.DataFrame:
    """Estimación por departamento, cada una con su intervalo de confianza."""
    numerador, es_proporcion = MICRODATO[clave_indicador]
    return muestreo.estimar_por_grupo(
        estado.microdatos(grado, area),
        "departamento",
        numerador=numerador,
        es_proporcion=es_proporcion,
        muestra_minima=config.MUESTRA_MINIMA,
        conglomerados_minimos=config.ESCUELAS_MINIMAS,
    )


def estimacion_de(fila: pd.Series) -> muestreo.Estimacion:
    """Rearma la estimación de una fila del ranking para poder usar `se_solapan`.

    `estimar_por_grupo` devuelve una tabla, no objetos. El número de estratos no
    interviene en la comparación de intervalos, así que se deja en cero.
    """
    return muestreo.Estimacion(
        valor=float(fila["valor"]),
        error_estandar=float(fila["error_estandar"]),
        ic_inferior=float(fila["ic_inferior"]),
        ic_sup=float(fila["ic_sup"]),
        n_muestra=int(fila["n_muestra"]),
        n_conglomerados=int(fila["n_conglomerados_diseno"]),
        n_estratos=0,
        grados_libertad=int(fila["grados_libertad"]),
        poblacion_estimada=float(fila["poblacion_estimada"]),
        n_conglomerados_dominio=int(fila["n_conglomerados"]),
    )


@st.cache_data(show_spinner=False)
def comparaciones_contra(
    grado: str, area: str, clave_indicador: str, referencia: str, otras: tuple[str, ...]
) -> pd.DataFrame:
    """Compara la región de referencia con cada una de las que se solapan con ella.

    El solapamiento de intervalos es una regla conservadora. Esta tabla resuelve los
    pares que esa regla deja sin decidir, comparando los dos grupos con el estimador que
    sí tiene en cuenta la covarianza entre ambas estimaciones.
    """
    numerador, es_proporcion = MICRODATO[clave_indicador]
    datos = estado.microdatos(grado, area)
    filas = []
    for otra in otras:
        brecha = muestreo.comparar_grupos(
            datos,
            "departamento",
            referencia,
            otra,
            numerador=numerador,
            es_proporcion=es_proporcion,
        )
        filas.append(
            {
                "region": otra,
                "diferencia": brecha.diferencia,
                "ic_inferior": brecha.ic_inferior,
                "ic_sup": brecha.ic_sup,
                "valor_p": brecha.valor_p,
                "significativa": brecha.es_significativa,
            }
        )
    return pd.DataFrame(filas)


f = estado.filtros()

cp.encabezado(
    "Brechas",
    f"Diferencias entre grupos en {f.descripcion()}, con la precisión de cada cifra",
)

# Con clave propia y sin `index`, por lo mismo que en el mapa: ver `estado.sembrar`.
estado.sembrar("brechas_indicador", "indicador")
clave_ind = st.radio(
    "Indicador",
    options=list(config.INDICADORES),
    format_func=lambda c: config.INDICADORES[c].nombre,
    horizontal=True,
    help="El mismo indicador se usa en las tarjetas de comparación y en el ranking.",
    key="brechas_indicador",
)
estado.actualizar(indicador=clave_ind)
f = estado.filtros()
indicador = config.INDICADORES[f.indicador]
unidad = "puntos porcentuales" if indicador.sufijo else "puntos de la escala del grado"


# 1. Las tres comparaciones, con su significancia ------------------------------------

cp.seccion(
    "Ámbito, gestión y sexo",
    f"{indicador.nombre} en cada grupo y cuánta distancia hay entre ellos, en todo el "
    "país. El ámbito y la gestión son de la escuela; el sexo, del estudiante.",
)

cp.igualar_tarjetas()
columnas = st.columns(3, gap="medium")

for columna_ui, (titulo, subtitulo, columna, grupo_a, grupo_b) in zip(
    columnas, COMPARACIONES
):
    brecha = comparacion(f.grado, f.area, f.indicador, columna, grupo_a, grupo_b)
    significativa = brecha.es_significativa

    # Quién queda por detrás depende del indicador, no del signo de la resta: en «% en
    # niveles críticos» está peor el que tiene más, y en los otros dos el que tiene
    # menos. Nombrar al grupo ahorra interpretar un signo que además se invierte entre
    # un área y otra: en Matemática la resta Hombre menos Mujer sale negativa y en
    # Lectura positiva, y la tarjeta decía lo mismo en los dos casos.
    a_esta_peor = (
        brecha.estimacion_a.valor > brecha.estimacion_b.valor
        if indicador.mas_es_peor
        else brecha.estimacion_a.valor < brecha.estimacion_b.valor
    )
    crudo_peor = grupo_a if a_esta_peor else grupo_b
    crudo_mejor = grupo_b if a_esta_peor else grupo_a

    # Una brecha confirmada no es una buena noticia, así que no lleva el verde de la
    # aplicación. Sin significancia no hay dirección que afirmar y la tarjeta se apaga.
    color = theme.CONTRASTE if significativa else theme.TEXTO_SECUNDARIO
    sello = (
        "Diferencia significativa" if significativa
        else "Diferencia no significativa"
    )
    if significativa:
        frase = frase_de_brecha(
            indicador, crudo_peor, crudo_mejor, abs(brecha.diferencia)
        )
    else:
        frase = (
            "La muestra no da para afirmar una diferencia entre "
            f"{GRUPO_EN_FRASE[grupo_a][3]} y {GRUPO_EN_FRASE[grupo_b][3]}."
        )

    # El margen va pegado a la cifra y no en una línea aparte al pie, que es donde no
    # se mira. Se escribe con ± porque el intervalo de una diferencia sí queda centrado
    # en ella: se construye sumando y restando el mismo error. El de una proporción no,
    # y por eso en el ranking regional se escriben los dos extremos.
    margen_mas_menos = (brecha.ic_sup - brecha.ic_inferior) / 2
    pie = f"(IC 95, {texto_p(brecha.valor_p)})."

    filas = "".join(
        f"<div style='display:flex;justify-content:space-between;"
        f"align-items:baseline;padding:7px 0;border-bottom:1px solid "
        f"{theme.BORDE_SUAVE}'>"
        f"<span style='font-size:0.86rem;color:{theme.TEXTO_SECUNDARIO}'>"
        f"{etiqueta(nombre)}</span>"
        f"<span style='font-size:1.02rem;font-weight:600;"
        f"font-variant-numeric:tabular-nums;color:{theme.TEXTO}'>"
        f"{cp.formato(estimacion.valor, 1, indicador.sufijo)}</span></div>"
        for nombre, estimacion in (
            (grupo_a, brecha.estimacion_a),
            (grupo_b, brecha.estimacion_b),
        )
    )

    # Toda la tarjeta en un solo bloque: dentro del contenedor, Streamlit separa cada
    # elemento con un hueco fijo que no se puede ajustar, y con cinco elementos seguidos
    # el conjunto quedaba apelmazado y la última línea pegada al borde de abajo.
    with columna_ui, st.container(border=True):
        st.markdown(
            f"<div class='tarjeta-pareja'>"
            f"<div style='display:flex;align-items:center;gap:11px;"
            f"min-height:40px'>"
            f"<span style='flex:0 0 auto;line-height:0'>"
            f"{icono(columna, theme.TEXTO_TENUE)}</span>"
            f"<div><div style='font-weight:700'>{titulo}</div>"
            f"<div class='nota' style='margin-top:1px'>{subtitulo}</div></div></div>"
            f"<div style='margin-top:16px'>{filas}</div>"
            # La distancia se escribe sin signo y sin el símbolo de porcentaje: entre
            # dos porcentajes lo que hay son puntos porcentuales.
            f"<div style='margin-top:18px;display:flex;align-items:baseline;"
            f"flex-wrap:wrap;gap:4px 8px;min-height:54px'>"
            f"<span style='font-size:2rem;font-weight:700;letter-spacing:-1px;"
            f"line-height:1;color:{color}'>"
            f"{cp.formato(abs(brecha.diferencia), 1)}</span>"
            f"<span style='font-size:1rem;font-weight:600;line-height:1;"
            f"color:{theme.TEXTO_SECUNDARIO}'>"
            f"± {cp.formato(margen_mas_menos, 1)}</span>"
            f"<span style='font-size:0.8rem;color:{theme.TEXTO_SECUNDARIO}'>"
            f"{unidad}</span></div>"
            f"<div style='margin-top:16px;background:{color}14;"
            f"border:1px solid {color}55;border-radius:{theme.RADIO_INTERNO};"
            f"padding:11px 13px;font-size:0.8rem;line-height:1.5;"
            f"box-sizing:border-box;min-height:82px;"
            f"color:{theme.TEXTO_SECUNDARIO}'>{frase}</div>"
            f"<div class='pie'>"
            f"<span style='color:{color};font-weight:600'>{sello}</span> "
            f"{pie}</div></div>",
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)


# 2. Ranking regional con intervalos de confianza ------------------------------------

ranking = ranking_regional(f.grado, f.area, f.indicador)
# Las regiones con dato, antes de aplicar ningún piso: es contra esto que hay que decir
# cuántas faltan, no contra las que sobrevivieron.
universo_regional = len(estado.resultados("departamento", f.grado, f.area))
if ranking.empty:
    st.warning(
        "Ninguna región alcanza la muestra mínima para el grado y el área "
        "seleccionados."
    )
    st.stop()

# Sin varianza estimable el intervalo saldría de ancho cero y aparentaría una precisión
# que no existe. El estimador ya lo declara en lugar de devolver un cero mudo.
sin_varianza = ranking[~ranking["varianza_estimable"]]
ranking = ranking.drop(sin_varianza.index)

cp.seccion(
    "¿Se puede ordenar a las regiones?",
    f"{indicador.nombre} en cada departamento. La prueba no se tomó a todos los "
    "estudiantes, sino a una muestra de escuelas, así que cada cifra viene con un "
    "margen.",
)

cp.aviso_representatividad(f.grado, "departamento")

orden_ranking = [str(region) for region in ranking["departamento"]]
estimaciones = {
    str(fila["departamento"]): estimacion_de(fila) for _, fila in ranking.iterrows()
}

referencia = st.selectbox(
    "Región de referencia",
    options=orden_ranking,
    # Por omisión, la región que queda a mitad del ranking: es donde se concentran los
    # intervalos que se tocan, que es justo lo que este gráfico tiene que mostrar.
    index=len(orden_ranking) // 2,
    key=f"referencia_{f.grado}_{f.area}",
    help="Se marcan las regiones cuyo intervalo se toca con el de esta.",
)

estimacion_referencia = estimaciones[referencia]
solapan = {
    region
    for region, estimacion in estimaciones.items()
    if region != referencia and muestreo.se_solapan(estimacion_referencia, estimacion)
}
# De menor a mayor, porque Plotly dibuja la primera categoría abajo.
grafico = ranking.sort_values("valor", ascending=True).reset_index(drop=True)

valores = [float(v) for v in grafico["valor"]]
limites_bajos = [float(v) for v in grafico["ic_inferior"]]
limites_altos = [float(v) for v in grafico["ic_sup"]]

# Los intervalos de un porcentaje se construyen en la escala logit, así que ya no
# pueden salirse de 0 y 100 y no hay nada que recortar al dibujarlos.
dibujo_bajo, dibujo_alto = limites_bajos, limites_altos

# Un punto con su margen, y no una barra desde cero. La barra invitaba a comparar
# largos, que es justo la lectura que esta sección desmiente, y dejaba el margen
# reducido a una rayita al final. Con el punto, lo que se compara es la posición, y los
# márgenes que se cruzan se ven de un vistazo.
color_punto = theme.CONTRASTE if indicador.mas_es_peor else theme.ACENTO
color_referencia = theme.TERCERO
bordes = [
    color_referencia if region == referencia else color_punto
    for region in grafico["departamento"]
]
anchos = [2.0 if region == referencia else 0.0 for region in grafico["departamento"]]
tamanos = [14 if region == referencia else 12 for region in grafico["departamento"]]

barras = figura_base(96 + 27 * len(grafico), dict(l=150, r=96, t=34, b=44))
barras.add_trace(
    go.Scatter(
        y=list(grafico["departamento"]),
        x=list(grafico["valor"]),
        mode="markers",
        marker=dict(
            size=tamanos,
            color=color_punto,
            line=dict(color=bordes, width=anchos),
        ),
        error_x=dict(
            type="data",
            symmetric=False,
            array=[alto - v for alto, v in zip(dibujo_alto, valores)],
            arrayminus=[v - bajo for bajo, v in zip(dibujo_bajo, valores)],
            color=theme.TEXTO_SECUNDARIO,
            thickness=1.2,
            width=3,
        ),
        customdata=[
            f"<b>{fila['departamento']}</b><br>"
            f"<span style='color:{theme.ACENTO}'><b>{indicador.nombre}: "
            f"{cp.formato(fila['valor'], 1, indicador.sufijo)}</b></span><br>"
            f"<span style='color:{theme.TEXTO_SECUNDARIO}'>"
            f"Margen: {cp.formato(fila['ic_inferior'], 1)} a "
            f"{cp.formato(fila['ic_sup'], 1)}.<br>"
            f"{cp.entero(fila['n_muestra'])} evaluados en "
            f"{cp.entero(fila['n_conglomerados'])} escuelas.</span>"
            for _, fila in grafico.iterrows()
        ],
        hovertemplate="%{customdata}<extra></extra>",
    )
)

# Columna de cifras fuera del área de trazado: así ninguna etiqueta se cruza con las
# barras ni con los intervalos.
for region, valor in zip(grafico["departamento"], grafico["valor"]):
    barras.add_annotation(
        xref="paper",
        x=1.01,
        y=region,
        text=cp.formato(valor, 1, indicador.sufijo),
        showarrow=False,
        xanchor="left",
        font=dict(
            size=11.5,
            color=(
                color_referencia
                if region == referencia
                else (theme.TEXTO if region in solapan else theme.TEXTO_TENUE)
            ),
        ),
    )

margen_eje = (max(dibujo_alto) - min(dibujo_bajo)) * 0.08
inicio_eje = min(dibujo_bajo) - margen_eje

# El margen de la referencia, como franja vertical. Las barras cuyo intervalo la cruzan
# son las que no se distinguen de ella, y eso se ve sin leer ninguna leyenda.
# El relleno va por debajo de las barras, porque encima las decolora y deja de leerse
# el color del indicador. Los dos bordes van por encima en línea punteada: son ellos los
# que marcan hasta dónde llega el margen, y tienen que verse crucen lo que crucen.
barras.add_vrect(
    x0=float(estimacion_referencia.ic_inferior),
    x1=float(estimacion_referencia.ic_sup),
    fillcolor=theme.TEXTO,
    opacity=0.07,
    layer="below",
    line_width=0,
)
for borde in (estimacion_referencia.ic_inferior, estimacion_referencia.ic_sup):
    barras.add_vline(
        x=float(borde),
        line_width=1.3,
        line_color=color_referencia,
        line_dash="dot",
        layer="above",
    )
barras.add_annotation(
    x=float(estimacion_referencia.valor),
    y=1,
    yref="paper",
    yanchor="bottom",
    text=f"margen de {referencia}",
    showarrow=False,
    font=dict(size=10.5, color=color_referencia),
)

barras.update_xaxes(
    range=[inicio_eje, max(dibujo_alto) + margen_eje],
    showgrid=False,
    zeroline=False,
    showline=True,
    linecolor=theme.BORDE,
    ticks="outside",
    tickcolor=theme.BORDE,
    ticklen=4,
    tickfont=dict(size=11, color=theme.TEXTO_TENUE),
    title=dict(
        text=indicador.nombre, font=dict(size=11.5, color=theme.TEXTO_TENUE), standoff=6
    ),
)
barras.update_yaxes(
    showgrid=True,
    gridcolor=theme.BORDE_SUAVE,
    gridwidth=1,
    zeroline=False,
    showline=False,
    ticks="",
    tickvals=list(grafico["departamento"]),
    ticktext=[
        f"<b><span style='color:{color_referencia}'>{r}</span></b>"
        if r == referencia
        else (
            f"<span style='color:{theme.TEXTO}'>{r}</span>"
            if r in solapan
            else f"<span style='color:{theme.TEXTO_TENUE}'>{r}</span>"
        )
        for r in grafico["departamento"]
    ],
    tickfont=dict(size=11.5, color=theme.TEXTO_TENUE),
)

st.markdown(
    f"<div class='nota' style='margin-bottom:2px'>La franja es el margen de "
    f"<span style='color:{color_referencia};font-weight:600'>{referencia}</span>. "
    f"En blanco, las {len(solapan)} regiones que no se distinguen de ella.</div>"
    if solapan
    else f"<div class='nota' style='margin-bottom:2px'>La franja es el margen de "
    f"<span style='color:{color_referencia};font-weight:600'>{referencia}</span>. "
    "Todas las demás se distinguen de ella.</div>",
    unsafe_allow_html=True,
)

st.plotly_chart(barras, config=CONFIG_PLOTLY, theme=None)

fuera = universo_regional - len(ranking)
# Los umbrales exactos y por qué pesan más las escuelas que los estudiantes están en
# Notas sobre los datos. Aquí basta con decir que no aparecen y por qué.
aparte = (
    f" {fuera} de las {universo_regional} regiones no aparecen aquí: se evaluaron en "
    "muy pocas escuelas y su cifra no sería fiable."
    if fuera
    else ""
)
# La lectura del gráfico para la región elegida, que es lo que uno se lleva de aquí.
# Un dato general sobre las 25 no responde la pregunta con la que se entra, que es qué
# pasa con una región en concreto.
valor_referencia = float(estimacion_referencia.valor)
peores = sum(
    1
    for region, estimacion in estimaciones.items()
    if region != referencia
    and region not in solapan
    and (
        estimacion.valor > valor_referencia
        if indicador.mas_es_peor
        else estimacion.valor < valor_referencia
    )
)
restantes = len(estimaciones) - 1
mejores = restantes - len(solapan) - peores

grupos = []
if peores:
    grupos.append((peores, "claramente peor", True))
if mejores:
    grupos.append((mejores, "claramente mejor", True))
if solapan:
    grupos.append((len(solapan), "demasiado cerca para decidirlo", False))

frases = []
for posicion, (cuantas, descripcion, comparativo) in enumerate(grupos):
    if posicion == 0:
        verbo = "queda" if cuantas == 1 else "quedan"
        cola = f" que {referencia}" if comparativo else ""
        frases.append(f"{cuantas} {verbo} {descripcion}{cola}")
    else:
        frases.append(f"{cuantas} {descripcion}")
cuerpo = frases[0] if len(frases) == 1 else ", ".join(frases[:-1]) + " y " + frases[-1]

# Destacada en una caja y no con una franja de color a la izquierda, que es el adorno
# que esta aplicación no usa. Es la conclusión del gráfico, así que se lee antes que
# nada de lo que viene debajo.
st.markdown(
    f"<div style='background:{theme.SUPERFICIE_HUNDIDA};"
    f"border:1px solid {theme.BORDE};border-radius:{theme.RADIO_INTERNO};"
    f"padding:14px 18px;margin:6px 0 4px;font-size:1.1rem;line-height:1.5;"
    f"color:{theme.TEXTO}'>De las {restantes} regiones restantes, {cuerpo}.</div>"
    + (f"<div class='nota' style='margin-top:6px'>{aparte.strip()}</div>" if aparte else ""),
    unsafe_allow_html=True,
)

if solapan:
    with st.expander(
        f"Comparar {referencia} con las {len(solapan)} regiones que no se "
        "distinguen de ella",
        expanded=True,
    ):
        detalle = comparaciones_contra(
            f.grado, f.area, f.indicador, referencia, tuple(sorted(solapan))
        )
        n_significativas = int(detalle["significativa"].sum())
        # «Que dos márgenes se crucen no quiere decir que tengan el mismo resultado»
        # era cierto pero no decía qué hacer con ello. Lo que importa es que el gráfico
        # da una primera lectura y la comparación directa afina más.
        st.caption(
            f"El gráfico deja estas {len(detalle)} regiones en duda. Comparar dos "
            "regiones de frente afina más que mirar si sus márgenes se cruzan, y así "
            f"{n_significativas} de ellas sí resultan distintas de {referencia}."
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Región": detalle["region"],
                    f"Diferencia con {referencia}": [
                        ("+" if v >= 0 else "-") + cp.formato(abs(v), 1)
                        for v in detalle["diferencia"]
                    ],
                    "Margen de la diferencia": [
                        f"{cp.formato(a, 1)} a {cp.formato(b, 1)}"
                        for a, b in zip(detalle["ic_inferior"], detalle["ic_sup"])
                    ],
                    # «No» a secas se leería como que las dos regiones empatan, que es
                    # lo contrario de lo que dice la columna. Y el valor p se queda en
                    # Notas sobre los datos: esta página está en Explorar.
                    f"¿Se distingue de {referencia}?": [
                        "Sí" if s else "No se puede decir"
                        for s in detalle["significativa"]
                    ],
                }
            ),
            hide_index=True,
            height=min(38 * (len(detalle) + 1) + 4, 420),
        )

with st.expander("Ver el ranking en tabla", expanded=False):
    tabla = ranking.sort_values("valor", ascending=not indicador.mas_es_peor)
    st.dataframe(
        pd.DataFrame(
            {
                "Región": tabla["departamento"],
                indicador.nombre: [
                    cp.formato(v, 1, indicador.sufijo) for v in tabla["valor"]
                ],
                "IC 95": [
                    f"{cp.formato(a, 1)} a {cp.formato(b, 1)}"
                    for a, b in zip(tabla["ic_inferior"], tabla["ic_sup"])
                ],
                # El intervalo de un porcentaje se construye en la escala logit y no
                # queda centrado en la estimación, así que escribirlo con ± diría algo
                # que no es: en Loreto, 95,1 % con un intervalo de 90,3 a 97,6 baja 4,8
                # y sube 2,5, no ± 3,7.
                "Margen": [
                    f"-{cp.formato(v - a, 1)} / +{cp.formato(b - v, 1)}"
                    if indicador.sufijo
                    else f"± {cp.formato(b - v, 1)}"
                    for v, a, b in zip(
                        tabla["valor"], tabla["ic_inferior"], tabla["ic_sup"]
                    )
                ],
                "Evaluados": [cp.entero(n) for n in tabla["n_muestra"]],
                "Escuelas": [cp.entero(n) for n in tabla["n_conglomerados"]],
            }
        ),
        hide_index=True,
        height=360,
    )


cp.pie_de_pagina()
