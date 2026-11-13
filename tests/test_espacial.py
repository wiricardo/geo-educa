"""Pruebas del análisis de autocorrelación espacial.

Hay dos clases de prueba aquí y conviene no confundirlas:

1. Sobre cuadrículas sintéticas, donde el resultado correcto se conoce de
   antemano: en una cuadrícula partida en dos mitades el índice de Moran tiene
   que ser positivo y alto, en una de franjas alternadas negativo, y en una de
   valores al azar no significativo. Si estas fallan, el estadístico está mal
   calculado.
2. Sobre los datos del proyecto, que fijan las cifras publicadas para que un
   cambio de código no las mueva sin que nadie se dé cuenta. Si estas fallan
   sin que hayan cambiado el almacén ni las capas, el cálculo cambió.

Los módulos de `src/geoeduca` no abren la base ni leen archivos: reciben
DataFrames. La carga vive acá, en las pruebas.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from geoeduca import espacial
import pandas as pd

from geoeduca.espacial import (
    CATEGORIAS_LISA,
    analizar_autocorrelacion,
    combinar_unidades_cartograficas,
    construir_vecindad,
    distancia_geodesica_km,
    filtrar_por_muestra,
    formato_p,
    lisa,
    moran_global,
    unir_con_geometria,
)

RAIZ = Path(__file__).resolve().parents[1]
ALMACEN = RAIZ / "processed" / "geoeduca.duckdb"
CAPAS = RAIZ / "geo"

# Caso de referencia del proyecto: 4.° de primaria, Matemática, nivel UGEL.
GRADO = "4P"
AREA = "M"


# --------------------------------------------------------------------------- #
# Carga de datos: solo en las pruebas, nunca en los módulos
# --------------------------------------------------------------------------- #


def _resultados(nivel: str, grado: str = GRADO, area: str = AREA):
    """Trae un corte de `resultados_geograficos` en solo lectura."""
    duckdb = pytest.importorskip("duckdb")
    if not ALMACEN.exists():
        pytest.skip(f"No existe el almacén en {ALMACEN}.")
    con = duckdb.connect(str(ALMACEN), read_only=True)
    try:
        return con.execute(
            """
            SELECT * FROM resultados_geograficos
            WHERE nivel_geografico = ? AND grado = ? AND cod_area = ?
            """,
            [nivel, grado, area],
        ).df()
    finally:
        con.close()


def _capa(archivo: str):
    """Lee una capa de `geo/`, que está en EPSG:4326 y no se reproyecta."""
    gpd = pytest.importorskip("geopandas")
    ruta = CAPAS / archivo
    if not ruta.exists():
        pytest.skip(f"No existe la capa {ruta}.")
    return gpd.read_file(ruta)


@pytest.fixture(scope="module")
def ugel_matematica():
    """UGEL con los resultados de Matemática de 4.° de primaria ya unidos."""
    capa, _ = unir_con_geometria(_capa("ugel.geojson"), _resultados("ugel"), "cod_ugel")
    return capa


@pytest.fixture(scope="module")
def distritos_matematica():
    """Distritos con los resultados unidos, sumando las unidades combinadas."""
    capa, diagnostico = unir_con_geometria(
        _capa("distritos.geojson"),
        _resultados("distrito"),
        "ubigeo",
        combinar_cartograficas=True,
    )
    return capa, diagnostico


@pytest.fixture(scope="module")
def vecindad_ugel(ugel_matematica):
    """Contigüidad Queen del caso de referencia, con muestra mínima 30."""
    return construir_vecindad(ugel_matematica, "pct_critico")


# --------------------------------------------------------------------------- #
# Cuadrículas sintéticas
# --------------------------------------------------------------------------- #


def _cuadricula(lado: int, valor, isla=None):
    """Cuadrícula de celdas cuadradas contiguas, en EPSG:4326.

    `valor` es una función de (fila, columna). Con `isla` se agrega una celda
    suelta, lejos del resto, que no toca a ninguna otra.
    """
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    filas = [
        {
            "cod_unidad": f"{i}-{j}",
            "nom_unidad": f"celda {i}-{j}",
            "n_estudiantes": 100,
            "valor": float(valor(i, j)),
            "geometry": box(j, i, j + 1, i + 1),
        }
        for i in range(lado)
        for j in range(lado)
    ]
    if isla is not None:
        filas.append(
            {
                "cod_unidad": "isla",
                "nom_unidad": "celda suelta",
                "n_estudiantes": 100,
                "valor": float(isla),
                "geometry": box(50, 50, 51, 51),
            }
        )
    return gpd.GeoDataFrame(filas, crs="EPSG:4326")


def test_contiguidad_queen_cuenta_las_diagonales():
    """Queen: en una cuadrícula 3x3 el centro tiene 8 vecinos y la esquina 3."""
    vecindad = construir_vecindad(_cuadricula(3, lambda i, j: i * 3 + j), "valor")

    assert vecindad.n_unidades == 9
    assert vecindad.w.cardinalities[4] == 8
    assert vecindad.w.cardinalities[0] == 3
    assert vecindad.n_islas == 0


def test_no_se_reproyecta_nada():
    """El cálculo trabaja en EPSG:4326: la capa que devuelve conserva el CRS."""
    capa = _cuadricula(4, lambda i, j: j)
    vecindad = construir_vecindad(capa, "valor")

    assert capa.crs.to_string() == "EPSG:4326"
    assert vecindad.tabla.crs.to_string() == "EPSG:4326"


def test_moran_detecta_agrupamiento():
    """Cuadrícula partida en dos mitades: autocorrelación positiva y clara."""
    mitades = _cuadricula(6, lambda i, j: 0 if j < 3 else 100)
    resultado = moran_global(mitades, "valor")

    assert resultado.i > 0.5
    assert resultado.significativo
    assert "se agrupan en el territorio" in resultado.interpretacion
    assert "causas" in resultado.interpretacion


def test_moran_detecta_alternancia():
    """Franjas alternadas: autocorrelación negativa y significativa."""
    franjas = _cuadricula(6, lambda i, j: 100 if j % 2 else 0)
    resultado = moran_global(franjas, "valor")

    assert resultado.i < 0
    assert resultado.significativo
    assert "se alternan en el territorio" in resultado.interpretacion


def test_moran_no_ve_patron_donde_no_hay():
    """Valores sorteados al azar sobre la cuadrícula: p-valor no significativo."""
    sorteo = np.random.default_rng(7).normal(50, 10, (6, 6))
    resultado = moran_global(_cuadricula(6, lambda i, j: sorteo[i][j]), "valor")

    assert not resultado.significativo
    assert "no se distingue del azar" in resultado.interpretacion


def test_la_isla_se_excluye_y_queda_informada():
    """Una unidad sin vecinos sale del cálculo y aparece en el resultado."""
    con_isla = _cuadricula(3, lambda i, j: i * 3 + j, isla=99)
    vecindad = construir_vecindad(con_isla, "valor")

    assert vecindad.n_unidades == 9
    assert list(vecindad.islas["codigo"]) == ["isla"]
    assert "isla" not in set(vecindad.tabla["cod_unidad"])
    assert "sin vecinos (isla)" in set(vecindad.descartadas["motivo"])
    assert any("sin vecinos" in aviso for aviso in vecindad.advertencias)


def test_la_isla_se_puede_enganchar_al_vecino_mas_cercano():
    """Con `vecino_mas_cercano` la isla entra, con enlace recíproco y distancia."""
    con_isla = _cuadricula(3, lambda i, j: i * 3 + j, isla=99)
    vecindad = construir_vecindad(
        con_isla, "valor", tratamiento_islas="vecino_mas_cercano"
    )

    assert vecindad.n_unidades == 10
    assert len(vecindad.enlaces_agregados) == 1
    enlace = vecindad.enlaces_agregados.iloc[0]
    assert enlace["codigo_isla"] == "isla"
    assert enlace["distancia_km"] > 0
    posicion_isla = list(vecindad.tabla["cod_unidad"]).index("isla")
    vecino = vecindad.w.neighbors[posicion_isla][0]
    assert posicion_isla in vecindad.w.neighbors[vecino]


def test_tratamiento_islas_error_avisa_cuales_son():
    """Con `error` la función falla y nombra las unidades sin vecinos."""
    con_isla = _cuadricula(3, lambda i, j: i * 3 + j, isla=99)

    with pytest.raises(ValueError, match="isla"):
        construir_vecindad(con_isla, "valor", tratamiento_islas="error")


def test_tratamiento_islas_desconocido_da_error():
    """Un tratamiento que no existe falla temprano, no en silencio."""
    with pytest.raises(ValueError, match="tratamiento_islas"):
        construir_vecindad(_cuadricula(3, lambda i, j: j), "valor", tratamiento_islas="omitir")


def test_excluir_islas_no_genera_islas_nuevas():
    """Una sola pasada alcanza: la contigüidad es simétrica.

    Dos celdas sueltas que se tocan entre sí forman un componente aparte pero
    no son islas, y las islas verdaderas no son vecinas de nadie, así que
    sacarlas no deja a ninguna otra unidad sin vecinos.
    """
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    capa = _cuadricula(3, lambda i, j: i * 3 + j, isla=99)
    par = gpd.GeoDataFrame(
        [
            {
                "cod_unidad": f"par-{k}",
                "nom_unidad": f"par {k}",
                "n_estudiantes": 100,
                "valor": 10.0 * k,
                "geometry": box(20 + k, 20, 21 + k, 21),
            }
            for k in (0, 1)
        ],
        crs="EPSG:4326",
    )
    import pandas as pd

    capa = gpd.GeoDataFrame(
        pd.concat([capa, par], ignore_index=True), crs="EPSG:4326"
    )
    vecindad = construir_vecindad(capa, "valor")

    assert list(vecindad.islas["codigo"]) == ["isla"]
    assert vecindad.n_unidades == 11
    assert vecindad.n_componentes == 2
    assert any("componentes desconectados" in a for a in vecindad.advertencias)


# --------------------------------------------------------------------------- #
# Distancias geodésicas
# --------------------------------------------------------------------------- #


def test_distancia_geodesica_sobre_el_elipsoide():
    """La distancia se mide sobre WGS84, no tratando grados como kilómetros."""
    assert distancia_geodesica_km(0, 0, 0, 1) == pytest.approx(110.574, abs=0.01)
    assert distancia_geodesica_km(0, 0, 1, 0) == pytest.approx(111.319, abs=0.01)
    # Un grado de longitud mide la mitad a 60 grados de latitud: el error de
    # tratar grados como una medida constante es del orden del 100 %.
    assert distancia_geodesica_km(0, 60, 1, 60) == pytest.approx(55.799, abs=0.01)
    assert distancia_geodesica_km(
        -77.0428, -12.0464, -71.9675, -13.5319
    ) == pytest.approx(575.0, abs=1.0)


def test_distancia_geodesica_es_simetrica_y_nula_en_el_mismo_punto():
    """Propiedades mínimas de una distancia."""
    assert distancia_geodesica_km(-75, -10, -75, -10) == pytest.approx(0.0)
    ida = distancia_geodesica_km(-75, -10, -70, -15)
    vuelta = distancia_geodesica_km(-70, -15, -75, -10)
    assert ida == pytest.approx(vuelta)


# --------------------------------------------------------------------------- #
# Filtro de muestra mínima
# --------------------------------------------------------------------------- #


def test_filtrar_por_muestra_separa_y_explica():
    """Las unidades descartadas salen con el motivo, no desaparecen."""
    import pandas as pd

    tabla = pd.DataFrame(
        {
            "cod_unidad": ["a", "b", "c", "d"],
            "n_estudiantes": [100, 29, 30, 500],
            "pct_critico": [50.0, 80.0, 40.0, None],
        }
    )
    quedan, fuera = filtrar_por_muestra(tabla, "pct_critico", muestra_minima=30)

    assert list(quedan["cod_unidad"]) == ["a", "c"]
    assert set(fuera["cod_unidad"]) == {"b", "d"}
    assert "muestra menor que 30" in fuera.loc[fuera.cod_unidad == "b", "motivo"].iloc[0]
    assert "sin valor" in fuera.loc[fuera.cod_unidad == "d", "motivo"].iloc[0]


def test_la_muestra_minima_se_aplica_antes_de_la_contiguidad(ugel_matematica):
    """Una unidad descartada por ruidosa tampoco sirve de puente entre vecinas."""
    con_filtro = construir_vecindad(ugel_matematica, "pct_critico", muestra_minima=30)
    sin_filtro = construir_vecindad(ugel_matematica, "pct_critico", muestra_minima=0)

    assert con_filtro.n_unidades < sin_filtro.n_unidades
    assert con_filtro.muestra_minima == 30
    descartadas = con_filtro.descartadas["motivo"].str.contains("muestra menor").sum()
    assert descartadas == 14


# --------------------------------------------------------------------------- #
# El caso de referencia del proyecto
# --------------------------------------------------------------------------- #


def test_moran_de_las_ugel_en_matematica(vecindad_ugel):
    """Cifra publicada: el rezago en Matemática se agrupa por UGEL.

    4.° de primaria, Matemática, porcentaje en niveles críticos, nivel UGEL,
    muestra mínima 30, contigüidad Queen, 999 permutaciones, semilla 42.
    """
    resultado = moran_global(vecindad_ugel, "pct_critico")

    assert resultado.n_unidades == 205
    assert resultado.i == pytest.approx(0.5501, abs=0.0005)
    assert resultado.p_valor == pytest.approx(0.001, abs=1e-9)
    assert resultado.significativo
    assert resultado.valor_esperado == pytest.approx(-1 / (205 - 1), abs=1e-6)
    assert resultado.z > 10


def test_las_tres_ugel_sin_vecinos(vecindad_ugel):
    """Las islas de la capa de UGEL son reales y están identificadas.

    La capa de UGEL se arma disolviendo los distritos que tienen UGEL asignada,
    de modo que no cubre el territorio de forma continua.
    """
    assert vecindad_ugel.n_islas == 3
    assert set(vecindad_ugel.islas["codigo"]) == {"040006", "040009", "230003"}
    assert set(vecindad_ugel.islas["nombre"]) == {"Caylloma", "La Unión", "Tarata"}


def test_enganchar_las_islas_mueve_poco_el_indice(ugel_matematica):
    """El tratamiento de islas cambia el índice, y conviene poder compararlo."""
    excluidas = moran_global(ugel_matematica, "pct_critico")
    enganchadas = moran_global(
        ugel_matematica, "pct_critico", tratamiento_islas="vecino_mas_cercano"
    )

    assert enganchadas.n_unidades == excluidas.n_unidades + 3
    assert enganchadas.i == pytest.approx(excluidas.i, abs=0.02)
    assert enganchadas.significativo
    assert len(enganchadas.vecindad.enlaces_agregados) == 3
    assert (enganchadas.vecindad.enlaces_agregados["distancia_km"] > 10).all()


def test_lisa_clasifica_en_las_cinco_categorias(vecindad_ugel):
    """Cifras publicadas del reparto LISA, y las cinco categorías siempre presentes."""
    resultado = lisa(vecindad_ugel, "pct_critico")
    conteo = resultado.conteo.set_index("clave")["n_unidades"].to_dict()

    assert len(resultado.conteo) == 5
    assert set(resultado.conteo["categoria"]) == set(CATEGORIAS_LISA.values())
    assert conteo == {"ns": 146, "aa": 28, "ba": 3, "bb": 27, "ab": 1}
    assert sum(conteo.values()) == resultado.vecindad.n_unidades
    assert resultado.n_significativas == 59


def test_las_ugel_de_loreto_son_conglomerado_de_rezago_alto(vecindad_ugel):
    """Las UGEL amazónicas de mayor rezago caen en alto rodeado de alto."""
    resultado = lisa(vecindad_ugel, "pct_critico")
    alto_alto = set(resultado.unidades_de("aa")["codigo"])

    # Nauta, Caballococha, Contamana y Requena, todas de la DRE Loreto.
    assert {"160004", "160005", "160007", "160006"} <= alto_alto
    assert (resultado.unidades_de("aa")["p_valor"] <= 0.05).all()
    assert (resultado.unidades_de("aa")["valor"] > resultado.tabla["valor"].mean()).all()


def test_sin_significancia_la_unidad_va_a_sin_patron(vecindad_ugel):
    """El cuadrante solo cuenta si el p-valor lo respalda."""
    exigente = lisa(vecindad_ugel, "pct_critico", nivel_significancia=0.001)
    laxo = lisa(vecindad_ugel, "pct_critico", nivel_significancia=0.05)

    assert exigente.n_significativas < laxo.n_significativas
    no_significativas = exigente.tabla[exigente.tabla["p_valor"] > 0.001]
    assert (no_significativas["cod_categoria"] == 0).all()
    assert (no_significativas["categoria"] == CATEGORIAS_LISA[0]).all()
    # El cuadrante crudo se conserva, para poder revisar la decisión.
    assert (no_significativas["cuadrante"] > 0).all()


def test_el_rezago_espacial_es_el_promedio_de_las_vecinas(vecindad_ugel):
    """Comprobación directa de `rezago_z` sobre una unidad cualquiera."""
    resultado = lisa(vecindad_ugel, "pct_critico")
    fila = 0
    vecinas = vecindad_ugel.w.neighbors[fila]
    esperado = resultado.tabla["valor_z"].iloc[vecinas].mean()

    assert resultado.tabla["rezago_z"].iloc[fila] == pytest.approx(esperado, abs=1e-9)
    assert resultado.tabla["n_vecinos"].iloc[fila] == len(vecinas)


def test_el_analisis_conjunto_comparte_la_matriz(ugel_matematica):
    """`analizar_autocorrelacion` da lo mismo que las dos funciones por separado."""
    conjunto = analizar_autocorrelacion(ugel_matematica, "pct_critico")

    assert conjunto.global_.vecindad is conjunto.vecindad
    assert conjunto.local.vecindad is conjunto.vecindad
    assert conjunto.global_.i == pytest.approx(
        moran_global(ugel_matematica, "pct_critico").i
    )


def test_los_distritos_tambien_se_agrupan(distritos_matematica):
    """A nivel distrital el patrón se sostiene, con más unidades sin vecinos.

    El filtro de muestra mínima deja fuera a casi la mitad de los distritos, y
    eso parte el territorio: 29 distritos quedan sin ninguna vecina calculable.
    """
    capa, _ = distritos_matematica
    resultado = analizar_autocorrelacion(capa, "pct_critico")

    assert resultado.global_.i > 0.5
    assert resultado.global_.significativo
    assert resultado.vecindad.n_islas == 29
    assert resultado.vecindad.n_componentes > 1
    assert resultado.local.conteo["n_unidades"].sum() == resultado.vecindad.n_unidades


# --------------------------------------------------------------------------- #
# Reproducibilidad
# --------------------------------------------------------------------------- #


def test_la_misma_semilla_da_el_mismo_p_valor(vecindad_ugel):
    """Los p-valores por permutaciones son reproducibles."""
    uno = moran_global(vecindad_ugel, "pct_critico", semilla=99)
    otro = moran_global(vecindad_ugel, "pct_critico", semilla=99)

    assert uno.p_valor == otro.p_valor
    assert uno.z == pytest.approx(otro.z)


def test_el_calculo_no_altera_el_azar_del_programa(vecindad_ugel):
    """Fijar la semilla no deja alterado el generador global de NumPy."""
    np.random.seed(123)
    antes = np.random.get_state()
    moran_global(vecindad_ugel, "pct_critico", semilla=7)
    despues = np.random.get_state()

    assert antes[0] == despues[0]
    assert np.array_equal(antes[1], despues[1])
    assert antes[2] == despues[2]


# --------------------------------------------------------------------------- #
# Unidades cartográficas combinadas y unión con geometría
# --------------------------------------------------------------------------- #


def test_mazamari_y_pangoa_se_suman_en_la_unidad_combinada():
    """El límite está en litigio: la cartografía publica un solo polígono.

    Los conteos se suman y los porcentajes se recomponen ponderando por
    población estimada, de modo que el porcentaje combinado sigue siendo la
    población crítica sobre la población estimada.
    """
    datos = _resultados("distrito")
    origen = datos[datos["cod_unidad"].isin(["120604", "120606"])]
    assert len(origen) == 2

    combinado = combinar_unidades_cartograficas(datos)
    fila = combinado[combinado["cod_unidad"] == "120699"]

    assert len(fila) == 1
    fila = fila.iloc[0]
    assert "120604" not in set(combinado["cod_unidad"])
    assert "120606" not in set(combinado["cod_unidad"])
    assert fila["nom_unidad"] == "Mazamari - Pangoa"
    assert fila["n_estudiantes"] == origen["n_estudiantes"].sum()
    assert fila["poblacion_estimada"] == pytest.approx(
        origen["poblacion_estimada"].sum()
    )
    assert fila["poblacion_critica"] == pytest.approx(origen["poblacion_critica"].sum())
    # El almacén guarda las poblaciones redondeadas a un decimal y los
    # porcentajes sin redondear, así que la identidad se cumple con la holgura
    # de ese redondeo, no al bit. La misma diferencia existe en las filas sin
    # combinar.
    assert fila["pct_critico"] == pytest.approx(
        100 * fila["poblacion_critica"] / fila["poblacion_estimada"], abs=0.01
    )
    assert fila["pct_critico"] == pytest.approx(
        (origen["pct_critico"] * origen["poblacion_estimada"]).sum()
        / origen["poblacion_estimada"].sum(),
        abs=1e-9,
    )
    assert bool(fila["muestra_suficiente"]) is True
    assert len(combinado) == len(datos) - 1


def test_combinar_no_toca_las_demas_unidades():
    """Las unidades que no están en la equivalencia pasan intactas."""
    datos = _resultados("distrito")
    combinado = combinar_unidades_cartograficas(datos)
    antes = datos[datos["cod_unidad"] == "150101"].iloc[0]
    despues = combinado[combinado["cod_unidad"] == "150101"].iloc[0]

    assert despues["pct_critico"] == antes["pct_critico"]
    assert despues["n_estudiantes"] == antes["n_estudiantes"]
    assert (
        combinado["poblacion_estimada"].sum()
        == pytest.approx(datos["poblacion_estimada"].sum())
    )


def test_sin_combinar_los_dos_distritos_quedan_sin_geometria():
    """Es la razón de ser de la equivalencia: sin ella los dos se pierden."""
    datos = _resultados("distrito")
    capa = _capa("distritos.geojson")

    _, sin_combinar = unir_con_geometria(capa, datos, "ubigeo")
    sueltos = sin_combinar[sin_combinar["situacion"] == "dato sin geometría"]
    assert {"120604", "120606"} <= set(sueltos["codigo"])

    unida, con_combinar = unir_con_geometria(
        capa, datos, "ubigeo", combinar_cartograficas=True
    )
    sueltos = con_combinar[con_combinar["situacion"] == "dato sin geometría"]
    assert not {"120604", "120606"} & set(sueltos["codigo"])
    assert "120699" in set(unida["ubigeo"])


def test_los_distritos_sin_geometria_quedan_listados(distritos_matematica):
    """Los 10 distritos creados después de la cartografía se informan, no se ocultan.

    Son distritos sin polígono propio: la pérdida es cartográfica y sus
    estudiantes siguen contando en los agregados por UGEL, DRE y nacional.
    """
    _, diagnostico = distritos_matematica
    sin_geometria = set(
        diagnostico.loc[diagnostico["situacion"] == "dato sin geometría", "codigo"]
    )
    conocidos = {
        "050512", "080915", "080917", "080918", "090724",
        "090725", "180107", "221006", "250306", "250307",
    }

    assert sin_geometria <= conocidos
    assert len(sin_geometria) >= 9


# --------------------------------------------------------------------------- #
# Contrato de diseño
# --------------------------------------------------------------------------- #


def test_el_modulo_no_abre_la_base_ni_lee_archivos():
    """Funciones puras sobre DataFrames: la carga es de otra capa."""
    fuente = inspect.getsource(espacial)

    assert "import duckdb" not in fuente
    assert "read_file" not in fuente
    assert "read_parquet" not in fuente
    assert "open(" not in fuente


def test_errores_claros_cuando_falta_la_columna(ugel_matematica):
    """Pedir una columna que no está falla con el nombre de la columna."""
    with pytest.raises(KeyError, match="pct_inventado"):
        construir_vecindad(ugel_matematica, "pct_inventado")
    with pytest.raises(KeyError, match="cod_inventado"):
        construir_vecindad(ugel_matematica, "pct_critico", columna_codigo="cod_inventado")


def test_pocas_unidades_no_se_calculan():
    """Con menos de tres unidades no hay autocorrelación que estimar."""
    capa = _cuadricula(1, lambda i, j: 10)

    with pytest.raises(ValueError, match="menos de tres"):
        construir_vecindad(capa, "valor")


def test_el_motivo_del_descarte_no_se_repite():
    """Las dos asignaciones encadenadas alcanzaban dos veces a la misma fila.

    Una unidad con muestra suficiente y sin valor salía con el motivo escrito dos veces.
    """
    tabla = pd.DataFrame({
        "cod_unidad": ["a", "b", "c", "d"],
        "n_estudiantes": [100, 5, 100, 5],
        "pct_critico": [10.0, 20.0, None, None],
    })
    _, fuera = filtrar_por_muestra(tabla, "pct_critico", muestra_minima=30)
    motivos = dict(zip(fuera["cod_unidad"], fuera["motivo"]))

    assert motivos["c"] == "sin valor en 'pct_critico'"
    assert motivos["b"] == "muestra menor que 30 estudiantes evaluados"
    assert motivos["d"] == (
        "muestra menor que 30 estudiantes evaluados; sin valor en 'pct_critico'"
    )
    for motivo in motivos.values():
        assert motivo.count("sin valor") <= 1


def test_el_p_por_permutaciones_se_escribe_como_tope():
    """Con 999 permutaciones el mínimo alcanzable es 0,001, no una medición.

    Los quince cortes reales del almacén devuelven exactamente ese tope, así que
    escribirlo como igualdad afirma una precisión que la prueba no tiene.
    """
    assert formato_p(0.001, 999) == "p ≤ 0,001"
    assert formato_p(0.0001, 9999) == "p ≤ 0,0001"
    assert formato_p(0.023, 999) == "p = 0,023"
    # Coma decimal, que es como se escriben las cifras en esta plataforma.
    assert "." not in formato_p(0.047, 999)
