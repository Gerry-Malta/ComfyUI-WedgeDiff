"""
history_extract.py — pure parsing of a ComfyUI /history record.

No ComfyUI imports. A /history/{prompt_id} record has this shape
(confirmed against ComfyUI's stable history format):

    {
      "<prompt_id>": {
        "prompt": [
            number,            # [0] queue counter
            "<prompt_id>",     # [1]
            { ...graph... },   # [2] API-format prompt dict  <-- the graph we diff
            { ...extra_data... },  # [3] may hold extra_pnginfo.workflow (full canvas graph)
            ["<node_id>", ...] # [4] outputs_to_execute
        ],
        "outputs": {
            "<node_id>": {
                "images": [{"filename": "...", "subfolder": "...", "type": "output"}],
                # or "gifs"/"videos"/"audio" depending on the save node
            }
        },
        "status": { ... }
      }
    }

Keeping this isolated means the diff/store pipeline can be exercised
against synthetic records in unit tests without a running ComfyUI,
exactly like diff.py and db.py.
"""

from __future__ import annotations

import posixpath
from typing import Any

# Output payload keys ComfyUI uses for different media types. Each maps
# to a list of {filename, subfolder, type} dicts.
_MEDIA_KEYS = ("images", "gifs", "videos", "audio")


def unwrap_record(history_response: dict[str, Any], prompt_id: str) -> dict[str, Any] | None:
    """
    /history/{prompt_id} returns {prompt_id: {...record...}}.
    /history (full) returns {id1: {...}, id2: {...}, ...}.
    This normalizes either into the single record for prompt_id.
    """
    if not history_response:
        return None
    if prompt_id in history_response:
        return history_response[prompt_id]
    return None


def extract_exec_graph(record: dict[str, Any]) -> dict[str, Any] | None:
    """The pruned API-format execution graph — prompt[2]. This is the
    same shape a node's hidden PROMPT input used to provide, so
    diff.normalize_graph() consumes it unchanged."""
    prompt = record.get("prompt")
    if not isinstance(prompt, (list, tuple)) or len(prompt) < 3:
        return None
    graph = prompt[2]
    return graph if isinstance(graph, dict) else None


def extract_canvas_graph(record: dict[str, Any]) -> dict[str, Any] | None:
    """
    The FULL canvas graph (litegraph format, includes disconnected
    nodes) if ComfyUI attached it under extra_data.extra_pnginfo.workflow.
    Returns None if absent. NOTE: this is litegraph format (nodes/links
    arrays), NOT the API-prompt format extract_exec_graph returns — it
    is NOT directly consumable by diff.normalize_graph() without a
    separate adapter. Captured opportunistically for a possible future
    "diff everything on canvas" mode; the exec graph remains the
    primary diff source for now.
    """
    prompt = record.get("prompt")
    if not isinstance(prompt, (list, tuple)) or len(prompt) < 4:
        return None
    extra_data = prompt[3]
    if not isinstance(extra_data, dict):
        return None
    pnginfo = extra_data.get("extra_pnginfo")
    if not isinstance(pnginfo, dict):
        return None
    workflow = pnginfo.get("workflow")
    return workflow if isinstance(workflow, dict) else None


def extract_output_paths(record: dict[str, Any]) -> list[str]:
    """
    Flatten all saved media into relative paths like
    "subfolder/filename" (posix-style, matching how ComfyUI's /view
    endpoint expects them). Only 'output'/'temp' typed entries are
    included; input echoes are skipped. Deterministic ordering by
    node_id then filename so snapshots are stable/comparable.
    """
    outputs = record.get("outputs")
    if not isinstance(outputs, dict):
        return []

    paths: list[str] = []
    for node_id in sorted(outputs, key=lambda k: (len(k), k)):
        node_out = outputs[node_id]
        if not isinstance(node_out, dict):
            continue
        for media_key in _MEDIA_KEYS:
            entries = node_out.get(media_key)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                filename = entry.get("filename")
                if not filename:
                    continue
                # default to treating untyped as output
                if entry.get("type") not in (None, "output", "temp"):
                    continue
                subfolder = entry.get("subfolder") or ""
                rel = posixpath.join(subfolder, filename) if subfolder else filename
                paths.append(rel)

    # de-dup while preserving order
    seen: set[str] = set()
    deduped = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    return deduped


def pick_thumbnail(output_paths: list[str]) -> str | None:
    """First image-like output makes the history-list thumbnail.
    Prefers stills; falls back to the first path of any kind."""
    image_exts = (".png", ".jpg", ".jpeg", ".webp")
    for p in output_paths:
        if p.lower().endswith(image_exts):
            return p
    return output_paths[0] if output_paths else None
