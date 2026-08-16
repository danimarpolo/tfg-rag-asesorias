"""
embeddings.py
=============
Construcción del modelo de embeddings usado tanto en la ingesta como en la
consulta.

IMPORTANTE: ingest.py y query.py DEBEN usar exactamente el mismo modelo y la
misma configuración. Si se indexa con un modelo y se consulta con otro, los
vectores viven en espacios distintos y la recuperación devuelve ruido sin dar
ningún error. Centralizar la construcción aquí elimina esa clase de fallo.
"""

from langchain_huggingface import HuggingFaceEmbeddings

import config


class E5Embeddings(HuggingFaceEmbeddings):
    """
    Envoltorio para la familia de modelos E5 (intfloat/multilingual-e5-*).

    Estos modelos se entrenaron de forma ASIMÉTRICA: el texto que se indexa
    debe prefijarse con "passage: " y el texto de la consulta con "query: ".
    HuggingFaceEmbeddings no lo hace automáticamente, así que lo añadimos aquí.

    Es un detalle pequeño pero con impacto real y medible en el recall: sin los
    prefijos, el modelo trata consulta y documento como el mismo tipo de texto
    y pierde parte de la ventaja del entrenamiento contrastivo.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return super().embed_documents([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return super().embed_query(f"query: {text}")


def get_embeddings():
    """Devuelve la instancia de embeddings configurada en config.py."""
    kwargs = dict(
        model_name=config.EMBEDDING_MODEL,
        model_kwargs={"device": config.EMBEDDING_DEVICE},
        # Normalizamos a norma 1: es lo que espera la métrica coseno de Chroma.
        encode_kwargs={"normalize_embeddings": True},
    )

    if config.USE_E5_PREFIXES:
        return E5Embeddings(**kwargs)
    return HuggingFaceEmbeddings(**kwargs)
