# Notas para el Capítulo 4 — Implementación

> **Documento de trabajo, no redactado.** Registro en bruto de las decisiones
> técnicas tomadas y de sus justificaciones, para no reconstruirlas de memoria
> al redactar la memoria. Se va ampliando conforme avanza el desarrollo.
>
> Última actualización: agosto 2026 · Estado: prototipo del recuperador cerrado

---

## 0. Índice de estado

| Bloque | Estado | Evidencia disponible |
|---|---|---|
| Recuperación (RAG) | **Cerrado y medido** | 5 corridas en `eval/resultados_*.json` |
| Triaje (extracción estructurada) | Pendiente | — |
| Redacción (drafting) | Pendiente | — |
| Backend / API | Pendiente | — |
| Frontend | Pendiente | — |

---

## 1. Desviaciones respecto al anteproyecto

Redactar un párrafo breve al inicio del capítulo. **El tutor autorizó
expresamente desviarse del anteproyecto en tecnologías**, pero la memoria debe
declararlo, no dejar que el tribunal lo descubra comparando documentos.

| Anteproyecto | Implementado | Motivo |
|---|---|---|
| LlamaIndex | LangChain | Amplitud del ecosistema de integraciones y abstracción de cadenas más adecuada para componer las dos fases (triaje + drafting) en un mismo marco. Ya justificado en el apartado 3.5. |
| Llama-3 local (PyTorch, bitsandbytes) | *Por decidir* | El anteproyecto asume ejecución local sobre «ordenador personal». Sin GPU, la generación de texto jurídico en español es lenta y de calidad insuficiente. **Decisión pendiente.** |
| SentenceTransformers (genérico) | `intfloat/multilingual-e5-*` | Modelo concreto de la familia, seleccionado por rendimiento multilingüe en español. Se ejecuta en CPU sin coste por token. |

Nota: los embeddings **sí** se ejecutan localmente, como preveía el
anteproyecto. La desviación afectaría únicamente al modelo generativo.

---

## 2. Estrategia de desarrollo: prototipo aislado previo

Antes de construir la aplicación completa se desarrolló un prototipo aislado
que implementa exclusivamente el paso 5 del flujo del apartado 3.4
(recuperación de contexto normativo), sin API, sin interfaz y sin persistencia
relacional.

**Justificación.** De los cuatro bloques de la arquitectura, tres son
ingeniería convencional de riesgo conocido (API REST, CRUD, interfaz web). El
riesgo técnico se concentra en la recuperación: si el sistema devuelve el
artículo equivocado, el modelo de lenguaje redactará un escrito correctamente
formulado pero fundamentado en normativa que no aplica, y ninguna ingeniería de
prompts posterior corrige ese error. Aislarlo permite además **medirlo**, lo que
convierte la validación en un experimento reproducible en lugar de una
demostración cualitativa.

Esta decisión es coherente con el enfoque de Desarrollo Basado en el Valor
declarado en el apartado 1.3.1: los primeros ciclos se orientan a resolver el
núcleo de incertidumbre.

---

## 3. Entorno de desarrollo

- Windows, Visual Studio Code con terminal integrada PowerShell.
- Python 3.12 en entorno virtual (`venv`).
- PyTorch instalado en su variante **CPU** (`--index-url .../whl/cpu`) para
  evitar la descarga de ruedas CUDA innecesarias (~2,5 GB).
- Control de versiones con Git; repositorio **privado** en GitHub.

**Sobre la privacidad del repositorio:** se mantiene privado durante el
desarrollo porque contendrá notificaciones de la AEAT anonimizadas y,
eventualmente, credenciales de API. El anteproyecto comprometía un repositorio
en GitHub como entregable; sigue cumpliéndose, con acceso concedido al tutor.

### Dependencias

Se instalan **cinco paquetes**. Decisiones no obvias que conviene documentar:

1. **No se instala el meta-paquete `langchain`.** Solo `langchain-core`,
   `langchain-text-splitters` y los dos conectores (`langchain-chroma`,
   `langchain-huggingface`). Reduce la superficie de dependencias y los
   conflictos de versión.
2. **El extra `[full]` de `langchain-huggingface` es obligatorio.** La
   instalación base ya no incluye `sentence-transformers`, y el fallo se
   manifiesta en tiempo de ejecución, no durante la instalación.
3. **No se usa `langchain-community`.** El PDF se lee con `pypdf`
   directamente: mismo motor de extracción que `PyPDFLoader`, una dependencia
   pesada menos y control página a página sobre la limpieza de cabeceras.

**Reproducibilidad:** versiones exactas congeladas en `requirements.lock.txt`.
Es imprescindible mencionarlo: LangChain rompe compatibilidad con frecuencia y
sin versiones fijadas el experimento no es reproducible.

---

## 4. Corpus normativo

Fuente: textos **consolidados** del BOE (no las versiones originales, que no
incorporan las modificaciones posteriores).

| Ley | Referencia BOE |
|---|---|
| Ley 58/2003, General Tributaria (LGT) | BOE-A-2003-23186 |
| Ley 37/1992, del IVA (LIVA) | BOE-A-1992-28740 |

### Limpieza previa

Los consolidados del BOE repiten en cada una de sus ~220 páginas: cabecera
(«BOLETÍN OFICIAL DEL ESTADO», «LEGISLACIÓN CONSOLIDADA»), referencia de la
disposición, fecha de última modificación y número de página. Incluyen además
un índice inicial con líneas de puntos guía.

Sin filtrar, ese ruido se incorpora a los fragmentos y contamina los
embeddings. La limpieza elimina en torno al 10-12 % del texto extraído.

**Dato a registrar en la próxima corrida:** porcentaje exacto eliminado por ley.

---

## 5. Estrategia de particionado (chunking)

Es la decisión de diseño central del capítulo, y la que respalda lo afirmado en
el apartado 3.3.3 de la memoria.

### Diseño

La unidad semántica primaria es el **artículo**, no un número fijo de
caracteres. Solo se subdividen los artículos que superan el límite
(`MAX_CHUNK_CHARS`), y en ese caso mediante `RecursiveCharacterTextSplitter`
con solapamiento.

### Detección de encabezados

Expresión regular sobre `^Artículo N.` con **terminador de ordinal
obligatorio** (`.`, `º`, `.º`). Esa exigencia no es cosmética: sin ella el
patrón dispara sobre las referencias cruzadas del articulado
(*«los artículos 93 y 94 de esta ley»*), abundantísimas en la LGT.

Casos contemplados: sufijos ordinales (`bis`, `ter`, `quáter`, `quinquies`…),
formato `Artículo 1.º` de la LIVA, y disposiciones adicionales, transitorias,
derogatorias y finales mediante un segundo patrón.

Se validó la lógica contra texto sintético que reproduce el formato del BOE:
detección correcta de los seis encabezados de prueba, sin falsos positivos
sobre referencias cruzadas, y reconstrucción de títulos partidos en dos líneas
por el salto de página.

### Línea de contexto

Todo fragmento comienza por una línea del tipo
`LGT · Artículo 66. Plazos de prescripción`. Dos motivos:

- El fragmento es **autoexplicativo** cuando se inyecta en el prompt de
  generación: el modelo sabe qué está citando.
- Mejora la recuperación ante consultas que mencionan el impuesto («IVA»,
  «IRPF») sin que esa palabra aparezca en el articulado.

### Metadatos por fragmento

`ley`, `ley_titulo`, `referencia_boe`, `tipo` (artículo/disposición), `numero`,
`articulo_id`, `titulo`, `fragmento`, `total_fragmentos`, `source`.

Dan la **trazabilidad** exigida por los requisitos: permiten citar la fuente
exacta en el borrador generado y filtrar la búsqueda por ley.

### Identificadores deterministas

Cada fragmento recibe un identificador reproducible
(`LGT::articulo-66::1`). Permite reindexar sin duplicar registros y actualizar
una sola ley sin tocar el resto — coherente con el proceso de reindexación
desacoplado descrito en el apartado 3.3.3.

---

## 6. Modelo de embeddings

Familia `intfloat/multilingual-e5-*`, ejecutada en local vía
`sentence-transformers`. Sin claves de API y sin coste por token, lo que permite
reindexar el corpus tantas veces como exija la fase experimental.

### Prefijos asimétricos

Los modelos E5 se entrenaron con prefijos: `passage:` en el texto indexado,
`query:` en la consulta. `HuggingFaceEmbeddings` no los añade automáticamente;
se implementó una subclase que lo hace.

**Medido experimentalmente** (ver §7): omitirlos no altera Recall@5 pero degrada
Recall@1 de 80,0 % a 66,7 % y MRR de 0,8467 a 0,7833.

### Normalización y métrica

Vectores normalizados a norma 1 e índice HNSW configurado con espacio coseno,
de forma que la distancia devuelta está acotada y `similitud = 1 − distancia`,
lo que hace interpretables las puntuaciones mostradas al usuario.

---

## 7. Evaluación del recuperador

### Metodología

Conjunto de 15 preguntas anotadas manualmente, cada una con los artículos que
un asesor consideraría respuesta correcta. Métricas:

- **Recall@k**: proporción de preguntas en las que al menos un artículo
  esperado aparece entre los k primeros resultados.
- **MRR**: inverso de la posición del primer acierto, promediado. Penaliza que
  el artículo correcto aparezca en 5.ª posición en lugar de 1.ª.
- **Cobertura**: fracción del total de artículos esperados recuperados.

Cuando un artículo aporta varios fragmentos, se computa la posición del mejor
de ellos (deduplicación por artículo antes de calcular el ranking).

### Resultados

| Configuración | Modelo | Chunk | R@1 | R@3 | R@5 | R@10 | MRR | Ingesta |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 · Base | e5-base | 1800 | 80,0 % | 86,7 % | 93,3 % | 93,3 % | 0,8467 | 903 s |
| 1 · Modelo pequeño | e5-small | 1800 | 73,3 % | 93,3 % | 93,3 % | 93,3 % | 0,8333 | 308 s |
| 2 · Fragmento corto | e5-base | 1200 | 80,0 % | 93,3 % | 93,3 % | 93,3 % | 0,8667 | 935 s |
| 3 · Fragmento largo | e5-base | 3000 | 80,0 % | 93,3 % | 93,3 % | 93,3 % | 0,8667 | 734 s |
| 4 · Sin prefijos E5 | e5-base | 1800 | 66,7 % | 86,7 % | 93,3 % | 93,3 % | 0,7833 | 895 s |

Cobertura media: 93,3 % en las cinco configuraciones.

### Hallazgos

**H1 · Recall@5 está saturado.** Las cinco configuraciones obtienen 93,3 %: los
mismos 14 aciertos de 15. La métrica fijada inicialmente como criterio de
decisión no discrimina en este corpus, y la comparación debe apoyarse en MRR y
Recall@1, que miden la posición del acierto y no su mera presencia. *Este
hallazgo metodológico merece mención explícita: reconocer que la métrica
elegida a priori resultó inadecuada es más sólido que forzar una conclusión.*

**H2 · Las configuraciones 0-3 son indistinguibles.** Con n = 15, una pregunta
equivale a 6,7 puntos de recall, y el rango completo de MRR observado
(0,8333–0,8667) corresponde al desplazamiento de **una sola pregunta en una
posición**. No hay base para preferir una sobre otra. Nueve de las quince
preguntas obtienen la posición 1 en las cinco corridas; solo cinco varían.

**H3 · El tamaño de fragmento es indiferente.** Las configuraciones 2 y 3
(1200 y 3000 caracteres) dan métricas idénticas. Consecuencia directa del
diseño: como la unidad primaria es el artículo, el límite de caracteres solo
afecta a la minoría de artículos que lo superan. **La insensibilidad a este
parámetro es un argumento a favor del particionado semántico-estructural**, no
una anomalía del experimento.

**H4 · Los prefijos E5 afectan al orden, no a la cobertura.** Desactivarlos deja
Recall@5 intacto y degrada Recall@1 y MRR. Lectura correcta: no cambian *qué*
artículos entran en el conjunto recuperado, sino *en qué orden* se colocan.

**H5 · El modelo pequeño ofrece la mejor relación coste/calidad.** `e5-small`
reduce el tiempo de ingesta a un tercio con MRR prácticamente igual y Recall@3
superior. La reducción de latencia afecta también a la codificación de cada
consulta en tiempo de ejecución, lo que la hace preferible operativamente.
**Configuración seleccionada para la implementación final.**

**H6 · Fallo sistemático en LIVA art. 84.** La consulta sobre inversión del
sujeto pasivo no recupera el artículo correcto en ninguna configuración.
Causa: desajuste de vocabulario. «Inversión del sujeto pasivo» es la
denominación doctrinal y profesional de la figura, mientras que el art. 84 LIVA
se titula «Sujetos pasivos» y la describe funcionalmente sin emplear nunca esa
expresión. Al tratarse de un fallo léxico y no de segmentación, **ninguna
variación de los parámetros evaluados lo corrige**.

*H6 es el hallazgo más aprovechable del experimento: un fallo comprendido,
explicado y que justifica una línea de trabajo futuro concreta (búsqueda
híbrida BM25 + densa, o expansión de consulta con sinónimos del dominio).*

### Limitaciones declaradas

- **Tamaño del conjunto de evaluación.** 15 preguntas son insuficientes para
  discriminar entre configuraciones próximas: la granularidad mínima es de 6,7
  puntos porcentuales.
- **Sesgo optimista en la redacción de las preguntas.** Se redactaron partiendo
  del articulado, por lo que emplean vocabulario cercano al texto legal. El
  caso del art. 84 sugiere que las consultas formuladas con terminología
  profesional —las que realmente producirá el sistema en explotación— presentan
  una dificultad mayor que la reflejada por estos resultados.
- **Medición de tiempos.** Los tiempos de ingesta se midieron en un equipo de
  desarrollo sin control de carga; solo son orientativos. No se registró el
  número de fragmentos por corrida, por lo que no puede normalizarse el tiempo
  por fragmento.

---

## 8. Pendiente

### Experimentos

- [ ] **Ampliar el conjunto de evaluación a 35-40 preguntas.** La mitad
      redactadas con jerga profesional de asesoría («paralela», «módulos»,
      «prorrata especial», «sanción por no atender requerimiento») y no con
      vocabulario copiado del articulado, para corregir el sesgo de H-limitación 2.
- [ ] **Comparación contra troceado de longitud fija.** Es la corrida que
      justifica empíricamente la decisión del apartado 3.3.3. Adquiere más
      importancia tras H2 y H3: como las demás comparaciones salieron planas,
      es la única que puede mostrar una diferencia real.
- [ ] Registrar `n_fragmentos` en cada corrida para normalizar tiempos.
- [ ] Repetir la corrida base con la configuración final seleccionada.

### Decisiones abiertas

- [ ] **Modelo generativo: API comercial frente a ejecución local.** Bloquea el
      desarrollo del eslabón de redacción. Si se opta por API, añadir en la
      memoria un párrafo sobre implicaciones de RGPD del envío de documentación
      tributaria de clientes a un proveedor externo, reconociéndolo como
      limitación y señalando el despliegue local como línea futura. *Es
      pregunta previsible de tribunal en un TFG sobre asesorías.*

### Desarrollo

- [ ] Prototipo de triaje: extracción estructurada validada con Pydantic
      (NIF, impuesto, ejercicio, motivo, artículos citados, plazo).
      Medir precisión **campo a campo**, no de forma agregada.
- [ ] Corpus de notificaciones reales de la AEAT anonimizadas (objetivo: 10-15).
      **Depende de terceros: iniciar la petición cuanto antes.** Plan B:
      documentos sintéticos a partir de las plantillas públicas de la sede
      electrónica, declarándolo como limitación.
- [ ] Cadena completa: triaje → recuperación → drafting.
- [ ] Backend FastAPI y frontend Streamlit.

---

## 9. Material gráfico para el capítulo

- Tabla comparativa de las configuraciones evaluadas (§7).
- Tabla de posición del primer acierto pregunta a pregunta — visualiza H2
  (nueve preguntas invariantes) y H6 (fallo sistemático) de un vistazo.
- Diagrama del pipeline de ingesta: PDF → limpieza → detección de encabezados
  → troceado → embeddings → ChromaDB.
- Captura de una consulta en consola mostrando artículo, título, similitud y
  extracto.
- Fragmento de código del patrón de detección de encabezados, comentando la
  exigencia del terminador de ordinal.
