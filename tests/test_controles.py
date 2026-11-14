"""Pruebas de que los controles de la barra siguen al filtro cuando cambia por fuera.

El asistente no mueve los controles: escribe en el filtro y espera que la barra se ponga
al día en la pasada siguiente. Si un control no lo hace, conserva su valor viejo y lo
escribe de vuelta sobre el filtro, de modo que la vista se deshace sola y sin avisar. Eso
pasaba con el área: pedirle al asistente otro grado funcionaba y pedirle otra área no.

Se ejercita la barra de verdad, no una copia de su lógica, porque el fallo estaba en el
orden de las líneas y una reimplementación lo habría escondido.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[1]
for ruta in (RAIZ / "src", RAIZ / "app"):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

#: Imita una pasada de la aplicación: lo que el asistente dejó pedido se aplica sobre el
#: filtro y después se dibuja la barra, que es el orden real.
GUION = f"""
import sys
from pathlib import Path

for ruta in ({str(RAIZ / "src")!r}, {str(RAIZ / "app")!r}):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

import streamlit as st
from core import componentes as cp
from core import estado

pedido = st.session_state.pop("_pedido_del_asistente", None)
if pedido:
    estado.actualizar(**pedido)

cp.barra_superior()

f = estado.filtros()
st.text(f"{{f.grado}}|{{f.area}}")
"""


def _barra() -> AppTest:
    app = AppTest.from_string(GUION)
    app.run()
    return app


def _vista(app: AppTest) -> str:
    """Grado y área tal como quedaron en el filtro al terminar la pasada."""
    return app.text[0].value


def _filtro(app: AppTest) -> dict[str, str]:
    grado, area = _vista(app).split("|")
    return {"grado": grado, "area": area}


def test_el_area_que_pide_el_asistente_sobrevive_a_la_pasada_siguiente():
    app = _barra()
    assert _vista(app).endswith("|M")

    app.session_state["_pedido_del_asistente"] = {"area": "L"}
    app.run()

    assert _vista(app) == "4P|L"
    assert app.session_state["sel_area"] == "L"


def test_el_grado_que_pide_el_asistente_tambien_sobrevive():
    app = _barra()

    app.session_state["_pedido_del_asistente"] = {"grado": "2S"}
    app.run()

    assert _vista(app).startswith("2S|")
    assert app.session_state["sel_grado"] == "2S"


def test_el_asistente_puede_cambiar_grado_y_area_a_la_vez():
    app = _barra()

    app.session_state["_pedido_del_asistente"] = {"grado": "2S", "area": "CN"}
    app.run()

    assert _vista(app) == "2S|CN"


def test_un_area_que_el_grado_no_evalua_cae_en_matematica_sin_romperse():
    # 4.° de primaria no evalúa Ciencia y Tecnología. El control no puede quedarse con un
    # valor que no está entre sus opciones, así que la barra lo corrige.
    app = _barra()

    app.session_state["_pedido_del_asistente"] = {"grado": "4P", "area": "CN"}
    app.run()

    assert _vista(app) == "4P|M"
    assert not app.exception


def test_cambiar_de_grado_conserva_el_area_si_el_grado_nuevo_la_evalua():
    app = _barra()
    app.session_state["_pedido_del_asistente"] = {"area": "L"}
    app.run()

    app.session_state["_pedido_del_asistente"] = {"grado": "2S"}
    app.run()

    assert _vista(app) == "2S|L"


@pytest.mark.parametrize("control, campo", [("sel_grado", "grado"), ("sel_area", "area")])
def test_el_clic_en_un_control_no_lo_deshace_la_pasada_siguiente(control, campo):
    """Sembrar no debe sobrescribir en cada pasada, solo cuando el filtro cambió fuera."""
    app = _barra()
    valor = {"sel_grado": "2S", "sel_area": "L"}[control]

    app.session_state[control] = valor
    app.run()
    app.run()

    assert app.session_state[control] == valor
    assert _filtro(app)[campo] == valor
