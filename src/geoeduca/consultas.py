"""Validación y ejecución de las consultas que escribe el asistente.

El riesgo de un agente que escribe SQL sobre estos datos no es que la consulta falle.
Una consulta que falla se corrige: devuelve un error, se reintenta y ya está. El riesgo
real es la consulta que funciona y devuelve un número equivocado.

`AVG(medida500)` sobre el hecho no da ningún error: devuelve 486,3 en lugar de 490,1,
porque ignora los pesos muestrales. Es una diferencia de casi cuatro puntos presentada
con total naturalidad, y nada en la respuesta delata el problema.

Por eso la validación no se limita a impedir escrituras. Analiza el árbol sintáctico que
devuelve DuckDB y rechaza las agregaciones sobre los microdatos que no usan el peso,
explicando por qué, de modo que el agente pueda corregirse. Analizar el árbol en lugar de
buscar patrones en el texto evita tanto los falsos positivos (la palabra `peso` dentro de
una cadena) como las evasiones triviales (comentarios, mayúsculas, espacios).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable

import duckdb
import pandas as pd

from . import almacen

# Tablas que el asistente puede consultar. Las de metadatos entran porque documentan el
# propio almacén y sirven para responder preguntas sobre su contenido.
TABLAS_PERMITIDAS = {
    "hechos_estudiante_area",
    "resultados_geograficos",
    "resultados_desagregado",
    "brechas",
    "dim_grado",
    "dim_area_evaluada",
    "dim_nivel_logro",
    "dim_departamento",
    "dim_provincia",
    "dim_distrito",
    "dim_dre",
    "dim_ugel",
    "dim_ie",
    "meta_almacen",
    "meta_diccionario",
    "meta_validacion",
    "meta_rango_medida",
}

# La tabla de microdatos: es la única sobre la que una agregación sin peso produce una
# cifra equivocada. Los agregados ya vienen ponderados desde la ingesta.
TABLA_MICRODATO = "hechos_estudiante_area"

# Las dos columnas que parten el microdato. El hecho trae una fila por estudiante y área,
# con el peso de esa área, así que agregar sin fijar las dos mezcla pesos que no son
# intercambiables y cuenta a cada estudiante de secundaria tres o cuatro veces: SUM(peso)
# sin `cod_area` da 1 721 256 donde la población de 2.° de secundaria es 573 752. El error
# de partición es mayor que el de ponderación.
COLUMNAS_DE_PARTICION = ("grado", "cod_area")

# Las únicas agregaciones que sobre el microdato dan una cifra correcta sin el peso: el
# mínimo y el máximo son valores observados, y contar filas describe la muestra.
AGREGACIONES_EXENTAS = frozenset({"count", "count_star", "min", "max"})

AGREGACIONES_DE_CONTEO = frozenset({"count", "count_star"})

# Macros que agregan sin que el catálogo de DuckDB las llame agregación.
MACROS_AGREGADAS = frozenset({
    "geomean", "geometric_mean", "list_avg", "list_sum", "weighted_avg", "wavg",
})

# Columnas de las tablas ya agregadas que no se pueden promediar entre unidades: cada
# fila viene ponderada, pero las unidades tienen tamaños distintos. El promedio simple de
# `pct_satisfactorio` por departamento da 30,4 % donde el nacional es 32,7 %.
PREFIJOS_NO_PROMEDIABLES = ("pct_", "medida_")


@lru_cache(maxsize=1)
def _agregaciones_conocidas() -> frozenset[str]:
    """Agregaciones según el propio DuckDB, más las macros que agregan.

    Se le pregunta al motor en lugar de mantener una lista a mano. Una lista escrita a
    mano siempre se queda corta: por una escrita a mano entraban `favg`, `fsum`, `mad`,
    `reservoir_quantile`, `product`, `entropy` y una docena más, todas sin ponderar.
    """
    with duckdb.connect() as con:
        filas = con.execute(
            "select distinct lower(function_name) from duckdb_functions() "
            "where function_type = 'aggregate'"
        ).fetchall()
    return frozenset(fila[0] for fila in filas) | MACROS_AGREGADAS

# Funciones que leen o escriben fuera del almacén. Ninguna tiene uso legítimo aquí.
FUNCIONES_PROHIBIDAS = {
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
    "read_text", "read_blob", "glob", "copy_to", "install", "load",
    "sniff_csv", "parquet_scan", "csv_scan", "shell", "getenv",
}

LIMITE_FILAS = 500


@dataclass
class Validacion:
    """Resultado de revisar una consulta antes de ejecutarla."""

    permitida: bool
    motivo: str = ""
    sugerencia: str = ""
    advertencias: list[str] = field(default_factory=list)
    tablas: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        return self.permitida

    def explicacion(self) -> str:
        """Texto para devolverle al agente cuando la consulta se rechaza."""
        partes = [self.motivo]
        if self.sugerencia:
            partes.append(self.sugerencia)
        return "\n\n".join(p for p in partes if p)


def _recorrer(nodo: Any) -> Iterable[dict]:
    """Recorre el árbol sintáctico y va entregando cada diccionario que encuentra."""
    if isinstance(nodo, dict):
        yield nodo
        for valor in nodo.values():
            yield from _recorrer(valor)
    elif isinstance(nodo, list):
        for elemento in nodo:
            yield from _recorrer(elemento)


def _arbol(sql: str) -> dict:
    """Árbol sintáctico de la consulta, tal como lo devuelve DuckDB."""
    with duckdb.connect() as con:
        crudo = con.execute("select json_serialize_sql(?)", [sql]).fetchone()[0]
    return json.loads(crudo)


def _nombres_de_funciones(arbol: Any) -> set[str]:
    """Nombres de función del árbol, de llamada normal o de ventana.

    Las dos clases juntas, porque una agregación escrita con OVER se serializa como
    `WINDOW` y no como `FUNCTION`: mirando solo `FUNCTION`, `avg(medida500) over ()`
    resultaba invisible y atravesaba la regla del peso sin una sola advertencia.
    """
    nombres = set()
    for nodo in _recorrer(arbol):
        if nodo.get("class") in ("FUNCTION", "WINDOW") and isinstance(
            nodo.get("function_name"), str
        ):
            nombres.add(nodo["function_name"].lower())
    return nombres


def _tablas_referenciadas(arbol: Any) -> set[str]:
    tablas = set()
    for nodo in _recorrer(arbol):
        if nodo.get("type") == "BASE_TABLE" and isinstance(nodo.get("table_name"), str):
            tablas.add(nodo["table_name"].lower())
    return tablas


def _nombres_de_cte(arbol: Any) -> set[str]:
    """Alias declarados con WITH.

    Un CTE se referencia como si fuera tabla base, así que sin esto una consulta
    correctamente ponderada se rechazaba con un motivo falso: que la tabla no existe.
    """
    nombres = set()
    for nodo in _recorrer(arbol):
        mapa = nodo.get("cte_map")
        if isinstance(mapa, dict):
            for entrada in mapa.get("map") or []:
                clave = entrada.get("key")
                if isinstance(clave, str):
                    nombres.add(clave.lower())
    return nombres


def _usa_funcion_de_tabla(arbol: Any) -> bool:
    """Si la consulta lee de una función en lugar de una tabla.

    `query_table('hechos_estudiante_area')` devuelve el microdato sin que aparezca
    ninguna tabla base, de modo que esquivaba a la vez la lista blanca y la regla del
    peso. Aquí no hace falta ninguna: se rechazan todas.
    """
    return any(nodo.get("type") == "TABLE_FUNCTION" for nodo in _recorrer(arbol))


def _usa_show(arbol: Any) -> bool:
    """Si la consulta es un SUMMARIZE o un DESCRIBE.

    `summarize select medida500 from hechos_estudiante_area` entrega el promedio sin
    ponderar ya etiquetado como `avg`, en una línea y sin ninguna función a la vista.
    """
    return any(nodo.get("type") == "SHOW_REF" for nodo in _recorrer(arbol))


def _columnas_de(nodo: Any) -> set[str]:
    """Columnas referenciadas dentro de un nodo."""
    nombres = set()
    for sub in _recorrer(nodo):
        if sub.get("class") == "COLUMN_REF":
            for nombre in sub.get("column_names") or []:
                if isinstance(nombre, str):
                    nombres.add(nombre.lower())
    return nombres


def _nombre_si_agrega(nodo: dict) -> str | None:
    """Nombre de la agregación, si el nodo es una."""
    nombre = nodo.get("function_name")
    if not isinstance(nombre, str):
        return None
    nombre = nombre.lower()
    if nodo.get("class") == "WINDOW":
        return nombre
    if nodo.get("class") == "FUNCTION" and nombre in _agregaciones_conocidas():
        return nombre
    return None


def _agregaciones(arbol: Any) -> list[tuple[str, set[str]]]:
    """Cada agregación del árbol con las columnas de sus propios argumentos.

    Lo que importa es dónde está el peso, no si aparece. Buscarlo en cualquier parte del
    árbol dejaba pasar `SELECT AVG(medida500), SUM(peso)`, que devuelve 486,3.
    """
    encontradas = []
    for nodo in _recorrer(arbol):
        nombre = _nombre_si_agrega(nodo)
        if nombre:
            encontradas.append((nombre, _columnas_de(nodo.get("arguments") or [])))
    return encontradas


def _divide_conteos(arbol: Any) -> bool:
    """Si la consulta divide un conteo entre otro.

    Es la forma natural de pedir una proporción y es la forma equivocada:
    `COUNT(*) FILTER (WHERE es_satisfactorio) / COUNT(*)` da 30,6 % donde la cifra
    oficial es 32,7 %, que es exactamente la diferencia que este módulo existe para
    evitar.
    """
    for nodo in _recorrer(arbol):
        if nodo.get("class") != "FUNCTION":
            continue
        if nodo.get("function_name") not in ("/", "//"):
            continue
        for argumento in nodo.get("arguments") or []:
            for sub in _recorrer(argumento):
                if _nombre_si_agrega(sub) in AGREGACIONES_DE_CONTEO:
                    return True
    return False


def validar(sql: str) -> Validacion:
    """Revisa una consulta antes de ejecutarla.

    Rechaza lo que no es una lectura, lo que toca tablas ajenas al almacén y, sobre todo,
    las agregaciones sobre los microdatos que olvidan el peso muestral, que es el error
    que no se nota.
    """
    if not sql or not sql.strip():
        return Validacion(False, "La consulta está vacía.")

    limpio = sql.strip().rstrip(";").strip()
    if ";" in limpio:
        return Validacion(
            False,
            "La consulta trae más de una instrucción.",
            "Envía una sola consulta SELECT.",
        )

    try:
        arbol = _arbol(limpio)
    except duckdb.Error as exc:
        return Validacion(
            False,
            f"La consulta no se pudo interpretar: {exc}",
            "Revisa la sintaxis y vuelve a intentarlo.",
        )

    # DuckDB solo sabe serializar consultas de lectura: cualquier otra cosa, desde un
    # DROP hasta un INSERT, vuelve como error en lugar de árbol. Eso es justo lo que
    # hace falta, pero el mensaje crudo no le sirve al agente para corregirse.
    if arbol.get("error"):
        return Validacion(
            False,
            "Solo se permiten consultas de lectura.",
            "El almacén se reconstruye desde los scripts de ingesta y no se modifica "
            "desde la aplicación. Escribe una consulta SELECT.",
        )

    sentencias = arbol.get("statements") or []
    if len(sentencias) != 1:
        return Validacion(False, "Se esperaba exactamente una instrucción.")

    nodo = sentencias[0].get("node") or {}
    if nodo.get("type") not in ("SELECT_NODE", "SET_OPERATION_NODE", "RECURSIVE_CTE_NODE"):
        return Validacion(
            False,
            "Solo se permiten consultas de lectura.",
            "El almacén se reconstruye desde los scripts de ingesta, no se modifica "
            "desde la aplicación. Usa SELECT.",
        )

    if _usa_show(arbol):
        return Validacion(
            False,
            "SUMMARIZE y DESCRIBE no están permitidos.",
            "Devuelven promedios sin ponderar ya etiquetados como `avg`. Escribe la "
            "consulta que necesitas, ponderando con `peso`.",
        )

    if _usa_funcion_de_tabla(arbol):
        return Validacion(
            False,
            "La consulta lee de una función de tabla en lugar de una tabla del almacén.",
            f"Tablas disponibles: {', '.join(sorted(TABLAS_PERMITIDAS))}.",
        )

    funciones = _nombres_de_funciones(arbol)
    prohibidas = funciones & FUNCIONES_PROHIBIDAS
    if prohibidas:
        return Validacion(
            False,
            f"La consulta usa funciones que no están permitidas: {', '.join(sorted(prohibidas))}.",
            "Consulta solo las tablas del almacén.",
        )

    tablas = _tablas_referenciadas(arbol) - _nombres_de_cte(arbol)
    desconocidas = tablas - TABLAS_PERMITIDAS
    if desconocidas:
        return Validacion(
            False,
            f"La consulta referencia tablas que no existen en el almacén: "
            f"{', '.join(sorted(desconocidas))}.",
            f"Tablas disponibles: {', '.join(sorted(TABLAS_PERMITIDAS))}.",
            tablas=tablas,
        )

    advertencias: list[str] = []
    agregaciones = _agregaciones(arbol)
    no_exentas = [(n, c) for n, c in agregaciones if n not in AGREGACIONES_EXENTAS]

    # La regla que de verdad importa.
    if TABLA_MICRODATO in tablas:
        sin_peso = sorted({n for n, columnas in no_exentas if "peso" not in columnas})
        if sin_peso:
            return Validacion(
                False,
                f"La consulta agrega sobre `{TABLA_MICRODATO}` con "
                f"{', '.join(sin_peso)} sin el peso dentro de la agregación.",
                "La ENLA es una evaluación muestral: sin ponderar, las cifras no "
                "coinciden con las oficiales. El peso tiene que entrar en el propio "
                "cálculo, no basta con pedirlo aparte. Un promedio se escribe "
                "SUM(peso * medida500) / SUM(peso) y una proporción, "
                "SUM(peso) FILTER (WHERE condicion) / SUM(peso). Si lo que quieres es "
                "una cifra ya agregada, consulta `resultados_geograficos`, que viene "
                "ponderada desde la ingesta.",
                tablas=tablas,
            )

        if _divide_conteos(arbol):
            return Validacion(
                False,
                "La consulta divide un conteo entre otro, que es una proporción de la "
                "muestra y no de la población.",
                "Contar filas no pondera: así, el nivel Satisfactorio de 4.° de "
                "primaria en Lectura da 30,6 % en lugar de 32,7 %. Escríbelo como "
                "SUM(peso) FILTER (WHERE es_satisfactorio) / SUM(peso).",
                tablas=tablas,
            )

        faltan = [c for c in COLUMNAS_DE_PARTICION if c not in _columnas_de(arbol)]
        if faltan and no_exentas:
            return Validacion(
                False,
                f"La consulta agrega sobre `{TABLA_MICRODATO}` sin fijar "
                f"{' ni '.join(f'`{c}`' for c in faltan)}.",
                "El hecho trae una fila por estudiante y área evaluada, cada una con el "
                "peso de su área. Sin fijar las dos columnas se mezclan pesos que no son "
                "intercambiables y cada estudiante de secundaria se cuenta tres o cuatro "
                "veces: SUM(peso) sin `cod_area` da 1 721 256 donde la población de 2.° "
                "de secundaria es 573 752. Filtra o agrupa por `grado` y `cod_area`.",
                tablas=tablas,
            )

        if not no_exentas and funciones & AGREGACIONES_DE_CONTEO:
            advertencias.append(
                "COUNT sobre los microdatos cuenta estudiantes de la muestra, no la "
                "población que representan. Para la población, suma `peso`."
            )

    # Las tablas ya agregadas vienen ponderadas fila a fila, pero sus porcentajes y
    # medidas no se pueden promediar entre unidades de tamaños distintos.
    promediadas = sorted({
        columna
        for _, columnas in no_exentas
        for columna in columnas
        if columna.startswith(PREFIJOS_NO_PROMEDIABLES)
    })
    if promediadas and TABLA_MICRODATO not in tablas:
        return Validacion(
            False,
            f"La consulta agrega {', '.join(f'`{c}`' for c in promediadas)} entre "
            "unidades de distinto tamaño.",
            "Cada fila viene ponderada por su cuenta, pero promediarlas entre sí no: el "
            "promedio simple de `pct_satisfactorio` por departamento da 30,4 % donde el "
            "nacional es 32,7 %. Pondera por `poblacion_estimada`, o pide directamente "
            "la fila con `nivel_geografico = 'nacional'`.",
            tablas=tablas,
        )

    return Validacion(True, advertencias=advertencias, tablas=tablas)


def celda_a_texto(valor: Any, decimales: int = 4) -> str:
    """Un valor tal como conviene que lo lea el modelo.

    Con decimales fijos y sin notación científica. Las columnas de población son DOUBLE,
    y con el formato general salían como `5.407e+05`: desde ahí el modelo ya no puede
    recuperar 540 704, y expandir mal una notación científica es un error clásico.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, (int,)) or (hasattr(valor, "is_integer") and float(valor).is_integer()):
        return f"{int(valor)}"
    if isinstance(valor, float):
        return f"{valor:.{decimales}f}".rstrip("0").rstrip(".")
    return str(valor)


def tabla_a_texto(tabla: pd.DataFrame, decimales: int = 4) -> str:
    """Tabla en Markdown, sin dependencias externas.

    Escrito a mano en lugar de usar `to_markdown`, que necesita `tabulate`: faltaba, y
    por eso toda consulta aceptada terminaba en ImportError en vez de devolver la cifra.
    """
    columnas = [str(c) for c in tabla.columns]
    filas = [
        [celda_a_texto(valor, decimales) for valor in registro]
        for registro in tabla.itertuples(index=False, name=None)
    ]
    anchos = [
        max(len(columna), *(len(fila[i]) for fila in filas)) if filas else len(columna)
        for i, columna in enumerate(columnas)
    ]
    def linea(celdas: list[str]) -> str:
        return "| " + " | ".join(c.ljust(anchos[i]) for i, c in enumerate(celdas)) + " |"

    separador = "|" + "|".join("-" * (ancho + 2) for ancho in anchos) + "|"
    return "\n".join([linea(columnas), separador, *(linea(fila) for fila in filas)])


@dataclass
class Resultado:
    """Lo que devuelve una consulta aceptada."""

    sql: str
    tabla: pd.DataFrame
    filas_totales: int
    truncada: bool
    advertencias: list[str] = field(default_factory=list)

    @property
    def vacia(self) -> bool:
        return self.tabla.empty

    def a_texto(self, max_filas: int = 50) -> str:
        """Representación compacta para pasarle el resultado al modelo."""
        if self.vacia:
            return "La consulta no devolvió ninguna fila."
        cuerpo = tabla_a_texto(self.tabla.head(max_filas))
        pie = f"\n\nFilas devueltas: {self.filas_totales}."
        if self.truncada:
            pie += f" Se muestran las primeras {min(max_filas, len(self.tabla))}."
        return cuerpo + pie


class ConsultaRechazada(ValueError):
    """La consulta no pasó la validación."""

    def __init__(self, validacion: Validacion):
        super().__init__(validacion.explicacion())
        self.validacion = validacion


def ejecutar(sql: str, limite: int = LIMITE_FILAS) -> Resultado:
    """Valida una consulta y la ejecuta en solo lectura.

    El límite de filas no es una protección frente a nada: es para que una consulta
    descuidada no devuelva medio millón de filas al modelo. Se informa cuando recorta.
    """
    validacion = validar(sql)
    if not validacion:
        raise ConsultaRechazada(validacion)

    limpio = sql.strip().rstrip(";").strip()
    with almacen.conectar() as con:
        tabla = con.execute(limpio).fetch_df()

    total = len(tabla)
    truncada = total > limite
    if truncada:
        tabla = tabla.head(limite)

    return Resultado(
        sql=limpio,
        tabla=tabla,
        filas_totales=total,
        truncada=truncada,
        advertencias=list(validacion.advertencias),
    )


def extraer_sql(texto: str) -> str | None:
    """Saca la consulta de una respuesta que puede venir envuelta en un bloque de código.

    Los modelos devuelven el SQL de formas distintas según el día: dentro de un bloque
    marcado, dentro de uno sin marcar, o suelto. Esto normaliza los tres casos en lugar
    de exigir un formato que a veces no se respeta.
    """
    if not texto:
        return None

    bloque = re.search(r"```(?:sql)?\s*(.+?)```", texto, re.DOTALL | re.IGNORECASE)
    if bloque:
        return bloque.group(1).strip()

    suelto = re.search(r"\b(with|select)\b.+", texto, re.DOTALL | re.IGNORECASE)
    if suelto:
        return suelto.group(0).strip()

    return None
