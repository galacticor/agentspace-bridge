---
name: ioh-agentspace
description: >-
  Offload coding tasks, analysis, reasoning, specialized agent queries (Netra Agent,
  ACE Platform, Slides Agent), or enterprise knowledge base searches (IOH Confluence,
  SharePoint, Jira, OneDrive, ServiceNow) to IOH's Gemini Enterprise (Agentspace)
  running Gemini 4 Argon (gemini-4-argon), and manage/delete chat sessions.
---

# IOH Agentspace (`gemini-4-argon` & Netra Agent) Skill

## Overview
This skill connects Antigravity to IOH's Gemini Enterprise (Agentspace) via `agentspace_cli.py` and the `ioh-agentspace` MCP server.

## How to Execute Queries

### 1. Fast Mode (`gemini-4-argon` — ~3 seconds)
Skips slow enterprise data store federated search and queries `gemini-4-argon` directly. Add `--ephemeral` (`--delete-after`) if the chat session is one-off and should be deleted immediately after:
```powershell
python "agentspace_cli.py" "<prompt>" --thinking MEDIUM --ephemeral
```
*(Or call the `agentspace_ask` MCP tool with `enable_enterprise_search: false, delete_session_after: true`.)*

### 2. Calling Netra Agent (or Other Custom IOH Agents)
Pass `--agent netra` (maps to Agent ID `17783079275007264980`, which coordinates `agent_cvm`, `agent_user_network_analytics`, `agent_techno`, `agent_export`, `agent_user_analytics`):
```powershell
python "agentspace_cli.py" "<netra query>" --agent netra --ephemeral
```
Other built-in aliases: `ace` (`8461818071814491910`), `slides` (`17216682253898748109`), `agb` (`18420663427156982501`), `catalyst` (`app_catalyst_agent`).

### 3. Enterprise Search Mode (Confluence, SharePoint, Jira, OneDrive, ServiceNow)
```powershell
python "agentspace_cli.py" "<search query>" --search --ephemeral
```

### 4. Managing & Deleting Chat Sessions
- **Auto-delete after a single turn:** Pass `--ephemeral` (or `--delete-after`) on CLI, or `delete_session_after=True` in `agentspace_ask`.
- **List recent sessions:**
  ```powershell
  python "agentspace_cli.py" --list-sessions --limit 20
  ```
- **Delete a specific session when done:**
  ```powershell
  python "agentspace_cli.py" --delete-session "<session_id_or_full_name>"
  ```
  *(Or call `agentspace_delete_session(session_id="...")` via MCP.)*

## Handling Expired XSRF Tokens (`HTTP 401`)
1. **Never** ask the user to paste their `xsrfToken` into the chat.
2. `agentspace_cli.py` and the `ioh-agentspace` MCP server **automatically** pop open a browser window (`https://agentspace.ioh.co.id`) whenever the token is missing or expires (`HTTP 401`), save the refreshed token to `./agentspace_xsrf.json` inside the project folder, and retry the request.
3. You can also explicitly trigger a refresh via `python "agentspace_cli.py" --refresh-token` or the `agentspace_refresh_token` MCP tool.
