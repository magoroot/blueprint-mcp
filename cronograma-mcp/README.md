# Cronograma MCP Server

Servidor MCP (Model Context Protocol) para geração de cronogramas corporativos em formato XLSX com endpoint de download HTTP integrado.

## 📋 Características

- **Geração de XLSX corporativo** com layout profissional usando OpenPyXL
- **Durações em horas** no formato `HHH:MM:SS` (permite valores acima de 24h, ex: `247:40:00`)
- **Validações rigorosas**: macro sempre deve conter pelo menos 1 micro
- **Cálculos automáticos**: macro = soma das micros, projeto = soma de todas as macros
- **Download via HTTP**: retorna base64 + URL de download com TTL configurável
- **Integração com OpenWebUI**: link clicável no chat para download direto
- **Governança**: limites de linhas, sanitização de nomes, TTL de arquivos

## 🚀 Instalação

### Pré-requisitos

- Python 3.11+
- pip3

### Instalação das dependências

```bash
pip3 install -r requirements.txt
```

## ⚙️ Configuração

O servidor utiliza variáveis de ambiente para configuração:

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `CRONOGRAMA_OUTPUT_DIR` | Diretório para salvar arquivos XLSX | `./outputs` |
| `CRONOGRAMA_MAX_ROWS` | Limite máximo de linhas no cronograma | `500` |
| `CRONOGRAMA_TTL_MINUTES` | Tempo de vida dos arquivos (minutos) | `30` |
| `CRONOGRAMA_BASE_URL` | URL base para links de download | `http://localhost:8000` |
| `CRONOGRAMA_HTTP_PORT` | Porta do servidor HTTP | `8000` |
| `LOG_LEVEL` | Nível de log (DEBUG, INFO, WARNING, ERROR) | `INFO` |

### Exemplo de configuração

```bash
export CRONOGRAMA_OUTPUT_DIR="/var/cronogramas"
export CRONOGRAMA_MAX_ROWS="1000"
export CRONOGRAMA_TTL_MINUTES="60"
export CRONOGRAMA_BASE_URL="http://meu-servidor.com:8000"
export CRONOGRAMA_HTTP_PORT="8000"
export LOG_LEVEL="INFO"
```

## 🏃 Execução

### Modo desenvolvimento (local)

```bash
python3 main.py
```

O servidor iniciará:
- **Servidor MCP**: comunicação via stdio para integração com clientes MCP
- **Servidor HTTP**: porta 8000 (ou conforme `CRONOGRAMA_HTTP_PORT`)

### Endpoints HTTP

- `GET /health` - Health check do servidor HTTP
- `GET /download/{token}` - Download de arquivo XLSX via token

## 📦 Integração com OpenWebUI

### Configuração no OpenWebUI

1. Configure o servidor MCP no OpenWebUI apontando para o `main.py`
2. Certifique-se de que o `CRONOGRAMA_BASE_URL` está acessível pelo navegador do usuário
3. O link de download será exibido como URL clicável no chat

### Exemplo de uso no chat

```
Usuário: Gere um cronograma para o Projeto XYZ
Assistente: [chama a tool cronograma.gerar_xlsx]
Assistente: Cronograma gerado! Baixe aqui: http://localhost:8000/download/abc123...
```

## 📄 Formato de Entrada (JSON)

### Estrutura completa

```json
{
  "project": {
    "name": "Projeto Lift-and-Shift Rehost - Grupo Zelo",
    "code": "Zelo-Fase1",
    "owner": "3DB",
    "timezone": "America/Sao_Paulo"
  },
  "settings": {
    "format_version": "1.0.0",
    "duration_format": "HOURS_OVER_24",
    "max_rows": 500,
    "sheet_name": "Planilha1",
    "include_project_row": true
  },
  "macros": [
    {
      "name": "Pre-Projeto",
      "responsible": "3DB+Cliente",
      "micros": [
        {
          "name": "Levantamento de Requisitos",
          "hours": 8,
          "responsible": "3DB+Cliente"
        }
      ]
    },
    {
      "name": "Atividades preliminares",
      "responsible": "3DB",
      "micros": [
        {
          "name": "Alinhamento (Comercial, Técnico)",
          "hours": 0.1667,
          "responsible": "3DB/PRJ"
        },
        {
          "name": "Redesenhar Blueprint",
          "hours": 4,
          "responsible": "3DB/AIM"
        }
      ]
    }
  ]
}
```

### Campos obrigatórios

- `project.name` - Nome do projeto
- `macros` - Array com pelo menos 1 macro
- `macros[].name` - Nome da macro
- `macros[].micros` - Array com **pelo menos 1 micro** (regra obrigatória)
- `macros[].micros[].name` - Nome da micro tarefa
- `macros[].micros[].hours` - Duração em horas (número > 0)

### Regras de validação

1. **Macro sempre com micro**: toda macro DEVE ter pelo menos 1 micro tarefa
2. **Duração da macro**: calculada automaticamente como soma das micros
3. **Total do projeto**: calculado como soma de todas as macros
4. **Limite de linhas**: total de linhas não pode exceder `max_rows`
5. **Horas válidas**: devem ser numéricas e maiores que 0

## 📊 Formato de Saída (JSON)

### Sucesso

```json
{
  "ok": true,
  "format_version": "1.0.0",
  "project_name": "Projeto Lift-and-Shift Rehost - Grupo Zelo",
  "project_total_hours": 247.6667,
  "project_total_duration_display": "247:40:00",
  "filename": "Cronograma - Projeto Lift-and-Shift Rehost - Grupo Zelo - 2026-01-06.xlsx",
  "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "base64": "<BASE64_DO_ARQUIVO_XLSX>",
  "download_url": "http://localhost:8000/download/abc123xyz...",
  "download_expires_at": "2026-01-06T15:30:00",
  "summary": {
    "macro_count": 5,
    "micro_count": 32,
    "macros": [
      {
        "name": "Pre-Projeto",
        "hours": 8.0,
        "duration_display": "8:00:00",
        "micro_count": 1
      },
      {
        "name": "Atividades preliminares",
        "hours": 4.1667,
        "duration_display": "4:10:00",
        "micro_count": 2
      }
    ]
  }
}
```

### Erro de validação

```json
{
  "ok": false,
  "error_code": "VALIDATION_ERROR",
  "message": "Erro de validação no payload",
  "details": [
    {
      "field": "macros[1].micros",
      "issue": "macro SEMPRE deve conter pelo menos 1 micro (regra obrigatória)"
    }
  ]
}
```

### Erro de limite excedido

```json
{
  "ok": false,
  "error_code": "MAX_ROWS_EXCEEDED",
  "message": "O cronograma possui 550 linhas, excedendo o limite de 500",
  "details": []
}
```

## 🛠️ Tools disponíveis

### 1. `cronograma.gerar_xlsx`

Gera o arquivo XLSX completo.

**Entrada**: payload JSON completo (ver formato acima)

**Saída**: JSON com base64, download_url e metadados

### 2. `cronograma.validar`

Valida o payload sem gerar o arquivo (útil para pré-validação).

**Entrada**: payload JSON completo

**Saída**: JSON com resultado da validação e preview dos totais

### 3. `cronograma.health`

Verifica status do servidor MCP.

**Entrada**: nenhuma

**Saída**: JSON com status e configurações

## 📐 Layout do XLSX

O arquivo XLSX gerado possui:

### Estrutura

1. **Cabeçalho** (linha 1): `Nome da Tarefa | Duration | Responsável`
   - Fundo cinza claro, fonte bold, bordas
   - Linha congelada (freeze panes)

2. **Linha do Projeto** (linha 2):
   - Nome do projeto, total em `HHH:MM:SS`, responsável
   - Fundo cinza médio, fonte bold

3. **Macros**:
   - Nome da macro, duração (soma das micros), responsável
   - Fundo cinza leve, fonte bold

4. **Micros**:
   - Nome indentado (`    Nome`), duração individual, responsável
   - Bordas padrão

### Formato de duração

- **Sempre em horas**: formato `HHH:MM:SS`
- **Permite valores acima de 24h**: ex: `247:40:00` (247 horas e 40 minutos)
- **Nunca converte para dias**: mantém tudo em horas acumuladas
- **Células como texto**: evita conversão automática do Excel

### Larguras de colunas

- Coluna A (Nome): 70 caracteres
- Coluna B (Duration): 15 caracteres (centralizado)
- Coluna C (Responsável): 22 caracteres

## 🐳 Docker

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependências
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copiar código
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

# Executar servidor
CMD ["python3", "main.py"]
```

### Build e execução

```bash
# Build
docker build -t cronograma-mcp .

# Executar
docker run -d \
  -p 8000:8000 \
  -e CRONOGRAMA_BASE_URL=http://meu-servidor.com:8000 \
  -v $(pwd)/outputs:/app/outputs \
  --name cronograma-mcp \
  cronograma-mcp
```

## 🔍 Troubleshooting

### Erro: "macro SEMPRE deve conter pelo menos 1 micro"

**Causa**: Uma macro foi enviada sem micros ou com array vazio.

**Solução**: Certifique-se de que toda macro possui pelo menos 1 micro tarefa.

### Erro: "MAX_ROWS_EXCEEDED"

**Causa**: O cronograma possui mais linhas do que o limite configurado.

**Solução**: Reduza o número de tarefas ou aumente `CRONOGRAMA_MAX_ROWS`.

### Link de download retorna 404

**Causa**: O token expirou (TTL padrão: 30 minutos) ou o arquivo foi removido.

**Solução**: Gere um novo cronograma. Ajuste `CRONOGRAMA_TTL_MINUTES` se necessário.

### Duração aparece como dias no Excel

**Causa**: O Excel pode tentar converter automaticamente.

**Solução**: O servidor já salva como texto para evitar isso. Se persistir, formate a coluna B como "Texto" no Excel.

## 📝 Exemplos

### Exemplo 1: Projeto simples

```json
{
  "project": {
    "name": "Migração Cloud",
    "owner": "TI"
  },
  "macros": [
    {
      "name": "Planejamento",
      "responsible": "Arquiteto",
      "micros": [
        {"name": "Levantamento", "hours": 16, "responsible": "Arquiteto"},
        {"name": "Documentação", "hours": 8, "responsible": "Arquiteto"}
      ]
    }
  ]
}
```

**Resultado**: Projeto com 24 horas (24:00:00)

### Exemplo 2: Projeto complexo

```json
{
  "project": {
    "name": "Implementação ERP",
    "code": "ERP-2026",
    "owner": "PMO"
  },
  "settings": {
    "max_rows": 1000
  },
  "macros": [
    {
      "name": "Fase 1 - Análise",
      "responsible": "Consultoria",
      "micros": [
        {"name": "Workshops", "hours": 40, "responsible": "Consultor Senior"},
        {"name": "Mapeamento processos", "hours": 80, "responsible": "Analista"}
      ]
    },
    {
      "name": "Fase 2 - Desenvolvimento",
      "responsible": "Dev Team",
      "micros": [
        {"name": "Configuração módulos", "hours": 160, "responsible": "Dev"},
        {"name": "Customizações", "hours": 120, "responsible": "Dev"},
        {"name": "Integrações", "hours": 80, "responsible": "Dev"}
      ]
    }
  ]
}
```

**Resultado**: Projeto com 480 horas (480:00:00)

## 📚 Referências

- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [OpenPyXL Documentation](https://openpyxl.readthedocs.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## 📄 Licença

Este projeto é fornecido como está, sem garantias.

## 👥 Suporte

Para questões ou suporte, consulte a documentação ou entre em contato com o time de desenvolvimento.
