#!/usr/bin/env python3
"""
cadena.py
=========
Cadena completa de generación del borrador de contestación (drafting): paso 6
del flujo del apartado 3.4, última pieza del módulo agéntico.

Encadena, sin introducir ningún comportamiento nuevo en los módulos que ya
existen:

    1. Triaje            -> triaje.extrae_documento (sin modificar)
    2. Clasificación      -> qué artículos citados son FUNDAMENTABLES
                             (norma indexada y artículo verificado contra
                             los metadatos reales del índice) y cuáles NO
    3. Consulta           -> plantilla determinista, sin LLM
    4. Recuperación       -> query.buscar (sin modificar)
    5. Generación         -> única llamada al modelo de triaje, con un
                             prompt que exige fundamentar solo en lo
                             recuperado

La verificación del paso 2 contra el índice (no solo contra la sigla de la
ley) es la pieza que importa: el triaje atribuye mal la norma en
aproximadamente la mitad de los casos (ver decisiones.md, 2026-08-30 y
2026-08-31), y sin esta comprobación ese fallo llegaría intacto y en
silencio hasta el borrador final.

Uso
---
    python src/cadena.py eval/corpus_triaje/req_001.pdf
    python src/cadena.py -k 8 eval/corpus_triaje/req_005.pdf
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from langchain_chroma import Chroma

import config
import query
import triaje
from evaluar_triaje import LEYES_INDEXADAS, normaliza_articulo
from triaje import RequerimientoAEAT

# ---------------------------------------------------------------------------
# 2. Clasificación de referencias citadas
# ---------------------------------------------------------------------------

_RE_CANONICO = re.compile(r"^([A-Z]+) art\. (.+)$")


def construye_indice_articulos(vs: Chroma) -> set[tuple[str, str]]:
    """
    Conjunto de (ley, número) realmente presentes en el índice, leído de los
    metadatos de ChromaDB. Se calcula una sola vez por ejecución (984
    fragmentos en el corpus actual) y se reutiliza para cada documento que
    se procese, en vez de releer los metadatos por documento.
    """
    datos = vs._collection.get(include=["metadatas"])
    indice: set[tuple[str, str]] = set()
    for m in datos["metadatas"]:
        ley, numero = m.get("ley"), m.get("numero", "")
        if ley and numero:
            indice.add((ley, numero.replace(" ", "")))
    return indice


def clasifica_articulos(
    articulos_citados: list[str], indice_articulos: set[tuple[str, str]]
) -> tuple[list[str], list[str]]:
    """
    Separa los artículos citados por el triaje en FUNDAMENTABLES (norma
    indexada y artículo verificado en el índice) y NO FUNDAMENTABLES (norma
    no indexada, o norma indexada pero artículo inexistente).

    Comprobar contra el índice, y no solo contra la sigla de la ley, es lo
    que convierte en detectable un fallo hoy silencioso: una cita "LIRPF
    art. 203" nunca es fundamentable porque LIRPF no está indexada, pero
    tampoco lo es una cita "LGT art. 9999" con sigla correcta si ese
    artículo no existe realmente en el índice.
    """
    fundamentables: list[str] = []
    no_fundamentables: list[str] = []
    vistos: set[str] = set()

    for cita in articulos_citados:
        for canon in normaliza_articulo(cita):
            if canon in vistos:
                continue
            vistos.add(canon)

            m = _RE_CANONICO.match(canon)
            es_fundamentable = False
            if m:
                ley, numero = m.group(1), m.group(2).replace(" ", "")
                es_fundamentable = ley in LEYES_INDEXADAS and (ley, numero) in indice_articulos

            (fundamentables if es_fundamentable else no_fundamentables).append(canon)

    return fundamentables, no_fundamentables


# ---------------------------------------------------------------------------
# 3. Formulación determinista de la consulta
# ---------------------------------------------------------------------------

_TIPO_DOCUMENTO_TEXTO = {
    "requerimiento_documentacion": "requerimiento de documentación",
    "propuesta_liquidacion_provisional": "propuesta de liquidación provisional",
    "requerimiento_iva_no_deducible": "requerimiento sobre IVA no deducible",
    "tramite_audiencia": "trámite de audiencia",
    "acuerdo_inicio_sancionador": "acuerdo de inicio de expediente sancionador",
}


def construye_consulta(datos: RequerimientoAEAT, fundamentables: list[str]) -> str:
    """
    Consulta de recuperación determinista, sin llamar al modelo de lenguaje:
    combina el impuesto, el tipo de documento (en texto legible) y los
    artículos fundamentables ya citados por el propio requerimiento, si los
    hay.
    """
    tipo_texto = _TIPO_DOCUMENTO_TEXTO.get(datos.tipo_documento.value, datos.tipo_documento.value)
    consulta = f"{datos.impuesto.value}: {tipo_texto}"
    if fundamentables:
        consulta += ". Normativa citada: " + ", ".join(fundamentables)
    return consulta


# ---------------------------------------------------------------------------
# 5. Generación del borrador
# ---------------------------------------------------------------------------

_PROMPT_DRAFTING = """Eres un asistente que redacta, para que un asesor fiscal lo revise \
antes de presentarlo, un borrador de escrito de contestación a un requerimiento de la \
Agencia Tributaria (AEAT) española.

DATOS DEL REQUERIMIENTO (extraídos automáticamente y ya validados):
- Tipo de documento: {tipo_documento}
- NIF del obligado tributario: {nif}
- Impuesto: {impuesto}
- Ejercicio: {ejercicio}
- Período: {periodo}
- Importe: {importe}
- Plazo de respuesta: {plazo_dias} días hábiles

FRAGMENTOS NORMATIVOS RECUPERADOS (única fuente admitida para fundamentar en derecho):
{fragmentos}

ARTÍCULOS QUE EL REQUERIMIENTO INVOCA PERO CUYO TEXTO NO ESTÁ DISPONIBLE (cítalos \
únicamente como referencia del propio requerimiento; no argumentes sobre su contenido, \
porque no dispones de él):
{no_fundamentables}

INSTRUCCIONES:
1. Fundamenta la argumentación jurídica ÚNICAMENTE en los fragmentos normativos \
recuperados arriba. Cada afirmación jurídica debe citar el artículo concreto del que \
procede (por ejemplo, "conforme al artículo 136 de la LGT").
2. Si el requerimiento invoca alguno de los artículos de la lista de no disponibles, \
menciónalo solo como cita del requerimiento original (por ejemplo, "el requerimiento \
invoca además el artículo 68 de la LIRPF"), sin argumentar sobre su contenido.
3. No inventes ningún artículo que no figure en los fragmentos normativos recuperados \
ni en la lista de no disponibles. Si no dispones de fundamento suficiente para algún \
punto, dilo explícitamente en vez de inventarlo.
4. Estructura el escrito en cuatro secciones, cada una encabezada en mayúsculas y en su \
propia línea: ENCABEZAMIENTO, EXPOSICIÓN DE HECHOS, FUNDAMENTOS DE DERECHO, SOLICITUD.
5. Redacta en español, en registro formal-administrativo, dirigido a la AEAT.

Devuelve solo el texto del escrito, sin explicaciones adicionales.
"""


def _cuerpo_fragmento(doc) -> str:
    """Cuerpo del fragmento sin la línea de contexto que antepone el particionador."""
    partes = doc.page_content.split("\n\n", 1)
    return partes[1] if len(partes) > 1 else doc.page_content


def _formatea_fragmentos(resultados_busqueda) -> str:
    if not resultados_busqueda:
        return "(ningún fragmento recuperado)"
    bloques = []
    for i, (doc, distancia) in enumerate(resultados_busqueda, start=1):
        articulo_id = doc.metadata.get("articulo_id", "")
        similitud = 1 - distancia
        bloques.append(f"[{i}] {articulo_id} (similitud={similitud:.2f})\n{_cuerpo_fragmento(doc)}")
    return "\n\n".join(bloques)


def _formatea_no_fundamentables(no_fundamentables: list[str]) -> str:
    if not no_fundamentables:
        return "(ninguno)"
    return "\n".join(f"- {ref}" for ref in no_fundamentables)


def _construye_prompt_drafting(
    datos: RequerimientoAEAT, resultados_busqueda, no_fundamentables: list[str]
) -> str:
    return _PROMPT_DRAFTING.format(
        tipo_documento=_TIPO_DOCUMENTO_TEXTO.get(datos.tipo_documento.value, datos.tipo_documento.value),
        nif=datos.nif,
        impuesto=datos.impuesto.value,
        ejercicio=datos.ejercicio,
        periodo=datos.periodo,
        importe=f"{datos.importe:.2f} euros" if datos.importe is not None else "no consta importe alguno",
        plazo_dias=datos.plazo_dias,
        fragmentos=_formatea_fragmentos(resultados_busqueda),
        no_fundamentables=_formatea_no_fundamentables(no_fundamentables),
    )


def _llama_ollama_drafting(prompt: str) -> str:
    resp = requests.post(
        config.OLLAMA_URL,
        json={
            "model": config.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": config.DRAFTING_TEMPERATURA,
                # Tope de longitud como red de seguridad: sin él, un bucle de
                # repetición del modelo (más probable a temperatura baja, sin
                # penalización de repetición) puede agotar el timeout.
                "num_predict": config.DRAFTING_MAX_TOKENS,
            },
        },
        timeout=config.DRAFTING_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

@dataclass
class ResultadoCadena:
    """Resultado de ejecutar triaje -> recuperación -> generación sobre un documento."""
    fichero: str
    triaje_valido: bool
    triaje: Optional[dict] = None
    fundamentables: list[str] = field(default_factory=list)
    no_fundamentables: list[str] = field(default_factory=list)
    consulta: str = ""
    recuperados: list[dict] = field(default_factory=list)
    borrador: Optional[str] = None
    error: Optional[str] = None
    latencia_triaje_s: float = 0.0
    latencia_recuperacion_s: float = 0.0
    latencia_generacion_s: float = 0.0

    @property
    def latencia_total_s(self) -> float:
        return self.latencia_triaje_s + self.latencia_recuperacion_s + self.latencia_generacion_s


def procesa_documento(
    ruta: Path,
    vs: Chroma,
    indice_articulos: set[tuple[str, str]],
    k: int = config.DEFAULT_TOP_K,
) -> ResultadoCadena:
    """Ejecuta la cadena completa sobre un único PDF de requerimiento."""
    fichero = ruta.name

    # 1. Triaje (sin modificar)
    t0 = time.perf_counter()
    resultado_triaje = triaje.extrae_documento(ruta)
    latencia_triaje = time.perf_counter() - t0

    if resultado_triaje.datos is None:
        return ResultadoCadena(
            fichero=fichero,
            triaje_valido=False,
            error=(
                f"Triaje no válido tras {resultado_triaje.intentos_usados} intento(s): "
                f"{resultado_triaje.error}"
            ),
            latencia_triaje_s=latencia_triaje,
        )

    datos = resultado_triaje.datos

    # 2. Clasificación de referencias
    fundamentables, no_fundamentables = clasifica_articulos(datos.articulos_citados, indice_articulos)

    # 3. Consulta determinista
    consulta = construye_consulta(datos, fundamentables)

    # 4. Recuperación (sin modificar)
    t1 = time.perf_counter()
    resultados_busqueda = query.buscar(vs, consulta, k, ley=None)
    latencia_recuperacion = time.perf_counter() - t1

    recuperados = [
        {
            "articulo_id": doc.metadata.get("articulo_id", ""),
            "ley": doc.metadata.get("ley", ""),
            "numero": doc.metadata.get("numero", ""),
            "similitud": round(1 - distancia, 4),
            # Cuerpo del fragmento (sin la línea de contexto): necesario para
            # que evaluar_drafting.py pueda distinguir una autorreferencia
            # DENTRO del propio articulado recuperado (p. ej. el art. 206 bis
            # de la LGT citando "el artículo 15 de esta Ley" en su propio
            # texto) de una cita realmente no fundamentada.
            "texto": _cuerpo_fragmento(doc),
        }
        for doc, distancia in resultados_busqueda
    ]

    # 5. Generación del borrador
    t2 = time.perf_counter()
    prompt = _construye_prompt_drafting(datos, resultados_busqueda, no_fundamentables)
    borrador = _llama_ollama_drafting(prompt)
    latencia_generacion = time.perf_counter() - t2

    return ResultadoCadena(
        fichero=fichero,
        triaje_valido=True,
        triaje=datos.model_dump(mode="json"),
        fundamentables=fundamentables,
        no_fundamentables=no_fundamentables,
        consulta=consulta,
        recuperados=recuperados,
        borrador=borrador,
        latencia_triaje_s=latencia_triaje,
        latencia_recuperacion_s=latencia_recuperacion,
        latencia_generacion_s=latencia_generacion,
    )


# ---------------------------------------------------------------------------
# CLI de prueba manual (un único documento)
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Cadena triaje + recuperación + generación (drafting)")
    p.add_argument("pdf", type=Path, help="Ruta al PDF del requerimiento")
    p.add_argument("-k", type=int, default=config.DEFAULT_TOP_K,
                   help=f"Fragmentos a recuperar (por defecto {config.DEFAULT_TOP_K})")
    args = p.parse_args()

    if not args.pdf.exists():
        print(f"[ERROR] No existe el fichero: {args.pdf}")
        return 1

    vs = query.abrir_indice()
    indice_articulos = construye_indice_articulos(vs)

    print(f"Procesando {args.pdf.name} ...")
    resultado = procesa_documento(args.pdf, vs, indice_articulos, k=args.k)

    if not resultado.triaje_valido:
        print(f"\n[ERROR] {resultado.error}")
        return 1

    print(f"\nfundamentables    : {resultado.fundamentables}")
    print(f"no_fundamentables : {resultado.no_fundamentables}")
    print(f"consulta          : {resultado.consulta!r}")
    print(f"recuperados       : {[r['articulo_id'] for r in resultado.recuperados]}")
    print(f"latencia (s)      : triaje={resultado.latencia_triaje_s:.2f} "
          f"recuperacion={resultado.latencia_recuperacion_s:.2f} "
          f"generacion={resultado.latencia_generacion_s:.2f} "
          f"total={resultado.latencia_total_s:.2f}")
    print("\n" + "=" * 68)
    print("BORRADOR")
    print("=" * 68)
    print(resultado.borrador)
    print("=" * 68 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
