"""
Roteador de canary release: fica na frente de duas instâncias idênticas
do app (stable e canary), decide pra qual mandar cada pergunta por um
peso (%), mede sucesso/latência de cada uma, e reverte o peso pra 0
sozinho se o canary começar a errar mais que o stable.

Serve a MESMA interface estática (web/static) -- pro usuário final não
muda nada visualmente; só o /api/ask é roteado.

Variáveis de ambiente:
  STABLE_URL        -- URL base do serviço estável (ex: https://olist-project.onrender.com)
  CANARY_URL        -- URL base do serviço canário (ex: https://olist-project-canary.onrender.com)
  CANARY_WEIGHT     -- peso inicial do canário, 0-100 (default: 5)
  SITE_PASSWORD     -- mesma senha compartilhada do app principal (ver web/auth.py)

Rodar com:
    ./.venv/bin/uvicorn router.app:app --reload --port 8020
"""

import os
import random
import time
from collections import deque
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.auth import BasicAuthMiddleware

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "static")

STABLE_URL = os.environ.get("STABLE_URL", "").rstrip("/")
CANARY_URL = os.environ.get("CANARY_URL", "").rstrip("/")

# Quantas amostras de canário esperar antes de confiar na taxa de erro
# dele (poucas amostras = ruído, não sinal) -- mesmo raciocínio do
# min_row_count dos gates de dados.
MIN_SAMPLES_FOR_ROLLBACK = 10
# Rollback automático se o canário errar mais que isso ACIMA da taxa de
# erro do stable (não em termos absolutos -- compara contra a baseline
# viva, igual o "AUC >= baseline * 0.99" das aulas).
ERROR_RATE_MARGIN = 0.15
WINDOW_SIZE = 50
PROXY_TIMEOUT_S = 90.0

_http: httpx.AsyncClient | None = None


class _Metrics:
    """Janela deslizante de resultados por backend -- em memória, por
    processo (suficiente pra um serviço de 1 instância; não é um store
    distribuído)."""

    def __init__(self) -> None:
        self.outcomes: deque[bool] = deque(maxlen=WINDOW_SIZE)
        self.latencies_ms: deque[float] = deque(maxlen=WINDOW_SIZE)

    def record(self, ok: bool, latency_ms: float) -> None:
        self.outcomes.append(ok)
        self.latencies_ms.append(latency_ms)

    @property
    def count(self) -> int:
        return len(self.outcomes)

    @property
    def error_rate(self) -> float | None:
        if not self.outcomes:
            return None
        return 1 - (sum(self.outcomes) / len(self.outcomes))

    @property
    def avg_latency_ms(self) -> float | None:
        if not self.latencies_ms:
            return None
        return sum(self.latencies_ms) / len(self.latencies_ms)

    def as_dict(self) -> dict:
        return {
            "samples": self.count,
            "error_rate": round(self.error_rate, 3) if self.error_rate is not None else None,
            "avg_latency_ms": round(self.avg_latency_ms, 1) if self.avg_latency_ms is not None else None,
        }


class _State:
    def __init__(self) -> None:
        self.weight = float(os.environ.get("CANARY_WEIGHT", "5"))
        self.stable = _Metrics()
        self.canary = _Metrics()
        self.last_rollback: dict | None = None


state = _State()


def _maybe_auto_rollback() -> None:
    """Chamado depois de cada resposta do canário. Reverte o peso pra 0
    sozinho se a taxa de erro do canário estiver claramente pior que a do
    stable -- a parte "safety net" do canary release."""
    if state.weight == 0:
        return
    if state.canary.count < MIN_SAMPLES_FOR_ROLLBACK:
        return
    canary_err = state.canary.error_rate or 0.0
    stable_err = state.stable.error_rate or 0.0
    if canary_err - stable_err > ERROR_RATE_MARGIN:
        state.last_rollback = {
            "at": time.time(),
            "reason": f"canary error_rate={canary_err:.2f} vs stable error_rate={stable_err:.2f} "
            f"(margem permitida: {ERROR_RATE_MARGIN})",
            "weight_before": state.weight,
        }
        state.weight = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http
    _http = httpx.AsyncClient(timeout=PROXY_TIMEOUT_S)
    yield
    await _http.aclose()


app = FastAPI(title="Olist RAG -- canary router", lifespan=lifespan)
app.add_middleware(BasicAuthMiddleware)


class AskIn(BaseModel):
    question: str


class WeightIn(BaseModel):
    weight: float


@app.post("/api/ask")
async def api_ask(payload: AskIn):
    use_canary = CANARY_URL and random.random() * 100 < state.weight
    target = CANARY_URL if use_canary else STABLE_URL
    metrics = state.canary if use_canary else state.stable

    if not target:
        return JSONResponse({"error": f"{'CANARY_URL' if use_canary else 'STABLE_URL'} não configurada."}, status_code=503)

    start = time.perf_counter()
    try:
        resp = await _http.post(f"{target}/api/ask", json=payload.model_dump())
        ok = resp.status_code == 200
        body = resp.json() if ok else {"error": f"backend respondeu {resp.status_code}"}
    except httpx.HTTPError as e:
        ok = False
        body = {"error": f"falha ao contatar backend: {e}"}
    latency_ms = (time.perf_counter() - start) * 1000

    metrics.record(ok, latency_ms)
    if use_canary:
        _maybe_auto_rollback()

    body["_routed_to"] = "canary" if use_canary else "stable"
    return JSONResponse(body, status_code=200 if ok else 502)


@app.get("/admin/status")
async def admin_status():
    return {
        "weight_percent": state.weight,
        "stable": {"url": STABLE_URL, **state.stable.as_dict()},
        "canary": {"url": CANARY_URL, **state.canary.as_dict()},
        "last_rollback": state.last_rollback,
    }


@app.post("/admin/weight")
async def admin_set_weight(payload: WeightIn):
    if not 0 <= payload.weight <= 100:
        return JSONResponse({"error": "weight deve estar entre 0 e 100"}, status_code=400)
    state.weight = payload.weight
    return {"weight_percent": state.weight}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
