# Plataforma de IA generativa para asesorías — Prototipo TFG

Sistema de triaje y generación asistida de escritos de contestación a
requerimientos de la AEAT (IRPF e IVA), mediante arquitectura RAG sobre los
textos consolidados de la LGT (Ley 58/2003) y la LIVA (Ley 37/1992).

Trabajo de Fin de Grado — Ingeniería Informática, Universidad de Málaga.
Daniel Márquez Polonio. Tutor: Francisco López Valverde.

## Estructura

- `src/` — ingesta y particionado del corpus normativo, recuperación
  semántica, triaje con validación Pydantic, cadena completa de generación
  y scripts de evaluación.
- `api/` — backend FastAPI (cuatro endpoints).
- `app/` — interfaz Streamlit de página única.
- `eval/` — conjuntos de referencia anotados y resultados de las
  evaluaciones en JSON.
- `tools/corpus/` — generador del corpus sintético de requerimientos y su
  conjunto anotado, junto con el script de verificación de ambos.
- `modelfile/` — Modelfile de importación del modelo generativo en Ollama.
- `data/normativa/` — textos consolidados del BOE (no versionados; deben
  descargarse antes de ejecutar la ingesta).

## Resultados principales

Documentados en el Capítulo 5 de la memoria.

- Recuperación: cobertura 93,3 %, MRR 0,8467 sobre 15 preguntas anotadas.
- Triaje: validación de esquema 100 %, F1 laxo 96,9 % en extracción de
  referencias normativas, con tasa de atribución correcta del 48,7 %.
- Generación: 91,5 % de citas fundamentadas, 3,4 % de alucinación normativa.

## Requisitos

- Python 3.12, dependencias en `requirements.lock.txt`
- Ollama con el modelo importado desde `modelfile/`
- Índice vectorial generado con `python src/ingest.py --reset`

## Ejecución

Backend y frontend, en dos terminales:

    uvicorn api.main:app --port 8000
    streamlit run app/interfaz.py