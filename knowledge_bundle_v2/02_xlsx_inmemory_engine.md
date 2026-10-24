# Knowledge Reference 2: Zero-Dependency In-Memory Excel Engine (`xlsx_inmemory_engine.py`) — Wall Street Formulas & Native Chat Delivery

> **CRITICAL VERTEX AI SANDBOX & CHAT DELIVERY RULE FOR `.xlsx`:**
> 1. **Never** leave a `.xlsx` file on disk in `/home/bard` when `file_and_coding_agent` finishes! Vertex AI's multi-agent file router crashes with `HTTP 500 Internal Error` when a sub-agent returns a `.xlsx` attachment on disk.
> 2. **DO NOT pass `.xlsx` to OneDrive (`onedrive_agent__upload_file`).** Instead, deliver `.xlsx` directly in chat using **`[Generate Document](tool://generate_document)`** (which gives the user Agentspace's native Download/Export button in the chat UI) AND run `WorkbookBuilder` below 100% in memory (`io.BytesIO()`) to print `B64_XLSX:<base64>` to `file_and_coding_agent` stdout for CLI auto-extraction!

```python
# === SELF-CONTAINED xlsx_inmemory_engine.py (ZERO-DEPENDENCY OOXML + WALL STREET STYLES + B64_XLSX) ===
import base64, io, zipfile
import xml.etree.ElementTree as ET

def _col_letter(col_idx_1based: int) -> str:
    res = ""
    n = int(col_idx_1based)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        res = chr(65 + rem) + res
    return res

def _cell_ref(row_1based: int, col_1based: int) -> str:
    return f"{_col_letter(col_1based)}{int(row_1based)}"

# Style indices in xl/styles.xml:
# 0: Default (Arial 10pt)
# 1: Sheet Title (Arial 14pt Bold #0F172A)
# 2: Subtitle / Legend (Arial 9.5pt Italic #475569)
# 3: Table Header (Arial 10pt Bold #FFFFFF on #0F172A Dark Slate fill)
# 4: Input Blue — Text/General (Arial 10pt #0000FF)
# 5: Input Blue — Integer #,##0 (Arial 10pt #0000FF)
# 6: Input Blue — Currency IDR #,##0 (Arial 10pt #0000FF)
# 7: Input Blue — Percent 0.0% (Arial 10pt #0000FF)
# 8: Formula Black — Integer #,##0 (Arial 10pt #000000)
# 9: Formula Black — Currency IDR #,##0 (Arial 10pt #000000)
# 10: Formula Black — Percent 0.0% (Arial 10pt #000000)
# 11: Link Green — Number #,##0 (Arial 10pt #008000)
# 12: Link Green — Percent 0.0% (Arial 10pt #008000)
# 13: Total Row — Bold Black Integer #,##0 (Top thin + Bottom double border, #F1F5F9 fill)
# 14: Total Row — Bold Black Currency IDR #,##0 (Top thin + Bottom double border, #F1F5F9 fill)
# 15: Total Row — Bold Black Percent 0.0% (Top thin + Bottom double border, #F1F5F9 fill)
# 16: Scenario Yellow Input — Blue #0000FF on #FEF9C3 Yellow Fill (Percent 0.0%)
# 17: Row Label Bold (#0F172A with bottom hairline border)

STYLE_MAP = {
    ("default", "text"): 0,
    ("title", "text"): 1,
    ("subtitle", "text"): 2,
    ("header", "text"): 3,
    ("label", "text"): 17,
    ("input", "text"): 4,
    ("input", "int"): 5,
    ("input", "idr"): 6,
    ("input", "pct"): 7,
    ("formula", "int"): 8,
    ("formula", "idr"): 9,
    ("formula", "pct"): 10,
    ("link", "int"): 11,
    ("link", "idr"): 11,
    ("link", "pct"): 12,
    ("total", "int"): 13,
    ("total", "idr"): 14,
    ("total", "pct"): 15,
    ("total", "text"): 13,
    ("scenario", "pct"): 16,
}

class _Worksheet:
    def __init__(self, name: str):
        self.name = name[:31]
        self.cells = {}  # (r, c) -> dict(type, val, formula, style_idx)
        self.col_widths = {}
        self.freeze_row = 5

    def set_col_widths(self, widths: dict[int, float]):
        for c, w in widths.items():
            self.col_widths[int(c)] = float(w)

    def write_text(self, r: int, c: int, text: str, role: str = "default"):
        s_idx = STYLE_MAP.get((role, "text"), 0)
        self.cells[(int(r), int(c))] = {"t": "inlineStr", "v": str(text), "f": None, "s": s_idx}

    def write_num(self, r: int, c: int, val: float, role: str = "input", fmt: str = "int"):
        s_idx = STYLE_MAP.get((role, fmt), 5)
        self.cells[(int(r), int(c))] = {"t": "n", "v": float(val), "f": None, "s": s_idx}

    def write_formula(self, r: int, c: int, formula: str, cached_val: float = 0.0, role: str = "formula", fmt: str = "int"):
        clean_f = str(formula).lstrip("=")
        for bad_fn in ("XLOOKUP(", "XMATCH(", "FILTER(", "UNIQUE(", "SEQUENCE("):
            if bad_fn in clean_f.upper():
                raise ValueError(f"Unsupported dynamic array function {bad_fn} in formula: {clean_f}")
        s_idx = STYLE_MAP.get((role, fmt), 8)
        self.cells[(int(r), int(c))] = {"t": "n", "v": float(cached_val), "f": clean_f, "s": s_idx}

    def to_xml_bytes(self) -> bytes:
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ET.register_namespace("", ns)
        root = ET.Element(f"{{{ns}}}worksheet")
        views = ET.SubElement(root, f"{{{ns}}}sheetViews")
        sv = ET.SubElement(views, f"{{{ns}}}sheetView", workbookViewId="0", showGridLines="1")
        if self.freeze_row and self.freeze_row > 1:
            ET.SubElement(sv, f"{{{ns}}}pane", ySplit=str(self.freeze_row - 1), topLeftCell=f"A{self.freeze_row}", activePane="bottomLeft", state="frozen")
        if self.col_widths:
            cols = ET.SubElement(root, f"{{{ns}}}cols")
            for c_idx in sorted(self.col_widths):
                ET.SubElement(cols, f"{{{ns}}}col", min=str(c_idx), max=str(c_idx), width=str(self.col_widths[c_idx]), customWidth="1")
        sd = ET.SubElement(root, f"{{{ns}}}sheetData")
        rows_map = {}
        for (r, c), info in self.cells.items():
            rows_map.setdefault(r, []).append((c, info))
        for r in sorted(rows_map):
            row_el = ET.SubElement(sd, f"{{{ns}}}row", r=str(r))
            for c, info in sorted(rows_map[r], key=lambda x: x[0]):
                ref = _cell_ref(r, c)
                c_attrib = {"r": ref, "s": str(info["s"])}
                if info["t"] == "inlineStr":
                    c_attrib["t"] = "inlineStr"
                    c_el = ET.SubElement(row_el, f"{{{ns}}}c", attrib=c_attrib)
                    is_el = ET.SubElement(c_el, f"{{{ns}}}is")
                    t_el = ET.SubElement(is_el, f"{{{ns}}}t")
                    t_el.text = info["v"]
                else:
                    c_el = ET.SubElement(row_el, f"{{{ns}}}c", attrib=c_attrib)
                    if info["f"]:
                        f_el = ET.SubElement(c_el, f"{{{ns}}}f")
                        f_el.text = info["f"]
                    v_el = ET.SubElement(c_el, f"{{{ns}}}v")
                    v_el.text = str(info["v"])
        return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
' + ET.tostring(root, encoding="utf-8")


class WorkbookBuilder:
    def __init__(self):
        self.sheets = []

    def add_sheet(self, name: str) -> _Worksheet:
        ws = _Worksheet(name)
        self.sheets.append(ws)
        return ws

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            ct = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            for i in range(1, len(self.sheets) + 1):
                ct += f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            ct += '</Types>'
            zf.writestr("[Content_Types].xml", ct.encode("utf-8"))
            zf.writestr("_rels/.rels", b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            wb = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            wb_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            for i, s in enumerate(self.sheets, start=1):
                wb += f'<sheet name="{s.name}" sheetId="{i}" r:id="rId{i}"/>'
                wb_rels += f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                zf.writestr(f"xl/worksheets/sheet{i}.xml", s.to_xml_bytes())
            wb += '</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'
            wb_rels += f'<Relationship Id="rId{len(self.sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
            zf.writestr("xl/workbook.xml", wb.encode("utf-8"))
            zf.writestr("xl/_rels/workbook.xml.rels", wb_rels.encode("utf-8"))

            styles_xml = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="3">
    <numFmt numFmtId="164" formatCode="#,##0;(#,##0);&quot;-&quot;"/>
    <numFmt numFmtId="165" formatCode="&quot;IDR &quot;#,##0;(&quot;IDR &quot;#,##0);&quot;-&quot;"/>
    <numFmt numFmtId="166" formatCode="0.0%"/>
  </numFmts>
  <fonts count="8">
    <font><sz val="10"/><color rgb="FF0F172A"/><name val="Arial"/></font>
    <font><b/><sz val="14"/><color rgb="FF0F172A"/><name val="Arial"/></font>
    <font><i/><sz val="9.5"/><color rgb="FF475569"/><name val="Arial"/></font>
    <font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>
    <font><sz val="10"/><color rgb="FF0000FF"/><name val="Arial"/></font>
    <font><sz val="10"/><color rgb="FF000000"/><name val="Arial"/></font>
    <font><sz val="10"/><color rgb="FF008000"/><name val="Arial"/></font>
    <font><b/><sz val="10"/><color rgb="FF000000"/><name val="Arial"/></font>
  </fonts>
  <fills count="5">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF0F172A"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFEF9C3"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="3">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left/><right/><top style="thin"><color rgb="FFE2E8F0"/></top><bottom style="thin"><color rgb="FFE2E8F0"/></bottom><diagonal/></border>
    <border><left/><right/><top style="thin"><color rgb="FF0F172A"/></top><bottom style="double"><color rgb="FF0F172A"/></bottom><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="18">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" applyFont="1"/>
    <xf numFmtId="0" fontId="2" fillId="0" borderId="0" applyFont="1"/>
    <xf numFmtId="0" fontId="3" fillId="2" borderId="1" applyFont="1" applyFill="1" applyBorder="1"/>
    <xf numFmtId="0" fontId="4" fillId="0" borderId="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="164" fontId="4" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="165" fontId="4" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="166" fontId="4" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="164" fontId="5" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="165" fontId="5" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="166" fontId="5" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="164" fontId="6" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="166" fontId="6" fillId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
    <xf numFmtId="164" fontId="7" fillId="3" borderId="2" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>
    <xf numFmtId="165" fontId="7" fillId="3" borderId="2" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>
    <xf numFmtId="166" fontId="7" fillId="3" borderId="2" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>
    <xf numFmtId="166" fontId="4" fillId="4" borderId="1" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>
    <xf numFmtId="0" fontId="7" fillId="0" borderId="1" applyFont="1" applyBorder="1"/>
  </cellXfs>
</styleSheet>"""
            zf.writestr("xl/styles.xml", styles_xml)
        return buf.getvalue()

    def emit_b64(self, filename: str = "Financial_Model.xlsx"):
        formula_cnt = sum(1 for s in self.sheets for info in s.cells.values() if info.get("f"))
        if formula_cnt == 0:
            raise AssertionError("XLSX QA Gate Failed: Workbook must contain live Excel formulas (SUM/IFERROR/INDEX/MATCH)!")
        raw = self.to_bytes()
        b64_str = base64.b64encode(raw).decode("ascii")
        print(f"[QA_GATE_PASSED] Verified {len(self.sheets)} tabs, {formula_cnt} live formulas, {len(raw)} bytes in-memory (zero disk .xlsx residue) for {filename}")
        print("B64_XLSX:" + b64_str)
```
