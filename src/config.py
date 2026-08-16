"""
config.py
=========
Configuración central del prototipo aislado (PoC) del núcleo RAG.

Todo parámetro ajustable del experimento vive aquí. El objetivo es que los
scripts (ingest / query / evaluate) no contengan constantes "mágicas", de forma
que cualquier variación del experimento (modelo de embeddings, tamaño de chunk,
top-k) sea trazable y reproducible en la memoria del TFG.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Rutas del proyecto
# ---------------------------------------------------------------------------
# BASE_DIR apunta a la raíz del proyecto (un nivel por encima de src/)
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data" / "normativa"   # PDFs originales del BOE
CHROMA_DIR = BASE_DIR / "chroma_db"          # Persistencia de ChromaDB
EVAL_DIR = BASE_DIR / "eval"                 # Conjunto de evaluación y resultados


# ---------------------------------------------------------------------------
# 2. Corpus normativo
# ---------------------------------------------------------------------------
# Clave  = nombre EXACTO del fichero PDF que debe existir en data/normativa/
# Valor  = metadatos que se propagarán a todos los fragmentos de esa ley.
#
# Los ficheros se descargan de los textos consolidados del BOE:
#   https://www.boe.es/buscar/pdf/2003/BOE-A-2003-23186-consolidado.pdf
#   https://www.boe.es/buscar/pdf/1992/BOE-A-1992-28740-consolidado.pdf
CORPUS = {
    "BOE-A-2003-23186-consolidado.pdf": {
        "ley": "LGT",
        "ley_titulo": "Ley 58/2003, de 17 de diciembre, General Tributaria",
        "referencia_boe": "BOE-A-2003-23186",
    },
    "BOE-A-1992-28740-consolidado.pdf": {
        "ley": "LIVA",
        "ley_titulo": "Ley 37/1992, de 28 de diciembre, del Impuesto sobre el Valor Añadido",
        "referencia_boe": "BOE-A-1992-28740",
    },
}


# ---------------------------------------------------------------------------
# 3. Modelo de embeddings
# ---------------------------------------------------------------------------
# Se ejecuta EN LOCAL vía sentence-transformers: sin claves de API y sin coste
# por token, lo que permite reindexar el corpus tantas veces como haga falta
# durante la fase experimental.
#
# Alternativas evaluables (para la tabla comparativa del capítulo 4):
#   - "intfloat/multilingual-e5-small"  -> 384 dim, muy rápido, calidad menor
#   - "intfloat/multilingual-e5-base"   -> 768 dim, equilibrio recomendado (CPU)
#   - "intfloat/multilingual-e5-large"  -> 1024 dim, mejor calidad, ~3x más lento
#   - "BAAI/bge-m3"                     -> 1024 dim, muy bueno, NO usa prefijos
EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
EMBEDDING_DEVICE = "cpu"          # "cuda" si dispones de GPU NVIDIA

# Los modelos de la familia E5 fueron entrenados con prefijos asimétricos
# ("query: " / "passage: "). Omitirlos degrada la recuperación de forma medible.
# Pon esto a False si cambias a un modelo que NO los use (p. ej. bge-m3).
USE_E5_PREFIXES = True


# ---------------------------------------------------------------------------
# 4. Particionado (chunking)
# ---------------------------------------------------------------------------
# La unidad semántica primaria es el ARTÍCULO. Solo los artículos que superen
# MAX_CHUNK_CHARS se subdividen; el resto se indexa completo.
MAX_CHUNK_CHARS = 1800    # ~450-500 tokens en español
CHUNK_OVERLAP = 200       # solapamiento entre subfragmentos de un mismo artículo
MIN_ARTICLE_CHARS = 40    # descarta residuos del índice / falsos positivos


# ---------------------------------------------------------------------------
# 5. ChromaDB
# ---------------------------------------------------------------------------
COLLECTION_NAME = "normativa_tributaria"

# Espacio métrico del índice HNSW. Con embeddings normalizados, "cosine" hace
# que la distancia devuelta esté en [0, 2] y que  similitud = 1 - distancia.
CHROMA_DISTANCE = "cosine"

INGEST_BATCH_SIZE = 128   # tamaño de lote al insertar en Chroma


# ---------------------------------------------------------------------------
# 6. Recuperación
# ---------------------------------------------------------------------------
DEFAULT_TOP_K = 5
EVAL_MAX_K = 10           # k máximo que se recupera en evaluate.py
EVAL_K_VALUES = (1, 3, 5, 10)
