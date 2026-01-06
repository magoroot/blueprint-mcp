# Integração com OpenWebUI

Este documento descreve como integrar o Cronograma MCP Server com o OpenWebUI para permitir que usuários gerem e baixem cronogramas diretamente pelo chat.

## 📋 Pré-requisitos

- OpenWebUI instalado e funcionando
- Servidor Cronograma MCP rodando e acessível
- Python 3.11+ no ambiente do OpenWebUI

## 🔧 Configuração do MCP no OpenWebUI

### 1. Configurar o servidor MCP

No OpenWebUI, adicione o servidor MCP nas configurações:

**Caminho**: Settings → Admin → MCP Servers

**Configuração**:

```json
{
  "mcpServers": {
    "cronograma": {
      "command": "python3",
      "args": ["/caminho/completo/para/cronograma-mcp/main.py"],
      "env": {
        "CRONOGRAMA_OUTPUT_DIR": "/var/cronogramas",
        "CRONOGRAMA_MAX_ROWS": "500",
        "CRONOGRAMA_TTL_MINUTES": "30",
        "CRONOGRAMA_BASE_URL": "http://seu-servidor.com:8000",
        "CRONOGRAMA_HTTP_PORT": "8000",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### 2. Ajustar CRONOGRAMA_BASE_URL

**IMPORTANTE**: O `CRONOGRAMA_BASE_URL` deve ser acessível pelo navegador do usuário final, não apenas pelo servidor do OpenWebUI.

**Opções:**

- **Servidor público**: `http://seu-dominio.com:8000`
- **Localhost (desenvolvimento)**: `http://localhost:8000`
- **IP interno**: `http://192.168.1.100:8000`
- **Túnel (ngrok, etc)**: `https://abc123.ngrok.io`

### 3. Garantir que a porta HTTP esteja acessível

O servidor HTTP (porta 8000 por padrão) precisa estar acessível:

```bash
# Verificar se a porta está aberta
curl http://localhost:8000/health

# Resposta esperada:
# {"ok":true,"service":"cronograma-mcp-http","status":"healthy","mcp_active":true}
```

Se estiver usando firewall, libere a porta:

```bash
sudo ufw allow 8000/tcp
```

## 🚀 Uso no Chat

### Exemplo de conversa

**Usuário:**
```
Crie um cronograma para o Projeto de Migração Cloud com as seguintes fases:

1. Planejamento (40 horas)
   - Levantamento: 16h
   - Documentação: 24h

2. Execução (120 horas)
   - Migração de dados: 80h
   - Testes: 40h
```

**Assistente (usando a tool):**

O assistente irá:
1. Estruturar o payload JSON
2. Chamar `cronograma.gerar_xlsx`
3. Receber a resposta com `download_url`
4. Apresentar o link ao usuário

**Resposta do Assistente:**
```
Cronograma gerado com sucesso! 

📊 Resumo:
- Total do projeto: 160:00:00 (160 horas)
- 2 macros, 4 micros

📥 Baixar cronograma:
http://seu-servidor.com:8000/download/abc123xyz...

O link expira em 30 minutos.
```

### Estrutura do payload que o assistente deve enviar

```json
{
  "project": {
    "name": "Projeto de Migração Cloud",
    "owner": "TI"
  },
  "macros": [
    {
      "name": "Planejamento",
      "responsible": "Arquiteto",
      "micros": [
        {"name": "Levantamento", "hours": 16, "responsible": "Analista"},
        {"name": "Documentação", "hours": 24, "responsible": "Arquiteto"}
      ]
    },
    {
      "name": "Execução",
      "responsible": "Equipe TI",
      "micros": [
        {"name": "Migração de dados", "hours": 80, "responsible": "DevOps"},
        {"name": "Testes", "hours": 40, "responsible": "QA"}
      ]
    }
  ]
}
```

## 🔍 Validação antes de gerar

O assistente pode usar a tool `cronograma.validar` para verificar se o payload está correto antes de gerar o arquivo:

```python
# Exemplo de uso da tool validar
resultado = cronograma.validar(payload)

if resultado["ok"]:
    # Payload válido, pode gerar
    print(f"Preview: {resultado['preview']['project_total_duration_display']}")
else:
    # Erro de validação
    print(f"Erro: {resultado['message']}")
```

## 🎯 Boas práticas para o assistente

### 1. Sempre validar entrada do usuário

- Garantir que toda macro tenha pelo menos 1 micro
- Converter dias para horas se o usuário fornecer em dias
- Validar que horas sejam números positivos

### 2. Apresentar resumo antes de gerar

```
Vou criar um cronograma com:
- Projeto: Migração Cloud
- 2 fases (macros)
- 4 tarefas (micros)
- Total estimado: 160 horas

Confirma?
```

### 3. Formatar a resposta de forma amigável

```markdown
✅ Cronograma gerado com sucesso!

📊 **Resumo do Projeto**
- Nome: Projeto de Migração Cloud
- Total: 160:00:00 (160 horas)
- Fases: 2
- Tarefas: 4

📥 **Download**
[Baixar cronograma XLSX](http://seu-servidor.com:8000/download/abc123...)

⏰ O link expira em 30 minutos.
```

### 4. Tratar erros de forma clara

```
❌ Erro ao gerar cronograma

Problema: A fase "Planejamento" não possui tarefas.

Regra: Toda fase (macro) DEVE conter pelo menos 1 tarefa (micro).

Por favor, adicione tarefas à fase "Planejamento".
```

## 🔐 Segurança

### 1. Limites

O servidor possui limites configuráveis:

- `MAX_ROWS`: limite de linhas no cronograma (padrão: 500)
- `TTL_MINUTES`: tempo de vida dos arquivos (padrão: 30 minutos)

### 2. Sanitização

- Nomes de arquivo são automaticamente sanitizados
- Caracteres inválidos são removidos
- Tamanho máximo de nome: 200 caracteres

### 3. Limpeza automática

- Arquivos expirados são removidos automaticamente
- Registry é limpo a cada nova requisição

## 🐛 Troubleshooting

### Problema: Link de download retorna 404

**Causas possíveis:**
1. Token expirado (TTL padrão: 30 minutos)
2. Servidor HTTP não está rodando
3. `CRONOGRAMA_BASE_URL` incorreto

**Soluções:**
1. Gerar novo cronograma
2. Verificar se o servidor HTTP está ativo: `curl http://localhost:8000/health`
3. Ajustar `CRONOGRAMA_BASE_URL` nas variáveis de ambiente

### Problema: Erro "macro SEMPRE deve conter pelo menos 1 micro"

**Causa:** Uma macro foi enviada sem micros ou com array vazio.

**Solução:** Garantir que toda macro tenha pelo menos 1 micro no payload.

### Problema: Duração aparece como dias no Excel

**Causa:** Excel pode tentar converter automaticamente.

**Solução:** O servidor já salva como texto. Se persistir, formatar coluna B como "Texto" no Excel.

### Problema: OpenWebUI não encontra a tool

**Causas possíveis:**
1. Servidor MCP não está rodando
2. Configuração incorreta no OpenWebUI
3. Caminho do `main.py` incorreto

**Soluções:**
1. Verificar se o processo está ativo
2. Revisar configuração JSON do MCP
3. Usar caminho absoluto para `main.py`

## 📊 Monitoramento

### Health check HTTP

```bash
curl http://localhost:8000/health
```

**Resposta esperada:**
```json
{
  "ok": true,
  "service": "cronograma-mcp-http",
  "status": "healthy",
  "mcp_active": true
}
```

### Health check MCP

Usar a tool `cronograma.health` no chat:

```
Usuário: Verifique o status do servidor de cronogramas
```

**Resposta esperada:**
```json
{
  "ok": true,
  "service": "cronograma-mcp",
  "status": "healthy",
  "output_dir": "/var/cronogramas",
  "max_rows": 500,
  "ttl_minutes": 30,
  "active_files": 3
}
```

## 🔄 Atualização e manutenção

### Atualizar o servidor

```bash
# Parar o servidor (se rodando como serviço)
sudo systemctl stop cronograma-mcp

# Atualizar código
cd /caminho/para/cronograma-mcp
git pull  # ou copiar novos arquivos

# Reinstalar dependências (se necessário)
pip3 install -r requirements.txt

# Reiniciar
sudo systemctl start cronograma-mcp
```

### Limpar arquivos antigos manualmente

```bash
# Remover todos os arquivos do diretório de saída
rm -rf /var/cronogramas/*

# Ou remover apenas arquivos mais antigos que 1 dia
find /var/cronogramas -name "*.xlsx" -mtime +1 -delete
```

## 📝 Exemplo completo de integração

### 1. Sistema prompt para o assistente

```
Você tem acesso à tool cronograma.gerar_xlsx para criar cronogramas em XLSX.

Regras obrigatórias:
1. Toda macro DEVE ter pelo menos 1 micro
2. Durações sempre em horas (nunca dias)
3. Macro duration = soma das micros (não definir manualmente)
4. Projeto total = soma de todas as macros

Quando o usuário pedir um cronograma:
1. Extrair informações (projeto, fases, tarefas, horas)
2. Estruturar o payload JSON
3. Validar com cronograma.validar (opcional)
4. Gerar com cronograma.gerar_xlsx
5. Apresentar link de download de forma amigável
```

### 2. Exemplo de fluxo

```
Usuário: Crie um cronograma para implementação de ERP

Assistente: Entendido! Vou precisar de mais informações:
- Quais são as fases do projeto?
- Quanto tempo (em horas) cada fase deve levar?
- Quais tarefas compõem cada fase?

Usuário: 
Fase 1 - Análise (40h):
- Workshops: 24h
- Documentação: 16h

Fase 2 - Desenvolvimento (120h):
- Configuração: 80h
- Testes: 40h

Assistente: [chama cronograma.gerar_xlsx com payload estruturado]

Assistente: ✅ Cronograma criado!

📊 Implementação de ERP
- Total: 160:00:00 (160 horas)
- 2 fases, 4 tarefas

📥 [Baixar cronograma](http://servidor.com:8000/download/abc...)
⏰ Link válido por 30 minutos
```

## 🌐 Deploy em produção

### Usando systemd (Linux)

Criar arquivo `/etc/systemd/system/cronograma-mcp.service`:

```ini
[Unit]
Description=Cronograma MCP Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/cronograma-mcp
Environment="CRONOGRAMA_OUTPUT_DIR=/var/cronogramas"
Environment="CRONOGRAMA_BASE_URL=http://seu-servidor.com:8000"
Environment="CRONOGRAMA_HTTP_PORT=8000"
ExecStart=/usr/bin/python3 /opt/cronograma-mcp/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Habilitar e iniciar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cronograma-mcp
sudo systemctl start cronograma-mcp
sudo systemctl status cronograma-mcp
```

### Usando Docker

```bash
# Build
docker build -t cronograma-mcp .

# Run
docker run -d \
  --name cronograma-mcp \
  -p 8000:8000 \
  -e CRONOGRAMA_BASE_URL=http://seu-servidor.com:8000 \
  -v /var/cronogramas:/app/outputs \
  --restart unless-stopped \
  cronograma-mcp

# Logs
docker logs -f cronograma-mcp
```

## 📚 Recursos adicionais

- [Documentação do MCP](https://modelcontextprotocol.io/)
- [OpenWebUI Documentation](https://docs.openwebui.com/)
- [README principal](./README.md)

---

**Suporte**: Para questões ou problemas, consulte o README principal ou entre em contato com o time de desenvolvimento.
