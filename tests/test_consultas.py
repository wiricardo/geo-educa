"""Pruebas del validador de consultas del asistente.

La prueba que más importa es la primera: una agregación sin peso sobre los microdatos
no falla, devuelve una cifra equivocada con total naturalidad. Si el validador deja
pasar eso, el asistente mentirá con confianza.
"""

from __future__ import annotations

import pandas as pd
import pytest

from geoeduca import almacen
from geoeduca.consultas import (
    ConsultaRechazada,
    ejecutar,
    extraer_sql,
    tabla_a_texto,
    validar,
)


def test_rechaza_agregacion_sin_peso():
    """El error silencioso: promedia los microdatos ignorando el diseño muestral."""
    v = validar("select avg(medida500) from hechos_estudiante_area where grado = '4P'")
    assert not v
    assert "peso" in v.motivo
    # El rechazo tiene que enseñar a corregirlo, no solo negarse.
    assert "SUM(peso" in v.sugerencia


def test_acepta_agregacion_ponderada():
    v = validar(
        "select sum(peso * medida500) / sum(peso) from hechos_estudiante_area "
        "where grado = '4P' and cod_area = 'L'"
    )
    assert v


def test_acepta_los_agregados_ya_ponderados():
    """Sobre resultados_geograficos no hace falta ponderar: ya viene hecho."""
    assert validar(
        "select nom_unidad, pct_critico from resultados_geograficos "
        "where nivel_geografico = 'ugel'"
    )


def test_count_sobre_microdatos_es_legitimo():
    """Contar filas de la muestra es correcto y no necesita peso, pero se advierte."""
    v = validar("select count(*) from hechos_estudiante_area where grado = '4P'")
    assert v
    assert any("muestra" in a for a in v.advertencias)


@pytest.mark.parametrize(
    "sql",
    [
        "drop table hechos_estudiante_area",
        "insert into brechas values (1)",
        "update brechas set grado = '4P'",
        "delete from brechas",
        "create table t as select 1",
    ],
)
def test_rechaza_escrituras(sql):
    v = validar(sql)
    assert not v
    assert "lectura" in v.motivo.lower()


def test_rechaza_tablas_que_no_existen():
    v = validar("select * from usuarios")
    assert not v
    assert "usuarios" in v.motivo


def test_rechaza_lectura_de_archivos():
    """Leer del disco se rechaza, y por ser una función de tabla.

    Antes se rechazaba por el nombre de la función, con una lista escrita a mano a la
    que le faltaban `read_ndjson`, `sqlite_scan` y `duckdb_tables`, entre otras. Ahora
    se rechaza toda función de tabla, que además cierra `query_table`, con la que se
    podía leer el microdato esquivando la regla del peso.
    """
    for sql in (
        "select * from read_csv('/etc/passwd')",
        "select * from read_ndjson('/etc/hosts')",
        "select * from sqlite_scan('/tmp/a.db','t')",
        "select * from duckdb_settings()",
        "select avg(medida500) from query_table('hechos_estudiante_area')",
    ):
        v = validar(sql)
        assert not v, sql
        assert "función de tabla" in v.motivo


def test_rechaza_varias_instrucciones():
    assert not validar("select 1; drop table brechas")


def test_un_comentario_no_cuenta_como_usar_el_peso():
    """Mencionar la palabra en un comentario no pondera nada.

    Se valida sobre el árbol sintáctico, no sobre el texto, así que los comentarios y
    los alias no sirven para esquivar la regla.
    """
    assert not validar(
        "select /* peso */ avg(medida500) from hechos_estudiante_area"
    )


def test_un_alias_tampoco_cuenta_como_usar_el_peso():
    assert not validar(
        'select avg(medida500) as "promedio con peso" from hechos_estudiante_area'
    )


def test_la_consulta_correcta_devuelve_la_cifra_oficial():
    """Prueba de extremo a extremo: ponderar bien reproduce el dato publicado."""
    try:
        resultado = ejecutar(
            "select round(sum(peso * medida500) / sum(peso), 1) as medida "
            "from hechos_estudiante_area where grado = '4P' and cod_area = 'L'"
        )
    except almacen.AlmacenNoEncontrado as exc:
        pytest.skip(str(exc))

    assert resultado.tabla.iloc[0, 0] == pytest.approx(490.1, abs=0.05)


def test_ejecutar_lanza_excepcion_con_la_explicacion():
    try:
        ejecutar("select avg(medida500) from hechos_estudiante_area")
    except ConsultaRechazada as exc:
        assert "peso" in str(exc)
    except almacen.AlmacenNoEncontrado as exc:
        pytest.skip(str(exc))
    else:
        pytest.fail("Tendría que haberse rechazado.")


def test_recorta_resultados_muy_largos():
    try:
        resultado = ejecutar(
            "select * from hechos_estudiante_area limit 2000", limite=10
        )
    except almacen.AlmacenNoEncontrado as exc:
        pytest.skip(str(exc))

    assert len(resultado.tabla) == 10
    assert resultado.truncada
    assert resultado.filas_totales > 10


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("```sql\nselect 1\n```", "select 1"),
        ("```\nselect 1\n```", "select 1"),
        ("Aquí tienes:\nselect 1 from t", "select 1 from t"),
        ("with a as (select 1) select * from a", "with a as (select 1) select * from a"),
        ("No hay consulta en este texto.", None),
    ],
)
def test_extraer_sql_tolera_los_formatos_del_modelo(texto, esperado):
    """Los modelos devuelven el SQL de tres formas distintas según el día."""
    assert extraer_sql(texto) == esperado


def test_consulta_vacia():
    assert not validar("")
    assert not validar("   ")


# --------------------------------------------------------------------------------------
# Regresiones: ocho formas de agregar sin ponderar que pasaban
# --------------------------------------------------------------------------------------

_MICRO_4P_L = "from hechos_estudiante_area where grado = '4P' and cod_area = 'L'"


@pytest.mark.parametrize(
    "caso, sql",
    [
        ("peso pedido en otra columna", f"select avg(medida500) m, sum(peso) p {_MICRO_4P_L}"),
        ("peso solo en el WHERE", f"select avg(medida500) m {_MICRO_4P_L} and peso > 0"),
        ("peso en el ORDER BY", f"select avg(medida500) m {_MICRO_4P_L} order by max(peso)"),
        ("peso en el GROUP BY", f"select avg(medida500) {_MICRO_4P_L} group by peso > 0"),
        (
            "peso en una subconsulta",
            "select avg(medida500) from (select medida500, peso "
            f"{_MICRO_4P_L})",
        ),
        ("agregación de ventana", f"select distinct avg(medida500) over () {_MICRO_4P_L}"),
        (
            "ventana con cociente",
            f"select distinct sum(medida500) over () / count(*) over () {_MICRO_4P_L}",
        ),
        ("alias favg", f"select favg(medida500) {_MICRO_4P_L}"),
        ("alias fsum", f"select fsum(medida500) / count(*) {_MICRO_4P_L}"),
        ("macro geomean", f"select geomean(medida500) {_MICRO_4P_L}"),
        ("mad", f"select mad(medida500) {_MICRO_4P_L}"),
        ("reservoir_quantile", f"select reservoir_quantile(medida500, 0.5) {_MICRO_4P_L}"),
        ("list_aggregate", f"select list_aggregate(list(medida500), 'avg') {_MICRO_4P_L}"),
    ],
)
def test_no_hay_forma_de_agregar_el_microdato_sin_el_peso(caso, sql):
    """El peso tiene que estar dentro de la agregación, no en cualquier parte.

    Todas estas devolvían 486,2610 donde la cifra correcta es 490,1364, que es la
    diferencia exacta que este módulo existe para evitar. Pasaban porque se buscaba la
    columna `peso` en todo el árbol, porque la lista de agregaciones estaba escrita a
    mano, y porque una agregación con OVER se serializa como WINDOW y no como FUNCTION.
    """
    assert not validar(sql), caso


def test_una_proporcion_contando_filas_se_rechaza():
    """Es la forma natural de pedirla y da 30,6 % donde la oficial es 32,7 %."""
    for sql in (
        f"select 100.0 * count(*) filter (where es_satisfactorio) / count(*) {_MICRO_4P_L}",
        f"select 100.0 * count(case when es_satisfactorio then 1 end) / count(*) {_MICRO_4P_L}",
    ):
        v = validar(sql)
        assert not v
        assert "30,6 %" in v.sugerencia


def test_agregar_el_microdato_sin_fijar_grado_y_area_se_rechaza():
    """El hecho trae una fila por estudiante y área, cada una con el peso de la suya.

    Sin fijar las dos, SUM(peso) da 1 721 256 donde la población de 2.° de secundaria
    es 573 752: el error de partición es mayor que el de ponderación.
    """
    assert not validar("select sum(peso) from hechos_estudiante_area where grado = '2S'")
    assert not validar("select sum(peso * medida500) / sum(peso) from hechos_estudiante_area")
    assert validar(
        "select grado, cod_area, sum(peso) from hechos_estudiante_area group by 1, 2"
    )


def test_promediar_porcentajes_entre_unidades_se_rechaza():
    """Cada fila viene ponderada; promediarlas entre sí no.

    El promedio simple de `pct_satisfactorio` por departamento da 30,4 % donde el
    nacional es 32,7 %.
    """
    v = validar(
        "select avg(pct_satisfactorio) from resultados_geograficos "
        "where nivel_geografico = 'departamento' and grado = '4P' and cod_area = 'L'"
    )
    assert not v
    assert "poblacion_estimada" in v.sugerencia
    # Sumar poblaciones entre unidades sí es correcto.
    assert validar(
        "select sum(poblacion_critica) from resultados_geograficos "
        "where nivel_geografico = 'departamento' and grado = '4P' and cod_area = 'L'"
    )


def test_summarize_y_describe_se_rechazan():
    """Entregan el promedio sin ponderar ya etiquetado como `avg`, y sin funciones."""
    assert not validar(f"summarize select medida500 {_MICRO_4P_L}")
    assert not validar("describe select 1 x")


def test_un_cte_correctamente_ponderado_se_acepta():
    """Se rechazaba con un motivo falso: que la tabla no existe.

    El alias de un CTE se serializa como tabla base, así que caía en el control de
    tablas desconocidas y el mensaje le mentía al modelo.
    """
    assert validar(
        "with t as (select peso, medida500 "
        f"{_MICRO_4P_L}) select sum(peso * medida500) / sum(peso) from t"
    )


def test_la_tabla_en_texto_no_necesita_tabulate():
    """`to_markdown` exige tabulate, que no está instalado."""
    tabla = pd.DataFrame({"unidad": ["LORETO"], "poblacion": [540704.0], "pct": [32.657]})
    texto = tabla_a_texto(tabla)
    assert "LORETO" in texto and "540704" in texto and "32.657" in texto
    assert "e+0" not in texto
