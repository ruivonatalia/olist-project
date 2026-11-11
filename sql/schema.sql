-- Schema "raw": landing zone dos dados do Olist, um espelho do que veio
-- das fontes de origem (Postgres relacional + extração do MongoDB), sem
-- foreign keys -- de propósito. Numa landing zone real, o dado chega como
-- veio da origem; integridade referencial é responsabilidade da camada de
-- transformação (dbt), verificada por testes (`relationships`,
-- `not_null`, `unique`), não pela constraint do banco.
--
-- Ex.: 2 categorias em products.product_category_name não existem em
-- category_translation ("pc_gamer", "portateis_cozinha_e_preparadores_de_
-- alimentos") -- é uma inconsistência real do dataset Olist. Com FK, a
-- carga quebraria; sem FK, ela vira um teste do dbt que documenta o
-- problema em vez de escondê-lo.

CREATE SCHEMA IF NOT EXISTS raw;

DROP TABLE IF EXISTS raw.order_payments;
DROP TABLE IF EXISTS raw.order_items;
DROP TABLE IF EXISTS raw.orders;
DROP TABLE IF EXISTS raw.products;
DROP TABLE IF EXISTS raw.category_translation;
DROP TABLE IF EXISTS raw.sellers;
DROP TABLE IF EXISTS raw.customers;
DROP TABLE IF EXISTS raw.geolocation;

CREATE TABLE raw.customers (
    customer_id               text PRIMARY KEY,
    customer_unique_id        text NOT NULL,
    customer_zip_code_prefix  text,
    customer_city             text,
    customer_state            text
);

CREATE TABLE raw.geolocation (
    geolocation_zip_code_prefix  text,
    geolocation_lat               double precision,
    geolocation_lng               double precision,
    geolocation_city              text,
    geolocation_state             text
);

CREATE TABLE raw.sellers (
    seller_id               text PRIMARY KEY,
    seller_zip_code_prefix  text,
    seller_city             text,
    seller_state            text
);

CREATE TABLE raw.category_translation (
    product_category_name          text PRIMARY KEY,
    product_category_name_english  text
);

CREATE TABLE raw.products (
    product_id                   text PRIMARY KEY,
    product_category_name        text,
    product_name_lenght           integer,
    product_description_lenght    integer,
    product_photos_qty            integer,
    product_weight_g              double precision,
    product_length_cm             double precision,
    product_height_cm             double precision,
    product_width_cm              double precision
);

CREATE TABLE raw.orders (
    order_id                        text PRIMARY KEY,
    customer_id                     text,
    order_status                    text,
    order_purchase_timestamp        timestamp,
    order_approved_at               timestamp,
    order_delivered_carrier_date    timestamp,
    order_delivered_customer_date   timestamp,
    order_estimated_delivery_date   timestamp
);

CREATE TABLE raw.order_items (
    order_id              text,
    order_item_id         integer,
    product_id            text,
    seller_id             text,
    shipping_limit_date   timestamp,
    price                 numeric(12, 2),
    freight_value         numeric(12, 2),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE raw.order_payments (
    order_id              text,
    payment_sequential    integer,
    payment_type          text,
    payment_installments  integer,
    payment_value         numeric(12, 2),
    PRIMARY KEY (order_id, payment_sequential)
);

-- Espelho, no Postgres, do que foi extraído do MongoDB -- é o que permite
-- ao dbt (que só fala SQL) cruzar dado relacional com dado não-estruturado
-- na mesma camada de transformação. Populado por ingest/sync_mongo_to_raw.py,
-- não por ingest_postgres.py.
--
-- Sem PRIMARY KEY em review_id de propósito: 814 linhas do dataset original
-- reaproveitam o mesmo review_id em order_id diferentes (outra
-- inconsistência real da fonte) -- forçar unicidade aqui quebraria a carga
-- em vez de deixar o dbt documentar o problema como teste.
CREATE TABLE IF NOT EXISTS raw.reviews (
    review_id                 text,
    order_id                  text,
    review_score              integer,
    review_comment_title      text,
    review_comment_message    text,
    review_creation_date      timestamp,
    review_answer_timestamp   timestamp
);
CREATE INDEX IF NOT EXISTS ix_raw_reviews_order_id ON raw.reviews (order_id);

CREATE TABLE IF NOT EXISTS raw.support_tickets (
    ticket_id         text PRIMARY KEY,
    order_id          text,
    channel           text,
    category          text,
    priority          text,
    status            text,
    customer_message  text,
    created_at        timestamp,
    resolved_at       timestamp
);
