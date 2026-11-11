# Olist Project

Chat web que responde perguntas em português sobre o dataset público da
Olist (e-commerce brasileiro), com texto, tabela e gráfico -- construído
em três passos didáticos:

1. [**Ingestão**](docs/01-ingestao.md) -- CSVs do Kaggle + MongoDB
   carregados num Postgres (Supabase), schema `raw`.
2. [**RAG com LangChain + MCP**](docs/02-rag-langchain.md) -- um agente
   LangChain usa um servidor MCP para descobrir o schema (embeddings) e
   rodar SQL com uma credencial restrita a leitura.
3. [**Deploy**](docs/03-deploy.md) -- aplicação publicada no Render.

## Estrutura

```
data/download_data.py       # baixa os CSVs do Kaggle para data/raw/
sql/schema.sql               # DDL do schema `raw`
ingest/                      # CSV + MongoDB -> Postgres
  ingest_postgres.py
  ingest_mongo.py
  sync_mongo_to_raw.py
  run_all.py

context/semantic_layer.yaml  # tabelas, colunas, sinônimos, métricas
mcp_server/                  # servidor MCP: search_context, list_tables, run_sql
rag/agent.py                 # agente LangChain (consome o servidor MCP)
sql/rag_reader_role.sql      # role restrita a SELECT no schema `raw`
sql/rag_log_schema.sql       # log de retrieval (app.rag_query_log)

web/main.py                  # API (POST /api/ask)
web/static/                   # chat (HTML/CSS/JS + Plotly via CDN)

render.yaml                  # blueprint de deploy (Render)
```

## Rodar localmente

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env   # preencha com suas credenciais (ver docs/01 e docs/02)

./.venv/bin/python ingest/ingest_postgres.py   # uma vez, pra carregar os dados
./.venv/bin/uvicorn web.main:app --reload --port 8010
```

Abre em [http://localhost:8010](http://localhost:8010).

Perguntas de exemplo: "Qual o ticket médio dos pedidos?", "Quantos
pedidos existem por status?", "Qual a receita total por mês?".
