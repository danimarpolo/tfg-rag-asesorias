#!/usr/bin/env python3
"""
app/interfaz.py
================
Frontend mínimo del MVP (apartado 3.2.2 de la memoria): una única página
Streamlit que sube un requerimiento, invoca el backend (api/main.py) por
HTTP y muestra el resultado. Deliberadamente no hay panel CRUD, gestión de
expedientes ni alertas de plazos: eso es diseño pendiente de implementar
(apartado 4.1), no parte de esta demo.

Este módulo NUNCA importa cadena.py, triaje.py ni query.py directamente:
toda la comunicación con la cadena de generación pasa por la API REST del
backend, para que la separación entre frontend y backend sea real y no
simulada.

Arranque (PowerShell, con el backend ya levantado en otra terminal)
---------------------------------------------------------------------
    streamlit run app\\interfaz.py
"""

from __future__ import annotations

import textwrap
import threading
import time

import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

# Duraciones medias reales por etapa, tomadas de la evaluación de la cadena
# (memoria, apartado 5.3.4; eval/tabla_drafting.md). El backend ejecuta
# cadena.procesa_documento en una única llamada síncrona y no expone
# progreso intermedio (ver apartado 3.4.6 del enunciado de este módulo);
# estos tiempos solo avanzan la etiqueta de etapa mostrada mientras se
# espera la respuesta real — no son una señal en vivo del backend.
_ETAPAS = [
    ("Triaje: extrayendo y validando los datos del requerimiento…", 9.27),
    ("Formulando la consulta y recuperando normativa…", 0.23),
    ("Generando el borrador de contestación…", 33.73),
]

st.set_page_config(page_title="Contestación a requerimientos AEAT", page_icon="📄")
st.title("Contestación a requerimientos de la AEAT")
st.caption(
    "Prototipo de TFG. Sube un requerimiento en PDF y genera un borrador de "
    "contestación fundamentado en la normativa indexada (LGT y LIVA)."
)

if "resultado" not in st.session_state:
    st.session_state["resultado"] = None

archivo = st.file_uploader("Requerimiento (PDF)", type="pdf")
procesar = st.button("Procesar requerimiento", disabled=archivo is None)


def _crear_expediente(archivo) -> str:
    resp = requests.post(
        f"{API_URL}/expedientes",
        files={"pdf": (archivo.name, archivo.getvalue(), "application/pdf")},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _procesar_con_progreso(expediente_id: str) -> dict:
    """Lanza POST /procesar en un hilo aparte y anima el indicador de etapa
    mientras se espera la respuesta real del backend."""
    salida: dict = {}

    def _llamar():
        try:
            # Timeout holgado: el peor caso teórico encadena hasta tres
            # intentos de triaje (config.OLLAMA_TIMEOUT = 120 s cada uno)
            # más la generación (config.DRAFTING_TIMEOUT = 300 s); la
            # latencia típica medida es de ~43 s en total.
            r = requests.post(f"{API_URL}/expedientes/{expediente_id}/procesar", timeout=900)
            r.raise_for_status()
            salida["respuesta"] = r.json()
        except requests.RequestException as e:
            salida["error"] = str(e)

    hilo = threading.Thread(target=_llamar, daemon=True)
    hilo.start()

    with st.status("Procesando requerimiento…", expanded=True) as status:
        for etiqueta, duracion in _ETAPAS:
            status.update(label=etiqueta)
            transcurrido = 0.0
            while hilo.is_alive() and transcurrido < duracion:
                time.sleep(0.3)
                transcurrido += 0.3
        while hilo.is_alive():   # la generación puede exceder la media
            time.sleep(0.3)
        hilo.join()

        if "error" in salida:
            status.update(label="Error al procesar el requerimiento.", state="error")
        else:
            status.update(label="Borrador generado.", state="complete")

    return salida


if procesar and archivo is not None:
    try:
        expediente_id = _crear_expediente(archivo)
    except requests.RequestException as e:
        st.error(f"No se pudo crear el expediente: {e}")
    else:
        salida = _procesar_con_progreso(expediente_id)
        if "error" in salida:
            st.error(f"Fallo al procesar el requerimiento: {salida['error']}")
        else:
            st.session_state["resultado"] = salida["respuesta"]

resultado = st.session_state["resultado"]

if resultado is not None:
    if not resultado.get("triaje_valido", False):
        st.error(f"El triaje no produjo una extracción válida: {resultado.get('error')}")
    else:
        st.divider()

        st.subheader("1. Datos extraídos por el triaje")
        triaje = resultado["triaje"]
        st.table(
            [
                {"Campo": campo, "Valor": ", ".join(valor) if isinstance(valor, list) else valor}
                for campo, valor in triaje.items()
            ]
        )

        st.subheader("2. Referencias normativas citadas")
        col_f, col_nf = st.columns(2)
        with col_f:
            st.markdown("**Fundamentables** — verificadas en el índice")
            if resultado["fundamentables"]:
                for a in resultado["fundamentables"]:
                    st.markdown(f"- {a}")
            else:
                st.caption("Ninguna.")
        with col_nf:
            st.markdown("**No fundamentables**")
            if resultado["no_fundamentables"]:
                for a in resultado["no_fundamentables"]:
                    st.markdown(f"- {a}")
            else:
                st.caption("Ninguna.")
            st.caption(
                "No pueden sustentar la argumentación jurídica: su texto no "
                "está en el corpus indexado (solo LGT y LIVA). El borrador "
                "las cita únicamente como referencia del requerimiento "
                "original, sin argumentar sobre su contenido."
            )

        st.subheader("3. Fragmentos normativos recuperados")
        st.caption(f"Consulta generada: “{resultado['consulta']}”")
        for i, r in enumerate(resultado["recuperados"], start=1):
            with st.expander(f"[{i}] {r['articulo_id']} · similitud {r['similitud']:.4f}"):
                st.write(textwrap.shorten(r["texto"], width=400, placeholder=" […]"))

        st.subheader("4. Borrador de contestación")
        st.warning(
            "Propuesta generada automáticamente, sujeta a revisión "
            "profesional obligatoria antes de su presentación ante la AEAT. "
            "No constituye un escrito definitivo."
        )
        borrador_editado = st.text_area("Borrador (editable)", value=resultado["borrador"], height=400)
        st.download_button(
            "Descargar borrador",
            data=borrador_editado,
            file_name=f"borrador_{resultado['fichero']}.txt",
            mime="text/plain",
        )

        st.divider()
        lat = resultado["latencias_s"]
        st.caption(
            f"Latencia — triaje: {lat['triaje']:.2f} s · recuperación: "
            f"{lat['recuperacion']:.2f} s · generación: {lat['generacion']:.2f} s · "
            f"total: {lat['total']:.2f} s"
        )
