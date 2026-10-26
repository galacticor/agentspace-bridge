# Knowledge Reference 1: Zero-Dependency `pptx_lxml_wrapper` Engine (`presentation_designer`)

> **CRITICAL SANDBOX & ONEDRIVE UPLOAD RULE FOR `.pptx` (ZERO `ContentBytes` / `pptx_payload.txt` BRIDGE):**
> 1. Always save `pptx_lxml_wrapper.py` to `/home/bard/pptx_lxml_wrapper.py` inside `file_and_coding_agent` and import `create_widescreen_prs`, `add_header_and_footer`, `add_top_accent_card`, `add_metric_callout`, `add_tufte_table`, `add_native_column_chart`, `add_roadmap_waves`, `add_callout_strip`, and `add_appendix_table_slide`.
> 2. **True Native Editable OOXML Charts (`<c:chartSpace>` in `ppt/charts/chart{k}.xml`):**
>    - `add_native_column_chart(slide, x, y, w, h, categories, series_list, chart_type="col", number_format="0.0", show_legend=True)` emits real editable PowerPoint `<c:chartSpace>` XML parts supporting:
>      - Clustered Column (`chart_type="col"`), Horizontal Bar (`chart_type="bar"`), Line (`chart_type="line"`), and **Dual-Axis Combo (`chart_type="combo"`)** by passing `"line"` as the 4th tuple element in any secondary-axis series: `("3ID Loan Rev (IDR B)", [24.7, 28.2, 26.2, 30.8, 33.9], C_TEAL, "line")`.
>      - Positive and negative values (`-1106`, `-2716`, `-1704`) plotted naturally across zero.
> 3. **100% Outline Fidelity & Smart Table Pagination (`add_appendix_table_slide`):**
>    - When the user prompt includes an explicit **Slide-by-Slide Outline** (e.g., Netra Section 5A), adopt the exact slide count, verbatim McKinsey Action Titles (auto-scaled `18pt`/`16pt`/`14.5pt` up to `118` chars), and exact chart types (`combo`, `col`, `bar`, `line`).
>    - When a slide combines a Chart or 3-Wave Roadmap (`add_roadmap_waves`) with a granular table of `> 8` rows (e.g., a 14-row Brand × Cohort × ARPU Tier breakdown), display a **5–6 row Executive Summary Table** on the main slide so nothing is cramped or dropped, and call `add_appendix_table_slide(prs, slide_num, total_slides, tracker, action_title, subtitle, headers, full_rows, ...)` to append the **complete granular table on an Appendix Backup Slide**!
> 4. **Mandatory `onedrive_agent__upload_file` Parameters (`HasBytes: false`, `ContentBytes: ""`):**
>    - `prs.save("<DeckName>.pptx")` writes the raw `.pptx` binary to `pptx_payload.txt` (`/home/bard/pptx_payload.txt`).
>    - Always pass `FileName: "<DeckName>.pptx"`, `InputFileName: "pptx_payload.txt"`, `HasBytes: false`, `ContentBytes: ""` (leave completely blank!).

```python
# pptx_lxml_wrapper.py — Self-Contained Zero-Dependency OOXML .pptx Micro-Engine (True Native <c:chartSpace> Charts + Iterative Visual QA Gate)
import os, zipfile, base64, math, html
try:
    from lxml import etree; _LXML = True
except ImportError:
    import xml.etree.ElementTree as etree; _LXML = False

O = "http://schemas.openxmlformats.org"
P_NS, A_NS, R_NS = f"{O}/presentationml/2006/main", f"{O}/drawingml/2006/main", f"{O}/officeDocument/2006/relationships"
C_NS = f"{O}/drawingml/2006/chart"
A_TBL_URI, PK_R, CT_NS = f"{O}/drawingml/2006/table", f"{O}/package/2006/relationships", f"{O}/package/2006/content-types"
if not _LXML:
    for k, v in (("a", A_NS), ("r", R_NS), ("p", P_NS), ("c", C_NS)): etree.register_namespace(k, v)
NSMAP, EMU = {"a": A_NS, "r": R_NS, "p": P_NS}, 914400
def Inches(v): return float(v)
def Pt(v): return float(v)
def RGBColor(r, g, b): return f"{r:02X}{g:02X}{b:02X}"
def _hex(c, d="0F172A"): return str(c).lstrip("#").upper() if c else d

class PP_ALIGN: LEFT="l"; CENTER="ctr"; RIGHT="r"
class MSO_ANCHOR: TOP="t"; MIDDLE="ctr"; BOTTOM="b"
class MSO_SHAPE: RECTANGLE="rect"; ROUNDED_RECTANGLE="roundRect"
class XL_CHART_TYPE: COLUMN_CLUSTERED="col"; BAR_CLUSTERED="bar"; LINE="line"; COMBO="combo"

C_BG, C_SURFACE, C_TINT = "FFFFFF", "F8FAFC", "F1F5F9"
C_TINT_ROSE, C_TINT_INDIGO, C_TINT_TEAL = "FFF1F2", "EEF2FF", "F0FDFA"
C_DARK, C_SLATE, C_MUTED, C_BORDER = "0F172A", "334155", "64748B", "E2E8F0"
C_CORAL, C_INDIGO, C_TEAL, C_AMBER, C_WHITE = "E11D48", "4840E6", "0D9488", "D97706", "FFFFFF"
FONT_HEAD, FONT_BODY, FONT_MONO = "Arial", "Calibri", "Consolas"

_C_TAGS = "".join(f"<a:{t}><a:srgbClr val=\"{v}\"/></a:{t}>" for t, v in (("dk1","0F172A"),("lt1","FFFFFF"),("dk2","334155"),("lt2","F8FAFC"),("accent1","E11D48"),("accent2","4840E6"),("accent3","0D9488"),("accent4","D97706"),("accent5","0284C7"),("accent6","64748B"),("hlink","4840E6"),("folHlink","64748B")))
_SF3 = "<a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill>" * 3
_LN_S = "".join(f"<a:ln w=\"{w}\" cap=\"flat\" cmpd=\"sng\" algn=\"ctr\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/></a:ln>" for w in (9525, 19050, 25400))
THEME_XML = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="{A_NS}" name="Exec"><a:themeElements><a:clrScheme name="Exec">{_C_TAGS}</a:clrScheme><a:fontScheme name="ExecF"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme><a:fmtScheme name="ExecFmt"><a:fillStyleLst>{_SF3}</a:fillStyleLst><a:lnStyleLst>{_LN_S}</a:lnStyleLst><a:effectStyleLst>{"<a:effectStyle><a:effectLst/></a:effectStyle>"*3}</a:effectStyleLst><a:bgFillStyleLst>{_SF3}</a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>'

class _Prs:
    def __init__(self): self.slides, self._id, self._qa, self._charts = [], 2, [], []

    def run_visual_qa(self, render_png_dir="/home/bard"):
        issues = []
        for s_idx, items in enumerate(self._qa, 1):
            fids = set()
            ctrs = [it for it in items if it["kind"] in ("card", "metric", "callout", "table", "chart", "bullets")]
            for a in items:
                k, x, y, w, h, lbl = a["kind"], a["x"], a["y"], a["w"], a["h"], a["label"]
                if k in ("bg", "rule", "accent_bar"): continue
                if k == "title" and len(lbl) > 118:
                    issues.append(f"Slide {s_idx} [TITLE_OVERFLOW]: Title is {len(lbl)} chars (>118 max). Shorten to <=112 chars."); fids.add(id(a))
                if k not in ("header", "title", "subtitle", "footer") and (y + h > 7.06 or x + w > 12.95 or x < 0.20 or y < 1.12):
                    issues.append(f"Slide {s_idx} [BOUNDARY_BREACH]: {k} '{lbl[:28]}' (x={x:.2f},y={y:.2f},w={w:.2f},h={h:.2f},bottom={y+h:.2f}) breaches body safe zone (y in 1.14..7.05). Reduce h or move y up."); fids.add(id(a))
                if k == "table" and (h / max(a.get("nrows", 2), 1)) < 0.21:
                    issues.append(f"Slide {s_idx} [TABLE_CRAMPED]: Table '{lbl[:24]}' row height < 0.21\" ({a.get('nrows',2)} rows in h={h:.2f}\"). If >8 rows on a multi-element slide, show a 5-7 row summary table on the main slide and call add_appendix_table_slide() for the full granular table!"); fids.add(id(a))
                if k in ("text", "bullets", "callout"):
                    fs = a.get("fs", 10.0)
                    cpl = max(12.0, (w - 0.12) * 72.0 / max(fs * 0.54, 4.0))
                    req_h = sum(max(1, math.ceil(len(ln) / cpl)) for ln in str(lbl).split("\n")) * (fs * 1.32 / 72.0)
                    if req_h > h * 1.28 and h < 4.5:
                        issues.append(f"Slide {s_idx} [TEXT_OVERFLOW]: {k} '{lbl[:28]}...' needs h>={req_h:.2f}\" but box h={h:.2f}\". Increase h or shorten text."); fids.add(id(a))
            for i in range(len(ctrs)):
                for j in range(i + 1, len(ctrs)):
                    a, b = ctrs[i], ctrs[j]
                    area = max(0.0, min(a["x"]+a["w"], b["x"]+b["w"]) - max(a["x"], b["x"])) * max(0.0, min(a["y"]+a["h"], b["y"]+b["h"]) - max(a["y"], b["y"]))
                    aa, ba = a["w"]*a["h"], b["w"]*b["h"]
                    if area > 0.04 and not (a["kind"] == "card" and area >= 0.85 * ba) and not (b["kind"] == "card" and area >= 0.85 * aa):
                        issues.append(f"Slide {s_idx} [OVERLAP]: {a['kind']} '{a['label'][:20]}' (y={a['y']:.2f}..{a['y']+a['h']:.2f}) overlaps {b['kind']} '{b['label'][:20]}' (y={b['y']:.2f}..{b['y']+b['h']:.2f}). Adjust y/h."); fids.add(id(a)); fids.add(id(b))
        return issues

    def save(self, out_path="output.pptx", strict_qa=True):
        bp, qa = out_path or "output.pptx", self.run_visual_qa()
        if qa:
            print(f"[QA_GATE_FAILED] {len(qa)} issue(s) found! Fix in your Python script and re-run:")
            for iss in qa: print("  - " + iss)
            if strict_qa: raise RuntimeError(f"Visual QA Gate blocked export ({len(qa)} issues). Fix coordinates above and re-run!")
        else: print(f"[QA_GATE_PASSED] All {len(self.slides)} slides passed Visual & Coordinate QA!")
        hdr, P_M = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "application/vnd.openxmlformats-officedocument.presentationml"
        sp0 = '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>'
        rels = [f'{hdr}<Relationships xmlns="{PK_R}">'] + [f'<Relationship Id="rId{k}" Type="{R_NS}/{t}" Target="{tg}"/>' for k, t, tg in (("M","slideMaster","slideMasters/slideMaster1.xml"),("Th","theme","theme/theme1.xml"),("PP","presProps","presProps.xml"),("VP","viewProps","viewProps.xml"),("TS","tableStyles","tableStyles.xml"))]
        s_ids, ct = [], [f'{hdr}<Types xmlns="{CT_NS}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'] + [f'<Override PartName="{pn}" ContentType="{cty}+xml"/>' for pn, cty in (("/ppt/presentation.xml",f"{P_M}.presentation.main"),("/ppt/slideMasters/slideMaster1.xml",f"{P_M}.slideMaster"),("/ppt/slideLayouts/slideLayout1.xml",f"{P_M}.slideLayout"),("/ppt/theme/theme1.xml","application/vnd.openxmlformats-officedocument.theme"),("/ppt/presProps.xml",f"{P_M}.presProps"),("/ppt/viewProps.xml",f"{P_M}.viewProps"),("/ppt/tableStyles.xml",f"{P_M}.tableStyles"),("/docProps/core.xml","application/vnd.openxmlformats-package.core-properties"),("/docProps/app.xml","application/vnd.openxmlformats-officedocument.extended-properties"))]
        with zipfile.ZipFile(bp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.writestr("_rels/.rels", f'{hdr}<Relationships xmlns="{PK_R}"><Relationship Id="rId1" Type="{R_NS}/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="{O}/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="{R_NS}/extended-properties" Target="docProps/app.xml"/></Relationships>')
            z.writestr("docProps/core.xml", f'{hdr}<cp:coreProperties xmlns:cp="{O}/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>IOH Executive Deck</dc:title></cp:coreProperties>')
            z.writestr("docProps/app.xml", f'{hdr}<Properties xmlns="{O}/officeDocument/2006/extended-properties"><Application>Microsoft Office PowerPoint</Application><Slides>{len(self.slides)}</Slides></Properties>')
            z.writestr("ppt/theme/theme1.xml", THEME_XML)
            z.writestr("ppt/presProps.xml", f'{hdr}<p:presentationPr xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}"/>')
            z.writestr("ppt/viewProps.xml", f'{hdr}<p:viewPr xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}"><p:normalViewPr><p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/></p:normalViewPr><p:slideViewPr><p:cSldViewPr><p:cViewPr varScale="1"><p:scale><a:sx n="100" d="100"/><a:sy n="100" d="100"/></p:scale><p:origin x="0" y="0"/></p:cViewPr></p:cSldViewPr></p:slideViewPr></p:viewPr>')
            z.writestr("ppt/tableStyles.xml", f'{hdr}<a:tblStyleLst xmlns:a="{A_NS}" def="{{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}}"/>')
            z.writestr("ppt/slideMasters/slideMaster1.xml", f'{hdr}<p:sldMaster xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}">{sp0}<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst></p:sldMaster>')
            z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", f'{hdr}<Relationships xmlns="{PK_R}"><Relationship Id="rId1" Type="{R_NS}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="{R_NS}/theme" Target="../theme/theme1.xml"/></Relationships>')
            z.writestr("ppt/slideLayouts/slideLayout1.xml", f'{hdr}<p:sldLayout xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}" type="blank">{sp0}</p:sldLayout>')
            z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", f'{hdr}<Relationships xmlns="{PK_R}"><Relationship Id="rId1" Type="{R_NS}/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>')
            for c_idx, c_xml in self._charts:
                ct.append(f'<Override PartName="/ppt/charts/chart{c_idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>')
                z.writestr(f"ppt/charts/chart{c_idx}.xml", c_xml)
            for i, s_item in enumerate(self.slides, 1):
                sld, _, s_c_rels = s_item[0], s_item[1], (s_item[2] if len(s_item) > 2 else [])
                rels.append(f'<Relationship Id="rId{i}" Type="{R_NS}/slide" Target="slides/slide{i}.xml"/>')
                s_ids.append(f'<p:sldId id="{255+i}" r:id="rId{i}"/>')
                ct.append(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="{P_M}.slide+xml"/>')
                xb = etree.tostring(sld, xml_declaration=True, encoding="UTF-8") if _LXML else (hdr.encode("utf-8") + etree.tostring(sld, encoding="utf-8"))
                z.writestr(f"ppt/slides/slide{i}.xml", xb)
                c_rel_str = "".join(f'<Relationship Id="{cr_id}" Type="{R_NS}/chart" Target="../charts/chart{c_idx}.xml"/>' for cr_id, c_idx in s_c_rels)
                z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", f'{hdr}<Relationships xmlns="{PK_R}"><Relationship Id="rId1" Type="{R_NS}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>{c_rel_str}</Relationships>')
            z.writestr("[Content_Types].xml", "".join(ct) + "</Types>")
            z.writestr("ppt/_rels/presentation.xml.rels", "".join(rels) + "</Relationships>")
            z.writestr("ppt/presentation.xml", f'{hdr}<p:presentation xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}" saveSubsetFonts="1"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rIdM"/></p:sldMasterIdLst><p:sldIdLst>{"".join(s_ids)}</p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')
        with open(bp, "rb") as f:
            raw_pptx = f.read()
        with open("pptx_payload.txt", "wb") as f_txt:
            f_txt.write(raw_pptx)
        if os.path.isdir("/home/bard"):
            with open("/home/bard/pptx_payload.txt", "wb") as f_txt2:
                f_txt2.write(raw_pptx)
        print(f"[PPTX_PAYLOAD_ATTACHED] Wrote {len(raw_pptx)} raw binary bytes to pptx_payload.txt (use InputFileName='pptx_payload.txt', HasBytes=false, ContentBytes='')")
        return f"pptx_payload.txt ({len(raw_pptx)} bytes)"

def create_widescreen_prs(): return _Prs()
def zero_tf_margins(tf, wrap=True, anchor="t"): return tf
def set_cell_border(*a, **k): pass

def _rec(slide, kind, x, y, w, h, label="", fill=None, **kw):
    d = {"kind": kind, "x": float(x), "y": float(y), "w": float(w), "h": float(h), "label": str(label), "fill": fill}
    d.update(kw); slide[3].append(d)

def add_blank_slide(prs, bg_color=C_SURFACE):
    sld = etree.Element(f"{{{P_NS}}}sld", nsmap=NSMAP) if _LXML else etree.Element(f"{{{P_NS}}}sld")
    spTree = etree.SubElement(etree.SubElement(sld, f"{{{P_NS}}}cSld"), f"{{{P_NS}}}spTree")
    nv = etree.SubElement(spTree, f"{{{P_NS}}}nvGrpSpPr")
    etree.SubElement(nv, f"{{{P_NS}}}cNvPr", id="1", name=""); etree.SubElement(nv, f"{{{P_NS}}}cNvGrpSpPr"); etree.SubElement(nv, f"{{{P_NS}}}nvPr")
    xf = etree.SubElement(etree.SubElement(spTree, f"{{{P_NS}}}grpSpPr"), f"{{{A_NS}}}xfrm")
    for tag in ("off", "ext", "chOff", "chExt"): etree.SubElement(xf, f"{{{A_NS}}}{tag}", **({"x":"0","y":"0"} if "Off" in tag or tag=="off" else {"cx":"0","cy":"0"}))
    s_qa, s_crels = [], []; prs._qa.append(s_qa); slide = (sld, spTree, prs, s_qa, s_crels); prs.slides.append((sld, spTree, s_crels))
    _sp(slide, 0, 0, 13.333, 7.5, fill=bg_color, b_col=None, prst="rect", _qa_kind="bg")
    return slide

def _sp(slide, x, y, w, h, fill=None, b_col=None, b_pt=0.75, prst="rect", rad=0.04, paras=(), align="l", anchor="t", _qa_kind=None, _qa_label=None):
    spTree, prs = slide[1], slide[2]; prs._id += 1
    sp = etree.SubElement(spTree, f"{{{P_NS}}}sp"); nv = etree.SubElement(sp, f"{{{P_NS}}}nvSpPr")
    etree.SubElement(nv, f"{{{P_NS}}}cNvPr", id=str(prs._id), name=f"s{prs._id}"); etree.SubElement(nv, f"{{{P_NS}}}cNvSpPr"); etree.SubElement(nv, f"{{{P_NS}}}nvPr")
    spPr = etree.SubElement(sp, f"{{{P_NS}}}spPr"); xf = etree.SubElement(spPr, f"{{{A_NS}}}xfrm")
    etree.SubElement(xf, f"{{{A_NS}}}off", x=str(int(float(x)*EMU)), y=str(int(float(y)*EMU))); etree.SubElement(xf, f"{{{A_NS}}}ext", cx=str(int(float(w)*EMU)), cy=str(int(float(h)*EMU)))
    av = etree.SubElement(etree.SubElement(spPr, f"{{{A_NS}}}prstGeom", prst=prst), f"{{{A_NS}}}avLst")
    if prst == "roundRect": etree.SubElement(av, f"{{{A_NS}}}gd", name="adj", fmla=f"val {int(rad*100000)}")
    if fill: etree.SubElement(etree.SubElement(spPr, f"{{{A_NS}}}solidFill"), f"{{{A_NS}}}srgbClr", val=_hex(fill))
    else: etree.SubElement(spPr, f"{{{A_NS}}}noFill")
    ln = etree.SubElement(spPr, f"{{{A_NS}}}ln", w=str(int(float(b_pt)*12700)))
    if b_col: etree.SubElement(etree.SubElement(ln, f"{{{A_NS}}}solidFill"), f"{{{A_NS}}}srgbClr", val=_hex(b_col))
    else: etree.SubElement(ln, f"{{{A_NS}}}noFill")
    tx = etree.SubElement(sp, f"{{{P_NS}}}txBody")
    etree.SubElement(tx, f"{{{A_NS}}}bodyPr", wrap="square", lIns="0", tIns="0", rIns="0", bIns="0", anchor=anchor); etree.SubElement(tx, f"{{{A_NS}}}lstStyle")
    if not paras: etree.SubElement(tx, f"{{{A_NS}}}p")
    all_txt, max_fs = [], 10.0
    for p_runs in paras:
        p = etree.SubElement(tx, f"{{{A_NS}}}p"); etree.SubElement(p, f"{{{A_NS}}}pPr", algn=align if align in ("l","ctr","r") else "l")
        p_str = []
        for txt, sz, bold, col, fn in p_runs:
            max_fs = max(max_fs, float(sz)); p_str.append(str(txt))
            r = etree.SubElement(p, f"{{{A_NS}}}r"); rPr = etree.SubElement(r, f"{{{A_NS}}}rPr", lang="en-US", sz=str(int(float(sz)*100)), b="1" if bold else "0", dirty="0")
            etree.SubElement(etree.SubElement(rPr, f"{{{A_NS}}}solidFill"), f"{{{A_NS}}}srgbClr", val=_hex(col)); etree.SubElement(rPr, f"{{{A_NS}}}latin", typeface=fn or FONT_BODY)
            etree.SubElement(r, f"{{{A_NS}}}t").text = str(txt)
        all_txt.append("".join(p_str))
    if _qa_kind != "skip":
        _rec(slide, _qa_kind or ("text" if all_txt else "card"), x, y, w, h, _qa_label if _qa_label is not None else "\n".join(all_txt), fill=fill, fs=max_fs)
    return sp

def add_rounded_box(slide, x, y, w, h, fill_color=C_SURFACE, border_color=C_BORDER, border_pt=0.75, radius=0.04):
    return _sp(slide, x, y, w, h, fill=fill_color, b_col=border_color, b_pt=border_pt, prst="roundRect" if radius else "rect", rad=radius, _qa_kind="card", _qa_label="box")

def add_top_accent_card(slide, x, y, w, h, accent_color=C_CORAL, bg_color=C_WHITE, border_color=C_BORDER):
    return _sp(slide, x, y, w, h, fill=bg_color, b_col=border_color, b_pt=0.75, _qa_kind="card", _qa_label="accent_card"), _sp(slide, x, y, w, 0.05, fill=accent_color, b_col=None, _qa_kind="accent_bar")

def add_textbox(slide, x, y, w, h, text, font_size=11, bold=False, color=C_DARK, font_name=FONT_BODY, align=PP_ALIGN.LEFT, _qa_kind="text"):
    return _sp(slide, x, y, w, h, paras=[[(text, font_size, bold, color, font_name)]], align=align, _qa_kind=_qa_kind, _qa_label=text)

def add_bullet_list(slide, x, y, w, h, items, font_size=10.0, lead_color=C_DARK, body_color=C_SLATE, space_after_pt=5.0):
    paras = [[(f"▪ {ld}: ", font_size, True, lead_color, FONT_BODY), (str(bd), font_size, False, body_color, FONT_BODY)] for ld, bd in items]
    return _sp(slide, x, y, w, h, paras=paras, _qa_kind="bullets", _qa_label="\n".join(f"▪ {ld}: {bd}" for ld, bd in items))

def add_metric_callout(slide, x, y, w, h, eyebrow, hero_val, sub_label, accent=C_CORAL, bg_color=C_WHITE):
    _sp(slide, x, y, w, h, fill=bg_color, b_col=C_BORDER, b_pt=0.75, _qa_kind="metric", _qa_label=f"{eyebrow}: {hero_val}")
    _sp(slide, x, y, w, 0.05, fill=accent, b_col=None, _qa_kind="accent_bar")
    _sp(slide, x+0.14, y+0.12, w-0.28, 0.22, paras=[[(eyebrow, 8.5, True, C_MUTED, FONT_HEAD)]], _qa_kind="skip")
    h_fs = min(22.0, max(13.0, (w - 0.30) * 72.0 / max(len(str(hero_val)) * 0.62, 1.0)))
    _sp(slide, x+0.14, y+0.34, w-0.28, 0.48, paras=[[(hero_val, h_fs, True, accent, FONT_HEAD)]], _qa_kind="skip")
    _sp(slide, x+0.14, y+0.84, w-0.28, max(0.25, h-0.90), paras=[[(sub_label, 9.0, False, C_SLATE, FONT_BODY)]], _qa_kind="skip")

def add_header_and_footer(slide, slide_num, tracker, action_title, subtitle, source_note="Source: IOH Enterprise Analytics", total_slides=8):
    t_len = len(str(action_title or ""))
    t_fs = 18.0 if t_len <= 82 else (16.0 if t_len <= 96 else 14.5)
    add_textbox(slide, 0.55, 0.28, 10.0, 0.20, tracker, 8.5, True, C_CORAL, FONT_HEAD, _qa_kind="header")
    add_textbox(slide, 0.55, 0.48, 12.23, 0.36, action_title, t_fs, True, C_DARK, FONT_HEAD, _qa_kind="title")
    add_textbox(slide, 0.55, 0.84, 12.23, 0.24, subtitle, 10.5, False, C_MUTED, FONT_BODY, _qa_kind="subtitle")
    _sp(slide, 0.55, 1.12, 12.23, 0.01, fill=C_BORDER, b_col=None, _qa_kind="rule"); _sp(slide, 0.55, 7.08, 12.23, 0.008, fill=C_BORDER, b_col=None, _qa_kind="rule")
    add_textbox(slide, 0.55, 7.13, 11.2, 0.22, source_note, 8.0, False, C_MUTED, FONT_BODY, _qa_kind="footer")
    add_textbox(slide, 11.8, 7.13, 0.98, 0.22, f"{slide_num} / {total_slides}", 8.5, True, C_SLATE, FONT_HEAD, PP_ALIGN.RIGHT, _qa_kind="footer")

def add_callout_strip(slide, x, y, w, h, lead_in, body_text, accent=C_INDIGO, bg_color=C_TINT_INDIGO):
    _sp(slide, x, y, w, h, fill=bg_color, b_col=C_BORDER, b_pt=0.5, _qa_kind="callout", _qa_label=f"{lead_in}: {body_text}")
    _sp(slide, x, y, 0.06, h, fill=accent, b_col=None, _qa_kind="accent_bar")
    return _sp(slide, x+0.16, y+0.08, w-0.28, h-0.16, paras=[[(f"{lead_in}: ", 9.5, True, accent, FONT_HEAD), (body_text, 9.5, False, C_DARK, FONT_BODY)]], anchor="ctr", _qa_kind="skip")

def add_roadmap_waves(slide, x, y, w, h, waves):
    n = max(len(waves), 1); gap = 0.22; cw = (w - gap * (n - 1)) / n
    for i, wv in enumerate(waves):
        wx = x + i * (cw + gap)
        phase, title, bullets, accent = wv[0], wv[1], wv[2], (wv[3] if len(wv) > 3 else [C_CORAL, C_INDIGO, C_TEAL][i % 3])
        _sp(slide, wx, y, cw, h, fill=C_WHITE, b_col=C_BORDER, b_pt=0.75, _qa_kind="card", _qa_label=f"{phase}: {title}")
        _sp(slide, wx, y, cw, 0.05, fill=accent, b_col=None, _qa_kind="accent_bar")
        _sp(slide, wx+0.12, y+0.10, cw-0.24, 0.20, paras=[[(str(phase), 8.5, True, accent, FONT_HEAD)]], _qa_kind="skip")
        _sp(slide, wx+0.12, y+0.30, cw-0.24, 0.28, paras=[[(str(title), 10.5, True, C_DARK, FONT_HEAD)]], _qa_kind="skip")
        b_paras = [[(f"▪ {ld}: ", 8.8, True, C_DARK, FONT_BODY), (str(bd), 8.8, False, C_SLATE, FONT_BODY)] if isinstance(b_it, (list, tuple)) and len(b_it)>=2 else [(f"▪ {b_it}", 8.8, False, C_SLATE, FONT_BODY)] for b_it in bullets for ld, bd in ([b_it[:2]] if isinstance(b_it, (list, tuple)) and len(b_it)>=2 else [(None, None)])]
        _sp(slide, wx+0.12, y+0.60, cw-0.24, max(0.30, h-0.66), paras=b_paras, _qa_kind="skip")

def add_tufte_table(slide, x, y, w, h, headers, rows, col_widths=None, num_cols=None, highlight_rows=None, bold_rows=None, accent_cols=None, font_size=9.5, header_bg=C_DARK, header_fg=C_WHITE):
    spTree, prs = slide[1], slide[2]; prs._id += 1
    _rec(slide, "table", x, y, w, h, label=" | ".join(str(c) for c in headers[:4]), fill=C_WHITE, nrows=len(rows)+1)
    num_cols, highlight_rows, bold_rows, accent_cols = set(num_cols or []), highlight_rows or {}, set(bold_rows or []), accent_cols or {}
    nc = max(len(headers), 1); cws = col_widths if (col_widths and len(col_widths)==nc) else [w/nc]*nc; rh = int((h / (len(rows) + 1)) * EMU)
    gf = etree.SubElement(spTree, f"{{{P_NS}}}graphicFrame"); nv = etree.SubElement(gf, f"{{{P_NS}}}nvGraphicFramePr")
    etree.SubElement(nv, f"{{{P_NS}}}cNvPr", id=str(prs._id), name=f"Table {prs._id}")
    etree.SubElement(etree.SubElement(nv, f"{{{P_NS}}}cNvGraphicFramePr"), f"{{{A_NS}}}graphicFrameLocks", noGrp="1"); etree.SubElement(nv, f"{{{P_NS}}}nvPr")
    xf = etree.SubElement(gf, f"{{{P_NS}}}xfrm"); etree.SubElement(xf, f"{{{A_NS}}}off", x=str(int(x*EMU)), y=str(int(y*EMU))); etree.SubElement(xf, f"{{{A_NS}}}ext", cx=str(int(w*EMU)), cy=str(int(h*EMU)))
    tbl = etree.SubElement(etree.SubElement(etree.SubElement(gf, f"{{{A_NS}}}graphic"), f"{{{A_NS}}}graphicData", uri=A_TBL_URI), f"{{{A_NS}}}tbl")
    etree.SubElement(tbl, f"{{{A_NS}}}tblPr", firstRow="0", bandRow="0"); grid = etree.SubElement(tbl, f"{{{A_NS}}}tblGrid")
    for cw in cws: etree.SubElement(grid, f"{{{A_NS}}}gridCol", w=str(int(cw*EMU)))
    def _c(tr, txt, b, fg, bg, al, tcol, tpt, bcol, bpt, fn):
        tc = etree.SubElement(tr, f"{{{A_NS}}}tc"); tx = etree.SubElement(tc, f"{{{A_NS}}}txBody")
        etree.SubElement(tx, f"{{{A_NS}}}bodyPr"); etree.SubElement(tx, f"{{{A_NS}}}lstStyle")
        p = etree.SubElement(tx, f"{{{A_NS}}}p"); etree.SubElement(p, f"{{{A_NS}}}pPr", algn=al)
        r = etree.SubElement(p, f"{{{A_NS}}}r"); rPr = etree.SubElement(r, f"{{{A_NS}}}rPr", lang="en-US", sz=str(int(font_size*100)), b="1" if b else "0", dirty="0")
        etree.SubElement(etree.SubElement(rPr, f"{{{A_NS}}}solidFill"), f"{{{A_NS}}}srgbClr", val=_hex(fg)); etree.SubElement(rPr, f"{{{A_NS}}}latin", typeface=fn)
        etree.SubElement(r, f"{{{A_NS}}}t").text = str(txt)
        tcPr = etree.SubElement(tc, f"{{{A_NS}}}tcPr", marL="64008", marR="64008", marT="36576", marB="36576", anchor="ctr")
        for tg, cl, pt in (("lnL",None,0),("lnR",None,0),("lnT",tcol,tpt),("lnB",bcol,bpt)):
            ln = etree.SubElement(tcPr, f"{{{A_NS}}}{tg}", w=str(int(pt*12700)))
            if cl: etree.SubElement(etree.SubElement(ln, f"{{{A_NS}}}solidFill"), f"{{{A_NS}}}srgbClr", val=_hex(cl))
            else: etree.SubElement(ln, f"{{{A_NS}}}noFill")
        sf = etree.SubElement(tcPr, f"{{{A_NS}}}solidFill"); etree.SubElement(sf, f"{{{A_NS}}}srgbClr", val=_hex(bg))
    htr = etree.SubElement(tbl, f"{{{A_NS}}}tr", h=str(rh))
    for ci, htxt in enumerate(headers): _c(htr, htxt, True, header_fg, header_bg, "r" if ci in num_cols else "l", "0F172A", 1.5, "0F172A", 1.5, FONT_HEAD)
    for ri, rvals in enumerate(rows):
        rtr = etree.SubElement(tbl, f"{{{A_NS}}}tr", h=str(rh)); rbg = highlight_rows.get(ri, C_WHITE if ri % 2 == 0 else C_SURFACE); ib = ri in bold_rows
        bc, bw = ("0F172A", 1.25) if (ib or ri==len(rows)-1) else ("E2E8F0", 0.5)
        for ci, val in enumerate(rvals[:nc]): _c(rtr, val, ib or ci==0 or ci in accent_cols, accent_cols.get(ci, C_DARK), rbg, "r" if ci in num_cols else "l", None, 0, bc, bw, FONT_BODY)
    return tbl

def add_appendix_table_slide(prs, slide_num, total_slides, tracker, action_title, subtitle, headers, rows, col_widths=None, num_cols=None, highlight_rows=None, bold_rows=None, accent_cols=None, callout_lead="Granular Audit Traceability", callout_body="Complete un-truncated cohort breakdown from BigQuery snapshot mart.", source_note="Source: IOH Enterprise Analytics"):
    s = add_blank_slide(prs)
    add_header_and_footer(s, slide_num, tracker, action_title, subtitle, source_note=source_note, total_slides=total_slides)
    tbl_h = min(5.00, max(2.40, (len(rows) + 1) * 0.30))
    add_tufte_table(s, 0.55, 1.22, 12.23, tbl_h, headers, rows, col_widths=col_widths, num_cols=num_cols, highlight_rows=highlight_rows, bold_rows=bold_rows, accent_cols=accent_cols, font_size=9.0)
    add_callout_strip(s, 0.55, 6.38, 12.23, 0.58, callout_lead, callout_body, accent=C_INDIGO, bg_color=C_TINT_INDIGO)
    return s

def add_native_column_chart(slide, x, y, w, h, categories, series_list, chart_type="col", number_format="0.0", show_legend=True, secondary_series=None):
    spTree, prs, s_crels = slide[1], slide[2], slide[4]; prs._id += 1
    _sp(slide, x, y, w, h, fill=C_WHITE, b_col=C_BORDER, b_pt=0.75, _qa_kind="chart", _qa_label="Chart: " + ", ".join(str(s[0]) for s in series_list))
    c_idx = len(prs._charts) + 1; r_id = f"rIdC{c_idx}"; s_crels.append((r_id, c_idx))
    gf = etree.SubElement(spTree, f"{{{P_NS}}}graphicFrame"); nv = etree.SubElement(gf, f"{{{P_NS}}}nvGraphicFramePr")
    etree.SubElement(nv, f"{{{P_NS}}}cNvPr", id=str(prs._id), name=f"Chart {c_idx}")
    etree.SubElement(etree.SubElement(nv, f"{{{P_NS}}}cNvGraphicFramePr"), f"{{{A_NS}}}graphicFrameLocks", noGrp="1"); etree.SubElement(nv, f"{{{P_NS}}}nvPr")
    xf = etree.SubElement(gf, f"{{{P_NS}}}xfrm")
    etree.SubElement(xf, f"{{{A_NS}}}off", x=str(int((float(x)+0.06)*EMU)), y=str(int((float(y)+0.06)*EMU)))
    etree.SubElement(xf, f"{{{A_NS}}}ext", cx=str(int((float(w)-0.12)*EMU)), cy=str(int((float(h)-0.12)*EMU)))
    gd = etree.SubElement(etree.SubElement(gf, f"{{{A_NS}}}graphic"), f"{{{A_NS}}}graphicData", uri=C_NS)
    ch_el = etree.SubElement(gd, f"{{{C_NS}}}chart", nsmap={"c": C_NS, "r": R_NS}) if _LXML else etree.SubElement(gd, f"{{{C_NS}}}chart")
    ch_el.set(f"{{{R_NS}}}id", r_id)
    ct_mode = str(chart_type or "col").lower()
    pri_s, sec_s = [], list(secondary_series or [])
    for s in series_list:
        if len(s) >= 4 and str(s[3]).lower() in ("line", "sec", "secondary", "true", "1"): sec_s.append(s[:3])
        else: pri_s.append(s[:3])
    if not pri_s and sec_s: pri_s, sec_s = sec_s, []
    cats_xml = f'<c:ptCount val="{len(categories)}"/>' + "".join(f'<c:pt idx="{i}"><c:v>{html.escape(str(c))}</c:v></c:pt>' for i, c in enumerate(categories))
    def _ser_xml(idx, name, vals, col_hex, is_line=False):
        hx = _hex(col_hex, C_INDIGO)
        pts = f'<c:formatCode>{html.escape(str(number_format or "General"))}</c:formatCode><c:ptCount val="{len(vals)}"/>' + "".join(f'<c:pt idx="{i}"><c:v>{float(v)}</c:v></c:pt>' for i, v in enumerate(vals))
        sp_pr = f'<c:spPr><a:ln w="28575"><a:solidFill><a:srgbClr val="{hx}"/></a:solidFill></a:ln></c:spPr><c:marker><c:symbol val="circle"/><c:size val="6"/><c:spPr><a:solidFill><a:srgbClr val="{hx}"/></a:solidFill></c:spPr></c:marker>' if is_line else f'<c:spPr><a:solidFill><a:srgbClr val="{hx}"/></a:solidFill></c:spPr><c:invertIfNegative val="0"/>'
        return f'<c:ser><c:idx val="{idx}"/><c:order val="{idx}"/><c:tx><c:v>{html.escape(str(name))}</c:v></c:tx>{sp_pr}<c:cat><c:strRef><c:strCache>{cats_xml}</c:strCache></c:strRef></c:cat><c:val><c:numRef><c:numCache>{pts}</c:numCache></c:numRef></c:val></c:ser>'
    dlbls = '<c:dLbls><c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="800" b="1"><a:solidFill><a:srgbClr val="0F172A"/></a:solidFill></a:defRPr></a:pPr><a:endParaRPr lang="en-US"/></a:p></c:txPr><c:showLegendKey val="0"/><c:showVal val="1"/><c:showCatName val="0"/><c:showSerName val="0"/><c:showPercent val="0"/></c:dLbls>'
    ax_tx = '<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="850"><a:solidFill><a:srgbClr val="334155"/></a:solidFill></a:defRPr></a:pPr><a:endParaRPr lang="en-US"/></a:p></c:txPr>'
    is_bar = "bar" in ct_mode and "col" not in ct_mode
    is_line_only = "line" in ct_mode and not sec_s
    p_ser_str = "".join(_ser_xml(i, s[0], s[1], s[2], is_line=is_line_only) for i, s in enumerate(pri_s))
    if is_line_only:
        pri_plot = f'<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>{p_ser_str}{dlbls}<c:axId val="101"/><c:axId val="102"/></c:lineChart>'
    else:
        bdir = "bar" if is_bar else "col"
        pri_plot = f'<c:barChart><c:barDir val="{bdir}"/><c:grouping val="clustered"/><c:varyColors val="0"/>{p_ser_str}{dlbls}<c:gapWidth val="160"/><c:overlap val="-15"/><c:axId val="101"/><c:axId val="102"/></c:barChart>'
    cat_pos, val_pos = ("l", "b") if is_bar else ("b", "l")
    axes_xml = (
        f'<c:catAx><c:axId val="101"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="{cat_pos}"/><c:numFmt formatCode="General" sourceLinked="1"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="low"/>{ax_tx}<c:spPr><a:ln w="9525"><a:solidFill><a:srgbClr val="CBD5E1"/></a:solidFill></a:ln></c:spPr><c:crossAx val="102"/><c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/></c:catAx>'
        f'<c:valAx><c:axId val="102"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="{val_pos}"/><c:majorGridlines><c:spPr><a:ln w="6350"><a:solidFill><a:srgbClr val="E2E8F0"/></a:solidFill></a:ln></c:spPr></c:majorGridlines><c:numFmt formatCode="{html.escape(str(number_format or "General"))}" sourceLinked="0"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/>{ax_tx}<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr><c:crossAx val="101"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx>'
    )
    sec_plot = ""
    if sec_s:
        s_ser_str = "".join(_ser_xml(len(pri_s)+j, s[0], s[1], s[2], is_line=True) for j, s in enumerate(sec_s))
        sec_plot = f'<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>{s_ser_str}{dlbls}<c:axId val="103"/><c:axId val="104"/></c:lineChart>'
        axes_xml += (
            f'<c:catAx><c:axId val="103"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="1"/><c:axPos val="b"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="none"/><c:crossAx val="104"/><c:crosses val="autoZero"/><c:auto val="1"/></c:catAx>'
            f'<c:valAx><c:axId val="104"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="r"/><c:numFmt formatCode="General" sourceLinked="0"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/>{ax_tx}<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr><c:crossAx val="103"/><c:crosses val="max"/><c:crossBetween val="between"/></c:valAx>'
        )
    leg_xml = f'<c:legend><c:legendPos val="t"/><c:overlay val="0"/>{ax_tx}</c:legend>' if show_legend else ''
    c_xml = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><c:chartSpace xmlns:c="{C_NS}" xmlns:a="{A_NS}" xmlns:r="{R_NS}"><c:roundedCorners val="0"/><c:chart><c:autoTitleDeleted val="1"/><c:plotArea><c:layout/>{pri_plot}{sec_plot}{axes_xml}</c:plotArea>{leg_xml}<c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart><c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr></c:chartSpace>'
    prs._charts.append((c_idx, c_xml.encode("utf-8")))
    return gf
```
