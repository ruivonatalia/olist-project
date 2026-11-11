-- Dispara um NOTIFY a cada INSERT em app.rag_query_log -- é o que
-- permite ao backend (web/realtime.py) empurrar a atualização pro
-- navegador via WebSocket no instante em que acontece, em vez de ficar
-- perguntando ao banco de tempos em tempos (polling).
--
-- O payload do NOTIFY tem limite de 8000 bytes no Postgres -- por isso
-- NÃO inclui question_embedding (384 floats, ~7KB só isso): quem só
-- quer acompanhar o feed em tempo real não precisa do vetor bruto, só
-- da pergunta, dos chunks recuperados e do score. O vetor continua
-- gravado na tabela pra quem for auditar via SQL depois.

CREATE OR REPLACE FUNCTION app.notify_rag_query_log() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify(
        'rag_query_log_channel',
        json_build_object(
            'id', NEW.id,
            'question', NEW.question,
            'embedding_model', NEW.embedding_model,
            'embedding_dim', NEW.embedding_dim,
            'chunks', NEW.chunks,
            'top_score', NEW.top_score,
            'created_at', NEW.created_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notify_rag_query_log ON app.rag_query_log;
CREATE TRIGGER trg_notify_rag_query_log
    AFTER INSERT ON app.rag_query_log
    FOR EACH ROW
    EXECUTE FUNCTION app.notify_rag_query_log();
