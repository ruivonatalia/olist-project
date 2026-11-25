"""
Gate 2 -- Retrieval evaluation.

Mede se search_context (embeddings sobre a camada de contexto) acha o
chunk certo (tabela ou métrica) pra cada pergunta do eval set, dentro do
top-k -- é o recall@k, mesma família de métrica do TCC, só que aplicada a
schema-retrieval (texto-pra-SQL) em vez de chunk retrieval de texto livre.
Não chama a API da Anthropic -- só o modelo de embeddings local.

Rodar com:
    ./.venv/bin/python -m gates.eval_retrieval
"""

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from context.semantic_layer import build_context_chunks
from mcp_server.retrieval import retrieve

K = 3
RECALL_THRESHOLD = 0.8  # recall@k mínimo pro gate passar


def log(status: str, check: str, **detail) -> None:
    print(json.dumps({"status": status, "check": check, **detail}, ensure_ascii=False, default=str))


def main() -> int:
    with open(os.path.join(os.path.dirname(__file__), "eval_set.json"), encoding="utf-8") as f:
        eval_set = json.load(f)

    chunks = build_context_chunks()
    hits = 0

    for item in eval_set:
        top_k, _ = retrieve(item["question"], chunks, k=K)
        names = [c["name"] for c in top_k]
        hit = item["expected_chunk"] in names
        hits += hit
        log(
            "PASS" if hit else "FAIL",
            "retrieval_top_k",
            id=item["id"],
            question=item["question"],
            expected=item["expected_chunk"],
            got=names,
        )

    recall_at_k = hits / len(eval_set)
    print()
    print(f"recall@{K} = {recall_at_k:.2f} ({hits}/{len(eval_set)})")

    if recall_at_k < RECALL_THRESHOLD:
        print(f"GATE 2 (retrieval eval): FALHOU -- recall@{K} abaixo do limiar ({RECALL_THRESHOLD}).")
        return 1

    print(f"GATE 2 (retrieval eval): PASSOU -- recall@{K} >= {RECALL_THRESHOLD}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
