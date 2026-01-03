from typing import Dict, Any

class MCPRequest:
    agent: str
    action: str
    payload: Dict[str, Any]

class MCPResponse:
    success: bool
    data: Dict[str, Any]
    error: str | None
