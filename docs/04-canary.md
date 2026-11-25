# Passo 4: canary release

## O que é e pra que serve

Canary release é uma estratégia de deploy gradual: em vez de trocar 100%
do tráfego pra uma versão nova de uma vez (o que a aula de CI/CD chama de
"deploy sem gate gradual" -- um anti-padrão), uma fatia pequena das
requisições (ex.: 5%) vai pra versão nova enquanto o resto continua na
versão estável. Se a versão nova se comportar bem, a fatia cresce aos
poucos (5% → 25% → 100%); se piorar, ela volta pra 0% -- idealmente
sozinha, sem alguém precisar perceber o incidente primeiro.

O ganho sobre "testar local e depois trocar tudo": a versão nova é
validada contra **tráfego e dado reais**, mas o "blast radius" de uma
regressão fica limitado à fração de usuários que caiu no canário,
enquanto a métrica monitorada ainda não disparou o rollback.

## Como esta implementação funciona

```
usuário -> olist-project-router -> (peso%) -> olist-project          (stable, branch main)
                                 -> (peso%) -> olist-project-canary   (canary, branch canary)
```

`router/app.py` é um terceiro serviço, leve (sem embeddings nem LLM
aqui -- só proxy), que:

1. Serve a mesma interface (`web/static`) -- visualmente idêntico ao app
   original.
2. Em cada `POST /api/ask`, sorteia stable ou canary de acordo com o peso
   atual (`CANARY_WEIGHT`, começa em 5%) e encaminha a pergunta pra lá.
3. Registra sucesso/erro e latência de cada chamada, numa janela das
   últimas 50 por backend.
4. **Rollback automático**: depois de pelo menos 10 amostras do canário,
   se a taxa de erro dele estiver mais de 15 pontos percentuais acima da
   do stable, o peso volta pra 0% sozinho -- e o motivo fica registrado.

Isso foi testado localmente com dois backends falsos (um sempre
respondendo erro) antes de subir: com peso 100%, o rollback disparou
exatamente na 10ª requisição e o tráfego voltou pro "stable" na
seguinte -- é esse mecanismo, sem mudança nenhuma, que vai rodar contra
os serviços de verdade.

## Setup no Render (manual -- não dá pra fazer isso por API aqui)

Depois que o PR deste branch for mergeado no `main`:

1. No painel do Render, vá no Blueprint do `olist-project` e sincronize
   (**Manual Sync**, ou aguarde o sync automático) -- o `render.yaml`
   atualizado cria dois serviços novos: `olist-project-canary` e
   `olist-project-router`. O serviço `olist-project` original não muda.

2. **`olist-project-canary`** -- precisa de 2 ajustes manuais que o
   blueprint não faz sozinho:
   - **Settings → Build & Deploy → Branch**: trocar de `main` pra
     `canary`. É nessa branch que você vai experimentar mudanças sem
     afetar o stable.
   - **Environment**: preencher `ANTHROPIC_API_KEY`, `OLIST_PG_DSN`,
     `OLIST_PG_READER_DSN` -- os mesmos valores já usados no
     `olist-project` (ver [03-deploy.md](03-deploy.md)). `SITE_PASSWORD`
     é opcional, igual ao original.

3. **`olist-project-router`**:
   - **Environment**: `STABLE_URL` = URL do `olist-project`
     (`https://olist-project.onrender.com`); `CANARY_URL` = URL do
     `olist-project-canary` (gerada no passo 2); `SITE_PASSWORD` = a
     mesma senha dos outros dois, se estiver usando uma.

4. Espere os 3 serviços ficarem "Live". O `olist-project-router` é o novo
   ponto de entrada opcional -- o `olist-project.onrender.com` original
   continua no ar, do jeito que sempre esteve, sem nenhuma dependência do
   router.

## Usando na prática

Abra a URL do `olist-project-router` em vez da do app original -- a
interface é a mesma. Pra realmente ver o canary em ação:

1. Faça uma mudança observável só na branch `canary` (ex.: trocar o
   modelo em `rag/agent.py`, ou alterar o `SYSTEM_PROMPT` de um jeito que
   piore a resposta de propósito) e dê push -- o Render reconstrói
   automaticamente só o `olist-project-canary`.
2. Acompanhe `GET /admin/status` no router -- mostra peso atual e as
   métricas (amostras, error_rate, latência média) de cada backend.
3. Ajuste o peso manualmente enquanto ganha confiança:
   ```bash
   curl -X POST https://<router>/admin/weight \
     -H "Content-Type: application/json" -d '{"weight": 25}'
   ```
4. Se a mudança que você fez for ruim o bastante, o rollback automático
   deve disparar sozinho depois de ~10 perguntas roteadas pro canário --
   `last_rollback` em `/admin/status` mostra quando e por quê.

## Custo

`olist-project-canary` é uma segunda instância completa (plano
`standard`, mesmo custo do serviço original). `olist-project-router` é
leve e está no plano `starter`. Rode o canário só enquanto estiver
testando uma mudança de verdade -- não precisa ficar ligado o tempo
todo.
