"""
db.py — SQLite storage for Wedge Diff Node run snapshots.

No ComfyUI imports. Plain sqlite3, so this is fully unit-testable
with a temp file/in-memory DB, same as diff.py.

Schema: one row per *distinct* graph state for a given workflow_name.
Re-running with an identical graph touches the existing row's
timestamp instead of inserting a duplicate (see insert_or_touch).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

try:
    from .diff import hash_graph
except ImportError:
    from diff import hash_graph

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    graph_hash    TEXT NOT NULL,
    graph_json    TEXT NOT NULL,
    output_paths  TEXT,
    thumbnail_path TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs (workflow_name, updated_at);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["graph_json"] = json.loads(d["graph_json"])
    d["output_paths"] = json.loads(d["output_paths"]) if d["output_paths"] else []
    return d


def insert_or_touch(
    conn: sqlite3.Connection, workflow_name: str, graph: dict[str, Any]
) -> tuple[str, bool]:
    """
    Insert a new run row, unless the most recent row for this workflow
    has an identical graph hash — in which case just touch its
    updated_at and return the existing run_id.

    Returns (run_id, is_new_row).
    """
    new_hash = hash_graph(graph)
    now = time.time()

    last = conn.execute(
        """SELECT run_id, graph_hash FROM runs
           WHERE workflow_name = ?
           ORDER BY updated_at DESC LIMIT 1""",
        (workflow_name,),
    ).fetchone()

    if last is not None and last["graph_hash"] == new_hash:
        conn.execute(
            "UPDATE runs SET updated_at = ? WHERE run_id = ?",
            (now, last["run_id"]),
        )
        conn.commit()
        return last["run_id"], False

    run_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO runs
           (run_id, workflow_name, graph_hash, graph_json, output_paths,
            thumbnail_path, created_at, updated_at)
           VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)""",
        (run_id, workflow_name, new_hash, json.dumps(graph), now, now),
    )
    conn.commit()
    return run_id, True


def attach_outputs(
    conn: sqlite3.Connection,
    run_id: str,
    output_paths: list[str],
    thumbnail_path: str | None = None,
) -> bool:
    """Called from the JS 'executed' hook once output files are known."""
    cur = conn.execute(
        "UPDATE runs SET output_paths = ?, thumbnail_path = ? WHERE run_id = ?",
        (json.dumps(output_paths), thumbnail_path, run_id),
    )
    conn.commit()
    return cur.rowcount > 0


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_history(
    conn: sqlite3.Connection, workflow_name: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Newest first — feeds the node's history dropdown."""
    rows = conn.execute(
        """SELECT run_id, workflow_name, created_at, updated_at,
                  thumbnail_path, output_paths
           FROM runs WHERE workflow_name = ?
           ORDER BY updated_at DESC LIMIT ?""",
        (workflow_name, limit),
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["output_paths"] = json.loads(d["output_paths"]) if d["output_paths"] else []
        out.append(d)
    return out


def list_groups(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """All groups (workflow labels) that have at least one run, with
    run counts and last-touched time. Feeds the panel's group list."""
    rows = conn.execute(
        """SELECT workflow_name AS label,
                  COUNT(*) AS count,
                  MAX(updated_at) AS updated_at
           FROM runs
           GROUP BY workflow_name
           ORDER BY MAX(updated_at) DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def delete_group(conn: sqlite3.Connection, label: str) -> int:
    """Delete every run in a group. Returns how many rows were removed.
    This is destructive and is only ever triggered by an explicit user
    action (the × on a group in the panel, behind a confirm)."""
    cur = conn.execute("DELETE FROM runs WHERE workflow_name = ?", (label,))
    conn.commit()
    return cur.rowcount
