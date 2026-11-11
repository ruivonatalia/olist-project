# Passo 3: deploy público (Render)

O Supabase já é o banco em produção (não existe "migração" pra fazer --
é o mesmo banco usado em desenvolvimento, ver
[01-ingestao.md](01-ingestao.md)). Só falta publicar a aplicação web.

## 1. Repositório no GitHub

```bash
git init
git add .
git commit -m "Olist Project: ingestão + RAG + chat web"
gh repo create olist-project --public --source=. --remote=origin --push
```

(sem `gh`, crie o repositório manualmente em github.com/new e rode
`git remote add origin <url> && git push -u origin main`.)

Confirme que `.env` **não** foi commitado (`git status` antes do commit,
ou `git show HEAD --stat` depois) -- ele está no `.gitignore`, mas vale
checar sempre que se mexe num repositório com segredo.

## 2. Criar conta no Render e conectar o repositório

1. Acesse [render.com](https://render.com) e crie uma conta (dá pra usar
   login do GitHub).
2. **New** → **Blueprint**.
3. Conecte o repositório `olist-project` que acabou de subir -- o Render
   detecta o `render.yaml` automaticamente (serviço web, build command,
   start command e as variáveis de ambiente que precisam ser
   preenchidas).

## 3. Preencher as variáveis de ambiente

No painel do Render (nunca no código -- `render.yaml` só declara os
*nomes*, marcados `sync: false`):

| Variável | Valor |
|---|---|
| `ANTHROPIC_API_KEY` | sua chave da Anthropic |
| `OLIST_PG_DSN` | connection string do Supabase (usuário `postgres`, a dona do banco) |
| `OLIST_PG_READER_DSN` | mesma connection string, trocando usuário/senha por `rag_reader` |
| `SITE_PASSWORD` | uma senha sua -- ver seção abaixo; deixe em branco para não proteger (aceitando o custo de acesso público) |

## 4. Deploy

Clique em **Apply** / **Deploy**. O Render builda (`pip install -r
requirements.txt`) e sobe (`uvicorn web.main:app --host 0.0.0.0 --port
$PORT`). Ao final, ele dá uma URL pública tipo
`https://olist-project.onrender.com`.

> **Plano free do Render:** `sentence-transformers` + `torch` consomem
> bastante memória pra carregar o modelo de embeddings na primeira
> requisição -- o plano free (512MB RAM) pode não ser suficiente ou
> ficar lento no "cold start" depois de um período sem uso. Se isso
> acontecer, o próximo passo seria um plano pago ou um modelo de
> embeddings mais leve.

## Acesso (senha compartilhada, opcional)

Sem cadastro/login de usuário -- uma única senha (`SITE_PASSWORD`)
protege a interface via HTTP Basic Auth (`web/auth.py`). Isso importa de
verdade: cada pergunta chama a API da Anthropic de verdade, cobrada na
sua chave -- sem essa trava, qualquer pessoa com o link pode gerar custo
sem limite. Sem `SITE_PASSWORD` definida, nada é bloqueado.

## Depois do deploy

- Teste perguntas de exemplo (ver [02-rag-langchain.md](02-rag-langchain.md)).
- Cada deploy novo (`git push`) na branch principal reconstrói
  automaticamente, porque o Render monitora o repositório.
