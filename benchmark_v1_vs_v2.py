import json
import os
import re
import time
import zipfile
from pathlib import Path
from agentspace_cli import ask_agentspace

SESSION_TAG = "05904963"

PPTX_PROMPT_TEMPLATE = (
    "Create a 4-slide executive PowerPoint presentation (.pptx) named '{filename}' on "
    "IOH 5G vs Non-5G Upgrade Target Sizing (Sep-Oct 2026: Total base 95.40M, 5G active 3.94M at Rp 71.2k ARPU "
    "& 33.1 GB/sub vs Non-5G 91.46M at Rp 43.9k ARPU & 18.4 GB/sub; Tier-1 5G-Ready Device on 4G SIM cohort = "
    "6.82M subs with +Rp 27.3k ARPU uplift = IDR 2.23T annualized revenue opportunity; Tier-2 High-ARPU 4G = 11.40M subs; "
    "Tier-3 Mass 4G = 73.24M subs). Run the automated Visual QA gate, upload '{filename}' to OneDrive "
    "/Agentspace_Exports, and return the clickable OneDrive webUrl."
)

XLSX_PROMPT_TEMPLATE = (
    "Create a 2-tab Excel financial model (.xlsx) named '{filename}' on IOH 5G Upgrade Target Sizing "
    "(Tab 1: Executive Summary with cross-sheet links; Tab 2: Cohort Model with Tier-1 6.82M subs at Rp 58.0k current ARPU "
    "and +Rp 27.3k uplift, Tier-2 11.40M subs at Rp 49.5k ARPU and +Rp 14.5k uplift, Tier-3 73.24M subs at Rp 41.7k ARPU "
    "and +Rp 5.0k uplift, using live SUM and IFERROR Excel formulas and Wall Street styles). "
    "Upload '{filename}' to OneDrive /Agentspace_Exports and return the clickable OneDrive webUrl."
)

def inspect_office_file(path: str | None) -> dict:
    if not path or not os.path.isfile(path):
        return {"exists": False}
    info = {
        "exists": True,
        "path": path,
        "bytes": os.path.getsize(path),
        "is_valid_zip": zipfile.is_zipfile(path),
        "slides_count": 0,
        "sheets_count": 0,
        "embedded_logos": [],
        "live_formulas_count": 0,
        "has_core_docprops": False,
    }
    if info["is_valid_zip"]:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            info["has_core_docprops"] = "docProps/core.xml" in names and "docProps/app.xml" in names
            info["slides_count"] = sum(1 for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            info["sheets_count"] = sum(1 for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            info["embedded_logos"] = [n for n in names if n.startswith("ppt/media/")]
            formula_cnt = 0
            for n in names:
                if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"):
                    xml_txt = zf.read(n).decode("utf-8", errors="replace")
                    formula_cnt += len(re.findall(r"<f[^>]*>", xml_txt))
            info["live_formulas_count"] = formula_cnt
    return info

def run_single_test(label: str, agent_alias: str, prompt: str, out_md: str) -> dict:
    print(f"\n=======================================================", flush=True)
    print(f"[STARTING] {label} (agent={agent_alias})", flush=True)
    t0 = time.perf_counter()
    err_msg = None
    res = {}
    try:
        res = ask_agentspace(
            prompt=prompt,
            agent=agent_alias,
            session_tag=SESSION_TAG,
            new_session=True,
            output_filename=out_md,
            save_output=True,
        )
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
    elapsed = round(time.perf_counter() - t0, 2)

    text = res.get("text", "") if isinstance(res, dict) else ""
    fcalls = res.get("function_calls", []) if isinstance(res, dict) else []
    exp = res.get("exported_artifacts") or {}
    ef = exp.get("exported_files", {}) if isinstance(exp, dict) else {}
    nat_info = ef.get("pptx_native") or {}
    local_file_path = nat_info.get("path")

    # Check OneDrive folder as well if uploaded
    od_dir = Path(r"C:\Users\ASUS\OneDrive - Indosatooredoo Hutchison\Agentspace_Exports")
    qa_passed = "[QA_GATE_PASSED]" in text
    has_b64_pptx = "B64_PPTX:" in text
    has_b64_xlsx = "B64_XLSX:" in text
    has_onedrive_upload = "onedrive_agent__upload_file" in fcalls or "sharepoint.com" in text.lower()
    web_urls = re.findall(r"https://[^\s\)\]]+sharepoint\.com[^\s\)\]]+", text)

    file_audit = inspect_office_file(local_file_path)

    summary = {
        "label": label,
        "agent": agent_alias,
        "session": res.get("session") if isinstance(res, dict) else None,
        "latency_sec": elapsed,
        "error": err_msg,
        "qa_gate_passed": qa_passed,
        "has_b64_pptx": has_b64_pptx,
        "has_b64_xlsx": has_b64_xlsx,
        "function_calls": fcalls,
        "has_onedrive_upload": has_onedrive_upload,
        "onedrive_web_urls": web_urls,
        "file_audit": file_audit,
        "response_excerpt": re.sub(r"B64_(?:PPTX|XLSX|DOCX):[A-Za-z0-9+/=]+", "<B64_STRIPPED>", text)[-1200:],
    }
    print(
        f"[FINISHED] {label} in {elapsed}s | QA={qa_passed} | OneDrive={has_onedrive_upload} | "
        f"File={file_audit.get('exists')} ({file_audit.get('bytes', 0)} bytes) | Err={err_msg}",
        flush=True,
    )
    return summary

def main():
    results = []
    # Test 1A: Original V1 PPTX
    results.append(
        run_single_test(
            label="Test 1A: PPTX - Original Office File Creator (v1)",
            agent_alias="office-creator",
            prompt=PPTX_PROMPT_TEMPLATE.format(filename="IOH_5G_Upgrade_Benchmark_V1.pptx"),
            out_md="bench_v1_pptx.md",
        )
    )
    # Test 1B: Upgraded V2 PPTX (with Trick 2 Brand Logo)
    results.append(
        run_single_test(
            label="Test 1B: PPTX - Office File Creator 2.0 (v2 + Brand Logo)",
            agent_alias="office-creator-2",
            prompt=PPTX_PROMPT_TEMPLATE.format(filename="IOH_5G_Upgrade_Benchmark_V2.pptx"),
            out_md="bench_v2_pptx.md",
        )
    )
    # Test 2A: Original V1 XLSX
    results.append(
        run_single_test(
            label="Test 2A: XLSX - Original Office File Creator (v1)",
            agent_alias="office-creator",
            prompt=XLSX_PROMPT_TEMPLATE.format(filename="IOH_5G_Model_Benchmark_V1.xlsx"),
            out_md="bench_v1_xlsx.md",
        )
    )
    # Test 2B: Upgraded V2 XLSX (with Trick 1 In-Memory Engine)
    results.append(
        run_single_test(
            label="Test 2B: XLSX - Office File Creator 2.0 (v2 In-Memory Engine)",
            agent_alias="office-creator-2",
            prompt=XLSX_PROMPT_TEMPLATE.format(filename="IOH_5G_Model_Benchmark_V2.xlsx"),
            out_md="bench_v2_xlsx.md",
        )
    )

    Path("benchmark_v1_vs_v2_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("\nSaved full benchmark results to benchmark_v1_vs_v2_results.json", flush=True)

if __name__ == "__main__":
    main()
