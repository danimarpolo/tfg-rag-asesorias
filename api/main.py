#!/usr/bin/env python3
"""
api/main.py
===========
Backend mínimo del MVP (apartado 3.2.2 de la memoria): expone la cadena de
generación del borrador (src/cadena.py) por HTTP. Sin autenticación, sin
gestión de usuarios y sin base de datos relacional: el almacén de
expedientes es un diccionario en memoria (EXPEDIENTES) que se pierde al
reiniciar el proceso. Es deliberadamente el mínimo necesario para una demo
—no una simulación de un almacén transaccional persistente—, consistente
con el alcance del prototipo descrito en el apartado 4.1.

Cuatro endpoints:
    POST /expedientes                    sube un PDF, crea el expediente
    POST /expedientes/{id}/procesar      ejecuta cadena.procesa_documento
    GET  /expedientes/{id}               resultado completo
    GET  /expedientes                    lista con estado

No modifica cadena.py, config.py, query.py ni triaje.py: los reutiliza tal
cual, importándolos desde src/ (ver _SRC_DIR más abajo).

Arranque (PowerShell, desde la raíz del repositorio, con .venv activado)
-------------------------------------------------------------------------
    uvicorn api.main:app --reload --port 8000

Requiere que el índice vectorial ya exista (python src\\ingest.py --reset)
y que Ollama esté sirviendo el modelo configurado en config.OLLAMA_MODEL.
"""

from __future__ import annotations

import sys
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

# ---------------------------------------------------------------------------
# src/ no es un paquete instalado: sus módulos hacen "import config",
# "import query", etc. (rutas relativas a su propio directorio). Se añade
# esa ruta a sys.path para reutilizarlos tal cual están escritos, sin
# modificarlos ni duplicar su lógica aquí.
# ---------------------------------------------------------------------------
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC_DIR))

import cadena  # noqa: E402
import config  # noqa: E402
import query  # noqa: E402

# ---------------------------------------------------------------------------
# Estado en memoria
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="aeat_expedientes_"))

# id -> {id, fichero, ruta, estado, fecha_creacion, resultado, error}.
# estado: "pendiente" | "procesando" | "completado" | "error".
# Sin lock: un diccionario y una demo de un único usuario concurrente no lo
# necesitan; no es la simplificación que un sistema en producción debería
# adoptar, pero sí la adecuada para el alcance de este MVP.
EXPEDIENTES: dict[str, dict] = {}

# Índice vectorial y conjunto de artículos verificables (apartado 4.6.1):
# se abren una sola vez al arrancar, igual que hace evaluar_drafting.py
# para los 13 documentos del corpus, no en cada petición.
_RECURSOS: dict = {"vs": None, "indice_articulos": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _RECURSOS["vs"] = query.abrir_indice()
    _RECURSOS["indice_articulos"] = cadena.construye_indice_articulos(_RECURSOS["vs"])
    yield


app = FastAPI(
    title="API del MVP — Requerimientos AEAT",
    description="Backend mínimo del prototipo: sube un requerimiento, procesa la cadena y consulta el resultado.",
    lifespan=lifespan,
)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resumen(exp: dict) -> dict:
    return {
        "id": exp["id"],
        "fichero": exp["fichero"],
        "estado": exp["estado"],
        "fecha_creacion": exp["fecha_creacion"],
    }


def _completo(exp: dict) -> dict:
    """Resultado completo de un expediente: resumen + ResultadoCadena, si ya se procesó."""
    base = _resumen(exp)
    r = exp["resultado"]
    if r is None:
        return {**base, "error": exp.get("error")}
    return {
        **base,
        "triaje_valido": r["triaje_valido"],
        "error": r["error"],
        "triaje": r["triaje"],
        "fundamentables": r["fundamentables"],
        "no_fundamentables": r["no_fundamentables"],
        "consulta": r["consulta"],
        "recuperados": r["recuperados"],
        "borrador": r["borrador"],
        "latencias_s": {
            "triaje": r["latencia_triaje_s"],
            "recuperacion": r["latencia_recuperacion_s"],
            "generacion": r["latencia_generacion_s"],
            "total": r["latencia_triaje_s"] + r["latencia_recuperacion_s"] + r["latencia_generacion_s"],
        },
    }


@app.post("/expedientes")
def crear_expediente(pdf: UploadFile = File(...)):
    nombre = pdf.filename or ""
    if pdf.content_type != "application/pdf" and not nombre.lower().endswith(".pdf"):
        raise HTTPException(400, "El fichero debe ser un PDF")

    expediente_id = uuid.uuid4().hex
    ruta = UPLOAD_DIR / f"{expediente_id}.pdf"
    ruta.write_bytes(pdf.file.read())

    EXPEDIENTES[expediente_id] = {
        "id": expediente_id,
        "fichero": nombre,
        "ruta": ruta,
        "estado": "pendiente",
        "fecha_creacion": _ahora(),
        "resultado": None,
        "error": None,
    }
    return {"id": expediente_id}


@app.post("/expedientes/{expediente_id}/procesar")
def procesar_expediente(expediente_id: str):
    exp = EXPEDIENTES.get(expediente_id)
    if exp is None:
        raise HTTPException(404, "Expediente no encontrado")

    exp["estado"] = "procesando"

    # Llamada síncrona y bloqueante: el procesamiento completo tarda en
    # torno a 43 s en el corpus medido (apartado 5.3.4 de la memoria),
    # dominado por las dos invocaciones al modelo de lenguaje. Lo correcto
    # en producción sería resolverlo con una cola de tareas (p. ej.
    # Celery/RQ) y notificar al cliente de forma asíncrona; para un MVP con
    # un único usuario concurrente esperado, eso es alcance excesivo. El
    # timeout es deliberadamente holgado: no se acorta aquí el de config
    # (OLLAMA_TIMEOUT = 120 s por intento de triaje, hasta 3 intentos;
    # DRAFTING_TIMEOUT = 300 s para la generación), y uvicorn no impone por
    # sí mismo ningún límite adicional sobre el tiempo de una petición.
    try:
        resultado = cadena.procesa_documento(
            exp["ruta"], _RECURSOS["vs"], _RECURSOS["indice_articulos"], k=config.DEFAULT_TOP_K
        )
    except Exception as e:
        exp["estado"] = "error"
        exp["error"] = str(e)
        raise HTTPException(500, f"Fallo al procesar el expediente: {e}") from e

    exp["resultado"] = asdict(resultado)
    exp["estado"] = "completado" if resultado.triaje_valido else "error"
    exp["error"] = resultado.error
    return _completo(exp)


@app.get("/expedientes/{expediente_id}")
def obtener_expediente(expediente_id: str):
    exp = EXPEDIENTES.get(expediente_id)
    if exp is None:
        raise HTTPException(404, "Expediente no encontrado")
    return _completo(exp)


@app.get("/expedientes")
def listar_expedientes():
    return [_resumen(exp) for exp in EXPEDIENTES.values()]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
