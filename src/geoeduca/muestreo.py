"""Estimadores para el diseño muestral de la ENLA.

La ENLA no es un censo: es una muestra estratificada por conglomerados, donde el
conglomerado es la escuela y el estrato combina región, ámbito y gestión. Eso tiene
dos consecuencias que este módulo resuelve.

La primera es que todo promedio y toda proporción se calculan ponderando por el peso
muestral del área evaluada. Sin ponderar, las cifras no coinciden con las oficiales.

La segunda es que el error estándar no se puede calcular con la fórmula habitual de
muestreo aleatorio simple. Los estudiantes de una misma escuela se parecen entre sí, así
que la muestra aporta menos información de la que sugiere su tamaño. Ignorarlo produce
intervalos de confianza demasiado estrechos y lleva a declarar diferencias significativas
que no lo son.

El método que se usa aquí es la linearización de Taylor, que es el procedimiento estándar
para estimar la varianza de una razón bajo un diseño complejo, y el mismo que emplea la
UMC en sus scripts oficiales en R con el paquete survey:

    svydesign(id = ~ID_IE, strata = ~Estrato_DRE, nest = TRUE, weights = ~peso_X)

Una diferencia deliberada: la UMC añade pps = "brewer", una corrección por población
finita que reduce ligeramente la varianza. Aquí se usa el estimador con reemplazo, que
es el predeterminado en la mayoría del software de encuestas y resulta algo más
conservador, es decir, da intervalos iguales o un poco más anchos. La función
comparar_con_survey de las pruebas mide esa diferencia sobre los datos reales.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats

# Los estratos que contienen un solo conglomerado no permiten estimar varianza interna.
# La UMC los trata como estratos de certeza, es decir, con aporte nulo a la varianza
# (options(survey.lonely.psu = "certainty")). Se replica esa decisión.
APORTE_NULO_SI_UN_SOLO_CONGLOMERADO = True


@dataclass(frozen=True)
class Estimacion:
    """Resultado de estimar un parámetro sobre una muestra compleja."""

    valor: float
    error_estandar: float
    ic_inferior: float
    ic_sup: float
    n_muestra: int
    n_conglomerados: int
    n_estratos: int
    grados_libertad: int
    poblacion_estimada: float
    #: Conglomerados del dominio estimado. Con un corte regional, los del diseño son los
    #: del país entero y estos son los de la región, que es lo que dice si la cifra se
    #: apoya en dos escuelas o en veinte.
    n_conglomerados_dominio: int = 0
    #: Estratos que no aportaron a la varianza por quedarse con un solo conglomerado.
    estratos_sin_varianza: int = 0

    @property
    def margen_error(self) -> float:
        """Mitad del ancho del intervalo de confianza.

        Para una medida promedio es la distancia a cualquiera de los dos extremos. Para
        un porcentaje no: su intervalo se construye en la escala logit y no queda
        centrado en la estimación, así que esta cifra es el ancho medio y no sirve para
        escribir "valor ± margen".
        """
        return (self.ic_sup - self.ic_inferior) / 2

    @property
    def varianza_estimable(self) -> bool:
        """Si la varianza salió de algún estrato con más de un conglomerado.

        Cuando todos los estratos del corte tienen uno solo, la varianza da exactamente
        cero y el coeficiente de variación también, que se lee como precisión perfecta
        cuando es lo contrario: no hay con qué estimarla. Quien consuma una estimación
        tiene que poder distinguir los dos casos.
        """
        return self.error_estandar > 0

    @property
    def coeficiente_variacion(self) -> float:
        """Error estándar como fracción del valor estimado.

        Por encima de 0,20 la estimación suele considerarse poco fiable y conviene
        advertirlo en pantalla en lugar de mostrar la cifra sin matices.
        """
        if self.valor == 0 or not self.varianza_estimable:
            return float("nan")
        return abs(self.error_estandar / self.valor)

    def __str__(self) -> str:
        return (
            f"{self.valor:.2f} (ee {self.error_estandar:.3f}, "
            f"IC95 {self.ic_inferior:.2f} a {self.ic_sup:.2f}, n {self.n_muestra})"
        )


@dataclass(frozen=True)
class _Varianza:
    """Varianza del total linearizado y el recuento del diseño que la sostiene."""

    valor: float
    n_conglomerados: int
    n_estratos: int
    estratos_sin_varianza: int


def _varianza_de_total_linearizado(
    residuos: np.ndarray,
    conglomerado: np.ndarray,
    estrato: np.ndarray,
) -> _Varianza:
    """Varianza del total de una variable linearizada, bajo diseño estratificado.

    Suma los residuos dentro de cada conglomerado y acumula la dispersión entre
    conglomerados del mismo estrato.

    Recibe siempre el marco completo, no el recorte. Al estimar un dominio, los residuos
    de fuera valen cero pero sus conglomerados siguen contando: son los del diseño, y de
    ellos salen la varianza y los grados de libertad.
    """
    tabla = pd.DataFrame(
        {"residuo": residuos, "conglomerado": conglomerado, "estrato": estrato}
    )

    # Total de cada conglomerado. La varianza del diseño se construye sobre estos
    # totales, no sobre las observaciones individuales.
    por_conglomerado = (
        tabla.groupby(["estrato", "conglomerado"], observed=True)["residuo"]
        .sum()
        .reset_index()
    )

    varianza = 0.0
    sin_varianza = 0
    for _, grupo in por_conglomerado.groupby("estrato", observed=True):
        n_h = len(grupo)
        if n_h < 2:
            if APORTE_NULO_SI_UN_SOLO_CONGLOMERADO:
                sin_varianza += 1
                continue
            raise ValueError(
                "Un estrato quedó con un solo conglomerado y no se permite el "
                "tratamiento de estrato de certeza."
            )
        totales = grupo["residuo"].to_numpy()
        varianza += n_h / (n_h - 1) * float(((totales - totales.mean()) ** 2).sum())

    return _Varianza(
        valor=varianza,
        n_conglomerados=len(por_conglomerado),
        n_estratos=int(por_conglomerado["estrato"].nunique()),
        estratos_sin_varianza=sin_varianza,
    )


def estimar_razon(
    datos: pd.DataFrame,
    numerador: str,
    peso: str = "peso",
    conglomerado: str = "id_ie",
    estrato: str = "cod_estrato",
    nivel_confianza: float = 0.95,
    dominio: pd.Series | np.ndarray | None = None,
) -> Estimacion:
    """Estima una media ponderada con su error estándar bajo el diseño de la ENLA.

    El parámetro estimado es la razón entre el total ponderado del numerador y el total
    de pesos, que es lo que la UMC llama medida promedio cuando el numerador es el
    puntaje. Para estimar una proporción se pasa una columna de ceros y unos.

    Con `dominio` se estima una subpoblación: una región, un ámbito, un sexo. El valor
    sale solo de las filas del dominio, pero la varianza se calcula sobre el marco
    entero, con residuo cero fuera. Es el estimador de dominio de libro y es lo que hace
    `survey` al llamar a `subset`, que arrastra el tamaño de muestra fijado en
    `svydesign`.

    La diferencia no es de matiz. Recortando el marco y recontando los conglomerados que
    quedan dentro, 5.° de secundaria en Matemática daba para Huánuco un error estándar
    de 2,63 cuando el correcto es 18,40, siete veces menor, porque los dos estratos que
    se quedaban con una sola escuela se descartaban y la varianza salía de cinco
    escuelas centradas en su propia media. Y los grados de libertad, recontados igual,
    se desplomaban a 1, con lo que el multiplicador t pasaba de 1,97 a 12,71.

    Las filas donde el numerador o el peso son nulos se descartan, igual que hace el
    procedimiento oficial con na.rm = TRUE.
    """
    columnas = [numerador, peso, conglomerado, estrato]
    faltantes = [c for c in columnas if c not in datos.columns]
    if faltantes:
        raise KeyError(f"Faltan columnas en los datos: {faltantes}")

    marco = datos[columnas].copy()
    if dominio is None:
        marco["_dominio"] = True
    else:
        serie = dominio if isinstance(dominio, pd.Series) else pd.Series(dominio, index=datos.index)
        marco["_dominio"] = serie.reindex(datos.index).fillna(False).astype(bool)

    limpio = marco.dropna(subset=columnas)
    if limpio.empty:
        raise ValueError("No quedan filas con valor y peso para estimar.")

    en_dominio = limpio["_dominio"].to_numpy()
    if not en_dominio.any():
        raise ValueError("Ninguna fila cae dentro del dominio pedido.")

    y = limpio[numerador].to_numpy(dtype=float)
    w = limpio[peso].to_numpy(dtype=float)
    total_pesos = float(w[en_dominio].sum())
    if total_pesos <= 0:
        raise ValueError("La suma de pesos es cero o negativa.")

    razon = float((w[en_dominio] * y[en_dominio]).sum() / total_pesos)

    # Linearización: la razón se aproxima por el total de w*(y - razon), dividido entre
    # el total de pesos. Ese es el término cuya varianza se estima. Fuera del dominio el
    # residuo es cero, pero la fila sigue estando: su conglomerado cuenta.
    residuos = np.where(en_dominio, w * (y - razon), 0.0)
    varianza = _varianza_de_total_linearizado(
        residuos,
        limpio[conglomerado].to_numpy(),
        limpio[estrato].to_numpy(),
    )

    error_estandar = float(np.sqrt(varianza.valor) / total_pesos)

    # Los grados de libertad de un diseño estratificado por conglomerados son el número
    # de conglomerados menos el número de estratos, no el número de observaciones.
    grados_libertad = max(varianza.n_conglomerados - varianza.n_estratos, 1)
    t = float(stats.t.ppf(0.5 + nivel_confianza / 2, grados_libertad))

    dentro = limpio[en_dominio]
    return Estimacion(
        valor=razon,
        error_estandar=error_estandar,
        ic_inferior=razon - t * error_estandar,
        ic_sup=razon + t * error_estandar,
        n_muestra=int(en_dominio.sum()),
        n_conglomerados=varianza.n_conglomerados,
        n_estratos=varianza.n_estratos,
        grados_libertad=grados_libertad,
        poblacion_estimada=total_pesos,
        n_conglomerados_dominio=int(dentro[conglomerado].nunique()),
        estratos_sin_varianza=varianza.estratos_sin_varianza,
    )


def estimar_proporcion(
    datos: pd.DataFrame,
    condicion: pd.Series | str,
    peso: str = "peso",
    conglomerado: str = "id_ie",
    estrato: str = "cod_estrato",
    nivel_confianza: float = 0.95,
    en_porcentaje: bool = True,
    dominio: pd.Series | np.ndarray | None = None,
) -> Estimacion:
    """Estima la proporción de casos que cumplen una condición.

    La condición puede ser el nombre de una columna booleana del propio marco o una
    serie booleana alineada con él. Por omisión el resultado se devuelve en porcentaje,
    que es como se publican los niveles de logro.

    El intervalo se construye en la escala logit y se devuelve a la escala original. Un
    intervalo simétrico alrededor de una proporción es un método lineal aplicado a algo
    acotado, y cerca de 0 o de 100 propone límites imposibles: en 5.° de secundaria
    llegaba a imprimir 43,63 % con un intervalo de -124,51 a 211,76, y en Loreto, con 16
    escuelas y grados de libertad razonables, un 0,67 % con el límite inferior en -0,23.
    La transformación logit es lo que usa `svyciprop` para esto mismo.
    """
    marco = datos.copy()
    if isinstance(condicion, str):
        if condicion not in marco.columns:
            raise KeyError(f"No existe la columna {condicion!r}.")
        indicador = marco[condicion]
    else:
        indicador = condicion.reindex(marco.index)

    marco["_indicador"] = indicador.astype(float)

    estimacion = estimar_razon(
        marco,
        numerador="_indicador",
        peso=peso,
        conglomerado=conglomerado,
        estrato=estrato,
        nivel_confianza=nivel_confianza,
        dominio=dominio,
    )

    p = estimacion.valor
    ee = estimacion.error_estandar
    t = float(stats.t.ppf(0.5 + nivel_confianza / 2, estimacion.grados_libertad))

    if 0.0 < p < 1.0 and ee > 0:
        # Escala logit: la derivada de log(p/(1-p)) es 1/(p(1-p)).
        g = np.log(p / (1.0 - p))
        ee_g = ee / (p * (1.0 - p))
        inferior = float(1.0 / (1.0 + np.exp(-(g - t * ee_g))))
        superior = float(1.0 / (1.0 + np.exp(-(g + t * ee_g))))
    else:
        # Con la proporción pegada a 0 o a 1, o sin varianza estimable, el logit no
        # está definido. Se recorta el intervalo simétrico, que es lo más que se puede
        # decir, en lugar de publicar un límite fuera de rango.
        inferior = max(0.0, estimacion.ic_inferior)
        superior = min(1.0, estimacion.ic_sup)

    factor = 100.0 if en_porcentaje else 1.0
    return Estimacion(
        valor=p * factor,
        error_estandar=ee * factor,
        ic_inferior=inferior * factor,
        ic_sup=superior * factor,
        n_muestra=estimacion.n_muestra,
        n_conglomerados=estimacion.n_conglomerados,
        n_estratos=estimacion.n_estratos,
        grados_libertad=estimacion.grados_libertad,
        poblacion_estimada=estimacion.poblacion_estimada,
        n_conglomerados_dominio=estimacion.n_conglomerados_dominio,
        estratos_sin_varianza=estimacion.estratos_sin_varianza,
    )


@dataclass(frozen=True)
class Brecha:
    """Diferencia entre dos grupos, con su significancia estadística."""

    nombre_a: str
    nombre_b: str
    estimacion_a: Estimacion
    estimacion_b: Estimacion
    diferencia: float
    error_estandar: float
    ic_inferior: float
    ic_sup: float
    valor_p: float
    grados_libertad: int

    @property
    def es_significativa(self) -> bool:
        """Verdadero si el intervalo de confianza de la diferencia excluye el cero."""
        return self.ic_inferior > 0 or self.ic_sup < 0

    def __str__(self) -> str:
        marca = "significativa" if self.es_significativa else "no significativa"
        return (
            f"{self.nombre_a} menos {self.nombre_b}: {self.diferencia:+.2f} "
            f"(IC95 {self.ic_inferior:+.2f} a {self.ic_sup:+.2f}, p {self.valor_p:.4f}, "
            f"{marca})"
        )


def comparar_grupos(
    datos: pd.DataFrame,
    columna_grupo: str,
    grupo_a,
    grupo_b,
    numerador: str = "medida500",
    peso: str = "peso",
    conglomerado: str = "id_ie",
    estrato: str = "cod_estrato",
    nivel_confianza: float = 0.95,
    es_proporcion: bool = False,
) -> Brecha:
    """Compara dos grupos y dice si la diferencia entre ambos es estadísticamente real.

    Los dos grupos provienen de la misma muestra, así que sus estimaciones no son
    independientes del todo. La varianza de la diferencia se obtiene linearizando ambas
    razones a la vez sobre el marco completo, de modo que la covarianza entre ellas queda
    incorporada. Calcularlas por separado y sumar las varianzas supondría independencia y
    daría un error estándar equivocado.
    """
    if columna_grupo not in datos.columns:
        raise KeyError(f"No existe la columna {columna_grupo!r}.")

    marco = datos[datos[columna_grupo].isin([grupo_a, grupo_b])].copy()
    marco = marco.dropna(subset=[numerador, peso, conglomerado, estrato])
    if marco.empty:
        raise ValueError("Ninguna fila corresponde a los grupos indicados.")

    es_a = (marco[columna_grupo] == grupo_a).to_numpy()
    es_b = (marco[columna_grupo] == grupo_b).to_numpy()
    y = marco[numerador].to_numpy(dtype=float)
    w = marco[peso].to_numpy(dtype=float)

    total_a = float(w[es_a].sum())
    total_b = float(w[es_b].sum())
    if total_a <= 0 or total_b <= 0:
        raise ValueError("Alguno de los dos grupos no tiene peso.")

    razon_a = float((w[es_a] * y[es_a]).sum() / total_a)
    razon_b = float((w[es_b] * y[es_b]).sum() / total_b)
    diferencia = razon_a - razon_b

    # Residuo conjunto: cada observación aporta a la diferencia según el grupo al que
    # pertenece, con signo opuesto y escalado por el total de pesos de su propio grupo.
    residuos = np.where(
        es_a,
        w * (y - razon_a) / total_a,
        -w * (y - razon_b) / total_b,
    )

    varianza = _varianza_de_total_linearizado(
        residuos,
        marco[conglomerado].to_numpy(),
        marco[estrato].to_numpy(),
    )
    error_estandar = float(np.sqrt(varianza.valor))

    grados_libertad = max(varianza.n_conglomerados - varianza.n_estratos, 1)
    t_critico = float(stats.t.ppf(0.5 + nivel_confianza / 2, grados_libertad))
    if error_estandar <= 0:
        raise ValueError(
            "No hay con qué estimar la varianza de la diferencia: todos los estratos "
            "del corte tienen un solo conglomerado."
        )
    t_observado = diferencia / error_estandar
    valor_p = float(2 * stats.t.sf(abs(t_observado), grados_libertad))

    factor = 100.0 if es_proporcion else 1.0

    def estimar_grupo(valor_grupo):
        """Cada grupo como dominio sobre el marco de los dos, no como marco recortado."""
        pertenece = marco[columna_grupo] == valor_grupo
        if es_proporcion:
            return estimar_proporcion(
                marco, numerador, peso, conglomerado, estrato, nivel_confianza,
                dominio=pertenece,
            )
        return estimar_razon(
            marco, numerador, peso, conglomerado, estrato, nivel_confianza,
            dominio=pertenece,
        )

    return Brecha(
        nombre_a=str(grupo_a),
        nombre_b=str(grupo_b),
        estimacion_a=estimar_grupo(grupo_a),
        estimacion_b=estimar_grupo(grupo_b),
        diferencia=diferencia * factor,
        error_estandar=error_estandar * factor,
        ic_inferior=(diferencia - t_critico * error_estandar) * factor,
        ic_sup=(diferencia + t_critico * error_estandar) * factor,
        valor_p=valor_p,
        grados_libertad=grados_libertad,
    )


def estimar_por_grupo(
    datos: pd.DataFrame,
    columnas_grupo: str | Sequence[str],
    numerador: str = "medida500",
    peso: str = "peso",
    conglomerado: str = "id_ie",
    estrato: str = "cod_estrato",
    nivel_confianza: float = 0.95,
    es_proporcion: bool = False,
    muestra_minima: int = 1,
    conglomerados_minimos: int = 2,
) -> pd.DataFrame:
    """Estima el mismo parámetro para cada grupo y devuelve una tabla.

    Pensado para el ranking regional del tablero, donde cada barra necesita su propio
    intervalo de confianza.

    Cada grupo se estima como dominio sobre el marco entero, no recortándolo: así la
    varianza y los grados de libertad salen del diseño y no de las escuelas que quedan
    dentro del corte.

    Hay dos pisos y no uno. `muestra_minima` cuenta estudiantes y `conglomerados_minimos`
    cuenta escuelas, que es lo que de verdad gobierna la precisión de un diseño por
    conglomerados: Moquegua pasaba el piso de 30 estudiantes en 5.° de secundaria con
    111 evaluados repartidos en dos escuelas.
    """
    if isinstance(columnas_grupo, str):
        columnas_grupo = [columnas_grupo]
    columnas_grupo = list(columnas_grupo)

    limpio = datos.dropna(subset=[numerador, peso])

    filas = []
    for claves, grupo in limpio.groupby(columnas_grupo, observed=True, dropna=True):
        if not isinstance(claves, tuple):
            claves = (claves,)
        if len(grupo) < muestra_minima:
            continue
        if grupo[conglomerado].nunique() < conglomerados_minimos:
            continue

        pertenece = pd.Series(False, index=limpio.index)
        pertenece.loc[grupo.index] = True
        try:
            if es_proporcion:
                est = estimar_proporcion(
                    limpio, numerador, peso, conglomerado, estrato, nivel_confianza,
                    dominio=pertenece,
                )
            else:
                est = estimar_razon(
                    limpio, numerador, peso, conglomerado, estrato, nivel_confianza,
                    dominio=pertenece,
                )
        except ValueError:
            continue

        fila = dict(zip(columnas_grupo, claves))
        fila.update(
            {
                "valor": est.valor,
                "error_estandar": est.error_estandar,
                "ic_inferior": est.ic_inferior,
                "ic_sup": est.ic_sup,
                "margen_error": est.margen_error,
                "coeficiente_variacion": est.coeficiente_variacion,
                "n_muestra": est.n_muestra,
                "n_conglomerados": est.n_conglomerados_dominio,
                "n_conglomerados_diseno": est.n_conglomerados,
                "grados_libertad": est.grados_libertad,
                "varianza_estimable": est.varianza_estimable,
                "poblacion_estimada": est.poblacion_estimada,
            }
        )
        filas.append(fila)

    if not filas:
        return pd.DataFrame(columns=columnas_grupo + ["valor", "error_estandar"])

    return pd.DataFrame(filas).sort_values("valor", ascending=False, ignore_index=True)


def se_solapan(a: Estimacion, b: Estimacion) -> bool:
    """Indica si dos intervalos de confianza se solapan.

    Sirve para decidir si dos barras de un ranking pueden presentarse como distintas.
    Es una regla conservadora y no sustituye a comparar_grupos, que calcula la
    significancia de la diferencia teniendo en cuenta la covarianza entre ambas
    estimaciones. Dos intervalos pueden solaparse y aun así diferir de forma
    significativa.
    """
    return not (a.ic_sup < b.ic_inferior or b.ic_sup < a.ic_inferior)
