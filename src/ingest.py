#!/usr/bin/env python3
"""
ingest.py
=========
Proceso de ingesta del corpus normativo en la base de datos vectorial.

Corresponde al proceso DESACOPLADO descrito en el apartado 3.3.3 de la memoria:
no forma parte del ciclo de respuesta a una petición de usuario, sino que es un
trabajo de preparación de datos que se ejecuta una vez (y se repite solo cuando
cambia la normativa o la estrategia de chunking).

Uso
---
    # 1) Solo trocear y ver estadísticas, SIN calcular embeddings (rápido).
    #    Úsalo para iterar sobre la estrategia de chunking.
    python src/ingest.py --dry-run

    # 2) Ingesta completa (borra el índice previo y lo reconstruye).
    python src/ingest.py --reset

    # 3) Ingesta de una sola ley.
    python src/ingest.py --only LGT --reset
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from collections import Counter

import config
from embeddings import get_embeddings
from legal_splitter import build_chunk_id, load_and_split


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingesta de normativa tributaria en ChromaDB")
    p.add_argument("--reset", action="store_true",
                   help="Elimina el índice existente antes de ingerir")
    p.add_argument("--dry-run", action="store_true",
                   help="Trocea y muestra estadísticas sin calcular embeddings")
    p.add_argument("--only", metavar="LEY",
                   help="Procesa solo la ley indicada (p. ej. LGT o LIVA)")
    p.add_argument("--sample", type=int, default=0, metavar="N",
                   help="Muestra N fragmentos de ejemplo al terminar el troceado")
    return p.parse_args()


def resumen_chunks(chunks) -> None:
    """Imprime estadísticas del troceado. Son los números que irán al cap. 4."""
    if not chunks:
        return

    longitudes = [len(c.page_content) for c in chunks]
    por_ley = Counter(c.metadata["ley"] for c in chunks)
    articulos = {(c.metadata["ley"], c.metadata["numero"]) for c in chunks}
    partidos = sum(1 for c in chunks if c.metadata["total_fragmentos"] > 1)

    print("\n" + "=" * 68)
    print("ESTADÍSTICAS DEL TROCEADO")
    print("=" * 68)
    print(f"  Fragmentos totales .............. {len(chunks):,}")
    print(f"  Artículos / disposiciones ....... {len(articulos):,}")
    print(f"  Fragmentos por ley .............. {dict(por_ley)}")
    print(f"  Fragmentos de artículos partidos  {partidos:,} "
          f"({100 * partidos / len(chunks):.1f}%)")
    print(f"  Longitud media .................. {sum(longitudes) // len(longitudes):,} caracteres")
    print(f"  Longitud mín / máx .............. {min(longitudes):,} / {max(longitudes):,}")
    print("=" * 68)


def main() -> int:
    args = parse_args()

    if not config.DATA_DIR.exists():
        print(f"[ERROR] No existe el directorio {config.DATA_DIR}")
        return 1

    # -- 1. Carga y troceado --------------------------------------------
    print("\n>>> FASE 1: carga y troceado de los PDFs\n")
    todos = []
    procesados = 0

    for nombre, meta in config.CORPUS.items():
        if args.only and meta["ley"].upper() != args.only.upper():
            continue

        ruta = config.DATA_DIR / nombre
        if not ruta.exists():
            print(f"  [AVISO] No encontrado: {ruta}  -> se omite")
            continue

        print(f"  [{meta['ley']}] {nombre}")
        try:
            chunks = load_and_split(ruta, meta)
        except ValueError as e:
            print(f"    [ERROR] {e}")
            continue

        print(f"    · {len(chunks):,} fragmentos generados\n")
        todos.extend(chunks)
        procesados += 1

    if not todos:
        print("[ERROR] No se ha generado ningún fragmento.")
        print("        Comprueba que los PDFs están en data/normativa/ con el")
        print("        nombre exacto declarado en config.CORPUS.")
        return 1

    resumen_chunks(todos)

    if args.sample:
        print(f"\n--- {args.sample} FRAGMENTOS DE EJEMPLO ---")
        paso = max(1, len(todos) // args.sample)
        for c in todos[::paso][:args.sample]:
            print(f"\n[{c.metadata['articulo_id']}] "
                  f"(frag. {c.metadata['fragmento']}/{c.metadata['total_fragmentos']}, "
                  f"{len(c.page_content)} car.)")
            print(c.page_content[:300].replace("\n", " ") + "...")

    if args.dry_run:
        print("\n[dry-run] No se ha calculado ningún embedding ni escrito en Chroma.")
        return 0

    # -- 2. Reset del índice --------------------------------------------
    if args.reset and config.CHROMA_DIR.exists():
        print(f"\n>>> Eliminando índice previo: {config.CHROMA_DIR}")
        shutil.rmtree(config.CHROMA_DIR)

    # -- 3. Embeddings + persistencia -----------------------------------
    # El import se hace aquí y no arriba para que --dry-run no cargue torch
    # ni el modelo (ahorra ~20 s en cada iteración del chunker).
    from langchain_chroma import Chroma

    print(f"\n>>> FASE 2: cálculo de embeddings")
    print(f"    Modelo: {config.EMBEDDING_MODEL} (device={config.EMBEDDING_DEVICE})")
    print("    La primera ejecución descarga el modelo (~500 MB). Ten paciencia.\n")

    t0 = time.time()
    emb = get_embeddings()

    vs = Chroma(
        collection_name=config.COLLECTION_NAME,
        embedding_function=emb,
        persist_directory=str(config.CHROMA_DIR),
        # Si tu versión de chromadb rechaza este argumento, coméntalo: el
        # ranking no cambia (los vectores están normalizados), solo la escala
        # numérica de las distancias que imprime query.py.
        collection_metadata={"hnsw:space": config.CHROMA_DISTANCE},
    )

    lote = config.INGEST_BATCH_SIZE
    for i in range(0, len(todos), lote):
        trozo = todos[i:i + lote]
        vs.add_documents(documents=trozo, ids=[build_chunk_id(d) for d in trozo])
        hechos = min(i + lote, len(todos))
        print(f"    Indexados {hechos:,}/{len(todos):,} fragmentos "
              f"({100 * hechos / len(todos):.0f}%)")

    elapsed = time.time() - t0

    print("\n" + "=" * 68)
    print("INGESTA COMPLETADA")
    print("=" * 68)
    print(f"  Leyes procesadas ................ {procesados}")
    print(f"  Fragmentos indexados ............ {len(todos):,}")
    print(f"  Tiempo total .................... {elapsed:.1f} s "
          f"({1000 * elapsed / len(todos):.0f} ms/fragmento)")
    print(f"  Índice persistido en ............ {config.CHROMA_DIR}")
    print("=" * 68)
    print("\nSiguiente paso:  python src/query.py \"plazo para recurrir una liquidación\"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
