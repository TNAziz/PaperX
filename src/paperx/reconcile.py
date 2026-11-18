"""Turn a parser's normalized items into the archive folder layout.

Writes paper.md, tables/, figures/, equations.json and returns the list of
reference strings plus a list of flags raised while assembling.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .pdfutil import Pdf

CAPTION_RE = re.compile(r"^\s*(fig(?:ure)?s?\.?|scheme|plate|table)\s*([A-Z]?\d+(?:\.\d+)?[a-z]?)", re.I)
CAPTION_LOOSE_RE = re.compile(r"\b(fig(?:ure)?s?\.?|scheme|table)\s*([A-Z]?\d+(?:\.\d+)?[a-z]?)\s*[.:|]", re.I)
# Body text that is really a caption: "Fig. 3: ...", "Figure 3. ...", "Table 2 | ...", "Figure S2: ..."
# Springer sets "Fig. 2" followed by an en space and thin space instead of punctuation.
CAPTION_TEXT_RE = re.compile(r"^\s*(fig(?:ure)?\.?|scheme|table)\s*[A-Z]?\d+(?:\.\d+)?[a-z]?(?:\s*[.:|]|[\u00a0\u2000-\u200b]+|\s+(?-i:(?=[A-Z])))\s*\S", re.I)
# Markdown emphasis a parser may put around a caption label: "**Figure S2:** ..."
EMPHASIS_RE = re.compile(r"^\s*[*_]{1,3}|(?<=[.:|])[*_]{1,3}")
PANEL_ONLY_RE = re.compile(r"^\s*(\(*[a-z]\)\s*)+$", re.I)
PANEL_PREFIX_RE = re.compile(r"^\s*(\(*[a-z]\)\s*)+(?=(fig|scheme))", re.I)
EQ_TAG_RE = re.compile(r"\\tag\{([^}]*)\}")
EQ_TRAIL_RE = re.compile(r"\(\s*(\d+[a-z]?)\s*\)\s*$")
REF_SPLIT_RE = re.compile(r"(?:(?<=\s)|^)(?=\(\d{1,3}\)\s|\[\d{1,3}\]\s)")
SUSPECT_GLYPHS = re.compile(r"[\ufffd\ue000-\uf8ff\u00fe\u00fd\u00de\u00a8\u00b4]")  # replacement, private-use, þ ý Þ ¨ ´


def flag(item: str, severity: str, reason: str, page=None, bbox=None, **kw) -> dict:
    return {"item": item, "severity": severity, "reason": reason, "page": page, "bbox": bbox, **kw}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()



# A caption label anywhere in a string: "Figure 7.", "Fig. 2:", "Table S1 |"
LABEL_ANY_RE = re.compile(r"(Fig(?:ure)?\.?|Scheme|Table)\s*([A-Z]?\d+(?:\.\d+)?[a-z]?)\s*[.:|]")


def clean_caption(cap: str) -> str:
    """Repair captions damaged by duplicate or hidden text layers (common in MDPI PDFs):
    a garbled prefix before the real label ("Classic Design i 7. E(t) d ... iFigure 7. E(t) ..."),
    a lost "Fi" ("gure 10."), the caption repeated twice, or doubled panel brackets ("((a)")."""
    cap = _norm(cap)
    if not cap:
        return cap
    cap = re.sub(r"^\(+", "(", cap)  # "((a)" -> "(a)"
    cap = re.sub(r"^(\([a-z]\)\s*)?gure\s+(?=[A-Z]?\d)", "Figure ", cap)  # "gure 10." -> "Figure 10."
    first = LABEL_ANY_RE.search(cap)
    if first and first.start() > 0 and not PANEL_ONLY_RE.match(cap[:first.start()].strip() or "x"):
        cap = cap[first.start():]  # drop the garbage in front of the real label
        first = LABEL_ANY_RE.search(cap)
    if first:
        # the same label again later means the caption was duplicated: keep the first copy
        # (also when the repeat lost its first letters: "...r(X).ure 16. Convergence ...")
        again = re.search(r"[A-Za-z]{0,3}(?:ure|ig\.?|cheme|able)\s*" + re.escape(first.group(2)) + r"\s*[.:|]",
                          cap[first.end():])
        if again:
            cap = cap[:first.end() + again.start()].strip()
    return cap


def caption_label(caption: str) -> tuple[str | None, str | None]:
    """('figure'|'table'|'scheme', number) from a caption, or (None, None)."""
    caption = EMPHASIS_RE.sub("", caption or "")
    caption = PANEL_PREFIX_RE.sub("", caption)
    m = CAPTION_RE.match(caption)
    if not m:
        # a stray drawing label in front of the caption ("Links Fig. 12: ...")
        m = CAPTION_LOOSE_RE.search(caption[:30])
    if not m:
        return None, None
    word = m.group(1).lower()
    kind = "table" if word.startswith("table") else ("scheme" if word.startswith("scheme") else "figure")
    return kind, m.group(2)


SECOND_CAPTION_RE = re.compile(r"(?<=[.)\]])\s+(?=(?:Fig(?:ure)?\.?|Scheme)\s*[A-Z]?\d+[a-z]?\s*[.:|]\s)", re.I)


def split_captions(caption: str) -> list[str]:
    """Split a block holding several figure captions ("Figure 4. ... detection limit. Figure 5. ...")."""
    if not caption or caption_label(caption)[0] not in ("figure", "scheme"):
        return [caption] if caption else []
    return [p.strip() for p in SECOND_CAPTION_RE.split(caption) if p.strip()]


def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def drop_running_headers(items: list[dict]) -> tuple[list[dict], int]:
    """Re-label short text that repeats on 3+ pages near the top or bottom margin as header."""
    hits = Counter()
    norm = lambda t: re.sub(r"\d+", "#", _norm(t).lower())
    for it in items:
        if it["kind"] == "text" and len(it.get("text", "")) < 120:
            hits[norm(it["text"])] += 1
    n = 0
    for it in items:
        if it["kind"] == "text":
            t = _norm(it.get("text", ""))
            if (len(t) < 120 and hits[norm(t)] >= 3) or re.fullmatch(r"\d{1,4}", t):
                it["kind"] = "header"
                n += 1
    return items, n


def group_figures(items: list[dict], flags: list[dict]) -> list[dict]:
    """Merge uncaptioned sub-panels into the captioned figure that follows on the same page,
    then attach free-standing captions to the nearest uncaptioned figure/table."""
    for it in items:
        if it["kind"] == "text" and len(_norm(it.get("text"))) < 600 and CAPTION_TEXT_RE.match(EMPHASIS_RE.sub("", it.get("text") or "")):
            it["kind"] = "caption"
            it["text"] = EMPHASIS_RE.sub("", it["text"]).strip()
    out: list[dict] = []
    pending: list[dict] = []  # uncaptioned figures on the current page
    for it in items:
        if it["kind"] == "figure":
            if pending and pending[-1]["page"] != it["page"]:
                out.extend(pending)
                pending = []
            # A sub-panel label alone ("(a)") is not a caption; a caption may start with one ("(d) Fig. 3. ...").
            cap = clean_caption(it.get("caption") or "")
            if cap and caption_label(cap)[0] in ("figure", "scheme"):
                it["caption"] = PANEL_PREFIX_RE.sub("", cap)
            elif cap and PANEL_ONLY_RE.match(cap):
                it["caption"] = ""
            elif cap:
                # text without a Figure/Scheme label (usually a chart legend the parser took for the
                # caption): keep it, but let the panel be matched to the real caption
                it["legend"], it["caption"] = cap, ""
            caps = split_captions(_norm(it.get("caption")))
            if len(caps) > 1 and pending:
                # Two captions merged into one block ("Figure 4. ... Figure 5. ..."), as when a caption
                # sits between two figures: the panels before this item take the first caption,
                # this item takes the rest.
                head = pending[0]
                for p in pending[1:]:
                    head["bbox"] = _union(head["bbox"], p["bbox"])
                head["caption"], head["panels"] = caps[0], len(pending)
                it["caption"], it["panels"] = " ".join(caps[1:]), 1
                out.extend([head, it])
                pending = []
            elif _norm(it.get("caption")):
                for p in pending:
                    it["bbox"] = _union(it["bbox"], p["bbox"])
                it["panels"] = len(pending) + 1
                pending = []
                out.append(it)
            else:
                pending.append(it)
            continue
        if it["kind"] not in ("header", "footer") and pending and it["kind"] != "caption":
            out.extend(pending)
            pending = []
        out.append(it)
    out.extend(pending)

    # Free-standing figure captions (common on scans, where the parser tags captions as plain
    # text): every uncaptioned figure piece goes to the nearest free caption below it in the
    # same column (else the nearest on the page); pieces sharing a caption become one figure.
    def xoverlap(a, b):
        return min(a[2], b[2]) - max(a[0], b[0]) > 0

    free_caps = [c for c in out if c["kind"] == "caption" and caption_label(c.get("text", ""))[0] in ("figure", "scheme")]
    groups: dict[int, list[dict]] = {}
    for fig in [o for o in out if o["kind"] == "figure" and not _norm(o.get("caption"))]:
        same = [c for c in free_caps if c["page"] == fig["page"]]
        below = [c for c in same if c["bbox"][1] >= fig["bbox"][3] - 5 and xoverlap(c["bbox"], fig["bbox"])]
        pool = below or same
        if not pool:
            continue
        cap = min(pool, key=lambda c: abs(c["bbox"][1] - fig["bbox"][3]))
        groups.setdefault(id(cap), []).append(fig)
    caps_by_id = {id(c): c for c in free_caps}
    for cid, figs in groups.items():
        cap, head = caps_by_id[cid], figs[0]
        for f in figs[1:]:
            head["bbox"] = _union(head["bbox"], f["bbox"])
            f["kind"] = "_merged_panel"
        head["caption"], head["panels"] = cap["text"], len(figs)
        cap["kind"] = "_consumed_caption"
        # short text fully inside the figure is a label in the drawing, not body text
        for o in out:
            if o["kind"] == "text" and o["page"] == head["page"] and len(_norm(o.get("text"))) < 80:
                cx, cy = (o["bbox"][0] + o["bbox"][2]) / 2, (o["bbox"][1] + o["bbox"][3]) / 2
                b = head["bbox"]
                if b[0] - 30 <= cx <= b[2] + 120 and b[1] <= cy <= b[3]:
                    o["kind"] = "_figure_label"

    # remaining free captions -> nearest uncaptioned table/figure on the same page
    for cap in [c for c in out if c["kind"] == "caption"]:
        kind, num = caption_label(cap.get("text", ""))
        if not kind:
            continue
        want = "table" if kind == "table" else "figure"
        cands = [o for o in out if o["kind"] == want and o["page"] == cap["page"] and not _norm(o.get("caption"))]
        if not cands:
            continue
        cy = (cap["bbox"][1] + cap["bbox"][3]) / 2
        best = min(cands, key=lambda o: min(abs(o["bbox"][1] - cy), abs(o["bbox"][3] - cy)))
        best["caption"] = cap["text"]
        cap["kind"] = "_consumed_caption"
    return [o for o in out if o["kind"] != "_merged_panel"]


REF_MARK_RE = re.compile(r"^\s*(\(\d{1,3}\)|\[\d{1,3}\]|\d{1,3}\.)\s")


def split_references(texts: list[str]) -> list[str]:
    refs: list[str] = []
    for t in texts:
        t = _norm(t)
        t = re.sub(r"^\W*references\s*", "", t, flags=re.I)
        parts = [p.strip() for p in REF_SPLIT_RE.split(t) if p.strip()]
        refs.extend(parts if len(parts) > 1 else [t])
    refs = [r for r in refs if r]
    # Numbered list: a fragment without a number is the continuation of the previous
    # entry (the parser split it at a column or page break).
    if refs and sum(bool(REF_MARK_RE.match(r)) for r in refs) / len(refs) > 0.6:
        merged: list[str] = []
        for r in refs:
            if merged and not REF_MARK_RE.match(r):
                merged[-1] = merged[-1] + " " + r
            else:
                merged.append(r)
        refs = merged
    return [r for r in refs if len(r) > 15]


def build(parsed: dict, pdf: Pdf, out: Path) -> tuple[list[str], list[dict], dict]:
    """Write paper.md, tables/, figures/, equations.json into `out`. Returns (refs, flags, stats)."""
    flags: list[dict] = []
    items = [dict(i) for i in parsed["items"]]
    items, n_hdr = drop_running_headers(items)
    items = group_figures(items, flags)

    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(exist_ok=True)

    md: list[str] = []
    equations, ref_texts = [], []
    nt = nf = ne = 0
    cur_page = None
    in_refs = False
    seen_fig_nums, seen_tab_nums, seen_eq_nums = [], [], []

    for it in items:
        k = it["kind"]
        if k in ("header", "footer", "_consumed_caption", "_figure_label"):
            continue
        if it["page"] != cur_page:
            cur_page = it["page"]
            md.append(f"<!-- page {cur_page} -->")
        if k == "heading":
            t = _norm(it.get("text"))
            in_refs = bool(re.search(r"\b(references|literature cited|bibliography|works cited)\b", t, re.I)) and len(t) < 40
            lvl = max(1, min(int(it.get("level") or 2), 6))
            md.append("#" * lvl + " " + re.sub(r"^[\W_]+", "", t))
            if in_refs:
                md.append("[[REFERENCES]]")
            continue
        if k == "reference" or (in_refs and k in ("text", "list")):
            ref_texts.append(it.get("text", ""))
            continue
        if k == "table":
            nt += 1
            tid = f"T{nt}"
            rows = it.get("rows") or []
            with open(out / "tables" / f"{tid}.csv", "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
            cap = clean_caption(it.get("caption") or "")
            _, num = caption_label(cap)
            seen_tab_nums.append(num)
            meta = {"id": tid, "number": num, "caption": cap, "footnote": it.get("footnote", ""), "page": it["page"],
                    "bbox": it["bbox"], "n_rows": len(rows), "n_cols": max((len(r) for r in rows), default=0),
                    "verification": {"status": "pending"}, "flagged_cells": []}
            if it.get("caption_bbox"):
                meta["caption_bbox"] = it["caption_bbox"]
            pdf.render_region(it["page"], it["bbox"], dpi=200).save(out / "tables" / f"{tid}.png")
            cells = [c for r in rows for c in r]
            bad = [c for c in cells if SUSPECT_GLYPHS.search(c)]
            if not rows:
                flags.append(flag(tid, "error", "table has no cells", it["page"], it["bbox"]))
            if bad:
                flags.append(flag(tid, "error", f"{len(bad)} cell(s) contain unmapped/suspect glyphs (e.g. {bad[0]!r}); "
                                  "symbols such as check marks were probably lost", it["page"], it["bbox"]))
            if cells and sum(1 for c in cells if not c.strip()) / len(cells) > 0.5:
                flags.append(flag(tid, "warn", "more than half the cells are empty; structure may be wrong", it["page"], it["bbox"]))
            if not cap:
                flags.append(flag(tid, "warn", "table has no caption", it["page"], it["bbox"]))
            (out / "tables" / f"{tid}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
            md.append(f"[[{tid}]]")
            continue
        if k == "figure":
            nf += 1
            fid = f"F{nf}"
            cap = _norm(it.get("caption"))
            lab, num = caption_label(cap)
            seen_fig_nums.append((lab, num))
            pdf.render_region(it["page"], it["bbox"], dpi=200, pad=2).save(out / "figures" / f"{fid}.png")
            meta = {"id": fid, "label": lab, "number": num, "caption": cap, "page": it["page"], "bbox": it["bbox"],
                    "panels": it.get("panels", 1), "caption_bbox": it.get("caption_bbox")}
            (out / "figures" / f"{fid}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
            if not cap:
                flags.append(flag(fid, "info", "image without caption (logo, graphical abstract, or missed caption)",
                                  it["page"], it["bbox"]))
            md.append(f"[[{fid}]]")
            continue
        if k == "equation":
            ne += 1
            eid = f"EQ{ne}"
            latex = (it.get("latex") or it.get("text") or "").strip()
            m = EQ_TAG_RE.search(latex) or EQ_TRAIL_RE.search(latex)
            num = m.group(1) if m else None
            seen_eq_nums.append(num)
            equations.append({"id": eid, "number": num, "latex": latex, "display": True, "page": it["page"],
                              "bbox": it["bbox"], "verification": {"status": "pending"}})
            md.append(f"[[{eid}]]")
            continue
        if k == "caption":
            # a caption we could not attach to anything: possible missed figure/table
            lab, num = caption_label(it.get("text", ""))
            if lab:
                flags.append(flag("caption", "error", f"caption for {lab} {num} has no matching {lab}; it may be missing",
                                  it["page"], it["bbox"], text=_norm(it.get("text"))[:200]))
            md.append(_norm(it.get("text")))
            continue
        t = _norm(it.get("text"))
        if not t:
            continue
        md.append(("- " + t) if k == "list" else t)

    (out / "paper.md").write_text("\n\n".join(md) + "\n", encoding="utf-8")
    (out / "equations.json").write_text(json.dumps(equations, indent=1, ensure_ascii=False), encoding="utf-8")

    # Completeness: compare numbers the body cites with numbers we found.
    body = (out / "paper.md").read_text(encoding="utf-8")
    captions = [json.loads(j.read_text(encoding="utf-8")).get("caption", "")
                for j in list((out / "figures").glob("F*.json")) + list((out / "tables").glob("T*.json"))]
    body += "\n" + "\n".join(captions)
    flags += completeness_flags(body, seen_fig_nums, seen_tab_nums, seen_eq_nums, pdf)

    refs = split_references(ref_texts)
    if not refs:
        flags.append(flag("references", "error", "no reference list found"))
    stats = {"headers_removed": n_hdr, "tables": nt, "figures": nf, "equations": ne, "references_raw": len(refs),
             "inline_math": body.count("$") // 2}
    return refs, flags, stats


def _ints(xs):
    out = set()
    for x in xs:
        if x and re.fullmatch(r"\d+", str(x)):
            out.add(int(x))
    return out


def completeness_from_folder(out: Path, pdf: Pdf) -> list[dict]:
    """Recompute completeness from the archive folder as it stands (after caption repair)."""
    figs, tabs, captions = [], [], []
    for j in (out / "figures").glob("F*.json"):
        if not j.stem[1:].isdigit():  # skip derived files such as F5.data.json
            continue
        m = json.loads(j.read_text(encoding="utf-8"))
        figs.append((m.get("label"), m.get("number")))
        captions.append(m.get("caption", ""))
    for j in (out / "tables").glob("T*.json"):
        if not j.stem[1:].isdigit():
            continue
        m = json.loads(j.read_text(encoding="utf-8"))
        tabs.append(m.get("number"))
        captions.append(m.get("caption", ""))
    eq_p, md_p = out / "equations.json", out / "paper.md"
    eqs = [e.get("number") for e in json.loads(eq_p.read_text(encoding="utf-8"))] if eq_p.exists() else []
    body = (md_p.read_text(encoding="utf-8") if md_p.exists() else "") + "\n" + "\n".join(captions)
    return completeness_flags(body, figs, tabs, eqs, pdf)


def completeness_flags(body: str, figs, tabs, eqs, pdf: Pdf) -> list[dict]:
    """Numbered items mentioned in the PDF text but not extracted are errors (bar: 100% of figures)."""
    flags = _completeness(body, figs, tabs, eqs, pdf)
    for f in flags:
        f["completeness"] = True
    return flags


def _series(nums) -> dict[str, set[int]]:
    """{'': {1, 2}, 'S': {1, 3}} from numbers such as '1', '2', 'S1', 'S3', '2a'."""
    out: dict[str, set[int]] = {}
    for n in nums:
        m = re.fullmatch(r"([A-Z]?(?:\d+\.)?)(\d+)[a-z]?", str(n or ""))
        if m:
            out.setdefault(m.group(1), set()).add(int(m.group(2)))
    return out


def _missing(label: str, cited_pat: str, found_nums, full: str, item: str, what: str) -> list[dict]:
    """Compare cited numbers with extracted ones within the document's own numbering series.
    A supplementary file (captions numbered S1, S2, ...) is checked on its S-series only, since its
    plain numbers point at the main paper; a main paper is checked on plain numbers only, since its
    S-numbers point at the supplement."""
    cited = _series(a + b for a, b in re.findall(cited_pat, full))
    found = _series(found_nums)
    # check the series the document's own captions use (plain, S, or chapter "33."); with no
    # numbered captions at all, check plain numbers
    own = sorted(found) or [""]
    if "" in found and "S" in found:
        own = [k for k in own if k != "S"]
    missing = []
    for key in own:
        c, f = cited.get(key, set()), found.get(key, set())
        if c:
            missing += [key + str(n) for n in sorted(set(range(1, max(c) + 1)) - f)]
    if not missing:
        return []
    return [flag(item, "error", f"{label} number(s) {missing} appear in the PDF text but {what}")]


def _completeness(body: str, figs, tabs, eqs, pdf: Pdf) -> list[dict]:
    flags = []
    if pdf.has_text_layer():
        full = " ".join(pdf.text(p) for p in range(1, pdf.n + 1))
    else:  # scanned: fall back to the OCR text (body plus captions) the parser produced
        full = body
    flags += _missing("scheme", r"\bSchemes?\s*(S?)(\d{1,3}(?:\.\d{1,3})?)\b", [n for lab, n in figs if lab == "scheme"], full,
                      "figures", "were not extracted")
    flags += _missing("figure", r"\bFig(?:ure)?s?\.?\s*(S?)(\d{1,3}(?:\.\d{1,3})?)", [n for lab, n in figs if lab == "figure"], full,
                      "figures", "no captioned figure was extracted")
    flags += _missing("table", r"\bTables?\s*(S?)(\d{1,3}(?:\.\d{1,3})?)\b", list(tabs), full, "tables", "were not extracted")
    eq_found = _ints(eqs)
    if eq_found:
        missing = sorted(set(range(1, max(eq_found) + 1)) - eq_found)
        if missing:
            flags.append(flag("equations", "warn", f"equation number(s) {missing} missing from the extracted sequence"))
    if not pdf.has_text_layer():
        flags.append(flag("document", "info", "no text layer: OCR path; citation-based completeness checks are weaker"))
    return flags
