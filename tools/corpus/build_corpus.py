# -*- coding: utf-8 -*-
"""
Genera los 14 PDF sinteticos del corpus de triaje y eval/golden_triaje.json.

    python build_corpus.py

Todo se deriva de corpus_spec.DOCS, de modo que el PDF y su anotacion no
pueden divergir. Los documentos son FICTICIOS y llevan un aviso explicito en
cabecera y pie: no son ni pueden pasar por notificaciones reales de la AEAT.
"""

import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, KeepTogether)

from corpus_spec import DOCS, NORMAS, IMPUESTOS, PERIODO_TEXTO

# Rutas relativas a la raiz del repositorio, no al directorio de trabajo:
# el script vive en tools/corpus/ y escribe en eval/, se lance desde donde se lance.
RAIZ = Path(__file__).resolve().parents[2]
OUT_PDF = RAIZ / "eval" / "corpus_triaje"
OUT_GOLDEN = RAIZ / "eval" / "golden_triaje.json"

# ---------------------------------------------------------------- identidad

_LETRAS_NIF = "TRWAGMYFPDXBNJZSQVHLCKE"
_CIF_LETRA_CONTROL = "JABCDEFGHI"
_CIF_SOLO_LETRA = set("KPQSNW")
_CIF_SOLO_DIGITO = set("ABEH")


def nif_completo(ocho_digitos: str) -> str:
    """NIF de persona fisica: 8 digitos + letra de control (modulo 23)."""
    return ocho_digitos + _LETRAS_NIF[int(ocho_digitos) % 23]


def cif_completo(letra_mas_siete: str) -> str:
    """NIF de persona juridica: letra + 7 digitos + caracter de control."""
    letra, digitos = letra_mas_siete[0].upper(), letra_mas_siete[1:]
    pares = sum(int(digitos[i]) for i in (1, 3, 5))
    impares = 0
    for i in (0, 2, 4, 6):
        d = int(digitos[i]) * 2
        impares += d // 10 + d % 10
    control = (10 - (pares + impares) % 10) % 10
    if letra in _CIF_SOLO_LETRA:
        return letra + digitos + _CIF_LETRA_CONTROL[control]
    return letra + digitos + str(control)


def identificador(tipo_id: str, seed: str) -> str:
    return nif_completo(seed) if tipo_id == "nif" else cif_completo(seed)


# ------------------------------------------------------------------- fechas

FESTIVOS = {
    date(2026, 1, 1), date(2026, 1, 6), date(2026, 2, 28), date(2026, 4, 2),
    date(2026, 4, 3), date(2026, 5, 1), date(2026, 8, 15), date(2026, 8, 19),
    date(2026, 9, 8), date(2026, 10, 12), date(2026, 11, 2), date(2026, 12, 7),
    date(2026, 12, 8), date(2026, 12, 25),
}

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def sumar_habiles(inicio: date, n: int) -> date:
    """Dia habil n contado a partir del siguiente al de la notificacion."""
    d, contados = inicio, 0
    while contados < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in FESTIVOS:
            contados += 1
    return d


def fecha_larga(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def csv_seguro(referencia: str) -> str:
    h = hashlib.sha256(referencia.encode()).hexdigest().upper()
    return "".join(c for c in h if c.isalnum())[:16]


def eur(txt: str) -> str:
    return f"{txt} euros"


# ------------------------------------------------------------------ estilos

GRIS = colors.HexColor("#444444")
GRIS_CLARO = colors.HexColor("#EFEFEF")
LINEA = colors.HexColor("#999999")
AVISO = colors.HexColor("#8A6D00")

S_AVISO = ParagraphStyle("aviso", fontName="Helvetica-Bold", fontSize=6.6,
                         leading=8, textColor=AVISO, alignment=TA_CENTER)
S_ORG = ParagraphStyle("org", fontName="Helvetica-Bold", fontSize=11.5, leading=13)
S_ORG2 = ParagraphStyle("org2", fontName="Helvetica", fontSize=7.6, leading=9.4,
                        textColor=GRIS, alignment=TA_RIGHT)
S_DEST = ParagraphStyle("dest", fontName="Helvetica", fontSize=9, leading=11.6)
S_REF = ParagraphStyle("ref", fontName="Helvetica", fontSize=8, leading=10.4)
S_TIT = ParagraphStyle("tit", fontName="Helvetica-Bold", fontSize=11, leading=14,
                       alignment=TA_CENTER, spaceBefore=4, spaceAfter=2)
S_SUB = ParagraphStyle("sub", fontName="Helvetica-Oblique", fontSize=8.6, leading=11,
                       alignment=TA_CENTER, textColor=GRIS, spaceAfter=6)
S_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.4, leading=13.2,
                        alignment=TA_JUSTIFY, spaceAfter=6)
S_LI = ParagraphStyle("li", parent=S_BODY, leftIndent=14, bulletIndent=4, spaceAfter=4)
S_H = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=9.4, leading=12,
                     spaceBefore=8, spaceAfter=4)
S_CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.4, leading=10.6)
S_CELLB = ParagraphStyle("cellb", parent=S_CELL, fontName="Helvetica-Bold")
S_FIRMA = ParagraphStyle("firma", fontName="Helvetica", fontSize=8.8, leading=11.6,
                         alignment=TA_CENTER)
S_PIE = ParagraphStyle("pie", fontName="Helvetica", fontSize=6.4, leading=8,
                       textColor=GRIS, alignment=TA_CENTER)

AVISO_TXT = ("DOCUMENTO SINTÉTICO GENERADO PARA PRUEBAS · NO ES UNA NOTIFICACIÓN REAL "
             "· NO PROCEDE DE LA AGENCIA ESTATAL DE ADMINISTRACIÓN TRIBUTARIA")


def _tabla(data, widths, style_extra=None, cabecera=False):
    t = Table(data, colWidths=widths, hAlign="LEFT")
    st = [
        ("GRID", (0, 0), (-1, -1), 0.4, LINEA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if cabecera:
        st.append(("BACKGROUND", (0, 0), (-1, 0), GRIS_CLARO))
    if style_extra:
        st.extend(style_extra)
    t.setStyle(TableStyle(st))
    return t


# ------------------------------------------------------------- construccion

def bloque_cabecera(doc, ident):
    """Membrete + destinatario + bloque de referencias."""
    story = []
    izq = Paragraph("AGENCIA TRIBUTARIA", S_ORG)
    der = Paragraph(
        "Delegación Especial de Andalucía, Ceuta y Melilla<br/>"
        f"{doc['oficina']}<br/>Unidad de Gestión Tributaria", S_ORG2)
    t = Table([[izq, der]], colWidths=[85 * mm, 85 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -1), 0.9, GRIS),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 7)]

    # Destinatario. En layout="cuerpo" el NIF no figura aqui: solo en el texto.
    lineas = [f"<b>{doc['titular_render']}</b>"]
    if doc["layout"] == "tabla":
        etiqueta = "NIF" if doc["tipo_id"] == "nif" else "NIF"
        lineas.append(f"{etiqueta}: {ident}")
    lineas += doc["domicilio"]
    dest = Paragraph("<br/>".join(lineas), S_DEST)

    refs = Paragraph(
        f"N.º de referencia: <b>{doc['referencia']}</b><br/>"
        f"N.º de justificante: {doc['justificante']}<br/>"
        f"Fecha de notificación: {fecha_larga(doc['fecha_notif'])}", S_REF)
    t2 = Table([[dest, refs]], colWidths=[95 * mm, 75 * mm], hAlign="LEFT")
    t2.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [t2, Spacer(1, 10)]
    return story


def bloque_titulo(doc):
    story = [Paragraph(doc["titulo"], S_TIT)]
    if doc.get("subtitulo"):
        story.append(Paragraph(doc["subtitulo"], S_SUB))
    else:
        story.append(Spacer(1, 4))
    return story


def tabla_datos(doc, ident):
    """Tabla de cabecera con los datos clave (solo layout='tabla')."""
    filas = [
        [Paragraph("Concepto tributario", S_CELLB),
         Paragraph(f"{IMPUESTOS[doc['impuesto']]} ({doc['impuesto']})", S_CELL),
         Paragraph("Modelo", S_CELLB), Paragraph(doc["modelo"], S_CELL)],
        [Paragraph("Ejercicio", S_CELLB), Paragraph(str(doc["ejercicio"]), S_CELL),
         Paragraph("Período", S_CELLB),
         Paragraph(f"{doc['periodo']} ({PERIODO_TEXTO[doc['periodo']]})", S_CELL)],
        [Paragraph("Obligado tributario", S_CELLB),
         Paragraph(doc["titular_render"], S_CELL),
         Paragraph("NIF", S_CELLB), Paragraph(ident, S_CELL)],
    ]
    if doc.get("representante"):
        r = doc["representante"]
        rid = identificador(r["tipo_id"], r["id_seed"])
        filas.append([Paragraph("Representante", S_CELLB),
                      Paragraph(f"{r['nombre']} · {r['cargo']}", S_CELL),
                      Paragraph("NIF", S_CELLB), Paragraph(rid, S_CELL)])
    return [_tabla(filas, [38 * mm, 62 * mm, 18 * mm, 52 * mm]), Spacer(1, 9)]


def frase_datos_en_cuerpo(doc, ident):
    """Los mismos datos clave, redactados dentro del texto (layout='cuerpo')."""
    if doc["periodo"] == "0A":
        loc = f"correspondiente al ejercicio {doc['ejercicio']}"
    else:
        codigo = f" ({doc['periodo']})" if doc.get("mostrar_codigo_periodo") else ""
        loc = (f"correspondiente al {doc['periodo_texto']}{codigo} "
               f"del ejercicio {doc['ejercicio']}")
    return (f"En relación con la autoliquidación del {IMPUESTOS[doc['impuesto']]}, "
            f"modelo {doc['modelo']}, {loc}, presentada por "
            f"{doc['titular_render']}, con NIF {ident} y domicilio fiscal en "
            f"{doc['domicilio'][0]}, {doc['domicilio'][1]}, esta Administración ha "
            f"iniciado las actuaciones que a continuación se indican.")


def cita_articulos(articulos):
    """Redaccion de la base normativa a partir de la lista de articulos."""
    por_norma = {}
    for a in articulos:
        norma, num = a.split(" art. ")
        por_norma.setdefault(norma, []).append(num)
    trozos = []
    for norma, nums in por_norma.items():
        arts = ("artículos " + ", ".join(nums[:-1]) + " y " + nums[-1]
                if len(nums) > 1 else "artículo " + nums[0])
        trozos.append(f"{arts} de {NORMAS[norma]}")
    if len(trozos) == 1:
        return trozos[0]
    return "; ".join(trozos[:-1]) + "; y " + trozos[-1]


def bloque_plazo(doc):
    n = doc["plazo_dias"]
    if not doc["plazo_con_fecha"]:
        # CASO DIFICIL: plazo relativo, sin fecha limite en el documento.
        return (f"El plazo para atender lo solicitado es de <b>{n} días hábiles</b>, "
                f"contados a partir del siguiente al de la notificación de este "
                f"documento.")
    fin = sumar_habiles(doc["fecha_notif"], n)
    return (f"El plazo para atender lo solicitado es de <b>{n} días hábiles</b>, "
            f"contados a partir del siguiente al de la notificación de este documento, "
            f"finalizando el <b>{fecha_larga(fin)}</b>.")


def bloque_distractores(doc):
    if not doc.get("distractores"):
        return []
    filas = [[Paragraph("Magnitud declarada / comprobada", S_CELLB),
              Paragraph("Importe (euros)", S_CELLB)]]
    for etiqueta, valor in doc["distractores"]:
        filas.append([Paragraph(etiqueta, S_CELL),
                      Paragraph(valor, ParagraphStyle("r", parent=S_CELL,
                                                      alignment=TA_RIGHT))])
    return [Paragraph("Datos que constan en esta Administración", S_H),
            _tabla(filas, [120 * mm, 50 * mm], cabecera=True), Spacer(1, 8)]


def bloque_paralela(doc):
    filas = [[Paragraph("Concepto", S_CELLB), Paragraph("Declarado", S_CELLB),
              Paragraph("Comprobado", S_CELLB)]]
    dr = ParagraphStyle("dr", parent=S_CELL, alignment=TA_RIGHT)
    for concepto, decl, comp in doc["paralela"]:
        filas.append([Paragraph(concepto, S_CELL), Paragraph(decl, dr),
                      Paragraph(comp, dr)])
    return [Paragraph("Comparación de los datos declarados con los comprobados", S_H),
            _tabla(filas, [90 * mm, 40 * mm, 40 * mm], cabecera=True), Spacer(1, 8)]


def bloque_desglose(doc, total_txt):
    dr = ParagraphStyle("dr", parent=S_CELL, alignment=TA_RIGHT)
    filas = [[Paragraph(c, S_CELL), Paragraph(v, dr)] for c, v in doc["desglose"]]
    filas.append([Paragraph("<b>TOTAL A INGRESAR</b>", S_CELLB),
                  Paragraph(f"<b>{total_txt}</b>", ParagraphStyle(
                      "drb", parent=S_CELLB, alignment=TA_RIGHT))])
    return [_tabla(filas, [120 * mm, 50 * mm],
                   style_extra=[("BACKGROUND", (0, -1), (-1, -1), GRIS_CLARO)]),
            Spacer(1, 8)]


def bloque_sancion(doc, total_txt):
    s = doc["sancion"]
    dr = ParagraphStyle("dr", parent=S_CELL, alignment=TA_RIGHT)
    filas = [
        [Paragraph("Base de la sanción", S_CELLB), Paragraph(s["base"], dr)],
        [Paragraph("Calificación de la infracción", S_CELLB),
         Paragraph(s["calificacion"], dr)],
        [Paragraph("Porcentaje aplicable", S_CELLB),
         Paragraph(f"{s['porcentaje']} %", dr)],
        [Paragraph("<b>SANCIÓN PROPUESTA</b>", S_CELLB),
         Paragraph(f"<b>{total_txt}</b>",
                   ParagraphStyle("drb", parent=S_CELLB, alignment=TA_RIGHT))],
    ]
    return [Paragraph("Cuantificación de la sanción propuesta", S_H),
            _tabla(filas, [120 * mm, 50 * mm],
                   style_extra=[("BACKGROUND", (0, -1), (-1, -1), GRIS_CLARO)]),
            Spacer(1, 8)]


def bloque_firma(doc):
    return [Spacer(1, 10),
            Paragraph(f"En Málaga, a {fecha_larga(doc['fecha_notif'])}", S_FIRMA),
            Spacer(1, 6),
            Paragraph(doc["firmante"], S_FIRMA),
            Spacer(1, 4),
            Paragraph("(Documento firmado electrónicamente · firma no visible en esta "
                      "muestra sintética)", S_PIE)]


# ----------------------------------------------------------- cuerpos por tipo

def cuerpo(doc, ident, importe_txt):
    st, base = [], cita_articulos(doc["articulos"])
    tipo = doc["tipo_documento"]

    if doc["layout"] == "cuerpo":
        st.append(Paragraph(frase_datos_en_cuerpo(doc, ident), S_BODY))
    else:
        st += tabla_datos(doc, ident)

    if doc.get("representante"):
        r = doc["representante"]
        rid = identificador(r["tipo_id"], r["id_seed"])
        st.append(Paragraph(
            f"Las presentes actuaciones se entienden con don {r['nombre']}, con NIF "
            f"{rid}, en su condición de {r['cargo'].lower()} del obligado tributario "
            f"{doc['titular_render']}, NIF {ident}, sin que ello altere la titularidad "
            f"de la obligación tributaria comprobada.", S_BODY))

    if doc.get("motivo"):
        st.append(Paragraph(doc["motivo"], S_BODY))

    if tipo == "requerimiento_documentacion":
        st.append(Paragraph(
            f"Al amparo de lo dispuesto en {base}, se le <b>requiere</b> para que aporte "
            f"la documentación que se relaciona a continuación:", S_BODY))
        st += bloque_distractores(doc)
        st.append(Paragraph("Documentación requerida", S_H))
        for i, d in enumerate(doc["documentacion"], 1):
            st.append(Paragraph(d, S_LI, bulletText=f"{i}."))
        st.append(Spacer(1, 6))
        st.append(Paragraph(bloque_plazo(doc), S_BODY))
        st.append(Paragraph(
            "Se le advierte que la desatención de este requerimiento puede constituir "
            "infracción tributaria y dar lugar a la imposición de la correspondiente "
            "sanción, así como a la continuación de las actuaciones con los datos que "
            "obran en poder de esta Administración. El presente documento no incorpora "
            "liquidación ni exige el ingreso de cantidad alguna.", S_BODY))

    elif tipo == "propuesta_liquidacion_provisional":
        st.append(Paragraph(
            f"De acuerdo con lo previsto en {base}, se formula la siguiente "
            f"<b>propuesta de liquidación provisional</b>, que se pone en su conocimiento "
            f"a efectos de que pueda formular alegaciones.", S_BODY))
        st += bloque_paralela(doc)
        st += bloque_desglose(doc, importe_txt)
        st.append(Paragraph(
            f"De la propuesta anterior resulta una cantidad a ingresar de "
            f"<b>{importe_txt} euros</b>.", S_BODY))
        st.append(Paragraph(bloque_plazo(doc), S_BODY))
        st.append(Paragraph(
            "Transcurrido dicho plazo sin que se hayan presentado alegaciones, se dictará "
            "la liquidación provisional que proceda, que le será notificada con indicación "
            "de los plazos y medios de impugnación.", S_BODY))

    elif tipo == "requerimiento_iva_no_deducible":
        st.append(Paragraph(
            f"En aplicación de {base}, se ponen de manifiesto las incidencias detectadas "
            f"en la deducción de las cuotas soportadas y se le requiere la documentación "
            f"que se indica.", S_BODY))
        st += bloque_distractores(doc)
        st.append(Paragraph("Documentación requerida", S_H))
        for i, d in enumerate(doc["documentacion"], 1):
            st.append(Paragraph(d, S_LI, bulletText=f"{i}."))
        st.append(Spacer(1, 6))
        if doc.get("desglose"):
            st.append(Paragraph(
                "Con la documentación anterior se le comunica, asimismo, la siguiente "
                "propuesta de liquidación provisional:", S_BODY))
            st += bloque_desglose(doc, importe_txt)
            st.append(Paragraph(
                f"De la propuesta resulta una cantidad a ingresar de "
                f"<b>{importe_txt} euros</b>.", S_BODY))
        else:
            st.append(Paragraph(
                "Este requerimiento tiene por objeto exclusivamente la aportación de la "
                "documentación relacionada. <b>No se practica liquidación ni se exige el "
                "ingreso de cantidad alguna</b>; las cifras reproducidas más arriba son "
                "las declaradas por usted y se recogen únicamente a efectos "
                "identificativos.", S_BODY))
        st.append(Paragraph(bloque_plazo(doc), S_BODY))

    elif tipo == "tramite_audiencia":
        st.append(Paragraph(doc["alegaciones_ctx"], S_BODY))
        st += bloque_distractores(doc)
        st.append(Paragraph(
            f"En cumplimiento de lo establecido en {base}, se le comunica la apertura del "
            f"<b>trámite de audiencia</b>, poniéndose de manifiesto el expediente para que "
            f"pueda examinarlo y formular las alegaciones y aportar los documentos y "
            f"justificantes que estime pertinentes.", S_BODY))
        st.append(Paragraph(
            f"De la comprobación practicada resulta, con carácter provisional, una deuda "
            f"tributaria de <b>{importe_txt} euros</b>.", S_BODY))
        st.append(Paragraph(bloque_plazo(doc), S_BODY))

    elif tipo == "acuerdo_inicio_sancionador":
        st.append(Paragraph(
            f"Al amparo de {base}, se acuerda el <b>inicio del procedimiento sancionador</b> "
            f"y se le comunica simultáneamente la propuesta de resolución, al obrar en el "
            f"expediente todos los elementos que permiten formularla.", S_BODY))
        st += bloque_sancion(doc, importe_txt)
        s = doc["sancion"]
        st.append(Paragraph(
            f"El importe de la sanción propuesta asciende a <b>{importe_txt} euros</b>. "
            f"Dicho importe podrá reducirse en un {s['reduccion_conformidad']} por ciento "
            f"en caso de conformidad con la propuesta y, sobre la cantidad resultante, en "
            f"un {s['reduccion_pronto_pago']} por ciento adicional si se realiza el ingreso "
            f"en período voluntario sin solicitar aplazamiento y no se interpone recurso.",
            S_BODY))
        st.append(Paragraph(bloque_plazo(doc), S_BODY))
        st.append(Paragraph(
            "Transcurrido el plazo indicado sin que se formulen alegaciones, la propuesta "
            "de resolución podrá elevarse a definitiva.", S_BODY))

    return st


# --------------------------------------------------------------- documento

class Plantilla(BaseDocTemplate):
    def __init__(self, filename, doc_spec, **kw):
        super().__init__(filename, pagesize=A4,
                         leftMargin=20 * mm, rightMargin=20 * mm,
                         topMargin=18 * mm, bottomMargin=18 * mm, **kw)
        self.doc_spec = doc_spec
        frame = Frame(self.leftMargin, self.bottomMargin, self.width,
                      self.height - 8 * mm, id="cuerpo")
        self.addPageTemplates([PageTemplate(id="std", frames=[frame],
                                            onPage=self._decoracion)])

    def _decoracion(self, canv, doc):
        d = self.doc_spec
        w, h = A4
        canv.saveState()
        # Banda superior de aviso
        canv.setFillColor(colors.HexColor("#FFF8DC"))
        canv.setStrokeColor(AVISO)
        canv.setLineWidth(0.4)
        canv.rect(20 * mm, h - 15 * mm, w - 40 * mm, 7 * mm, stroke=1, fill=1)
        canv.setFillColor(AVISO)
        # tamano ajustado para que el aviso nunca desborde el recuadro
        tam, ancho_max = 6.6, w - 46 * mm
        while canv.stringWidth(AVISO_TXT, "Helvetica-Bold", tam) > ancho_max:
            tam -= 0.1
        canv.setFont("Helvetica-Bold", tam)
        canv.drawCentredString(w / 2, h - 12.7 * mm, AVISO_TXT)
        # Pie
        canv.setStrokeColor(LINEA)
        canv.setLineWidth(0.4)
        canv.line(20 * mm, 14 * mm, w - 20 * mm, 14 * mm)
        canv.setFillColor(GRIS)
        canv.setFont("Helvetica", 6.2)
        canv.drawString(20 * mm, 10.6 * mm,
                        f"Código Seguro de Verificación (CSV): {csv_seguro(d['referencia'])}")
        canv.drawRightString(w - 20 * mm, 10.6 * mm, f"Página {doc.page}")
        canv.drawString(20 * mm, 7.4 * mm,
                        "Sede electrónica (ficticia): sede.ejemplo-aeat.test  ·  "
                        "Documento ficticio para evaluación de un prototipo académico. "
                        "No procede de la AEAT.")
        canv.restoreState()


def construir(doc_spec):
    ident = identificador(doc_spec["tipo_id"], doc_spec["id_seed"])
    if doc_spec["importe"] is not None:
        importe_txt = f"{doc_spec['importe']:,.2f}".replace(",", "X") \
            .replace(".", ",").replace("X", ".")
    else:
        importe_txt = None

    story = []
    story += bloque_cabecera(doc_spec, ident)
    story += bloque_titulo(doc_spec)
    story += cuerpo(doc_spec, ident, importe_txt)
    story += bloque_firma(doc_spec)

    Plantilla(str(OUT_PDF / doc_spec["fichero"]), doc_spec).build(story)
    return ident


def golden(doc_spec, ident):
    return {
        "fichero": doc_spec["fichero"],
        "tipo_documento": doc_spec["tipo_documento"],
        "nif": ident,
        "impuesto": doc_spec["impuesto"],
        "ejercicio": doc_spec["ejercicio"],
        "periodo": doc_spec["periodo"],
        "articulos_citados": doc_spec["articulos"],
        "importe": doc_spec["importe"],
        "plazo_dias": doc_spec["plazo_dias"],
    }


def main():
    OUT_PDF.mkdir(parents=True, exist_ok=True)
    anotaciones = []
    for spec in DOCS:
        ident = construir(spec)
        anotaciones.append(golden(spec, ident))
        print(f"  {spec['fichero']:14s} {spec['tipo_documento']:36s} {ident}")
    with open(OUT_GOLDEN, "w", encoding="utf-8") as f:
        json.dump(anotaciones, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n{len(anotaciones)} documentos en {OUT_PDF.relative_to(RAIZ)}/ "
          f"y {OUT_GOLDEN.relative_to(RAIZ)} generados.")


if __name__ == "__main__":
    main()
