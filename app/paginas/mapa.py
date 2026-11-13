"""Mapa de resultados: la pantalla de entrada.

El mapa domina la pantalla porque es la razón de ser del proyecto. Todo lo demás de esta
página reacciona a lo que se selecciona en él.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import componentes as cp
from core import config, estado, theme
from geoeduca import almacen

f = estado.filtros()
indicador = config.INDICADORES[f.indicador]

cp.encabezado(
    "Mapa de resultados",
    f"{f.descripcion()}. {indicador.descripcion}",
)

# Controles propios del mapa, separados de los filtros globales de la barra lateral. El
# nivel geográfico se lleva el ancho que necesite: son cinco opciones en una fila, y con
# la columna estrecha las dos últimas caían a una segunda línea que parecía otro control.
col_ind, col_nivel = st.columns([1.7, 3.6])

# Cada control lleva su propia clave y no recibe `index` ni `value`: así Streamlit lo
# reconoce como el mismo widget en todas las pasadas. Con el índice calculado desde el
# filtro, cambiarlo creaba un widget nuevo, se perdía el primer clic y durante un instante
# se dibujaban los dos a la vez.
estado.sembrar("mapa_indicador", "indicador")
estado.sembrar("mapa_nivel", "nivel_geografico")

with col_ind:
    clave_ind = st.selectbox(
        "Indicador",
        options=list(config.INDICADORES),
        format_func=lambda c: config.INDICADORES[c].nombre,
        key="mapa_indicador",
    )

with col_nivel:
    nivel = st.radio(
        "Nivel geográfico",
        options=list(config.NIVELES_GEOGRAFICOS),
        format_func=lambda c: config.NIVELES_GEOGRAFICOS[c],
        horizontal=True,
        key="mapa_nivel",
    )

# El umbral de muestra no es un control aquí: es la decisión de calidad con la que esta
# página se lee, y moverlo cambia qué se ve sin que cambie ningún dato. Bajándolo a cero,
# una UGEL de tres estudiantes con 100 % se pinta con el mismo peso que Lima con 3 061.
# Quien quiera ver su efecto lo tiene en Análisis espacial y en Focalización, que es
# donde el umbral forma parte del análisis y no de la primera lectura.
MUESTRA_MINIMA = config.MUESTRA_MINIMA

estado.actualizar(indicador=clave_ind, nivel_geografico=nivel)
f = estado.filtros()
indicador = config.INDICADORES[f.indicador]

cp.aviso_representatividad(f.grado, f.nivel_geografico)

datos = estado.resultados(f.nivel_geografico, f.grado, f.area)
if datos.empty:
    st.warning("No hay resultados para el grado y el área seleccionados.")
    st.stop()

datos = datos.assign(muestra_suficiente=datos["n_estudiantes"] >= MUESTRA_MINIMA)

# El umbral viaja hasta la unión porque el polígono combinado recalcula su suficiencia
# sobre la muestra sumada. Heredándola de uno de los dos distritos, Mazamari - Pangoa se
# pintaba gris con 436 evaluados en cuanto el umbral pasaba de 170.
capa = almacen.unir_con_geometria(
    datos, f.nivel_geografico, muestra_minima=MUESTRA_MINIMA
)

# Catorce distritos están atendidos por más de una UGEL y la cartografía no los puede
# partir, así que la UGEL que no se queda el polígono conserva su cifra completa sobre
# un territorio que ya no contiene a esos estudiantes. No se puede arreglar en el mapa,
# pero sí decirlo en la unidad donde ocurre.
prestado = (
    almacen.territorio_prestado(f.grado, f.area)
    if f.nivel_geografico == "ugel"
    else pd.DataFrame()
)
if not prestado.empty:
    parte = dict(zip(prestado["cod_unidad"], prestado["pct_fuera"]))
    capa["nota_territorio"] = [
        f"{parte[c]:.0f} % de sus evaluados están fuera de este polígono"
        if c in parte
        else ""
        for c in capa["cod_unidad"]
    ]
sin_geometria = almacen.unidades_sin_geometria(datos, f.nivel_geografico)
clave_geo = almacen.CAPAS[f.nivel_geografico][1]

fondo = None
if f.nivel_geografico in ("ugel", "dre"):
    # Estas capas se construyen desde los distritos muestreados, así que no cubren todo
    # el país. Sin un fondo debajo, el territorio restante se vería como un hueco blanco.
    fondo = estado.geometrias("departamento")

# `st_folium` recuerda el último polígono sobre el que se hizo clic y lo sigue
# devolviendo en cada ejecución. Deseleccionar no bastaba: a la pasada siguiente se leía
# otra vez el mismo clic y el panel volvía a la unidad. Rehacer el componente con otra
# clave es lo que borra ese recuerdo, y solo ocurre al volver al resultado nacional.
vuelta = st.session_state.setdefault("mapa_vuelta", 0)

col_mapa, col_panel = st.columns([2.6, 1], gap="medium")

with col_mapa:
    resultado = cp.mapa_coropletico(
        capa,
        indicador.columna,
        indicador,
        alto=600,
        capa_fondo=fondo,
        clave=f"mapa_{f.nivel_geografico}_{f.grado}_{f.area}_{f.indicador}_{vuelta}",
        muestra_minima=MUESTRA_MINIMA,
    )
    seleccion = cp.unidad_del_clic(resultado, clave_geo)
    if seleccion:
        estado.actualizar(unidad_seleccionada=seleccion)

    # Una línea y nada más. Las unidades sin polígono tienen su propia lista debajo, y
    # lo de las UGEL que comparten distrito está contado en Notas sobre los datos, que
    # es donde cabe explicarlo: en el pie del mapa era un párrafo que nadie pidió.
    insuficientes = int((~capa["muestra_suficiente"]).sum())
    if insuficientes:
        st.caption(
            f"En negro, {cp.unidades(insuficientes)} con menos de "
            f"{MUESTRA_MINIMA} evaluados."
        )

with col_panel:
    codigo = f.unidad_seleccionada
    fila = None
    if codigo is not None:
        # En la capa y no en `datos`: el polígono de Mazamari y Pangoa devuelve 120699,
        # un código que el almacén no tiene, así que buscarlo allí no encontraba nada y
        # el panel caía al resultado nacional. Era el único polígono del país cuyo
        # detalle no se podía abrir.
        coincide = capa[capa["cod_unidad"] == codigo]
        fila = coincide.iloc[0] if len(coincide) else None

    if fila is None:
        fila = estado.nacional(f.grado, f.area)
        # Sin subtítulo: el nombre basta, y la línea de abajo ya dice de qué grado y
        # área es la cifra. Para una unidad del mapa, el subtítulo sí aporta, porque
        # dice a qué región o UGEL pertenece.
        titulo, contexto = "Perú", ""
    else:
        titulo = str(fila["nom_unidad"])
        contexto = str(fila.get("nom_padre") or "")

    with st.container(border=True):
        st.markdown(f"**{titulo}**")
        if contexto:
            st.caption(contexto)

        # La cifra toma el color de la dirección del indicador, como la escala del
        # mapa: en el verde de la aplicación, un 30,9 % de estudiantes que no llegan a
        # lo esperado se lee como una buena noticia.
        color_cifra = theme.CONTRASTE if indicador.mas_es_peor else theme.ACENTO
        st.markdown(
            f"<div style='font-size:2.1rem;font-weight:700;letter-spacing:-1px;"
            f"color:{color_cifra};line-height:1.1'>"
            f"{cp.formato(fila[indicador.columna], 1, indicador.sufijo)}</div>"
            f"<div class='nota'>{indicador.nombre}</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        cp.desglose_niveles(fila, f.indicador)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        # Los rótulos dicen lo que son en lugar de nombrarlo: "estimados" no
        # significa nada para quien no trabaja con muestras, y obligaba a una línea de
        # explicación debajo que presuponía justo lo que había que explicar.
        cp.par_de_cifras(
            ("Rindieron la prueba", cp.entero(fila["n_estudiantes"])),
            ("Representan a", cp.entero(fila["poblacion_estimada"])),
        )
        st.caption(f"De {f.descripcion()}.")

    if codigo is not None:
        if st.button("Volver al resultado nacional", width="stretch"):
            estado.limpiar_seleccion()
            st.session_state["mapa_vuelta"] += 1
            st.rerun()
    else:
        st.caption("Haz clic en una unidad del mapa para ver su detalle.")


st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# Ranking de las unidades del nivel elegido, como lectura alternativa del mapa.
with st.expander("Ver todas las unidades en tabla", expanded=False):
    tabla = datos.sort_values(indicador.columna, ascending=indicador.mas_es_peor is False)
    # Las cifras se escriben, no se vuelcan: sin formatear, la tabla mostraba
    # "95.7816" y "1637.3" al lado de un panel que escribe "486 219". La tabla llega
    # ya ordenada por el indicador, que es para lo que se abre.
    columnas = {
        "Unidad": tabla["nom_unidad"],
        indicador.nombre: [
            cp.formato(v, 1, indicador.sufijo) for v in tabla[indicador.columna]
        ],
        "Rindieron la prueba": [cp.entero(v) for v in tabla["n_estudiantes"]],
        "Representan a": [cp.entero(v) for v in tabla["poblacion_estimada"]],
    }
    if "nom_padre" in tabla.columns and tabla["nom_padre"].notna().any():
        columnas = {
            "Unidad": columnas["Unidad"],
            "Pertenece a": tabla["nom_padre"],
            **{k: v for k, v in columnas.items() if k != "Unidad"},
        }
    st.dataframe(
        pd.DataFrame(columnas),
        width="stretch",
        hide_index=True,
        height=320,
    )

if len(sin_geometria):
    with st.expander(
        f"Unidades con datos que no aparecen en el mapa ({len(sin_geometria)})"
    ):
        st.caption(
            "Sus estudiantes sí cuentan en los totales por UGEL, región y país: lo "
            "que falta es el polígono."
        )
        st.dataframe(
            pd.DataFrame({
                "Unidad": sin_geometria["nom_unidad"],
                "Pertenece a": sin_geometria["nom_padre"],
                "Rindieron la prueba": [
                    cp.entero(v) for v in sin_geometria["n_estudiantes"]
                ],
            }),
            width="stretch",
            hide_index=True,
        )

cp.pie_de_pagina()
