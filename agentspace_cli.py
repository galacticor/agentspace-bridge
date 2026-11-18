#!/usr/bin/env python3
r"""
IOH Agentspace (Gemini Enterprise) CLI & Helper for Google Antigravity.
Connects directly to https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetStreamAssist
using the local Workforce Identity BYOID session key (~/Downloads/json.txt or %TEMP%/agentspace_xsrf.json).
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import glob
import hashlib
import hmac
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_XSRF_PATH = os.path.join(SCRIPT_DIR, "agentspace_xsrf.json")
LOCAL_CONFIG_JSON_PATH = os.path.join(SCRIPT_DIR, "agentspace_local.json")
LOCAL_ENV_PATH = os.path.join(SCRIPT_DIR, ".env")
AUTH_PROFILE_DIR = os.path.join(SCRIPT_DIR, ".auth_profile")
REFRESH_LOCK_PATH = os.path.join(AUTH_PROFILE_DIR, ".refresh.lock")
OUTPUTS_DIR = os.path.join(SCRIPT_DIR, "outputs")

_INTRA_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_INTRA_LOCKS_GUARD = threading.Lock()


def _get_intra_process_lock(lock_path: str) -> threading.Lock:
    norm = os.path.abspath(lock_path)
    with _INTRA_LOCKS_GUARD:
        lk = _INTRA_PROCESS_LOCKS.get(norm)
        if lk is None:
            lk = threading.Lock()
            _INTRA_PROCESS_LOCKS[norm] = lk
        return lk


class _FileLock:
    """Zero-dependency cross-process (fcntl/msvcrt) + intra-process (threading.Lock) file lock."""

    def __init__(self, lock_path: str, blocking: bool = True, timeout_sec: float = 90.0) -> None:
        self.lock_path = os.path.abspath(lock_path)
        self.blocking = blocking
        self.timeout_sec = max(0.1, float(timeout_sec))
        self._thread_lock = _get_intra_process_lock(self.lock_path)
        self._fh = None

    def _try_os_lock(self) -> bool:
        assert self._fh is not None
        if sys.platform == "win32":
            import msvcrt

            self._fh.seek(0)
            try:
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        else:
            import fcntl

            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (BlockingIOError, OSError):
                return False

    def _release_os_lock(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass

    def __enter__(self) -> "_FileLock":
        deadline = time.monotonic() + self.timeout_sec
        acquired_thread = (
            self._thread_lock.acquire(timeout=self.timeout_sec)
            if self.blocking
            else self._thread_lock.acquire(blocking=False)
        )
        if not acquired_thread:
            if not self.blocking:
                raise BlockingIOError(f"Lock busy (intra-process): {self.lock_path}")
            raise TimeoutError(f"Timed out after {self.timeout_sec:.1f}s waiting for thread lock: {self.lock_path}")

        try:
            os.makedirs(os.path.dirname(self.lock_path) or ".", exist_ok=True)
            try:
                self._fh = open(self.lock_path, "r+b")
            except FileNotFoundError:
                self._fh = open(self.lock_path, "a+b")
            if sys.platform == "win32":
                self._fh.seek(0, os.SEEK_END)
                if self._fh.tell() == 0:
                    self._fh.write(b"0")
                    self._fh.flush()

            while True:
                if self._try_os_lock():
                    return self
                if not self.blocking:
                    raise BlockingIOError(f"Lock busy (OS): {self.lock_path}")
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out after {self.timeout_sec:.1f}s waiting for file lock: {self.lock_path}")
                time.sleep(0.15)
        except Exception:
            if self._fh is not None:
                try:
                    self._fh.close()
                except Exception:
                    pass
                self._fh = None
            self._thread_lock.release()
            raise

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self._release_os_lock()
        finally:
            if self._fh is not None:
                try:
                    self._fh.close()
                except Exception:
                    pass
                self._fh = None
            self._thread_lock.release()


def _atomic_write_json(target_path: str, data: dict | list) -> None:
    """Atomically writes JSON via same-directory temp file + fsync + os.replace."""
    abs_target = os.path.abspath(target_path)
    parent_dir = os.path.dirname(abs_target) or "."
    os.makedirs(parent_dir, exist_ok=True)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent_dir,
            prefix=".tmp_",
            suffix=".json",
            delete=False,
        ) as tf:
            tmp_path = tf.name
            json.dump(data, tf, indent=2)
            tf.flush()
            os.fsync(tf.fileno())
        for rep_try in range(3):
            try:
                os.replace(tmp_path, abs_target)
                break
            except PermissionError:
                if rep_try == 2:
                    raise
                time.sleep(0.05 * (rep_try + 1))
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise


def _load_local_personal_config() -> dict:
    """
    Loads git-ignored personal configuration from `./.env` and `./agentspace_local.json`
    into `os.environ` (without overwriting existing shell env vars).
    """
    local_cfg: dict = {}
    if os.path.isfile(LOCAL_ENV_PATH):
        try:
            with open(LOCAL_ENV_PATH, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and v:
                        os.environ.setdefault(k, v)
        except Exception:
            pass

    if os.path.isfile(LOCAL_CONFIG_JSON_PATH):
        try:
            with open(LOCAL_CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                local_cfg = loaded
                json_to_env = {
                    "employee_id": "AGENTSPACE_EMPLOYEE_ID",
                    "csesidx": "AGENTSPACE_CSESIDX",
                    "entry_url": "AGENTSPACE_ENTRY_URL",
                    "config_id": "AGENTSPACE_CONFIG_ID",
                    "model": "AGENTSPACE_MODEL",
                    "thinking": "AGENTSPACE_THINKING",
                    "browser": "AGENTSPACE_BROWSER",
                    "onedrive_drive_id": "AGENTSPACE_ONEDRIVE_DRIVE_ID",
                    "onedrive_parent_id": "AGENTSPACE_ONEDRIVE_PARENT_ID",
                    "onedrive_drive_name": "AGENTSPACE_ONEDRIVE_DRIVE_NAME",
                    "onedrive_folder_name": "AGENTSPACE_ONEDRIVE_FOLDER_NAME",
                    "onedrive_folder_url": "AGENTSPACE_ONEDRIVE_FOLDER_URL",
                }
                for jk, env_k in json_to_env.items():
                    val = loaded.get(jk)
                    if val is not None and str(val).strip():
                        os.environ.setdefault(env_k, str(val).strip())
        except Exception:
            pass
    return local_cfg


LOCAL_PERSONAL_CONFIG = _load_local_personal_config()
AGENTSPACE_ENTRY_URL = os.environ.get("AGENTSPACE_ENTRY_URL", "https://agentspace.ioh.co.id")
WIDGET_CONFIG_ID = os.environ.get("AGENTSPACE_CONFIG_ID", "384c42b0-2885-415a-82d5-f2babc063b6e")
DEFAULT_CSESIDX = os.environ.get("AGENTSPACE_CSESIDX", "")
DEFAULT_MODEL = os.environ.get("AGENTSPACE_MODEL", "gemini-4-argon")
DEFAULT_THINKING = os.environ.get("AGENTSPACE_THINKING", "MEDIUM")
DEFAULT_STREAM_TIMEOUT = int(os.environ.get("AGENTSPACE_STREAM_TIMEOUT", "300"))
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
    "office-creator-2": "2291045905737541211",
    "office2": "2291045905737541211",
    "agb": "18420663427156982501",
    "catalyst": "app_catalyst_agent",
    "netra-office-workflow": "8458183310708652909",
    "workflow": "8458183310708652909",
}

# Skills (`agentType: "SKILL_AGENT"`) run inside NORMAL mode (`gemini-4-argon` + `canvasSpec: {}`
# + `load_skill` tool) rather than `answerGenerationMode: "AGENT"` (which causes HTTP 500 for skills).
SKILL_AGENT_IDS: dict[str, str] = {
    "14950672669329422296": "office-workflow-suite",
}

SLIDES_AGENT_IDS: set[str] = {
    "14950672669329422296",  # office-workflow-suite (SKILL_AGENT)
    "17216682253898748109",  # Office File Creator (LOW_CODE)
    "2291045905737541211",   # Office File Creator 2.0 (LOW_CODE with Tricks 1 & 2)
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


def _get_fresh_cached_xsrf(
    stale_key_id: str | None = None,
    min_saved_at: int | None = None,
    call_started_at: int | None = None,
) -> tuple[dict, str] | None:
    """Checks whether another concurrent worker already refreshed the XSRF token on disk."""
    try:
        xsrf, path = load_xsrf()
    except FileNotFoundError:
        return None
    saved_at = int(xsrf.get("savedAt") or 0)
    if stale_key_id and xsrf.get("keyId") and str(xsrf.get("keyId")) != str(stale_key_id):
        return xsrf, path
    if min_saved_at is not None and saved_at >= min_saved_at:
        return xsrf, path
    if stale_key_id is None and min_saved_at is None and call_started_at is not None and saved_at > call_started_at:
        return xsrf, path
    return None


def refresh_xsrf_token(
    csesidx: str | None = None,
    browser_channel: str = DEFAULT_BROWSER_CHANNEL,
    timeout_sec: int = 180,
    headless_first: bool = True,
    stale_key_id: str | None = None,
    min_saved_at: int | None = None,
) -> tuple[dict, str]:
    """
    Refreshes the IOH Agentspace XSRF token using a persistent Work profile in .auth_profile/,
    serialized across threads and OS processes via REFRESH_LOCK_PATH.
    """
    call_started_at = int(time.time())
    pre_cached = _get_fresh_cached_xsrf(stale_key_id=stale_key_id, min_saved_at=min_saved_at)
    if pre_cached is not None:
        return pre_cached

    target_save_path = (
        os.path.abspath(os.environ["AGENTSPACE_XSRF_PATH"])
        if os.environ.get("AGENTSPACE_XSRF_PATH")
        else PROJECT_XSRF_PATH
    )

    # Resolve Playwright interpreter BEFORE acquiring OS REFRESH_LOCK_PATH so child `alt_py` never deadlocks,
    # but serialize threads inside this process via _get_intra_process_lock so only 1 `alt_py` spawns.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        alt_py = _find_playwright_python()
        if alt_py:
            with _get_intra_process_lock(REFRESH_LOCK_PATH):
                cached = _get_fresh_cached_xsrf(
                    stale_key_id=stale_key_id,
                    min_saved_at=min_saved_at,
                    call_started_at=call_started_at,
                )
                if cached is not None:
                    return cached
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
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
                return load_xsrf()
        raise

    with _FileLock(REFRESH_LOCK_PATH, blocking=True, timeout_sec=timeout_sec + 35):
        cached = _get_fresh_cached_xsrf(
            stale_key_id=stale_key_id,
            min_saved_at=min_saved_at,
            call_started_at=call_started_at,
        )
        if cached is not None:
            print(
                f"[Agentspace Auth] Reusing token refreshed by peer worker (keyId={cached[0].get('keyId')}) from {cached[1]}",
                file=sys.stderr,
            )
            return cached

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

        captured["savedAt"] = max(int(captured.get("savedAt") or time.time()), int(min_saved_at or 0), call_started_at + 1)
        _atomic_write_json(target_save_path, captured)
        print(
            f"[Agentspace Auth] Saved fresh token (keyId={captured.get('keyId')}, csesidx={captured.get('csesidx')}) to {target_save_path}",
            file=sys.stderr,
        )
        return captured, target_save_path


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

def resolve_csesidx(csesidx: str | None = None) -> str:
    """Returns explicit csesidx if provided, or reads the user's csesidx from ./agentspace_xsrf.json."""
    if csesidx:
        return str(csesidx)
    try:
        xsrf, _ = load_xsrf()
        if xsrf.get("csesidx"):
            return str(xsrf["csesidx"])
    except Exception:
        pass
    return DEFAULT_CSESIDX



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
        xsrf, xsrf_path = refresh_xsrf_token(csesidx=csesidx, min_saved_at=int(time.time()) - 5)

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
                except (http.client.IncompleteRead, TimeoutError, socket.timeout) as ir:
                    raw = getattr(ir, "partial", b"").decode("utf-8", errors="replace")
                if not raw.strip():
                    return {}, xsrf_path
                try:
                    return json.loads(raw), xsrf_path
                except json.JSONDecodeError:
                    # Salvage complete JSON objects from partial stream array
                    salvaged = []
                    decoder = json.JSONDecoder()
                    idx = 0
                    n = len(raw)
                    while idx < n:
                        while idx < n and raw[idx] in " \t\r\n,[]":
                            idx += 1
                        if idx >= n:
                            break
                        try:
                            obj, next_idx = decoder.raw_decode(raw, idx)
                            salvaged.append(obj)
                            idx = next_idx
                        except json.JSONDecodeError:
                            break
                    if salvaged:
                        return salvaged, xsrf_path
                    raise
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and auto_refresh and attempt == 0:
                stale_kid = str(xsrf.get("keyId") or "")
                next_min_ts = int(xsrf.get("savedAt") or 0) + 1
                print(
                    f"[Agentspace Auth] Token in {xsrf_path} expired (HTTP {e.code}, keyId={stale_kid}). Refreshing under lock...",
                    file=sys.stderr,
                )
                xsrf, xsrf_path = refresh_xsrf_token(
                    csesidx=csesidx,
                    stale_key_id=stale_kid or None,
                    min_saved_at=next_min_ts if next_min_ts > 1 else int(time.time()),
                )
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
DEFAULT_MAX_MEDIA_PROMPTS = int(os.environ.get("AGENTSPACE_MAX_MEDIA_PROMPTS", "3"))

_MEDIA_PROMPT_RE = re.compile(
    r"(?:^\s*(?:generate|create|render|make|draw|produce)\s+(?:an?\s+)?(?:short\s+|cinematic\s+|realistic\s+|3d\s+|10-second\s+|8-second\s+)*"
    r"(?:image|video|animation|illustration|picture|photo|clip)\b|"
    r"\b(?:generate\s+an?\s+image|generate\s+a\s+video|create\s+an?\s+image|create\s+a\s+(?:short\s+|cinematic\s+|realistic\s+|10-second\s+|8-second\s+)*video)\b)",
    re.IGNORECASE,
)

# Data visualization / chart / plot / diagram terms that must NEVER be treated as AI image/video generator sessions
_DATA_VIZ_EXCLUDE_RE = re.compile(
    r"\b(?:chart|charts|plot|plots|graph|graphs|visualization|visualisation|histogram|heatmap|scatter|"
    r"bar\s+chart|line\s+chart|pie\s+chart|dashboard|table|sql|query|bigquery|netra|arpu|revenue|cohort|"
    r"pptx|slide|slides|presentation|deck|matplotlib|seaborn|plotly|dataframe|csv|xlsx|excel)\b",
    re.IGNORECASE,
)


def is_media_generation_prompt(prompt: str) -> bool:
    """
    Detects whether a prompt is purely an AI image/artwork or video generation request
    (Imagen / Veo), while explicitly excluding data visualization, chart, plot, or analytical requests.
    """
    if not prompt:
        return False
    head = prompt.strip()[:350]
    if _DATA_VIZ_EXCLUDE_RE.search(head):
        return False
    return bool(_MEDIA_PROMPT_RE.search(head))


def _normalize_media_base_tag(session_tag: str | None) -> str | None:
    """
    Strips per-asset suffixes like `_img1`, `_vid2`, `_scene3`, `_asset4` from a session_tag
    so that multiple media calls in the same task share a single media session slot and counter.
    """
    if not session_tag:
        return None
    cleaned = session_tag.strip()
    cleaned = re.sub(r"_(?:img|vid|video|image|scene|shot|asset|cutout|clip)_?\d+$", "", cleaned, flags=re.IGNORECASE)
    return cleaned or session_tag


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


def _load_session_state(session_tag: str | None) -> tuple[dict, str | None]:
    state_path = _get_session_state_path(session_tag)
    state: dict = {
        "session_tag": session_tag,
        "sessions": {},
        "prompt_counts": {},
        "media_sessions": [],
        "history": [],
    }
    if state_path and os.path.isfile(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    state.update(loaded)
        except Exception:
            pass
    if not isinstance(state.get("sessions"), dict):
        state["sessions"] = {}
    if not isinstance(state.get("prompt_counts"), dict):
        state["prompt_counts"] = {}
    if not isinstance(state.get("media_sessions"), list):
        state["media_sessions"] = []
    if not isinstance(state.get("history"), list):
        state["history"] = []
    return state, state_path


def get_reusable_session(session_tag: str | None, mode_key: str) -> str | None:
    state, _ = _load_session_state(session_tag)
    return state.get("sessions", {}).get(mode_key)


def get_session_prompt_count(session_tag: str | None, mode_key: str) -> int:
    state, _ = _load_session_state(session_tag)
    try:
        return int(state.get("prompt_counts", {}).get(mode_key, 0))
    except Exception:
        return 0


def clear_reusable_session(
    session_tag: str | None,
    mode_key: str,
    deleted_session_id: str | None = None,
) -> None:
    state_path = _get_session_state_path(session_tag)
    if not state_path:
        return
    with _FileLock(f"{state_path}.lock", blocking=True, timeout_sec=15):
        state, _ = _load_session_state(session_tag)
        state["sessions"].pop(mode_key, None)
        state["prompt_counts"].pop(mode_key, None)
        if deleted_session_id:
            short_del = normalize_session_id(deleted_session_id)
            state["media_sessions"] = [
                s for s in state.get("media_sessions", []) if normalize_session_id(s) != short_del
            ]
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _atomic_write_json(state_path, state)


def save_reusable_session(
    session_tag: str | None,
    mode_key: str,
    session_name: str,
    display_name: str | None = None,
    prompt_count: int | None = None,
    is_media: bool = False,
    update_active_slot: bool = True,
) -> int:
    state_path = _get_session_state_path(session_tag)
    if not state_path or not session_name:
        return 0
    with _FileLock(f"{state_path}.lock", blocking=True, timeout_sec=15):
        state, _ = _load_session_state(session_tag)
        prev_sess = state["sessions"].get(mode_key)
        short_new = normalize_session_id(session_name)
        short_prev = normalize_session_id(prev_sess) if prev_sess else None

        if prompt_count is not None:
            new_count = prompt_count
        elif short_prev == short_new:
            new_count = int(state["prompt_counts"].get(mode_key, 0)) + 1
        else:
            new_count = 1

        if update_active_slot:
            state["sessions"][mode_key] = session_name
            state["prompt_counts"][mode_key] = new_count
        if is_media or ":media" in mode_key:
            if short_new not in [normalize_session_id(x) for x in state["media_sessions"]]:
                state["media_sessions"].append(short_new)
        if short_new not in [normalize_session_id(x) for x in state["history"]]:
            state["history"].append(short_new)
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if display_name:
            state["last_display_name"] = display_name
        _atomic_write_json(state_path, state)
        return new_count


def finish_task_sessions(
    session_tag: str,
    media_only: bool = True,
    csesidx: str = DEFAULT_CSESIDX,
) -> dict:
    """
    Cleans up and deletes tracked Agentspace sessions for a finished subagent or task (`--finish-task`).
    Also sweeps any sibling `<session_tag>_img*` / `<session_tag>_vid*` folders in `./outputs/`.
    By default (`media_only=True`), deletes all media sessions (and any single-asset sub-tags)
    while preserving main Netra/Search/Slides sessions unless `media_only=False`.
    """
    base_tag = _normalize_media_base_tag(session_tag) or session_tag
    clean_base = _sanitize_slug(base_tag, max_len=24)
    if not clean_base.startswith("chat_"):
        clean_base = f"chat_{clean_base}"

    candidate_dirs: list[str] = []
    if os.path.isdir(OUTPUTS_DIR):
        for entry in sorted(os.listdir(OUTPUTS_DIR)):
            if entry == clean_base or entry.startswith(f"{clean_base}_"):
                full_d = os.path.join(OUTPUTS_DIR, entry)
                if os.path.isdir(full_d):
                    candidate_dirs.append(full_d)

    sessions_to_delete: list[str] = []
    state_files_touched: list[str] = []

    for d_path in candidate_dirs:
        st_file = os.path.join(d_path, "session_state.json")
        is_sub_asset_dir = os.path.basename(d_path) != clean_base
        if os.path.isfile(st_file):
            with _FileLock(f"{st_file}.lock", blocking=True, timeout_sec=15):
                try:
                    with open(st_file, "r", encoding="utf-8") as f:
                        st = json.load(f)
                except Exception:
                    st = {}
                sess_map = st.get("sessions", {}) if isinstance(st.get("sessions"), dict) else {}
                media_list = st.get("media_sessions", []) if isinstance(st.get("media_sessions"), list) else []

                for m_sess in media_list:
                    short_id = normalize_session_id(m_sess)
                    if short_id and short_id not in sessions_to_delete:
                        sessions_to_delete.append(short_id)

                for m_key, s_val in list(sess_map.items()):
                    if not s_val:
                        continue
                    if (not media_only) or (":media" in m_key) or is_sub_asset_dir:
                        short_id = normalize_session_id(s_val)
                        if short_id and short_id not in sessions_to_delete:
                            sessions_to_delete.append(short_id)
                        sess_map.pop(m_key, None)
                        if isinstance(st.get("prompt_counts"), dict):
                            st["prompt_counts"].pop(m_key, None)

                st["media_sessions"] = []
                st["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                try:
                    _atomic_write_json(st_file, st)
                    state_files_touched.append(st_file)
                except Exception:
                    pass

        # Also check filenames in sub-asset folders (`chat_<tag>_img1__<ts>__<short_id>__...`)
        if is_sub_asset_dir:
            for fname in os.listdir(d_path):
                m_fn = re.match(r"^chat_[a-z0-9_]+__\d{8}_\d{6}__([0-9]{6,22})__", fname)
                if m_fn:
                    cand_prefix = m_fn.group(1)
                    if len(cand_prefix) >= 12 and cand_prefix not in sessions_to_delete:
                        sessions_to_delete.append(cand_prefix)

    deleted_ids: list[str] = []
    already_deleted_ids: list[str] = []
    failed_ids: list[dict] = []
    for sid in sessions_to_delete:
        try:
            delete_session(sid, csesidx=csesidx)
            deleted_ids.append(sid)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                already_deleted_ids.append(sid)
            else:
                failed_ids.append({"session_id": sid, "error": str(exc)})
        except Exception as exc:
            if "404" in str(exc):
                already_deleted_ids.append(sid)
            else:
                failed_ids.append({"session_id": sid, "error": str(exc)})

    return {
        "base_session_tag": base_tag,
        "media_only": media_only,
        "deleted_sessions": deleted_ids,
        "already_deleted_sessions": already_deleted_ids,
        "deleted_count": len(deleted_ids),
        "failed": failed_ids,
        "state_files_updated": state_files_touched,
    }


def cleanup_media_sessions(
    limit: int = 50,
    keep_latest: int = 0,
    csesidx: str = DEFAULT_CSESIDX,
) -> dict:
    """
    Scans recent Agentspace sessions via `list_sessions` and deletes sessions that were created
    for image or video generation (matching media prompts or known media titles).
    """
    sessions = list_sessions(limit=limit, csesidx=csesidx)
    matched_media: list[dict] = []
    title_media_re = re.compile(
        r"(?:\b(?:video|animation|image|helix\s+art|wave\s+art|celestial\s+observatory|cosmic\s+emblems|cosmic\s+hall|nautilus\s+shell)\b)",
        re.IGNORECASE,
    )
    for s in sessions:
        if s.get("mode") == "AGENT":
            continue
        fq = (s.get("first_query") or "").strip()
        dn = (s.get("display_name") or "").strip()
        if _DATA_VIZ_EXCLUDE_RE.search(fq) or _DATA_VIZ_EXCLUDE_RE.search(dn):
            continue
        if is_media_generation_prompt(fq) or is_media_generation_prompt(dn) or bool(title_media_re.search(dn)):
            # Never accidentally delete PPTX / Netra / OneDrive / outline planning / chart sessions
            if any(k in fq.lower() or k in dn.lower() for k in ("pptx", "slide", "onedrive", "netra", "series plan", "chart", "plot", "visualization")):
                continue
            matched_media.append(s)

    to_delete = matched_media[keep_latest:] if keep_latest > 0 else matched_media
    deleted: list[dict] = []
    errors: list[dict] = []
    for s in to_delete:
        sid = s["session_id"]
        try:
            delete_session(sid, csesidx=csesidx)
            deleted.append({
                "session_id": sid,
                "display_name": s.get("display_name"),
                "first_query": s.get("first_query"),
            })
        except Exception as exc:
            errors.append({"session_id": sid, "error": str(exc)})

    return {
        "scanned": len(sessions),
        "matched_media_sessions": len(matched_media),
        "kept_latest": keep_latest,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "errors": errors,
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
    """Updates an Agentspace agent or skill directly from a JSON file via widgetUpdateAgent
    and automatically deploys lowCodeAgentDefinition agents via widgetDeployLowCodeAgent."""
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
    if isinstance(agent_obj, dict) and "lowCodeAgentDefinition" in agent_obj:
        short_id = normalize_session_id(agent_obj.get("name", ""))
        if short_id:
            deploy_payload = {
                "configId": WIDGET_CONFIG_ID,
                "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
                "deployLowCodeAgentRequest": {"name": short_id},
            }
            deploy_res, _ = _post_widget_rpc("widgetDeployLowCodeAgent", deploy_payload, csesidx=csesidx, timeout=60)
            if isinstance(data, dict):
                data["deployOperation"] = deploy_res
    return data if isinstance(data, dict) else {"result": data}


def list_workflows(csesidx: str = DEFAULT_CSESIDX) -> list[dict]:
    """Lists WORKFLOW_AGENT pipelines on IOH Agentspace with their Agent Flow Builder URLs."""
    agents = list_agents(include_skills=False, csesidx=csesidx)
    workflows: list[dict] = []
    for a in agents:
        raw_id = a.get("agent_id") or normalize_session_id(a.get("name", ""))
        # Check if agent is a workflow
        try:
            full_def = get_agent(raw_id, csesidx=csesidx, auto_refresh=False)
            ag = full_def.get("agent", full_def) if isinstance(full_def, dict) else {}
            if "workflowAgentDefinition" in ag or a.get("agent_type") == "WORKFLOW_AGENT":
                wf_def = ag.get("workflowAgentDefinition", {})
                flow = wf_def.get("agentFlow", {})
                nodes = flow.get("nodes", [])
                edges = flow.get("edges", [])
                builder_url = f"{ORIGIN}/home/cid/{WIDGET_CONFIG_ID}/r/agent-flow-builder/{raw_id}?csesidx={resolve_csesidx(csesidx)}"
                workflows.append({
                    "agent_id": raw_id,
                    "name": ag.get("name", a.get("name", "")),
                    "display_name": ag.get("displayName", a.get("display_name", "")),
                    "description": ag.get("description", a.get("description", "")),
                    "state": ag.get("state", a.get("state", "ENABLED")),
                    "nodes_count": len(nodes),
                    "edges_count": len(edges),
                    "builder_url": builder_url,
                })
        except Exception:
            continue
    return workflows


def build_netra_to_office_workflow_payload(
    workflow_id: str | None = "8458183310708652909",
    display_name: str = "Netra to Office File Creator Workflow",
) -> dict:
    """Constructs the complete, validated multi-agent branched WORKFLOW_AGENT JSON payload."""
    agent_id = normalize_session_id(workflow_id) if workflow_id and workflow_id != "new" else ""
    return {
        "name": agent_id,
        "displayName": display_name,
        "description": (
            "End-to-end multi-agent pipeline: Netra queries live IOH marts -> Human-in-the-loop approval -> "
            "Condition routing (PPTX vs XLSX) -> Office File Creator builds executive deliverables."
        ),
        "workflowAgentDefinition": {
            "triggerNodeId": "manual_trigger",
            "agentFlow": {
                "nodes": [
                    {
                        "id": "manual_trigger",
                        "displayName": "Manual Trigger (Topic & Format)",
                        "nodeType": "MANUAL_TRIGGER",
                        "manualTrigger": {},
                        "outputSchema": {
                            "properties": {
                                "analysis_topic": {
                                    "title": "Analysis Topic & Cohort",
                                    "description": "Specify the business question, cohort, metric, and date range for Netra to analyze (e.g., 90d CVM conversion and ARPU by brand).",
                                    "type": "STRING",
                                    "additionalProperties": {"display_order": 0},
                                },
                                "deliverable_format": {
                                    "title": "Deliverable Format (PPTX or XLSX)",
                                    "description": "Enter PPTX for an executive slide deck or XLSX for a multi-sheet Excel model.",
                                    "type": "STRING",
                                    "additionalProperties": {"display_order": 1},
                                },
                            },
                            "required": ["analysis_topic", "deliverable_format"],
                        },
                    },
                    {
                        "id": "netra_agent",
                        "displayName": "Netra Agent",
                        "nodeType": "AGENT_REFERENCE_NODE",
                        "agentReferenceNode": {
                            "agent": "17783079275007264980",
                            "agentReferenceType": "ADK_AGENT",
                            "inputParameters": {
                                "prompt": (
                                    "You are Netra Agent, the enterprise data coordinator for IOH. "
                                    "Query live IOH BigQuery marts and perform an exhaustive analysis on: ${manual_trigger.analysis_topic}.\n\n"
                                    "Target Deliverable Format requested by user: ${manual_trigger.deliverable_format}.\n\n"
                                    "You MUST structure your response with:\n"
                                    "1. Headline Executive Summary & Core Quantified Impact\n"
                                    "2. Complete Multi-Column Data Tables (every cohort, headcount, share %, revenue IDR T, and ARPU)\n"
                                    "3. Exact Native Chart Series (separating volume metrics from rate/ARPU percentages)\n"
                                    "4. Slide-by-Slide (for PPTX) or Sheet-by-Sheet (for XLSX) detailed outline with McKinsey action titles and commercial interpretation."
                                )
                            },
                        },
                    },
                    {
                        "id": "approval_step",
                        "displayName": "Review & Approve Netra Analysis",
                        "nodeType": "APPROVAL_NODE",
                        "approvalNode": {
                            "message": (
                                "Please review Netra Agent's extracted IOH metrics, tables, and outline before generating the "
                                "${manual_trigger.deliverable_format} deliverable:\n\n${netra_agent.output}"
                            )
                        },
                    },
                    {
                        "id": "format_condition",
                        "displayName": "Route by Deliverable Format (PPTX vs XLSX)",
                        "nodeType": "CONDITION_NODE",
                        "conditionNode": {
                            "ruleBasedRouting": {
                                "rules": [
                                    {
                                        "branch": "PPTX",
                                        "rule": {
                                            "rootExpression": {
                                                "logicalGroup": {
                                                    "logicalOperator": "AND",
                                                    "expressions": [
                                                        {
                                                            "condition": {
                                                                "left": {"variablePath": "manual_trigger.deliverable_format"},
                                                                "conditionOperator": "CONTAINS",
                                                                "right": {"literal": "PPTX"},
                                                            }
                                                        }
                                                    ],
                                                }
                                            }
                                        },
                                    }
                                ],
                                "elseBranch": "XLSX",
                            }
                        },
                    },
                    {
                        "id": "office_file_creator_pptx",
                        "displayName": "Office File Creator (Executive PPTX)",
                        "nodeType": "AGENT_NODE",
                        "agentNode": {
                            "model": "gemini-4-argon",
                            "instruction": (
                                "You are the Executive Presentation Specialist in the multi-agent workflow. "
                                "Using the Netra Agent analysis, structured slide outline, and tables below:\n\n"
                                "${netra_agent.output}\n\n"
                                "Topic requested: ${manual_trigger.analysis_topic}\n\n"
                                "Generate an executive McKinsey-grade PowerPoint presentation (.pptx) adhering to these rules:\n"
                                "1. Follow executive-slides and minimal-slides principles with single-line action titles (<85 chars stating the quantified business conclusion).\n"
                                "2. Use native editable charts (<c:chart>) separating rate (%) from volume (headcount/IDR) and structured data tables.\n"
                                "3. Execute python-pptx / pptx_lxml_wrapper in the sandbox to build the widescreen deck.\n"
                                "4. Upload the final .pptx file to OneDrive /Agentspace_Exports via onedrive_agent__upload_file."
                            ),
                            "outputDisplayEnabled": True,
                            "skillAgentNames": ["14950672669329422296"],
                        },
                    },
                    {
                        "id": "office_file_creator_xlsx",
                        "displayName": "Office File Creator (Analytical XLSX)",
                        "nodeType": "AGENT_NODE",
                        "agentNode": {
                            "model": "gemini-4-argon",
                            "instruction": (
                                "You are the Spreadsheet & Financial Modeling Specialist in the multi-agent workflow. "
                                "Using the Netra Agent cohorts, revenue numbers, ARPU, and metrics below:\n\n"
                                "${netra_agent.output}\n\n"
                                "Topic requested: ${manual_trigger.analysis_topic}\n\n"
                                "Generate a multi-sheet analytical Excel workbook (.xlsx) adhering to these rules:\n"
                                "1. Tab 1: Executive KPI Dashboard & Summary Matrix.\n"
                                "2. Tab 2: Detailed Cohort & Segment Breakdown with dynamic Excel formulas (SUM, AVERAGE, INDEX/MATCH, SUMIFS) and zero hardcoded totals.\n"
                                "3. Tab 3: Native Chart Data Series.\n"
                                "4. Build the workbook using openpyxl / WorkbookBuilder in memory and deliver via generate_document."
                            ),
                            "outputDisplayEnabled": True,
                            "skillAgentNames": ["14950672669329422296"],
                        },
                    },
                ],
                "edges": [
                    {"sourceNodeId": "manual_trigger", "targetNodeId": "netra_agent"},
                    {"sourceNodeId": "netra_agent", "targetNodeId": "approval_step"},
                    {"sourceNodeId": "approval_step", "targetNodeId": "format_condition"},
                    {"sourceNodeId": "format_condition", "targetNodeId": "office_file_creator_pptx", "routeString": "PPTX"},
                    {"sourceNodeId": "format_condition", "targetNodeId": "office_file_creator_xlsx", "routeString": "XLSX"},
                ],
            }
        },
    }


def upsert_netra_office_workflow(
    workflow_id: str = "8458183310708652909",
    csesidx: str = DEFAULT_CSESIDX,
) -> dict:
    """Updates (or creates if workflow_id == 'new') the Netra -> Office File Creator branched workflow."""
    agent_id = normalize_session_id(workflow_id)
    payload_agent = build_netra_to_office_workflow_payload(workflow_id=agent_id)
    if agent_id and agent_id != "new":
        payload = {
            "configId": WIDGET_CONFIG_ID,
            "additionalParams": {"token": "-", "origin": "AGENT_DESIGNER"},
            "updateAgentRequest": {
                "agent": payload_agent,
                "updateMask": "display_name,description,workflow_agent_definition.agent_flow,workflow_agent_definition.trigger_node_id",
            },
        }
        res, _ = _post_widget_rpc("widgetUpdateAgent", payload, csesidx=csesidx, timeout=60)
    else:
        payload = {
            "configId": WIDGET_CONFIG_ID,
            "additionalParams": {"token": "-", "origin": "AGENT_DESIGNER"},
            "createAgentRequest": {
                "agent": payload_agent,
            },
        }
        res, _ = _post_widget_rpc("widgetCreateAgent", payload, csesidx=csesidx, timeout=60)

    saved_ag = res.get("agent", res) if isinstance(res, dict) else {}
    target_id = normalize_session_id(saved_ag.get("name", agent_id))
    builder_url = f"{ORIGIN}/home/cid/{WIDGET_CONFIG_ID}/r/agent-flow-builder/{target_id}?csesidx={resolve_csesidx(csesidx)}"
    return {
        "agent": saved_ag,
        "workflow_id": target_id,
        "display_name": saved_ag.get("displayName", "Netra to Office File Creator Workflow"),
        "builder_url": builder_url,
    }


def download_session_media_files(
    session_id: str,
    file_ids: list[str] | None = None,
    session_tag: str | None = None,
    output_dir: str | None = None,
    prompt_slug: str | None = None,
    csesidx: str = DEFAULT_CSESIDX,
) -> list[dict]:
    """
    Downloads AI-generated or session-attached media files (.png, .jpg, .mp4, etc.) from an
    Agentspace session via `widgetListSessionFileMetadata` + `biz-discoveryengine.googleapis.com/...:downloadFile`.
    Costs ZERO Antigravity LLM tokens and ZERO personal API quota!
    """
    short_sess = normalize_session_id(session_id)
    full_name = format_delete_session_name(short_sess)
    meta_payload = {
        "configId": WIDGET_CONFIG_ID,
        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
        "listSessionFileMetadataRequest": {"name": full_name},
    }
    meta_resp, _ = _post_widget_rpc("widgetListSessionFileMetadata", meta_payload, csesidx=csesidx, timeout=30)
    file_meta_list = (
        meta_resp.get("listSessionFileMetadataResponse", {}).get("fileMetadata", [])
        if isinstance(meta_resp, dict)
        else []
    )
    if not file_meta_list:
        return []

    meta_by_id = {m.get("fileId"): m for m in file_meta_list if isinstance(m, dict) and m.get("fileId")}
    if file_ids:
        ordered_ids = [fid for fid in file_ids if fid in meta_by_id]
        if not ordered_ids:
            ordered_ids = list(meta_by_id.keys())
    else:
        ordered_ids = [
            m.get("fileId")
            for m in file_meta_list
            if isinstance(m, dict) and m.get("fileId") and m.get("fileOriginType") == "AI_GENERATED"
        ] or list(meta_by_id.keys())

    if output_dir:
        target_dir = os.path.abspath(output_dir)
    else:
        tag = _sanitize_slug(session_tag or os.environ.get("AGY_SESSION_TAG", "chat_default"), max_len=24)
        if not tag.startswith("chat_"):
            tag = f"chat_{tag}"
        target_dir = os.path.join(OUTPUTS_DIR, tag)
    os.makedirs(target_dir, exist_ok=True)

    def _make_dl_headers(curr_xsrf: dict) -> dict[str, str]:
        eff_cses = str(curr_xsrf.get("csesidx") or csesidx)
        hdrs = _build_browser_rpc_headers(make_jwt(curr_xsrf, csesidx=eff_cses))
        hdrs.pop("Content-Type", None)
        return hdrs

    xsrf, _ = load_xsrf()
    dl_headers = _make_dl_headers(xsrf)

    out_prefix = f"chat_{_sanitize_slug(session_tag, 16)}__" if session_tag else ""
    slug_part = f"__{_sanitize_slug(prompt_slug, 28)}" if prompt_slug else ""

    downloaded: list[dict] = []
    for idx, fid in enumerate(ordered_ids, start=1):
        meta = meta_by_id[fid]
        raw_uri = meta.get("downloadUri", "")
        if not raw_uri:
            raw_uri = (
                f"https://{HOST}/v1/{ENGINE_RESOURCE_NAME}/sessions/{short_sess}:downloadFile"
                f"?file_id={fid}&alt=media"
            )
        else:
            raw_uri = raw_uri.replace("https://discoveryengine.googleapis.com/", f"https://{HOST}/")

        mime_type = meta.get("mimeType", "application/octet-stream")
        orig_name = meta.get("name") or f"media_{fid[:8]}"
        _, ext = os.path.splitext(orig_name)
        if not ext:
            if "mp4" in mime_type:
                ext = ".mp4"
            elif "png" in mime_type:
                ext = ".png"
            elif "jpeg" in mime_type or "jpg" in mime_type:
                ext = ".jpg"
            else:
                ext = ".bin"

        media_kind = "video" if "video" in mime_type else ("image" if "image" in mime_type else "file")
        suffix_idx = f"_{idx}" if len(ordered_ids) > 1 else ""
        out_filename = f"{out_prefix}{short_sess}{slug_part}__{media_kind}{suffix_idx}{ext}"
        out_path = os.path.join(target_dir, out_filename)

        file_bytes = b""
        for dl_try in range(2):
            req = urllib.request.Request(raw_uri, headers=dl_headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    file_bytes = resp.read()
                break
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) and dl_try == 0:
                    xsrf, _ = refresh_xsrf_token(
                        csesidx=csesidx,
                        stale_key_id=str(xsrf.get("keyId") or "") or None,
                        min_saved_at=int(xsrf.get("savedAt") or 0) + 1,
                    )
                    dl_headers = _make_dl_headers(xsrf)
                    continue
                raise
        with open(out_path, "wb") as f:
            f.write(file_bytes)

        summary_obj = meta.get("fileSummary", {}) if isinstance(meta.get("fileSummary"), dict) else {}
        downloaded.append({
            "file_id": fid,
            "name": orig_name,
            "mime_type": mime_type,
            "media_type": media_kind,
            "path": out_path,
            "bytes": len(file_bytes),
            "summary": summary_obj.get("summary", ""),
        })
    return downloaded


def export_session_artifacts(
    session_id: str | None = None,
    artifact_id: str | None = None,
    formats: list[str] | tuple[str, ...] = ("pptx", "pdf"),
    session_tag: str | None = None,
    output_dir: str | None = None,
    csesidx: str = DEFAULT_CSESIDX,
    fallback_text: str | None = None,
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
            "skill:office-workflow-suite",
            "skill:office-workflow-suite:lxml",
            "agent:14950672669329422296",
            "agent:17216682253898748109",
            "model:gemini-4-argon:search=0",
        ):
            cached = get_reusable_session(session_tag, candidate_mode)
            if cached:
                short_sess = normalize_session_id(cached)
                break

    artifact_ids: list[str] = []
    sess_data: dict = {}
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

    native_lxml_exported: dict | None = None
    if sess_data or fallback_text:
        all_texts: list[str] = [fallback_text] if fallback_text else []
        all_code_blocks: list[str] = []
        b64_pptx_payloads: list[str] = []
        b64_office_payloads: list[tuple[str, str]] = []
        if fallback_text:
            for fmt_tag, m_b64 in re.findall(r"B64_(PPTX|XLSX|DOCX):([A-Za-z0-9+/=]+)", fallback_text):
                if len(m_b64) > 200:
                    b64_office_payloads.append((fmt_tag.lower(), m_b64))
                    if fmt_tag == "PPTX":
                        b64_pptx_payloads.append(m_b64)
        sess_obj = sess_data.get("session", sess_data) if isinstance(sess_data, dict) else {}
        for turn in sess_obj.get("turns", []):
            ans_text = turn.get("detailedAssistAnswer", {}).get("answerText", "")
            if ans_text:
                all_texts.append(ans_text)
            for rep in turn.get("detailedAssistAnswer", {}).get("replies", []):
                gc_content = rep.get("groundedContent", {}).get("content", {})
                t_str = gc_content.get("text", "")
                if t_str:
                    all_texts.append(t_str)
                exec_code = gc_content.get("executableCode", {}).get("code", "")
                if exec_code:
                    all_code_blocks.append(exec_code)
                    all_texts.append(f"```python\n{exec_code}\n```")
                code_out = gc_content.get("codeExecutionResult", {}).get("output", "")
                if code_out:
                    for fmt_tag, m_b64 in re.findall(r"B64_(PPTX|XLSX|DOCX):([A-Za-z0-9+/=]+)", code_out):
                        if len(m_b64) > 200:
                            b64_office_payloads.append((fmt_tag.lower(), m_b64))
                            if fmt_tag == "PPTX":
                                b64_pptx_payloads.append(m_b64)

        if output_dir:
            target_dir_nat = os.path.abspath(output_dir)
        else:
            tag_nat = _sanitize_slug(session_tag or os.environ.get("AGY_SESSION_TAG", "chat_default"), max_len=24)
            if not tag_nat.startswith("chat_"):
                tag_nat = f"chat_{tag_nat}"
            target_dir_nat = os.path.join(OUTPUTS_DIR, tag_nat)
        out_prefix_nat = f"chat_{_sanitize_slug(session_tag, 16)}__" if session_tag else ""
        out_path_nat = os.path.join(target_dir_nat, f"{out_prefix_nat}{short_sess}__native_pptx.pptx")

        if b64_office_payloads:
            try:
                os.makedirs(target_dir_nat, exist_ok=True)
                fmt_ext, last_b64 = b64_office_payloads[-1]
                out_path_fmt = os.path.join(target_dir_nat, f"{out_prefix_nat}{short_sess}__native_{fmt_ext}.{fmt_ext}")
                raw_bytes = base64.b64decode(last_b64)
                with open(out_path_fmt, "wb") as bf:
                    bf.write(raw_bytes)
                script_path_nat = os.path.splitext(out_path_fmt)[0] + "_builder.py"
                if all_code_blocks:
                    with open(script_path_nat, "w", encoding="utf-8") as sf:
                        sf.write(all_code_blocks[-1])
                items_cnt = 1
                if fmt_ext == "pptx":
                    from pptx import Presentation as _PrsCheck
                    items_cnt = len(_PrsCheck(out_path_fmt).slides)
                elif fmt_ext == "xlsx":
                    import zipfile
                    with zipfile.ZipFile(out_path_fmt, "r") as zf:
                        items_cnt = sum(1 for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
                native_lxml_exported = {
                    "path": out_path_fmt,
                    "bytes": len(raw_bytes),
                    "script_path": script_path_nat if all_code_blocks else None,
                    "slides_count": items_cnt,
                    "compiler": f"agentspace_bard_python_interpreter_{fmt_ext}",
                    "mime_type": EXPORT_MIME_TYPES.get(fmt_ext, "application/octet-stream"),
                }
            except Exception:
                native_lxml_exported = None

        if not native_lxml_exported and short_sess:
            try:
                dl_media = download_session_media_files(
                    session_id=short_sess,
                    session_tag=session_tag,
                    output_dir=target_dir_nat,
                    csesidx=csesidx,
                )
                import zipfile
                best_pptx_media = None
                for m_item in dl_media:
                    mp = m_item.get("path", "")
                    if mp and os.path.isfile(mp) and zipfile.is_zipfile(mp):
                        with zipfile.ZipFile(mp, "r") as zf:
                            if "ppt/presentation.xml" in zf.namelist():
                                if not best_pptx_media or m_item.get("bytes", 0) >= best_pptx_media.get("bytes", 0):
                                    best_pptx_media = m_item
                if best_pptx_media:
                    import shutil
                    shutil.copyfile(best_pptx_media["path"], out_path_nat)
                    with zipfile.ZipFile(out_path_nat, "r") as zf:
                        slides_cnt = sum(1 for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
                    native_lxml_exported = {
                        "path": out_path_nat,
                        "bytes": os.path.getsize(out_path_nat),
                        "script_path": None,
                        "slides_count": slides_cnt,
                        "compiler": "agentspace_session_media_pptx",
                        "mime_type": EXPORT_MIME_TYPES["pptx"],
                    }
            except Exception:
                pass

        combined_turn_text = "\n\n".join(all_texts)
        if not native_lxml_exported and ("create_widescreen_prs" in combined_turn_text or "from pptx" in combined_turn_text):
            try:
                import pptx_lxml_wrapper

                os.makedirs(target_dir_nat, exist_ok=True)
                lxml_res = pptx_lxml_wrapper.compile_python_pptx_from_response(
                    response_text=combined_turn_text,
                    out_pptx_path=out_path_nat,
                )
                native_lxml_exported = {
                    "path": lxml_res["pptx_path"],
                    "bytes": lxml_res["bytes"],
                    "script_path": lxml_res["script_path"],
                    "slides_count": lxml_res["slides_count"],
                    "mime_type": EXPORT_MIME_TYPES["pptx"],
                }
            except Exception as nat_err:
                if not artifact_ids:
                    raise RuntimeError(f"Failed to compile native python-pptx script in session {short_sess}: {nat_err}") from nat_err

    if not artifact_ids:
        if native_lxml_exported:
            return {
                "session_id": short_sess,
                "artifact_id": "native_python_pptx_lxml",
                "title": f"Native python-pptx Deck ({short_sess})",
                "slides_count": native_lxml_exported["slides_count"],
                "exported_files": {
                    "pptx_native": native_lxml_exported,
                },
            }

        raise ValueError(
            f"No immersive Canvas/Slides artifact or native python-pptx script found in session {short_sess or '(none)'}."
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

        if fmt_key == "pptx":
            slides_html_list = art_obj.get("slidesArtifact", {}).get("slides", [])
            out_prefix = f"chat_{_sanitize_slug(session_tag, 16)}__" if session_tag else ""
            out_filename = f"{out_prefix}{short_sess or target_artifact_id[:8]}__{slug_title}.{fmt_key}"
            out_path = os.path.join(target_dir, out_filename)
            if slides_html_list:
                try:
                    import dom_pptx_compiler

                    dom_pptx_compiler.compile_slides_html_to_pptx(slides_html_list, out_path)
                    dom_filename = f"{out_prefix}{short_sess or target_artifact_id[:8]}__{slug_title}__dom_compiled.pptx"
                    dom_path = os.path.join(target_dir, dom_filename)
                    if os.path.abspath(dom_path) != os.path.abspath(out_path):
                        with open(out_path, "rb") as src_f, open(dom_path, "wb") as dst_f:
                            dst_f.write(src_f.read())
                    dom_bytes = os.path.getsize(out_path)
                    exported_files["pptx"] = {
                        "path": out_path,
                        "bytes": dom_bytes,
                        "mime_type": mime_type,
                        "compiler": "html_tailwind_playwright_python_pptx_lxml",
                    }
                    exported_files["pptx_dom"] = {
                        "path": dom_path,
                        "bytes": dom_bytes,
                        "mime_type": mime_type,
                        "compiler": "html_tailwind_playwright_python_pptx_lxml",
                    }
                    continue
                except Exception:
                    pass

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

    if native_lxml_exported:
        exported_files["pptx_native"] = native_lxml_exported

    slides_count = len(art_obj.get("slidesArtifact", {}).get("slides", []))
    return {
        "session_id": short_sess,
        "artifact_id": target_artifact_id,
        "title": title,
        "slides_count": slides_count,
        "exported_files": exported_files,
    }


def watch_and_autocompile(
    interval_sec: int = 8,
    limit: int = 8,
    session_tag: str | None = None,
    once: bool = False,
    csesidx: str = DEFAULT_CSESIDX,
) -> list[dict]:
    """
    Zero-token background watcher that polls recent Agentspace sessions and automatically
    compiles any new or updated `default` (Canvas HTML -> Playwright DOM) or `native`
    (`python-pptx + lxml`) presentation sessions to `./outputs/`.
    """
    state_file = os.path.join(OUTPUTS_DIR, "watch_compiled_state.json")
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    compiled_state: dict[str, str] = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                compiled_state = json.load(f)
        except Exception:
            compiled_state = {}

    compiled_results: list[dict] = []
    print(
        f"[Agentspace Auto-Compiler Watcher] Watching latest {limit} sessions "
        f"(interval={interval_sec}s, once={once}, 0 LLM tokens)...",
        flush=True,
    )
    while True:
        try:
            sessions = list_sessions(limit=limit, csesidx=csesidx)
            for s in sessions:
                sess_id = s.get("session_id", "")
                if not sess_id:
                    continue
                sig = f"{s.get('start_time', '')}|{s.get('display_name', '')}"
                if compiled_state.get(sess_id) == sig:
                    continue
                try:
                    exp_res = export_session_artifacts(
                        session_id=sess_id,
                        formats=("pptx",),
                        session_tag=session_tag or "watched",
                        csesidx=csesidx,
                    )
                    compiled_state[sess_id] = sig
                    with open(state_file, "w", encoding="utf-8") as f:
                        json.dump(compiled_state, f, indent=2)
                    compiled_results.append(exp_res)
                    print(
                        f"  [AUTO-COMPILED] Session {sess_id} ('{exp_res['title']}', {exp_res['slides_count']} slides):",
                        flush=True,
                    )
                    for fmt_k, info in exp_res.get("exported_files", {}).items():
                        print(f"    -> [{fmt_k.upper()}] {info['path']} ({info['bytes']:,} bytes)", flush=True)
                except ValueError:
                    # Normal chat session without slides or native pptx code; mark seen so we don't re-fetch
                    compiled_state[sess_id] = sig
                    with open(state_file, "w", encoding="utf-8") as f:
                        json.dump(compiled_state, f, indent=2)
                except Exception as sess_err:
                    print(f"  [WARN] Session {sess_id} compile warning: {sess_err}", file=sys.stderr, flush=True)
        except KeyboardInterrupt:
            print("\n[Agentspace Auto-Compiler Watcher] Stopped.", flush=True)
            break
        except Exception as poll_err:
            print(f"[Watcher Poll Warning] {poll_err}", file=sys.stderr, flush=True)

        if once:
            break
        try:
            time.sleep(max(2, interval_sec))
        except KeyboardInterrupt:
            print("\n[Agentspace Auto-Compiler Watcher] Stopped.", flush=True)
            break

    return compiled_results


def serve_chrome_bridge(
    port: int = 18765,
    session_tag: str | None = None,
    csesidx: str = DEFAULT_CSESIDX,
) -> None:
    """
    Runs a local HTTP bridge server (`http://127.0.0.1:18765`) for the Agentspace Chrome Extension.
    Endpoints:
      - GET /health -> {"ok": true, "port": 18765}
      - GET /export?session=<session_id>&csesidx=<csesidx> -> Compiles the session via
        `python-pptx + lxml` (if native script present) or Playwright DOM compiler (if Canvas slides)
        and streams the resulting `.pptx` binary directly to Chrome Downloads!
    """
    import http.server
    import urllib.parse

    class BridgeHandler(http.server.BaseHTTPRequestHandler):
        def _send_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Expose-Headers", "Content-Disposition, X-PPTX-Compiler, X-PPTX-Slides")

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._send_cors_headers()
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/health":
                body = json.dumps({"ok": True, "port": port, "service": "agentspace-chrome-bridge"}).encode("utf-8")
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed.path == "/export":
                raw_sess = (qs.get("session", [""])[0] or "").strip()
                req_csesidx = (qs.get("csesidx", [csesidx])[0] or csesidx).strip()
                req_tag = (qs.get("tag", [session_tag or "chrome_ext"])[0] or "chrome_ext").strip()
                short_sess = normalize_session_id(raw_sess) if raw_sess else None

                try:
                    print(f"[Chrome Bridge] Compiling PPTX for session={short_sess or 'AUTO'} (csesidx={req_csesidx})...", flush=True)
                    exp_res = export_session_artifacts(
                        session_id=short_sess,
                        formats=("pptx",),
                        session_tag=req_tag,
                        csesidx=req_csesidx,
                    )
                    ef = exp_res.get("exported_files", {})
                    # Prefer native python-pptx + lxml if present, otherwise DOM-compiled pptx
                    chosen = ef.get("pptx_native") or ef.get("pptx_dom") or ef.get("pptx")
                    if not chosen or not os.path.isfile(chosen.get("path", "")):
                        raise RuntimeError(f"No compiled PPTX file produced for session {short_sess}")

                    pptx_path = chosen["path"]
                    compiler_type = "native_python_pptx_lxml" if "pptx_native" in ef else chosen.get("compiler", "dom_playwright_pptx")
                    filename = os.path.basename(pptx_path)
                    with open(pptx_path, "rb") as f:
                        pptx_bytes = f.read()

                    self.send_response(200)
                    self._send_cors_headers()
                    self.send_header("Content-Type", EXPORT_MIME_TYPES["pptx"])
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(len(pptx_bytes)))
                    self.send_header("X-PPTX-Compiler", compiler_type)
                    self.send_header("X-PPTX-Slides", str(exp_res.get("slides_count", 0)))
                    self.end_headers()
                    self.wfile.write(pptx_bytes)
                    print(f"[Chrome Bridge] -> Sent {filename} ({len(pptx_bytes):,} bytes, compiler={compiler_type})", flush=True)
                except Exception as exc:
                    err_msg = str(exc)
                    print(f"[Chrome Bridge ERROR] {err_msg}", file=sys.stderr, flush=True)
                    err_body = json.dumps({"ok": False, "error": err_msg, "session": short_sess}).encode("utf-8")
                    self.send_response(400)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(err_body)))
                    self.end_headers()
                    self.wfile.write(err_body)
                return

            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

        def log_message(self, format: str, *args) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), BridgeHandler)
    print(
        f"[Agentspace Chrome Bridge] Listening on http://127.0.0.1:{port} "
        f"(Ready for '⬇ Native PPTX' clicks in Google Chrome!)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Agentspace Chrome Bridge] Stopped.", flush=True)
    finally:
        server.server_close()


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
    with _FileLock(REFRESH_LOCK_PATH, blocking=True, timeout_sec=150), sync_playwright() as p:
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

    with _FileLock(os.path.join(session_dir, ".path_alloc.lock"), blocking=True, timeout_sec=5):
        seq = 1
        while True:
            sfx = "" if seq == 1 else f"_{seq}"
            filename = f"{tag}__{ts}__{short_as_id}__{slug}{sfx}{ext}"
            candidate = os.path.join(session_dir, filename)
            try:
                fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.close(fd)
                return candidate
            except FileExistsError:
                seq += 1
_ADVISOR_IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".auth_profile",
    "outputs", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
}
_ADVISOR_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".tar",
    ".gz", ".mp4", ".mp3", ".wav", ".pptx", ".xlsx", ".docx", ".pyc", ".so",
    ".dylib", ".dll", ".exe", ".bin", ".woff", ".woff2", ".ttf",
}

ADVISOR_SYSTEM_PREAMBLE = (
    "You are acting as the **Senior Architect & Planner** for a smaller local Executor model "
    "(e.g., Hydrogen or Flash Medium/High).\n"
    "Produce a crisp, unambiguous **Implementation Manifest** and end every advisory turn with a "
    "compact `<antigravity_spec>` block containing:\n"
    "1. **Exact target file paths & line/function targets**.\n"
    "2. **Exact SQL/Python logic changes or schema contracts** (precise diffs or replacement instructions).\n"
    "3. **Edge cases & invariants** to preserve.\n"
    "4. **Exact verification commands** (tests, syntax checks, dry-runs with `--tb=short` / `-q`).\n"
    "CRITICAL: If you need additional files, schemas, or command outputs before finalizing the spec, "
    "do NOT guess — list the exact paths or commands under a `[NEED_CONTEXT]` section and stop."
)


def _expand_input_paths(
    paths: list[str],
    cwd: str | None = None,
    max_files: int = 40,
    max_total_bytes: int = 300_000,
) -> list[tuple[str, str]]:
    """Expand file paths, directories, and glob patterns into (abs_path, display_rel_path) tuples."""
    import glob as _glob

    base_dir = os.path.abspath(cwd or os.getcwd())
    collected: list[str] = []
    seen: set[str] = set()

    def _add_file(p: str) -> None:
        ap = os.path.abspath(p)
        if ap in seen or not os.path.isfile(ap):
            return
        ext = os.path.splitext(ap)[1].lower()
        if ext in _ADVISOR_BINARY_EXTS:
            return
        seen.add(ap)
        collected.append(ap)

    for raw in paths:
        candidate = raw if os.path.isabs(raw) else os.path.join(base_dir, raw)
        if any(ch in raw for ch in ("*", "?", "[")):
            for m in sorted(_glob.glob(candidate, recursive=True)):
                if os.path.isfile(m):
                    _add_file(m)
        elif os.path.isdir(candidate):
            for root, dirs, files in os.walk(candidate):
                dirs[:] = sorted(d for d in dirs if d not in _ADVISOR_IGNORED_DIRS and not d.startswith("."))
                for fn in sorted(files):
                    if len(collected) >= max_files:
                        break
                    _add_file(os.path.join(root, fn))
                if len(collected) >= max_files:
                    break
        elif os.path.isfile(candidate):
            _add_file(candidate)
        else:
            raise FileNotFoundError(f"Input path not found: {candidate}")

    result: list[tuple[str, str]] = []
    total_bytes = 0
    for ap in collected[:max_files]:
        size = os.path.getsize(ap)
        if total_bytes + size > max_total_bytes and result:
            break
        total_bytes += size
        try:
            rel = os.path.relpath(ap, base_dir)
            display = rel if not rel.startswith("..") else os.path.basename(ap)
        except ValueError:
            display = os.path.basename(ap)
        result.append((ap, display))
    return result


def _build_repo_tree(cwd: str | None = None, max_entries: int = 200) -> str:
    """Build a compact file list of the workspace for Advisor context."""
    base_dir = os.path.abspath(cwd or os.getcwd())
    entries: list[str] = []
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            entries = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    except Exception:
        entries = []

    if not entries:
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = sorted(d for d in dirs if d not in _ADVISOR_IGNORED_DIRS and not d.startswith("."))
            for fn in sorted(files):
                rel = os.path.relpath(os.path.join(root, fn), base_dir)
                entries.append(rel)
                if len(entries) >= max_entries:
                    break
            if len(entries) >= max_entries:
                break

    truncated = len(entries) > max_entries
    shown = entries[:max_entries]
    header = f"--- REPO FILE TREE ({base_dir}, {len(shown)}/{len(entries)} files) ---"
    body = "\n".join(shown)
    if truncated:
        body += f"\n... ({len(entries) - max_entries} more files omitted)"
    return f"{header}\n{body}\n--- END REPO FILE TREE ---"


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
    python_pptx: bool = False,
    max_media_prompts: int = DEFAULT_MAX_MEDIA_PROMPTS,
    csesidx: str = DEFAULT_CSESIDX,
    include_tree: bool = False,
    advise_mode: bool = False,
    cwd: str | None = None,
) -> dict:
    with contextlib.ExitStack() as stack:
        return _ask_agentspace_inner(
            prompt=prompt,
            model_id=model_id,
            thinking_level=thinking_level,
            session=session,
            enable_search=enable_search,
            agent=agent,
            delete_session_after=delete_session_after,
            input_files=input_files,
            save_output=save_output,
            output_filename=output_filename,
            session_tag=session_tag,
            new_session=new_session,
            python_pptx=python_pptx,
            max_media_prompts=max_media_prompts,
            csesidx=csesidx,
            include_tree=include_tree,
            advise_mode=advise_mode,
            cwd=cwd,
            _exit_stack=stack,
        )


def _ask_agentspace_inner(
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
    python_pptx: bool = False,
    max_media_prompts: int = DEFAULT_MAX_MEDIA_PROMPTS,
    csesidx: str = DEFAULT_CSESIDX,
    include_tree: bool = False,
    advise_mode: bool = False,
    cwd: str | None = None,
    _exit_stack: contextlib.ExitStack | None = None,
) -> dict:
    if python_pptx and not agent:
        agent = "office-workflow-suite"
    resolved_agent = resolve_agent_id(agent)
    skill_name = SKILL_AGENT_IDS.get(resolved_agent) if resolved_agent else None
    is_media_prompt = (not resolved_agent and not skill_name and is_media_generation_prompt(prompt))
    effective_state_tag = _normalize_media_base_tag(session_tag) if is_media_prompt else session_tag
    mode_key = (
        f"skill:{skill_name}:lxml"
        if (skill_name and python_pptx)
        else (
            f"skill:{skill_name}"
            if skill_name
            else (
                f"agent:{resolved_agent}"
                if resolved_agent
                else (
                    f"model:{model_id}:media"
                    if is_media_prompt
                    else f"model:{model_id}:search={int(bool(enable_search))}"
                )
            )
        )
    )

    effective_session = session
    reused_existing_session = False
    isolated_from_busy_session = False
    rotated_previous_media_session: str | None = None
    if not effective_session and effective_state_tag and not new_session and not delete_session_after:
        cached_sess = get_reusable_session(effective_state_tag, mode_key)
        if cached_sess:
            prev_count = get_session_prompt_count(effective_state_tag, mode_key)
            if is_media_prompt and max_media_prompts > 0 and prev_count >= max_media_prompts:
                try:
                    delete_session(cached_sess, csesidx=csesidx)
                    rotated_previous_media_session = normalize_session_id(cached_sess)
                except Exception:
                    pass
                clear_reusable_session(effective_state_tag, mode_key, deleted_session_id=cached_sess)
                cached_sess = None
            if cached_sess and _exit_stack is not None:
                short_cached = normalize_session_id(cached_sess)
                inflight_path = os.path.join(OUTPUTS_DIR, f".inflight_sess_{short_cached}.lock")
                try:
                    _exit_stack.enter_context(_FileLock(inflight_path, blocking=False))
                except BlockingIOError:
                    print(
                        f"[Agentspace Concurrency] Session {short_cached} is busy in a parallel subagent; spawning isolated session.",
                        file=sys.stderr,
                    )
                    cached_sess = None
                    isolated_from_busy_session = True
            if cached_sess:
                effective_session = format_delete_session_name(cached_sess)
                reused_existing_session = True
    elif effective_session:
        effective_session = format_delete_session_name(effective_session)
        reused_existing_session = True

    full_prompt = prompt
    if python_pptx:
        import pptx_lxml_wrapper

        full_prompt = f"{pptx_lxml_wrapper.PYTHON_PPTX_PROMPT_PREFIX}{full_prompt}"
    if skill_name and f"mention://?uri={resolved_agent}" not in full_prompt:
        mention_pill = f"[{skill_name}](mention://?uri={resolved_agent})"
        if python_pptx:
            full_prompt = (
                f"{mention_pill} First call `load_skill` for `{skill_name}` and follow its V2.0 instructions:\n\n{full_prompt}"
            )
        else:
            full_prompt = (
                f"{mention_pill} {full_prompt}"
            )

    if advise_mode:
        full_prompt = f"{ADVISOR_SYSTEM_PREAMBLE}\n\n--- TASK ---\n{full_prompt}"

    context_blocks: list[str] = []
    if include_tree:
        context_blocks.append(_build_repo_tree(cwd=cwd))

    attached_files: list[str] = []
    if input_files:
        expanded = _expand_input_paths(input_files, cwd=cwd)
        for abs_fp, display_path in expanded:
            with open(abs_fp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            attached_files.append(abs_fp)
            context_blocks.append(f"--- BEGIN FILE: {display_path} ---\n{content}\n--- END FILE: {display_path} ---")

    if context_blocks:
        full_prompt = f"{full_prompt}\n\n" + "\n\n".join(context_blocks)

    stream_req: dict = {
        "query": {"parts": [{"text": full_prompt}]},
    }

    if effective_session:
        stream_req["session"] = effective_session

    onedrive_ds_specs = [
        {
            "dataStore": "collections/default_collection/dataStores/onedrive-federated-live_1776136353357_file"
        }
    ]
    if resolved_agent and not skill_name:
        stream_req["answerGenerationMode"] = "AGENT"
        stream_req["agentsSpec"] = {
            "agentSpecs": [{"agentId": resolved_agent}]
        }
        stream_req["toolsSpec"] = {
            "vertexAiSearchSpec": {"dataStoreSpecs": onedrive_ds_specs},
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
        if enable_search or skill_name or ("onedrive" in full_prompt.lower()):
            stream_req["toolsSpec"] = {
                "vertexAiSearchSpec": {"dataStoreSpecs": onedrive_ds_specs},
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

    timeout_sec = DEFAULT_STREAM_TIMEOUT
    chunks: list | dict = []
    xsrf_path = ""
    for rpc_try in range(3):
        chunks, xsrf_path = _post_widget_rpc("widgetStreamAssist", payload, csesidx=csesidx, timeout=timeout_sec)
        stream_err = None
        if isinstance(chunks, list):
            for ch in chunks:
                if isinstance(ch, dict) and "error" in ch:
                    stream_err = ch["error"]
                    break
        if stream_err and rpc_try < 2:
            err_reason = ""
            for det in stream_err.get("details", []):
                if isinstance(det, dict) and det.get("reason"):
                    err_reason = det["reason"]
                    break
            wait_s = 5 * (rpc_try + 1)
            print(
                f"[Agentspace Stream Error: {err_reason or stream_err.get('status') or stream_err.get('code')} "
                f"(attempt {rpc_try + 1}/3). Retrying in {wait_s}s...]",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(wait_s)
            continue
        break

    # Automatically confirm connector actionInvocation turns (e.g. onedrive_agent__upload_file)
    for _confirm_step in range(3):
        if not isinstance(chunks, list):
            break
        pending_action = None
        last_answer_name = None
        curr_sess = effective_session
        for ch in chunks:
            sar = ch.get("streamAssistResponse", {}) if isinstance(ch, dict) else {}
            if sar.get("sessionInfo", {}).get("session"):
                curr_sess = sar["sessionInfo"]["session"]
            ans = sar.get("answer", {})
            if ans.get("name"):
                last_answer_name = ans["name"]
            for rep in ans.get("replies", []):
                if "actionInvocation" in rep and rep["actionInvocation"].get("invocationId"):
                    pending_action = rep["actionInvocation"]
        if not pending_action and curr_sess and _confirm_step == 0:
            try:
                sess_check, _ = _post_widget_rpc(
                    "widgetGetSession",
                    {
                        "configId": WIDGET_CONFIG_ID,
                        "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
                        "getSessionRequest": {
                            "name": normalize_session_id(curr_sess),
                            "includeAnswerDetails": True,
                        },
                    },
                    csesidx=csesidx,
                )
                turns = sess_check.get("session", {}).get("turns", []) if isinstance(sess_check, dict) else []
                if turns:
                    lturn = turns[-1]
                    if lturn.get("assistAnswer"):
                        last_answer_name = lturn["assistAnswer"]
                    lreps = lturn.get("detailedAssistAnswer", {}).get("replies", [])
                    if lreps and "actionInvocation" in lreps[-1]:
                        pending_action = lreps[-1]["actionInvocation"]
            except Exception:
                pass
        if not pending_action or not curr_sess:
            break
        action_args = dict(pending_action.get("args", {}) or {})
        if pending_action.get("actionName") == "onedrive_agent__upload_file":
            env_drive_id = os.environ.get("AGENTSPACE_ONEDRIVE_DRIVE_ID", "").strip()
            env_parent_id = os.environ.get("AGENTSPACE_ONEDRIVE_PARENT_ID", "").strip()
            if env_drive_id:
                action_args.setdefault("driveId", env_drive_id)
            action_args.setdefault(
                "DriveName",
                os.environ.get("AGENTSPACE_ONEDRIVE_DRIVE_NAME", "OneDrive - Indosat Ooredoo Hutchison"),
            )
            if env_parent_id:
                action_args.setdefault("ParentId", env_parent_id)
            action_args.setdefault(
                "ParentName",
                os.environ.get("AGENTSPACE_ONEDRIVE_FOLDER_NAME", "Agentspace_Exports"),
            )
            action_args.setdefault("FileName", "presentation.pptx")
            action_args.setdefault("InputFileName", action_args["FileName"])
            if str(action_args.get("InputFileName", "")).endswith(".txt") and not action_args.get("ContentBytes"):
                action_args["HasBytes"] = False
                action_args["ContentBytes"] = ""
            else:
                action_args["HasBytes"] = True
                raw_b64_matches = re.findall(r"B64_(?:PPTX|XLSX|DOCX):([A-Za-z0-9+/=]{200,})", json.dumps(chunks))
                if raw_b64_matches:
                    action_args["ContentBytes"] = raw_b64_matches[-1]
        confirm_req = {
            "session": curr_sess,
            "query": {"parts": [{"text": "Action Confirmed"}]},
            "assistSkippingMode": 1,
            "answerGenerationMode": stream_req["answerGenerationMode"],
            "toolsSpec": stream_req["toolsSpec"],
            "actionExecutionParams": {
                "agentName": pending_action.get("agentName", "root_agent"),
                "actionName": pending_action.get("actionName", ""),
                "actionInvocationId": pending_action.get("invocationId", ""),
                "assistAnswerName": last_answer_name,
                "args": action_args,
            },
        }
        if "agentsSpec" in stream_req:
            confirm_req["agentsSpec"] = stream_req["agentsSpec"]
        if "assistGenerationConfig" in stream_req:
            confirm_req["assistGenerationConfig"] = stream_req["assistGenerationConfig"]
        confirm_payload = {
            "configId": WIDGET_CONFIG_ID,
            "additionalParams": {"token": "-", "origin": "ORIGIN_UNSPECIFIED"},
            "streamAssistRequest": confirm_req,
        }
        more_chunks, _ = _post_widget_rpc("widgetStreamAssist", confirm_payload, csesidx=csesidx, timeout=timeout_sec)
        if isinstance(more_chunks, list):
            for ch in chunks:
                sar = ch.get("streamAssistResponse", {}) if isinstance(ch, dict) else {}
                for rep in sar.get("answer", {}).get("replies", []):
                    if "actionInvocation" in rep:
                        rep.pop("actionInvocation", None)
            chunks.extend(more_chunks)
        else:
            break

    text_parts = []
    thoughts = []
    function_calls = []
    stream_errors: list[dict] = []
    final_media_file_ids: list[str] = []
    all_media_file_ids: list[str] = []
    has_immersive_artifact = False
    session_name = effective_session

    if isinstance(chunks, list):
        for chunk in chunks:
            if isinstance(chunk, dict) and "error" in chunk:
                stream_errors.append(chunk["error"])
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
                if "file" in content and isinstance(content["file"], dict):
                    fid = content["file"].get("fileId")
                    if fid:
                        if fid not in all_media_file_ids:
                            all_media_file_ids.append(fid)
                        if not content.get("thought") and fid not in final_media_file_ids:
                            final_media_file_ids.append(fid)
                if "functionCall" in content:
                    fname = content["functionCall"].get("name") or content["functionCall"].get("functionName", "unknown")
                    function_calls.append(fname)
                    if fname == "save_slides_to_artifact":
                        has_immersive_artifact = True
                if "executableCode" in content:
                    exec_c = content["executableCode"].get("code", "")
                    if exec_c:
                        text_parts.append(f"\n```python\n{exec_c}\n```\n")
                if "codeExecutionResult" in content:
                    c_out = content["codeExecutionResult"].get("output", "")
                    if any(k in c_out for k in ("B64_PPTX:", "B64_XLSX:", "B64_DOCX:", "[QA_GATE_PASSED]")):
                        text_parts.append(f"\n{c_out}\n")
                if content.get("thought"):
                    if "text" in content:
                        thoughts.append(content["text"])
                elif "text" in content:
                    text_parts.append(content["text"])

    target_media_ids = final_media_file_ids or all_media_file_ids
    generated_media: list[dict] = []
    if session_name and target_media_ids:
        try:
            generated_media = download_session_media_files(
                session_id=session_name,
                file_ids=target_media_ids,
                session_tag=session_tag,
                prompt_slug=output_filename or prompt,
                csesidx=csesidx,
            )
        except Exception:
            generated_media = []

    session_deleted = False
    session_auto_cleared_reason = None
    media_prompt_count = 0
    display_name = None
    has_video_media = any(m.get("media_type") == "video" for m in generated_media)
    # Only treat as an AI image/video generator session if the prompt itself is a pure media generation prompt
    # (never if an analytical/Netra/chart/code-execution query produced a visualization chart image)
    is_media_turn = bool(
        not resolved_agent
        and not skill_name
        and (is_media_prompt or (has_video_media and not _DATA_VIZ_EXCLUDE_RE.search(prompt or "")))
    )
    if delete_session_after and session_name:
        try:
            delete_session(session_name, csesidx=csesidx)
            session_deleted = True
            session_auto_cleared_reason = "ephemeral"
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
        state_tag_to_save = (_normalize_media_base_tag(session_tag) if is_media_turn else session_tag) or session_tag
        save_mode_key = (
            f"model:{model_id}:media"
            if (is_media_turn and not resolved_agent and not skill_name)
            else mode_key
        )
        if state_tag_to_save:
            media_prompt_count = save_reusable_session(
                session_tag=state_tag_to_save,
                mode_key=save_mode_key,
                session_name=session_name,
                display_name=display_name,
                is_media=is_media_turn,
                update_active_slot=not isolated_from_busy_session,
            )
            if is_media_turn and max_media_prompts > 0 and media_prompt_count >= max_media_prompts:
                try:
                    delete_session(session_name, csesidx=csesidx)
                    session_deleted = True
                    session_auto_cleared_reason = f"media_quota_reached ({media_prompt_count}/{max_media_prompts})"
                    clear_reusable_session(
                        state_tag_to_save,
                        save_mode_key,
                        deleted_session_id=session_name,
                    )
                except Exception:
                    pass

    final_text = "".join(text_parts).strip()
    saved_output_path = None
    if save_output or output_filename or python_pptx:
        alloc_filename = output_filename or ("lxml_deck__python_pptx_lxml.pptx" if python_pptx else None)
        saved_output_path = build_scoped_output_path(
            prompt=prompt,
            session_tag=session_tag,
            output_filename=alloc_filename,
            agentspace_session_id=session_name,
        )
        if not python_pptx or (output_filename and not output_filename.lower().endswith(".pptx")):
            with open(saved_output_path, "w", encoding="utf-8") as f:
                f.write(final_text)

    exported_artifacts = None
    if python_pptx and final_text:
        try:
            import pptx_lxml_wrapper

            if saved_output_path and saved_output_path.lower().endswith(".pptx"):
                target_pptx = saved_output_path
            else:
                target_pptx = build_scoped_output_path(
                    prompt=prompt,
                    session_tag=session_tag,
                    output_filename="lxml_deck__python_pptx_lxml.pptx",
                    agentspace_session_id=session_name,
                )

            lxml_res = pptx_lxml_wrapper.compile_python_pptx_from_response(
                response_text=final_text,
                out_pptx_path=target_pptx,
            )
            exported_artifacts = {
                "session_id": normalize_session_id(session_name) if session_name else "",
                "artifact_id": "python_pptx_lxml",
                "title": "python-pptx + lxml Native Deck",
                "slides_count": lxml_res["slides_count"],
                "exported_files": {
                    "pptx_lxml": {
                        "format": "pptx",
                        "path": lxml_res["pptx_path"],
                        "bytes": lxml_res["bytes"],
                        "script_path": lxml_res["script_path"],
                    }
                },
            }
            saved_output_path = lxml_res["script_path"]
        except Exception as exc:
            exported_artifacts = {"error": str(exc)}
    elif session_name and not session_deleted and (has_immersive_artifact or resolved_agent in SLIDES_AGENT_IDS):
        try:
            exported_artifacts = export_session_artifacts(
                session_id=session_name,
                formats=("pptx",),
                session_tag=session_tag,
                csesidx=csesidx,
                fallback_text=final_text,
            )
        except Exception:
            exported_artifacts = None

    return {
        "text": final_text,
        "thoughts": "".join(thoughts).strip(),
        "function_calls": function_calls,
        "generated_media": generated_media,
        "session": session_name,
        "session_reused": reused_existing_session,
        "session_display_name": display_name,
        "session_deleted": session_deleted,
        "session_auto_cleared_reason": session_auto_cleared_reason,
        "rotated_previous_media_session": rotated_previous_media_session,
        "media_prompt_count": media_prompt_count if is_media_turn else None,
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
    parser.add_argument(
        "--pptx-mode",
        choices=["default", "native"],
        default=None,
        help="Presentation mode: 'default' (HTML/Tailwind Canvas -> Playwright DOM .pptx) or 'native' (python-pptx + lxml script -> .pptx)",
    )
    parser.add_argument(
        "--native-pptx",
        "--python-pptx",
        "--pptx-lxml",
        dest="python_pptx",
        action="store_true",
        help="Use 'native' pptx mode: ask Agentspace (gemini-4-argon + office-workflow-suite) for a python-pptx + lxml script and compile it locally to .pptx at 0 AGY coding tokens",
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
        help="Attach a local file, directory, or glob pattern directly from disk into the prompt (can be specified multiple times)",
    )
    parser.add_argument(
        "--advise",
        action="store_true",
        help="Advisor Planner Mode: use gemini-4-carbon + HIGH thinking, attach repo tree, inject Implementation Manifest framing, and save to advisor_plan.md (--summary-only)",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Attach a compact repository file tree to the prompt",
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
        "--finish-task",
        nargs="?",
        const="AUTO",
        default=None,
        metavar="SESSION_TAG",
        help="Delete tracked media sessions (and any _img*/_vid* sub-sessions) for a finished subagent/task (--session-tag) and exit",
    )
    parser.add_argument(
        "--finish-all-sessions",
        action="store_true",
        help="When used with --finish-task, delete all tracked sessions for that tag (not just media sessions)",
    )
    parser.add_argument(
        "--cleanup-media-sessions",
        action="store_true",
        help="Scan recent Agentspace sessions and delete image/video generation chat sessions to declutter the Web UI",
    )
    parser.add_argument(
        "--keep-latest-media",
        type=int,
        default=0,
        help="Number of most recent media sessions to keep when running --cleanup-media-sessions (default: 0)",
    )
    parser.add_argument(
        "--max-media-prompts",
        type=int,
        default=DEFAULT_MAX_MEDIA_PROMPTS,
        help=f"Auto-clear/rotate media generation session after N prompts (default: {DEFAULT_MAX_MEDIA_PROMPTS}; 0 disables auto-clear)",
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
        "--download-media",
        default=None,
        metavar="SESSION_ID",
        help="Download AI-generated or attached media files (.png, .mp4) from an Agentspace session and exit",
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
        "--list-workflows",
        action="store_true",
        help="List WORKFLOW_AGENT pipelines on Agentspace with their Agent Flow Builder URLs and exit",
    )
    parser.add_argument(
        "--sync-netra-workflow",
        nargs="?",
        const="8458183310708652909",
        default=None,
        metavar="WORKFLOW_ID",
        help="Deploy/update the Netra -> Office File Creator branched multi-agent workflow (default ID: 8458183310708652909) and exit",
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
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run zero-token background auto-compiler watcher that polls recent Web UI sessions and compiles native/DOM .pptx files",
    )
    parser.add_argument(
        "--watch-once",
        action="store_true",
        help="Run a single pass of the auto-compiler watcher on recent sessions and exit",
    )
    parser.add_argument(
        "--watch-interval",
        type=int,
        default=8,
        help="Polling interval in seconds for --watch (default: 8)",
    )
    parser.add_argument(
        "--serve-chrome",
        "--serve",
        dest="serve_chrome",
        action="store_true",
        help="Start local HTTP bridge on http://127.0.0.1:18765 for the Agentspace Chrome Extension ('⬇ Native PPTX' button)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=18765,
        help="Local port for --serve-chrome (default: 18765)",
    )
    parser.add_argument("--limit", type=int, default=20, help="Number of sessions to list with --list-sessions")
    parser.add_argument("--csesidx", default=DEFAULT_CSESIDX, help="Browser session index (csesidx) from URL")
    parser.add_argument("--search", action="store_true", help="Enable Enterprise Search (Confluence/SharePoint/Jira) & Web Grounding")
    parser.add_argument("--json", action="store_true", help="Output full JSON response")
    args = parser.parse_args()

    try:
        if args.serve_chrome:
            serve_chrome_bridge(
                port=args.port,
                session_tag=args.session_tag,
                csesidx=args.csesidx,
            )
            return
        if args.watch or args.watch_once:
            watch_res = watch_and_autocompile(
                interval_sec=args.watch_interval,
                limit=min(args.limit, 10),
                session_tag=args.session_tag,
                once=args.watch_once,
                csesidx=args.csesidx,
            )
            if args.json:
                print(json.dumps(watch_res, indent=2))
            return
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

        if args.list_workflows:
            workflows = list_workflows(csesidx=args.csesidx)
            if args.json:
                print(json.dumps(workflows, indent=2))
            else:
                print(f"Found {len(workflows)} WORKFLOW_AGENT pipeline(s) on Agentspace:")
                for w in workflows:
                    print(f"\n[{w['agent_id']}] {w['display_name']} (state={w['state']}, nodes={w['nodes_count']}, edges={w['edges_count']})")
                    print(f"  Description: {w['description']}")
                    print(f"  Builder Canvas URL: {w['builder_url']}")
            return

        if args.sync_netra_workflow is not None:
            sync_res = upsert_netra_office_workflow(workflow_id=args.sync_netra_workflow, csesidx=args.csesidx)
            if args.json:
                print(json.dumps(sync_res, indent=2))
            else:
                ag = sync_res.get("agent", {})
                flow = ag.get("workflowAgentDefinition", {}).get("agentFlow", {})
                print(
                    f"Successfully synced workflow: {ag.get('displayName')} ({normalize_session_id(ag.get('name', ''))})\n"
                    f"  Nodes: {len(flow.get('nodes', []))} | Edges: {len(flow.get('edges', []))}\n"
                    f"  Canvas URL: {ORIGIN}/home/cid/{WIDGET_CONFIG_ID}/r/agent-flow-builder/{normalize_session_id(ag.get('name', ''))}?csesidx={resolve_csesidx(args.csesidx)}"
                )
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

        if args.finish_task:
            target_tag = args.session_tag if args.finish_task == "AUTO" else args.finish_task
            if not target_tag:
                parser.error("--finish-task requires either a SESSION_TAG argument or --session-tag.")
            fin_res = finish_task_sessions(
                session_tag=target_tag,
                media_only=not args.finish_all_sessions,
                csesidx=args.csesidx,
            )
            if args.json:
                print(json.dumps(fin_res, indent=2))
            else:
                print(
                    f"Finished task cleanup for tag '{fin_res['base_session_tag']}' "
                    f"(media_only={fin_res['media_only']}): deleted {fin_res['deleted_count']} session(s)."
                )
                for sid in fin_res["deleted_sessions"]:
                    print(f"  - Deleted session: {sid}")
                for fail in fin_res["failed"]:
                    print(f"  - Failed ({fail['session_id']}): {fail['error']}", file=sys.stderr)
            return

        if args.cleanup_media_sessions:
            clean_res = cleanup_media_sessions(
                limit=max(args.limit, 50),
                keep_latest=args.keep_latest_media,
                csesidx=args.csesidx,
            )
            if args.json:
                print(json.dumps(clean_res, indent=2))
            else:
                print(
                    f"Media session cleanup: scanned {clean_res['scanned']} session(s), "
                    f"matched {clean_res['matched_media_sessions']}, deleted {clean_res['deleted_count']}."
                )
                for d in clean_res["deleted"]:
                    print(f"  - Deleted [{d['session_id']}] {d.get('display_name') or d.get('first_query')}")
                for err in clean_res["errors"]:
                    print(f"  - Error [{err['session_id']}]: {err['error']}", file=sys.stderr)
            return

        if args.download_media and not args.prompt:
            dl_files = download_session_media_files(
                session_id=args.download_media,
                session_tag=args.session_tag,
                prompt_slug=args.output_filename,
                csesidx=args.csesidx,
            )
            if args.json:
                print(json.dumps(dl_files, indent=2))
            else:
                print(f"Downloaded {len(dl_files)} media file(s) from session {normalize_session_id(args.download_media)}:")
                for m in dl_files:
                    print(f"  [{m['media_type'].upper()} | {m['mime_type']}] {m['path']} ({m['bytes']:,} bytes)")
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
            parser.error(
                "A prompt is required unless --list-sessions, --list-agents, --list-workflows, "
                "--sync-netra-workflow, --get-agent, --update-agent-file, --delete-session, --finish-task, "
                "--cleanup-media-sessions, --export-slides, or --download-media is specified."
            )

        use_native_pptx = bool(args.python_pptx or (args.pptx_mode and args.pptx_mode.lower() == "native"))
        if args.pptx_mode and args.pptx_mode.lower() == "default" and not args.agent:
            args.agent = "office-workflow-suite"

        effective_model = "gemini-4-carbon" if (args.advise and args.model == DEFAULT_MODEL) else args.model
        effective_thinking = "HIGH" if (args.advise and args.thinking == DEFAULT_THINKING) else args.thinking
        effective_output = args.output_filename or ("advisor_plan.md" if args.advise else None)
        effective_summary = bool(args.summary_only or args.advise or use_native_pptx)

        res = ask_agentspace(
            prompt=args.prompt,
            model_id=effective_model,
            thinking_level=effective_thinking,
            session=args.session,
            enable_search=args.search,
            agent=args.agent,
            delete_session_after=args.delete_after,
            input_files=args.input_files,
            save_output=args.save_output or bool(effective_output) or effective_summary,
            output_filename=effective_output,
            session_tag=args.session_tag,
            new_session=args.new_session,
            python_pptx=use_native_pptx,
            max_media_prompts=args.max_media_prompts,
            csesidx=args.csesidx,
            include_tree=bool(args.tree or args.advise),
            advise_mode=bool(args.advise),
        )
        if args.json:
            print(json.dumps(res, indent=2))
        elif effective_summary and res.get("saved_output_path"):
            preview = res["text"][: args.max_preview_chars]
            if len(res["text"]) > args.max_preview_chars:
                preview += "\n... [truncated in stdout to save AGY tokens]"
            print(
                f"Saved full response ({res['line_count']} lines, {res['char_count']} chars) to:\n"
                f"  {res['saved_output_path']}\n\n"
                f"Preview:\n{preview}"
            )
            for m in res.get("generated_media", []):
                print(f"\n[Auto-Downloaded {m['media_type'].upper()} ({m['mime_type']}): {m['path']} ({m['bytes']:,} bytes)]")
            if res.get("exported_artifacts"):
                exp = res["exported_artifacts"]
                if exp.get("error"):
                    print(f"\n[python-pptx Compile Error: {exp['error']}]", file=sys.stderr)
                for fmt_k, info in exp.get("exported_files", {}).items():
                    print(f"\n[Auto-Exported {fmt_k.upper()} ({exp.get('slides_count')} slides): {info['path']} ({info['bytes']:,} bytes)]")
            if res.get("rotated_previous_media_session"):
                print(
                    f"\n[Media Session Rotated: deleted previous 3-prompt session {res['rotated_previous_media_session']}]",
                    file=sys.stderr,
                )
            if res.get("session_deleted"):
                reason_str = res.get("session_auto_cleared_reason") or "ephemeral"
                print(
                    f"\n[Auto-Cleared Session ({reason_str}): deleted {normalize_session_id(res['session'])}]",
                    file=sys.stderr,
                )
            elif res.get("session"):
                mode_note = "Continued" if res.get("session_reused") else f"Created ({res.get('session_display_name') or '[agy-bridge]'})"
                quota_note = (
                    f" [media prompt {res['media_prompt_count']}/{args.max_media_prompts}]"
                    if res.get("media_prompt_count")
                    else ""
                )
                print(f"\n[Agentspace Session {mode_note}{quota_note}: {normalize_session_id(res['session'])}]", file=sys.stderr)
        else:
            if res["text"]:
                print(res["text"])
            for m in res.get("generated_media", []):
                print(f"[Auto-Downloaded {m['media_type'].upper()} ({m['mime_type']}): {m['path']} ({m['bytes']:,} bytes)]")
            if res.get("saved_output_path"):
                print(f"\n[Saved session-scoped output to: {res['saved_output_path']}]", file=sys.stderr)
            if res.get("exported_artifacts"):
                exp = res["exported_artifacts"]
                for fmt_k, info in exp.get("exported_files", {}).items():
                    print(f"\n[Auto-Exported {fmt_k.upper()} ({exp.get('slides_count')} slides): {info['path']} ({info['bytes']:,} bytes)]", file=sys.stderr)
            if res.get("rotated_previous_media_session"):
                print(
                    f"\n[Media Session Rotated: deleted previous 3-prompt session {res['rotated_previous_media_session']}]",
                    file=sys.stderr,
                )
            if res.get("session_deleted"):
                reason_str = res.get("session_auto_cleared_reason") or "ephemeral"
                print(
                    f"\n[Auto-Cleared Session ({reason_str}): deleted {normalize_session_id(res['session'])}]",
                    file=sys.stderr,
                )
            elif res.get("session"):
                mode_note = "Continued" if res.get("session_reused") else f"Created ({res.get('session_display_name') or '[agy-bridge]'})"
                quota_note = (
                    f" [media prompt {res['media_prompt_count']}/{args.max_media_prompts}]"
                    if res.get("media_prompt_count")
                    else ""
                )
                print(f"\n[Agentspace Session {mode_note}{quota_note}: {normalize_session_id(res['session'])}]", file=sys.stderr)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} Error:\n{err_body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
