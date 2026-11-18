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
4. **Agentspace Advisor Mode (`--model gemini-4-argon` / `gemini-4-carbon`, `--thinking HIGH`, `-f <file>`)**:
   - When Antigravity is constrained to a lighter local model (e.g., Hydrogen) and faces complex architecture, multi-file refactoring, or hard root-cause debugging, use Agentspace as an **external Senior Architect / Advisor** (`agentspace_cli.py --advise -f <file1> -f <file2> --session-tag <8_char_conv_id>`).
   - **Strict `<antigravity_spec>` Bridge:** `--advise` / `agentspace_advise` instructs Agentspace to end every advisory turn with a compact `<antigravity_spec>` block (exact file paths + line/function targets, exact code changes, edge cases, and verification commands). The tool and CLI return this `<antigravity_spec>` inline and auto-write `*.spec.md` to disk, allowing the Executor to execute changes directly without an extra `read_file` roundtrip on `advisor_plan.md`.
   - **Zero Output-Token Context Sharing & Auto-Deduplication:** Always pass local files via `-f <path>` (never paste large codeblocks into the prompt). Multi-turn follow-ups in the same session tag automatically hash and deduplicate unchanged files, so you do not need to re-pass unchanged context. Keep trivial local edits, simple lint fixes, and routine unit-test loops 100% local.
5. **Context Hygiene & Local Model Routing:**
   - **Trim Terminal Noise:** Pipe verbose CLI outputs (`pytest`, SQL dry-runs, dataframe prints, stack traces) with `--tb=short`, `-q`, or `| head -n 30`.
   - **Compact / Reset:** Start a fresh session or `/compact` every ~40k tokens after completing a milestone.
   - **Model Routing:** Use **Hydrogen** (or **Flash Medium/High** via `/argon-flash`) for local execution; only use `flash-lite` if explicitly specified.

---

## 2. Architecture & Technical Knowledge Base

- **Target Endpoints (`https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/`):**
  - `widgetStreamAssist`: Send chat queries to specialized IOH Agents (`agentsSpec.agentSpecs`), Skill Agents (`load_skill` + `canvasSpec`), or Federated Search (`vertexAiSearchSpec`).
  - `widgetDeleteSession`: Delete a chat session (`deleteSessionRequest: {"name": "collections/default_collection/engines/enterprise-search-17429648_1742964839282/sessions/<short_session_id>"}`). Requires full engine prefix.
  - `widgetListSessions`: List recent chat sessions (`listSessionsRequest: {}`).
  - `widgetGetSession`: Retrieve full session turn & tool-call history (`getSessionRequest: {"name": "<short_session_id>", "includeAnswerDetails": true}`).
  - `widgetGetImmersiveArtifact`: Retrieve Canvas / Slides `immersiveArtifact` payload (`getImmersiveArtifactRequest: {"name": "<artifact_id>"}`).
  - `widgetExportImmersiveArtifact`: Export a Canvas / Slides `immersiveArtifact` directly to native `.pptx` (`fileContentDestination: {"mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}`) at zero LLM token cost!
  - `lookupWidgetConfig`: Retrieve widget configuration, connectors, and enabled models.
- **Widget Config ID (`cid`):** `384c42b0-2885-415a-82d5-f2babc063b6e`
- **Underlying GCP Engine:** `projects/195467123768/locations/global/collections/default_collection/engines/enterprise-search-17429648_1742964839282`
- **Model IDs:** `gemini-4-argon` (default) and `gemini-4-carbon` (supports `thinkingLevel`: `"LOW"`, `"MEDIUM"`, `"HIGH"`)
- **Known Agent & Skill Aliases (`--agent`):**
  - `netra` -> `17783079275007264980` (Netra Multi-Agent Coordinator: CVM, Network Analytics, Techno, Export, User Analytics)
  - `ace` -> `8461818071814491910` (ACE Platform Agent)
  - `workflow` / `netra-office-workflow` -> `8458183310708652909` (`Netra & Office Workflow Coordinator`)
  - `office-workflow-suite` / `office` / `slides` / `pptx` -> `14950672669329422296` (Configured `office-workflow-suite` `SKILL_AGENT` in Agentspace; automatically invokes `load_skill` for `office-workflow-suite` + `references/executive-slides.md` & `references/minimal-slides.md`, generates Canvas slides, and exports `.pptx`)
  - `office-creator` -> `17216682253898748109` (`Office File Creator` LOW_CODE Multi-Agent upgraded to V2 architecture)
  - `office-creator-2` / `office2` / `office-v2` -> `2291045905737541211` (`Office File Creator 2.0` LOW_CODE Multi-Agent)
  - `agb` -> `18420663427156982501`
  - `catalyst` -> `app_catalyst_agent`

---

## 3. How the Agent Should Use Agentspace in This Workspace

### Session Lifecycle & `[agy-bridge]` Naming Rules
- **Keep Text/Data Sessions by Default:** Do **NOT** pass `--ephemeral` (`delete_session_after=True`) on normal Netra, Search, or Slides queries. Keeping sessions allows multi-turn follow-ups and lets the user inspect or continue chats in the Agentspace Web UI.
- **Image & Video Generation Media Session Policy (1 Session per Task, Auto-Clear Every 3 Prompts, Delete on Task Finish):**
  - **Scope (Pure AI Artwork / Video Generation Only — Never Data Visualization Charts):** This policy applies **strictly** to standalone Imagen/Veo artwork and video generation prompts. If a Netra, data analysis, or Python code-execution query produces a **visualization chart, plot, or graph image**, `agentspace_cli.py` still auto-downloads the `.png` chart locally, but **never** classifies or deletes that chat as a media-generator session.
  - **Single Shared Media Session:** Always pass the **base** `--session-tag <first_8_chars_of_AGY_Conversation_ID>` (never append `_img1`, `_vid2`, etc., and never pass `--new-session` per image/video). `agentspace_cli.py` routes all media prompts in the task to a single shared `model:<model_id>:media` session slot.
  - **Automatic 3-Prompt Rotation & Deletion (`--max-media-prompts 3`):** `agentspace_cli.py` tracks the media prompt count in `session_state.json`. Once the media session reaches **3 prompts** (default `DEFAULT_MAX_MEDIA_PROMPTS = 3`), `agentspace_cli.py` automatically downloads the generated `.png`/`.mp4` files and immediately **deletes** that media session so the next prompt starts clean with zero context bloat or Web UI clutter.
  - **Mandatory Task/Subagent Teardown (`--finish-task`):** Whenever a subagent or main agent finishes a batch of image/video generation prompts (e.g., if only 1 or 2 prompts were left in the current cycle), it **MUST** run:
    ```powershell
    python agentspace_cli.py --finish-task <8_char_conv_id>
    ```
    *(or call `agentspace_finish_task(session_tag="<8_char_conv_id>")` via MCP)* to delete any remaining media session from the Agentspace Web UI while preserving Netra/Search/Slides sessions.
  - **Bulk Media Clutter Sweep (`--cleanup-media-sessions`):** To sweep any orphaned image/video generation sessions across the Agentspace Web UI sidebar at any time, run `python agentspace_cli.py --cleanup-media-sessions`.
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
  1. **`office-workflow-suite` Skill Agent (`14950672669329422296`)** (`--agent office-workflow-suite` / `--agent slides`): Upgraded to V2.0 architecture! Calls `load_skill` on `office-workflow-suite` + `references/executive-slides.md` and `references/minimal-slides.md`, builds the presentation in `/home/bard` using the zero-dependency `pptx_lxml_wrapper` (`prs.run_visual_qa()` + dynamic KPI font scaling + `/home/bard/pptx_payload.txt`), uploads the `.pptx` to OneDrive `/Agentspace_Exports` (`parent_id="<onedrive_folder_id>"`) with `FileName: "<Deck_Name>.pptx"`, `InputFileName: "pptx_payload.txt"`, `HasBytes: false`, and `ContentBytes: ""` (zero token bloat), and returns a clickable PowerPoint Online `webUrl` (plus in-memory `WorkbookBuilder` / `DocxBuilder` + `generate_document` for `.xlsx` and `.docx`).
  2. **`Office File Creator` (`17216682253898748109`) & `Office File Creator 2.0` (`2291045905737541211`)** (`--agent office-creator` / `--agent office-creator-2`): Multi-agent builders (`presentation_designer`, `spreadsheet_creator`, `document_creator`, `visual_qa_auditor` + `file_and_coding_agent`) with the attached **OneDrive Connector (`collections/onedrive-federated-live_1776136353357/dataConnector`)**:
     - **Zero-`ContentBytes` `.pptx` OneDrive Upload (`pptx_payload.txt`):** Builds the 9-part OOXML `.pptx` in `/home/bard` via `pptx_lxml_wrapper` (`prs.run_visual_qa()` + dynamic KPI font scaling), automatically writes `/home/bard/pptx_payload.txt` so the sandbox registers the binary in `Files currently attached` without triggering Vertex AI's `application/vnd.openxmlformats-*` `HTTP 500` crash, and calls `onedrive_agent__upload_file` with `FileName: "<Deck_Name>.pptx"`, `InputFileName: "pptx_payload.txt"`, `HasBytes: false`, and `ContentBytes: ""` (saving ~12,500 LLM output tokens, ~60s latency, and eliminating Base64 truncation).
     - **Native In-Chat Delivery for `.xlsx` & `.docx` (Zero OneDrive Modal):** Builds `.xlsx` (`WorkbookBuilder`) and `.docx` (`DocxBuilder`) 100% in memory (`io.BytesIO()`) and calls `[Generate Document](tool://generate_document)` for native in-chat download cards.
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
