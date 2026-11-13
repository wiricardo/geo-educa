"""Catálogos y constantes de la aplicación.

Todo lo que la interfaz necesita saber sobre la estructura de la evaluación vive aquí,
para que las páginas no repitan listas ni nombres y un cambio se haga en un solo sitio.
"""

from __future__ import annotations

from dataclasses import dataclass

TITULO = "GEO_EDUCA"
SUBTITULO = "Logros de aprendizaje en el Perú, ENLA 2025"
FUENTE = "Minedu - UMC. Evaluación Nacional de Logros de Aprendizaje 2025."


@dataclass(frozen=True)
class Grado:
    codigo: str
    nombre: str
    areas: tuple[str, ...]
    representatividad: str


GRADOS: dict[str, Grado] = {
    "4P": Grado("4P", "4.° de primaria", ("L", "M"), "nacional, regional y por estrato"),
    "2S": Grado("2S", "2.° de secundaria", ("L", "M", "CN"), "nacional, regional y por estrato"),
    "5S": Grado("5S", "5.° de secundaria", ("L", "M", "CN", "CI"), "nacional y por estrato"),
}

AREAS: dict[str, str] = {
    "L": "Lectura",
    "M": "Matemática",
    "CN": "Ciencia y Tecnología",
    "CI": "Ciudadanía",
}

NIVELES_LOGRO: dict[int, str] = {
    0: "Previo al inicio",
    1: "En inicio",
    2: "En proceso",
    3: "Satisfactorio",
}

#: Qué significa cada nivel, en una línea. Los nombres oficiales no se explican solos:
#: "Previo al inicio" y "En inicio" suenan a lo mismo si no se conoce la escala, y de
#: hecho son el peor y el segundo peor. La definición completa está en Notas sobre los
#: datos; esto es lo que cabe al lado del nombre.
GLOSA_NIVEL: dict[int, str] = {
    0: "No alcanza ni lo más básico",
    1: "Solo lo más elemental",
    2: "Una parte de lo esperado",
    3: "Todo lo esperado para su grado",
}

# Niveles geográficos que el mapa puede pintar, del más agregado al más fino.
NIVELES_GEOGRAFICOS: dict[str, str] = {
    "departamento": "Departamento",
    "dre": "DRE",
    "provincia": "Provincia",
    "ugel": "UGEL",
    "distrito": "Distrito",
}

# A qué unidad pertenece cada nivel, en plural, para escribirlo en una frase. No es el
# mismo en todos: una UGEL pertenece a una DRE y un distrito a una provincia. Los dos
# niveles de arriba no tienen a quién pertenecer y no figuran aquí. Hace falta porque
# «ámbito» ya significa urbano o rural en Brechas.
NIVEL_PADRE: dict[str, str] = {
    "provincia": "departamentos",
    "ugel": "DRE",
    "distrito": "provincias",
}


@dataclass(frozen=True)
class Indicador:
    clave: str
    nombre: str
    columna: str
    sufijo: str
    descripcion: str
    mas_es_peor: bool


INDICADORES: dict[str, Indicador] = {
    "pct_critico": Indicador(
        "pct_critico",
        "% en niveles críticos",
        "pct_critico",
        " %",
        "Estudiantes que no llegan a lo que se espera para su grado.",
        mas_es_peor=True,
    ),
    "pct_satisfactorio": Indicador(
        "pct_satisfactorio",
        "% Satisfactorio",
        "pct_satisfactorio",
        " %",
        "Estudiantes que alcanzan lo que se espera para su grado.",
        mas_es_peor=False,
    ),
    "medida_promedio": Indicador(
        "medida_promedio",
        "Medida promedio",
        "medida_promedio",
        "",
        "Puntaje promedio. Cada grado tiene su propia escala, así que dos grados no "
        "se comparan entre sí.",
        mas_es_peor=False,
    ),
}

# Por debajo de este número de estudiantes evaluados, la cifra de una unidad geográfica
# tiene tanto ruido muestral que informa poco. Se muestra marcada, no se oculta.
MUESTRA_MINIMA = 30

#: Escuelas mínimas para que una unidad entre en una estimación con intervalo. En un
#: muestreo por conglomerados la precisión la gobiernan las escuelas, no los estudiantes:
#: Moquegua pasaba el piso de 30 estudiantes en 5.° de secundaria con 111 evaluados
#: repartidos en dos escuelas.
ESCUELAS_MINIMAS: int = 3

# Advertencia sobre la comparación entre grados, que es el error de lectura más común.
AVISO_ESCALAS = (
    "Las medidas promedio no son comparables entre grados: cada grado tiene su propia "
    "escala. Lo que sí se puede comparar es la distribución por niveles de logro."
)


def nombre_area(codigo: str) -> str:
    return AREAS.get(codigo, codigo)


def nombre_grado(codigo: str) -> str:
    grado = GRADOS.get(codigo)
    return grado.nombre if grado else codigo


def areas_de(grado: str) -> dict[str, str]:
    """Áreas evaluadas en un grado, en el orden en que se presentan."""
    codigos = GRADOS[grado].areas if grado in GRADOS else tuple(AREAS)
    return {c: AREAS[c] for c in codigos}
