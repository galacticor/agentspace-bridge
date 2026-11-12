import json
import copy
import re
from pathlib import Path
from agentspace_cli import get_agent, update_agent_from_file

V2_AGENT_ID = "2291045905737541211"

# 1. Load baseline from office_creator_v2_created.json
import os
raw_created_txt = Path("office_creator_v2_created.json").read_text(encoding="utf-8")
if os.environ.get("AGENTSPACE_ONEDRIVE_DRIVE_ID"):
    raw_created_txt = raw_created_txt.replace("<YOUR_ONEDRIVE_DRIVE_ID>", os.environ["AGENTSPACE_ONEDRIVE_DRIVE_ID"])
if os.environ.get("AGENTSPACE_ONEDRIVE_PARENT_ID"):
    raw_created_txt = raw_created_txt.replace("<YOUR_ONEDRIVE_FOLDER_ID>", os.environ["AGENTSPACE_ONEDRIVE_PARENT_ID"])
if os.environ.get("AGENTSPACE_EMPLOYEE_ID"):
    raw_created_txt = raw_created_txt.replace("<employee_id>", os.environ["AGENTSPACE_EMPLOYEE_ID"])
created = json.loads(raw_created_txt)
created_agent = created["agent"] if "agent" in created else created
nodes = created_agent["lowCodeAgentDefinition"]["nodes"]

node_map = {}
for idx, n in enumerate(nodes):
    nid = n.get("id") or ("root_agent" if idx == 0 else f"node_{idx}")
    node_map[nid] = n["llmAgentNode"]

orig_root_instr = node_map["root_agent"]["instruction"]
orig_pres_instr = node_map["presentation_designer"]["instruction"]
orig_doc_instr = node_map["document_creator"]["instruction"]
orig_xls_instr = node_map["spreadsheet_creator"]["instruction"]

# Extract the clean wrapper code block from orig_pres_instr and upgrade prs.save() to write pptx_payload.txt
code_match = re.search(r"```python\r?\n(# pptx_lxml_wrapper\.py.*?)```", orig_pres_instr, re.S)
assert code_match, "Could not find pptx_lxml_wrapper.py in office_creator_v2_created.json"
clean_wrapper_code = code_match.group(1).strip()

old_save_tail = '''        with open(bp, "rb") as f:
            b64_str = base64.b64encode(f.read()).decode("ascii")
            print("B64_PPTX:" + b64_str)
            return b64_str'''

new_save_tail = '''        with open(bp, "rb") as f:
            raw_pptx = f.read()
        with open("pptx_payload.txt", "wb") as f_txt:
            f_txt.write(raw_pptx)
        if os.path.isdir("/home/bard"):
            with open("/home/bard/pptx_payload.txt", "wb") as f_txt2:
                f_txt2.write(raw_pptx)
        b64_str = base64.b64encode(raw_pptx).decode("ascii")
        print(f"[PPTX_PAYLOAD_ATTACHED] Wrote {len(raw_pptx)} raw binary bytes to pptx_payload.txt (use InputFileName='pptx_payload.txt', HasBytes=false, ContentBytes='')")
        print("B64_PPTX:" + b64_str)
        return b64_str'''

assert old_save_tail in clean_wrapper_code, "Could not find old_save_tail in clean_wrapper_code"
clean_wrapper_code = clean_wrapper_code.replace(old_save_tail, new_save_tail)
clean_wrapper_code = clean_wrapper_code.replace(
    '_sp(slide, x+0.14, y+0.34, w-0.28, 0.48, paras=[[(hero_val, 22, True, accent, FONT_HEAD)]], _qa_kind="skip")',
    'h_fs = min(22.0, max(13.0, (w - 0.30) * 72.0 / max(len(str(hero_val)) * 0.62, 1.0)))\n    _sp(slide, x+0.14, y+0.34, w-0.28, 0.48, paras=[[(hero_val, h_fs, True, accent, FONT_HEAD)]], _qa_kind="skip")'
)

# 2. Update all 3 Knowledge Bundle files (01, 02, 03):
#    - 01: Clean unified pptx_lxml_wrapper, zero BRAND_LOGOS_B64, use pptx_payload.txt session attachment bridge (HasBytes=false, ContentBytes='')
kb_01_clean = f"""# Knowledge Reference 1: Zero-Dependency `pptx_lxml_wrapper` Engine (`presentation_designer`)

> **CRITICAL SANDBOX & ONEDRIVE UPLOAD RULE FOR `.pptx` (ZERO `ContentBytes` / `pptx_payload.txt` BRIDGE):**
> 1. Always save `pptx_lxml_wrapper.py` to `/home/bard/pptx_lxml_wrapper.py` inside `file_and_coding_agent` and import `create_widescreen_prs`, `add_header_and_footer`, `add_top_accent_card`, `add_metric_callout`, `add_tufte_table`, `add_native_column_chart`, and `add_callout_strip`.
> 2. **How We Avoid Broken `.pptx` Files & `ContentBytes` Token Burn (`pptx_payload.txt` Session Bridge):**
>    - Because `/home/bard` ignores `.pptx` files when indexing session attachments, passing `InputFileName="<DeckName>.pptx"` with blank `ContentBytes` fails lookup, while passing a 35,000-character Base64 string in `ContentBytes` causes LLM token truncation/corruption and breaks the `.pptx` file on OneDrive!
>    - Instead, `prs.save("<DeckName>.pptx")` automatically writes an exact byte-for-byte copy of the raw `.pptx` binary to **`pptx_payload.txt`** (`/home/bard/pptx_payload.txt`), which `/home/bard` automatically attaches to the session's `Files currently attached` registry!
> 3. **Mandatory `onedrive_agent__upload_file` Parameters (`HasBytes: false`, `ContentBytes: ""`):**
>    - Always pass:
>      - `FileName`: `"<DeckName>.pptx"` (the target `.pptx` filename on OneDrive)
>      - `InputFileName`: `"pptx_payload.txt"` (the attached session file containing the raw `.pptx` binary bytes!)
>      - `HasBytes`: `false`
>      - `ContentBytes`: `""` (leave **completely empty/blank** — NEVER pass Base64 inside `ContentBytes`!)
>    - Google's OneDrive connector streams the exact binary bytes directly from `pptx_payload.txt` into `<DeckName>.pptx` on OneDrive with **100% bit-for-bit integrity** and **zero `ContentBytes` token cost**!
> 4. **Do NOT upload `.xlsx` or `.docx` to OneDrive** — `.xlsx` and `.docx` use `[Generate Document](tool://generate_document)` for native in-chat download buttons!
> 5. *(Optional Custom Logos)*: You can add your own brand logo PNG helpers (`add_picture_b64(slide, x, y, w, h, b64_png)`) at the bottom of `pptx_lxml_wrapper.py` where suited.

```python
{clean_wrapper_code}
```
"""
Path("knowledge_bundle_v2/01_pptx_lxml_engine_and_brand_logos.md").write_text(kb_01_clean, encoding="utf-8")

#    - 02: Update header so .xlsx is delivered directly in chat (NO OneDrive upload)
kb_02_raw = Path("knowledge_bundle_v2/02_xlsx_inmemory_engine.md").read_text(encoding="utf-8")
kb_02_code = kb_02_raw[kb_02_raw.index("```python"):]
kb_02_clean = """# Knowledge Reference 2: Zero-Dependency In-Memory Excel Engine (`xlsx_inmemory_engine.py`) — Wall Street Formulas & Native Chat Delivery

> **CRITICAL VERTEX AI SANDBOX & CHAT DELIVERY RULE FOR `.xlsx`:**
> 1. **Never** leave a `.xlsx` file on disk in `/home/bard` when `file_and_coding_agent` finishes! Vertex AI's multi-agent file router crashes with `HTTP 500 Internal Error` when a sub-agent returns a `.xlsx` attachment on disk.
> 2. **DO NOT pass `.xlsx` to OneDrive (`onedrive_agent__upload_file`).** Instead, deliver `.xlsx` directly in chat using **`[Generate Document](tool://generate_document)`** (which gives the user Agentspace's native Download/Export button in the chat UI) AND run `WorkbookBuilder` below 100% in memory (`io.BytesIO()`) to print `B64_XLSX:<base64>` to `file_and_coding_agent` stdout for CLI auto-extraction!

""" + kb_02_code
Path("knowledge_bundle_v2/02_xlsx_inmemory_engine.md").write_text(kb_02_clean, encoding="utf-8")

#    - 03: Update header so .docx is delivered directly in chat (NO OneDrive upload)
kb_03_raw = Path("knowledge_bundle_v2/03_docx_inmemory_engine.md").read_text(encoding="utf-8")
kb_03_code = kb_03_raw[kb_03_raw.index("```python"):]
kb_03_clean = """# Knowledge Reference 3: Zero-Dependency In-Memory Word Engine (`docx_inmemory_engine.py`) — Executive Memos & Native Chat Delivery

> **CRITICAL VERTEX AI SANDBOX & CHAT DELIVERY RULE FOR `.docx`:**
> 1. **Never** leave a `.docx` file on disk in `/home/bard` when `file_and_coding_agent` finishes! Vertex AI's multi-agent file router crashes with `HTTP 500 Internal Error` when a sub-agent returns a `.docx` attachment on disk.
> 2. **DO NOT pass `.docx` to OneDrive (`onedrive_agent__upload_file`).** Instead, deliver `.docx` directly in chat using **`[Generate Document](tool://generate_document)`** (which renders Agentspace's native document card with its built-in Download button in the chat UI) AND run `DocxBuilder` below 100% in memory (`io.BytesIO()`) to print `B64_DOCX:<base64>` to `file_and_coding_agent` stdout for CLI auto-extraction!

""" + kb_03_code
Path("knowledge_bundle_v2/03_docx_inmemory_engine.md").write_text(kb_03_clean, encoding="utf-8")
print("Updated all 3 files in knowledge_bundle_v2/!")

# 3. Fetch live Office File Creator 2.0 to preserve user-uploaded agentFiles
live_data = get_agent(V2_AGENT_ID)
live_agent_files = (
    live_data.get("agent", {}).get("lowCodeAgentDefinition", {}).get("agentFiles")
    or live_data.get("lowCodeAgentDefinition", {}).get("agentFiles")
    or []
)
print("Preserving live agentFiles count:", len(live_agent_files))

# 4. Patch root_agent instruction:
#    - Use InputFileName="pptx_payload.txt", HasBytes=false, ContentBytes="" so Web UI OneDrive uploads never corrupt .pptx or burn tokens
#    - Explicitly state OneDrive upload is ONLY for .pptx (never .docx or .xlsx)
patched_root = orig_root_instr.replace(
    '- `InputFileName`: `"<DeckName>.pptx"`\n     - `HasBytes`: `true`\n     - `ContentBytes`: `"<the raw base64 string printed after B64_PPTX:>"`',
    '- `InputFileName`: `"pptx_payload.txt"` (the session attachment written by `prs.save()` containing the raw `.pptx` binary bytes!)\n     - `HasBytes`: `false`\n     - `ContentBytes`: `""` (leave **completely empty/blank** — NEVER pass Base64 inside `ContentBytes`!)'
)
docx_xlsx_rule = """
---
## CRITICAL DELIVERY RULE FOR `.pptx`, `.docx`, AND `.xlsx`
1. **For `.pptx` (Zero-`ContentBytes` `pptx_payload.txt` Session Bridge to OneDrive):**
   - `prs.save("<DeckName>.pptx")` automatically writes an exact byte-for-byte copy of the `.pptx` binary to **`pptx_payload.txt`** (`/home/bard/pptx_payload.txt`), which `/home/bard` attaches to the session's `Files currently attached` registry!
   - When calling `onedrive_agent__upload_file`, **ALWAYS** pass:
     - `FileName`: `"<DeckName>.pptx"`
     - `InputFileName`: `"pptx_payload.txt"`
     - `HasBytes`: `false`
     - `ContentBytes`: `""` (leave **completely empty/blank** — NEVER put Base64 inside `ContentBytes`, which prevents LLM token truncation and broken `.pptx` files on OneDrive!)
2. **For `.docx` and `.xlsx` (NO OneDrive Upload!):**
   - **NEVER** call `onedrive_agent__upload_file` for `.docx` (`document_creator`) or `.xlsx` (`spreadsheet_creator`).
   - Instead, `document_creator` and `spreadsheet_creator` deliver directly in chat using **`[Generate Document](tool://generate_document)`** (which gives the user Agentspace's native Download/Export button in the chat UI) plus in-memory `B64_DOCX:` / `B64_XLSX:` stdout inside `file_and_coding_agent`.
"""
new_root_instr = patched_root + "\n" + docx_xlsx_rule

# 5. Patch presentation_designer instruction:
#    - Upgrade prs.save() inside presentation_designer instruction to also write pptx_payload.txt
#    - Replace HasBytes=true / ContentBytes with InputFileName="pptx_payload.txt", HasBytes=false, ContentBytes=""
patched_pres = orig_pres_instr.replace(old_save_tail, new_save_tail).replace(
    '_sp(slide, x+0.14, y+0.34, w-0.28, 0.48, paras=[[(hero_val, 22, True, accent, FONT_HEAD)]], _qa_kind="skip")',
    'h_fs = min(22.0, max(13.0, (w - 0.30) * 72.0 / max(len(str(hero_val)) * 0.62, 1.0)))\n    _sp(slide, x+0.14, y+0.34, w-0.28, 0.48, paras=[[(hero_val, h_fs, True, accent, FONT_HEAD)]], _qa_kind="skip")'
).replace(
    '- `InputFileName`: `"<DeckName>.pptx"`\n     - `HasBytes`: `true`\n     - `ContentBytes`: `"<the exact base64 string printed after B64_PPTX:>"`',
    '- `InputFileName`: `"pptx_payload.txt"` (the session attachment written by `prs.save()` containing the raw `.pptx` binary bytes!)\n     - `HasBytes`: `false`\n     - `ContentBytes`: `""` (leave **completely empty/blank** — NEVER pass Base64 inside `ContentBytes`!)'
)
transfer_rule = """
> **MANDATORY HANDOFF TO `root_agent` AFTER `[QA_GATE_PASSED]` (`pptx_payload.txt` ZERO-`ContentBytes` BRIDGE):**
> 1. `prs.save("<Deck_Name>.pptx")` automatically writes the exact raw `.pptx` binary bytes to `pptx_payload.txt` (`/home/bard/pptx_payload.txt`), which `/home/bard` attaches to the session file store.
> 2. Immediately after `[QA_GATE_PASSED]`, either call `onedrive_agent__upload_file` or call **`transfer_to_agent(agent_name="root_agent")`** so `onedrive_agent__upload_file` is executed with:
>    - `FileName`: `"<Deck_Name>.pptx"`
>    - `InputFileName`: `"pptx_payload.txt"`
>    - `HasBytes`: `false`
>    - `ContentBytes`: `""` (completely blank!)
"""
new_pres_instr = patched_pres + "\n\n" + transfer_rule

# 6. Patch spreadsheet_creator and document_creator instructions
new_xls_instr = orig_xls_instr + "\n\n---\n\n" + kb_02_clean + """

---
### MANDATORY `.xlsx` EXECUTION & CHAT DELIVERY SEQUENCE (NO ONEDRIVE!)
1. **Step 1 — In-Memory `.xlsx` Generation (`file_and_coding_agent`):** Run a single Python script using `WorkbookBuilder` in `io.BytesIO()` (never writing `.xlsx` to disk) that validates all formulas/XML and prints `B64_XLSX:<base64>` to stdout.
2. **Step 2 — Native Chat Download Card (`generate_document`):** Call `[Generate Document](tool://generate_document)` with a clean Markdown summary of all tabs, tables, and key outputs so the user gets Agentspace's native Download/Export button directly in chat.
3. **Step 3 — Final Response (NO OneDrive Upload):** Present the executive summary and key tables in chat. Do **NOT** call `onedrive_agent__upload_file` and do **NOT** echo the raw `B64_XLSX:` string in your chat message.
"""

new_doc_instr = orig_doc_instr + "\n\n---\n\n" + kb_03_clean + """

---
### MANDATORY `.docx` EXECUTION & CHAT DELIVERY SEQUENCE (NO ONEDRIVE!)
1. **Step 1 — In-Memory `.docx` Generation (`file_and_coding_agent`):** Run a single Python script using `DocxBuilder` in `io.BytesIO()` (never writing `.docx` to disk) that builds the styled `.docx` and prints `B64_DOCX:<base64>` to stdout.
2. **Step 2 — Native Chat Download Card (`generate_document`):** Call `[Generate Document](tool://generate_document)` with the full formatted document content so the user gets Agentspace's native Document card and Download button directly in chat.
3. **Step 3 — Final Response (NO OneDrive Upload):** Present a concise executive summary in chat. Do **NOT** call `onedrive_agent__upload_file` and do **NOT** echo the raw `B64_DOCX:` string in your chat message.
"""

agent_payload = copy.deepcopy(created_agent)
for idx, n in enumerate(agent_payload["lowCodeAgentDefinition"]["nodes"]):
    nid = n.get("id") or ("root_agent" if idx == 0 else f"node_{idx}")
    if nid == "root_agent":
        n["llmAgentNode"]["instruction"] = new_root_instr
    elif nid == "presentation_designer":
        n["llmAgentNode"]["instruction"] = new_pres_instr
    elif nid == "spreadsheet_creator":
        n["llmAgentNode"]["instruction"] = new_xls_instr
    elif nid == "document_creator":
        n["llmAgentNode"]["instruction"] = new_doc_instr

if live_agent_files:
    agent_payload["lowCodeAgentDefinition"]["agentFiles"] = live_agent_files

out_json_path = Path("office_creator_v2_patched.json")
out_json_path.write_text(json.dumps({"agent": agent_payload}, indent=2), encoding="utf-8")
data = update_agent_from_file(str(out_json_path))
print("Successfully updated and deployed Office File Creator 2.0 (2291045905737541211)!")

# Also promote V2 instructions to Production Office File Creator (17216682253898748109)
v1_live = get_agent("17216682253898748109").get("agent", {})
v1_promoted = copy.deepcopy(v1_live)
for k in ("deployedNodes", "deployedRootAgentId", "session"):
    v1_promoted.get("lowCodeAgentDefinition", {}).pop(k, None)
for idx, n in enumerate(v1_promoted["lowCodeAgentDefinition"]["nodes"]):
    nid = n.get("id") or ("root_agent" if idx == 0 else f"node_{idx}")
    if nid == "root_agent":
        n["llmAgentNode"]["instruction"] = new_root_instr
    elif nid == "presentation_designer":
        n["llmAgentNode"]["instruction"] = new_pres_instr
    elif nid == "spreadsheet_creator":
        n["llmAgentNode"]["instruction"] = new_xls_instr
    elif nid == "document_creator":
        n["llmAgentNode"]["instruction"] = new_doc_instr

v1_out_path = Path("office_creator_v1_promoted.json")
v1_out_path.write_text(json.dumps({"agent": v1_promoted}, indent=2), encoding="utf-8")
update_agent_from_file(str(v1_out_path))
v1_verified = get_agent("17216682253898748109").get("agent", {})
print("Successfully promoted V2 to Production Office File Creator (17216682253898748109)!")
for dn in v1_verified.get("lowCodeAgentDefinition", {}).get("deployedNodes", []):
    instr = dn.get("llmAgentNode", {}).get("instruction", "")
    print(f"  [17216682253898748109 deployed] {dn.get('id')}: {len(instr)} chars | pptx_payload.txt={'pptx_payload.txt' in instr}")
print("  root_agent len:", len(new_root_instr))
print("  presentation_designer len:", len(new_pres_instr))
print("  spreadsheet_creator len:", len(new_xls_instr))
print("  document_creator len:", len(new_doc_instr))
print("  HasBytes=true in root_agent:", "HasBytes`: `true`" in new_root_instr)
print("  HasBytes=true in presentation_designer:", "HasBytes`: `true`" in new_pres_instr)
print("  pptx_payload.txt in root_agent:", "pptx_payload.txt" in new_root_instr)
print("  pptx_payload.txt in presentation_designer:", "pptx_payload.txt" in new_pres_instr)
print("  BRAND_LOGOS_B64 in presentation_designer:", "BRAND_LOGOS_B64" in new_pres_instr)
print("  agentFiles preserved on V2:", len(live_agent_files))
