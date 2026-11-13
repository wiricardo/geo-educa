#!/usr/bin/env python3
"""Construye la capa geografica de GEO_EDUCA: poligonos listos para la web.

Fuente
------
Peru - Subnational Administrative Boundaries (COD-AB), de OCHA Field Information
Services Section, publicada en Humanitarian Data Exchange con licencia CC BY-IGO.
Ver FUENTES.md. El archivo que se descarga trae los niveles admin0 a admin3, mas
las capas de lineas y de puntos, que este script no usa.

Salidas, todas en geo/
----------------------
    departamentos.geojson      25 departamentos        (admin1)
    provincias.geojson        196 provincias           (admin2)
    distritos.geojson       1 873 unidades distritales (admin3)
    dre.geojson                26 Direcciones Regionales de Educacion
    ugel.geojson              222 Unidades de Gestion Educativa Local
    metadatos_geo.json        cifras y decisiones de esta construccion

Sistema de referencia
---------------------
Todo queda en EPSG:4326 (CRS84, orden longitud/latitud), igual que la fuente. No
se reproyecta nada en ningun paso. Las areas que el script necesita para decidir
la tolerancia de simplificacion se calculan con pyproj.Geod sobre el elipsoide
WGS84, no proyectando.

Uso
---
    .venv/bin/python ingest/build_geo.py
    .venv/bin/python ingest/build_geo.py --dir-crudos /otra/ruta

Es idempotente: si el zip ya esta descargado y descomprimido no vuelve a bajarlo,
las unidades se ordenan por codigo antes de escribir y las coordenadas se
redondean a un numero fijo de decimales, asi que dos corridas producen archivos
identicos byte a byte.

IMPORTANTE: el Python global de anaconda tiene pyproj roto. Hay que usar el
interprete del entorno virtual del proyecto (.venv/bin/python).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Geod

# --------------------------------------------------------------------------- #
# Rutas y fuente
# --------------------------------------------------------------------------- #

RAIZ = Path(__file__).resolve().parent.parent
DIR_GEO = RAIZ / "geo"
DIR_DATA = RAIZ / "DATA"

# Las bases de DATA/ son de solo lectura. El script nunca escribe ahi.
BASES_ENLA = {
    "4P": DIR_DATA / "BD_4P ENLA 2025.xlsx",
    "2S": DIR_DATA / "BD_2S ENLA 2025.xlsx",
    "5S": DIR_DATA / "BD_5S ENLA 2025.xlsx",
}
# La relacion distrito -> UGEL se toma de la base de 4.o de primaria, que es la
# mas extensa (129 482 estudiantes, 1 165 distritos) y la que define las 222 UGEL
# del proyecto. Las otras dos bases solo se leen para medir cobertura: entre las
# tres cubren 1 321 distritos y mencionan 223 UGEL. Si en algun momento se quiere
# que la capa de UGEL cubra tambien los distritos que solo aparecen en secundaria,
# basta poner aqui las tres claves; la capa pasaria de 222 a 223 unidades.
BASES_RELACION_UGEL = ("4P", "2S", "5S")

URL_FUENTE = (
    "https://data.humdata.org/dataset/54fc7f4d-f4c0-4892-91f6-2fe7c1ecf363/"
    "resource/63647792-0951-40d2-a30e-4a0e60f7a176/download/"
    "per_admin_boundaries.geojson.zip"
)
# HDX responde con una pagina HTML, no con el archivo, si el agente de usuario no
# parece un navegador. Con esta cabecera la descarga directa funciona.
AGENTE = "Mozilla/5.0"
NOMBRE_ZIP = "per_admin_boundaries.geojson.zip"
ARCHIVOS_FUENTE = ("per_admin1.geojson", "per_admin2.geojson", "per_admin3.geojson")

# --------------------------------------------------------------------------- #
# Simplificacion: que tolerancia se usa y por que
# --------------------------------------------------------------------------- #
#
# El problema: la capa de distritos de la fuente pesa 74 MB (1 598 113 vertices)
# y es inservible para una aplicacion web. Hay que bajar de unos 2 MB por capa sin
# que aparezcan huecos ni solapamientos entre poligonos vecinos.
#
# Herramienta: shapely.coverage_simplify (GEOS >= 3.12, aqui 3.14.1). Simplifica
# una cobertura de poligonos tratando cada borde compartido como una sola linea,
# asi que dos vecinos quedan siempre con el mismo borde: ni huecos ni solapes. El
# simplify() corriente, que trabaja poligono por poligono, si los produce.
#
# Por que no una sola tolerancia global: el pais mezcla distritos amazonicos de
# 10 000 km2 con distritos urbanos de 1 km2. Medido sobre esta misma fuente, una
# tolerancia unica que deje la capa en el peso buscado destroza los distritos
# chicos de Lima, Callao y Trujillo, que es donde se concentran los estudiantes.
#
# Lo que se usa: simplificacion progresiva por tamano. Una primera pasada aplica
# TOL_BASE a toda la cobertura, incluido el borde exterior (costa y frontera).
# Despues, para cada tolerancia de NIVELES, se vuelve a simplificar solo el
# subconjunto de distritos lo bastante grandes para tolerarla, y solo sus bordes
# interiores (simplify_boundary=False). Un borde entre un distrito grande y uno
# chico no se toca mas alla de TOL_BASE, porque para el subconjunto grande es un
# borde exterior. No hace falta calcular adyacencias: GEOS ya distingue el borde
# compartido del borde exterior del subconjunto.
#
# Un distrito "tolera" una tolerancia T si su lado equivalente en grados (la raiz
# de su area geodesica, dividida entre 111,32 km por grado) es al menos FACTOR_K
# veces T, es decir si T no pasa de ~1/12 de su tamano lineal.
#
# Las dos opciones, medidas con el mismo presupuesto de vertices (~70 000):
#
#     tolerancia unica 0,008 grados:  71 063 vertices | error de area por
#         distrito: mediana 0,45 %, p95 3,86 %, maximo 77,6 % (La Punta, Callao)
#     progresiva, la que se usa:      68 972 vertices | error de area por
#         distrito: mediana 0,50 %, p95 1,59 %, maximo 4,93 %
#
# La mediana empeora un pelo porque el presupuesto se gasta en las unidades
# chicas en lugar de las grandes, y a cambio el p95 baja a menos de la mitad y el
# maximo pasa de 77,6 % a 4,93 %: ya no hay ningun distrito irreconocible. El
# error de area del pais entero es de 0,000 %.
#
# Equivalencias utiles: 0,001 grados = ~111 m. A la escala en que se abre el mapa
# (el pais completo en unos 1 000 px) un pixel son ~0,015 grados, asi que pasar de
# 0,020 no tiene sentido: ya es mas fino que un pixel y lo unico que se consigue
# es angular los distritos amazonicos.
#
TOL_BASE = 0.002                                          # ~220 m, para todo
NIVELES = (0.004, 0.006, 0.008, 0.012, 0.016, 0.020)      # ~440 m a ~2,2 km
FACTOR_K = 12                                             # T <= lado/12
KM_POR_GRADO = 111.32

# Las capas de provincias, departamentos, DRE y UGEL no se simplifican por
# separado: se disuelven a partir de los distritos ya simplificados. Asi el borde
# de una provincia es exactamente la union de los bordes de sus distritos y las
# cinco capas encajan entre si, superpuestas o alternadas, sin desajustes. Al
# disolver desaparecen los bordes interiores, asi que cada capa agregada pesa
# bastante menos que la de distritos y ninguna necesita otra pasada.

PRECISION = 4   # decimales al escribir el GeoJSON: ~11 m, veinte veces mas fino
                # que TOL_BASE. Redondear es determinista, asi que los vertices
                # compartidos siguen coincidiendo y la topologia se mantiene.

OBJETIVO_MB = 2.0

# Campos que a proposito NO se guardan en distritos.geojson, para que la capa
# quede por debajo del objetivo: la provincia (son los cuatro primeros digitos
# del ubigeo, y el nombre esta en provincias.geojson), el nombre de la UGEL (esta
# en ugel.geojson, se cruza por cod_ugel) y el codigo de DRE (esta en ugel.geojson
# y se deduce del ubigeo con dre_territorial). Cada uno costaba entre 30 y 50 kB.

# --------------------------------------------------------------------------- #
# Los distritos con datos ENLA que no tienen poligono propio en la fuente
# --------------------------------------------------------------------------- #
#
# Son 12 de los 1 321 distritos con datos (0,9 %), y no son todos el mismo caso.
#
# a) Diez son distritos creados despues del 14 de julio de 2020, que es la fecha
#    de validez de la cartografia, separados de un distrito que si esta en la
#    capa. DECISION: quedan FUERA de la capa de distritos, documentados en
#    geo/metadatos_geo.json, en lugar de fusionarlos con su distrito de origen.
#    Fusionarlos obligaria a dos cosas que no se pueden sostener en una
#    herramienta de politica educativa:
#
#      1. Usar una tabla de equivalencias distrito nuevo -> distrito de origen
#         que no esta en ninguna fuente del proyecto. Habria que construirla a
#         mano desde las leyes de creacion, sin manera de verificarla con los
#         datos que tenemos.
#      2. Mezclar los indicadores de dos unidades administrativas distintas en un
#         solo poligono. El distrito de origen tiene sus propios resultados, y al
#         sumarle los del nuevo el valor que se pinta en el mapa deja de ser el
#         de ninguna de las dos unidades, sin que el usuario pueda notarlo.
#
#    Un hueco visible es mas honesto que una cifra mezclada, y el costo es solo
#    cartografico, no estadistico: los estudiantes de esos diez distritos siguen
#    contando en los agregados por UGEL, por DRE y nacionales, porque esos se
#    calculan desde los registros de la ENLA y no desde la geometria. La
#    aplicacion deberia mostrarlos como "sin geometria disponible" cuando el
#    usuario los busque, usando la lista de geo/metadatos_geo.json.
#
# b) Los otros dos, Mazamari (120604) y Pangoa (120606), son un caso distinto: su
#    territorio SI esta en la cartografia, pero en un solo poligono. Ver
#    UNIDADES_COMBINADAS.
#
DISTRITOS_SIN_GEOMETRIA_ESPERADOS = (
    "050512", "080915", "080917", "080918", "090724", "090725",
    "120604", "120606", "180107", "221006", "250306", "250307",
)

# --------------------------------------------------------------------------- #
# Unidades cartograficas que cubren mas de un distrito
# --------------------------------------------------------------------------- #
#
# El limite entre Mazamari y Pangoa (provincia de Satipo, Junin) esta en litigio,
# asi que la cartografia oficial no los separa: publica un solo poligono llamado
# "Mazamari - Pangoa" con el codigo de distrito 99, que es la convencion del INEI
# para estos casos. La ENLA si trae los dos distritos por separado.
#
# DECISION: el poligono se conserva como una unidad propia, con ubigeo 120699, y
# aqui queda escrito que cubre dos ubigeos. Quitarlo dejaria un hueco de ~3 000
# km2 en Junin por un limite que nadie discute con sus vecinos, y duplicarlo como
# 120604 y 120606 crearia dos poligonos superpuestos. Quien pinte el mapa de
# distritos tiene que sumar los datos de los dos ubigeos para esta unidad: la
# lista esta en geo/metadatos_geo.json.
#
# Para la capa de UGEL la unidad se asigna a la UGEL con mas estudiantes entre
# los distritos que cubre, la misma regla que se usa con los distritos que
# aparecen con mas de una UGEL. Sin esto la UGEL Pangoa se quedaria sin poligono,
# porque el unico distrito que la ENLA le asigna es Pangoa.
#
# Es la unica unidad combinada de la fuente, y el script lo comprueba en cada
# corrida avisando si aparece alguna otra.
#
UNIDADES_COMBINADAS = {"120699": ("120604", "120606")}

# --------------------------------------------------------------------------- #
# DRE: la capa no se puede tomar de la cartografia tal cual
# --------------------------------------------------------------------------- #
#
# Hay 26 DRE y 25 departamentos: el departamento de Lima se reparte entre la DRE
# Lima Metropolitana (provincia de Lima) y la DRE Lima Provincias (las otras nueve
# provincias). Callao es departamento y DRE a la vez. La capa de DRE se construye
# aplicando esa regla territorial sobre los distritos, y el script comprueba que
# reproduce el cod_DRE de la ENLA distrito por distrito.
#
# Unica excepcion en la ENLA 2025: el distrito 200706 (Piura, Talara) aparece con
# DRE Tumbes y UGEL Contralmirante Villar. Es una asignacion administrativa que
# cruza el limite departamental. La capa de DRE sigue el territorio y lo deja en
# DRE Piura, para que las 26 DRE formen una particion del pais sin huecos ni
# poligonos sueltos. En la capa de UGEL si se respeta la asignacion de la ENLA,
# porque ahi la unidad la define la ENLA y no el territorio.
#
GEOD = Geod(ellps="WGS84")


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def miles(n: float) -> str:
    """Formato peruano: espacio como separador de miles."""
    return f"{int(n):,}".replace(",", " ")


def dec(x: float, n: int = 2) -> str:
    """Formato peruano: coma decimal, espacio para los miles."""
    return f"{x:,.{n}f}".replace(",", "\x00").replace(".", ",").replace("\x00", " ")


def areas_km2(geometrias) -> np.ndarray:
    """Area geodesica en km2 sobre el elipsoide WGS84, sin proyectar."""
    return np.array([abs(GEOD.geometry_area_perimeter(g)[0]) / 1e6 for g in geometrias])


def mb(ruta: Path) -> float:
    return ruta.stat().st_size / 1e6


def paso(texto: str) -> None:
    print(f"\n[{time.strftime('%H:%M:%S')}] {texto}", flush=True)


# --------------------------------------------------------------------------- #
# 1. Descarga de la fuente
# --------------------------------------------------------------------------- #

def preparar_fuente(dir_crudos: Path) -> Path:
    """Descarga y descomprime la fuente si hace falta. Devuelve el directorio."""
    dir_crudos.mkdir(parents=True, exist_ok=True)
    dir_extraido = dir_crudos / "extraido"
    if all((dir_extraido / n).exists() for n in ARCHIVOS_FUENTE):
        print(f"  ya descomprimido en {dir_extraido}")
        return dir_extraido

    zip_local = dir_crudos / NOMBRE_ZIP
    if not zip_local.exists():
        print(f"  descargando {URL_FUENTE}")
        pedido = urllib.request.Request(URL_FUENTE, headers={"User-Agent": AGENTE})
        parcial = zip_local.with_suffix(".parcial")
        with urllib.request.urlopen(pedido) as respuesta, open(parcial, "wb") as salida:
            shutil.copyfileobj(respuesta, salida)
        parcial.replace(zip_local)
    print(f"  zip: {dec(mb(zip_local))} MB")

    if not zipfile.is_zipfile(zip_local):
        raise SystemExit(
            f"{zip_local} no es un zip. HDX devuelve una pagina HTML cuando el "
            "agente de usuario no parece un navegador: revisar la cabecera "
            "User-Agent de la descarga."
        )

    dir_extraido.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_local) as z:
        # Se extrae solo lo que se va a usar, y solo nombres planos, para no
        # confiar en las rutas que vengan dentro del zip.
        for nombre in z.namelist():
            if nombre not in ARCHIVOS_FUENTE:
                continue
            with z.open(nombre) as origen, open(dir_extraido / nombre, "wb") as destino:
                shutil.copyfileobj(origen, destino)
    faltan = [n for n in ARCHIVOS_FUENTE if not (dir_extraido / n).exists()]
    if faltan:
        raise SystemExit(f"el zip no trajo {', '.join(faltan)}")
    return dir_extraido


# --------------------------------------------------------------------------- #
# 2. Lectura y validacion de la cobertura de distritos
# --------------------------------------------------------------------------- #

def leer_distritos(dir_extraido: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(
        dir_extraido / "per_admin3.geojson",
        columns=["adm3_pcode", "adm3_name", "adm2_pcode", "adm2_name",
                 "adm1_pcode", "adm1_name"],
    )
    gdf = gdf.rename(columns={
        "adm3_name": "distrito", "adm2_name": "provincia", "adm1_name": "departamento",
    })
    # El pcode es el prefijo PE mas el ubigeo. PE030101 -> ubigeo 030101.
    for col, digitos in (("adm3_pcode", 6), ("adm2_pcode", 4), ("adm1_pcode", 2)):
        malos = gdf[~gdf[col].str.fullmatch(rf"PE\d{{{digitos}}}")]
        if len(malos):
            raise SystemExit(f"{col} con formato inesperado: {malos[col].tolist()[:5]}")
    gdf["ubigeo"] = gdf.adm3_pcode.str.removeprefix("PE")
    gdf["ubigeo_prov"] = gdf.adm2_pcode.str.removeprefix("PE")
    gdf["ubigeo_dep"] = gdf.adm1_pcode.str.removeprefix("PE")
    if gdf.ubigeo.duplicated().any():
        raise SystemExit("hay ubigeos repetidos en la capa de distritos")
    # Los ubigeos tienen que anidar: los cuatro primeros digitos son la provincia
    # y los dos primeros el departamento.
    if not (gdf.ubigeo.str[:4] == gdf.ubigeo_prov).all():
        raise SystemExit("hay distritos cuyo ubigeo no empieza con el de su provincia")
    if not (gdf.ubigeo.str[:2] == gdf.ubigeo_dep).all():
        raise SystemExit("hay distritos cuyo ubigeo no empieza con el de su departamento")

    gdf = gdf.sort_values("ubigeo").reset_index(drop=True)
    geoms = gdf.geometry.to_numpy()
    invalidas = int((~shapely.is_valid(geoms)).sum())
    vacias = int(shapely.is_empty(geoms).sum())
    print(f"  {miles(len(gdf))} unidades | "
          f"{miles(shapely.get_num_coordinates(geoms).sum())} vertices | "
          f"CRS {gdf.crs.to_string()}")
    print(f"  geometrias invalidas: {invalidas} | vacias: {vacias}")
    if invalidas or vacias:
        raise SystemExit("la fuente trae geometrias invalidas o vacias")
    valida = bool(shapely.coverage_is_valid(geoms, gap_width=0.0))
    print(f"  cobertura valida (sin huecos ni solapamientos): {valida}")
    if not valida:
        bordes = shapely.coverage_invalid_edges(geoms, gap_width=0.0)
        culpables = [gdf.ubigeo.iloc[i] for i, b in enumerate(bordes)
                     if b is not None and not b.is_empty]
        raise SystemExit(f"cobertura invalida en: {culpables[:20]}")
    return gdf


def verificar_unidades_combinadas(con_geometria: set, universo_enla: set) -> None:
    """Comprueba que las unidades combinadas son las que quedaron documentadas."""
    con_codigo_99 = {u for u in con_geometria if u[4:] == "99"}
    if con_codigo_99 != set(UNIDADES_COMBINADAS):
        print("  AVISO: las unidades con codigo de distrito 99 de la fuente "
              f"({sorted(con_codigo_99)}) ya no son las documentadas en "
              f"UNIDADES_COMBINADAS ({sorted(UNIDADES_COMBINADAS)}). Revisar.")
    for combinada, miembros in UNIDADES_COMBINADAS.items():
        if combinada not in con_geometria:
            print(f"  AVISO: la unidad combinada {combinada} ya no esta en la cartografia")
            continue
        propios = [m for m in miembros if m in con_geometria]
        if propios:
            print(f"  AVISO: {', '.join(propios)} ya tienen poligono propio. "
                  "Sacarlos de UNIDADES_COMBINADAS.")
        sin_datos = [m for m in miembros if m not in universo_enla]
        print(f"  {combinada} cubre {', '.join(miembros)} (limite en litigio, la "
              f"cartografia no los separa)"
              + (f"; sin datos ENLA: {', '.join(sin_datos)}" if sin_datos else ""))


# --------------------------------------------------------------------------- #
# 3. Simplificacion progresiva por tamano
# --------------------------------------------------------------------------- #

def simplificar(geoms: np.ndarray, areas: np.ndarray) -> np.ndarray:
    lado = np.sqrt(areas) / KM_POR_GRADO   # lado equivalente, en grados
    actual = shapely.coverage_simplify(geoms, TOL_BASE, simplify_boundary=True)
    print(f"  pasada base sobre toda la cobertura, tolerancia {dec(TOL_BASE, 4)} "
          f"grados: {miles(shapely.get_num_coordinates(actual).sum())} vertices")
    for tol in NIVELES:
        sel = np.flatnonzero(lado >= FACTOR_K * tol)
        if sel.size == 0:
            continue
        # Solo los bordes interiores del subconjunto: los bordes con los distritos
        # que quedan fuera no se tocan, asi que la topologia global se mantiene.
        actual[sel] = shapely.coverage_simplify(actual[sel], tol, simplify_boundary=False)
        print(f"  tolerancia {dec(tol, 3)} grados (~{miles(tol * KM_POR_GRADO * 1000)} m) "
              f"sobre {miles(sel.size)} unidades: "
              f"{miles(shapely.get_num_coordinates(actual).sum())} vertices")
    return actual


def verificar_cobertura(geoms: np.ndarray, etiqueta: str) -> None:
    invalidas = int((~shapely.is_valid(geoms)).sum())
    vacias = int(shapely.is_empty(geoms).sum())
    valida = bool(shapely.coverage_is_valid(geoms, gap_width=0.0))
    print(f"  {etiqueta}: cobertura valida {valida} | invalidas {invalidas} | "
          f"vacias {vacias}")
    if not valida or invalidas or vacias:
        raise SystemExit(f"se rompio la topologia en {etiqueta}")


# --------------------------------------------------------------------------- #
# 4. Disolucion de distritos en unidades mayores
# --------------------------------------------------------------------------- #

def disolver(geoms: np.ndarray, claves) -> dict:
    """Une las geometrias de cada grupo. Devuelve {clave: geometria}."""
    grupos: dict[str, list[int]] = {}
    for i, clave in enumerate(claves):
        grupos.setdefault(clave, []).append(i)
    salida = {}
    for clave, indices in grupos.items():
        trozos = geoms[np.asarray(indices)]
        if len(trozos) == 1:
            salida[clave] = trozos[0]
            continue
        try:
            # Union de cobertura: exacta y rapida cuando los bordes coinciden.
            salida[clave] = shapely.coverage_union_all(trozos)
        except shapely.errors.GEOSException:
            salida[clave] = shapely.union_all(trozos)
    return salida


# --------------------------------------------------------------------------- #
# 5. La ENLA: universo de distritos y relacion distrito -> UGEL
# --------------------------------------------------------------------------- #

COLS_ENLA = ["codgeo", "cod_UGEL", "nom_UGEL", "cod_DRE", "nom_DRE",
             "Departamento", "Provincia", "Distrito"]


def leer_enla() -> dict[str, pd.DataFrame]:
    """Lee las columnas geograficas de las tres bases. DATA/ es de solo lectura."""
    bases = {}
    for clave, ruta in BASES_ENLA.items():
        if not ruta.exists():
            raise SystemExit(f"falta {ruta}. Ver FUENTES.md para obtenerla.")
        df = pd.read_excel(ruta, sheet_name="BD", usecols=COLS_ENLA, dtype=str)
        # codgeo viene como entero y pierde el cero inicial: se normaliza a seis
        # digitos. Si ya viene como texto de seis, zfill no hace nada.
        df["ubigeo"] = df.codgeo.str.strip().str.zfill(6)
        for col in COLS_ENLA:
            if col != "codgeo":
                df[col] = df[col].str.strip()
        if not df.ubigeo.str.fullmatch(r"\d{6}").all():
            raise SystemExit(f"{ruta.name}: hay codgeo que no son seis digitos")
        bases[clave] = df
        print(f"  {ruta.name}: {miles(len(df))} estudiantes | "
              f"{miles(df.ubigeo.nunique())} distritos | "
              f"{miles(df.cod_UGEL.nunique())} UGEL")
    return bases


def resolver_relacion_ugel(bases: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, list]:
    """Distrito -> UGEL. Donde hay mas de una, gana la de mas estudiantes."""
    df = pd.concat([bases[k] for k in BASES_RELACION_UGEL], ignore_index=True)
    conteo = (df.groupby(["ubigeo", "cod_UGEL", "nom_UGEL", "cod_DRE", "nom_DRE"])
                .size().reset_index(name="n_estudiantes"))
    total_distrito = df.groupby("ubigeo").size()
    # Orden determinista: mas estudiantes primero y, si empatan, menor codigo de
    # UGEL. Asi el resultado no depende del orden de las filas de la base.
    conteo = conteo.sort_values(["ubigeo", "n_estudiantes", "cod_UGEL"],
                               ascending=[True, False, True])
    decisiones = []
    for ubigeo, grupo in conteo.groupby("ubigeo", sort=True):
        if len(grupo) == 1:
            continue
        gana, pierden = grupo.iloc[0], grupo.iloc[1:]
        decisiones.append({
            "ubigeo": ubigeo,
            "distrito": df.loc[df.ubigeo == ubigeo, "Distrito"].iloc[0],
            "ugel_asignada": f"{gana.cod_UGEL} {gana.nom_UGEL}",
            "estudiantes_asignada": int(gana.n_estudiantes),
            "ugel_descartadas": [
                {"ugel": f"{r.cod_UGEL} {r.nom_UGEL}", "estudiantes": int(r.n_estudiantes)}
                for r in pierden.itertuples()
            ],
            "empate": bool(pierden.n_estudiantes.max() == gana.n_estudiantes),
        })
    relacion = conteo.drop_duplicates("ubigeo", keep="first").reset_index(drop=True)
    relacion["n_estudiantes_distrito"] = relacion.ubigeo.map(total_distrito)
    print(f"  {miles(len(relacion))} distritos con UGEL | "
          f"{miles(relacion.cod_UGEL.nunique())} UGEL")
    print(f"  distritos que aparecen con mas de una UGEL: {len(decisiones)} "
          f"({dec(len(decisiones) / len(relacion) * 100)} %); se asigna la de mas "
          "estudiantes y se deja constancia en geo/metadatos_geo.json")
    for d in decisiones:
        descartadas = ", ".join(f"{x['ugel']} ({miles(x['estudiantes'])})"
                                for x in d["ugel_descartadas"])
        aviso = "  EMPATE, se desempata por codigo" if d["empate"] else ""
        print(f"    {d['ubigeo']} {d['distrito'][:22]:22s} -> {d['ugel_asignada']} "
              f"({miles(d['estudiantes_asignada'])}) | descartada: {descartadas}{aviso}")
    return relacion, decisiones


def dre_territorial(ubigeo: str) -> str:
    """Codigo de DRE que le corresponde a un distrito por territorio.

    26 DRE sobre 25 departamentos: Lima se parte en Lima Metropolitana (provincia
    de Lima, 1501) y Lima Provincias (1502). Callao es su propia DRE (0701).
    """
    dep, prov = ubigeo[:2], ubigeo[:4]
    if dep == "07":
        return "0701"
    if dep == "15":
        return "1501" if prov == "1501" else "1502"
    return dep + "00"


def validar_regla_dre(bases: dict[str, pd.DataFrame]) -> tuple[list, dict]:
    """Comprueba la regla territorial de DRE contra el cod_DRE de la ENLA."""
    df = pd.concat(bases.values(), ignore_index=True)
    pares = df.groupby(["ubigeo", "cod_DRE", "nom_DRE"]).size().reset_index(name="n")
    excepciones = []
    for r in pares.itertuples():
        if dre_territorial(r.ubigeo) != r.cod_DRE:
            excepciones.append({
                "ubigeo": r.ubigeo,
                "dre_enla": f"{r.cod_DRE} {r.nom_DRE}",
                "dre_territorial": dre_territorial(r.ubigeo),
                "estudiantes": int(r.n),
            })
    print(f"  la regla territorial reproduce el cod_DRE de la ENLA en "
          f"{miles(len(pares) - len(excepciones))} de {miles(len(pares))} distritos")
    for e in excepciones:
        print(f"    excepcion: {e['ubigeo']} esta en DRE {e['dre_enla']} segun la "
              f"ENLA ({miles(e['estudiantes'])} estudiantes); la capa lo deja en "
              f"DRE {e['dre_territorial']} por territorio")
    nombres = df.drop_duplicates("cod_DRE").set_index("cod_DRE")["nom_DRE"].to_dict()
    return excepciones, nombres


# --------------------------------------------------------------------------- #
# 6. Escritura
# --------------------------------------------------------------------------- #

def escribir(gdf: gpd.GeoDataFrame, ruta: Path) -> dict:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(ruta, driver="GeoJSON", COORDINATE_PRECISION=PRECISION)
    vertices = int(shapely.get_num_coordinates(gdf.geometry.to_numpy()).sum())
    info = {"archivo": f"geo/{ruta.name}", "unidades": len(gdf),
            "vertices": vertices, "mb": round(mb(ruta), 3),
            "campos": [c for c in gdf.columns if c != "geometry"]}
    aviso = "" if info["mb"] <= OBJETIVO_MB else f"   POR ENCIMA DE {OBJETIVO_MB} MB"
    print(f"  {ruta.name:22s} {miles(len(gdf)):>6} unidades | "
          f"{miles(vertices):>8} vertices | {dec(info['mb'])} MB{aviso}")
    return info


# --------------------------------------------------------------------------- #
# Programa principal
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir-crudos", type=Path, default=DIR_GEO / "raw",
                    help="donde guardar y descomprimir la descarga "
                         "(por omision geo/raw, que .gitignore excluye)")
    ap.add_argument("--dir-salida", type=Path, default=DIR_GEO,
                    help="donde escribir las capas (por omision geo/)")
    args = ap.parse_args()
    t_inicio = time.time()

    paso("Fuente HDX")
    dir_extraido = preparar_fuente(args.dir_crudos)

    paso("Unidades distritales de la fuente")
    distritos = leer_distritos(dir_extraido)
    geoms0 = distritos.geometry.to_numpy()
    vertices0 = int(shapely.get_num_coordinates(geoms0).sum())
    areas0 = areas_km2(geoms0)

    paso("Simplificacion progresiva por tamano")
    geoms = simplificar(geoms0, areas0)
    verificar_cobertura(geoms, "distritos simplificados")
    areas1 = areas_km2(geoms)
    err = np.abs(areas1 - areas0) / areas0 * 100
    vertices1 = int(shapely.get_num_coordinates(geoms).sum())
    print(f"  vertices: {miles(vertices0)} -> {miles(vertices1)} "
          f"({dec(vertices1 / vertices0 * 100)} % del original)")
    print(f"  error de area por unidad: mediana {dec(np.median(err))} %, "
          f"p95 {dec(np.percentile(err, 95))} %, maximo {dec(err.max())} %")
    print(f"  error de area del pais: "
          f"{dec(abs(areas1.sum() - areas0.sum()) / areas0.sum() * 100, 3)} % "
          f"sobre {miles(areas0.sum())} km2")

    paso("Bases ENLA (solo lectura)")
    bases = leer_enla()
    universo = sorted(set().union(*(set(b.ubigeo) for b in bases.values())))
    universo_set = set(universo)
    print(f"  universo ENLA: {miles(len(universo))} distritos con datos en alguna base")

    paso("Relacion distrito -> UGEL")
    relacion, decisiones_ugel = resolver_relacion_ugel(bases)
    excepciones_dre, nombres_dre = validar_regla_dre(bases)

    paso("Unidades cartograficas que cubren mas de un distrito")
    con_geometria = set(distritos.ubigeo)
    verificar_unidades_combinadas(con_geometria, universo_set)

    paso("Construccion de capas")
    mapa_ugel = relacion.set_index("ubigeo")
    nombres_enla = (pd.concat(bases.values(), ignore_index=True)
                      .drop_duplicates("ubigeo").set_index("ubigeo")
                      [["Departamento", "Provincia", "Distrito"]])

    # UGEL de cada unidad cartografica. Para las unidades combinadas se aplica la
    # misma regla que para los distritos con mas de una UGEL: gana la UGEL con mas
    # estudiantes entre los distritos que cubre.
    ugel_unidad: dict[str, str] = {}
    decisiones_combinadas = []
    for unidad in distritos.ubigeo:
        miembros = [m for m in UNIDADES_COMBINADAS.get(unidad, (unidad,))
                    if m in mapa_ugel.index]
        if not miembros:
            continue
        miembros.sort(key=lambda m: (-int(mapa_ugel.n_estudiantes_distrito[m]), m))
        elegido = miembros[0]
        ugel_unidad[unidad] = mapa_ugel.cod_UGEL[elegido]
        if len(miembros) > 1:
            decisiones_combinadas.append({
                "unidad": unidad,
                "ubigeos_cubiertos": list(UNIDADES_COMBINADAS[unidad]),
                "ugel_asignada": f"{mapa_ugel.cod_UGEL[elegido]} {mapa_ugel.nom_UGEL[elegido]}",
                "por": f"{elegido} con {int(mapa_ugel.n_estudiantes_distrito[elegido])} estudiantes",
                "ugel_descartadas": [
                    f"{mapa_ugel.cod_UGEL[m]} {mapa_ugel.nom_UGEL[m]} "
                    f"({int(mapa_ugel.n_estudiantes_distrito[m])} estudiantes de {m})"
                    for m in miembros[1:]
                ],
            })
    for d in decisiones_combinadas:
        print(f"  {d['unidad']} (cubre {', '.join(d['ubigeos_cubiertos'])}) -> UGEL "
              f"{d['ugel_asignada']}, por {d['por']}; descartada: "
              f"{', '.join(d['ugel_descartadas'])}")

    cod_ugel_unidad = [ugel_unidad.get(u) for u in distritos.ubigeo]
    nombre_unidad = distritos.set_index("ubigeo").distrito

    # Distritos: la capa base. Ya viene ordenada por ubigeo desde leer_distritos.
    cap_dist = gpd.GeoDataFrame({
        "ubigeo": distritos.ubigeo,
        "distrito": distritos.distrito,
        "departamento": distritos.departamento,
        "cod_ugel": cod_ugel_unidad,
    }, geometry=geoms, crs=distritos.crs)

    # Provincias y departamentos: disolucion de los distritos ya simplificados.
    geo_prov = disolver(geoms, distritos.ubigeo_prov.tolist())
    ref_prov = distritos.drop_duplicates("ubigeo_prov").set_index("ubigeo_prov")
    cap_prov = gpd.GeoDataFrame({
        "ubigeo_prov": list(geo_prov),
        "provincia": [ref_prov.provincia[k] for k in geo_prov],
        "departamento": [ref_prov.departamento[k] for k in geo_prov],
    }, geometry=list(geo_prov.values()), crs=distritos.crs
    ).sort_values("ubigeo_prov").reset_index(drop=True)

    geo_dep = disolver(geoms, distritos.ubigeo_dep.tolist())
    ref_dep = distritos.drop_duplicates("ubigeo_dep").set_index("ubigeo_dep")
    cap_dep = gpd.GeoDataFrame({
        "ubigeo_dep": list(geo_dep),
        "departamento": [ref_dep.departamento[k] for k in geo_dep],
    }, geometry=list(geo_dep.values()), crs=distritos.crs
    ).sort_values("ubigeo_dep").reset_index(drop=True)

    # DRE: regla territorial, 26 unidades que cubren todo el pais.
    geo_dre = disolver(geoms, [dre_territorial(u) for u in distritos.ubigeo])
    cap_dre = gpd.GeoDataFrame({
        "cod_dre": list(geo_dre),
        "nom_dre": [nombres_dre.get(k, "") for k in geo_dre],
    }, geometry=list(geo_dre.values()), crs=distritos.crs
    ).sort_values("cod_dre").reset_index(drop=True)

    # UGEL: no existe como unidad cartografica oficial, se construye disolviendo
    # las unidades distritales que la ENLA le asigna.
    idx = np.flatnonzero([c is not None for c in cod_ugel_unidad])
    geo_ugel = disolver(geoms[idx], [cod_ugel_unidad[i] for i in idx])
    ref_ugel = relacion.drop_duplicates("cod_UGEL").set_index("cod_UGEL")
    n_dist_enla = relacion.cod_UGEL.value_counts()        # distritos con datos ENLA
    n_unid_geo = pd.Series([cod_ugel_unidad[i] for i in idx]).value_counts()
    cap_ugel = gpd.GeoDataFrame({
        "cod_ugel": list(geo_ugel),
        "nom_ugel": [ref_ugel.nom_UGEL[k] for k in geo_ugel],
        "cod_dre": [ref_ugel.cod_DRE[k] for k in geo_ugel],
        "nom_dre": [ref_ugel.nom_DRE[k] for k in geo_ugel],
        "n_distritos": [int(n_dist_enla[k]) for k in geo_ugel],
        "n_unidades_geo": [int(n_unid_geo[k]) for k in geo_ugel],
    }, geometry=list(geo_ugel.values()), crs=distritos.crs
    ).sort_values("cod_ugel").reset_index(drop=True)

    ugel_sin_poligono = sorted(set(relacion.cod_UGEL) - set(cap_ugel.cod_ugel))
    if ugel_sin_poligono:
        print(f"  AVISO: {len(ugel_sin_poligono)} UGEL se quedaron sin poligono "
              f"porque ninguna de sus unidades tiene geometria: {ugel_sin_poligono}")

    for capa, etiqueta in ((cap_prov, "provincias"), (cap_dep, "departamentos"),
                           (cap_dre, "DRE"), (cap_ugel, "UGEL")):
        verificar_cobertura(capa.geometry.to_numpy(), etiqueta)

    paso("Escritura de las capas")
    salidas = [
        escribir(cap_dep, args.dir_salida / "departamentos.geojson"),
        escribir(cap_prov, args.dir_salida / "provincias.geojson"),
        escribir(cap_dist, args.dir_salida / "distritos.geojson"),
        escribir(cap_dre, args.dir_salida / "dre.geojson"),
        escribir(cap_ugel, args.dir_salida / "ugel.geojson"),
    ]

    # ------------------------------------------------------------------- #
    # Reporte de cobertura
    # ------------------------------------------------------------------- #
    paso("Reporte de cobertura")
    cubiertos_por_unidad = {u: UNIDADES_COMBINADAS.get(u, (u,)) for u in distritos.ubigeo}
    prov_enla = {u[:4] for u in universo_set}
    dep_enla = {u[:2] for u in universo_set}
    dre_enla = {dre_territorial(u) for u in universo_set}
    cruces = {
        "departamentos.geojson": sum(1 for k in cap_dep.ubigeo_dep if k in dep_enla),
        "provincias.geojson": sum(1 for k in cap_prov.ubigeo_prov if k in prov_enla),
        "distritos.geojson": sum(1 for u in cap_dist.ubigeo
                                 if universo_set.intersection(cubiertos_por_unidad[u])),
        "dre.geojson": sum(1 for k in cap_dre.cod_dre if k in dre_enla),
        "ugel.geojson": len(cap_ugel),
    }
    print(f"  {'capa':24s} {'unidades':>9} {'con datos ENLA':>16} {'tamano':>10}")
    for info in salidas:
        nombre = Path(info["archivo"]).name
        con, total = cruces[nombre], info["unidades"]
        info["con_datos_enla"] = con
        print(f"  {nombre:24s} {miles(total):>9} "
              f"{miles(con) + ' (' + dec(con / total * 100, 1) + ' %)':>16} "
              f"{dec(info['mb']) + ' MB':>10}")

    # Cobertura a nivel de ubigeo, que es lo que importa para cruzar con la ENLA.
    sin_geometria = [u for u in universo if u not in con_geometria]
    miembros_combinados = {m for ms in UNIDADES_COMBINADAS.values() for m in ms}
    en_combinada = [u for u in sin_geometria if u in miembros_combinados]
    fuera = [u for u in sin_geometria if u not in miembros_combinados]
    representables = len(universo_set) - len(fuera)
    print(f"\n  distritos con datos ENLA: {miles(len(universo_set))}")
    print(f"    con poligono propio:        {miles(len(universo_set & con_geometria))} "
          f"({dec(len(universo_set & con_geometria) / len(universo_set) * 100)} %)")
    print(f"    dentro de una unidad combinada: {len(en_combinada)} "
          f"({', '.join(en_combinada)})")
    print(f"    representables en el mapa:  {miles(representables)} "
          f"({dec(representables / len(universo_set) * 100)} %)")
    print(f"    sin geometria, quedan fuera: {len(fuera)}")
    for u in fuera:
        fila = nombres_enla.loc[u] if u in nombres_enla.index else None
        nombre = (f"{fila.Distrito}, {fila.Provincia}, {fila.Departamento}"
                  if fila is not None else "?")
        ugel = (mapa_ugel.nom_UGEL[u] if u in mapa_ugel.index
                else "solo aparece en secundaria")
        print(f"      {u}  {nombre:46s} UGEL: {ugel}")
    inesperados = sorted(set(sin_geometria) ^ set(DISTRITOS_SIN_GEOMETRIA_ESPERADOS))
    if inesperados:
        print("  AVISO: la lista de distritos sin geometria cambio respecto de la "
              f"verificada en octubre de 2025: {inesperados}")
    print("  decision: los que quedan fuera estan documentados en "
          "geo/metadatos_geo.json, con su nombre y su UGEL, para que la "
          "aplicacion pueda declararlos sin geometria. Sus estudiantes siguen "
          "contando en los agregados por UGEL, DRE y nacionales.")

    todas_ugel = pd.concat(bases.values(), ignore_index=True).cod_UGEL.nunique()
    if todas_ugel != len(cap_ugel):
        print(f"\n  nota: la capa de UGEL se construye con la base "
              f"{', '.join(BASES_RELACION_UGEL)} y tiene {miles(len(cap_ugel))} "
              f"unidades. Sumando las tres bases la ENLA 2025 menciona "
              f"{miles(todas_ugel)} UGEL: la diferencia solo aparece en secundaria.")

    # ------------------------------------------------------------------- #
    # Metadatos
    # ------------------------------------------------------------------- #
    metadatos = {
        "generado_por": "ingest/build_geo.py",
        "fuente": {
            "nombre": "Peru - Subnational Administrative Boundaries (COD-AB)",
            "institucion": "OCHA Field Information Services Section",
            "portal": "https://data.humdata.org/dataset/cod-ab-per",
            "url_descarga": URL_FUENTE,
            "licencia": "CC BY-IGO",
        },
        "crs": "EPSG:4326 (CRS84, orden longitud/latitud). No se reproyecta nada.",
        "simplificacion": {
            "metodo": "shapely.coverage_simplify, progresiva por tamano de unidad",
            "preserva_topologia": True,
            "tolerancia_base_grados": TOL_BASE,
            "niveles_grados": list(NIVELES),
            "factor_k": FACTOR_K,
            "precision_coordenadas_decimales": PRECISION,
            "vertices_originales": vertices0,
            "vertices_resultantes": vertices1,
            "error_area_unidad_mediana_pct": round(float(np.median(err)), 3),
            "error_area_unidad_p95_pct": round(float(np.percentile(err, 95)), 3),
            "error_area_unidad_max_pct": round(float(err.max()), 3),
            "error_area_pais_pct": round(
                float(abs(areas1.sum() - areas0.sum()) / areas0.sum() * 100), 4),
        },
        "capas": salidas,
        "campos_omitidos_en_distritos": (
            "provincia (son los cuatro primeros digitos del ubigeo, el nombre esta "
            "en provincias.geojson), nom_ugel (esta en ugel.geojson, se cruza por "
            "cod_ugel) y cod_dre (esta en ugel.geojson). Se omiten para que la capa "
            "quede por debajo de 2 MB."
        ),
        "cobertura_enla": {
            "bases": {k: v.name for k, v in BASES_ENLA.items()},
            "base_relacion_ugel": list(BASES_RELACION_UGEL),
            "distritos_con_datos": len(universo_set),
            "distritos_con_poligono_propio": len(universo_set & con_geometria),
            "distritos_dentro_de_unidad_combinada": en_combinada,
            "distritos_representables_en_el_mapa": representables,
            "ugel_en_la_capa": len(cap_ugel),
            "ugel_mencionadas_en_las_tres_bases": int(todas_ugel),
        },
        "distritos_sin_geometria": [
            {
                "ubigeo": u,
                "distrito": (nombres_enla.loc[u].Distrito
                             if u in nombres_enla.index else None),
                "provincia": (nombres_enla.loc[u].Provincia
                              if u in nombres_enla.index else None),
                "departamento": (nombres_enla.loc[u].Departamento
                                 if u in nombres_enla.index else None),
                "cod_ugel": (mapa_ugel.cod_UGEL[u] if u in mapa_ugel.index else None),
                "nom_ugel": (mapa_ugel.nom_UGEL[u] if u in mapa_ugel.index else None),
            }
            for u in fuera
        ],
        "decision_distritos_sin_geometria": (
            "Quedan fuera de la capa de distritos. Son distritos creados despues del "
            "14 de julio de 2020, fecha de validez de la cartografia, separados de un "
            "distrito que si esta en la capa. Fusionarlos con su distrito de origen "
            "exigiria una tabla de equivalencias que no esta en ninguna fuente del "
            "proyecto y mezclaria los indicadores de dos unidades administrativas en "
            "un solo poligono, de modo que el valor pintado no seria el de ninguna de "
            "las dos. La perdida es solo cartografica: sus estudiantes siguen contando "
            "en los agregados por UGEL, DRE y nacionales, que se calculan desde los "
            "registros de la ENLA y no desde la geometria."
        ),
        "unidades_cartograficas_combinadas": [
            {
                "unidad": unidad,
                "nombre_en_la_fuente": nombre_unidad[unidad],
                "ubigeos_cubiertos": list(miembros),
                "motivo": ("el limite entre los dos distritos esta en litigio y la "
                           "cartografia oficial no los separa: publica un solo "
                           "poligono con codigo de distrito 99"),
                "para_pintar_el_mapa": ("sumar los datos de los ubigeos cubiertos y "
                                        "atribuirlos a esta unidad"),
            }
            for unidad, miembros in UNIDADES_COMBINADAS.items()
        ],
        "ugel_de_unidades_combinadas": decisiones_combinadas,
        "distritos_con_mas_de_una_ugel": decisiones_ugel,
        "decision_distritos_con_mas_de_una_ugel": (
            "Se asigna la UGEL con mas estudiantes en la base de 4.o de primaria. Si "
            "hubiera empate se desempata por el menor codigo de UGEL, para que el "
            "resultado no dependa del orden de las filas de la base."
        ),
        "dre": {
            "unidades": len(cap_dre),
            "regla": ("26 DRE sobre 25 departamentos: Lima se parte en Lima "
                      "Metropolitana (provincia 1501) y Lima Provincias (el resto); "
                      "Callao es DRE propia (0701). La capa sigue el territorio."),
            "excepciones_respecto_de_la_enla": excepciones_dre,
        },
        "nota_sobre_nombres": (
            "Los nombres de departamento, provincia y distrito son los de la fuente "
            "cartografica y vienen sin tilde en varios casos (Ancash, Apurimac, "
            "Junin). Para mostrar en pantalla conviene usar los nombres de la ENLA, "
            "que si las llevan, cruzando por ubigeo."
        ),
    }
    ruta_meta = args.dir_salida / "metadatos_geo.json"
    ruta_meta.write_text(json.dumps(metadatos, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    print(f"\n  metadatos: geo/{ruta_meta.name} ({dec(mb(ruta_meta))} MB)")
    print(f"\nlisto en {dec(time.time() - t_inicio, 1)} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
