# Passo a passo: ingestão no Postgres (Supabase)

## 1. Criar o banco (Supabase)

1. Acesse [supabase.com](https://supabase.com) e crie um projeto (**New Project**).
2. Defina uma senha do banco e anote -- vai precisar dela na connection string.
3. Espere o projeto provisionar (~2 min).
4. No topo da página do projeto, clique em **Connect**.
5. Em **Connection string**, escolha o modo **Session** (porta `5432`) -- não o
   *Transaction pooler*: a ingestão usa `COPY`, que precisa de conexão direta.
6. Copie a string e troque `[YOUR-PASSWORD]` pela senha real.

## 2. Configurar o ambiente

```bash
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edite o `.env` e preencha `OLIST_PG_DSN` com a connection string do passo 1.

## 3. Baixar os CSVs do Olist

Precisa de credenciais do Kaggle (`~/.kaggle/kaggle.json`, ou as variáveis de
ambiente `KAGGLE_USERNAME` / `KAGGLE_KEY`):

```bash
./.venv/bin/python data/download_data.py
```

Isso baixa os CSVs para `data/raw/`.

## 4. Rodar a ingestão

Só os CSVs (schema `raw` com `customers`, `geolocation`, `sellers`,
`category_translation`, `products`, `orders`, `order_items`, `order_payments`):

```bash
./.venv/bin/python ingest/ingest_postgres.py
```

Para incluir também os dados não-estruturados (`raw.reviews` e
`raw.support_tickets`, que vêm de um MongoDB local via Mongo -> Postgres),
rode a cadeia completa:

```bash
./.venv/bin/python ingest/run_all.py
```

(precisa de um MongoDB rodando -- `OLIST_MONGO_URI` no `.env`).

## 5. Conferir no Supabase

No **Table Editor**, troque o schema de `public` para **`raw`** no seletor
de schema -- por padrão o Supabase só mostra `public`, e todas as tabelas
da ingestão ficam em `raw` (ver comentário em `sql/schema.sql` sobre por
que a landing zone fica separada do schema de aplicação).
