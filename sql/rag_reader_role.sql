-- Role de banco com privilégio mínimo pra SQL gerado por LLM: o
-- agente/MCP nunca conecta como o dono do banco pra rodar `run_sql`,
-- só como `rag_reader`, que só pode SELECT no schema `raw` (os dados
-- analíticos da Olist). Não alcança o schema `app` (contas, senhas em
-- hash, CNPJ/CPF, tokens de 2FA) nem pode escrever em lugar nenhum --
-- mesmo que a validação de "só SELECT" em mcp_server/server.py falhe ou
-- seja contornada, o banco em si recusa qualquer outra coisa.
--
-- Defesa em profundidade: a validação de texto (regex "começa com
-- SELECT") é a primeira camada; esta role é a segunda, e não depende de
-- o código da aplicação estar certo.

-- Senha via variável do psql, pra não depender do nome do banco nem
-- hardcodar a senha de produção neste arquivo versionado:
--   psql "$NEON_URL" -v reader_password="'minha-senha-forte'" -f rag_reader_role.sql
-- Sem -v, cai no valor de desenvolvimento local.
\if :{?reader_password}
\else
    \set reader_password 'rag_reader_local_dev'
\endif

-- Nota pra quem for ler: psql NÃO substitui variáveis (:'nome') dentro
-- de blocos $$ ... $$ (evita quebrar corpos de função que tenham ':'
-- literal) -- por isso o CREATE/ALTER ROLE roda via \gexec (substitui
-- na query de fora, manda o texto resultante pro servidor) em vez de
-- um DO block como o de GRANT CONNECT abaixo, que não precisa de
-- variável do psql.
SELECT CASE
    WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_reader')
    THEN format('ALTER ROLE rag_reader WITH PASSWORD %L', :'reader_password')
    ELSE format('CREATE ROLE rag_reader LOGIN PASSWORD %L', :'reader_password')
END AS _sql
\gexec

-- current_database() em vez de um nome fixo -- o banco em produção
-- (Neon) não necessariamente se chama "olist".
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rag_reader', current_database());
END $$;

GRANT USAGE ON SCHEMA raw TO rag_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO rag_reader;

-- garante que tabelas criadas depois no schema raw também fiquem visíveis
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO rag_reader;

-- explicitamente SEM acesso ao schema app (contas, senhas, 2FA)
REVOKE ALL ON SCHEMA app FROM rag_reader;
