"""
Agentes sintéticos: simulam perguntas de usuários reais contra o chat do
Olist Project, uma vez por rodada (pensado pra rodar de hora em hora via
CronJob do Kubernetes). Cada "agente" é uma persona com uma pergunta
gerada na hora pelo Claude (não fixa/template) -- gera tráfego realista e
variado, alimenta a janela de métricas do canary router quando aponta pra
ele, e grava um log em Postgres pra análise posterior.

Variáveis de ambiente:
  ANTHROPIC_API_KEY  -- obrigatória
  OLIST_PG_DSN       -- connection string do Postgres (dona do banco -- precisa escrever em app.*)
  TARGET_URL         -- base URL do app a testar (o router, idealmente, ou o stable direto)
  SITE_PASSWORD      -- opcional, se o app estiver protegido por HTTP Basic Auth
  MODEL              -- opcional, default claude-haiku-4-5-20251001 (barato, suficiente pra gerar uma pergunta curta)

Rodar com:
    python run_agents.py
"""

import json
import os
import sys
import time

import httpx
import psycopg2
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OLIST_PG_DSN = os.environ["OLIST_PG_DSN"].strip()
TARGET_URL = os.environ["TARGET_URL"].rstrip("/")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD")
MODEL = os.environ.get("MODEL", "claude-haiku-4-5-20251001")

PERSONAS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "personas.json")

_QUESTION_PROMPT = (
    "Você é {description}. Gere UMA pergunta curta e natural em português "
    "que essa pessoa faria no chat de um e-commerce (sobre pedidos, "
    "pagamentos, entregas, vendedores, produtos, avaliações ou tickets de "
    "suporte). Responda APENAS com a pergunta, sem aspas e sem nenhuma "
    "explicação."
)


def log(**fields) -> None:
    print(json.dumps(fields, ensure_ascii=False, default=str))


def generate_question(client: Anthropic, description: str) -> str:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": _QUESTION_PROMPT.format(description=description)}],
    )
    return msg.content[0].text.strip().strip('"')


def ask_app(http: httpx.Client, question: str) -> tuple[bool, dict, float, str | None]:
    auth = ("x", SITE_PASSWORD) if SITE_PASSWORD else None
    start = time.perf_counter()
    try:
        resp = http.post(f"{TARGET_URL}/api/ask", json={"question": question}, auth=auth, timeout=90.0)
        latency_ms = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            return True, resp.json(), latency_ms, None
        return False, {}, latency_ms, f"HTTP {resp.status_code}: {resp.text[:300]}"
    except httpx.HTTPError as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return False, {}, latency_ms, str(e)


def save_log(conn, persona: str, question: str, success: bool, body: dict, latency_ms: float, error: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.synthetic_traffic_log
                (persona, question, answer, routed_to, success, latency_ms, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                persona,
                question,
                body.get("answer"),
                body.get("_routed_to"),
                success,
                latency_ms,
                error,
            ),
        )
    conn.commit()


def main() -> int:
    with open(PERSONAS_PATH, encoding="utf-8") as f:
        personas = json.load(f)

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    conn = psycopg2.connect(OLIST_PG_DSN)
    successes = 0

    try:
        with httpx.Client() as http:
            for persona in personas:
                name = persona["name"]
                try:
                    question = generate_question(client, persona["description"])
                    ok, body, latency_ms, error = ask_app(http, question)
                    save_log(conn, name, question, ok, body, latency_ms, error)
                    successes += int(ok)
                    log(
                        status="PASS" if ok else "FAIL",
                        persona=name,
                        question=question,
                        routed_to=body.get("_routed_to"),
                        latency_ms=round(latency_ms, 1),
                        error=error,
                    )
                except Exception as e:
                    log(status="ERROR", persona=name, error=str(e))
    finally:
        conn.close()

    print()
    print(f"{successes}/{len(personas)} agentes completaram com sucesso.")
    return 0 if successes > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
