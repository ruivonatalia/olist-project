"""
Baixa o dataset "Brazilian E-Commerce Public Dataset by Olist" do Kaggle
via kagglehub e copia os CSVs para data/raw/, de onde ingest/ingest_postgres.py
os carrega no Postgres.

Precisa de credenciais do Kaggle configuradas -- ver docs/01-ingestao.md
(arquivo ~/.kaggle/kaggle.json, ou variáveis de ambiente KAGGLE_USERNAME /
KAGGLE_KEY).
"""

import os
import shutil

import kagglehub

DATASET = "olistbr/brazilian-ecommerce"
RAW_DIR = os.path.join(os.path.dirname(__file__), "raw")


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    print(f"Baixando {DATASET} via kagglehub (pode levar um tempo na primeira vez)...")
    cache_path = kagglehub.dataset_download(DATASET)
    print(f"Dataset em cache local: {cache_path}")

    copied = 0
    for name in os.listdir(cache_path):
        if name.endswith(".csv"):
            shutil.copy2(os.path.join(cache_path, name), os.path.join(RAW_DIR, name))
            copied += 1
    print(f"{copied} arquivos CSV copiados para {RAW_DIR}")
    if copied == 0:
        print("Nenhum CSV encontrado -- confira se o download funcionou corretamente.")


if __name__ == "__main__":
    main()
