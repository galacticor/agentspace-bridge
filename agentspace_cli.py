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
import urllib.request

WIDGET_CONFIG_ID = os.environ.get("AGENTSPACE_CONFIG_ID", "384c42b0-2885-415a-82d5-f2babc063b6e")
DEFAULT_CSESIDX = os.environ.get("AGENTSPACE_CSESIDX", "")
DEFAULT_MODEL = os.environ.get("AGENTSPACE_MODEL", "gemini-4-argon")
DEFAULT_THINKING = os.environ.get("AGENTSPACE_THINKING", "MEDIUM")
HOST = "biz-discoveryengine.googleapis.com"
ORIGIN = "https://vertexaisearch.cloud.google"


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


def load_xsrf() -> tuple[dict, str]:
    for p in get_xsrf_candidate_paths():
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                idx = raw.find("{")
                if idx != -1:
                    raw = raw[idx:]
                data = json.loads(raw)
                if "xsrfToken" in data and "keyId" in data:
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


def ask_agentspace(
    prompt: str,
    model_id: str = DEFAULT_MODEL,
    thinking_level: str = DEFAULT_THINKING,
    session: str | None = None,
    enable_search: bool = False,
    csesidx: str = DEFAULT_CSESIDX,
) -> dict:
    xsrf, xsrf_path = load_xsrf()
    jwt_tok = make_jwt(xsrf, csesidx=csesidx)
    url = f"https://{HOST}/v1alpha/locations/global/widgetStreamAssist"

    stream_req: dict = {
        "query": {"parts": [{"text": prompt}]},
        "assistGenerationConfig": {"modelId": model_id},
    }
    if thinking_level and thinking_level.upper() != "NONE":
        stream_req["generationSpec"] = {
            "thinkingConfig": {"thinkingLevel": thinking_level.upper()}
        }
    if session:
        stream_req["session"] = session
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

    with urllib.request.urlopen(req, timeout=120) as resp:
        chunks = json.loads(resp.read().decode("utf-8"))

    text_parts = []
    thoughts = []
    session_name = None

    for chunk in chunks:
        sar = chunk.get("streamAssistResponse", {})
        if not session_name and sar.get("sessionInfo", {}).get("session"):
            session_name = sar["sessionInfo"]["session"]
        ans = sar.get("answer", {})
        for rep in ans.get("replies", []):
            content = rep.get("groundedContent", {}).get("content", {})
            if content.get("thought"):
                if "text" in content:
                    thoughts.append(content["text"])
            elif "text" in content:
                text_parts.append(content["text"])

    return {
        "text": "".join(text_parts).strip(),
        "thoughts": "".join(thoughts).strip(),
        "session": session_name,
        "model": model_id,
        "xsrf_source": xsrf_path,
    }


def main():
    parser = argparse.ArgumentParser(description="Query IOH Agentspace (Gemini 4 Argon)")
    parser.add_argument("prompt", help="Prompt text to send to Agentspace")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model ID (default: gemini-4-argon)")
    parser.add_argument("--thinking", default=DEFAULT_THINKING, help="Thinking level: LOW, MEDIUM, HIGH, NONE")
    parser.add_argument("--session", default=None, help="Optional session resource name to continue a conversation")
    parser.add_argument("--csesidx", default=DEFAULT_CSESIDX, help="Browser session index (csesidx) from URL")
    parser.add_argument("--search", action="store_true", help="Enable Enterprise Search (Confluence/SharePoint/Jira) & Web Grounding")
    parser.add_argument("--json", action="store_true", help="Output full JSON response")
    args = parser.parse_args()

    try:
        res = ask_agentspace(
            prompt=args.prompt,
            model_id=args.model,
            thinking_level=args.thinking,
            session=args.session,
            enable_search=args.search,
            csesidx=args.csesidx,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(res["text"])
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} Error:\n{err_body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
