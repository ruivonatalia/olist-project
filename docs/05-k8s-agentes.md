# Passo 5: agentes sintéticos via Kubernetes

## O que é e pra que serve

`agents/run_agents.py` simula perguntas de usuários reais contra o chat
do Olist Project: cada "agente" é uma persona (cliente, gestor de vendas,
suporte, analista de pagamentos) que gera uma pergunta nova via Claude a
cada rodada -- não é uma lista fixa de perguntas -- e manda pro
`/api/ask` do app de verdade. O resultado (pergunta, resposta, sucesso,
latência) é gravado em `app.synthetic_traffic_log` no Postgres.

Isso serve três propósitos: (1) gera tráfego real e contínuo pro app
(útil pra alimentar as métricas do canary router -- ver
[04-canary.md](04-canary.md)), (2) funciona como monitoramento contínuo
("continuous evaluation" das aulas do curso), e (3) vira dado real
consultável (não só log efêmero) pra estudar comportamento de retrieval
ao longo do tempo.

Esse é o primeiro componente do projeto rodando em **Docker +
Kubernetes** em vez de direto no Render -- escolha deliberada pra
praticar essas duas ferramentas, não porque o Render não daria conta
(daria, perfeitamente, com um Cron Job).

## Conceitos rápidos

- **Docker**: empacota o script + dependências numa *imagem*; um
  *container* é essa imagem rodando.
- **Kubernetes (K8s)**: o orquestrador que decide quando/onde rodar
  containers. Um **Pod** é a menor unidade (aqui, 1 container). Um
  **CronJob** é o recurso que diz "roda este container nesse horário, de
  novo e de novo" -- cada disparo cria um **Job**, que cria um **Pod**,
  que roda e termina (não fica de pé feito um servidor web).
- **Secret**: onde o K8s guarda valor sensível (API key, connection
  string) sem deixar em texto claro no manifesto.
- **Namespace**: uma "pasta" lógica pra agrupar recursos relacionados
  (aqui, `olist-agents`).

## Setup local (Docker Desktop)

Pré-requisito: Docker Desktop instalado, com **Settings → Kubernetes →
Enable Kubernetes** marcado e aplicado (`Apply & Restart`). Confirme com:

```bash
kubectl get nodes
# NAME                    STATUS   ROLES           AGE   VERSION
# desktop-control-plane   Ready    control-plane   ...   v1.36.1
```

### 1. Migration no Postgres (uma vez)

```bash
./.venv/bin/python -c "
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.environ['OLIST_PG_DSN'].strip())
with conn.cursor() as cur:
    cur.execute(open('sql/synthetic_traffic_schema.sql').read())
conn.commit()
"
```

### 2. Build da imagem

```bash
cd agents
docker build -t olist-agents:local .
```

Não precisa de registry -- o Kubernetes do Docker Desktop enxerga as
mesmas imagens que `docker images` lista, direto.

### 3. Namespace + Secret + CronJob

```bash
kubectl apply -f k8s/namespace.yaml

# NUNCA aplique k8s/secret.example.yaml com valores reais -- é só
# referência de formato. O secret de verdade é criado por comando, lendo
# do seu .env, sem nunca escrever os valores em disco:
set -a && source .env && set +a
kubectl create secret generic olist-agents-secrets \
  --namespace olist-agents \
  --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  --from-literal=OLIST_PG_DSN="$OLIST_PG_DSN" \
  --from-literal=TARGET_URL="https://olist-project.onrender.com" \
  --from-literal=SITE_PASSWORD="${SITE_PASSWORD:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f k8s/cronjob.yaml
```

> Troque `TARGET_URL` pra URL do `olist-project-router` assim que ele
> estiver no ar (ver 04-canary.md) -- é aí que o tráfego sintético passa
> a contar pras métricas do canary.

### 4. Testar sem esperar 1 hora

```bash
kubectl create job --from=cronjob/olist-synthetic-agents manual-test-1 -n olist-agents
kubectl wait --for=condition=complete --timeout=120s job/manual-test-1 -n olist-agents
kubectl logs job/manual-test-1 -n olist-agents
```

Cada linha do log é um agente (persona, pergunta gerada, se passou,
latência). No final: `N/4 agentes completaram com sucesso`.

### 5. Comandos do dia a dia

```bash
kubectl get cronjobs -n olist-agents          # schedule, último disparo
kubectl get jobs -n olist-agents              # histórico de rodadas
kubectl logs job/<nome-do-job> -n olist-agents
kubectl delete job manual-test-1 -n olist-agents   # limpa um teste manual
```

Pra ver rodar mais rápido que de hora em hora enquanto testa, edite
`k8s/cronjob.yaml` trocando `schedule: "0 * * * *"` por
`"*/5 * * * *"` (cada 5 min) e reaplique.

## Limitação importante

Esse cluster só existe enquanto o Docker Desktop estiver rodando no seu
Mac -- fechar o laptop ou sair do Docker Desktop para o CronJob. Isso é
esperado e ok pra aprendizado; pra rodar de verdade 24/7 o próximo passo
seria migrar os mesmos manifestos pra um Kubernetes gerenciado na nuvem
(ex.: DigitalOcean Kubernetes) -- os arquivos em `k8s/` já são
praticamente reaproveitáveis, só trocando onde a imagem é publicada
(precisaria de um registry, tipo o GitHub Container Registry) e de onde
o secret é criado.
