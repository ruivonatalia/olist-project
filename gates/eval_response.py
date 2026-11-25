"""
Gate 3 -- Response (model) quality.

Roda o agente LangChain de verdade (rag/agent.py -- chama a API da
Anthropic) pra cada pergunta do eval set, e compara o número que ele
devolveu na resposta em português contra o valor real (rodando o SQL de
referência da métrica direto no Postgres, com tolerância). Perguntas
não-escalares (ex: "tickets por status") só verificam que o agente
respondeu sem erro -- smoke test de ponta a ponta.

Custo: cada pergunta chama o Claude de verdade (via create_agent) em pelo
menos 2 rodadas (search_context + run_sql + resposta final) -- roda sob
demanda, não em todo commit.

Rodar com:
    ./.venv/bin/python -m gates.eval_response
"""

import asyncio
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(REPO_ROOT, ".env"))

from mcp_server.db import get_reader_conn
from rag.agent import aclose_agent, ask

TOLERANCE = 0.05  # 5% de diferença aceitável entre o número da resposta e o valor real

_NUMBER_RE = re.compile(r"-?\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|-?\d+(?:\.\d+)?")


def log(status: str, check: str, **detail) -> None:
    print(json.dumps({"status": status, "check": check, **detail}, ensure_ascii=False, default=str))


def _ground_truth(sql: str):
    conn = get_reader_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _parse_numbers_pt(text: str) -> list[float]:
    """Extrai números de um texto em português, aceitando tanto '1234.56'
    quanto '1.234,56' (milhar com ponto, decimal com vírgula)."""
    out = []
    for raw in _NUMBER_RE.findall(text):
        cleaned = raw.replace(" ", "")
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            out.append(float(cleaned))
        except ValueError:
            continue
    return out


def _closest_within_tolerance(numbers: list[float], expected: float, tol: float) -> float | None:
    if expected == 0:
        return next((n for n in numbers if abs(n) < 1e-9), None)
    for n in numbers:
        if abs(n - expected) / abs(expected) <= tol:
            return n
    return None


async def main_async() -> int:
    with open(os.path.join(os.path.dirname(__file__), "eval_set.json"), encoding="utf-8") as f:
        eval_set = json.load(f)

    failures = []
    skipped = []

    try:
        for item in eval_set:
            expected = _ground_truth(item["expected_sql"])

            if item["scalar"] and expected is None:
                log("SKIP", "response_quality", id=item["id"], reason="ground truth é NULL (ver Gate 1 -- tabela vazia)")
                skipped.append(item["id"])
                continue

            result = await ask(item["question"])
            answer = result["answer"]

            if not item["scalar"]:
                ok = bool(answer) and bool(result.get("table") or result.get("tool_calls"))
                log(
                    "PASS" if ok else "FAIL",
                    "response_quality",
                    id=item["id"],
                    question=item["question"],
                    answer=answer,
                )
                if not ok:
                    failures.append(f"{item['id']}: resposta vazia ou sem dado de suporte")
                continue

            expected_f = float(expected)
            numbers = _parse_numbers_pt(answer)
            match = _closest_within_tolerance(numbers, expected_f, TOLERANCE)
            ok = match is not None
            log(
                "PASS" if ok else "FAIL",
                "response_quality",
                id=item["id"],
                question=item["question"],
                expected=round(expected_f, 2),
                answer=answer,
                numbers_found=numbers,
            )
            if not ok:
                failures.append(f"{item['id']}: esperado ~{expected_f:.2f}, resposta não bateu dentro de {TOLERANCE:.0%} ({answer!r})")
    finally:
        await aclose_agent()

    print()
    if skipped:
        print(f"{len(skipped)} pergunta(s) pulada(s) (ground truth indisponível): {', '.join(skipped)}")
    if failures:
        print(f"GATE 3 (response quality): FALHOU -- {len(failures)} problema(s):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("GATE 3 (response quality): PASSOU.")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
