"""
Interface web deste projeto: POST /api/ask chama o agente LangChain
(rag/agent.py), que por sua vez fala com o servidor MCP (busca de
contexto + SQL), e devolve a resposta final (texto + gráfico opcional).

Rodar com:
    ./.venv/bin/uvicorn web.main:app --reload --port 8010

Abre em http://localhost:8010 -- a própria API serve o site (web/static/).
"""

import contextlib
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rag.agent import _get_agent, aclose_agent, ask
from web.auth import BasicAuthMiddleware

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


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


@app.post("/api/ask")
async def api_ask(payload: AskIn):
    """Chama o agente LangChain de ponta a ponta (search_context +
    run_sql via MCP) e devolve a resposta final."""
    return await ask(payload.question)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
