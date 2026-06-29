"""
diff.py — pure graph-diff logic for Wedge Diff Node.

No ComfyUI imports here on purpose. This module only knows about the
*shape* of a Comfy API-format graph (the "prompt" dict), so it can be
unit tested standalone and reused by the drag-and-drop PNG comparator
(which never touches the running ComfyUI server at all).

Comfy API graph shape (per node_id):
    {
      "<node_id>": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 42,                 <- widget value (scalar)
            "model": ["1", 0]           <- link: [source_node_id, source_slot]
        },
        "_meta": {"title": "KSampler"}
      },
      ...
    }
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeSnapshot:
    node_id: str
    class_type: str
    title: str
    widgets: dict[str, Any] = field(default_factory=dict)
    links: dict[str, tuple[str, int]] = field(default_factory=dict)


def _is_link(value: Any) -> bool:
    """A link is serialized as [source_node_id, source_slot_index]."""
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    )


def normalize_graph(graph: dict[str, Any]) -> dict[str, NodeSnapshot]:
    """Convert a raw Comfy API graph dict into {node_id: NodeSnapshot}."""
    normalized: dict[str, NodeSnapshot] = {}
    for node_id, node in graph.items():
        class_type = node.get("class_type", "")
        title = (node.get("_meta") or {}).get("title", class_type)
        widgets: dict[str, Any] = {}
        links: dict[str, tuple[str, int]] = {}

        for input_name, value in (node.get("inputs") or {}).items():
            if _is_link(value):
                links[input_name] = (str(value[0]), int(value[1]))
            else:
                widgets[input_name] = value

        normalized[str(node_id)] = NodeSnapshot(
            node_id=str(node_id),
            class_type=class_type,
            title=title,
            widgets=widgets,
            links=links,
        )
    return normalized


def hash_graph(graph: dict[str, Any]) -> str:
    """Stable hash of a graph, used to dedupe identical re-runs."""
    canonical = json.dumps(graph, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _diff_widgets(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[Any]]:
    changed: dict[str, list[Any]] = {}
    for key in set(old) | set(new):
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            changed[key] = [old_val, new_val]
    return changed


def _diff_links(
    old: dict[str, tuple[str, int]], new: dict[str, tuple[str, int]]
) -> dict[str, dict[str, Any]]:
    changed: dict[str, dict[str, Any]] = {}
    for key in set(old) | set(new):
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            changed[key] = {
                "old": list(old_val) if old_val else None,
                "new": list(new_val) if new_val else None,
            }
    return changed


def _sort_key(node_id: str):
    """Sort numerically when possible, falling back to string order —
    Comfy node_ids are usually numeric strings but custom flows could
    use anything, so this must never raise."""
    return (0, int(node_id)) if node_id.isdigit() else (1, node_id)


def diff_graphs(graph_a: dict[str, Any], graph_b: dict[str, Any]) -> dict[str, Any]:
    """
    Diff two Comfy API graphs. Matches nodes by node_id, which is stable
    across re-executions of the *same* workflow file over time (the
    primary use case). Cross-file best-effort matching is a later phase.
    """
    a = normalize_graph(graph_a)
    b = normalize_graph(graph_b)

    ids_a, ids_b = set(a), set(b)
    added_ids = ids_b - ids_a
    removed_ids = ids_a - ids_b
    common_ids = ids_a & ids_b

    added_nodes = [
        {"id": nid, "class_type": b[nid].class_type, "title": b[nid].title}
        for nid in sorted(added_ids, key=_sort_key)
    ]
    removed_nodes = [
        {"id": nid, "class_type": a[nid].class_type, "title": a[nid].title}
        for nid in sorted(removed_ids, key=_sort_key)
    ]

    type_swapped: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    unchanged_count = 0

    for nid in sorted(common_ids, key=_sort_key):
        node_a, node_b = a[nid], b[nid]

        if node_a.class_type != node_b.class_type:
            type_swapped.append(
                {
                    "id": nid,
                    "old_type": node_a.class_type,
                    "new_type": node_b.class_type,
                    "title": node_b.title,
                }
            )
            continue

        widget_changes = _diff_widgets(node_a.widgets, node_b.widgets)
        link_changes = _diff_links(node_a.links, node_b.links)

        if widget_changes or link_changes:
            changed.append(
                {
                    "id": nid,
                    "class_type": node_b.class_type,
                    "title": node_b.title,
                    "widgets": widget_changes,
                    "links": link_changes,
                }
            )
        else:
            unchanged_count += 1

    # Per-node label maps so the frontend can render link endpoints as
    # readable names ("ColorMatch #8") instead of raw "8:0". Old link
    # endpoints are looked up in labels_a (graph A), new ones in
    # labels_b (graph B), since a node's type/title could differ
    # between the two runs.
    labels_a = {nid: {"type": a[nid].class_type, "title": a[nid].title} for nid in a}
    labels_b = {nid: {"type": b[nid].class_type, "title": b[nid].title} for nid in b}

    return {
        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,
        "type_swapped": type_swapped,
        "changed": changed,
        "unchanged_count": unchanged_count,
        "labels_a": labels_a,
        "labels_b": labels_b,
    }
