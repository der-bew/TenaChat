#!/usr/bin/env python3
import sys

sys.path.insert(
    0, "/home/derbew/Desktop/Projects/ethiopian-women-health-chatbot/backend"
)

print("Step 1: Loading config...")
from app.config import load_config

load_config()
print("Config loaded!")

print("\nStep 2: Testing graph import...")
try:
    from app.rag.graph import agent_graph

    print("Graph imported!")
    print(f"Graph: {agent_graph}")
except Exception as e:
    print(f"Error importing graph: {e}")
    import traceback

    traceback.print_exc()

print("\nStep 3: Testing chat endpoint...")
try:
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    response = client.get("/health")
    print(f"Health check: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
