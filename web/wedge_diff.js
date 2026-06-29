// wedge_diff.js — Wedge Diff frontend (Phase 3: sidebar panel + auto-capture)
//
// Two responsibilities, clearly sectioned:
//   1. Auto-capture: on each finished prompt, snapshot it via the
//      backend (unchanged from Phase 2).
//   2. Sidebar panel: a District Zero / Wedge Studio styled panel that
//      lists run history, diffs any two runs, and opens a wipe compare
//      of their outputs.
//
// Everything is namespaced under .wd-root with wd- prefixed classes so
// ComfyUI's own styles can't bleed in and ours can't leak out. CSS is
// injected (not a linked file) so it loads as one unit with no path
// risk. Logging is verbose with a [WedgeDiff] prefix so the first real
// run at the PC is self-diagnosing.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { renderDiff, esc } from "./wd_render.js";
import { splitCompoundId, resolveCompoundNode, findPromotedHost } from "./wd_locate.js";

const LOG = "[WedgeDiff]";
const LABEL_KEY = "wedgeDiff.workflowLabel";
// Resolves to /extensions/ComfyUI-WedgeDiff/district_zero.png if that
// PNG is dropped into web/. Falls back to a CSS diamond via the
// logoImg "error" handler below if it's not there yet.
const LOGO_URL = new URL("./district_zero.png", import.meta.url).href;

/* ============================ styles ============================ */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,400&display=swap');

.wd-root{
  --wd-bg:#0a0a0a; --wd-panel:#0e0e0e; --wd-panel-2:#131313;
  --wd-line:#1f1f1f; --wd-line-2:#2a2a2a;
  --wd-gold:#d18d1f; --wd-gold-dim:#7a5413;
  --wd-text:#e8e4dc; --wd-muted:#6b6862; --wd-muted-2:#48453f;
  --wd-add:#5a9e6f; --wd-del:#b15a5a; --wd-swap:#c79a3a; --wd-blue:#5a86b1;
  font-family:'DM Mono',ui-monospace,monospace; color:var(--wd-text);
  font-size:13px; line-height:1.5; letter-spacing:.2px;
  background:var(--wd-bg); height:100%; overflow:hidden;
  display:flex; flex-direction:column; position:relative;
}
.wd-root *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
.wd-root::after{
  content:"";position:absolute;inset:0;pointer-events:none;z-index:2;
  background:repeating-linear-gradient(0deg,rgba(209,141,31,.035) 0 1px,transparent 1px 3px);
}
.wd-root > *{position:relative;z-index:3}

.wd-hd{
  flex:0 0 auto;
  padding:14px 16px;border-bottom:1px solid var(--wd-line);
  display:flex;align-items:center;background:var(--wd-panel);
}
.wd-logo-img{height:20px;width:auto;display:block;flex:0 0 auto}
.wd-logo-fallback{
  width:20px;height:20px;border:1.5px solid var(--wd-gold);border-radius:3px;
  display:flex;align-items:center;justify-content:center;flex:0 0 auto;transform:rotate(45deg);
}
.wd-logo-fallback::before{content:"";width:6px;height:6px;background:var(--wd-gold);box-shadow:0 0 8px var(--wd-gold)}
.wd-divider{width:1px;height:15px;background:var(--wd-line-2);margin:0 12px;flex:0 0 auto}
.wd-nm{font-size:12px;font-weight:500;letter-spacing:2.5px;color:var(--wd-gold)}
.wd-ctx{font-size:11px;letter-spacing:1.5px;color:var(--wd-muted-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wd-icon-btn{
  margin-left:auto;flex:0 0 auto;background:var(--wd-panel-2);border:1px solid var(--wd-line-2);
  color:var(--wd-muted);width:24px;height:24px;border-radius:3px;cursor:pointer;font-size:12px;
  display:flex;align-items:center;justify-content:center;transition:border-color .15s,color .15s;
}
.wd-icon-btn:hover{border-color:var(--wd-gold);color:var(--wd-gold)}
.wd-icon-btn + .wd-icon-btn{margin-left:6px}
.wd-ws-settings{
  flex:0 0 auto;display:none;padding:10px 16px;border-bottom:1px solid var(--wd-line);
  background:var(--wd-panel-2);gap:8px;flex-direction:column;
}
.wd-ws-settings.wd-open{display:flex}
.wd-ws-row{display:flex;align-items:center;gap:10px}
.wd-ws-row label{font-size:10px;color:var(--wd-muted);letter-spacing:1px;width:46px;flex:0 0 auto}
.wd-ws-row input{
  flex:1;min-width:0;background:var(--wd-panel);border:1px solid var(--wd-line-2);color:var(--wd-gold);
  font-family:inherit;font-size:11px;padding:5px 8px;border-radius:3px;letter-spacing:.3px;
}
.wd-ws-row input:focus{outline:none;border-color:var(--wd-gold-dim)}
.wd-ws-hint{font-size:9px;color:var(--wd-muted-2);letter-spacing:.3px;line-height:1.5}

.wd-label-row{flex:0 0 auto;padding:11px 16px;border-bottom:1px solid var(--wd-line);display:flex;align-items:center;gap:10px}
.wd-label-row label{font-size:10px;color:var(--wd-muted);letter-spacing:1px;white-space:nowrap}
.wd-label-row input{
  flex:1;min-width:0;background:var(--wd-panel-2);border:1px solid var(--wd-line-2);color:var(--wd-gold);
  font-family:inherit;font-size:12px;padding:6px 9px;border-radius:3px;letter-spacing:.5px;
}
.wd-label-row input:focus{outline:none;border-color:var(--wd-gold-dim)}
.wd-setbtn{
  flex:0 0 auto;background:var(--wd-panel-2);border:1px solid var(--wd-gold-dim);color:var(--wd-gold);
  font-family:inherit;font-size:10px;letter-spacing:1px;padding:6px 10px;border-radius:3px;cursor:pointer;
  text-transform:uppercase;transition:background .15s,color .15s;
}
.wd-setbtn:hover{background:var(--wd-gold);color:#0a0a0a}

.wd-groups{flex:0 0 auto;display:flex;flex-wrap:wrap;gap:6px;padding:0 16px 4px}
.wd-grp{
  display:flex;align-items:center;gap:6px;background:var(--wd-panel-2);border:1px solid var(--wd-line-2);
  border-radius:3px;padding:4px 6px 4px 9px;cursor:pointer;font-size:10.5px;letter-spacing:.3px;
  transition:border-color .15s,background .15s;
}
.wd-grp:hover{border-color:var(--wd-muted-2)}
.wd-grp-active{border-color:var(--wd-gold);background:#16120a}
.wd-grp-active .wd-grp-name{color:var(--wd-gold)}
.wd-grp-name{color:var(--wd-text)}
.wd-grp-count{color:var(--wd-muted-2);font-size:9px;font-variant-numeric:tabular-nums}
.wd-grp-x{
  color:var(--wd-muted-2);font-size:13px;line-height:1;width:15px;height:15px;display:flex;
  align-items:center;justify-content:center;border-radius:2px;
}
.wd-grp-x:hover{color:var(--wd-del);background:rgba(177,90,90,.12)}
.wd-grp-x.wd-confirm{color:#0a0a0a;background:var(--wd-del);font-size:9px;width:auto;padding:0 5px;letter-spacing:.5px}

.wd-cap{flex:0 0 auto;font-size:9px;letter-spacing:2px;color:var(--wd-muted-2);padding:13px 16px 7px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center}
.wd-sync{background:none;border:1px solid var(--wd-line-2);color:var(--wd-muted);font-family:inherit;font-size:9px;letter-spacing:1px;padding:3px 8px;border-radius:3px;cursor:pointer;text-transform:uppercase}
.wd-sync:hover{border-color:var(--wd-gold);color:var(--wd-gold)}

.wd-history{flex:0 0 auto;display:flex;gap:8px;overflow-x:auto;padding:2px 16px 13px;scrollbar-width:thin}
.wd-history::-webkit-scrollbar{height:5px}
.wd-history::-webkit-scrollbar-thumb{background:var(--wd-line-2);border-radius:3px}
.wd-run{
  flex:0 0 auto;width:96px;cursor:pointer;border:1px solid var(--wd-line-2);border-radius:4px;
  overflow:hidden;background:var(--wd-panel-2);transition:border-color .15s,transform .15s,box-shadow .15s;position:relative;
}
.wd-run:hover{border-color:var(--wd-muted-2);transform:translateY(-1px);box-shadow:0 3px 12px rgba(0,0,0,.4)}
.wd-run.wd-sel-a{border-color:var(--wd-gold)}
.wd-run.wd-sel-b{border-color:var(--wd-blue)}
.wd-run .wd-thumb{height:60px;width:100%;position:relative;overflow:hidden;background:#161616 center/cover no-repeat}
.wd-run .wd-meta{padding:5px 6px 6px}
.wd-run .wd-t{font-size:9px;color:var(--wd-muted)}
.wd-run .wd-h{font-size:10px;color:var(--wd-text);margin-top:1px;letter-spacing:.5px}
.wd-run .wd-badge{position:absolute;top:4px;left:4px;font-size:8px;letter-spacing:1px;padding:2px 5px;border-radius:2px;font-weight:500}
.wd-run .wd-badge.wd-a{background:var(--wd-gold);color:#0a0a0a}
.wd-run .wd-badge.wd-b{background:var(--wd-blue);color:#0a0a0a}
.wd-run.wd-live .wd-meta::after{content:"● live";color:var(--wd-gold);font-size:8px;display:block;margin-top:2px;letter-spacing:1px}

.wd-cmp-bar{flex:0 0 auto;margin:0 16px;padding:9px 11px;background:var(--wd-panel-2);border:1px solid var(--wd-line-2);border-radius:4px;display:flex;align-items:center;gap:8px;font-size:10px;flex-wrap:wrap}
.wd-cmp-bar .wd-chip{padding:2px 7px;border-radius:2px;font-weight:500;font-size:10px}
.wd-cmp-bar .wd-chip.wd-a{background:var(--wd-gold);color:#0a0a0a}
.wd-cmp-bar .wd-chip.wd-b{background:var(--wd-blue);color:#0a0a0a}
.wd-cmp-bar .wd-arrow{color:var(--wd-muted-2)}

.wd-diff{flex:1 1 auto;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:14px 16px;scrollbar-width:thin}
.wd-diff::-webkit-scrollbar{width:6px}
.wd-diff::-webkit-scrollbar-thumb{background:var(--wd-line-2);border-radius:3px}
.wd-summary{display:flex;gap:14px;flex-wrap:wrap;padding-bottom:13px;margin-bottom:13px;border-bottom:1px solid var(--wd-line);font-size:10px;letter-spacing:.5px}
.wd-summary .wd-s{display:flex;align-items:center;gap:5px;color:var(--wd-muted)}
.wd-summary .wd-s b{color:var(--wd-text);font-weight:500}
.wd-summary .wd-s .wd-k{width:6px;height:6px;border-radius:1px}
.wd-group{margin-bottom:16px}
.wd-group > .wd-gh{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--wd-muted);margin-bottom:8px;display:flex;align-items:center;gap:7px}
.wd-group > .wd-gh .wd-n{color:#0a0a0a;border-radius:2px;padding:0 5px;font-size:9px;font-weight:500}
.wd-card{border:1px solid var(--wd-line-2);border-radius:4px;background:var(--wd-panel-2);margin-bottom:7px;overflow:hidden}
.wd-card .wd-ch{padding:8px 11px;display:flex;align-items:center;gap:8px;border-bottom:1px solid transparent}
.wd-card.wd-has-body .wd-ch{border-bottom-color:var(--wd-line)}
.wd-card .wd-sigil{font-size:12px;width:16px;text-align:center;flex:0 0 auto;font-weight:500}
.wd-card .wd-ctype{color:var(--wd-text);font-size:12px;letter-spacing:.3px}
.wd-card .wd-cid{color:var(--wd-muted-2);font-size:10px;margin-left:auto}
.wd-card.wd-addc{border-color:#23402c} .wd-card.wd-addc .wd-sigil{color:var(--wd-add)} .wd-card.wd-addc .wd-ch{background:#101a13}
.wd-card.wd-delc{border-color:#3f2222} .wd-card.wd-delc .wd-sigil{color:var(--wd-del)} .wd-card.wd-delc .wd-ch{background:#1a1010}
.wd-card.wd-swapc{border-color:#3a3014} .wd-card.wd-swapc .wd-sigil{color:var(--wd-swap)} .wd-card.wd-swapc .wd-ch{background:#1a160c}
.wd-card .wd-body{padding:7px 11px 9px}
.wd-kv{display:grid;grid-template-columns:1fr auto;gap:6px 10px;align-items:baseline;padding:3px 4px;font-size:11px;margin:0 -4px;border-radius:3px}
.wd-widgetrow{cursor:pointer}
.wd-widgetrow:hover{background:rgba(209,141,31,.14);box-shadow:0 0 0 1px var(--wd-gold-dim) inset}
.wd-widgetrow:hover .wd-key{color:var(--wd-gold)}
.wd-kv .wd-key{color:var(--wd-muted);letter-spacing:.3px}
.wd-kv .wd-val{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.wd-old{color:var(--wd-muted-2);text-decoration:line-through;text-decoration-color:var(--wd-del)}
.wd-ar{color:var(--wd-muted-2);margin:0 6px}
.wd-new{color:var(--wd-gold)}
.wd-link-line{font-size:10.5px;color:var(--wd-muted);padding:4px 0;letter-spacing:.2px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.wd-link-in{color:var(--wd-text)}
.wd-swap-line{font-size:11px;padding:2px 0}
/* clickable node references (endpoint chips + id badges) */
.wd-noderef{cursor:pointer;border-radius:3px;transition:background .12s,color .12s,box-shadow .12s}
.wd-noderef:hover{background:rgba(209,141,31,.14);box-shadow:0 0 0 1px var(--wd-gold-dim) inset}
.wd-endpoint{display:inline-flex;align-items:baseline;gap:4px;background:var(--wd-panel);border:1px solid var(--wd-line-2);padding:2px 6px}
.wd-endpoint:hover{border-color:var(--wd-gold)}
.wd-ep-name{color:var(--wd-text)}
.wd-noderef-id{color:var(--wd-muted-2);font-size:9px;font-variant-numeric:tabular-nums}
.wd-noderef-none{color:var(--wd-muted-2);font-style:italic}
.wd-cid.wd-noderef{padding:1px 5px}
.wd-cid.wd-noderef:hover{color:var(--wd-gold)}
.wd-unchanged{border:1px dashed var(--wd-line-2);border-radius:4px;padding:9px 11px;color:var(--wd-muted-2);font-size:10.5px;letter-spacing:.5px}
.wd-empty,.wd-msg{padding:40px 20px;text-align:center;color:var(--wd-muted);font-size:12px;line-height:1.7}
.wd-msg .wd-msg-mark{font-size:30px;color:var(--wd-muted-2);margin-bottom:10px}
.wd-identical{padding:40px 20px;text-align:center;color:var(--wd-muted)}
.wd-identical-mark{font-size:34px;color:var(--wd-gold);margin-bottom:10px}
/* transient toast for locate feedback */
.wd-toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(10px);z-index:99999;
  background:#16120a;border:1px solid var(--wd-gold-dim);color:var(--wd-text);font-family:'DM Mono',ui-monospace,monospace;
  font-size:11px;letter-spacing:.3px;padding:9px 14px;border-radius:4px;max-width:80vw;text-align:center;
  opacity:0;transition:opacity .2s,transform .2s;pointer-events:none;box-shadow:0 6px 24px rgba(0,0,0,.5)}
.wd-toast.wd-show{opacity:1;transform:translateX(-50%) translateY(0)}
.wd-sub2{font-size:10px;color:var(--wd-muted-2);margin-top:6px;letter-spacing:.5px}

.wd-foot{flex:0 0 auto;padding:12px 16px;border-top:1px solid var(--wd-line);background:var(--wd-panel)}
.wd-wipe-btn{position:relative;overflow:hidden;width:100%;padding:12px;background:var(--wd-gold);color:#0a0a0a;border:none;font-family:inherit;font-weight:500;font-size:12px;letter-spacing:1.5px;border-radius:3px;cursor:pointer;text-transform:uppercase;transition:transform .15s,box-shadow .15s,filter .15s}
.wd-wipe-btn:disabled{opacity:.4;cursor:not-allowed}
.wd-wipe-btn::before{content:"";position:absolute;top:0;left:-100%;width:100%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.4),transparent);transition:left .5s}
.wd-wipe-btn:not(:disabled):hover{transform:translateY(-2px);box-shadow:0 5px 20px rgba(209,141,31,.45);filter:brightness(1.05)}
.wd-wipe-btn:not(:disabled):hover::before{left:100%}

/* wipe overlay (fixed, fullscreen) */
.wd-overlay{position:fixed;inset:0;background:rgba(5,5,5,.97);z-index:99998;display:none;flex-direction:column;font-family:'DM Mono',ui-monospace,monospace}
.wd-overlay.wd-open{display:flex}
.wd-ov-hd{padding:14px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--wd-line,#1f1f1f)}
.wd-ov-hd .wd-ovt{font-size:11px;letter-spacing:2px;color:#e8e4dc}
.wd-ov-hd .wd-x{background:none;border:1px solid #2a2a2a;color:#6b6862;width:30px;height:30px;border-radius:4px;cursor:pointer;font-family:inherit;font-size:15px}
.wd-ov-hd .wd-x:hover{border-color:#d18d1f;color:#d18d1f}
.wd-wipe-wrap{flex:1;display:flex;align-items:center;justify-content:center;padding:16px;min-height:0}
.wd-wipe{position:relative;width:100%;max-width:760px;max-height:100%;aspect-ratio:16/9;border:1px solid #2a2a2a;border-radius:5px;overflow:hidden;touch-action:none;cursor:ew-resize;user-select:none;background:#000}
.wd-frame{position:absolute;inset:0;overflow:hidden}
.wd-frame img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000}
.wd-frame.wd-top{clip-path:inset(0 50% 0 0);will-change:clip-path}
.wd-flabel{position:absolute;top:9px;font-size:9px;letter-spacing:1.5px;padding:3px 7px;border-radius:2px;font-weight:500;z-index:3}
.wd-flabel.wd-a{left:9px;background:#d18d1f;color:#0a0a0a}
.wd-flabel.wd-b{right:9px;background:#5a86b1;color:#0a0a0a}
.wd-handle{position:absolute;top:0;bottom:0;width:2px;background:#d18d1f;left:50%;transform:translateX(-1px);z-index:4;box-shadow:0 0 10px rgba(209,141,31,.6)}
.wd-handle::after{content:"⇆";position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:30px;height:30px;background:#d18d1f;color:#0a0a0a;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px}
.wd-novid{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#6b6862;font-size:11px;text-align:center;padding:20px}

/* floating fallback (only if sidebar API absent) */
/* styled confirm modal — used for the Wedge Studio restart warning */
.wd-confirm-overlay{
  position:fixed;inset:0;background:rgba(5,5,5,.85);z-index:99997;
  display:none;align-items:center;justify-content:center;
  font-family:'DM Mono',ui-monospace,monospace;
}
.wd-confirm-overlay.wd-open{display:flex}
.wd-confirm-box{
  width:340px;max-width:calc(100vw - 40px);background:#0e0e0e;border:1px solid #2a2a2a;
  border-radius:6px;padding:18px;box-shadow:0 12px 40px rgba(0,0,0,.6);
}
.wd-confirm-msg{font-size:12px;color:#e8e4dc;line-height:1.6;margin-bottom:16px;white-space:pre-line}
.wd-confirm-btns{display:flex;gap:8px}
.wd-confirm-btns button{
  flex:1;padding:9px;font-family:inherit;font-size:11px;letter-spacing:.5px;border-radius:3px;
  cursor:pointer;text-transform:uppercase;transition:filter .15s;
}
.wd-confirm-cancel{background:#131313;border:1px solid #2a2a2a;color:#888880}
.wd-confirm-cancel:hover{border-color:#6b6862;color:#e8e4dc}
.wd-confirm-ok{background:#d18d1f;border:1px solid #d18d1f;color:#0a0a0a;font-weight:500}
.wd-confirm-ok:hover{filter:brightness(1.08)}

.wd-fab{position:fixed;right:18px;bottom:18px;z-index:99990;width:46px;height:46px;border-radius:50%;background:#d18d1f;color:#0a0a0a;border:none;cursor:pointer;font-size:18px;box-shadow:0 4px 16px rgba(0,0,0,.5);font-family:inherit}
.wd-float-panel{position:fixed;right:18px;bottom:74px;z-index:99990;width:380px;max-width:calc(100vw - 36px);height:560px;max-height:calc(100vh - 110px);border:1px solid #2a2a2a;border-radius:8px;overflow:hidden;display:none;box-shadow:0 8px 40px rgba(0,0,0,.6)}
.wd-float-panel.wd-open{display:block}
`;

function injectStyles() {
  if (document.getElementById("wd-styles")) return;
  const s = document.createElement("style");
  s.id = "wd-styles";
  s.textContent = CSS;
  document.head.appendChild(s);
}

/* ============================ helpers ============================ */
function getLabel() {
  try { return localStorage.getItem(LABEL_KEY) || "default"; }
  catch (e) { return "default"; }
}
function setLabel(v) {
  try { localStorage.setItem(LABEL_KEY, v); } catch (e) {}
}
function apiUrl(path) {
  return typeof api.apiURL === "function" ? api.apiURL(path) : path;
}
// Reverse db's posixpath.join(subfolder, filename) back into a /view URL.
function viewUrl(relPath, type = "output") {
  if (!relPath) return null;
  const idx = relPath.lastIndexOf("/");
  const subfolder = idx >= 0 ? relPath.slice(0, idx) : "";
  const filename = idx >= 0 ? relPath.slice(idx + 1) : relPath;
  const qs = new URLSearchParams({ filename, subfolder, type });
  return apiUrl(`/view?${qs.toString()}`);
}
function isImagePath(p) {
  return /\.(png|jpe?g|webp|gif|bmp)$/i.test(p || "");
}
function shortId(runId) {
  return (runId || "").replace(/-/g, "").slice(0, 4);
}
function hhmm(epoch) {
  try {
    const d = new Date((epoch || 0) * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch (e) { return ""; }
}

/* ============================ capture (Phase 2) ============================ */
function extractPromptId(detail) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (detail.prompt_id) return detail.prompt_id;
  if (Array.isArray(detail.prompt) && detail.prompt[1]) return detail.prompt[1];
  return null;
}
async function capture(promptId) {
  const workflow_label = getLabel();
  console.log(`${LOG} prompt finished: ${promptId} -> capturing (label="${workflow_label}")`);
  try {
    const res = await api.fetchApi("/wedge_diff/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt_id: promptId, workflow_label }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { console.warn(`${LOG} capture HTTP ${res.status}:`, data); return; }
    if (data.ok) {
      console.log(`${LOG} captured: ${data.is_new ? "NEW row" : "deduped"}, run_id=${data.run_id}, outputs=${data.output_count}`);
      if (state.mounted) refreshAll(); // live-refresh history + group counts
    } else {
      console.warn(`${LOG} capture not-ok:`, data);
    }
  } catch (err) {
    console.error(`${LOG} capture failed:`, err);
  }
}

/* ============================ panel state + data ============================ */
const state = { history: [], groups: [], aId: null, bId: null, mounted: false, container: null };

async function loadHistory() {
  const label = getLabel();
  try {
    const res = await api.fetchApi(`/wedge_diff/history?workflow_label=${encodeURIComponent(label)}&limit=50`);
    state.history = await res.json();
  } catch (err) {
    console.error(`${LOG} loadHistory failed:`, err);
    state.history = [];
  }
  // default selection: two most recent (history is newest-first)
  const ids = state.history.map((r) => r.run_id);
  if (!ids.includes(state.bId)) state.bId = ids[0] || null;
  if (!ids.includes(state.aId)) state.aId = ids[1] || null;
  renderHistory();
  renderCompareBar();
  loadDiff();
}

async function loadDiff() {
  const diffEl = state.container?.querySelector("#wd-diff");
  if (!diffEl) return;
  if (!state.aId || !state.bId) {
    const n = state.history.length;
    diffEl.innerHTML = `<div class="wd-msg"><div class="wd-msg-mark">⧉</div>${
      n === 0 ? "No runs captured yet.<br>Queue a prompt to begin." :
      "Need at least two runs to compare.<br>Queue another to see a diff."
    }</div>`;
    updateWipeBtn();
    return;
  }
  if (state.aId === state.bId) {
    diffEl.innerHTML = `<div class="wd-msg"><div class="wd-msg-mark">≡</div>Pick two different runs.</div>`;
    updateWipeBtn();
    return;
  }
  try {
    const res = await api.fetchApi(`/wedge_diff/diff?run_a=${state.aId}&run_b=${state.bId}`);
    const d = await res.json();
    diffEl.innerHTML = renderDiff(d);
    wireNodeRefs(diffEl);
  } catch (err) {
    console.error(`${LOG} loadDiff failed:`, err);
    diffEl.innerHTML = `<div class="wd-msg">Diff failed — see console.</div>`;
  }
  updateWipeBtn();
}

function runById(id) { return state.history.find((r) => r.run_id === id); }

/* ============================ render ============================ */
function renderHistory() {
  const el = state.container?.querySelector("#wd-history");
  if (!el) return;
  if (!state.history.length) {
    el.innerHTML = `<div style="color:var(--wd-muted-2);font-size:10px;padding:8px 0">no runs yet</div>`;
    return;
  }
  el.innerHTML = state.history.map((r, i) => {
    const sel = r.run_id === state.aId ? "wd-sel-a" : r.run_id === state.bId ? "wd-sel-b" : "";
    const badge = r.run_id === state.aId ? '<span class="wd-badge wd-a">A</span>' :
                  r.run_id === state.bId ? '<span class="wd-badge wd-b">B</span>' : "";
    const live = i === 0 ? "wd-live" : "";
    const thumb = r.thumbnail_path && isImagePath(r.thumbnail_path)
      ? `style="background-image:url('${viewUrl(r.thumbnail_path)}')"` : "";
    return `<div class="wd-run ${sel} ${live}" data-id="${r.run_id}">
      <div class="wd-thumb" ${thumb}>${badge}</div>
      <div class="wd-meta"><div class="wd-t">${hhmm(r.updated_at)}</div><div class="wd-h">${shortId(r.run_id)}</div></div>
    </div>`;
  }).join("");

  el.querySelectorAll(".wd-run").forEach((node) => {
    node.addEventListener("click", () => onRunClick(node.dataset.id));
  });
}

// Click cycles selection: first click sets A, next sets B, then A again...
function onRunClick(id) {
  if (state.aId === id) { state.aId = null; }
  else if (state.bId === id) { state.bId = null; }
  else if (!state.aId) { state.aId = id; }
  else if (!state.bId) { state.bId = id; }
  else { state.aId = id; } // both full -> replace A
  renderHistory();
  renderCompareBar();
  loadDiff();
}

function renderCompareBar() {
  const el = state.container?.querySelector("#wd-cmp-bar");
  if (!el) return;
  const a = runById(state.aId), b = runById(state.bId);
  el.innerHTML = `
    <span class="wd-chip wd-a">A</span><span>${a ? shortId(a.run_id) + " · " + hhmm(a.updated_at) : "—"}</span>
    <span class="wd-arrow">↔</span>
    <span class="wd-chip wd-b">B</span><span>${b ? shortId(b.run_id) + " · " + hhmm(b.updated_at) : "—"}</span>
    <span style="color:var(--wd-muted-2);margin-left:auto">tap runs to change</span>`;
}

function updateWipeBtn() {
  const btn = state.container?.querySelector("#wd-wipe-btn");
  if (!btn) return;
  const a = runById(state.aId), b = runById(state.bId);
  const canWipe = a && b && a.run_id !== b.run_id &&
    (a.output_paths || []).length && (b.output_paths || []).length;
  btn.disabled = !canWipe;
}

/* ============================ locate on canvas ============================ */
// Wire every clickable node reference (.wd-noderef) in a freshly
// rendered diff to jump to + flash that node (and, for widget rows,
// the specific parameter row) on the ComfyUI canvas.
function wireNodeRefs(root) {
  root.querySelectorAll(".wd-noderef").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      locateNode(el.dataset.nodeId, el.dataset.type || null, el.dataset.widget || null);
    });
  });
}

function locateNode(nodeIdRaw, expectedType, widgetKey = null) {
  const rootGraph = app.graph;
  const canvas = app.canvas;
  if (!rootGraph || !canvas) { showToast("Canvas not available"); return; }

  // Compound ids like "82:81" mean: outer subgraph instance #82, inner
  // node #81 inside its interior. Plain "35" is just ["35"] — no
  // subgraph involved, same as before this fix.
  const idChain = splitCompoundId(nodeIdRaw);
  const resolved = resolveCompoundNode(rootGraph, idChain);

  if (!resolved.found) {
    if (resolved.reason === "no-subgraph") {
      showToast(`#${resolved.failedId} isn't a subgraph on the current canvas — its structure may have changed since this run`);
    } else if (idChain.length > 1) {
      showToast(`Couldn't find #${resolved.failedId} inside that subgraph — this diff may be between past runs`);
    } else {
      showToast(`Node #${nodeIdRaw} isn't on the current canvas — this diff may be between past runs`);
    }
    return;
  }

  // If this is a parameter change inside a subgraph, check whether
  // it's promoted/exposed onto the immediate containing instance —
  // if so, that's the node the user can actually click to change it,
  // so land there directly instead of diving into the subgraph.
  const promotedHost = findPromotedHost(resolved.openChain, widgetKey);
  if (promotedHost) {
    try { canvas.centerOnNode(promotedHost); } catch (e) { console.warn(`${LOG} centerOnNode failed`, e); }
    try { canvas.selectNodes?.([promotedHost]); } catch (e) {}
    flashNodeGold(promotedHost, widgetKey);
    try { (canvas.graph?.setDirtyCanvas || canvas.setDirty)?.call(canvas.graph || canvas, true, true); } catch (e) {}
    const hostTitle = promotedHost.title || promotedHost.type || `#${promotedHost.id}`;
    showToast(`→ ${hostTitle} (#${promotedHost.id}) · ${widgetKey} — promoted from inside the subgraph`);
    return;
  }

  // Enter every subgraph interior on the path to the node, outermost
  // first, so the camera ends up showing the right nested view before
  // we try to center on anything inside it.
  if (resolved.openChain.length > 0) {
    if (typeof canvas.openSubgraph !== "function") {
      showToast(`This ComfyUI version's canvas can't navigate into subgraphs automatically — open it manually, then try again`);
      return;
    }
    for (const step of resolved.openChain) {
      // openSubgraph's exact accepted argument isn't confirmed across
      // every ComfyUI version — try the subgraph interior itself first
      // (most consistent with closeSubgraph's documented LGraph param),
      // then fall back to the outer instance node.
      let opened = false;
      try { canvas.openSubgraph(step.subgraph); opened = true; } catch (e) {}
      if (!opened) {
        try { canvas.openSubgraph(step.outerNode); opened = true; } catch (e) {}
      }
      if (!opened) {
        console.warn(`${LOG} openSubgraph failed for instance #${step.outerNode.id}`);
        showToast(`Couldn't open the subgraph at #${step.outerNode.id} — see console`);
        return;
      }
    }
  }

  const node = resolved.finalNode;
  // centerOnNode + selectNodes are documented LGraphCanvas methods.
  try { canvas.centerOnNode(node); } catch (e) { console.warn(`${LOG} centerOnNode failed`, e); }
  try { canvas.selectNodes?.([node]); } catch (e) {}
  const widgetFound = flashNodeGold(node, widgetKey);
  try { (canvas.graph?.setDirtyCanvas || canvas.setDirty)?.call(canvas.graph || canvas, true, true); } catch (e) {}

  const title = node.title || node.type || `#${nodeIdRaw}`;
  let msg = `→ ${title} (#${nodeIdRaw})`;
  if (widgetKey) {
    msg += widgetFound ? ` · ${widgetKey}` : ` — couldn't pinpoint "${widgetKey}" (renamed or hidden on this node?)`;
  }
  if (expectedType && node.type && node.type !== expectedType) {
    msg += ` — note: it's a ${node.type} on canvas, was ${expectedType} in this run`;
  }
  if (resolved.openChain.length > 0) {
    msg += ` (inside subgraph)`;
  }
  showToast(msg);
}

// Pulsing gold highlight for ~2s: always outlines the whole node, and
// additionally bands a specific widget's row if widgetKey is given.
// State lives in a single node._wdFlash object (not separate flags per
// call) so re-triggering — even with a different widgetKey — just
// updates the target instead of stacking a second onDrawForeground
// wrapper. Returns true/false if a widget was requested and found/not
// found; returns null if no widgetKey was requested.
function flashNodeGold(node, widgetKey = null) {
  node._wdFlash = { start: performance.now(), widgetKey };
  const widget = widgetKey ? node.widgets?.find((w) => w.name === widgetKey) : null;
  const found = widgetKey ? !!widget : null;

  if (node._wdFlashWrapped) { node.setDirtyCanvas?.(true, true); return found; }
  node._wdFlashWrapped = true;
  const prev = node.onDrawForeground;
  const DURATION = 2000;
  const titleH = (window.LiteGraph && LiteGraph.NODE_TITLE_HEIGHT) || 30;
  const widgetH = (window.LiteGraph && LiteGraph.NODE_WIDGET_HEIGHT) || 20;

  node.onDrawForeground = function (ctx) {
    prev?.apply(this, arguments);
    const flash = node._wdFlash;
    if (!flash) return;
    const t = (performance.now() - flash.start) / DURATION;
    if (t >= 1) { node.onDrawForeground = prev; node._wdFlashWrapped = false; node._wdFlash = null; return; }
    const pulse = 0.5 + 0.5 * Math.sin(t * Math.PI * 6); // a few pulses
    const alpha = 0.35 + 0.55 * pulse;

    ctx.save();
    ctx.strokeStyle = `rgba(209,141,31,${alpha})`;
    ctx.lineWidth = 3;
    const w = this.size[0], h = this.flags?.collapsed ? 0 : this.size[1];
    ctx.strokeRect(-3, -titleH - 3, w + 6, h + titleH + 6);
    ctx.restore();

    // Re-look-up the widget each frame (not just at flash start): if
    // the node was collapsed/resized when clicked, last_y may not have
    // been computed yet on the first frame, but will be by the next.
    const wKey = flash.widgetKey;
    const w2 = wKey ? this.widgets?.find((x) => x.name === wKey) : null;
    if (w2 && !this.flags?.collapsed && typeof w2.last_y === "number") {
      const rowH =
        (typeof w2.computeSize === "function" ? w2.computeSize(this.size[0])[1] : null) || widgetH;
      ctx.save();
      ctx.fillStyle = `rgba(209,141,31,${alpha * 0.22})`;
      ctx.strokeStyle = `rgba(209,141,31,${alpha})`;
      ctx.lineWidth = 2;
      const bx = 4, by = w2.last_y - 1, bw = this.size[0] - 8, bh = rowH + 2;
      if (ctx.roundRect) {
        ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, 4); ctx.fill(); ctx.stroke();
      } else {
        ctx.fillRect(bx, by, bw, bh); ctx.strokeRect(bx, by, bw, bh);
      }
      ctx.restore();
    }
    node.setDirtyCanvas?.(true, true); // keep the animation going
  };
  node.setDirtyCanvas?.(true, true);
  return found;
}

let _toastTimer = null;
function showToast(msg) {
  let t = document.getElementById("wd-toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "wd-toast";
    t.className = "wd-toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  // force reflow so the transition re-triggers on rapid successive toasts
  void t.offsetWidth;
  t.classList.add("wd-show");
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove("wd-show"), 2600);
}

/* ============================ wipe ============================ */
function frameHtml(run, side) {
  const path = (run.output_paths || [])[0];
  const label = side === "a" ? "A" : "B";
  if (path && isImagePath(path)) {
    return `<img src="${viewUrl(path)}" alt="${label}"><span class="wd-flabel wd-${side}">${label} · ${shortId(run.run_id)}</span>`;
  }
  // non-image output (e.g. video) — no inline frame to wipe
  return `<div class="wd-novid">${label}: ${path ? "video output<br>(open in ComfyUI to view)" : "no output"}</div>
          <span class="wd-flabel wd-${side}">${label} · ${shortId(run.run_id)}</span>`;
}

function openWipe() {
  const a = runById(state.aId), b = runById(state.bId);
  if (!a || !b) return;
  let ov = document.getElementById("wd-overlay");
  if (!ov) {
    ov = document.createElement("div");
    ov.id = "wd-overlay";
    ov.className = "wd-overlay";
    document.body.appendChild(ov);
  }
  ov.innerHTML = `
    <div class="wd-ov-hd"><span class="wd-ovt">WIPE COMPARE · A ↔ B</span>
      <button class="wd-x" id="wd-ov-x">✕</button></div>
    <div class="wd-wipe-wrap">
      <div class="wd-wipe" id="wd-wipe">
        <div class="wd-frame wd-bottom">${frameHtml(b, "b")}</div>
        <div class="wd-frame wd-top" id="wd-topframe">${frameHtml(a, "a")}</div>
        <div class="wd-handle" id="wd-handle"></div>
      </div>
    </div>`;
  ov.classList.add("wd-open");
  document.getElementById("wd-ov-x").addEventListener("click", closeWipe);
  initWipeDrag();
  setWipe(50);
}
function closeWipe() {
  document.getElementById("wd-overlay")?.classList.remove("wd-open");
}
function setWipe(pct) {
  pct = Math.max(0, Math.min(100, pct));
  const top = document.getElementById("wd-topframe");
  const handle = document.getElementById("wd-handle");
  // Clip the full-size top frame to reveal only its left `pct`%. The
  // image inside stays full-size and anchored, so it lines up exactly
  // with the bottom frame instead of shrinking with the wipe.
  if (top) top.style.clipPath = `inset(0 ${100 - pct}% 0 0)`;
  if (handle) handle.style.left = pct + "%";
}
function initWipeDrag() {
  const wipe = document.getElementById("wd-wipe");
  if (!wipe) return;
  let drag = false;
  const move = (clientX) => {
    const r = wipe.getBoundingClientRect();
    setWipe(((clientX - r.left) / r.width) * 100);
  };
  const down = (e) => { drag = true; move((e.touches ? e.touches[0] : e).clientX); e.preventDefault(); };
  const mv = (e) => { if (drag) move((e.touches ? e.touches[0] : e).clientX); };
  const up = () => { drag = false; };
  wipe.addEventListener("mousedown", down);
  wipe.addEventListener("touchstart", down, { passive: false });
  window.addEventListener("mousemove", mv);
  window.addEventListener("touchmove", mv, { passive: false });
  window.addEventListener("mouseup", up);
  window.addEventListener("touchend", up);
}

/* ============================ panel shell ============================ */
function buildPanel(container) {
  injectStyles();
  state.container = container;
  state.mounted = true;
  container.classList.add("wd-root");
  container.innerHTML = `
    <div class="wd-hd">
      <img class="wd-logo-img" src="${LOGO_URL}" alt="DZ">
      <span class="wd-divider"></span>
      <span class="wd-nm">WEDGE DIFF</span>
      <span class="wd-divider"></span>
      <span class="wd-ctx" id="wd-ctx">${getLabel()}</span>
      <button class="wd-icon-btn" id="wd-ws-open" title="Open Wedge Studio">⤴</button>
      <button class="wd-icon-btn" id="wd-ws-gear" title="Wedge Studio settings">⚙</button>
    </div>
    <div class="wd-ws-settings" id="wd-ws-settings">
      <div class="wd-ws-row">
        <label>URL</label>
        <input id="wd-ws-url" placeholder="http://localhost:8080" spellcheck="false">
      </div>
      <div class="wd-ws-row">
        <label>FOLDER</label>
        <input id="wd-ws-folder" placeholder="D:\\path\\to\\wedge_studio" spellcheck="false">
      </div>
      <div class="wd-ws-hint">Folder is only needed to auto-launch it when it's not already running.</div>
    </div>
    <div class="wd-label-row">
      <label>GROUP</label>
      <input id="wd-label" value="${getLabel().replace(/"/g, "&quot;")}" spellcheck="false"
             placeholder="group name" title="Type a group name and press Set (or Enter)">
      <button class="wd-setbtn" id="wd-setgroup" title="Create / switch to this group">+ Set</button>
    </div>
    <div class="wd-groups" id="wd-groups"></div>
    <div class="wd-cap"><span>Run history</span>
      <button class="wd-sync" id="wd-sync">↻ Sync</button></div>
    <div class="wd-history" id="wd-history"></div>
    <div class="wd-cmp-bar" id="wd-cmp-bar"></div>
    <div class="wd-diff" id="wd-diff"></div>
    <div class="wd-foot">
      <button class="wd-wipe-btn" id="wd-wipe-btn" disabled>◧ Open Wipe Compare</button>
    </div>`;

  const labelInput = container.querySelector("#wd-label");
  // If the District Zero PNG isn't in web/ yet, swap to the CSS diamond.
  const logoImg = container.querySelector(".wd-logo-img");
  if (logoImg) {
    logoImg.addEventListener("error", () => {
      logoImg.outerHTML = '<span class="wd-logo-fallback"></span>';
    });
  }
  // Explicit "Set" replaces the old switch-on-blur behavior: type a
  // group name, press Set (or Enter), and that becomes the active group
  // (creating it if new). Switching between existing groups is done via
  // the group chips below.
  const commitGroup = () => {
    const name = (labelInput.value || "").trim() || "default";
    addKnownGroup(name);
    switchGroup(name);
  };
  container.querySelector("#wd-setgroup").addEventListener("click", commitGroup);
  labelInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commitGroup(); }
  });
  container.querySelector("#wd-sync").addEventListener("click", async () => {
    try {
      await api.fetchApi(`/wedge_diff/sync?workflow_label=${encodeURIComponent(getLabel())}`);
    } catch (e) { console.error(`${LOG} sync failed`, e); }
    refreshAll();
  });
  container.querySelector("#wd-wipe-btn").addEventListener("click", openWipe);

  // Wedge Studio: header button opens/launches it; gear toggles the
  // small settings strip; inputs persist straight to localStorage.
  container.querySelector("#wd-ws-open").addEventListener("click", openWedgeStudio);
  const wsSettings = container.querySelector("#wd-ws-settings");
  container.querySelector("#wd-ws-gear").addEventListener("click", () => {
    wsSettings.classList.toggle("wd-open");
  });
  const wsUrlInput = container.querySelector("#wd-ws-url");
  const wsFolderInput = container.querySelector("#wd-ws-folder");
  wsUrlInput.value = getWsUrl();
  wsFolderInput.value = getWsFolder();
  wsUrlInput.addEventListener("change", () => setWsUrl(wsUrlInput.value.trim()));
  wsFolderInput.addEventListener("change", () => setWsFolder(wsFolderInput.value.trim()));


  // Defensive safety net: stop wheel events over the changes list from
  // bubbling further once this element has handled the scroll itself.
  // The panel is a separate DOM region from the ComfyUI canvas, so
  // canvas-zoom shouldn't normally see these at all — this just makes
  // sure of it regardless, at zero cost.
  const diffEl = container.querySelector("#wd-diff");
  diffEl?.addEventListener(
    "wheel",
    (e) => { e.stopPropagation(); },
    { passive: true }
  );

  addKnownGroup(getLabel()); // make sure the current group is always listed
  refreshAll();
}

/* ============================ groups ============================ */
const KNOWN_KEY = "wedgeDiff.knownGroups";

function getKnownGroups() {
  let list = [];
  try { list = JSON.parse(localStorage.getItem(KNOWN_KEY) || "[]"); } catch (e) {}
  if (!Array.isArray(list)) list = [];
  if (!list.includes("default")) list.unshift("default");
  return list;
}
function addKnownGroup(name) {
  const list = getKnownGroups();
  if (!list.includes(name)) {
    list.push(name);
    try { localStorage.setItem(KNOWN_KEY, JSON.stringify(list)); } catch (e) {}
  }
}
function removeKnownGroup(name) {
  const list = getKnownGroups().filter((n) => n !== name);
  try { localStorage.setItem(KNOWN_KEY, JSON.stringify(list)); } catch (e) {}
}

async function loadGroups() {
  try {
    const res = await api.fetchApi("/wedge_diff/groups");
    state.groups = await res.json();
  } catch (err) {
    console.error(`${LOG} loadGroups failed:`, err);
    state.groups = [];
  }
  renderGroups();
}

function renderGroups() {
  const el = state.container?.querySelector("#wd-groups");
  if (!el) return;
  _armedDelete = null; // any re-render disarms a pending delete (safety)
  const counts = {};
  (state.groups || []).forEach((g) => { counts[g.label] = g.count; });
  // union of: groups with runs (backend) + locally-known names + active
  const names = new Set(getKnownGroups());
  (state.groups || []).forEach((g) => names.add(g.label));
  names.add(getLabel());
  const active = getLabel();
  // active first, then by run count desc, then alphabetical
  const ordered = [...names].sort((a, b) => {
    if (a === active) return -1;
    if (b === active) return 1;
    return (counts[b] || 0) - (counts[a] || 0) || a.localeCompare(b);
  });
  el.innerHTML = ordered.map((n) => `
    <div class="wd-grp ${n === active ? "wd-grp-active" : ""}" data-name="${esc(n)}">
      <span class="wd-grp-name">${esc(n)}</span>
      <span class="wd-grp-count">${counts[n] || 0}</span>
      <span class="wd-grp-x" data-del="${esc(n)}" title="Delete this group">×</span>
    </div>`).join("");

  el.querySelectorAll(".wd-grp").forEach((chip) => {
    chip.addEventListener("click", (e) => {
      if (e.target.classList.contains("wd-grp-x")) return; // x handled below
      switchGroup(chip.dataset.name);
    });
  });
  el.querySelectorAll(".wd-grp-x").forEach((x) => {
    x.addEventListener("click", (e) => {
      e.stopPropagation();
      handleDeleteClick(x, x.dataset.del);
    });
  });
}

function switchGroup(name) {
  if (!name) return;
  setLabel(name);
  const input = state.container?.querySelector("#wd-label");
  if (input) input.value = name;
  const ctx = state.container?.querySelector("#wd-ctx");
  if (ctx) ctx.textContent = name;
  state.aId = state.bId = null;
  refreshAll();
}

// Two-step delete: first click on × arms it ("delete?"), second confirms.
// Clicking anything else re-renders and disarms.
let _armedDelete = null;
function handleDeleteClick(xEl, name) {
  if (_armedDelete === name) {
    _armedDelete = null;
    deleteGroup(name);
  } else {
    _armedDelete = name;
    xEl.classList.add("wd-confirm");
    xEl.textContent = "delete?";
    // disarm if they click elsewhere
    setTimeout(() => {
      const off = () => { _armedDelete = null; renderGroups(); document.removeEventListener("click", off); };
      document.addEventListener("click", off, { once: true });
    }, 0);
  }
}

async function deleteGroup(name) {
  try {
    await api.fetchApi("/wedge_diff/group/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow_label: name }),
    });
  } catch (err) {
    console.error(`${LOG} deleteGroup failed:`, err);
  }
  removeKnownGroup(name);
  if (getLabel() === name) {
    switchGroup("default"); // deleted the active group -> fall back
  } else {
    refreshAll();
  }
}

function refreshAll() {
  loadGroups();
  loadHistory();
}

/* ============================ Wedge Studio integration ============================ */
const WS_URL_KEY = "wedgeDiff.wedgeStudioUrl";
const WS_FOLDER_KEY = "wedgeDiff.wedgeStudioFolder";
const WS_DEFAULT_URL = "http://localhost:8080";

function getWsUrl() {
  try { return localStorage.getItem(WS_URL_KEY) || WS_DEFAULT_URL; }
  catch (e) { return WS_DEFAULT_URL; }
}
function setWsUrl(v) {
  try { localStorage.setItem(WS_URL_KEY, v || WS_DEFAULT_URL); } catch (e) {}
}
function getWsFolder() {
  try { return localStorage.getItem(WS_FOLDER_KEY) || ""; }
  catch (e) { return ""; }
}
function setWsFolder(v) {
  try { localStorage.setItem(WS_FOLDER_KEY, v || ""); } catch (e) {}
}

// Direct browser->WedgeStudio fetch, not through our backend: Wedge
// Studio's own server already sends permissive CORS headers, so no
// proxy is needed for this simple liveness check.
async function checkWedgeStudioAlive(url) {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 2000);
    const res = await fetch(url, { method: "GET", signal: ctrl.signal });
    clearTimeout(t);
    return !!res.ok;
  } catch (e) {
    return false;
  }
}

async function launchWedgeStudio(folder) {
  try {
    const res = await api.fetchApi("/wedge_diff/wedge_studio/launch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder }),
    });
    const data = await res.json().catch(() => ({}));
    if (!data.ok) {
      console.warn(`${LOG} Wedge Studio launch failed:`, data);
      showToast(`Couldn't launch Wedge Studio: ${data.error || "unknown error"}`);
      return false;
    }
    return true;
  } catch (err) {
    console.error(`${LOG} Wedge Studio launch request failed:`, err);
    showToast("Couldn't reach the backend to launch Wedge Studio — see console");
    return false;
  }
}

// Polls the URL until it responds or maxWaitMs elapses. Used right
// after launching, since the Python process takes a moment to bind
// the port.
async function waitForWedgeStudio(url, maxWaitMs = 15000, intervalMs = 700) {
  const deadline = performance.now() + maxWaitMs;
  while (performance.now() < deadline) {
    if (await checkWedgeStudioAlive(url)) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

// Promise-based styled confirm, matching the panel's look instead of
// the browser's native dialog. Resolves true for the primary (gold)
// button, false for cancel.
function showConfirm(message, okLabel = "Restart", cancelLabel = "Cancel") {
  return new Promise((resolve) => {
    let ov = document.getElementById("wd-confirm-overlay");
    if (!ov) {
      ov = document.createElement("div");
      ov.id = "wd-confirm-overlay";
      ov.className = "wd-confirm-overlay";
      document.body.appendChild(ov);
    }
    ov.innerHTML = `
      <div class="wd-confirm-box">
        <div class="wd-confirm-msg">${esc(message)}</div>
        <div class="wd-confirm-btns">
          <button class="wd-confirm-cancel" id="wd-confirm-cancel">${esc(cancelLabel)}</button>
          <button class="wd-confirm-ok" id="wd-confirm-ok">${esc(okLabel)}</button>
        </div>
      </div>`;
    ov.classList.add("wd-open");
    const cleanup = (val) => { ov.classList.remove("wd-open"); resolve(val); };
    ov.querySelector("#wd-confirm-ok").addEventListener("click", () => cleanup(true));
    ov.querySelector("#wd-confirm-cancel").addEventListener("click", () => cleanup(false));
  });
}

// The actual button handler. Always-restart-by-default would risk
// killing an in-progress unattended batch, so: nothing running -> just
// launch, no friction. Already running -> ask, since restarting resets
// its state (run order, selections). Cancelling still opens the
// existing session rather than doing nothing.
async function openWedgeStudio() {
  const url = getWsUrl();
  const folder = getWsFolder();

  showToast("Checking Wedge Studio…");
  const alive = await checkWedgeStudioAlive(url);

  if (alive) {
    const restart = await showConfirm(
      "Wedge Studio is already running.\n\nRestarting resets its current state (run order, selections, anything in progress).",
      "Restart",
      "Just open it"
    );
    if (!restart) {
      window.open(url, "_blank");
      return;
    }
    if (!folder) {
      showToast("Set the Wedge Studio folder path (gear icon) to enable restart.");
      return;
    }
    showToast("Restarting Wedge Studio…");
    const launched = await launchWedgeStudio(folder);
    if (!launched) return;
    const backUp = await waitForWedgeStudio(url);
    if (backUp) window.open(url, "_blank");
    else showToast("Wedge Studio didn't come back up in time — check it manually.");
    return;
  }

  // not running at all
  if (!folder) {
    showToast("Wedge Studio isn't running, and no folder is set to launch it (gear icon).");
    return;
  }
  showToast("Wedge Studio not running — launching…");
  const launched = await launchWedgeStudio(folder);
  if (!launched) return;
  const up = await waitForWedgeStudio(url);
  if (up) window.open(url, "_blank");
  else showToast("Wedge Studio didn't respond in time — check the folder path and try again.");
}

/* ============================ registration ============================ */
app.registerExtension({
  name: "wedge.diff",
  async setup() {
    injectStyles();
    console.log(`${LOG} extension loaded`);

    // ---- auto-capture (Phase 2) ----
    const seen = new Set();
    const handle = (src) => (e) => {
      const pid = extractPromptId(e?.detail);
      if (!pid) { console.warn(`${LOG} ${src} had no prompt_id`, e?.detail); return; }
      if (seen.has(pid)) return;
      seen.add(pid);
      if (seen.size > 200) seen.clear();
      capture(pid);
    };
    api.addEventListener("execution_success", handle("execution_success"));
    api.addEventListener("executed", handle("executed"));

    // ---- sidebar panel (Phase 3) ----
    if (app.extensionManager && typeof app.extensionManager.registerSidebarTab === "function") {
      app.extensionManager.registerSidebarTab({
        id: "wedgeDiff",
        icon: "pi pi-clone",
        title: "Wedge Diff",
        tooltip: "Wedge Diff — compare runs",
        type: "custom",
        render: (el) => buildPanel(el),
      });
      console.log(`${LOG} sidebar tab registered`);
    } else {
      console.warn(`${LOG} no sidebar API on this ComfyUI version — using floating fallback`);
      buildFloatingFallback();
    }
  },
});

// Fallback for ComfyUI builds without the sidebar manager: a gold FAB
// bottom-right that toggles a floating panel with the same content.
function buildFloatingFallback() {
  const fab = document.createElement("button");
  fab.className = "wd-fab";
  fab.textContent = "◧";
  fab.title = "Wedge Diff";
  const panel = document.createElement("div");
  panel.className = "wd-float-panel wd-root";
  document.body.appendChild(panel);
  document.body.appendChild(fab);
  let built = false;
  fab.addEventListener("click", () => {
    panel.classList.toggle("wd-open");
    if (panel.classList.contains("wd-open") && !built) {
      buildPanel(panel);
      built = true;
    }
  });
}
