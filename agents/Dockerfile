# Imagem enxuta: só o necessário pra rodar run_agents.py -- não reaproveita
# o requirements.txt do projeto principal (que traz torch/sentence-
# transformers/langchain, pesados demais pra um script que só chama uma
# API HTTP).
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY run_agents.py personas.json ./

CMD ["python", "run_agents.py"]
