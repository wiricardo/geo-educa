"""Estado compartido de la aplicación y carga de datos con caché.

Todas las páginas leen y escriben los mismos filtros a través de este módulo. Eso importa
más de lo que parece: el asistente conversacional de la siguiente fase no responde solo
con texto, también cambia la vista, y lo hace escribiendo aquí. Si cada página guardara
sus filtros por su cuenta, el chat tendría que conocer el detalle de todas.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from geoeduca import almacen, focalizacion  # noqa: E402

from . import config  # noqa: E402


@dataclass
class Filtros:
    """Lo que el usuario está mirando en este momento."""

    grado: str = "4P"
    area: str = "M"
    nivel_geografico: str = "ugel"
    indicador: str = "pct_critico"
    unidad_seleccionada: str | None = None
    muestra_minima: int = config.MUESTRA_MINIMA
    #: Con cuál de los tres criterios ordena Focalización. Vive aquí y no en la página
    #: porque el asistente mueve la vista por este camino: lo que no esté en los
    #: filtros no lo puede cambiar.
    criterio: str = "combinado"

    def validar(self) -> "Filtros":
        """Corrige combinaciones imposibles en lugar de dejar que fallen abajo.

        Al cambiar de grado puede quedar seleccionada un área que ese grado no evalúa.
        En ese caso se vuelve a Matemática, que está en los tres.
        """
        if self.grado not in config.GRADOS:
            self.grado = "4P"
        if self.area not in config.GRADOS[self.grado].areas:
            self.area = "M"
        if self.nivel_geografico not in config.NIVELES_GEOGRAFICOS:
            self.nivel_geografico = "ugel"
        if self.indicador not in config.INDICADORES:
            self.indicador = "pct_critico"
        if self.criterio not in focalizacion.CRITERIOS:
            self.criterio = "combinado"
        return self

    def descripcion(self) -> str:
        return (
            f"{config.nombre_area(self.area)} en {config.nombre_grado(self.grado)}"
        )


def filtros() -> Filtros:
    """Filtros actuales, creándolos la primera vez."""
    if "filtros" not in st.session_state:
        st.session_state.filtros = Filtros()
    return st.session_state.filtros.validar()


#: Último valor con el que se sincronizó cada control. Sirve para distinguir un cambio
#: que viene del usuario, que lo escribe el propio widget, de uno que viene del asistente,
#: que escribe en los filtros.
_SOMBRA_CONTROLES = "_sombra_controles"


def sembrar(clave: str, campo: str) -> None:
    """Deja listo el valor de un control antes de dibujarlo.

    Un widget de Streamlit sin `key` recibe una identidad derivada de sus parámetros,
    `index` incluido. Pasarle un `index` calculado desde el mismo filtro que el widget
    escribe lo convierte en un widget distinto en cuanto el filtro cambia: Streamlit lo
    desmonta y monta otro, y eso produce los dos síntomas que se veían. El primer clic
    se perdía, porque el widget nuevo nacía con el valor viejo y hacía falta un segundo
    clic, y durante la transición se dibujaban los dos a la vez, que es el parpadeo de
    medio segundo con las opciones repetidas debajo.

    Con una `key` estable la identidad no cambia nunca. Este ayudante se encarga de lo
    único que hacía el `index`: que el control siga al filtro cuando el filtro cambia
    por fuera. Se escribe antes de dibujar, porque después Streamlit no lo permite, y
    solo cuando el valor cambió por fuera, porque sobrescribirlo en cada pasada anularía
    el clic recién dado.
    """
    sombras = st.session_state.setdefault(_SOMBRA_CONTROLES, {})
    actual = getattr(filtros(), campo)
    if clave not in st.session_state or sombras.get(clave) != actual:
        st.session_state[clave] = actual
    sombras[clave] = actual


def actualizar(**cambios) -> None:
    """Modifica los filtros desde cualquier punto de la aplicación.

    Es la puerta que usará el asistente para mover el mapa: recibe solo los campos que
    cambian y deja el resto como estaba.
    """
    actuales = filtros()
    for clave, valor in cambios.items():
        if valor is not None and hasattr(actuales, clave):
            setattr(actuales, clave, valor)
    st.session_state.filtros = actuales.validar()


def limpiar_seleccion() -> None:
    """Deselecciona la unidad del mapa.

    `actualizar` ignora los valores nulos a propósito, para que quien solo quiera mover
    un filtro no borre de paso los demás. Deseleccionar necesita por eso su propia
    puerta: pasarle `None` a `actualizar` no hacía nada y el botón de volver al
    resultado nacional dejaba el panel como estaba.
    """
    actuales = filtros()
    actuales.unidad_seleccionada = None
    st.session_state.filtros = actuales.validar()


def como_diccionario() -> dict:
    """Filtros en forma de diccionario, para registrar o mostrar."""
    return asdict(filtros())


@st.cache_data(show_spinner=False)
def resultados(nivel: str, grado: str, area: str) -> pd.DataFrame:
    """Métricas agregadas de un nivel geográfico, con caché."""
    return almacen.resultados_geograficos(nivel, grado, area)


@st.cache_data(show_spinner=False)
def nacional(grado: str, area: str) -> pd.Series | None:
    """Fila nacional de un grado y un área."""
    tabla = almacen.resultados_geograficos("nacional", grado, area)
    return tabla.iloc[0] if len(tabla) else None


@st.cache_data(show_spinner=False)
def microdatos(grado: str, area: str) -> pd.DataFrame:
    """Hecho a nivel de estudiante, necesario para los intervalos de confianza."""
    return almacen.microdatos(grado, area)


@st.cache_resource(show_spinner=False)
def geometrias(nivel: str) -> gpd.GeoDataFrame:
    """Capa geográfica de un nivel.

    Con cache_resource y no cache_data porque las geometrías son grandes y no cambian:
    conviene una sola copia en memoria y no una por combinación de parámetros.
    """
    return almacen.geometrias(nivel)


@st.cache_data(show_spinner=False)
def desagregado(grado: str, area: str) -> pd.DataFrame:
    """Resultados nacionales por sexo, gestión y ámbito."""
    with almacen.conectar() as con:
        return con.execute(
            "select * from resultados_desagregado where grado = ? and cod_area = ?",
            [grado, area],
        ).fetch_df()


@st.cache_data(show_spinner=False)
def brechas(grado: str, area: str) -> pd.DataFrame:
    """Diferencias entre categorías, ya calculadas en el almacén."""
    with almacen.conectar() as con:
        return con.execute(
            "select * from brechas where grado = ? and cod_area = ?",
            [grado, area],
        ).fetch_df()


def hay_almacen() -> bool:
    """Indica si la ingesta ya se ejecutó."""
    return almacen.RUTA_ALMACEN.exists()
