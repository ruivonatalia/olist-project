"""
Servidor MCP que dá ao agente LangChain acesso aos dados fictícios da
Olist, por três ferramentas:

  - search_context: recupera trechos relevantes da camada de contexto
    (tabelas/métricas) por similaridade de embeddings -- a etapa de
    "retrieval" do RAG. Loga pergunta, embedding, chunks e scores em
    app.rag_query_log (ver sql/rag_log_schema.sql).
  - run_sql: executa um SELECT contra o schema `raw`, usando uma conexão
    com a role rag_reader (só leitura, só esse schema -- ver
    sql/rag_reader_role.sql). Bloqueia qualquer coisa que não seja SELECT
    já no texto, e de novo no banco, como defesa em profundidade.
  - list_tables: lista as tabelas da camada de contexto sem gastar uma
    chamada de embeddings -- índice rápido do schema.

Rodar com:
    ./.venv/bin/python -m mcp_server.server
(mas normalmente é o cliente MCP -- rag/agent.py -- que inicia este
processo sozinho via stdio, não se roda à mão.)
"""

import datetime
import decimal
import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP

from context.semantic_layer import build_context_chunks, load_semantic_layer
from mcp_server.db import get_owner_conn, get_reader_conn
from mcp_server.retrieval import MODEL_NAME, retrieve

mcp = FastMCP(
    name="olist-context",
    instructions=(
        "Ferramentas para responder perguntas sobre o banco de dados "
        "fictício da Olist (schema `raw` no Postgres). Use search_context "
        "primeiro para descobrir quais tabelas/colunas usar, depois "
        "run_sql para executar a consulta. Nunca invente nomes de coluna "
        "-- confirme com search_context ou list_tables antes."
    ),
)

_layer = load_semantic_layer()
_chunks = build_context_chunks(_layer)

MAX_ROWS = 200


def _log_query(question: str, chunks_with_scores: list[dict], query_embedding: list[float]) -> None:
    """Grava a pergunta, o embedding dela, os chunks recuperados (com
    score) e o modelo usado em app.rag_query_log -- usa a conexão dona
    do banco (não a rag_reader), porque é o próprio servidor escrevendo,
    não SQL vindo do agente."""
    conn = get_owner_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app.rag_query_log
                    (question, embedding_model, embedding_dim, question_embedding, chunks, top_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    question,
                    MODEL_NAME,
                    len(query_embedding),
                    query_embedding,
                    json.dumps(chunks_with_scores, ensure_ascii=False),
                    chunks_with_scores[0]["score"] if chunks_with_scores else None,
                ),
            )
        conn.commit()
    finally:
        conn.close()


@mcp.tool()
def search_context(question: str, k: int = 3) -> list[dict]:
    """Busca, por similaridade de embeddings, as tabelas e métricas da
    camada de contexto mais relevantes para a pergunta em português.
    Retorna até k chunks com nome, tipo (tabela ou métrica), texto
    descritivo e score de similaridade (0 a 1, maior = mais relevante).
    Toda chamada é registrada em app.rag_query_log para auditoria."""
    top_chunks, query_embedding = retrieve(question, _chunks, k=k)
    _log_query(question, top_chunks, query_embedding)
    return [
        {"kind": c["kind"], "name": c["name"], "score": round(c["score"], 4), "text": c["text"]}
        for c in top_chunks
    ]


@mcp.tool()
def list_tables() -> list[dict]:
    """Lista todas as tabelas disponíveis no schema `raw`, com uma
    descrição curta de cada uma -- não usa embeddings, é só um índice
    rápido pra explorar o schema sem gastar uma chamada de retrieval."""
    return [
        {"table": f"raw.{name}", "description": t["description"].strip()}
        for name, t in _layer["tables"].items()
    ]


_SELECT_ONLY = re.compile(r"(?is)^\s*select\b")


def _jsonable(value):
    """psycopg2 devolve datetime/Decimal, que o protocolo MCP (JSON) não
    serializa direto -- normaliza pra str/float antes de responder."""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


@mcp.tool()
def run_sql(sql: str) -> dict:
    """Executa uma consulta SELECT contra o schema `raw` do Postgres
    (dados fictícios da Olist -- pedidos, clientes, produtos, pagamentos,
    reviews, tickets de suporte) e retorna as linhas (até 200). Use
    nomes totalmente qualificados (ex: raw.orders). Bloqueado para
    qualquer coisa que não seja SELECT; conecta com uma credencial
    (rag_reader) que só tem permissão de leitura nesse schema -- mesmo
    pedir dados de app.* (contas de usuário) seria recusado pelo banco."""
    if not _SELECT_ONLY.match(sql):
        return {"error": "Só são permitidas consultas SELECT."}

    conn = get_reader_conn()
    try:
        with conn.cursor() as cur:
            # embrulha em subquery: além de limitar linhas, qualquer
            # tentativa de empilhar um segundo comando (`; DROP ...`)
            # quebra a sintaxe da subquery em vez de executar.
            cur.execute(f"SELECT * FROM ({sql.rstrip(';')}) AS _sub LIMIT {MAX_ROWS}")
            columns = [desc[0] for desc in cur.description]
            rows = [
                {col: _jsonable(v) for col, v in zip(columns, row)}
                for row in cur.fetchall()
            ]
        return {"columns": columns, "rows": rows, "truncated": len(rows) == MAX_ROWS}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
