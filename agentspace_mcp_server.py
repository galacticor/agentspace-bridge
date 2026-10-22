#!/usr/bin/env python3
r"""
Zero-dependency stdio MCP Server for IOH Agentspace (Gemini Enterprise - gemini-4-argon).
Allows Google Antigravity to offload queries, code generation, and enterprise search (Confluence/Jira/SharePoint)
to IOH Agentspace (`agentspace.ioh.co.id`) using the local BYOID XSRF session key.
"""
import json
import sys
from agentspace_cli import ask_agentspace, DEFAULT_MODEL, DEFAULT_THINKING, DEFAULT_CSESIDX

TOOLS = [
    {
        "name": "agentspace_ask",
        "description": (
            "Offload a prompt, coding question, analysis, or enterprise search query (Confluence, SharePoint, Jira) "
            "to IOH's Gemini Enterprise (Agentspace) running Gemini 4 Argon (`gemini-4-argon`). "
            "Use this to save Antigravity quota or query internal IOH knowledge bases."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt or question to send to Gemini 4 Argon on Agentspace."
                },
                "model": {
                    "type": "string",
                    "default": DEFAULT_MODEL,
                    "description": "Model ID (default: 'gemini-4-argon')."
                },
                "thinking_level": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "NONE"],
                    "default": DEFAULT_THINKING,
                    "description": "Thinking effort level for Gemini 4 Argon."
                },
                "enable_enterprise_search": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set to true to search IOH Confluence, SharePoint, Jira, and Google Drive connectors."
                },
                "session": {
                    "type": "string",
                    "description": "Optional session resource name returned by a previous call to continue a multi-turn conversation."
                },
                "csesidx": {
                    "type": "string",
                    "default": DEFAULT_CSESIDX,
                    "description": "Optional csesidx query parameter from the vertexaisearch.cloud.google URL."
                }
            },
            "required": ["prompt"]
        }
    }
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
                "serverInfo": {"name": "ioh-agentspace-mcp", "version": "1.0.0"},
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
        if name != "agentspace_ask":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }
        try:
            res = ask_agentspace(
                prompt=args["prompt"],
                model_id=args.get("model", DEFAULT_MODEL),
                thinking_level=args.get("thinking_level", DEFAULT_THINKING),
                session=args.get("session"),
                enable_search=bool(args.get("enable_enterprise_search", False)),
                csesidx=args.get("csesidx", DEFAULT_CSESIDX),
            )
            out_text = res["text"]
            if res.get("session"):
                out_text += f"\n\n---\n_Agentspace Session: `{res['session']}` (Model: `{res['model']}`)_"
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": out_text}],
                    "isError": False,
                },
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
