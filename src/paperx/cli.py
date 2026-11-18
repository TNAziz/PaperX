"""paperx command line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="paperx", description="Paper PDF -> verified, searchable archive")
    ap.add_argument("--archive", type=Path, default=config.ARCHIVE, help=f"archive root (default {config.ARCHIVE})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="extract one or more PDFs into the archive")
    e.add_argument("pdfs", nargs="+", type=Path)
    e.add_argument("--parser", choices=config.PARSERS, default="mineru")
    e.add_argument("--crosscheck", choices=config.PARSERS, help="second parser used only to cross-check tables/equations")
    e.add_argument("--force", action="store_true", help="re-run even if hash and tool versions are unchanged")
    e.add_argument("--no-claude", action="store_true", help="skip Claude visual verification (items are flagged unverified)")
    e.add_argument("--offline", action="store_true", help="no Crossref lookups")
    e.add_argument("--no-autocorrect", action="store_true", help="flag failed tables/equations but do not correct them")
    e.add_argument("--figure-data", action="store_true", help="also read numeric data from charts (approximate; verified by re-plotting)")
    e.add_argument("--reuse-raw", action="store_true", help="reuse parser output already in the archive folder (e.g. after an interrupted run)")

    p = sub.add_parser("parse", help="run one parser only and write its normalized items.json (bake-off)")
    p.add_argument("pdf", type=Path)
    p.add_argument("--parser", choices=config.PARSERS, required=True)
    p.add_argument("--out", type=Path, required=True)

    rb = sub.add_parser("rebuild", help="re-assemble archive folders from their saved raw parser output")
    rb.add_argument("keys", nargs="*", help="archive keys (default: all)")
    rb.add_argument("--no-claude", action="store_true")
    rb.add_argument("--offline", action="store_true")
    rb.add_argument("--no-autocorrect", action="store_true")
    rb.add_argument("--figure-data", action="store_true")

    fd = sub.add_parser("figdata", help="read numeric data from the charts of papers already in the archive")
    fd.add_argument("keys", nargs="+", help="archive keys")
    fd.add_argument("--figures", nargs="*", help="only these figure ids, e.g. F2 F5")

    ds = sub.add_parser("dataset", help="package verified chart data and tables as a validation dataset")
    ds.add_argument("keys", nargs="+", help="archive keys")
    ds.add_argument("-o", "--out", type=Path, required=True)
    ds.add_argument("--include-unverified", action="store_true")

    rc = sub.add_parser("recheck", help="recompute completeness flags only (no parsing, no Claude calls)")
    rc.add_argument("keys", nargs="*", help="archive keys (default: all)")

    s = sub.add_parser("search", help="full-text search the archive")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=10)

    sub.add_parser("index", help="rebuild index.sqlite")
    sub.add_parser("sync-zotero", help="map PDFs to Zotero item keys (reads a copy of zotero.sqlite, never writes)")

    a = ap.parse_args(argv)
    if a.cmd == "extract":
        from .pipeline import extract

        a.archive.mkdir(parents=True, exist_ok=True)
        for pdf in a.pdfs:
            print(f"extract {pdf.name}", file=sys.stderr)
            out = extract(pdf, a.archive, parser=a.parser, crosscheck=a.crosscheck, force=a.force,
                          use_claude=not a.no_claude, online=not a.offline, autocorrect=not a.no_autocorrect,
                          figure_data=a.figure_data, reuse_raw=a.reuse_raw)
            print(out)
        from .index import build

        print(json.dumps(build(a.archive)), file=sys.stderr)
    elif a.cmd == "parse":
        import shutil

        from .parsers import run_parser

        a.out.mkdir(parents=True, exist_ok=True)
        staged = a.out / "source.pdf"
        shutil.copy2(a.pdf, staged)
        d = run_parser(a.parser, staged, a.out / a.parser)
        print(json.dumps({"tool": d["tool"], "items": len(d["items"]), "seconds": d.get("seconds_wall")}))
    elif a.cmd == "rebuild":
        from .index import build
        from .pipeline import rebuild

        keys = a.keys or [d.name for d in sorted(a.archive.iterdir()) if (d / "meta.json").exists()]
        for k in keys:
            print(f"rebuild {k}", file=sys.stderr)
            rebuild(a.archive / k, use_claude=not a.no_claude, online=not a.offline, autocorrect=not a.no_autocorrect,
                    figure_data=a.figure_data)
        print(json.dumps(build(a.archive)), file=sys.stderr)
    elif a.cmd == "figdata":
        from .figdata import run as figrun

        for k in a.keys:
            print(f"figdata {k}", file=sys.stderr)
            summ = figrun(a.archive / k, only=a.figures)
            for f in summ["figures"]:
                print(f"  {f['id']} (Figure {f['number']}): {f['status']}"
                      + (f", {f['points']} points" if f.get("points") else f" [{f.get('kind')}]"))
            print(f"  tokens: {summ['tokens']}", file=sys.stderr)
    elif a.cmd == "dataset":
        from .dataset import build as dsbuild

        print(json.dumps(dsbuild(a.archive, a.keys, a.out, a.include_unverified)))
    elif a.cmd == "recheck":
        from .pipeline import recheck

        keys = a.keys or [d.name for d in sorted(a.archive.iterdir()) if (d / "meta.json").exists()]
        for k in keys:
            print(k, recheck(a.archive / k))
    elif a.cmd == "search":
        from .index import search

        for r in search(a.archive, a.query, a.n):
            print(f"{r['key']}  p.{r['page']}  {r['kind']}{' ' + r['item'] if r['item'] else ''}  {r['title'][:70]}")
            print(f"    {r['snippet']}")
    elif a.cmd == "index":
        from .index import build

        print(json.dumps(build(a.archive)))
    elif a.cmd == "sync-zotero":
        from .zotero import sync

        print(json.dumps(sync()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
