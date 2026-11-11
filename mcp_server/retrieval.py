"""
Retrieval sobre a camada de contexto usando embeddings reais
(sentence-transformers, modelo multilíngue) -- mesma mecânica da
Atividade didática RAG 2 (texto -> vetor -> similaridade de cosseno ->
top-k), reaproveitada aqui dentro do servidor MCP.
"""

import logging
import os

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

from sentence_transformers import SentenceTransformer, util

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model_cache: dict[str, SentenceTransformer] = {}
_chunk_embeddings_cache = {}


def get_model(model_name: str = MODEL_NAME) -> SentenceTransformer:
    if model_name not in _model_cache:
        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def embed_chunks(chunks: list[dict], model_name: str = MODEL_NAME):
    """Embeda o corpus inteiro uma vez e guarda em cache (chamadas
    seguintes reusam, já que a camada de contexto não muda em runtime)."""
    key = model_name
    if key not in _chunk_embeddings_cache:
        model = get_model(model_name)
        texts = [c["text"] for c in chunks]
        embeddings = model.encode(texts, convert_to_tensor=True, normalize_embeddings=True)
        _chunk_embeddings_cache[key] = embeddings
    return get_model(model_name), _chunk_embeddings_cache[key]


def embed_query(question: str, model: SentenceTransformer):
    return model.encode(question, convert_to_tensor=True, normalize_embeddings=True)


def retrieve(question: str, chunks: list[dict], model_name: str = MODEL_NAME, k: int = 3) -> tuple[list[dict], list[float]]:
    """Retorna (top-k chunks com score, embedding da pergunta como lista
    de floats) -- o embedding é devolvido pra quem chamar poder logar."""
    model, chunk_embeddings = embed_chunks(chunks, model_name)
    query_emb = embed_query(question, model)
    scores = util.cos_sim(query_emb, chunk_embeddings)[0].tolist()
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    top = [{"score": float(s), **c} for s, c in ranked[:k]]
    return top, query_emb.tolist()
