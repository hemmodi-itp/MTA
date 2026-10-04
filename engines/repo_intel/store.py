"""
store.py — persist / load a RepoIndex in Postgres (RepoSnapshot, KgNode, KgEdge, CodeChunk).

Snapshots are content-addressed by (repo_full_name, commit_sha, indexer_version): indexing the
same commit twice is a cache hit that loads instead of re-parsing. Without a commit SHA there is no
content address, so nothing is cached (save() returns None) — never a shared placeholder SHA.
The whole snapshot is written in one transaction, so a crash never leaves an empty snapshot behind.
"""

import secrets
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from psycopg.types.json import Jsonb

from connectors.db.postgres import PostgresConnector
from engines.repo_intel import INDEXER_VERSION
from engines.repo_intel.indexer import RepoIndex
from engines.repo_intel.model import Chunk, Graph, Node


def new_id() -> str:
    """cuid-shaped id: 'c' + 24 url-safe lowercase chars, time-ordered prefix (same shape as the app's other ids)."""
    return "c" + format(int(time.time() * 1000), "x")[-10:] + secrets.token_hex(7)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _valid_sha(sha: Optional[str]) -> bool:
    return bool(sha) and len(sha) >= 7 and set(sha.lower()) <= set("0123456789abcdef") and set(sha) != {"0"}


class SnapshotStore:
    def __init__(self, db: Optional[PostgresConnector] = None) -> None:
        self.db = db or PostgresConnector()

    def find(self, repo: str, sha: Optional[str], version: str = INDEXER_VERSION) -> Optional[str]:
        if not _valid_sha(sha):
            return None
        rows = self.db.query('SELECT "id" FROM "RepoSnapshot" WHERE "repoFullName"=%s AND "commitSha"=%s AND "indexerVersion"=%s',
                             [repo, sha, version])
        return rows[0]["id"] if rows else None

    def save(self, repo: str, sha: Optional[str], idx: RepoIndex) -> Optional[str]:
        """Persist the index; returns the id of the snapshot actually used (an existing one when another run saved
        the same commit first), or None when there is no commit SHA to key the cache by."""
        if not _valid_sha(sha):
            return None
        sid = new_id()
        ids: Dict[str, str] = {k: new_id() for k in idx.graph.nodes}
        with self.db.connection() as conn:
            conn.execute(
                'INSERT INTO "RepoSnapshot" ("id","repoFullName","commitSha","indexerVersion","fileCount","languages","repoModel","createdAt") '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT ("repoFullName","commitSha","indexerVersion") DO NOTHING',
                [sid, repo, sha, idx.indexer_version, idx.file_count, Jsonb(idx.languages), Jsonb(idx.repo_model), utcnow()])
            existing = conn.execute('SELECT "id" FROM "RepoSnapshot" WHERE "repoFullName"=%s AND "commitSha"=%s AND "indexerVersion"=%s',
                                    [repo, sha, idx.indexer_version]).fetchone()
            if existing and existing["id"] != sid:  # another run indexed this commit first: use its snapshot
                return existing["id"]
            with conn.cursor() as cur:
                cur.executemany(
                    'INSERT INTO "KgNode" ("id","snapshotId","kind","key","filePath","startLine","endLine","name","props") '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    [(ids[n.key], sid, n.kind, n.key, n.file_path, n.start_line, n.end_line, n.name, Jsonb(n.props))
                     for n in idx.graph.nodes.values()])
                cur.executemany(
                    'INSERT INTO "KgEdge" ("snapshotId","src","dst","kind") VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    [(sid, ids[s], ids[d], k) for (s, k, d) in idx.graph.edges if s in ids and d in ids])
                cur.executemany(
                    'INSERT INTO "CodeChunk" ("id","snapshotId","filePath","startLine","endLine","symbol","content") '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    [(new_id(), sid, c.file_path, c.start_line, c.end_line, c.symbol, c.content.replace("\x00", ""))
                     for c in idx.chunks])
        return sid

    def load(self, snapshot_id: str) -> Tuple[Graph, list, Dict]:
        g = Graph()
        id_to_key: Dict[str, str] = {}
        for r in self.db.query('SELECT * FROM "KgNode" WHERE "snapshotId"=%s', [snapshot_id]):
            g.add(Node(r["kind"], r["key"], r["filePath"], r["startLine"], r["endLine"], r["name"], r["props"] or {}))
            id_to_key[r["id"]] = r["key"]
        for r in self.db.query('SELECT "src","dst","kind" FROM "KgEdge" WHERE "snapshotId"=%s', [snapshot_id]):
            if r["src"] in id_to_key and r["dst"] in id_to_key:
                g.link(id_to_key[r["src"]], r["kind"], id_to_key[r["dst"]])
        chunks = [Chunk(r["filePath"], r["startLine"], r["endLine"], r["content"], r["symbol"])
                  for r in self.db.query('SELECT "filePath","startLine","endLine","symbol","content" FROM "CodeChunk" '
                                         'WHERE "snapshotId"=%s ORDER BY "filePath","startLine"', [snapshot_id])]
        model = self.db.query('SELECT "repoModel" FROM "RepoSnapshot" WHERE "id"=%s', [snapshot_id])[0]["repoModel"] or {}
        return g, chunks, model
