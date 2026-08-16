#!/usr/bin/env python3
"""
evaluate.py
===========
Evaluación cuantitativa de la calidad de la recuperación.

Este script es el que convierte el prototipo en un EXPERIMENTO reproducible en
lugar de una demo. Ejecuta un conjunto de preguntas de referencia
(eval/golden_set.json), en el que para cada pregunta se han anotado a mano los
artículos que un asesor consideraría correctos, y calcula:

  · Recall@k  — porcentaje de preguntas en las que al menos un artículo
                esperado aparece entre los k primeros resultados.
  · MRR       — Mean Reciprocal Rank: 1/posición del primer acierto,
                promediado. Penaliza que el artículo correcto salga el 5.º
                en lugar del 1.º.
  · Cobertura — fracción de TODOS los artículos esperados que se recuperan.

Estos son los números que justifican empíricamente en el capítulo 5 las
decisiones de diseño del capítulo 3 (estrategia de chunking, modelo de
embeddings, valor de k). Reejecuta el script cada vez que cambies un parámetro
y guarda los resultados: la tabla comparativa se construye sola.

Uso
---
    python src/evaluate.py
    python src/evaluate.py --out eval/resultados_e5base.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime

from langchain_chroma import Chroma

import config
from embeddings import get_embeddings


def normaliza_id(valor: str) -> str:
    """
    Normaliza un identificador de artículo para comparar sin depender de
    tildes, mayúsculas ni espaciado.  "LGT Artículo 66" -> "lgt articulo 66"
    """
    v = unicodedata.normalize("NFKD", valor)
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = re.sub(r"\s+", " ", v.lower()).strip()
    return v


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluación del recuperador RAG")
    p.add_argument("--golden", default=None,
                   help="Ruta al conjunto de evaluación (por defecto eval/golden_set.json)")
    p.add_argument("--out", default=None,
                   help="Guarda los resultados en un JSON para la memoria")
    p.add_argument("-k", type=int, default=config.EVAL_MAX_K,
                   help="Profundidad máxima de recuperación")
    p.add_argument("--verbose", action="store_true",
                   help="Muestra los resultados recuperados de cada pregunta")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    golden_path = (config.EVAL_DIR / "golden_set.json") if args.golden is None else args.golden
    try:
        with open(golden_path, encoding="utf-8") as f:
            casos = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] No se encuentra el conjunto de evaluación: {golden_path}")
        return 1

    if not config.CHROMA_DIR.exists():
        print("[ERROR] No hay índice. Ejecuta primero:  python src/ingest.py --reset")
        return 1

    vs = Chroma(
        collection_name=config.COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(config.CHROMA_DIR),
    )

    k_values = [k for k in config.EVAL_K_VALUES if k <= args.k]
    aciertos = {k: 0 for k in k_values}
    suma_rr = 0.0
    suma_cobertura = 0.0
    detalle = []

    print(f"\nEvaluando {len(casos)} preguntas · modelo {config.EMBEDDING_MODEL} · k={args.k}\n")

    for caso in casos:
        pregunta = caso["pregunta"]
        esperados = {normaliza_id(a) for a in caso["esperados"]}

        docs = vs.similarity_search(pregunta, k=args.k)
        # Ranking de artículos únicos: si un artículo aporta 2 fragmentos, su
        # posición es la del mejor de ellos.
        ranking, vistos = [], set()
        for d in docs:
            aid = normaliza_id(d.metadata["articulo_id"])
            if aid not in vistos:
                vistos.add(aid)
                ranking.append(aid)

        # Posición (1-based) del primer acierto
        primera = next((i + 1 for i, aid in enumerate(ranking) if aid in esperados), None)

        for k in k_values:
            if primera is not None and primera <= k:
                aciertos[k] += 1

        rr = 1.0 / primera if primera else 0.0
        suma_rr += rr

        recuperados_ok = esperados & set(ranking)
        cobertura = len(recuperados_ok) / len(esperados) if esperados else 0.0
        suma_cobertura += cobertura

        estado = "OK " if primera == 1 else (f"~{primera} " if primera else "FALLO")
        print(f"  [{estado:>5}] {pregunta[:66]}")
        if primera is None or args.verbose:
            print(f"           esperados : {caso['esperados']}")
            print(f"           top-{min(5, args.k)}     : {ranking[:5]}")

        detalle.append({
            "pregunta": pregunta,
            "esperados": caso["esperados"],
            "primera_posicion": primera,
            "reciprocal_rank": round(rr, 4),
            "cobertura": round(cobertura, 4),
            "top_k": ranking[:args.k],
        })

    n = len(casos)
    resumen = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modelo_embeddings": config.EMBEDDING_MODEL,
        "max_chunk_chars": config.MAX_CHUNK_CHARS,
        "chunk_overlap": config.CHUNK_OVERLAP,
        "n_preguntas": n,
        "recall_at_k": {str(k): round(aciertos[k] / n, 4) for k in k_values},
        "mrr": round(suma_rr / n, 4),
        "cobertura_media": round(suma_cobertura / n, 4),
    }

    print("\n" + "=" * 68)
    print("RESULTADOS")
    print("=" * 68)
    for k in k_values:
        print(f"  Recall@{k:<3} ....... {aciertos[k]}/{n}  = {100 * aciertos[k] / n:5.1f} %")
    print(f"  MRR ............... {resumen['mrr']:.4f}")
    print(f"  Cobertura media ... {100 * resumen['cobertura_media']:5.1f} %")
    print("=" * 68)
    print(f"  Configuración: chunk={config.MAX_CHUNK_CHARS} overlap={config.CHUNK_OVERLAP}")
    print("=" * 68 + "\n")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"resumen": resumen, "detalle": detalle}, f,
                      ensure_ascii=False, indent=2)
        print(f"Resultados guardados en {args.out}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
