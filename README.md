# IOH Agentspace (`gemini-4-argon` & Netra Agent) Bridge for Google Antigravity

Connects **Google Antigravity** directly to IOH's **Gemini Enterprise (Agentspace)** instance (`https://agentspace.ioh.co.id` / `vertexaisearch.cloud.google`) using **Gemini 4 Argon (`gemini-4-argon`)** and custom IOH Agents (**Netra Agent**, **ACE Platform**, **Slides Agent**) so you can offload coding tasks, data/CVM/network analysis, and internal IOH Confluence/SharePoint/Jira searches without burning Antigravity quota.

Zero external Python dependencies required (uses Python 3 standard library only).

---

## Quick Setup on Any PC

### 1. Clone this repository
```powershell
cd $HOME\Documents
git clone <YOUR_GIT_REMOTE_URL> agentspace-bridge
cd agentspace-bridge
```

### 2. Register the MCP Server in Antigravity
Run the setup script once to automatically add `ioh-agentspace` to `~/.gemini/config/mcp_config.json` (works on both Windows and macOS):
```bash
# macOS / Linux
/opt/homebrew/bin/python3 setup_mcp.py

# Windows
python setup_mcp.py
```

### 3. Automatic Browser Token Refresh (`./agentspace_xsrf.json`)
Because IOH Agentspace uses Workforce Identity Federation (BYOID), requests are authenticated using a short-lived HS256 JWT signed by your browser session's `getoxsrf` key (~1 hour validity).

- **Isolated Work Profile (`.auth_profile/`):** `agentspace_cli.py` uses an isolated browser profile folder (`./.auth_profile/`) separate from your personal browser profile. On macOS it defaults to **Google Chrome (`chrome`)**; on Windows it defaults to **Microsoft Edge (`msedge`)** (with automatic fallback across both).
- **Silent Headless Refresh + Interactive Fallback:** Whenever `./agentspace_xsrf.json` is missing or expires (`HTTP 401`), `agentspace_cli.py` and the MCP server first try a **15-second silent headless refresh** in the background if `.auth_profile/` is already logged in (0 screen interruption). If first-time login or 2FA is needed, it automatically opens a visible browser window (`https://agentspace.ioh.co.id`), grabs `/auth/getoxsrf` + `csesidx`, saves `./agentspace_xsrf.json`, and closes the window.
- **Manual Trigger:** You can also trigger a token refresh at any time via:
  ```bash
  python3 agentspace_cli.py --refresh-token
  ```

---

## Usage

### Option A: Inside Antigravity (via MCP Tools)
Once `setup_mcp.py` has been run, Antigravity has four MCP tools:
- `agentspace_ask`: Query `gemini-4-argon` or an agent (`agent="netra"`, `agent="ace"`, `agent="slides"`). Set `delete_session_after=true` to automatically delete the chat after completion.
- `agentspace_delete_session`: Delete an existing chat session by ID (`session_id="..."`).
- `agentspace_list_sessions`: List recent chat sessions (`limit=20`).
- `agentspace_refresh_token`: Pop open a browser window to refresh `./agentspace_xsrf.json`.

### Option B: Direct CLI (`agentspace_cli.py`)
```powershell
# Refresh and save ./agentspace_xsrf.json via browser pop-up
python agentspace_cli.py --refresh-token

# Fast coding & reasoning (~3.5s, skips Confluence/SharePoint search)
python agentspace_cli.py "Write a Python script to parse logs"

# Auto-delete the chat session immediately after getting the answer (--ephemeral / --delete-after)
python agentspace_cli.py "One-off question" --ephemeral

# Maximum AGY Token-Saving Mode: attach local files directly from disk (-f) and save long outputs
# into a session-isolated folder (./outputs/chat_<session_tag>/) with only a short preview in stdout:
python agentspace_cli.py "Optimize this SQL" -f raw_query.sql -o optimized.sql --session-tag bba4da86 --summary-only --ephemeral

# Call Netra Agent (17783079275007264980) and auto-delete the chat afterward
python agentspace_cli.py "Check CVM RGU90 definition" --agent netra --ephemeral

# Enterprise Search mode (searches IOH Confluence, SharePoint, Jira, OneDrive, ServiceNow)
python agentspace_cli.py "Find architecture docs for..." --search

# List recent chat sessions
python agentspace_cli.py --list-sessions

# Delete a specific chat session when no longer needed
python agentspace_cli.py --delete-session 6300471525476906605
```
