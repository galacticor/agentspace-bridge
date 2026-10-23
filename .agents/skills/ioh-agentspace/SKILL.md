---
name: ioh-agentspace
description: >-
  Query IOH's Gemini Enterprise (Agentspace) for tasks requiring IOH enterprise data or
  internal knowledge: (1) specialized IOH data agents like Netra Agent (CVM, Network
  Analytics, Techno, Export, User Analytics) and ACE Platform, (2) internal IOH enterprise
  connectors (Confluence, SharePoint, Jira, OneDrive, ServiceNow) via federated search, and
  (3) IOH executive presentations via Mode 3A (Netra/Search data outline -> local Antigravity
  executive-slides subagent build) or Mode 3B (Agentspace slide generation using the configured
  office-workflow-suite skill agent). Do NOT use this skill to offload general local coding,
  debugging, or unit testing.
---

# IOH Agentspace (`netra`, `search`, & `office-workflow-suite`) Skill

## Overview & Strict Scope (IOH Data & Agents Only)

This skill connects Antigravity to **IOH's Gemini Enterprise (Agentspace)** via `agentspace_cli.py` and the `ioh-agentspace` MCP server (`agentspace_ask`, `agentspace_export_slides`, `agentspace_list_sessions`, `agentspace_delete_session`, `agentspace_refresh_token`).

> [!IMPORTANT]
> **When to Use vs. When NOT to Use (`Do Not Offload Local Coding`):**
> - **NEVER use `ioh-agentspace` to offload general coding, local debugging, or unit-test fixing.** Empirical benchmarks prove that routing local code/test loops through an external CLI burns **4×–5× more Antigravity tokens** due to per-turn system-prompt overhead (`~30k tokens/turn`) and backgrounding turns. Solve all local coding, SQL writing, and debugging **100% locally in Antigravity**.
> - **ONLY use `ioh-agentspace` for tasks tied to IOH data or Agentspace agents:**
>   1. **IOH Enterprise Data Agents (`--agent netra`, `--agent ace`)**: Live subscriber, CVM, revenue, and network analytics queries in IOH's GCP environment.
>   2. **IOH Enterprise Knowledge Base Search (`--search`)**: Internal IOH Confluence, Jira (`DSB2C-*`), SharePoint, OneDrive, and ServiceNow lookups.
>   3. **IOH Executive Presentations (`Mode 3A` Default vs. `Mode 3B` On-Demand)**: Extracting IOH data outlines for local `.pptx` builds (`Mode 3A`), or running your configured **`office-workflow-suite` Skill Agent (`14950672669329422296`)** when you explicitly ask Agentspace to create the slides (`Mode 3B`).

---

## Session Naming, Continuity & Anti-Polling Rules

- **Keep Sessions by Default:** Do **not** pass `--ephemeral` on normal queries. Keeping sessions allows multi-turn follow-ups and lets the user view the chat in the Agentspace Web UI.
- **Automatic `[agy-bridge]` Prefix:** Every newly created session is automatically renamed via `widgetUpdateSession` so its Web UI title starts with **`[agy-bridge]`** (e.g., `[agy-bridge] Non-5G Device Subscribers`).
- **Automatic Multi-Turn Continuity per Antigravity Chat:**
  - Always pass `--session-tag <first_8_chars_of_AGY_Conversation_ID>`.
  - `agentspace_cli.py` saves the active Agentspace session ID per mode/agent inside `./outputs/chat_<tag>/session_state.json`.
  - Subsequent calls in the same Antigravity chat with the same `--session-tag` automatically continue the existing `[agy-bridge]` session!
  - Pass `--new-session` only if switching to an unrelated topic in the same mode, or `--ephemeral` only for throwaway utility checks.
- **Session Isolation Rule:** Never read files from `./outputs/chat_<other_tag>/` belonging to a different Antigravity conversation ID unless the user explicitly asks for them.
- **Anti-Polling Rule:** When running `agentspace_cli.py` via `run_command`, if the command backgrounds after `WaitMsBeforeAsync`, **NEVER poll `manage_task` or set `schedule` timers**. Simply end your turn with zero tool calls; Antigravity's reactive wakeup will automatically resume you the instant `agentspace_cli.py` finishes. (Or call the synchronous `agentspace_ask` MCP tool.)

---

## Core Workflows

### 1. Querying Netra Agent & Custom IOH Data Agents (`--agent netra` / `--agent ace`)
Pass `--agent netra` (maps to Agent ID `17783079275007264980`, sets `answerGenerationMode: "AGENT"`, and coordinates `agent_cvm`, `agent_user_network_analytics`, `agent_techno`, `agent_export`, `agent_user_analytics`):
```powershell
python "agentspace_cli.py" "<netra query>" --agent netra --session-tag <8_char_conv_id>
```
- **Saving Large Data Outputs (`-o` + `--summary-only`):** When extracting large tables or multi-cohort readouts from Netra, save directly to `./outputs/chat_<tag>/` via `-o <filename>.md --summary-only` so only a 500-char preview enters the main chat context:
```powershell
python "agentspace_cli.py" "Pull 90-day CVM conversion and ARPU by segment" --agent netra -o netra_cvm_readout.md --session-tag <8_char_conv_id> --summary-only
```
Other built-in agent aliases: `ace` (`8461818071814491910`), `office-workflow-suite` / `office` / `slides` / `pptx` (`14950672669329422296`), `office-creator` (`17216682253898748109`), `agb` (`18420663427156982501`), `catalyst` (`app_catalyst_agent`).

---

### 2. Enterprise Knowledge Base Search (`--search`)
Query internal IOH Confluence specs, SharePoint decks, Jira tickets, OneDrive files, and ServiceNow records:
```powershell
python "agentspace_cli.py" "<search query>" --search --session-tag <8_char_conv_id>
```

---

### 3. Executive Presentation (`.pptx`) Workflows: `Mode 3A` (Default) vs. `Mode 3B` (On-Demand)

#### Mode 3A (DEFAULT): Agentspace IOH Data Outline $\rightarrow$ Local Subagent Build (`executive-slides` + `minimal-slides` + `pptx`)
- **Default Rule:** Always use **Mode 3A** by default whenever the user asks for a presentation or slide deck:
  - **If the deck requires IOH enterprise data:** Query `--agent netra` (or `--search`) in Agentspace to gather the data and generate an exhaustive slide-by-slide Markdown outline (`-o pptx_outline.md --summary-only`), then delegate the `.pptx` build to a local Antigravity subagent.
  - **If the deck only uses local files already on disk:** Do **not** call Agentspace at all—delegate directly to the local Antigravity subagent!
- **Stage 1 — Request Exhaustive PPTX Outline from Agentspace (`-o pptx_outline.md --summary-only`):**
  ```powershell
  python "agentspace_cli.py" "Synthesize all findings into a complete, exhaustive <N>-slide executive presentation outline in Markdown. Do NOT summarize or omit numbers. For EVERY slide, explicitly include:
  1. Section Tracker & Single-Line McKinsey Action Title (<= 80 chars, stating the quantitative 'So What?' conclusion).
  2. Context Subtitle (<= 110 chars, metric, unit, cohort, and snapshot/window dates).
  3. Native Chart Specification: Exact chart type (column/bar/line), Category Labels, and Numeric Series values (strictly separating rate/%/ARPU metrics on the chart from raw volume/headcount in the table).
  4. Complete Multi-Column Markdown Table: Every cohort/sub-segment, headcount, % share, net revenue, ARPU, payload, and delta with zero omitted rows.
  5. Analytical Nuance & Callout Box: 1-2 sentences explaining the commercial/technical root cause or strategic action.
  6. Source Footnote: Exact table name, filter conditions, and date range." -o pptx_outline.md --session-tag <8_char_conv_id> --summary-only
  ```
- **Stage 2 — Delegate `.pptx` Generation & M365 Visual QA to a Local Subagent (`invoke_subagent`):**
  - Call `invoke_subagent(TypeName="self", Role="Executive Slide Builder & Visual QA")` and pass it the saved outline file path (`./outputs/chat_<tag>/chat_<tag>__...__pptx_outline.md`) and target `.pptx` output path (`./outputs/chat_<tag>/chat_<tag>__local_agy_skills__<name>.pptx`).
  - Instruct the subagent to:
    1. Read `executive-slides`, `minimal-slides`, and `pptx` (`SKILL.md`), and run `select_palette.py` on the outline file.
    2. Build the deck via `pptxgenjs` with **true native editable Office charts (`pres.charts.BAR`/`LINE`)**, **Tufte tables** (top/bottom rules only, zero vertical gridlines, single-line rows), and **single-line Cambria Action Titles**.
    3. Run closed-loop M365 Visual QA (`python "%USERPROFILE%\.gemini\config\office_view_hook.py" "<pptx_path>" --pages "..." --summary-only --render` on Windows or `/opt/homebrew/bin/python3 "$HOME/.gemini/config/office_view_hook.py"` on macOS), inspect the rendered `.png` slides via `read_file`, fix any text wrapping or table overflow, and return only a concise summary + final `.pptx` path to the main agent.

#### Mode 3B (ON-DEMAND): Agentspace Slide Creation via `office-workflow-suite` (`--agent office-workflow-suite`) or `Office File Creator` (`--agent office-creator`)
- **When to Use Mode 3B:** Whenever the user explicitly asks for **Agentspace** to create the slides directly or wants to export the `.pptx` to their OneDrive `/Agentspace_Exports` folder (`https://o365indosat-my.sharepoint.com/personal/<employee_id>_ioh_co_id/Documents/Agentspace_Exports`).
- **Configured Agents & Skills in Agentspace:**
  1. **`office-workflow-suite` (`14950672669329422296`)** (`--agent office-workflow-suite` / `--agent slides`): Calls `load_skill` for `office-workflow-suite` (`references/executive-slides.md` & `references/minimal-slides.md`), builds the `.pptx` in `/home/bard` via the universal `pptx_lxml_wrapper` (`lxml.etree` + `xml.etree.ElementTree` fallback), uploads it to OneDrive `/Agentspace_Exports` (`parent_id="<onedrive_folder_id>"`), and outputs a clickable PowerPoint Online `webUrl`.
  2. **`Office File Creator` (`17216682253898748109`)** (`--agent office-creator`): Multi-agent builder (`presentation_designer` + `file_and_coding_agent`) with the **OneDrive Connector (`collections/onedrive-federated-live_1776136353357/dataConnector`)** attached. Generates `<Deck_Name>.pptx` + `slide_*.png` previews in `/home/bard` (without `.xlsx`/`.docx` copies, avoiding the Vertex AI `HTTP 500` crash), prints `B64_PPTX:<base64>`, calls `onedrive_agent__upload_file` (`parent_id="<onedrive_folder_id>"`), and calls `onedrive_agent__get_item_by_path` to return a clickable `[📥 Open & Download <Deck_Name>.pptx in OneDrive](<webUrl>)` link.
- **OneDrive Connector Activation Rule:**
  - `agentspace_cli.py` automatically passes `{"dataStore": "collections/default_collection/dataStores/onedrive-federated-live_1776136353357_file"}` in `toolsSpec.vertexAiSearchSpec.dataStoreSpecs` and auto-confirms `onedrive_agent__upload_file`.
  - When chatting directly in the **Agentspace Web UI**, ensure the **OneDrive** tool/source toggle is enabled when starting the session.
  ```powershell
  python "agentspace_cli.py" "Create an <N>-slide executive presentation on <topic> using our Netra findings" --agent office-workflow-suite --session-tag <8_char_conv_id>
  ```
  - To re-export an existing Canvas session to `.pptx` and/or `.pdf` at zero LLM token cost:
    ```powershell
    python "agentspace_cli.py" --export-slides --export-format pptx,pdf --session-tag <8_char_conv_id>
    ```
    *(Or call `agentspace_export_slides(session_tag="<8_char_conv_id>", formats=["pptx", "pdf"])` via MCP.)*

---

### 4. Managing & Deleting Chat Sessions
- **List recent sessions:**
  ```powershell
  python "agentspace_cli.py" --list-sessions --limit 20
  ```
- **Delete a specific session when done:**
  ```powershell
  python "agentspace_cli.py" --delete-session "<session_id_or_full_name>"
  ```
  *(Or call `agentspace_delete_session(session_id="...")` via MCP.)*

---

## Handling Expired XSRF Tokens (`HTTP 401`)
1. **Never** ask the user to paste their `xsrfToken` into the chat.
2. **Automatic Silent Headless Refresh (`run_command` & Auto-401 Retry):**
   - When `agentspace_cli.py` encounters `HTTP 401`/`403` (or when you run `python "agentspace_cli.py" --refresh-token`), it automatically performs a silent headless refresh using `.auth_profile/` (`~8s`, zero popup windows).
   - On multi-account Windows machines where Windows Web Account Manager (WAM) shows the Microsoft Entra ID `"Pick an account"` screen (e.g., `@ioh.co.id` alongside another Windows-connected Microsoft account), `agentspace_cli.py` automatically clicks the `@ioh.co.id` account tile in headless mode.
   - Only if the Entra ID session itself requires interactive 2FA/password entry will it fall back to an interactive browser window (or you can invoke `agentspace_refresh_token` via MCP).
