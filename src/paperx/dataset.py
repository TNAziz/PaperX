"""Package a paper's extracted numbers as a validation dataset with provenance.

`paperx dataset KEY [KEY ...] -o OUTDIR` writes:
  OUTDIR/figure_data.csv   every digitized chart value, long format, one provenance block per row
  OUTDIR/tables/<KEY>_Tn.csv  each table, as verified (corrected where Claude corrected it)
  OUTDIR/provenance.json   per paper: citation, DOI, source hash, tool versions; per item: page,
                           caption, verification status, reading precision
  OUTDIR/README.md         what the columns mean and how far to trust them

Only items that passed verification (as extracted or after correction) are included unless
--include-unverified is given, in which case their status column says so.
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from .figdata import normalize_panel, series_axes

OK = ("pass", "pass_after_correction")


def _cite(meta: dict) -> str:
    """Author-year citation from Crossref metadata, falling back to Zotero's creators and date."""
    from .zotero import lookup

    authors = [a.split()[-1] for a in meta.get("authors") or [] if a.strip()]
    year = meta.get("year")
    if not authors or not year:
        z = lookup(meta.get("source_sha256") or "") or {}
        authors = authors or z.get("authors") or []
        year = year or z.get("year")
    if not authors:
        return f"{(meta.get('title') or meta.get('source_file') or '?')[:40]} ({year or 'n.d.'})"
    etal = " et al." if len(authors) > 2 else (f" and {authors[1]}" if len(authors) == 2 else "")
    return f"{authors[0]}{etal} ({year or 'n.d.'})"


def build(archive: Path, keys: list[str], outdir: Path, include_unverified: bool = False) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "tables").mkdir(exist_ok=True)
    (outdir / "replots").mkdir(exist_ok=True)
    prov = {"papers": []}
    n_rows = n_tables = 0
    with open(outdir / "figure_data.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["citation", "doi", "archive_key", "figure", "page", "panel", "panel_title", "series",
                    "x", "x_label", "x_unit", "x_scale", "x_inverted", "y", "y_label", "y_unit", "y_scale",
                    "y_inverted", "y_low", "y_high",
                    "read_precision", "verification"])
        for key in keys:
            folder = archive / key
            meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
            cite = _cite(meta)
            paper = {"archive_key": key, "citation": cite, "title": meta.get("title"), "doi": meta.get("doi"),
                     "authors": meta.get("authors"), "year": meta.get("year"), "venue": meta.get("venue"),
                     "source_sha256": meta.get("source_sha256"), "tool_versions": meta.get("tool_versions"),
                     "figures": [], "tables": []}
            for dj in sorted((folder / "figures").glob("F*.data.json")):
                d = json.loads(dj.read_text(encoding="utf-8"))
                fid = d["figure"]
                fmeta = json.loads((folder / "figures" / f"{fid}.json").read_text(encoding="utf-8"))
                if d["status"] not in OK and not include_unverified:
                    continue
                label = f"{(fmeta.get('label') or 'figure').capitalize()} {fmeta.get('number') or '?'}"
                rp = folder / "figures" / f"{fid}.replot.png"
                if rp.exists():  # original | re-plot, for checking a series by eye
                    shutil.copyfile(rp, outdir / "replots" / f"{key}_{fid}.png")
                paper["figures"].append({"figure": label, "id": fid, "page": fmeta.get("page"), "caption": d.get("caption"),
                                         "verification": d["status"], "approximate": True,
                                         "panels": [{"panel": p["panel"], "axes": normalize_panel(p)["axes"],
                                                     "read_precision": p["read_precision"], "notes": p["notes"]}
                                                    for p in d["panels"]]})
                for p in d["panels"]:
                    for s in p["series"]:
                        xa, ya = series_axes(p, s)
                        for pt in s["points"]:
                            w.writerow([cite, meta.get("doi") or "", key, label, fmeta.get("page"), p["panel"], p["title"],
                                        s["name"], pt["x"], xa.get("label", ""), xa.get("unit", ""), xa.get("scale", ""),
                                        bool(xa.get("inverted")), pt["y"], ya.get("label", ""), ya.get("unit", ""),
                                        ya.get("scale", ""), bool(ya.get("inverted")),
                                        "" if pt["y_low"] is None else pt["y_low"],
                                        "" if pt["y_high"] is None else pt["y_high"], p["read_precision"], d["status"]])
                            n_rows += 1
            for tj in sorted((folder / "tables").glob("T*.json")):
                if not tj.stem[1:].isdigit():
                    continue
                t = json.loads(tj.read_text(encoding="utf-8"))
                st = (t.get("verification") or {}).get("status")
                if st not in OK and not include_unverified:
                    continue
                name = f"{key}_{t['id']}.csv"
                shutil.copyfile(folder / "tables" / f"{t['id']}.csv", outdir / "tables" / name)
                paper["tables"].append({"table": f"Table {t.get('number') or '?'}", "file": f"tables/{name}",
                                        "page": t.get("page"), "caption": t.get("caption"), "verification": st,
                                        "corrected_by_claude": bool(t.get("corrected"))})
                n_tables += 1
            prov["papers"].append(paper)
    (outdir / "provenance.json").write_text(json.dumps(prov, indent=1, ensure_ascii=False), encoding="utf-8")
    (outdir / "README.md").write_text(README.format(n_rows=n_rows, n_tables=n_tables,
                                                    papers="\n".join(f"- {p['citation']}: {p['title']} "
                                                                     f"(doi:{p['doi']})" for p in prov["papers"])),
                                      encoding="utf-8")
    return {"figure_rows": n_rows, "tables": n_tables, "papers": len(prov["papers"]), "out": str(outdir)}


README = """# Validation data extracted with paperx

Papers:
{papers}

## figure_data.csv ({n_rows} rows)

Values read from chart images. They are approximate: each value was read against the axis ticks by
Claude, re-plotted, and the re-plot was compared with the original figure by a separate Claude call.
`verification` is `pass` (matched on the first check) or `pass_after_correction` (matched after
Claude re-read the chart). `read_precision` is the model's own estimate of reading precision for that panel.
On a benchmark of six charts drawn from known data (bench/figdata_bench.py), every point was found;
median error was 0.0 to 0.24% of the axis range and the largest single error 1.5%. Real figures, and
especially scans and crowded plots, are harder: check the re-plot images in `replots/` before relying
on a series, and read each panel's `notes` in provenance.json (overlapping curves, detection limits,
axis caveats). Data re-plotted from other studies (for example experimental points) should be cited
to their original source.

Columns: citation, doi, archive_key, figure, page, panel, panel_title, series, x, x_label, x_unit,
x_scale (linear/log/categorical), x_inverted, y, y_label, y_unit, y_scale, y_inverted, y_low/y_high (error-bar ends as read,
blank if none drawn), read_precision, verification.

## tables/ ({n_tables} files)

Tables as verified against the page image. Tables marked `corrected_by_claude` in provenance.json were
rewritten from the image after the parser's version failed the check, and then passed a fresh check.

## replots/

For every figure in figure_data.csv: the original chart (left) beside a re-plot of the extracted values
(right). Look here before relying on a series.

## provenance.json

Per paper: citation, DOI, source PDF SHA-256, tool versions. Per item: page, caption, verification status.
Cite the original papers, not this file.
"""
