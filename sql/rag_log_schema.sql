-- Log de observabilidade do retrieval: uma linha por pergunta respondida
-- pelo servidor MCP, guardando o embedding da pergunta, os chunks
-- recuperados (com score de similaridade) e o modelo usado -- pra poder
-- auditar depois "por que o sistema respondeu isso" sem precisar
-- reproduzir a chamada.
--
-- Vive no mesmo Postgres do projeto "Desenvolvimento de app similar ao
-- olist" (schema `app`, ao lado de sellers_accounts/customers_accounts),
-- reaproveitando a conexão que já existe -- não é um banco novo.
--
-- Embedding como double precision[] em vez de um tipo `vector` (pgvector):
-- o Homebrew só compila pgvector pro Postgres 17/18, e esta instância é
-- Postgres 16. Como este log é pra inspeção/auditoria, não pra busca
-- vetorial indexada (a similaridade já foi calculada em Python antes de
-- gravar), um array comum guarda o mesmo dado sem precisar da extensão.

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.rag_query_log (
    id                  serial PRIMARY KEY,
    question            text NOT NULL,
    -- `question` é o que o MODELO mandou pro search_context (às vezes
    -- reformulado); `original_question` é o texto literal que o usuário
    -- digitou no chat -- preenchido pela camada web (web/main.py), que é
    -- a única que vê o texto original, não pelo servidor MCP.
    original_question   text,
    embedding_model     text NOT NULL,
    embedding_dim       integer NOT NULL,
    question_embedding  double precision[] NOT NULL,
    chunks              jsonb NOT NULL,   -- [{kind, name, score, text}, ...], mais relevante primeiro
    top_score           double precision,
    created_at          timestamp NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_rag_query_log_created_at ON app.rag_query_log (created_at DESC);
