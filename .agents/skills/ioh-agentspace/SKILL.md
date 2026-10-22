---
name: ioh-agentspace
description: >-
  Offload coding tasks, analysis, reasoning, or enterprise knowledge base searches
  (IOH Confluence, SharePoint, Jira, Google Drive) to IOH's Gemini Enterprise
  (Agentspace) running Gemini 4 Argon (gemini-4-argon). Use whenever the user
  asks to run prompts via Agentspace, use Gemini 4 Argon, reduce Antigravity quota,
  or search internal IOH documentation.
---

# IOH Agentspace (`gemini-4-argon`) Skill

## Overview
This skill connects Antigravity to IOH's Gemini Enterprise (Agentspace) via `agentspace_cli.py` and the `ioh-agentspace` MCP server.

## How to Execute Queries

### 1. Fast Mode (Coding, Reasoning, Drafting — ~3 seconds)
Skips slow enterprise data store federated search and queries `gemini-4-argon` directly:
```powershell
python "agentspace_cli.py" "<prompt>" --thinking MEDIUM
```
*(Or call the `agentspace_ask` MCP tool with `enable_enterprise_search: false`.)*

### 2. Enterprise Search Mode (Confluence, SharePoint, Jira, Drive)
Searches IOH's connected enterprise data stores before synthesizing an answer:
```powershell
python "agentspace_cli.py" "<search query>" --search
```
*(Or call the `agentspace_ask` MCP tool with `enable_enterprise_search: true`.)*

### 3. Multi-Turn Sessions
To continue an existing conversation on Agentspace, pass `--json` on the first call to capture the `session` ID (`collections/default_collection/engines/.../sessions/...`), then pass `--session "<session_id>"` on follow-up calls.

## Handling Expired XSRF Tokens (`HTTP 401`)
1. **Never** ask the user to paste their `xsrfToken` into the chat.
2. Ask the user to download a fresh `getoxsrf` response from their logged-in browser tab:
   `https://vertexaisearch.cloud.google/auth/getoxsrf?csesidx=`
   into `~/Downloads/json.txt` (or save via clipboard to `$env:TEMP\agentspace_xsrf.json`).
