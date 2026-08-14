"""Local doctrine index: SQLite FTS5 with BM25 ranking.

Deliberately not a vector store. On a CPU-only corporate laptop, BM25 over
full-text search is instant, uses no RAM to speak of, needs no embedding model,
and — for doctrine, where the vocabulary is fixed and precise — retrieves at
least as well as a small embedding model would. It also survives being copied
around as a single .db file.

Ingest is idempotent: a document whose content hash has not changed is skipped.
"""

import hashlib
import os
import re

from harness import db
from harness.rag import extract

SUPPORTED = (".txt", ".md", ".markdown", ".pdf", ".docx", ".pptx", ".html",
             ".htm", ".csv")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:40]


def _title_for(path):
    base = os.path.basename(path)
    stem = os.path.splitext(base)[0]
    return re.sub(r"[_-]+", " ", stem).strip()


def ingest_file(path, force=False):
    """Index one file. Returns a dict describing what happened."""
    path = os.path.abspath(path)
    title = _title_for(path)
    text, note = extract.extract(path)
    if not text.strip():
        return {"path": path, "title": title, "status": "empty",
                "chunks": 0, "note": note or "no text recovered"}

    sha = _sha(text)
    existing = db.q1("SELECT * FROM docs WHERE path=?", (path,))
    if existing and existing["sha"] == sha and not force:
        return {"path": path, "title": title, "status": "unchanged",
                "chunks": existing["n_chunks"], "note": note}

    conn = db.connect()
    if existing:
        conn.execute("DELETE FROM chunks WHERE doc_id=?", (existing["id"],))
        conn.execute("DELETE FROM docs WHERE id=?", (existing["id"],))

    cur = conn.execute(
        "INSERT INTO docs(path,title,sha,n_chunks,added_at) VALUES(?,?,?,?,?)",
        (path, title, sha, 0, db.now()))
    doc_id = cur.lastrowid

    pieces = extract.chunk(text)
    for i, body in enumerate(pieces):
        conn.execute("INSERT INTO chunks(body,doc_id,ord,title) "
                     "VALUES(?,?,?,?)", (body, doc_id, i, title))
    conn.execute("UPDATE docs SET n_chunks=? WHERE id=?", (len(pieces), doc_id))
    conn.commit()
    return {"path": path, "title": title, "status": "indexed",
            "chunks": len(pieces), "note": note}


# The corpus directory's own README explains how to use the folder; indexing
# it would put "what is worth adding" prose into doctrine retrieval results.
SKIP_NAMES = {"readme.md", "readme.txt", "readme"}


def ingest_dir(root, force=False):
    results = []
    root = os.path.abspath(root)
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.startswith("."):
                continue
            if (os.path.abspath(dirpath) == root
                    and name.lower() in SKIP_NAMES):
                continue
            if os.path.splitext(name)[1].lower() not in SUPPORTED:
                continue
            results.append(ingest_file(os.path.join(dirpath, name), force))
    return results


_FTS_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-']*")
_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "are",
         "was", "will", "your", "you", "what", "which", "when", "how", "its"}


def _fts_query(text):
    """Build a forgiving OR query. FTS5 syntax errors are the usual failure."""
    words = [w.lower() for w in _FTS_SAFE.findall(text or "")]
    words = [w for w in words if len(w) > 2 and w not in _STOP]
    if not words:
        return None
    seen, terms = set(), []
    for w in words[:14]:
        if w in seen:
            continue
        seen.add(w)
        terms.append('"%s"' % w.replace('"', ""))
    return " OR ".join(terms)


def search(text, limit=5):
    """BM25-ranked passages. Returns [] rather than raising."""
    query = _fts_query(text)
    if not query:
        return []
    try:
        rows = db.q(
            "SELECT title, body, bm25(chunks) AS score FROM chunks "
            "WHERE chunks MATCH ? ORDER BY score LIMIT ?", (query, limit))
    except Exception:
        return []
    out = []
    for r in rows:
        body = re.sub(r"\s+", " ", r["body"]).strip()
        out.append({"title": r["title"], "snippet": body[:600],
                    "score": r["score"]})
    return out


def stats():
    docs = db.q("SELECT title, path, n_chunks FROM docs ORDER BY title")
    total = db.q1("SELECT COUNT(*) AS n FROM chunks") or {"n": 0}
    return {"documents": docs, "chunks": total["n"]}


def clear():
    conn = db.connect()
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM docs")
    conn.commit()
