"""
Carrega semantic_layer.yaml e monta os "chunks" recuperáveis por
embeddings: um por tabela (descrição + colunas + sinônimos) e um por
métrica de negócio -- mesma ideia da Atividade didática RAG 2, agora
reaproveitada como a camada de contexto que o servidor MCP expõe.
"""

import os

import yaml

SEMANTIC_LAYER_PATH = os.path.join(os.path.dirname(__file__), "semantic_layer.yaml")


def load_semantic_layer(path: str = SEMANTIC_LAYER_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_table_chunks(layer: dict) -> list[dict]:
    chunks = []
    for name, table in layer["tables"].items():
        cols = "; ".join(
            f"{col} ({info.get('type', '')}): {info['description']}"
            for col, info in table["columns"].items()
        )
        synonyms = ", ".join(table.get("synonyms", []))
        text = (
            f"Tabela `raw.{name}` -- {table['description'].strip()} "
            f"Também conhecida como: {synonyms}. "
            f"Colunas: {cols}."
        )
        chunks.append({"kind": "table", "name": name, "text": text})
    return chunks


def build_metric_chunks(layer: dict) -> list[dict]:
    chunks = []
    for name, metric in layer.get("metrics", {}).items():
        text = (
            f"Métrica `{name}` -- {metric['description'].strip()} "
            f"Tabelas envolvidas: {', '.join(metric.get('tables', []))}. "
            f"Definição de referência em SQL: {metric['sql']}"
        )
        chunks.append({"kind": "metric", "name": name, "text": text})
    return chunks


def build_context_chunks(layer: dict | None = None) -> list[dict]:
    """Corpus completo (tabelas + métricas) indexado pelo retrieval."""
    layer = layer or load_semantic_layer()
    return build_table_chunks(layer) + build_metric_chunks(layer)
