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
  - `widgetGetImmersiveArtifact`: Retrieve Canvas / Slides `immersiveArtifact` payload (`getImmersiveArtifactRequest: {"name": "<artifact_id>"}`).
  - `widgetExportImmersiveArtifact`: Export a Canvas / Slides `immersiveArtifact` directly to native `.pptx` (`fileContentDestination: {"mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}`) at zero LLM token cost!
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

### Session Lifecycle & `[agy-bridge]` Naming Rules
- **Keep Sessions by Default:** Do **NOT** pass `--ephemeral` (`delete_session_after=True`) on normal queries. Keeping sessions allows multi-turn follow-ups and lets the user inspect or continue chats in the Agentspace Web UI.
- **Automatic `[agy-bridge]` Prefix:** Whenever a new session is created and kept, `agentspace_cli.py` automatically calls `widgetUpdateSession` (`updateMask: "displayName"`) to prefix the Web UI session title with **`[agy-bridge]`** (e.g., `[agy-bridge] Non-5G Device Subscribers`).
- **Automatic Multi-Turn Continuity per Antigravity Chat:**
  - Always pass `--session-tag <first_8_chars_of_AGY_Conversation_ID>`.
  - `agentspace_cli.py` stores the active Agentspace session ID per mode/agent inside `./outputs/chat_<session_tag>/session_state.json`.
  - Follow-up queries in the same Antigravity chat with the same `--session-tag` and same `--agent`/model automatically reuse the existing `[agy-bridge]` session (so you don't even need to re-attach `-f` files on Turn 2+).
  - Pass `--new-session` only if you want to start a fresh topic thread within the same Antigravity chat, or `--ephemeral` only for throwaway health checks.

1. **Via MCP Tools (`ioh-agentspace`):**
   - `agentspace_ask(prompt=..., agent="netra", session_tag="<8_char_id>")`: Query Netra, Slides (`agent="slides"` — auto-exports `.pptx`!), or `gemini-4-argon` (automatically prefixes new sessions with `[agy-bridge]` and reuses the session on follow-up turns for that `session_tag`).
   - `agentspace_export_slides(session_tag="<8_char_id>", formats=["pptx", "pdf"])`: Export a Canvas/Slides presentation directly to native `.pptx` (via `widgetExportImmersiveArtifact` RPC) and/or `.pdf` (via headless Web UI Export) at zero AGY token cost.
   - `agentspace_delete_session(session_id=...)`: Delete a specific chat session when explicitly requested.
   - `agentspace_list_sessions(limit=20)`: List recent chat sessions.
   - `agentspace_refresh_token(browser=...)`: Refresh and save `./agentspace_xsrf.json` inside the project folder (defaults to `"chrome"` on macOS and `"msedge"` on Windows; tries a silent headless refresh first if `.auth_profile/` already exists, and falls back to an interactive popup window when login/2FA is needed).

2. **Via Direct CLI (`agentspace_cli.py`):**
   - Fast coding/reasoning query (kept & prefixed with `[agy-bridge]`):
     ```powershell
     python agentspace_cli.py "Your prompt here" --session-tag 95e5efcf
     ```
   - **Maximum AGY Token-Saving Mode** (attach local files directly from disk via `--file`, save long output to `./outputs/chat_<AGY_CONV_ID>/` via `--output`, and print only a short preview via `--summary-only`):
     ```powershell
     python agentspace_cli.py "Optimize this SQL query" -f my_query.sql -o optimized.sql --session-tag 95e5efcf --summary-only
     ```
     *Rule:* Always pass the first 8 characters of your current Antigravity `Conversation ID` to `--session-tag` (or `session_tag` in MCP), and **ONLY** read files matching `outputs/chat_<current_conversation_id>/chat_<current_conversation_id>__*` so you never mix up outputs from unrelated chat sessions.
   - Call **Netra Agent**:
     ```powershell
     python agentspace_cli.py "Your Netra query here" --agent netra --session-tag 95e5efcf
     ```
   - **Presentation / `.pptx` Generation Architecture (3-Stage Hybrid Pipeline — Default):**
     > **CRITICAL RULE:** By default, **ALWAYS generate `.pptx` presentations locally via a delegated Antigravity subagent** (`invoke_subagent(TypeName="self")`) using our local skills (`executive-slides` + `minimal-slides` + `pptx` / `pptxgenjs` + `office_view_hook.py` Visual QA) after requesting a **complete, exhaustive slide-by-slide Markdown outline** from Agentspace (`gemini-4-argon` or `--agent netra`).
     > - **Why:** Agentspace's internal `slidegen_agent` (`--agent slides` / `17216682253898748109` & `office-workflow-suite` / `14950672669329422296`) converts Tailwind HTML to PPTX, which cannot emit native editable PowerPoint `<c:chart>` objects and suffers from DOM-to-PPTX clipping/border-radius bugs. Our local Antigravity skill pipeline builds true native editable Office charts, crisp Tufte tables, Swiss hairline grids, and runs closed-loop M365 Visual QA (`office_view_hook.py`).
     > - **Why Delegate to a Subagent (`invoke_subagent`):** Writing a 1,000+ line `pptxgenjs` script and inspecting rendered slide `.png` files in a subagent keeps the main Antigravity conversation context window nearly **0-token clean** while delivering superior design and UI!

     **The Mandatory 3-Stage Presentation Workflow:**
     1. **Stage 1 — Data Gathering & Exhaustive PPTX Outline in Agentspace (`0 AGY tokens`):**
        - Query `--agent netra` (or `gemini-4-argon` with `-f` files) to extract all data and synthesize a **complete, detailed slide-by-slide Markdown outline** saved directly to `./outputs/chat_<tag>/` (`-o slide_outline.md --summary-only`).
        - **Clear Outline Prompting Contract:** Always instruct Agentspace to structure the Markdown outline with:
          - **Slide Number, Section Tracker, and McKinsey Action Title** (`<= 80 chars`, single-line conclusion stating the quantitative "So What?").
          - **Context Subtitle** (`<= 110 chars`, metric, unit, cohort, and date range).
          - **Exact Native Chart Series Payload:** Separate rate (`%` / `ARPU`) from volume (`headcount` / `IDR T`), specifying exact category labels and numerical series values so `pptxgenjs` can build native `<c:chart>` bar/column/line charts without guessing.
          - **Complete Markdown Data Table:** Every sub-segment, cohort, headcount, share `%`, revenue, ARPU, and delta with zero omitted rows.
          - **Analytical Nuances & Bottom Callout Strip:** Exact 1–2 sentence commercial/technical interpretation and data source footnote (`table_name`, active filters, snapshot dates).
        ```powershell
        python agentspace_cli.py "Based on our analysis, generate a complete, exhaustive 8-slide executive presentation outline in Markdown. For EVERY slide, explicitly provide: (1) Section Tracker & single-line McKinsey Action Title (<80 chars) with the headline metric, (2) Context Subtitle, (3) Exact Native Chart Data Series (Category Labels + Numeric Series separating rates/ARPU from volume), (4) Complete Multi-Column Data Table with all sub-segments and exact numbers, (5) Key Analytical Nuance / Strategic Takeaway Callout, and (6) Exact Source Footnote." -o pptx_detailed_outline.md --session-tag 95e5efcf --summary-only
        ```
     2. **Stage 2 — Delegate Local `.pptx` Build & M365 Visual QA to a Subagent (`invoke_subagent`):**
        - Do **not** read the giant outline or render `.png` slides in the main agent context. Instead, launch `invoke_subagent(TypeName="self", Role="Executive Slide Builder & Visual QA")`.
        - Pass the subagent:
          1. The exact path to the Agentspace Markdown outline (`./outputs/chat_<tag>/chat_<tag>__...__pptx_detailed_outline.md`).
          2. The target output `.pptx` path (`./outputs/chat_<tag>/chat_<tag>__local_agy_skills__<deck_name>.pptx`).
          3. Explicit instructions to read `executive-slides`, `minimal-slides`, and `pptx` (`SKILL.md`), run `select_palette.py` on the outline, write the `pptxgenjs` builder script with native editable charts and Tufte tables, render the slides via `office_view_hook.py --pages ... --render --no-media`, visually inspect the `.png` slides via `read_file` to fix any wrapping/overlaps, and return only the final `.pptx` path + a compact summary.
     3. **Optional Fallback (Agentspace Native Export):** Only use `python agentspace_cli.py --agent slides` / `--export-slides` if the user explicitly asks for an instant Agentspace Canvas export rather than a local executive build.
   - Enterprise knowledge base query (IOH Confluence, SharePoint, Jira):
     ```powershell
     python agentspace_cli.py "Your search query here" --search --session-tag 95e5efcf
     ```
   - Start a brand-new session within the same Antigravity chat:
     ```powershell
     python agentspace_cli.py "New unrelated topic" --session-tag 95e5efcf --new-session
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
