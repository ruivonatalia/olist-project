-- Log do tráfego sintético gerado pelos agentes (agents/run_agents.py):
-- uma linha por pergunta simulada, pra servir de dado real de
-- monitoramento contínuo (e de insumo pro estudo de retrieval do TCC) --
-- independente do app.rag_query_log, que é o log do retrieval em si.

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.synthetic_traffic_log (
    id          serial PRIMARY KEY,
    persona     text NOT NULL,
    question    text NOT NULL,
    answer      text,
    routed_to   text,              -- 'stable', 'canary', ou null (quando não passou pelo router)
    success     boolean NOT NULL,
    latency_ms  double precision NOT NULL,
    error       text,
    created_at  timestamp NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_synthetic_traffic_log_created_at ON app.synthetic_traffic_log (created_at DESC);
