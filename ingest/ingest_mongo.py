"""
Carrega os dados "não-estruturados" no MongoDB:
  - reviews reais do Olist (order_reviews.csv) -- um documento por review,
    incluindo só os campos que existem de fato (sem chave para title/
    message quando a review não tem esses campos, em vez de gravar null)
    -- é o retrato mais fiel de schema variável que um banco de documentos
    guarda, diferente de uma tabela relacional onde toda linha tem as
    mesmas colunas.
  - tickets de suporte sintéticos (gerados com Faker, pt_BR) -- não existe
    no dataset original; simula um sistema de atendimento ligado a pedidos
    reais por order_id, também com schema variável (ticket resolvido tem
    resolved_at; aberto, não tem).

Rodar com:
    ./.venv/bin/python ingest/ingest_mongo.py
"""

import os
import random
import uuid
from datetime import timedelta

import pandas as pd
from dotenv import load_dotenv
from faker import Faker
from pymongo import MongoClient

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
MONGO_URI = os.environ.get("OLIST_MONGO_URI", "mongodb://127.0.0.1:27017")
DB_NAME = "olist"

CATEGORIES = [
    "atraso na entrega", "produto com defeito", "duvida sobre pagamento",
    "solicitacao de troca", "elogio", "produto errado enviado",
]
CHANNELS = ["chat", "email", "telefone"]
SEED = 42


def load_reviews(db):
    df = pd.read_csv(os.path.join(DATA_DIR, "olist_order_reviews_dataset.csv"))
    docs = []
    for _, row in df.iterrows():
        doc = {
            "review_id": row["review_id"],
            "order_id": row["order_id"],
            "review_score": int(row["review_score"]),
        }
        for field in ("review_comment_title", "review_comment_message", "review_creation_date", "review_answer_timestamp"):
            if pd.notna(row.get(field)):
                doc[field] = row[field]
        docs.append(doc)

    db.reviews.drop()
    db.reviews.insert_many(docs)
    print(f"{len(docs)} reviews inseridas em {DB_NAME}.reviews")


def generate_support_tickets(db, n: int = 2000, seed: int = SEED):
    fake = Faker("pt_BR")
    Faker.seed(seed)
    random.seed(seed)

    orders = pd.read_csv(os.path.join(DATA_DIR, "olist_orders_dataset.csv"), usecols=["order_id", "order_purchase_timestamp"])
    orders["order_purchase_timestamp"] = pd.to_datetime(orders["order_purchase_timestamp"])
    sample = orders.sample(n=n, random_state=seed)

    docs = []
    for _, row in sample.iterrows():
        created_at = row["order_purchase_timestamp"] + timedelta(days=random.randint(1, 30))
        status = random.choices(["resolvido", "em andamento", "aberto"], weights=[0.7, 0.2, 0.1])[0]
        doc = {
            "ticket_id": str(uuid.uuid4()),
            "order_id": row["order_id"],
            "channel": random.choice(CHANNELS),
            "category": random.choice(CATEGORIES),
            "priority": random.choices(["baixa", "media", "alta"], weights=[0.5, 0.35, 0.15])[0],
            "status": status,
            "customer_message": fake.paragraph(nb_sentences=random.randint(1, 4)),
            "created_at": created_at.to_pydatetime(),
        }
        if status == "resolvido":
            doc["resolved_at"] = created_at.to_pydatetime() + timedelta(hours=random.randint(1, 96))
        docs.append(doc)

    db.support_tickets.drop()
    db.support_tickets.insert_many(docs)
    print(f"{len(docs)} tickets de suporte sintéticos inseridos em {DB_NAME}.support_tickets")


def main():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    load_reviews(db)
    generate_support_tickets(db)
    client.close()


if __name__ == "__main__":
    main()
