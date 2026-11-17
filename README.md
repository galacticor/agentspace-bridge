# IOH Agentspace Bridge for Google Antigravity

Connects **Google Antigravity (AGY)** and your local terminal directly to **Indosat Ooredoo Hutchison's (IOH) Gemini Enterprise (Agentspace)** instance (`https://agentspace.ioh.co.id` / `vertexaisearch.cloud.google`) powered by **Gemini 4 Argon (`gemini-4-argon`)**, custom IOH data agents (**Netra Agent**, **ACE Platform**), federated enterprise search (**Confluence, Jira, SharePoint, OneDrive, ServiceNow**), and executive Office deliverable engines (**`office-workflow-suite`**, **`Office File Creator 2.0`**).

---

## Table of Contents

1. [Purpose & Strict Scope (When to Use vs. Not Use)](#1-purpose--strict-scope-when-to-use-vs-not-use)
2. [Security & Authentication Architecture](#2-security--authentication-architecture)
3. [Quick Start & Installation (Windows & macOS)](#3-quick-start--installation-windows--macos)
4. [Core Workflows & Usage Examples](#4-core-workflows--usage-examples)
5. [MCP Server Tools (Inside Antigravity)](#5-mcp-server-tools-inside-antigravity)
6. [Chrome Extension & Native PPTX Compiler](#6-chrome-extension--native-pptx-compiler)
7. [Repository Structure](#7-repository-structure)
8. [Configuration & Environment Variables](#8-configuration--environment-variables)
9. [Safe Internal Distribution Guide](#9-safe-internal-distribution-guide)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Purpose & Strict Scope (When to Use vs. Not Use)

> [!IMPORTANT]
> **Do NOT Offload General Local Coding:**
> Never use `agentspace_cli.py` or `agentspace_ask` to offload general coding, local debugging, or unit-test fixing that Antigravity can execute locally. Routing local code/test loops through an external CLI consumes **4×–5× more Antigravity context tokens** due to per-turn system-prompt overhead. Solve all general coding, SQL authoring, and debugging **100% locally in Antigravity**.

Use **IOH Agentspace Bridge** strictly for tasks requiring **IOH enterprise data, internal company knowledge, or Agentspace-hosted agents**:

1. **IOH Enterprise Data Agents (`--agent netra`, `--agent ace`)**: Query live IOH subscriber cohorts, CVM conversion, revenue, ARPU, network analytics, and BigQuery marts via **Netra Agent (`17783079275007264980`)** (`agent_cvm`, `agent_user_network_analytics`, `agent_techno`, `agent_export`, `agent_user_analytics`) or **ACE Platform (`8461818071814491910`)**.
2. **IOH Enterprise Knowledge Base Search (`--search`)**: Search across internal IOH connectors (**Confluence, SharePoint, Jira, OneDrive, ServiceNow**).
3. **IOH Executive Presentations & Deliverables (`.pptx`, `.xlsx`, `.docx`)**:
   - **Mode 3A (Default — Hybrid Pipeline)**: Extract a complete, quantitative slide-by-slide Markdown outline from Netra/Search (`-o pptx_outline.md --summary-only`), then delegate the `.pptx` build and M365 Visual QA to a local Antigravity subagent.
   - **Mode 3B (On-Demand — Agentspace Build)**: Generate slides, spreadsheets, or memos directly inside Agentspace via `--agent office-workflow-suite` (`--agent slides`) or `--agent office-creator-2` and export native `.pptx`/`.pdf` locally at zero LLM token cost.
4. **Agentspace Advisor Mode (`--model gemini-4-argon` / `gemini-4-carbon`, `--thinking HIGH`)**:
   - When Antigravity is running a lighter local model (e.g., Hydrogen) and needs deep architectural reasoning, multi-file refactoring plans, or complex root-cause debugging, attach local files via `-f <path>` and save an actionable implementation plan to disk via `-o advisor_plan.md --summary-only`.

---

## 2. Security & Authentication Architecture

This repository contains **zero hardcoded credentials, API keys, or personal tokens**:

- **Per-User Workforce Identity (BYOID) Authentication**: Each colleague authenticates with their own `@ioh.co.id` Microsoft Entra ID account via `python agentspace_cli.py --refresh-token`.
- **Short-Lived Local Signing Key (`./agentspace_xsrf.json`)**: `agentspace_cli.py` captures your browser session's `/auth/getoxsrf` key (`xsrfToken`, `keyId`, and `csesidx`) into `./agentspace_xsrf.json` (git-ignored) and mints 5-minute HS256 JWTs (`Authorization: Bearer <jwt>`) locally using Python's standard `hmac` + `hashlib` libraries.
- **Isolated Browser Auth Profile (`./.auth_profile/`)**: Uses a dedicated local browser profile directory (git-ignored) separate from your personal browser profile. Defaults to **Microsoft Edge (`msedge`)** on Windows and **Google Chrome (`chrome`)** on macOS, with automatic fallback across Edge, Chrome, and Chromium.
- **Silent Headless Refresh (`~8s`, Zero Popup Interruption)**: When `./agentspace_xsrf.json` expires (`HTTP 401`/`403`), `agentspace_cli.py` first performs a silent headless refresh using `.auth_profile/` and automatically selects your `@ioh.co.id` account tile on the Microsoft Entra ID account picker. It only opens a visible browser window if interactive 2FA or password entry is required.
- **Never Print Tokens in Chat**: Both `GEMINI.md` and `.agents/skills/ioh-agentspace/SKILL.md` enforce a strict rule preventing the AI agent from reading or printing `agentspace_xsrf.json` into chat transcripts.

---

## 3. Quick Start & Installation (Windows & macOS)

### Prerequisites
- **Python 3.10+**
- **Microsoft Edge** (pre-installed on Windows) or **Google Chrome** (macOS/Windows)
- Active IOH corporate account (`@ioh.co.id`) with access to `https://agentspace.ioh.co.id`

### Step 1: Clone the Repository
```powershell
# Windows (PowerShell)
cd $HOME\Documents
git clone <INTERNAL_REPO_URL> agentspace-bridge
cd agentspace-bridge
```
```bash
# macOS / Linux
cd ~/Documents
git clone <INTERNAL_REPO_URL> agentspace-bridge
cd agentspace-bridge
```

### Step 2: Install Python Dependencies
Creating a local `.venv` (or installing into your user Python environment) is recommended for Playwright browser automation and local `.pptx` compilation:

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Register the MCP Server & Skill in Google Antigravity
Run `setup_mcp.py` once. It automatically:
1. Detects the Python interpreter with `playwright` installed (`.venv`, Homebrew, or system Python).
2. Registers `ioh-agentspace` in `~/.gemini/config/mcp_config.json`.
3. Links (or copies) `.agents/skills/ioh-agentspace/SKILL.md` into `~/.gemini/config/skills/ioh-agentspace/`.

```powershell
# Windows
python setup_mcp.py

# macOS / Linux
python3 setup_mcp.py
```

### Step 4: Authenticate with Your `@ioh.co.id` Account
Run the initial token refresh to log in via Microsoft Entra ID SSO and generate your local `./agentspace_xsrf.json`:

```powershell
python agentspace_cli.py --refresh-token
```
A browser window will open to `https://agentspace.ioh.co.id`. Sign in with your `@ioh.co.id` credentials; once the portal loads, the window will close automatically and save `./agentspace_xsrf.json`. Future token refreshes happen silently in headless mode.

---

## 4. Core Workflows & Usage Examples

### A. Querying IOH Data Agents (`--agent netra` / `--agent ace`)
```powershell
# Query Netra Agent with multi-turn session continuity (--session-tag)
python agentspace_cli.py "Analyze 90-day CVM conversion and ARPU by brand" --agent netra --session-tag mytask01

# Save large tables/reports directly to ./outputs/chat_<tag>/ with a compact 500-char stdout preview
python agentspace_cli.py "Extract full cohort table for 5G vs Non-5G subscribers" --agent netra -o netra_cohort_data.md --session-tag mytask01 --summary-only
```

**Built-in `--agent` Aliases:**
| Alias | Agent ID | Description |
| :--- | :--- | :--- |
| `netra` | `17783079275007264980` | **Netra Multi-Agent Coordinator** (`agent_cvm`, `agent_user_network_analytics`, `agent_techno`, `agent_export`, `agent_user_analytics`) |
| `ace` | `8461818071814491910` | **ACE Platform Agent** |
| `office-workflow-suite`, `office`, `slides`, `pptx` | `14950672669329422296` | **`office-workflow-suite` Skill Agent** (Canvas slides + native `.pptx` export) |
| `office-creator` | `17216682253898748109` | **Office File Creator** (Multi-Agent `.pptx`, `.xlsx`, `.docx` builder) |
| `office-creator-2`, `office2` | `2291045905737541211` | **Office File Creator 2.0** (Low-Code V2 Multi-Agent with Visual QA Gate) |
| `agb` | `18420663427156982501` | **AGB Agent** |
| `catalyst` | `app_catalyst_agent` | **App Catalyst Agent** |
| `netra-office-workflow`, `workflow` | `8458183310708652909` | **Netra to Office File Creator Workflow** |

### B. Searching Internal IOH Knowledge Base (`--search`)
Queries internal IOH Confluence pages, Jira tickets, SharePoint sites, OneDrive documents, and ServiceNow records:
```powershell
python agentspace_cli.py "Find architecture specs and Jira tickets for CVM campaign ingestion" --search --session-tag mytask01
```

### C. Executive Presentations (`.pptx`)
- **Mode 3A (Default — Hybrid Outline $\rightarrow$ Local Antigravity Build)**:
  ```powershell
  python agentspace_cli.py "Synthesize our Netra findings into an exhaustive 8-slide executive presentation outline in Markdown with Action Titles, native chart series, and full cohort tables." -o pptx_outline.md --session-tag mytask01 --summary-only
  ```
- **Mode 3B (On-Demand — Direct Agentspace Slide Generation & Export)**:
  ```powershell
  # Generate slides via office-workflow-suite and auto-export .pptx to ./outputs/chat_<tag>/
  python agentspace_cli.py "Create an 8-slide executive presentation on 5G Upgrade Target Sizing" --agent slides --session-tag mytask01

  # Re-export an existing Canvas session to native .pptx and .pdf at zero LLM token cost
  python agentspace_cli.py --export-slides --export-format pptx,pdf --session-tag mytask01
  ```

### D. Session Lifecycle & Media Cleanup
- Every kept session created through the bridge is automatically prefixed with **`[agy-bridge]`** in the Agentspace Web UI sidebar.
- Follow-up queries using the same `--session-tag` and `--agent`/mode automatically continue the same multi-turn session (tracked in `./outputs/chat_<tag>/session_state.json`).
- Pass `--new-session` to start a fresh thread, or `--ephemeral` for one-off utility checks that auto-delete after completion.

```powershell
# List your recent Agentspace chat sessions
python agentspace_cli.py --list-sessions --limit 20

# Delete a specific session by ID
python agentspace_cli.py --delete-session <SESSION_ID>

# Clean up media-generation sessions for a finished task tag
python agentspace_cli.py --finish-task <SESSION_TAG>

# Sweep orphaned AI image/video generation sessions from the Web UI sidebar
python agentspace_cli.py --cleanup-media-sessions
```

### E. Agentspace Advisor Mode (`--model gemini-4-argon` / `gemini-4-carbon`, `--thinking HIGH`)
When Antigravity is running a lighter local model (e.g., Hydrogen) and needs deep architectural reasoning, multi-file refactoring plans, or complex root-cause debugging:
1. Attach local files directly via `-f <path>` (never paste large codeblocks into the prompt).
2. Pass `--model gemini-4-argon` (or `gemini-4-carbon`), `--thinking HIGH`, and `--session-tag <8_char_conv_id>`.
3. Save the resulting implementation plan to disk via `-o advisor_plan.md --summary-only` and execute it locally in Antigravity:
```powershell
python agentspace_cli.py "Review the attached files and produce a step-by-step implementation plan with exact file paths, function signatures, edge cases, and verification steps." --model gemini-4-argon --thinking HIGH -f path/to/file1.py -f path/to/file2.py -o advisor_plan.md --session-tag mytask01 --summary-only
```

---

## 5. MCP Server Tools (Inside Antigravity)

Once registered via `python setup_mcp.py`, Google Antigravity has native access to these MCP tools from `agentspace_mcp_server.py`:

| MCP Tool | Description |
| :--- | :--- |
| `agentspace_ask` | Query `gemini-4-argon`, IOH Agents (`agent="netra"`, `"ace"`, `"slides"`, `"office-creator-2"`), or Enterprise Search (`enable_enterprise_search=True`). Supports `input_files`, `output_filename`, `session_tag`, and `summary_only`. |
| `agentspace_export_slides` | Export Canvas/Slides artifacts or native `python-pptx` scripts from an Agentspace session directly to `.pptx` and/or `.pdf` inside `./outputs/chat_<session_tag>/`. |
| `agentspace_list_sessions` | List recent chat sessions (`limit=20`). |
| `agentspace_delete_session` | Delete a specific chat session by ID (`widgetDeleteSession`). |
| `agentspace_finish_task` | Delete tracked media generation sessions for a finished task (`session_tag`) while preserving data/search/slides sessions. |
| `agentspace_cleanup_media_sessions` | Scan recent sessions and remove standalone image/video generation clutter from the Web UI sidebar. |
| `agentspace_refresh_token` | Refresh `./agentspace_xsrf.json` via headless/interactive browser login. |

---

## 6. Chrome Extension & Native PPTX Compiler

The repository includes an optional Chrome/Edge Extension (`./chrome_extension/`) that adds a **`⬇ Native PPTX`** button to the top-right corner of the Agentspace Web UI (`https://agentspace.ioh.co.id` / `https://vertexaisearch.cloud.google`).

1. **Start the local Chrome bridge server**:
   ```powershell
   python agentspace_cli.py --serve-chrome
   ```
   *(Listens on `http://127.0.0.1:18765`.)*
2. **Load the unpacked extension in Chrome or Edge**:
   - Open `chrome://extensions` (or `edge://extensions`).
   - Enable **Developer mode**.
   - Click **Load unpacked** and select the `chrome_extension/` folder in this repository.
3. Open any Agentspace session containing slides and click **`⬇ Native PPTX`** to compile and download a formatted widescreen `.pptx` via `pptx_lxml_wrapper.py` or `dom_pptx_compiler.py`.

---

## 7. Repository Structure

```text
agentspace-bridge/
├── .agents/skills/
│   ├── ioh-agentspace/SKILL.md       # Antigravity skill instructions (auto-linked by setup_mcp.py)
│   └── agentspace-advisor/SKILL.md   # Advisor Mode skill (Hydrogen executor + Argon/Carbon architect)
├── knowledge_base/                   # Structured repository documentation (architecture, CLI, MCP, PPTX)
│   ├── README.md
│   ├── 01_architecture_and_auth.md
│   ├── 02_cli_and_workflows.md
│   ├── 03_mcp_and_skills.md
│   └── 04_pptx_and_chrome_extension.md
├── chrome_extension/             # Unpacked Chrome/Edge extension for 1-click Native PPTX export
│   ├── manifest.json
│   ├── content.js
│   └── service-worker.js
├── knowledge_bundle_v2/          # Zero-dependency OOXML engines for Agentspace Office File Creator
│   ├── 01_pptx_lxml_engine_and_brand_logos.md
│   ├── 02_xlsx_inmemory_engine.md
│   └── 03_docx_inmemory_engine.md
├── workflows/
│   └── netra_to_office_workflow.json  # Multi-agent workflow template (Netra -> Approval -> PPTX/XLSX)
├── agentspace_cli.py             # Core CLI, BYOID JWT auth, RPC client, and session manager
├── agentspace_mcp_server.py      # Zero-dependency JSON-RPC stdio MCP server for Antigravity
├── dom_pptx_compiler.py          # HTML/Tailwind Canvas -> Playwright DOM -> python-pptx compiler
├── pptx_lxml_wrapper.py          # Reusable python-pptx + lxml consulting design system wrapper
├── build_knowledge_bundle_v2.py  # Generator script for ./knowledge_bundle_v2/
├── deploy_office_creator_v2.py   # Admin utility to sync/deploy Office File Creator V2 instructions
├── office_creator_v2_created.json# Sanitized baseline definition for Office File Creator 2.0
├── setup_mcp.py                  # Cross-platform installer for Antigravity MCP & Skill
├── requirements.txt              # Python dependencies (playwright, python-pptx, lxml)
├── .env.example                  # Optional environment variable overrides template
├── .gitignore                    # Excludes tokens, browser profiles, and session outputs
├── GEMINI.md                     # Workspace rules & technical architecture reference
└── README.md                     # Project documentation and setup guide
```

---

## 8. Configuration & Environment Variables

All defaults work out-of-the-box for IOH employees. For personal settings (such as your employee ID, `csesidx`, or personal OneDrive folder IDs), `agentspace_cli.py` automatically loads **`./.env`** and **`./agentspace_local.json`** (both are git-ignored so your personal info is never committed). See [`.env.example`](.env.example) and [`agentspace_local.example.json`](agentspace_local.example.json):

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `AGENTSPACE_ENTRY_URL` | `https://agentspace.ioh.co.id` | IOH Agentspace SSO entry URL |
| `AGENTSPACE_CONFIG_ID` | `384c42b0-2885-415a-82d5-f2babc063b6e` | Discovery Engine Widget Config ID (`cid`) |
| `AGENTSPACE_MODEL` | `gemini-4-argon` | Default model ID for standard queries |
| `AGENTSPACE_THINKING` | `MEDIUM` | Default thinking effort (`LOW`, `MEDIUM`, `HIGH`, `NONE`) |
| `AGENTSPACE_BROWSER` | `msedge` (Win) / `chrome` (Mac) | Preferred browser channel for Playwright SSO |
| `AGENTSPACE_XSRF_PATH` | `./agentspace_xsrf.json` | Custom path for the XSRF JSON file |
| `AGENTSPACE_MAX_MEDIA_PROMPTS` | `3` | Max AI image/video prompts before auto-rotating media session |
| `AGENTSPACE_ONEDRIVE_DRIVE_ID` | *(dynamic)* | Optional OneDrive `driveId` override for Mode 3B `.pptx` upload |
| `AGENTSPACE_ONEDRIVE_PARENT_ID` | *(dynamic)* | Optional OneDrive folder `ParentId` override |
| `AGENTSPACE_ONEDRIVE_FOLDER_NAME` | `Agentspace_Exports` | Target OneDrive folder name for Mode 3B `.pptx` exports |

---

## 9. Safe Internal Distribution Guide

> [!CAUTION]
> **Never zip or copy your working folder directly (`Compress-Archive *`)** if you have already logged in locally, because your working folder contains untracked local state (`agentspace_xsrf.json`, `.auth_profile/`, and `outputs/`).

Always distribute the repository using **`git clone`** or **`git archive`** so only tracked, sanitized source files are shared:

```powershell
# Option 1: Create a clean, credential-free release .zip from git tracked files only
git archive --format=zip --output=agentspace-bridge-clean.zip HEAD
```

Before pushing to an internal Git remote (e.g., GitHub Enterprise / GitLab / Bitbucket), verify with:
```powershell
git status --ignored
```
Ensure `agentspace_xsrf.json`, `.auth_profile/`, and `outputs/` remain under `Ignored files`.

---

## 10. Troubleshooting

- **`HTTP 401` / `HTTP 403` or `FileNotFoundError: Could not find a valid Agentspace XSRF JSON file`**:
  Run `python agentspace_cli.py --refresh-token` to sign in via your browser and save a fresh `./agentspace_xsrf.json`.
- **Multiple Microsoft Accounts on Windows (Personal/University + `@ioh.co.id`)**:
  `agentspace_cli.py` automatically detects the Microsoft Entra ID `"Pick an account"` screen and selects your `@ioh.co.id` tile. If your session requires interactive MFA approval, a browser window will open automatically.
- **`ModuleNotFoundError: No module named 'playwright'`**:
  Activate your virtual environment (`.\.venv\Scripts\Activate.ps1` or `source .venv/bin/activate`), run `pip install -r requirements.txt`, and re-run `python setup_mcp.py` so Antigravity points to the `.venv` Python interpreter.
- **MCP tools not appearing in Antigravity after `python setup_mcp.py`**:
  Reload or restart the Antigravity window so it reloads `~/.gemini/config/mcp_config.json`.
