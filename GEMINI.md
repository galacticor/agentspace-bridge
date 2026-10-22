# IOH Agentspace (`gemini-4-argon`) Bridge — Workspace Knowledge Base & Rules

When working in this workspace (`agentspace-bridge`), you have direct access to **IOH's Gemini Enterprise (Agentspace)** instance (`https://agentspace.ioh.co.id` / `vertexaisearch.cloud.google`) powered by **Gemini 4 Argon (`gemini-4-argon`)**.

## 1. Purpose of This Project
This workspace bridges **Google Antigravity** with **IOH Agentspace** so that:
1. Antigravity can offload coding, drafting, analysis, and reasoning tasks to **Gemini 4 Argon (`gemini-4-argon`)** to save Antigravity usage quota.
2. Antigravity can query internal IOH enterprise connectors (**Confluence, SharePoint, Jira, Google Drive**) via Agentspace's federated search.

---

## 2. Architecture & Technical Knowledge Base

- **Target Endpoint:** `https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetStreamAssist` (and `lookupWidgetConfig`)
- **Widget Config ID (`cid`):** `384c42b0-2885-415a-82d5-f2babc063b6e`
- **Underlying GCP Engine:** `projects/195467123768/locations/global/collections/default_collection/engines/enterprise-search-17429648_1742964839282`
- **Model ID:** `gemini-4-argon` (supports `thinkingLevel`: `"LOW"`, `"MEDIUM"`, `"HIGH"`)
- **Authentication Mechanism (BYOID / Workforce Identity):**
  - Standard GCP ADC OAuth tokens (`ya29...`) fail with `403 PERMISSION_DENIED` (`SERVICE_DISABLED`) because end-users on Workforce Identity (`ioh-workorce-saml-office365`) do not have IAM `serviceusage.services.use` on a quota project.
  - Instead, the web app authenticates using a 1-hour XSRF signing key fetched from `https://vertexaisearch.cloud.google/auth/getoxsrf?csesidx=<CSESIDX>`.
  - `agentspace_cli.py` reads that JSON file locally, signs a 5-minute `HS256` JWT (`iss: "https://vertexaisearch.cloud.google"`, `aud: "https://biz-discoveryengine.googleapis.com"`, `sub: "csesidx/<CSESIDX>"`, `kid: keyId`), and passes it in `Authorization: Bearer <JWT>`.
- **Fast Mode vs. Enterprise Search Mode:**
  - By default (`enable_search=False`), `agentspace_cli.py` sets `"assistSkippingMode": "REQUEST_ASSIST"` and omits `"vertexAiSearchSpec"`. This skips federated Confluence/SharePoint search and returns responses from `gemini-4-argon` in **~3 seconds**.
  - When `--search` (`enable_enterprise_search=True`) is enabled, `"vertexAiSearchSpec": {}` is included so Agentspace searches IOH's connected data stores.

---

## 3. How the Agent Should Use Agentspace in This Workspace

1. **Via MCP Tool (`agentspace_ask`):**
   - If the `ioh-agentspace` MCP server is active, call `agentspace_ask(prompt=..., model="gemini-4-argon", thinking_level="MEDIUM", enable_enterprise_search=False)`.
   - If the MCP server has not been registered on the current PC yet, run `python setup_mcp.py` once.

2. **Via Direct CLI (`agentspace_cli.py`):**
   - Fast coding/reasoning query:
     ```powershell
     python agentspace_cli.py "Your prompt here"
     ```
   - Enterprise knowledge base query (IOH Confluence, SharePoint, Jira):
     ```powershell
     python agentspace_cli.py "Your search query here" --search
     ```
   - Continue a multi-turn conversation using `--session "<session_name>"`.

---

## 4. Security & Token Refresh Protocol

- **NEVER print or read the raw `xsrfToken` value into the chat history.** Always let `agentspace_cli.py` load the JSON file from disk.
- `agentspace_cli.py` automatically searches for the newest XSRF JSON file in:
  1. `$env:AGENTSPACE_XSRF_PATH`
  2. `./agentspace_xsrf.json`
  3. `%TEMP%\agentspace_xsrf.json`
  4. `~/Downloads/json*.txt` or `~/Downloads/getoxsrf*`
- **When a request fails with `HTTP 401` or `invalid-xsrf-token` (after the 1-hour token window expires):**
  Instruct the user to refresh their token in one of two ways:
  1. Open `https://vertexaisearch.cloud.google/auth/getoxsrf?csesidx=` (or their current `csesidx`) in their logged-in browser and save it to `~/Downloads/json.txt`.
  2. Or run in their browser DevTools Console:
     ```javascript
     fetch(`/auth/getoxsrf?csesidx=${new URLSearchParams(location.search).get('csesidx')}`).then(r => r.text()).then(t => { copy(t); console.log("Copied!"); })
     ```
     Followed by PowerShell:
     ```powershell
     Get-Clipboard | Set-Content -Path "$env:TEMP\agentspace_xsrf.json" -Encoding UTF8
     ```
