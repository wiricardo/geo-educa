"""Análisis espacial: ¿los niveles críticos se agrupan o se reparten al azar?

La página no agrega un indicador nuevo. Toma el porcentaje en niveles críticos que ya
pinta el mapa y le hace una sola pregunta: cómo se reparte en el territorio. La respuesta
cambia lo que conviene hacer, y por eso la pregunta tiene su propia pantalla.

Dos decisiones que conviene tener a la vista:

1. El análisis se hace siempre sobre el porcentaje en niveles críticos. Las cinco
   categorías de conglomerado y sus colores en `theme.LISA` están pensados para un
   indicador donde más es peor (cálido para los niveles críticos, frío para lo
   contrario), así que cambiar de indicador invertiría el significado del color sin
   avisar.
2. El mapa de conglomerados necesita una función propia porque `cp.mapa_coropletico`
   pinta una escala continua y aquí las clases son cualitativas. Lo demás se reutiliza:
   el fondo gris de las unidades sin cálculo, el encuadre y el estilo son los del mapa.
"""

from __future__ import annotations

import random

import re

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from core import componentes as cp
from core import config, estado, theme
from geoeduca import almacen, espacial

# Parámetros del cálculo, fijos y declarados en pantalla. El p-valor sale de
# permutaciones: sin semilla fija, dos corridas de la misma vista darían cifras
# distintas y la pantalla dejaría de ser reproducible.
PERMUTACIONES = 999
SIGNIFICANCIA = 0.05
SEMILLA = 42

INDICADOR = config.INDICADORES["pct_critico"]

# Color de cada categoría. Las claves cortas vienen del motor (`CLAVES_LISA`) y los
# colores de `theme.LISA`: aquí solo se emparejan, no se define ningún color.
COLOR_CATEGORIA = {
    "aa": theme.LISA["alto_alto"],
    "ab": theme.LISA["alto_bajo"],
    "ba": theme.LISA["bajo_alto"],
    "bb": theme.LISA["bajo_bajo"],
    "ns": theme.LISA["sin_patron"],
}

# Leyenda completa. «Alto» y «bajo» son el % en niveles críticos de la unidad frente al
# promedio, y eso se declara una vez encima de la lista en lugar de repetirlo en los
# cuatro nombres. El orden es de lectura, no de magnitud: primero el conglomerado que
# concentra el problema.
LEYENDA = (
    (
        "aa",
        "Alto, rodeada de alto",
        "Los niveles críticos se acumulan en una zona contigua.",
    ),
    (
        "ab",
        "Alto, rodeada de bajo",
        "Aislada en un entorno con menos niveles críticos.",
    ),
    (
        "ba",
        "Bajo, rodeada de alto",
        "Excepción dentro de una zona con más.",
    ),
    ("bb", "Bajo, rodeada de bajo", "Una zona contigua sin concentración."),
    (
        "ns",
        "Sin patrón significativo",
        "Su parecido con las vecinas no se distingue del azar.",
    ),
)

COLUMNAS_DESCARTE = (
    "cod_unidad",
    "nom_unidad",
    "nom_padre",
    "n_estudiantes",
    "pct_critico",
    "motivo",
)


def en_peruano(texto: str) -> str:
    """Coma decimal en un texto que viene del motor de análisis.

    El motor escribe sus p-valores con punto decimal porque es una librería de cálculo
    y no sabe dónde se va a leer su resultado. La interfaz sí lo sabe, así que cambia el
    separador antes de mostrarlo. Solo toca el punto que está entre dos dígitos.
    """
    return re.sub(r"(?<=\d)\.(?=\d)", ",", texto)


@st.cache_data(show_spinner="Calculando el índice de Moran y los conglomerados locales")
def autocorrelacion(
    nivel: str,
    grado: str,
    area: str,
    muestra_minima: int,
    permutaciones: int = PERMUTACIONES,
    significancia: float = SIGNIFICANCIA,
) -> dict:
    """Moran global y LISA de una vista, en forma de datos simples.

    La caché es necesaria, no un adorno: las permutaciones se repetirían en cada
    interacción de la página (mover el mapa, abrir un desplegable) y el resultado sería
    siempre el mismo. Se devuelven tablas y números y no los objetos del motor, porque
    `st.cache_data` guarda una copia serializada de lo que retorna y la matriz de pesos
    no tiene por qué viajar hasta la página.
    """
    datos = estado.resultados(nivel, grado, area)
    capa = estado.geometrias(nivel)
    clave_geo = almacen.CAPAS[nivel][1]

    unida, diagnostico = espacial.unir_con_geometria(
        capa,
        datos,
        clave_geo,
        combinar_cartograficas=(nivel == "distrito"),
    )

    resultado = espacial.analizar_autocorrelacion(
        unida,
        INDICADOR.columna,
        permutaciones=permutaciones,
        nivel_significancia=significancia,
        semilla=SEMILLA,
        muestra_minima=muestra_minima,
    )
    global_ = resultado.global_
    vecindad = resultado.vecindad

    descartadas = vecindad.descartadas
    columnas = [c for c in COLUMNAS_DESCARTE if c in descartadas.columns]
    situaciones = diagnostico["situacion"].value_counts().to_dict()
    # Una unidad de la cartografía sin resultados en esta vista no aparece en ninguna
    # tabla de datos, así que su nombre solo está en la capa.
    sin_dato_codigos = diagnostico.loc[
        diagnostico["situacion"] == "geometría sin dato", "codigo"
    ].astype(str)
    columna_nombre_capa = almacen.NOMBRE_EN_CAPA[nivel]
    nombres_capa = capa.assign(**{clave_geo: capa[clave_geo].astype(str)}).set_index(
        clave_geo
    )[columna_nombre_capa]
    sin_dato_nombres = [
        str(nombres_capa.get(cod, cod)) for cod in sorted(sin_dato_codigos)
    ]

    return {
        "i": global_.i,
        "esperado": global_.valor_esperado,
        "p_valor": global_.p_valor,
        "z": global_.z,
        "significativo": global_.significativo,
        "interpretacion": global_.interpretacion,
        "n_unidades": global_.n_unidades,
        "permutaciones": global_.permutaciones,
        "significancia": global_.nivel_significancia,
        "n_con_dato": int(len(unida)),
        "muestra_minima": vecindad.muestra_minima,
        "vecinos_promedio": vecindad.vecinos_promedio,
        "n_componentes": vecindad.n_componentes,
        "advertencias": list(vecindad.advertencias),
        "islas": vecindad.islas.copy(),
        "descartadas": descartadas[columnas].copy(),
        "lisa": resultado.local.tabla.copy(),
        "conteo": resultado.local.conteo.copy(),
        "n_significativas": resultado.local.n_significativas,
        "sin_geometria": int(situaciones.get("dato sin geometría", 0)),
        "sin_dato": int(situaciones.get("geometría sin dato", 0)),
        "sin_dato_nombres": sin_dato_nombres,
        "clave_geo": clave_geo,
    }


def mapa_conglomerados(
    capa,
    capa_excluidas=None,
    capa_fondo=None,
    # Al alto de la leyenda de al lado, que con las explicaciones de cada categoría
    # ocupa más que los 540 de antes. Un mapa del país agradece el sitio de sobra.
    alto: int = 700,
    clave: str = "mapa_lisa",
) -> None:
    """Mapa de las cinco categorías de conglomerado.

    Es el mismo mapa del resto de la aplicación con un relleno distinto: sin mosaicos de
    fondo, encuadrado sobre la extensión de los datos y con las unidades que no entraron
    al cálculo en negro con borde punteado, para que se lean como ausencia de resultado y
    no como una categoría más.
    """
    mapa = folium.Map(
        location=cp.CENTRO_PERU,
        zoom_start=cp.ZOOM_INICIAL,
        tiles=None,
        zoom_control=True,
        attributionControl=False,
    )
    # Sin mosaicos, el lienzo de Leaflet queda claro por omisión y rompe el panel oscuro.
    mapa.get_root().html.add_child(folium.Element(cp.estilo_de_lienzo()))

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
            name="Territorio sin cálculo",
        ).add_to(mapa)

    if capa_excluidas is not None and len(capa_excluidas):
        folium.GeoJson(
            capa_excluidas,
            style_function=lambda _: {
                "fillColor": theme.SIN_DATO,
                "color": theme.SIN_DATO_BORDE,
                "weight": 0.5,
                "fillOpacity": 0.92,
                "dashArray": "3,3",
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["nombre", "nota"],
                aliases=["Unidad", "Situación"],
                sticky=True,
            ),
            name="No entró al cálculo",
        ).add_to(mapa)

    folium.GeoJson(
        capa,
        style_function=lambda elemento: {
            "fillColor": COLOR_CATEGORIA.get(
                elemento["properties"].get("clave"), theme.SIN_DATO
            ),
            "color": theme.FONDO,
            "weight": 0.6,
            "fillOpacity": 0.9,
        },
        highlight_function=lambda _: {"weight": 2.2, "color": theme.TEXTO},
        tooltip=folium.GeoJsonTooltip(
            fields=["nombre", "categoria", "etq_valor", "etq_p", "etq_vecinos"],
            aliases=[
                "Unidad",
                "Categoría",
                INDICADOR.nombre,
                "p-valor local",
                "Vecinas",
            ],
            sticky=True,
        ),
        name="Conglomerados locales",
    ).add_to(mapa)

    cp.encuadrar(mapa, capa)

    # Sin objetos de retorno: esta página no reacciona al clic y así el mapa no provoca
    # una nueva ejecución del script cada vez que se mueve.
    st_folium(
        mapa,
        height=alto,
        use_container_width=True,
        returned_objects=[],
        key=clave,
    )


# Tres tonos y no los cinco de la escala del mapa: con los cinco, que son vecinos entre
# sí, las dos cuadrículas de abajo salían indistinguibles a este tamaño y el dibujo no
# enseñaba nada. Se toman los extremos y el centro.
TONOS_DIBUJO = (theme.ESCALA_MAPA[0], theme.ESCALA_MAPA[2], theme.ESCALA_MAPA[4])


def cuadricula(celdas: list[int], lado: int = 16, hueco: int = 2) -> str:
    """Una cuadrícula de 5×5 en SVG, cada celda con uno de los tres tonos."""
    paso = lado + hueco
    medida = 5 * lado + 4 * hueco
    rectangulos = "".join(
        f"<rect x='{(i % 5) * paso}' y='{(i // 5) * paso}' width='{lado}' "
        f"height='{lado}' rx='2' fill='{TONOS_DIBUJO[valor]}'/>"
        for i, valor in enumerate(celdas)
    )
    return (
        f"<svg width='{medida}' height='{medida}' viewBox='0 0 {medida} {medida}'>"
        f"{rectangulos}</svg>"
    )


# Un mapa inventado donde los valores altos se tocan, y el mismo mapa con los valores
# barajados. Es lo que hace el cálculo 999 veces para saber si el índice observado se
# podía conseguir por azar, así que el dibujo explica la pregunta y el método a la vez.
# La baraja lleva semilla fija para que el dibujo no cambie entre ejecuciones.
_AGRUPADO = [
    2, 2, 2, 1, 0,
    2, 2, 1, 1, 0,
    2, 1, 1, 0, 0,
    1, 1, 0, 0, 0,
    1, 0, 0, 0, 0,
]
_AL_AZAR = random.Random(11).sample(_AGRUPADO, len(_AGRUPADO))


def leyenda_conglomerados(conteo: dict[str, int], n_unidades: int) -> str:
    """Leyenda única del mapa: color, nombre, cuántas unidades, qué parte y qué es.

    Antes había dos, una al lado del mapa con los recuentos y otra debajo con las
    explicaciones, que repetían los mismos cinco nombres y la misma aclaración de qué
    son alto y bajo. Devuelve el HTML en lugar de pintarlo, para que el panel entero
    quepa en un solo bloque y pueda estirarse al alto del mapa.
    """
    filas = []
    for clave, nombre, explicacion in LEYENDA:
        cuenta = int(conteo.get(clave, 0))
        parte = 100.0 * cuenta / n_unidades if n_unidades else 0.0
        filas.append(
            f"<div style='padding:7px 0;border-top:1px solid {theme.BORDE_SUAVE}'>"
            f"<div style='display:flex;align-items:center;gap:8px'>"
            f"<span style='flex:0 0 auto;width:10px;height:10px;border-radius:2px;"
            f"background:{COLOR_CATEGORIA[clave]};"
            f"border:1px solid {theme.BORDE}'></span>"
            f"<span style='flex:1;min-width:0;font-size:0.78rem;font-weight:600;"
            f"color:{theme.TEXTO}'>{nombre}</span>"
            f"<span style='flex:0 0 auto;font-size:0.82rem;font-weight:700;"
            f"font-variant-numeric:tabular-nums;color:{theme.TEXTO}'>"
            f"{cp.entero(cuenta)}</span>"
            f"<span style='flex:0 0 42px;text-align:right;font-size:0.72rem;"
            f"font-variant-numeric:tabular-nums;color:{theme.TEXTO_TENUE}'>"
            f"{cp.formato(parte, 1, ' %')}</span></div>"
            + (
                f"<div class='nota' style='font-size:0.73rem;margin-left:18px'>"
                f"{explicacion}</div>"
                if explicacion
                else ""
            )
            + "</div>"
        )
    # El negro va al final y sin recuento: esas unidades no están en el denominador de
    # las que sí entraron, y ponerlas en la misma columna de porcentajes sugeriría que
    # suman con las otras cinco.
    filas.append(
        f"<div style='padding:7px 0;border-top:1px solid {theme.BORDE_SUAVE}'>"
        f"<div style='display:flex;align-items:center;gap:8px'>"
        f"<span style='flex:0 0 auto;width:10px;height:10px;"
        f"background:{theme.SIN_DATO};"
        f"border:1px dashed {theme.SIN_DATO_BORDE}'></span>"
        f"<span style='flex:1;min-width:0;font-size:0.78rem;font-weight:600;"
        f"color:{theme.TEXTO}'>No entró al cálculo</span></div>"
        f"<div class='nota' style='font-size:0.73rem;margin-left:18px'>Sin dato, "
        f"muestra insuficiente o sin vecinas calculables.</div></div>"
    )
    return "".join(filas)


f = estado.filtros()

cp.encabezado(
    "¿Los niveles críticos se agrupan en el territorio?",
    f"{INDICADOR.nombre} en {f.descripcion()}, medido con el índice de Moran",
)

# El nivel geográfico se lleva el ancho que necesite: cinco opciones en una fila.
col_nivel, col_min, _ = st.columns([3.3, 1.2, 1.5])

# Con clave propia y sin `index`: el widget conserva su identidad entre pasadas. Ver
# `estado.sembrar`.
estado.sembrar("espacial_nivel", "nivel_geografico")
estado.sembrar("espacial_muestra_minima", "muestra_minima")

with col_nivel:
    nivel = st.radio(
        "Nivel geográfico",
        options=list(config.NIVELES_GEOGRAFICOS),
        format_func=lambda c: config.NIVELES_GEOGRAFICOS[c],
        horizontal=True,
        key="espacial_nivel",
    )

with col_min:
    minimo = st.number_input(
        "Muestra mínima",
        min_value=0,
        max_value=200,
        step=10,
        key="espacial_muestra_minima",
        help=(
            "Las unidades con menos estudiantes evaluados que este número quedan fuera "
            "del cálculo. Treinta es el corte que usa el resto de la plataforma: "
            "moverlo sirve para comprobar cuánto depende el resultado de esa decisión, "
            "no para mejorarlo.\n\n"
            "Bajarlo mete unidades cuyo porcentaje es casi ruido muestral, y que "
            "además pasan a enlazar como vecinas a otras que no se tocan. Subirlo deja "
            "más territorio fuera del mapa y puede partir la matriz en trozos "
            "separados."
        ),
    )

estado.actualizar(nivel_geografico=nivel, muestra_minima=minimo)
f = estado.filtros()

cp.aviso_representatividad(f.grado, f.nivel_geografico)

try:
    analisis = autocorrelacion(
        f.nivel_geografico, f.grado, f.area, f.muestra_minima
    )
except (ValueError, KeyError) as error:
    st.warning(
        "No se puede medir la agrupación territorial con esta selección: "
        f"{error}"
    )
    st.stop()

lisa = analisis["lisa"]
conteo = analisis["conteo"]
por_clave = dict(zip(conteo["clave"], conteo["n_unidades"]))
n_unidades = analisis["n_unidades"]

# El veredicto, en corto. La frase larga del motor se queda para el chat, que no tiene
# al lado ni la tira de cifras ni el dibujo y necesita decirlo todo en texto.
if not analisis["significativo"]:
    veredicto = "El reparto de los valores no se distingue del azar."
elif analisis["i"] > 0:
    veredicto = "Los valores se agrupan en el territorio."
else:
    veredicto = "Los valores se alternan en el territorio."
veredicto += (
    " El índice cambia con el nivel geográfico y con el grado y el área que se miren."
)
islas = len(analisis["islas"])
if islas:
    veredicto += (
        f" {cp.unidades(islas)} quedaron fuera del cálculo por no tener vecinas."
    )

cp.igualar_tarjetas()
col_moran, col_dibujo = st.columns([1.35, 1], gap="medium")

with col_moran:
    with st.container(border=True):
        # La cifra se queda sola en su columna y todo lo demás se reparte a su derecha
        # en una rejilla de tres. Antes el p y el z iban sueltos al lado del número y
        # dejaban vacía la mitad derecha de la tarjeta.
        juicio = "significativo" if analisis["significativo"] else "no significativo"
        datos = (
            (
                espacial.formato_p(analisis["p_valor"], PERMUTACIONES),
                f"{juicio}, a {cp.formato(analisis['z'], 1)} desviaciones del azar",
                3,
            ),
            (cp.entero(n_unidades), "unidades analizadas", 1),
            (cp.formato(analisis["vecinos_promedio"], 1), "vecinas en promedio", 1),
            (cp.entero(PERMUTACIONES), "mapas barajados", 1),
        )
        celdas = "".join(
            f"<div style='grid-column:span {ancho}'>"
            f"<div style='font-size:1.1rem;font-weight:700;line-height:1.2;"
            f"color:{theme.TEXTO}'>{valor}</div>"
            f"<div class='nota' style='font-size:0.72rem'>{rotulo}</div></div>"
            for valor, rotulo, ancho in datos
        )
        posicion = min(max((float(analisis["i"]) + 1) / 2 * 100, 0.0), 100.0)
        st.markdown(
            f"<div class='tarjeta-pareja'>"
            f"<div class='rotulo'>Índice de Moran del {INDICADOR.nombre.lower()}</div>"
            f"<div style='display:flex;gap:20px;align-items:stretch;margin-top:8px'>"
            f"<div style='flex:0 0 auto;display:flex;align-items:center'>"
            f"<span style='font-size:2.6rem;font-weight:700;letter-spacing:-1.5px;"
            f"line-height:1;color:{theme.ACENTO}'>"
            f"{cp.formato(analisis['i'], 4)}</span></div>"
            f"<div style='flex:0 0 1px;background:{theme.BORDE}'></div>"
            f"<div style='flex:1;min-width:0;display:grid;"
            f"grid-template-columns:repeat(3, 1fr);gap:12px 14px;"
            f"align-content:center'>{celdas}</div>"
            f"</div>"
            f"<div style='margin-top:34px'>"
            f"<div style='position:relative;height:6px;border-radius:3px;"
            f"background:{theme.SUPERFICIE_HUNDIDA}'>"
            f"<div style='position:absolute;left:50%;top:-4px;width:1px;height:14px;"
            f"background:{theme.BORDE}'></div>"
            f"<div style='position:absolute;left:{posicion:.1f}%;top:-5px;width:3px;"
            f"height:16px;border-radius:2px;background:{theme.ACENTO}'></div>"
            f"<div style='position:absolute;left:{posicion:.1f}%;top:-24px;"
            f"transform:translateX(-50%);font-size:0.72rem;font-weight:600;"
            f"white-space:nowrap;color:{theme.ACENTO}'>"
            f"{cp.formato(analisis['i'], 4)}</div>"
            f"</div>"
            f"<div style='display:flex;justify-content:space-between;margin-top:5px'>"
            f"<span class='nota' style='font-size:0.7rem'>−1 alternados</span>"
            f"<span class='nota' style='font-size:0.7rem'>0 al azar</span>"
            f"<span class='nota' style='font-size:0.7rem'>1 agrupados</span>"
            f"</div></div>"
            f"<div class='pie'>{veredicto}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

with col_dibujo:
    with st.container(border=True):
        st.markdown(
            f"<div class='tarjeta-pareja'>"
            "<div class='rotulo'>Qué compara el índice</div>"
            # El bloque ocupa el espacio que queda entre el rótulo y el pie, y se
            # centra en él: anclado arriba, todo el sobrante de estirar la tarjeta se
            # acumulaba en un hueco justo encima de la frase final.
            "<div style='flex:1;display:flex;gap:18px;margin-top:10px;"
            "flex-wrap:wrap;align-items:center;align-content:center;"
            "justify-content:center'>"
            + "".join(
                f"<div style='flex:0 0 auto'><div>{dibujo}</div>"
                f"<div style='font-size:0.78rem;font-weight:600;margin-top:7px;"
                f"color:{theme.TEXTO}'>{titulo}</div>"
                f"<div class='nota' style='font-size:0.72rem'>{pie}</div></div>"
                for dibujo, titulo, pie in (
                    (cuadricula(_AGRUPADO), "Agrupado", "Los altos se tocan"),
                    (cuadricula(_AL_AZAR), "Al azar", "Los mismos valores, repartidos"),
                )
            )
            + "</div>"
            f"<div class='pie'>Cada celda es una unidad con su "
            f"{INDICADOR.nombre.lower()}. El índice compara el mapa real con "
            f"{cp.entero(PERMUTACIONES)} barajados como el de la derecha.</div>"
            "</div>",
            unsafe_allow_html=True,
        )

# Para qué sirve saberlo, en una línea: el detalle estaba en dos párrafos que repetían
# lo que el dibujo ya enseña.
st.markdown(
    "<div class='nota' style='margin-top:10px'>Donde los niveles críticos se concentran "
    "se puede intervenir por zonas enteras, en vez de repartir el esfuerzo por todo el "
    "país. Eso no significa que se pueda atribuir una causa.</div>",
    unsafe_allow_html=True,
)

cp.separador()

# La capa del mapa se arma aquí y no dentro de la caché: las geometrías ya están en
# memoria y unir 200 filas en cada ejecución no cuesta nada, mientras que guardar la
# capa unida en la caché duplicaría los polígonos por cada combinación de filtros.
capa_nivel = estado.geometrias(f.nivel_geografico)
datos_nivel = estado.resultados(f.nivel_geografico, f.grado, f.area).assign(
    codigo=lambda t: t["cod_unidad"].astype(str)
)
clave_geo = analisis["clave_geo"]
base = capa_nivel[[clave_geo, "geometry"]].copy()
base["codigo"] = base[clave_geo].astype(str)

etiquetas = lisa.assign(
    etq_valor=lisa["valor"].map(lambda v: cp.formato(v, 1, INDICADOR.sufijo)),
    etq_p=lisa["p_valor"].map(lambda v: cp.formato(v, 3)),
    etq_vecinos=lisa["n_vecinos"].map(cp.entero),
)
columnas_capa = [
    "codigo",
    "nombre",
    "categoria",
    "clave",
    "etq_valor",
    "etq_p",
    "etq_vecinos",
]
capa_lisa = base.merge(etiquetas[columnas_capa], on="codigo", how="inner")

# Unidades del nivel que no entraron al cálculo, con el motivo cuando se conoce.
motivos = dict(
    zip(
        analisis["descartadas"]["cod_unidad"].astype(str),
        analisis["descartadas"]["motivo"],
    )
)
nombres_nivel = dict(zip(datos_nivel["codigo"], datos_nivel["nom_unidad"]))
capa_excluidas = base[~base["codigo"].isin(capa_lisa["codigo"])].copy()
capa_excluidas["nombre"] = capa_excluidas["codigo"].map(nombres_nivel).fillna(
    "Unidad sin resultados en esta vista"
)
capa_excluidas["nota"] = (
    capa_excluidas["codigo"].map(motivos).fillna("sin dato en esta vista")
)

# Las capas de UGEL y DRE se arman disolviendo los distritos con unidad asignada, así
# que no cubren todo el país: sin un fondo debajo el resto quedaría en blanco.
fondo = None
if f.nivel_geografico in ("ugel", "dre"):
    fondo = estado.geometrias("departamento")

cp.igualar_tarjetas()
col_mapa, col_resumen = st.columns([2.5, 1], gap="medium")

with col_mapa:
    mapa_conglomerados(
        capa_lisa,
        capa_excluidas=capa_excluidas,
        capa_fondo=fondo,
        clave=f"lisa_{f.nivel_geografico}_{f.grado}_{f.area}_{f.muestra_minima}",
    )

with col_resumen:
    with st.container(border=True):
        st.markdown(
            "<div class='tarjeta-pareja'>"
            "<div class='rotulo'>Categorías de conglomerado</div>"
            f"<div class='nota' style='margin:-2px 0 2px'>Alto y bajo son el "
            f"{INDICADOR.nombre.lower()} de la unidad frente al promedio de las "
            "analizadas, no frente a un umbral de política.</div>"
            + leyenda_conglomerados(por_clave, n_unidades)
            + f"<div class='pie'>Patrón local significativo en "
            f"{cp.entero(analisis['n_significativas'])} de las "
            f"{cp.entero(n_unidades)} unidades del cálculo.</div>"
            "</div>",
            unsafe_allow_html=True,
        )


cp.separador()

alto_alto = lisa[lisa["clave"] == "aa"].copy()

with st.container(border=True):
    st.markdown(
        f"**Las {cp.unidades(len(alto_alto))} donde se acumulan "
        f"los {INDICADOR.nombre.lower().removeprefix('% en ')}**"
    )
    st.markdown(
        "<div class='nota' style='margin-bottom:14px'>Están sobre el promedio y sus "
        "vecinas también, así que forman zonas continuas donde una intervención alcanza "
        "a varias a la vez. Por cuál empezar se decide en Focalización.</div>",
        unsafe_allow_html=True,
    )
    if len(alto_alto):
        contexto = datos_nivel[
            [
                "codigo",
                "nom_padre",
                "n_estudiantes",
                "poblacion_estimada",
                "poblacion_critica",
            ]
        ]
        tabla_aa = (
            alto_alto.merge(contexto, on="codigo", how="left")
            .sort_values("valor", ascending=False)
            .reset_index(drop=True)
        )
        presentacion = pd.DataFrame(
            {
                "Unidad": tabla_aa["nombre"],
                "Pertenece a": tabla_aa["nom_padre"],
                INDICADOR.nombre: tabla_aa["valor"].map(
                    lambda v: cp.formato(v, 1, INDICADOR.sufijo)
                ),
                "p-valor local": tabla_aa["p_valor"].map(lambda v: cp.formato(v, 3)),
                "Vecinas": tabla_aa["n_vecinos"].map(cp.entero),
                "Evaluados": tabla_aa["n_estudiantes"].map(cp.entero),
                "Estimados": tabla_aa["poblacion_estimada"].map(cp.entero),
                "Estudiantes en niveles críticos": tabla_aa["poblacion_critica"].map(
                    cp.entero
                ),
            }
        )
        st.dataframe(
            presentacion,
            width="stretch",
            hide_index=True,
            height=min(60 + 35 * len(presentacion), 330),
        )
        st.page_link(
            "paginas/focalizacion.py",
            label="Ordenar estas unidades por prioridad en Focalización",
            icon=":material/target:",
        )
    else:
        st.caption(
            "Con los filtros actuales ninguna unidad forma un conglomerado alto "
            "significativo."
        )

cp.separador()

islas = analisis["islas"]
descartadas = analisis["descartadas"]
por_motivo = (
    descartadas["motivo"].value_counts().to_dict() if len(descartadas) else {}
)

with st.container(border=True):
    st.markdown("**Lo que queda fuera del cálculo**")
    st.markdown(
        f"<div class='nota' style='margin-bottom:6px'>De las "
        f"{cp.entero(analisis['n_con_dato'])} unidades con dato en esta vista, "
        f"{cp.entero(n_unidades)} entraron a la matriz de vecindad.</div>",
        unsafe_allow_html=True,
    )

    # Un motivo por fila, con su cifra delante. Antes iban las cuatro frases seguidas
    # separadas solo por un salto de línea, y había que leerlas enteras para saber
    # cuántos motivos distintos había y cuántas unidades caían en cada uno.
    motivos = []
    chicas = sum(v for k, v in por_motivo.items() if k.startswith("muestra menor"))
    if chicas:
        motivos.append((
            cp.entero(chicas),
            "Muestra insuficiente",
            f"Menos de {cp.entero(analisis['muestra_minima'])} estudiantes evaluados: "
            "su porcentaje tiene demasiado ruido para compararlo con el de sus vecinas.",
        ))
    if len(islas):
        # Con pocas islas conviene nombrarlas; con muchas, la lista se vuelve ilegible
        # y basta con las primeras, porque la tabla de descartes las trae todas.
        todas = [str(n) for n in islas.get("nombre", islas["codigo"]).tolist()]
        nombres_islas = ", ".join(todas[:6])
        if len(todas) > 6:
            nombres_islas += f" y {cp.entero(len(todas) - 6)} más"
        motivos.append((
            cp.entero(len(islas)),
            "Sin ninguna vecina calculable",
            f"{nombres_islas}. Sin vecinas no hay con qué compararlas, y dejarlas "
            "dentro las metería como si su entorno fuera exactamente el promedio.",
        ))
    if analisis["sin_geometria"]:
        motivos.append((
            cp.entero(analisis["sin_geometria"]),
            "Con dato pero sin polígono",
            "No pueden entrar a una matriz de contigüidad. Sus estudiantes sí cuentan "
            "en los agregados.",
        ))

    if motivos:
        filas_motivo = "".join(
            # La cifra se centra con el bloque de dos líneas que tiene al lado y se
            # alinea a la derecha de su columna, para que quede pegada al texto que
            # cuenta en lugar de flotar lejos.
            f"<div style='display:flex;gap:11px;align-items:center;padding:9px 0;"
            f"border-top:1px solid {theme.BORDE_SUAVE}'>"
            f"<span style='flex:0 0 30px;text-align:right;font-size:1.3rem;"
            f"font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums;"
            f"color:{theme.TEXTO}'>{cifra}</span>"
            f"<span style='flex:1;min-width:0'>"
            f"<span style='font-size:0.82rem;font-weight:600;color:{theme.TEXTO}'>"
            f"{titulo}</span>"
            + (
                f"<div class='nota' style='font-size:0.76rem;margin-top:1px'>"
                f"{detalle}</div>"
                if detalle
                else ""
            )
            + "</span></div>"
            for cifra, titulo, detalle in motivos
        )
        st.markdown(filas_motivo, unsafe_allow_html=True)

    if analisis["sin_dato"]:
        # Fuera de la lista de arriba a propósito: esas unidades nunca estuvieron entre
        # las que tienen dato, así que no son un descarte y sumarlas al mismo recuento
        # dejaba la cuenta sin cuadrar con la tabla.
        nombres_sin_dato = ", ".join(analisis["sin_dato_nombres"][:6])
        if len(analisis["sin_dato_nombres"]) > 6:
            nombres_sin_dato += (
                f" y {cp.entero(len(analisis['sin_dato_nombres']) - 6)} más"
            )
        verbo = "tiene" if analisis["sin_dato"] == 1 else "tienen"
        st.markdown(
            f"<div class='nota' style='margin-top:10px'>Aparte, "
            f"{cp.unidades(analisis['sin_dato'])} de la cartografía no {verbo} "
            f"resultados en esta vista: {nombres_sin_dato}.</div>",
            unsafe_allow_html=True,
        )

    if analisis["n_componentes"] > 1:
        st.markdown(
            f"<div class='nota' style='margin-top:8px'>La matriz queda partida en "
            f"{cp.entero(analisis['n_componentes'])} componentes separados: el índice "
            "global resume un territorio que no es continuo.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    with st.expander(f"Ver las {cp.unidades(len(descartadas))} descartadas"):
        if len(descartadas):
            columnas = {
                "nom_unidad": "Unidad",
                "nom_padre": "Pertenece a",
                "n_estudiantes": "Evaluados",
                "pct_critico": INDICADOR.nombre,
                "motivo": "Motivo",
            }
            presentes = [c for c in columnas if c in descartadas.columns]
            vista = descartadas[presentes].rename(columns=columnas)
            if "Evaluados" in vista.columns:
                vista["Evaluados"] = descartadas["n_estudiantes"].map(cp.entero)
            if INDICADOR.nombre in vista.columns:
                vista[INDICADOR.nombre] = descartadas["pct_critico"].map(
                    lambda v: cp.formato(v, 1, INDICADOR.sufijo)
                )
            st.dataframe(
                vista.sort_values("Motivo"),
                width="stretch",
                hide_index=True,
                height=300,
            )
        else:
            st.caption("Ninguna unidad quedó fuera en esta vista.")
        # Los avisos del motor se muestran tal como vienen, salvo el de la librería de
        # pesos, que llega en inglés y con índices internos de fila: su contenido ya
        # está arriba, en castellano, como islas y componentes separados.
        avisos = [
            a.replace("(ver `descartadas`)", "(la tabla de arriba)")
            for a in analisis["advertencias"]
            if "weights matrix" not in a
        ]
        if avisos:
            st.caption("Avisos del cálculo: " + en_peruano(" ".join(avisos)))

cp.pie_de_pagina()
