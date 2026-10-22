# IOH Agentspace (`gemini-4-argon`) Bridge for Google Antigravity

Connects **Google Antigravity** directly to IOH's **Gemini Enterprise (Agentspace)** instance (`https://agentspace.ioh.co.id` / `vertexaisearch.cloud.google`) using **Gemini 4 Argon (`gemini-4-argon`)** so you can offload coding tasks, reasoning, and internal IOH Confluence/SharePoint/Jira searches without burning Antigravity quota.

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
Run the setup script once to automatically add `ioh-agentspace` to `~/.gemini/config/mcp_config.json`:
```powershell
python setup_mcp.py
```

### 3. Download Your Session Key (`getoxsrf`)
Because IOH Agentspace uses Workforce Identity Federation (BYOID) without end-user GCP project IAM roles, requests are authenticated using a short-lived HS256 JWT signed by your browser session's `getoxsrf` key:

1. Log into `https://agentspace.ioh.co.id` in your browser.
2. Check the URL bar for your `csesidx` number (e.g., `?csesidx=`).
3. Open this URL in the same browser window (replace `<CSESIDX>` if different):
   ```text
   https://vertexaisearch.cloud.google/auth/getoxsrf?csesidx=
   ```
   *(Or open DevTools `F12` -> Console and run:)*
   ```javascript
   fetch(`/auth/getoxsrf?csesidx=${new URLSearchParams(location.search).get('csesidx')}`).then(r => r.text()).then(t => { copy(t); console.log("Copied!"); })
   ```
4. Save the downloaded file as **`~/Downloads/json.txt`** (or `./agentspace_xsrf.json` inside this folder, or `%TEMP%\agentspace_xsrf.json`).
   - If you used the Console `copy(t)` snippet, run in PowerShell:
     ```powershell
     Get-Clipboard | Set-Content -Path "$env:TEMP\agentspace_xsrf.json" -Encoding UTF8
     ```
   - If your `csesidx` on the other PC is different from ``, pass `--csesidx <NUMBER>` or set `$env:AGENTSPACE_CSESIDX="<NUMBER>"`.

---

## Usage

### Option A: Inside Antigravity (via MCP Tool `agentspace_ask`)
Once `setup_mcp.py` has been run, Antigravity automatically has the `agentspace_ask` tool. Just ask Antigravity in chat:
- *"Use `agentspace_ask` to write/analyze..."*
- *"Use `agentspace_ask` with `enable_enterprise_search=true` to search IOH Confluence for..."*

### Option B: Direct CLI (`agentspace_cli.py`)
```powershell
# Fast coding & reasoning (~3.5s, skips Confluence/SharePoint search)
python agentspace_cli.py "Write a Python script to parse logs"

# Enterprise Search mode (searches IOH Confluence, SharePoint, Jira, Drive + Web)
python agentspace_cli.py "Find architecture docs for..." --search

# Choose thinking level (LOW, MEDIUM, HIGH, NONE) or output JSON
python agentspace_cli.py "Complex architecture question" --thinking HIGH --json
```
