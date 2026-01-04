from fastapi import FastAPI
from router.router import route

app = FastAPI(title="Blueprint MCP Core")

@app.post("/mcp")
def mcp_entrypoint(request: dict):
    return route(request)

@app.get("/health")
def health():
    return {"status": "ok"}
