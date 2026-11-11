"""
Roda a ingestão completa, na ordem certa:
  1. Postgres  -- CSVs do Olist -> schema raw.*
  2. MongoDB   -- reviews reais + tickets de suporte sintéticos
  3. Sync      -- Mongo -> raw.reviews / raw.support_tickets (Postgres)

Rodar com:
    ./.venv/bin/python ingest/run_all.py
"""

from ingest_postgres import main as ingest_postgres
from ingest_mongo import main as ingest_mongo
from sync_mongo_to_raw import main as sync_mongo_to_raw

if __name__ == "__main__":
    print("=== 1/3 Postgres (CSVs -> raw.*) ===")
    ingest_postgres()

    print("\n=== 2/3 MongoDB (reviews + tickets sintéticos) ===")
    ingest_mongo()

    print("\n=== 3/3 Sync Mongo -> raw.reviews / raw.support_tickets ===")
    sync_mongo_to_raw()

    print("\nIngestão completa.")
