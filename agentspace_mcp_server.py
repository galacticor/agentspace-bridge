#!/usr/bin/env python3
r"""
Zero-dependency stdio MCP Server for IOH Agentspace (Gemini Enterprise - gemini-4-argon & Agents).
Allows Google Antigravity to offload queries, code generation, Netra/ACE agent queries, and enterprise search
(Confluence/Jira/SharePoint) to IOH Agentspace (`agentspace.ioh.co.id`), as well as list and delete chat sessions.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import threading

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from agentspace_cli import (
    ask_agentspace,
    cleanup_media_sessions,
    delete_session,
    export_session_artifacts,
    finish_task_sessions,
    list_sessions,
    refresh_xsrf_token,
    DEFAULT_BROWSER_CHANNEL,
    DEFAULT_MAX_MEDIA_PROMPTS,
    DEFAULT_MODEL,
    DEFAULT_THINKING,
    DEFAULT_CSESIDX,
)

_MAX_MCP_WORKERS = max(2, int(os.environ.get("AGENTSPACE_MCP_WORKERS", "6")))
_STDOUT_LOCK = threading.Lock()
_PROTO_STDOUT = sys.stdout

TOOLS = [
    {
        "name": "agentspace_ask",
        "description": (
            "Query IOH's Gemini Enterprise (Agentspace) ONLY when the task requires: "
            "(1) specialized IOH data agents ('netra', 'ace'), (2) internal @ioh.co.id enterprise search connectors "
            "(Confluence, SharePoint, Jira, OneDrive, ServiceNow via enable_enterprise_search=True), or "
            "(3) executive deliverables ('office-workflow-suite' / 'slides' / 'office-creator' / python_pptx=True). "
            "ROUTING RULE: Keep mechanical file edits, grep, and shell/test execution in Antigravity's native harness; "
            "use `agentspace_advise` instead for multi-file architectural or SQL planning."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt or question to send to an Agentspace Agent or Gemini 4 Argon.",
                },
                "agent": {
                    "type": "string",
                    "description": (
                        "Optional agent alias ('netra' for Netra Multi-Agent Coordinator 17783079275007264980, "
                        "'ace' for ACE Platform 8461818071814491910, 'office-workflow-suite' / 'slides' / 'pptx' for "
                        "Skill Agent 14950672669329422296, 'office-creator' for Office File Creator 17216682253898748109, "
                        "'office-creator-2' / 'office2' / 'office-v2' for Office File Creator 2.0 2291045905737541211, "
                        "'workflow' / 'netra-office-workflow' for 8458183310708652909, "
                        "'agb' for 18420663427156982501, 'catalyst' for app_catalyst_agent) or raw numeric Agent ID."
                    ),
                },
                "python_pptx": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set to true to use native python-pptx + lxml compilation mode with office-workflow-suite.",
                },
                "model": {
                    "type": "string",
                    "default": DEFAULT_MODEL,
                    "description": "Model ID when not calling a specialized agent (default: 'gemini-4-argon').",
                },
                "thinking_level": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "NONE"],
                    "default": DEFAULT_THINKING,
                    "description": "Thinking effort level for Gemini 4 Argon.",
                },
                "enable_enterprise_search": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set to true to search IOH Confluence, SharePoint, Jira, and OneDrive connectors.",
                },
                "session": {
                    "type": "string",
                    "description": "Optional session resource name returned by a previous call to continue a multi-turn conversation.",
                },
                "new_session": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set to true to force creating a brand-new Agentspace session instead of continuing the active session for `session_tag`.",
                },
                "delete_session_after": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set to true only for throwaway utility checks that should be deleted immediately after the response.",
                },
                "input_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of local file paths to attach directly from disk into the prompt without reading them into Antigravity's context window.",
                },
                "save_output": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set to true to save the full response into `./outputs/<session_tag>/` with a session-scoped filename.",
                },
                "output_filename": {
                    "type": "string",
                    "description": "Optional filename suffix (e.g., 'feature_query.sql' or 'report.md') saved inside `./outputs/<session_tag>/`.",
                },
                "session_tag": {
                    "type": "string",
                    "description": "Antigravity conversation ID prefix or tag (e.g. 'bba4da86') so other chat sessions never confuse output files.",
                },
                "summary_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "When saving output to a file, set to true to return only the saved file path and a short preview to save Antigravity context tokens.",
                },
                "max_media_prompts": {
                    "type": "integer",
                    "default": DEFAULT_MAX_MEDIA_PROMPTS,
                    "description": "Auto-clear/rotate media generation session after N prompts (default: 3).",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "agentspace_advise",
        "description": (
            "Advisor Planner Mode: delegate complex multi-file architecture, concurrency/refactoring plans, "
            "heavy BigQuery SQL design, or root-cause synthesis to Gemini 4 Carbon (HIGH thinking) while keeping "
            "a fast/low-quota native model in Antigravity as Executor. Attaches a compact repo tree + every relevant "
            "local file via `files` (attach config/setup/doc files upfront to avoid `[NEED_CONTEXT]` round-trips) "
            "and saves an Implementation Manifest to `./outputs/<session_tag>/`. For parallel subagents, pass "
            "distinct `session_tag` suffixes or `new_session=True`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The architectural, refactoring, or debugging task to plan.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of file paths, directories, or glob patterns to attach from disk.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional project root directory for resolving relative paths and building the repo tree.",
                },
                "include_tree": {
                    "type": "boolean",
                    "default": True,
                    "description": "Attach a compact repo file tree so the Advisor knows what files exist (default: true).",
                },
                "model": {
                    "type": "string",
                    "default": "gemini-4-carbon",
                    "description": "Advisor model ID ('gemini-4-carbon' or 'gemini-4-argon').",
                },
                "thinking_level": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "NONE"],
                    "default": "HIGH",
                    "description": "Thinking effort level (default: HIGH).",
                },
                "session_tag": {
                    "type": "string",
                    "description": "Antigravity conversation ID prefix (e.g. 'bba4da86') for session continuity.",
                },
                "new_session": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force creating a brand-new Agentspace session.",
                },
                "output_filename": {
                    "type": "string",
                    "default": "advisor_plan.md",
                    "description": "Filename to save the plan under ./outputs/<session_tag>/ (default: 'advisor_plan.md').",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "agentspace_finish_task",
        "description": (
            "Delete tracked media sessions (and any `_img*`/`_vid*` sub-sessions) for a finished subagent or task "
            "(`session_tag`) so image/video generation chats do not clutter the Agentspace Web UI sidebar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_tag": {
                    "type": "string",
                    "description": "The Antigravity conversation ID prefix or task tag (e.g. '7cb9cd02').",
                },
                "media_only": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true (default), deletes only media sessions and single-asset sub-sessions while preserving Netra/Search/Slides sessions.",
                },
            },
            "required": ["session_tag"],
        },
    },
    {
        "name": "agentspace_cleanup_media_sessions",
        "description": (
            "Scan recent Agentspace sessions and delete image/video generation chat sessions to declutter the Web UI sidebar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Number of recent sessions to scan (default: 50).",
                },
                "keep_latest": {
                    "type": "integer",
                    "default": 0,
                    "description": "Number of most recent media sessions to keep (default: 0).",
                },
            },
        },
    },
    {
        "name": "agentspace_delete_session",
        "description": (
            "Delete a chat session from IOH Agentspace (`widgetDeleteSession`) when a conversation is finished "
            "and no longer needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The session ID or full session resource path (`collections/.../sessions/<id>`) to delete.",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "agentspace_list_sessions",
        "description": "List recent chat sessions in IOH Agentspace (`widgetListSessions`) to inspect or clean up unused chats.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Maximum number of recent sessions to return (default: 20).",
                },
            },
        },
    },
    {
        "name": "agentspace_export_slides",
        "description": (
            "Export a Canvas/Slides immersive artifact from an IOH Agentspace session directly into a native `.pptx` "
            "(via `widgetExportImmersiveArtifact` RPC) and/or `.pdf` (via headless Web UI Export) inside `./outputs/<session_tag>/` "
            "without burning any Antigravity LLM tokens."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional Agentspace session ID (if omitted, uses the active slides session for `session_tag`).",
                },
                "formats": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["pptx", "pdf"]},
                    "default": ["pptx"],
                    "description": "Export formats to generate ('pptx', 'pdf', or both).",
                },
                "session_tag": {
                    "type": "string",
                    "description": "Antigravity conversation ID prefix (e.g. '95e5efcf').",
                },
            },
        },
    },
    {
        "name": "agentspace_refresh_token",
        "description": (
            "Pop up a browser window to automatically download/refresh the IOH Agentspace XSRF token "
            "and save it inside the project folder (`./agentspace_xsrf.json`). Note: `agentspace_ask`, "
            "`agentspace_list_sessions`, and `agentspace_delete_session` also auto-trigger this if the token expires."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "browser": {
                    "type": "string",
                    "default": DEFAULT_BROWSER_CHANNEL,
                    "description": f"Browser channel to open ('chrome' or 'msedge'; default on this OS: '{DEFAULT_BROWSER_CHANNEL}').",
                },
            },
        },
    },
]


def handle_request(msg: dict) -> dict | None:
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ioh-agentspace-mcp", "version": "1.2.0"},
            },
        }
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    elif isinstance(method, str) and method.startswith("notifications/"):
        return None
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }
    elif method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}

        try:
            if name == "agentspace_ask":
                summary_only = bool(args.get("summary_only", False))
                python_pptx = bool(args.get("python_pptx", False))
                save_output = bool(args.get("save_output", False)) or bool(args.get("output_filename")) or summary_only or python_pptx
                res = ask_agentspace(
                    prompt=args["prompt"],
                    model_id=args.get("model", DEFAULT_MODEL),
                    thinking_level=args.get("thinking_level", DEFAULT_THINKING),
                    session=args.get("session"),
                    enable_search=bool(args.get("enable_enterprise_search", False)),
                    agent=args.get("agent"),
                    delete_session_after=bool(args.get("delete_session_after", False)),
                    input_files=args.get("input_files"),
                    save_output=save_output,
                    output_filename=args.get("output_filename"),
                    session_tag=args.get("session_tag"),
                    new_session=bool(args.get("new_session", False)),
                    python_pptx=python_pptx,
                    max_media_prompts=int(args.get("max_media_prompts", DEFAULT_MAX_MEDIA_PROMPTS)),
                    csesidx=args.get("csesidx", DEFAULT_CSESIDX),
                )
                if (summary_only or python_pptx) and res.get("saved_output_path"):
                    preview = res["text"][:500]
                    if len(res["text"]) > 500:
                        preview += "\n... [truncated to save AGY context tokens]"
                    out_text = (
                        f"Saved full response ({res['line_count']} lines, {res['char_count']} chars) to:\n"
                        f"`{res['saved_output_path']}`\n\n"
                        f"**Preview:**\n{preview}"
                    )
                else:
                    out_text = res["text"]
                    if res.get("saved_output_path"):
                        out_text += f"\n\n_Saved session-scoped output to: `{res['saved_output_path']}`_"
                for m in res.get("generated_media", []):
                    out_text += f"\n\n_Auto-downloaded `{m['media_type'].upper()}` (`{m['mime_type']}`): `{m['path']}` ({m['bytes']:,} bytes)_"
                if res.get("exported_artifacts"):
                    exp = res["exported_artifacts"]
                    if exp.get("error"):
                        out_text += f"\n\n_python-pptx Compile Error: `{exp['error']}`_"
                    for fmt_k, info in exp.get("exported_files", {}).items():
                        out_text += f"\n\n_Auto-exported `{fmt_k.upper()}` ({exp.get('slides_count')} slides): `{info['path']}` ({info['bytes']:,} bytes)_"
                if res.get("rotated_previous_media_session"):
                    out_text += f"\n\n_Media session rotated: deleted previous 3-prompt session `{res['rotated_previous_media_session']}`_"
                if res.get("session"):
                    status_note = (
                        f"deleted ({res.get('session_auto_cleared_reason') or 'ephemeral'})"
                        if res.get("session_deleted")
                        else f"`{res['session']}`"
                    )
                    out_text += f"\n\n---\n_Agentspace Session: {status_note} (Target: `{res['model']}`)_"
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": out_text}],
                        "isError": False,
                    },
                }

            elif name == "agentspace_advise":
                res = ask_agentspace(
                    prompt=args["task"],
                    model_id=args.get("model", "gemini-4-carbon"),
                    thinking_level=args.get("thinking_level", "HIGH"),
                    input_files=args.get("files"),
                    save_output=True,
                    output_filename=args.get("output_filename", "advisor_plan.md"),
                    session_tag=args.get("session_tag"),
                    new_session=bool(args.get("new_session", False)),
                    csesidx=args.get("csesidx", DEFAULT_CSESIDX),
                    include_tree=bool(args.get("include_tree", True)),
                    advise_mode=True,
                    cwd=args.get("cwd"),
                )
                skipped_note = (
                    f"\n\n**Omitted Files (budget cap):** `{', '.join(res['skipped_files'][:10])}`"
                    if res.get("skipped_files")
                    else ""
                )
                if res.get("need_context"):
                    body_preview = (
                        "**[NEED_CONTEXT] DETECTED:** Gather the requested files/outputs below and call "
                        "`agentspace_advise` again with the same `session_tag`:\n\n"
                        f"{res['need_context'][:4000]}"
                    )
                elif res.get("advisor_spec"):
                    spec_txt = res["advisor_spec"]
                    if len(spec_txt) <= 4000:
                        body_preview = (
                            f"**Extracted `<antigravity_spec>`** (also saved to `{res.get('advisor_spec_path', '')}` — "
                            f"apply directly without reading full `advisor_plan.md`):\n\n{spec_txt}"
                        )
                    else:
                        body_preview = (
                            f"**Spec exceeds inline cap ({len(spec_txt)} chars).** Read ONLY `{res.get('advisor_spec_path', '')}` "
                            f"(skip full narrative `advisor_plan.md`).\n\n{spec_txt[:1500]}\n... [truncated]"
                        )
                else:
                    preview = res["text"][:800]
                    if len(res["text"]) > 800:
                        preview += "\n... [truncated; no <antigravity_spec> tag found — read saved plan]"
                    body_preview = f"**Preview:**\n{preview}"

                out_text = (
                    f"Saved full Advisor rationale ({res['line_count']} lines, {res['char_count']} chars) to "
                    f"`{res.get('saved_output_path', '')}`.{skipped_note}\n\n{body_preview}"
                )
                if res.get("session"):
                    out_text += f"\n\n---\n_Agentspace Session: `{res['session']}` (Target: `{res['model']}`)_"
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": out_text}],
                        "isError": False,
                    },
                }

            elif name == "agentspace_finish_task":
                fin_res = finish_task_sessions(
                    session_tag=args["session_tag"],
                    media_only=bool(args.get("media_only", True)),
                    csesidx=args.get("csesidx", DEFAULT_CSESIDX),
                )
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(fin_res, indent=2)}],
                        "isError": False,
                    },
                }

            elif name == "agentspace_cleanup_media_sessions":
                clean_res = cleanup_media_sessions(
                    limit=int(args.get("limit", 50)),
                    keep_latest=int(args.get("keep_latest", 0)),
                    csesidx=args.get("csesidx", DEFAULT_CSESIDX),
                )
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(clean_res, indent=2)}],
                        "isError": False,
                    },
                }

            elif name == "agentspace_export_slides":
                exp_res = export_session_artifacts(
                    session_id=args.get("session_id"),
                    formats=args.get("formats") or ["pptx"],
                    session_tag=args.get("session_tag"),
                    csesidx=args.get("csesidx", DEFAULT_CSESIDX),
                )
                lines = [
                    f"Exported **{exp_res['title']}** ({exp_res['slides_count']} slides, artifact `{exp_res['artifact_id']}`):"
                ]
                for fmt_k, info in exp_res["exported_files"].items():
                    lines.append(f"- **{fmt_k.upper()}**: `{info['path']}` ({info['bytes']:,} bytes)")
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": "\n".join(lines)}],
                        "isError": False,
                    },
                }

            elif name == "agentspace_delete_session":
                res = delete_session(
                    session_id=args["session_id"],
                    csesidx=args.get("csesidx", DEFAULT_CSESIDX),
                )
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Successfully deleted Agentspace chat session `{res['session_id']}`.",
                            }
                        ],
                        "isError": False,
                    },
                }

            elif name == "agentspace_list_sessions":
                sessions = list_sessions(
                    limit=int(args.get("limit", 20)),
                    csesidx=args.get("csesidx", DEFAULT_CSESIDX),
                )
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(sessions, indent=2)}],
                        "isError": False,
                    },
                }

            elif name == "agentspace_refresh_token":
                data, saved_path = refresh_xsrf_token(
                    browser_channel=args.get("browser", DEFAULT_BROWSER_CHANNEL),
                )
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Successfully refreshed and saved Agentspace token to `{saved_path}` "
                                    f"(keyId: `{data.get('keyId')}`, csesidx: `{data.get('csesidx')}`)."
                                ),
                            }
                        ],
                        "isError": False,
                    },
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {name}"},
                }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Error calling IOH Agentspace: {e}\n\n"
                                "Auto-refresh is locked via `.auth_profile/.refresh.lock`. If interactive Entra ID "
                                "re-login is needed, call `agentspace_refresh_token` or run: "
                                "`python3 agentspace_cli.py --refresh-token`"
                            ),
                        }
                    ],
                    "isError": True,
                },
            }
    elif msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def _write_jsonrpc(resp: dict) -> None:
    payload = json.dumps(resp) + "\n"
    with _STDOUT_LOCK:
        try:
            _PROTO_STDOUT.write(payload)
            _PROTO_STDOUT.flush()
        except (BrokenPipeError, OSError):
            pass


def _dispatch_tool_call(msg: dict) -> None:
    msg_id = msg.get("id")
    try:
        resp = handle_request(msg)
        if resp is not None:
            _write_jsonrpc(resp)
    except Exception as exc:
        sys.stderr.write(f"MCP worker error: {exc}\n")
        sys.stderr.flush()
        if msg_id is not None:
            _write_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32603, "message": f"Internal MCP worker error: {exc}"},
                }
            )


def main():
    global _PROTO_STDOUT
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.flush()
    # Duplicate true OS FD 1 for JSON-RPC, then redirect FD 1 -> stderr so child subprocesses cannot pollute stdout
    proto_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    _PROTO_STDOUT = os.fdopen(proto_fd, "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr

    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_MCP_WORKERS) as pool:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("method") == "tools/call":
                    pool.submit(_dispatch_tool_call, msg)
                else:
                    resp = handle_request(msg)
                    if resp is not None:
                        _write_jsonrpc(resp)
            except Exception as e:
                sys.stderr.write(f"MCP error: {e}\n")
                sys.stderr.flush()


if __name__ == "__main__":
    main()
