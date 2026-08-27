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