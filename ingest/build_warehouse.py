#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Construye el almacen analitico de GEO_EDUCA a partir de las tres bases ENLA 2025.

Lee los microdatos de 4.o de primaria, 2.o de secundaria y 5.o de secundaria que
publica la Oficina de Medicion de la Calidad de los Aprendizajes (UMC) del Minedu
de Peru, los normaliza y escribe un almacen DuckDB pensado para consultas
analiticas agregadas por geografia y estrato.

El script es idempotente: reconstruye el archivo de salida desde cero en cada
corrida. No escribe nada dentro de DATA/, que es de solo lectura.

Uso:
    .venv/bin/python ingest/build_warehouse.py
    .venv/bin/python ingest/build_warehouse.py --destino otra/ruta.duckdb

Codigo de salida 0 si la validacion contra las cifras oficiales pasa, 1 si falla.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# Rutas y constantes
# ---------------------------------------------------------------------------

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "DATA"
DESTINO_POR_DEFECTO = RAIZ / "processed" / "geoeduca.duckdb"

# Un registro por base de origen. La columna de estrato muestral cambia de
# nombre entre bases: 4P y 2S traen Estrato_DRE, 5S trae Estrato.
GRADOS = {
    "4P": {
        "archivo": "BD_4P ENLA 2025.xlsx",
        "etiqueta": "4.o de primaria",
        "orden": 1,
        "areas": ["L", "M"],
        "col_estrato": "Estrato_DRE",
        "representatividad": (
            "Nacional y por DRE. El estrato muestral es la combinacion de DRE, "
            "ambito y gestion (codigo de 5 digitos: los 4 primeros son el cod_dre)."
        ),
    },
    "2S": {
        "archivo": "BD_2S ENLA 2025.xlsx",
        "etiqueta": "2.o de secundaria",
        "orden": 2,
        "areas": ["L", "M", "CN"],
        "col_estrato": "Estrato_DRE",
        "representatividad": (
            "Nacional y por DRE. El estrato muestral es la combinacion de DRE, "
            "ambito y gestion (codigo de 5 digitos: los 4 primeros son el cod_dre)."
        ),
    },
    "5S": {
        "archivo": "BD_5S ENLA 2025.xlsx",
        "etiqueta": "5.o de secundaria",
        "orden": 3,
        "areas": ["L", "M", "CN", "CI"],
        "col_estrato": "Estrato",
        "representatividad": (
            "Solo nacional. La muestra se estratifico en tres grupos (1 urbana "
            "publica, 2 rural publica, 3 privada) sin diseno por DRE, asi que los "
            "desagregados por DRE, UGEL o distrito NO son estimaciones oficiales."
        ),
    },
}

AREAS = {
    "L": "Lectura",
    "M": "Matematica",
    "CN": "Ciencia y tecnologia",
    "CI": "Ciudadania",
}

NIVELES = {
    0: "Previo al inicio",
    1: "En inicio",
    2: "En proceso",
    3: "Satisfactorio",
}

ETIQUETAS = {
    "gestion": {1: "Publica", 2: "Privada"},
    "ambito": {1: "Urbana", 2: "Rural"},
    "sexo": {0: "Hombre", 1: "Mujer"},
}

# Umbral por debajo del cual una unidad geografica no deberia reportarse sola.
MUESTRA_MINIMA = 30

# Cifras oficiales publicadas por la UMC para la ENLA 2025. La corrida tiene que
# reproducirlas exactamente al primer decimal. Fuente: scripts oficiales de
# calculo de resultados de la UMC (survey::svymean con los pesos por area) y
# resumen ejecutivo ENLA 2025.
CIFRAS_OFICIALES = [
    # (grado, area, metrica, valor esperado)
    ("4P", "L", "pct_previo_inicio", 2.1),
    ("4P", "L", "pct_en_inicio", 24.9),
    ("4P", "L", "pct_en_proceso", 40.4),
    ("4P", "L", "pct_satisfactorio", 32.7),
    ("4P", "L", "medida_promedio", 490.1),
    ("4P", "M", "pct_previo_inicio", 11.3),
    ("4P", "M", "pct_en_inicio", 19.6),
    ("4P", "M", "pct_en_proceso", 39.1),
    ("4P", "M", "pct_satisfactorio", 30.0),
    ("4P", "M", "medida_promedio", 474.3),
    ("5S", "L", "pct_previo_inicio", 27.8),
    ("5S", "L", "pct_en_inicio", 35.8),
    ("5S", "L", "pct_en_proceso", 25.2),
    ("5S", "L", "pct_satisfactorio", 11.3),
    ("5S", "M", "pct_previo_inicio", 35.2),
    ("5S", "M", "pct_en_inicio", 30.4),
    ("5S", "M", "pct_en_proceso", 21.7),
    ("5S", "M", "pct_satisfactorio", 12.8),
    # Satisfactorio de 2S y de las areas restantes de 5S, segun el panorama
    # nacional publicado. Sirven de control adicional del mismo procedimiento.
    ("2S", "L", "pct_satisfactorio", 18.5),
    ("2S", "M", "pct_satisfactorio", 12.7),
    ("2S", "CN", "pct_satisfactorio", 13.5),
    ("5S", "CN", "pct_satisfactorio", 8.3),
]

# Medida promedio de 4.o de primaria en Matematica por categoria, publicada en
# el analisis de brechas. Controla que el desagregado use el peso correcto.
BRECHAS_OFICIALES = [
    # (grado, area, dimension, categoria, medida esperada)
    ("4P", "M", "ambito", "Urbana", 482.9),
    ("4P", "M", "ambito", "Rural", 426.7),
    ("4P", "M", "gestion", "Publica", 468.2),
    ("4P", "M", "gestion", "Privada", 488.9),
    ("4P", "M", "sexo", "Hombre", 483.9),
    ("4P", "M", "sexo", "Mujer", 464.3),
]


# ---------------------------------------------------------------------------
# Utilidades de consola
# ---------------------------------------------------------------------------

def titulo(texto: str) -> None:
    print()
    print("=" * 78)
    print(texto)
    print("=" * 78)


def paso(texto: str) -> None:
    print(f"  {texto}")


def miles(n) -> str:
    """Formato peruano: espacio fino como separador de miles."""
    return f"{int(n):,}".replace(",", " ")


def escalar(con: duckdb.DuckDBPyConnection, consulta: str):
    """Devuelve el primer valor de una consulta agotando el resultado.

    DuckDB 2.0 no permite otras operaciones sobre la conexion mientras queda un
    resultado a medio consumir, asi que se usa fetchall y no fetchone.
    """
    return con.execute(consulta).fetchall()[0][0]


# ---------------------------------------------------------------------------
# Lectura y normalizacion
# ---------------------------------------------------------------------------

def leer_base(grado: str, especificacion: dict) -> pd.DataFrame:
    """Lee la hoja BD de un Excel de origen y normaliza codigos y etiquetas."""
    ruta = DIR_DATOS / especificacion["archivo"]
    if not ruta.exists():
        raise FileNotFoundError(f"No se encuentra el archivo de origen: {ruta}")

    t0 = time.perf_counter()
    df = pd.read_excel(ruta, sheet_name="BD")
    segundos = time.perf_counter() - t0
    paso(
        f"{grado}: {miles(len(df))} filas y {len(df.columns)} columnas leidas de "
        f"'{especificacion['archivo']}' en {segundos:.1f} s"
    )

    col_estrato = especificacion["col_estrato"]
    faltantes = [c for c in ("codgeo", "cod_DRE", "cod_UGEL", col_estrato) if c not in df.columns]
    if faltantes:
        raise ValueError(f"{grado}: faltan columnas esperadas {faltantes}")

    # Los codigos vienen como enteros en el Excel y pierden el cero inicial.
    # Se restituyen con zfill a su longitud oficial. La llave geografica es
    # siempre el ubigeo de seis digitos, nunca el nombre del distrito.
    cortos_geo = int((df["codgeo"].astype(str).str.len() == 5).sum())
    df["ubigeo"] = df["codgeo"].astype(str).str.zfill(6)
    df["cod_departamento"] = df["ubigeo"].str[:2]
    df["cod_provincia"] = df["ubigeo"].str[:4]
    df["cod_dre"] = df["cod_DRE"].astype(str).str.zfill(4)
    df["cod_ugel"] = df["cod_UGEL"].astype(str).str.zfill(6)
    df["cod_estrato"] = df[col_estrato].astype(str).str.zfill(5 if col_estrato == "Estrato_DRE" else 1)
    paso(
        f"{grado}: ubigeo normalizado a seis digitos ({miles(cortos_geo)} filas "
        f"venian con cinco); cod_dre a cuatro y cod_ugel a seis"
    )

    # Identificadores. ID_IE es un correlativo interno de cada base, no el
    # codigo modular, asi que se le antepone el grado para que sea unico en el
    # almacen y quede claro que no cruza entre bases.
    df["id_ie_base"] = df["ID_IE"].astype(str).str.zfill(6)
    df["id_ie"] = grado + "-" + df["id_ie_base"]
    df["id_seccion"] = df["ID_seccion"].astype(str).str.zfill(2)
    df["cor_est"] = df["cor_est"].astype(str).str.zfill(3)
    df["id_estudiante"] = df["id_ie"] + "-" + df["id_seccion"] + "-" + df["cor_est"]

    # Etiquetas legibles junto a los codigos.
    df = df.rename(columns={"area": "cod_ambito", "gestion2": "cod_gestion", "sexo": "cod_sexo"})
    df["gestion"] = df["cod_gestion"].map(ETIQUETAS["gestion"]).astype("str")
    df["ambito"] = df["cod_ambito"].map(ETIQUETAS["ambito"]).astype("str")
    df["sexo"] = df["cod_sexo"].map(ETIQUETAS["sexo"]).astype("str")

    df["grado"] = grado
    df["grado_etq"] = especificacion["etiqueta"]
    return df


def resolver_nombres_geograficos(bases: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, list[dict]]:
    """Unifica los nombres de distrito, provincia y departamento por ubigeo.

    Hay ubigeos que aparecen con dos nombres de distrito distintos. Se resuelve
    por mayoria de filas y se devuelve el detalle de los conflictos para el
    reporte de calidad.
    """
    cols = ["ubigeo", "cod_provincia", "cod_departamento", "Distrito", "Provincia", "Departamento"]
    union = pd.concat([df[cols] for df in bases.values()], ignore_index=True)

    conteo = union.groupby(["ubigeo", "Distrito"], as_index=False).size()
    conteo = conteo.sort_values(["ubigeo", "size"], ascending=[True, False])
    conflictos = []
    for ubigeo, grupo in conteo.groupby("ubigeo"):
        if len(grupo) > 1:
            conflictos.append(
                {
                    "ubigeo": ubigeo,
                    "nombre_elegido": grupo.iloc[0]["Distrito"],
                    "filas_elegido": int(grupo.iloc[0]["size"]),
                    "nombres_descartados": "; ".join(
                        f"{r.Distrito} ({r.size} filas)" for r in grupo.iloc[1:].itertuples()
                    ),
                }
            )
    elegido = conteo.drop_duplicates("ubigeo")[["ubigeo", "Distrito"]]

    dim = (
        union.drop(columns=["Distrito"])
        .drop_duplicates("ubigeo")
        .merge(elegido, on="ubigeo", how="left")
        .rename(
            columns={
                "Distrito": "distrito",
                "Provincia": "provincia",
                "Departamento": "departamento",
            }
        )
        .sort_values("ubigeo")
        .reset_index(drop=True)
    )
    return dim[["ubigeo", "distrito", "cod_provincia", "provincia", "cod_departamento", "departamento"]], conflictos


def construir_hechos(bases: dict[str, pd.DataFrame], dim_distrito: pd.DataFrame) -> pd.DataFrame:
    """Pasa las bases anchas a un hecho largo: una fila por estudiante y area.

    Este es el nucleo del diseno. En el Excel original cada area evaluada ocupa
    tres columnas (medida500_X, grupo_X, peso_X) y es facil combinar la medida de
    un area con el peso de otra, que es el error mas grave posible en estos
    datos. Al pasar a formato largo queda una sola columna 'peso' y una sola
    columna 'medida500', y el area pasa a ser un filtro: la equivocacion deja de
    ser representable.

    Solo entran las filas con medida no nula para el area, igual que hace el
    script oficial de la UMC (filter(!is.na(medida500_X))).
    """
    comunes = [
        "grado", "grado_etq", "id_estudiante", "id_ie", "id_ie_base", "id_seccion", "cor_est",
        "cod_dre", "nom_DRE", "cod_ugel", "nom_UGEL", "ubigeo",
        "cod_estrato", "cod_gestion", "gestion", "cod_ambito", "ambito", "cod_sexo", "sexo",
    ]
    trozos = []
    for grado, df in bases.items():
        for area in GRADOS[grado]["areas"]:
            mask = df[f"medida500_{area}"].notna()
            trozo = df.loc[mask, comunes].copy()
            trozo["cod_area"] = area
            trozo["area_evaluada"] = AREAS[area]
            trozo["medida500"] = df.loc[mask, f"medida500_{area}"].astype("float64")
            trozo["cod_nivel"] = df.loc[mask, f"grupo_{area}"].astype("int8")
            trozo["peso"] = df.loc[mask, f"peso_{area}"].astype("float64")
            trozos.append(trozo)
            paso(
                f"{grado} / {AREAS[area]:<22}: {miles(mask.sum())} evaluados "
                f"({miles((~mask).sum())} sin medida), poblacion estimada "
                f"{miles(round(df.loc[mask, f'peso_{area}'].sum()))}"
            )

    hechos = pd.concat(trozos, ignore_index=True)
    hechos = hechos.rename(columns={"nom_DRE": "nom_dre", "nom_UGEL": "nom_ugel"})

    hechos["nivel_logro"] = hechos["cod_nivel"].map(NIVELES).astype("str")
    hechos["es_critico"] = hechos["cod_nivel"].isin([0, 1])
    hechos["es_satisfactorio"] = hechos["cod_nivel"] == 3

    hechos = hechos.merge(dim_distrito, on="ubigeo", how="left", validate="many_to_one")

    orden = [
        "grado", "grado_etq", "cod_area", "area_evaluada",
        "id_estudiante", "id_ie", "id_ie_base", "id_seccion", "cor_est",
        "cod_dre", "nom_dre", "cod_ugel", "nom_ugel",
        "ubigeo", "distrito", "cod_provincia", "provincia", "cod_departamento", "departamento",
        "cod_estrato", "cod_gestion", "gestion", "cod_ambito", "ambito", "cod_sexo", "sexo",
        "medida500", "cod_nivel", "nivel_logro", "es_critico", "es_satisfactorio", "peso",
    ]
    return hechos[orden]


# ---------------------------------------------------------------------------
# SQL de agregacion
# ---------------------------------------------------------------------------

# Bloque de metricas que comparten todos los agregados. Es la definicion unica
# de "como se calcula bien" en este almacen:
#   - promedio ponderado  = SUM(peso * medida500) / SUM(peso)
#   - proporcion ponderada = SUM(peso filtrado) / SUM(peso) * 100
#   - poblacion estimada  = SUM(peso)
#   - tamano de muestra   = COUNT(*), sin ponderar
METRICAS_SQL = """
    COUNT(*)::BIGINT                                        AS n_estudiantes,
    COUNT(DISTINCT id_ie)::BIGINT                           AS n_escuelas,
    ROUND(SUM(peso), 1)                                     AS poblacion_estimada,
    ROUND(SUM(peso * medida500) / SUM(peso), 4)             AS medida_promedio,
    ROUND(100.0 * SUM(CASE WHEN cod_nivel = 0 THEN peso ELSE 0 END) / SUM(peso), 4) AS pct_previo_inicio,
    ROUND(100.0 * SUM(CASE WHEN cod_nivel = 1 THEN peso ELSE 0 END) / SUM(peso), 4) AS pct_en_inicio,
    ROUND(100.0 * SUM(CASE WHEN cod_nivel = 2 THEN peso ELSE 0 END) / SUM(peso), 4) AS pct_en_proceso,
    ROUND(100.0 * SUM(CASE WHEN cod_nivel = 3 THEN peso ELSE 0 END) / SUM(peso), 4) AS pct_satisfactorio,
    ROUND(100.0 * SUM(CASE WHEN es_critico THEN peso ELSE 0 END) / SUM(peso), 4)    AS pct_critico,
    ROUND(100.0 * SUM(CASE WHEN cod_nivel >= 2 THEN peso ELSE 0 END) / SUM(peso), 4) AS pct_al_menos_proceso,
    ROUND(SUM(CASE WHEN es_critico THEN peso ELSE 0 END), 1)                        AS poblacion_critica,
    ROUND(SUM(CASE WHEN cod_nivel = 3 THEN peso ELSE 0 END), 1)                     AS poblacion_satisfactoria,
    (COUNT(*) >= {minima})                                  AS muestra_suficiente
"""

# Cada nivel geografico declara su codigo, su nombre, su unidad padre y el
# departamento al que pertenece cuando la jerarquia lo permite. DRE y UGEL no
# declaran departamento porque hay UGEL que administran distritos de otro
# departamento (la UGEL 240002 Contralmirante Villar, de la DRE Tumbes,
# atiende Mancora, que es de Piura).
NIVELES_GEOGRAFICOS = [
    ("nacional", "'PE'", "'Peru'", "NULL", "NULL", "NULL", "NULL", []),
    ("departamento", "cod_departamento", "departamento", "NULL", "NULL",
     "cod_departamento", "departamento", ["cod_departamento", "departamento"]),
    ("provincia", "cod_provincia", "provincia", "cod_departamento", "departamento",
     "cod_departamento", "departamento",
     ["cod_provincia", "provincia", "cod_departamento", "departamento"]),
    ("distrito", "ubigeo", "distrito", "cod_provincia", "provincia",
     "cod_departamento", "departamento",
     ["ubigeo", "distrito", "cod_provincia", "provincia", "cod_departamento", "departamento"]),
    ("dre", "cod_dre", "nom_dre", "NULL", "NULL", "NULL", "NULL", ["cod_dre", "nom_dre"]),
    ("ugel", "cod_ugel", "nom_ugel", "cod_dre", "nom_dre", "NULL", "NULL",
     ["cod_ugel", "nom_ugel", "cod_dre", "nom_dre"]),
]


def sql_resultados_geograficos() -> str:
    piezas = []
    for nivel, cod, nom, cod_padre, nom_padre, cod_dep, dep, agrupar in NIVELES_GEOGRAFICOS:
        group_by = ", ".join(["grado", "grado_etq", "cod_area", "area_evaluada"] + agrupar)
        piezas.append(
            f"""
SELECT
    grado, grado_etq, cod_area, area_evaluada,
    '{nivel}'           AS nivel_geografico,
    {cod}               AS cod_unidad,
    {nom}               AS nom_unidad,
    {cod_padre}         AS cod_padre,
    {nom_padre}         AS nom_padre,
    {cod_dep}           AS cod_departamento,
    {dep}               AS departamento,
{METRICAS_SQL.format(minima=MUESTRA_MINIMA)}
FROM hechos_estudiante_area
GROUP BY {group_by}
"""
        )
    return "\nUNION ALL\n".join(piezas)


def sql_resultados_desagregado() -> str:
    piezas = [
        f"""
SELECT
    grado, grado_etq, cod_area, area_evaluada,
    'nacional' AS dimension, NULL AS cod_categoria, 'Nacional' AS categoria, 0 AS orden_categoria,
{METRICAS_SQL.format(minima=MUESTRA_MINIMA)}
FROM hechos_estudiante_area
GROUP BY grado, grado_etq, cod_area, area_evaluada
"""
    ]
    for dimension, columna_cod, columna_etq in [
        ("sexo", "cod_sexo", "sexo"),
        ("gestion", "cod_gestion", "gestion"),
        ("ambito", "cod_ambito", "ambito"),
    ]:
        piezas.append(
            f"""
SELECT
    grado, grado_etq, cod_area, area_evaluada,
    '{dimension}' AS dimension, {columna_cod}::INTEGER AS cod_categoria,
    {columna_etq} AS categoria, {columna_cod}::INTEGER + 1 AS orden_categoria,
{METRICAS_SQL.format(minima=MUESTRA_MINIMA)}
FROM hechos_estudiante_area
GROUP BY grado, grado_etq, cod_area, area_evaluada, {columna_cod}, {columna_etq}
"""
        )
    return "\nUNION ALL\n".join(piezas)


# Pares de categorias que definen cada brecha. El orden importa: la brecha se
# calcula siempre como categoria_a menos categoria_b.
PARES_BRECHA = [
    ("ambito", "Urbana", "Rural"),
    ("gestion", "Privada", "Publica"),
    ("sexo", "Hombre", "Mujer"),
]


def sql_brechas() -> str:
    piezas = []
    for dimension, cat_a, cat_b in PARES_BRECHA:
        piezas.append(
            f"""
SELECT
    a.grado, a.grado_etq, a.cod_area, a.area_evaluada,
    '{dimension}'       AS dimension,
    '{cat_a}'           AS categoria_a,
    '{cat_b}'           AS categoria_b,
    a.medida_promedio   AS medida_a,
    b.medida_promedio   AS medida_b,
    ROUND(a.medida_promedio - b.medida_promedio, 4)     AS brecha_medida,
    a.pct_satisfactorio AS pct_satisfactorio_a,
    b.pct_satisfactorio AS pct_satisfactorio_b,
    ROUND(a.pct_satisfactorio - b.pct_satisfactorio, 4) AS brecha_pct_satisfactorio,
    a.pct_critico       AS pct_critico_a,
    b.pct_critico       AS pct_critico_b,
    ROUND(a.pct_critico - b.pct_critico, 4)             AS brecha_pct_critico,
    a.n_estudiantes     AS n_estudiantes_a,
    b.n_estudiantes     AS n_estudiantes_b
FROM resultados_desagregado a
JOIN resultados_desagregado b
  ON a.grado = b.grado AND a.cod_area = b.cod_area AND a.dimension = b.dimension
WHERE a.dimension = '{dimension}' AND a.categoria = '{cat_a}' AND b.categoria = '{cat_b}'
"""
        )
    return "\nUNION ALL\n".join(piezas)


# ---------------------------------------------------------------------------
# Diccionario de columnas (se guarda como tabla para alimentar al agente SQL)
# ---------------------------------------------------------------------------

DICCIONARIO = [
    # (tabla, columna, descripcion)
    ("hechos_estudiante_area", "grado", "Base de origen: 4P, 2S o 5S."),
    ("hechos_estudiante_area", "grado_etq", "Nombre del grado."),
    ("hechos_estudiante_area", "cod_area", "Area evaluada: L, M, CN o CI."),
    ("hechos_estudiante_area", "area_evaluada", "Nombre del area evaluada."),
    ("hechos_estudiante_area", "id_estudiante", "Llave unica de la fila: grado, IE, seccion y correlativo."),
    ("hechos_estudiante_area", "id_ie", "Llave de la escuela dentro del almacen (grado mas correlativo interno). NO es el codigo modular y no cruza entre grados."),
    ("hechos_estudiante_area", "id_ie_base", "Correlativo interno de la IE tal como viene en su base de origen."),
    ("hechos_estudiante_area", "id_seccion", "Identificador de la seccion dentro de la IE."),
    ("hechos_estudiante_area", "cor_est", "Correlativo del estudiante dentro de la seccion."),
    ("hechos_estudiante_area", "cod_dre", "Codigo de la Direccion Regional de Educacion, cuatro digitos con cero inicial."),
    ("hechos_estudiante_area", "nom_dre", "Nombre de la DRE."),
    ("hechos_estudiante_area", "cod_ugel", "Codigo de la UGEL, seis digitos con cero inicial."),
    ("hechos_estudiante_area", "nom_ugel", "Nombre de la UGEL."),
    ("hechos_estudiante_area", "ubigeo", "Codigo geografico del distrito (codgeo del origen) normalizado a seis digitos. Es la unica llave valida de distrito."),
    ("hechos_estudiante_area", "distrito", "Nombre del distrito. Se repite entre distritos distintos, no sirve de llave."),
    ("hechos_estudiante_area", "cod_provincia", "Primeros cuatro digitos del ubigeo."),
    ("hechos_estudiante_area", "provincia", "Nombre de la provincia."),
    ("hechos_estudiante_area", "cod_departamento", "Primeros dos digitos del ubigeo."),
    ("hechos_estudiante_area", "departamento", "Nombre del departamento."),
    ("hechos_estudiante_area", "cod_estrato", "Estrato muestral del diseno de la UMC. En 4P y 2S son cinco digitos (cod_dre mas numero de estrato); en 5S es un digito (1 urbana publica, 2 rural publica, 3 privada)."),
    ("hechos_estudiante_area", "cod_gestion", "1 publica, 2 privada."),
    ("hechos_estudiante_area", "gestion", "Etiqueta de gestion: Publica o Privada."),
    ("hechos_estudiante_area", "cod_ambito", "1 urbana, 2 rural. En el Excel original esta columna se llama 'area'; aqui se renombro a ambito para no confundirla con el area evaluada."),
    ("hechos_estudiante_area", "ambito", "Etiqueta del ambito: Urbana o Rural."),
    ("hechos_estudiante_area", "cod_sexo", "0 hombre, 1 mujer."),
    ("hechos_estudiante_area", "sexo", "Etiqueta de sexo: Hombre o Mujer."),
    ("hechos_estudiante_area", "medida500", "Medida de logro del estudiante en la escala de la UMC para ese grado y area. NO es comparable entre grados."),
    ("hechos_estudiante_area", "cod_nivel", "Nivel de logro: 0 previo al inicio, 1 en inicio, 2 en proceso, 3 satisfactorio."),
    ("hechos_estudiante_area", "nivel_logro", "Etiqueta del nivel de logro."),
    ("hechos_estudiante_area", "es_critico", "Verdadero si el nivel es 0 o 1 (niveles criticos)."),
    ("hechos_estudiante_area", "es_satisfactorio", "Verdadero si el nivel es 3."),
    ("hechos_estudiante_area", "peso", "Peso muestral del estudiante PARA ESA AREA. Es obligatorio en todo promedio o proporcion. Los pesos de areas distintas no son intercambiables."),
    ("resultados_geograficos", "nivel_geografico", "nacional, departamento, provincia, distrito, dre o ugel. Siempre hay que filtrarlo."),
    ("resultados_geograficos", "cod_unidad", "Codigo de la unidad geografica segun su nivel."),
    ("resultados_geograficos", "nom_unidad", "Nombre de la unidad geografica."),
    ("resultados_geograficos", "cod_padre", "Codigo de la unidad superior: provincia para distrito, departamento para provincia, DRE para UGEL."),
    ("resultados_geograficos", "nom_padre", "Nombre de la unidad superior."),
    ("resultados_geograficos", "n_estudiantes", "Estudiantes evaluados en la muestra, sin ponderar. Es el tamano de muestra, no una poblacion."),
    ("resultados_geograficos", "n_escuelas", "Escuelas distintas en la muestra."),
    ("resultados_geograficos", "poblacion_estimada", "Suma de pesos: estimacion de cuantos estudiantes representa la muestra."),
    ("resultados_geograficos", "medida_promedio", "Medida promedio ponderada en la escala del grado."),
    ("resultados_geograficos", "pct_previo_inicio", "Porcentaje ponderado en Previo al inicio."),
    ("resultados_geograficos", "pct_en_inicio", "Porcentaje ponderado en En inicio."),
    ("resultados_geograficos", "pct_en_proceso", "Porcentaje ponderado en En proceso."),
    ("resultados_geograficos", "pct_satisfactorio", "Porcentaje ponderado en Satisfactorio."),
    ("resultados_geograficos", "pct_critico", "Porcentaje ponderado en niveles criticos (Previo al inicio mas En inicio)."),
    ("resultados_geograficos", "pct_al_menos_proceso", "Porcentaje ponderado en En proceso o Satisfactorio."),
    ("resultados_geograficos", "poblacion_critica", "Suma de pesos de los estudiantes en niveles criticos: estimacion de cuantos estudiantes estan en esa situacion."),
    ("resultados_geograficos", "poblacion_satisfactoria", "Suma de pesos de los estudiantes en Satisfactorio."),
    ("resultados_geograficos", "muestra_suficiente", f"Falso si n_estudiantes es menor que {MUESTRA_MINIMA}. Esas unidades no deberian reportarse solas."),
    ("resultados_desagregado", "dimension", "nacional, sexo, gestion o ambito."),
    ("resultados_desagregado", "cod_categoria", "Codigo de la categoria dentro de la dimension."),
    ("resultados_desagregado", "categoria", "Etiqueta de la categoria: Nacional, Hombre, Mujer, Publica, Privada, Urbana o Rural."),
    ("resultados_desagregado", "orden_categoria", "Orden de presentacion de la categoria."),
    ("brechas", "dimension", "ambito, gestion o sexo."),
    ("brechas", "categoria_a", "Categoria del lado izquierdo de la resta."),
    ("brechas", "categoria_b", "Categoria del lado derecho de la resta."),
    ("brechas", "brecha_medida", "medida_a menos medida_b, en puntos de la escala del grado."),
    ("brechas", "brecha_pct_satisfactorio", "pct_satisfactorio_a menos pct_satisfactorio_b, en puntos porcentuales."),
    ("brechas", "brecha_pct_critico", "pct_critico_a menos pct_critico_b, en puntos porcentuales."),
    ("dim_grado", "representatividad", "Hasta que nivel geografico el diseno muestral del grado produce estimaciones oficiales."),
    ("dim_grado", "escala_comparable", "Siempre falso: cada grado tiene su propia calibracion y las medidas no se comparan entre grados."),
    ("meta_rango_medida", "medida_min", "Medida mas baja observada en ese grado, area y nivel de logro."),
    ("meta_rango_medida", "medida_max", "Medida mas alta observada en ese grado, area y nivel de logro. Junto con el minimo del nivel siguiente delimita el punto de corte observado, que no es el punto de corte oficial publicado."),
]


# ---------------------------------------------------------------------------
# Construccion del almacen
# ---------------------------------------------------------------------------

def construir(destino: Path) -> int:
    inicio = time.perf_counter()

    titulo("GEO_EDUCA: construccion del almacen analitico ENLA 2025")
    print(f"  Origen  : {DIR_DATOS}")
    print(f"  Destino : {destino}")

    titulo("1. Lectura y normalizacion de las bases de origen")
    bases = {g: leer_base(g, esp) for g, esp in GRADOS.items()}

    titulo("2. Resolucion de la geografia")
    dim_distrito, conflictos = resolver_nombres_geograficos(bases)
    paso(f"{miles(len(dim_distrito))} distritos distintos por ubigeo en las tres bases")
    nombres_repetidos = int((dim_distrito.groupby("distrito")["ubigeo"].transform("size") > 1).sum())
    paso(
        f"{miles(dim_distrito['distrito'].nunique())} nombres de distrito distintos para "
        f"{miles(len(dim_distrito))} ubigeos ({miles(nombres_repetidos)} ubigeos con nombre repetido)"
    )
    if conflictos:
        paso(f"{len(conflictos)} ubigeos traian mas de un nombre de distrito, resueltos por mayoria:")
        for c in conflictos:
            print(
                f"      {c['ubigeo']}: se conserva '{c['nombre_elegido']}' "
                f"({miles(c['filas_elegido'])} filas), se descarta {c['nombres_descartados']}"
            )

    titulo("3. Hecho largo: una fila por estudiante y area evaluada")
    hechos = construir_hechos(bases, dim_distrito)
    paso(f"Total: {miles(len(hechos))} filas de hecho")

    titulo("4. Escritura del almacen DuckDB")
    destino.parent.mkdir(parents=True, exist_ok=True)
    for sufijo in ("", ".wal"):
        previo = Path(str(destino) + sufijo)
        if previo.exists():
            previo.unlink()
            paso(f"Se elimino el archivo previo {previo.name} (la construccion es desde cero)")

    con = duckdb.connect(str(destino))
    con.register("tmp_hechos", hechos)
    con.register("tmp_dim_distrito", dim_distrito)

    con.execute("CREATE TABLE hechos_estudiante_area AS SELECT * FROM tmp_hechos")
    paso(f"hechos_estudiante_area: {miles(len(hechos))} filas")

    # --- Dimensiones -------------------------------------------------------
    filas_grado = pd.DataFrame(
        [
            {
                "grado": g,
                "grado_etq": esp["etiqueta"],
                "orden": esp["orden"],
                "archivo_origen": esp["archivo"],
                "areas_evaluadas": ", ".join(AREAS[a] for a in esp["areas"]),
                "col_estrato_origen": esp["col_estrato"],
                "representatividad": esp["representatividad"],
                "escala_comparable": False,
            }
            for g, esp in GRADOS.items()
        ]
    )
    con.register("tmp_dim_grado", filas_grado)
    con.execute("CREATE TABLE dim_grado AS SELECT * FROM tmp_dim_grado ORDER BY orden")

    filas_area = pd.DataFrame(
        [
            {
                "cod_area": a,
                "area_evaluada": nombre,
                "grados": ", ".join(g for g, esp in GRADOS.items() if a in esp["areas"]),
            }
            for a, nombre in AREAS.items()
        ]
    )
    con.register("tmp_dim_area", filas_area)
    con.execute("CREATE TABLE dim_area_evaluada AS SELECT * FROM tmp_dim_area")

    filas_nivel = pd.DataFrame(
        [
            {
                "cod_nivel": k,
                "nivel_logro": v,
                "orden": k,
                "es_critico": k in (0, 1),
                "descripcion": d,
            }
            for (k, v), d in zip(
                NIVELES.items(),
                [
                    "No logro los aprendizajes necesarios para estar en el nivel En inicio.",
                    "Logro aprendizajes muy elementales respecto de lo esperado para el grado.",
                    "Logro parcialmente los aprendizajes esperados para el grado.",
                    "Logro los aprendizajes esperados para el grado y esta listo para seguir aprendiendo.",
                ],
            )
        ]
    )
    con.register("tmp_dim_nivel", filas_nivel)
    con.execute("CREATE TABLE dim_nivel_logro AS SELECT * FROM tmp_dim_nivel ORDER BY orden")

    con.execute("CREATE TABLE dim_distrito AS SELECT * FROM tmp_dim_distrito ORDER BY ubigeo")
    con.execute(
        """
        CREATE TABLE dim_provincia AS
        SELECT DISTINCT cod_provincia, provincia, cod_departamento, departamento
        FROM dim_distrito ORDER BY cod_provincia
        """
    )
    con.execute(
        """
        CREATE TABLE dim_departamento AS
        SELECT DISTINCT cod_departamento, departamento
        FROM dim_distrito ORDER BY cod_departamento
        """
    )
    con.execute(
        """
        CREATE TABLE dim_dre AS
        SELECT cod_dre, any_value(nom_dre) AS nom_dre,
               COUNT(DISTINCT cod_ugel)::BIGINT AS n_ugel,
               COUNT(DISTINCT ubigeo)::BIGINT   AS n_distritos
        FROM hechos_estudiante_area GROUP BY cod_dre ORDER BY cod_dre
        """
    )
    con.execute(
        """
        CREATE TABLE dim_ugel AS
        SELECT cod_ugel, any_value(nom_ugel) AS nom_ugel,
               any_value(cod_dre) AS cod_dre, any_value(nom_dre) AS nom_dre,
               COUNT(DISTINCT ubigeo)::BIGINT AS n_distritos
        FROM hechos_estudiante_area GROUP BY cod_ugel ORDER BY cod_ugel
        """
    )
    con.execute(
        """
        CREATE TABLE dim_ie AS
        SELECT id_ie, any_value(grado) AS grado, any_value(id_ie_base) AS id_ie_base,
               any_value(cod_ugel) AS cod_ugel, any_value(nom_ugel) AS nom_ugel,
               any_value(cod_dre) AS cod_dre, any_value(nom_dre) AS nom_dre,
               any_value(ubigeo) AS ubigeo, any_value(distrito) AS distrito,
               any_value(cod_gestion) AS cod_gestion, any_value(gestion) AS gestion,
               any_value(cod_ambito) AS cod_ambito, any_value(ambito) AS ambito,
               any_value(cod_estrato) AS cod_estrato,
               COUNT(DISTINCT id_estudiante)::BIGINT AS n_estudiantes
        FROM hechos_estudiante_area GROUP BY id_ie ORDER BY id_ie
        """
    )
    for t in ["dim_grado", "dim_area_evaluada", "dim_nivel_logro", "dim_distrito",
              "dim_provincia", "dim_departamento", "dim_dre", "dim_ugel", "dim_ie"]:
        n = escalar(con, f"SELECT COUNT(*) FROM {t}")
        paso(f"{t}: {miles(n)} filas")

    # --- Agregados ---------------------------------------------------------
    con.execute(f"CREATE TABLE resultados_geograficos AS {sql_resultados_geograficos()}")
    con.execute(f"CREATE TABLE resultados_desagregado AS {sql_resultados_desagregado()}")
    con.execute(f"CREATE TABLE brechas AS {sql_brechas()}")
    con.execute(
        """
        CREATE TABLE meta_rango_medida AS
        SELECT grado, cod_area, area_evaluada, cod_nivel, nivel_logro,
               ROUND(MIN(medida500), 3) AS medida_min,
               ROUND(MAX(medida500), 3) AS medida_max,
               COUNT(*)::BIGINT AS n_estudiantes
        FROM hechos_estudiante_area
        GROUP BY grado, cod_area, area_evaluada, cod_nivel, nivel_logro
        ORDER BY grado, cod_area, cod_nivel
        """
    )
    for t in ["resultados_geograficos", "resultados_desagregado", "brechas", "meta_rango_medida"]:
        n = escalar(con, f"SELECT COUNT(*) FROM {t}")
        paso(f"{t}: {miles(n)} filas")

    # --- Metadatos ---------------------------------------------------------
    con.register("tmp_diccionario", pd.DataFrame(DICCIONARIO, columns=["tabla", "columna", "descripcion"]))
    con.execute("CREATE TABLE meta_diccionario AS SELECT * FROM tmp_diccionario")

    filas_meta = [
        ("construido_en", datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")),
        ("fuente", "Minedu - UMC. Evaluacion Nacional de Logros de Aprendizaje (ENLA) 2025, evaluacion muestral."),
        ("grano_hecho", "Una fila por estudiante y area evaluada, solo donde hay medida."),
        ("regla_ponderacion", "Todo promedio usa SUM(peso*medida500)/SUM(peso) y toda proporcion usa SUM(peso filtrado)/SUM(peso). Sin ponderar, las cifras no coinciden con las oficiales."),
        ("regla_escala", "Las medidas medida500 NO son comparables entre grados: cada grado tiene su propia calibracion."),
        ("regla_llave_geografica", "El distrito se identifica por ubigeo de seis digitos, nunca por nombre."),
        ("regla_escuela", "id_ie es un correlativo interno por base. Las tres bases no se cruzan a nivel de escuela, solo agregando por geografia."),
        ("muestra_minima", str(MUESTRA_MINIMA)),
    ]
    for g, esp in GRADOS.items():
        filas_meta.append((f"archivo_{g}", esp["archivo"]))
    con.register("tmp_meta", pd.DataFrame(filas_meta, columns=["clave", "valor"]))
    con.execute("CREATE TABLE meta_almacen AS SELECT * FROM tmp_meta")

    # --- Validacion --------------------------------------------------------
    titulo("5. Validacion contra las cifras oficiales de la UMC")
    ok = validar(con)

    con.execute("CHECKPOINT")
    con.close()

    tam = destino.stat().st_size
    titulo("Resumen")
    print(f"  Archivo        : {destino}")
    print(f"  Tamano         : {tam / 1024 / 1024:.1f} MB ({miles(tam)} bytes)")
    print(f"  Filas de hecho : {miles(len(hechos))}")
    print(f"  Tiempo total   : {time.perf_counter() - inicio:.1f} s")
    print(f"  Validacion     : {'CORRECTA' if ok else 'FALLIDA'}")
    return 0 if ok else 1


def validar(con: duckdb.DuckDBPyConnection) -> bool:
    """Compara los agregados del almacen contra las cifras publicadas.

    Consulta el almacen por SQL, no los DataFrames intermedios, para que la
    validacion pruebe lo que la aplicacion y el agente van a consultar.
    """
    filas = []

    nacional = con.execute(
        """
        SELECT grado, cod_area, medida_promedio, pct_previo_inicio, pct_en_inicio,
               pct_en_proceso, pct_satisfactorio
        FROM resultados_geograficos WHERE nivel_geografico = 'nacional'
        """
    ).df()
    nacional = nacional.set_index(["grado", "cod_area"])

    for grado, area, metrica, esperado in CIFRAS_OFICIALES:
        obtenido = float(nacional.loc[(grado, area), metrica])
        filas.append(
            {
                "control": "nacional",
                "grado": grado,
                "cod_area": area,
                "detalle": metrica,
                "esperado": esperado,
                "obtenido": round(obtenido, 4),
                "diferencia": round(obtenido - esperado, 4),
                "pasa": round(obtenido, 1) == esperado,
            }
        )

    desag = con.execute(
        "SELECT grado, cod_area, dimension, categoria, medida_promedio FROM resultados_desagregado"
    ).df()
    desag = desag.set_index(["grado", "cod_area", "dimension", "categoria"])

    for grado, area, dimension, categoria, esperado in BRECHAS_OFICIALES:
        obtenido = float(desag.loc[(grado, area, dimension, categoria), "medida_promedio"])
        filas.append(
            {
                "control": "desagregado",
                "grado": grado,
                "cod_area": area,
                "detalle": f"{dimension}: {categoria}, medida promedio",
                "esperado": esperado,
                "obtenido": round(obtenido, 4),
                "diferencia": round(obtenido - esperado, 4),
                "pasa": round(obtenido, 1) == esperado,
            }
        )

    # Controles internos de coherencia del almacen.
    coherencia = [
        (
            "Los cuatro porcentajes suman 100 en todas las filas de resultados_geograficos",
            "SELECT COUNT(*) FROM resultados_geograficos WHERE "
            "ABS(pct_previo_inicio + pct_en_inicio + pct_en_proceso + pct_satisfactorio - 100) > 0.001",
        ),
        (
            "pct_critico equivale a Previo al inicio mas En inicio",
            "SELECT COUNT(*) FROM resultados_geograficos WHERE "
            "ABS(pct_critico - (pct_previo_inicio + pct_en_inicio)) > 0.001",
        ),
        (
            "Ningun peso nulo o no positivo en el hecho",
            "SELECT COUNT(*) FROM hechos_estudiante_area WHERE peso IS NULL OR peso <= 0",
        ),
        (
            "Ninguna medida o nivel nulo en el hecho",
            "SELECT COUNT(*) FROM hechos_estudiante_area WHERE medida500 IS NULL OR cod_nivel IS NULL",
        ),
        (
            "Todo ubigeo tiene seis digitos",
            "SELECT COUNT(*) FROM hechos_estudiante_area WHERE LENGTH(ubigeo) <> 6",
        ),
        (
            "Todo id_estudiante es unico dentro de su grado y area",
            "SELECT COUNT(*) FROM (SELECT grado, cod_area, id_estudiante FROM hechos_estudiante_area "
            "GROUP BY 1,2,3 HAVING COUNT(*) > 1)",
        ),
        (
            "Todo distrito del hecho existe en dim_distrito",
            "SELECT COUNT(*) FROM hechos_estudiante_area h "
            "LEFT JOIN dim_distrito d USING (ubigeo) WHERE d.ubigeo IS NULL",
        ),
    ]
    for descripcion, consulta in coherencia:
        incumplen = escalar(con, consulta)
        filas.append(
            {
                "control": "coherencia",
                "grado": None,
                "cod_area": None,
                "detalle": descripcion,
                "esperado": 0.0,
                "obtenido": float(incumplen),
                "diferencia": float(incumplen),
                "pasa": incumplen == 0,
            }
        )

    resultado = pd.DataFrame(filas)
    con.register("tmp_validacion", resultado)
    con.execute("CREATE OR REPLACE TABLE meta_validacion AS SELECT * FROM tmp_validacion")

    ancho = max(len(f["detalle"]) for f in filas)
    print(f"  {'grado':<6} {'area':<5} {'control':<{ancho}} {'esperado':>10} {'obtenido':>10}  estado")
    print("  " + "-" * (ancho + 38))
    for f in filas:
        estado = "ok" if f["pasa"] else "FALLA"
        print(
            f"  {(f['grado'] or ''):<6} {(f['cod_area'] or ''):<5} {f['detalle']:<{ancho}} "
            f"{f['esperado']:>10.1f} {f['obtenido']:>10.1f}  {estado}"
        )
    fallidos = int((~resultado["pasa"]).sum())
    print("  " + "-" * (ancho + 38))
    print(f"  {len(filas) - fallidos} de {len(filas)} controles correctos")
    return fallidos == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Construye el almacen DuckDB de GEO_EDUCA.")
    parser.add_argument(
        "--destino",
        type=Path,
        default=DESTINO_POR_DEFECTO,
        help=f"Ruta del archivo DuckDB de salida (por defecto {DESTINO_POR_DEFECTO}).",
    )
    args = parser.parse_args()
    return construir(args.destino.resolve())


if __name__ == "__main__":
    sys.exit(main())
