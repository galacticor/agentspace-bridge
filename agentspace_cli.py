#!/usr/bin/env python3
r"""
IOH Agentspace (Gemini Enterprise) CLI & Helper for Google Antigravity.
Connects directly to https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetStreamAssist
using the local Workforce Identity BYOID session key (~/Downloads/json.txt or %TEMP%/agentspace_xsrf.json).
"""
import argparse
import base64
import glob
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_XSRF_PATH = os.path.join(SCRIPT_DIR, "agentspace_xsrf.json")
AUTH_PROFILE_DIR = os.path.join(SCRIPT_DIR, ".auth_profile")
AGENTSPACE_ENTRY_URL = os.environ.get("AGENTSPACE_ENTRY_URL", "https://agentspace.ioh.co.id")
WIDGET_CONFIG_ID = os.environ.get("AGENTSPACE_CONFIG_ID", "384c42b0-2885-415a-82d5-f2babc063b6e")
DEFAULT_CSESIDX = os.environ.get("AGENTSPACE_CSESIDX", "")
DEFAULT_MODEL = os.environ.get("AGENTSPACE_MODEL", "gemini-4-argon")
DEFAULT_THINKING = os.environ.get("AGENTSPACE_THINKING", "MEDIUM")
HOST = "biz-discoveryengine.googleapis.com"
ORIGIN = "https://vertexaisearch.cloud.google"

# Known IOH Agentspace Agent Aliases -> Agent IDs
AGENT_ALIASES: dict[str, str] = {
    "netra": "17783079275007264980",
    "ace": "8461818071814491910",
    "slides": "17216682253898748109",
    "pptx": "17216682253898748109",
    "agb": "18420663427156982501",
    "catalyst": "app_catalyst_agent",
}


def resolve_agent_id(agent: str | None) -> str | None:
    if not agent:
        return None
    cleaned = agent.strip()
    return AGENT_ALIASES.get(cleaned.lower(), cleaned)


ENGINE_SESSION_PREFIX = "collections/default_collection/engines/enterprise-search-17429648_1742964839282/sessions/"


def normalize_session_id(session_id: str) -> str:
    """Extracts the short numeric session ID for widgetGetSession / display."""
    cleaned = session_id.strip().rstrip("/")
    if "/" in cleaned:
        return cleaned.split("/")[-1]
    return cleaned


def format_delete_session_name(session_id: str) -> str:
    """Formats the session resource path required by widgetDeleteSession."""
    short_id = normalize_session_id(session_id)
    return f"{ENGINE_SESSION_PREFIX}{short_id}"


def get_xsrf_candidate_paths() -> list[str]:
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    temp_dir = tempfile.gettempdir()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    candidates = []
    if os.environ.get("AGENTSPACE_XSRF_PATH"):
        candidates.append(os.environ["AGENTSPACE_XSRF_PATH"])

    # Project local or temp file
    candidates.append(os.path.join(script_dir, "agentspace_xsrf.json"))
    candidates.append(os.path.join(temp_dir, "agentspace_xsrf.json"))

    # Common filenames in ~/Downloads (pick newest if multiple exist)
    dl_matches = []
    for pattern in ["json*.txt", "getoxsrf*", "agentspace_xsrf*.json"]:
        dl_matches.extend(glob.glob(os.path.join(downloads, pattern)))
    dl_matches.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    candidates.extend(dl_matches)

    return candidates


def _parse_xsrf_payload(raw_text: str) -> dict | None:
    if not raw_text:
        return None
    idx = raw_text.find("{")
    if idx != -1:
        raw_text = raw_text[idx:]
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict) and "xsrfToken" in data and "keyId" in data:
            return data
    except Exception:
        pass
    return None


def refresh_xsrf_token(
    csesidx: str | None = None,
    browser_channel: str = "msedge",
    timeout_sec: int = 180,
) -> tuple[dict, str]:
    """
    Launches an interactive browser window (using a persistent profile in .auth_profile)
    pointing to https://agentspace.ioh.co.id, waits for SSO / Agentspace load, fetches
    /auth/getoxsrf, and saves the refreshed token to ./agentspace_xsrf.json.
    """
    from playwright.sync_api import sync_playwright

    os.makedirs(AUTH_PROFILE_DIR, exist_ok=True)
    captured: dict = {}

    print(
        f"[Agentspace Auth] Opening browser ({browser_channel}) to refresh XSRF token -> {PROJECT_XSRF_PATH} ...",
        file=sys.stderr,
    )

    with sync_playwright() as p:
        context = None
        for ch in [browser_channel, "msedge", "chrome", None]:
            try:
                launch_kwargs = {
                    "user_data_dir": AUTH_PROFILE_DIR,
                    "headless": False,
                    "viewport": {"width": 1100, "height": 780},
                }
                if ch:
                    launch_kwargs["channel"] = ch
                context = p.chromium.launch_persistent_context(**launch_kwargs)
                break
            except Exception:
                continue

        if context is None:
            raise RuntimeError("Failed to launch browser (Edge/Chrome/Chromium) via Playwright.")

        def on_response(response):
            if "/auth/getoxsrf" in response.url and response.status == 200 and not captured:
                try:
                    parsed_url = urllib.parse.urlparse(response.url)
                    qs = urllib.parse.parse_qs(parsed_url.query)
                    resp_cses = qs.get("csesidx", [csesidx or DEFAULT_CSESIDX])[0]
                    data = _parse_xsrf_payload(response.text())
                    if data:
                        data["csesidx"] = resp_cses
                        data["savedAt"] = int(time.time())
                        captured.update(data)
                except Exception:
                    pass

        context.on("response", on_response)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(AGENTSPACE_ENTRY_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass

        deadline = time.time() + timeout_sec
        while time.time() < deadline and not captured:
            for pg in list(context.pages):
                try:
                    cur_url = pg.url
                    if cur_url.startswith(ORIGIN):
                        qs = urllib.parse.parse_qs(urllib.parse.urlparse(cur_url).query)
                        detected_cses = qs.get("csesidx", [None])[0] or csesidx
                        if detected_cses:
                            raw_xsrf = pg.evaluate(
                                """async (u) => {
                                    const r = await fetch(u, {credentials: 'include'});
                                    return await r.text();
                                }""",
                                f"{ORIGIN}/auth/getoxsrf?csesidx={detected_cses}",
                            )
                            data = _parse_xsrf_payload(raw_xsrf)
                            if data:
                                data["csesidx"] = detected_cses
                                data["savedAt"] = int(time.time())
                                captured.update(data)
                                break
                except Exception:
                    pass
            if not captured:
                page.wait_for_timeout(1000)

        try:
            context.close()
        except Exception:
            pass

    if not captured:
        raise RuntimeError(
            f"Timed out after {timeout_sec}s waiting for Agentspace SSO login and XSRF token."
        )

    with open(PROJECT_XSRF_PATH, "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2)

    print(
        f"[Agentspace Auth] Saved fresh token (keyId={captured.get('keyId')}, csesidx={captured.get('csesidx')}) to {PROJECT_XSRF_PATH}",
        file=sys.stderr,
    )
    return captured, PROJECT_XSRF_PATH


def load_xsrf() -> tuple[dict, str]:
    for p in get_xsrf_candidate_paths():
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                data = _parse_xsrf_payload(raw)
                if data:
                    return data, p
            except Exception:
                continue
    raise FileNotFoundError(
        "Could not find a valid Agentspace XSRF JSON file (containing 'xsrfToken' and 'keyId').\n"
        "Checked:\n"
        "  - $AGENTSPACE_XSRF_PATH\n"
        "  - ./agentspace_xsrf.json\n"
        "  - %TEMP%/agentspace_xsrf.json\n"
        "  - ~/Downloads/json.txt (or ~/Downloads/getoxsrf*)"
    )


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * ((4 - len(s) % 4) % 4)
    return base64.b64decode(s)


def make_jwt(xsrf: dict, csesidx: str = DEFAULT_CSESIDX) -> str:
    key_bytes = b64_decode(xsrf["xsrfToken"])
    header = {"alg": "HS256", "typ": "JWT", "kid": xsrf["keyId"]}
    now = int(time.time())
    payload = {
        "iss": ORIGIN,
        "aud": f"https://{HOST}",
        "sub": f"csesidx/{csesidx}",
        "iat": now,
        "exp": now + 300,
        "nbf": now,
    }
    h_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(key_bytes, signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{b64url_encode(sig)}"


def _post_widget_rpc(
    endpoint: str,
    payload: dict,
    csesidx: str = DEFAULT_CSESIDX,
    timeout: int = 120,
    auto_refresh: bool = True,
) -> tuple[dict | list, str]:
    try:
        xsrf, xsrf_path = load_xsrf()
    except FileNotFoundError:
        if not auto_refresh:
            raise
        xsrf, xsrf_path = refresh_xsrf_token(csesidx=csesidx)

    for attempt in range(2):
        effective_csesidx = str(xsrf.get("csesidx") or csesidx)
        jwt_tok = make_jwt(xsrf, csesidx=effective_csesidx)
        url = f"https://{HOST}/v1alpha/locations/global/{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {jwt_tok}",
                "Content-Type": "application/json",
                "X-Goog-Api-Client": "gemini-enterprise-classic/1.0.0",
                "Origin": ORIGIN,
                "Referer": f"{ORIGIN}/",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return (json.loads(raw) if raw.strip() else {}), xsrf_path
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and auto_refresh and attempt == 0:
                print(
                    f"[Agentspace Auth] Token in {xsrf_path} expired (HTTP {e.code}). Launching browser UI to refresh...",
                    file=sys.stderr,
                )
                xsrf, xsrf_path = refresh_xsrf_token(csesidx=csesidx)
                continue
            raise
    raise RuntimeError("Unreachable RPC retry state")


def delete_session(session_id: str, csesidx: str = DEFAULT_CSESIDX) -> dict:
    """Deletes a chat session from IOH Agentspace via widgetDeleteSession."""
    short_id = normalize_session_id(session_id)
    full_name = format_delete_session_name(short_id)
    payload = {
        "configId": WIDGET_CONFIG_ID,
        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
        "deleteSessionRequest": {"name": full_name},
    }
    _, xsrf_path = _post_widget_rpc("widgetDeleteSession", payload, csesidx=csesidx, timeout=30)
    return {
        "deleted": True,
        "session_id": short_id,
        "name": full_name,
        "xsrf_source": xsrf_path,
    }


def list_sessions(limit: int = 20, csesidx: str = DEFAULT_CSESIDX) -> list[dict]:
    """Lists recent chat sessions on IOH Agentspace via widgetListSessions."""
    payload = {
        "configId": WIDGET_CONFIG_ID,
        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
        "listSessionsRequest": {},
    }
    data, _ = _post_widget_rpc("widgetListSessions", payload, csesidx=csesidx, timeout=30)
    raw_sessions = data.get("listSessionsResponse", {}).get("sessions", []) if isinstance(data, dict) else []
    results = []
    for s in raw_sessions[:limit]:
        name = s.get("name", "")
        short_id = normalize_session_id(name)
        turns = s.get("turns", [])
        first_query = ""
        is_agent = False
        if turns:
            first_query = turns[0].get("query", {}).get("text", "")[:100].replace("\n", " ")
            qc = turns[0].get("queryConfig", {})
            if qc.get("google.discoveryengine.googleapis.com.Assistant.answer_generation_mode") == "AGENT":
                is_agent = True
        results.append({
            "session_id": short_id,
            "name": name,
            "display_name": s.get("displayName", "(Untitled)"),
            "start_time": s.get("startTime"),
            "last_message_time": s.get("lastMessageTime"),
            "turns_count": len(turns),
            "mode": "AGENT" if is_agent else "CHAT",
            "first_query": first_query,
        })
    return results


def ask_agentspace(
    prompt: str,
    model_id: str = DEFAULT_MODEL,
    thinking_level: str = DEFAULT_THINKING,
    session: str | None = None,
    enable_search: bool = False,
    agent: str | None = None,
    delete_session_after: bool = False,
    csesidx: str = DEFAULT_CSESIDX,
) -> dict:
    resolved_agent = resolve_agent_id(agent)

    stream_req: dict = {
        "query": {"parts": [{"text": prompt}]},
    }

    if session:
        stream_req["session"] = session

    if resolved_agent:
        stream_req["agentsSpec"] = {
            "agentSpecs": [{"agentId": resolved_agent}]
        }
        stream_req["toolsSpec"] = {
            "webGroundingSpec": {},
            "toolRegistry": "default_tool_registry",
        }
    else:
        stream_req["assistGenerationConfig"] = {"modelId": model_id}
        if thinking_level and thinking_level.upper() != "NONE":
            stream_req["generationSpec"] = {
                "thinkingConfig": {"thinkingLevel": thinking_level.upper()}
            }
        if enable_search:
            stream_req["toolsSpec"] = {
                "vertexAiSearchSpec": {},
                "webGroundingSpec": {},
                "toolRegistry": "default_tool_registry",
            }
        else:
            stream_req["toolsSpec"] = {
                "webGroundingSpec": {},
                "toolRegistry": "default_tool_registry",
            }
            stream_req["assistSkippingMode"] = "REQUEST_ASSIST"

    payload = {
        "configId": WIDGET_CONFIG_ID,
        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
        "streamAssistRequest": stream_req,
    }

    timeout_sec = 300 if resolved_agent else 120
    chunks, xsrf_path = _post_widget_rpc("widgetStreamAssist", payload, csesidx=csesidx, timeout=timeout_sec)

    text_parts = []
    thoughts = []
    function_calls = []
    session_name = None

    if isinstance(chunks, list):
        for chunk in chunks:
            sar = chunk.get("streamAssistResponse", {})
            if not session_name and sar.get("sessionInfo", {}).get("session"):
                session_name = sar["sessionInfo"]["session"]
            ans = sar.get("answer", {})
            for rep in ans.get("replies", []):
                if "functionCall" in rep:
                    fc = rep["functionCall"]
                    function_calls.append(fc.get("functionName", "unknown"))
                content = rep.get("groundedContent", {}).get("content", {})
                if content.get("thought"):
                    if "text" in content:
                        thoughts.append(content["text"])
                elif "text" in content:
                    text_parts.append(content["text"])

    session_deleted = False
    if delete_session_after and session_name:
        try:
            delete_session(session_name, csesidx=csesidx)
            session_deleted = True
        except Exception:
            session_deleted = False

    return {
        "text": "".join(text_parts).strip(),
        "thoughts": "".join(thoughts).strip(),
        "function_calls": function_calls,
        "session": session_name,
        "session_deleted": session_deleted,
        "agent": resolved_agent,
        "model": model_id if not resolved_agent else f"agent:{resolved_agent}",
        "xsrf_source": xsrf_path,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Query IOH Agentspace (Gemini 4 Argon & Custom Agents)")
    parser.add_argument("prompt", nargs="?", default=None, help="Prompt text to send to Agentspace")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model ID (default: gemini-4-argon)")
    parser.add_argument("--thinking", default=DEFAULT_THINKING, help="Thinking level: LOW, MEDIUM, HIGH, NONE")
    parser.add_argument(
        "--agent",
        default=None,
        help="Optional Agent alias ('netra', 'ace', 'slides', 'agb', 'catalyst') or numeric Agent ID",
    )
    parser.add_argument("--session", default=None, help="Optional session resource name to continue a conversation")
    parser.add_argument(
        "--ephemeral",
        "--delete-after",
        dest="delete_after",
        action="store_true",
        help="Automatically delete the chat session after receiving the response",
    )
    parser.add_argument(
        "--delete-session",
        default=None,
        metavar="SESSION_ID",
        help="Delete a specific chat session by ID or full resource name and exit",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List recent chat sessions on Agentspace and exit",
    )
    parser.add_argument(
        "--refresh-token",
        action="store_true",
        help="Open browser UI to download/refresh the XSRF token into ./agentspace_xsrf.json",
    )
    parser.add_argument(
        "--browser",
        default="msedge",
        help="Browser channel for --refresh-token (default: msedge, or chrome)",
    )
    parser.add_argument("--limit", type=int, default=20, help="Number of sessions to list with --list-sessions")
    parser.add_argument("--csesidx", default=DEFAULT_CSESIDX, help="Browser session index (csesidx) from URL")
    parser.add_argument("--search", action="store_true", help="Enable Enterprise Search (Confluence/SharePoint/Jira) & Web Grounding")
    parser.add_argument("--json", action="store_true", help="Output full JSON response")
    args = parser.parse_args()

    try:
        if args.refresh_token:
            data, saved_path = refresh_xsrf_token(csesidx=args.csesidx, browser_channel=args.browser)
            if not args.prompt and not args.list_sessions and not args.delete_session:
                if args.json:
                    print(
                        json.dumps(
                            {
                                "refreshed": True,
                                "path": saved_path,
                                "keyId": data.get("keyId"),
                                "csesidx": data.get("csesidx"),
                                "savedAt": data.get("savedAt"),
                            },
                            indent=2,
                        )
                    )
                else:
                    print(f"Refreshed token saved to: {saved_path} (keyId={data.get('keyId')}, csesidx={data.get('csesidx')})")
                return

        if args.list_sessions:
            sessions = list_sessions(limit=args.limit, csesidx=args.csesidx)
            if args.json:
                print(json.dumps(sessions, indent=2))
            else:
                for s in sessions:
                    print(f"[{s['session_id']}] ({s['mode']}) {s['display_name']} | {s['start_time']} | {s['first_query']}")
            return

        if args.delete_session:
            res = delete_session(args.delete_session, csesidx=args.csesidx)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Deleted session: {res['session_id']}")
            return

        if not args.prompt:
            parser.error("A prompt is required unless --list-sessions or --delete-session is specified.")

        res = ask_agentspace(
            prompt=args.prompt,
            model_id=args.model,
            thinking_level=args.thinking,
            session=args.session,
            enable_search=args.search,
            agent=args.agent,
            delete_session_after=args.delete_after,
            csesidx=args.csesidx,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(res["text"])
            if res.get("session_deleted"):
                print(f"\n[Ephemeral mode: deleted temporary session {normalize_session_id(res['session'])}]", file=sys.stderr)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} Error:\n{err_body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
