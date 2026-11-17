# 2. CLI & Core Workflows

## Built-in `--agent` Aliases

| Alias | Agent ID | Description |
| :--- | :--- | :--- |
| `netra` | `17783079275007264980` | **Netra Multi-Agent Coordinator** (`agent_cvm`, `agent_user_network_analytics`, `agent_techno`, `agent_export`, `agent_user_analytics`) |
| `ace` | `8461818071814491910` | **ACE Platform Agent** |
| `office-workflow-suite`, `office`, `slides`, `pptx` | `14950672669329422296` | **`office-workflow-suite` Skill Agent** (Canvas slides + native `.pptx` export) |
| `office-creator` | `17216682253898748109` | **Office File Creator** (Multi-Agent `.pptx`, `.xlsx`, `.docx` builder) |
| `office-creator-2`, `office2`, `office-v2` | `2291045905737541211` | **Office File Creator 2.0** (Low-Code V2 Multi-Agent with Visual QA Gate) |
| `agb` | `18420663427156982501` | **AGB Agent** |
| `catalyst` | `app_catalyst_agent` | **App Catalyst Agent** |
| `netra-office-workflow`, `workflow` | `8458183310708652909` | **Netra to Office File Creator Workflow** |

---

## Core Workflows

### 1. IOH Enterprise Data (`--agent netra` / `--agent ace`)
```powershell
python agentspace_cli.py "Analyze 90-day CVM conversion and ARPU by brand" --agent netra --session-tag mytask01
python agentspace_cli.py "Extract full cohort table" --agent netra -o netra_data.md --session-tag mytask01 --summary-only
```

### 2. Federated Enterprise Search (`--search`)
Queries Confluence, Jira, SharePoint, OneDrive, and ServiceNow:
```powershell
python agentspace_cli.py "Find architecture specs for CVM ingestion" --search --session-tag mytask01
```

### 3. Agentspace Advisor Mode (`--model gemini-4-argon` / `gemini-4-carbon`, `--thinking HIGH`)
Used when Antigravity is running a lighter local model (e.g., Hydrogen) and needs deep architectural reasoning:
- Attach local files directly with `-f <path>` (never paste large codeblocks into the prompt).
- Save the resulting implementation plan to disk via `-o advisor_plan.md --summary-only`.
```powershell
python agentspace_cli.py "Review the attached files and produce a step-by-step implementation plan." --model gemini-4-argon --thinking HIGH -f path/to/file1.py -f path/to/file2.py -o advisor_plan.md --session-tag mytask01 --summary-only
```

### 4. Executive Presentations (Mode 3A Default vs. Mode 3B On-Demand)
- **Mode 3A (Default)**: Query Netra/Search to write an exhaustive slide-by-slide Markdown outline (`-o pptx_outline.md --summary-only`), then build the `.pptx` locally via an Antigravity subagent (`executive-slides` + `minimal-slides` + `pptx`).
- **Mode 3B (On-Demand)**: Generate slides directly in Agentspace via `--agent slides` (or `--agent office-creator-2`) and export `.pptx`/`.pdf`:
  ```powershell
  python agentspace_cli.py "Create an 8-slide deck on 5G Upgrade Target Sizing" --agent slides --session-tag mytask01
  python agentspace_cli.py --export-slides --export-format pptx,pdf --session-tag mytask01
  ```

### 5. Media Session Cleanup (AI Image/Video Generation Only)
- Standalone Imagen/Veo prompts share a single `model:<model_id>:media` session slot per `--session-tag` and auto-rotate every **3 prompts** (`--max-media-prompts 3`).
- Data visualization charts from Netra/code-execution are **never** treated as media sessions.
- Run `python agentspace_cli.py --finish-task <session_tag>` when done, or `python agentspace_cli.py --cleanup-media-sessions` to sweep orphaned media sessions.
