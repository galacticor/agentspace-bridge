# IOH Agentspace (`gemini-4-argon` & Custom IOH Agents) Bridge — Workspace Knowledge Base & Rules

When working in this workspace (`agentspace-bridge`), you have direct access to **IOH's Gemini Enterprise (Agentspace)** instance (`https://agentspace.ioh.co.id` / `vertexaisearch.cloud.google`) powered by **Gemini 4 Argon (`gemini-4-argon`)**, custom IOH Agents (**Netra Agent**, **ACE Platform**), and your configured **`office-workflow-suite` Skill Agent (`14950672669329422296`)**.

## 1. Purpose & Strict Scope of This Project (IOH Data & Agents Only)

> [!IMPORTANT]
> **Empirical Token Rule (Do NOT Offload General Local Coding):**
> Never use `agentspace_cli.py` or `agentspace_ask` to offload general coding, local debugging, or unit-test fixing that Antigravity can execute locally. Routing local code fixes over an external CLI burns **4×–5× more Antigravity tokens** due to per-turn system-prompt overhead (`~30k tokens/turn`) and backgrounding turns. Solve all local coding/debugging tasks **100% locally in Antigravity**.

Use **IOH Agentspace** strictly for tasks that require **IOH enterprise data, IOH internal documents, or Agentspace-hosted agents/skills**:
1. **IOH Enterprise Agents (`--agent netra`, `--agent ace`)**: Querying live IOH subscriber, CVM, revenue, network analytics, and BigQuery marts via **Netra Agent (`17783079275007264980`)** (`agent_cvm`, `agent_user_network_analytics`, `agent_techno`, `agent_export`, `agent_user_analytics`) or **ACE Platform (`8461818071814491910`)**.
2. **IOH Enterprise Knowledge Base Search (`--search`)**: Querying internal IOH connectors (**Confluence, SharePoint, Jira, OneDrive, ServiceNow**) via Agentspace's federated search.
3. **IOH Executive Presentations (`.pptx`) — 3A Default vs. 3B On-Demand**:
   - **Mode 3A (Default — Hybrid Pipeline):** Query Agentspace (`--agent netra` or `--search`) to extract IOH data into an exhaustive slide-by-slide Markdown outline (`-o slide_outline.md --summary-only`), then build the `.pptx` **locally via a delegated Antigravity subagent** (`executive-slides` + `minimal-slides` + `pptx` / `pptxgenjs` + M365 Visual QA via `office_view_hook.py`). *(Note: If the presentation uses purely local files already on disk and needs zero IOH data, skip Agentspace completely and build locally!)*
   - **Mode 3B (When User Explicitly Requests Agentspace to Create Slides):** Invoke the user's configured **`office-workflow-suite` Skill Agent (`14950672669329422296`)** via `--agent office-workflow-suite` (or `--agent slides`), which loads `office-workflow-suite` (`references/executive-slides.md` and `references/minimal-slides.md`) inside Agentspace and auto-exports the native `.pptx` via `widgetExportImmersiveArtifact`.

---

## 2. Architecture & Technical Knowledge Base

- **Target Endpoints (`https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/`):**
  - `widgetStreamAssist`: Send chat queries to specialized IOH Agents (`agentsSpec.agentSpecs`), Skill Agents (`load_skill` + `canvasSpec`), or Federated Search (`vertexAiSearchSpec`).
  - `widgetDeleteSession`: Delete a chat session (`deleteSessionRequest: {"name": "<short_session_id>"}`).
  - `widgetListSessions`: List recent chat sessions (`listSessionsRequest: {}`).
  - `widgetGetSession`: Retrieve full session turn & tool-call history (`getSessionRequest: {"name": "<short_session_id>", "includeAnswerDetails": true}`).
  - `widgetGetImmersiveArtifact`: Retrieve Canvas / Slides `immersiveArtifact` payload (`getImmersiveArtifactRequest: {"name": "<artifact_id>"}`).
  - `widgetExportImmersiveArtifact`: Export a Canvas / Slides `immersiveArtifact` directly to native `.pptx` (`fileContentDestination: {"mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}`) at zero LLM token cost!
  - `lookupWidgetConfig`: Retrieve widget configuration, connectors, and enabled models.
- **Widget Config ID (`cid`):** `384c42b0-2885-415a-82d5-f2babc063b6e`
- **Underlying GCP Engine:** `projects/195467123768/locations/global/collections/default_collection/engines/enterprise-search-17429648_1742964839282`
- **Model ID:** `gemini-4-argon` (supports `thinkingLevel`: `"LOW"`, `"MEDIUM"`, `"HIGH"`)
- **Known Agent & Skill Aliases (`--agent`):**
  - `netra` -> `17783079275007264980` (Netra Multi-Agent Coordinator: CVM, Network Analytics, Techno, Export, User Analytics)
  - `ace` -> `8461818071814491910` (ACE Platform Agent)
  - `office-workflow-suite` / `office` / `slides` / `pptx` -> `14950672669329422296` (Configured `office-workflow-suite` `SKILL_AGENT` in Agentspace; automatically invokes `load_skill` for `office-workflow-suite` + `references/executive-slides.md` & `references/minimal-slides.md`, generates Canvas slides, and exports `.pptx`)
  - `office-creator` -> `17216682253898748109` (Legacy LOW_CODE Office File Creator)
  - `agb` -> `18420663427156982501`
  - `catalyst` -> `app_catalyst_agent`

---

## 3. How the Agent Should Use Agentspace in This Workspace

### Session Lifecycle & `[agy-bridge]` Naming Rules
- **Keep Sessions by Default:** Do **NOT** pass `--ephemeral` (`delete_session_after=True`) on normal queries. Keeping sessions allows multi-turn follow-ups and lets the user inspect or continue chats in the Agentspace Web UI.
- **Automatic `[agy-bridge]` Prefix:** Whenever a new session is created and kept, `agentspace_cli.py` automatically calls `widgetUpdateSession` (`updateMask: "displayName"`) to prefix the Web UI session title with **`[agy-bridge]`** (e.g., `[agy-bridge] Non-5G Device Subscribers`).
- **Automatic Multi-Turn Continuity per Antigravity Chat:**
  - Always pass `--session-tag <first_8_chars_of_AGY_Conversation_ID>`.
  - `agentspace_cli.py` stores the active Agentspace session ID per mode/agent inside `./outputs/chat_<session_tag>/session_state.json`.
  - Follow-up queries in the same Antigravity chat with the same `--session-tag` and same `--agent`/mode automatically reuse the existing `[agy-bridge]` session.
  - Pass `--new-session` only if you want to start a fresh topic thread within the same Antigravity chat, or `--ephemeral` only for throwaway health checks.
- **No Polling on Backgrounded Commands:** If a `run_command` call to `agentspace_cli.py` backgrounds after `WaitMsBeforeAsync`, **never** poll `manage_task` or set `schedule` timers. End your turn and wait for Antigravity's reactive wakeup (or call `agentspace_ask` via MCP).

### 1. Querying IOH Enterprise Data (`--agent netra` / `--agent ace`)
```powershell
python agentspace_cli.py "Your Netra query here" --agent netra --session-tag <8_char_conv_id>
```
- When expecting large tables or detailed multi-cohort reports from Netra, save directly to disk via `-o report.md --summary-only` so you only pay ~500 characters in the main chat context:
```powershell
python agentspace_cli.py "Extract 90d CVM conversion and ARPU by segment" --agent netra -o netra_cvm_data.md --session-tag <8_char_conv_id> --summary-only
```

### 2. Querying IOH Enterprise Knowledge Base (`--search`)
Query internal IOH Confluence pages, Jira tickets, SharePoint documents, OneDrive files, and ServiceNow tickets:
```powershell
python agentspace_cli.py "Your IOH Confluence / Jira / SharePoint query here" --search --session-tag <8_char_conv_id>
```

### 3. Presentation / `.pptx` Generation Architecture (Mode 3A Default vs. Mode 3B On-Demand)

#### Mode 3A (DEFAULT): Hybrid IOH Data Outline $\rightarrow$ Local Antigravity Subagent Build
> **CRITICAL RULE:** Always default to **Mode 3A** for executive presentations.
> - **If the deck requires IOH data:** First query `--agent netra` (or `--search`) in Agentspace to gather the data and generate a complete slide-by-slide Markdown outline (`-o pptx_detailed_outline.md --summary-only`), then delegate the `.pptx` build to a local Antigravity subagent (`invoke_subagent`).
> - **If the deck uses purely local data files already on disk:** Do **not** call Agentspace at all—delegate directly to the local Antigravity subagent!

1. **Stage 1 (When IOH Data is Needed) — Data Gathering & Exhaustive PPTX Outline in Agentspace:**
   - Query `--agent netra` (or follow up in the same `--session-tag` thread) to synthesize a **complete, detailed slide-by-slide Markdown outline** saved to `./outputs/chat_<tag>/` (`-o pptx_detailed_outline.md --summary-only`).
   - **Mandatory Outline Structure:**
     - **Slide Number, Section Tracker, and McKinsey Action Title** (`<= 80 chars`, single-line conclusion stating the quantitative "So What?").
     - **Context Subtitle** (`<= 110 chars`, metric, unit, cohort, and date range).
     - **Exact Native Chart Series Payload:** Separate rate (`%` / `ARPU`) from volume (`headcount` / `IDR T`), specifying exact category labels and numerical series values so `pptxgenjs` can build native `<c:chart>` bar/column/line charts.
     - **Complete Markdown Data Table:** Every sub-segment, cohort, headcount, share `%`, revenue, ARPU, and delta with zero omitted rows.
     - **Analytical Nuances & Bottom Callout Strip:** Exact 1–2 sentence commercial/technical interpretation and data source footnote (`table_name`, active filters, snapshot dates).
   ```powershell
   python agentspace_cli.py "Based on our Netra analysis, generate a complete, exhaustive 8-slide executive presentation outline in Markdown. For EVERY slide, explicitly provide: (1) Section Tracker & single-line McKinsey Action Title (<80 chars) with the headline metric, (2) Context Subtitle, (3) Exact Native Chart Data Series (Category Labels + Numeric Series separating rates/ARPU from volume), (4) Complete Multi-Column Data Table with all sub-segments and exact numbers, (5) Key Analytical Nuance / Strategic Takeaway Callout, and (6) Exact Source Footnote." -o pptx_detailed_outline.md --session-tag <8_char_conv_id> --summary-only
   ```
2. **Stage 2 — Delegate Local `.pptx` Build & M365 Visual QA to a Subagent (`invoke_subagent`):**
   - Launch `invoke_subagent(TypeName="self", Role="Executive Slide Builder & Visual QA")`.
   - Pass the subagent:
     1. The exact path to the Markdown outline (`./outputs/chat_<tag>/chat_<tag>__...__pptx_detailed_outline.md`) or local data file.
     2. The target output `.pptx` path (`./outputs/chat_<tag>/chat_<tag>__local_agy_skills__<deck_name>.pptx`).
     3. Explicit instructions to read `executive-slides`, `minimal-slides`, and `pptx` (`SKILL.md`), run `select_palette.py`, write the `pptxgenjs` builder script with **native editable `<c:chart>` charts** and **Tufte tables**, render the slides via `office_view_hook.py --pages ... --render --no-media`, visually inspect the `.png` slides via `read_file` to fix any wrapping/overlaps, and return only the final `.pptx` path + a compact summary.

#### Mode 3B (ON-DEMAND): Agentspace Slide Creation via `office-workflow-suite` (`--agent office-workflow-suite`) or `Office File Creator` (`--agent office-creator`)
> **When to Use Mode 3B:** Whenever the user explicitly asks for **Agentspace** to create or export the slides directly (instead of building locally in Antigravity), or chats directly in the Agentspace Web UI.
- **Configured Agents & Skills in Agentspace:**
  1. **`office-workflow-suite` Skill Agent (`14950672669329422296`)** (`--agent office-workflow-suite` / `--agent slides`): Calls `load_skill` on `office-workflow-suite` + `references/executive-slides.md` and `references/minimal-slides.md`, builds the presentation in `/home/bard` using the zero-dependency `pptx_lxml_wrapper` (`lxml.etree` + `xml.etree.ElementTree` fallback), uploads the `.pptx` to OneDrive `/Agentspace_Exports` (`parent_id="<onedrive_folder_id>"`), and returns a clickable PowerPoint Online `webUrl` (plus Canvas export when using `save_slides_to_artifact`).
  2. **`Office File Creator` Agent (`17216682253898748109`)** (`--agent office-creator`): Multi-agent builder (`presentation_designer` + `file_and_coding_agent`) with the attached **OneDrive Connector (`collections/onedrive-federated-live_1776136353357/dataConnector`)**. Builds the `.pptx` + `slide_*.png` previews in `/home/bard` (without `.xlsx`/`.docx` copying, which causes a Vertex AI `HTTP 500` crash), prints `B64_PPTX:<base64>`, uploads the binary via `onedrive_agent__upload_file` into `/Agentspace_Exports` (`parent_id="<onedrive_folder_id>"`), and calls `onedrive_agent__get_item_by_path` to display a clickable `[📥 Open & Download <Deck_Name>.pptx in OneDrive](<webUrl>)` link.
- **Mandatory OneDrive Connector Activation Rule:**
  - **In `agentspace_cli.py`:** Automatically injects `"dataStoreSpecs": [{"dataStore": "collections/default_collection/dataStores/onedrive-federated-live_1776136353357_file"}]` into `toolsSpec.vertexAiSearchSpec` and auto-confirms `onedrive_agent__upload_file` (`actionExecutionParams`).
  - **In Agentspace Web UI:** The **OneDrive** connector/tool toggle must be enabled in the chat input bar when starting a session so `onedrive_agent__upload_file` and `onedrive_agent__get_item_by_path` are mounted in the session.
```powershell
python agentspace_cli.py "Create an 8-slide executive presentation on <topic>" --agent office-workflow-suite --session-tag <8_char_conv_id>
```
*(Or via MCP: `agentspace_ask(prompt="...", agent="office-workflow-suite", session_tag="<8_char_conv_id>")`, and `agentspace_export_slides(session_tag="<8_char_conv_id>", formats=["pptx", "pdf"])` to re-export existing Canvas sessions.)*

---

## 4. Security & Token Refresh Protocol

- **NEVER print or read the raw `xsrfToken` value into the chat history.** Always let `agentspace_cli.py` load `./agentspace_xsrf.json` from disk.
- **Automatic Silent Headless Refresh (Inside `run_command` or Auto-Retry on 401):**
  - When `./agentspace_xsrf.json` expires (`HTTP 401`/`403`) or `python agentspace_cli.py --refresh-token` is called, `agentspace_cli.py` first runs a **silent headless refresh** using the persistent `.auth_profile/` directory.
  - On multi-account Windows PCs where Windows Web Account Manager (WAM) injects multiple Microsoft accounts (e.g., `@ioh.co.id` + a university/personal Microsoft account), `agentspace_cli.py` automatically selects the `@ioh.co.id` tile on the Entra ID `"Pick an account"` screen in headless mode (`~8s`, zero popup windows).
  - If the underlying Entra ID refresh token itself has expired (e.g., after a password change or 2FA prompt), it automatically falls back to opening a visible Chrome/Edge window (or via `agentspace_refresh_token` MCP tool).
