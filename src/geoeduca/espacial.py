"""Autocorrelación espacial de los indicadores agregados de GEO_EDUCA.

El módulo responde una sola pregunta: ¿un indicador se agrupa en el territorio
o se reparte al azar? Para eso calcula el índice de Moran global (una cifra
para todo el conjunto de unidades) y los indicadores locales de asociación
espacial o LISA (una clasificación por unidad).

Qué hace y qué no hace
----------------------
- Recibe un GeoDataFrame ya cargado y devuelve resultados. No abre la base de
  datos, no lee archivos y no escribe nada: la carga vive en la capa de acceso
  a datos y en las pruebas.
- Mide la similitud entre unidades vecinas. No explica por qué los valores se
  parecen: un conglomerado espacial describe un patrón, no una causa.

Decisiones de cálculo
---------------------
*Vecindad.* Contigüidad tipo Queen: dos unidades son vecinas si comparten al
menos un punto de su frontera. La contigüidad es una relación topológica, así
que no se reproyecta nada: las capas de `geo/` están en EPSG:4326 y ahí se
trabajan. Las únicas distancias que este módulo calcula son geodésicas, con
`pyproj.Geod` sobre el elipsoide WGS84, y solo intervienen si se pide enganchar
las islas a su vecino más cercano.

*Muestra mínima.* El filtro se aplica antes de construir la matriz, no después.
Una unidad con pocos estudiantes evaluados trae un porcentaje ruidoso, y si se
la deja dentro contamina dos veces: como valor propio y como vecina de las
demás. Dejarla fuera de la matriz implica que tampoco sirve de puente entre sus
vecinas, que es lo correcto: si no se confía en su valor, no se la puede usar
para transmitir vecindad. El umbral por omisión es 30 estudiantes evaluados, el
mismo de `muestra_suficiente` en el almacén.

*Islas.* Una isla es una unidad que se queda sin ningún vecino. No es un dato
faltante: es una unidad para la que la pregunta "¿te pareces a tus vecinas?" no
tiene respuesta con esta matriz. Con estandarización por filas su fila de pesos
queda en ceros, de modo que su rezago espacial vale 0, que en unidades
estandarizadas es exactamente el promedio: la unidad entraría al cálculo como
si su entorno fuera perfectamente medio, achicando el índice global y recibiendo
una clasificación LISA que no proviene de ninguna vecina. Por eso el
tratamiento por omisión es `excluir`: se las saca del cálculo y se las devuelve
listadas en el resultado, nunca en silencio. Las alternativas son
`vecino_mas_cercano`, que engancha cada isla a la unidad geodésicamente más
cercana y deja el grafo conectado a cambio de inventar una adyacencia que la
cartografía no tiene, y `error`, que levanta excepción.

Excluir islas no genera islas nuevas: la contigüidad es simétrica, de modo que
una isla no figura como vecina de nadie y sacarla no le quita vecinos a ninguna
otra unidad. Lo que sí puede quedar es un territorio partido en varios
componentes, que la matriz informa por separado.

En las capas de este proyecto las islas son reales, no artefactos de la
simplificación: la capa de UGEL se arma disolviendo los distritos que tienen
UGEL asignada, no cubre el territorio de forma continua, y a nivel de UGEL
quedan sin vecinos Caylloma, La Unión y Tarata.

A nivel distrital el filtro de muestra mínima deja fuera a casi la mitad de los
distritos y eso parte el territorio: en 4.º de primaria y Matemática quedan 649
distritos calculables, 29 sin ninguna vecina y 27 componentes separados. El
índice global sigue siendo interpretable, pero resume un territorio con agujeros
y conviene decirlo al reportarlo. Antes de armar la vecindad distrital hay que
pasar los datos por `combinar_unidades_cartograficas`, o la unidad combinada
120699 se queda sin dato y abre un hueco más en el mapa.

*Reproducibilidad.* Los p-valores salen de permutaciones. `esda` permuta con el
generador global de NumPy, así que las funciones fijan la semilla y después
restauran el estado que encontraron, para no alterar el azar del programa que
las llama.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from esda.moran import Moran, Moran_Local
from libpysal.weights import W, Queen, lag_spatial
from pyproj import Geod

# La recomposición de unidades fusionadas vive en la capa de datos, que es de donde
# salen las cifras. Aquí solo se usa, para que haya una sola implementación: tener dos
# dejó durante un tiempo el mapa pintando `n_escuelas` con el valor de uno solo de los
# dos distritos fusionados.
from .almacen import (  # noqa: F401
    COLUMNAS_PONDERADAS,
    COLUMNAS_SUMA,
    NOMBRES_UNIDADES_COMBINADAS,
    UNIDADES_CARTOGRAFICAS_COMBINADAS,
    combinar_unidades_cartograficas,
)

__all__ = [
    "CATEGORIAS_LISA",
    "CLAVES_LISA",
    "MUESTRA_MINIMA",
    "TRATAMIENTOS_ISLAS",
    "UNIDADES_CARTOGRAFICAS_COMBINADAS",
    "Vecindad",
    "MoranGlobal",
    "ResultadoLisa",
    "AutocorrelacionEspacial",
    "filtrar_por_muestra",
    "construir_vecindad",
    "moran_global",
    "lisa",
    "analizar_autocorrelacion",
    "distancia_geodesica_km",
    "combinar_unidades_cartograficas",
    "formato_p",
    "unir_con_geometria",
]

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #

#: Estudiantes evaluados mínimos para que una unidad entre al cálculo.
#: Coincide con la regla `muestra_suficiente` del almacén (meta_almacen).
MUESTRA_MINIMA = 30

#: Las cinco categorías LISA. Las claves son los cuadrantes que devuelve `esda`
#: (1 alto-alto, 2 bajo-alto, 3 bajo-bajo, 4 alto-bajo) más el 0, que este
#: módulo reserva para las unidades cuyo p-valor no alcanza el nivel de
#: significancia pedido. Son categorías cualitativas, sin orden entre ellas.
CATEGORIAS_LISA: Mapping[int, str] = {
    0: "Sin patrón significativo",
    1: "Alto rodeado de alto",
    2: "Bajo rodeado de alto",
    3: "Bajo rodeado de bajo",
    4: "Alto rodeado de bajo",
}

#: Clave corta de cada categoría, para usarla como identificador estable en la
#: interfaz (colores, filtros) sin depender del texto.
CLAVES_LISA: Mapping[int, str] = {
    0: "ns",
    1: "aa",
    2: "ba",
    3: "bb",
    4: "ab",
}

#: Tratamientos admitidos para las unidades que quedan sin vecinos.
TRATAMIENTOS_ISLAS = ("excluir", "vecino_mas_cercano", "error")

#: Unidades que la cartografía publica fusionadas y el almacén tiene separadas.
#: El límite entre Mazamari (120604) y Pangoa (120606) está en litigio y la
#: fuente cartográfica publica un solo polígono con código de distrito 99. Para
#: pintar o para calcular vecindad hay que sumar los dos ubigeos y atribuirlos
#: a la unidad combinada. Documentado en `geo/metadatos_geo.json`, clave
#: `unidades_cartograficas_combinadas`.
_GEOD = Geod(ellps="WGS84")


# --------------------------------------------------------------------------- #
# Resultados
# --------------------------------------------------------------------------- #


@dataclass
class Vecindad:
    """Matriz de contigüidad lista para calcular, con su hoja de descartes.

    `tabla` es el subconjunto de unidades que entró a la matriz, en el mismo
    orden que `w`. `descartadas` lleva una fila por unidad que quedó fuera, con
    el motivo, de modo que ningún descarte sea invisible.
    """

    w: W
    tabla: pd.DataFrame
    columna_codigo: str
    columna_nombre: str | None
    tratamiento_islas: str
    muestra_minima: int
    islas: pd.DataFrame
    enlaces_agregados: pd.DataFrame
    descartadas: pd.DataFrame
    n_componentes: int
    advertencias: list[str] = field(default_factory=list)

    @property
    def n_unidades(self) -> int:
        """Unidades que entraron a la matriz."""
        return int(self.w.n)

    @property
    def n_islas(self) -> int:
        """Unidades que quedaron sin vecinos al construir la contigüidad."""
        return int(len(self.islas))

    @property
    def vecinos_promedio(self) -> float:
        """Promedio de vecinos por unidad."""
        if self.w.n == 0:
            return 0.0
        return float(np.mean(list(self.w.cardinalities.values())))

    def resumen(self) -> str:
        """Una línea con el estado de la matriz, para registro o pantalla."""
        partes = [
            f"{self.n_unidades} unidades",
            f"{self.vecinos_promedio:.1f} vecinos en promedio",
            f"muestra mínima {self.muestra_minima}",
        ]
        if self.n_islas:
            partes.append(f"{self.n_islas} sin vecinos ({self.tratamiento_islas})")
        else:
            partes.append("ninguna unidad sin vecinos")
        if self.n_componentes > 1:
            partes.append(f"{self.n_componentes} componentes desconectados")
        return "Contigüidad Queen: " + "; ".join(partes) + "."


@dataclass
class MoranGlobal:
    """Índice de Moran global de un indicador sobre un conjunto de unidades."""

    indicador: str
    i: float
    valor_esperado: float
    p_valor: float
    z: float
    permutaciones: int
    nivel_significancia: float
    n_unidades: int
    vecindad: Vecindad
    interpretacion: str

    @property
    def significativo(self) -> bool:
        """Verdadero si el p-valor por permutaciones alcanza el nivel pedido."""
        return bool(self.p_valor <= self.nivel_significancia)

    @property
    def islas(self) -> pd.DataFrame:
        """Unidades que quedaron sin vecinos, tal como las reporta la matriz."""
        return self.vecindad.islas

    def resumen(self) -> str:
        """Cifra e interpretación en una sola cadena."""
        return (
            f"I de Moran = {self.i:.4f} (esperado {self.valor_esperado:.4f}), "
            f"{formato_p(self.p_valor, self.permutaciones)} con "
            f"{self.permutaciones} permutaciones, "
            f"{self.n_unidades} unidades. {self.interpretacion}"
        )


@dataclass
class ResultadoLisa:
    """Clasificación LISA de cada unidad en las cinco categorías."""

    indicador: str
    tabla: pd.DataFrame
    permutaciones: int
    nivel_significancia: float
    alternativa: str
    vecindad: Vecindad

    @property
    def conteo(self) -> pd.DataFrame:
        """Unidades por categoría, con las cinco categorías siempre presentes."""
        cuenta = self.tabla["cod_categoria"].value_counts()
        filas = [
            {
                "cod_categoria": cod,
                "clave": CLAVES_LISA[cod],
                "categoria": etiqueta,
                "n_unidades": int(cuenta.get(cod, 0)),
            }
            for cod, etiqueta in CATEGORIAS_LISA.items()
        ]
        return pd.DataFrame(filas)

    @property
    def n_significativas(self) -> int:
        """Unidades con patrón significativo, es decir fuera de la categoría 0."""
        return int((self.tabla["cod_categoria"] != 0).sum())

    @property
    def islas(self) -> pd.DataFrame:
        """Unidades que quedaron sin vecinos, tal como las reporta la matriz."""
        return self.vecindad.islas

    def unidades_de(self, categoria: int | str) -> pd.DataFrame:
        """Filas de una categoría, por código (0 a 4) o por clave ('aa', 'bb')."""
        cod = _codigo_categoria(categoria)
        return self.tabla[self.tabla["cod_categoria"] == cod].copy()


@dataclass
class AutocorrelacionEspacial:
    """Resultado global y local sobre una misma matriz de contigüidad."""

    global_: MoranGlobal
    local: ResultadoLisa
    vecindad: Vecindad


# --------------------------------------------------------------------------- #
# Preparación de los datos
# --------------------------------------------------------------------------- #


def filtrar_por_muestra(
    tabla: pd.DataFrame,
    columna_indicador: str | None = None,
    muestra_minima: int = MUESTRA_MINIMA,
    columna_muestra: str = "n_estudiantes",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa las unidades calculables de las que no lo son.

    Quedan fuera las unidades con menos de `muestra_minima` estudiantes
    evaluados y las que no tienen valor en el indicador. Devuelve dos tablas:
    las que siguen y las descartadas, estas últimas con una columna `motivo`.

    En 4.º de primaria y Matemática, 482 de los 1 165 distritos del almacén
    están por debajo de 30 estudiantes evaluados: sin este filtro el ruido
    muestral entra al cálculo espacial como si fuera señal.
    """
    tabla = tabla.copy()
    motivos = pd.Series("", index=tabla.index, dtype="object")

    if columna_muestra in tabla.columns and muestra_minima > 0:
        muestra = pd.to_numeric(tabla[columna_muestra], errors="coerce")
        chica = muestra.isna() | (muestra < muestra_minima)
        motivos[chica] = f"muestra menor que {muestra_minima} estudiantes evaluados"

    if columna_indicador is not None:
        if columna_indicador not in tabla.columns:
            raise KeyError(
                f"La tabla no tiene la columna del indicador '{columna_indicador}'."
            )
        valor = pd.to_numeric(tabla[columna_indicador], errors="coerce")
        sin_valor = valor.isna()
        # Los dos casos se separan antes de escribir nada. Encadenando las dos
        # asignaciones, la segunda volvía a alcanzar a las filas que acababa de llenar
        # la primera y les concatenaba el mismo motivo: una unidad con muestra
        # suficiente y sin valor salía con "sin valor en X; sin valor en X".
        ya_tenia_motivo = motivos != ""
        motivos[sin_valor & ~ya_tenia_motivo] = f"sin valor en '{columna_indicador}'"
        a_concatenar = sin_valor & ya_tenia_motivo
        motivos[a_concatenar] = motivos[a_concatenar].map(
            lambda m: f"{m}; sin valor en '{columna_indicador}'"
        )

    fuera = motivos != ""
    descartadas = tabla[fuera].copy()
    descartadas["motivo"] = motivos[fuera]
    return tabla[~fuera].copy(), descartadas


def unir_con_geometria(
    capa: Any,
    tabla: pd.DataFrame,
    columna_geo: str,
    columna_datos: str = "cod_unidad",
    combinar_cartograficas: bool = False,
    **opciones_combinar: Any,
) -> tuple[Any, pd.DataFrame]:
    """Une una capa con una tabla de indicadores y reporta lo que no calza.

    Devuelve la capa unida (solo las unidades con dato) y una tabla de
    diagnóstico con una fila por desencuentro: unidades de la capa que se
    quedaron sin dato y unidades con dato que no tienen geometría. Esa segunda
    lista no es un error del cruce: son 10 distritos creados después de la fecha
    de validez de la cartografía, el 0,56 % de la población estimada, y sus
    estudiantes siguen contando en los agregados por UGEL, DRE y nacional.

    Con `combinar_cartograficas=True` suma antes las unidades que la cartografía
    publica fusionadas (ver `combinar_unidades_cartograficas`), que es lo que
    corresponde al unir a nivel distrital.
    """
    if combinar_cartograficas:
        tabla = combinar_unidades_cartograficas(
            tabla, columna_codigo=columna_datos, **opciones_combinar
        )

    izquierda = capa.copy()
    izquierda[columna_geo] = izquierda[columna_geo].astype(str)
    derecha = tabla.copy()
    derecha[columna_datos] = derecha[columna_datos].astype(str)

    unida = izquierda.merge(
        derecha, left_on=columna_geo, right_on=columna_datos, how="inner"
    )

    con_geometria = set(izquierda[columna_geo])
    con_dato = set(derecha[columna_datos])
    diagnostico = pd.DataFrame(
        [
            {"codigo": cod, "situacion": "geometría sin dato"}
            for cod in sorted(con_geometria - con_dato)
        ]
        + [
            {"codigo": cod, "situacion": "dato sin geometría"}
            for cod in sorted(con_dato - con_geometria)
        ],
        columns=["codigo", "situacion"],
    )
    return unida, diagnostico


# --------------------------------------------------------------------------- #
# Vecindad
# --------------------------------------------------------------------------- #


def distancia_geodesica_km(
    lon_a: float, lat_a: float, lon_b: float, lat_b: float
) -> float:
    """Distancia geodésica en kilómetros sobre el elipsoide WGS84.

    Las capas están en EPSG:4326 y no se reproyectan. Cuando hace falta una
    distancia métrica, se calcula sobre el elipsoide con `pyproj.Geod`, no
    tratando los grados como si fueran metros.
    """
    _, _, metros = _GEOD.inv(lon_a, lat_a, lon_b, lat_b)
    return float(metros) / 1000.0


def construir_vecindad(
    capa: Any,
    columna_indicador: str | None = None,
    columna_codigo: str = "cod_unidad",
    columna_nombre: str | None = "nom_unidad",
    muestra_minima: int = MUESTRA_MINIMA,
    columna_muestra: str = "n_estudiantes",
    tratamiento_islas: str = "excluir",
) -> Vecindad:
    """Arma la matriz de contigüidad Queen del subconjunto calculable.

    Orden de las operaciones, que no es indiferente: primero se descartan las
    unidades sin valor o con muestra insuficiente, después se construye la
    contigüidad sobre las que quedan, y al final se tratan las islas. Construir
    la matriz antes de filtrar dejaría que una unidad descartada por ruidosa
    sirva de puente entre dos unidades que no se tocan.

    `tratamiento_islas` admite:

    - `excluir` (por omisión): las unidades sin vecinos salen del cálculo y
      quedan listadas en `Vecindad.islas`.
    - `vecino_mas_cercano`: cada isla se engancha a la unidad geodésicamente
      más cercana, con enlace recíproco. El grafo queda conectado a costa de
      una adyacencia que la cartografía no tiene; los enlaces agregados quedan
      en `Vecindad.enlaces_agregados` con su distancia en kilómetros.
    - `error`: levanta `ValueError` si hay islas.
    """
    if tratamiento_islas not in TRATAMIENTOS_ISLAS:
        raise ValueError(
            f"tratamiento_islas debe ser uno de {TRATAMIENTOS_ISLAS}, "
            f"no {tratamiento_islas!r}."
        )
    if columna_codigo not in capa.columns:
        raise KeyError(f"La capa no tiene la columna '{columna_codigo}'.")

    advertencias: list[str] = []
    tabla, descartadas = filtrar_por_muestra(
        capa,
        columna_indicador=columna_indicador,
        muestra_minima=muestra_minima,
        columna_muestra=columna_muestra,
    )
    tabla = tabla.reset_index(drop=True)
    if len(tabla) < 3:
        raise ValueError(
            "Quedan menos de tres unidades con valor y muestra suficiente: "
            "no hay con qué calcular contigüidad."
        )
    if len(descartadas):
        advertencias.append(
            f"{len(descartadas)} unidades quedaron fuera del cálculo "
            f"(ver `descartadas`)."
        )

    tabla, w, islas, advertencias_islas = _resolver_islas(
        tabla, tratamiento_islas, columna_codigo, columna_nombre
    )
    advertencias.extend(advertencias_islas)

    enlaces = _enlaces_vecino_mas_cercano(tabla, islas, columna_codigo, columna_nombre)
    if tratamiento_islas == "vecino_mas_cercano" and len(islas):
        w = _enganchar(w, enlaces, tabla, columna_codigo)
    else:
        enlaces = enlaces.iloc[0:0]

    if len(islas) and tratamiento_islas == "excluir":
        descartadas = pd.concat(
            [descartadas, islas.assign(motivo="sin vecinos (isla)")],
            ignore_index=True,
        )

    w.transform = "r"
    n_componentes = int(getattr(w, "n_components", 1) or 1)
    if n_componentes > 1:
        advertencias.append(
            f"La matriz tiene {n_componentes} componentes desconectados: el "
            "índice global resume un territorio que no es continuo."
        )

    return Vecindad(
        w=w,
        tabla=tabla,
        columna_codigo=columna_codigo,
        columna_nombre=columna_nombre,
        tratamiento_islas=tratamiento_islas,
        muestra_minima=muestra_minima,
        islas=islas.reset_index(drop=True),
        enlaces_agregados=enlaces.reset_index(drop=True),
        descartadas=descartadas.reset_index(drop=True),
        n_componentes=n_componentes,
        advertencias=advertencias,
    )


def _queen(tabla: Any) -> tuple[W, list[str]]:
    """Contigüidad Queen en EPSG:4326, sin reproyectar, recogiendo avisos."""
    with warnings.catch_warnings(record=True) as capturados:
        warnings.simplefilter("always")
        w = Queen.from_dataframe(tabla, use_index=False)
    avisos = [
        " ".join(str(aviso.message).split())
        for aviso in capturados
        if "not fully connected" in str(aviso.message)
    ]
    return w, avisos


def _resolver_islas(
    tabla: Any,
    tratamiento: str,
    columna_codigo: str,
    columna_nombre: str | None,
) -> tuple[Any, W, pd.DataFrame, list[str]]:
    """Construye la contigüidad y aplica el tratamiento de islas elegido."""
    advertencias: list[str] = []

    w, avisos = _queen(tabla)
    advertencias.extend(avisos)

    if tratamiento != "excluir":
        islas = _describir(tabla, list(w.islands), columna_codigo, columna_nombre)
        if len(islas) and tratamiento == "error":
            nombres = ", ".join(islas["codigo"].astype(str))
            raise ValueError(
                f"{len(islas)} unidades quedaron sin vecinos ({nombres}). "
                "Elige 'excluir' o 'vecino_mas_cercano' para seguir."
            )
        if len(islas):
            advertencias.append(
                f"{len(islas)} unidades sin vecinos enganchadas a su vecino más "
                "cercano: la adyacencia es una decisión del análisis, no de la "
                "cartografía."
            )
        return tabla, w, islas, advertencias

    # `excluir`: una sola pasada alcanza. La contigüidad es simétrica, así que
    # una isla no es vecina de nadie y sacarla no le quita vecinos a ninguna
    # otra unidad: no puede aparecer una isla nueva. Lo que sí puede quedar es
    # un territorio partido en varios componentes, que se informa aparte.
    islas = _describir(tabla, list(w.islands), columna_codigo, columna_nombre)
    if len(islas):
        quedan = [i for i in range(len(tabla)) if i not in set(w.islands)]
        if len(quedan) < 3:
            raise ValueError(
                "Al excluir las unidades sin vecinos quedan menos de tres: "
                "no hay con qué calcular autocorrelación."
            )
        tabla = tabla.iloc[quedan].reset_index(drop=True)
        w, avisos = _queen(tabla)
        advertencias.extend(a for a in avisos if a not in advertencias)
        advertencias.append(
            f"{len(islas)} unidades quedaron sin vecinos y se excluyeron del "
            "cálculo: sin vecinas no hay promedio del entorno con el que compararlas."
        )
    return tabla, w, islas, advertencias


def _describir(
    tabla: Any,
    posiciones: Sequence[int],
    columna_codigo: str,
    columna_nombre: str | None,
) -> pd.DataFrame:
    """Las filas de la capa para un conjunto de posiciones, con alias de identidad.

    Devuelve todas las columnas salvo la geometría y añade `codigo` y `nombre` como
    alias de las dos que identifican a la unidad. Quien solo quiera nombrarlas tiene
    esos dos; quien concatene este resultado con otra tabla de la misma capa, como la
    de descartes, conserva el resto y no se queda con una fila de nulos.
    """
    trozo = tabla.iloc[list(posiciones)].copy()
    geometria = getattr(tabla, "geometry", None)
    if geometria is not None and geometria.name in trozo.columns:
        trozo = trozo.drop(columns=[geometria.name])
    trozo = pd.DataFrame(trozo)
    trozo["codigo"] = trozo[columna_codigo]
    if columna_nombre and columna_nombre in trozo.columns:
        trozo["nombre"] = trozo[columna_nombre]
    return trozo.reset_index(drop=True)


def _puntos_representativos(tabla: Any) -> np.ndarray:
    """Un punto interior por unidad, en grados (lon, lat), sin reproyectar."""
    puntos = tabla.geometry.representative_point()
    return np.column_stack([puntos.x.to_numpy(), puntos.y.to_numpy()])


def _enlaces_vecino_mas_cercano(
    tabla: Any,
    islas: pd.DataFrame,
    columna_codigo: str,
    columna_nombre: str | None,
) -> pd.DataFrame:
    """Para cada isla, la unidad más cercana en distancia geodésica."""
    if not len(islas):
        return pd.DataFrame(
            columns=["codigo_isla", "nombre_isla", "codigo_vecino", "nombre_vecino", "distancia_km"]
        )

    puntos = _puntos_representativos(tabla)
    codigos = tabla[columna_codigo].astype(str).to_numpy()
    nombres = (
        tabla[columna_nombre].astype(str).to_numpy()
        if columna_nombre and columna_nombre in tabla.columns
        else codigos
    )
    por_codigo = {cod: i for i, cod in enumerate(codigos)}

    filas = []
    for _, isla in islas.iterrows():
        i = por_codigo.get(str(isla["codigo"]))
        if i is None:
            continue
        distancias = np.array(
            [
                np.inf
                if j == i
                else distancia_geodesica_km(
                    puntos[i, 0], puntos[i, 1], puntos[j, 0], puntos[j, 1]
                )
                for j in range(len(codigos))
            ]
        )
        j = int(np.argmin(distancias))
        filas.append(
            {
                "codigo_isla": codigos[i],
                "nombre_isla": nombres[i],
                "codigo_vecino": codigos[j],
                "nombre_vecino": nombres[j],
                "distancia_km": round(float(distancias[j]), 3),
            }
        )
    return pd.DataFrame(filas)


def _enganchar(w: W, enlaces: pd.DataFrame, tabla: Any, columna_codigo: str) -> W:
    """Agrega los enlaces recíprocos isla - vecino a la matriz de contigüidad."""
    codigos = tabla[columna_codigo].astype(str).to_numpy()
    por_codigo = {cod: i for i, cod in enumerate(codigos)}
    vecinos = {k: list(v) for k, v in w.neighbors.items()}
    for _, enlace in enlaces.iterrows():
        i = por_codigo[str(enlace["codigo_isla"])]
        j = por_codigo[str(enlace["codigo_vecino"])]
        if j not in vecinos[i]:
            vecinos[i].append(j)
        if i not in vecinos[j]:
            vecinos[j].append(i)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return W(vecinos, id_order=list(range(len(codigos))))


# --------------------------------------------------------------------------- #
# Moran global y LISA
# --------------------------------------------------------------------------- #


def _vecindad_de(capa_o_vecindad: Any, columna_indicador: str, **opciones: Any) -> Vecindad:
    """Acepta una capa o una `Vecindad` ya construida, para no recalcularla."""
    if isinstance(capa_o_vecindad, Vecindad):
        return capa_o_vecindad
    return construir_vecindad(
        capa_o_vecindad, columna_indicador=columna_indicador, **opciones
    )


def _valores(vecindad: Vecindad, columna_indicador: str) -> np.ndarray:
    if columna_indicador not in vecindad.tabla.columns:
        raise KeyError(
            f"La tabla de la vecindad no tiene la columna '{columna_indicador}'."
        )
    valores = pd.to_numeric(
        vecindad.tabla[columna_indicador], errors="coerce"
    ).to_numpy(dtype=float)
    if np.isnan(valores).any():
        raise ValueError(
            f"Hay valores faltantes en '{columna_indicador}' dentro de la "
            "vecindad: construye la vecindad con ese mismo indicador."
        )
    return valores


def moran_global(
    capa: Any,
    columna_indicador: str,
    permutaciones: int = 999,
    nivel_significancia: float = 0.05,
    semilla: int | None = 42,
    **opciones_vecindad: Any,
) -> MoranGlobal:
    """Índice de Moran global de un indicador, con p-valor por permutaciones.

    `capa` puede ser un GeoDataFrame con los indicadores ya unidos o una
    `Vecindad` ya construida, para reusar la matriz entre cálculos.

    El índice compara cada unidad con el promedio de sus vecinas. Un valor
    positivo y significativo dice que los valores parecidos tienden a estar
    juntos; uno negativo, que tienden a alternarse; uno no significativo, que no
    se distingue de un reparto al azar del mismo conjunto de valores sobre el
    mismo mapa. El p-valor es pseudo: sale de comparar el índice observado con
    el de `permutaciones` reordenamientos al azar de los valores entre unidades.
    """
    vecindad = _vecindad_de(capa, columna_indicador, **opciones_vecindad)
    valores = _valores(vecindad, columna_indicador)

    with _azar_fijo(semilla):
        moran = Moran(valores, vecindad.w, transformation="r", permutations=permutaciones)

    interpretacion = _interpretar_moran(
        float(moran.I), float(moran.p_sim), nivel_significancia, vecindad,
        int(permutaciones),
    )
    return MoranGlobal(
        indicador=columna_indicador,
        i=float(moran.I),
        valor_esperado=float(moran.EI),
        p_valor=float(moran.p_sim),
        z=float(moran.z_sim),
        permutaciones=int(permutaciones),
        nivel_significancia=float(nivel_significancia),
        n_unidades=vecindad.n_unidades,
        vecindad=vecindad,
        interpretacion=interpretacion,
    )


def lisa(
    capa: Any,
    columna_indicador: str,
    permutaciones: int = 999,
    nivel_significancia: float = 0.05,
    semilla: int | None = 42,
    alternativa: str = "directed",
    **opciones_vecindad: Any,
) -> ResultadoLisa:
    """Clasificación LISA de cada unidad en las cinco categorías, con p-valor.

    Devuelve una tabla con una fila por unidad: su valor, el promedio
    estandarizado de sus vecinas (`rezago_z`), el indicador local, el p-valor
    por permutaciones y la categoría. Las unidades cuyo p-valor no alcanza
    `nivel_significancia` van a "Sin patrón significativo", sin importar en qué
    cuadrante caigan: el cuadrante solo describe la posición de la unidad y de
    su entorno respecto del promedio, y sin significancia esa posición puede ser
    azar.

    El p-valor es local y se calcula una vez por unidad, de modo que al mirar
    cientos de unidades a la vez algunas resultan significativas por azar. La
    tabla incluye `p_valor` para que la interfaz pueda ser explícita al respecto.

    `alternativa` elige la hipótesis alternativa del p-valor por permutaciones y
    se pasa explícita a `esda` para que el resultado no dependa de la versión de
    la librería. `directed` es el p-valor condicional de una cola, el que usa
    GeoDa y con el que se publicaron las cifras de este proyecto;
    `two-sided` es de dos colas y da p-valores cercanos al doble, de modo que
    clasifica menos unidades como significativas.
    """
    vecindad = _vecindad_de(capa, columna_indicador, **opciones_vecindad)
    valores = _valores(vecindad, columna_indicador)

    with _azar_fijo(semilla):
        local = Moran_Local(
            valores,
            vecindad.w,
            transformation="r",
            permutations=permutaciones,
            seed=semilla,
            alternative=alternativa,
        )

    desviacion = valores.std()
    z = (valores - valores.mean()) / desviacion if desviacion > 0 else valores * 0.0
    rezago_z = lag_spatial(vecindad.w, z)

    p_valor = np.asarray(local.p_sim, dtype=float)
    cuadrante = np.asarray(local.q, dtype=int)
    cod_categoria = np.where(p_valor <= nivel_significancia, cuadrante, 0)

    columnas = {
        "codigo": vecindad.tabla[vecindad.columna_codigo].astype(str).to_numpy(),
    }
    if vecindad.columna_nombre and vecindad.columna_nombre in vecindad.tabla.columns:
        columnas["nombre"] = vecindad.tabla[vecindad.columna_nombre].to_numpy()
    columnas.update(
        {
            "valor": valores,
            "valor_z": z,
            "rezago_z": np.asarray(rezago_z, dtype=float),
            "i_local": np.asarray(local.Is, dtype=float),
            "p_valor": p_valor,
            "cuadrante": cuadrante,
            "cod_categoria": cod_categoria,
            "clave": [CLAVES_LISA[int(c)] for c in cod_categoria],
            "categoria": [CATEGORIAS_LISA[int(c)] for c in cod_categoria],
            "significativa": p_valor <= nivel_significancia,
        }
    )
    tabla = pd.DataFrame(columnas)
    tabla.insert(len(tabla.columns), "n_vecinos", [
        vecindad.w.cardinalities[i] for i in range(vecindad.w.n)
    ])

    return ResultadoLisa(
        indicador=columna_indicador,
        tabla=tabla,
        permutaciones=int(permutaciones),
        nivel_significancia=float(nivel_significancia),
        alternativa=alternativa,
        vecindad=vecindad,
    )


def analizar_autocorrelacion(
    capa: Any,
    columna_indicador: str,
    permutaciones: int = 999,
    nivel_significancia: float = 0.05,
    semilla: int | None = 42,
    alternativa: str = "directed",
    **opciones_vecindad: Any,
) -> AutocorrelacionEspacial:
    """Moran global y LISA sobre una sola matriz de contigüidad.

    Es la entrada que conviene a la interfaz: construye la vecindad una vez,
    informa los descartes una vez y devuelve los dos resultados consistentes
    entre sí.
    """
    vecindad = _vecindad_de(capa, columna_indicador, **opciones_vecindad)
    return AutocorrelacionEspacial(
        global_=moran_global(
            vecindad,
            columna_indicador,
            permutaciones=permutaciones,
            nivel_significancia=nivel_significancia,
            semilla=semilla,
        ),
        local=lisa(
            vecindad,
            columna_indicador,
            permutaciones=permutaciones,
            nivel_significancia=nivel_significancia,
            semilla=semilla,
            alternativa=alternativa,
        ),
        vecindad=vecindad,
    )


def formato_p(p_valor: float, permutaciones: int) -> str:
    """El p por permutaciones, escrito como lo que es.

    `esda` lo calcula como (mayores + 1) / (permutaciones + 1), así que con 999
    permutaciones la rejilla de valores posibles empieza en 0,001 y ese es el mínimo
    alcanzable. Escribirlo como igualdad afirma una precisión que la prueba no tiene:
    0,001 significa que ninguna permutación alcanzó el índice observado, no que la
    probabilidad medida sea exactamente esa. En los quince cortes reales del almacén las
    quince devuelven el tope.
    """
    minimo = 1.0 / (permutaciones + 1)
    # Los decimales salen del propio tope: con 9 999 permutaciones el mínimo es 0,0001 y
    # con tres decimales se redondearía a cero.
    decimales = max(3, int(math.ceil(-math.log10(minimo))))
    valor, signo = (minimo, "≤") if p_valor <= minimo else (p_valor, "=")
    return f"p {signo} " + f"{valor:.{decimales}f}".replace(".", ",")


def _interpretar_moran(
    i: float, p_valor: float, nivel: float, vecindad: Vecindad, permutaciones: int
) -> str:
    """Lectura sobria del índice: qué dice el estadístico y nada más."""
    p = formato_p(p_valor, permutaciones)
    if p_valor > nivel:
        texto = (
            "Con este indicador y esta vecindad, el reparto de los valores en el "
            "territorio no se distingue del azar: el índice observado cabe dentro "
            "de lo que producen las permutaciones "
            f"({p}, por encima de {nivel:g})."
        )
    elif i > 0:
        texto = (
            "Los valores se agrupan en el territorio: las unidades vecinas se "
            "parecen más entre sí de lo que se parecerían si los mismos valores "
            f"se repartieran al azar sobre el mismo mapa ({p}). "
            "El índice mide esa similitud, no sus causas."
        )
    else:
        texto = (
            "Los valores se alternan en el territorio: las unidades vecinas se "
            "parecen menos entre sí de lo que se parecerían con un reparto al "
            f"azar sobre el mismo mapa ({p}). El índice mide esa "
            "disimilitud, no sus causas."
        )
    detalle = [f"Calculado sobre {vecindad.n_unidades} unidades"]
    if vecindad.muestra_minima:
        detalle.append(
            f"con al menos {vecindad.muestra_minima} estudiantes evaluados"
        )
    if vecindad.n_islas:
        trato = (
            "excluidas del cálculo"
            if vecindad.tratamiento_islas == "excluir"
            else "enganchadas a su vecino más cercano"
        )
        detalle.append(f"{vecindad.n_islas} sin vecinos, {trato}")
    return texto + " " + ", ".join(detalle) + "."


class _azar_fijo:
    """Fija la semilla global de NumPy y restaura el estado al salir.

    `esda` permuta con el generador global de NumPy y la clase `Moran` no
    recibe semilla, así que esta es la única forma de obtener p-valores
    reproducibles sin dejar alterado el azar del programa que llama.
    """

    def __init__(self, semilla: int | None):
        self.semilla = semilla
        self.estado = None

    def __enter__(self):
        if self.semilla is not None:
            self.estado = np.random.get_state()
            np.random.seed(self.semilla)
        return self

    def __exit__(self, *_):
        if self.estado is not None:
            np.random.set_state(self.estado)
        return False


def _codigo_categoria(categoria: int | str) -> int:
    """Traduce una clave ('aa') o un código (1) a código de categoría LISA."""
    if isinstance(categoria, str):
        for cod, clave in CLAVES_LISA.items():
            if clave == categoria:
                return cod
        raise ValueError(
            f"Categoría LISA desconocida: {categoria!r}. "
            f"Claves válidas: {sorted(CLAVES_LISA.values())}."
        )
    if int(categoria) not in CATEGORIAS_LISA:
        raise ValueError(
            f"Código de categoría LISA desconocido: {categoria!r}. "
            f"Códigos válidos: {sorted(CATEGORIAS_LISA)}."
        )
    return int(categoria)
