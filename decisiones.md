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
El corpus de evaluación del triaje (14 requerimientos AEAT) se genera por script desde una única estructura de datos, de la que se derivan a la vez el PDF y su anotación, de modo que documento y golden no pueden divergir. Se descarta usar notificaciones reales anonimizadas: evita el tratamiento de datos personales de contribuyentes y permite publicar el corpus como anexo de la memoria.

## 2026-08-28 · Convenciones de anotación de eval/golden_triaje.json. 
periodo usa el código AEAT (1T–4T, 0A para anual); impuesto la sigla normalizada aunque el documento solo use la denominación desarrollada; importe es únicamente la cantidad que el documento exige o propone ingresar, no cualquier cifra en euros (bases y cuotas soportadas son distractores deliberados); nif es el del obligado tributario, nunca el del representante; articulos_citados se normaliza a nivel de artículo sin apartado, en formato "<NORMA> art. <N>".

## 2026-08-28 · Limitación conocida: sesgo del corpus de triaje. 
El corpus está generado por un LLM y será procesado por un LLM, por lo que su vocabulario es más homogéneo y limpio que el de una notificación real (sin ruido de OCR ni PDF escaneado). Es el mismo sesgo optimista ya identificado en el golden set del recuperador. Además, con n = 14 la granularidad mínima de cualquier métrica es de 7,1 puntos, insuficiente para discriminar configuraciones próximas: ampliar el corpus antes de medir.

## 2026-08-28 · Debilidad de la taxonomía de tipo_documento. 
Las cinco clases del triaje mezclan dos ejes: cuatro describen la forma del acto administrativo (requerimiento, propuesta de liquidación, trámite de audiencia, acuerdo sancionador) y una describe la materia (requerimiento_iva_no_deducible), por lo que no son mutuamente excluyentes. Se asume conscientemente por ser una taxonomía operativa orientada al enrutamiento en una asesoría; la alternativa, separar forma_acto y materia en dos campos, queda documentada como mejora inmediata.

## 2026-08-28 · Calendario de depósito. 
El tutor confirma que la ventana de depósito del TFG es del 9 al 12 de septiembre de 2026 y que estará de vacaciones hasta el día 9, por lo que se planifica asumiendo una única ronda de revisión. Consecuencia: la memoria pasa a ser la prioridad absoluta sobre el desarrollo de software.

## 2026-08-28 · Recorte de alcance por calendario. 
Se descarta la ampliación del golden set a 35-40 preguntas (coste 8-10 h, valor defensivo ya cubierto por la sección de limitaciones) y se reducen a 8 los requerimientos sintéticos de la AEAT. Se mantienen la prueba de troceado por longitud fija (2 h, sostiene la decisión del apartado 3.3.3) y una API con cuatro endpoints sin autenticación, con usuario fijo documentado como acotación de alcance.

## 2026-08-28 · Criterio de evaluación revisado en la memoria. 
El capítulo 5 debe presentar explícitamente que Recall@5, fijada a priori como métrica de decisión, resultó saturada (93,3 % en las cinco configuraciones) y que la decisión se trasladó a MRR y Recall@1. Presentar MRR como criterio original desaprovecha el argumento metodológico.