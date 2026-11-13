"""Panel del asistente: conversación, clave de acceso y control de la vista.

La pieza que distingue a este asistente de un chat cualquiera es que sus respuestas
cambian lo que se ve en pantalla. Cuando el modelo decide que hay que mover el mapa,
devuelve una acción, aquí se aplica sobre el estado compartido y se avisa en la
conversación con una marca distinta de un mensaje. Sin ese aviso, la pantalla se movería
sola y nadie entendería por qué.

Sobre la clave: la aplicación trae una propia con límite para que cualquiera pueda
probar el asistente sin registrarse en ningún sitio. Quien quiera usarlo a fondo pone la
suya en la pantalla de configuración. Esa clave es de quien la escribe, así que vive solo
en la sesión: no se guarda en disco, ni en el navegador, ni en registros, y no se muestra
de vuelta.
"""

from __future__ import annotations

import os

import streamlit as st

from geoeduca import agente

from . import config, estado, theme

CLAVE_SESION = "clave_api_usuario"
PAGINA_ACTUAL = "pagina_actual"
SECCION_PEDIDA = "seccion_pedida"
PROVEEDOR_SESION = "proveedor_api_usuario"
MODELO_SESION = "modelo_api_usuario"
HISTORIAL = "historial_chat"
CONSULTAS_HECHAS = "consultas_hechas"

# Tope por sesión cuando se usa la clave del proyecto. No es una protección real, porque
# recargar la página lo reinicia: la protección es el límite de gasto del proveedor. Esto
# solo evita que un visitante agote la cuota de una sentada.
TOPE_POR_SESION = 15

SUGERENCIAS = [
    "¿Dónde está peor matemática en primaria?",
    "Compara Lima con Loreto",
    "¿Los niveles críticos se agrupan en el territorio?",
    "¿Por dónde habría que empezar?",
]


def clave_del_proyecto() -> str:
    """Clave compartida, si está configurada en el servidor.

    Se busca en dos sitios porque cada servicio de despliegue la pone en uno: los
    secretos de Streamlit en su nube propia, y una variable de entorno en Posit Connect
    Cloud y en casi todos los demás. Leer solo los secretos dejaba la clave configurada
    y sin efecto, que es el fallo que no avisa.
    """
    try:
        if clave := st.secrets.get("DEEPSEEK_API_KEY", ""):
            return clave
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("DEEPSEEK_API_KEY", "")


def clave_activa() -> tuple[str, bool]:
    """Devuelve la clave a usar y si es la del propio visitante."""
    propia = st.session_state.get(CLAVE_SESION, "")
    if propia:
        return propia, True
    return clave_del_proyecto(), False


def proveedor_activo() -> str:
    """Proveedor con el que consultar.

    Solo lo elige quien trae su propia clave: la del proyecto es de DeepSeek y mandarla
    a otro proveedor sería un error de autenticación con un mensaje que no ayuda.
    """
    _, es_propia = clave_activa()
    if es_propia:
        return st.session_state.get(PROVEEDOR_SESION, agente.PROVEEDOR_POR_OMISION)
    return agente.PROVEEDOR_POR_OMISION


def modelo_activo() -> str:
    """Modelo elegido a mano, si lo hay. Vacío quiere decir el del proveedor."""
    _, es_propia = clave_activa()
    if es_propia:
        return st.session_state.get(MODELO_SESION, "").strip()
    return ""


def hay_clave() -> bool:
    clave, _ = clave_activa()
    return bool(clave)


def consultas_restantes() -> int | None:
    """Consultas que quedan con la clave compartida. None si usa la suya."""
    _, es_propia = clave_activa()
    if es_propia:
        return None
    return max(TOPE_POR_SESION - st.session_state.get(CONSULTAS_HECHAS, 0), 0)


def historial() -> list[dict]:
    if HISTORIAL not in st.session_state:
        st.session_state[HISTORIAL] = []
    return st.session_state[HISTORIAL]


def _historial_para_modelo(limite: int = 8) -> list[dict]:
    """Últimos turnos en el formato que espera el modelo."""
    return [
        {"role": m["rol"], "content": m["texto"]}
        for m in historial()[-limite:]
        if m.get("texto")
    ]


def _aplicar(acciones: list[agente.Accion]) -> list[str]:
    """Lleva las acciones del asistente al estado compartido."""
    aplicadas = []
    for accion in acciones:
        if accion.tipo == "ir_a_seccion":
            destino = accion.parametros.get("seccion")
            if destino:
                # No se cambia de página aquí. La respuesta todavía no está guardada en
                # el historial, y saltar en este punto se la llevaría por delante: el
                # visitante llegaría a la otra sección sin la contestación que pidió.
                # Queda anotado y `app.py` lo atiende al principio de la pasada
                # siguiente, cuando el turno ya está completo.
                st.session_state[SECCION_PEDIDA] = destino
                aplicadas.append(accion.descripcion or f"Abriendo {destino}.")
            continue
        if accion.tipo != "cambiar_vista":
            continue
        parametros = {
            k: v for k, v in accion.parametros.items()
            if k in {"grado", "area", "nivel_geografico", "indicador", "criterio"}
            and v
        }
        if accion.parametros.get("unidad"):
            parametros["unidad_seleccionada"] = accion.parametros["unidad"]
        if parametros:
            estado.actualizar(**parametros)
            aplicadas.append(accion.descripcion or "Vista actualizada.")
    return aplicadas


def _marca_de_accion(texto: str) -> None:
    """Aviso de que el asistente cambió la pantalla.

    No es un mensaje de la conversación: es la señal de que algo se movió. Por eso se
    dibuja distinto, con icono y en una sola línea.
    """
    st.markdown(
        f"""<div style='display:flex;align-items:center;gap:8px;background:{theme.ACENTO_SUAVE};
                    border:1px solid {theme.BORDE};border-radius:7px;padding:8px 11px;
                    margin:4px 0'>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="{theme.ACENTO}" stroke-width="2" stroke-linecap="round"
                 stroke-linejoin="round" aria-hidden="true">
                <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"></polygon>
                <line x1="8" y1="2" x2="8" y2="18"></line>
                <line x1="16" y1="6" x2="16" y2="22"></line>
            </svg>
            <span style='font-size:0.78rem;color:{theme.ACENTO};font-weight:500'>{texto}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def _marca_sin_respaldo() -> None:
    """Aviso de que la respuesta trae cifras que ninguna herramienta devolvió.

    La regla del asistente es que toda cifra salga de una herramienta recién ejecutada.
    Cuando no hay ninguna que la sostenga, decirlo es lo único honesto: antes una
    respuesta de memoria salía igual que una consultada y no había forma de notarlo.
    """
    st.markdown(
        f"""<div style='background:{theme.SUPERFICIE};border:1px solid {theme.CONTRASTE};
                    border-radius:7px;padding:8px 11px;margin:4px 0;font-size:0.76rem;
                    color:{theme.TEXTO_SECUNDARIO};line-height:1.5'>
            Esta respuesta trae cifras que no salieron de ninguna consulta a los datos.
            Compruébalas antes de usarlas.
        </div>""",
        unsafe_allow_html=True,
    )


def _dibujar_mensaje(mensaje: dict) -> None:
    with st.chat_message("user" if mensaje["rol"] == "user" else "assistant"):
        if mensaje.get("texto"):
            st.markdown(mensaje["texto"])
        for aviso in mensaje.get("acciones", []):
            _marca_de_accion(aviso)
        if mensaje.get("sin_respaldo"):
            _marca_sin_respaldo()
        descartadas = mensaje.get("descartadas", [])
        if descartadas:
            st.caption(
                "Intentos que no devolvieron datos y no respaldan ninguna cifra: "
                + ", ".join(descartadas)
                + "."
            )


def _contexto() -> dict:
    """Lo que el asistente necesita saber de lo que el visitante tiene delante.

    Los filtros son los mismos en todas las secciones, así que por sí solos no dicen
    en cuál está: con la misma vista, en Mapa tiene sentido ofrecerse a moverla y en
    Notas sobre los datos no hay nada que mover.
    """
    contexto = estado.como_diccionario()
    contexto["pagina"] = st.session_state.get(PAGINA_ACTUAL, "")
    return contexto


def _preguntar(pregunta: str) -> None:
    """Manda la pregunta al asistente y guarda el turno completo."""
    clave, es_propia = clave_activa()
    if not clave:
        st.session_state[HISTORIAL].append(
            {
                "rol": "assistant",
                "texto": "Para usar el asistente hace falta una clave de API. Puedes "
                         "poner la tuya en la sección de configuración.",
            }
        )
        return

    if not es_propia and consultas_restantes() == 0:
        st.session_state[HISTORIAL].append(
            {
                "rol": "assistant",
                "texto": "Se agotaron las consultas de prueba de esta sesión. Para "
                         "seguir, pon tu propia clave en la sección de configuración.",
            }
        )
        return

    historial().append({"rol": "user", "texto": pregunta})

    with st.spinner("Consultando los datos"):
        respuesta = agente.responder(
            pregunta,
            clave=clave,
            historial=_historial_para_modelo(),
            contexto_vista=_contexto(),
            nombre_proveedor=proveedor_activo(),
            modelo=modelo_activo(),
        )

    if not es_propia:
        st.session_state[CONSULTAS_HECHAS] = (
            st.session_state.get(CONSULTAS_HECHAS, 0) + 1
        )

    avisos = _aplicar(respuesta.acciones)

    texto = respuesta.texto
    if respuesta.error:
        texto = (
            "No pude completar la consulta. "
            + ("Revisa que la clave sea válida y tenga saldo."
               if "auth" in respuesta.error.lower() or "key" in respuesta.error.lower()
               else "Vuelve a intentarlo en un momento.")
        )

    historial().append(
        {
            "rol": "assistant",
            "texto": texto,
            "acciones": avisos,
            "descartadas": sorted({
                f"{e.herramienta} ({e.estado.replace('_', ' ')})"
                for e in respuesta.evidencias
                if not e.respalda
            }),
            "sin_respaldo": respuesta.cifras_sin_respaldo and not respuesta.error,
        }
    )


def panel(alto: int = 420, titulo: str = "Asistente") -> None:
    """Dibuja el panel completo del asistente."""
    st.markdown(f"**{titulo}**")

    restantes = consultas_restantes()
    if restantes is None:
        st.caption("Usando tu clave")
    elif restantes > 0:
        st.caption(f"{restantes} consultas de prueba en esta sesión")
    else:
        st.caption("Consultas de prueba agotadas")

    if not hay_clave():
        st.markdown(
            f"<div class='nota' style='margin:10px 0 14px'>El asistente necesita una "
            f"clave de API para responder.</div>",
            unsafe_allow_html=True,
        )
        st.page_link(
            "paginas/configuracion.py",
            label="Configurar una clave",
            icon=":material/key:",
        )
        return

    contenedor = st.container(height=alto)
    with contenedor:
        if not historial():
            st.caption(
                "Pregunta por los datos y el mapa responde. Las cifras salen del "
                "almacén, no de la memoria del modelo."
            )
        for mensaje in historial():
            _dibujar_mensaje(mensaje)

    if not historial():
        # Una por fila y no en dos columnas: en un panel estrecho cada botón se
        # quedaba con unos ciento cuarenta píxeles y la pregunta salía cortada.
        for i, sugerencia in enumerate(SUGERENCIAS[:4]):
            if st.button(sugerencia, key=f"sug_{i}", width="stretch"):
                _preguntar(sugerencia)
                st.rerun()

    pregunta = st.chat_input("Escribe tu pregunta")
    if pregunta:
        _preguntar(pregunta)
        st.rerun()

    if historial():
        if st.button("Reiniciar conversación", width="stretch"):
            st.session_state[HISTORIAL] = []
            st.rerun()


def panel_contraido() -> None:
    """Versión reducida, para las páginas donde el contenido necesita el ancho."""
    with st.popover("Asistente", width="stretch"):
        panel(alto=360)
