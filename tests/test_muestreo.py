"""Pruebas de los estimadores de muestreo.

Los valores de referencia no son inventados ni calculados con este mismo código: salen
de ejecutar el paquete survey de R sobre los mismos datos, con el diseño que la UMC
declara en sus scripts oficiales:

    options(survey.lonely.psu = "certainty")
    svydesign(id = ~id_ie, strata = ~cod_estrato, nest = TRUE, weights = ~peso)
    svymean(~medida500, diseno, na.rm = TRUE)

Para la diferencia entre grupos la referencia es svyglm y no svyby, porque svyby solo
devuelve la diagonal de la matriz de covarianza y por tanto supone independencia entre
los dos grupos, cosa que no se cumple cuando ambos salen de la misma muestra.

Si alguna de estas pruebas falla, el error está en el estimador, no en la referencia.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from geoeduca import almacen, muestreo
from geoeduca.muestreo import (
    comparar_grupos,
    estimar_por_grupo,
    estimar_proporcion,
    estimar_razon,
    se_solapan,
)

# Tolerancias: las estimaciones puntuales deben coincidir hasta la sexta cifra decimal y
# los errores estándar hasta la quinta. Lo que queda por debajo es redondeo.
TOL_VALOR = 1e-6
TOL_ERROR = 1e-5


@pytest.fixture(scope="module")
def primaria_lectura():
    """Microdatos de 4.° de primaria en Lectura, el caso con referencia en R."""
    try:
        datos = almacen.microdatos("4P", "L")
    except almacen.AlmacenNoEncontrado as exc:
        pytest.skip(str(exc))
    datos["satisfactorio"] = (datos["cod_nivel"] == 3).astype(float)
    datos["critico"] = datos["es_critico"].astype(float)
    return datos


def test_estructura_de_la_muestra(primaria_lectura):
    """El diseño declarado tiene las unidades que la UMC describe."""
    assert len(primaria_lectura) == 129_457
    assert primaria_lectura["id_ie"].nunique() == 4_816
    assert primaria_lectura["cod_estrato"].nunique() == 123


def test_medida_promedio_coincide_con_survey(primaria_lectura):
    """La medida promedio y su error estándar reproducen a survey de R."""
    est = estimar_razon(primaria_lectura, "medida500")

    assert est.valor == pytest.approx(490.136410, abs=TOL_VALOR)
    assert est.error_estandar == pytest.approx(0.812306, abs=TOL_ERROR)
    # Los grados de libertad de un diseño estratificado por conglomerados son el número
    # de conglomerados menos el de estratos, no el número de estudiantes.
    assert est.grados_libertad == 4_693
    assert est.n_muestra == 129_457


def test_la_cifra_publicada_cae_dentro_del_intervalo(primaria_lectura):
    """El 490 que publica la UMC es el centro del intervalo, no un extremo."""
    est = estimar_razon(primaria_lectura, "medida500")
    assert est.ic_inferior < 490 < est.ic_sup
    assert est.margen_error == pytest.approx(est.ic_sup - est.valor, abs=1e-9)


def test_proporcion_satisfactorio_coincide_con_survey(primaria_lectura):
    """El porcentaje en nivel satisfactorio reproduce a survey de R."""
    est = estimar_proporcion(primaria_lectura, "satisfactorio")
    assert est.valor == pytest.approx(32.656970, abs=TOL_VALOR)
    assert est.error_estandar == pytest.approx(0.492173, abs=TOL_ERROR)


def test_proporcion_critico_coincide_con_survey(primaria_lectura):
    """El porcentaje en niveles críticos reproduce a survey de R."""
    est = estimar_proporcion(primaria_lectura, "critico")
    assert est.valor == pytest.approx(26.959887, abs=TOL_VALOR)
    assert est.error_estandar == pytest.approx(0.444057, abs=TOL_ERROR)


def test_ponderar_cambia_el_resultado(primaria_lectura):
    """Sin ponderar, la cifra no es la oficial.

    Esta prueba existe para dejar constancia del tamaño del error: no es un matiz
    decimal, son casi dos puntos porcentuales.
    """
    sin_ponderar = primaria_lectura["satisfactorio"].mean() * 100
    ponderado = estimar_proporcion(primaria_lectura, "satisfactorio").valor

    assert sin_ponderar == pytest.approx(30.6, abs=0.1)
    assert ponderado == pytest.approx(32.7, abs=0.1)
    assert abs(ponderado - sin_ponderar) > 1.5


def test_error_estandar_mayor_que_el_de_muestreo_simple(primaria_lectura):
    """Ignorar el conglomerado subestima la incertidumbre.

    Si se tratara la muestra como aleatoria simple, el error estándar saldría bastante
    menor y los intervalos serían demasiado estrechos. El efecto de diseño mide cuánto.
    """
    import numpy as np

    est = estimar_razon(primaria_lectura, "medida500")

    pesos = primaria_lectura["peso"].to_numpy()
    valores = primaria_lectura["medida500"].to_numpy()
    media = np.average(valores, weights=pesos)
    varianza = np.average((valores - media) ** 2, weights=pesos)
    ee_simple = float(np.sqrt(varianza / len(valores)))

    efecto_diseno = (est.error_estandar / ee_simple) ** 2
    assert est.error_estandar > ee_simple
    # Acotado por los dos lados y pegado al valor real. Con un `> 3` a secas, el error
    # estándar podía estar subestimado por un factor 2,4 y la prueba seguía pasando:
    # el valor que de verdad sale en este corte es 17,5, no 3.
    assert efecto_diseno == pytest.approx(17.5, abs=0.5)
    assert est.error_estandar == pytest.approx(0.812306, abs=1e-5)


def test_brecha_urbano_rural_coincide_con_svyglm(primaria_lectura):
    """La diferencia entre ámbitos y su error estándar reproducen a svyglm de R."""
    brecha = comparar_grupos(primaria_lectura, "ambito", "Urbana", "Rural", "medida500")

    assert brecha.diferencia == pytest.approx(43.225764, abs=TOL_VALOR)
    assert brecha.error_estandar == pytest.approx(1.315022, abs=TOL_ERROR)
    assert brecha.es_significativa
    assert brecha.valor_p < 1e-100


def test_la_brecha_considera_la_covarianza(primaria_lectura):
    """Sumar varianzas por separado no da lo mismo que linearizar en conjunto.

    Los dos grupos salen de la misma muestra, así que sus estimaciones están
    correlacionadas. Suponerlas independientes da un error estándar distinto.
    """
    import numpy as np

    brecha = comparar_grupos(primaria_lectura, "ambito", "Urbana", "Rural", "medida500")
    ingenuo = float(
        np.sqrt(
            brecha.estimacion_a.error_estandar**2 + brecha.estimacion_b.error_estandar**2
        )
    )
    assert brecha.error_estandar != pytest.approx(ingenuo, abs=1e-9)


def test_estimar_por_grupo_devuelve_intervalos(primaria_lectura):
    """El ranking regional trae un intervalo por fila, que es lo que pide el tablero."""
    tabla = estimar_por_grupo(primaria_lectura, "departamento", "medida500")

    assert len(tabla) == 25
    assert (tabla["ic_inferior"] < tabla["valor"]).all()
    assert (tabla["valor"] < tabla["ic_sup"]).all()
    assert tabla["valor"].is_monotonic_decreasing

    tacna = tabla[tabla["departamento"] == "TACNA"].iloc[0]
    loreto = tabla[tabla["departamento"] == "LORETO"].iloc[0]
    assert tacna["valor"] == pytest.approx(520.2, abs=0.1)
    assert loreto["valor"] == pytest.approx(431.6, abs=0.1)


def test_dos_regiones_distantes_no_se_solapan(primaria_lectura):
    """Tacna y Loreto difieren de verdad, no por ruido muestral."""
    tabla = estimar_por_grupo(primaria_lectura, "departamento", "medida500")
    extremos = tabla.iloc[[0, -1]]
    assert extremos.iloc[0]["ic_inferior"] > extremos.iloc[-1]["ic_sup"]


def test_muestra_minima_descarta_grupos_pequenos(primaria_lectura):
    """Con el filtro activo quedan menos unidades que sin él."""
    sin_filtro = estimar_por_grupo(primaria_lectura, "ubigeo", "medida500")
    con_filtro = estimar_por_grupo(
        primaria_lectura, "ubigeo", "medida500", muestra_minima=30
    )
    assert len(con_filtro) < len(sin_filtro)
    assert (con_filtro["n_muestra"] >= 30).all()


def test_se_solapan_es_simetrico(primaria_lectura):
    """La comprobación de solapamiento no depende del orden de los argumentos."""
    tabla = estimar_por_grupo(primaria_lectura, "ambito", "medida500")
    urbana = estimar_razon(
        primaria_lectura[primaria_lectura["ambito"] == "Urbana"], "medida500"
    )
    rural = estimar_razon(
        primaria_lectura[primaria_lectura["ambito"] == "Rural"], "medida500"
    )
    assert se_solapan(urbana, rural) == se_solapan(rural, urbana)
    assert not se_solapan(urbana, rural)


def test_faltan_columnas_da_error_claro(primaria_lectura):
    """Un error de nombre se detecta al entrar, no en mitad del cálculo."""
    with pytest.raises(KeyError, match="inexistente"):
        estimar_razon(primaria_lectura, "inexistente")


# --------------------------------------------------------------------------------------
# Regresiones
# --------------------------------------------------------------------------------------


def _dominio_a_mano(datos, mascara, numerador="medida500"):
    """Estimador de dominio escrito aquí, sin reusar nada del módulo.

    Linealiza el dominio sobre el marco completo, con residuo cero fuera, y cuenta los
    conglomerados del diseño. Es la referencia contra la que se compara el módulo.
    """
    limpio = datos.dropna(subset=[numerador, "peso"])
    dentro = mascara.reindex(limpio.index).fillna(False).to_numpy()
    y = limpio[numerador].to_numpy(float)
    w = limpio["peso"].to_numpy(float)
    total = w[dentro].sum()
    razon = (w[dentro] * y[dentro]).sum() / total
    residuo = np.where(dentro, w * (y - razon), 0.0)

    tabla = pd.DataFrame({
        "r": residuo,
        "ie": limpio["id_ie"].to_numpy(),
        "h": limpio["cod_estrato"].to_numpy(),
    })
    por_ie = tabla.groupby(["h", "ie"], observed=True)["r"].sum().reset_index()
    varianza = 0.0
    for _, g in por_ie.groupby("h", observed=True):
        n_h = len(g)
        if n_h < 2:
            continue
        t = g["r"].to_numpy()
        varianza += n_h / (n_h - 1) * ((t - t.mean()) ** 2).sum()
    gl = len(por_ie) - por_ie["h"].nunique()
    return razon, float(np.sqrt(varianza) / total), gl


def test_el_dominio_no_recorta_el_marco():
    """Recortar el marco subestimaba el error estándar hasta siete veces.

    En 5.° de secundaria los estratos no anidan dentro del departamento, así que al
    recortar quedaban estratos con una sola escuela, que se descartaban, y la varianza
    salía de las pocas que quedaban. Huánuco publicaba 2,63 donde corresponde 18,40.
    """
    datos = almacen.microdatos("5S", "M")
    for region in ("HUÁNUCO", "MOQUEGUA", "TUMBES", "LAMBAYEQUE", "LIMA"):
        mascara = datos["departamento"] == region
        razon, ee, gl = _dominio_a_mano(datos, mascara)
        est = muestreo.estimar_razon(datos, "medida500", dominio=mascara)
        assert est.valor == pytest.approx(razon, abs=1e-9), region
        assert est.error_estandar == pytest.approx(ee, abs=1e-9), region
        assert est.grados_libertad == gl, region


def test_los_grados_de_libertad_son_los_del_diseno():
    """Recontados sobre el recorte caían a 1, y el multiplicador t pasaba de 1,97 a 12,71."""
    datos = almacen.microdatos("5S", "M")
    tabla = muestreo.estimar_por_grupo(
        datos, "departamento", "medida500", muestra_minima=30, conglomerados_minimos=2
    )
    gl_diseno = datos["id_ie"].nunique() - datos["cod_estrato"].nunique()
    assert gl_diseno == 302
    assert set(tabla["grados_libertad"]) == {302}


@pytest.mark.parametrize("grado", ["4P", "2S", "5S"])
@pytest.mark.parametrize("columna", ["es_critico", "es_satisfactorio"])
def test_ningun_intervalo_de_un_porcentaje_sale_de_cero_a_cien(grado, columna):
    """Imprimía 43,63 % con un intervalo de -124,51 a 211,76.

    El intervalo se construye ahora en la escala logit, que no puede salirse.
    """
    datos = almacen.microdatos(grado, "M")
    tabla = muestreo.estimar_por_grupo(
        datos, "departamento", columna, es_proporcion=True,
        muestra_minima=30, conglomerados_minimos=2,
    )
    assert not tabla.empty
    assert (tabla["ic_inferior"] >= 0).all()
    assert (tabla["ic_sup"] <= 100).all()
    # Y el intervalo sigue conteniendo la estimación.
    assert (tabla["ic_inferior"] <= tabla["valor"]).all()
    assert (tabla["valor"] <= tabla["ic_sup"]).all()


def test_una_proporcion_pegada_a_cero_no_baja_de_cero():
    """Loreto, 0,67 % con 16 escuelas, daba un límite inferior de -0,23.

    No era culpa de los grados de libertad: la simetría sola lo produce.
    """
    datos = almacen.microdatos("5S", "L")
    mascara = datos["departamento"] == "LORETO"
    est = muestreo.estimar_proporcion(datos, "es_satisfactorio", dominio=mascara)
    assert est.valor == pytest.approx(0.6669, abs=0.01)
    assert est.ic_inferior > 0
    assert est.ic_sup < 100


def test_la_varianza_no_estimable_se_declara():
    """Devolver cero en silencio se lee como precisión perfecta."""
    datos = almacen.microdatos("4P", "L").head(400).copy()
    # Un estrato por escuela: ningún estrato tiene dos conglomerados.
    datos["cod_estrato"] = datos["id_ie"]
    est = muestreo.estimar_razon(datos, "medida500")
    assert est.error_estandar == 0
    assert not est.varianza_estimable
    assert est.estratos_sin_varianza == datos["id_ie"].nunique()
    assert np.isnan(est.coeficiente_variacion)


def test_el_piso_de_escuelas_descarta_lo_que_el_de_estudiantes_dejaba_pasar():
    """Moquegua pasaba el piso de 30 estudiantes con 111 evaluados en dos escuelas."""
    datos = almacen.microdatos("5S", "M")
    con_piso = muestreo.estimar_por_grupo(
        datos, "departamento", "medida500", muestra_minima=30, conglomerados_minimos=3
    )
    sin_piso = muestreo.estimar_por_grupo(
        datos, "departamento", "medida500", muestra_minima=30, conglomerados_minimos=1
    )
    assert "MOQUEGUA" in set(sin_piso["departamento"])
    assert "MOQUEGUA" not in set(con_piso["departamento"])
    assert (con_piso["n_conglomerados"] >= 3).all()


def test_el_nacional_no_cambia_al_estimar_sin_dominio():
    """Lo que no es un dominio tiene que seguir dando exactamente lo mismo."""
    datos = almacen.microdatos("4P", "L")
    est = muestreo.estimar_razon(datos, "medida500")
    assert est.valor == pytest.approx(490.136410, abs=1e-5)
    assert est.error_estandar == pytest.approx(0.812306, abs=1e-5)
    assert est.grados_libertad == 4693
