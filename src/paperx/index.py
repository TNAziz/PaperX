"""Full-text search over the archive (SQLite FTS5): body text, captions, table cells."""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path


def build(archive: Path) -> dict:
    db = archive / "index.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.execute("CREATE VIRTUAL TABLE chunks USING fts5(key UNINDEXED, title UNINDEXED, page UNINDEXED, "
                "item UNINDEXED, kind UNINDEXED, text, tokenize='porter unicode61')")
    n_papers = n_chunks = 0
    for d in sorted(p for p in archive.iterdir() if (p / "meta.json").exists()):
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        key, title = d.name, meta.get("title") or meta.get("zotero_title") or meta.get("source_file")
        rows = []
        page = 1
        if (d / "paper.md").exists():
            for para in re.split(r"\n\s*\n", (d / "paper.md").read_text(encoding="utf-8")):
                m = re.match(r"<!-- page (\d+) -->", para.strip())
                if m:
                    page = int(m.group(1))
                    continue
                if para.strip() and not re.fullmatch(r"\[\[\w+\]\]", para.strip()):
                    rows.append((key, title, page, None, "body", para.strip()))
        for j in sorted((d / "figures").glob("F*.json")) + sorted((d / "tables").glob("T*.json")):
            if not j.stem[1:].isdigit():  # skip F5.data.json and other derived files
                continue
            m = json.loads(j.read_text(encoding="utf-8"))
            if m.get("caption"):
                rows.append((key, title, m["page"], m["id"], "caption", m["caption"]))
            if j.parent.name == "tables" and (j.with_suffix(".csv")).exists():
                cells = " | ".join(" ".join(r) for r in csv.reader(open(j.with_suffix(".csv"), encoding="utf-8")))
                rows.append((key, title, m["page"], m["id"], "table", cells))
        con.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?)", rows)
        n_papers += 1
        n_chunks += len(rows)
    con.commit()
    con.close()
    return {"papers": n_papers, "chunks": n_chunks, "db": str(db)}


def search(archive: Path, query: str, limit: int = 10) -> list[dict]:
    con = sqlite3.connect(archive / "index.sqlite")
    q = query if re.search(r'["*()]|\b(AND|OR|NOT|NEAR)\b', query) else '"' + query.replace('"', "") + '"'
    rows = con.execute("SELECT key, title, page, item, kind, snippet(chunks, 5, '[', ']', ' ... ', 16), bm25(chunks) "
                       "FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?", (q, limit)).fetchall()
    con.close()
    return [dict(zip(("key", "title", "page", "item", "kind", "snippet", "score"), r)) for r in rows]
