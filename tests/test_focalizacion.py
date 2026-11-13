"""Pruebas de la priorización de unidades para intervención.

Dos clases de prueba, como en `test_espacial.py`:

1. Sobre tablas construidas a mano, donde el comportamiento esperado se deduce
   de la definición: el índice combinado no puede premiar a una unidad que esté
   en el fondo de una de las dos dimensiones, no puede depender de la unidad de
   medida del alcance, y el orden no puede depender del orden en que llegaron
   las filas.
2. Sobre los datos del proyecto, que fijan el caso que la pantalla de
   focalización tiene que mostrar: las ocho UGEL priorizadas de 4.° de primaria
   en Matemática y la tensión entre intensidad y alcance en Yurimaguas.

El módulo recibe DataFrames: la carga vive acá.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from geoeduca import almacen, focalizacion
from geoeduca.focalizacion import (
    CRITERIOS,
    cobertura_acumulada,
    comparar_criterios,
    describir_tension,
    indice_combinado,
    ninos_alcanzados,
    priorizar,
)

RAIZ = Path(__file__).resolve().parents[1]
ALMACEN = RAIZ / "processed" / "geoeduca.duckdb"

# Caso de referencia del proyecto, el de la pantalla de focalización.
GRADO = "4P"
AREA = "M"
# Umbrales con los que la pantalla llega a las ocho UGEL: muestra suficiente,
# al menos 500 estudiantes estimados y al menos 70 % en niveles críticos.
UMBRALES = {"intensidad_minima": 70, "poblacion_minima": 500}


@pytest.fixture(scope="module")
def ugel_matematica():
    """Resultados de UGEL en Matemática de 4.° de primaria, sin filtrar."""
    duckdb = pytest.importorskip("duckdb")
    if not ALMACEN.exists():
        pytest.skip(f"No existe el almacén en {ALMACEN}.")
    con = duckdb.connect(str(ALMACEN), read_only=True)
    try:
        return con.execute(
            """
            SELECT * FROM resultados_geograficos
            WHERE nivel_geografico = 'ugel' AND grado = ? AND cod_area = ?
            """,
            [GRADO, AREA],
        ).df()
    finally:
        con.close()


@pytest.fixture(scope="module")
def ocho_ugel(ugel_matematica):
    """Las ocho UGEL priorizadas, ordenadas por alcance."""
    return priorizar(ugel_matematica, "alcance", **UMBRALES)


def _tabla(filas):
    """Tabla mínima con las columnas que el módulo espera."""
    return pd.DataFrame(
        filas,
        columns=[
            "cod_unidad",
            "nom_unidad",
            "n_estudiantes",
            "poblacion_estimada",
            "pct_critico",
            "poblacion_critica",
        ],
    )


# --------------------------------------------------------------------------- #
# El índice combinado
# --------------------------------------------------------------------------- #


def test_el_indice_combinado_exige_las_dos_dimensiones():
    """Estar en el fondo de una dimensión no se compensa con la otra.

    La media geométrica de los percentiles se va a cero si cualquiera de las
    dos posiciones es la última. Una media aritmética dejaría entrar a la
    unidad diminuta con rezago extremo, que es lo que hay que moderar.
    """
    intensidad = [95.0, 60.0, 30.0]
    alcance = [20.0, 1500.0, 5000.0]
    indice = indice_combinado(intensidad, alcance)

    # La unidad del medio está arriba en las dos dimensiones sin ser extrema en
    # ninguna, y por eso gana.
    assert indice[1] == max(indice)
    assert indice[0] < indice[1]
    assert indice[2] < indice[1]


def test_el_indice_combinado_no_depende_de_la_unidad_de_medida():
    """El percentil es invariante a la escala: medir en miles no cambia nada."""
    intensidad = [80.0, 55.0, 40.0, 70.0]
    alcance = [100.0, 3000.0, 8000.0, 900.0]

    original = indice_combinado(intensidad, alcance)
    en_miles = indice_combinado(intensidad, [a / 1000 for a in alcance])

    assert list(original) == pytest.approx(list(en_miles))


def test_el_indice_combinado_esta_entre_cero_y_uno(ugel_matematica):
    """El índice es una posición relativa, no una cantidad de estudiantes."""
    priorizacion = priorizar(ugel_matematica, "combinado")
    indice = priorizacion.universo["indice_combinado"]

    assert indice.min() > 0
    assert indice.max() <= 1


def test_el_criterio_combinado_no_es_el_de_alcance_con_otro_nombre(ugel_matematica):
    """La unidad más grande no se queda con el primer puesto del combinado.

    Es la razón de usar percentiles y no una normalización por mínimo y máximo:
    San Juan de Miraflores es la primera por alcance, con 8 218 estudiantes en
    niveles críticos, y baja al puesto 17 del combinado porque su intensidad
    está en la mitad de la tabla.
    """
    universo = priorizar(ugel_matematica, "combinado").universo.set_index("codigo")
    san_juan = universo.loc["150102"]
    yurimaguas = universo.loc["160002"]

    assert san_juan["pos_alcance"] == 1
    assert san_juan["pos_combinado"] == 17
    assert yurimaguas["pos_combinado"] == 2


def test_el_criterio_combinado_tampoco_premia_a_la_unidad_diminuta(ugel_matematica):
    """La UGEL con el rezago más extendido tiene 34 estudiantes: el combinado la baja.

    Intercultural Bilingüe Río Santiago tiene 94,4 % en niveles críticos, el
    porcentaje más alto del país, sobre 36 estudiantes estimados.
    """
    universo = priorizar(ugel_matematica, "combinado").universo.set_index("codigo")
    rio_santiago = universo.loc["010010"]

    assert rio_santiago["pos_intensidad"] == 1
    assert rio_santiago["pos_combinado"] > 100


# --------------------------------------------------------------------------- #
# La tensión entre intensidad y alcance
# --------------------------------------------------------------------------- #


def test_yurimaguas_es_octava_por_intensidad_y_primera_por_alcance(ocho_ugel):
    """El caso que la pantalla tiene que hacer visible.

    Alto Amazonas - Yurimaguas tiene el porcentaje de rezago más bajo de las
    ocho unidades priorizadas y la población estimada más alta, así que
    concentra más estudiantes en niveles críticos que cualquier otra.
    """
    comparacion = comparar_criterios(ocho_ugel).set_index("codigo")
    yurimaguas = comparacion.loc["160002"]

    assert yurimaguas["intensidad"] == pytest.approx(70.3234, abs=0.001)
    assert yurimaguas["alcance"] == pytest.approx(2387.0, abs=0.1)
    assert yurimaguas["intensidad"] == comparacion["intensidad"].min()
    assert yurimaguas["alcance"] == comparacion["alcance"].max()
    assert yurimaguas["pos_intensidad"] == 8
    assert yurimaguas["pos_alcance"] == 1
    assert yurimaguas["desacuerdo"] == 7


def test_el_criterio_elegido_cambia_quien_va_primero(ugel_matematica):
    """Los tres criterios dan tres primeros puestos distintos."""
    primeros = {
        criterio: priorizar(ugel_matematica, criterio, **UMBRALES).tabla.iloc[0]["codigo"]
        for criterio in CRITERIOS
    }

    assert primeros["alcance"] == "160002"  # Yurimaguas
    assert primeros["intensidad"] == "160004"  # Nauta
    assert primeros["intensidad"] != primeros["alcance"]
    assert len(set(primeros.values())) >= 2


def test_describir_tension_nombra_los_dos_ordenes(ocho_ugel):
    """El texto describe el desacuerdo sin decir cuál criterio es el correcto."""
    texto = describir_tension(ocho_ugel)

    assert "Yurimaguas" in texto
    assert "8.ª por intensidad" in texto
    assert "1.ª por alcance" in texto
    assert "70,3 %" in texto
    # Las dos lecturas quedan nombradas, que es lo que hace del texto una descripción
    # y no una recomendación. Antes se comprobaba que apareciera la palabra
    # «preguntas», que era un rastro de una redacción concreta y no de la propiedad.
    assert "más extendido" in texto
    assert "más estudiantes" in texto
    assert not any(p in texto.lower() for p in ("mejor", "conviene", "recomend"))
    assert "\u2014" not in texto  # la raya larga está prohibida en el proyecto


def test_comparar_criterios_recalcula_dentro_del_conjunto(ugel_matematica, ocho_ugel):
    """Las posiciones del universo y las del conjunto corto no son las mismas.

    En el universo de 208 UGEL, Yurimaguas es la décima por intensidad; entre
    las ocho seleccionadas es la octava. Las dos cifras son correctas y
    responden a conjuntos distintos.
    """
    en_el_universo = ocho_ugel.tabla.set_index("codigo").loc["160002"]
    en_las_ocho = comparar_criterios(ocho_ugel).set_index("codigo").loc["160002"]

    assert en_el_universo["pos_intensidad"] == 10
    assert en_el_universo["pos_alcance"] == 14
    assert en_las_ocho["pos_intensidad"] == 8
    assert en_las_ocho["pos_alcance"] == 1


def test_los_umbrales_no_mueven_las_posiciones_del_universo(ugel_matematica):
    """Los umbrales de política seleccionan, no reordenan.

    El índice y las posiciones se calculan sobre el universo con muestra
    suficiente, antes de aplicar umbrales, para que la magnitud se mida contra
    el país y no contra la lista corta.
    """
    sin_umbrales = priorizar(ugel_matematica, "combinado")
    con_umbrales = priorizar(ugel_matematica, "combinado", **UMBRALES)

    columnas = ["pos_intensidad", "pos_alcance", "pos_combinado", "indice_combinado"]
    de_todos = sin_umbrales.universo.set_index("codigo")[columnas]
    de_los_ocho = con_umbrales.tabla.set_index("codigo")[columnas]

    pd.testing.assert_frame_equal(
        de_los_ocho.sort_index(),
        de_todos.loc[de_los_ocho.index].sort_index(),
        check_like=True,
    )


# --------------------------------------------------------------------------- #
# Las ocho UGEL y la cobertura acumulada
# --------------------------------------------------------------------------- #


def test_las_ocho_ugel_priorizadas(ocho_ugel):
    """Cifra publicada: ocho UGEL, seis de Loreto, y cuántos estudiantes reúnen."""
    assert ocho_ugel.n_unidades == 8
    assert ocho_ugel.n_universo == 208
    assert (ocho_ugel.tabla["ambito"] == "Loreto").sum() == 6
    assert ocho_ugel.alcance_total == pytest.approx(8812.7, abs=0.1)
    assert set(ocho_ugel.tabla["codigo"]) == {
        "160002", "160004", "160005", "160006",
        "160007", "250002", "160003", "200012",
    }


def test_la_cobertura_acumulada_crece_y_cierra(ocho_ugel):
    """Una fila por N, acumulados monótonos y el último igual al total."""
    cobertura = ocho_ugel.cobertura()

    assert list(cobertura["n_unidades"]) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert cobertura["acum_criticos"].is_monotonic_increasing
    assert cobertura["acum_poblacion"].is_monotonic_increasing
    assert cobertura["acum_criticos"].iloc[-1] == pytest.approx(
        ocho_ugel.alcance_total, abs=1e-6
    )
    assert cobertura["acum_criticos"].iloc[0] == pytest.approx(2387.0, abs=0.1)
    assert (cobertura["acum_criticos"] <= cobertura["acum_poblacion"]).all()


def test_la_cobertura_distingue_criticos_de_atendidos(ocho_ugel):
    """Las tres cifras de tamaño no son lo mismo, y la tabla las separa."""
    cobertura = ocho_ugel.cobertura()
    fila = cobertura.iloc[-1]

    assert fila["acum_criticos"] == pytest.approx(8812.7, abs=0.1)
    assert fila["acum_poblacion"] == pytest.approx(11426.6, abs=0.1)
    assert fila["pct_criticos_en_lo_atendido"] == pytest.approx(
        100 * fila["acum_criticos"] / fila["acum_poblacion"], abs=1e-9
    )
    # Las ocho UGEL reúnen alrededor del 5 % de los estudiantes en niveles críticos
    # del universo evaluado: la focalización concentra, no resuelve.
    assert 4.0 < fila["pct_cobertura"] < 6.0


def test_la_cobertura_admite_un_total_de_referencia(ocho_ugel):
    """Con el total nacional del grado y área, la cobertura es sobre el país."""
    nacional = 167102.5
    cobertura = ocho_ugel.cobertura(total_referencia=nacional)

    assert cobertura["pct_cobertura"].iloc[-1] == pytest.approx(
        100 * ocho_ugel.alcance_total / nacional, abs=1e-9
    )
    assert cobertura["pct_cobertura"].iloc[-1] < ocho_ugel.cobertura()["pct_cobertura"].iloc[-1]


def test_ninos_alcanzados_en_las_primeras_n(ocho_ugel):
    """El atajo de la tarjeta de resumen coincide con el acumulado."""
    cobertura = ocho_ugel.cobertura()

    assert ninos_alcanzados(ocho_ugel, 1) == pytest.approx(2387.0, abs=0.1)
    assert ninos_alcanzados(ocho_ugel, 3) == pytest.approx(
        cobertura["acum_criticos"].iloc[2], abs=1e-6
    )
    assert ninos_alcanzados(ocho_ugel, 99) == pytest.approx(ocho_ugel.alcance_total)
    with pytest.raises(ValueError):
        ninos_alcanzados(ocho_ugel, 0)


def test_el_recorte_top_no_cambia_el_orden(ugel_matematica):
    """`top` corta la lista, no la reordena, y deja constancia del recorte."""
    completa = priorizar(ugel_matematica, "combinado")
    recortada = priorizar(ugel_matematica, "combinado", top=5)

    assert recortada.n_unidades == 5
    assert list(recortada.tabla["codigo"]) == list(completa.tabla["codigo"].head(5))
    assert (
        recortada.descartadas["motivo"]
        .str.contains("fuera de las primeras 5")
        .sum()
        == completa.n_unidades - 5
    )


# --------------------------------------------------------------------------- #
# Filtros, descartes y determinismo
# --------------------------------------------------------------------------- #


def test_la_muestra_minima_descarta_y_deja_el_motivo(ugel_matematica):
    """14 de las 222 UGEL no llegan a 30 estudiantes evaluados."""
    priorizacion = priorizar(ugel_matematica, "alcance")
    por_muestra = priorizacion.descartadas[
        priorizacion.descartadas["motivo"].str.contains("muestra menor")
    ]

    assert priorizacion.n_universo == 208
    assert len(por_muestra) == 14
    assert (por_muestra["muestra"] < 30).all()
    # Sin el filtro, esas unidades entran: el umbral es una decisión explícita.
    assert priorizar(ugel_matematica, "alcance", muestra_minima=0).n_universo == 222


def test_los_umbrales_de_politica_quedan_registrados(ocho_ugel):
    """La priorización dice con qué umbrales se armó."""
    assert ocho_ugel.umbrales["intensidad_minima"] == 70
    assert ocho_ugel.umbrales["poblacion_minima"] == 500
    assert ocho_ugel.umbrales["muestra_minima"] == 30
    assert "intensidad_minima = 70" in ocho_ugel.resumen()
    assert "8 unidades seleccionadas de 208" in ocho_ugel.resumen()


def test_cada_unidad_descartada_tiene_un_motivo(ugel_matematica):
    """Nada se descarta en silencio: universo más descartes es el total."""
    priorizacion = priorizar(ugel_matematica, "alcance", **UMBRALES)
    motivos = set(priorizacion.descartadas["motivo"])

    assert len(priorizacion.descartadas) == len(ugel_matematica) - priorizacion.n_unidades
    assert priorizacion.descartadas["motivo"].notna().all()
    assert any("muestra menor" in m for m in motivos)
    assert any("intensidad menor" in m for m in motivos)
    assert any("población estimada menor" in m for m in motivos)


def test_el_orden_no_depende_del_orden_de_las_filas(ugel_matematica):
    """Desempate determinista: barajar la entrada no cambia la salida."""
    derecho = priorizar(ugel_matematica, "combinado", top=20)
    barajado = priorizar(
        ugel_matematica.sample(frac=1, random_state=11).reset_index(drop=True),
        "combinado",
        top=20,
    )

    assert list(derecho.tabla["codigo"]) == list(barajado.tabla["codigo"])


def test_los_empates_se_resuelven_siempre_igual():
    """Dos unidades con la misma intensidad se ordenan por alcance, y luego por código."""
    tabla = _tabla(
        [
            ["b", "Be", 100, 1000.0, 50.0, 500.0],
            ["a", "Alfa", 100, 1000.0, 50.0, 500.0],
            ["c", "Ce", 100, 2000.0, 50.0, 1000.0],
        ]
    )
    orden = list(priorizar(tabla, "intensidad", muestra_minima=0).tabla["codigo"])

    assert orden == ["c", "a", "b"]


def test_criterio_desconocido_da_error(ugel_matematica):
    """Un criterio que no existe falla con la lista de los válidos."""
    with pytest.raises(ValueError, match="Criterio desconocido"):
        priorizar(ugel_matematica, "por_departamento")


def test_tabla_sin_las_columnas_necesarias_da_error():
    """El error nombra las columnas que faltan."""
    tabla = pd.DataFrame({"cod_unidad": ["a"], "otra_cosa": [1]})

    with pytest.raises(KeyError, match="pct_critico"):
        priorizar(tabla, "intensidad")


def test_pedir_poblacion_minima_sin_la_columna_da_error():
    """No se filtra por una columna que la tabla no trae."""
    tabla = _tabla([["a", "Alfa", 100, 1000.0, 50.0, 500.0]]).drop(
        columns=["poblacion_estimada"]
    )

    with pytest.raises(KeyError, match="poblacion_estimada"):
        priorizar(tabla, "alcance", muestra_minima=0, poblacion_minima=500)


def test_sin_unidades_validas_da_error():
    """Si el filtro no deja nada, se dice, no se devuelve una tabla vacía."""
    tabla = _tabla([["a", "Alfa", 5, 50.0, 90.0, 45.0]])

    with pytest.raises(ValueError, match="muestra mínima"):
        priorizar(tabla, "alcance", muestra_minima=30)


def test_nombres_de_columna_configurables():
    """El módulo sirve para cualquier indicador, no solo para `pct_critico`."""
    tabla = pd.DataFrame(
        {
            "ubigeo": ["a", "b"],
            "distrito": ["Alfa", "Be"],
            "muestra": [100, 100],
            "pct_previo_inicio": [30.0, 10.0],
            "poblacion_previo_inicio": [300.0, 100.0],
        }
    )
    priorizacion = priorizar(
        tabla,
        "intensidad",
        columna_codigo="ubigeo",
        columna_nombre="distrito",
        columna_intensidad="pct_previo_inicio",
        columna_alcance="poblacion_previo_inicio",
        columna_muestra="muestra",
        columna_poblacion=None,
        columna_padre=None,
    )

    assert list(priorizacion.tabla["codigo"]) == ["a", "b"]
    assert priorizacion.tabla.iloc[0]["nombre"] == "Alfa"


# --------------------------------------------------------------------------- #
# Contrato de diseño
# --------------------------------------------------------------------------- #


def test_el_modulo_no_abre_la_base_ni_lee_archivos():
    """Funciones puras sobre DataFrames: la carga es de otra capa."""
    fuente = inspect.getsource(focalizacion)

    assert "import duckdb" not in fuente
    assert "read_file" not in fuente
    assert "open(" not in fuente


def test_el_modulo_no_necesita_geometria():
    """La priorización se calcula sin cargar las capas."""
    fuente = inspect.getsource(focalizacion)

    assert "geopandas" not in fuente
    assert "shapely" not in fuente


def test_cobertura_acumulada_pide_la_tabla_del_modulo():
    """Pasarle cualquier DataFrame falla con un mensaje que dice qué pasar."""
    with pytest.raises(KeyError, match="alcance"):
        cobertura_acumulada(pd.DataFrame({"codigo": ["a"], "otra": [1]}))


def test_comparar_criterios_no_pisa_el_indice_del_universo():
    """Ordenar por `indice_combinado` tiene que dar el mismo orden que `priorizar`.

    El índice combinado es un percentil, así que su valor depende del conjunto sobre el
    que se calcula. `comparar_criterios` necesita recalcularlo dentro del conjunto
    recibido para dar las posiciones relativas, pero si eso sobrescribiera la columna
    original, ordenar por ella invertiría el resultado: sobre las ocho UGEL priorizadas,
    Yurimaguas caía del primer puesto al séptimo.
    """
    from geoeduca import almacen
    from geoeduca.focalizacion import comparar_criterios, priorizar

    try:
        datos = almacen.resultados_geograficos("ugel", "4P", "M")
    except almacen.AlmacenNoEncontrado as exc:
        pytest.skip(str(exc))

    prioridad = priorizar(
        datos,
        criterio="combinado",
        muestra_minima=30,
        intensidad_minima=70,
        poblacion_minima=500,
    )
    comparacion = comparar_criterios(prioridad)

    assert "indice_combinado_local" in comparacion.columns
    orden_priorizar = prioridad.tabla["nombre"].tolist()
    orden_comparacion = (
        comparacion.sort_values("indice_combinado", ascending=False)["nombre"].tolist()
    )
    assert orden_priorizar == orden_comparacion

    # Y la tensión sigue a la vista: última por intensidad, primera por alcance.
    yurimaguas = comparacion[comparacion["nombre"].str.contains("Yurimaguas")].iloc[0]
    assert int(yurimaguas["pos_intensidad"]) == len(comparacion)
    assert int(yurimaguas["pos_alcance"]) == 1


def test_la_posicion_combinada_sale_del_indice_local():
    """`_posiciones` recibía la columna y no la usaba.

    Dentro de un conjunto ya seleccionado, el criterio combinado se ordena por el índice
    recalculado en ese conjunto, no por el del universo. Con el parámetro muerto, seis
    de las ocho unidades priorizadas quedaban en un puesto que no era el suyo y
    Yurimaguas aparecía primera donde el índice local la deja séptima.
    """
    datos = almacen.resultados_geograficos("ugel", "4P", "M")
    prioridad = focalizacion.priorizar(
        datos, criterio="combinado", intensidad_minima=70.0, poblacion_minima=500.0
    )
    comparacion = focalizacion.comparar_criterios(prioridad.tabla)

    orden_local = (
        comparacion.sort_values("indice_combinado_local", ascending=False)["nombre"]
        .tolist()
    )
    orden_posiciones = comparacion.sort_values("pos_combinado")["nombre"].tolist()
    assert orden_posiciones == orden_local

    yurimaguas = comparacion[comparacion["nombre"].str.contains("Yurimaguas")].iloc[0]
    assert yurimaguas["pos_intensidad"] == 8
    assert yurimaguas["pos_alcance"] == 1
    assert yurimaguas["pos_combinado"] == 7
