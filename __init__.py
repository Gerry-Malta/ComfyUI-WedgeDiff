"""
ComfyUI-WedgeDiff — entry point loaded by ComfyUI's custom node loader.

v2: Wedge Diff is a sidebar PANEL, not a graph node. There are no
node classes to register — capture happens via a frontend extension
(web/wedge_diff.js) that reads ComfyUI's own /history after each queue
and POSTs it to the routes registered in server_routes.py.

NODE_CLASS_MAPPINGS is intentionally empty: ComfyUI still needs the
symbol present, and WEB_DIRECTORY is what makes it load our web/ assets.
"""

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

WEB_DIRECTORY = "web"

# Registers the /wedge_diff/* HTTP routes on ComfyUI's own server.
# Guarded so any failure here can't break ComfyUI startup.
try:
    from . import server_routes  # noqa: F401
except Exception as exc:  # pragma: no cover
    print(f"[Wedge Diff] Could not load server routes: {exc}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
