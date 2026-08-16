#!/usr/bin/env python3
"""
query.py
========
Consulta semántica por consola contra el índice vectorial.

Este script aísla el paso 5 del flujo descrito en el apartado 3.4 de la
memoria ("Recuperación de contexto normativo"). NO genera ningún borrador ni
llama a un LLM: su único objetivo es responder a la pregunta que constituye el
mayor riesgo técnico del proyecto —¿el sistema recupera los artículos
correctos?—, de forma aislada y observable.

Si la recuperación falla, ninguna ingeniería de prompts posterior lo arregla.

Uso
---
    python src/query.py "¿Qué plazo tengo para recurrir una liquidación?"
    python src/query.py -k 8 "devengo del impuesto en entregas de bienes"
    python src/query.py --ley LIVA "requisitos para deducir el IVA soportado"
    python src/query.py                     # modo interactivo (REPL)
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from langchain_chroma import Chroma

import config
from embeddings import get_embeddings


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Consulta semántica sobre la normativa indexada")
    p.add_argument("consulta", nargs="*", help="Texto de la consulta")
    p.add_argument("-k", type=int, default=config.DEFAULT_TOP_K,
                   help=f"Número de fragmentos a recuperar (por defecto {config.DEFAULT_TOP_K})")
    p.add_argument("--ley", help="Filtra por ley: LGT o LIVA")
    p.add_argument("--full", action="store_true",
                   help="Muestra el fragmento completo en lugar de un extracto")
    return p.parse_args()


def abrir_indice() -> Chroma:
    """Abre el índice persistido. El modelo de embeddings debe ser el mismo
    que se usó en la ingesta; por eso ambos scripts llaman a get_embeddings()."""
    if not config.CHROMA_DIR.exists():
        print(f"[ERROR] No existe el índice en {config.CHROMA_DIR}")
        print("        Ejecuta primero:  python src/ingest.py --reset")
        sys.exit(1)

    return Chroma(
        collection_name=config.COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(config.CHROMA_DIR),
    )


def buscar(vs: Chroma, consulta: str, k: int, ley: str | None):
    """Devuelve una lista de (Document, distancia) ordenada por relevancia."""
    filtro = {"ley": {"$eq": ley.upper()}} if ley else None
    return vs.similarity_search_with_score(consulta, k=k, filter=filtro)


def mostrar(resultados, full: bool = False) -> None:
    if not resultados:
        print("\n  Sin resultados. ¿Has filtrado por una ley que no está indexada?\n")
        return

    print()
    for pos, (doc, distancia) in enumerate(resultados, start=1):
        m = doc.metadata
        # Con espacio métrico coseno:  similitud = 1 - distancia
        similitud = 1 - distancia

        cabecera = f"[{pos}] {m['articulo_id']}"
        if m.get("titulo"):
            cabecera += f" — {m['titulo']}"
        if m.get("total_fragmentos", 1) > 1:
            cabecera += f"  (frag. {m['fragmento']}/{m['total_fragmentos']})"

        print("─" * 78)
        print(f"{cabecera}")
        print(f"    similitud={similitud:.4f}   distancia={distancia:.4f}   "
              f"fuente={m['referencia_boe']}")
        print()

        # El contenido lleva la línea de contexto que añadió el splitter; la
        # separamos para que el extracto muestre articulado real.
        partes = doc.page_content.split("\n\n", 1)
        cuerpo = partes[1] if len(partes) > 1 else doc.page_content
        texto = cuerpo if full else textwrap.shorten(cuerpo, width=420, placeholder=" […]")
        print(textwrap.indent(textwrap.fill(texto, width=74), "    "))
        print()
    print("─" * 78)


def main() -> int:
    args = parse_args()
    vs = abrir_indice()

    try:
        total = vs._collection.count()
        print(f"\nÍndice: {total:,} fragmentos · modelo: {config.EMBEDDING_MODEL}")
    except Exception:
        pass

    # --- Modo directo -----------------------------------------------------
    if args.consulta:
        consulta = " ".join(args.consulta)
        print(f"Consulta: {consulta!r}" + (f"  [ley={args.ley.upper()}]" if args.ley else ""))
        mostrar(buscar(vs, consulta, args.k, args.ley), args.full)
        return 0

    # --- Modo interactivo -------------------------------------------------
    print("Modo interactivo. Escribe una consulta y pulsa Enter.")
    print("Comandos:  :k <n>   cambia el top-k")
    print("           :ley <LGT|LIVA|*>   filtra por ley")
    print("           :q      salir\n")

    k, ley = args.k, args.ley
    while True:
        try:
            linea = input(f"[k={k}{' ley=' + ley.upper() if ley else ''}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not linea:
            continue
        if linea in (":q", ":quit", ":salir"):
            return 0
        if linea.startswith(":k "):
            k = int(linea[3:].strip())
            continue
        if linea.startswith(":ley "):
            valor = linea[5:].strip()
            ley = None if valor in ("*", "todas") else valor
            continue

        mostrar(buscar(vs, linea, k, ley), args.full)


if __name__ == "__main__":
    sys.exit(main())
