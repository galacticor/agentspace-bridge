# Knowledge Reference 1: Zero-Dependency `pptx_lxml_wrapper` Engine (`presentation_designer`)

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
# pptx_lxml_wrapper.py — Self-Contained Zero-Dependency OOXML .pptx Micro-Engine + Iterative Visual & Coordinate QA Gate
import os, zipfile, base64, math
try:
    from lxml import etree; _LXML = True
except ImportError:
    import xml.etree.ElementTree as etree; _LXML = False

O = "http://schemas.openxmlformats.org"
P_NS, A_NS, R_NS = f"{O}/presentationml/2006/main", f"{O}/drawingml/2006/main", f"{O}/officeDocument/2006/relationships"
A_TBL_URI, PK_R, CT_NS = f"{O}/drawingml/2006/table", f"{O}/package/2006/relationships", f"{O}/package/2006/content-types"
if not _LXML:
    for k, v in (("a", A_NS), ("r", R_NS), ("p", P_NS)): etree.register_namespace(k, v)
NSMAP, EMU = {"a": A_NS, "r": R_NS, "p": P_NS}, 914400
def Inches(v): return float(v)
def Pt(v): return float(v)
def RGBColor(r, g, b): return f"{r:02X}{g:02X}{b:02X}"
def _hex(c, d="0F172A"): return str(c).lstrip("#").upper() if c else d

class PP_ALIGN: LEFT="l"; CENTER="ctr"; RIGHT="r"
class MSO_ANCHOR: TOP="t"; MIDDLE="ctr"; BOTTOM="b"
class MSO_SHAPE: RECTANGLE="rect"; ROUNDED_RECTANGLE="roundRect"
class XL_CHART_TYPE: COLUMN_CLUSTERED="col"; BAR_CLUSTERED="bar"; LINE="line"

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
    def __init__(self): self.slides, self._id, self._qa = [], 2, []

    def run_visual_qa(self, render_png_dir="/home/bard"):
        issues = []
        for s_idx, items in enumerate(self._qa, 1):
            fids = set()
            ctrs = [it for it in items if it["kind"] in ("card", "metric", "callout", "table", "chart", "bullets")]
            for a in items:
                k, x, y, w, h, lbl = a["kind"], a["x"], a["y"], a["w"], a["h"], a["label"]
                if k in ("bg", "rule", "accent_bar"): continue
                if k == "title" and len(lbl) > 88:
                    issues.append(f"Slide {s_idx} [TITLE_OVERFLOW]: Title is {len(lbl)} chars (>88 max). Shorten to <=82 chars."); fids.add(id(a))
                if k not in ("header", "title", "subtitle", "footer") and (y + h > 7.06 or x + w > 12.95 or x < 0.20 or y < 1.12):
                    issues.append(f"Slide {s_idx} [BOUNDARY_BREACH]: {k} '{lbl[:28]}' (x={x:.2f},y={y:.2f},w={w:.2f},h={h:.2f},bottom={y+h:.2f}) breaches body safe zone (y in 1.14..7.05). Reduce h or move y up."); fids.add(id(a))
                if k == "table" and (h / max(a.get("nrows", 2), 1)) < 0.22:
                    issues.append(f"Slide {s_idx} [TABLE_CRAMPED]: Table '{lbl[:24]}' row height < 0.22\". Increase h to >= {a.get('nrows',2)*0.24:.2f}\"."); fids.add(id(a))
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
            try:
                from PIL import Image, ImageDraw
                if render_png_dir and os.path.isdir(render_png_dir):
                    img = Image.new("RGB", (1333, 750), (248, 250, 252)); drw = ImageDraw.Draw(img)
                    for it in items:
                        x0, y0, x1, y1 = int(it["x"]*100), int(it["y"]*100), int((it["x"]+it["w"])*100), int((it["y"]+it["h"])*100)
                        rgb = tuple(int(_hex(it["fill"])[k:k+2], 16) for k in (0, 2, 4)) if it.get("fill") else None
                        ol = (255, 0, 0) if id(it) in fids else ((203, 213, 225) if it["kind"] in ("card", "metric", "table", "chart", "callout") else None)
                        if rgb or ol: drw.rectangle([x0, y0, max(x0+1, x1), max(y0+1, y1)], fill=rgb, outline=ol, width=3 if id(it) in fids else 1)
                        if it["label"] and it["kind"] != "bg": drw.text((x0+4, y0+2), str(it["label"])[:65], fill=(225, 29, 72) if id(it) in fids else (15, 23, 42))
                    img.save(os.path.join(render_png_dir, f"slide_{s_idx}.png"))
            except Exception: pass
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
            for i, (sld, _) in enumerate(self.slides, 1):
                rels.append(f'<Relationship Id="rId{i}" Type="{R_NS}/slide" Target="slides/slide{i}.xml"/>')
                s_ids.append(f'<p:sldId id="{255+i}" r:id="rId{i}"/>')
                ct.append(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="{P_M}.slide+xml"/>')
                xb = etree.tostring(sld, xml_declaration=True, encoding="UTF-8") if _LXML else (hdr.encode("utf-8") + etree.tostring(sld, encoding="utf-8"))
                z.writestr(f"ppt/slides/slide{i}.xml", xb)
                z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", f'{hdr}<Relationships xmlns="{PK_R}"><Relationship Id="rId1" Type="{R_NS}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>')
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
        b64_str = base64.b64encode(raw_pptx).decode("ascii")
        print(f"[PPTX_PAYLOAD_ATTACHED] Wrote {len(raw_pptx)} raw binary bytes to pptx_payload.txt (use InputFileName='pptx_payload.txt', HasBytes=false, ContentBytes='')")
        print("B64_PPTX:" + b64_str)
        return b64_str

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
    s_qa = []; prs._qa.append(s_qa); slide = (sld, spTree, prs, s_qa); prs.slides.append((sld, spTree))
    _sp(slide, 0, 0, 13.333, 7.5, fill=bg_color, b_col=None, prst="rect", _qa_kind="bg")
    return slide

def _sp(slide, x, y, w, h, fill=None, b_col=None, b_pt=0.75, prst="rect", rad=0.04, paras=(), align="l", anchor="t", _qa_kind=None, _qa_label=None):
    _, spTree, prs, _ = slide; prs._id += 1
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
    add_textbox(slide, 0.55, 0.28, 10.0, 0.20, tracker, 8.5, True, C_CORAL, FONT_HEAD, _qa_kind="header")
    add_textbox(slide, 0.55, 0.48, 12.23, 0.36, action_title, 18.0, True, C_DARK, FONT_HEAD, _qa_kind="title")
    add_textbox(slide, 0.55, 0.84, 12.23, 0.24, subtitle, 10.5, False, C_MUTED, FONT_BODY, _qa_kind="subtitle")
    _sp(slide, 0.55, 1.12, 12.23, 0.01, fill=C_BORDER, b_col=None, _qa_kind="rule"); _sp(slide, 0.55, 7.08, 12.23, 0.008, fill=C_BORDER, b_col=None, _qa_kind="rule")
    add_textbox(slide, 0.55, 7.13, 11.2, 0.22, source_note, 8.0, False, C_MUTED, FONT_BODY, _qa_kind="footer")
    add_textbox(slide, 11.8, 7.13, 0.98, 0.22, f"{slide_num} / {total_slides}", 8.5, True, C_SLATE, FONT_HEAD, PP_ALIGN.RIGHT, _qa_kind="footer")

def add_callout_strip(slide, x, y, w, h, lead_in, body_text, accent=C_INDIGO, bg_color=C_TINT_INDIGO):
    _sp(slide, x, y, w, h, fill=bg_color, b_col=C_BORDER, b_pt=0.5, _qa_kind="callout", _qa_label=f"{lead_in}: {body_text}")
    _sp(slide, x, y, 0.06, h, fill=accent, b_col=None, _qa_kind="accent_bar")
    return _sp(slide, x+0.16, y+0.08, w-0.28, h-0.16, paras=[[(f"{lead_in}: ", 9.5, True, accent, FONT_HEAD), (body_text, 9.5, False, C_DARK, FONT_BODY)]], anchor="ctr", _qa_kind="skip")

def add_tufte_table(slide, x, y, w, h, headers, rows, col_widths=None, num_cols=None, highlight_rows=None, bold_rows=None, accent_cols=None, font_size=9.5, header_bg=C_DARK, header_fg=C_WHITE):
    _, spTree, prs, _ = slide; prs._id += 1
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
        etree.SubElement(etree.SubElement(tcPr, f"{{{A_NS}}}solidFill"), f"{{{A_NS}}}srgbClr", val=_hex(bg))
    htr = etree.SubElement(tbl, f"{{{A_NS}}}tr", h=str(rh))
    for ci, htxt in enumerate(headers): _c(htr, htxt, True, header_fg, header_bg, "r" if ci in num_cols else "l", "0F172A", 1.5, "0F172A", 1.5, FONT_HEAD)
    for ri, rvals in enumerate(rows):
        rtr = etree.SubElement(tbl, f"{{{A_NS}}}tr", h=str(rh)); rbg = highlight_rows.get(ri, C_WHITE if ri % 2 == 0 else C_SURFACE); ib = ri in bold_rows
        bc, bw = ("0F172A", 1.25) if (ib or ri==len(rows)-1) else ("E2E8F0", 0.5)
        for ci, val in enumerate(rvals[:nc]): _c(rtr, val, ib or ci==0 or ci in accent_cols, accent_cols.get(ci, C_DARK), rbg, "r" if ci in num_cols else "l", None, 0, bc, bw, FONT_BODY)
    return tbl

def add_native_column_chart(slide, x, y, w, h, categories, series_list, chart_type="col", number_format="0.0", show_legend=True):
    _sp(slide, x, y, w, h, fill=C_WHITE, b_col=C_BORDER, b_pt=0.5, _qa_kind="chart", _qa_label="Chart: " + ", ".join(s[0] for s in series_list))
    if show_legend:
        lx = x + 0.15
        for s_name, _, s_col in series_list:
            _sp(slide, lx, y+0.10, 0.14, 0.14, fill=s_col, b_col=None, _qa_kind="skip"); _sp(slide, lx+0.18, y+0.08, 1.8, 0.18, paras=[[(s_name, 8.0, True, C_SLATE, FONT_BODY)]], _qa_kind="skip"); lx += 2.0
    max_v = max([max(vals or [1]) for _, vals, _ in series_list] + [1.0]) * 1.18
    py, ph, px, pw = y + 0.36, h - 0.72, x + 0.35, w - 0.50; _sp(slide, px, py+ph, pw, 0.01, fill=C_SLATE, b_col=None, _qa_kind="skip")
    nc, ns = max(len(categories), 1), max(len(series_list), 1); gw = pw / nc; bw = min(0.42, (gw * 0.68) / ns)
    for ci, cat in enumerate(categories):
        gx = px + ci * gw + (gw - bw * ns) / 2
        for si, (_, vals, s_col) in enumerate(series_list):
            v = float(vals[ci]) if ci < len(vals) else 0.0; bh = max(0.03, (v / max_v) * ph); bx, by = gx + si * bw, py + ph - bh
            _sp(slide, bx, by, bw * 0.9, bh, fill=s_col, b_col=None, _qa_kind="skip")
            _sp(slide, bx-0.08, by-0.20, bw+0.16, 0.18, paras=[[(f"{v:.1f}" if isinstance(v, float) and not v.is_integer() else str(int(v)), 7.5, True, C_DARK, FONT_HEAD)]], align=PP_ALIGN.CENTER, _qa_kind="skip")
        _sp(slide, px + ci * gw, py + ph + 0.05, gw, 0.25, paras=[[(str(cat), 8.0, False, C_SLATE, FONT_BODY)]], align=PP_ALIGN.CENTER, _qa_kind="skip")
```
