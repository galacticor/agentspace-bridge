---
name: agentspace-advisor
description: >-
  Use Gemini 4 Argon (gemini-4-argon) or Gemini 4 Carbon (gemini-4-carbon) in IOH
  Agentspace as an external Senior Architect / Advisor when Antigravity is running
  a lighter local model (e.g., Hydrogen). Shares local codebase context efficiently
  via `-f <file_path>` without burning Antigravity output tokens, and writes an
  actionable implementation plan to disk via `-o advisor_plan.md --summary-only`.
---

# Agentspace Advisor Mode (Hydrogen Executor + Argon/Carbon Architect)

## When to Use vs. When NOT to Use

- **USE `agentspace-advisor` when:**
  - Antigravity is running a lighter local model (e.g., Hydrogen) and needs deep architectural reasoning, multi-file refactoring plans, or complex root-cause debugging.
  - You want **Gemini 4 Argon (`gemini-4-argon`)** or **Gemini 4 Carbon (`gemini-4-carbon`)** with `--thinking HIGH` to review local files and produce a step-by-step implementation manifest.
- **DO NOT USE `agentspace-advisor` when:**
  - Performing trivial local edits, simple syntax/lint fixes, or routine unit-test loops. Keep those **100% local in Antigravity**.

---

## Core Workflow (Zero Output-Token Context Sharing)

1. **Attach Local Files Directly (`-f <file_path>`):**
   - Never paste large file contents into the prompt. Pass one or more `-f <path>` flags to `agentspace_cli.py` so the files are uploaded directly from disk.
2. **Select Advisor Model & High Thinking:**
   - Pass `--model gemini-4-argon` (or `--model gemini-4-carbon`) and `--thinking HIGH`.
3. **Maintain Session Continuity (`--session-tag`):**
   - Always pass `--session-tag <8_char_conv_id>` so follow-up turns reuse the same `[agy-bridge]` session without re-uploading earlier files.
4. **Interactive Agentic Context Loop (Let the Advisor Ask for What It Needs):**
   - Instruct the Advisor in your prompt: *"If you need additional files, schemas, or command outputs before finalizing the plan, list them under `[NEED_CONTEXT]` instead of guessing."*
   - If the Advisor responds with `[NEED_CONTEXT]`, gather those exact files/outputs locally and send them in the next turn using `-f <requested_file>` with the **same `--session-tag`** (cap at 2–3 rounds).
5. **Save the Implementation Plan to Disk (`-o advisor_plan.md --summary-only`):**
   - Save the advisor's full plan to `./outputs/chat_<tag>/` and return only a compact preview to Antigravity's context.
   - Read the saved `advisor_plan.md` locally and execute the steps in Antigravity.

### Example Command

*(If `agentspace_ask` MCP tool is available, you can call it directly; otherwise run `agentspace_cli.py` using its repo path so it works from any workspace:)*

```bash
python3 "$HOME/Documents/Projects/agentspace-bridge/agentspace_cli.py" "Review the attached files and produce a step-by-step implementation plan with exact file paths, function signatures, edge cases, and verification steps." --model gemini-4-argon --thinking HIGH -f path/to/file1.py -f path/to/file2.py -o advisor_plan.md --session-tag <8_char_conv_id> --summary-only
```

*(Note: If `agentspace_cli.py` backgrounds after `WaitMsBeforeAsync`, do **not** poll `manage_task` or set `schedule` timers—end your turn and wait for Antigravity's reactive wakeup.)*
