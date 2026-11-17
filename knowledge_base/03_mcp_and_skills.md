# 3. MCP Server & Antigravity Skills

## Automated Setup (`setup_mcp.py`)

Run `python setup_mcp.py` (or `python3 setup_mcp.py` on macOS/Linux) once after cloning:
1. Detects the Python interpreter with `playwright` installed (`.venv`, Homebrew, or system Python).
2. Registers `ioh-agentspace` in `~/.gemini/config/mcp_config.json` pointing to `agentspace_mcp_server.py`.
3. Links or copies `.agents/skills/ioh-agentspace/SKILL.md` into `~/.gemini/config/skills/ioh-agentspace/`.

*(Reload or restart Antigravity after running `setup_mcp.py` so it picks up the new MCP tools.)*

---

## MCP Tools (`agentspace_mcp_server.py`)

| Tool | Description |
| :--- | :--- |
| `agentspace_ask` | Query `gemini-4-argon`, `gemini-4-carbon`, IOH Agents (`netra`, `ace`, `slides`, `office-creator-2`), or Enterprise Search (`enable_enterprise_search=True`). Supports `input_files`, `output_filename`, `session_tag`, and `summary_only`. |
| `agentspace_export_slides` | Export Canvas/Slides artifacts or native `python-pptx` scripts from a session to `.pptx` / `.pdf` in `./outputs/chat_<session_tag>/`. |
| `agentspace_list_sessions` | List recent chat sessions (`limit=20`). |
| `agentspace_delete_session` | Delete a specific chat session by ID. |
| `agentspace_finish_task` | Delete tracked media generation sessions for a finished `session_tag` while preserving data/search/slides sessions. |
| `agentspace_cleanup_media_sessions` | Scan recent sessions and remove standalone AI image/video generation clutter from the Web UI sidebar. |
| `agentspace_refresh_token` | Refresh `./agentspace_xsrf.json` via headless/interactive browser login. |

---

## Workspace Skills (`.agents/skills/`)

- **`ioh-agentspace`**: Governs IOH enterprise data queries (`netra`, `ace`), federated search (`--search`), Mode 3A/3B presentations, and media session cleanup. Strictly prohibits offloading general local coding/debugging.
- **`agentspace-advisor`**: Governs **Agentspace Advisor Mode** (`--model gemini-4-argon` / `gemini-4-carbon`, `--thinking HIGH`, `-f <file>`, `-o advisor_plan.md --summary-only`) for deep architectural planning when Antigravity is running a lighter local model.
