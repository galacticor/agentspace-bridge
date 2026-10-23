#!/usr/bin/env python3
"""
Automatically registers `ioh-agentspace` in Google Antigravity's global ~/.gemini/config/mcp_config.json
on any Windows, macOS, or Linux machine.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def _resolve_python_executable() -> str:
    """
    Picks a Python interpreter that has `playwright` installed (e.g., local `.venv`,
    Homebrew `/opt/homebrew/bin/python3` on macOS if `/usr/bin/python3` was used),
    while remaining 100% compatible with Windows (`sys.executable`).
    """
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    venv_win = os.path.join(repo_dir, ".venv", "Scripts", "python.exe")
    venv_unix = os.path.join(repo_dir, ".venv", "bin", "python")

    candidates = [venv_win, venv_unix, sys.executable]
    if sys.platform == "darwin":
        candidates = [venv_unix, "/opt/homebrew/bin/python3", "/usr/local/bin/python3", sys.executable]
    elif sys.platform != "win32":
        candidates = [venv_unix, sys.executable, "/usr/local/bin/python3", "/usr/bin/python3"]

    for cand in candidates:
        if cand and os.path.isfile(cand):
            try:
                res = subprocess.run(
                    [cand, "-c", "import playwright"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                if res.returncode == 0:
                    return cand
            except Exception:
                continue
    return sys.executable or "python"


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

    python_cmd = _resolve_python_executable()
    server_entry = {
        "command": python_cmd,
        "args": [mcp_server_script],
    }
    if os.name != "nt":
        server_entry["env"] = {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        }

    data["mcpServers"]["ioh-agentspace"] = server_entry

    with open(mcp_config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Registered 'ioh-agentspace' in {mcp_config_path}")
    print(f"  Python : {python_cmd}")
    print(f"  Server : {mcp_server_script}")

    # Link ~/.gemini/config/skills/ioh-agentspace -> <repo>/.agents/skills/ioh-agentspace
    # Uses a live symlink on macOS/Linux (and Windows when allowed) so `git pull` or local edits
    # never require manual syncing. Falls back to file copy on Windows if symlinks are restricted.
    src_skill_dir = os.path.join(repo_dir, ".agents", "skills", "ioh-agentspace")
    src_skill_md = os.path.join(src_skill_dir, "SKILL.md")
    if os.path.isfile(src_skill_md):
        skills_root = os.path.join(config_dir, "skills")
        os.makedirs(skills_root, exist_ok=True)
        dst_skill_dir = os.path.join(skills_root, "ioh-agentspace")

        if os.path.islink(dst_skill_dir):
            os.unlink(dst_skill_dir)
        elif os.path.isdir(dst_skill_dir):
            shutil.rmtree(dst_skill_dir)

        try:
            os.symlink(src_skill_dir, dst_skill_dir, target_is_directory=True)
            print(f"  Skill  : {dst_skill_dir} -> {src_skill_dir} (live symlink, zero sync needed)")
        except OSError:
            os.makedirs(dst_skill_dir, exist_ok=True)
            shutil.copy2(src_skill_md, os.path.join(dst_skill_dir, "SKILL.md"))
            print(f"  Skill  : {os.path.join(dst_skill_dir, 'SKILL.md')} (copied; re-run setup_mcp.py after updates)")


if __name__ == "__main__":
    main()
