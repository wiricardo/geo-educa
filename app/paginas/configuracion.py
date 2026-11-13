"""Configuración: con qué clave habla el asistente.

La aplicación es pública y trae una clave propia con límite para que cualquiera pueda
probar el asistente sin registrarse en ningún sitio. Quien quiera usarlo sin ese tope
pone aquí la suya, de cualquiera de los cuatro proveedores.

Los cuatro exponen la misma interfaz de `chat/completions` con llamada a herramientas,
así que cambiar de proveedor es cambiar la URL y el modelo: el asistente es el mismo.
La clave del proyecto es de DeepSeek, de modo que el proveedor solo lo elige quien trae
la suya.

Una clave ajena se trata como lo que es: algo prestado. Vive solo en la sesión, no se
guarda en ningún sitio y no se muestra de vuelta. Eso se dice en la pantalla, no se deja
implícito.

El orden de la pantalla sigue al de las preguntas: para qué sirve la clave, dónde se
pone, y al final qué pasa con ella.
"""

from __future__ import annotations

import streamlit as st

from core import chat
from core import componentes as cp
from core import theme
from geoeduca import agente

cp.encabezado(
    "Configuración",
    "Con qué clave de API responde el asistente",
)

# Qué hace el asistente va primero: es la razón para poner una clave, y antes estaba
# debajo de todo el trámite de ponerla.
with st.container(border=True):
    st.markdown("**El asistente**")
    st.markdown(
        """<div class='nota'>
        Consulta los datos de la evaluación y responde con cifras calculadas en el
        momento, nunca de memoria. Puede comparar regiones, armar rankings, calcular
        brechas, analizar si los niveles críticos se agrupan en el territorio y ordenar
        las unidades para decidir dónde intervenir primero.<br><br>
        Además cambia lo que ves: si le pides el mapa de una región o de otra área,
        mueve los filtros y avisa de que lo hizo.<br><br>
        Si alguna cifra de una respuesta no sale de una consulta hecha en el momento,
        la propia respuesta lo advierte.
        </div>""",
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

_, es_propia = chat.clave_activa()
restantes = chat.consultas_restantes()

# Guardar una clave redibuja la pantalla, y si el estado ya decía lo mismo no cambiaba
# nada a la vista: el botón parecía no haber hecho nada. La bandera se escribía desde el
# principio y no la leía nadie.
if st.session_state.pop("clave_recien_aplicada", False):
    st.toast("Clave guardada. El asistente ya puede responder.", icon=":material/key:")
if st.session_state.pop("clave_recien_borrada", False):
    st.toast("Clave borrada de esta sesión.", icon=":material/key_off:")

col_clave, col_donde = st.columns([1.35, 1], gap="medium")

with col_clave:
    with st.container(border=True):
        st.markdown("**Tu clave**")

        # El estado se dice con un punto de color y una línea de texto, sin una caja
        # dentro de la caja.
        if es_propia:
            nombre = agente.proveedor(chat.proveedor_activo()).nombre
            punto, mensaje = (
                theme.ACENTO,
                f"Tu propia clave de {nombre}, sin límite de consultas.",
            )
        elif chat.clave_del_proyecto():
            punto, mensaje = (
                theme.AVISO,
                f"Clave compartida de DeepSeek. Te quedan {restantes} consultas en "
                "esta sesión.",
            )
        else:
            punto, mensaje = (
                theme.TEXTO_TENUE,
                "Sin clave configurada. El asistente no puede responder.",
            )

        st.markdown(
            f"""<div style='display:flex;align-items:center;gap:9px;margin:4px 0 16px'>
                <span style='width:8px;height:8px;border-radius:50%;background:{punto};
                        flex-shrink:0'></span>
                <span style='font-size:0.85rem;color:{theme.TEXTO}'>{mensaje}</span>
            </div>""",
            unsafe_allow_html=True,
        )

        elegido = st.selectbox(
            "Proveedor",
            options=list(agente.PROVEEDORES),
            format_func=lambda clave: agente.PROVEEDORES[clave].nombre,
            key=chat.PROVEEDOR_SESION,
            help="Los cuatro responden a la misma interfaz, así que el asistente "
            "funciona igual con cualquiera.",
        )
        ficha = agente.PROVEEDORES[elegido]

        clave = st.text_input(
            f"Tu clave de API de {ficha.nombre}",
            type="password",
            placeholder="sk-...",
            help="No se guarda en ningún sitio: vive solo mientras dure esta sesión.",
        )

        # El modelo se puede cambiar porque los proveedores renombran y retiran modelos
        # a menudo: con una lista fija, la aplicación envejece sin que nadie se entere.
        st.text_input(
            "Modelo",
            placeholder=ficha.modelo,
            key=chat.MODELO_SESION,
            help="En blanco usa el de partida del proveedor, que es el del marcador "
            "de posición. Sirve para probar otro o para reemplazar uno retirado.",
        )

        izquierda, derecha = st.columns(2)
        if izquierda.button("Usar esta clave", type="primary", width="stretch"):
            if not clave.strip():
                st.error("El campo está vacío.")
            else:
                st.session_state[chat.CLAVE_SESION] = clave.strip()
                st.session_state["clave_recien_aplicada"] = True
                st.rerun()

        if derecha.button("Borrar mi clave", width="stretch", disabled=not es_propia):
            st.session_state.pop(chat.CLAVE_SESION, None)
            st.session_state["clave_recien_borrada"] = True
            st.rerun()

        if es_propia:
            st.page_link(
                "paginas/mapa.py",
                label="Probar el asistente en el mapa",
                icon=":material/map:",
            )

with col_donde:
    with st.container(border=True):
        st.markdown("**Dónde conseguir una clave**")
        st.markdown(
            cp.glosario([
                (
                    datos.nombre,
                    f"<a href='{datos.consola}' target='_blank' "
                    f"style='color:{theme.ACENTO}'>Abrir su panel</a>",
                )
                for datos in agente.PROVEEDORES.values()
            ])
            + "<div class='nota' style='margin-top:12px'>Crea una cuenta, entra a la "
            "sección de claves de API y genera una nueva. Conviene ponerle un límite "
            "de gasto antes de usarla en cualquier sitio.</div>",
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("**Qué pasa con tu clave**")
    st.markdown(
        cp.glosario([
            (
                "Dónde vive",
                "Solo en la memoria de esta sesión. Al cerrar la pestaña desaparece.",
            ),
            (
                "Dónde no",
                "No se escribe en disco, ni en el navegador, ni en ningún registro, y "
                "no se muestra de vuelta en pantalla.",
            ),
            (
                "Para qué se usa",
                "Solo para consultar en tu nombre el modelo del proveedor que elijas.",
            ),
            (
                "Por dónde pasa",
                "La aplicación corre en un servidor, así que la clave pasa por él "
                "mientras dure la sesión.",
            ),
            ("Quién paga", "El consumo, en el panel de tu proveedor."),
        ]),
        unsafe_allow_html=True,
    )

cp.pie_de_pagina()
