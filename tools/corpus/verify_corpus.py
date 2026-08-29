# -*- coding: utf-8 -*-
"""
Verifica que cada PDF contiene realmente lo que el golden afirma.

    python verify_corpus.py

Comprueba, documento a documento:
  - el texto es extraible y no hay glifos perdidos;
  - el NIF anotado aparece y su letra/digito de control es valido;
  - el ejercicio y el periodo (en alguna de sus formas de superficie) aparecen;
  - la cita normativa completa aparece literalmente;
  - el importe anotado aparece formateado en euros, o bien, si es null, el
    documento declara expresamente que no exige cantidad alguna;
  - el numero de dias de plazo aparece.
Y, sobre el conjunto: reparto por tipo, unicidad de ficheros y presencia de
los cinco casos dificiles.
"""

import json
import re
import sys

import pdfplumber

from build_corpus import (identificador, cita_articulos, nif_completo,
                          cif_completo, OUT_PDF, OUT_GOLDEN, RAIZ)
from corpus_spec import DOCS, PERIODO_TEXTO, IMPUESTOS

REPARTO_ESPERADO = {
    "requerimiento_documentacion": 4,
    "propuesta_liquidacion_provisional": 3,
    "requerimiento_iva_no_deducible": 3,
    "tramite_audiencia": 2,
    "acuerdo_inicio_sancionador": 2,
}

fallos, avisos = [], []


def norm(t):
    return re.sub(r"\s+", " ", t.replace("­", "")).strip()


def check(cond, doc, msg):
    if not cond:
        fallos.append(f"{doc}: {msg}")
    return cond


def nif_valido(ident):
    if re.fullmatch(r"\d{8}[A-Z]", ident):
        return ident == nif_completo(ident[:8])
    if re.fullmatch(r"[A-Z]\d{7}[0-9A-J]", ident):
        return ident == cif_completo(ident[:8])
    return False


def main():
    golden = json.load(open(OUT_GOLDEN, encoding="utf-8"))
    spec_por_fichero = {d["fichero"]: d for d in DOCS}

    check(len(golden) == 14, "GLOBAL", f"se esperaban 14 registros, hay {len(golden)}")
    check(len({g["fichero"] for g in golden}) == 14, "GLOBAL", "ficheros duplicados")

    reparto = {}
    for g in golden:
        reparto[g["tipo_documento"]] = reparto.get(g["tipo_documento"], 0) + 1
    for tipo, n in REPARTO_ESPERADO.items():
        check(reparto.get(tipo) == n, "GLOBAL",
              f"reparto de '{tipo}': {reparto.get(tipo)} != {n}")

    textos = {}
    for g in golden:
        f, spec = g["fichero"], spec_por_fichero[g["fichero"]]
        with pdfplumber.open(OUT_PDF / f) as pdf:
            txt = norm("\n".join((p.extract_text() or "") for p in pdf.pages))
            paginas = len(pdf.pages)
        textos[f] = txt

        check(len(txt) > 900, f, f"texto demasiado corto ({len(txt)} car.)")
        check(paginas <= 2, f, f"{paginas} páginas (se esperaba 1-2)")
        check("(cid:" not in txt, f, "glifos no incrustados en el PDF")
        check("DOCUMENTO SINTÉTICO" in txt, f, "falta el aviso de documento sintético")

        # --- NIF -------------------------------------------------------
        check(nif_valido(g["nif"]), f, f"NIF con control inválido: {g['nif']}")
        check(g["nif"] in txt, f, f"el NIF anotado {g['nif']} no aparece en el texto")

        # el NIF del representante NO debe ser la respuesta anotada
        if spec.get("representante"):
            r = spec["representante"]
            rid = identificador(r["tipo_id"], r["id_seed"])
            check(rid in txt, f, "el NIF del representante no aparece")
            check(rid != g["nif"], f, "el golden anota el NIF del representante")

        # --- impuesto, ejercicio, periodo ------------------------------
        # el golden normaliza a la sigla; el documento puede usar solo el nombre
        # desarrollado (asi ocurre en los documentos con los datos en el cuerpo)
        formas_imp = {g["impuesto"], IMPUESTOS[g["impuesto"]]}
        check(any(x in txt for x in formas_imp), f,
              f"no aparece el impuesto {g['impuesto']} en ninguna forma")
        if g["impuesto"] not in txt:
            avisos.append(f"{f}: solo nombre desarrollado del impuesto, sin la sigla "
                          f"{g['impuesto']} (dificultad intencionada)")
        check(str(g["ejercicio"]) in txt, f, f"no aparece el ejercicio {g['ejercicio']}")
        formas = {g["periodo"], PERIODO_TEXTO[g["periodo"]], spec["periodo_texto"]}
        if g["periodo"] == "0A":
            formas.add(f"ejercicio {g['ejercicio']}")
        check(any(x in txt for x in formas), f,
              f"el periodo {g['periodo']} no aparece en ninguna forma: {formas}")

        # --- articulos --------------------------------------------------
        cita = norm(cita_articulos(g["articulos_citados"]))
        check(cita in txt, f, f"la cita normativa no aparece literalmente:\n      {cita}")
        for a in g["articulos_citados"]:
            check(re.search(rf"\b{a.split(' art. ')[1]}\b", txt), f,
                  f"no aparece el número de artículo de {a}")

        # --- importe ----------------------------------------------------
        if g["importe"] is None:
            check(re.search(r"no (se practica liquidación|exige el ingreso|"
                            r"incorpora liquidación)", txt, re.I), f,
                  "importe null pero el documento no declara que no exige cantidad")
            check("TOTAL A INGRESAR" not in txt and "SANCIÓN PROPUESTA" not in txt, f,
                  "importe null pero el documento contiene un total exigido")
            check(re.search(r"\d{1,3}\.\d{3},\d{2}", txt), f,
                  "importe null sin cifras distractoras (el caso pierde dificultad)")
        else:
            s = f"{g['importe']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            check(s in txt, f, f"el importe anotado {s} no aparece en el texto")
            check(re.search(rf"{re.escape(s)} euros", txt), f,
                  f"el importe {s} aparece pero no como cantidad exigida en euros")

        # --- coherencia aritmetica interna del documento ------------------
        def num(t):
            return round(float(t.replace(".", "").replace(",", ".")), 2)

        if spec.get("desglose"):
            suma = round(sum(num(v) for _, v in spec["desglose"]), 2)
            check(suma == g["importe"], f,
                  f"el desglose suma {suma}, el importe anotado es {g['importe']}")
        if spec.get("sancion"):
            s = spec["sancion"]
            esperado = round(num(s["base"]) * int(s["porcentaje"]) / 100, 2)
            check(esperado == g["importe"], f,
                  f"base {s['base']} x {s['porcentaje']}% = {esperado}, "
                  f"pero el importe anotado es {g['importe']}")
        if spec.get("paralela") and spec.get("desglose"):
            cuota = num(spec["desglose"][0][1])
            difs = [round(abs(num(c) - num(d)), 2) for _, d, c in spec["paralela"]]
            check(cuota in difs, f,
                  f"ninguna fila de la paralela varía en la cuota propuesta ({cuota}); "
                  f"diferencias observadas: {sorted(set(difs))}")

        # --- plazo ------------------------------------------------------
        check(re.search(rf"{g['plazo_dias']} días hábiles", txt), f,
              f"no aparece 'plazo de {g['plazo_dias']} días hábiles'")
        if not spec["plazo_con_fecha"]:
            check("finalizando el" not in txt, f,
                  "el caso 'plazo sin fecha' contiene una fecha límite")

    # ---------------- casos dificiles -----------------------------------
    g = {x["fichero"]: x for x in golden}

    sin_fecha = [d["fichero"] for d in DOCS if not d["plazo_con_fecha"]]
    check(len(sin_fecha) == 1, "CASOS", f"plazo sin fecha: {sin_fecha}")

    dos_nif = [d["fichero"] for d in DOCS if d.get("representante")]
    check(len(dos_nif) == 1, "CASOS", f"dos NIF: {dos_nif}")

    cinco = [x["fichero"] for x in golden if len(x["articulos_citados"]) >= 4]
    check(len(cinco) == 1, "CASOS", f"4-5 artículos: {cinco}")
    if cinco:
        normas = {a.split(" art. ")[0] for a in g[cinco[0]]["articulos_citados"]}
        check(len(normas & {"RGAT", "RIVA"}) > 0 and len(normas & {"LGT", "LIVA", "LIRPF"}) > 0,
              "CASOS", f"el caso de 4-5 artículos no mezcla ley y reglamento: {normas}")

    # par de ablacion 001 / 002: identicos salvo el fichero
    a, b = dict(g["req_001.pdf"]), dict(g["req_002.pdf"])
    a.pop("fichero"), b.pop("fichero")
    check(a == b, "CASOS", "el par tabla/cuerpo no comparte los mismos valores")
    check("Concepto tributario" in textos["req_001.pdf"], "CASOS",
          "req_001 no lleva tabla de cabecera")
    check("Concepto tributario" not in textos["req_002.pdf"], "CASOS",
          "req_002 lleva tabla de cabecera (debería ir en el cuerpo)")
    check(g["req_002.pdf"]["nif"] in textos["req_002.pdf"], "CASOS",
          "req_002 no contiene el NIF en el cuerpo")

    sin_importe = [x["fichero"] for x in golden if x["importe"] is None]
    check("req_010.pdf" in sin_importe, "CASOS", "req_010 debería no tener importe")

    # ---------------- informe --------------------------------------------
    print(f"{'fichero':13s} {'tipo':34s} {'nif':11s} {'imp':5s} {'ej':5s} "
          f"{'per':4s} {'arts':5s} {'importe':>10s} {'plazo':>5s}")
    print("-" * 104)
    for x in golden:
        imp = "null" if x["importe"] is None else f"{x['importe']:.2f}"
        print(f"{x['fichero']:13s} {x['tipo_documento']:34s} {x['nif']:11s} "
              f"{x['impuesto']:5s} {x['ejercicio']:<5d} {x['periodo']:4s} "
              f"{len(x['articulos_citados']):<5d} {imp:>10s} {x['plazo_dias']:>5d}")
    print("-" * 104)

    for a in avisos:
        print("AVISO  ", a)
    if fallos:
        print(f"\n{len(fallos)} FALLOS:")
        for x in fallos:
            print("  ✗", x)
        sys.exit(1)
    print(f"\nOK · 14 documentos verificados contra {OUT_GOLDEN.relative_to(RAIZ)} "
          f"({sum(len(t) for t in textos.values()):,} caracteres extraídos).")


if __name__ == "__main__":
    main()
