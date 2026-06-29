# Wedge Diff

A ComfyUI sidebar panel that automatically snapshots every prompt you run, diffs the workflow graph between any two runs, lets you jump straight to what changed on the canvas, and pairs that with a drag-and-drop wipe-compare of the outputs.

It's the in-app sibling to a separate tool, Wedge Studio — Wedge Studio handles automated batch sweeps and their reports; Wedge Diff fills the gap for everyday manual iteration: *"what did I actually change since the last good render?"*

**This is not a node.** There's nothing to drag onto your graph. It lives in ComfyUI's left dock, runs in the background, and never touches your workflow.

---

## What it does

- **Auto-captures every run** — no setup, no button to remember to click. It reads the graph straight from ComfyUI's own execution history the moment a prompt finishes.
- **Diffs any two runs** — nodes added, removed, type-swapped, or with changed parameters. Unchanged nodes collapse into a single count instead of cluttering the view.
- **Click a change → it finds it on the canvas.** Click a parameter or a node reference in the diff and the camera flies to it, pulses gold, and (for a single parameter) highlights that exact widget row — not just the node.
- **Understands subgraphs.** Changes inside a subgraph resolve to the real inner node and open the subgraph to show it — or, if the parameter is promoted/exposed onto the outer instance, lands you there directly instead, since that's where you'd actually click to change it.
- **Wipe-compare** the two runs' outputs, with the structural diff in a drawer underneath.
- **Groups** — keep separate workflows' histories apart instead of one giant mixed list. Switch between them with one click; delete old ones when they pile up.
- **Drag-and-drop comparison** for two PNGs (reads the workflow straight out of the file's own embedded metadata) — works even for runs that predate installing this.
- **Optional: open/launch Wedge Studio** from the same panel, with a safety check so it never silently kills an in-progress batch.

## Install

Drop this folder into `ComfyUI/custom_nodes/`, restart ComfyUI, hard-refresh the browser tab (the JS is cached aggressively — `Ctrl+Shift+R` / `Cmd+Shift+R`).

No extra Python dependencies — everything it uses ships with ComfyUI already.

## Using it

Click the **Wedge Diff** tab in the left dock. The panel has three fixed sections (always visible) and one that scrolls:

- **Header** — label field + group chips. Groups keep separate workflows' run histories apart. Type a name, hit **+ Set** to create/switch; click a chip to switch; the **×** deletes a group after a confirm click.
- **Run history** — thumbnails of captured runs for the active group, newest first. Tap to pick which two you're comparing (A/B).
- **Compare bar** — shows the current A/B pair.
- **The diff itself** (this part scrolls independently of everything above it) — added/removed/type-swapped/changed, with collapsed unchanged count. Anything with a node or parameter reference is clickable.
- **Wipe Compare** button at the bottom, enabled once two runs with outputs are selected.

### A note on what gets diffed

The diff is built from the *executed* graph — the one ComfyUI's backend actually ran — not just whatever's sitting on the canvas. That's almost always what you want, but it means a node that's on the canvas but disconnected from any output won't show up, since it never ran either.

### Headless / batch runs

If a run happened with no browser tab open (a Wedge Studio batch, for instance), it won't auto-capture in real time — but it's still sitting in ComfyUI's own history. Hit **↻ Sync** to backfill anything missed next time you open the panel.

## Known limitations, stated plainly

- **Classic canvas only.** The gold pulse/highlight draws via the older litegraph `onDrawForeground` path. If you're running ComfyUI's newer "Nodes 2.0" rendering, centering on a node should still work, but the highlight itself may not draw.
- **Sidebar API varies by ComfyUI frontend version.** If your installed version doesn't expose `registerSidebarTab`, you'll get a floating button bottom-right instead of a dock tab — same functionality, different entry point. The console logs which path it took.
- **`openSubgraph`'s exact signature isn't pinned across every ComfyUI version.** The locate-into-subgraph feature tries two reasonable call shapes and falls back gracefully; if neither works on your version, you'll get a clear toast saying so rather than a silent failure.
- **Promoted-widget detection is intentionally shallow** — it checks the immediate containing subgraph instance only, not every ancestor level. ComfyUI's own widget-promotion feature has open upstream issues around deeper nesting, so this matches its real reliability rather than guessing past it.

If any of the above doesn't behave as described on your version, the console (`F12`) is verbose on purpose — every major step logs with a `[WedgeDiff]` prefix.

## How it works, briefly

No node, no graph caching to fight. A frontend extension listens for ComfyUI's "prompt finished" event, reads the graph back out of ComfyUI's own `/history`, and posts it to a small backend route that hashes/dedupes it into a local SQLite file (`wedge_diff.sqlite3`, created next to this folder — gitignored, it's per-install run data, not something to commit).

```
diff.py              pure graph-diff algorithm (no ComfyUI imports)
db.py                SQLite storage, dedupe-on-identical-hash
history_extract.py   pulls graph + outputs out of a /history record
web/wd_locate.js      subgraph-aware node/widget resolver for the canvas
web/wd_render.js      pure diff -> HTML renderer
web/wedge_diff.js     the panel itself: capture, UI, wipe, locate, Wedge Studio launch
server_routes.py      the handful of HTTP routes tying it together
```

## Testing

```bash
python -m unittest discover -s tests      # backend
node tests/test_render.mjs                 # diff renderer
node tests/test_locate.mjs                 # subgraph/widget resolver
```

All pure logic — none of it needs a running ComfyUI to test.

## License

MIT — see [LICENSE.txt](LICENSE.txt).
