"""Run a layout parser in its own environment and normalize its output.

Every parser ends up as the same `items.json` (see schema below), so the rest of
paperx never needs to know which parser produced it.

Common item schema (coordinates in PDF points, top-left origin, pages 1-based):
  kind     heading | text | list | caption | footnote | header | footer |
           equation | table | figure | reference
  page     int
  bbox     [x0, y0, x1, y1]
  text     str            (text-like kinds)
  level    int            (heading)
  latex    str            (equation)
  rows     list[list[str]](table)
  html     str            (table, when the parser gives it)
  caption  str            (table, figure)
"""
from __future__ import annotations

import html as htmllib
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from importlib.metadata import version as pkg_version
from pathlib import Path

from . import config
from .pdfutil import Pdf


class ParserError(RuntimeError):
    pass


def _env() -> dict:
    e = dict(os.environ)
    e.update(
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        HF_HUB_DISABLE_SYMLINKS_WARNING="1",
        MINERU_TELEMETRY_DISABLED="1",  # keep MinerU from sending usage telemetry
        DO_NOT_TRACK="1",
    )
    return e


def _run(cmd: list[str], log: Path, timeout: int) -> None:
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=_env(), timeout=timeout)
    if p.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-1500:]
        raise ParserError(f"{cmd[0]} exited {p.returncode}:\n{tail}")


def tool_version(tool: str) -> str:
    pkg = {"marker": "marker-pdf"}.get(tool, tool)
    py = config.env_python(tool)
    if not py.exists():
        return "not-installed"
    out = subprocess.run([str(py), "-c", f"import importlib.metadata as m;print(m.version('{pkg}'))"],
                         capture_output=True, text=True, env=_env())
    return out.stdout.strip() or "unknown"


def run_parser(tool: str, staged_pdf: Path, outdir: Path, timeout: int | None = None) -> dict:
    """Run `tool` on a staged (short-path) PDF copy; return the normalized items dict."""
    timeout = timeout or config.PARSER_TIMEOUT
    outdir.mkdir(parents=True, exist_ok=True)
    native = outdir / "native"
    if native.exists():
        shutil.rmtree("\\\\?\\" + str(native.resolve()) if os.name == "nt" else native)
    t0 = time.time()
    if tool == "docling":
        _run([str(config.env_python("docling")), str(config.REPO / "tools" / "docling" / "run.py"),
              str(staged_pdf), str(outdir)], outdir / "log.txt", timeout)
        data = json.loads((outdir / "items.json").read_text(encoding="utf-8"))
    elif tool == "mineru":
        native.mkdir(parents=True)
        z = native / "out.zip"
        # Local only: no --remote, image analysis off, telemetry off via env.
        _run([str(config.env_script("mineru", "mineru-kit")), "parse", str(staged_pdf), "-o", str(z),
              "-f", "zip", "--disable-image-analysis"], outdir / "log.txt", timeout)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(native)
        data = normalize_mineru(native, staged_pdf)
    elif tool == "marker":
        native.mkdir(parents=True)
        _run([str(config.env_script("marker", "marker_single")), str(staged_pdf), "--output_dir", str(native),
              "--output_format", "json"], outdir / "log.txt", timeout)
        js = next(native.rglob(f"{staged_pdf.stem}.json"))
        data = normalize_marker(js, staged_pdf)
    else:
        raise ValueError(f"unknown parser {tool}")
    data["seconds_wall"] = round(time.time() - t0, 1)
    data.setdefault("tool_version", tool_version(tool))
    (outdir / "items.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


def renormalize(tool: str, outdir: Path, staged_pdf: Path) -> dict:
    """Rebuild items.json from a parser's saved native output (no parsing). Docling normalizes
    inside its own environment, so its items.json is reused as is."""
    old = json.loads((outdir / "items.json").read_text(encoding="utf-8"))
    native = outdir / "native"
    if tool == "mineru" and (native / "structured_content.json").exists():
        data = normalize_mineru(native, staged_pdf)
    elif tool == "marker" and native.exists() and list(native.rglob(f"{staged_pdf.stem}.json")):
        data = normalize_marker(next(native.rglob(f"{staged_pdf.stem}.json")), staged_pdf)
    else:
        return old
    for k in ("seconds_wall", "tool_version"):
        if k in old:
            data[k] = old[k]
    (outdir / "items.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


# ---------------------------------------------------------------- MinerU (4.x)

_MINERU_KIND = {
    "doc_title": "heading", "paragraph_title": "heading", "title": "heading",
    "text": "text", "list": "list", "ref_text": "reference",
    "header": "header", "page_number": "header", "footer": "footer",
    "page_footnote": "footnote", "footnote": "footnote",
    "equation": "equation", "interline_equation": "equation",
    "image": "figure", "chart": "figure", "table": "table",
    "caption": "caption", "aside_text": "footer", "code": "text",
}


def md_table_rows(md: str) -> list[list[str]]:
    rows = []
    for line in md.strip().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue
        rows.append([_clean_inline(c) for c in cells])
    return rows


def html_table_rows(html: str) -> list[list[str]]:
    """Flatten an HTML table to rows; spanned cells are repeated so columns line up."""
    rows: list[list[str]] = []
    spans: dict[tuple[int, int], str] = {}
    for r, tr in enumerate(re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I)):
        row: list[str] = []
        c = 0
        for m in re.finditer(r"<t([hd])([^>]*)>(.*?)</t[hd]>", tr, re.S | re.I):
            while (r, c) in spans:
                row.append(spans.pop((r, c)))
                c += 1
            attrs, cell = m.group(2), _clean_inline(m.group(3))
            cs = int((re.search(r'colspan="?(\d+)', attrs) or [0, 1])[1])
            rs = int((re.search(r'rowspan="?(\d+)', attrs) or [0, 1])[1])
            for k in range(cs):
                row.append(cell)
                for dr in range(1, rs):
                    spans[(r + dr, c + k)] = cell
            c += cs
        while (r, c) in spans:
            row.append(spans.pop((r, c)))
            c += 1
        rows.append(row)
    return rows


def _clean_inline(s: str) -> str:
    s = re.sub(r"<sub>(.*?)</sub>", r"_\1", s, flags=re.S)
    s = re.sub(r"<sup>(.*?)</sup>", r"^\1", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def normalize_mineru(native: Path, pdf_path: Path) -> dict:
    sc = json.loads((native / "structured_content.json").read_text(encoding="utf-8"))
    meta = json.loads((native / "middle_json.json").read_text(encoding="utf-8")).get("metadata", {})
    pdf = Pdf(pdf_path)
    items, pages = [], []
    for p in sc["pages"]:
        pno = p["page_idx"] + 1
        w, h = pdf.size(pno)
        pages.append({"page": pno, "width": w, "height": h})
        for b in p["blocks"]:
            kind = _MINERU_KIND.get(b["type"])
            if kind is None:
                kind = "text"
            x0, y0, x1, y1 = b.get("bbox", [0, 0, 0, 0])
            rec = {"kind": kind, "page": pno, "bbox": [round(x0 * w, 1), round(y0 * h, 1), round(x1 * w, 1), round(y1 * h, 1)],
                   "native_type": b["type"]}
            content = b.get("content", "") or ""
            caps = " ".join(c.get("content", "") for c in b.get("captions", []) or [])
            cap_boxes = [c["bbox"] for c in b.get("captions", []) or [] if c.get("bbox")]
            if cap_boxes:  # where the caption is on the page, for caption repair
                rec["caption_bbox"] = [round(min(c[0] for c in cap_boxes) * w, 1), round(min(c[1] for c in cap_boxes) * h, 1),
                                       round(max(c[2] for c in cap_boxes) * w, 1), round(max(c[3] for c in cap_boxes) * h, 1)]
            if kind == "heading":
                rec.update(text=content, level=b.get("level", 1))
            elif kind == "equation":
                rec.update(latex=content, text=content)
            elif kind == "table":
                rows = html_table_rows(content) if "<tr" in content.lower() else md_table_rows(content)
                rec.update(rows=rows, caption=_clean_inline(caps), raw=content,
                           footnote=" ".join(c.get("content", "") for c in b.get("footnotes", []) or []))
            elif kind == "figure":
                rec.update(caption=caps, image_native=b.get("image_source"))
            else:
                rec.update(text=_clean_inline(content) if "<" in content else content)
            items.append(rec)
    pdf.close()
    return {"tool": "mineru", "tool_version": meta.get("producer", {}).get("version") or tool_version("mineru"),
            "settings": {"backend": "mineru-kit parse (local)", "image_analysis": False,
                         **sc.get("extensions", {}).get("mineru", {})},
            "pages": pages, "items": items}


# ---------------------------------------------------------------- Marker

_MARKER_KIND = {
    "SectionHeader": "heading", "Text": "text", "TextInlineMath": "text", "ListGroup": "list",
    "ListItem": "list", "Caption": "caption", "Footnote": "footnote", "PageHeader": "header",
    "PageFooter": "footer", "Equation": "equation", "Table": "table", "Figure": "figure",
    "Picture": "figure", "Code": "text", "Reference": "reference", "Form": "table", "Handwriting": "text",
}


def normalize_marker(js: Path, pdf_path: Path) -> dict:
    d = json.loads(js.read_text(encoding="utf-8"))
    pdf = Pdf(pdf_path)
    items, pages = [], []
    for pno, page in enumerate(d["children"], start=1):
        w, h = pdf.size(pno)
        _, _, mw, mh = page.get("bbox") or [0, 0, w, h]
        sx, sy = w / mw, h / mh
        pages.append({"page": pno, "width": w, "height": h})

        def bb(b):
            x0, y0, x1, y1 = b["bbox"]
            return [round(x0 * sx, 1), round(y0 * sy, 1), round(x1 * sx, 1), round(y1 * sy, 1)]

        for b in page.get("children") or []:
            t = b["block_type"]
            if t in ("TableGroup", "FigureGroup", "PictureGroup"):
                kids = b.get("children") or []
                cap = " ".join(_clean_inline(k.get("html", "")) for k in kids if k["block_type"] == "Caption")
                obj = next((k for k in kids if k["block_type"] in ("Table", "Figure", "Picture")), None)
                if obj is None:
                    continue
                kind = "table" if obj["block_type"] == "Table" else "figure"
                rec = {"kind": kind, "page": pno, "bbox": bb(obj), "caption": cap, "native_type": t}
                if kind == "table":
                    rec.update(rows=html_table_rows(obj.get("html", "")), html=obj.get("html", ""))
                items.append(rec)
                continue
            kind = _MARKER_KIND.get(t, "text")
            html = b.get("html", "")
            rec = {"kind": kind, "page": pno, "bbox": bb(b), "native_type": t}
            if kind == "heading":
                m = re.search(r"<h(\d)", html)
                rec.update(text=_clean_inline(html), level=int(m.group(1)) if m else 2)
            elif kind == "equation":
                m = re.search(r"<math[^>]*>(.*?)</math>", html, re.S)
                rec.update(latex=htmllib.unescape(m.group(1)).strip() if m else _clean_inline(html))
            elif kind == "table":
                rec.update(rows=html_table_rows(html), html=html, caption="")
            elif kind == "figure":
                rec.update(caption="")
            else:
                # keep inline math as $...$
                txt = re.sub(r"<math[^>]*>(.*?)</math>", lambda m: f"${htmllib.unescape(m.group(1)).strip()}$", html, flags=re.S)
                rec.update(text=_clean_inline(txt))
            items.append(rec)
    pdf.close()
    return {"tool": "marker", "tool_version": tool_version("marker"), "settings": {"output_format": "json", "use_llm": False},
            "pages": pages, "items": items}
