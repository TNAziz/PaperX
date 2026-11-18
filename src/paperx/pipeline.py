"""`paperx extract`: PDF -> archive folder."""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import sys
import traceback
from pathlib import Path

from . import config, reconcile, refs, verify
from .parsers import ParserError, renormalize, run_parser, tool_version
from .pdfutil import Pdf, find_doi, sha256
from .zotero import lookup as zotero_lookup


def rmtree_long(p: Path) -> None:
    """rmtree that survives Windows paths over 260 characters."""
    import os

    import time

    target = "\\\\?\\" + str(p.resolve()) if os.name == "nt" else str(p)
    for attempt in range(6):  # sync clients (Google Drive, OneDrive) can briefly hold handles
        try:
            shutil.rmtree(target)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(2)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def tool_versions(parsers: list[str]) -> dict:
    import anthropic
    from importlib.metadata import version as pkg_version

    v = {p: tool_version(p) for p in parsers}
    v.update(paperx=config.PAPERX_VERSION, pypdfium2=pkg_version("pypdfium2"), anthropic=anthropic.__version__,
             claude_model=config.CLAUDE_MODEL)
    return v


def extract(pdf_path: Path, archive: Path, parser: str = "mineru", crosscheck: str | None = None,
            force: bool = False, use_claude: bool = True, online: bool = True,
            reuse_raw: bool = False, source_name: str | None = None, autocorrect: bool = config.AUTOCORRECT,
            figure_data: bool = False) -> Path:
    """reuse_raw: re-assemble from raw/<parser>/items.json already in the archive folder
    (no parser runs). Used by `paperx rebuild` when only paperx's own logic changed."""
    pdf_path = Path(pdf_path).resolve()
    archive = Path(archive).resolve()
    digest = sha256(pdf_path)
    z = zotero_lookup(digest)
    key = z["item_key"] if z else "X" + digest[:7].upper()
    out = archive / key
    parsers = [parser] + ([crosscheck] if crosscheck else [])
    versions = tool_versions(parsers)

    meta_p = out / "meta.json"
    reuse = reuse_raw and all((out / "raw" / p / "items.json").exists() for p in parsers)
    if meta_p.exists() and not force and not reuse:
        old = json.loads(meta_p.read_text(encoding="utf-8"))
        if old.get("source_sha256") == digest and old.get("tool_versions") == versions and old.get("parser") == parser:
            log(f"skip {pdf_path.name}: unchanged ({key})")
            return out

    if out.exists():
        if reuse:
            for child in out.iterdir():
                if child.name != "raw":
                    rmtree_long(child) if child.is_dir() else child.unlink()
        else:
            rmtree_long(out)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    # Stage a copy under a short path: the source PDF is never touched, and Windows path limits are avoided.
    staged = out / "raw" / "source.pdf"
    if not reuse:
        shutil.copy2(pdf_path, staged)

    flags: list[dict] = []
    if not z:
        flags.append({"item": "document", "severity": "info", "reason": "PDF not found in Zotero (by hash); keyed by hash"})
    t0 = dt.datetime.now()
    parsed, other = None, None
    for i, p in enumerate(parsers):
        log(f"  {p}: {'reusing raw output' if reuse else 'parsing'} {pdf_path.name}")
        try:
            d = (renormalize(p, out / "raw" / p, staged) if reuse
                 else run_parser(p, staged, out / "raw" / p))
        except (ParserError, Exception) as e:  # fail loudly but keep going
            flags.append({"item": "document", "severity": "error", "reason": f"{p} failed: {e}"[:2000]})
            log(f"  {p}: FAILED {e}"[:500])
            continue
        if i == 0:
            parsed = d
        else:
            other = d

    pdf = Pdf(staged)
    stats, ref_stats, vreport = {}, {}, {"checks": [], "tokens": {}}
    if parsed is None:
        flags.append({"item": "document", "severity": "error", "reason": "primary parser produced nothing; no archive content"})
    else:
        try:
            ref_list, rflags, stats = reconcile.build(parsed, pdf, out)
            flags += rflags
            log(f"  references: resolving {len(ref_list)} with Crossref")
            rf, ref_stats = refs.resolve(ref_list, out, online=online)
            flags += rf
            log(f"  verify: {stats.get('tables', 0)} tables, {stats.get('equations', 0)} equations")
            vreport = verify.run(out, flags, other=other, use_claude=use_claude, autocorrect=autocorrect)
            # captions may have been repaired: recount which numbered items are missing
            flags[:] = [f for f in flags if not f.get("completeness")]
            flags += reconcile.completeness_from_folder(out, pdf)
            if figure_data and use_claude:
                from . import figdata

                log("  figure data: reading charts")
                fsum = figdata.run(out)
                for f in fsum["figures"]:
                    if f["status"] in ("fail", "uncertain", "error"):
                        flags.append({"item": f["id"], "severity": "warn",
                                      "reason": f"chart data did not pass the re-plot check ({f['status']})"})
        except Exception as e:
            flags.append({"item": "document", "severity": "error", "reason": f"assembly failed: {e!r}",
                          "traceback": traceback.format_exc()[-2000:]})
            log(traceback.format_exc())

    first_text = " ".join(pdf.text(p) for p in range(1, min(pdf.n, 2) + 1))
    doi = find_doi(first_text)
    bib = refs.paper_metadata(doi, online=online)
    m = re.search(r"arXiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?)", first_text)
    if m:
        bib["arxiv_id"] = m.group(1)
    if not doi and not m:
        flags.append({"item": "document", "severity": "warn", "reason": "no DOI or arXiv ID found on the first two pages"})
    if not bib.get("title"):
        # fall back to the first heading of paper.md, then the Zotero title
        h = re.search(r"^# (.+)$", (out / "paper.md").read_text(encoding="utf-8"), re.M) if (out / "paper.md").exists() else None
        heading = re.sub(r"\]\([^)]*\)|[\[\]*_]", "", h.group(1)).strip() if h else None  # drop Markdown links/emphasis
        bib["title"] = (z or {}).get("title") or heading
        bib["title_source"] = "zotero" if (z or {}).get("title") else ("first heading" if h else None)
    meta = {
        "zotero_item_key": z["item_key"] if z else None,
        "zotero_attachment_key": z["attachment_key"] if z else None,
        "archive_key": key,
        **bib,
        "zotero_title": z.get("title") if z else None,
        "source_file": source_name or pdf_path.name,
        "source_sha256": digest,
        "pages": pdf.n,
        "has_text_layer": pdf.has_text_layer(),
        "parser": parser,
        "crosscheck_parser": crosscheck,
        "tool_versions": versions,
        "run_date": t0.isoformat(timespec="seconds"),
        "seconds": round((dt.datetime.now() - t0).total_seconds(), 1),
        "parser_seconds": {p: (json.loads((out / "raw" / p / "items.json").read_text(encoding="utf-8")).get("seconds_wall")
                               if (out / "raw" / p / "items.json").exists() else None) for p in parsers},
        "stats": {**stats, **ref_stats},
        "claude_tokens": vreport.get("tokens"),
        "flag_counts": {s: sum(1 for f in flags if f["severity"] == s) for s in ("error", "warn", "info")},
    }
    pdf.close()
    (out / "verify_report.json").write_text(json.dumps({"archive_key": key, "checks": vreport["checks"], "flags": flags},
                                                       indent=1, ensure_ascii=False), encoding="utf-8")
    meta_p.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"  done {key}: {meta['flag_counts']} in {meta['seconds']}s")
    return out


def rebuild(folder: Path, use_claude: bool = True, online: bool = True, autocorrect: bool = config.AUTOCORRECT,
            figure_data: bool = False) -> Path:
    """Re-assemble an existing archive folder from its raw/ parser output."""
    folder = Path(folder).resolve()
    old = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    return extract(folder / "raw" / "source.pdf", folder.parent, parser=old["parser"],
                   crosscheck=old.get("crosscheck_parser"), use_claude=use_claude, online=online,
                   reuse_raw=True, source_name=old.get("source_file"), autocorrect=autocorrect,
                   figure_data=figure_data)


def recheck(folder: Path) -> dict:
    """Recompute only the completeness flags of an archive folder (no parsing, no Claude calls)."""
    folder = Path(folder).resolve()
    vr_p, meta_p = folder / "verify_report.json", folder / "meta.json"
    vr = json.loads(vr_p.read_text(encoding="utf-8"))
    pdf = Pdf(folder / "raw" / "source.pdf")
    def is_completeness(f):  # tagged flags, plus untagged ones from folders built by earlier versions
        return f.get("completeness") or ("appear in the PDF text but" in f.get("reason", "")
                                         or "missing from the extracted sequence" in f.get("reason", ""))

    flags = [f for f in vr["flags"] if not is_completeness(f)] + reconcile.completeness_from_folder(folder, pdf)
    pdf.close()
    vr["flags"] = flags
    vr_p.write_text(json.dumps(vr, indent=1, ensure_ascii=False), encoding="utf-8")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta["flag_counts"] = {s: sum(1 for f in flags if f["severity"] == s) for s in ("error", "warn", "info")}
    meta_p.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return meta["flag_counts"]
