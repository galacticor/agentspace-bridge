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
  - You want **Gemini 4 Argon (`gemini-4-argon`)** or **Gemini 4 Carbon (`gemini-4-carbon`)** with `--thinking MEDIUM` (or `--thinking HIGH` when explicitly requested) to review local files and produce a step-by-step implementation manifest.
- **DO NOT USE `agentspace-advisor` when:**
  - Performing trivial local edits, simple syntax/lint fixes, or routine unit-test loops. Keep those **100% local in Antigravity**.

---

## Core Workflow (Advisor as Planner, Small Model as Executor)

1. **Attach Local Files, Directories, or Globs (`files` / `-f`):**
   - Never paste large file contents into the prompt. Pass files, directories (e.g. `src/`), or globs (e.g. `src/**/*.py`) directly so they are read from disk.
2. **Use `agentspace_advise` (MCP) or `--advise` (CLI):**
   - Automatically selects `gemini-4-carbon` + `MEDIUM` thinking (override with `--thinking HIGH` / `thinking_level="HIGH"` when needed), attaches a compact repo file tree (`include_tree=True` / `--tree`), injects the **Planner Implementation Manifest** framing, and saves to `advisor_plan.md` with `--summary-only`.
3. **Maintain Session Continuity (`session_tag`):**
   - Always pass `session_tag` (`<8_char_conv_id>`) so follow-up turns reuse the same `[agy-bridge]` session without re-uploading earlier files.
4. **Interactive `[NEED_CONTEXT]` Loop:**
   - If the Advisor responds with `[NEED_CONTEXT]`, gather those exact files/command outputs locally and send them in the next turn with the **same `session_tag`** (cap at 2–3 rounds).
5. **Execute Locally:**
   - Read the saved `advisor_plan.md` locally and apply the edits + run the verification commands in Antigravity.

### Option A: Zero-Friction MCP (`agentspace_advise`)

```python
agentspace_advise(
    task="Refactor auth middleware to support token rotation and add unit tests.",
    files=["src/auth/", "tests/test_auth.py"],
    cwd="/path/to/repo",
    session_tag="<8_char_conv_id>",
)
```

### Option B: CLI (`--advise`)

```bash
python3 "$HOME/Documents/Projects/agentspace-bridge/agentspace_cli.py" "Refactor auth middleware to support token rotation." --advise -f src/auth/ -f tests/test_auth.py --session-tag <8_char_conv_id>
```

*(Note: If `agentspace_cli.py` backgrounds after `WaitMsBeforeAsync`, do **not** poll `manage_task` or set `schedule` timers—end your turn and wait for Antigravity's reactive wakeup.)*
