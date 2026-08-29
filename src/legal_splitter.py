"""
legal_splitter.py
=================
Carga, limpieza y particionado semántico-estructural de textos normativos
consolidados del BOE.

Implementa la estrategia descrita en el apartado 3.3.3 de la memoria: en lugar
de trocear el corpus por longitud fija de caracteres (lo que produce fragmentos
que mezclan el final de un artículo con el principio del siguiente), se
respetan las fronteras naturales del texto legal —artículo y disposición—, y
solo se subdivide un artículo cuando su extensión supera el límite fijado.

Pipeline:

    PDF  ->  texto por páginas (pypdf)
         ->  limpieza de cabeceras, pies e índice del BOE
         ->  detección de encabezados "Artículo N." / "Disposición ..."
         ->  troceado por artículo
         ->  subtroceado de artículos largos (con solapamiento)
         ->  lista de Document con metadatos de trazabilidad

Nota de diseño: se usa `pypdf` directamente en lugar de `PyPDFLoader` de
`langchain-community`. Ambos usan el mismo motor de extracción, pero el acceso
directo evita una dependencia pesada adicional y da control página a página
sobre la eliminación de cabeceras y pies, que en los consolidados del BOE se
repiten en las ~200 páginas del documento.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

import config

# Separador interno del metadato `articulo_ids` (estrategia "longitud_fija"):
# ChromaDB solo admite valores escalares en los metadatos, no listas, así que
# un fragmento que solape varios artículos los guarda como cadena delimitada.
# Ningún identificador de artículo contiene "|".
ARTICULO_IDS_SEP = "|"


# ===========================================================================
# 1. Limpieza del texto extraído
# ===========================================================================

# Líneas de "ruido" que aparecen repetidas en cada página del consolidado del
# BOE y que, de no eliminarse, se cuelan dentro de los fragmentos y contaminan
# los embeddings.
NOISE_LINE_PATTERNS = [
    r"^\s*BOLETÍN OFICIAL DEL ESTADO\s*$",
    r"^\s*LEGISLACIÓN CONSOLIDADA\s*$",
    r"^\s*TEXTO CONSOLIDADO\s*$",
    r"^\s*ÍNDICE\s*$",
    r"^\s*Página\s+\d+\s*$",
    r"^\s*Referencia:\s*BOE-",
    r"^\s*Última modificación:",
    r"^\s*\d{1,4}\s*$",          # números de página sueltos
    r"\.\s?\.\s?\.\s?\.",        # líneas del índice con puntos guía ". . . . 45"
]

_NOISE_RE = re.compile("|".join(NOISE_LINE_PATTERNS), re.MULTILINE)


def clean_boe_text(raw: str) -> str:
    """
    Elimina cabeceras, pies de página y entradas del índice del texto extraído.

    Conserva deliberadamente los saltos de línea originales: son los puntos de
    corte naturales que aprovecha después RecursiveCharacterTextSplitter.
    """
    lines = []
    for line in raw.splitlines():
        if _NOISE_RE.search(line):
            continue
        lines.append(line.rstrip())

    text = "\n".join(lines)
    # Colapsa runs de 3+ saltos de línea a 2 (separador de párrafo).
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def normalize_whitespace(text: str) -> str:
    """Normaliza el espaciado para el texto que se almacena definitivamente."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return text.strip()


# ===========================================================================
# 2. Detección de encabezados legales
# ===========================================================================

# "Artículo 66." / "Artículo 1.º" / "Artículo 68 bis." / "Artículo 27 quáter."
#
# El terminador del ordinal ('.', 'º', '.º') es OBLIGATORIO: es lo que impide
# que el patrón dispare sobre referencias cruzadas dentro del cuerpo del texto
# (p. ej. "Artículo 93 y 94 de esta ley" no lleva punto tras el número).
ARTICULO_RE = re.compile(
    r"^[ \t]*Artículo\s+(?P<num>\d+)"
    r"(?:\s+(?P<sufijo>bis|ter|qu[áa]ter|quinquies|sexies|septies|octies|nonies|decies))?"
    r"\s*(?:\.º|º\.|º|\.)",
    re.MULTILINE,
)

# "Disposición adicional primera." / "Disposición transitoria única." / etc.
DISPOSICION_RE = re.compile(
    r"^[ \t]*Disposici[óo]n\s+"
    r"(?P<clase>adicional|transitoria|derogatoria|final)\s+"
    r"(?P<ordinal>[A-Za-zÁÉÍÓÚÑáéíóúñ]+(?:\s+[a-záéíóúñ]+)?)"
    r"\s*\.",
    re.MULTILINE,
)


@dataclass
class Heading:
    """Un encabezado detectado dentro del texto de una ley."""
    start: int          # posición del inicio del encabezado en el texto
    heading_end: int    # posición del final de la línea del encabezado
    tipo: str           # "articulo" | "disposicion"
    numero: str         # "66", "68 bis", "adicional primera", ...
    etiqueta: str       # "Artículo 66", "Disposición adicional primera"


def _titulo_del_encabezado(text: str, pos: int, limite: int = 250) -> str:
    """
    Extrae, en modo best-effort, el título que sigue al ordinal del encabezado.

    Se toma hasta el primer punto seguido de espacio, colapsando saltos de línea
    (los títulos largos suelen partirse en dos líneas en el PDF). El resultado
    solo se usa como METADATO legible; nunca como contenido indexable, por lo
    que un fallo puntual aquí no afecta a la recuperación.
    """
    cola = re.sub(r"\s+", " ", text[pos:pos + limite]).strip()
    m = re.match(r"(.+?\.)(?:\s|$)", cola)
    titulo = (m.group(1) if m else cola).strip(" .")
    # Si lo capturado empieza por un dígito, el artículo no tenía título y
    # hemos capturado el primer apartado del cuerpo.
    if not titulo or titulo[0].isdigit() or len(titulo) < 5:
        return ""
    return titulo


def _fin_del_titulo(text: str, pos: int, titulo: str, limite: int = 300) -> int | None:
    """
    Devuelve la posición en la que termina el título dentro del texto original.

    Es necesario porque en el PDF los títulos largos se parten en dos líneas
    ("Artículo 100. Terminación de los procedimientos de gestión\\ntributaria.");
    si el cuerpo se cortase simplemente al final de la primera línea, el resto
    del título quedaría pegado al inicio del articulado.
    """
    if not titulo:
        return None
    patron = r"\s*" + r"\s+".join(re.escape(w) for w in titulo.split()) + r"\s*\.?"
    m = re.match(patron, text[pos:pos + limite])
    return pos + m.end() if m else None


def find_headings(text: str) -> list[Heading]:
    """Localiza y ordena todos los encabezados (artículos y disposiciones)."""
    headings: list[Heading] = []

    for m in ARTICULO_RE.finditer(text):
        numero = m.group("num")
        if m.group("sufijo"):
            numero = f"{numero} {m.group('sufijo').lower()}"
        headings.append(
            Heading(
                start=m.start(),
                heading_end=m.end(),
                tipo="articulo",
                numero=numero,
                etiqueta=f"Artículo {numero}",
            )
        )

    for m in DISPOSICION_RE.finditer(text):
        numero = f"{m.group('clase').lower()} {m.group('ordinal').lower()}"
        headings.append(
            Heading(
                start=m.start(),
                heading_end=m.end(),
                tipo="disposicion",
                numero=numero,
                etiqueta=f"Disposición {numero}",
            )
        )

    headings.sort(key=lambda h: h.start)
    return headings


# ===========================================================================
# 3. Particionado
# ===========================================================================

def split_ley(text: str, meta: dict, source: str) -> list[Document]:
    """
    Trocea el texto limpio de una ley en Documents listos para indexar.

    Cada Document resultante lleva SIEMPRE una línea de contexto al principio
    con la ley y el artículo al que pertenece. Esto es deliberado: garantiza
    que un fragmento recuperado sea autoexplicativo cuando se inyecte en el
    prompt de generación, y mejora la recuperación en consultas que mencionan
    el impuesto ("IVA", "IRPF") sin que la palabra aparezca en el articulado.
    """
    headings = find_headings(text)
    if not headings:
        raise ValueError(
            f"No se ha detectado ningún artículo en '{source}'. "
            "Revisa que el PDF tenga capa de texto y que sea el consolidado del BOE."
        )

    subsplitter = RecursiveCharacterTextSplitter(
        chunk_size=config.MAX_CHUNK_CHARS,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
        length_function=len,
    )

    documents: list[Document] = []
    descartados = 0

    for i, h in enumerate(headings):
        fin = headings[i + 1].start if i + 1 < len(headings) else len(text)

        titulo = _titulo_del_encabezado(text, h.heading_end)

        # El cuerpo empieza justo tras el título, para no duplicar el texto
        # "Artículo N. Título" (ya va en la línea de contexto que anteponemos).
        inicio_cuerpo = _fin_del_titulo(text, h.heading_end, titulo)
        if inicio_cuerpo is None or inicio_cuerpo >= fin:
            # Sin título detectado: cortamos al final de la línea del encabezado.
            salto = text.find("\n", h.heading_end)
            inicio_cuerpo = salto + 1 if 0 <= salto < fin else h.heading_end
        cuerpo = text[inicio_cuerpo:fin]

        if len(normalize_whitespace(cuerpo)) < config.MIN_ARTICLE_CHARS:
            descartados += 1
            continue

        contexto = f"{meta['ley']} · {h.etiqueta}"
        if titulo:
            contexto += f". {titulo}"

        partes = subsplitter.split_text(cuerpo)
        for j, parte in enumerate(partes):
            parte = normalize_whitespace(parte)
            if not parte:
                continue

            documents.append(
                Document(
                    page_content=f"{contexto}\n\n{parte}",
                    metadata={
                        "ley": meta["ley"],
                        "ley_titulo": meta["ley_titulo"],
                        "referencia_boe": meta["referencia_boe"],
                        "tipo": h.tipo,
                        "numero": h.numero,
                        # Identificador canónico usado por el conjunto de
                        # evaluación (eval/golden_set.json).
                        "articulo_id": f"{meta['ley']} {h.etiqueta}",
                        "titulo": titulo,
                        "fragmento": j + 1,
                        "total_fragmentos": len(partes),
                        "source": source,
                    },
                )
            )

    if descartados:
        print(f"    · {descartados} encabezados descartados (cuerpo demasiado corto)")

    return documents


# ===========================================================================
# 3b. Particionado — variante de control (longitud fija)
# ===========================================================================

def split_ley_longitud_fija(text: str, meta: dict, source: str) -> list[Document]:
    """
    Variante de control del experimento de ablación del apartado 3.3.3: trocea
    el texto COMPLETO de la ley con RecursiveCharacterTextSplitter, sin
    ninguna conciencia de la estructura del articulado (ni encabezados, ni
    títulos, ni fronteras de artículo). Se contrasta frente a `split_ley` para
    justificar empíricamente la decisión de usar el artículo como unidad
    primaria de partición.

    CONFOUND DECLARADO (anotado también en decisiones.md): `split_ley`
    antepone a cada fragmento una línea de contexto fija
    ("LGT · Artículo 66. Plazos de prescripción") que aquí NO se puede
    construir, porque un fragmento de longitud fija puede solapar varios
    artículos, uno solo, o ninguno (texto anterior al primer encabezado). La
    comparación de métricas entre ambas estrategias es por tanto entre dos
    estrategias COMPLETAS —troceado y presencia/ausencia de línea de
    contexto—, no el efecto de un único parámetro aislado.

    Metadatos de artículo por desplazamiento: como el splitter no respeta las
    fronteras del articulado, el artículo (o artículos) de cada fragmento se
    asigna A POSTERIORI, comparando su rango de caracteres [inicio, fin) en
    `text` contra la posición de cada encabezado que devuelve `find_headings`.
    Un fragmento que solape el rango de más de un artículo —por cruzar su
    frontera, o por el propio solapamiento entre fragmentos— queda etiquetado
    con TODOS ellos en el metadato `articulo_ids` (ver ARTICULO_IDS_SEP),
    porque ChromaDB no admite listas como valor de metadato.
    """
    headings = find_headings(text)
    if not headings:
        raise ValueError(
            f"No se ha detectado ningún artículo en '{source}'. "
            "Revisa que el PDF tenga capa de texto y que sea el consolidado del BOE."
        )
    starts = [h.start for h in headings]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.MAX_CHUNK_CHARS,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
        length_function=len,
    )
    partes_brutas = splitter.split_text(text)

    documents: list[Document] = []
    cursor = 0  # el splitter avanza monótonamente: cada parte empieza donde
                # empezó o después de donde empezó la anterior en `text`.

    for j, parte_bruta in enumerate(partes_brutas):
        pos = text.find(parte_bruta, cursor)
        if pos == -1:
            pos = text.find(parte_bruta)  # último recurso: no debería hacer falta
        if pos == -1:
            raise ValueError(
                f"No se ha podido localizar el fragmento {j} de '{source}' "
                "en el texto original tras el troceado por longitud fija."
            )
        frag_start, frag_end = pos, pos + len(parte_bruta)
        cursor = frag_start

        # Encabezados cuyo rango [start_i, start_(i+1)) solapa [frag_start, frag_end).
        lo = max(0, bisect.bisect_right(starts, frag_start) - 1)
        solapados = []
        for i in range(lo, len(headings)):
            if starts[i] >= frag_end:
                break
            fin_heading = starts[i + 1] if i + 1 < len(headings) else len(text)
            if fin_heading > frag_start:
                solapados.append(headings[i])

        articulo_ids = [f"{meta['ley']} {h.etiqueta}" for h in solapados]

        parte = normalize_whitespace(parte_bruta)
        if not parte:
            continue

        documents.append(
            Document(
                page_content=parte,
                metadata={
                    "ley": meta["ley"],
                    "ley_titulo": meta["ley_titulo"],
                    "referencia_boe": meta["referencia_boe"],
                    "tipo": solapados[0].tipo if solapados else "sin_encabezado",
                    "numero": solapados[0].numero if solapados else "",
                    "articulo_id": articulo_ids[0] if articulo_ids else "",
                    "articulo_ids": ARTICULO_IDS_SEP.join(articulo_ids),
                    "num_articulos": len(articulo_ids),
                    "titulo": "",
                    "fragmento": j + 1,
                    "total_fragmentos": len(partes_brutas),
                    "source": source,
                },
            )
        )

    return documents


# ===========================================================================
# 4. Punto de entrada del módulo
# ===========================================================================

def load_and_split(pdf_path: Path, meta: dict) -> list[Document]:
    """Carga un PDF del BOE y devuelve su lista de fragmentos indexables."""
    reader = PdfReader(str(pdf_path))
    paginas = [(p.extract_text() or "") for p in reader.pages]
    raw = "\n".join(paginas)

    if len(raw.strip()) < 1000:
        raise ValueError(
            f"'{pdf_path.name}' apenas contiene texto extraíble ({len(raw)} caracteres). "
            "Probablemente sea un PDF escaneado: necesitaría OCR."
        )

    print(f"    · {len(paginas)} páginas, {len(raw):,} caracteres extraídos")

    text = clean_boe_text(raw)
    print(f"    · {len(text):,} caracteres tras limpieza "
          f"({100 * (1 - len(text) / len(raw)):.1f}% eliminado)")

    if config.CHUNK_STRATEGY == "articulo":
        return split_ley(text, meta, source=pdf_path.name)
    elif config.CHUNK_STRATEGY == "longitud_fija":
        return split_ley_longitud_fija(text, meta, source=pdf_path.name)
    raise ValueError(f"CHUNK_STRATEGY no reconocida: {config.CHUNK_STRATEGY!r}")


def build_chunk_id(doc: Document) -> str:
    """
    Identificador determinista de fragmento.

    Al ser determinista, reejecutar la ingesta sobrescribe los mismos registros
    en lugar de duplicarlos, y permite reindexar una sola ley sin tocar el resto.
    """
    m = doc.metadata
    numero = str(m["numero"]).replace(" ", "-")
    return f"{m['ley']}::{m['tipo']}-{numero}::{m['fragmento']}"
