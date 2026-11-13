"""Piezas de interfaz que comparten las páginas.

Centralizar el mapa y los filtros evita que cada página los reconstruya con pequeñas
diferencias, que es como una aplicación termina mostrando el mismo dato de dos maneras.
"""

from __future__ import annotations

import json

import branca.colormap as cm
import folium
from branca.element import MacroElement, Template
import geopandas as gpd
import mapclassify
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from geoeduca import almacen

from . import config, estado, theme

# Centro aproximado del Perú y acercamiento inicial del mapa.
CENTRO_PERU = (-9.2, -75.0)
ZOOM_INICIAL = 5


def encabezado(titulo: str, subtitulo: str = "") -> None:
    """Título de página con su línea de contexto."""
    st.markdown(theme.CSS, unsafe_allow_html=True)
    st.markdown(f"### {titulo}")
    if subtitulo:
        st.markdown(
            f"<div class='nota' style='margin-top:-2px;margin-bottom:16px'>"
            f"{subtitulo}</div>",
            unsafe_allow_html=True,
        )


def _marca_svg() -> str:
    """Logotipo del proyecto, dibujado como SVG para que siga al tema."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 184 34" width="184" '
        'height="34" role="img" aria-label="GEO_EDUCA">'
        f'<path d="M10 25c0-5 4-9 9-9s9 4 9 9" fill="none" stroke="{theme.TEXTO_SOBRE_MARCA}" '
        'stroke-width="2.2" stroke-linecap="round"/>'
        f'<circle cx="19" cy="12" r="4.2" fill="none" stroke="{theme.TEXTO_SOBRE_MARCA}" '
        'stroke-width="2.2"/>'
        f'<text x="36" y="24" font-family="Plus Jakarta Sans, sans-serif" font-size="17" '
        f'font-weight="700" letter-spacing="0.5" fill="{theme.TEXTO_SOBRE_MARCA}">'
        "GEO_EDUCA</text></svg>"
    )


def barra_lateral() -> None:
    """Marca en el panel de navegación.

    No lleva cifras. El tamaño de la muestra depende del grado y del área elegidos, así
    que puesto aquí cambiaba al mover los filtros mientras Panorama seguía mostrando el
    total de los tres grados, y las dos cifras se contradecían. Las cifras de tamaño
    viven en Panorama, que es donde se explican.

    Los filtros de grado y área no van aquí sino en la barra superior, como en el
    diseño: son los dos controles que gobiernan todas las páginas y conviene que estén
    donde se mira primero, no escondidos bajo el menú.
    """
    # El nombre va por encima de la navegación, que es donde Streamlit coloca el logotipo
    # y donde se espera encontrar el título. Como SVG en lugar de imagen, para que herede
    # los colores del tema y no haya un archivo que mantener aparte.
    st.logo(_marca_svg(), size="large")


def barra_superior() -> None:
    """Cabecera con la marca y los dos filtros que gobiernan toda la aplicación.

    Se dibuja una sola vez, antes de la página, de modo que grado y área estén siempre
    en el mismo sitio y cambiarlos no dependa de en qué sección se esté.
    """
    f = estado.filtros()
    rotulo, col_grado, col_area, hueco = st.columns([2.3, 1.9, 2.0, 1.8], gap="small")

    with rotulo:
        # El nombre vive en la navegación, así que aquí basta decir qué se está mirando.
        st.markdown(
            f"""<div style='display:flex;align-items:center;min-height:44px'>
                <span style='font-size:0.78rem;color:{theme.TEXTO_SECUNDARIO}'>
                    Estás viendo</span>
            </div>""",
            unsafe_allow_html=True,
        )

    # Sin `index`: con una clave estable, Streamlit ya guarda el valor, y pasarle además
    # un índice calculado desde el filtro solo sirve para que los dos se peleen.
    estado.sembrar("sel_grado", "grado")

    with col_grado:
        grado = st.selectbox(
            "Grado",
            options=list(config.GRADOS),
            format_func=config.nombre_grado,
            key="sel_grado",
            label_visibility="collapsed",
        )

    with col_area:
        # Al cambiar de grado puede quedar guardada un área que el nuevo no evalúa, y un
        # selectbox cuyo valor no está entre sus opciones falla. Se corrige antes de
        # dibujarlo, que es cuando todavía se puede escribir en el estado.
        areas = config.areas_de(grado)
        if st.session_state.get("sel_area") not in areas:
            st.session_state["sel_area"] = f.area if f.area in areas else "M"
        area = st.selectbox(
            "Área evaluada",
            options=list(areas),
            format_func=config.nombre_area,
            key="sel_area",
            label_visibility="collapsed",
        )

    estado.actualizar(grado=grado, area=area)
    st.markdown(
        f"<div style='height:1px;background:{theme.BORDE};margin:2px 0 14px'></div>",
        unsafe_allow_html=True,
    )


def separador() -> None:
    """Línea fina entre dos bloques de una página.

    Con solo aire de por medio, varios bloques seguidos se leen como una página larga y
    cuesta ver dónde acaba uno y empieza el siguiente. Es la misma línea que separa la
    barra de filtros del contenido, para no meter un recurso nuevo en el sistema.
    """
    st.markdown(
        f"<div style='height:1px;background:{theme.BORDE};margin:26px 0 18px'></div>",
        unsafe_allow_html=True,
    )


def seccion(titulo: str, nota: str) -> None:
    """Encabezado de bloque, con su línea de separación y su contexto.

    Un bloque que no necesita contexto tampoco necesita encabezado: las cuatro cifras de
    tamaño de Panorama se quedaron sin título por eso, porque cada tarjeta ya trae el
    suyo.
    """
    st.markdown(
        f"<div style='height:1px;background:{theme.BORDE};margin:26px 0 18px'></div>"
        f"<div style='font-size:1.08rem;font-weight:700;color:{theme.TEXTO}'>{titulo}</div>"
        f"<div class='nota' style='margin-top:4px;margin-bottom:20px'>{nota}</div>",
        unsafe_allow_html=True,
    )


def aviso_representatividad(grado: str, nivel: str) -> None:
    """Muestra la advertencia cuando el corte no tiene respaldo en el diseño muestral.

    Con margen propio y no el de la clase: este aviso se cuela entre los controles y el
    contenido de la página, y pegado a los dos parecía parte del mapa. Los otros
    recuadros de la misma clase van debajo de un gráfico, donde ese aire sobra.
    """
    mensaje = almacen.advertencia_representatividad(grado, nivel)
    if mensaje:
        # El aire va en bloques propios y no en un margen del recuadro: Streamlit envuelve
        # cada elemento en su propio contenedor y ahí el margen se colapsa contra el del
        # contenedor, de modo que no separaba nada.
        st.markdown(
            "<div style='height:12px'></div>"
            f"<div class='aviso'>{mensaje}</div>"
            "<div style='height:20px'></div>",
            unsafe_allow_html=True,
        )


def formato(valor: float, decimales: int = 1, sufijo: str = "") -> str:
    """Formato peruano: coma decimal y espacio como separador de miles."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "sin dato"
    texto = f"{valor:,.{decimales}f}"
    # Un negativo diminuto se redondea a cero y arrastra el signo: el extremo de un
    # intervalo salía escrito "-0,0", que no es una cifra que nadie quiera leer.
    if texto.startswith("-") and float(texto.replace(",", "")) == 0:
        texto = texto[1:]
    texto = texto.replace(",", " ").replace(".", ",")
    return texto + sufijo


def entero(valor: float) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "sin dato"
    return f"{int(round(valor)):,}".replace(",", " ")


def unidades(n: float) -> str:
    """Cuenta de unidades con su singular, para no escribir "1 unidades"."""
    return f"{entero(n)} unidad" if int(n) == 1 else f"{entero(n)} unidades"


def tarjeta_metrica(rotulo: str, valor: str, pie: str = "") -> None:
    """Tarjeta con una cifra y su contexto.

    Se estira al alto de su fila y ancla la cifra abajo, de modo que las cifras de una
    fila quedan alineadas entre sí sea cual sea el largo de cada pie. Con el alto fijo
    que tenía antes, un rótulo o un pie de un renglón más se salían de la caja. La
    página que la use tiene que llamar antes a `igualar_tarjetas`.
    """
    st.markdown(
        f"""<div class='tarjeta tarjeta-pareja' style='min-height:130px'>
            <div class='rotulo' style='margin:0'>{rotulo}</div>
            <div style='margin-top:auto;padding-top:12px'>
                <div style='font-size:1.65rem;font-weight:700;letter-spacing:-0.6px;
                            line-height:1.15;color:{theme.TEXTO}'>{valor}</div>
                <div class='nota' style='margin-top:3px'>{pie}</div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


def par_de_cifras(izquierda: tuple[str, str], derecha: tuple[str, str]) -> None:
    """Dos cifras con su rótulo, una al lado de la otra, en un espacio estrecho.

    Escrito a mano y no con `st.metric`, que dentro de dos columnas del panel lateral
    recortaba con puntos suspensivos tanto el rótulo como el número: en pantalla se leía
    "EVALU… 129…" y "ESTIM… 54…", es decir ninguna de las dos cifras.

    El rótulo puede partirse en dos líneas, porque aquí los rótulos explican en lugar de
    nombrar y son largos. Reserva las dos líneas aunque ocupe una, para que las dos
    cifras queden a la misma altura: con una altura libre, un rótulo de dos líneas
    hundía su número por debajo del otro.
    """
    celdas = "".join(
        f"""<div style='flex:1;min-width:0'>
            <div style='font-size:0.64rem;letter-spacing:0.05em;text-transform:uppercase;
                        color:{theme.TEXTO_SECUNDARIO};line-height:1.35;
                        min-height:1.73rem'>{rotulo}</div>
            <div style='font-size:1.05rem;font-weight:700;letter-spacing:-0.3px;
                        color:{theme.TEXTO};white-space:nowrap'>{valor}</div>
        </div>"""
        for rotulo, valor in (izquierda, derecha)
    )
    st.markdown(
        f"<div style='display:flex;gap:14px;margin-top:4px'>{celdas}</div>",
        unsafe_allow_html=True,
    )


def barra_niveles(fila: pd.Series, alto: int = 26) -> None:
    """Barra apilada con la distribución por nivel de logro."""
    partes = [
        (fila.get("pct_previo_inicio", 0), theme.NIVELES[0], config.NIVELES_LOGRO[0]),
        (fila.get("pct_en_inicio", 0), theme.NIVELES[1], config.NIVELES_LOGRO[1]),
        (fila.get("pct_en_proceso", 0), theme.NIVELES[2], config.NIVELES_LOGRO[2]),
        (fila.get("pct_satisfactorio", 0), theme.NIVELES[3], config.NIVELES_LOGRO[3]),
    ]
    segmentos = "".join(
        f"<div style='width:{p}%;background:{c}' title='{n}: {formato(p)} %'></div>"
        for p, c, n in partes
        if p and p > 0
    )
    st.markdown(
        f"<div style='display:flex;height:{alto}px;border-radius:4px;"
        f"overflow:hidden;background:{theme.BORDE_SUAVE}'>{segmentos}</div>",
        unsafe_allow_html=True,
    )


#: Qué niveles de logro componen cada indicador. Sirve para señalar, en el desglose,
#: cuáles de los cuatro suman la cifra que el usuario está mirando.
NIVELES_DEL_INDICADOR: dict[str, tuple[int, ...]] = {
    "pct_critico": (0, 1),
    "pct_satisfactorio": (3,),
}

def desglose_niveles(fila: pd.Series, clave_indicador: str = "") -> None:
    """Distribución por nivel de logro, con lo que significa cada uno y su relación
    con el indicador que se está mirando.

    La barra sola no comunica. Quien no conoce la evaluación ve cuatro colores sin
    saber qué proporción es cada uno, y los nombres tampoco ayudan: "Previo al inicio"
    y "En inicio" suenan a lo mismo si no se conoce la escala, cuando son el peor y el
    segundo peor. Cada nivel lleva por eso su glosa de una línea.

    Los niveles que componen el indicador activo van dentro de un recuadro con su suma,
    para que la relación con la cifra de arriba se vea antes de leerla.
    """
    partes = [
        (fila.get("pct_previo_inicio", 0), theme.NIVELES[0]),
        (fila.get("pct_en_inicio", 0), theme.NIVELES[1]),
        (fila.get("pct_en_proceso", 0), theme.NIVELES[2]),
        (fila.get("pct_satisfactorio", 0), theme.NIVELES[3]),
    ]
    barra_niveles(fila)

    componen = NIVELES_DEL_INDICADOR.get(clave_indicador, ())

    def renglon(i: int) -> str:
        valor, color = partes[i]
        destacado = i in componen
        return (
            f"<div style='display:flex;align-items:baseline;gap:7px;margin-top:6px'>"
            f"<span style='width:9px;height:9px;border-radius:2px;flex:0 0 auto;"
            f"background:{color};transform:translateY(1px)'></span>"
            f"<span style='flex:1;min-width:0'>"
            f"<span style='font-size:0.76rem;color:{theme.TEXTO};"
            f"font-weight:{600 if destacado else 500}'>"
            f"{config.NIVELES_LOGRO[i]}</span><br>"
            f"<span style='font-size:0.68rem;color:{theme.TEXTO_SECUNDARIO}'>"
            f"{config.GLOSA_NIVEL[i]}</span></span>"
            f"<span style='font-size:0.76rem;color:{theme.TEXTO};"
            f"font-weight:{600 if destacado else 400}'>"
            f"{formato(valor, 1, ' %')}</span></div>"
        )

    # Los cuatro niveles van siempre en su orden, del peor al mejor, que es el mismo
    # de la barra de arriba. La caja se abre y se cierra alrededor de los que componen
    # el indicador: construirla aparte y pegarla delante dejaba a Satisfactorio por
    # encima de Previo al inicio y contradecía la barra.
    suma = sum(partes[i][0] or 0 for i in componen)
    # El color de la caja es el del nivel que encierra, no el verde de la aplicación:
    # en verde, un 30,9 % de estudiantes que no llegan a lo esperado se lee como una
    # buena noticia. Con los niveles críticos sale cálido y con Satisfactorio, frío.
    color_caja = theme.NIVELES[componen[0]] if componen else theme.ACENTO
    piezas: list[str] = []
    for i in range(4):
        if i in componen and (i - 1) not in componen:
            piezas.append(
                # Margen negativo que cancela el relleno propio: así el borde sale
                # hacia afuera y las filas de dentro quedan en la misma columna que
                # las de fuera. Con el relleno sin compensar, los niveles de la caja
                # aparecían diez píxeles más adentro que En proceso y Satisfactorio.
                f"<div style='border:1px solid {color_caja}55;"
                f"border-radius:{theme.RADIO_INTERNO};background:{color_caja}14;"
                "padding:4px 10px 10px;margin:9px -10px'>"
            )
        piezas.append(renglon(i))
        if i in componen and (i + 1) not in componen:
            piezas.append(
                f"<div style='display:flex;justify-content:space-between;gap:8px;"
                f"margin-top:8px;padding-top:7px;"
                f"border-top:1px solid {color_caja}55;font-size:0.74rem;"
                f"color:{color_caja};font-weight:700'>"
                f"<span>En total</span>"
                f"<span>{formato(suma, 1, ' %')}</span></div></div>"
            )

    cuerpo = f"<div style='margin-top:9px;padding:0 10px'>{''.join(piezas)}</div>"

    st.markdown(cuerpo, unsafe_allow_html=True)


def leyenda_niveles() -> None:
    """Leyenda de los cuatro niveles de logro, en orden."""
    piezas = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:6px;"
        f"margin-right:16px;font-size:0.74rem;color:{theme.TEXTO_SECUNDARIO}'>"
        f"<span style='width:11px;height:11px;border-radius:2px;"
        f"background:{theme.NIVELES[i]}'></span>{config.NIVELES_LOGRO[i]}</span>"
        for i in range(4)
    )
    st.markdown(f"<div style='margin-top:6px'>{piezas}</div>", unsafe_allow_html=True)


def _cortes(valores: np.ndarray, k: int = 5) -> list[float]:
    """Cortes de la escala del mapa.

    Se usan rupturas naturales en lugar de intervalos iguales porque los indicadores
    educativos están muy sesgados: con intervalos iguales casi todas las unidades caerían
    en la misma clase y el mapa quedaría plano.

    Los cortes repetidos se descartan. La primera ruptura coincide con el mínimo cuando
    la clase más baja tiene un solo valor, y entonces la leyenda dibujaba dos bloques
    seguidos con el mismo rótulo y uno de ellos de ancho cero. Pasaba en 31 de las 135
    combinaciones de grado, área, nivel e indicador.
    """
    limpios = valores[~np.isnan(valores)]
    if len(limpios) < k:
        return sorted(set(limpios.tolist()))
    try:
        clasificador = mapclassify.NaturalBreaks(limpios, k=k)
        crudos = [float(limpios.min())] + [float(b) for b in clasificador.bins]
    except Exception:
        crudos = [float(x) for x in np.quantile(limpios, np.linspace(0, 1, k + 1))]

    unicos: list[float] = []
    for corte in crudos:
        if not unicos or corte > unicos[-1]:
            unicos.append(corte)
    return unicos


def estilo_de_lienzo() -> str:
    """CSS del lienzo de Leaflet y de su globo de texto, para los mapas de la aplicación.

    Dos cosas que Leaflet trae por omisión y aquí sobran. El lienzo es claro, y sin
    mosaicos de fondo rompe el panel oscuro. Y el globo del tooltip no envuelve el
    texto, así que una línea larga lo estira hasta cruzar el mapa entero: con un ancho
    máximo se parte en varias líneas y deja de tapar lo que el usuario está mirando.
    """
    return (
        "<style>"
        f".folium-map, .leaflet-container {{background: {theme.SUPERFICIE_HUNDIDA} "
        "!important;}"
        # El globo se compone a mano, en una sola columna. La tabla de dos columnas
        # que arma folium se estrangula dentro de un ancho máximo: el rótulo
        # "% en niveles críticos" se lleva el ancho y el valor baja letra a letra.
        ".leaflet-tooltip {"
        f"  width: 230px; background: {theme.SUPERFICIE} !important;"
        f"  color: {theme.TEXTO}; border: 1px solid {theme.BORDE};"
        f"  border-radius: {theme.RADIO_INTERNO}; box-shadow: none;"
        "  opacity: 1 !important;"
        f"  font-family: {theme.FUENTE}; font-size: 0.76rem; line-height: 1.45;"
        "  padding: 10px 12px; white-space: normal; word-break: normal;"
        "}"
        ".leaflet-tooltip:before, .leaflet-tooltip:after {display: none;}"
        "</style>"
    )


class _BotonCentrar(MacroElement):
    """Control de Leaflet que devuelve el mapa a su encuadre inicial.

    Es un hijo del mapa y no un script suelto a propósito: `st_folium` no publica el
    script de la raíz de la figura, solo recorre el mapa y sus hijos, así que todo lo
    que se añada por fuera se pierde al renderizar dentro de Streamlit.
    """

    _name = "BotonCentrar"
    _template = Template("""
        {% macro script(this, kwargs) %}
            var {{ this.get_name() }} = L.Control.extend({
                options: {position: 'topleft'},
                onAdd: function (mapa) {
                    var caja = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
                    var boton = L.DomUtil.create('a', '', caja);
                    boton.href = '#';
                    boton.title = {{ this.rotulo }};
                    boton.setAttribute('role', 'button');
                    boton.setAttribute('aria-label', {{ this.rotulo }});
                    boton.innerHTML = {{ this.icono }};
                    L.DomEvent.on(boton, 'click', function (evento) {
                        L.DomEvent.stop(evento);
                        mapa.fitBounds({{ this.marco }});
                    });
                    L.DomEvent.disableClickPropagation(caja);
                    return caja;
                }
            });
            {{ this._parent.get_name() }}.addControl(new {{ this.get_name() }}());
        {% endmacro %}
    """)

    # Cuatro esquinas, el símbolo habitual de "encuadrar" en cualquier visor de mapas.
    ICONO = (
        "<svg width='13' height='13' viewBox='0 0 24 24' fill='none' "
        "stroke='currentColor' stroke-width='2.4' stroke-linecap='round' "
        "stroke-linejoin='round' style='vertical-align:-2px'>"
        "<path d='M3 8V5a2 2 0 0 1 2-2h3'/>"
        "<path d='M16 3h3a2 2 0 0 1 2 2v3'/>"
        "<path d='M21 16v3a2 2 0 0 1-2 2h-3'/>"
        "<path d='M8 21H5a2 2 0 0 1-2-2v-3'/></svg>"
    )

    def __init__(self, marco: list[list[float]]) -> None:
        super().__init__()
        self.marco = json.dumps(marco)
        self.rotulo = json.dumps("Volver al encuadre inicial")
        self.icono = json.dumps(self.ICONO)


def igualar_tarjetas() -> None:
    """Hace que las tarjetas de una fila midan lo mismo y respiren igual por abajo.

    Streamlit no estira el contenedor con borde al alto de su columna: la tarjeta que
    necesita un renglón más crece sola y las demás terminan en otra línea. Y con el alto
    forzado, el contenido se come el relleno inferior del contenedor y la última línea
    toca el borde, así que el aire de abajo lo pone la propia tarjeta.

    Se emite una vez por página. Dentro de cada contenedor, el contenido va envuelto en
    un `div` con la clase `tarjeta` y lo que deba quedar anclado abajo, con `pie`.
    """
    st.markdown(
        f"""<style>
/* `height: 100%` no sirve aquí: puesto en la columna anula el estiramiento que el
   propio flex de la fila ya hace, y el porcentaje se resuelve contra un padre de
   altura automática, así que la columna colapsaba al alto de su contenido. Con flex
   la altura se propaga por toda la cadena sin depender de porcentajes, y `:has` elige
   justo los ancestros de la tarjeta sin tener que nombrarlos uno a uno. */
[data-testid="stColumn"]:has(.tarjeta-pareja) {{
    display: flex;
    flex-direction: column;
}}
[data-testid="stColumn"]:has(.tarjeta-pareja) div:has(.tarjeta-pareja) {{
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
    min-height: 0;
}}
.tarjeta-pareja {{
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
}}
.tarjeta-pareja .pie {{
    margin-top: auto;
    padding-top: 14px;
    color: {theme.TEXTO_TENUE};
    font-size: 0.72rem;
    line-height: 1.45;
}}
</style>""",
        unsafe_allow_html=True,
    )


def encuadrar(mapa: folium.Map, capa: gpd.GeoDataFrame) -> None:
    """Ajusta el mapa a la extensión de sus datos y le pone el botón de volver a ella.

    Encuadre sobre lo que hay y no sobre un centro fijo, para que el mapa aproveche
    todo el espacio sea cual sea el nivel geográfico.

    El botón de volver vive dentro del mapa, debajo de los de acercar y alejar, que es
    donde se busca un control de mapa. Antes era un botón de Streamlit al lado de la
    leyenda y recentrar obligaba a recrear el componente entero, con su parpadeo y su
    nueva ejecución del script.
    """
    limites = capa.total_bounds
    marco = [[float(limites[1]), float(limites[0])],
             [float(limites[3]), float(limites[2])]]
    mapa.fit_bounds(marco)
    mapa.add_child(_BotonCentrar(marco))

def _nota_de_muestra(fila: pd.Series, muestra_minima: int) -> str:
    """Una línea que dice cuánta muestra hay detrás de la cifra y qué la limita.

    Reúne en un solo renglón los dos motivos por los que una unidad puede aparecer en
    negro, más el aviso de las UGEL cuya cifra incluye estudiantes de otro polígono.
    Juntos y no en filas aparte, porque una fila con el valor vacío sale igual de
    dibujada y se lee como un fallo.
    """
    evaluados = fila.get("n_estudiantes")
    if evaluados is None or pd.isna(evaluados):
        return "Esta unidad no tiene estudiantes evaluados."

    linea = f"{entero(evaluados)} evaluados"
    if muestra_minima and evaluados < muestra_minima:
        linea += f", por debajo del mínimo de {entero(muestra_minima)}: va en negro"
    frases = [linea + "."]
    nota = str(fila.get("nota_territorio") or "").strip()
    if nota:
        frases.append(nota.rstrip(".") + ".")
    return " ".join(frases)


def mapa_coropletico(
    capa: gpd.GeoDataFrame,
    columna: str,
    indicador: config.Indicador,
    columna_nombre: str = "nom_unidad",
    alto: int = 560,
    capa_fondo: gpd.GeoDataFrame | None = None,
    clave: str = "mapa",
    muestra_minima: int = 0,
) -> dict | None:
    """Dibuja el mapa y devuelve lo que el usuario haya seleccionado.

    Las unidades sin dato o con muestra insuficiente se pintan en negro, no en el color
    más claro de la escala: tienen que leerse como ausencia de información y no como un
    valor bajo. El resultado del clic permite que el resto de la página reaccione.

    El negro significa dos cosas, y el tooltip es el que las separa: una unidad puede no
    tener dato o tenerlo sobre tan pocos estudiantes que no se pinta. Purús aparece en
    negro con un 44,9 % y 26 evaluados, y sin esa línea parece un fallo del mapa.
    """
    # Sin mosaicos de fondo, a propósito. En un mapa coroplético el mapa base compite
    # con los datos, y además los proveedores gratuitos pasaron a exigir clave de API:
    # una demostración pública no debería depender de un servicio externo para dibujarse.
    # El contexto geográfico lo da la propia silueta del país.
    mapa = folium.Map(
        location=CENTRO_PERU,
        zoom_start=ZOOM_INICIAL,
        tiles=None,
        zoom_control=True,
        attributionControl=False,
    )
    mapa.get_root().html.add_child(folium.Element(estilo_de_lienzo()))

    # Territorio sin datos, debajo de todo, para que no queden huecos blancos.
    if capa_fondo is not None and len(capa_fondo):
        folium.GeoJson(
            capa_fondo,
            style_function=lambda _: {
                "fillColor": theme.SIN_DATO,
                "color": theme.SIN_DATO_BORDE,
                "weight": 0.4,
                "fillOpacity": 0.9,
            },
            interactive=False,
            name="Sin datos",
        ).add_to(mapa)

    # La escala se construye solo con las unidades que se van a pintar. Incluir las que
    # el propio mapa declara sin información suficiente movía las rupturas naturales y
    # dejaba 143 de las 208 UGEL en una clase de color distinta de la que les toca.
    if "muestra_suficiente" in capa.columns:
        pintadas = capa.loc[capa["muestra_suficiente"].fillna(True).astype(bool)]
    else:
        pintadas = capa
    valores = pintadas[columna].to_numpy(dtype=float)
    if not len(valores) or np.all(np.isnan(valores)):
        valores = capa[columna].to_numpy(dtype=float)
    cortes = _cortes(valores)
    paleta = theme.escala_de(indicador.mas_es_peor)

    escala = cm.StepColormap(
        colors=paleta[: max(len(cortes) - 1, 1)],
        index=cortes,
        vmin=float(np.nanmin(valores)),
        vmax=float(np.nanmax(valores)),
    )

    def estilo(elemento):
        propiedades = elemento["properties"]
        valor = propiedades.get(columna)
        suficiente = propiedades.get("muestra_suficiente", True)
        if valor is None or (isinstance(valor, float) and np.isnan(valor)) or not suficiente:
            return {
                "fillColor": theme.SIN_DATO,
                "color": theme.SIN_DATO_BORDE,
                "weight": 0.5,
                "fillOpacity": 0.92,
                "dashArray": "3,3",
            }
        return {
            "fillColor": escala(valor),
            "color": theme.FONDO,
            "weight": 0.6,
            "fillOpacity": 0.88,
        }

    # El tooltip no vuelca columnas: las escribe. Con los valores crudos salía
    # "44.852" en un mapa cuyo panel escribe "44,9 %", y la fila de la nota de
    # territorio aparecía vacía en las unidades que no tienen ninguna.
    capa = capa.copy()
    capa["_globo"] = [
        (
            f"<div style='font-weight:700;font-size:0.84rem;margin-bottom:5px'>"
            f"{fila.get(columna_nombre, '')}</div>"
            f"<div style='color:{theme.ACENTO};font-weight:600'>"
            f"{indicador.nombre}: "
            f"{formato(fila[columna], 1, indicador.sufijo) if pd.notna(fila[columna]) else 'sin dato'}"
            "</div>"
            f"<div style='color:{theme.TEXTO_SECUNDARIO};margin-top:4px'>"
            f"{_nota_de_muestra(fila, muestra_minima)}</div>"
        )
        for _, fila in capa.iterrows()
    ]

    folium.GeoJson(
        capa,
        style_function=estilo,
        highlight_function=lambda _: {"weight": 2.2, "color": theme.TEXTO},
        tooltip=folium.GeoJsonTooltip(
            fields=["_globo"],
            labels=False,
            sticky=True,
        ),
        name=indicador.nombre,
    ).add_to(mapa)

    encuadrar(mapa, capa)

    resultado = st_folium(
        mapa,
        height=alto,
        use_container_width=True,
        returned_objects=["last_active_drawing"],
        key=clave,
    )
    leyenda_escala(cortes, paleta, indicador)
    return resultado


def leyenda_escala(
    cortes: list[float], paleta: list[str], indicador: config.Indicador
) -> None:
    """Escala de color con su rótulo, y el máximo al final.

    Cada bloque se rotula con su límite inferior, así que sin el máximo al final no se
    podía leer dónde acaba la última clase: la leyenda decía 6, 19, 30, 42 y el valor
    más alto, 54,61, no aparecía en ningún sitio.
    """
    tramos = []
    for i in range(len(cortes) - 1):
        color = paleta[i] if i < len(paleta) else paleta[-1]
        tramos.append(
            f"<div style='flex:1;min-width:0'>"
            f"<div style='height:10px;background:{color}'></div>"
            f"<div style='font-size:0.66rem;color:{theme.TEXTO_SECUNDARIO};"
            f"margin-top:3px'>{formato(cortes[i], 0)}</div></div>"
        )
    maximo = (
        f"<div style='flex:0 0 auto;font-size:0.66rem;color:{theme.TEXTO_SECUNDARIO};"
        f"align-self:flex-end;padding-left:2px'>{formato(cortes[-1], 0)}</div>"
        if len(cortes) > 1
        else ""
    )
    st.markdown(
        f"""<div style='display:flex;align-items:flex-end;gap:14px;margin-top:6px'>
            <div style='flex:1;min-width:0'>
                <div class='rotulo' style='margin-bottom:4px'>{indicador.nombre}</div>
                <div style='display:flex;gap:2px;align-items:flex-end'>
                    {''.join(tramos)}{maximo}</div>
            </div>
            <div style='flex:0 0 auto;text-align:center'>
                <div style='width:34px;height:10px;background:{theme.SIN_DATO};
                            border:1px dashed {theme.SIN_DATO_BORDE}'></div>
                <div style='font-size:0.66rem;color:{theme.TEXTO_SECUNDARIO};
                            margin-top:3px'>sin dato suficiente</div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


def unidad_del_clic(resultado: dict | None, columna_codigo: str) -> str | None:
    """Código de la unidad sobre la que se hizo clic, si la hubo."""
    if not resultado:
        return None
    dibujo = resultado.get("last_active_drawing")
    if not dibujo:
        return None
    return (dibujo.get("properties") or {}).get(columna_codigo)


def panel_asistente(contraido: bool = False) -> None:
    """Panel del asistente conversacional.

    En las páginas con espacio va abierto; donde el contenido necesita el ancho, va
    dentro de un desplegable. La lógica vive en `core/chat.py`.
    """
    from . import chat  # aquí dentro para no crear una dependencia circular al importar

    if contraido:
        chat.panel_contraido()
        return
    with st.container(border=True):
        chat.panel()


def pie_de_pagina() -> None:
    """Cierre de página: la fuente y el camino a las aclaraciones.

    Las advertencias metodológicas viven en una sola página en lugar de repetirse en
    cada pantalla. Aquí queda el enlace para quien las busque.
    """
    st.divider()
    izquierda, derecha = st.columns([3, 1])
    izquierda.caption(
        f"{config.FUENTE} Evaluación muestral: todas las cifras están ponderadas con "
        "los pesos del diseño."
    )
    with derecha:
        st.page_link(
            "paginas/metodologia.py",
            label="Notas sobre los datos",
            icon=":material/help:",
        )


def glosario(filas: list[tuple[str, str]]) -> str:
    """Término y definición en dos columnas, como HTML para meter en un bloque.

    Una tabla y no una lista de términos en negrita seguidos de dos puntos: esa forma
    es de las que delatan un texto generado, y lo que hay aquí son definiciones.

    La primera columna mide lo que mide su término más largo. Sin eso, con la tabla a
    todo el ancho el sobrante se reparte entre las dos y la columna de términos acaba
    con el triple de lo que necesita, de modo que la definición arranca lejos y en un
    punto que no responde a nada. Las dos llevan la misma sangría: pegada al borde de
    su columna, la palabra parece el inicio de la tabla y no una celda.
    """
    celdas = "".join(
        f"<tr><td style='width:1%;padding:6px 18px 6px 14px;vertical-align:top;"
        f"white-space:nowrap;color:{theme.TEXTO_SECUNDARIO}'>{termino}</td>"
        f"<td style='padding:6px 0 6px 14px;vertical-align:top'>{definicion}</td></tr>"
        for termino, definicion in filas
    )
    return f"<table style='width:100%;border-collapse:collapse'>{celdas}</table>"
