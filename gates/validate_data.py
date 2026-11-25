"""
Gate 1 -- Data validation.

Confere se o schema `raw` (Postgres/Supabase) está íntegro o bastante
pra alimentar o retrieval e o agente: cada tabela do semantic_layer.yaml
existe, tem um número mínimo de linhas, e as colunas-chave não têm nulos.

Mesmo padrão da aula 3 (validate_data.py do curso): roda, imprime um log
estruturado (JSON) por checagem, e sai com exit code 1 na primeira falha
-- fail fast, sem gastar tempo nos gates seguintes em cima de dado ruim.

Rodar com:
    ./.venv/bin/python -m gates.validate_data
"""

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(REPO_ROOT, ".env"))

from context.semantic_layer import load_semantic_layer
from mcp_server.db import get_reader_conn

MIN_ROWS = 1

# Colunas-chave que não podem ter nulo em cada tabela -- um subconjunto
# pequeno e deliberado (chaves primárias/estrangeiras usadas nos joins do
# semantic_layer.yaml), não a lista inteira de colunas.
KEY_COLUMNS = {
    "orders": ["order_id", "customer_id"],
    "customers": ["customer_id", "customer_unique_id"],
    "order_items": ["order_id", "product_id", "price"],
    "order_payments": ["order_id", "payment_value"],
    "reviews": ["order_id", "review_score"],
    "products": ["product_id"],
    "sellers": ["seller_id"],
}


def log(status: str, check: str, **detail) -> None:
    print(json.dumps({"status": status, "check": check, **detail}, ensure_ascii=False, default=str))


def main() -> int:
    layer = load_semantic_layer()
    tables = list(layer["tables"].keys())
    conn = get_reader_conn()
    failures = []
    try:
        with conn.cursor() as cur:
            for name in tables:
                # 1) a tabela existe no schema raw?
                try:
                    cur.execute(f"SELECT COUNT(*) FROM raw.{name}")
                    (count,) = cur.fetchone()
                except Exception as e:
                    log("FAIL", "table_exists", table=name, error=str(e))
                    failures.append(f"raw.{name} não existe ou não pôde ser lida")
                    continue

                # 2) row count mínimo
                if count < MIN_ROWS:
                    log("FAIL", "min_row_count", table=name, rows=count, min_required=MIN_ROWS)
                    failures.append(f"raw.{name} tem {count} linhas (mínimo: {MIN_ROWS})")
                else:
                    log("PASS", "min_row_count", table=name, rows=count)

                # 3) nulls nas colunas-chave
                for col in KEY_COLUMNS.get(name, []):
                    cur.execute(f"SELECT COUNT(*) FROM raw.{name} WHERE {col} IS NULL")
                    (nulls,) = cur.fetchone()
                    if nulls > 0:
                        log("FAIL", "null_check", table=name, column=col, nulls=nulls)
                        failures.append(f"raw.{name}.{col} tem {nulls} valor(es) nulo(s)")
                    else:
                        log("PASS", "null_check", table=name, column=col)
    finally:
        conn.close()

    print()
    if failures:
        print(f"GATE 1 (data validation): FALHOU -- {len(failures)} problema(s):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"GATE 1 (data validation): PASSOU -- {len(tables)} tabelas verificadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
