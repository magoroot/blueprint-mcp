import requests
from registry.loader import load_agents

agents = load_agents()

def route(request: dict):
    agent_name = request.get("agent")

    if agent_name not in agents:
        return {
            "success": False,
            "error": f"Agent '{agent_name}' not registered"
        }

    agent = agents[agent_name]

    try:
        resp = requests.post(
            agent["endpoint"],
            json=request.get("payload", {}),
            timeout=agent.get("timeout_ms", 15000) / 1000
        )
        return {
            "success": True,
            "data": resp.json()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

