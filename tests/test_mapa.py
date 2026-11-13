"""Pruebas de la capa que alimenta el mapa.

Todas son regresiones. Lo que se verifica aquí es que lo que llega al
mapa sea lo que el mapa dice que es: que el polígono fusionado traiga la suma de los dos
distritos y no la de uno, que su código se pueda resolver al hacer clic, que la escala de
color no la muevan las unidades que el propio mapa declara sin información, y que la
leyenda no repita un rótulo ni esconda el máximo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
for ruta in (RAIZ / "src", RAIZ / "app"):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

from core.componentes import _cortes  # noqa: E402
from geoeduca import almacen  # noqa: E402

#: El polígono que la cartografía publica fusionado, y sus dos miembros.
FUSIONADO = "120699"
MIEMBROS = ("120604", "120606")


def _distrital(grado: str = "4P", area: str = "M"):
    return almacen.resultados_geograficos("distrito", grado, area)


@pytest.mark.parametrize("grado, area", [("4P", "L"), ("4P", "M"), ("2S", "L"), ("2S", "M")])
def test_el_poligono_fusionado_trae_la_suma_de_los_dos_distritos(grado, area):
    """Había dos implementaciones de la misma operación y solo una era correcta.

    La que usaba el mapa sumaba tres columnas y heredaba el resto de una de las dos
    filas, así que `n_escuelas` llegaba con el valor de uno solo: 8 en lugar de 26.
    """
    datos = _distrital(grado, area)
    capa = almacen.unir_con_geometria(datos, "distrito")
    fila = capa[capa["cod_unidad"] == FUSIONADO]
    assert len(fila) == 1
    fila = fila.iloc[0]

    partes = datos[datos["cod_unidad"].isin(MIEMBROS)]
    assert len(partes) == 2
    for columna in ("n_estudiantes", "n_escuelas", "poblacion_estimada",
                    "poblacion_critica", "poblacion_satisfactoria"):
        assert fila[columna] == pytest.approx(partes[columna].sum(), rel=1e-9), columna


def test_los_porcentajes_del_poligono_fusionado_se_ponderan():
    """Promediar los dos porcentajes a secas daría un valor equivocado."""
    datos = _distrital()
    capa = almacen.unir_con_geometria(datos, "distrito")
    fila = capa[capa["cod_unidad"] == FUSIONADO].iloc[0]
    partes = datos[datos["cod_unidad"].isin(MIEMBROS)]
    esperado = (
        (partes["pct_critico"] * partes["poblacion_estimada"]).sum()
        / partes["poblacion_estimada"].sum()
    )
    assert fila["pct_critico"] == pytest.approx(esperado, rel=1e-9)


def test_el_codigo_del_poligono_fusionado_se_resuelve_en_la_capa():
    """El clic devolvía 120699, que el almacén no tiene.

    Buscarlo en `datos` no encontraba nada y el panel caía al resultado nacional: era el
    único polígono del país cuyo detalle no se podía abrir.
    """
    datos = _distrital()
    capa = almacen.unir_con_geometria(datos, "distrito")
    assert FUSIONADO not in set(datos["cod_unidad"])
    assert FUSIONADO in set(capa["cod_unidad"])
    assert capa[capa["cod_unidad"] == FUSIONADO].iloc[0]["nom_unidad"] == "Mazamari - Pangoa"
    # Y los dos miembros no quedan además por su cuenta, que los contaría dos veces.
    assert not set(capa["cod_unidad"]) & set(MIEMBROS)


@pytest.mark.parametrize("umbral", [170, 200])
def test_la_suficiencia_del_poligono_fusionado_se_recalcula(umbral):
    """Se heredaba de Mazamari, con 163 evaluados, y el polígono tiene 436.

    Con el umbral del mapa por encima de 170 se pintaba gris, como ausencia de
    información, mientras el tooltip mostraba los 436 evaluados.
    """
    datos = _distrital()
    datos = datos.assign(muestra_suficiente=datos["n_estudiantes"] >= umbral)
    capa = almacen.unir_con_geometria(datos, "distrito", muestra_minima=umbral)
    fila = capa[capa["cod_unidad"] == FUSIONADO].iloc[0]
    assert fila["n_estudiantes"] == 436
    assert bool(fila["muestra_suficiente"]) is (436 >= umbral)


def test_la_escala_no_la_mueven_las_unidades_sin_muestra():
    """Gobernaban los colores de 143 de las 208 UGEL que sí se pintan."""
    datos = almacen.resultados_geograficos("ugel", "4P", "M")
    suficientes = datos[datos["n_estudiantes"] >= 30]
    con_todas = _cortes(datos["pct_critico"].to_numpy(float))
    solo_pintadas = _cortes(suficientes["pct_critico"].to_numpy(float))
    assert con_todas != solo_pintadas
    # La escala de las pintadas empieza en el mínimo de las pintadas, no en el de todas.
    assert solo_pintadas[0] == pytest.approx(suficientes["pct_critico"].min())


def test_los_cortes_de_la_escala_nunca_se_repiten():
    """La primera ruptura coincide con el mínimo cuando la clase más baja tiene un valor.

    La leyenda dibujaba entonces dos bloques seguidos con el mismo rótulo, uno de ellos
    de ancho cero. Pasaba en 31 de las 135 combinaciones.
    """
    combinaciones = 0
    for grado, areas in (("4P", "LM"), ("2S", "LM"), ("5S", "LM")):
        for area in areas:
            for nivel in ("departamento", "provincia", "distrito", "dre", "ugel"):
                datos = almacen.resultados_geograficos(nivel, grado, area)
                datos = datos[datos["n_estudiantes"] >= 30]
                for columna in ("pct_critico", "pct_satisfactorio", "medida_promedio"):
                    valores = datos[columna].to_numpy(float)
                    if len(valores) < 6:
                        continue
                    combinaciones += 1
                    cortes = _cortes(valores)
                    assert len(set(cortes)) == len(cortes), (grado, area, nivel, columna)
                    assert cortes == sorted(cortes)
    assert combinaciones > 50, "la prueba tiene que recorrer un número razonable de vistas"


def test_la_escala_aguanta_una_vista_con_pocas_unidades():
    assert _cortes(np.array([1.0, 2.0])) == [1.0, 2.0]
    assert _cortes(np.array([5.0, 5.0, 5.0])) == [5.0]
    assert _cortes(np.array([np.nan, np.nan])) == []


def test_las_ugel_con_territorio_prestado_se_identifican():
    """Catorce distritos están atendidos por más de una UGEL.

    La que no se queda el polígono conserva su cifra completa sobre un territorio que ya
    no contiene a esos estudiantes. El mapa no puede arreglarlo, pero sí declararlo.
    """
    tabla = almacen.territorio_prestado("4P", "M")
    assert not tabla.empty
    assert set(tabla.columns) >= {"cod_unidad", "nom_unidad", "evaluados", "fuera", "pct_fuera"}
    assert (tabla["fuera"] > 0).all()
    assert (tabla["pct_fuera"] <= 100).all()

    # El caso extremo documentado: cuatro de cada cinco estudiantes de Trujillo Sur Este
    # están en un distrito que el mapa asigna a otra UGEL.
    trujillo = tabla[tabla["cod_unidad"] == "130017"]
    assert len(trujillo) == 1
    assert trujillo.iloc[0]["pct_fuera"] == pytest.approx(79.36, abs=0.1)


def test_los_distritos_sin_poligono_no_cuentan_como_territorio_prestado():
    """No se los lleva otra UGEL: simplemente no se pintan, y eso ya se declara aparte."""
    sin_poligono = set(
        almacen.unidades_sin_geometria(_distrital(), "distrito")["cod_unidad"]
    )
    capa = almacen.geometrias("distrito")
    assert not sin_poligono & set(capa["ubigeo"].astype(str))


def test_el_aviso_de_quinto_cita_las_escuelas_que_hay_en_el_almacen():
    """El aviso compara 305 escuelas con 4 816 y esas cifras no se consultan.

    Están escritas en el módulo para no lanzar una consulta en cada pasada de cada
    página, así que esta prueba es lo que impide que se queden viejas: si la ingesta
    cambiara el número de escuelas, el mensaje mentiría y nada lo delataría.
    """
    reales = almacen.consultar(
        "select grado, count(*) as escuelas from dim_ie group by 1"
    )
    esperado = dict(zip(reales["grado"], reales["escuelas"]))
    assert almacen.ESCUELAS_POR_GRADO == esperado

    aviso = almacen.advertencia_representatividad("5S", "departamento")
    assert aviso is not None
    assert "305 escuelas" in aviso
    assert "4 816" in aviso, "separador de miles en formato peruano"
    # Las palabras que el aviso existe para no usar.
    for jerga in ("estrato", "representatividad", "indicativas"):
        assert jerga not in aviso.lower()


def test_el_aviso_solo_sale_donde_corresponde():
    for nivel in ("departamento", "provincia", "distrito", "dre", "ugel"):
        assert almacen.advertencia_representatividad("5S", nivel) is not None
    assert almacen.advertencia_representatividad("5S", "nacional") is None
    for grado in ("4P", "2S"):
        for nivel in ("departamento", "ugel", "nacional"):
            assert almacen.advertencia_representatividad(grado, nivel) is None
