"""Acceso al almacén analítico y a las capas geográficas.

Este módulo es el único punto por donde el resto del proyecto lee datos. Centralizarlo
evita que cada pantalla invente su propia consulta y, sobre todo, concentra en un solo
lugar las dos equivalencias que hay que respetar al unir los datos con el mapa.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import duckdb
import geopandas as gpd
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
RUTA_ALMACEN = RAIZ / "processed" / "geoeduca.duckdb"
RUTA_GEO = RAIZ / "geo"

# Niveles geográficos disponibles y el archivo de geometría que les corresponde.
CAPAS = {
    "departamento": ("departamentos.geojson", "ubigeo_dep"),
    "provincia": ("provincias.geojson", "ubigeo_prov"),
    "distrito": ("distritos.geojson", "ubigeo"),
    "dre": ("dre.geojson", "cod_dre"),
    "ugel": ("ugel.geojson", "cod_ugel"),
}

# Qué columna de cada capa lleva el nombre de la unidad. Las tablas de resultados ya
# traen `nom_unidad`, pero una unidad que está en la cartografía y no tiene resultados
# en una vista no aparece en ellas, y su nombre solo se puede sacar de aquí.
NOMBRE_EN_CAPA = {
    "departamento": "departamento",
    "provincia": "provincia",
    "distrito": "distrito",
    "dre": "nom_dre",
    "ugel": "nom_ugel",
}

# La cartografía oficial no separa Mazamari de Pangoa porque el límite entre ambos está
# en litigio: publica un solo polígono con ubigeo 120699. Para pintar el mapa hay que
# sumar los datos de los dos distritos y atribuirlos a esa unidad.
UNIDADES_CARTOGRAFICAS_COMBINADAS: Mapping[str, tuple[str, ...]] = {
    "120699": ("120604", "120606"),
}

#: El mismo mapa al revés, de miembro a destino, que es como se consulta al unir.
UNIDADES_COMBINADAS = {
    miembro: destino
    for destino, miembros in UNIDADES_CARTOGRAFICAS_COMBINADAS.items()
    for miembro in miembros
}

#: Nombre con el que la fuente cartográfica publica cada unidad combinada.
NOMBRES_UNIDADES_COMBINADAS: Mapping[str, str] = {
    "120699": "Mazamari - Pangoa",
}

#: Columnas de `resultados_geograficos` que al combinar unidades se suman.
COLUMNAS_SUMA = (
    "n_estudiantes",
    "n_escuelas",
    "poblacion_estimada",
    "poblacion_critica",
    "poblacion_satisfactoria",
)

#: Columnas que al combinar unidades se promedian ponderando por población
#: estimada. Es la forma exacta de recomponerlas: cada una es un cociente cuyo
#: denominador es la suma de pesos, es decir la población estimada.
COLUMNAS_PONDERADAS = (
    "medida_promedio",
    "pct_previo_inicio",
    "pct_en_inicio",
    "pct_en_proceso",
    "pct_satisfactorio",
    "pct_critico",
    "pct_al_menos_proceso",
)

# Grados cuya muestra no fue diseñada para dar resultados por región. El script oficial
# de la UMC calcula 5.° de secundaria solo a nivel nacional y por sexo, gestión y ámbito.
GRADOS_SIN_DISENO_REGIONAL = {"5S"}

NIVELES_SUBNACIONALES = {"departamento", "provincia", "distrito", "dre", "ugel"}

#: Estudiantes evaluados por debajo de los cuales una unidad no se pinta. Vive aquí
#: porque la recomposición de unidades fusionadas lo necesita para recalcular el
#: indicador sobre la muestra sumada.
MUESTRA_MINIMA = 30


class AlmacenNoEncontrado(FileNotFoundError):
    """El almacén no existe todavía: hay que ejecutar la ingesta."""


def _verificar_almacen() -> None:
    if not RUTA_ALMACEN.exists():
        raise AlmacenNoEncontrado(
            f"No existe {RUTA_ALMACEN}. Ejecuta primero "
            "`.venv/bin/python ingest/build_warehouse.py`."
        )


def conectar() -> duckdb.DuckDBPyConnection:
    """Abre el almacén en solo lectura.

    Solo lectura a propósito: la aplicación consulta, nunca escribe. Reconstruir el
    almacén es tarea de los scripts de ingesta.
    """
    _verificar_almacen()
    return duckdb.connect(str(RUTA_ALMACEN), read_only=True)


def consultar(sql: str, parametros: Iterable | None = None) -> pd.DataFrame:
    """Ejecuta una consulta y devuelve el resultado como DataFrame."""
    with conectar() as con:
        return con.execute(sql, parametros or []).fetch_df()


def microdatos(
    grado: str,
    area: str,
    columnas: Iterable[str] | None = None,
    solo_con_medida: bool = True,
) -> pd.DataFrame:
    """Devuelve el hecho a nivel de estudiante para un grado y un área.

    Es la entrada de los estimadores de muestreo, que necesitan el microdato para poder
    calcular errores estándar: con los agregados ya calculados no se puede.

    Por omisión excluye las filas sin medida, igual que el procedimiento oficial.
    """
    seleccion = ", ".join(columnas) if columnas else "*"
    filtro_medida = " and medida500 is not null" if solo_con_medida else ""
    return consultar(
        f"""
        select {seleccion}
        from hechos_estudiante_area
        where grado = ? and cod_area = ?{filtro_medida}
        """,
        [grado, area],
    )


def resultados_geograficos(
    nivel: str,
    grado: str | None = None,
    area: str | None = None,
    solo_muestra_suficiente: bool = False,
) -> pd.DataFrame:
    """Devuelve las métricas ya agregadas para un nivel geográfico.

    Más rápido que recalcular desde el microdato, pero sin errores estándar. Para
    intervalos de confianza hay que pasar por `microdatos` y el módulo de muestreo.
    """
    condiciones = ["nivel_geografico = ?"]
    parametros: list = [nivel]
    if grado:
        condiciones.append("grado = ?")
        parametros.append(grado)
    if area:
        condiciones.append("cod_area = ?")
        parametros.append(area)
    if solo_muestra_suficiente:
        condiciones.append("muestra_suficiente")

    return consultar(
        f"select * from resultados_geograficos where {' and '.join(condiciones)}",
        parametros,
    )


@lru_cache(maxsize=8)
def _leer_capa(archivo: str) -> gpd.GeoDataFrame:
    ruta = RUTA_GEO / archivo
    if not ruta.exists():
        raise FileNotFoundError(
            f"No existe {ruta}. Ejecuta primero "
            "`.venv/bin/python ingest/build_geo.py`."
        )
    return gpd.read_file(ruta)


def geometrias(nivel: str) -> gpd.GeoDataFrame:
    """Carga la capa de un nivel geográfico, en EPSG:4326.

    El resultado viene de una caché: las capas no cambian durante la ejecución y
    releerlas en cada interacción haría lento el mapa.
    """
    if nivel not in CAPAS:
        raise ValueError(
            f"Nivel {nivel!r} desconocido. Disponibles: {sorted(CAPAS)}."
        )
    archivo, _ = CAPAS[nivel]
    return _leer_capa(archivo).copy()


def metadatos_geo() -> dict:
    """Decisiones tomadas al construir las capas, con sus cifras."""
    return json.loads((RUTA_GEO / "metadatos_geo.json").read_text(encoding="utf-8"))


def combinar_unidades_cartograficas(
    tabla: pd.DataFrame,
    columna_codigo: str = "cod_unidad",
    columna_nombre: str = "nom_unidad",
    por: Sequence[str] = ("grado", "cod_area"),
    equivalencias: Mapping[str, Iterable[str]] = UNIDADES_CARTOGRAFICAS_COMBINADAS,
    nombres: Mapping[str, str] = NOMBRES_UNIDADES_COMBINADAS,
    muestra_minima: int = MUESTRA_MINIMA,
) -> pd.DataFrame:
    """Suma las unidades que la cartografía publica fusionadas.

    El caso del proyecto es Mazamari (120604) y Pangoa (120606): el almacén los
    tiene separados y la cartografía los publica como un solo polígono, 120699,
    porque el límite entre ambos está en litigio. Sin esta recomposición, unir
    datos con geometría a nivel distrital deja fuera a los dos distritos o
    atribuye al polígono el valor de solo uno de ellos.

    La suma no es un promedio de porcentajes: los conteos (`n_estudiantes`,
    `poblacion_estimada`, `poblacion_critica`) se suman y los porcentajes y la
    medida promedio se recomponen ponderando por `poblacion_estimada`, que es la
    suma de los pesos muestrales. Así el resultado coincide con el que daría
    volver al microdato y ponderar de nuevo. `muestra_suficiente`, si existe, se
    recalcula sobre la muestra sumada.

    Las unidades que no aparecen en `equivalencias` pasan intactas.
    """
    if columna_codigo not in tabla.columns:
        raise KeyError(f"La tabla no tiene la columna '{columna_codigo}'.")

    miembros_a_destino: dict[str, str] = {}
    for destino, miembros in equivalencias.items():
        for miembro in miembros:
            miembros_a_destino[str(miembro)] = str(destino)

    codigos = tabla[columna_codigo].astype(str)
    afectadas = codigos.isin(miembros_a_destino)
    if not afectadas.any():
        return tabla.copy()

    por = [c for c in por if c in tabla.columns]
    resto = tabla[~afectadas].copy()
    nuevas: list[dict[str, Any]] = []

    bloque = tabla[afectadas].copy()
    bloque["_destino"] = codigos[afectadas].map(miembros_a_destino)

    llaves = ["_destino"] + por
    for valores, grupo in bloque.groupby(llaves, dropna=False, sort=True):
        valores = valores if isinstance(valores, tuple) else (valores,)
        destino = str(valores[0])
        fila: dict[str, Any] = {}

        peso = pd.to_numeric(
            grupo.get("poblacion_estimada", pd.Series(dtype="float64")),
            errors="coerce",
        )
        total_peso = float(peso.sum()) if len(peso) else 0.0

        for columna in tabla.columns:
            if columna == columna_codigo:
                fila[columna] = destino
            elif columna == columna_nombre:
                fila[columna] = nombres.get(
                    destino, " - ".join(sorted(grupo[columna].astype(str).unique()))
                )
            elif columna in COLUMNAS_SUMA:
                fila[columna] = pd.to_numeric(grupo[columna], errors="coerce").sum()
            elif columna in COLUMNAS_PONDERADAS:
                valor = pd.to_numeric(grupo[columna], errors="coerce")
                fila[columna] = (
                    float((valor * peso).sum() / total_peso)
                    if total_peso > 0
                    else float(valor.mean())
                )
            elif columna == "muestra_suficiente":
                fila[columna] = bool(
                    pd.to_numeric(grupo.get("n_estudiantes"), errors="coerce").sum()
                    >= muestra_minima
                )
            else:
                unicos = grupo[columna].dropna().unique()
                fila[columna] = unicos[0] if len(unicos) else None

        if "n_estudiantes" in fila:
            fila["n_estudiantes"] = int(fila["n_estudiantes"])
        if "n_escuelas" in fila:
            fila["n_escuelas"] = int(fila["n_escuelas"])
        nuevas.append(fila)

    combinadas = pd.DataFrame(nuevas, columns=list(tabla.columns))
    return pd.concat([resto, combinadas], ignore_index=True)


def unir_con_geometria(
    datos: pd.DataFrame,
    nivel: str,
    columna_codigo: str = "cod_unidad",
    muestra_minima: int = MUESTRA_MINIMA,
) -> gpd.GeoDataFrame:
    """Une métricas con su geometría, resolviendo las unidades combinadas.

    A nivel distrital, Mazamari y Pangoa comparten un solo polígono. Sus filas se
    combinan antes de unir con `combinar_unidades_cartograficas`, que suma las cinco
    cantidades, recompone los porcentajes ponderando por población estimada y recalcula
    la suficiencia de muestra sobre la muestra sumada.

    Hubo durante un tiempo una segunda implementación aquí que sumaba solo tres
    columnas y heredaba el resto de una de las dos filas: el polígono recibía
    `n_escuelas` de uno solo de los dos distritos (8 en lugar de 26) y, con el umbral
    del mapa por encima de 170, se pintaba gris pese a tener 436 evaluados.

    Las unidades sin geometría quedan fuera del resultado y se informan por separado con
    `unidades_sin_geometria`, para que la aplicación pueda declararlas en vez de hacerlas
    desaparecer en silencio.
    """
    capa = geometrias(nivel)
    _, clave_geo = CAPAS[nivel]
    marco = datos.copy()

    if nivel == "distrito":
        marco = combinar_unidades_cartograficas(
            marco, columna_codigo=columna_codigo, muestra_minima=muestra_minima
        )

    unido = capa.merge(
        marco, left_on=clave_geo, right_on=columna_codigo, how="inner"
    )
    return gpd.GeoDataFrame(unido, geometry="geometry", crs=capa.crs)


@lru_cache(maxsize=32)
def territorio_prestado(grado: str, area: str) -> pd.DataFrame:
    """UGEL cuya cifra incluye estudiantes que están fuera de su polígono.

    Catorce distritos del país están atendidos por más de una UGEL. La cartografía no
    puede partirlos, así que cada uno se asigna entero a la UGEL con más estudiantes y
    las demás conservan en el almacén su cifra completa, que incluye a esos estudiantes,
    sobre un polígono que ya no los contiene.

    El caso extremo es la UGEL 130017, Trujillo Sur Este: su polígono es Moche y
    Salaverry, y cuatro de cada cinco de sus estudiantes están en el distrito de
    Trujillo, que pertenece a otra UGEL. El mapa no puede arreglarlo, pero sí decirlo.

    Devuelve una fila por UGEL afectada, con cuántos de sus evaluados quedan fuera.
    """
    capa = geometrias("distrito")[["ubigeo", "cod_ugel"]]
    asignada = dict(zip(capa["ubigeo"].astype(str), capa["cod_ugel"].astype(str)))

    detalle = consultar(
        """
        SELECT cod_ugel, nom_ugel, ubigeo, COUNT(*) AS n
        FROM hechos_estudiante_area
        WHERE grado = ? AND cod_area = ?
        GROUP BY 1, 2, 3
        """,
        [grado, area],
    )
    if detalle.empty:
        return pd.DataFrame(columns=["cod_unidad", "nom_unidad", "evaluados", "fuera", "pct_fuera"])

    detalle["asignada"] = detalle["ubigeo"].astype(str).map(asignada)
    # Un distrito sin polígono no presta territorio a nadie: simplemente no se pinta, y
    # eso ya se declara aparte.
    detalle["fuera"] = detalle["asignada"].notna() & (detalle["asignada"] != detalle["cod_ugel"])

    agregado = detalle.groupby(["cod_ugel", "nom_ugel"], as_index=False).apply(
        lambda g: pd.Series({
            "evaluados": int(g["n"].sum()),
            "fuera": int(g.loc[g["fuera"], "n"].sum()),
        }),
        include_groups=False,
    )
    agregado = agregado[agregado["fuera"] > 0].copy()
    agregado["pct_fuera"] = 100.0 * agregado["fuera"] / agregado["evaluados"]
    return agregado.rename(
        columns={"cod_ugel": "cod_unidad", "nom_ugel": "nom_unidad"}
    ).sort_values("pct_fuera", ascending=False).reset_index(drop=True)


def unidades_sin_geometria(datos: pd.DataFrame, nivel: str,
                           columna_codigo: str = "cod_unidad") -> pd.DataFrame:
    """Filas cuyas unidades no tienen polígono en el mapa.

    A nivel distrital son diez distritos creados después de la fecha de validez de la
    cartografía. Pesan entre el 0,13 por ciento de la población estimada en 4.° de
    primaria y el 0,77 por ciento en 5.° de secundaria, y sus estudiantes sí cuentan
    en los agregados por UGEL, DRE y nacionales: lo que falta es únicamente el
    polígono.

    La proporción se calcula por grado y área: sumar el peso sobre todas las filas del
    hecho mezclaría pesos de áreas distintas y contaría varias veces a cada estudiante
    de secundaria.
    """
    capa = geometrias(nivel)
    _, clave_geo = CAPAS[nivel]
    codigos = set(capa[clave_geo])
    if nivel == "distrito":
        codigos |= set(UNIDADES_COMBINADAS)
    return datos[~datos[columna_codigo].isin(codigos)].copy()


#: Escuelas evaluadas en cada grado, para el aviso de representatividad. Están escritas
#: y no consultadas porque el aviso se dibuja en cada pasada de cada página y no merece
#: una consulta; una prueba las ata a `dim_ie` para que no puedan quedarse viejas.
ESCUELAS_POR_GRADO = {"4P": 4816, "2S": 2792, "5S": 305}


def advertencia_representatividad(grado: str, nivel: str) -> str | None:
    """Mensaje a mostrar cuando un corte no tiene respaldo en el diseño muestral.

    La muestra de 5.° de secundaria se diseñó para dar resultados nacionales y por
    estrato, no por región. Sus agregados geográficos se pueden calcular, porque la
    aritmética es la misma, pero no tienen la representatividad que sí tienen los de 4.°
    de primaria y 2.° de secundaria. Mostrarlos sin advertirlo induce a error.

    El mensaje lo lee gente que no trabaja con muestras, así que explica el problema con
    la comparación entre dos cifras en lugar de con las palabras que lo nombran. Decir
    "estrato", "representatividad" e "indicativas" es preciso y no comunica nada a quien
    no sabe ya lo que significan; decir 305 escuelas frente a 4 816 se entiende solo.
    """
    if grado in GRADOS_SIN_DISENO_REGIONAL and nivel in NIVELES_SUBNACIONALES:
        # Separador de miles en formato peruano, que es un espacio y no una coma.
        primaria = f"{ESCUELAS_POR_GRADO['4P']:,}".replace(",", " ")
        return (
            f"En 5.° de secundaria se evaluaron {ESCUELAS_POR_GRADO['5S']} escuelas, "
            f"frente a las {primaria} de 4.° de primaria. Con esa muestra sale una "
            "cifra fiable del país entero, pero no de cada zona: las cifras separadas "
            "por territorio son orientativas."
        )
    return None
