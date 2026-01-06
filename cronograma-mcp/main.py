#!/usr/bin/env python3
"""
Servidor de Cronograma (produção)
- HTTP-first (FastAPI + Uvicorn) para uso em Docker/OpenWebUI
- Download via /download/{token}
- Endpoints /cronograma/generate e /cronograma/validate
- Modo MCP stdio opcional via CRONOGRAMA_RUN_MODE=stdio (para execução por cliente MCP)
"""

import os
import sys
import re
import logging
import base64
import secrets
import asyncio
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

# MCP (mantido para reuso de lógica e compatibilidade futura)
from mcp.server.fastmcp import FastMCP

# XLSX
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side


# ========================================================
# CONFIG
# ========================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cronograma-mcp")

OUTPUT_DIR = Path(os.getenv("CRONOGRAMA_OUTPUT_DIR", "./outputs"))
MAX_ROWS = int(os.getenv("CRONOGRAMA_MAX_ROWS", "500"))
TTL_MINUTES = int(os.getenv("CRONOGRAMA_TTL_MINUTES", "30"))
BASE_URL = os.getenv("CRONOGRAMA_BASE_URL", "http://localhost:8000").rstrip("/")
HTTP_PORT = int(os.getenv("CRONOGRAMA_HTTP_PORT", "8000"))

# Modo de execução:
# - http  (padrão para Docker/produção)
# - stdio (apenas quando um cliente MCP spawnar o processo)
RUN_MODE = os.getenv("CRONOGRAMA_RUN_MODE", "http").strip().lower()

# Cleanup periódico (segundos)
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CRONOGRAMA_CLEANUP_INTERVAL_SECONDS", "60"))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Registry: token -> {filepath, filename, expires_at}
file_registry: Dict[str, Dict[str, Any]] = {}
registry_lock = threading.Lock()


# ========================================================
# UTIL
# ========================================================

def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:200] if sanitized else "Cronograma"

def hours_to_duration_display(hours: float) -> str:
    """
    Converte horas decimais para HHH:MM:SS (sem virar dias).
    Ex: 247.6667 -> 247:40:00
    """
    if hours is None or hours < 0:
        hours = 0.0
    total_seconds = int(round(hours * 3600))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:d}:{m:02d}:{s:02d}"

def generate_token() -> str:
    return secrets.token_urlsafe(32)

def cleanup_expired_files() -> None:
    now = datetime.now()
    expired_tokens: List[str] = []

    with registry_lock:
        for token, info in list(file_registry.items()):
            expires_at = info.get("expires_at")
            if expires_at and now > expires_at:
                expired_tokens.append(token)

        for token in expired_tokens:
            info = file_registry.pop(token, None)
            if not info:
                continue
            try:
                filepath = Path(info["filepath"])
                if filepath.exists():
                    filepath.unlink()
                    logger.info(f"Arquivo expirado removido: {filepath.name}")
            except Exception as e:
                logger.error(f"Erro ao remover arquivo expirado: {e}")


# ========================================================
# VALIDATION
# ========================================================

def validate_payload(payload: dict) -> Tuple[bool, Optional[dict]]:
    errors = []

    if not isinstance(payload, dict):
        return False, {
            "ok": False,
            "error_code": "VALIDATION_ERROR",
            "message": "Payload deve ser um objeto JSON",
            "details": [{"field": "payload", "issue": "tipo inválido"}],
        }

    # project
    project = payload.get("project")
    if not project:
        errors.append({"field": "project", "issue": "campo obrigatório"})
    else:
        if not project.get("name"):
            errors.append({"field": "project.name", "issue": "nome do projeto obrigatório"})

    # macros
    macros = payload.get("macros")
    if macros is None:
        errors.append({"field": "macros", "issue": "campo obrigatório"})
    elif not isinstance(macros, list) or len(macros) == 0:
        errors.append({"field": "macros", "issue": "deve conter pelo menos 1 macro"})
    else:
        total_rows = 1  # linha do projeto

        for idx, macro in enumerate(macros):
            if not isinstance(macro, dict):
                errors.append({"field": f"macros[{idx}]", "issue": "macro deve ser objeto"})
                continue

            if not macro.get("name"):
                errors.append({"field": f"macros[{idx}].name", "issue": "nome da macro obrigatório"})

            micros = macro.get("micros")
            # REGRA CRÍTICA
            if not isinstance(micros, list) or len(micros) == 0:
                errors.append({
                    "field": f"macros[{idx}].micros",
                    "issue": "macro SEMPRE deve conter pelo menos 1 micro (regra obrigatória)",
                })
                continue

            total_rows += 1  # macro
            for midx, micro in enumerate(micros):
                total_rows += 1
                if not isinstance(micro, dict):
                    errors.append({"field": f"macros[{idx}].micros[{midx}]", "issue": "micro deve ser objeto"})
                    continue

                if not micro.get("name"):
                    errors.append({"field": f"macros[{idx}].micros[{midx}].name", "issue": "nome da micro obrigatório"})

                if "hours" not in micro:
                    errors.append({"field": f"macros[{idx}].micros[{midx}].hours", "issue": "hours obrigatório"})
                else:
                    try:
                        h = float(micro["hours"])
                        if h <= 0:
                            errors.append({"field": f"macros[{idx}].micros[{midx}].hours", "issue": "hours deve ser maior que 0"})
                    except (ValueError, TypeError):
                        errors.append({"field": f"macros[{idx}].micros[{midx}].hours", "issue": "hours deve ser numérico"})

        settings = payload.get("settings", {}) if isinstance(payload.get("settings", {}), dict) else {}
        max_rows_limit = int(settings.get("max_rows", MAX_ROWS))

        if total_rows > max_rows_limit:
            errors.append({"field": "total_rows", "issue": f"total de linhas ({total_rows}) excede o limite ({max_rows_limit})"})
            return False, {
                "ok": False,
                "error_code": "MAX_ROWS_EXCEEDED",
                "message": f"O cronograma possui {total_rows} linhas, excedendo o limite de {max_rows_limit}",
                "details": errors,
            }

    if errors:
        return False, {
            "ok": False,
            "error_code": "VALIDATION_ERROR",
            "message": "Erro de validação no payload",
            "details": errors,
        }

    return True, None


# ========================================================
# XLSX GEN
# ========================================================

def generate_xlsx(payload: dict) -> Tuple[Path, dict, float]:
    project = payload["project"]
    settings = payload.get("settings", {}) if isinstance(payload.get("settings", {}), dict) else {}
    macros = payload["macros"]

    sheet_name = settings.get("sheet_name", "Planilha1")
    include_project_row = bool(settings.get("include_project_row", True))

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    # styles
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    project_font = Font(bold=True, size=11)
    project_fill = PatternFill(start_color="A9A9A9", end_color="A9A9A9", fill_type="solid")

    macro_font = Font(bold=True, size=10)
    macro_fill = PatternFill(start_color="E8E8E8", end_color="E8E8E8", fill_type="solid")

    border_thin = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    ws.column_dimensions["A"].width = 70
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 22

    # header row
    ws["A1"] = "Nome da Tarefa"
    ws["B1"] = "Duration"
    ws["C1"] = "Responsável"

    for col in ["A", "B", "C"]:
        cell = ws[f"{col}1"]
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border_thin
        cell.alignment = header_alignment if col != "A" else Alignment(horizontal="left", vertical="center")

    ws.freeze_panes = "A2"
    current_row = 2

    # totals
    project_total_hours = 0.0
    macro_summaries = []

    for macro in macros:
        macro_total_hours = 0.0
        micro_count = 0
        for micro in macro["micros"]:
            h = float(micro["hours"])
            macro_total_hours += h
            micro_count += 1

        project_total_hours += macro_total_hours
        macro_summaries.append({
            "name": macro["name"],
            "hours": round(macro_total_hours, 4),
            "duration_display": hours_to_duration_display(macro_total_hours),
            "micro_count": micro_count,
        })

    # project row
    if include_project_row:
        ws[f"A{current_row}"] = project["name"]
        ws[f"B{current_row}"] = hours_to_duration_display(project_total_hours)  # texto
        ws[f"C{current_row}"] = project.get("owner", "")

        for col in ["A", "B", "C"]:
            cell = ws[f"{col}{current_row}"]
            cell.font = project_font
            cell.fill = project_fill
            cell.border = border_thin
            if col == "B":
                cell.alignment = Alignment(horizontal="center", vertical="center")
        current_row += 1

    # macros + micros
    for macro_idx, macro in enumerate(macros):
        ws[f"A{current_row}"] = macro["name"]
        ws[f"B{current_row}"] = macro_summaries[macro_idx]["duration_display"]  # texto
        ws[f"C{current_row}"] = macro.get("responsible", "")

        for col in ["A", "B", "C"]:
            cell = ws[f"{col}{current_row}"]
            cell.font = macro_font
            cell.fill = macro_fill
            cell.border = border_thin
            if col == "B":
                cell.alignment = Alignment(horizontal="center", vertical="center")

        current_row += 1

        for micro in macro["micros"]:
            hours = float(micro["hours"])
            ws[f"A{current_row}"] = f"    {micro['name']}"
            ws[f"B{current_row}"] = hours_to_duration_display(hours)  # texto
            ws[f"C{current_row}"] = micro.get("responsible", "")

            for col in ["A", "B", "C"]:
                cell = ws[f"{col}{current_row}"]
                cell.border = border_thin
                if col == "B":
                    cell.alignment = Alignment(horizontal="center", vertical="center")
            current_row += 1

    project_name_clean = sanitize_filename(project["name"])
    timestamp = datetime.now().strftime("%Y-%m-%d")
    filename = f"Cronograma - {project_name_clean} - {timestamp}.xlsx"
    filepath = OUTPUT_DIR / filename

    wb.save(filepath)
    logger.info(f"XLSX gerado: {filepath.name}")

    summary = {
        "macro_count": len(macros),
        "micro_count": sum(m["micro_count"] for m in macro_summaries),
        "macros": macro_summaries,
    }

    return filepath, summary, project_total_hours


# ========================================================
# CORE SERVICE (compartilhado por MCP e HTTP)
# ========================================================

def build_generation_response(payload: dict) -> dict:
    logger.info("Iniciando geração de cronograma XLSX")

    cleanup_expired_files()

    is_valid, error = validate_payload(payload)
    if not is_valid:
        logger.warning(f"Validação falhou: {error['error_code']}")
        return error

    filepath, summary, project_total_hours = generate_xlsx(payload)

    with open(filepath, "rb") as f:
        file_base64 = base64.b64encode(f.read()).decode("utf-8")

    token = generate_token()
    expires_at = datetime.now() + timedelta(minutes=TTL_MINUTES)

    with registry_lock:
        file_registry[token] = {
            "filepath": str(filepath),
            "filename": filepath.name,
            "expires_at": expires_at,
        }

    download_url = f"{BASE_URL}/download/{token}"

    project = payload["project"]
    settings = payload.get("settings", {}) if isinstance(payload.get("settings", {}), dict) else {}

    resp = {
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
        "summary": summary,
    }

    logger.info(f"Cronograma gerado com sucesso: {filepath.name}")
    logger.info(f"Download disponível em: {download_url}")
    return resp


def build_validate_response(payload: dict) -> dict:
    logger.info("Validando payload (sem gerar arquivo)")
    is_valid, error = validate_payload(payload)
    if not is_valid:
        return error

    project_total_hours = 0.0
    macro_count = len(payload["macros"])
    micro_count = 0

    for macro in payload["macros"]:
        for micro in macro["micros"]:
            project_total_hours += float(micro["hours"])
            micro_count += 1

    return {
        "ok": True,
        "message": "Payload válido",
        "preview": {
            "project_name": payload["project"]["name"],
            "project_total_hours": round(project_total_hours, 4),
            "project_total_duration_display": hours_to_duration_display(project_total_hours),
            "macro_count": macro_count,
            "micro_count": micro_count,
        },
    }


# ========================================================
# MCP (opcional)
# ========================================================

mcp = FastMCP("cronograma-mcp")

@mcp.tool()
def gerar_xlsx(payload: dict) -> dict:
    return build_generation_response(payload)

@mcp.tool()
def validar(payload: dict) -> dict:
    return build_validate_response(payload)

@mcp.tool()
def health() -> dict:
    with registry_lock:
        active_files = len(file_registry)
    return {
        "ok": True,
        "service": "cronograma-mcp",
        "status": "healthy",
        "output_dir": str(OUTPUT_DIR),
        "max_rows": MAX_ROWS,
        "ttl_minutes": TTL_MINUTES,
        "active_files": active_files,
        "run_mode": RUN_MODE,
    }


# ========================================================
# HTTP (produção)
# ========================================================

app = FastAPI(title="Cronograma Server (HTTP-first)")

@app.get("/health")
async def http_health():
    return {
        "ok": True,
        "service": "cronograma-http",
        "status": "healthy",
        "run_mode": RUN_MODE,
    }

@app.post("/cronograma/generate")
async def http_generate(payload: dict = Body(...)):
    resp = build_generation_response(payload)
    status = 200 if resp.get("ok") else 400
    return JSONResponse(status_code=status, content=resp)

@app.post("/cronograma/validate")
async def http_validate(payload: dict = Body(...)):
    resp = build_validate_response(payload)
    status = 200 if resp.get("ok") else 400
    return JSONResponse(status_code=status, content=resp)

@app.get("/download/{token}")
async def download_file(token: str):
    cleanup_expired_files()

    with registry_lock:
        info = file_registry.get(token)

    if not info:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado ou expirado")

    filepath = Path(info["filepath"])
    if not filepath.exists():
        with registry_lock:
            file_registry.pop(token, None)
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    logger.info(f"Download iniciado: {info['filename']}")
    return FileResponse(
        path=str(filepath),
        filename=info["filename"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{info["filename"]}"'},
    )

@app.on_event("startup")
async def on_startup():
    logger.info("HTTP server startup - iniciando tarefa de cleanup periódico")

    async def _periodic_cleanup():
        while True:
            try:
                cleanup_expired_files()
            except Exception as e:
                logger.error(f"Erro no cleanup periódico: {e}")
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

    # roda em background no mesmo loop do FastAPI
    asyncio.create_task(_periodic_cleanup())


# ========================================================
# MAIN
# ========================================================

async def run_mcp_stdio():
    """
    Modo MCP stdio: SOMENTE quando um cliente MCP spawnar este processo.
    Não use isso como daemon em Docker.
    """
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        logger.info("MCP stdio iniciado")
        # Observação: dependendo da versão do mcp/fastmcp, o transporte stdio pode variar.
        # Se o cliente MCP for o responsável por spawn, isso funciona como esperado.
        await mcp.run(read_stream, write_stream)

def run_http():
    logger.info(f"Iniciando HTTP na porta {HTTP_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=HTTP_PORT, log_level="info")

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Cronograma Server")
    logger.info("=" * 60)
    logger.info(f"RUN_MODE: {RUN_MODE}")
    logger.info(f"OUTPUT_DIR: {OUTPUT_DIR}")
    logger.info(f"MAX_ROWS: {MAX_ROWS}")
    logger.info(f"TTL_MINUTES: {TTL_MINUTES}")
    logger.info(f"BASE_URL: {BASE_URL}")
    logger.info(f"HTTP_PORT: {HTTP_PORT}")
    logger.info("=" * 60)

    if RUN_MODE == "stdio":
        # Atenção: use somente se um cliente MCP estiver conectando via stdio
        try:
            asyncio.run(run_mcp_stdio())
        except KeyboardInterrupt:
            logger.info("Encerrado pelo usuário")
        except Exception as e:
            logger.error(f"Erro fatal no MCP stdio: {e}", exc_info=True)
            sys.exit(1)
    else:
        # Produção: HTTP-first
        run_http()
