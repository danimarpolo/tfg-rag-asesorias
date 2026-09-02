#!/usr/bin/env python3
"""
evaluar_drafting.py
====================
Ejecuta la cadena completa (triaje -> recuperación -> generación,
src/cadena.py) sobre el corpus de triaje y mide, con criterios
exclusivamente automáticos y verificables, la fundamentación jurídica del
borrador generado. No se mide calidad subjetiva del texto (redacción, estilo,
persuasión): eso exigiría un juicio humano que este script no puede emitir.

Métricas:

  · Tasa de fundamentación
        De los artículos citados en el CUERPO del borrador, qué fracción
        procede de algo que el modelo realmente tenía delante: la cabecera
        de un fragmento recuperado, O una autorreferencia presente dentro
        del TEXTO de un fragmento recuperado (p. ej. el art. 206 bis de la
        LGT cita en su propio articulado "el artículo 15 de esta Ley"; si el
        borrador repite esa remisión, no la ha inventado, la ha leído). Las
        citas se extraen del texto libre del borrador y se canonicalizan con
        el mismo criterio que evaluar_triaje.py ("LGT art. 136" y "artículo
        136 de la LGT" cuentan como la misma referencia).
  · Tasa de alucinación normativa (la métrica más importante; debería ser 0)
        Artículos citados en el borrador que NO aparecen ni como fragmento
        recuperado, ni como autorreferencia dentro de uno, ni en la lista de
        no fundamentables que se le entregó al modelo. Una cita alucinada es
        indistinguible en el texto de una cita legítima: por eso importa más
        que cualquier otra métrica de este script.
  · Presencia de elementos estructurales
        Encabezamiento, exposición de hechos, fundamentos de derecho y
        solicitud, detectados por marcadores de texto, no por juicio de
        calidad sobre su contenido.
  · Longitud media del borrador (en palabras) y latencia media, total y por
    etapa (triaje, recuperación, generación).

Las métricas se calculan sobre los 13 documentos principales del corpus
(excluye config.TRIAJE_ABLACION_CASO, igual que evaluar_triaje.py).

Uso
---
    python src\\evaluar_drafting.py
    python src\\evaluar_drafting.py --out eval\\resultados_drafting.json --tabla eval\\tabla_drafting.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import cadena
import config
import query
from evaluar_triaje import _LEY_ABREV, _LEY_PATRONES, _sin_tildes

# ---------------------------------------------------------------------------
# Extracción de citas del borrador
# ---------------------------------------------------------------------------

_RE_NUMERO_CITA = re.compile(r"art(?:\.|iculos?)\.?\s*(\d+\s*(?:bis|ter|quater)?)", re.IGNORECASE)
_VENTANA_LEY = 60  # caracteres alrededor del número donde se busca la ley


_RE_ANAFORICA = re.compile(r"\besta\s+ley\b|\besta\s+norma\b|\bdicha\s+ley\b|\bmisma\s+ley\b")


def _menciones_ley(t: str) -> list[tuple[int, int, str]]:
    """Todas las menciones explícitas de ley en el texto (inicio, fin, código), en orden."""
    menciones: list[tuple[int, int, str]] = []
    for abrev, code in _LEY_ABREV.items():
        for m in re.finditer(rf"\b{abrev}\b", t):
            menciones.append((m.start(), m.end(), code))
    for patron, code in _LEY_PATRONES:
        for m in patron.finditer(t):
            menciones.append((m.start(), m.end(), code))
    menciones.sort()
    return menciones


def extrae_citas_borrador(texto: str) -> set[str]:
    """
    Localiza cada mención de "artículo N" / "art. N" en el cuerpo de un
    borrador y le atribuye una ley, reutilizando el mismo vocabulario de
    leyes de evaluar_triaje.py (misma canonicalización "LEY art. N" que el
    resto del proyecto). Dos casos, no uno:

    - Si el número va seguido de una referencia anafórica ("de esta ley",
      "de esta norma"...), la ley es la última mencionada EXPLÍCITAMENTE
      antes de ese punto del texto (la ley ya establecida en el párrafo),
      no la mención léxicamente más próxima: un párrafo como "conforme al
      artículo 138 de la LGT, ... al apartado 7 del artículo 99 de esta
      ley" debe resolver "99" a LGT aunque la palabra "LGT" esté a bastante
      distancia y no sea la mención de ley más cercana en el texto.
    - En cualquier otro caso, se toma la mención de ley EXPLÍCITA más
      próxima al número dentro de una ventana de texto. Es necesario medir
      la distancia real, y no tomar la primera que se encuentre: una frase
      de cierre como "los artículos 101 y 168 de la LGT y el artículo 167
      ter de la LIVA" contiene dos leyes distintas próximas entre sí, y
      tomar la primera atribuiría "167 ter" a la LGT solo por aparecer antes
      en la misma ventana, aunque "LIVA" esté justo al lado del número.

    Una mención de artículo sin ley resoluble por ninguna de las dos vías se
    descarta: no hay base para atribuirle una norma sin inventarla.
    """
    t = _sin_tildes(texto).lower()
    menciones = _menciones_ley(t)

    citas: set[str] = set()
    for m in _RE_NUMERO_CITA.finditer(t):
        pos_numero = m.start(1)
        fin_numero = m.end(1)
        cola = t[fin_numero:fin_numero + 40]

        ley = None
        if _RE_ANAFORICA.search(cola):
            anteriores = [c for (ini, fin, c) in menciones if fin <= pos_numero]
            if anteriores:
                ley = anteriores[-1]

        if ley is None:
            inicio_v = max(0, pos_numero - _VENTANA_LEY)
            fin_v = min(len(t), fin_numero + _VENTANA_LEY)
            candidatas = [
                (abs(ini - pos_numero), c) for (ini, fin, c) in menciones if inicio_v <= ini < fin_v
            ]
            if candidatas:
                ley = min(candidatas, key=lambda c: c[0])[1]

        if ley:
            numero = re.sub(r"\s+", "", m.group(1))
            citas.add(f"{ley} art. {numero}")

    return citas


def _canon_desde_metadata(item: dict) -> str | None:
    ley, numero = item.get("ley"), item.get("numero", "")
    if not ley or not numero:
        return None
    return f"{ley} art. {numero.replace(' ', '')}"


def _autorreferencias_fragmento(item: dict) -> set[str]:
    """
    Números de artículo mencionados DENTRO del propio texto de un fragmento
    recuperado (autorreferencias del articulado, p. ej. el art. 206 bis de
    la LGT citando "el artículo 15 de esta Ley" en su propio contenido).

    Se atribuyen siempre a la MISMA ley del fragmento, sin necesidad de
    resolución anafórica: un artículo remite casi siempre a otro artículo de
    su propio texto legal, nunca a una ley distinta sin nombrarla
    explícitamente. Sin esto, una cita del borrador que reproduce fielmente
    una remisión interna del propio fragmento recuperado —no inventada, y
    presente en lo que el modelo realmente tenía delante— contaría como
    alucinación.
    """
    ley = item.get("ley")
    texto = item.get("texto")
    if not ley or not texto:
        return set()
    t = _sin_tildes(texto).lower()
    numeros = {re.sub(r"\s+", "", m.group(1)) for m in _RE_NUMERO_CITA.finditer(t)}
    return {f"{ley} art. {n}" for n in numeros}


# ---------------------------------------------------------------------------
# Elementos estructurales
# ---------------------------------------------------------------------------

_MARCADORES_ESTRUCTURA = {
    "encabezamiento": ["encabezamiento"],
    "hechos": ["exposicion de hechos", "hechos"],
    "fundamentos": ["fundamentos de derecho", "fundamentos juridicos", "fundamentos"],
    "solicitud": ["solicitud", "suplico"],
}


def detecta_estructura(texto: str) -> dict[str, bool]:
    t = _sin_tildes(texto).lower()
    return {
        seccion: any(marcador in t for marcador in marcadores)
        for seccion, marcadores in _MARCADORES_ESTRUCTURA.items()
    }


# ---------------------------------------------------------------------------
# Evaluación de un documento
# ---------------------------------------------------------------------------

def evalua_documento(resultado: cadena.ResultadoCadena) -> dict:
    borrador = resultado.borrador or ""
    citas_borrador = extrae_citas_borrador(borrador)

    # "Fundamentado" incluye tanto el propio fragmento recuperado (su
    # cabecera de artículo) como cualquier autorreferencia presente EN SU
    # TEXTO: ambas cosas están igualmente disponibles en lo que se entregó
    # al modelo como contexto.
    recuperados_canon = {
        c for c in (_canon_desde_metadata(r) for r in resultado.recuperados) if c
    }
    for r in resultado.recuperados:
        recuperados_canon |= _autorreferencias_fragmento(r)

    no_fundamentables_canon = set(resultado.no_fundamentables)

    fundamentadas = citas_borrador & recuperados_canon
    alucinadas = citas_borrador - recuperados_canon - no_fundamentables_canon

    n_citas = len(citas_borrador)
    tasa_fundamentacion = round(len(fundamentadas) / n_citas, 4) if n_citas else None
    tasa_alucinacion = round(len(alucinadas) / n_citas, 4) if n_citas else 0.0

    return {
        "fichero": resultado.fichero,
        "n_citas_borrador": n_citas,
        "citas_borrador": sorted(citas_borrador),
        "n_fundamentadas": len(fundamentadas),
        "n_alucinadas": len(alucinadas),
        "alucinadas": sorted(alucinadas),
        "tasa_fundamentacion": tasa_fundamentacion,
        "tasa_alucinacion": tasa_alucinacion,
        "estructura": detecta_estructura(borrador),
        "longitud_palabras": len(borrador.split()),
        "latencia_s": {
            "triaje": round(resultado.latencia_triaje_s, 3),
            "recuperacion": round(resultado.latencia_recuperacion_s, 3),
            "generacion": round(resultado.latencia_generacion_s, 3),
            "total": round(resultado.latencia_total_s, 3),
        },
    }


# ---------------------------------------------------------------------------
# Agregación
# ---------------------------------------------------------------------------

_SECCIONES = ["encabezamiento", "hechos", "fundamentos", "solicitud"]


def agrega(evaluaciones: list[dict]) -> dict:
    n = len(evaluaciones)

    n_citas_total = sum(e["n_citas_borrador"] for e in evaluaciones)
    n_fundamentadas_total = sum(e["n_fundamentadas"] for e in evaluaciones)
    n_alucinadas_total = sum(e["n_alucinadas"] for e in evaluaciones)

    tasa_fundamentacion = round(n_fundamentadas_total / n_citas_total, 4) if n_citas_total else None
    tasa_alucinacion = round(n_alucinadas_total / n_citas_total, 4) if n_citas_total else 0.0

    estructura_presente = {
        s: round(sum(e["estructura"][s] for e in evaluaciones) / n, 4) for s in _SECCIONES
    }

    longitud_media = round(sum(e["longitud_palabras"] for e in evaluaciones) / n, 1)

    latencia_media_s = {
        etapa: round(sum(e["latencia_s"][etapa] for e in evaluaciones) / n, 3)
        for etapa in ("triaje", "recuperacion", "generacion", "total")
    }

    return {
        "n_documentos": n,
        "n_citas_borrador_total": n_citas_total,
        "n_fundamentadas_total": n_fundamentadas_total,
        "n_alucinadas_total": n_alucinadas_total,
        "tasa_fundamentacion": tasa_fundamentacion,
        "tasa_alucinacion": tasa_alucinacion,
        "estructura_presente": estructura_presente,
        "longitud_media_palabras": longitud_media,
        "latencia_media_s": latencia_media_s,
        "por_documento": [
            {
                "fichero": e["fichero"],
                "n_citas_borrador": e["n_citas_borrador"],
                "tasa_fundamentacion": e["tasa_fundamentacion"],
                "tasa_alucinacion": e["tasa_alucinacion"],
                "estructura_completa": all(e["estructura"][s] for s in _SECCIONES),
                "longitud_palabras": e["longitud_palabras"],
            }
            for e in sorted(evaluaciones, key=lambda e: e["fichero"])
        ],
    }


# ---------------------------------------------------------------------------
# Salida en markdown
# ---------------------------------------------------------------------------

def _fmt_pct(x: float | None) -> str:
    return f"{100 * x:.1f} %" if x is not None else "n/a"


def genera_markdown(resumen: dict) -> str:
    lineas = []
    lineas.append("# Generación del borrador (drafting) — evaluación automática\n")
    lineas.append(
        f"Evaluación de `src/cadena.py` (modelo `{config.OLLAMA_MODEL}` vía Ollama) sobre "
        f"{resumen['n_documentos']} documentos (excluye `{config.TRIAJE_ABLACION_CASO}`, igual "
        "que `evaluar_triaje.py`). Métricas exclusivamente automáticas y verificables: ninguna "
        "mide calidad subjetiva de la redacción.\n"
    )

    lineas.append("## Fundamentación y alucinación normativa\n")
    lineas.append(
        "La tasa de alucinación —artículos citados en el borrador que no proceden ni de un "
        "fragmento recuperado ni de la lista de referencias no fundamentables— es la métrica "
        "más importante de este informe: debería ser 0.\n"
    )
    lineas.append("| Métrica | Valor |")
    lineas.append("|---|---:|")
    lineas.append(f"| Citas normativas totales en los borradores | {resumen['n_citas_borrador_total']} |")
    lineas.append(
        f"| Fundamentadas (proceden de un fragmento recuperado) | "
        f"{resumen['n_fundamentadas_total']} ({_fmt_pct(resumen['tasa_fundamentacion'])}) |"
    )
    lineas.append(
        f"| Alucinadas (ni recuperadas ni reconocidas como no disponibles) | "
        f"{resumen['n_alucinadas_total']} ({_fmt_pct(resumen['tasa_alucinacion'])}) |"
    )
    lineas.append("")

    lineas.append("## Elementos estructurales presentes\n")
    lineas.append("| Sección | Presente en |")
    lineas.append("|---|---:|")
    lineas.append(f"| Encabezamiento | {_fmt_pct(resumen['estructura_presente']['encabezamiento'])} |")
    lineas.append(f"| Exposición de hechos | {_fmt_pct(resumen['estructura_presente']['hechos'])} |")
    lineas.append(f"| Fundamentos de derecho | {_fmt_pct(resumen['estructura_presente']['fundamentos'])} |")
    lineas.append(f"| Solicitud | {_fmt_pct(resumen['estructura_presente']['solicitud'])} |")
    lineas.append("")

    lineas.append("## Longitud y latencia\n")
    lat = resumen["latencia_media_s"]
    lineas.append("| Métrica | Valor |")
    lineas.append("|---|---:|")
    lineas.append(f"| Longitud media del borrador | {resumen['longitud_media_palabras']:.1f} palabras |")
    lineas.append(f"| Latencia media — triaje | {lat['triaje']:.2f} s |")
    lineas.append(f"| Latencia media — recuperación | {lat['recuperacion']:.2f} s |")
    lineas.append(f"| Latencia media — generación | {lat['generacion']:.2f} s |")
    lineas.append(f"| Latencia media — total | {lat['total']:.2f} s |")
    lineas.append("")

    lineas.append("## Detalle por documento\n")
    lineas.append("| Fichero | Citas | Fundamentación | Alucinación | Estructura completa | Palabras |")
    lineas.append("|---|---:|---:|---:|---:|---:|")
    for d in resumen["por_documento"]:
        lineas.append(
            f"| {d['fichero']} | {d['n_citas_borrador']} | "
            f"{_fmt_pct(d['tasa_fundamentacion'])} | {_fmt_pct(d['tasa_alucinacion'])} | "
            f"{'si' if d['estructura_completa'] else 'no'} | {d['longitud_palabras']} |"
        )
    lineas.append("")

    return "\n".join(lineas) + "\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluación de la cadena de drafting")
    p.add_argument("--golden", default=None, help="Ruta al golden set (por defecto config.TRIAJE_GOLDEN)")
    p.add_argument("--corpus", default=None, help="Directorio de PDF (por defecto config.TRIAJE_CORPUS_DIR)")
    p.add_argument("-k", type=int, default=config.DEFAULT_TOP_K, help="Fragmentos a recuperar por documento")
    p.add_argument("--out", default=None, help="JSON de resultados (por defecto eval/resultados_drafting.json)")
    p.add_argument("--tabla", default=None, help="Markdown de resultados (por defecto eval/tabla_drafting.md)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    golden_path = Path(args.golden) if args.golden else config.TRIAJE_GOLDEN
    corpus_dir = Path(args.corpus) if args.corpus else config.TRIAJE_CORPUS_DIR
    out_path = Path(args.out) if args.out else config.EVAL_DIR / "resultados_drafting.json"
    tabla_path = Path(args.tabla) if args.tabla else config.EVAL_DIR / "tabla_drafting.md"

    with open(golden_path, encoding="utf-8") as f:
        ficheros = [c["fichero"] for c in json.load(f) if c["fichero"] != config.TRIAJE_ABLACION_CASO]

    print(f"\nDrafting de {len(ficheros)} documentos - modelo {config.OLLAMA_MODEL} - {config.OLLAMA_URL}\n")

    vs = query.abrir_indice()
    indice_articulos = cadena.construye_indice_articulos(vs)
    print(f"Indice: {len(indice_articulos)} articulos unicos disponibles para fundamentar\n")

    detalle = []
    evaluaciones = []
    for fichero in ficheros:
        ruta = corpus_dir / fichero
        resultado = cadena.procesa_documento(ruta, vs, indice_articulos, k=args.k)

        if not resultado.triaje_valido:
            print(f"  [AVISO] {fichero}: triaje no valido, se omite de la medicion ({resultado.error})")
            detalle.append({"fichero": fichero, "cadena": resultado.__dict__, "evaluacion": None})
            continue

        ev = evalua_documento(resultado)
        evaluaciones.append(ev)
        detalle.append({"fichero": fichero, "cadena": resultado.__dict__, "evaluacion": ev})

        print(f"  [OK] {fichero} - citas={ev['n_citas_borrador']} "
              f"fundamentadas={ev['n_fundamentadas']} alucinadas={ev['n_alucinadas']} "
              f"palabras={ev['longitud_palabras']} - {resultado.latencia_total_s:.1f}s")

    resumen = agrega(evaluaciones)

    print("\n" + "=" * 68)
    print(f"RESUMEN ({resumen['n_documentos']} documentos)")
    print("=" * 68)
    print(f"  Tasa de fundamentacion : {_fmt_pct(resumen['tasa_fundamentacion'])}")
    print(f"  Tasa de alucinacion    : {_fmt_pct(resumen['tasa_alucinacion'])}  <- deberia ser 0")
    print(f"  Estructura completa    : "
          f"{sum(1 for d in resumen['por_documento'] if d['estructura_completa'])}/{resumen['n_documentos']}")
    print(f"  Longitud media         : {resumen['longitud_media_palabras']:.1f} palabras")
    print(f"  Latencia media total   : {resumen['latencia_media_s']['total']:.2f} s")
    print("=" * 68 + "\n")

    resultado_final = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modelo": config.OLLAMA_MODEL,
        "resumen": resumen,
        "detalle": detalle,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultado_final, f, ensure_ascii=False, indent=2)
    print(f"Resultados guardados en {out_path}")

    tabla_md = genera_markdown(resumen)
    with open(tabla_path, "w", encoding="utf-8") as f:
        f.write(tabla_md)
    print(f"Tabla guardada en {tabla_path}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
