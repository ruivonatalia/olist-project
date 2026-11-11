"""
Cria o schema `raw` no Postgres (sql/schema.sql) e carrega cada CSV do
Olist via COPY -- muito mais rápido que INSERT linha a linha para as
tabelas grandes (order_items tem ~112 mil linhas, geolocation ~1 milhão).

Rodar com:
    ./.venv/bin/python ingest/ingest_postgres.py
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
SCHEMA_SQL = os.path.join(os.path.dirname(__file__), "..", "sql", "schema.sql")
DSN = os.environ.get("OLIST_PG_DSN", "dbname=olist host=/tmp")

TABLES = [
    ("raw.customers", "olist_customers_dataset.csv"),
    ("raw.geolocation", "olist_geolocation_dataset.csv"),
    ("raw.sellers", "olist_sellers_dataset.csv"),
    ("raw.category_translation", "product_category_name_translation.csv"),
    ("raw.products", "olist_products_dataset.csv"),
    ("raw.orders", "olist_orders_dataset.csv"),
    ("raw.order_items", "olist_order_items_dataset.csv"),
    ("raw.order_payments", "olist_order_payments_dataset.csv"),
]


def create_schema(conn):
    with open(SCHEMA_SQL, encoding="utf-8") as f:
        ddl = f.read()
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def copy_csv(conn, table: str, csv_name: str):
    path = os.path.join(DATA_DIR, csv_name)
    with conn.cursor() as cur, open(path, encoding="utf-8") as f:
        cur.copy_expert(f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')", f)
    conn.commit()


def main():
    conn = psycopg2.connect(DSN)
    print("Criando schema raw (sql/schema.sql)...")
    create_schema(conn)

    for table, csv_name in TABLES:
        print(f"Carregando {csv_name} -> {table}...")
        copy_csv(conn, table, csv_name)
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {cur.fetchone()[0]} linhas")

    conn.close()
    print("Ingestão Postgres concluída.")


if __name__ == "__main__":
    main()
