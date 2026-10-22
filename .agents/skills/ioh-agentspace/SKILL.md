---
name: ioh-agentspace
description: >-
  Offload deep thinking, multi-file architecture, complex debugging, >100-line code/SQL
  generation, analytical reasoning, specialized agent queries (Netra Agent, ACE Platform,
  Slides Agent), or enterprise knowledge base searches (IOH Confluence, SharePoint, Jira,
  OneDrive, ServiceNow) to IOH's Gemini Enterprise (Agentspace) running Gemini 4 Argon
  (gemini-4-argon). MANDATORY when running on Gemini 3.7 Flash as an Orchestrator to
  save Antigravity quota without sacrificing reasoning quality.
---

# IOH Agentspace (`gemini-4-argon` & Netra Agent) Skill

## Overview
This skill connects Antigravity to IOH's Gemini Enterprise (Agentspace) via `/Users/widyantohd/Documents/Projects/agentspace-bridge/agentspace_cli.py` (or `agentspace_cli.py` in the bridge workspace) and the `ioh-agentspace` MCP server (`agentspace_ask`, `agentspace_export_slides`, `agentspace_list_sessions`, `agentspace_delete_session`, `agentspace_refresh_token`).

---

## Flash-as-Orchestrator Protocol (Mandatory 4-Step Playbook When Running on Gemini 3.7 Flash)

Whenever the Antigravity main agent is running on **Gemini 3.7 Flash (Medium/High)** (or whenever offloading complex work to save AGY quota), **DO NOT attempt to solve complex architecture, tricky bugs, or large code/SQL generation using local Flash weights alone.** Act strictly as a high-speed **Orchestrator** for `gemini-4-argon`:

1. **Step 1 — Local Dependency Recon (Never Send Blind Prompts):**
   - Before calling `agentspace_ask` or `agentspace_cli.py` on a repo task, run fast local searches (`grep_search`, `find_by_name`, or `read_file` on headers/imports) to identify **all coupled files**.
   - Pass those files directly from disk via `input_files` (`-f fileA.py fileB.py`) so `gemini-4-argon` sees the real source code without bloating AGY's token window.
2. **Step 2 — Prompt `gemini-4-argon` (`HIGH`) for "Drop-In" Outputs:**
   - Do **not** ask Agentspace for vague advice that Flash has to translate into code.
   - Instruct `gemini-4-argon` (`thinking_level="HIGH"`, `output_file="<name>"`, `summary_only=True`) to return either:
     - **Complete standalone scripts/queries** saved directly to `./outputs/chat_<tag>/`, OR
     - **Exact surgical edit specifications** (`File Path`, `Exact Target Block`, `Exact Replacement Block`) that you can apply mechanically with `edit_file`.
   - **CRITICAL Anti-Polling Rule for Flash:** When running `agentspace_cli.py` via `run_command` (especially with `--thinking HIGH`, which takes 60–180s), if the command backgrounds after `WaitMsBeforeAsync`, **NEVER poll `manage_task` or set `schedule` timers**. Simply end your turn with zero tool calls; Antigravity's reactive wakeup will automatically resume you the instant `agentspace_cli.py` finishes. (Or call the synchronous `agentspace_ask` MCP tool.)
3. **Step 3 — Zero-Guesswork Error Loop (Multi-Turn Continuity):**
   - After applying `gemini-4-argon`'s changes, immediately verify locally via `run_command` (unit tests, syntax check, or dry run).
   - If an error or edge case appears, **DO NOT guess or improvise a fix on Flash**. Send the exact stderr traceback back to the **same** `session_tag` thread (`agentspace_ask` reuses the existing session automatically on Turn 2+ without re-uploading `-f` files) and let `gemini-4-argon` diagnose the root cause.
4. **Step 4 — Subagent Model Rules (`Model: "flash"` vs `Model: "inherit"`):**
   - **NEVER use Flash Low (`flash_lite`).** (Also note: `Model: "pro"` is not mapped in `TieredModelConfig`; use `Model: "inherit"` or `Model: "flash"` with `[EFFORT: HIGH]` / `[EFFORT: MEDIUM]`).
   - When the main agent is running on **Gemini 3.7 Flash** and needs a complex script (e.g., an 800-line `pptxgenjs` deck builder in Stage 2 of the `.pptx` pipeline), have `gemini-4-argon` in Agentspace generate the complete `build_deck.js` script or exhaustive spec first (`-o ... --summary-only`), and use the `Model: "flash"` (`[EFFORT: HIGH]` / `[EFFORT: MEDIUM]`) subagent to execute the build and run M365 Visual QA (`office_view_hook.py`).

## How to Execute Queries

### Session Naming & Continuity Rules (Default Behavior)
- **Keep Sessions by Default:** Do **not** pass `--ephemeral` on normal queries. Keeping sessions allows multi-turn follow-ups and lets the user view the chat in the Agentspace Web UI.
- **Automatic `[agy-bridge]` Prefix:** Every newly created session is automatically renamed via `widgetUpdateSession` so its Web UI title starts with **`[agy-bridge]`** (e.g., `[agy-bridge] Non-5G Device Subscribers`).
- **Automatic Multi-Turn Continuity per Antigravity Chat:**
  - Always pass `--session-tag <first_8_chars_of_AGY_Conversation_ID>`.
  - `agentspace_cli.py` saves the active Agentspace session ID per mode/agent inside `./outputs/chat_<tag>/session_state.json`.
  - Subsequent calls in the same Antigravity chat with the same `--session-tag` automatically continue the existing `[agy-bridge]` session!
  - Pass `--new-session` only if switching to an unrelated topic in the same mode, or `--ephemeral` only for throwaway utility checks.

### 1. Fast Mode (`gemini-4-argon` — ~3 seconds)
Skips slow enterprise data store federated search and queries `gemini-4-argon` directly:
```powershell
python "agentspace_cli.py" "<prompt>" --thinking MEDIUM --session-tag <8_char_conv_id>
```
*(Or call the `agentspace_ask` MCP tool with `session_tag: "<8_char_conv_id>"`.)*

### 1b. Maximum AGY Token-Saving Mode (File Input + Session-Scoped File Output)
When sending large code/SQL files or expecting a large output (e.g., >100 lines of SQL/Python or a long report), avoid reading/dumping huge text into Antigravity's context window:
- Pass `-f <path>` (`input_files`) so `agentspace_cli.py` reads the file directly from disk (only needed on Turn 1 of a session!).
- Pass `--session-tag <first_8_chars_of_AGY_Conversation_ID>` + `-o <name>` + `--summary-only` so the full output is saved to `./outputs/chat_<tag>/chat_<tag>__<timestamp>__<session_id>__<name>` and only a 500-char preview is returned to AGY:
```powershell
python "agentspace_cli.py" "Refactor and optimize this query" -f input.sql -o optimized.sql --session-tag 95e5efcf --summary-only
```
> **Session Isolation Rule:** Never read files from `./outputs/chat_<other_tag>/` belonging to a different Antigravity conversation ID unless the user explicitly asks for them.

### 2. Calling Netra Agent, Slides Agent, or Other Custom IOH Agents
Pass `--agent netra` (maps to Agent ID `17783079275007264980`, sets `answerGenerationMode: "AGENT"`, and coordinates `agent_cvm`, `agent_user_network_analytics`, `agent_techno`, `agent_export`, `agent_user_analytics`):
```powershell
python "agentspace_cli.py" "<netra query>" --agent netra --session-tag <8_char_conv_id>
```
Other built-in aliases: `ace` (`8461818071814491910`), `slides` / `pptx` (`17216682253898748109`), `agb` (`18420663427156982501`), `catalyst` (`app_catalyst_agent`).

### 2b. Default Presentation (`.pptx`) Workflow: Agentspace Detailed Outline $\rightarrow$ Local Subagent Build (`executive-slides` + `minimal-slides` + `pptx`)
- **Default Rule:** Whenever the user wants a PowerPoint presentation (`.pptx`), **DO NOT use Agentspace's `slidegen_agent` (`--agent slides`) by default**, because Agentspace converts HTML/Tailwind to PPTX (producing 0 native editable charts and frequent DOM clipping/border-radius bugs). Instead, use the **3-Stage Hybrid Pipeline**:
  1. **Stage 1 — Request a Complete, Exhaustive PPTX Outline from Agentspace (`-o pptx_outline.md --summary-only`):**
     - After gathering data in Agentspace (e.g., via `--agent netra` or `gemini-4-argon`), instruct Agentspace to synthesize a **complete, slide-by-slide Markdown specification** and save it directly to `./outputs/chat_<tag>/` with `--summary-only` (so it costs ~0 AGY tokens).
     - **Mandatory Prompt Template for Agentspace Outline Generation:**
       ```powershell
       python "agentspace_cli.py" "Synthesize all findings into a complete, exhaustive <N>-slide executive presentation outline in Markdown. Do NOT summarize or omit numbers. For EVERY slide, explicitly include:
       1. Section Tracker & Single-Line McKinsey Action Title (<= 80 chars, stating the quantitative 'So What?' conclusion).
       2. Context Subtitle (<= 110 chars, metric, unit, cohort, and snapshot/window dates).
       3. Native Chart Specification: Exact chart type (column/bar/line), Category Labels, and Numeric Series values (strictly separating rate/%/ARPU metrics on the chart from raw volume/headcount in the table).
       4. Complete Multi-Column Markdown Table: Every cohort/sub-segment, headcount, % share, net revenue, ARPU, payload, and delta with zero omitted rows.
       5. Analytical Nuance & Callout Box: 1-2 sentences explaining the commercial/technical root cause or strategic action.
       6. Source Footnote: Exact table name, filter conditions, and date range." -o pptx_outline.md --session-tag <8_char_conv_id> --summary-only
       ```
  2. **Stage 2 — Delegate `.pptx` Generation & M365 Visual QA to a Local Subagent (`invoke_subagent`):**
     - Call `invoke_subagent(TypeName="self", Role="Executive Slide Builder & Visual QA")` and pass it the saved outline file path (`./outputs/chat_<tag>/chat_<tag>__...__pptx_outline.md`) and target `.pptx` output path (`./outputs/chat_<tag>/chat_<tag>__local_agy_skills__<name>.pptx`).
     - Instruct the subagent to:
       1. Read `executive-slides`, `minimal-slides`, and `pptx` (`SKILL.md`), and run `select_palette.py` on the outline file.
       2. Build the deck via `pptxgenjs` with **true native editable Office charts (`pres.charts.BAR`/`LINE`)**, **Tufte tables** (top/bottom rules only, zero vertical gridlines, single-line rows), and **single-line Cambria Action Titles**.
       3. Run closed-loop M365 Visual QA (`office_view_hook.py "<pptx_path>" --pages "..." --summary-only --render` — via `/opt/homebrew/bin/python3 "$HOME/.gemini/config/office_view_hook.py"` on macOS or `python "%USERPROFILE%\.gemini\config\office_view_hook.py"` on Windows), inspect the rendered `.png` slides via `read_file`, fix any text wrapping or table overflow, and return only a concise summary + final `.pptx` path to the main agent.
  3. **Optional Fallback (`--agent slides` / `--export-slides`):**
     - Only use `python "agentspace_cli.py" --agent slides` or `--export-slides` if the user explicitly asks to export an Agentspace Canvas/Slides artifact from the Web UI.

### 3. Enterprise Search Mode (Confluence, SharePoint, Jira, OneDrive, ServiceNow)
```powershell
python "agentspace_cli.py" "<search query>" --search --session-tag <8_char_conv_id>
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
