# 1. Architecture & Authentication

## Target Endpoints

All RPC calls target `https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/`:

| Endpoint | Purpose |
| :--- | :--- |
| `widgetStreamAssist` | Send chat queries to `gemini-4-argon`, `gemini-4-carbon`, IOH Agents (`agentsSpec.agentSpecs`), Skill Agents (`load_skill` + `canvasSpec`), or Federated Search (`vertexAiSearchSpec`). |
| `widgetListSessions` | List recent chat sessions (`listSessionsRequest`). |
| `widgetGetSession` | Retrieve full session turn & tool-call history (`getSessionRequest`). |
| `widgetUpdateSession` | Update session metadata (used to prefix `[agy-bridge]` on `displayName`). |
| `widgetDeleteSession` | Delete a chat session (`deleteSessionRequest`). |
| `widgetGetImmersiveArtifact` | Retrieve Canvas / Slides `immersiveArtifact` payload. |
| `widgetExportImmersiveArtifact` | Export Canvas / Slides `immersiveArtifact` directly to native `.pptx` or `.pdf` at zero LLM token cost. |
| `lookupWidgetConfig` | Retrieve widget configuration, connectors, and enabled models. |

- **Widget Config ID (`cid`)**: `384c42b0-2885-415a-82d5-f2babc063b6e`
- **Underlying GCP Engine**: `projects/195467123768/locations/global/collections/default_collection/engines/enterprise-search-17429648_1742964839282`
- **Entry URL**: `https://agentspace.ioh.co.id`

---

## Per-User BYOID Authentication

This repository contains **zero hardcoded credentials or shared tokens**. Each user authenticates with their own `@ioh.co.id` Microsoft Entra ID account:

1. **Initial Login (`--refresh-token`)**:
   - Launches Playwright using an isolated browser profile in `./.auth_profile/` (git-ignored).
   - Defaults to **Microsoft Edge (`msedge`)** on Windows and **Google Chrome (`chrome`)** on macOS, with automatic fallback.
   - Captures `/auth/getoxsrf` (`xsrfToken`, `keyId`, `csesidx`) into `./agentspace_xsrf.json` (git-ignored).
2. **Local JWT Minting**:
   - `agentspace_cli.py` mints 5-minute HS256 JWTs (`Authorization: Bearer <jwt>`) locally using Python's standard `hmac` and `hashlib` libraries.
3. **Silent Headless Refresh (`~8s`)**:
   - On `HTTP 401`/`403`, `agentspace_cli.py` automatically runs a silent headless refresh using `.auth_profile/`.
   - On multi-account Windows PCs (e.g., personal/university + `@ioh.co.id`), it automatically selects the `@ioh.co.id` tile on the Entra ID `"Pick an account"` screen.
   - Only falls back to a visible browser window if interactive 2FA/password entry is required.

---

## Session Lifecycle & `[agy-bridge]` Naming

- **Automatic Prefix**: New kept sessions are automatically renamed via `widgetUpdateSession` (`updateMask: "displayName"`) with the **`[agy-bridge]`** prefix.
- **Multi-Turn Continuity**: Passing `--session-tag <8_char_conv_id>` stores active session IDs per mode/agent in `./outputs/chat_<session_tag>/session_state.json`.
- **Fresh Thread / Throwaway**: Pass `--new-session` to start a new thread under the same tag, or `--ephemeral` to auto-delete the session after the command finishes.
