FROM python:3.12-slim

WORKDIR /app

# Dependências básicas do sistema (mínimas e clássicas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Copia o projeto
COPY . .

# Instala:
# - uv: para instalar deps via pyproject/uv.lock e executar "uv run"
# - mcpo: para expor seu MCP (stdio) como HTTP/OpenAPI (pra Open WebUI)
RUN pip install --no-cache-dir uv mcpo

# Instala dependências do projeto (se existir pyproject.toml/uv.lock)
# - se tiver uv.lock, ele usa e fica reprodutível
RUN if [ -f "pyproject.toml" ]; then uv sync; fi

# O seu MCP escreve no diretório DEFAULT_OUTPUT_DIR, que vem de CRONOGRAMA_OUTPUT_DIR
# (no server.py o default é ./outputs) :contentReference[oaicite:4]{index=4}
ENV CRONOGRAMA_OUTPUT_DIR=/app/outputs

# Porta do mcpo (proxy HTTP)
EXPOSE 8000

# mcpo sobe HTTP/OpenAPI e, após o "--", a gente inicia o MCP via uv
CMD ["sh", "-lc", "mcpo --host 0.0.0.0 --port 8000 -- uv run server.py"]
