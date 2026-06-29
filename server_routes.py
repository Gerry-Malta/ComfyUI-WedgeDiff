"""
server_routes.py — HTTP API for Wedge Diff, registered on ComfyUI's
own PromptServer at import time.

Split into two layers:
  - capture_logic(...) : pure-ish core (history dict in -> stored run
    out). Takes the already-fetched history record, so it has NO
    ComfyUI dependency and is unit-tested in tests/test_capture.py.
  - the aiohttp route handlers : thin glue that fetches the history
    record from ComfyUI in-process, then calls capture_logic.

Only the route handlers touch ComfyUI, so everything that can be
tested without a running server, is.

Routes:
    POST /wedge_diff/capture        {prompt_id, workflow_label}
    GET  /wedge_diff/history        ?workflow_label=&limit=
    GET  /wedge_diff/diff           ?run_a=&run_b=
    POST /wedge_diff/diff_external  {graph_a, graph_b}
    GET  /wedge_diff/sync           ?workflow_label=   (backfill from /history)
"""

import os
import subprocess
import sys

try:
    from . import db
    from . import diff
    from . import history_extract as hx
except ImportError:
    import db
    import diff
    import history_extract as hx


_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wedge_diff.sqlite3")
_conn = None


def get_conn():
    global _conn
    if _conn is None:
        _conn = db.connect(_DB_PATH)
    return _conn


def capture_logic(conn, workflow_label, prompt_id, history_response):
    """
    Core capture flow, ComfyUI-free for testability.

    history_response: the dict returned by ComfyUI's history lookup,
    shaped {prompt_id: record}. Returns a result dict describing what
    happened (stored/deduped/not_found).
    """
    record = hx.unwrap_record(history_response, prompt_id)
    if record is None:
        return {"ok": False, "reason": "prompt_id not found in history"}

    graph = hx.extract_exec_graph(record)
    if graph is None:
        return {"ok": False, "reason": "no execution graph in record"}

    output_paths = hx.extract_output_paths(record)
    thumbnail = hx.pick_thumbnail(output_paths)

    run_id, is_new = db.insert_or_touch(conn, workflow_label, graph)
    # Attach outputs in the same flow — no second round-trip like the
    # old node design needed. Touch-updates also refresh outputs in
    # case a re-run produced new files for an identical graph.
    db.attach_outputs(conn, run_id, output_paths, thumbnail)

    return {
        "ok": True,
        "run_id": run_id,
        "is_new": is_new,
        "output_count": len(output_paths),
    }


def sync_logic(conn, workflow_label, full_history_response):
    """
    Backfill any prompt_ids present in ComfyUI's full /history but not
    yet stored. full_history_response is {prompt_id: record, ...}.
    Returns count of newly stored runs. Used for headless/batch runs
    that completed with no browser tab connected.
    """
    stored = 0
    # oldest-first so insertion order matches execution order
    for prompt_id, record in full_history_response.items():
        graph = hx.extract_exec_graph(record)
        if graph is None:
            continue
        output_paths = hx.extract_output_paths(record)
        thumbnail = hx.pick_thumbnail(output_paths)
        _run_id, is_new = db.insert_or_touch(conn, workflow_label, graph)
        db.attach_outputs(conn, _run_id, output_paths, thumbnail)
        if is_new:
            stored += 1
    return stored


# --------------------------------------------------------------------
# ComfyUI-coupled layer below. Imported lazily/guarded so this module
# can still be imported in a plain test process (where `server` and
# `aiohttp` ComfyUI internals don't exist).
# --------------------------------------------------------------------

def validate_wedge_studio_folder(folder):
    """
    Pure validation for a Wedge Studio launch request, checked before
    ever touching subprocess. Split out from the route handler so it's
    unit-testable without actually spawning a process.

    Checks for _wedge_studio.py directly rather than the .bat: the
    launch route runs the script with sys.executable itself, bypassing
    the .bat's own Python-discovery chain entirely (that chain is what
    caused the silent hang -- see _kill_previous_instance commit notes).
    Because of that, this is no longer Windows-only at the validation
    level; only the route's subprocess creation flags branch by OS.
    """
    if not folder:
        return False, "folder path required"
    if not os.path.isdir(folder):
        return False, f"folder not found: {folder}"
    script_path = os.path.join(folder, "_wedge_studio.py")
    if not os.path.isfile(script_path):
        return False, "_wedge_studio.py not found in that folder"
    return True, None


def _fetch_history(prompt_id=None):
    """
    Read ComfyUI's history in-process (no HTTP loopback to itself).
    PromptServer.instance.prompt_queue.get_history() is ComfyUI's own
    accessor backing the /history route. Falls back gracefully if the
    internal shape differs across versions.
    """
    from server import PromptServer

    pq = PromptServer.instance.prompt_queue
    if prompt_id is not None:
        # get_history accepts a prompt_id filter in current ComfyUI
        try:
            return pq.get_history(prompt_id=prompt_id)
        except TypeError:
            # older/newer signature: fetch all, filter ourselves
            allh = pq.get_history()
            return {prompt_id: allh[prompt_id]} if prompt_id in allh else {}
    return pq.get_history()


def register_routes():
    from aiohttp import web
    from server import PromptServer

    routes = PromptServer.instance.routes

    @routes.post("/wedge_diff/capture")
    async def _capture(request):
        body = await request.json()
        prompt_id = body.get("prompt_id")
        workflow_label = body.get("workflow_label", "default")
        if not prompt_id:
            return web.json_response({"ok": False, "reason": "prompt_id required"}, status=400)
        history = _fetch_history(prompt_id)
        result = capture_logic(get_conn(), workflow_label, prompt_id, history)
        status = 200 if result.get("ok") else 404
        return web.json_response(result, status=status)

    @routes.get("/wedge_diff/history")
    async def _history(request):
        workflow_label = request.rel_url.query.get("workflow_label", "default")
        limit = int(request.rel_url.query.get("limit", "50"))
        rows = db.get_history(get_conn(), workflow_label, limit=limit)
        return web.json_response(rows)

    @routes.get("/wedge_diff/diff")
    async def _diff(request):
        run_a = request.rel_url.query.get("run_a")
        run_b = request.rel_url.query.get("run_b")
        if not run_a or not run_b:
            return web.json_response({"error": "run_a and run_b required"}, status=400)
        conn = get_conn()
        a = db.get_run(conn, run_a)
        b = db.get_run(conn, run_b)
        if a is None or b is None:
            return web.json_response({"error": "run not found"}, status=404)
        return web.json_response(diff.diff_graphs(a["graph_json"], b["graph_json"]))

    @routes.post("/wedge_diff/diff_external")
    async def _diff_external(request):
        body = await request.json()
        graph_a = body.get("graph_a")
        graph_b = body.get("graph_b")
        if not isinstance(graph_a, dict) or not isinstance(graph_b, dict):
            return web.json_response(
                {"error": "graph_a and graph_b objects required"}, status=400
            )
        return web.json_response(diff.diff_graphs(graph_a, graph_b))

    @routes.get("/wedge_diff/sync")
    async def _sync(request):
        workflow_label = request.rel_url.query.get("workflow_label", "default")
        history = _fetch_history()
        stored = sync_logic(get_conn(), workflow_label, history)
        return web.json_response({"ok": True, "newly_stored": stored})

    @routes.get("/wedge_diff/groups")
    async def _groups(request):
        return web.json_response(db.list_groups(get_conn()))

    @routes.post("/wedge_diff/group/delete")
    async def _group_delete(request):
        body = await request.json()
        label = body.get("workflow_label")
        if not label:
            return web.json_response({"error": "workflow_label required"}, status=400)
        deleted = db.delete_group(get_conn(), label)
        return web.json_response({"ok": True, "deleted": deleted})

    @routes.post("/wedge_diff/wedge_studio/launch")
    async def _wedge_studio_launch(request):
        body = await request.json()
        folder = (body.get("folder") or "").strip()
        ok, error = validate_wedge_studio_folder(folder)
        if not ok:
            return web.json_response({"ok": False, "error": error}, status=400)

        script_path = os.path.join(folder, "_wedge_studio.py")

        # sys.executable -- the exact interpreter already running ComfyUI's
        # own backend -- bypasses the .bat's venv/python_embeded/PATH search
        # entirely. That search is what silently hung before: when spawned
        # as a detached child of ComfyUI, it doesn't reliably inherit the
        # same PATH as a manually double-clicked .bat, so `where python`
        # could fail, hitting the .bat's `pause` -- which then waits forever
        # for a keypress on a console that was deliberately suppressed.
        # --no-browser still applies since we open the tab ourselves once
        # the port responds.
        #
        # CREATE_NEW_CONSOLE (rather than the previous CREATE_NO_WINDOW +
        # DETACHED_PROCESS) gives it a real, visible terminal -- same as
        # double-clicking the .bat yourself. That terminal staying open is
        # the desired at-a-glance "it's running" signal, and the script's
        # own startup banner (now that the UTF-8 fix is in) prints the URL
        # right there, same content the .bat would show. No stdout/stderr
        # redirect this time: the console itself is the feedback mechanism,
        # so output goes straight to it instead of a log file. CREATE_NEW_CONSOLE
        # and DETACHED_PROCESS are mutually exclusive -- can't combine them.
        popen_kwargs = dict(cwd=folder, close_fds=True)
        if os.name == "nt":
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE
            )
        else:
            popen_kwargs["start_new_session"] = True

        try:
            subprocess.Popen([sys.executable, script_path, "--no-browser"], **popen_kwargs)
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

        return web.json_response({"ok": True})


# Register on import, but never let a failure here break node loading.
try:
    register_routes()
except Exception as exc:  # pragma: no cover
    print(f"[Wedge Diff] Could not register HTTP routes: {exc}")
