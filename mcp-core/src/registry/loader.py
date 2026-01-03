import yaml

AGENTS_FILE = "/app/registry/agents.yaml"

def load_agents():
    with open(AGENTS_FILE, "r") as f:
        data = yaml.safe_load(f)
    return {a["name"]: a for a in data.get("agents", [])}
