# Passo 2: chat web com LangChain sobre os dados do Supabase

## Objetivo

Uma aplicação web onde o usuário faz qualquer pergunta em linguagem
natural sobre os dados da Olist (carregados no Supabase, ver
[01-ingestao.md](01-ingestao.md)) e recebe uma resposta em texto, com
tabela e gráfico quando fizer sentido -- um chat focado só nesse dataset.

## Arquitetura (portada do projeto irmão)

Esta não é a primeira vez que este dataset ganha um RAG: o projeto
[`olist-rag-langchain-mcp`](../../olist-rag-langchain-mcp) já implementava
esse padrão -- LangChain + **MCP** (Model Context Protocol) como ponte
entre o agente e o banco -- apontando para um Postgres local/Neon. Todo
esse código foi migrado pra cá, trocando o banco pelo Supabase, com o
código-fonte removido do projeto irmão (ver o README dele).

```
pergunta em português
        │
        ▼
agente LangChain (rag/agent.py)
  create_agent(ChatAnthropic, tools) -- decide sozinho quando chamar
  cada ferramenta, num loop (LangGraph por baixo)
        │
        ▼  (via stdio, langchain-mcp-adapters)
servidor MCP (mcp_server/server.py)
  ┌─────────────────┬──────────────────────┬────────────────────────┐
  │ list_tables()    │ search_context(q, k)  │ run_sql(sql)            │
  │ índice do schema │ embeddings + cosseno  │ SELECT no schema `raw`, │
  │ sem embeddings   │ sobre a camada de     │ credencial rag_reader   │
  │                  │ contexto; loga em     │ (só leitura, só raw)    │
  │                  │ app.rag_query_log     │                         │
  └─────────────────┴──────────────────────┴────────────────────────┘
        │                         │                        │
        ▼                         ▼                        ▼
context/semantic_layer.yaml   app.rag_query_log         raw.* (Supabase)
        │
        ▼
rag/agent.py separa o texto da resposta de um bloco ```viz (se houver) --
o bloco só referencia NOMES DE COLUNA, nunca valores; o agente então
busca o resultado de verdade do run_sql e monta a tabela e a figura
Plotly a partir dos dados reais (nunca do que o modelo "digitou")
        │
        ▼
web/main.py (POST /api/ask) -> web/static/ (chat + Plotly + tabela/CSV)
```

### Por que MCP em vez do agente falar direto com o banco

Um agente LLM com acesso direto ao banco tem todo o poder da conexão que
abriu. O servidor MCP expõe só três ferramentas, e `run_sql` roda com uma
credencial restrita (`rag_reader`) que só enxerga `SELECT` no schema
`raw` -- defesa em profundidade, não depende só da validação de texto no
código.

## Segurança: role `rag_reader` no Supabase

Criada rodando `sql/rag_reader_role.sql` no SQL Editor do Supabase -- uma
role com `SELECT` só no schema `raw`, nada em `public`/`auth`/`storage`/
`app` (o schema `app.rag_query_log`, de observabilidade, pertence ao
dono do banco, não à role do agente).

## Camada de contexto (semantic layer)

`context/semantic_layer.yaml` descreve cada tabela do schema `raw`
(descrição, colunas, sinônimos em português) e métricas de negócio
(ticket médio, taxa de atraso, nota média, etc.) -- é o texto que vira
embeddings em `search_context`.

## Gráfico e tabela: como funciona de verdade

`run_sql` devolve dados estruturados (`{columns, rows}`), não só texto.
Em vez de pedir pro modelo reescrever os números num JSON (caro em
tokens e arriscado -- LLM pode transcrever um valor errado), o contrato é:

1. O agente responde em texto curto (1-3 frases) e, quando o resultado
   tiver mais de uma linha comparável, acrescenta um bloco ` ```viz `
   referenciando só os **nomes das colunas** a usar, ex:
   `{"type": "bar", "x": "order_status", "y": "total", "title": "..."}`.
2. `rag/agent.py` (`_build_plotly_chart`) pega o resultado **real** do
   último `run_sql` e monta a figura Plotly (`{data, layout}`) buscando
   os valores pelas colunas indicadas -- o número que aparece no gráfico
   é sempre o que veio do Postgres.
3. A mesma função também monta a `table` (colunas + linhas) sempre que o
   resultado tiver mais de uma célula, mesmo sem gráfico.
4. O front-end (`web/static/app.js`) renderiza o gráfico com
   **Plotly.js** (via CDN) e a tabela com um `<table>` + botão de
   exportar CSV (gerado no navegador, sem round-trip ao servidor).

Tipos de gráfico suportados: `bar` (comparação entre categorias), `line`
(série temporal -- só quando o eixo x é uma sequência de datas/meses) e
`scatter` (relação entre duas colunas numéricas). Sem pizza -- bar
resolve melhor o "parte-do-todo" e evita o problema de cor de um gráfico
com muitas fatias.

## Interface

Chat de página única (sem abas): bolhas de mensagem, indicador de
"digitando", perguntas de exemplo clicáveis, e um botão "Nova conversa".
Cada resposta pode trazer texto + gráfico Plotly + tabela com exportação
CSV, dependendo do que a pergunta pedir.

## Ferramentas / dependências

```
pyyaml                  # carregar context/semantic_layer.yaml
python-dotenv           # carregar .env
psycopg2-binary         # Postgres (ingestão + MCP)

sentence-transformers   # embeddings da camada de contexto (retrieval)

mcp                     # servidor + cliente MCP
langchain
langchain-core
langchain-anthropic     # ChatAnthropic -- precisa de ANTHROPIC_API_KEY
langchain-mcp-adapters  # ponte entre o agente LangChain e o servidor MCP

fastapi
uvicorn[standard]       # serve a API + o site estático
```

No front-end (sem instalar nada via pip, via CDN): **Plotly.js** (gráfico)
e a fonte **Inter** (Google Fonts).

Variáveis de ambiente (além de `OLIST_PG_DSN`, da ingestão):

```
ANTHROPIC_API_KEY=sk-ant-...
OLIST_PG_READER_DSN=<connection string do Supabase com o usuário rag_reader>
SITE_PASSWORD=<senha escolhida -- protege o site em produção; vazio = sem proteção>
```

## Arquivos

| Caminho | O que é |
|---|---|
| `context/semantic_layer.yaml` / `.py` | Camada de contexto: tabelas, colunas, sinônimos, métricas |
| `mcp_server/db.py` | Conexão dona do banco + conexão `rag_reader` |
| `mcp_server/retrieval.py` | Embeddings (sentence-transformers) + similaridade de cosseno |
| `mcp_server/server.py` | Servidor MCP: `search_context`, `list_tables`, `run_sql` |
| `rag/agent.py` | Agente LangChain + extração do bloco `viz` + montagem de tabela/gráfico |
| `sql/rag_reader_role.sql` | Role restrita a `SELECT` no schema `raw` |
| `sql/rag_log_schema.sql` / `rag_log_notify.sql` | Log de retrieval (`app.rag_query_log`) para auditoria via SQL |
| `web/main.py` | API: `POST /api/ask` |
| `web/auth.py` | Senha compartilhada (HTTP Basic Auth) em produção |
| `web/static/` | Chat (HTML/CSS/JS puro + Plotly via CDN) |
| `render.yaml` | Blueprint de deploy (Render) -- ver [03-deploy.md](03-deploy.md) |

## Próximo passo

Deploy em produção -- ver [03-deploy.md](03-deploy.md).
