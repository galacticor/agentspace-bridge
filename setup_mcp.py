#!/usr/bin/env python3
"""
Automatically registers `ioh-agentspace` in Google Antigravity's global ~/.gemini/config/mcp_config.json
on any Windows, macOS, or Linux machine.
"""
import json
import os
import sys

def main():
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_server_script = os.path.join(repo_dir, "agentspace_mcp_server.py")

    config_dir = os.path.join(os.path.expanduser("~"), ".gemini", "config")
    os.makedirs(config_dir, exist_ok=True)
    mcp_config_path = os.path.join(config_dir, "mcp_config.json")

    if os.path.exists(mcp_config_path):
        with open(mcp_config_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {"mcpServers": {}}
    else:
        data = {"mcpServers": {}}

    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    data["mcpServers"]["ioh-agentspace"] = {
        "command": sys.executable or "python",
        "args": [mcp_server_script],
    }

    with open(mcp_config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Registered 'ioh-agentspace' in {mcp_config_path}")
    print(f"Pointing to: {mcp_server_script}")

if __name__ == "__main__":
    main()
