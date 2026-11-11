"""
Interface web deste projeto: POST /api/ask chama o agente LangChain
(rag/agent.py), que por sua vez fala com o servidor MCP (busca de
contexto + SQL), e devolve a resposta final (texto + gráfico opcional).

Rodar com:
    ./.venv/bin/uvicorn web.main:app --reload --port 8010

Abre em http://localhost:8010 -- a própria API serve o site (web/static/).
"""

import contextlib
import json
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rag.agent import _get_agent, aclose_agent, ask
from web.auth import BasicAuthMiddleware

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
OWNER_DSN = os.environ.get("OLIST_PG_DSN", "dbname=olist host=/tmp").strip()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Monta o agente (e abre o processo do servidor MCP) uma vez, no
    # startup -- sem isso, quem paga o custo de carregar o modelo de
    # embeddings seria a primeira pergunta de um usuário de verdade.
    await _get_agent()
    yield
    await aclose_agent()


app = FastAPI(title="Olist RAG -- chat", lifespan=lifespan)
app.add_middleware(BasicAuthMiddleware)


class AskIn(BaseModel):
    question: str


def _tag_request_log(question: str, tool_calls: list, since: datetime) -> None:
    """search_context loga o que o MODELO mandou pra ele (às vezes
    reformulado) em app.rag_query_log -- só a camada web vê o texto
    literal que o usuário digitou e a trilha completa de ferramentas
    (incluindo o SQL real do run_sql), então é aqui que os dois são
    gravados, marcando as linhas criadas durante esta chamada (que ainda
    não têm original_question). Falha de log nunca deve derrubar a
    resposta pro usuário -- por isso o try/except."""
    try:
        conn = psycopg2.connect(OWNER_DSN)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app.rag_query_log SET original_question = %s, tool_trace = %s "
                "WHERE created_at >= %s AND original_question IS NULL",
                (question, json.dumps(tool_calls, ensure_ascii=False), since),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass


@app.post("/api/ask")
async def api_ask(payload: AskIn):
    """Chama o agente LangChain de ponta a ponta (search_context +
    run_sql via MCP) e devolve a resposta final."""
    since = datetime.now(timezone.utc)
    result = await ask(payload.question)
    _tag_request_log(payload.question, result["tool_calls"], since)
    return result


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
