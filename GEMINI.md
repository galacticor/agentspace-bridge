# IOH Agentspace (`gemini-4-argon` & Custom Agents) Bridge — Workspace Knowledge Base & Rules

When working in this workspace (`agentspace-bridge`), you have direct access to **IOH's Gemini Enterprise (Agentspace)** instance (`https://agentspace.ioh.co.id` / `vertexaisearch.cloud.google`) powered by **Gemini 4 Argon (`gemini-4-argon`)** as well as custom IOH Agents (including **Netra Agent**, **ACE Platform**, and **Slides Agent**).

## 1. Purpose of This Project
This workspace bridges **Google Antigravity** with **IOH Agentspace** so that:
1. Antigravity can offload coding, drafting, analysis, and reasoning tasks to **Gemini 4 Argon (`gemini-4-argon`)** to save Antigravity usage quota.
2. Antigravity can invoke specialized IOH enterprise agents like **Netra Agent (`17783079275007264980`)** (`agent_cvm`, `agent_user_network_analytics`, `agent_techno`, `agent_export`, `agent_user_analytics`).
3. Antigravity can query internal IOH enterprise connectors (**Confluence, SharePoint, Jira, OneDrive, ServiceNow**) via Agentspace's federated search.
4. Antigravity can clean up / delete temporary chat sessions (`widgetDeleteSession`) when a chat will not be reused.

---

## 2. Architecture & Technical Knowledge Base

- **Target Endpoints (`https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/`):**
  - `widgetStreamAssist`: Send chat queries to `gemini-4-argon` or specialized Agents (`agentsSpec.agentSpecs`).
  - `widgetDeleteSession`: Delete a chat session (`deleteSessionRequest: {"name": "<short_session_id>"}`).
  - `widgetListSessions`: List recent chat sessions (`listSessionsRequest: {}`).
  - `widgetGetSession`: Retrieve full session turn & tool-call history (`getSessionRequest: {"name": "<short_session_id>", "includeAnswerDetails": true}`).
  - `lookupWidgetConfig`: Retrieve widget configuration, connectors, and enabled models.
- **Widget Config ID (`cid`):** `384c42b0-2885-415a-82d5-f2babc063b6e`
- **Underlying GCP Engine:** `projects/195467123768/locations/global/collections/default_collection/engines/enterprise-search-17429648_1742964839282`
- **Model ID:** `gemini-4-argon` (supports `thinkingLevel`: `"LOW"`, `"MEDIUM"`, `"HIGH"`)
- **Known Agent Aliases (`--agent`):**
  - `netra` -> `17783079275007264980` (Netra Multi-Agent Coordinator: CVM, Network Analytics, Techno, Export, User Analytics)
  - `ace` -> `8461818071814491910` (ACE Platform Agent)
  - `slides` / `pptx` -> `17216682253898748109` (Presentation / Research Agent)
  - `agb` -> `18420663427156982501`
  - `catalyst` -> `app_catalyst_agent`

---

## 3. How the Agent Should Use Agentspace in This Workspace

1. **Via MCP Tools (`ioh-agentspace`):**
   - `agentspace_ask(prompt=..., agent="netra", delete_session_after=True)`: Query Netra or `gemini-4-argon`, optionally auto-deleting the chat session when finished.
   - `agentspace_delete_session(session_id=...)`: Delete a specific chat session when it is no longer needed.
   - `agentspace_list_sessions(limit=20)`: List recent chat sessions.
   - `agentspace_refresh_token(browser="msedge")`: Pop up a browser window to automatically refresh and save `./agentspace_xsrf.json` inside the project folder.

2. **Via Direct CLI (`agentspace_cli.py`):**
   - Fast coding/reasoning query (auto-delete chat after response):
     ```powershell
     python agentspace_cli.py "Your prompt here" --ephemeral
     ```
   - Call **Netra Agent** (and delete chat after response):
     ```powershell
     python agentspace_cli.py "Your Netra query here" --agent netra --ephemeral
     ```
   - Enterprise knowledge base query (IOH Confluence, SharePoint, Jira):
     ```powershell
     python agentspace_cli.py "Your search query here" --search --ephemeral
     ```
   - List or delete existing chat sessions:
     ```powershell
     python agentspace_cli.py --list-sessions
     python agentspace_cli.py --delete-session 6300471525476906605
     ```
   - Manually trigger browser pop-up to refresh `./agentspace_xsrf.json`:
     ```powershell
     python agentspace_cli.py --refresh-token
     ```

---

## 4. Security & Token Refresh Protocol

- **NEVER print or read the raw `xsrfToken` value into the chat history.** Always let `agentspace_cli.py` load the JSON file from disk.
- **Automatic Browser Pop-up Refresh:**
  - Whenever `agentspace_cli.py` (or the MCP server) encounters a missing token or `HTTP 401` (`SESSION_COOKIE_INVALID` after the ~1-hour token window expires), it **automatically opens a persistent browser window** (`.auth_profile/`) to `https://agentspace.ioh.co.id`, waits for SSO / page load, fetches `/auth/getoxsrf?csesidx=<csesidx>`, saves the fresh token directly to `./agentspace_xsrf.json` in the project folder, closes the browser, and retries the request.
  - You can also explicitly run `python agentspace_cli.py --refresh-token` (or call `agentspace_refresh_token`) at any time.
