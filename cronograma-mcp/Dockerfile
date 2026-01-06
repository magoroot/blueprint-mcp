FROM python:3.11-slim

# Metadados
LABEL maintainer="Cronograma MCP Team"
LABEL description="Servidor MCP para geração de cronogramas em XLSX"

# Definir diretório de trabalho
WORKDIR /app

# Instalar dependências do sistema (se necessário)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY main.py .

# Criar diretório de saída
RUN mkdir -p /app/outputs

# Variáveis de ambiente padrão
ENV CRONOGRAMA_OUTPUT_DIR=/app/outputs
ENV CRONOGRAMA_MAX_ROWS=500
ENV CRONOGRAMA_TTL_MINUTES=30
ENV CRONOGRAMA_BASE_URL=http://localhost:8000
ENV CRONOGRAMA_HTTP_PORT=8000
ENV LOG_LEVEL=INFO

# Expor porta HTTP
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python3 -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Executar servidor
CMD ["python3", "main.py"]
