"""
Duas conexões com o mesmo Postgres, com propósitos diferentes:
  - get_owner_conn(): acesso completo (dono do banco) -- usado só pelo
    próprio código do servidor pra gravar o log de retrieval
    (app.rag_query_log). Nunca executa SQL vindo do agente/LLM.
  - get_reader_conn(): role `rag_reader`, só SELECT no schema `raw` --
    é a única conexão que executa o SQL que o agente LangChain manda via
    a tool `run_sql`. Ver sql/rag_reader_role.sql.
"""

import os

import psycopg2

def _env_dsn(key: str, default: str) -> str:
    # .strip() porque é fácil colar a connection string com uma quebra de
    # linha sobrando num campo de ambiente (Render, etc) -- sem isso, o
    # \n vira parte do nome do banco e psycopg2 falha com um erro
    # confuso ("database \"postgres\n\" does not exist").
    return os.environ.get(key, default).strip()


OWNER_DSN = _env_dsn("OLIST_PG_DSN", "dbname=olist host=/tmp")
READER_DSN = _env_dsn("OLIST_PG_READER_DSN", "dbname=olist host=/tmp user=rag_reader password=rag_reader_local_dev")


def get_owner_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(OWNER_DSN)


def get_reader_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(READER_DSN)
