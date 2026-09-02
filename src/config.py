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
EVAL_DIR = BASE_DIR / "eval"                 # Conjunto de evaluación y resultados

# Estrategia de troceado activa (documentada en detalle en la sección 4, con
# la que comparte bloque conceptual). Se fija aquí, antes que CHROMA_DIR,
# porque también decide el directorio de persistencia: cada estrategia
# escribe en su propio índice para poder compararlas sin destruir la anterior.
CHUNK_STRATEGY = "articulo"  # "articulo" | "longitud_fija"  -- por defecto "articulo"

_CHROMA_DIR_POR_ESTRATEGIA = {
    "articulo": BASE_DIR / "chroma_db",
    "longitud_fija": BASE_DIR / "chroma_db_longitud_fija",
}
CHROMA_DIR = _CHROMA_DIR_POR_ESTRATEGIA[CHUNK_STRATEGY]   # Persistencia de ChromaDB


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
# CHUNK_STRATEGY (definida en la sección 1, junto a CHROMA_DIR) selecciona la
# unidad primaria de partición:
#   "articulo"      -> el ARTÍCULO legal. Solo se subdivide lo que supere
#                      MAX_CHUNK_CHARS (legal_splitter.split_ley). Estrategia
#                      ya medida y descrita en el apartado 3.3.3 de la memoria.
#   "longitud_fija" -> RecursiveCharacterTextSplitter sobre el texto COMPLETO
#                      de la ley, sin ninguna conciencia de dónde empieza o
#                      acaba un artículo (legal_splitter.split_ley_longitud_fija).
#                      Grupo de control del experimento de ablación que
#                      contrasta empíricamente esa decisión de diseño.
# Los dos parámetros siguientes son el tamaño de ventana y el solapamiento del
# RecursiveCharacterTextSplitter; se aplican por igual en ambas estrategias
# (en "articulo" solo entran en juego para subdividir artículos largos).
MAX_CHUNK_CHARS = 1800    # ~450-500 tokens en español
CHUNK_OVERLAP = 200       # solapamiento entre fragmentos
MIN_ARTICLE_CHARS = 40    # descarta residuos del índice / falsos positivos (solo estrategia "articulo")


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


# ---------------------------------------------------------------------------
# 7. Triaje de requerimientos (extracción estructurada)
# ---------------------------------------------------------------------------
# Módulo independiente del recuperador: extrae datos de un PDF de requerimiento
# de la AEAT con un LLM local servido por Ollama (src/triaje.py).
TRIAJE_CORPUS_DIR = EVAL_DIR / "corpus_triaje"
TRIAJE_GOLDEN = EVAL_DIR / "golden_triaje.json"

# Ollama debe estar arrancado en local (ollama serve) con el modelo importado.
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3b-tfg"
OLLAMA_TIMEOUT = 120      # segundos; modelo de 3B en CPU puede tardar

# Reintentos ante una respuesta que no valida contra el esquema Pydantic.
# "Hasta 2 reintentos" -> 3 intentos totales como máximo por documento.
TRIAJE_MAX_REINTENTOS = 2

# Temperatura de muestreo por intento (campo "options.temperature" de la API
# de Ollama). El modelo es determinista a temperatura fija: repetir el mismo
# prompt sin variar la temperatura devuelve exactamente la misma salida
# (verificado empíricamente, hash idéntico en 5 llamadas), así que un
# reintento "a ciegas" nunca rescata un documento. Escalar la temperatura
# entre intentos le da al reintento una oportunidad real de obtener una
# respuesta distinta. Si TRIAJE_MAX_REINTENTOS cambiara y hubiera más
# intentos que temperaturas, se reutiliza la última.
TRIAJE_TEMPERATURAS = (0.1, 0.4, 0.7)

# Rango razonable para el campo "ejercicio" (año fiscal). Fijo, no dinámico
# sobre el año actual, para que el experimento sea reproducible.
TRIAJE_EJERCICIO_MIN = 2000
TRIAJE_EJERCICIO_MAX = 2035

# Caso de ablación de maquetación (mismo contenido, PDF distinto). Se excluye
# de las métricas agregadas y se reporta aparte frente a TRIAJE_ABLACION_BASE.
TRIAJE_ABLACION_CASO = "req_002.pdf"
TRIAJE_ABLACION_BASE = "req_001.pdf"


# ---------------------------------------------------------------------------
# 8. Cadena de generación del borrador (drafting)
# ---------------------------------------------------------------------------
# Paso 6 del flujo del apartado 3.4: triaje -> recuperación -> generación.
# Usa el mismo modelo y la misma URL de Ollama que el triaje (sección 7); solo
# cambia la temperatura y el timeout, por generar texto libre más largo.
DRAFTING_TEMPERATURA = 0.1   # sin reintento ni escalado: una única llamada
DRAFTING_TIMEOUT = 300       # segundos; un escrito completo tarda más que el JSON del triaje
DRAFTING_MAX_TOKENS = 2000   # options.num_predict; límite de seguridad frente a bucles de repetición
