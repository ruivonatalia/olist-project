#!/usr/bin/env bash
# Roda os 3 gates em sequência, fail-fast -- se um gate falha, os
# seguintes nem rodam (mesmo princípio da aula 3: não gastar tempo/custo
# em cima de dado ou modelo que já se sabe ruim).
set -e
cd "$(dirname "$0")/.."

echo "== Gate 1: data validation =="
./.venv/bin/python -m gates.validate_data
echo

echo "== Gate 2: retrieval eval =="
./.venv/bin/python -m gates.eval_retrieval
echo

echo "== Gate 3: response quality =="
./.venv/bin/python -m gates.eval_response
echo

echo "Todos os gates passaram."
