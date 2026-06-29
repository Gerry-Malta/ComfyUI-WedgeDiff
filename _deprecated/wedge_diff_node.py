"""
wedge_diff_node.py — ComfyUI node classes for Wedge Diff.

Only uses ComfyUI's hidden-input mechanism (no `comfy`/`server`
imports), so node *registration* doesn't depend on the runtime —
though actually exercising it still needs a real ComfyUI process,
since that's what supplies the "PROMPT" and "UNIQUE_ID" hidden values
at execution time.

Design note on `workflow_label`: see module docstring in __init__.py.
History is grouped by this plain visible string widget rather than an
auto-detected filename, since the backend doesn't reliably get that
across ComfyUI frontend versions.
"""

import os

try:
    from . import db
except ImportError:
    import db

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wedge_diff.sqlite3")
_conn = None


def get_conn():
    """Shared connection — also used by server_routes.py so the node
    and the HTTP API read/write the same sqlite file."""
    global _conn
    if _conn is None:
        _conn = db.connect(_DB_PATH)
    return _conn


def _snapshot(workflow_label, prompt):
    conn = get_conn()
    return db.insert_or_touch(conn, workflow_label, prompt)


class _AnyType(str):
    """
    Wildcard type for Comfy slot type-checking. Overriding __ne__ to
    always return False means any `WEDGE_ANY != "WHATEVER"` comparison
    is False — so both the canvas wire-compatibility check and the
    backend execution validator treat connections to/from this as
    always valid, regardless of exact ComfyUI version. This is the
    same trick several long-standing community "any type" reroute
    nodes use, chosen over the literal string "*" because not every
    Comfy version treats that string as special in every code path.
    """

    def __ne__(self, other):
        return False


WEDGE_ANY = _AnyType("*")


class WedgeDiffAuto:
    """
    Wireless variant — drop anywhere on the canvas, leave disconnected.
    OUTPUT_NODE=True means Comfy always executes it on every queue,
    the same mechanism SaveImage uses to run regardless of whether
    anything depends on its output.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workflow_label": ("STRING", {"default": "default"}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "snapshot"
    OUTPUT_NODE = True
    CATEGORY = "utils/Wedge Diff"

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        # Forces a real re-execution on every queue. Without this,
        # ComfyUI's result cache only re-runs a node when its own
        # declared (non-hidden) inputs change -- and OUTPUT_NODE=True
        # only protects against pruning, it doesn't bypass the cache.
        # Since this node's hidden "prompt" input (the thing we
        # actually care about) isn't part of the cache key, the node
        # would otherwise silently stop re-running the moment
        # workflow_label stops changing. NaN != NaN is always True in
        # Python, which is exactly the signal ComfyUI's cache checks
        # for "always treat this as changed."
        return float("nan")

    def snapshot(self, workflow_label, prompt, unique_id):
        run_id, is_new = _snapshot(workflow_label, prompt)
        # Returned under "ui" so the frontend's "executed" websocket
        # event for THIS node's own id carries the run_id straight
        # back to wedge_diff.js -- no separate lookup round-trip.
        return {"ui": {"wedge_diff_run_id": [run_id], "wedge_diff_is_new": [is_new]}}


class WedgeDiffPassthrough:
    """
    Wildcard passthrough variant — splice into a single wire, right
    before whatever save/combine node terminates that branch. Forwards
    the value through unchanged. More reliable than the wireless
    variant for thumbnail timing, since it holds the actual in-memory
    value at execution time rather than depending on the "executed"
    websocket hook's timing -- trade-off is you have to pick one wire.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workflow_label": ("STRING", {"default": "default"}),
                "passthrough": (WEDGE_ANY,),
            },
            "hidden": {
                "prompt": "PROMPT",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = (WEDGE_ANY,)
    RETURN_NAMES = ("passthrough",)
    FUNCTION = "snapshot_and_forward"
    OUTPUT_NODE = True
    CATEGORY = "utils/Wedge Diff"

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        # Same reasoning as WedgeDiffAuto.IS_CHANGED above.
        return float("nan")

    def snapshot_and_forward(self, workflow_label, passthrough, prompt, unique_id):
        run_id, is_new = _snapshot(workflow_label, prompt)
        return {
            "ui": {"wedge_diff_run_id": [run_id], "wedge_diff_is_new": [is_new]},
            "result": (passthrough,),
        }
