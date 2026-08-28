# TFG — Prototipo RAG para requerimientos AEAT

Proyecto de fin de grado. Defensa en septiembre de 2026.

## Contexto
Recuperación de normativa tributaria (LGT y LIVA) sobre ChromaDB, con troceado
por artículo. El MVP procesa requerimientos de la AEAT: extrae los datos,
recupera los artículos aplicables y redacta un borrador de contestación.

## Entorno
Windows, PowerShell, VS Code. Entorno virtual en `.venv`.
Comandos siempre desde la raíz: `python src\ingest.py`.

## Reglas
- Reejecutar SIEMPRE `python src\ingest.py --reset` tras tocar el troceado o
  el modelo de embeddings. Sin `--reset` los resultados son inválidos y no da
  ningún error.
- Todos los parámetros del experimento viven en `src\config.py`. No introducir
  constantes en los scripts.
- `src\embeddings.py` es la única fábrica de embeddings: ingesta y consulta
  deben usar el mismo modelo.
- Comentarios y mensajes de consola en español.

## Registro de decisiones
Las decisiones de diseño con su justificación se anotan en `decisiones.md`.
Cuando tomemos una decisión técnica relevante, añádela ahí sin que tenga que
pedírtelo.