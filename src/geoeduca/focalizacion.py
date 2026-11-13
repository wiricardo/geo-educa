"""Priorización de unidades geográficas para intervención.

Responde la pregunta de la pantalla de focalización: con recursos limitados,
¿por dónde empezar? El módulo no decide: ordena el mismo conjunto de unidades
según tres criterios distintos y deja ver que el orden cambia según cuál se
elija. Esa discrepancia no es un defecto del dato, es la decisión de política
que el dato no puede tomar.

Los tres criterios
------------------
*Intensidad* (`pct_critico`): qué proporción de los estudiantes de la unidad
está en niveles críticos. Mide cuán extendido está el rezago donde se
interviene. No depende del tamaño de la unidad, así que favorece unidades
chicas: una UGEL de 36 estudiantes estimados con 94 % de rezago encabeza este
orden.

*Alcance* (`poblacion_critica`): cuántos estudiantes de la unidad están en
niveles críticos, en población estimada. Mide a cuántos estudiantes llega la
intervención. Favorece unidades grandes, incluso con porcentajes medios: las
UGEL de Lima aparecen arriba porque son enormes, aunque su rezago sea menor
que el de la Amazonía.

*Combinado*: media geométrica de la posición relativa de la unidad en cada una
de las dos dimensiones, medida como percentil dentro del conjunto evaluado.

    indice = raiz( percentil(intensidad) * percentil(alcance) )

Por qué así, y no de otra forma:

1. Las dos dimensiones no son comparables en bruto. La intensidad vive entre 0
   y 100; el alcance va de unas decenas a más de ocho mil estudiantes y está muy
   sesgado a la derecha. Normalizar por mínimo y máximo haría que la UGEL más
   grande se lleve el 1,0 y deje a casi todas las demás por debajo de 0,3, con
   lo cual el criterio combinado sería el de alcance con otro nombre. Se
   comprobó sobre los datos: con mínimo-máximo, San Juan de Miraflores sube al
   segundo puesto y las UGEL amazónicas bajan. El percentil es invariante a la
   escala y a cualquier transformación monótona, así que no arrastra ese sesgo.
2. La media geométrica exige las dos cosas a la vez: si una unidad está en el
   fondo de cualquiera de las dos dimensiones, el índice se va a cero y no hay
   cómo compensarlo con la otra. Una media aritmética sí dejaría entrar a la
   unidad diminuta con rezago extremo y a la unidad enorme con rezago medio,
   que son justamente los dos casos que el criterio combinado debe moderar.
3. El índice es relativo al conjunto que recibe. Por eso `priorizar` lo calcula
   sobre el universo completo (todas las unidades con muestra suficiente) y
   recién después aplica los umbrales de política y el recorte a las primeras
   N. Calcularlo sobre una lista ya recortada a ocho unidades compararía cada
   unidad solo contra las otras siete y perdería la magnitud: hay que saber que
   2 387 estudiantes es mucho para el país, no solo más que los otros siete.

La tensión que el módulo tiene que hacer visible
------------------------------------------------
En 4.º de primaria y Matemática, con muestra mínima 30, al menos 500
estudiantes estimados y al menos 70 % de rezago, quedan ocho UGEL. La de Alto
Amazonas - Yurimaguas tiene el porcentaje más bajo de las ocho (70,3 %) y la
población estimada más alta (3 394), de modo que concentra más estudiantes en
niveles críticos que cualquier otra. Ordenar por intensidad la deja octava; ordenar por
alcance la deja primera. `comparar_criterios` y `describir_tension` existen para
que ese desacuerdo se vea, en lugar de quedar escondido detrás del orden que
la pantalla trajo por omisión.

Qué hace y qué no hace
----------------------
Funciones puras sobre DataFrames: no abren la base de datos, no leen archivos y
no escriben nada. Tampoco importan nada de geometría, para que la priorización
se pueda calcular sin cargar las capas.

Las cifras son estimaciones de una evaluación muestral. La población en niveles
críticos de una unidad describe a cuántos estudiantes representa la muestra de esa
unidad, no un padrón de estudiantes identificables, y por debajo de la DRE ninguna de
estas cifras tiene representatividad declarada: sirven para ordenar
prioridades, no para rendir cuentas de una cobertura.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "CRITERIOS",
    "MUESTRA_MINIMA",
    "Priorizacion",
    "indice_combinado",
    "priorizar",
    "cobertura_acumulada",
    "ninos_alcanzados",
    "comparar_criterios",
    "describir_tension",
]

#: Estudiantes evaluados mínimos para que una unidad entre a la priorización.
#: Coincide con `muestra_suficiente` del almacén.
MUESTRA_MINIMA = 30

#: Los tres criterios y qué mide cada uno, para rotular la interfaz sin repetir
#: el texto en cada pantalla.
CRITERIOS: Mapping[str, str] = {
    "intensidad": "Porcentaje de estudiantes en niveles críticos",
    "alcance": "Estudiantes en niveles críticos (población estimada)",
    "combinado": "Media geométrica de los percentiles de intensidad y alcance",
}

_CRITERIO_A_COLUMNA = {
    "intensidad": "intensidad",
    "alcance": "alcance",
    "combinado": "indice_combinado",
}

# Desempate de cada criterio, para que el orden no dependa del orden de las
# filas que llegaron: siempre se desempata por la otra dimensión y, al final,
# por el código de la unidad.
_DESEMPATES = {
    "intensidad": ["alcance", "codigo"],
    "alcance": ["intensidad", "codigo"],
    "combinado": ["alcance", "intensidad", "codigo"],
}


@dataclass
class Priorizacion:
    """Unidades ordenadas por un criterio, con la hoja de descartes y el resto.

    `tabla` trae una fila por unidad seleccionada, en el orden del criterio
    pedido, con la posición que cada unidad ocupa bajo los tres criterios
    dentro del universo evaluado. `descartadas` trae una fila por unidad que
    quedó fuera, con el motivo.
    """

    criterio: str
    tabla: pd.DataFrame
    universo: pd.DataFrame
    descartadas: pd.DataFrame
    muestra_minima: int
    umbrales: dict[str, Any] = field(default_factory=dict)

    @property
    def n_unidades(self) -> int:
        """Unidades seleccionadas."""
        return int(len(self.tabla))

    @property
    def n_universo(self) -> int:
        """Unidades con muestra suficiente sobre las que se calcularon los índices."""
        return int(len(self.universo))

    @property
    def alcance_total(self) -> float:
        """Estudiantes en niveles críticos de las unidades seleccionadas."""
        return float(self.tabla["alcance"].sum())

    @property
    def alcance_universo(self) -> float:
        """Estudiantes en niveles críticos de todo el universo evaluado."""
        return float(self.universo["alcance"].sum())

    def cobertura(self, total_referencia: float | None = None) -> pd.DataFrame:
        """Cobertura acumulada al atender las primeras N unidades."""
        return cobertura_acumulada(self, total_referencia=total_referencia)

    def resumen(self) -> str:
        """Una línea con lo esencial de la selección."""
        umbrales = ", ".join(
            f"{k} = {v}" for k, v in self.umbrales.items() if v is not None
        )
        texto = (
            f"Criterio {self.criterio}: {self.n_unidades} unidades seleccionadas "
            f"de {self.n_universo} con muestra suficiente, "
            f"{_formato(self.alcance_total, 0)} estudiantes en niveles críticos"
        )
        if umbrales:
            texto += f". Umbrales: {umbrales}"
        return texto + "."


def indice_combinado(
    intensidad: Sequence[float] | pd.Series,
    alcance: Sequence[float] | pd.Series,
) -> np.ndarray:
    """Media geométrica de los percentiles de intensidad y de alcance.

    El percentil es la posición relativa de la unidad dentro del conjunto que
    se le pasa (0 a 1), calculado con el rango promedio en caso de empate. El
    índice queda entre 0 y 1 y vale cero solo si una de las dos dimensiones
    está en el extremo inferior. La justificación de esta forma está en el
    encabezado del módulo.

    Como depende del conjunto, dos corridas sobre conjuntos distintos no son
    comparables entre sí: hay que calcularlo una vez sobre el universo y
    recortar después.
    """
    i = pd.Series(np.asarray(intensidad, dtype=float)).rank(pct=True, method="average")
    a = pd.Series(np.asarray(alcance, dtype=float)).rank(pct=True, method="average")
    return np.sqrt(i.to_numpy() * a.to_numpy())


def _normalizar(
    tabla: pd.DataFrame,
    columna_codigo: str,
    columna_nombre: str | None,
    columna_intensidad: str,
    columna_alcance: str,
    columna_muestra: str | None,
    columna_poblacion: str | None,
    columna_padre: str | None,
) -> pd.DataFrame:
    """Lleva la tabla de entrada a los nombres internos del módulo."""
    faltan = [
        c
        for c in (columna_codigo, columna_intensidad, columna_alcance)
        if c not in tabla.columns
    ]
    if faltan:
        raise KeyError(f"La tabla no tiene las columnas {faltan}.")

    salida = pd.DataFrame(index=tabla.index)
    salida["codigo"] = tabla[columna_codigo].astype(str)
    if columna_nombre and columna_nombre in tabla.columns:
        salida["nombre"] = tabla[columna_nombre]
    if columna_padre and columna_padre in tabla.columns:
        salida["ambito"] = tabla[columna_padre]
    if columna_muestra and columna_muestra in tabla.columns:
        salida["muestra"] = pd.to_numeric(tabla[columna_muestra], errors="coerce")
    if columna_poblacion and columna_poblacion in tabla.columns:
        salida["poblacion"] = pd.to_numeric(tabla[columna_poblacion], errors="coerce")
    salida["intensidad"] = pd.to_numeric(tabla[columna_intensidad], errors="coerce")
    salida["alcance"] = pd.to_numeric(tabla[columna_alcance], errors="coerce")
    return salida


def priorizar(
    tabla: pd.DataFrame,
    criterio: str = "combinado",
    muestra_minima: int = MUESTRA_MINIMA,
    intensidad_minima: float | None = None,
    poblacion_minima: float | None = None,
    top: int | None = None,
    columna_codigo: str = "cod_unidad",
    columna_nombre: str | None = "nom_unidad",
    columna_intensidad: str = "pct_critico",
    columna_alcance: str = "poblacion_critica",
    columna_muestra: str | None = "n_estudiantes",
    columna_poblacion: str | None = "poblacion_estimada",
    columna_padre: str | None = "nom_padre",
) -> Priorizacion:
    """Ordena las unidades por uno de los tres criterios.

    El orden de las operaciones importa:

    1. Se descartan las unidades sin valor y las que tienen menos de
       `muestra_minima` estudiantes evaluados. Es un filtro de calidad del dato,
       no de política: un porcentaje calculado sobre quince estudiantes no
       sostiene una decisión de focalización.
    2. Sobre las que quedan, el universo, se calculan los percentiles, el índice
       combinado y la posición de cada unidad bajo los tres criterios. Así las
       posiciones y el índice describen al país y no a la lista corta.
    3. Recién entonces se aplican los umbrales de política, `intensidad_minima`
       y `poblacion_minima`, que definen qué unidades son candidatas, y el
       recorte `top` a las primeras N.

    La columna `posicion` es el orden dentro de la selección, de 1 a N, y es la
    que la pantalla muestra. Las columnas `pos_intensidad`, `pos_alcance` y
    `pos_combinado` son las posiciones en el universo, que no cambian al mover
    los umbrales.

    Toda unidad descartada queda en `Priorizacion.descartadas` con su motivo.
    """
    if criterio not in CRITERIOS:
        raise ValueError(
            f"Criterio desconocido: {criterio!r}. Válidos: {sorted(CRITERIOS)}."
        )

    datos = _normalizar(
        tabla,
        columna_codigo,
        columna_nombre,
        columna_intensidad,
        columna_alcance,
        columna_muestra,
        columna_poblacion,
        columna_padre,
    )

    motivos = pd.Series("", index=datos.index, dtype="object")
    sin_valor = datos["intensidad"].isna() | datos["alcance"].isna()
    motivos[sin_valor] = "sin valor en intensidad o alcance"
    if "muestra" in datos.columns and muestra_minima > 0:
        chica = datos["muestra"].isna() | (datos["muestra"] < muestra_minima)
        motivos[chica & (motivos == "")] = (
            f"muestra menor que {muestra_minima} estudiantes evaluados"
        )

    universo = datos[motivos == ""].copy()
    descartadas = datos[motivos != ""].copy()
    descartadas["motivo"] = motivos[motivos != ""]
    if len(universo) == 0:
        raise ValueError(
            "Ninguna unidad pasó el filtro de muestra mínima y valores presentes."
        )

    universo["percentil_intensidad"] = universo["intensidad"].rank(
        pct=True, method="average"
    )
    universo["percentil_alcance"] = universo["alcance"].rank(pct=True, method="average")
    universo["indice_combinado"] = indice_combinado(
        universo["intensidad"], universo["alcance"]
    )
    for nombre, columna in _CRITERIO_A_COLUMNA.items():
        universo[f"pos_{nombre}"] = _posiciones(universo, nombre, columna)

    seleccion = universo
    umbrales: dict[str, Any] = {
        "muestra_minima": muestra_minima,
        "intensidad_minima": intensidad_minima,
        "poblacion_minima": poblacion_minima,
        "top": top,
    }
    if intensidad_minima is not None:
        fuera = seleccion["intensidad"] < intensidad_minima
        descartadas = _sumar_descartes(
            descartadas,
            seleccion[fuera],
            f"intensidad menor que {intensidad_minima}",
        )
        seleccion = seleccion[~fuera]
    if poblacion_minima is not None:
        if "poblacion" not in seleccion.columns:
            raise KeyError(
                "Se pidió `poblacion_minima` pero la tabla no trae la columna "
                f"'{columna_poblacion}'."
            )
        fuera = seleccion["poblacion"].isna() | (
            seleccion["poblacion"] < poblacion_minima
        )
        descartadas = _sumar_descartes(
            descartadas,
            seleccion[fuera],
            f"población estimada menor que {poblacion_minima}",
        )
        seleccion = seleccion[~fuera]

    seleccion = _ordenar(seleccion, criterio).reset_index(drop=True)
    if top is not None:
        if top < 1:
            raise ValueError("`top` debe ser al menos 1.")
        descartadas = _sumar_descartes(
            descartadas, seleccion.iloc[top:], f"fuera de las primeras {top}"
        )
        seleccion = seleccion.iloc[:top].copy()
    seleccion.insert(0, "posicion", np.arange(1, len(seleccion) + 1))

    return Priorizacion(
        criterio=criterio,
        tabla=seleccion,
        universo=_ordenar(universo, criterio).reset_index(drop=True),
        descartadas=descartadas.reset_index(drop=True),
        muestra_minima=muestra_minima,
        umbrales=umbrales,
    )


def _posiciones(tabla: pd.DataFrame, criterio: str, columna: str) -> np.ndarray:
    """Posición de cada unidad bajo un criterio, 1 es la más prioritaria.

    `columna` existe porque no siempre se ordena por la columna del criterio. Al
    comparar criterios dentro de un conjunto ya seleccionado, el combinado se ordena por
    el índice recalculado dentro de ese conjunto y no por el del universo. El parámetro
    estaba y no se usaba, así que `pos_combinado` salía del índice del universo: de las
    ocho unidades priorizadas, seis quedaban en un puesto que no era el suyo, y
    Yurimaguas aparecía primera donde el índice local la deja séptima.
    """
    orden = _ordenar(tabla, criterio, columna)
    puesto = pd.Series(np.arange(1, len(orden) + 1), index=orden.index)
    return puesto.reindex(tabla.index).to_numpy()


def _ordenar(
    tabla: pd.DataFrame, criterio: str, columna: str | None = None
) -> pd.DataFrame:
    """Ordena de mayor prioridad a menor, con desempate determinista."""
    columnas = [columna or _CRITERIO_A_COLUMNA[criterio]] + [
        c for c in _DESEMPATES[criterio] if c in tabla.columns
    ]
    ascendente = [False] * len(columnas)
    if columnas[-1] == "codigo":
        ascendente[-1] = True
    return tabla.sort_values(columnas, ascending=ascendente, kind="mergesort")


def _sumar_descartes(
    descartadas: pd.DataFrame, nuevas: pd.DataFrame, motivo: str
) -> pd.DataFrame:
    """Agrega unidades a la hoja de descartes con su motivo."""
    if not len(nuevas):
        return descartadas
    bloque = nuevas.copy()
    bloque["motivo"] = motivo
    return pd.concat([descartadas, bloque], ignore_index=True)


def cobertura_acumulada(
    priorizacion: Priorizacion | pd.DataFrame,
    total_referencia: float | None = None,
) -> pd.DataFrame:
    """Cuántos estudiantes alcanza una intervención en las primeras N unidades.

    Devuelve una fila por valor de N, de 1 al total de unidades seleccionadas,
    con tres lecturas distintas de "alcanzar", que conviene no confundir:

    - `acum_criticos`: estudiantes en niveles críticos de las primeras N
      unidades. Es la cifra que la pantalla llama "estudiantes alcanzados".
    - `acum_poblacion`: todos los estudiantes estimados de esas unidades, en
      cualquier nivel de logro. Es el tamaño operativo de la intervención si
      alcanza a la unidad entera.
    - `pct_criticos_en_lo_atendido`: qué proporción de los estudiantes
      atendidos está en niveles críticos. Baja cuando se agregan unidades
      grandes con rezago moderado.

    `pct_cobertura` es la parte del total de estudiantes en niveles críticos que
    cubren las primeras N unidades. Por omisión el total es el del universo
    evaluado (todas las unidades con muestra suficiente); con
    `total_referencia` se puede pedir contra otro total, por ejemplo el nacional
    del grado y área.
    """
    if isinstance(priorizacion, Priorizacion):
        tabla = priorizacion.tabla
        total = (
            float(total_referencia)
            if total_referencia is not None
            else priorizacion.alcance_universo
        )
    else:
        tabla = priorizacion
        total = (
            float(total_referencia)
            if total_referencia is not None
            else float(pd.to_numeric(tabla["alcance"], errors="coerce").sum())
        )

    if "alcance" not in tabla.columns:
        raise KeyError(
            "La tabla no trae la columna 'alcance': pásale el resultado de "
            "`priorizar`."
        )

    alcance = pd.to_numeric(tabla["alcance"], errors="coerce").fillna(0.0)
    poblacion = (
        pd.to_numeric(tabla["poblacion"], errors="coerce").fillna(0.0)
        if "poblacion" in tabla.columns
        else pd.Series(np.nan, index=tabla.index)
    )

    salida = pd.DataFrame(
        {
            "n_unidades": np.arange(1, len(tabla) + 1),
            "codigo": tabla["codigo"].to_numpy(),
        }
    )
    if "nombre" in tabla.columns:
        salida["nombre"] = tabla["nombre"].to_numpy()
    salida["criticos"] = alcance.to_numpy()
    salida["acum_criticos"] = alcance.cumsum().to_numpy()
    salida["acum_poblacion"] = poblacion.cumsum().to_numpy()
    salida["pct_cobertura"] = (
        100.0 * salida["acum_criticos"] / total if total > 0 else np.nan
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        salida["pct_criticos_en_lo_atendido"] = np.where(
            salida["acum_poblacion"] > 0,
            100.0 * salida["acum_criticos"] / salida["acum_poblacion"],
            np.nan,
        )
    return salida


def ninos_alcanzados(priorizacion: Priorizacion, n: int) -> float:
    """Estudiantes en niveles críticos de las primeras `n` unidades.

    Es el atajo para la tarjeta de resumen de la pantalla. Si `n` supera las
    unidades seleccionadas, devuelve el total de la selección.
    """
    if n < 1:
        raise ValueError("`n` debe ser al menos 1.")
    return float(priorizacion.tabla["alcance"].head(n).sum())


def comparar_criterios(
    priorizacion: Priorizacion | pd.DataFrame,
    orden: str = "desacuerdo",
) -> pd.DataFrame:
    """Posición de cada unidad bajo los tres criterios, dentro del mismo conjunto.

    A diferencia de las columnas `pos_*` que devuelve `priorizar`, que se
    refieren al universo, esta comparación recalcula las posiciones dentro del
    conjunto que recibe. Es lo que hace falta para decir "de las ocho
    priorizadas, esta es la octava por intensidad y la primera por alcance".

    `desacuerdo` es la posición por intensidad menos la posición por alcance:
    positivo cuando la unidad gana puestos al ordenar por alcance, negativo
    cuando los pierde. `orden` admite `desacuerdo` (por magnitud del
    desacuerdo, de mayor a menor) o cualquiera de los tres criterios.

    Cuidado con el índice combinado. Es un percentil, así que su valor depende
    del conjunto sobre el que se calcula, y el que sirve para priorizar es el
    del universo, no el de una lista ya recortada. Esta función conserva
    `indice_combinado` tal como venía y expone el recalculado dentro del
    conjunto en `indice_combinado_local`, que es el que sostiene
    `pos_combinado`. Ordenar por el local invierte el resultado: sobre las ocho
    UGEL priorizadas de 4.° de primaria en Matemática, Yurimaguas pasa del
    primer puesto al séptimo. Para ordenar, usa la tabla de `priorizar`.
    """
    tabla = (
        priorizacion.tabla if isinstance(priorizacion, Priorizacion) else priorizacion
    )
    for columna in ("codigo", "intensidad", "alcance"):
        if columna not in tabla.columns:
            raise KeyError(
                f"La tabla no trae la columna '{columna}': pásale el resultado "
                "de `priorizar`."
            )

    base = tabla.copy().reset_index(drop=True)
    # El percentil se recalcula dentro del conjunto recibido para que las posiciones
    # relativas tengan sentido, pero en una columna aparte: pisar `indice_combinado`
    # haría que ordenar por él diera un orden distinto al de `priorizar`.
    base["indice_combinado_local"] = indice_combinado(
        base["intensidad"], base["alcance"]
    )
    columnas = ["codigo"]
    if "nombre" in base.columns:
        columnas.append("nombre")
    if "ambito" in base.columns:
        columnas.append("ambito")
    if "poblacion" in base.columns:
        columnas.append("poblacion")
    columnas += ["intensidad", "alcance"]

    salida = base[columnas].copy()
    if "indice_combinado" in base.columns:
        salida["indice_combinado"] = base["indice_combinado"]
    salida["indice_combinado_local"] = base["indice_combinado_local"]
    for criterio in CRITERIOS:
        columna = _CRITERIO_A_COLUMNA[criterio]
        if criterio == "combinado":
            columna = "indice_combinado_local"
        salida[f"pos_{criterio}"] = _posiciones(base, criterio, columna)
    salida["desacuerdo"] = salida["pos_intensidad"] - salida["pos_alcance"]

    if orden == "desacuerdo":
        return salida.reindex(
            salida["desacuerdo"].abs().sort_values(ascending=False, kind="mergesort").index
        ).reset_index(drop=True)
    if orden in CRITERIOS:
        return salida.sort_values(f"pos_{orden}", kind="mergesort").reset_index(drop=True)
    raise ValueError(
        f"Orden desconocido: {orden!r}. Válidos: 'desacuerdo' o {sorted(CRITERIOS)}."
    )


def describir_tension(priorizacion: Priorizacion | pd.DataFrame) -> str:
    """Texto sobrio sobre la unidad donde más se contradicen los dos criterios.

    Describe el desacuerdo y nada más: no dice cuál criterio es el correcto,
    porque eso no lo decide el dato.
    """
    comparacion = comparar_criterios(priorizacion, orden="desacuerdo")
    if len(comparacion) < 2:
        return "Con menos de dos unidades no hay orden que comparar."

    fila = comparacion.iloc[0]
    if int(fila["desacuerdo"]) == 0:
        return (
            f"Los dos criterios coinciden en el orden de las "
            f"{len(comparacion)} unidades seleccionadas."
        )

    nombre = fila.get("nombre", fila["codigo"])
    total = len(comparacion)
    intensidad = _formato(fila["intensidad"], 1)
    criticos = _formato(fila["alcance"], 0)
    poblacion = (
        _formato(fila["poblacion"], 0) if "poblacion" in comparacion.columns else None
    )
    detalle_poblacion = (
        f" sobre una población estimada de {poblacion}" if poblacion else ""
    )
    gana = int(fila["desacuerdo"]) > 0

    return (
        f"{nombre} tiene {intensidad} % en niveles críticos"
        f"{detalle_poblacion}, es decir {criticos} estudiantes. "
        f"Entre las {total} unidades seleccionadas queda "
        f"{int(fila['pos_intensidad'])}.ª por intensidad y "
        f"{int(fila['pos_alcance'])}.ª por alcance: "
        + (
            "el criterio de alcance la sube"
            if gana
            else "el criterio de alcance la baja"
        )
        + f" {abs(int(fila['desacuerdo']))} puestos. "
        "Un orden busca dónde el problema es más extendido y el otro, dónde "
        "alcanza a más estudiantes."
    )


def _formato(valor: Any, decimales: int) -> str:
    """Número en formato peruano: coma decimal y espacio de millares."""
    if pd.isna(valor):
        return "sin dato"
    texto = f"{float(valor):,.{decimales}f}"
    return texto.replace(",", " ").replace(".", ",")
