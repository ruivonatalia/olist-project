"""
Agente LangChain que consome o servidor MCP (mcp_server/server.py) como
ferramentas -- a peça "RAG com LangChain usando MCP" do projeto.

O agente recebe uma pergunta em português, decide sozinho quando chamar
search_context (retrieval na camada de contexto -- embeddings +
similaridade) e run_sql (executar a consulta descoberta no schema
`raw`), e devolve uma resposta. Cada chamada a search_context já fica
registrada em app.rag_query_log pelo próprio servidor MCP (pergunta,
embedding, chunks recuperados, scores).

O agente nunca abre uma conexão com o Postgres diretamente -- só fala
com o processo do servidor MCP via stdio, que é quem de fato toca no
banco (com a credencial restrita rag_reader para run_sql).

Rodar com:
    ./.venv/bin/python -m rag.agent "Qual o ticket médio dos pedidos?"
"""

import asyncio
import contextlib
import json
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYSTEM_PROMPT = (
    "Você responde perguntas em português sobre o banco de dados fictício "
    "da Olist (e-commerce brasileiro). Sempre use a ferramenta "
    "search_context primeiro para descobrir quais tabelas/colunas/"
    "métricas existem -- nunca invente nomes de coluna. Depois, use "
    "run_sql para executar uma consulta SELECT contra o schema `raw` "
    "e responda com base no resultado, em 1-3 frases, em português.\n\n"
    "Se o resultado do run_sql tiver 2 ou mais linhas comparáveis (ex: "
    "valores por categoria, por mês, por status, ou duas colunas "
    "numéricas pra correlacionar), acrescente depois do texto um bloco "
    "cercado por ```viz e ``` com um JSON descrevendo o gráfico --"
    "usando os NOMES EXATOS das colunas que o run_sql devolveu, nunca os "
    "valores (quem desenha o gráfico busca os valores de verdade pelos "
    "nomes de coluna):\n"
    '  bar ou line: {"type": "bar"|"line", "x": "<coluna categórica ou '
    'temporal>", "y": "<coluna numérica>", "title": "..."}\n'
    '  scatter: {"type": "scatter", "x": "<coluna numérica>", '
    '"y": "<coluna numérica>", "title": "..."}\n'
    "Regra pra escolher o tipo: \"line\" só quando x for uma sequência "
    "temporal (datas/meses) -- nesse caso sempre ORDENE a consulta SQL "
    "por essa coluna; \"scatter\" só quando x e y forem ambas numéricas "
    "contínuas (ex: preço vs frete); senão, \"bar\". Nunca gráfico de "
    "pizza. Não inclua o bloco quando a resposta for um único número "
    "(ex: uma média geral). No máximo ~15 categorias em bar -- se a "
    "consulta puder devolver mais, agrupe as menores em 'Outros' no "
    "próprio SQL ou use LIMIT com ORDER BY."
)

_VIZ_BLOCK = re.compile(r"```viz\s*(\{.*?\})\s*```", re.DOTALL)

# Paleta categórica validada (skill de dataviz) -- série única em todo
# gráfico deste app, então sempre o slot 1 (azul): com 1 série não existe
# par adjacente pra falhar o teste de daltonismo.
_SERIES_COLOR = "#2a78d6"


def _extract_text(message) -> str:
    """O content de uma AIMessage pode ser string ou uma lista de blocos
    (texto, thinking) -- normaliza pra texto puro."""
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block["text"])
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def _extract_viz_spec(answer: str) -> tuple[str, dict | None]:
    """Separa um bloco ```viz {...}``` do texto da resposta, se existir.
    Retorna (texto sem o bloco, spec do gráfico ou None)."""
    match = _VIZ_BLOCK.search(answer)
    if not match:
        return answer.strip(), None
    text = (answer[: match.start()] + answer[match.end() :]).strip()
    try:
        spec = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return text, None
    if spec.get("type") not in ("bar", "line", "scatter") or not spec.get("x") or not spec.get("y"):
        return text, None
    return text, spec


def _last_run_sql_result(messages) -> dict | None:
    """Acha a última chamada a run_sql e devolve {columns, rows, truncated}
    já parseado -- é o dado de verdade (vindo do Postgres), nunca o que o
    modelo pode ter re-digitado na resposta."""
    for m in reversed(messages):
        if getattr(m, "type", None) == "tool" and getattr(m, "name", None) == "run_sql":
            try:
                parsed = json.loads(_extract_text(m))
            except (json.JSONDecodeError, TypeError):
                return None
            if "error" in parsed:
                return None
            return parsed
    return None


def _build_table(sql_result: dict | None) -> dict | None:
    """Só vale a pena mostrar como tabela quando há mais de um valor --
    uma única célula (ex: "ticket médio") já está na frase da resposta."""
    if not sql_result:
        return None
    if len(sql_result["rows"]) <= 1 and len(sql_result["columns"]) <= 1:
        return None
    return sql_result


def _build_plotly_chart(spec: dict | None, sql_result: dict | None) -> dict | None:
    """Monta a figura Plotly (formato {data, layout}) a partir dos dados
    reais do run_sql (não do que o modelo escreveu) + do spec (tipo e
    quais colunas usar)."""
    if not spec or not sql_result:
        return None
    rows = sql_result["rows"]
    columns = set(sql_result["columns"])
    x_col, y_col = spec["x"], spec["y"]
    if x_col not in columns or y_col not in columns or not rows:
        return None

    x_vals = [r[x_col] for r in rows]
    y_vals = [r[y_col] for r in rows]
    title = spec.get("title") or f"{y_col} por {x_col}"

    if spec["type"] == "scatter":
        trace = {"type": "scatter", "mode": "markers", "x": x_vals, "y": y_vals,
                  "marker": {"color": _SERIES_COLOR, "size": 8}}
    elif spec["type"] == "line":
        trace = {"type": "scatter", "mode": "lines+markers", "x": x_vals, "y": y_vals,
                  "line": {"color": _SERIES_COLOR, "width": 2},
                  "marker": {"color": _SERIES_COLOR, "size": 6}}
    else:  # bar
        trace = {"type": "bar", "x": x_vals, "y": y_vals, "marker": {"color": _SERIES_COLOR}}

    return {
        "data": [trace],
        "layout": {
            "title": {"text": title, "font": {"size": 14, "color": "#1c2228"}},
            "xaxis": {"title": x_col, "gridcolor": "#eceee9", "zeroline": False},
            "yaxis": {"title": y_col, "gridcolor": "#eceee9", "zeroline": False},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"family": "Inter, -apple-system, sans-serif", "color": "#68706a", "size": 12},
            "margin": {"t": 44, "r": 20, "b": 48, "l": 56},
            "bargap": 0.35,
        },
    }


# `MultiServerMCPClient.get_tools()` sem sessão explícita abre um
# subprocesso do servidor MCP NOVO a cada chamada de ferramenta (ver
# docstring da lib: "a new session will be created for each tool call")
# -- ruim aqui porque o servidor reimporta torch/sentence-transformers e
# recarrega o modelo de embeddings toda vez. Em vez disso, abrimos UMA
# sessão (um processo) e mantemos viva pela vida do processo web inteiro,
# reaproveitada por todas as perguntas -- é só isso que _get_agent() e
# aclose_agent() fazem.
_agent_lock = asyncio.Lock()
_cached_agent = None
_exit_stack: contextlib.AsyncExitStack | None = None


async def _get_agent():
    global _cached_agent, _exit_stack
    if _cached_agent is not None:
        return _cached_agent
    async with _agent_lock:
        if _cached_agent is not None:  # outra requisição pode ter montado enquanto esperava o lock
            return _cached_agent
        client = MultiServerMCPClient({
            "olist": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", "mcp_server.server"],
                "cwd": REPO_ROOT,
            }
        })
        stack = contextlib.AsyncExitStack()
        session = await stack.enter_async_context(client.session("olist"))
        tools = await load_mcp_tools(session)
        model = ChatAnthropic(model="claude-sonnet-5")
        _cached_agent = create_agent(model, tools, system_prompt=SYSTEM_PROMPT)
        _exit_stack = stack
        return _cached_agent


async def aclose_agent():
    """Encerra o processo do servidor MCP -- chamar no shutdown da app."""
    global _cached_agent, _exit_stack
    if _exit_stack is not None:
        await _exit_stack.aclose()
    _cached_agent = None
    _exit_stack = None


async def ask(question: str) -> dict:
    agent = await _get_agent()
    result = await agent.ainvoke({"messages": [{"role": "user", "content": question}]})
    raw_answer = _extract_text(result["messages"][-1])
    answer, viz_spec = _extract_viz_spec(raw_answer)

    sql_result = _last_run_sql_result(result["messages"])
    table = _build_table(sql_result)
    chart = _build_plotly_chart(viz_spec, sql_result)

    tool_calls = [
        {"tool": m.name, "result_preview": str(m.content)[:200]}
        for m in result["messages"]
        if getattr(m, "type", None) == "tool"
    ]
    return {"answer": answer, "chart": chart, "table": table, "tool_calls": tool_calls}


async def main():
    question = " ".join(sys.argv[1:]) or "Qual o ticket médio dos pedidos?"
    print(f"PERGUNTA: {question}\n")
    result = await ask(question)
    for call in result["tool_calls"]:
        print(f"[ferramenta] {call['tool']} -> {call['result_preview']}...\n")
    print(f"RESPOSTA:\n{result['answer']}")
    if result["chart"]:
        print(f"\n[gráfico] {result['chart']['data'][0]['type']}")
    if result["table"]:
        print(f"[tabela] {len(result['table']['rows'])} linhas, colunas: {result['table']['columns']}")
    await aclose_agent()


if __name__ == "__main__":
    asyncio.run(main())
