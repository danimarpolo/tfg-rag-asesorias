# PoC — Núcleo RAG sobre normativa tributaria

Prototipo aislado (*proof of concept*) del núcleo de recuperación del TFG
**"Desarrollo de plataforma basada en IA Generativa para la Optimización de
Procesos Operativos en Asesorías Multidisciplinares"**.

---

## 0. Qué valida este prototipo (y qué deliberadamente no)

| | |
|---|---|
| **Valida** | Que la ingesta de la LGT y la LIVA en ChromaDB, con troceado por artículo y embeddings multilingües, **recupera los artículos correctos** ante una consulta en lenguaje natural. |
| **No incluye** | FastAPI, Streamlit, SQLite, LLM generativo, OCR, autenticación. |

El motivo es de gestión de riesgo. De los cinco bloques del capítulo 3, cuatro
son ingeniería conocida y de riesgo bajo (API REST, CRUD, formulario web). El
único con riesgo técnico real es el paso 5 del flujo del apartado 3.4:
**recuperación de contexto normativo**. Si el recuperador devuelve el artículo
equivocado, ninguna ingeniería de prompts posterior lo arregla — el LLM
redactará un escrito impecable fundamentado en normativa que no aplica.

Aislarlo permite además medirlo, y la medición es lo que convierte esto en un
capítulo de resultados en lugar de una demo.

---

## 1. Requisitos previos

- **Python 3.11 o 3.12** (evita 3.13: algunas ruedas de `torch` /
  `sentence-transformers` todavía dan problemas).
- ~3 GB de disco (modelo de embeddings + índice).
- No hace falta GPU. No hace falta ninguna clave de API.

Comprueba tu versión:

```bash
python3 --version
```

---

## 2. Descarga del corpus normativo

Descarga los **textos consolidados** del BOE (no las versiones originales de
1992/2003: las consolidadas incorporan todas las modificaciones vigentes) y
guárdalos en `data/normativa/` **con el nombre exacto**:

```bash
mkdir -p data/normativa
cd data/normativa

# Ley 58/2003, General Tributaria (LGT)
curl -L -o BOE-A-2003-23186-consolidado.pdf \
  "https://www.boe.es/buscar/pdf/2003/BOE-A-2003-23186-consolidado.pdf"

# Ley 37/1992, del IVA (LIVA)
curl -L -o BOE-A-1992-28740-consolidado.pdf \
  "https://www.boe.es/buscar/pdf/1992/BOE-A-1992-28740-consolidado.pdf"

cd ../..
```

Verifica que pesan del orden de 1–2 MB cada uno. Si pesan 4 KB, has descargado
una página de error: bájalos a mano desde
`https://www.boe.es/buscar/act.php?id=BOE-A-2003-23186` → botón *PDF de la
disposición consolidada*, y renómbralos.

> El nombre de fichero es la clave del diccionario `CORPUS` en `src/config.py`.
> Si prefieres otro nombre, cámbialo ahí.

---

## 3. Entorno virtual e instalación

```bash
# Desde la raíz del proyecto
python3 -m venv .venv

# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip

# 1) torch en versión CPU (evita descargar ~2,5 GB de ruedas CUDA).
#    Si tienes GPU NVIDIA, sáltate esta línea.
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2) el resto de dependencias
pip install -r requirements.txt
```

### `requirements.txt`

```
langchain-core
langchain-text-splitters
langchain-chroma
langchain-huggingface[full]
pypdf
```

Cinco paquetes. Tres detalles no obvios:

1. **No se instala el meta-paquete `langchain`.** En este prototipo no aporta
   nada; solo `langchain-core`, los *text splitters* y los dos conectores.
2. **El extra `[full]` de `langchain-huggingface` es obligatorio.** La
   instalación base ya *no* incluye `sentence-transformers`, y
   `HuggingFaceEmbeddings` lo necesita. Sin el extra obtendrás un `ImportError`
   en tiempo de ejecución, no en la instalación.
3. **No se usa `langchain-community`.** Se lee el PDF con `pypdf` directamente:
   mismo motor de extracción que `PyPDFLoader`, una dependencia pesada menos y
   control página a página sobre la limpieza de cabeceras del BOE.

Una vez que la instalación funcione, **congela las versiones**:

```bash
pip freeze > requirements.lock.txt
```

Cita ese fichero en la memoria. LangChain rompe compatibilidad con frecuencia;
sin versiones fijadas, tu experimento no es reproducible en la defensa.

---

## 4. Estructura del proyecto

```
poc-rag-aeat/
├── requirements.txt
├── .gitignore
├── README.md
├── data/
│   └── normativa/                 # PDFs del BOE (no se versionan)
│       ├── BOE-A-2003-23186-consolidado.pdf
│       └── BOE-A-1992-28740-consolidado.pdf
├── eval/
│   └── golden_set.json            # preguntas de referencia anotadas
├── chroma_db/                     # índice generado (no se versiona)
└── src/
    ├── config.py                  # todos los parámetros del experimento
    ├── embeddings.py              # modelo de embeddings (compartido)
    ├── legal_splitter.py          # limpieza + troceado por artículo
    ├── ingest.py                  # PDF -> chunks -> embeddings -> Chroma
    ├── query.py                   # consulta semántica por consola
    └── evaluate.py                # Recall@k y MRR
```

Todos los comandos se ejecutan **desde la raíz** (`poc-rag-aeat/`).

---

## 5. Ejecución

### Paso 1 — Troceado en seco (sin embeddings)

```bash
python src/ingest.py --dry-run --sample 3
```

No carga `torch` ni el modelo, así que tarda **segundos**. Úsalo para iterar
sobre la estrategia de troceado sin esperar cada vez a que se recalculen los
embeddings.

Salida esperada, aproximadamente:

```
  [LGT] BOE-A-2003-23186-consolidado.pdf
    · 220 páginas, 731.482 caracteres extraídos
    · 641.905 caracteres tras limpieza (12,2% eliminado)
    · 412 fragmentos generados

====================================================================
ESTADÍSTICAS DEL TROCEADO
====================================================================
  Fragmentos totales ..............  798
  Artículos / disposiciones .......  546
  Fragmentos por ley ..............  {'LGT': 412, 'LIVA': 386}
  ...
```

**Criterio de sanidad:** el número de artículos detectados debe estar en el
orden de los ~250 de la LGT y ~170 de la LIVA (más disposiciones). Si detecta
20, el patrón de encabezado no está casando; si detecta 3.000, se está colando
el índice del documento. Revisa la salida de `--sample`.

### Paso 2 — Ingesta completa

```bash
python src/ingest.py --reset
```

La **primera ejecución descarga el modelo de embeddings (~500 MB)** desde
Hugging Face. En CPU, indexar ~800 fragmentos lleva del orden de 2–5 minutos.

### Paso 3 — Consulta por consola

```bash
# Consulta directa
python src/query.py "¿Qué plazo tengo para recurrir una liquidación de la AEAT?"

# Más resultados, filtrando por ley
python src/query.py -k 8 --ley LIVA "requisitos para deducir el IVA soportado"

# Fragmento completo en vez de extracto
python src/query.py --full "recargo por declaración extemporánea"

# Modo interactivo (REPL): comandos  :k <n>   :ley <LGT|LIVA|*>   :q
python src/query.py
```

Cada resultado muestra la ley, el artículo, el título, la similitud coseno y
un extracto del articulado.

### Paso 4 — Evaluación cuantitativa

```bash
python src/evaluate.py --out eval/resultados_e5base.json
```

Ejecuta las preguntas de `eval/golden_set.json` y calcula Recall@1/3/5/10, MRR
y cobertura.

> **Importante:** el `golden_set.json` que se entrega es una **semilla**. Cada
> entrada lleva `"nota": "VERIFICAR"`. Ábrelo, comprueba cada artículo contra
> el texto consolidado y corrígelo antes de citar ningún número en la memoria.
> Un conjunto de evaluación mal anotado invalida el capítulo 5 entero, y es
> exactamente el tipo de cosa que pregunta un tribunal.

---

## 6. Cómo interpretar los resultados

| Métrica | Qué mide | Umbral orientativo |
|---|---|---|
| **Recall@5** | ¿está el artículo correcto entre los 5 que se inyectarán en el prompt? | ≥ 0,85 para dar el núcleo por válido |
| **Recall@1** | ¿es el primero el correcto? | ≥ 0,60 es buena señal |
| **MRR** | penaliza que el acierto salga en 5.ª posición en vez de 1.ª | ≥ 0,70 |
| **Cobertura** | fracción de *todos* los artículos esperados recuperados | relevante en preguntas multi-artículo |

Recall@5 es la métrica que gobierna la decisión, porque `k = 5` es el número de
fragmentos que la fase de *drafting* inyectará en el prompt. Si el artículo
correcto no está ahí, el LLM no puede citarlo.

**Si Recall@5 < 0,80**, prueba en este orden (una variable cada vez, guardando
los resultados de cada corrida):

1. Sube `EMBEDDING_MODEL` a `intfloat/multilingual-e5-large`.
2. Baja `MAX_CHUNK_CHARS` a 1200 (fragmentos más específicos).
3. Sube `k` a 8–10.
4. Añade re-ranking o búsqueda híbrida (BM25 + denso) — ya es material de
   "trabajos futuros", no del MVP.

Cada corrida con su fichero JSON te da una fila de la tabla comparativa del
capítulo 5, **con datos propios**. Eso es lo que distingue un TFG de ingeniería
de un tutorial reproducido.

---

## 7. Decisiones de diseño que documentar en el capítulo 4

Estas cuatro son las defendibles ante el tribunal, y las cuatro están
implementadas en el código:

1. **Troceado por artículo, no por longitud fija** (`legal_splitter.py`). El
   apartado 3.3.3 de tu memoria promete "particionado semántico-estructural";
   un `RecursiveCharacterTextSplitter` genérico lo incumpliría. El patrón de
   encabezado exige un terminador de ordinal (`.`, `º`) precisamente para no
   disparar sobre referencias cruzadas del tipo *"los artículos 93 y 94 de esta
   ley"*, que son abundantísimas en la LGT.

2. **Línea de contexto en cada fragmento.** Todo *chunk* empieza por
   `LGT · Artículo 66. Plazos de prescripción`. Así el fragmento es
   autoexplicativo cuando se inyecta en el prompt, y se recupera mejor ante
   consultas que mencionan el impuesto sin que la palabra aparezca en el
   articulado.

3. **Prefijos E5** (`embeddings.py`). Los modelos `multilingual-e5-*` se
   entrenaron de forma asimétrica: `passage:` al indexar, `query:` al consultar.
   `HuggingFaceEmbeddings` no los añade solo. Omitirlos degrada el recall de
   forma medible — y es un experimento de cuatro minutos que puedes incluir
   como ablación en el capítulo 5.

4. **Limpieza previa del BOE.** Los consolidados repiten cabecera, pie y número
   de página en cada una de sus ~220 páginas, más un índice con puntos guía. Sin
   filtrarlos, ese ruido entra en los embeddings.

---

## 8. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `ImportError: sentence_transformers` | Instalaste sin el extra. `pip install "langchain-huggingface[full]"` |
| `No se ha detectado ningún artículo` | El PDF no es el consolidado, o no tiene capa de texto. Comprueba el tamaño del fichero. |
| `TypeError` con `collection_metadata` | Tu versión de `chromadb` rechaza `hnsw:space`. Comenta esa línea en `ingest.py`: el ranking no cambia (los vectores están normalizados), solo la escala de las distancias. |
| La consulta devuelve ruido total | Has indexado con un modelo y consultado con otro. Cambia `EMBEDDING_MODEL` y **reejecuta `ingest.py --reset`**: los vectores viven en espacios distintos y esto no da ningún error. |
| Descarga del modelo muy lenta | Normal la primera vez (~500 MB). Se cachea en `~/.cache/huggingface`. |
| `chroma_db` crece en cada ejecución | Usa siempre `--reset` mientras experimentas. |

---

## 9. Siguiente paso

Con Recall@5 validado, el orden natural de trabajo es:

1. **Extracción estructurada del triaje** (fase 3 del apartado 3.4): un
   requerimiento real de la AEAT anonimizado → salida JSON validada con
   Pydantic (NIF, impuesto, ejercicio, motivo, artículos citados, plazo). Se
   prueba también en consola, sin API ni interfaz.
2. **Cadena de *drafting*** encadenando triaje → recuperación → generación.
3. Solo entonces, envolver en FastAPI y Streamlit.

Los bloques 1 y 2 son los que llevan riesgo. La API y la interfaz son trabajo
mecánico y se pueden comprimir si el calendario aprieta.
