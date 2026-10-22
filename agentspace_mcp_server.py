#!/usr/bin/env python3
r"""
Zero-dependency stdio MCP Server for IOH Agentspace (Gemini Enterprise - gemini-4-argon & Agents).
Allows Google Antigravity to offload queries, code generation, Netra/ACE agent queries, and enterprise search
(Confluence/Jira/SharePoint) to IOH Agentspace (`agentspace.ioh.co.id`), as well as list and delete chat sessions.
"""
import json
import sys
from agentspace_cli import (
    ask_agentspace,
    delete_session,
    list_sessions,
    refresh_xsrf_token,
    DEFAULT_MODEL,
    DEFAULT_THINKING,
    DEFAULT_CSESIDX,
)

TOOLS = [
    {
        "name": "agentspace_ask",
        "description": (
            "Offload a prompt, coding question, analysis, specialized agent query (e.g. 'netra', 'ace', 'slides'), "
            "or enterprise search query (Confluence, SharePoint, Jira) to IOH's Gemini Enterprise (Agentspace) "
            "running Gemini 4 Argon (`gemini-4-argon`). Set `delete_session_after=true` for one-off queries so the "
            "chat session is automatically deleted after receiving the answer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt or question to send to Gemini 4 Argon or an Agentspace Agent.",
                },
                "agent": {
                    "type": "string",
                    "description": (
                        "Optional agent alias ('netra' for Netra Multi-Agent Coordinator 17783079275007264980, "
                        "'ace' for ACE Platform 8461818071814491910, 'slides' for PPTX Agent 17216682253898748109, "
                        "'agb' for 18420663427156982501, 'catalyst' for app_catalyst_agent) or raw numeric Agent ID."
                    ),
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
                "delete_session_after": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set to true if this chat session will not be used again, so it is automatically deleted after the response is returned.",
                },
                "csesidx": {
                    "type": "string",
                    "default": DEFAULT_CSESIDX,
                    "description": "Optional csesidx query parameter from the vertexaisearch.cloud.google URL.",
                },
            },
            "required": ["prompt"],
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
                "csesidx": {
                    "type": "string",
                    "default": DEFAULT_CSESIDX,
                    "description": "Optional csesidx query parameter from the vertexaisearch.cloud.google URL.",
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
                "csesidx": {
                    "type": "string",
                    "default": DEFAULT_CSESIDX,
                    "description": "Optional csesidx query parameter from the vertexaisearch.cloud.google URL.",
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
                    "default": "msedge",
                    "description": "Browser channel to open ('msedge' or 'chrome').",
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
                "serverInfo": {"name": "ioh-agentspace-mcp", "version": "1.1.0"},
            },
        }
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }
    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})

        try:
            if name == "agentspace_ask":
                res = ask_agentspace(
                    prompt=args["prompt"],
                    model_id=args.get("model", DEFAULT_MODEL),
                    thinking_level=args.get("thinking_level", DEFAULT_THINKING),
                    session=args.get("session"),
                    enable_search=bool(args.get("enable_enterprise_search", False)),
                    agent=args.get("agent"),
                    delete_session_after=bool(args.get("delete_session_after", False)),
                    csesidx=args.get("csesidx", DEFAULT_CSESIDX),
                )
                out_text = res["text"]
                if res.get("session"):
                    status_note = "deleted (ephemeral)" if res.get("session_deleted") else f"`{res['session']}`"
                    out_text += f"\n\n---\n_Agentspace Session: {status_note} (Target: `{res['model']}`)_"
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": out_text}],
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
                    browser_channel=args.get("browser", "msedge"),
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
                                "If the 1-hour XSRF session expired, download a fresh copy from:\n"
                                "https://vertexaisearch.cloud.google/auth/getoxsrf?csesidx=<YOUR_CSESIDX>\n"
                                "into ~/Downloads/json.txt or %TEMP%/agentspace_xsrf.json"
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


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            resp = handle_request(msg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"MCP error: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
