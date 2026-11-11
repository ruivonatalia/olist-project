"""
Interface web deste projeto: POST /api/ask chama o agente LangChain
(rag/agent.py), que por sua vez fala com o servidor MCP (busca de
contexto + SQL), e devolve a resposta final (texto + gráfico opcional).

Rodar com:
    ./.venv/bin/uvicorn web.main:app --reload --port 8010

Abre em http://localhost:8010 -- a própria API serve o site (web/static/).
"""

import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rag.agent import ask
from web.auth import BasicAuthMiddleware

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Olist RAG -- chat")
app.add_middleware(BasicAuthMiddleware)


class AskIn(BaseModel):
    question: str


@app.post("/api/ask")
async def api_ask(payload: AskIn):
    """Chama o agente LangChain de ponta a ponta (search_context +
    run_sql via MCP) e devolve a resposta final."""
    return await ask(payload.question)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
