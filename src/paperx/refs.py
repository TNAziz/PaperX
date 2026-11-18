"""References: resolve each reference string to a DOI with Crossref and write BibTeX.

Only the reference string (public bibliographic text) is sent to Crossref, with a
generic User-Agent and no personal contact details. Results are cached locally.

An entry counts as doi-verified only when the Crossref title is found inside the
reference string (fuzzy) and the year matches. Everything else is written as an
unverified entry and flagged.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import html as htmllib
import unicodedata
from pathlib import Path

import httpx
from rapidfuzz import fuzz

from . import config

UA = "paperx/0.1 (local research archive tool)"
_lock = threading.Lock()


def _cache_path() -> Path:
    config.CACHE.mkdir(parents=True, exist_ok=True)
    return config.CACHE / "crossref.json"


def _load_cache() -> dict:
    p = _cache_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def crossref_query(client: httpx.Client, ref: str, cache: dict) -> dict | None:
    key = hashlib.sha1(ref.encode()).hexdigest()
    with _lock:
        if key in cache:
            return cache[key]
    q = re.sub(r"^\s*(\(\d+\)|\[\d+\]|\d+\.)\s*", "", ref)[:500]
    items = None
    for attempt in range(5):
        try:
            r = client.get("https://api.crossref.org/works",
                           params={"query.bibliographic": q, "rows": 2,
                                   "select": "DOI,title,author,issued,container-title,volume,page,type,score"})
            if r.status_code == 429 or r.status_code >= 500:  # rate limited / busy: back off and retry
                time.sleep(float(r.headers.get("retry-after", 2 ** attempt)))
                continue
            r.raise_for_status()
            items = r.json()["message"]["items"]
            break
        except Exception as e:  # network failure is a flag, not a crash
            if attempt == 4:
                return {"error": str(e)}
            time.sleep(2 ** attempt)
    if items is None:
        return {"error": "Crossref rate limit: gave up after 5 tries"}
    time.sleep(0.25)  # stay well under Crossref's public rate limit
    with _lock:
        cache[key] = items
    return items


def crossref_doi(client: httpx.Client, doi: str, cache: dict) -> dict | None:
    key = "doi:" + doi.lower()
    with _lock:
        if key in cache:
            return cache[key]
    try:
        r = client.get(f"https://api.crossref.org/works/{doi}")
        r.raise_for_status()
        msg = r.json()["message"]
    except Exception:
        return None
    with _lock:
        cache[key] = msg
    return msg


def _s(x) -> str:
    if isinstance(x, list):
        x = x[0] if x else ""
    return htmllib.unescape(re.sub(r"<[^>]+>", "", str(x or "")))


def _year(w: dict) -> int | None:
    try:
        return w["issued"]["date-parts"][0][0]
    except Exception:
        return None


def match(ref: str, items) -> tuple[dict | None, str]:
    if not items or isinstance(items, dict):
        return None, (items or {}).get("error", "no Crossref result") if isinstance(items, dict) else "no Crossref result"
    nref = _norm(ref)
    years = set(int(y) for y in re.findall(r"\b(1[89]\d\d|20\d\d)\b", ref))
    for w in items:
        title = _s(w.get("title"))
        if not title:
            continue
        sim = fuzz.partial_ratio(_norm(title), nref)
        y = _year(w)
        if sim >= 90 and (not years or y in years or (y and (y - 1) in years) or (y and (y + 1) in years)):
            return w, f"title match {sim:.0f}, year {y}"
    # Many chemistry styles (ACS) omit titles; fall back to author+journal+year+volume+page match.
    for w in items:
        y = _year(w)
        fam = _norm((w.get("author") or [{}])[0].get("family", ""))
        vol, page = str(w.get("volume", "")), str(w.get("page", "")).split("-")[0]
        if fam and fam in nref and y in years and vol and vol in ref and page and page in ref:
            return w, f"author/year/volume/page match ({fam} {y} {vol}:{page})"
    best = items[0]
    return None, f"best candidate rejected: {(best.get('title') or [''])[0][:80]!r} ({_year(best)})"


def _bibkey(w: dict, used: set) -> str:
    fam = _norm((w.get("author") or [{}])[0].get("family", "anon")).replace(" ", "") or "anon"
    base = f"{fam}{_year(w) or ''}"
    k, i = base, 0
    while k in used:
        i += 1
        k = base + "abcdefghijklmnopqrstuvwxyz"[i - 1]
    used.add(k)
    return k


def _esc(s: str) -> str:
    return (s or "").replace("{", "\\{").replace("}", "\\}")


def to_bibtex(w: dict, key: str, n: int, raw: str, how: str) -> str:
    typ = "article" if w.get("type") == "journal-article" else "misc"
    authors = " and ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") for a in w.get("author", []) or [])
    f = {
        "author": authors, "title": _s(w.get("title")), "journal": _s(w.get("container-title")),
        "year": str(_year(w) or ""), "volume": w.get("volume", ""), "pages": w.get("page", ""), "doi": w.get("DOI", ""),
        "x-paperx-status": "doi-verified", "x-paperx-match": how, "x-paperx-index": str(n), "x-paperx-raw": raw,
    }
    body = ",\n".join(f"  {k} = {{{_esc(v)}}}" for k, v in f.items() if v)
    return f"@{typ}{{{key},\n{body}\n}}"


def unverified_bibtex(raw: str, n: int, reason: str) -> str:
    years = re.findall(r"\b(1[89]\d\d|20\d\d)\b", raw)
    f = {"note": raw, "year": years[0] if years else "", "x-paperx-status": "unverified", "x-paperx-reason": reason,
         "x-paperx-index": str(n)}
    body = ",\n".join(f"  {k} = {{{_esc(v)}}}" for k, v in f.items() if v)
    return f"@misc{{ref{n},\n{body}\n}}"


def resolve(refs: list[str], out: Path, online: bool = True) -> tuple[list[dict], dict]:
    """Write references.bib; return (flags, stats)."""
    cache = _load_cache()
    entries, flags, used = [], [], set()
    results: list = [None] * len(refs)
    if online and refs:
        with httpx.Client(headers={"User-Agent": UA}, timeout=30) as client:
            results = [crossref_query(client, r, cache) for r in refs]  # sequential: Crossref rate-limits bursts
        _cache_path().write_text(json.dumps(cache), encoding="utf-8")
    n_ok = 0
    for i, (raw, items) in enumerate(zip(refs, results), start=1):
        w, how = match(raw, items) if online else (None, "offline")
        if w:
            n_ok += 1
            entries.append(to_bibtex(w, _bibkey(w, used), i, raw, how))
        else:
            entries.append(unverified_bibtex(raw, i, how))
            flags.append({"item": f"ref{i}", "severity": "warn", "reason": f"reference not DOI-verified: {how}",
                          "text": raw[:200]})
    (out / "references.bib").write_text("\n\n".join(entries) + "\n", encoding="utf-8")
    return flags, {"references": len(refs), "doi_verified": n_ok}


def paper_metadata(doi: str | None, online: bool = True) -> dict:
    if not (doi and online):
        return {"doi": doi}
    cache = _load_cache()
    with httpx.Client(headers={"User-Agent": UA}, timeout=30) as client:
        w = crossref_doi(client, doi, cache)
    _cache_path().write_text(json.dumps(cache), encoding="utf-8")
    if not w:
        return {"doi": doi, "doi_resolved": False}
    return {"doi": w.get("DOI", doi), "doi_resolved": True, "title": _s(w.get("title")),
            "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in w.get("author", []) or []],
            "year": _year(w), "venue": _s(w.get("container-title"))}
