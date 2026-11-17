# IOH Agentspace Bridge — Knowledge Base

This directory contains structured technical documentation for the **IOH Agentspace Bridge** repository.

## Documents

1. **[01_architecture_and_auth.md](01_architecture_and_auth.md)**
   - Target Discovery Engine endpoints (`widgetStreamAssist`, `widgetExportImmersiveArtifact`, etc.)
   - GCP Engine & Widget Config (`cid`)
   - Per-user BYOID Microsoft Entra ID authentication, `/auth/getoxsrf`, and 5-minute HS256 JWT minting
   - Silent headless refresh, multi-account picker handling, and `[agy-bridge]` session lifecycle
2. **[02_cli_and_workflows.md](02_cli_and_workflows.md)**
   - Complete `agentspace_cli.py` flag reference and `--agent` aliases
   - Netra & ACE data queries, Federated Enterprise Search (`--search`)
   - **Agentspace Advisor Mode** (`--model gemini-4-argon` / `gemini-4-carbon`, `--thinking HIGH`, `-f`)
   - Executive Presentations: Mode 3A (Hybrid Outline $\rightarrow$ Local Subagent) vs. Mode 3B (Agentspace `office-workflow-suite` / `office-creator-2`)
   - Media session rotation (`--max-media-prompts 3`), `--finish-task`, and `--cleanup-media-sessions`
3. **[03_mcp_and_skills.md](03_mcp_and_skills.md)**
   - `setup_mcp.py` automated installer
   - `agentspace_mcp_server.py` MCP tool definitions (`agentspace_ask`, `agentspace_export_slides`, etc.)
   - Antigravity Skills (`ioh-agentspace` and `agentspace-advisor`)
4. **[04_pptx_and_chrome_extension.md](04_pptx_and_chrome_extension.md)**
   - Chrome/Edge Extension (`chrome_extension/`) & local bridge server (`--serve-chrome` on port `18765`)
   - `dom_pptx_compiler.py` & `pptx_lxml_wrapper.py`
   - `knowledge_bundle_v2/` zero-dependency OOXML engines & OneDrive connector (`pptx_payload.txt`)
