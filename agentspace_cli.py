#!/usr/bin/env python3
r"""
IOH Agentspace (Gemini Enterprise) CLI & Helper for Google Antigravity.
Connects directly to https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetStreamAssist
using the local Workforce Identity BYOID session key (~/Downloads/json.txt or %TEMP%/agentspace_xsrf.json).
"""
from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import hmac
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_XSRF_PATH = os.path.join(SCRIPT_DIR, "agentspace_xsrf.json")
AUTH_PROFILE_DIR = os.path.join(SCRIPT_DIR, ".auth_profile")
OUTPUTS_DIR = os.path.join(SCRIPT_DIR, "outputs")
AGENTSPACE_ENTRY_URL = os.environ.get("AGENTSPACE_ENTRY_URL", "https://agentspace.ioh.co.id")
WIDGET_CONFIG_ID = os.environ.get("AGENTSPACE_CONFIG_ID", "384c42b0-2885-415a-82d5-f2babc063b6e")
DEFAULT_CSESIDX = os.environ.get("AGENTSPACE_CSESIDX", "")
DEFAULT_MODEL = os.environ.get("AGENTSPACE_MODEL", "gemini-4-argon")
DEFAULT_THINKING = os.environ.get("AGENTSPACE_THINKING", "MEDIUM")
DEFAULT_BROWSER_CHANNEL = os.environ.get(
    "AGENTSPACE_BROWSER",
    "chrome" if sys.platform == "darwin" else "msedge",
)
HOST = "biz-discoveryengine.googleapis.com"
ORIGIN = "https://vertexaisearch.cloud.google"

# Known IOH Agentspace Agent Aliases -> Agent IDs
AGENT_ALIASES: dict[str, str] = {
    "netra": "17783079275007264980",
    "ace": "8461818071814491910",
    "office-workflow-suite": "14950672669329422296",
    "office": "14950672669329422296",
    "slides": "14950672669329422296",
    "pptx": "14950672669329422296",
    "office-creator": "17216682253898748109",
    "agb": "18420663427156982501",
    "catalyst": "app_catalyst_agent",
}

# Skills (`agentType: "SKILL_AGENT"`) run inside NORMAL mode (`gemini-4-argon` + `canvasSpec: {}`
# + `load_skill` tool) rather than `answerGenerationMode: "AGENT"` (which causes HTTP 500 for skills).
SKILL_AGENT_IDS: dict[str, str] = {
    "14950672669329422296": "office-workflow-suite",
}

SLIDES_AGENT_IDS: set[str] = {
    "14950672669329422296",  # office-workflow-suite (SKILL_AGENT)
    "17216682253898748109",  # Office File Creator (LOW_CODE)
}


def resolve_agent_id(agent: str | None) -> str | None:
    if not agent:
        return None
    cleaned = agent.strip()
    return AGENT_ALIASES.get(cleaned.lower(), cleaned)


ENGINE_SESSION_PREFIX = "collections/default_collection/engines/enterprise-search-17429648_1742964839282/sessions/"
ENGINE_RESOURCE_NAME = "projects/195467123768/locations/global/collections/default_collection/engines/enterprise-search-17429648_1742964839282"
EXPORT_MIME_TYPES: dict[str, str] = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
}


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


def _find_playwright_python() -> str | None:
    """
    On macOS/Linux/Windows, if the current Python interpreter lacks `playwright`
    (e.g. global `python` vs `.venv/Scripts/python.exe` on Windows, or Apple's
    `/usr/bin/python3` vs Homebrew's `/opt/homebrew/bin/python3` on macOS),
    locates an installed Python interpreter that has `playwright`.
    """
    venv_win = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "python.exe")
    venv_unix = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")
    candidates = [venv_win, venv_unix]
    if sys.platform == "darwin":
        candidates.extend(["/opt/homebrew/bin/python3", "/usr/local/bin/python3"])
    elif sys.platform != "win32":
        candidates.extend(["/usr/local/bin/python3", "/usr/bin/python3"])

    for cand in candidates:
        if os.path.isfile(cand) and os.path.realpath(cand) != os.path.realpath(sys.executable):
            try:
                res = subprocess.run(
                    [cand, "-c", "import playwright"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                if res.returncode == 0:
                    return cand
            except Exception:
                continue
    return None


def _get_browser_channel_candidates(preferred: str | None = None) -> list[str | None]:
    """
    Returns ordered browser channels to try on the current OS so that both
    Windows (msedge -> chrome -> chromium) and macOS (chrome -> msedge -> chromium)
    work seamlessly without breaking each other.
    """
    pref = (preferred or DEFAULT_BROWSER_CHANNEL).strip() if (preferred or DEFAULT_BROWSER_CHANNEL) else None
    if sys.platform == "darwin":
        base_order: list[str | None] = [pref, "chrome", "msedge", None]
    else:
        base_order = [pref, "msedge", "chrome", None]
    deduped: list[str | None] = []
    for ch in base_order:
        if ch not in deduped:
            deduped.append(ch)
    return deduped


def _launch_persistent_browser(playwright_instance, browser_channel: str | None = None, **kwargs):
    """
    Launches a persistent Chromium context trying the preferred browser channel first,
    then gracefully falling back across Chrome, Edge, and bundled Chromium.
    Suppresses Playwright automation flags so navigator.webdriver is false.
    """
    os.makedirs(AUTH_PROFILE_DIR, exist_ok=True)
    last_err = None
    for ch in _get_browser_channel_candidates(browser_channel):
        try:
            launch_kwargs = dict(kwargs)
            launch_kwargs["user_data_dir"] = AUTH_PROFILE_DIR
            launch_kwargs.setdefault("args", ["--disable-blink-features=AutomationControlled"])
            launch_kwargs.setdefault("ignore_default_args", ["--enable-automation"])
            if ch:
                launch_kwargs["channel"] = ch
            ctx = playwright_instance.chromium.launch_persistent_context(**launch_kwargs)
            return ctx, (ch or "chromium")
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Failed to launch browser (Chrome/Edge/Chromium) via Playwright: {last_err}")


def _attempt_xsrf_capture(
    playwright_instance,
    csesidx: str | None,
    browser_channel: str,
    headless: bool,
    timeout_sec: int,
) -> dict:
    captured: dict = {}
    context, active_channel = _launch_persistent_browser(
        playwright_instance,
        browser_channel=browser_channel,
        headless=headless,
        viewport={"width": 1100, "height": 780},
    )
    mode_label = "headless background" if headless else "interactive window"
    print(
        f"[Agentspace Auth] Trying {mode_label} ({active_channel}) with profile {AUTH_PROFILE_DIR} ...",
        file=sys.stderr,
    )

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
        page.goto(AGENTSPACE_ENTRY_URL, wait_until="domcontentloaded", timeout=min(60000, timeout_sec * 1000))
    except Exception:
        pass

    deadline = time.time() + timeout_sec
    clicked_sso_tile = False
    while time.time() < deadline and not captured:
        for pg in list(context.pages):
            try:
                cur_url = pg.url
                # Multi-account Windows WAM / Entra ID picker: auto-select the @ioh.co.id tile
                if "login.microsoftonline.com" in cur_url and not clicked_sso_tile:
                    try:
                        tile = pg.locator('[data-test-id*="@ioh.co.id"], div.table:has-text("@ioh.co.id")').first
                        if tile.count() > 0 and tile.is_visible():
                            print(
                                "[Agentspace Auth] Auto-selecting @ioh.co.id account on Entra ID account picker ...",
                                file=sys.stderr,
                            )
                            tile.click()
                            clicked_sso_tile = True
                    except Exception:
                        pass
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

    return captured


def refresh_xsrf_token(
    csesidx: str | None = None,
    browser_channel: str = DEFAULT_BROWSER_CHANNEL,
    timeout_sec: int = 180,
    headless_first: bool = True,
) -> tuple[dict, str]:
    """
    Refreshes the IOH Agentspace XSRF token using a persistent Work profile in .auth_profile/.
    - If .auth_profile/ already has a saved login session and headless_first=True, first attempts
      a silent 15s headless refresh so no popup window interrupts the user.
    - If first-time setup or SSO requires interactive login/2FA, opens a visible browser window.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        alt_py = _find_playwright_python()
        if alt_py:
            cmd = [
                alt_py,
                os.path.abspath(__file__),
                "--refresh-token",
                "--browser",
                browser_channel,
                "--json",
            ]
            if csesidx:
                cmd.extend(["--csesidx", csesidx])
            subprocess.run(cmd, check=True)
            return load_xsrf()
        raise

    has_existing_profile = os.path.isdir(os.path.join(AUTH_PROFILE_DIR, "Default"))
    captured: dict = {}

    with sync_playwright() as p:
        if headless_first and has_existing_profile:
            try:
                captured = _attempt_xsrf_capture(
                    p,
                    csesidx=csesidx,
                    browser_channel=browser_channel,
                    headless=True,
                    timeout_sec=25,
                )
            except Exception:
                captured = {}

        if not captured:
            captured = _attempt_xsrf_capture(
                p,
                csesidx=csesidx,
                browser_channel=browser_channel,
                headless=False,
                timeout_sec=timeout_sec,
            )

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


def _build_browser_rpc_headers(jwt_tok: str) -> dict[str, str]:
    """
    Returns authentic browser CORS + Client Hints headers matching the host OS
    (Chrome on macOS/Linux, Edge on Windows) so RPC requests never send
    Python's default 'User-Agent: Python-urllib/3.x' header.
    """
    if sys.platform == "darwin":
        user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        sec_ch_ua = '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
        sec_ch_platform = '"macOS"'
    elif sys.platform == "win32":
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        )
        sec_ch_ua = '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
        sec_ch_platform = '"Windows"'
    else:
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        sec_ch_ua = '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
        sec_ch_platform = '"Linux"'

    return {
        "Authorization": f"Bearer {jwt_tok}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": user_agent,
        "Sec-Ch-Ua": sec_ch_ua,
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": sec_ch_platform,
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "X-Goog-Api-Client": "gemini-enterprise-classic/1.0.0",
        "Origin": ORIGIN,
        "Referer": f"{ORIGIN}/",
    }


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
            headers=_build_browser_rpc_headers(jwt_tok),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                try:
                    raw = resp.read().decode("utf-8")
                except http.client.IncompleteRead as ir:
                    raw = ir.partial.decode("utf-8", errors="replace")
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


SESSION_PREFIX = "[agy-bridge]"


def ensure_session_prefix(
    session_id: str,
    fallback_title: str = "",
    prefix: str = SESSION_PREFIX,
    csesidx: str = DEFAULT_CSESIDX,
) -> str | None:
    """
    Ensures the Agentspace session displayName starts with `[agy-bridge]` so it is
    immediately recognizable in the Agentspace Web UI sidebar.
    """
    short_id = normalize_session_id(session_id)
    full_name = format_delete_session_name(short_id)
    current_title = ""
    try:
        get_payload = {
            "configId": WIDGET_CONFIG_ID,
            "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
            "getSessionRequest": {"name": short_id, "includeAnswerDetails": False},
        }
        data, _ = _post_widget_rpc("widgetGetSession", get_payload, csesidx=csesidx, timeout=20)
        if isinstance(data, dict):
            current_title = (data.get("session", {}).get("displayName") or "").strip()
    except Exception:
        pass

    if current_title.startswith(prefix):
        return current_title

    base_title = current_title if current_title and current_title != "(Untitled)" else ""
    if not base_title:
        clean_fallback = re.sub(r"\s+", " ", (fallback_title or "").strip())
        base_title = clean_fallback[:60] if clean_fallback else "Session"

    new_title = f"{prefix} {base_title}".strip()
    update_payload = {
        "configId": WIDGET_CONFIG_ID,
        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
        "updateSessionRequest": {
            "session": {
                "name": full_name,
                "displayName": new_title,
            },
            "updateMask": "displayName",
        },
    }
    try:
        _post_widget_rpc("widgetUpdateSession", update_payload, csesidx=csesidx, timeout=20)
        return new_title
    except Exception:
        return None


def _get_session_state_path(session_tag: str | None) -> str | None:
    if not session_tag:
        return None
    tag = _sanitize_slug(session_tag, max_len=24)
    if not tag.startswith("chat_"):
        tag = f"chat_{tag}"
    session_dir = os.path.join(OUTPUTS_DIR, tag)
    os.makedirs(session_dir, exist_ok=True)
    return os.path.join(session_dir, "session_state.json")


def get_reusable_session(session_tag: str | None, mode_key: str) -> str | None:
    state_path = _get_session_state_path(session_tag)
    if not state_path or not os.path.isfile(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state.get("sessions", {}).get(mode_key)
    except Exception:
        return None


def save_reusable_session(
    session_tag: str | None,
    mode_key: str,
    session_name: str,
    display_name: str | None = None,
) -> None:
    state_path = _get_session_state_path(session_tag)
    if not state_path or not session_name:
        return
    state: dict = {"session_tag": session_tag, "sessions": {}, "history": []}
    if os.path.isfile(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    state.update(loaded)
        except Exception:
            pass
    if "sessions" not in state or not isinstance(state["sessions"], dict):
        state["sessions"] = {}
    state["sessions"][mode_key] = session_name
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if display_name:
        state["last_display_name"] = display_name
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


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


def list_agents(include_skills: bool = True, csesidx: str = DEFAULT_CSESIDX) -> list[dict]:
    """Lists agents and skills on IOH Agentspace via widgetListAgents and lookupWidgetConfig."""
    results: list[dict] = []
    seen_ids: set[str] = set()
    try:
        data, _ = _post_widget_rpc(
            "widgetListAgents",
            {
                "configId": WIDGET_CONFIG_ID,
                "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
                "listAgentsRequest": {"pageSize": 100},
            },
            csesidx=csesidx,
            timeout=30,
            auto_refresh=False,
        )
        for a in (data.get("listAgentsResponse", {}).get("agents", []) if isinstance(data, dict) else []):
            short_id = normalize_session_id(a.get("name", ""))
            if short_id and short_id not in seen_ids:
                seen_ids.add(short_id)
                results.append({
                    "agent_id": short_id,
                    "name": a.get("name", ""),
                    "display_name": a.get("displayName", ""),
                    "agent_type": a.get("agentType", "AGENT"),
                    "state": a.get("state", ""),
                    "sharing_type": a.get("sharingConfig", {}).get("type", ""),
                    "description": (a.get("description") or "")[:140],
                })
    except Exception:
        pass

    candidate_ids: list[str] = []
    for aid in AGENT_ALIASES.values():
        if aid not in candidate_ids and aid != "app_catalyst_agent":
            candidate_ids.append(aid)

    for idx, aid in enumerate(candidate_ids):
        if aid in seen_ids:
            continue
        try:
            s_data = get_agent(aid, csesidx=csesidx, auto_refresh=(idx == 0))
            a = s_data.get("agent", {})
            if a:
                seen_ids.add(aid)
                ag_type = "SKILL_AGENT" if "skillAgentDefinition" in a else ("LOW_CODE" if "lowCodeAgentDefinition" in a else a.get("agentType", "AGENT"))
                results.append({
                    "agent_id": aid,
                    "name": a.get("name", ""),
                    "display_name": a.get("displayName", ""),
                    "agent_type": ag_type,
                    "state": a.get("state", "ENABLED"),
                    "sharing_type": a.get("sharingConfig", {}).get("type", ""),
                    "description": (a.get("description") or "")[:140],
                })
        except Exception:
            continue
    return results


def get_agent(agent: str, csesidx: str = DEFAULT_CSESIDX, auto_refresh: bool = True) -> dict:
    """Retrieves full agent or skill definition via widgetGetAgent."""
    resolved = resolve_agent_id(agent) or agent
    short_id = normalize_session_id(resolved)
    payload = {
        "configId": WIDGET_CONFIG_ID,
        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
        "getAgentRequest": {"name": short_id},
    }
    data, _ = _post_widget_rpc("widgetGetAgent", payload, csesidx=csesidx, timeout=30, auto_refresh=auto_refresh)
    return data if isinstance(data, dict) else {"agent": data}


def update_agent_from_file(agent_file: str, csesidx: str = DEFAULT_CSESIDX) -> dict:
    """Updates an Agentspace agent or skill directly from a JSON file via widgetUpdateAgent."""
    abs_path = os.path.abspath(agent_file)
    with open(abs_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    agent_obj = loaded.get("agent", loaded) if isinstance(loaded, dict) else loaded
    payload = {
        "configId": WIDGET_CONFIG_ID,
        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
        "updateAgentRequest": {"agent": agent_obj},
    }
    data, _ = _post_widget_rpc("widgetUpdateAgent", payload, csesidx=csesidx, timeout=60)
    return data if isinstance(data, dict) else {"result": data}


def export_session_artifacts(
    session_id: str | None = None,
    artifact_id: str | None = None,
    formats: list[str] | tuple[str, ...] = ("pptx", "pdf"),
    session_tag: str | None = None,
    output_dir: str | None = None,
    csesidx: str = DEFAULT_CSESIDX,
) -> dict:
    """
    Exports Canvas / Slides immersive artifacts from an Agentspace session directly into
    native .pptx and/or .pdf files via `widgetGetImmersiveArtifact` + `widgetExportImmersiveArtifact`
    (the exact backend RPCs behind the Web UI's `Export -> Download as pptx / Download as PDF` menu).
    Costs ZERO Antigravity LLM tokens!
    """
    short_sess = normalize_session_id(session_id) if session_id else None
    if not short_sess and not artifact_id and session_tag:
        # Try finding the latest slides or active session from session_state.json
        for candidate_mode in (
            "agent:14950672669329422296",
            "agent:17216682253898748109",
            "model:gemini-4-argon:search=0",
        ):
            cached = get_reusable_session(session_tag, candidate_mode)
            if cached:
                short_sess = normalize_session_id(cached)
                break

    artifact_ids: list[str] = []
    if artifact_id:
        artifact_ids.append(normalize_session_id(artifact_id))
    elif short_sess:
        get_payload = {
            "configId": WIDGET_CONFIG_ID,
            "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
            "getSessionRequest": {
                "name": short_sess,
                "includeAnswerDetails": True,
                "includeMostRecentSearchResponseDetails": True,
            },
        }
        sess_data, _ = _post_widget_rpc("widgetGetSession", get_payload, csesidx=csesidx, timeout=60)
        raw_json = json.dumps(sess_data)
        found = re.findall(r"immersiveArtifacts/([0-9]+)", raw_json)
        # Preserve order of appearance, deduplicated
        for aid in found:
            if aid not in artifact_ids:
                artifact_ids.append(aid)

    if not artifact_ids:
        raise ValueError(
            f"No immersive Canvas/Slides artifact (`immersiveArtifacts/<id>`) found in session {short_sess or '(none)'}."
        )

    target_artifact_id = artifact_ids[-1]
    art_payload = {
        "configId": WIDGET_CONFIG_ID,
        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
        "getImmersiveArtifactRequest": {"name": target_artifact_id},
    }
    art_resp, _ = _post_widget_rpc("widgetGetImmersiveArtifact", art_payload, csesidx=csesidx, timeout=60)
    art_obj = art_resp.get("immersiveArtifact", art_resp) if isinstance(art_resp, dict) else {}
    if not isinstance(art_obj, dict) or not art_obj:
        raise RuntimeError(f"Failed to fetch immersiveArtifact {target_artifact_id}")

    # Crucial: widgetExportImmersiveArtifact requires the full `projects/.../locations/global/...` prefix in `name`
    art_name = art_obj.get("name", "")
    if art_name and not art_name.startswith("projects/"):
        art_obj["name"] = f"projects/195467123768/locations/global/{art_name.lstrip('/')}"
    elif not art_name:
        art_obj["name"] = f"{ENGINE_RESOURCE_NAME}/immersiveArtifacts/{target_artifact_id}"

    title = (art_obj.get("title") or f"artifact_{target_artifact_id}").strip()
    slug_title = _sanitize_slug(title, max_len=48)

    if output_dir:
        target_dir = os.path.abspath(output_dir)
    else:
        tag = _sanitize_slug(session_tag or os.environ.get("AGY_SESSION_TAG", "chat_default"), max_len=24)
        if not tag.startswith("chat_"):
            tag = f"chat_{tag}"
        target_dir = os.path.join(OUTPUTS_DIR, tag)
    os.makedirs(target_dir, exist_ok=True)

    exported_files: dict[str, dict] = {}
    need_webui_pdf = False
    for fmt in formats:
        fmt_key = fmt.strip().lower().lstrip(".")
        mime_type = EXPORT_MIME_TYPES.get(fmt_key)
        if not mime_type:
            raise ValueError(f"Unsupported export format '{fmt}'. Supported: {list(EXPORT_MIME_TYPES.keys())}")

        if fmt_key == "pdf":
            need_webui_pdf = True
            continue

        exp_payload = {
            "configId": WIDGET_CONFIG_ID,
            "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
            "location": "global",
            "exportImmersiveArtifactRequest": {
                "parent": ENGINE_RESOURCE_NAME,
                "inlineSource": {"immersiveArtifact": art_obj},
                "fileContentDestination": {"mimeType": mime_type},
            },
        }
        exp_resp, _ = _post_widget_rpc("widgetExportImmersiveArtifact", exp_payload, csesidx=csesidx, timeout=180)
        fc_obj = (
            exp_resp.get("exportImmersiveArtifactResponse", {}).get("fileContent", {})
            if isinstance(exp_resp, dict)
            else {}
        )
        b64_content = fc_obj.get("content", "") if isinstance(fc_obj, dict) else (fc_obj if isinstance(fc_obj, str) else "")
        if not b64_content:
            raise RuntimeError(f"Empty fileContent returned by widgetExportImmersiveArtifact for format={fmt_key}")

        file_bytes = base64.b64decode(b64_content)
        out_prefix = f"chat_{_sanitize_slug(session_tag, 16)}__" if session_tag else ""
        out_filename = f"{out_prefix}{short_sess or target_artifact_id[:8]}__{slug_title}.{fmt_key}"
        out_path = os.path.join(target_dir, out_filename)
        with open(out_path, "wb") as f:
            f.write(file_bytes)

        exported_files[fmt_key] = {
            "path": out_path,
            "bytes": len(file_bytes),
            "mime_type": mime_type,
        }

    if need_webui_pdf:
        if not short_sess:
            raise ValueError("A session_id (or active --session-tag) is required to export PDF via the Web UI Canvas.")
        out_prefix = f"chat_{_sanitize_slug(session_tag, 16)}__" if session_tag else ""
        pdf_filename = f"{out_prefix}{short_sess}__{slug_title}.pdf"
        pdf_path = os.path.join(target_dir, pdf_filename)
        _export_pdf_via_webui(short_sess=short_sess, save_pdf_path=pdf_path, csesidx=csesidx)
        exported_files["pdf"] = {
            "path": pdf_path,
            "bytes": os.path.getsize(pdf_path),
            "mime_type": EXPORT_MIME_TYPES["pdf"],
        }

    slides_count = len(art_obj.get("slidesArtifact", {}).get("slides", []))
    return {
        "session_id": short_sess,
        "artifact_id": target_artifact_id,
        "title": title,
        "slides_count": slides_count,
        "exported_files": exported_files,
    }


def _export_pdf_via_webui(
    short_sess: str,
    save_pdf_path: str,
    csesidx: str = DEFAULT_CSESIDX,
    browser_channel: str = DEFAULT_BROWSER_CHANNEL,
) -> str:
    """
    Uses headless Playwright with `.auth_profile` to open the session's Canvas artifact
    and click `Export -> Download as PDF` directly from the Agentspace Web UI.
    """
    from playwright.sync_api import sync_playwright

    effective_csesidx = csesidx
    try:
        xsrf, _ = load_xsrf()
        effective_csesidx = str(xsrf.get("csesidx") or csesidx)
    except Exception:
        pass

    url = f"{ORIGIN}/home/cid/{WIDGET_CONFIG_ID}/r/session/{short_sess}?csesidx={effective_csesidx}"
    with sync_playwright() as p:
        ctx, _ = _launch_persistent_browser(
            p,
            browser_channel=browser_channel,
            headless=True,
            accept_downloads=True,
            viewport={"width": 1600, "height": 900},
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(5000)

            get_started = page.get_by_text("Get started", exact=False)
            if get_started.count() > 0 and get_started.first.is_visible():
                get_started.first.click(force=True)
                page.wait_for_timeout(1200)

            page.mouse.wheel(0, 8000)
            page.wait_for_timeout(1500)

            view_btn = page.locator("[data-test-id='view-artifact-button']")
            if view_btn.count() > 0:
                view_btn.last.click(force=True)
                page.wait_for_timeout(3500)
            else:
                open_btn = page.get_by_text("Open", exact=True)
                if open_btn.count() > 0:
                    open_btn.last.click(force=True)
                    page.wait_for_timeout(3500)

            export_btn = page.get_by_text("Export", exact=False)
            for idx in range(export_btn.count()):
                if export_btn.nth(idx).is_visible():
                    export_btn.nth(idx).click(force=True)
                    page.wait_for_timeout(1200)
                    break

            pdf_item = page.get_by_text("Download as PDF", exact=False)
            if pdf_item.count() == 0:
                raise RuntimeError("Could not locate 'Download as PDF' in Web UI Export menu.")
            with page.expect_download(timeout=90000) as dl_info:
                pdf_item.first.click(force=True)
            dl = dl_info.value
            dl.save_as(save_pdf_path)
            return save_pdf_path
        finally:
            ctx.close()


def _sanitize_slug(text: str, max_len: int = 36) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", text.strip()).strip("_").lower()
    return cleaned[:max_len] or "output"


def build_scoped_output_path(
    prompt: str,
    session_tag: str | None = None,
    output_filename: str | None = None,
    agentspace_session_id: str | None = None,
) -> str:
    """
    Builds a session-scoped output file path inside ./outputs/<session_tag>/
    prefixed with <session_tag>__<timestamp>__ so different Antigravity chat
    sessions never confuse files from other chats.
    """
    tag = _sanitize_slug(session_tag or os.environ.get("AGY_SESSION_TAG", "chat_default"), max_len=24)
    if not tag.startswith("chat_"):
        tag = f"chat_{tag}"

    session_dir = os.path.join(OUTPUTS_DIR, tag)
    os.makedirs(session_dir, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    short_as_id = normalize_session_id(agentspace_session_id)[:8] if agentspace_session_id else "nosess"

    if output_filename:
        base_name = os.path.basename(output_filename)
        name_part, ext = os.path.splitext(base_name)
        ext = ext or ".md"
        slug = _sanitize_slug(name_part, max_len=40)
    else:
        slug = _sanitize_slug(prompt, max_len=32)
        ext = ".md"

    filename = f"{tag}__{ts}__{short_as_id}__{slug}{ext}"
    return os.path.join(session_dir, filename)


def ask_agentspace(
    prompt: str,
    model_id: str = DEFAULT_MODEL,
    thinking_level: str = DEFAULT_THINKING,
    session: str | None = None,
    enable_search: bool = False,
    agent: str | None = None,
    delete_session_after: bool = False,
    input_files: list[str] | None = None,
    save_output: bool = False,
    output_filename: str | None = None,
    session_tag: str | None = None,
    new_session: bool = False,
    csesidx: str = DEFAULT_CSESIDX,
) -> dict:
    resolved_agent = resolve_agent_id(agent)
    skill_name = SKILL_AGENT_IDS.get(resolved_agent) if resolved_agent else None
    mode_key = (
        f"skill:{skill_name}"
        if skill_name
        else (f"agent:{resolved_agent}" if resolved_agent else f"model:{model_id}:search={int(bool(enable_search))}")
    )

    effective_session = session
    reused_existing_session = False
    if not effective_session and session_tag and not new_session and not delete_session_after:
        cached_sess = get_reusable_session(session_tag, mode_key)
        if cached_sess:
            effective_session = format_delete_session_name(cached_sess)
            reused_existing_session = True
    elif effective_session:
        effective_session = format_delete_session_name(effective_session)
        reused_existing_session = True

    full_prompt = prompt
    if skill_name and skill_name.lower() not in full_prompt.lower():
        full_prompt = (
            f"First call `load_skill` for `{skill_name}` (and any relevant reference files via `load_skill_resource`, "
            f"such as `references/executive-slides.md` and `references/minimal-slides.md`), then follow its instructions "
            f"to fulfill this request:\n\n{full_prompt}"
        )

    attached_files: list[str] = []
    if input_files:
        file_blocks = []
        for fp in input_files:
            abs_fp = os.path.abspath(fp)
            if not os.path.isfile(abs_fp):
                raise FileNotFoundError(f"Input file not found: {abs_fp}")
            with open(abs_fp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            attached_files.append(abs_fp)
            file_blocks.append(f"--- BEGIN FILE: {os.path.basename(abs_fp)} ---\n{content}\n--- END FILE: {os.path.basename(abs_fp)} ---")
        full_prompt = f"{full_prompt}\n\n" + "\n\n".join(file_blocks)

    stream_req: dict = {
        "query": {"parts": [{"text": full_prompt}]},
    }

    if effective_session:
        stream_req["session"] = effective_session

    if resolved_agent and not skill_name:
        stream_req["answerGenerationMode"] = "AGENT"
        stream_req["agentsSpec"] = {
            "agentSpecs": [{"agentId": resolved_agent}]
        }
        stream_req["toolsSpec"] = {
            "webGroundingSpec": {},
            "imageGenerationSpec": {},
            "videoGenerationSpec": {},
            "canvasSpec": {},
            "toolRegistry": "default_tool_registry",
        }
    else:
        stream_req["answerGenerationMode"] = "NORMAL"
        stream_req["assistGenerationConfig"] = {"modelId": model_id}
        if thinking_level and thinking_level.upper() != "NONE":
            stream_req["generationSpec"] = {
                "thinkingConfig": {"thinkingLevel": thinking_level.upper()}
            }
        if enable_search:
            stream_req["toolsSpec"] = {
                "vertexAiSearchSpec": {},
                "webGroundingSpec": {},
                "imageGenerationSpec": {},
                "videoGenerationSpec": {},
                "canvasSpec": {},
                "toolRegistry": "default_tool_registry",
            }
        else:
            stream_req["toolsSpec"] = {
                "webGroundingSpec": {},
                "imageGenerationSpec": {},
                "videoGenerationSpec": {},
                "canvasSpec": {},
                "toolRegistry": "default_tool_registry",
            }
            stream_req["assistSkippingMode"] = "REQUEST_ASSIST"

    payload = {
        "configId": WIDGET_CONFIG_ID,
        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
        "streamAssistRequest": stream_req,
    }

    timeout_sec = 300 if (resolved_agent or skill_name) else 180
    chunks, xsrf_path = _post_widget_rpc("widgetStreamAssist", payload, csesidx=csesidx, timeout=timeout_sec)

    text_parts = []
    thoughts = []
    function_calls = []
    has_immersive_artifact = False
    session_name = effective_session

    if isinstance(chunks, list):
        for chunk in chunks:
            sar = chunk.get("streamAssistResponse", {})
            if sar.get("sessionInfo", {}).get("session"):
                session_name = sar["sessionInfo"]["session"]
            ans = sar.get("answer", {})
            for rep in ans.get("replies", []):
                if "immersiveArtifact" in rep:
                    has_immersive_artifact = True
                if "functionCall" in rep:
                    fc = rep["functionCall"]
                    fname = fc.get("functionName", "unknown")
                    function_calls.append(fname)
                    if fname == "save_slides_to_artifact":
                        has_immersive_artifact = True
                content = rep.get("groundedContent", {}).get("content", {})
                if content.get("thought"):
                    if "text" in content:
                        thoughts.append(content["text"])
                elif "text" in content:
                    text_parts.append(content["text"])

    session_deleted = False
    display_name = None
    if delete_session_after and session_name:
        try:
            delete_session(session_name, csesidx=csesidx)
            session_deleted = True
        except Exception:
            session_deleted = False
    elif session_name:
        if not reused_existing_session:
            display_name = ensure_session_prefix(
                session_id=session_name,
                fallback_title=prompt,
                prefix=SESSION_PREFIX,
                csesidx=csesidx,
            )
        if session_tag:
            save_reusable_session(
                session_tag=session_tag,
                mode_key=mode_key,
                session_name=session_name,
                display_name=display_name,
            )

    final_text = "".join(text_parts).strip()
    saved_output_path = None
    if save_output or output_filename:
        saved_output_path = build_scoped_output_path(
            prompt=prompt,
            session_tag=session_tag,
            output_filename=output_filename,
            agentspace_session_id=session_name,
        )
        with open(saved_output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

    exported_artifacts = None
    if session_name and not session_deleted and (has_immersive_artifact or resolved_agent in SLIDES_AGENT_IDS):
        try:
            exported_artifacts = export_session_artifacts(
                session_id=session_name,
                formats=("pptx",),
                session_tag=session_tag,
                csesidx=csesidx,
            )
        except Exception:
            exported_artifacts = None

    return {
        "text": final_text,
        "thoughts": "".join(thoughts).strip(),
        "function_calls": function_calls,
        "session": session_name,
        "session_reused": reused_existing_session,
        "session_display_name": display_name,
        "session_deleted": session_deleted,
        "agent": resolved_agent,
        "model": model_id if not resolved_agent else f"agent:{resolved_agent}",
        "attached_files": attached_files,
        "saved_output_path": saved_output_path,
        "exported_artifacts": exported_artifacts,
        "line_count": len(final_text.splitlines()) if final_text else 0,
        "char_count": len(final_text),
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
        "--new-session",
        action="store_true",
        help="Force creating a brand-new Agentspace chat session even if --session-tag has an active session",
    )
    parser.add_argument(
        "--ephemeral",
        "--delete-after",
        dest="delete_after",
        action="store_true",
        help="Automatically delete the chat session after receiving the response",
    )
    parser.add_argument(
        "--file",
        "-f",
        dest="input_files",
        action="append",
        default=[],
        metavar="FILE_PATH",
        help="Attach a local file directly from disk into the prompt (can be specified multiple times) to save AGY tokens",
    )
    parser.add_argument(
        "--save-output",
        action="store_true",
        help="Save the full response into ./outputs/<session_tag>/ with a session-scoped filename",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output_filename",
        default=None,
        metavar="FILENAME",
        help="Custom filename suffix (e.g. 'feature_query.sql') saved inside ./outputs/<session_tag>/",
    )
    parser.add_argument(
        "--session-tag",
        default=None,
        metavar="TAG",
        help="Antigravity conversation ID prefix or tag (e.g. 'bba4da86') so other chat sessions never confuse output files",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="When saving output to disk, print only the file path and a short preview to stdout to save AGY context tokens",
    )
    parser.add_argument(
        "--max-preview-chars",
        type=int,
        default=500,
        help="Maximum preview characters when --summary-only is used (default: 500)",
    )
    parser.add_argument(
        "--delete-session",
        default=None,
        metavar="SESSION_ID",
        help="Delete a specific chat session by ID or full resource name and exit",
    )
    parser.add_argument(
        "--export-slides",
        "--export-artifact",
        dest="export_slides",
        nargs="?",
        const="AUTO",
        default=None,
        metavar="SESSION_ID",
        help="Export Canvas/Slides artifact from a session (or latest --session-tag slides session) to native .pptx/.pdf",
    )
    parser.add_argument(
        "--export-format",
        default="pptx",
        help="Comma-separated export formats for --export-slides: 'pptx', 'pdf', or 'pptx,pdf' (default: pptx)",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List recent chat sessions on Agentspace and exit",
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="List custom agents and skills on Agentspace and exit",
    )
    parser.add_argument(
        "--get-agent",
        default=None,
        metavar="AGENT_ID_OR_ALIAS",
        help="Fetch the full JSON definition of an agent or skill (e.g. 'office', 'office-creator', 'netra') and exit",
    )
    parser.add_argument(
        "--update-agent-file",
        default=None,
        metavar="JSON_FILE_PATH",
        help="Update an agent or skill on Agentspace directly from a local JSON definition file via widgetUpdateAgent and exit",
    )
    parser.add_argument(
        "--refresh-token",
        action="store_true",
        help="Open browser UI to download/refresh the XSRF token into ./agentspace_xsrf.json",
    )
    parser.add_argument(
        "--browser",
        default=DEFAULT_BROWSER_CHANNEL,
        help=f"Browser channel for --refresh-token (default on this OS: {DEFAULT_BROWSER_CHANNEL}; supports chrome or msedge)",
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

        if args.list_agents:
            agents = list_agents(include_skills=True, csesidx=args.csesidx)
            if args.json:
                print(json.dumps(agents, indent=2))
            else:
                for a in agents:
                    print(f"[{a['agent_id']}] ({a['agent_type']} | {a['state']}) {a['display_name']} — {a['description']}")
            return

        if args.get_agent:
            agent_data = get_agent(args.get_agent, csesidx=args.csesidx)
            if args.output_filename:
                out_path = os.path.abspath(args.output_filename)
                os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(agent_data, f, indent=2)
                print(f"Saved agent definition to: {out_path}")
            else:
                print(json.dumps(agent_data, indent=2))
            return

        if args.update_agent_file:
            upd_res = update_agent_from_file(args.update_agent_file, csesidx=args.csesidx)
            if args.json:
                print(json.dumps(upd_res, indent=2))
            else:
                ag = upd_res.get("agent", {})
                print(
                    f"Updated agent/skill: {ag.get('displayName')} ({normalize_session_id(ag.get('name', ''))}) "
                    f"[type={ag.get('agentType')}, state={ag.get('state')}]"
                )
            return

        if args.delete_session:
            res = delete_session(args.delete_session, csesidx=args.csesidx)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Deleted session: {res['session_id']}")
            return

        if args.export_slides and not args.prompt:
            target_sess = None if args.export_slides == "AUTO" else args.export_slides
            fmts = [x.strip() for x in args.export_format.split(",") if x.strip()]
            exp_res = export_session_artifacts(
                session_id=target_sess,
                formats=fmts,
                session_tag=args.session_tag,
                csesidx=args.csesidx,
            )
            if args.json:
                print(json.dumps(exp_res, indent=2))
            else:
                print(
                    f"Exported '{exp_res['title']}' ({exp_res['slides_count']} slides, artifact={exp_res['artifact_id']}):"
                )
                for fmt_k, info in exp_res["exported_files"].items():
                    print(f"  [{fmt_k.upper()}] {info['path']} ({info['bytes']:,} bytes)")
            return

        if not args.prompt:
            parser.error("A prompt is required unless --list-sessions, --delete-session, or --export-slides is specified.")

        res = ask_agentspace(
            prompt=args.prompt,
            model_id=args.model,
            thinking_level=args.thinking,
            session=args.session,
            enable_search=args.search,
            agent=args.agent,
            delete_session_after=args.delete_after,
            input_files=args.input_files,
            save_output=args.save_output or bool(args.output_filename) or args.summary_only,
            output_filename=args.output_filename,
            session_tag=args.session_tag,
            new_session=args.new_session,
            csesidx=args.csesidx,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        elif args.summary_only and res.get("saved_output_path"):
            preview = res["text"][: args.max_preview_chars]
            if len(res["text"]) > args.max_preview_chars:
                preview += "\n... [truncated in stdout to save AGY tokens]"
            print(
                f"Saved full response ({res['line_count']} lines, {res['char_count']} chars) to:\n"
                f"  {res['saved_output_path']}\n\n"
                f"Preview:\n{preview}"
            )
            if res.get("exported_artifacts"):
                exp = res["exported_artifacts"]
                for fmt_k, info in exp.get("exported_files", {}).items():
                    print(f"\n[Auto-Exported {fmt_k.upper()} ({exp.get('slides_count')} slides): {info['path']} ({info['bytes']:,} bytes)]")
            if res.get("session_deleted"):
                print(f"\n[Ephemeral mode: deleted temporary session {normalize_session_id(res['session'])}]", file=sys.stderr)
            elif res.get("session"):
                mode_note = "Continued" if res.get("session_reused") else f"Created ({res.get('session_display_name') or '[agy-bridge]'})"
                print(f"\n[Agentspace Session {mode_note}: {normalize_session_id(res['session'])}]", file=sys.stderr)
        else:
            print(res["text"])
            if res.get("saved_output_path"):
                print(f"\n[Saved session-scoped output to: {res['saved_output_path']}]", file=sys.stderr)
            if res.get("exported_artifacts"):
                exp = res["exported_artifacts"]
                for fmt_k, info in exp.get("exported_files", {}).items():
                    print(f"\n[Auto-Exported {fmt_k.upper()} ({exp.get('slides_count')} slides): {info['path']} ({info['bytes']:,} bytes)]", file=sys.stderr)
            if res.get("session_deleted"):
                print(f"\n[Ephemeral mode: deleted temporary session {normalize_session_id(res['session'])}]", file=sys.stderr)
            elif res.get("session"):
                mode_note = "Continued" if res.get("session_reused") else f"Created ({res.get('session_display_name') or '[agy-bridge]'})"
                print(f"\n[Agentspace Session {mode_note}: {normalize_session_id(res['session'])}]", file=sys.stderr)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} Error:\n{err_body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
