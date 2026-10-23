#!/usr/bin/env python3
r"""
HTML/Tailwind (`1280x720` Agentspace Canvas `slidesArtifact`) -> Playwright -> `python-pptx` + `lxml`
DOM Bounding-Box Compiler (`dom_pptx_compiler.py`).

Why this exists:
- Google's server-side `widgetExportImmersiveArtifact` `.pptx` exporter turns single-side CSS borders
  (`border-t-2` / `border-l-4`) on `rounded-*` containers into giant bleeding rounded-rectangle borders,
  and wraps compact badges across 2 lines when converting Web fonts to PowerPoint shapes.
- This compiler renders each `1280x720` HTML/Tailwind slide in headless Chromium via Playwright,
  reads exact computed bounding boxes (`getBoundingClientRect()`) and styles (`getComputedStyle()`),
  and writes 100% native editable PowerPoint (`python-pptx` + `lxml`) shapes, top-border accent
  bars, Tufte hairline `<a:tbl>` tables, and zero-margin text frames (`tf.margin_* = 0`).
- Automatically handles dual-environment setups (e.g., if Playwright is installed in `.venv` while
  `python-pptx` is in system `python` or vice versa).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))

DOM_EXTRACTOR_JS = r"""
() => {
  const container = document.querySelector('.slide-container') || document.body;
  const cRect = container.getBoundingClientRect();

  function parseRgba(str) {
    if (!str || str === 'transparent' || str === 'rgba(0, 0, 0, 0)') return null;
    const m = str.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    if (!m) return null;
    const a = m[4] !== undefined ? parseFloat(m[4]) : 1.0;
    if (a < 0.05) return null;
    return [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])];
  }

  function relRect(el) {
    const r = el.getBoundingClientRect();
    return {
      x: r.left - cRect.left,
      y: r.top - cRect.top,
      w: r.width,
      h: r.height
    };
  }

  const shapes = [];
  const tables = [];
  const texts = [];

  // 1. Extract all <table> elements first (so we don't duplicate table text or cell boxes)
  const tableEls = Array.from(container.querySelectorAll('table'));
  const tableSet = new Set(tableEls);

  function isInsideTable(el) {
    let cur = el;
    while (cur && cur !== container) {
      if (tableSet.has(cur)) return true;
      cur = cur.parentElement;
    }
    return false;
  }

  for (const tbl of tableEls) {
    const tRect = relRect(tbl);
    if (tRect.w < 10 || tRect.h < 10) continue;
    const rowsData = [];
    const trs = Array.from(tbl.querySelectorAll('tr'));
    let colWidths = [];

    for (let rIdx = 0; rIdx < trs.length; rIdx++) {
      const tr = trs[rIdx];
      const trStyle = window.getComputedStyle(tr);
      const trBg = parseRgba(trStyle.backgroundColor);
      const cells = Array.from(tr.querySelectorAll('th, td'));
      const rowCells = [];
      if (rIdx === 0) {
        colWidths = cells.map(c => c.getBoundingClientRect().width);
      }
      for (const cell of cells) {
        const cs = window.getComputedStyle(cell);
        const cellBg = parseRgba(cs.backgroundColor) || trBg;
        const bBottomW = parseFloat(cs.borderBottomWidth) || parseFloat(trStyle.borderBottomWidth) || 0;
        const bBottomC = parseRgba(cs.borderBottomColor) || parseRgba(trStyle.borderBottomColor);
        const bTopW = parseFloat(cs.borderTopWidth) || parseFloat(trStyle.borderTopWidth) || 0;
        const bTopC = parseRgba(cs.borderTopColor) || parseRgba(trStyle.borderTopColor);

        let color = parseRgba(cs.color) || [17, 24, 39];
        let fontWeight = parseInt(cs.fontWeight) || (cell.tagName === 'TH' ? 700 : 400);
        const strongChild = cell.querySelector('strong, b');
        if (strongChild && strongChild.innerText.trim() === cell.innerText.trim()) {
          const scs = window.getComputedStyle(strongChild);
          color = parseRgba(scs.color) || color;
          fontWeight = Math.max(fontWeight, parseInt(scs.fontWeight) || 700);
        }

        rowCells.push({
          tag: cell.tagName.toLowerCase(),
          text: cell.innerText.replace(/\s+/g, ' ').trim(),
          align: cs.textAlign,
          fontSizePx: parseFloat(cs.fontSize) || 12,
          bold: fontWeight >= 600,
          color: color,
          bg: cellBg,
          borderBottomW: bBottomW,
          borderBottomColor: bBottomC,
          borderTopW: bTopW,
          borderTopColor: bTopC
        });
      }
      if (rowCells.length > 0) {
        rowsData.push({
          heightPx: tr.getBoundingClientRect().height,
          cells: rowCells
        });
      }
    }
    if (rowsData.length > 0) {
      tables.push({
        rect: tRect,
        colWidthsPx: colWidths,
        rows: rowsData
      });
    }
  }

  // 2. Walk non-table elements for background boxes, borders/dividers, and progress bars
  const allEls = Array.from(container.querySelectorAll('*'));
  for (const el of allEls) {
    if (isInsideTable(el)) continue;
    const r = relRect(el);
    if (r.w <= 0 || r.h <= 0) continue;
    const cs = window.getComputedStyle(el);

    const bg = parseRgba(cs.backgroundColor);
    const btW = parseFloat(cs.borderTopWidth) || 0;
    const bbW = parseFloat(cs.borderBottomWidth) || 0;
    const blW = parseFloat(cs.borderLeftWidth) || 0;
    const brW = parseFloat(cs.borderRightWidth) || 0;

    const btC = parseRgba(cs.borderTopColor);
    const bbC = parseRgba(cs.borderBottomColor);
    const blC = parseRgba(cs.borderLeftColor);
    const brC = parseRgba(cs.borderRightColor);
    const radiusPx = parseFloat(cs.borderTopLeftRadius) || 0;

    // Background fill rectangle (skip full 1280x720 white slide root)
    if (bg && !(r.w >= 1270 && r.h >= 710 && bg[0] > 250 && bg[1] > 250 && bg[2] > 250)) {
      shapes.push({
        kind: 'rect',
        rect: r,
        bg: bg,
        radiusPx: radiusPx
      });
    }

    // Per-side borders -> top-border accent strips or crisp hairline rules!
    if (btW >= 1 && btC) {
      shapes.push({
        kind: 'line_h',
        rect: { x: r.x, y: r.y, w: r.w, h: Math.max(btW, 1.5) },
        bg: btC,
        weightPx: btW
      });
    }
    if (bbW >= 1 && bbC) {
      shapes.push({
        kind: 'line_h',
        rect: { x: r.x, y: r.y + r.h - bbW, w: r.w, h: Math.max(bbW, 1.5) },
        bg: bbC,
        weightPx: bbW
      });
    }
    if (blW >= 1 && blC) {
      shapes.push({
        kind: 'line_v',
        rect: { x: r.x, y: r.y, w: Math.max(blW, 1.5), h: r.h },
        bg: blC,
        weightPx: blW
      });
    }
    if (brW >= 1 && brC) {
      shapes.push({
        kind: 'line_v',
        rect: { x: r.x + r.w - brW, y: r.y, w: Math.max(brW, 1.5), h: r.h },
        bg: brC,
        weightPx: brW
      });
    }
  }

  // 3. Extract text blocks (elements that contain direct text or inline formatting tags only)
  const INLINE_TAGS = new Set(['STRONG', 'B', 'SPAN', 'EM', 'I', 'CODE', 'BR', 'SMALL', 'SUP', 'SUB']);

  function isTextLeafBlock(el) {
    if (isInsideTable(el)) return false;
    if (INLINE_TAGS.has(el.tagName)) {
      const p = el.parentElement;
      if (!p) return false;
      const pd = window.getComputedStyle(p).display;
      if (!pd.includes('flex') && !pd.includes('grid')) return false;
    }
    const text = el.innerText ? el.innerText.trim() : '';
    if (!text) return false;

    const cs = window.getComputedStyle(el);
    if (cs.display.includes('flex') || cs.display.includes('grid')) {
      if (el.children.length > 0) return false;
    }
    for (const child of Array.from(el.children)) {
      if (!INLINE_TAGS.has(child.tagName)) return false;
    }
    return true;
  }

  function extractRuns(rootEl) {
    const runs = [];
    function walk(node, activeEl) {
      if (node.nodeType === Node.TEXT_NODE) {
        const raw = node.textContent.replace(/\s+/g, ' ');
        if (raw) {
          const cs = window.getComputedStyle(activeEl);
          const fw = parseInt(cs.fontWeight) || 400;
          runs.push({
            text: raw,
            fontSizePx: parseFloat(cs.fontSize) || 12,
            bold: fw >= 600 || activeEl.tagName === 'STRONG' || activeEl.tagName === 'B',
            color: parseRgba(cs.color) || [17, 24, 39],
            fontFamily: cs.fontFamily || 'Calibri'
          });
        }
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        for (const child of Array.from(node.childNodes)) {
          walk(child, node);
        }
      }
    }
    walk(rootEl, rootEl);
    return runs;
  }

  for (const el of allEls) {
    if (!isTextLeafBlock(el)) continue;
    const r = relRect(el);
    if (r.w < 4 || r.h < 4) continue;
    const cs = window.getComputedStyle(el);
    const runs = extractRuns(el);
    if (runs.length === 0) continue;
    runs[0].text = runs[0].text.replace(/^\s+/, '');
    runs[runs.length - 1].text = runs[runs.length - 1].text.replace(/\s+$/, '');
    const fullText = runs.map(x => x.text).join('').trim();
    if (!fullText) continue;

    texts.push({
      rect: r,
      align: cs.textAlign || 'left',
      runs: runs
    });
  }

  return {
    canvasW: cRect.width || 1280,
    canvasH: cRect.height || 720,
    shapes: shapes,
    tables: tables,
    texts: texts
  };
}
"""


def _find_python_with_module(module_name: str) -> str:
    """Finds a Python executable that has `module_name` installed."""
    candidates = [
        sys.executable,
        os.path.join(WORKSPACE_DIR, ".venv", "Scripts", "python.exe"),
        "python",
    ]
    for cand in candidates:
        if not cand:
            continue
        if os.path.sep in cand and not os.path.exists(cand):
            continue
        try:
            res = subprocess.run(
                [cand, "-c", f"import {module_name}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0:
                return cand
        except Exception:
            continue
    raise RuntimeError(f"Could not find a Python interpreter with `{module_name}` installed.")


def extract_dom_from_slides_in_process(slides_list: list[dict]) -> list[dict]:
    """Renders each HTML/Tailwind slide in headless Playwright (`1280x720`) and returns DOM layout dicts."""
    from playwright.sync_api import sync_playwright

    extracted_slides = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        for idx, s_obj in enumerate(slides_list):
            html_code = s_obj.get("code", "") if isinstance(s_obj, dict) else str(s_obj)
            page.set_content(html_code, wait_until="networkidle", timeout=35000)
            page.wait_for_timeout(300)
            dom_data = page.evaluate(DOM_EXTRACTOR_JS)
            dom_data["slideIndex"] = idx + 1
            extracted_slides.append(dom_data)
        browser.close()
    return extracted_slides


def compile_dom_layout_to_pptx_in_process(slides_dom: list[dict], output_pptx_path: str) -> str:
    """Compiles extracted DOM bounding-box dictionaries into a native editable `.pptx` using `python-pptx` + `lxml`."""
    from lxml import etree
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Inches, Pt

    prs = Presentation()
    SLIDE_W_IN = 13.333
    SLIDE_H_IN = 7.5
    prs.slide_width = Inches(SLIDE_W_IN)
    prs.slide_height = Inches(SLIDE_H_IN)
    blank_layout = prs.slide_layouts[6]

    PX_TO_IN_X = SLIDE_W_IN / 1280.0
    PX_TO_IN_Y = SLIDE_H_IN / 720.0
    PX_TO_PT = 540.0 / 720.0  # 0.75 pt per px in 1280x720 canvas

    def rgb_from_list(c_list, default=(17, 24, 39)):
        if not c_list or len(c_list) < 3:
            return RGBColor(*default)
        return RGBColor(int(c_list[0]), int(c_list[1]), int(c_list[2]))

    def hex_from_list(c_list, default="E5E7EB"):
        if not c_list or len(c_list) < 3:
            return default
        return f"{int(c_list[0]):02X}{int(c_list[1]):02X}{int(c_list[2]):02X}"

    def set_cell_border_lxml(cell, side: str, color_hex: str | None, width_pt: float = 0.5):
        tcPr = cell._tc.get_or_add_tcPr()
        tag_map = {"left": "a:lnL", "right": "a:lnR", "top": "a:lnT", "bottom": "a:lnB"}
        tag = qn(tag_map[side])
        existing = tcPr.find(tag)
        if existing is not None:
            tcPr.remove(existing)
        ln = etree.SubElement(tcPr, tag)
        if color_hex is None:
            etree.SubElement(ln, qn("a:noFill"))
        else:
            ln.set("w", str(int(max(width_pt, 0.5) * 12700)))
            ln.set("cap", "flat")
            ln.set("cmpd", "sng")
            ln.set("algn", "ctr")
            solidFill = etree.SubElement(ln, qn("a:solidFill"))
            srgbClr = etree.SubElement(solidFill, qn("a:srgbClr"))
            srgbClr.set("val", color_hex.lstrip("#").upper())
            prstDash = etree.SubElement(ln, qn("a:prstDash"))
            prstDash.set("val", "solid")

    def clean_font_name(ff: str) -> str:
        ff_low = ff.lower()
        if "cambria" in ff_low or "georgia" in ff_low or "serif" in ff_low:
            return "Cambria"
        if "mono" in ff_low or "consolas" in ff_low or "courier" in ff_low:
            return "Consolas"
        return "Calibri"

    for s_data in slides_dom:
        slide = prs.slides.add_slide(blank_layout)

        # 1. Render Background Shapes, Progress Bars, and Top-Border / Hairline Strips
        for shp_info in s_data.get("shapes", []):
            r = shp_info["rect"]
            x_in = r["x"] * PX_TO_IN_X
            y_in = r["y"] * PX_TO_IN_Y
            w_in = max(r["w"] * PX_TO_IN_X, 0.01)
            h_in = max(r["h"] * PX_TO_IN_Y, 0.01)

            kind = shp_info.get("kind", "rect")
            rad_px = shp_info.get("radiusPx", 0)
            if kind == "rect" and rad_px >= 4:
                shp = slide.shapes.add_shape(
                    MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in)
                )
                shp.adjustments[0] = 0.04
            else:
                if kind == "line_h":
                    h_in = max(shp_info.get("weightPx", 1.0) * PX_TO_IN_Y, 0.012)
                elif kind == "line_v":
                    w_in = max(shp_info.get("weightPx", 1.0) * PX_TO_IN_X, 0.012)
                shp = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in)
                )
            shp.fill.solid()
            shp.fill.fore_color.rgb = rgb_from_list(shp_info.get("bg"))
            shp.line.fill.background()

        # 2. Render Native Editable `<a:tbl>` Tables with `lxml` Tufte Hairlines
        for tbl_info in s_data.get("tables", []):
            r = tbl_info["rect"]
            rows = tbl_info.get("rows", [])
            if not rows:
                continue
            n_rows = len(rows)
            n_cols = max(len(row["cells"]) for row in rows)
            if n_cols == 0:
                continue

            x_in = r["x"] * PX_TO_IN_X
            y_in = r["y"] * PX_TO_IN_Y
            w_in = r["w"] * PX_TO_IN_X
            h_in = r["h"] * PX_TO_IN_Y

            t_shape = slide.shapes.add_table(
                n_rows, n_cols, Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in)
            )
            tbl = t_shape.table

            tblPr = tbl._tbl.tblPr
            for attr in ("bandRow", "firstRow", "lastRow", "bandCol", "firstCol", "lastCol"):
                tblPr.set(attr, "0")

            col_w_px = tbl_info.get("colWidthsPx", [])
            if len(col_w_px) == n_cols and sum(col_w_px) > 0:
                scale_w = w_in / sum(col_w_px)
                for c_idx, cw in enumerate(col_w_px):
                    tbl.columns[c_idx].width = Inches(cw * scale_w)

            for r_idx, row_obj in enumerate(rows):
                tbl.rows[r_idx].height = Inches(max(row_obj.get("heightPx", 24) * PX_TO_IN_Y, 0.22))
                for c_idx, cell_obj in enumerate(row_obj["cells"]):
                    if c_idx >= n_cols:
                        continue
                    cell = tbl.cell(r_idx, c_idx)
                    cell.margin_left = Inches(0.06)
                    cell.margin_right = Inches(0.06)
                    cell.margin_top = Inches(0.03)
                    cell.margin_bottom = Inches(0.03)
                    cell.vertical_anchor = MSO_ANCHOR.MIDDLE

                    if cell_obj.get("bg"):
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = rgb_from_list(cell_obj["bg"])
                    else:
                        cell.fill.background()

                    set_cell_border_lxml(cell, "left", None)
                    set_cell_border_lxml(cell, "right", None)

                    if cell_obj.get("borderTopW", 0) > 0 and cell_obj.get("borderTopColor"):
                        set_cell_border_lxml(
                            cell,
                            "top",
                            hex_from_list(cell_obj["borderTopColor"]),
                            cell_obj["borderTopW"] * 0.75,
                        )
                    else:
                        set_cell_border_lxml(cell, "top", None)

                    if cell_obj.get("borderBottomW", 0) > 0 and cell_obj.get("borderBottomColor"):
                        set_cell_border_lxml(
                            cell,
                            "bottom",
                            hex_from_list(cell_obj["borderBottomColor"]),
                            cell_obj["borderBottomW"] * 0.75,
                        )
                    elif r_idx == 0:
                        set_cell_border_lxml(cell, "bottom", "111827", 1.5)
                    else:
                        set_cell_border_lxml(cell, "bottom", "E5E7EB", 0.5)

                    tf = cell.text_frame
                    tf.word_wrap = True
                    p = tf.paragraphs[0]
                    p.text = cell_obj.get("text", "")
                    al = cell_obj.get("align", "left")
                    if "right" in al:
                        p.alignment = PP_ALIGN.RIGHT
                    elif "center" in al:
                        p.alignment = PP_ALIGN.CENTER
                    else:
                        p.alignment = PP_ALIGN.LEFT
                    p.font.name = "Calibri"
                    p.font.size = Pt(max(cell_obj.get("fontSizePx", 12) * PX_TO_PT, 7.5))
                    p.font.bold = bool(cell_obj.get("bold", False))
                    p.font.color.rgb = rgb_from_list(cell_obj.get("color"))

        # 3. Render Zero-Margin Text Frames from Computed DOM Bounding Boxes
        for txt_info in s_data.get("texts", []):
            r = txt_info["rect"]
            x_in = r["x"] * PX_TO_IN_X
            y_in = r["y"] * PX_TO_IN_Y
            w_in = max(r["w"] * PX_TO_IN_X + 0.14, 0.25)
            h_in = max(r["h"] * PX_TO_IN_Y + 0.04, 0.15)

            al = txt_info.get("align", "left")
            if "right" in al:
                x_in = max(0.0, (r["x"] + r["w"]) * PX_TO_IN_X - w_in)

            tb = slide.shapes.add_textbox(Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in))
            tf = tb.text_frame
            tf.margin_left = Emu(0)
            tf.margin_right = Emu(0)
            tf.margin_top = Emu(0)
            tf.margin_bottom = Emu(0)
            tf.word_wrap = bool(r["h"] > 26.0)
            tf.vertical_anchor = MSO_ANCHOR.TOP

            p = tf.paragraphs[0]
            if "right" in al:
                p.alignment = PP_ALIGN.RIGHT
            elif "center" in al:
                p.alignment = PP_ALIGN.CENTER
            else:
                p.alignment = PP_ALIGN.LEFT

            for run_info in txt_info.get("runs", []):
                run = p.add_run()
                raw_txt = run_info.get("text", "")
                if r["h"] <= 26.0:
                    raw_txt = re.sub(r"(\d)-(\d)", "\\1\u2011\\2", raw_txt)
                run.text = raw_txt
                run.font.name = clean_font_name(run_info.get("fontFamily", "Calibri"))
                run.font.size = Pt(max(run_info.get("fontSizePx", 12) * 0.71, 7.5))
                run.font.bold = bool(run_info.get("bold", False))
                run.font.color.rgb = rgb_from_list(run_info.get("color"))

    os.makedirs(os.path.dirname(os.path.abspath(output_pptx_path)), exist_ok=True)
    prs.save(output_pptx_path)
    return output_pptx_path


def compile_slides_html_to_pptx(slides_list: list[dict], output_pptx_path: str) -> str:
    """
    End-to-end orchestrator: takes `slidesArtifact.slides` (`[{"code": "<html>..."}, ...]`)
    and compiles a native `.pptx` at `output_pptx_path`.
    Automatically bridges across Python interpreters if `playwright` and `pptx` live in
    different environments (e.g. `.venv` vs system `python`).
    """
    with tempfile.TemporaryDirectory(prefix="agy_dom_pptx_") as tmpdir:
        slides_json = os.path.join(tmpdir, "slides_html.json")
        dom_json = os.path.join(tmpdir, "dom_layout.json")
        with open(slides_json, "w", encoding="utf-8") as f:
            json.dump(slides_list, f)

        # Step 1: Extract DOM bounding boxes with Playwright
        try:
            import playwright.sync_api  # noqa: F401
            slides_dom = extract_dom_from_slides_in_process(slides_list)
            with open(dom_json, "w", encoding="utf-8") as f:
                json.dump(slides_dom, f)
        except ImportError:
            pw_py = _find_python_with_module("playwright")
            res = subprocess.run(
                [pw_py, os.path.abspath(__file__), "--extract", slides_json, dom_json],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if res.returncode != 0:
                raise RuntimeError(f"Playwright DOM extraction failed:\n{res.stderr or res.stdout}")
            with open(dom_json, "r", encoding="utf-8") as f:
                slides_dom = json.load(f)

        # Step 2: Compile DOM layout into native `.pptx` via `python-pptx` + `lxml`
        try:
            import lxml  # noqa: F401
            import pptx  # noqa: F401
            compile_dom_layout_to_pptx_in_process(slides_dom, output_pptx_path)
        except ImportError:
            pptx_py = _find_python_with_module("pptx")
            res = subprocess.run(
                [pptx_py, os.path.abspath(__file__), "--compile", dom_json, output_pptx_path],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode != 0:
                raise RuntimeError(f"python-pptx compilation failed:\n{res.stderr or res.stdout}")

    return output_pptx_path


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--extract":
        in_slides_json, out_dom_json = sys.argv[2], sys.argv[3]
        with open(in_slides_json, "r", encoding="utf-8") as f:
            s_list = json.load(f)
        dom_out = extract_dom_from_slides_in_process(s_list)
        with open(out_dom_json, "w", encoding="utf-8") as f:
            json.dump(dom_out, f)
    elif len(sys.argv) >= 4 and sys.argv[1] == "--compile":
        in_dom_json, out_pptx = sys.argv[2], sys.argv[3]
        with open(in_dom_json, "r", encoding="utf-8") as f:
            dom_in = json.load(f)
        compile_dom_layout_to_pptx_in_process(dom_in, out_pptx)
    elif len(sys.argv) >= 3:
        in_slides_json, out_pptx = sys.argv[1], sys.argv[2]
        with open(in_slides_json, "r", encoding="utf-8") as f:
            s_list = json.load(f)
        compile_slides_html_to_pptx(s_list, out_pptx)
        print(f"Compiled DOM PPTX: {out_pptx}")
    else:
        print("Usage: python dom_pptx_compiler.py <slides_html.json> <output.pptx>")
        sys.exit(1)
