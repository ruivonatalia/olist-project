"""
Extrai os documentos do MongoDB (reviews + support_tickets) e materializa
como tabelas no schema `raw` do Postgres -- a ponte entre o banco
não-estruturado e o dbt, que só executa SQL e não fala com o Mongo
diretamente. Simula o que, numa stack real, seria um job agendado de
"reverse ETL" (ex: Airflow, Fivetran) rodando periodicamente.

Rodar com:
    ./.venv/bin/python ingest/sync_mongo_to_raw.py
"""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.environ.get("OLIST_MONGO_URI", "mongodb://127.0.0.1:27017")
PG_DSN = os.environ.get("OLIST_PG_DSN", "dbname=olist host=/tmp")


def sync_reviews(mongo_db, pg_conn):
    docs = list(mongo_db.reviews.find({}, {"_id": 0}))
    rows = [
        (
            d["review_id"], d.get("order_id"), d.get("review_score"),
            d.get("review_comment_title"), d.get("review_comment_message"),
            d.get("review_creation_date"), d.get("review_answer_timestamp"),
        )
        for d in docs
    ]
    with pg_conn.cursor() as cur:
        cur.execute("TRUNCATE raw.reviews")
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO raw.reviews "
            "(review_id, order_id, review_score, review_comment_title, review_comment_message, "
            "review_creation_date, review_answer_timestamp) VALUES %s",
            rows,
        )
    pg_conn.commit()
    print(f"{len(rows)} reviews sincronizadas Mongo -> raw.reviews")


def sync_support_tickets(mongo_db, pg_conn):
    docs = list(mongo_db.support_tickets.find({}, {"_id": 0}))
    rows = [
        (
            d["ticket_id"], d.get("order_id"), d.get("channel"), d.get("category"),
            d.get("priority"), d.get("status"), d.get("customer_message"),
            d.get("created_at"), d.get("resolved_at"),
        )
        for d in docs
    ]
    with pg_conn.cursor() as cur:
        cur.execute("TRUNCATE raw.support_tickets")
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO raw.support_tickets "
            "(ticket_id, order_id, channel, category, priority, status, customer_message, created_at, resolved_at) "
            "VALUES %s",
            rows,
        )
    pg_conn.commit()
    print(f"{len(rows)} tickets sincronizados Mongo -> raw.support_tickets")


def main():
    mongo_db = MongoClient(MONGO_URI)[os.environ.get("OLIST_MONGO_DB", "olist")]
    pg_conn = psycopg2.connect(PG_DSN)
    sync_reviews(mongo_db, pg_conn)
    sync_support_tickets(mongo_db, pg_conn)
    pg_conn.close()


if __name__ == "__main__":
    main()
