# Decisiones de diseño — registro

Bitácora de decisiones técnicas del TFG. Sirve de continuidad entre
conversaciones y de material en bruto para el capítulo 4.

---

## 2026-08-27 · Orquestación: LangChain en lugar de LlamaIndex
El anteproyecto especificaba LlamaIndex. Se opta por LangChain por la amplitud
de su ecosistema de integraciones y la flexibilidad de sus abstracciones para
componer las dos fases del flujo (triaje y drafting) en un mismo marco. El
tutor autoriza la desviación respecto al anteproyecto.

## 2026-08-27 · Troceado por artículo, no por longitud fija
La unidad primaria de partición es el artículo legal; solo se subdivide lo que
supera el límite de caracteres. Evita fragmentos que mezclen el final de un
artículo con el principio del siguiente. Descartado el troceado por longitud
fija, pendiente de contrastar empíricamente.

## 2026-08-27 · Modelo de embeddings: multilingual-e5-small
Frente a e5-base, reduce el tiempo de ingesta a un tercio (308 s vs 903 s) con
MRR equivalente (0,8333 vs 0,8467) y Recall@3 superior. La menor latencia
beneficia también la codificación de cada consulta en tiempo de ejecución.

## 2026-08-27 · Recall@5 no sirve como criterio de decisión
Saturado en 93,3 % en las cinco configuraciones evaluadas. La comparación se
apoya en MRR y Recall@1. El golden set de 15 preguntas es insuficiente:
9 de ellas dan posición 1 en todas las corridas.

## 2026-08-27 · Limitación conocida: LIVA art. 84
No se recupera en ninguna configuración. Desajuste de vocabulario entre la
jerga profesional ("inversión del sujeto pasivo") y la redacción legal
("Sujetos pasivos"). No corregible por ajuste de parámetros. Justifica
búsqueda híbrida o expansión de consulta como trabajo futuro.

## 2026-08-27 · LLM generativo local vía Ollama
Hardware: GTX 1650 con 4 GB de VRAM (~3,4 GB útiles). Se descarta
PyTorch + bitsandbytes por problemas conocidos en Windows. Los embeddings se
mantienen en CPU para no competir por la VRAM con el LLM en la cadena
completa. Limitación asumida: los tiempos de generación con este hardware no
son aptos para explotación real.

## 2026-08-28 · Corpus de triaje sintético y reproducible. 
El corpus de evaluación del triaje (14 requerimientos AEAT) se genera por script desde una única estructura de datos, de la que se derivan a la vez el PDF y su anotación, de modo que documento y golden no pueden divergir. Se descarta usar notificaciones reales anonimizadas: evita el tratamiento de datos personales de contribuyentes.

## 2026-08-28 · Convenciones de anotación de eval/golden_triaje.json. 
periodo usa el código AEAT (1T–4T, 0A para anual); impuesto la sigla normalizada aunque el documento solo use la denominación desarrollada; importe es únicamente la cantidad que el documento exige o propone ingresar, no cualquier cifra en euros (bases y cuotas soportadas son distractores deliberados); nif es el del obligado tributario, nunca el del representante; articulos_citados se normaliza a nivel de artículo sin apartado, en formato "<NORMA> art. <N>".

## 2026-08-28 · Limitación conocida: sesgo del corpus de triaje. 
El corpus está generado por un LLM y será procesado por un LLM, por lo que su vocabulario es más homogéneo y limpio que el de una notificación real (sin ruido de OCR ni PDF escaneado). Es el mismo sesgo optimista ya identificado en el golden set del recuperador. Además, con n = 14 la granularidad mínima de cualquier métrica es de 7,1 puntos, insuficiente para discriminar configuraciones próximas: ampliar el corpus antes de medir.


## 2026-08-28 · Recorte de alcance por calendario. 
Se descarta la ampliación del golden set a 35-40 preguntas (coste 8-10 h, valor defensivo ya cubierto por la sección de limitaciones) y se reducen a 14 los requerimientos sintéticos de la AEAT. Se mantienen la prueba de troceado por longitud fija (2 h, sostiene la decisión del apartado 3.3.3) y una API con cuatro endpoints sin autenticación, con usuario fijo documentado como acotación de alcance.

## 2026-08-28 · Criterio de evaluación revisado en la memoria. 
El capítulo 5 debe presentar explícitamente que Recall@5, fijada a priori como métrica de decisión, resultó saturada (93,3 % en las cinco configuraciones) y que la decisión se trasladó a MRR y Recall@1. Presentar MRR como criterio original desaprovecha el argumento metodológico.

## 2026-08-29 · Troceado por longitud fija: contrastado empíricamente.
Implementado como segunda CHUNK_STRATEGY en config.py, con índice propio
(chroma_db_longitud_fija) y evaluado con el mismo golden set, modelo e5-base,
chunk=1800 y overlap=200 de la configuración base. Resultado: Recall@1 cae de
80,0% a 26,7% y MRR de 0,8467 a 0,5345, pero Recall@10 y cobertura SUBEN a
100% (recupera incluso LIVA art. 84, que fallaba en las cinco configuraciones
del sondeo de modelo/chunk). Lo explica que el 50,7% de los fragmentos (402
de 793) solapan más de un artículo: al diluirse el embedding entre dos o tres
artículos, los vecinos compiten por las primeras posiciones y degradan la
precisión aunque mejore la cobertura agregada. Confirma empíricamente la
decisión del 2026-08-27 de trocear por artículo. Detalle completo en
eval/tabla_comparativa_chunking.md.

**Confound declarado** (en código, en legal_splitter.py::split_ley_longitud_fija):
la estrategia por artículo antepone a cada fragmento una línea de contexto
("LGT · Artículo 66...") que en longitud fija no se puede construir, así que
la comparación es entre dos estrategias completas, no un parámetro aislado.
Debe declararse así en la memoria.

## 2026-08-29 · req_001 y req_002 son un par de ablación de maquetación. 
Comparten los nueve campos del golden de triaje y difieren únicamente en el formato del documento, de modo que cualquier discrepancia en la extracción es atribuible a la maquetación y no al contenido. Las métricas agregadas se calculan sobre los 13 casos de contenido distinto; req_002 se reporta por separado como prueba de robustez al formato.

## 2026-08-29 · Ablación de troceado: longitud fija frente a artículo. 
Con e5-base 1800/200 y todo lo demás idéntico, el troceado por longitud fija degrada Recall@1 del 80,0 % al 26,7 % y MRR de 0,8467 a 0,5345. La causa es que el 50,7 % de sus fragmentos (402 de 793) solapa más de un artículo, diluyendo el embedding entre artículos vecinos que compiten por las primeras posiciones. Queda así justificado empíricamente el particionado semántico-estructural del apartado 3.3.3, hasta ahora sostenido solo por argumento teórico.

## 2026-08-29 · Sesgo favorable a la estrategia descartada en la ablación. 
Los fragmentos de longitud fija se etiquetaron con todos los artículos que solapan, de modo que recuperar uno cuenta como acierto para cualquiera de ellos; esto infla artificialmente su Recall@10 (100 %) y su cobertura (100 %) por encima de los de la estrategia por artículo. El diseño se mantuvo deliberadamente generoso con la alternativa descartada, y debe declararse al presentar la tabla. Confound adicional: la estrategia por artículo antepone una línea de contexto que la longitud fija no puede construir, por lo que se comparan dos estrategias completas y no un parámetro aislado.

## 2026-08-30 · Esquema de triaje: "fichero" no es un campo extraído.
`RequerimientoAEAT` (src/triaje.py) define ocho campos, no nueve: el noveno
campo del golden ("fichero") identifica el PDF de origen y no está en su
texto, así que no tiene sentido pedírselo al LLM. El pipeline lo añade a
partir del nombre real del fichero procesado, fuera del esquema Pydantic.

## 2026-08-30 · Validación de NIF/CIF con dígito de control real, no solo formato.
`triaje.py::_valida_nif` implementa el algoritmo de control completo: módulo
23 sobre letra "TRWAGMYFPDXBNJZSQVHLCKE" para NIF de persona física, y el
algoritmo estándar de suma ponderada (par/impar con doblado) para CIF de
entidad, incluyendo qué letras iniciales exigen dígito de control, cuáles
letra, y cuáles admiten ambos. Comprobado contra los 13 NIF/CIF del golden
set: todos tienen dígito de control real y válido (el generador sintético
del corpus ya los calculó correctamente), así que una validación de solo
formato (regex) no los habría distinguido de un NIF con letra al azar.

## 2026-08-30 · Solo "importe" es Optional en el esquema de triaje.
El golden set nunca deja en null nif, impuesto, ejercicio, periodo,
plazo_dias ni tipo_documento: si el LLM no logra extraer alguno de esos
campos, la validación Pydantic debe fallar (y consumir un reintento), no
aceptar un None silencioso. Solo importe es Optional[float], porque el
golden sí lo anota en null cuando el documento no liquida ni propone ningún
importe (ver convención ya registrada el 2026-08-28).

## 2026-08-30 · Canonicalización de articulos_citados en evaluar_triaje.py, no en el esquema.
La normalización a "LEY art. N" vive en la medición, no en `RequerimientoAEAT`:
el esquema se limita a validar que sea una lista de cadenas no vacías. Razón:
la canonicalización debe aplicarse por igual al valor esperado (golden) y al
obtenido, y debe poder evolucionar sin tocar el contrato del LLM. Reconoce
tanto la sigla ("LGT art. 136") como el nombre completo de la norma tal cual
aparece en el propio documento ("Ley 58/2003, de 17 de diciembre, General
Tributaria"), con mapeo explícito LGT/LIVA/LIRPF/RIVA/RGAT, para no depender
de que el LLM abrevie exactamente como se le pide en el prompt.

## 2026-08-29 · Pista sobre el fallo del LIVA art. 84. 
En la corrida de longitud fija el artículo aparece en posición 3, frente al fallo sistemático en las cinco configuraciones por artículo, probablemente por arrastre de vocabulario del art. 83 contenido en el mismo fragmento. Esto sugiere que la ampliación de contexto del fragmento recuperado (parent document retrieval) es una línea de trabajo futuro más precisa que la búsqueda híbrida genérica para este tipo de fallo por desajuste de vocabulario.

## 2026-08-30 · Primeros resultados del triaje: el modelo confunde impuesto con ley de origen.
Ejecución completa de evaluar_triaje.py con qwen3b-tfg sobre los 13 documentos
(excl. req_002): accuracy 92,3 % en nif/impuesto/ejercicio/periodo/plazo_dias,
pero solo 69,2 % en tipo_documento y F1 = 44,6 % en articulos_citados. La causa
dominante del F1 bajo no es un fallo de normalización: en los cuatro
documentos de impuesto IRPF (req_004, req_007, req_011, req_014) el modelo
etiqueta como "LIRPF" artículos que el propio texto atribuye explícitamente a
la LGT o al RGAT (p. ej. "artículo 99 de la Ley 58/2003, General Tributaria"
se extrae como "LIRPF art. 99"). El modelo generaliza el impuesto del
documento a la norma de cada cita, en vez de leer la ley que la acompaña.
Confirma con datos la fragilidad ya anotada el 2026-08-28 sobre el sesgo
optimista del corpus: aquí el fallo es del modelo, no del corpus, pero
afecta igual de directo a la métrica de cobertura del índice (51,8 %, más
baja de lo esperable porque cuenta como "fuera de LGT/LIVA" citas que en
realidad sí eran de la LGT).

## 2026-08-30 · req_012 agota los 3 intentos: alucinación de un dígito del CIF.
Único documento sin extracción válida. El modelo devuelve "A9999997" (7
dígitos) en vez de "A99999997" (8 dígitos) en las tres tentativas: no es un
fallo de formato ocasional sino una alucinación repetida del mismo dígito
que los 2 reintentos, al usar el mismo prompt, no corrigen. Evidencia de que
el mecanismo de reintentos protege contra JSON mal formado o campos que
incumplen el esquema, pero no contra una transcripción sistemáticamente
errónea del propio modelo.

## 2026-08-30 · Ablación de maquetación (req_001 vs. req_002): robustez confirmada.
Extracción idéntica y correcta en ambos ficheros pese al cambio de
maquetación del PDF (mismo layout de datos, distinta distribución del
CSV/cabecera). Ninguna de las nueve variables se ve afectada: los 8 campos
de contenido y articulos_citados coinciden exactamente entre sí. Contrasta
con la fragilidad del modelo frente al desajuste impuesto/ley (entrada
anterior), que es un problema de contenido/razonamiento, no de maquetación.

## 2026-08-30 · Resultados del triaje (primera corrida). 
Con qwen3b-tfg sobre 13 documentos sintéticos: 92,3 % en los cinco campos de formato regular (NIF, impuesto, ejercicio, periodo, plazo), cifra que corresponde a 12 de 13 documentos, ya que uno falló íntegramente la validación Pydantic; articulos_citados obtiene F1 de 0,446 (precisión 0,462, exhaustividad 0,436) y la latencia media es de 9,12 s por documento. La extracción de referencias normativas es, por tanto, el punto débil del módulo y la principal línea de trabajo futuro.

## 2026-08-30 · Inconsistencia en la taxonomía de tipo_documento. 
La categoría requerimiento_iva_no_deducible del golden de triaje mezcla naturaleza del acto administrativo con materia tributaria, a diferencia de las otras cuatro, y no figura en el conjunto cerrado del esquema, por lo que sus tres casos fallan por construcción y deprimen la exactitud del campo al 69,2 %. Debe reetiquetarse conforme a la naturaleza del acto o declararse explícitamente como limitación del conjunto de evaluación.

## 2026-08-30 · Limitación del corpus sintético de triaje. 
Los requerimientos y sus anotaciones se generaron con el mismo asistente, por lo que la correspondencia entre documento y campos anotados es más regular que en notificaciones reales de la AEAT. Los resultados en campos de formato fijo no son extrapolables a documentos reales; el F1 de articulos_citados constituye el indicador más representativo de la dificultad efectiva de la tarea.


## 2026-08-30 · Segunda corrida del triaje: temperatura escalada, NIF desacoplado del esquema, cobertura sobre el golden.
Tres correcciones al módulo, motivadas por el diagnóstico de req_012 y por el
sesgo de la métrica de cobertura:

1. **Reintentos con temperatura escalada** (0,1 / 0,4 / 0,7, en
   config.TRIAJE_TEMPERATURAS, vía `options.temperature` de la API de
   Ollama). El diagnóstico había confirmado por hash que el modelo es
   determinista a temperatura fija, así que un reintento sin variarla nunca
   cambia la salida.
2. **nif_formato_valido como campo derivado**, no como validador que
   invalida el esquema. Un NIF con dígito de control incorrecto ya no
   arrastra los otros ocho campos del mismo documento (era exactamente el
   caso de req_012). Para los pocos casos en que OTRO campo sí hiciera
   fallar la validación completa, evaluar_triaje.py incorpora un "mejor
   esfuerzo" (`_mejor_esfuerzo`) que reutiliza las mismas funciones de
   coerción del esquema sobre el JSON crudo, para no comparar nunca valores
   sin coercionar.
3. **Cobertura del índice recalculada sobre el golden**, no sobre lo
   extraído: la versión anterior (51,8 %) mezclaba dos cosas distintas —
   cuánta normativa citada es indexable, y cuántas citas atribuye mal el
   modelo a otra ley (ver entrada anterior sobre IRPF/LIRPF)—. Sobre el
   golden, la cobertura real es del 75,0 % (18 de 24 artículos únicos
   citados en el corpus pertenecen a LGT o LIVA) y no depende del extractor.

Resultado tras aplicar las tres correcciones (13 documentos, más la
recategorización de tipo_documento del 2026-08-30 anterior): validación de
esquema 100 % a la primera (0 documentos rescatados por la variación de
temperatura — el determinismo de req_012 se resolvió por el cambio de
diseño del punto 2, no por el reintento), tipo_documento 100 %, nif 92,3 %
(req_012 sigue con CIF mal transcrito, pero ya no invalida el resto de
campos), articulos_citados F1 = 0,477 (antes 0,446: req_012 pasa de aportar
F1=0,00 —sin datos— a F1=0,40). El F1 por documento (nuevo, en
tabla_triaje.md) muestra la varianza real: 100 % en req_001/006/013, 0 % en
los tres documentos IRPF con la confusión LIRPF/LGT ya diagnosticada
(req_004, req_011, req_014). 

## 2026-08-30 · Resultados finales del triaje. 
Tras corregir la taxonomía y desacoplar la validación del NIF del esquema: validación estructural 100 %, tipo_documento 100 %, NIF 92,3 % (el único fallo es req_012, artefacto del corpus), articulos_citados F1 0,477 y cobertura del índice 75,0 % calculada sobre el golden. Los dos primeros valores derivan de correcciones metodológicas y no de mejoras del modelo, lo que debe declararse al presentarlos; el F1 de artículos y la exactitud del NIF son los indicadores de rendimiento efectivo.


## 2026-08-30 · Fallo de atribución normativa en el triaje. 
El modelo asigna a cada artículo citado la ley correspondiente al impuesto del documento en lugar de la norma que el texto asocia a esa cita: en los tres requerimientos de IRPF etiqueta como LIRPF artículos de la LGT, incluidos los de procedimiento (arts. 203, 209, 211), que aplican con independencia del impuesto. Acierta 8 de 9 números de artículo y no inventa ninguno, de modo que el F1 de 0,00 en esos casos mide la atribución de norma y no la localización de la referencia.

## 2026-08-30 · El fallo de atribución es silencioso y propaga error a la cadena completa. 
Una cita mal atribuida (p. ej. «LIRPF art. 203») supera la validación de esquema, existe como número de artículo y no es detectada por ningún control del sistema, pero conduce al recuperador a un índice que no contiene esa norma, de modo que el borrador se fundamenta sobre contexto inadecuado con formato impecable. Constituye la limitación más relevante del prototipo y el principal argumento a favor de la revisión humana obligatoria del apartado 3.4. Mitigaciones propuestas como trabajo futuro: fijar en el prompt la lista cerrada de normas admisibles con la regla de que los artículos de procedimiento pertenecen a la LGT, y validar cada atribución contra el índice para convertir el fallo silencioso en fallo detectable.

## 2026-08-30 · Modelo generativo local seleccionado. 
Se emplea Qwen2.5-3B-Instruct en formato GGUF con cuantización Q4_K_M (~2 GB), servido mediante Ollama con temperatura 0,1 y contexto de 8192 tokens. Ocupa 2288 MiB de los 4096 de la GTX 1650, lo que permite ejecución íntegra en GPU. El modelo hubo de descargarse desde Hugging Face e importarse con un Modelfile propio (qwen3b-tfg), ya que el registro de Ollama descarga los pesos desde un dominio de almacenamiento de Cloudflare bloqueado en la red de desarrollo.

## 2026-08-30 · Coerción de tipos en la salida del extractor. 
El modelo devuelve de forma recurrente los campos numéricos como cadenas ("ejercicio": "2023"), por lo que la validación Pydantic debe coercionar tipos y la comparación con el golden set ha de realizarse sobre el objeto ya validado y no sobre el JSON crudo, para evitar fallos atribuibles a diferencia de tipo y no de contenido.

## 2026-08-31 · Desglose de la extracción de artículos: localización frente a atribución. 
Con F1 laxo (solo número) de 96,9 % y precisión laxa del 100 %, el modelo no inventa ninguna referencia y localiza casi todas; el F1 estricto (ley + número) cae a 47,7 % y la tasa de atribución correcta es del 48,7 % (19 de 39 números localizados llevan la ley correcta). El déficit del módulo es, por tanto, exclusivamente de atribución normativa y no de localización, lo que descarta la ampliación del modelo como vía de mejora y señala el prompt y la validación contra el índice como intervenciones pertinentes.

## Auditoría bibliográfica del capítulo 2 (31/08/2026): 
se detectaron tres errores factuales refutados por documentación oficial —coste en tokens de una captura de pantalla (real: ~1.560 tokens para 1920×1080, no 100-200), cabecera X-Business de la API de Sage (es opcional, no obligatoria) y capacidades del servidor MCP de CData para Sage (es de solo lectura, no admite UPDATE)—, además de una atribución incorrecta a a3innuva de funcionalidades de auditoría que pertenecen a CCH Axcess. Corregidos en la memoria.

## El modelo generativo del módulo de triaje es Qwen2.5-3B 
(3,09 B de parámetros según la ficha oficial de Hugging Face), no "Qwen2 de 3,4 mil millones" como figuraba en §4.4.1: la familia Qwen2 no publicó ningún modelo de 3B. Corregido para preservar la trazabilidad del experimento.

## El texto consolidado de la Ley 37/1992 (LIVA) tiene una actualización publicada el 28/02/2026. 
Se declara explícitamente en §4.2.1 la fecha de la redacción efectivamente indexada en el corpus vectorial, para evitar que una reforma posterior a la ingesta invalide los resultados presentados en el capítulo 5.

## 2026-09-01 · Corrección: la distribución del F1 no es bimodal. 
El desglose documento a documento muestra tres casos con F1 estricto del 100 %, tres del 0 % y siete en valores intermedios (33,3 %, 40 %, 66,7 % y 80 %), de modo que la caracterización como distribución bimodal registrada el 30 de agosto es inexacta y debe sustituirse por la de un gradiente continuo. Lo que sí es categórico es la precisión laxa del 100 %: el modelo no produce ninguna referencia numérica ausente del conjunto esperado.

## 2026-09-01 · Resultados definitivos del triaje. 
Sobre 13 documentos: exactitud del 100 % en impuesto, ejercicio, periodo, plazo, tipo de documento e importe, y del 92,3 % en NIF (único fallo, req_012, artefacto del corpus); validación de esquema del 100 % a la primera; articulos_citados con F1 laxo del 96,9 % (precisión 100 %) frente a F1 estricto del 47,7 % y atribución correcta del 48,7 %; cobertura del índice del 75,0 % sobre el golden; latencia media de 9,27 s por documento. Los valores del 100 % en tipo de documento y validación de esquema derivan de correcciones metodológicas, no de mejoras del modelo, y así deben presentarse.