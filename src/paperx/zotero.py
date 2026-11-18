"""Read-only Zotero mapping: PDF content hash -> Zotero parent item key.

Zotero locks zotero.sqlite while running, so we copy it to a temp file first and
never open the live file. Nothing in the Zotero data directory is written.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from . import config
from .pdfutil import sha256

MAP = lambda: config.HOME / "zotero_map.json"
HASH_CACHE = lambda: config.CACHE / "zotero_hashes.json"


def _resolve(path: str, att_key: str, zdir: Path) -> Path | None:
    if not path:
        return None
    if path.startswith("storage:"):
        return zdir / "storage" / att_key / path[len("storage:"):]
    if path.startswith("attachments:"):
        return None  # relative to a linked-attachment base directory; not configured
    return Path(path)


def sync(zdir: Path = config.ZOTERO_DIR) -> dict:
    src = zdir / "zotero.sqlite"
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "zotero_copy.sqlite"
        shutil.copy2(src, tmp)
        con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        rows = con.execute("""
            SELECT a.itemID, att.key, par.key, a.path,
                   (SELECT v.value FROM itemData d JOIN fields f ON f.fieldID=d.fieldID
                    JOIN itemDataValues v ON v.valueID=d.valueID
                    WHERE d.itemID=COALESCE(a.parentItemID, a.itemID) AND f.fieldName='title'),
                   (SELECT v.value FROM itemData d JOIN fields f ON f.fieldID=d.fieldID
                    JOIN itemDataValues v ON v.valueID=d.valueID
                    WHERE d.itemID=COALESCE(a.parentItemID, a.itemID) AND f.fieldName='date'),
                   (SELECT group_concat(lastName, '|') FROM (
                        SELECT c.lastName FROM itemCreators ic JOIN creators c ON c.creatorID=ic.creatorID
                        WHERE ic.itemID=COALESCE(a.parentItemID, a.itemID) ORDER BY ic.orderIndex))
            FROM itemAttachments a
            JOIN items att ON att.itemID=a.itemID
            LEFT JOIN items par ON par.itemID=a.parentItemID
            WHERE a.contentType='application/pdf'
        """).fetchall()
        con.close()

    config.CACHE.mkdir(parents=True, exist_ok=True)
    cache = json.loads(HASH_CACHE().read_text(encoding="utf-8")) if HASH_CACHE().exists() else {}
    mapping, missing = {}, 0
    for i, (_, att_key, parent_key, path, title, date, creators) in enumerate(rows):
        f = _resolve(path, att_key, zdir)
        if f is None or not f.exists():
            missing += 1
            continue
        st = f.stat()
        ck = f"{f}|{st.st_size}|{int(st.st_mtime)}"
        h = cache.get(ck) or sha256(f)
        cache[ck] = h
        year = int(date[:4]) if date and date[:4].isdigit() else None
        mapping[h] = {"item_key": parent_key or att_key, "attachment_key": att_key, "title": title, "path": str(f),
                      "authors": [n for n in (creators or "").split("|") if n], "year": year}
        if i % 250 == 0:
            print(f"  hashed {i}/{len(rows)}", file=sys.stderr, flush=True)
    HASH_CACHE().write_text(json.dumps(cache), encoding="utf-8")
    MAP().write_text(json.dumps(mapping, indent=0, ensure_ascii=False), encoding="utf-8")
    return {"pdf_attachments": len(rows), "mapped": len(mapping), "file_missing": missing}


_map_cache: dict | None = None


def lookup(digest: str) -> dict | None:
    global _map_cache
    if _map_cache is None:
        _map_cache = json.loads(MAP().read_text(encoding="utf-8")) if MAP().exists() else {}
    return _map_cache.get(digest)
