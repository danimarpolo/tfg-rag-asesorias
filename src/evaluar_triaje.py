#!/usr/bin/env python3
"""
evaluar_triaje.py
==================
Medición campo a campo del módulo de triaje (src/triaje.py) contra el golden
set anotado a mano (eval/golden_triaje.json).

No hay un único criterio de acierto: cada tipo de campo tiene el suyo (ver
capítulo 5 de la memoria):

  · nif, impuesto, ejercicio, periodo, plazo_dias
        Coincidencia exacta, normalizando mayúsculas y espacios. Se compara
        siempre un valor ya coercionado —nunca el JSON crudo sin procesar—:
        por defecto el que ha validado Pydantic (RequerimientoAEAT), y solo
        cuando ALGÚN OTRO campo hace fallar la validación completa del
        esquema, un "mejor esfuerzo" (_mejor_esfuerzo) que aplica esas mismas
        reglas de coerción campo a campo sobre el JSON crudo, para que ese
        fallo ajeno no arrastre a campos de ese documento que sí son
        correctos. Así, la accuracy por campo se calcula sobre TODOS los
        documentos que produjeron JSON parseable, no solo sobre los que
        validaron el esquema completo.
  · nif — además de la coincidencia exacta anterior, nif_formato_valido
        reporta aparte qué fracción tiene NIF/CIF con dígito de control
        correcto; un NIF mal formado ya NO invalida el esquema (ver
        decisiones.md, 2026-08-30).
  · importe
        Coincidencia exacta, pero separando los casos cuyo valor esperado es
        null: acertar un null (no liquida importe) no es lo mismo que acertar
        una cifra.
  · tipo_documento
        Coincidencia exacta sobre el conjunto cerrado de 5 valores, más una
        matriz de confusión.
  · articulos_citados
        Precisión / exhaustividad / F1 sobre el conjunto, normalizando cada
        referencia a forma canónica "LEY art. N" antes de comparar.

Las métricas agregadas se calculan sobre 13 documentos, excluyendo
config.TRIAJE_ABLACION_CASO (req_002.pdf): comparte los 8 campos de contenido
con TRIAJE_ABLACION_BASE (req_001.pdf) a propósito —solo cambia la
maquetación del PDF— y se reporta aparte como prueba de robustez.

Uso
---
    python src\\evaluar_triaje.py
    python src\\evaluar_triaje.py --out eval\\resultados_triaje.json --tabla eval\\tabla_triaje.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import config
import triaje
from triaje import extrae_documento, ResultadoTriaje


# ---------------------------------------------------------------------------
# Normalización para comparar
# ---------------------------------------------------------------------------

def normaliza_valor(v) -> str | None:
    """Normaliza un valor escalar para comparar sin depender de mayúsculas/espacios."""
    if v is None:
        return None
    return re.sub(r"\s+", " ", str(v)).strip().upper()


_LEY_ABREV = {"lgt": "LGT", "liva": "LIVA", "lirpf": "LIRPF", "riva": "RIVA", "rgat": "RGAT"}

_LEY_PATRONES = [
    (re.compile(r"real decreto\s*1624\s*/\s*1992"), "RIVA"),
    (re.compile(r"reglamento del impuesto sobre el valor a[nñ]adido"), "RIVA"),
    (re.compile(r"real decreto\s*1065\s*/\s*2007"), "RGAT"),
    (re.compile(r"reglamento general de las actuaciones"), "RGAT"),
    (re.compile(r"ley\s*58\s*/\s*2003"), "LGT"),
    (re.compile(r"general tributaria"), "LGT"),
    (re.compile(r"ley\s*37\s*/\s*1992"), "LIVA"),
    (re.compile(r"impuesto sobre el valor a[nñ]adido"), "LIVA"),
    (re.compile(r"ley\s*35\s*/\s*2006"), "LIRPF"),
    (re.compile(r"impuesto sobre la renta de las personas f[ií]sicas"), "LIRPF"),
]

_RE_NUM_RUN = re.compile(
    r"art(?:\.|iculos?)\.?\s*((?:\d+\s*(?:bis|ter|quater)?\s*(?:,|y|e|-)?\s*)+)"
)
_RE_NUM_UNO = re.compile(r"\d+\s*(?:bis|ter|quater)?")


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in t if not unicodedata.combining(c))


def _detecta_ley(texto_norm: str) -> str | None:
    for abrev, code in _LEY_ABREV.items():
        if re.search(rf"\b{abrev}\b", texto_norm):
            return code
    for patron, code in _LEY_PATRONES:
        if patron.search(texto_norm):
            return code
    return None


def normaliza_articulo(texto: str) -> list[str]:
    """
    Normaliza una referencia legal a forma canónica "LEY art. N".

    Admite tanto la forma abreviada que se le pide al modelo ("LGT art. 136",
    "art. 136 LGT") como citar la ley por su nombre completo, tal cual
    aparece en el propio documento ("artículo 136 de la Ley 58/2003, General
    Tributaria"). Si no se reconoce la ley o no hay número de artículo, se
    devuelve el texto normalizado tal cual: mejor un fallo de comparación
    visible que ocultar un caso que la normalización no cubre.
    """
    t = _sin_tildes(texto).lower()
    ley = _detecta_ley(t)
    m = _RE_NUM_RUN.search(t)
    numeros = [re.sub(r"\s+", "", n) for n in _RE_NUM_UNO.findall(m.group(1))] if m else []

    if not ley or not numeros:
        return [re.sub(r"\s+", " ", t).strip()]
    return [f"{ley} art. {n}" for n in numeros]


def normaliza_articulos(lista: list[str]) -> set[str]:
    resultado: set[str] = set()
    for item in lista:
        resultado.update(normaliza_articulo(item))
    return resultado


LEYES_INDEXADAS = {"LGT", "LIVA"}


# ---------------------------------------------------------------------------
# Comparación de un documento
# ---------------------------------------------------------------------------

CAMPOS_EXACTOS = ["nif", "impuesto", "ejercicio", "periodo", "plazo_dias"]


def _mejor_esfuerzo(crudo: dict | None) -> dict:
    """
    Coerción por campo, independiente entre sí, sobre un JSON crudo que NO
    llegó a validar como RequerimientoAEAT completo (algún campo incumplió el
    esquema y Pydantic invalidó el documento entero).

    Reutiliza exactamente las mismas reglas de coerción que el esquema
    (triaje.coerce_importe, triaje.normaliza_periodo_texto, los enums) para
    que un campo aquí rescatado se haya normalizado igual que si hubiera
    pasado por Pydantic — nunca se compara el JSON crudo sin coercionar. Un
    campo que ni siquiera con esta coerción laxa es interpretable queda
    ausente del dict devuelto (no se inventa un valor), así que la
    comparación posterior lo cuenta como fallo, no como "no evaluable".
    """
    r: dict = {}
    if not isinstance(crudo, dict):
        return r

    if isinstance(crudo.get("nif"), str):
        r["nif"] = triaje.normaliza_nif_texto(crudo["nif"])

    for campo, enum_cls in (("tipo_documento", triaje.TipoDocumento), ("impuesto", triaje.Impuesto)):
        try:
            r[campo] = enum_cls(crudo[campo]).value
        except (KeyError, ValueError):
            pass

    for campo in ("ejercicio", "plazo_dias"):
        try:
            r[campo] = int(crudo[campo])
        except (KeyError, TypeError, ValueError):
            pass

    if "periodo" in crudo:
        try:
            r["periodo"] = triaje.normaliza_periodo_texto(crudo["periodo"])
        except ValueError:
            pass

    if "importe" in crudo:
        try:
            r["importe"] = triaje.coerce_importe(crudo["importe"])
        except ValueError:
            pass

    if isinstance(crudo.get("articulos_citados"), list):
        r["articulos_citados"] = [str(a).strip() for a in crudo["articulos_citados"] if str(a).strip()]

    return r


def compara_documento(golden: dict, resultado: ResultadoTriaje) -> dict:
    # El valor validado por Pydantic tiene prioridad siempre que exista; el
    # "mejor esfuerzo" sobre el JSON crudo solo entra en juego cuando algún
    # OTRO campo hizo fallar la validación completa del esquema, para que ese
    # fallo ajeno no arrastre a campos de este documento que sí son correctos.
    if resultado.datos is not None:
        obtenido = resultado.datos.model_dump(mode="json")
        nif_fmt_valido = resultado.datos.nif_formato_valido
    else:
        obtenido = _mejor_esfuerzo(resultado.crudo)
        nif_fmt_valido = triaje.nif_formato_valido(obtenido["nif"]) if "nif" in obtenido else None

    aciertos_exactos = {}
    valores_obtenidos = {}
    for campo in CAMPOS_EXACTOS:
        esp = normaliza_valor(golden[campo])
        obt = normaliza_valor(obtenido.get(campo))
        aciertos_exactos[campo] = esp is not None and esp == obt
        valores_obtenidos[campo] = obt

    tipo_esperado = golden["tipo_documento"]
    tipo_obtenido = obtenido.get("tipo_documento", "(sin_datos)")
    acierto_tipo = tipo_esperado == tipo_obtenido

    importe_esperado = golden["importe"]
    importe_obtenido = obtenido.get("importe")
    if importe_esperado is None:
        importe_caso = "null"
        importe_acierto = importe_obtenido is None
    else:
        importe_caso = "valor"
        importe_acierto = (
            importe_obtenido is not None
            and abs(importe_obtenido - importe_esperado) < 0.005
        )

    esperados_norm = normaliza_articulos(golden["articulos_citados"])
    obtenidos_norm = normaliza_articulos(obtenido.get("articulos_citados", []))
    tp = len(esperados_norm & obtenidos_norm)
    precision = (tp / len(obtenidos_norm)) if obtenidos_norm else (1.0 if not esperados_norm else 0.0)
    recall = (tp / len(esperados_norm)) if esperados_norm else (1.0 if not obtenidos_norm else 0.0)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "fichero": golden["fichero"],
        "valido": resultado.valido,
        "intentos_usados": resultado.intentos_usados,
        "temperatura_usada": resultado.temperatura_usada,
        "latencia_s": round(resultado.latencia_s, 3),
        "error": resultado.error,
        "aciertos_exactos": aciertos_exactos,
        "valores_obtenidos": valores_obtenidos,
        "nif_formato_valido": nif_fmt_valido,
        "tipo_documento": {"esperado": tipo_esperado, "obtenido": tipo_obtenido, "acierto": acierto_tipo},
        "importe": {
            "caso": importe_caso,
            "esperado": importe_esperado,
            "obtenido": importe_obtenido,
            "acierto": importe_acierto,
        },
        "articulos_citados": {
            "esperados": sorted(esperados_norm),
            "obtenidos": sorted(obtenidos_norm),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        },
    }


# ---------------------------------------------------------------------------
# Agregación
# ---------------------------------------------------------------------------

def agrega(comparaciones: list[dict]) -> dict:
    n = len(comparaciones)

    accuracy_exactos = {
        campo: round(sum(c["aciertos_exactos"][campo] for c in comparaciones) / n, 4)
        for campo in CAMPOS_EXACTOS
    }

    aciertos_tipo = sum(c["tipo_documento"]["acierto"] for c in comparaciones)
    matriz_confusion: dict[str, dict[str, int]] = {}
    for c in comparaciones:
        esp = c["tipo_documento"]["esperado"]
        obt = c["tipo_documento"]["obtenido"]
        matriz_confusion.setdefault(esp, {}).setdefault(obt, 0)
        matriz_confusion[esp][obt] += 1

    casos_null = [c for c in comparaciones if c["importe"]["caso"] == "null"]
    casos_valor = [c for c in comparaciones if c["importe"]["caso"] == "valor"]
    importe_stats = {
        "n_null": len(casos_null),
        "acierto_null": round(sum(c["importe"]["acierto"] for c in casos_null) / len(casos_null), 4) if casos_null else None,
        "n_valor": len(casos_valor),
        "acierto_valor": round(sum(c["importe"]["acierto"] for c in casos_valor) / len(casos_valor), 4) if casos_valor else None,
    }

    articulos_stats = {
        "precision_media": round(sum(c["articulos_citados"]["precision"] for c in comparaciones) / n, 4),
        "recall_media": round(sum(c["articulos_citados"]["recall"] for c in comparaciones) / n, 4),
        "f1_media": round(sum(c["articulos_citados"]["f1"] for c in comparaciones) / n, 4),
        "por_documento": [
            {
                "fichero": c["fichero"],
                "precision": c["articulos_citados"]["precision"],
                "recall": c["articulos_citados"]["recall"],
                "f1": c["articulos_citados"]["f1"],
            }
            for c in sorted(comparaciones, key=lambda c: c["fichero"])
        ],
    }

    # Cobertura sobre el GOLDEN, no sobre lo extraído: la pregunta es qué
    # fracción de la normativa realmente citada en los requerimientos es
    # fundamentable con el índice actual (LGT/LIVA), algo que depende del
    # corpus, no de los aciertos/errores del extractor. Calcularla sobre lo
    # extraído (como en la versión anterior) mezclaba ambas cosas: una cita
    # mal atribuida a otra norma por el modelo (p. ej. "LIRPF art. 136" en
    # vez de "LGT art. 136") contaba como "fuera de índice" aunque el
    # artículo real sí estuviera indexado.
    todos_esperados = set()
    for c in comparaciones:
        todos_esperados.update(c["articulos_citados"]["esperados"])
    en_indice = sum(1 for a in todos_esperados if a.split(" art.")[0] in LEYES_INDEXADAS)
    fuera_indice = len(todos_esperados) - en_indice
    cobertura_indice = {
        "articulos_unicos_en_golden": len(todos_esperados),
        "en_lgt_liva": en_indice,
        "fuera_lgt_liva": fuera_indice,
        "fraccion_en_indice": round(en_indice / len(todos_esperados), 4) if todos_esperados else None,
    }

    validos_primera = sum(1 for c in comparaciones if c["valido"] and c["intentos_usados"] == 1)
    validos_total = sum(1 for c in comparaciones if c["valido"])
    rescatados = [c["fichero"] for c in comparaciones if c["valido"] and c["intentos_usados"] > 1]
    validacion = {
        "tasa_valida_primera": round(validos_primera / n, 4),
        "tasa_valida_tras_reintentos": round(validos_total / n, 4),
        "n_rescatados_por_reintento": len(rescatados),
        "ficheros_rescatados": rescatados,
    }

    con_nif = [c for c in comparaciones if c["nif_formato_valido"] is not None]
    calidad_nif = {
        "n_evaluados": len(con_nif),
        "tasa_formato_valido": round(sum(c["nif_formato_valido"] for c in con_nif) / len(con_nif), 4) if con_nif else None,
    }

    latencia_media = round(sum(c["latencia_s"] for c in comparaciones) / n, 3)

    return {
        "n_documentos": n,
        "accuracy_campos_exactos": accuracy_exactos,
        "tipo_documento": {
            "accuracy": round(aciertos_tipo / n, 4),
            "matriz_confusion": matriz_confusion,
        },
        "importe": importe_stats,
        "articulos_citados": articulos_stats,
        "cobertura_indice_lgt_liva": cobertura_indice,
        "validacion_pydantic": validacion,
        "calidad_nif": calidad_nif,
        "latencia_media_s": latencia_media,
    }


def compara_ablacion(golden_001: dict, comp_001: dict, comp_002: dict) -> dict:
    """
    req_001 y req_002 comparten los 8 campos de contenido a propósito (mismo
    contenido, maquetación de PDF distinta). Aquí no se compara contra el
    golden sino la extracción de un fichero contra la del otro: si el modelo
    es robusto a la maquetación, ambas extracciones deben coincidir entre sí
    (y, en consecuencia, con el golden, que es el mismo para los dos).
    """
    detalle = []
    for campo in CAMPOS_EXACTOS:
        detalle.append({
            "campo": campo,
            "esperado": golden_001[campo],
            "req_001_correcto": comp_001["aciertos_exactos"][campo],
            "req_002_correcto": comp_002["aciertos_exactos"][campo],
            "req_001_vs_req_002_coinciden": comp_001["valores_obtenidos"][campo] == comp_002["valores_obtenidos"][campo],
        })

    detalle.append({
        "campo": "tipo_documento",
        "esperado": golden_001["tipo_documento"],
        "req_001_correcto": comp_001["tipo_documento"]["acierto"],
        "req_002_correcto": comp_002["tipo_documento"]["acierto"],
        "req_001_vs_req_002_coinciden": comp_001["tipo_documento"]["obtenido"] == comp_002["tipo_documento"]["obtenido"],
    })

    detalle.append({
        "campo": "importe",
        "esperado": golden_001["importe"],
        "req_001_correcto": comp_001["importe"]["acierto"],
        "req_002_correcto": comp_002["importe"]["acierto"],
        "req_001_vs_req_002_coinciden": comp_001["importe"]["obtenido"] == comp_002["importe"]["obtenido"],
    })

    detalle.append({
        "campo": "articulos_citados",
        "esperado": sorted(normaliza_articulos(golden_001["articulos_citados"])),
        "req_001_f1": comp_001["articulos_citados"]["f1"],
        "req_002_f1": comp_002["articulos_citados"]["f1"],
        "req_001_vs_req_002_coinciden": set(comp_001["articulos_citados"]["obtenidos"]) == set(comp_002["articulos_citados"]["obtenidos"]),
    })

    return {
        "req_001": comp_001,
        "req_002": comp_002,
        "detalle_comparado": detalle,
    }


# ---------------------------------------------------------------------------
# Salida en markdown
# ---------------------------------------------------------------------------

def _fmt_pct(x: float | None) -> str:
    return f"{100 * x:.1f} %" if x is not None else "n/a"


def genera_markdown(resumen: dict, ablacion: dict) -> str:
    campos_exactos = resumen["accuracy_campos_exactos"]
    lineas = []
    lineas.append("# Triaje de requerimientos AEAT — extracción estructurada\n")
    lineas.append(
        f"Evaluación de `src/triaje.py` (modelo `{config.OLLAMA_MODEL}` vía Ollama) contra el "
        f"golden set anotado a mano (`eval/golden_triaje.json`), {resumen['n_documentos']} documentos "
        f"(excluye `{config.TRIAJE_ABLACION_CASO}`, reportado aparte como prueba de robustez frente "
        f"a la maquetación).\n"
    )

    lineas.append("## Accuracy por campo (coincidencia exacta)\n")
    lineas.append("| Campo | Accuracy |")
    lineas.append("|---|---:|")
    for campo in CAMPOS_EXACTOS:
        lineas.append(f"| {campo} | {_fmt_pct(campos_exactos[campo])} |")
    lineas.append(f"| tipo_documento | {_fmt_pct(resumen['tipo_documento']['accuracy'])} |")
    lineas.append("")

    imp = resumen["importe"]
    lineas.append("## Importe\n")
    lineas.append("| Caso | n | Accuracy |")
    lineas.append("|---|---:|---:|")
    lineas.append(f"| Esperado null | {imp['n_null']} | {_fmt_pct(imp['acierto_null'])} |")
    lineas.append(f"| Esperado con valor | {imp['n_valor']} | {_fmt_pct(imp['acierto_valor'])} |")
    lineas.append("")

    lineas.append("## Matriz de confusión — tipo_documento\n")
    tipos = sorted(resumen["tipo_documento"]["matriz_confusion"].keys())
    todos_obt = sorted({o for fila in resumen["tipo_documento"]["matriz_confusion"].values() for o in fila})
    cabecera = "| esperado \\ obtenido | " + " | ".join(todos_obt) + " |"
    lineas.append(cabecera)
    lineas.append("|---|" + "---:|" * len(todos_obt))
    for t in tipos:
        fila = resumen["tipo_documento"]["matriz_confusion"][t]
        lineas.append(f"| {t} | " + " | ".join(str(fila.get(o, 0)) for o in todos_obt) + " |")
    lineas.append("")

    art = resumen["articulos_citados"]
    lineas.append("## articulos_citados (precisión / exhaustividad / F1)\n")
    lineas.append("| Precisión media | Exhaustividad media | F1 media |")
    lineas.append("|---:|---:|---:|")
    lineas.append(f"| {_fmt_pct(art['precision_media'])} | {_fmt_pct(art['recall_media'])} | {_fmt_pct(art['f1_media'])} |")
    lineas.append("")

    lineas.append("### F1 por documento\n")
    lineas.append("| Fichero | Precisión | Exhaustividad | F1 |")
    lineas.append("|---|---:|---:|---:|")
    for d in art["por_documento"]:
        lineas.append(f"| {d['fichero']} | {_fmt_pct(d['precision'])} | {_fmt_pct(d['recall'])} | {_fmt_pct(d['f1'])} |")
    lineas.append("")

    cov = resumen["cobertura_indice_lgt_liva"]
    lineas.append("## Cobertura del índice (LGT/LIVA vs. otras normas)\n")
    lineas.append(
        "Calculada sobre los artículos del GOLDEN (no sobre lo extraído): mide qué parte de la "
        "normativa realmente citada en los requerimientos es fundamentable con el índice actual, "
        "con independencia de los aciertos o errores de atribución del extractor.\n"
    )
    lineas.append(
        f"De {cov['articulos_unicos_en_golden']} artículos únicos citados en el golden set: "
        f"**{cov['en_lgt_liva']}** pertenecen a LGT o LIVA (fundamentables con el índice actual) y "
        f"**{cov['fuera_lgt_liva']}** a otras normas (LIRPF, RIVA, RGAT) — "
        f"{_fmt_pct(cov['fraccion_en_indice'])} en índice.\n"
    )

    val = resumen["validacion_pydantic"]
    lineas.append("## Validación de esquema, reintentos y latencia\n")
    lineas.append("| Métrica | Valor |")
    lineas.append("|---|---:|")
    lineas.append(f"| Válida a la primera | {_fmt_pct(val['tasa_valida_primera'])} |")
    lineas.append(f"| Válida tras reintentos (máx. {config.TRIAJE_MAX_REINTENTOS}, temperaturas {config.TRIAJE_TEMPERATURAS}) | {_fmt_pct(val['tasa_valida_tras_reintentos'])} |")
    lineas.append(f"| Documentos rescatados por variar la temperatura | {val['n_rescatados_por_reintento']} |")
    if val["ficheros_rescatados"]:
        lineas.append(f"| Ficheros rescatados | {', '.join(val['ficheros_rescatados'])} |")
    lineas.append(f"| Latencia media / documento | {resumen['latencia_media_s']:.2f} s |")
    lineas.append("")

    nif_q = resumen["calidad_nif"]
    lineas.append("## Calidad de NIF (campo derivado, no invalida el esquema)\n")
    lineas.append(
        "`nif_formato_valido` se calcula siempre a partir del NIF extraído, tenga o no dígito de "
        "control correcto; un NIF mal formado ya no invalida el documento ni arrastra a los otros "
        "ocho campos (ver decisiones.md).\n"
    )
    lineas.append(f"Tasa de NIF con formato/dígito de control válido: {_fmt_pct(nif_q['tasa_formato_valido'])} "
                   f"({nif_q['n_evaluados']} documentos evaluados).\n")

    lineas.append(f"## Ablación de maquetación — `{config.TRIAJE_ABLACION_BASE}` vs. `{config.TRIAJE_ABLACION_CASO}`\n")
    lineas.append(
        "Mismo contenido de fondo (mismos 8 campos en el golden), maquetación de PDF distinta. "
        "Comparación de la extracción de un fichero contra la del otro, no contra el golden por "
        "separado, como prueba de robustez.\n"
    )
    lineas.append("| Campo | Esperado | req_001 correcto | req_002 correcto | ¿Coinciden entre sí? |")
    lineas.append("|---|---|---:|---:|---:|")
    for fila in ablacion["detalle_comparado"]:
        if fila["campo"] == "articulos_citados":
            lineas.append(
                f"| articulos_citados | {', '.join(fila['esperado'])} | "
                f"F1={fila['req_001_f1']:.2f} | F1={fila['req_002_f1']:.2f} | "
                f"{'sí' if fila['req_001_vs_req_002_coinciden'] else 'no'} |"
            )
        else:
            esperado = fila["esperado"] if fila["esperado"] is not None else "—"
            lineas.append(
                f"| {fila['campo']} | {esperado} | "
                f"{'✓' if fila['req_001_correcto'] else '✗'} | "
                f"{'✓' if fila['req_002_correcto'] else '✗'} | "
                f"{'sí' if fila['req_001_vs_req_002_coinciden'] else 'no'} |"
            )
    lineas.append("")

    return "\n".join(lineas) + "\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluación del módulo de triaje")
    p.add_argument("--golden", default=None, help="Ruta al golden set (por defecto config.TRIAJE_GOLDEN)")
    p.add_argument("--corpus", default=None, help="Directorio de PDF (por defecto config.TRIAJE_CORPUS_DIR)")
    p.add_argument("--out", default=None, help="JSON de resultados (por defecto eval/resultados_triaje.json)")
    p.add_argument("--tabla", default=None, help="Markdown de resultados (por defecto eval/tabla_triaje.md)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    golden_path = Path(args.golden) if args.golden else config.TRIAJE_GOLDEN
    corpus_dir = Path(args.corpus) if args.corpus else config.TRIAJE_CORPUS_DIR
    out_path = Path(args.out) if args.out else config.EVAL_DIR / "resultados_triaje.json"
    tabla_path = Path(args.tabla) if args.tabla else config.EVAL_DIR / "tabla_triaje.md"

    with open(golden_path, encoding="utf-8") as f:
        golden = {caso["fichero"]: caso for caso in json.load(f)}

    print(f"\nTriaje de {len(golden)} documentos · modelo {config.OLLAMA_MODEL} · {config.OLLAMA_URL}\n")

    comparaciones_por_fichero: dict[str, dict] = {}
    for fichero, caso in golden.items():
        ruta = corpus_dir / fichero
        resultado = extrae_documento(ruta)
        comp = compara_documento(caso, resultado)
        comparaciones_por_fichero[fichero] = comp

        estado = "OK" if resultado.valido else "FALLO"
        tipo_doc_ok = "si" if comp["tipo_documento"]["acierto"] else "no"
        print(f"  [{estado:>5}] {fichero} - intentos={resultado.intentos_usados} "
              f"(T={resultado.temperatura_usada}) - {resultado.latencia_s:.1f}s - "
              f"tipo_doc_ok={tipo_doc_ok} - articulos F1={comp['articulos_citados']['f1']:.2f} - "
              f"nif_formato_valido={comp['nif_formato_valido']}")

    principales = [
        comparaciones_por_fichero[f] for f in golden if f != config.TRIAJE_ABLACION_CASO
    ]
    resumen = agrega(principales)

    comp_001 = comparaciones_por_fichero[config.TRIAJE_ABLACION_BASE]
    comp_002 = comparaciones_por_fichero[config.TRIAJE_ABLACION_CASO]
    ablacion = compara_ablacion(golden[config.TRIAJE_ABLACION_BASE], comp_001, comp_002)

    print("\n" + "=" * 68)
    print("RESUMEN (13 documentos, excluye req_002)")
    print("=" * 68)
    for campo, acc in resumen["accuracy_campos_exactos"].items():
        print(f"  {campo:<15} {_fmt_pct(acc)}")
    print(f"  {'tipo_documento':<15} {_fmt_pct(resumen['tipo_documento']['accuracy'])}")
    print(f"  articulos_citados  P={_fmt_pct(resumen['articulos_citados']['precision_media'])}  "
          f"R={_fmt_pct(resumen['articulos_citados']['recall_media'])}  "
          f"F1={_fmt_pct(resumen['articulos_citados']['f1_media'])}")
    print(f"  Validación 1er intento : {_fmt_pct(resumen['validacion_pydantic']['tasa_valida_primera'])}")
    print(f"  Validación con reintentos: {_fmt_pct(resumen['validacion_pydantic']['tasa_valida_tras_reintentos'])}")
    print(f"  Rescatados por variar temperatura: {resumen['validacion_pydantic']['n_rescatados_por_reintento']} "
          f"{resumen['validacion_pydantic']['ficheros_rescatados']}")
    print(f"  Tasa NIF formato valido: {_fmt_pct(resumen['calidad_nif']['tasa_formato_valido'])}")
    print(f"  Latencia media   : {resumen['latencia_media_s']:.2f} s")
    print(f"  Cobertura indice (sobre golden): {_fmt_pct(resumen['cobertura_indice_lgt_liva']['fraccion_en_indice'])}")
    print("=" * 68 + "\n")

    resultado_final = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modelo": config.OLLAMA_MODEL,
        "resumen": resumen,
        "detalle": list(comparaciones_por_fichero.values()),
        "ablacion_maquetacion": ablacion,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultado_final, f, ensure_ascii=False, indent=2)
    print(f"Resultados guardados en {out_path}")

    tabla_md = genera_markdown(resumen, ablacion)
    with open(tabla_path, "w", encoding="utf-8") as f:
        f.write(tabla_md)
    print(f"Tabla guardada en {tabla_path}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
