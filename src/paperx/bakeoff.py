"""Pre-ground-truth comparison of parsers (Phase 2 preview).

Without hand-corrected answers we can still measure things the PDF itself tells us:
which figure/table numbers the text cites, how many numbered equations exist, and
whether references and running headers are labelled. This is a proxy, not the
bake-off score; score.py is used once ground truth exists.

Usage: python -m paperx.bakeoff <archive_dir_or_parse_dirs...>  -> markdown table
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .pdfutil import Pdf
from .reconcile import caption_label, drop_running_headers, group_figures


def _ints(xs):
    return {int(x) for x in xs if x and re.fullmatch(r"\d+", str(x))}


def proxy(items: dict, pdf: Pdf) -> dict:
    full = " ".join(pdf.text(p) for p in range(1, pdf.n + 1))
    fig_cited = _ints(re.findall(r"\bFig(?:ure)?s?\.?\s*(\d{1,3})", full))
    tab_cited = _ints(re.findall(r"\bTables?\s*(\d{1,3})\b", full))
    its = [dict(i) for i in items["items"]]
    its, _ = drop_running_headers(its)
    its = group_figures(its, [])
    figs = _ints(caption_label(i.get("caption", ""))[1] for i in its
                 if i["kind"] == "figure" and caption_label(i.get("caption", ""))[0] == "figure")
    tabs = _ints(caption_label(i.get("caption", ""))[1] for i in its if i["kind"] == "table")
    eqs = [i for i in its if i["kind"] == "equation"]
    def eq_number(latex: str):
        m = re.search(r"\\tag\{(\d+)\}", latex) or re.search(r"\(\s*(\d+)\s*\)\s*$", latex)
        return m.group(1) if m else None

    eq_num = _ints(eq_number(i.get("latex") or "") for i in eqs)
    n_fig = max(fig_cited) if fig_cited else 0
    n_tab = max(tab_cited) if tab_cited else 0
    return {
        "figures": f"{len(figs & set(range(1, n_fig + 1)))}/{n_fig}" if n_fig else "-",
        "tables": f"{len(tabs & set(range(1, n_tab + 1)))}/{n_tab}" if n_tab else "-",
        "equations": len(eqs),
        "eq_numbered": len(eq_num),
        "ref_items": sum(1 for i in its if i["kind"] == "reference"),
        "headers_labelled": sum(1 for i in items["items"] if i["kind"] in ("header", "footer")),
        "seconds": items.get("seconds_wall") or items.get("seconds"),
    }


def main(paths: list[str]) -> int:
    rows = []
    for d in paths:
        d = Path(d)
        raw = d / "raw" if (d / "raw").exists() else d
        src = raw / "source.pdf"
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
        pdf = Pdf(src)
        for tool in ("mineru", "docling", "marker"):
            f = raw / tool / "items.json"
            if not f.exists():
                continue
            items = json.loads(f.read_text(encoding="utf-8"))
            rows.append({"paper": (meta.get("title") or meta.get("source_file") or d.name)[:45], "pages": pdf.n,
                         "tool": tool, **proxy(items, pdf)})
        pdf.close()
    cols = ["paper", "pages", "tool", "figures", "tables", "equations", "eq_numbered", "ref_items", "headers_labelled", "seconds"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
