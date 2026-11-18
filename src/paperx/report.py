"""Archive-wide results table (markdown): one row per paper, then every open error.

Usage: python -m paperx.report [archive_dir] [--keys K1 K2 ...]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter
from pathlib import Path

from . import config


def summarize(folder: Path) -> dict:
    m = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    v = json.loads((folder / "verify_report.json").read_text(encoding="utf-8"))
    own = lambda p: Path(p).stem[1:].isdigit()  # noqa: E731  (skip derived files such as F5.data.json)
    items = [json.loads(Path(t).read_text(encoding="utf-8")) for t in glob.glob(str(folder / "tables" / "T*.json")) if own(t)]
    items += json.loads((folder / "equations.json").read_text(encoding="utf-8")) if (folder / "equations.json").exists() else []
    st = Counter((i.get("verification") or {}).get("status", "none") for i in items)
    s = m.get("stats") or {}
    t = m.get("claude_tokens") or {}
    figs = [json.loads(Path(f).read_text(encoding="utf-8")) for f in glob.glob(str(folder / "figures" / "F*.json")) if own(f)]
    fd_p = folder / "figures" / "figdata_report.json"
    fd = json.loads(fd_p.read_text(encoding="utf-8")) if fd_p.exists() else {"figures": [], "tokens": {}}
    charts = [f for f in fd["figures"] if f.get("points") or f.get("kind") == "chart"]
    open_err = [f for f in v["flags"] if f["severity"] == "error"]
    return {
        "key": folder.name,
        "title": (m.get("title") or m.get("source_file") or "")[:60],
        "pages": m.get("pages"),
        "scan": not m.get("has_text_layer", True),
        "zotero": bool(m.get("zotero_item_key")),
        "tables": s.get("tables", 0),
        "equations": s.get("equations", 0),
        "figures_numbered": sum(1 for f in figs if f.get("number")),
        "figures_total": len(figs),
        "verified": f"{st.get('pass', 0)} + {st.get('pass_after_correction', 0)} corrected / {sum(st.values())}",
        "unverified": sum(n for k, n in st.items() if k not in ("pass", "pass_after_correction")),
        "refs": f"{s.get('doi_verified', 0)}/{s.get('references', 0)}",
        "seconds": m.get("seconds"),
        "charts": f"{sum(1 for f in charts if f['status'] in ('pass', 'pass_after_correction'))}/{len(charts)}" if fd_p.exists() else "-",
        "tokens": t.get("input", 0) + t.get("output", 0) + fd["tokens"].get("input", 0) + fd["tokens"].get("output", 0),
        "cost": t.get("cost_usd", 0),
        "errors": open_err,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("archive", nargs="?", type=Path, default=config.ARCHIVE)
    ap.add_argument("--keys", nargs="*")
    a = ap.parse_args(argv)
    keys = a.keys or sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(str(a.archive / "*" / "meta.json")))
    rows = [summarize(a.archive / k) for k in keys]
    print("| Key | Paper | Pages | Scan | Tables | Eqs | Figures (numbered/all) | Tables+eqs verified | Charts verified | Refs DOI | Time s | Tokens |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['key']} | {r['title']} | {r['pages']} | {'yes' if r['scan'] else ''} | {r['tables']} | {r['equations']} | "
              f"{r['figures_numbered']}/{r['figures_total']} | {r['verified']} | {r['charts']} | {r['refs']} | {r['seconds']} | {r['tokens']} |")
    tot_tok = sum(r["tokens"] for r in rows)
    print(f"\n{len(rows)} papers, {sum(r['pages'] or 0 for r in rows)} pages, {tot_tok} Claude tokens of plan usage "
          f"(last run of each paper), {sum(r['seconds'] or 0 for r in rows) / 60:.0f} min")
    print("\nOpen errors:")
    for r in rows:
        for f in r["errors"]:
            print(f"- {r['key']} {f['item']}: {f['reason'][:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
