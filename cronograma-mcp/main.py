#!/usr/bin/env python3
"""
Servidor MCP para geração de cronogramas em XLSX
Integra FastMCP + FastAPI para download via HTTP
"""

import os
import sys
import logging
import base64
import secrets
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
import re

# FastMCP e FastAPI
from mcp.server.fastmcp import FastMCP
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import uvicorn

# OpenPyXL para geração de XLSX
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# ========================================================
# CONFIGURAÇÃO E CONSTANTES
# ========================================================

# Configuração de logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("cronograma-mcp")

# Variáveis de ambiente
OUTPUT_DIR = Path(os.getenv("CRONOGRAMA_OUTPUT_DIR", "./outputs"))
MAX_ROWS = int(os.getenv("CRONOGRAMA_MAX_ROWS", "500"))
TTL_MINUTES = int(os.getenv("CRONOGRAMA_TTL_MINUTES", "30"))
BASE_URL = os.getenv("CRONOGRAMA_BASE_URL", "http://localhost:8000")
HTTP_PORT = int(os.getenv("CRONOGRAMA_HTTP_PORT", "8000"))

# Criar diretório de saída
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Registry de arquivos temporários (token -> info)
file_registry: Dict[str, Dict[str, Any]] = {}

# ========================================================
# UTILITÁRIOS
# ========================================================

def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos do nome do arquivo"""
    # Remove caracteres especiais e substitui por espaço ou hífen
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    return sanitized[:200]  # Limita tamanho

def hours_to_duration_display(hours: float) -> str:
    """
    Converte horas decimais para formato HHH:MM:SS
    Permite valores acima de 24h (ex: 247:40:00)
    """
    if hours < 0:
        hours = 0
    
    total_seconds = int(round(hours * 3600))
    
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    
    return f"{h:d}:{m:02d}:{s:02d}"

def generate_token() -> str:
    """Gera token seguro para download"""
    return secrets.token_urlsafe(32)

def cleanup_expired_files():
    """Remove arquivos expirados do registry e disco"""
    now = datetime.now()
    expired_tokens = []
    
    for token, info in file_registry.items():
        if now > info["expires_at"]:
            expired_tokens.append(token)
            # Remove arquivo do disco
            try:
                filepath = Path(info["filepath"])
                if filepath.exists():
                    filepath.unlink()
                    logger.info(f"Arquivo expirado removido: {filepath.name}")
            except Exception as e:
                logger.error(f"Erro ao remover arquivo expirado: {e}")
    
    # Remove do registry
    for token in expired_tokens:
        del file_registry[token]

# ========================================================
# VALIDAÇÃO
# ========================================================

def validate_payload(payload: dict) -> tuple[bool, Optional[dict]]:
    """
    Valida o payload de entrada
    Retorna (is_valid, error_response)
    """
    errors = []
    
    # Validar project
    if "project" not in payload:
        errors.append({"field": "project", "issue": "campo obrigatório"})
    else:
        project = payload["project"]
        if not project.get("name"):
            errors.append({"field": "project.name", "issue": "nome do projeto obrigatório"})
    
    # Validar macros
    if "macros" not in payload:
        errors.append({"field": "macros", "issue": "campo obrigatório"})
    elif not isinstance(payload["macros"], list) or len(payload["macros"]) == 0:
        errors.append({"field": "macros", "issue": "deve conter pelo menos 1 macro"})
    else:
        macros = payload["macros"]
        total_rows = 1  # Linha do projeto
        
        for idx, macro in enumerate(macros):
            # Validar nome da macro
            if not macro.get("name"):
                errors.append({"field": f"macros[{idx}].name", "issue": "nome da macro obrigatório"})
            
            # REGRA CRÍTICA: Macro SEMPRE deve ter micros
            if "micros" not in macro or not isinstance(macro["micros"], list) or len(macro["micros"]) == 0:
                errors.append({
                    "field": f"macros[{idx}].micros",
                    "issue": "macro SEMPRE deve conter pelo menos 1 micro (regra obrigatória)"
                })
            else:
                micros = macro["micros"]
                total_rows += 1  # Linha da macro
                
                for midx, micro in enumerate(micros):
                    total_rows += 1  # Linha da micro
                    
                    # Validar nome da micro
                    if not micro.get("name"):
                        errors.append({
                            "field": f"macros[{idx}].micros[{midx}].name",
                            "issue": "nome da micro obrigatório"
                        })
                    
                    # Validar hours
                    if "hours" not in micro:
                        errors.append({
                            "field": f"macros[{idx}].micros[{midx}].hours",
                            "issue": "hours obrigatório"
                        })
                    else:
                        try:
                            hours = float(micro["hours"])
                            if hours <= 0:
                                errors.append({
                                    "field": f"macros[{idx}].micros[{midx}].hours",
                                    "issue": "hours deve ser maior que 0"
                                })
                        except (ValueError, TypeError):
                            errors.append({
                                "field": f"macros[{idx}].micros[{midx}].hours",
                                "issue": "hours deve ser numérico"
                            })
        
        # Validar MAX_ROWS
        settings = payload.get("settings", {})
        max_rows_limit = settings.get("max_rows", MAX_ROWS)
        
        if total_rows > max_rows_limit:
            errors.append({
                "field": "total_rows",
                "issue": f"total de linhas ({total_rows}) excede o limite ({max_rows_limit})"
            })
            return False, {
                "ok": False,
                "error_code": "MAX_ROWS_EXCEEDED",
                "message": f"O cronograma possui {total_rows} linhas, excedendo o limite de {max_rows_limit}",
                "details": errors
            }
    
    if errors:
        return False, {
            "ok": False,
            "error_code": "VALIDATION_ERROR",
            "message": "Erro de validação no payload",
            "details": errors
        }
    
    return True, None

# ========================================================
# GERAÇÃO DO XLSX
# ========================================================

def generate_xlsx(payload: dict) -> tuple[Path, dict]:
    """
    Gera o arquivo XLSX e retorna (filepath, summary)
    """
    project = payload["project"]
    settings = payload.get("settings", {})
    macros = payload["macros"]
    
    # Configurações
    sheet_name = settings.get("sheet_name", "Planilha1")
    include_project_row = settings.get("include_project_row", True)
    
    # Criar workbook
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    
    # Estilos
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    project_font = Font(bold=True, size=11)
    project_fill = PatternFill(start_color="A9A9A9", end_color="A9A9A9", fill_type="solid")
    
    macro_font = Font(bold=True, size=10)
    macro_fill = PatternFill(start_color="E8E8E8", end_color="E8E8E8", fill_type="solid")
    
    border_thin = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Larguras das colunas
    ws.column_dimensions['A'].width = 70
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 22
    
    # Cabeçalho (linha 1)
    ws['A1'] = "Nome da Tarefa"
    ws['B1'] = "Duration"
    ws['C1'] = "Responsável"
    
    for col in ['A', 'B', 'C']:
        cell = ws[f'{col}1']
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment if col != 'A' else Alignment(horizontal="left", vertical="center")
        cell.border = border_thin
    
    # Congelar primeira linha
    ws.freeze_panes = 'A2'
    
    current_row = 2
    
    # Calcular totais
    project_total_hours = 0.0
    macro_summaries = []
    
    for macro in macros:
        macro_total_hours = 0.0
        micro_count = 0
        
        for micro in macro["micros"]:
            hours = float(micro["hours"])
            macro_total_hours += hours
            micro_count += 1
        
        project_total_hours += macro_total_hours
        
        macro_summaries.append({
            "name": macro["name"],
            "hours": round(macro_total_hours, 4),
            "duration_display": hours_to_duration_display(macro_total_hours),
            "micro_count": micro_count
        })
    
    # Linha do projeto (se habilitado)
    if include_project_row:
        ws[f'A{current_row}'] = project["name"]
        ws[f'B{current_row}'] = hours_to_duration_display(project_total_hours)
        ws[f'C{current_row}'] = project.get("owner", "")
        
        for col in ['A', 'B', 'C']:
            cell = ws[f'{col}{current_row}']
            cell.font = project_font
            cell.fill = project_fill
            cell.border = border_thin
            if col == 'B':
                cell.alignment = Alignment(horizontal="center", vertical="center")
        
        current_row += 1
    
    # Processar macros e micros
    for macro_idx, macro in enumerate(macros):
        # Linha da macro
        ws[f'A{current_row}'] = macro["name"]
        ws[f'B{current_row}'] = macro_summaries[macro_idx]["duration_display"]
        ws[f'C{current_row}'] = macro.get("responsible", "")
        
        for col in ['A', 'B', 'C']:
            cell = ws[f'{col}{current_row}']
            cell.font = macro_font
            cell.fill = macro_fill
            cell.border = border_thin
            if col == 'B':
                cell.alignment = Alignment(horizontal="center", vertical="center")
        
        current_row += 1
        
        # Linhas das micros
        for micro in macro["micros"]:
            hours = float(micro["hours"])
            duration_display = hours_to_duration_display(hours)
            
            # Indentação no nome
            ws[f'A{current_row}'] = f"    {micro['name']}"
            ws[f'B{current_row}'] = duration_display
            ws[f'C{current_row}'] = micro.get("responsible", "")
            
            for col in ['A', 'B', 'C']:
                cell = ws[f'{col}{current_row}']
                cell.border = border_thin
                if col == 'B':
                    cell.alignment = Alignment(horizontal="center", vertical="center")
            
            current_row += 1
    
    # Gerar nome do arquivo
    project_name_clean = sanitize_filename(project["name"])
    timestamp = datetime.now().strftime("%Y-%m-%d")
    filename = f"Cronograma - {project_name_clean} - {timestamp}.xlsx"
    filepath = OUTPUT_DIR / filename
    
    # Salvar arquivo
    wb.save(filepath)
    logger.info(f"XLSX gerado: {filepath.name}")
    
    # Preparar summary
    summary = {
        "macro_count": len(macros),
        "micro_count": sum(m["micro_count"] for m in macro_summaries),
        "macros": macro_summaries
    }
    
    return filepath, summary, project_total_hours

# ========================================================
# SERVIDOR MCP
# ========================================================

# Inicializar FastMCP
mcp = FastMCP("cronograma-mcp")

@mcp.tool()
def gerar_xlsx(payload: dict) -> dict:
    """
    Gera um cronograma em formato XLSX a partir do payload JSON.
    
    Retorna base64 do arquivo e URL para download via HTTP.
    
    Regras:
    - Durações sempre em horas (formato HHH:MM:SS)
    - Macro SEMPRE deve conter pelo menos 1 micro
    - Macro duration = soma das micros
    - Projeto total = soma de todas as macros
    """
    try:
        logger.info("Iniciando geração de cronograma XLSX")
        
        # Limpar arquivos expirados
        cleanup_expired_files()
        
        # Validar payload
        is_valid, error_response = validate_payload(payload)
        if not is_valid:
            logger.warning(f"Validação falhou: {error_response['error_code']}")
            return error_response
        
        # Gerar XLSX
        filepath, summary, project_total_hours = generate_xlsx(payload)
        
        # Ler arquivo e converter para base64
        with open(filepath, "rb") as f:
            file_bytes = f.read()
            file_base64 = base64.b64encode(file_bytes).decode('utf-8')
        
        # Gerar token para download
        token = generate_token()
        expires_at = datetime.now() + timedelta(minutes=TTL_MINUTES)
        
        # Registrar arquivo
        file_registry[token] = {
            "filepath": str(filepath),
            "filename": filepath.name,
            "expires_at": expires_at
        }
        
        # Montar download_url
        download_url = f"{BASE_URL}/download/{token}"
        
        # Preparar resposta
        project = payload["project"]
        settings = payload.get("settings", {})
        
        response = {
            "ok": True,
            "format_version": settings.get("format_version", "1.0.0"),
            "project_name": project["name"],
            "project_total_hours": round(project_total_hours, 4),
            "project_total_duration_display": hours_to_duration_display(project_total_hours),
            "filename": filepath.name,
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "base64": file_base64,
            "download_url": download_url,
            "download_expires_at": expires_at.isoformat(),
            "summary": summary
        }
        
        logger.info(f"Cronograma gerado com sucesso: {filepath.name}")
        logger.info(f"Download disponível em: {download_url}")
        
        return response
        
    except Exception as e:
        logger.error(f"Erro interno ao gerar cronograma: {e}", exc_info=True)
        return {
            "ok": False,
            "error_code": "INTERNAL_ERROR",
            "message": f"Erro interno ao gerar cronograma: {str(e)}",
            "details": []
        }

@mcp.tool()
def validar(payload: dict) -> dict:
    """
    Valida o payload sem gerar o arquivo.
    Útil para verificar se o JSON está correto antes de gerar.
    """
    try:
        logger.info("Validando payload")
        
        is_valid, error_response = validate_payload(payload)
        
        if not is_valid:
            return error_response
        
        # Calcular totais para preview
        project_total_hours = 0.0
        macro_count = len(payload["macros"])
        micro_count = 0
        
        for macro in payload["macros"]:
            for micro in macro["micros"]:
                hours = float(micro["hours"])
                project_total_hours += hours
                micro_count += 1
        
        return {
            "ok": True,
            "message": "Payload válido",
            "preview": {
                "project_name": payload["project"]["name"],
                "project_total_hours": round(project_total_hours, 4),
                "project_total_duration_display": hours_to_duration_display(project_total_hours),
                "macro_count": macro_count,
                "micro_count": micro_count
            }
        }
        
    except Exception as e:
        logger.error(f"Erro ao validar payload: {e}", exc_info=True)
        return {
            "ok": False,
            "error_code": "INTERNAL_ERROR",
            "message": f"Erro ao validar: {str(e)}",
            "details": []
        }

@mcp.tool()
def health() -> dict:
    """
    Verifica o status do servidor MCP.
    """
    return {
        "ok": True,
        "service": "cronograma-mcp",
        "status": "healthy",
        "output_dir": str(OUTPUT_DIR),
        "max_rows": MAX_ROWS,
        "ttl_minutes": TTL_MINUTES,
        "active_files": len(file_registry)
    }

# ========================================================
# SERVIDOR HTTP (FastAPI)
# ========================================================

app = FastAPI(title="Cronograma MCP HTTP Server")

@app.get("/health")
async def http_health():
    """Endpoint de health check HTTP"""
    return {
        "ok": True,
        "service": "cronograma-mcp-http",
        "status": "healthy",
        "mcp_active": True
    }

@app.get("/download/{token}")
async def download_file(token: str):
    """
    Endpoint para download do arquivo XLSX via token
    """
    # Limpar arquivos expirados
    cleanup_expired_files()
    
    # Verificar se token existe
    if token not in file_registry:
        logger.warning(f"Token inválido ou expirado: {token[:10]}...")
        raise HTTPException(status_code=404, detail="Arquivo não encontrado ou expirado")
    
    file_info = file_registry[token]
    filepath = Path(file_info["filepath"])
    
    # Verificar se arquivo existe
    if not filepath.exists():
        logger.error(f"Arquivo não encontrado no disco: {filepath}")
        del file_registry[token]
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    logger.info(f"Download iniciado: {file_info['filename']}")
    
    # Retornar arquivo
    return FileResponse(
        path=str(filepath),
        filename=file_info["filename"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{file_info["filename"]}"'
        }
    )

# ========================================================
# MAIN
# ========================================================

async def run_mcp_server():
    """Executa o servidor MCP"""
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        logger.info("Servidor MCP iniciado (stdio)")
        await mcp.run(read_stream, write_stream)

def run_http_server():
    """Executa o servidor HTTP"""
    logger.info(f"Iniciando servidor HTTP na porta {HTTP_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=HTTP_PORT, log_level="info")

if __name__ == "__main__":
    import threading
    
    logger.info("=" * 60)
    logger.info("Cronograma MCP Server")
    logger.info("=" * 60)
    logger.info(f"OUTPUT_DIR: {OUTPUT_DIR}")
    logger.info(f"MAX_ROWS: {MAX_ROWS}")
    logger.info(f"TTL_MINUTES: {TTL_MINUTES}")
    logger.info(f"BASE_URL: {BASE_URL}")
    logger.info(f"HTTP_PORT: {HTTP_PORT}")
    logger.info("=" * 60)
    
    # Iniciar servidor HTTP em thread separada
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # Executar servidor MCP no thread principal
    try:
        asyncio.run(run_mcp_server())
    except KeyboardInterrupt:
        logger.info("Servidor encerrado pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)
