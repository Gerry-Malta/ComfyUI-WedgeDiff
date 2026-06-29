#!/usr/bin/env python3
"""
Wedge Studio — District Zero
=============================
Run this file to start the Wedge Studio server.

    python wedge_studio.py            # starts on port 8080
    python wedge_studio.py 9090       # custom port

Then the browser opens automatically at http://localhost:<port>/
Press Ctrl+C to stop the server.
"""

import sys
import os
import json
import threading
import webbrowser
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import queue as _queue
import time as _time_mod
from socketserver import ThreadingMixIn

# Force UTF-8 on stdout/stderr regardless of the system's default codepage.
# Without this, redirecting output to a file/pipe (rather than an
# interactive console) falls back to e.g. cp1252 on Windows, which can't
# encode the box-drawing characters in the startup banner below --
# crashing on the very first print() with UnicodeEncodeError. Harmless in
# every other run mode; only matters when output isn't going to a console
# that already happens to support these characters.
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_port_args = [a for a in sys.argv[1:] if not a.startswith('--')]
PORT = int(_port_args[0]) if _port_args else 8080

# ── embedded HTML (the full Wedge Studio UI) ──────────────────────────────────
HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Wedge Studio — District Zero</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">\n<style>\n* { margin: 0; padding: 0; box-sizing: border-box; }\n\n:root {\n    --bg-primary: #0a0a0a;\n    --bg-secondary: #0c0c0c;\n    --bg-tertiary: #0e0e0e;\n    --border-primary: #1e1e1e;\n    --border-secondary: #2a2a2a;\n    --text-primary: #e8e4dc;\n    --text-secondary: #888880;\n    --text-dim: #555550;\n    --accent-gold: #d18d1f;\n    --accent-gold-dim: #8a5c14;\n    --glow-gold: rgba(209, 141, 31, 0.4);\n    --node-bg: #141414;\n    --ok: #5ad17a;\n    --warn: #f0b656;\n    --err: #ff6b6b;\n    --running: #6ea8fe;\n    --ease: cubic-bezier(0.4, 0, 0.2, 1);\n}\n\nbody {\n    font-family: \'DM Mono\', \'Courier New\', monospace;\n    background: var(--bg-primary);\n    color: var(--text-primary);\n    height: 100vh;\n    overflow: hidden;\n    display: flex;\n    flex-direction: column;\n}\n\nbody::before {\n    content: \'\';\n    position: fixed;\n    inset: 0;\n    background: repeating-linear-gradient(0deg, rgba(209,141,31,0.02) 0px, transparent 1px, transparent 2px, rgba(209,141,31,0.02) 3px);\n    pointer-events: none;\n    z-index: 1000;\n}\n\n/* ---------- HEADER ---------- */\n.header {\n    border-bottom: 1px solid var(--border-primary);\n    padding: 18px 28px;\n    display: flex; align-items: center; justify-content: space-between;\n    background: var(--bg-primary); flex-shrink: 0; gap: 20px;\n}\n.logo-wrap { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }\n.logo-img {\n    height: 36px; width: auto;\n}\n.logo-div { width: 1px; height: 28px; background: var(--border-secondary); }\n.logo-sub { font-size: 13px; letter-spacing: 0.2em; color: var(--accent-gold); text-transform: uppercase; }\n.logo-module { font-size: 13px; letter-spacing: 0.15em; color: var(--text-dim); text-transform: uppercase; }\n.logo-ver { font-size: 9px; color: var(--text-dim); letter-spacing: 0.1em; }\n.header-right { display: flex; align-items: center; gap: 14px; }\n.mode-pill {\n    font-size: 9px; letter-spacing: 0.15em; text-transform: uppercase;\n    padding: 5px 10px; border-radius: 3px; border: 1px solid;\n}\n.mode-pill.planning { color: var(--text-secondary); border-color: var(--border-secondary); }\n.mode-pill.local-ok { color: var(--ok); border-color: rgba(90,209,122,.4); box-shadow: 0 0 10px rgba(90,209,122,.15); }\n.mode-pill.local-bad { color: var(--err); border-color: rgba(255,107,107,.4); }\n.cfg { display: flex; align-items: center; gap: 6px; }\n.cfg label { font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-dim); }\n.cfg input {\n    background: var(--bg-tertiary); border: 1px solid var(--border-secondary); color: var(--text-primary);\n    font-family: inherit; font-size: 11px; padding: 6px 8px; border-radius: 3px; outline: none;\n    transition: border-color .2s var(--ease);\n}\n.cfg input:focus { border-color: var(--accent-gold); }\n\n/* ---------- DROPZONE ---------- */\n.dropzone {\n    margin: 8px 12px; border: 1px dashed var(--border-secondary); border-radius: 3px;\n    padding: 14px; text-align: center; font-size: 10px; letter-spacing: 0.08em;\n    text-transform: uppercase; color: var(--text-dim); transition: all .2s var(--ease);\n    cursor: pointer;\n}\n.dropzone:hover { border-color: var(--accent-gold-dim); color: var(--text-secondary); }\n.dropzone.over { border-color: var(--accent-gold); background: rgba(209,141,31,0.06); color: var(--accent-gold); }\n\n/* ---------- LAYOUT ---------- */\n.workspace { flex: 1; display: flex; overflow: hidden; }\n.col { display: flex; flex-direction: column; overflow: hidden; border-right: 1px solid var(--border-primary); }\n.col-avail { width: 290px; flex-shrink: 0; }\n.col-order { width: 330px; flex-shrink: 0; container-type: inline-size; }\n.col-main { flex: 1; }\n/* ---------- col-order resize handle ---------- */\n#col-resize-handle {\n    width: 5px; flex-shrink: 0; cursor: ew-resize; position: relative;\n    background: var(--bg-secondary); border-right: 1px solid var(--border-primary);\n    transition: background .15s, border-color .15s; user-select: none;\n}\n#col-resize-handle::before {\n    content: \'\'; position: absolute; top: 0; bottom: 0;\n    left: -4px; right: -4px; cursor: ew-resize; z-index: 1;\n}\n#col-resize-handle:hover { background: rgba(209,141,31,0.06); border-color: var(--accent-gold-dim); }\n#col-resize-handle.active { background: rgba(209,141,31,0.12); border-color: var(--accent-gold); box-shadow: 0 0 6px var(--glow-gold); }\n.col-order { border-right: none; }\n#orderColHead .btn-sm { white-space: nowrap; overflow: hidden; }\n@container (max-width: 265px) { .btn-lbl { display: none; } }\n.col-head {\n    padding: 14px 18px; font-size: 9px; letter-spacing: 0.15em; text-transform: uppercase;\n    color: var(--text-dim); border-bottom: 1px solid var(--border-primary);\n    display: flex; align-items: center; justify-content: space-between; background: var(--bg-secondary);\n}\n.col-body { flex: 1; overflow-y: auto; padding: 12px; }\n\n/* ---------- buttons ---------- */\n.btn {\n    padding: 9px 14px; font-family: inherit; font-size: 10px; letter-spacing: 0.1em;\n    text-transform: uppercase; cursor: pointer; border: 1px solid var(--border-secondary);\n    background: var(--bg-secondary); color: var(--text-primary); border-radius: 3px;\n    transition: all .3s var(--ease); position: relative; overflow: hidden;\n}\n.btn::before {\n    content: \'\'; position: absolute; top: 0; left: -100%; width: 100%; height: 100%;\n    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent); transition: left .5s;\n}\n.btn:hover::before { left: 100%; }\n.btn:hover { border-color: var(--accent-gold); background: rgba(209,141,31,0.1); transform: translateY(-1px); box-shadow: 0 4px 20px var(--glow-gold); }\n.btn:disabled { opacity: .4; cursor: not-allowed; transform: none; box-shadow: none; }\n.btn:disabled::before { display: none; }\n.btn-primary { background: var(--accent-gold); border-color: var(--accent-gold); color: #000; font-weight: 500; }\n.btn-primary:hover { background: #e09d2f; transform: translateY(-2px); box-shadow: 0 8px 30px var(--glow-gold); }\n.btn-sm { padding: 5px 9px; font-size: 9px; }\n.btn-danger:hover { border-color: var(--err); background: rgba(255,107,107,.1); box-shadow: 0 4px 20px rgba(255,107,107,.3); }\n\n/* ---------- available list ---------- */\n.wf-item {\n    background: var(--bg-tertiary); border: 1px solid var(--border-primary); color: var(--text-primary);\n    padding: 9px 12px; margin-bottom: 5px; border-radius: 3px; font-size: 11px; cursor: pointer;\n    transition: all .2s var(--ease); user-select: none; display: flex; align-items: center; gap: 8px;\n    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;\n}\n.wf-item:hover { border-color: var(--accent-gold-dim); }\n.wf-item.selected { border-color: var(--accent-gold); background: rgba(209,141,31,0.12); }\n.wf-item.invalid { opacity: .45; border-style: dashed; }\n.wf-item .seq {\n    width: 18px; height: 18px; flex-shrink: 0; border-radius: 3px; background: var(--accent-gold); color: #000;\n    font-size: 9px; display: none; align-items: center; justify-content: center; font-weight: 500;\n}\n.wf-item.selected .seq { display: flex; }\n.sel-row { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }\n.sel-info { font-size: 9px; color: var(--text-dim); letter-spacing: 0.05em; margin-bottom: 10px; word-break: break-all; min-height: 14px; }\n\n/* ---------- run order ---------- */\n.unit {\n    background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 3px;\n    padding: 10px 12px; margin-bottom: 6px; font-size: 11px; cursor: grab;\n    transition: border-color .2s var(--ease), opacity .2s; position: relative;\n    display: flex; align-items: center; gap: 8px;\n}\n.unit:hover { border-color: var(--accent-gold-dim); }\n.unit.selected { outline: 2px solid var(--accent-gold); outline-offset: -2px; box-shadow: 0 0 12px var(--glow-gold); }\n.unit.dragging { opacity: .4; cursor: grabbing; }\n.unit.drag-over { border-top: 2px solid var(--accent-gold); }\n.unit .idx { color: var(--text-dim); font-size: 9px; flex-shrink: 0; width: 16px; }\n.unit .ico { flex-shrink: 0; }\n.unit .lbl { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }\n.unit.chain { color: var(--accent-gold); }\n.unit.running { border-color: var(--running); color: var(--running); box-shadow: 0 0 8px rgba(110,168,254,.25); }\n.unit.ok      { border-color: var(--ok); color: var(--ok); }\n.unit.fail    { border-color: var(--err); color: var(--err); }\n/* chain row gold while running — individual nodes still show blue/green/red in graph */\n.unit.chain.running { border-color: var(--accent-gold); color: var(--accent-gold); box-shadow: 0 0 8px rgba(209,141,31,.3); }\n.unit .mode-tag {\n    font-size: 8px; letter-spacing: .08em; padding: 2px 6px; border-radius: 2px; flex-shrink: 0;\n    border: 1px solid var(--border-secondary); text-transform: uppercase;\n}\n.unit .timeout-field {\n    display: flex; align-items: center; gap: 4px; flex-shrink: 0; margin-left: 2px;\n}\n.unit .timeout-field input {\n    width: 38px; background: var(--bg-tertiary); border: 1px solid var(--accent-gold-dim);\n    color: var(--accent-gold); font-family: inherit; font-size: 9px; padding: 2px 4px;\n    border-radius: 2px; outline: none; text-align: center;\n}\n.unit .timeout-field label { font-size: 8px; color: var(--accent-gold-dim); letter-spacing: .05em; }\n.unit .mode-tag.success { color: var(--ok); border-color: rgba(90,209,122,.4); }\n.unit .mode-tag.failure { color: var(--warn); border-color: rgba(240,182,86,.4); }\n\n/* ---------- graph ---------- */\n.graph-wrap { padding: 12px 18px; border-bottom: 1px solid var(--border-primary); max-height: 200px; overflow-y: auto; }\n.graph-title { font-size: 9px; letter-spacing: .15em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 10px; }\n.chain-row { display: flex; align-items: center; gap: 0; margin-bottom: 12px; flex-wrap: wrap; cursor: pointer; }\n.chain-mode {\n    font-size: 8px; letter-spacing: .08em; text-transform: uppercase; margin-right: 10px;\n    padding: 3px 7px; border-radius: 2px; border: 1px solid var(--border-secondary); flex-shrink: 0;\n}\n.chain-mode.success { color: var(--ok); border-color: rgba(90,209,122,.4); }\n.chain-mode.failure { color: var(--warn); border-color: rgba(240,182,86,.4); }\n.gnode {\n    background: var(--node-bg); border: 1px solid var(--border-secondary); border-radius: 3px;\n    padding: 7px 12px; font-size: 10px; color: var(--text-primary); transition: all .3s var(--ease);\n    max-width: 150px; display: flex; flex-direction: column; gap: 3px; align-items: flex-start;\n}\n.gnode-lbl { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 126px; }\n.vram-cb {\n    display: flex; align-items: center; gap: 3px; flex-shrink: 0;\n    font-size: 8px; letter-spacing: .05em; text-transform: uppercase;\n    color: var(--text-dim); cursor: pointer; user-select: none; line-height: 1;\n}\n.vram-cb input[type=checkbox] { accent-color: var(--accent-gold); width: 10px; height: 10px; cursor: pointer; margin: 0; }\n.vram-cb.on { color: var(--accent-gold); }\n.restart-cb.on { color: var(--err) !important; }\n.restart-cb.on input[type=checkbox] { accent-color: var(--err); }\n/* VRAM cb in run-order row */\n.unit .vram-cb { margin-left: 6px; font-size: 9px; }\n.unit .vram-cb input[type=checkbox] { width: 11px; height: 11px; }\n.gnode.running { border-color: var(--running); color: var(--running); box-shadow: 0 0 10px rgba(110,168,254,.4); }\n.gnode.ok { border-color: var(--ok); color: var(--ok); box-shadow: 0 0 10px rgba(90,209,122,.3); }\n.gnode.fail { border-color: var(--err); color: var(--err); }\n.gnode.reused { border-style: dashed; opacity: .7; }\n.garrow { color: var(--text-dim); padding: 0 8px; font-size: 12px; }\n\n/* ---------- progress ---------- */\n.pbars { padding: 10px 18px; border-top: 1px solid var(--border-primary); background: var(--bg-secondary); flex-shrink: 0; }\n.pbar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }\n.pbar-row:last-child { margin-bottom: 0; }\n.pbar-lbl { font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--text-dim); width: 46px; }\n.pbar-track { flex: 1; height: 6px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden; border: 1px solid var(--border-primary); }\n.pbar-fill { height: 100%; width: 0%; transition: width .25s var(--ease); border-radius: 3px; }\n.pbar-fill.job { background: var(--ok); box-shadow: 0 0 8px rgba(90,209,122,.5); }\n.pbar-fill.batch { background: var(--accent-gold); box-shadow: 0 0 8px var(--glow-gold); }\n.pbar-pct { font-size: 9px; color: var(--text-secondary); width: 64px; text-align: right; }\n\n/* ---------- log ---------- */\n.log-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 120px; }\n.log {\n    flex: 1; overflow-y: auto; padding: 12px 18px; font-size: 11px; line-height: 1.7;\n    background: var(--bg-secondary); white-space: pre-wrap; word-break: break-word;\n}\n.log .ts { color: var(--text-dim); }\n.log .info { color: var(--text-primary); }\n.log .muted { color: var(--text-secondary); }\n.log .ok { color: var(--ok); }\n.log .warn { color: var(--warn); }\n.log .err { color: var(--err); }\n.log .running { color: var(--running); }\n.log .header-line { color: var(--accent-gold); }\n.log .fallback { color: #f59edb; }\n\n/* ---------- results ---------- */\n.results { border-top: 1px solid var(--border-primary); padding: 12px 18px; max-height: 220px; overflow-y: auto; background: var(--bg-secondary); flex-shrink: 0; }\n.results-grid { display: flex; gap: 12px; flex-wrap: wrap; }\n.result-card {\n    background: var(--node-bg); border: 1px solid var(--border-primary); border-radius: 4px;\n    overflow: hidden; width: 180px; transition: all .2s var(--ease); position: relative;\n}\n.result-card:hover { border-color: var(--accent-gold-dim); }\n.result-thumb {\n    width: 100%; height: 101px; background: #000; cursor: pointer; position: relative;\n    display: flex; align-items: center; justify-content: center; overflow: hidden;\n}\n.result-thumb img, .result-thumb video { width: 100%; height: 100%; object-fit: cover; display: block; }\n.result-thumb .play {\n    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;\n    color: #fff; font-size: 28px; background: rgba(0,0,0,.25); transition: opacity .2s;\n    text-shadow: 0 0 12px rgba(0,0,0,.8);\n}\n.result-thumb:hover .play { opacity: .7; }\n.result-thumb .no-prev { color: var(--text-dim); font-size: 9px; letter-spacing: .1em; text-transform: uppercase; }\n.result-meta { padding: 8px 10px; }\n.result-name { font-size: 10px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }\n.result-status { font-size: 9px; margin-top: 3px; letter-spacing: .05em; }\n.result-status.ok { color: var(--ok); }\n.result-status.check { color: var(--warn); }\n.result-status.fail, .result-status.err { color: var(--err); }\n\n::-webkit-scrollbar { width: 8px; height: 8px; }\n::-webkit-scrollbar-track { background: var(--bg-primary); }\n::-webkit-scrollbar-thumb { background: var(--border-secondary); border-radius: 4px; }\n::-webkit-scrollbar-thumb:hover { background: var(--accent-gold-dim); }\n\n.section-label { font-size: 9px; letter-spacing: .15em; text-transform: uppercase; color: var(--text-dim); padding: 10px 18px 6px; }\n.empty-hint { color: var(--text-dim); font-size: 10px; line-height: 1.8; padding: 8px 4px; }\n\n/* ---------- planning banner ---------- */\n.planning-banner {\n    background: linear-gradient(90deg, rgba(209,141,31,0.08), rgba(209,141,31,0.02));\n    border-bottom: 1px solid rgba(209,141,31,0.25);\n    padding: 10px 28px;\n    font-size: 10px; color: var(--text-secondary); letter-spacing: 0.05em;\n    display: flex; align-items: center; justify-content: space-between; gap: 16px;\n}\n.planning-banner.hidden { display: none; }\n.planning-banner strong { color: var(--accent-gold); letter-spacing: 0.1em; text-transform: uppercase; font-weight: 500; }\n\n/* tooltip-ish info row */\n.info-line {\n    font-size: 9px; color: var(--text-dim); letter-spacing: 0.05em; padding: 6px 12px;\n}\n\n/* ---------- result card compare checkbox ---------- */\n.result-card { position: relative; }\n.result-card .compare-cb {\n    position: absolute; top: 6px; left: 6px; z-index: 100;\n    width: 22px; height: 22px; border-radius: 3px;\n    border: 1px solid var(--border-secondary); background: rgba(10,10,10,.85);\n    display: none; align-items: center; justify-content: center;\n    cursor: pointer; transition: all .2s var(--ease); font-size: 11px;\n    pointer-events: all; user-select: none;\n}\n.result-card:hover .compare-cb { display: flex; }\n.result-card.in-compare .compare-cb { display: flex; border-color: var(--accent-gold); background: var(--accent-gold); color: #000; }\n.result-card.in-compare { border-color: var(--accent-gold); box-shadow: 0 0 12px var(--glow-gold); }\n.compare-bar {\n    display: none; align-items: center; gap: 10px;\n    padding: 8px 18px; background: var(--bg-secondary);\n    border-top: 1px solid var(--border-primary); flex-shrink: 0;\n    font-size: 10px; color: var(--text-secondary); letter-spacing: .08em;\n}\n.compare-bar.visible { display: flex; }\n.compare-bar strong { color: var(--accent-gold); }\n\n/* ---------- lightbox ---------- */\n.lightbox {\n    position: fixed; inset: 0; z-index: 9000;\n    background: rgba(0,0,0,.92); display: none;\n    flex-direction: column; align-items: center; justify-content: center;\n}\n.lightbox.open { display: flex; }\n.lb-close {\n    position: absolute; top: 18px; right: 22px;\n    font-size: 22px; color: var(--text-dim); cursor: pointer;\n    transition: color .2s; z-index: 9100; background: none; border: none;\n    font-family: inherit;\n}\n.lb-close:hover { color: var(--text-primary); }\n.lb-nav {\n    position: absolute; top: 50%; transform: translateY(-50%);\n    font-size: 28px; color: var(--text-dim); cursor: pointer;\n    background: none; border: none; font-family: inherit;\n    transition: color .2s; z-index: 9100; padding: 0 18px;\n}\n.lb-nav:hover { color: var(--accent-gold); }\n.lb-prev { left: 0; }\n.lb-next { right: 0; }\n.lb-content {\n    max-width: calc(100vw - 120px); max-height: calc(100vh - 120px);\n    display: flex; align-items: center; justify-content: center;\n}\n.lb-content video, .lb-content img {\n    max-width: 100%; max-height: calc(100vh - 120px);\n    border-radius: 3px; display: block;\n}\n.lb-meta {\n    position: absolute; bottom: 18px; left: 50%; transform: translateX(-50%);\n    font-size: 10px; letter-spacing: .1em; color: var(--text-secondary);\n    background: rgba(0,0,0,.6); padding: 6px 14px; border-radius: 3px;\n    white-space: nowrap; text-align: center;\n}\n.lb-counter {\n    position: absolute; top: 18px; left: 50%; transform: translateX(-50%);\n    font-size: 9px; letter-spacing: .15em; text-transform: uppercase;\n    color: var(--text-dim);\n}\n\n/* ---------- compare / wipe lightbox ---------- */\n.wipe-lb {\n    position: fixed; inset: 0; z-index: 9000;\n    background: rgba(0,0,0,.95); display: none;\n    flex-direction: column; align-items: center; justify-content: center;\n}\n.wipe-lb.open { display: flex; }\n.wipe-wrap {\n    position: relative; overflow: hidden;\n    max-width: calc(100vw - 80px); max-height: calc(100vh - 140px);\n    border-radius: 3px; user-select: none;\n    display: flex; align-items: center; justify-content: center;\n}\n.wipe-a, .wipe-b {\n    position: absolute; inset: 0;\n    display: flex; align-items: center; justify-content: center;\n    overflow: hidden;\n}\n.wipe-a video, .wipe-a img,\n.wipe-b video, .wipe-b img {\n    width: 100%; height: 100%; object-fit: contain; display: block;\n}\n.wipe-a { clip-path: inset(0 50% 0 0); }  /* left half */\n.wipe-b { }                                 /* full, behind */\n.wipe-handle {\n    position: absolute; top: 0; bottom: 0; width: 3px;\n    background: var(--accent-gold); left: 50%;\n    transform: translateX(-50%); cursor: ew-resize; z-index: 10;\n    box-shadow: 0 0 10px var(--glow-gold);\n}\n.wipe-handle::after {\n    content: \'◀ ▶\'; position: absolute; top: 50%; left: 50%;\n    transform: translate(-50%,-50%);\n    background: var(--accent-gold); color: #000;\n    font-size: 10px; padding: 5px 8px; border-radius: 3px;\n    white-space: nowrap; letter-spacing: .05em;\n}\n.wipe-labels {\n    position: absolute; bottom: 0; left: 0; right: 0;\n    display: flex; justify-content: space-between; padding: 8px 12px;\n    pointer-events: none;\n}\n.wipe-lbl {\n    font-size: 9px; letter-spacing: .1em; text-transform: uppercase;\n    background: rgba(0,0,0,.7); padding: 4px 8px; border-radius: 3px;\n    max-width: 45%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;\n}\n.wipe-lbl.a { color: var(--running); }\n.wipe-lbl.b { color: var(--warn); }\n.wipe-controls {\n    display: flex; gap: 14px; align-items: center; margin-top: 14px;\n    font-size: 10px; letter-spacing: .08em; color: var(--text-secondary);\n    flex-direction: column; width: calc(100vw - 80px);\n}\n.wipe-controls-row { display: flex; gap: 14px; align-items: center; width: 100%; }\n.wipe-scrubber {\n    width: 100%; margin-top: 6px; display: flex; align-items: center; gap: 12px;\n}\n.scrub-track {\n    flex: 1; height: 28px; background: var(--bg3, #0e0e0e);\n    border: 1px solid var(--border-secondary, #2a2a2a); border-radius: 3px;\n    position: relative; cursor: ew-resize; overflow: hidden;\n}\n.scrub-fill {\n    position: absolute; top: 0; left: 0; height: 100%; width: 0%;\n    background: rgba(209,141,31,0.25); pointer-events: none; transition: none;\n}\n.scrub-needle {\n    position: absolute; top: 0; bottom: 0; width: 2px;\n    background: var(--accent-gold, #d18d1f);\n    box-shadow: 0 0 6px var(--glow-gold, rgba(209,141,31,0.4));\n    pointer-events: none; transform: translateX(-50%);\n}\n.scrub-label {\n    font-size: 9px; letter-spacing: .12em; color: var(--accent-gold, #d18d1f);\n    min-width: 80px; text-align: right; text-transform: uppercase;\n}\n.folder-browser {\n    position: fixed; inset: 0; z-index: 8000; background: rgba(0,0,0,.85);\n    display: none; align-items: center; justify-content: center;\n}\n.folder-browser.open { display: flex; }\n.fb-panel {\n    background: var(--bg-secondary); border: 1px solid var(--border-secondary);\n    border-radius: 4px; width: 560px; max-height: 70vh; display: flex; flex-direction: column;\n    box-shadow: 0 20px 60px rgba(0,0,0,.6);\n}\n.fb-head {\n    padding: 14px 18px; border-bottom: 1px solid var(--border-primary);\n    display: flex; align-items: center; gap: 10px;\n    font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--text-dim);\n}\n.fb-head .fb-title { flex: 1; color: var(--text-secondary); }\n.fb-breadcrumb {\n    padding: 10px 18px; border-bottom: 1px solid var(--border-primary);\n    font-size: 10px; color: var(--text-dim); white-space: nowrap; overflow: hidden;\n    text-overflow: ellipsis; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;\n}\n.fb-crumb { cursor: pointer; color: var(--text-secondary); transition: color .2s; }\n.fb-crumb:hover { color: var(--accent-gold); }\n.fb-crumb.current { color: var(--text-primary); cursor: default; }\n.fb-sep { color: var(--text-dim); }\n.fb-list { flex: 1; overflow-y: auto; padding: 8px 0; }\n.fb-item {\n    padding: 9px 18px; font-size: 11px; cursor: pointer; display: flex;\n    align-items: center; gap: 10px; transition: background .15s;\n    color: var(--text-secondary);\n}\n.fb-item:hover { background: rgba(209,141,31,.08); color: var(--text-primary); }\n.fb-item .fb-ico { font-size: 13px; flex-shrink: 0; }\n.fb-foot {\n    padding: 12px 18px; border-top: 1px solid var(--border-primary);\n    display: flex; align-items: center; gap: 10px;\n    font-size: 10px;\n}\n.fb-current-path {\n    flex: 1; color: var(--text-secondary); white-space: nowrap; overflow: hidden;\n    text-overflow: ellipsis;\n}\n.fb-json-count { color: var(--accent-gold); font-size: 9px; letter-spacing: .08em; flex-shrink: 0; }\n.scrub-cfg {\n    display: flex; align-items: center; gap: 10px; margin-top: 6px;\n    font-size: 9px; letter-spacing: .1em; color: var(--text-secondary, #888880);\n}\n.scrub-cfg label { text-transform: uppercase; }\n.scrub-cfg input {\n    width: 46px; background: var(--bg3, #0e0e0e);\n    border: 1px solid var(--border-secondary, #2a2a2a); color: var(--fg, #e8e4dc);\n    font-family: inherit; font-size: 10px; padding: 4px 6px; border-radius: 3px;\n    outline: none; text-align: center;\n}\n.scrub-cfg input:focus { border-color: var(--accent-gold, #d18d1f); }\n.speed-btns { display: flex; gap: 4px; }\n.speed-btn {\n    padding: 3px 8px; font-family: inherit; font-size: 9px;\n    letter-spacing: .08em; text-transform: uppercase; cursor: pointer;\n    border: 1px solid var(--border-secondary, #2a2a2a);\n    background: var(--bg2, #0c0c0c); color: var(--text-secondary, #888880);\n    border-radius: 3px; transition: all .2s;\n}\n.speed-btn:hover { border-color: var(--accent-gold, #d18d1f); color: var(--fg, #e8e4dc); }\n.speed-btn.active { border-color: var(--accent-gold, #d18d1f); color: var(--accent-gold, #d18d1f); background: rgba(209,141,31,0.12); }\n.wipe-controls button { }\n\n\n/* ── bottom log terminal ── */\n#terminal {\n    position: fixed; bottom: 0; left: 0; right: 0; z-index: 500;\n    resize: vertical; overflow: hidden;\n}\n#terminal.collapsed {\n    height: 32px !important; resize: none; transition: height 0.25s var(--ease);\n}\n#terminal.open {\n    min-height: 100px; max-height: 80vh;\n}\n#terminal.resizing { transition: none !important; }\n\n#terminal-bar {\n    height: 32px; background: var(--bg-secondary);\n    border-top: 1px solid var(--border-primary);\n    display: flex; align-items: center; justify-content: space-between;\n    padding: 0 18px; cursor: pointer; user-select: none; position: relative;\n}\n#terminal-bar::before {\n    content: \'\'; position: absolute; top: -4px; left: 0; right: 0;\n    height: 8px; cursor: ns-resize; z-index: 10;\n}\n#terminal.open #terminal-bar:hover::before {\n    background: rgba(209,141,31,0.08);\n}\n#terminal.open #terminal-bar::after {\n    content: \'⋮⋮⋮\'; position: absolute; top: 50%; left: 50%;\n    transform: translate(-50%,-50%); font-size: 8px;\n    color: var(--text-dim); letter-spacing: 2px; pointer-events: none;\n}\n#terminal-bar-left { display: flex; align-items: center; gap: 10px; }\n#terminal-label {\n    font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase;\n    color: var(--text-dim);\n}\n#terminal-dot {\n    width: 6px; height: 6px; border-radius: 50%;\n    background: var(--text-dim); opacity: 0; transition: opacity 0.3s;\n}\n#terminal-dot.active { opacity: 1; }\n@keyframes termBlink { 0%,100%{opacity:1} 50%{opacity:0.2} }\n#terminal-dot.blink { animation: termBlink 0.8s ease infinite; }\n#terminal-actions { display: flex; gap: 8px; }\n#terminal-body {\n    height: calc(100% - 32px); background: var(--bg-secondary);\n    border-top: 1px solid var(--border-primary);\n    overflow-y: auto; padding: 8px 18px;\n    font-size: 11px; font-family: inherit; display: none; line-height: 1.7;\n}\n#terminal.open #terminal-body { display: block; }\n.tlog-line { white-space: pre-wrap; word-break: break-word; }\n.tlog-time { color: var(--text-dim); margin-right: 8px; }\n.tlog-info    { color: var(--text-primary); }\n.tlog-muted   { color: var(--text-secondary); }\n.tlog-ok      { color: var(--ok); }\n.tlog-warn    { color: var(--warn); }\n.tlog-err     { color: var(--err); }\n.tlog-running { color: var(--running); }\n.tlog-header-line { color: var(--accent-gold); }\n.tlog-fallback { color: #f59edb; }\n\n/* push workspace up so terminal bar doesn\'t overlap content */\nbody { padding-bottom: 32px; }\n\n\n.pp-sheet-wrap{position:fixed;inset:0;z-index:9000;display:flex;align-items:flex-end;pointer-events:none;}\n.pp-sheet-wrap.open{pointer-events:auto;}\n.pp-overlay{position:absolute;inset:0;background:rgba(0,0,0,.55);opacity:0;transition:opacity .25s;}\n.pp-sheet-wrap.open .pp-overlay{opacity:1;}\n.pp-sheet{position:relative;width:100%;max-height:80vh;background:var(--bg-secondary);border-top:1px solid var(--border-primary);display:flex;flex-direction:column;transform:translateY(100%);transition:transform .25s;}\n.pp-sheet-wrap.open .pp-sheet{transform:translateY(0);}\n.pp-head{display:flex;align-items:center;padding:14px 18px;border-bottom:1px solid var(--border-primary);gap:10px;}\n.pp-wf-title{flex:1;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-primary);}\n.pp-scroll{flex:1;overflow-y:auto;padding:12px 18px;}\n.pp-search{width:100%;box-sizing:border-box;background:var(--bg-tertiary);border:1px solid var(--border-secondary);color:var(--text-primary);font-family:inherit;font-size:11px;padding:7px 10px;border-radius:3px;outline:none;margin-bottom:10px;}\n.pp-search:focus{border-color:var(--accent-gold);}\n.pp-grp-lbl{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-dim);margin:10px 0 4px;}\n.pp-param{display:flex;align-items:center;gap:8px;padding:5px 0;cursor:pointer;}\n.pp-pname{flex:1;font-size:11px;color:var(--text-secondary);}\n.pp-pval{font-size:10px;color:var(--text-dim);max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}\n.pp-pty{font-size:9px;color:var(--accent-gold);letter-spacing:.05em;width:28px;text-align:right;}\n.pp-var-hdr{display:flex;align-items:center;justify-content:space-between;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-dim);margin:14px 0 6px;border-top:1px solid var(--border-primary);padding-top:10px;}\n.pp-var-card{background:var(--bg-tertiary);border:1px solid var(--border-secondary);border-radius:3px;padding:8px 10px;margin-bottom:8px;}\n.pp-var-lbl-row{display:flex;align-items:center;gap:6px;margin-bottom:6px;}\n.pp-var-lbl-inp{flex:1;background:var(--bg-secondary);border:1px solid var(--border-secondary);color:var(--text-primary);font-family:inherit;font-size:10px;padding:4px 7px;border-radius:3px;outline:none;}\n.pp-var-lbl-inp:focus{border-color:var(--accent-gold);}\n.pp-var-del{background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:13px;padding:0 4px;}\n.pp-var-del:hover{color:var(--err);}\n.pp-param-row{display:flex;align-items:center;gap:8px;margin-bottom:4px;}\n.pp-param-key{font-size:9px;color:var(--text-dim);width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}\n.pp-param-inp{flex:1;background:var(--bg-secondary);border:1px solid var(--border-secondary);color:var(--text-primary);font-family:inherit;font-size:11px;padding:3px 7px;border-radius:3px;outline:none;}\n.pp-param-inp:focus{border-color:var(--accent-gold);}\n.pp-no-promo{font-size:10px;color:var(--text-dim);padding:8px 0;}\n.pp-foot{display:flex;gap:8px;padding:12px 18px;border-top:1px solid var(--border-primary);}\n.pp-add-all{background:var(--accent-gold);color:#000;border-color:var(--accent-gold);}\n.unit-gear{background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:13px;padding:0 4px;flex-shrink:0;}\n.unit-gear:hover{color:var(--accent-gold);}\n.unit-gear.cfg{color:var(--accent-gold);}\n.chain-gears{display:flex;gap:3px;align-items:center;flex-shrink:0;margin-left:2px;}\n</style>\n</head>\n<body>\n\n<div class="header">\n    <div class="logo-wrap">\n        <a href="https://comfy.org/" target="_blank" rel="noopener" style="display:flex;align-items:center;line-height:0;"><img class="logo-img" src="https://raw.githubusercontent.com/Gerry-Malta/AI_LAB/main/_img/comfyui_logo_1.png" alt="ComfyUI" style="border-radius:4px;" onerror="this.style.display=\\\'none\\\'"></a><span style="font-size:13px;color:var(--text-dim);line-height:1;flex-shrink:0;">+</span><a href="https://thedistrictzero.com/" target="_blank" rel="noopener" style="display:flex;align-items:center;line-height:0;"><img class="logo-img" src="https://cdn.jsdelivr.net/gh/Gerry-Malta/AI_LAB@main/_img/DZ_logo_5.png" alt="District Zero" onerror="this.style.display=\\\'none\\\'"></a>\n        <div class="logo-div"></div>\n        <span class="logo-sub">AI Lab</span>\n        <div class="logo-div"></div>\n        <span class="logo-module">Wedge Studio</span>\n        <div class="logo-div"></div>\n        <span class="logo-ver" id="logoVer">v0.2.0</span>\n    </div>\n    <div class="header-right">\n        <div class="cfg">\n            <label>Server</label>\n            <input id="server" value="127.0.0.1:8188" size="14">\n        </div>\n        <div class="cfg">\n            <label>Timeout(min)</label>\n            <input id="timeout" value="20" size="3">\n        </div>\n        <div class="cfg" id="comfyPathCfg" style="display:none;">\n            <label>ComfyUI folder</label>\n            <input id="comfyPath" placeholder="D:\\ComfyUI" size="20" title="Path to your ComfyUI folder (for auto-restart)">\n            <button class="btn btn-sm" onclick="saveComfyPath()" title="Save path">✓</button>\n        </div>\n        <span class="mode-pill planning" id="modePill">Checking…</span>\n    </div>\n</div>\n\n</div>\n\n<div class="workspace">\n    <!-- AVAILABLE -->\n    <div class="col col-avail">\n        <div class="col-head"><span>Workflows · click in order to chain</span></div>\n        <div id="serverFolderRow" style="display:none;padding:0 12px 8px;">\n            <div style="font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-dim);margin-bottom:6px;">Workflow folder path</div>\n            <div style="display:flex;gap:6px;">\n                <input id="folderPathInput" placeholder="D:\\your\\workflow\\folder" style="flex:1;background:var(--bg-tertiary);border:1px solid var(--border-secondary);color:var(--text-primary);font-family:inherit;font-size:11px;padding:6px 8px;border-radius:3px;outline:none;">\n                <button class="btn btn-sm" onclick="openFolderBrowser()" title="Browse folders">&#128193;</button>\n                <button class="btn btn-sm" onclick="loadFromServer()">&#x21ba; Reload</button>\n            </div>\n        </div>\n\n        <!-- folder browser modal -->\n        <div class="folder-browser" id="folderBrowser">\n            <div class="fb-panel">\n                <div class="fb-head">\n                    <span class="fb-title">Select Workflow Folder</span>\n                    <button class="btn btn-sm" onclick="closeFolderBrowser()">✕</button>\n                </div>\n                <div class="fb-breadcrumb" id="fbBreadcrumb"></div>\n                <div class="fb-list" id="fbList"></div>\n                <div class="fb-foot">\n                    <span class="fb-current-path" id="fbCurrentPath"></span>\n                    <span class="fb-json-count" id="fbJsonCount"></span>\n                    <button class="btn btn-sm btn-primary" id="fbSelectBtn" onclick="selectFolderFromBrowser()">Select this folder</button>\n                    <button class="btn btn-sm" onclick="closeFolderBrowser()">Cancel</button>\n                </div>\n            </div>\n        </div>\n        <div class="dropzone" id="dropzone" onclick="document.getElementById(\'fileInput\').click()">\n            Drag &amp; drop a folder<br>or click to choose .json files\n        </div>\n        <div class="col-body">\n            <div class="sel-info" id="selInfo">selected: (none)</div>\n            <div class="sel-row">\n                <button class="btn btn-sm" onclick="addSingles()">Add Singles</button>\n                <button class="btn btn-sm" onclick="clearSel()">Clear Sel</button>\n            </div>\n            <div id="availList"></div>\n            <input type="file" id="fileInput" accept=".json" multiple webkitdirectory directory style="display:none">\n        </div>\n    </div>\n\n    <!-- RUN ORDER -->\n    <div class="col col-order">\n        <div class="col-head" id="orderColHead">\n            <span id="orderColTitle">Run Order · drag to reorder</span>\n            <div style="display:flex;gap:6px;align-items:center;">\n                <button class="btn btn-sm" id="makeChainBtn" onclick="makeChain()" title="Enter chain-build mode">⛓ <span class="btn-lbl">Chain</span></button>\n                <button class="btn btn-sm btn-danger" id="removeSelBtn" onclick="removeSelectedUnit()" title="Remove selected row">✕ <span class="btn-lbl">Remove</span></button>\n                <button class="btn btn-sm" onclick="saveOrderConfig()" title="Save run order to config">✓</button>\n            </div>\n        </div>\n        <div id="chainBuildBanner" style="display:none;padding:8px 12px;background:rgba(209,141,31,0.08);border-bottom:1px solid rgba(209,141,31,0.3);font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent-gold);align-items:center;gap:8px;">\n            <span style="flex:1;" id="chainBuildHint">Click items in order · select ≥2</span>\n            <button class="btn btn-sm btn-primary" id="confirmChainBtn" onclick="confirmChain()" disabled>✓ Confirm</button>\n            <button class="btn btn-sm" onclick="cancelChainBuild()">✕</button>\n        </div>\n        <div class="col-body" id="orderList"></div>\n    </div><div id="col-resize-handle"></div>\n\n    <!-- MAIN -->\n    <div class="col col-main">\n        <div class="graph-wrap">\n            <div class="graph-title" id="graphTitle">Chain Graph · click a chain to flip its mode</div>\n            <div id="graph"></div>\n        </div>\n        <div class="log-wrap" style="display:none;">\n            <div class="log" id="log"></div>\n        </div>\n        <div class="compare-bar" id="compareBar">\n    <strong id="compareCount">0 selected</strong>\n    &nbsp;·&nbsp; click thumbnails to select for compare (max 2)\n    <button class="btn btn-sm" id="compareBtn" onclick="openWipe()" style="margin-left:auto;" disabled>⇌ Compare</button>\n    <button class="btn btn-sm" onclick="clearCompare()">Clear</button>\n    <button class="btn btn-sm" id="exportReportBtn" onclick="exportReport()">↓ Export Report</button>\n    <label class="vram-cb" id="autoReportLabel" title="Auto-save report after each workflow and at batch end" style="margin-left:4px;gap:5px;">\n        <input type="checkbox" id="autoReportChk" checked onchange="_autoReportEnabled=this.checked;document.getElementById(\'autoReportLabel\').classList.toggle(\'on\',this.checked);">\n        <span>Auto</span>\n    </label>\n</div>\n\n<!-- standard lightbox -->\n<div class="lightbox" id="lightbox">\n    <button class="lb-close" onclick="lbClose()">✕</button>\n    <button class="lb-nav lb-prev" onclick="lbNav(-1)">&#8592;</button>\n    <button class="lb-nav lb-next" onclick="lbNav(1)">&#8594;</button>\n    <div class="lb-counter" id="lbCounter"></div>\n    <div class="lb-content" id="lbContent"></div>\n    <div class="lb-meta" id="lbMeta"></div>\n</div>\n\n<!-- wipe compare lightbox -->\n<div class="wipe-lb" id="wipeLb">\n    <button class="lb-close" onclick="wipeClose()">✕</button>\n    <div class="wipe-wrap" id="wipeWrap">\n        <div class="wipe-b" id="wipeB"></div>\n        <div class="wipe-a" id="wipeA"></div>\n        <div class="wipe-handle" id="wipeHandle"></div>\n        <div class="wipe-labels">\n            <span class="wipe-lbl a" id="wipeLblA"></span>\n            <span class="wipe-lbl b" id="wipeLblB"></span>\n        </div>\n    </div>\n    <div class="wipe-controls">\n        <div class="wipe-controls-row">\n            <button class="btn btn-sm" id="wipePlayBtn" onclick="wipeTogglePlay()">▶ Play</button>\n        </div>\n        <div class="wipe-scrubber" id="wipeScrubber">\n            <div class="scrub-track" id="scrubTrack">\n                <div class="scrub-fill" id="scrubFill"></div>\n                <div class="scrub-needle" id="scrubNeedle"></div>\n            </div>\n            <span class="scrub-label" id="scrubLabel">frame —</span>\n        </div>\n        <div class="scrub-cfg">\n            <label>fps</label>\n            <input id="scrubFps" type="number" value="30" min="1" max="120"\n                oninput="wipeDetectedFps=parseInt(this.value)||30; scrubFromVideo();"\n                title="Set fps to correct the frame number display">\n            <label>speed</label>\n            <div class="speed-btns">\n                <button class="speed-btn" onclick="setWipeSpeed(0.1)" title="10% speed">×0.1</button>\n                <button class="speed-btn" onclick="setWipeSpeed(0.25)" title="25% speed">×0.25</button>\n                <button class="speed-btn" onclick="setWipeSpeed(0.5)" title="50% speed">×0.5</button>\n                <button class="speed-btn active" id="speedBtn1" onclick="setWipeSpeed(1)" title="Normal speed">×1</button>\n            </div>\n        </div>\n    </div>\n</div>\n\n<div class="results">\n            <div class="section-label" style="padding:0 0 8px">Results · click to play · hover for compare select · ← → keys navigate</div>\n            <div class="results-grid" id="results"></div>\n        </div>\n        <div class="pbars">\n            <div class="pbar-row">\n                <span class="pbar-lbl">Job</span>\n                <div class="pbar-track"><div class="pbar-fill job" id="jobFill"></div></div>\n                <span class="pbar-pct" id="jobPct"></span>\n            </div>\n            <div class="pbar-row">\n                <span class="pbar-lbl">Batch</span>\n                <div class="pbar-track"><div class="pbar-fill batch" id="batchFill"></div></div>\n                <span class="pbar-pct" id="batchPct"></span>\n            </div>\n            <div class="pbar-row" style="margin-top:10px; justify-content:flex-end; gap:8px;">\n                <span id="progressText" style="flex:1; font-size:9px; color:var(--text-dim); letter-spacing:.1em;"></span>\n                <button class="btn btn-sm" id="runBtn" onclick="startRun()" disabled>▶ Run</button>\n                <button class="btn btn-sm" id="stopBtn" onclick="stopRun()" disabled>■ Stop</button>\n            </div>\n        </div>\n    </div>\n</div>\n\n<script>\n// ============ baked-in plan (filled on download from web) ============\nconst BAKED_PLAN = null; // when not null: {order:[...], server, timeout}\n\n// ============ state ============\nconst OUTPUT_NODE_TYPES = {\n    "SaveVideo": "filename_prefix",\n    "VHS_VideoCombine": "filename_prefix",\n    "SaveImage": "filename_prefix",\n    "SaveAudio": "filename_prefix",\n};\nlet workflows = {};      // name -> {wf, validApi}    (wf may be null when loaded from plan only)\nlet order = [];          // run units\nlet chainSel = [];\nlet chainBuildMode = false;\nlet orderChainSel = [];\nlet _pCfg = {}, _ppWf = null;\nlet _ppChainUnit = null, _ppChainNodeIdx = -1;\nlet selUnit = null;\nlet clientId = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random());\nlet running = false;\nlet stopFlag = false;\nlet dragIdx = null;\nlet comfyOnline = false;\nlet _pendingSavedOrder = null;  // order restored from _wedge_config.json at startup\nlet folderName = \'wedge\';\nlet serverFolder = null;   // set when served from wedge_studio.py\nconst WEDGE_SERVER = (location.protocol !== \'file:\') ? location.origin : null;\n// when running from wedge_studio.py, proxy ComfyUI calls through our server\n// so browser never needs to make cross-origin requests to port 8188\nconst comfyBase = () => WEDGE_SERVER ? WEDGE_SERVER + \'/comfy_proxy\' : base();\n\nconst server = () => document.getElementById(\'server\').value.trim() || \'127.0.0.1:8188\';\nconst base = () => \'http://\' + server();\n\n// ============ helpers ============\nfunction isApiFormat(wf){\n    if (!wf || typeof wf !== \'object\') return false;\n    if (Array.isArray(wf.nodes)) return false;\n    return Object.values(wf).some(v => v && typeof v === \'object\' && \'class_type\' in v);\n}\nfunction rewritePrefix(wf, prefix){\n    let n = 0;\n    for (const node of Object.values(wf)){\n        if (!node || typeof node !== \'object\') continue;\n        const key = OUTPUT_NODE_TYPES[node.class_type];\n        if (key && node.inputs && key in node.inputs){ node.inputs[key] = \'wedge/\' + prefix; n++; }\n    }\n    return n;\n}\n// tag → {css class, dot colour}\nconst LOG_TAGS = {\n    \'info\':        {cls:\'tlog-info\',        dot:\'#e8e4dc\'},\n    \'muted\':       {cls:\'tlog-muted\',       dot:\'#555550\'},\n    \'ok\':          {cls:\'tlog-ok\',          dot:\'#5ad17a\'},\n    \'warn\':        {cls:\'tlog-warn\',        dot:\'#f0b656\'},\n    \'err\':         {cls:\'tlog-err\',         dot:\'#ff6b6b\'},\n    \'running\':     {cls:\'tlog-running\',     dot:\'#6ea8fe\'},\n    \'header-line\': {cls:\'tlog-header-line\', dot:\'#d18d1f\'},\n    \'fallback\':    {cls:\'tlog-fallback\',    dot:\'#f59edb\'},\n};\nfunction log(msg, tag=\'info\'){\n    const ts = new Date().toLocaleTimeString(\'en-GB\');\n    // legacy hidden div (keeps existing code that reads #log working)\n    const legEl = document.getElementById(\'log\');\n    if (legEl){\n        const l = document.createElement(\'div\');\n        l.innerHTML = \'<span class="ts">[\'+ts+\']</span> <span class="\'+tag+\'">\'+escapeHtml(msg)+\'</span>\';\n        legEl.appendChild(l);\n    }\n    // terminal panel\n    const tb = document.getElementById(\'terminal-body\');\n    if (tb){\n        const t = LOG_TAGS[tag] || {cls:\'tlog-muted\', dot:\'#555550\'};\n        const line = document.createElement(\'div\');\n        line.className = \'tlog-line\';\n        line.innerHTML = \'<span class="tlog-time">[\'+ts+\']</span><span class="\'+t.cls+\'">\'+escapeHtml(msg)+\'</span>\';\n        tb.appendChild(line);\n        tb.scrollTop = tb.scrollHeight;\n        // dot: colour + blink on err/running, solid flash otherwise\n        const dot = document.getElementById(\'terminal-dot\');\n        if (dot){\n            dot.style.background = t.dot;\n            dot.classList.remove(\'blink\');\n            dot.classList.add(\'active\');\n            if (tag === \'err\' || tag === \'running\') dot.classList.add(\'blink\');\n            else setTimeout(() => { dot.classList.remove(\'active\'); }, 2000);\n        }\n        // auto-open terminal on first log entry if collapsed\n        const term = document.getElementById(\'terminal\');\n        if (term && term.classList.contains(\'collapsed\')){\n            // just flash the dot — don\'t auto-open, let user decide\n        }\n    }\n}\nfunction toggleTerminal(){\n    const term = document.getElementById(\'terminal\');\n    term.classList.toggle(\'collapsed\');\n    term.classList.toggle(\'open\');\n    if (term.classList.contains(\'collapsed\')){\n        term.style.height = \'\';\n    } else if (!term.style.height){\n        term.style.height = \'220px\';\n    }\n}\nfunction clearTerminal(){\n    const tb = document.getElementById(\'terminal-body\');\n    if (tb) tb.innerHTML = \'\';\n    const dot = document.getElementById(\'terminal-dot\');\n    if (dot){ dot.classList.remove(\'active\',\'blink\'); }\n    log(\'Log cleared.\', \'muted\');\n}\n// resize drag — exact Blueprint Builder implementation\n(function(){\n    let isResizing = false, startY = 0, startHeight = 0, mouseHasMoved = false;\n    // wait for DOM ready\n    function initTermResize(){\n        const terminal = document.getElementById(\'terminal\');\n        const termBar  = document.getElementById(\'terminal-bar\');\n        if (!terminal || !termBar) return;\n\n        termBar.addEventListener(\'mousedown\', (e) => {\n            if (e.target.closest(\'#terminal-actions\')) return;\n            const rect = termBar.getBoundingClientRect();\n            const edgeDistance = e.clientY - rect.top;\n            if (edgeDistance <= 4 && terminal.classList.contains(\'open\')) {\n                isResizing = true;\n                mouseHasMoved = false;\n                startY = e.clientY;\n                startHeight = terminal.offsetHeight;\n                e.preventDefault();\n                e.stopPropagation();\n            }\n        });\n\n        document.addEventListener(\'mousemove\', (e) => {\n            if (!isResizing) return;\n            mouseHasMoved = true;\n            terminal.classList.add(\'resizing\');\n            document.body.style.cursor = \'ns-resize\';\n            const deltaY = startY - e.clientY;\n            const newHeight = Math.max(100, Math.min(window.innerHeight * 0.8, startHeight + deltaY));\n            terminal.style.height = newHeight + \'px\';\n            e.preventDefault();\n        });\n\n        document.addEventListener(\'mouseup\', (e) => {\n            if (!isResizing) return;\n            isResizing = false;\n            terminal.classList.remove(\'resizing\');\n            document.body.style.cursor = \'\';\n            if (mouseHasMoved) {\n                termBar.dataset.justResized = \'true\';\n                setTimeout(() => { delete termBar.dataset.justResized; }, 100);\n                e.preventDefault();\n                e.stopPropagation();\n            }\n            mouseHasMoved = false;\n        });\n\n        // click to toggle — separate from mousedown, checks justResized\n        termBar.addEventListener(\'click\', (e) => {\n            if (e.target.closest(\'#terminal-actions\')) return;\n            if (termBar.dataset.justResized === \'true\') return;\n            toggleTerminal();\n        });\n    }\n    if (document.readyState === \'loading\')\n        document.addEventListener(\'DOMContentLoaded\', initTermResize);\n    else\n        initTermResize();\n})();\n// col-order horizontal resize handle\n(function(){\n    let isResizing = false, startX = 0, startW = 0;\n    function initColResize(){\n        const handle   = document.getElementById(\'col-resize-handle\');\n        const colOrder = document.querySelector(\'.col-order\');\n        if (!handle || !colOrder) return;\n        const clamp = (v) => Math.max(180, Math.min(600, v));\n        handle.addEventListener(\'mousedown\', (e) => {\n            isResizing = true; startX = e.clientX; startW = colOrder.offsetWidth;\n            handle.classList.add(\'active\'); document.body.style.cursor = \'ew-resize\';\n            e.preventDefault();\n        });\n        document.addEventListener(\'mousemove\', (e) => {\n            if (!isResizing) return;\n            colOrder.style.width = clamp(startW + e.clientX - startX) + \'px\';\n            e.preventDefault();\n        });\n        document.addEventListener(\'mouseup\', () => {\n            if (!isResizing) return;\n            isResizing = false; handle.classList.remove(\'active\'); document.body.style.cursor = \'\';\n        });\n        handle.addEventListener(\'touchstart\', (e) => {\n            isResizing = true; startX = e.touches[0].clientX; startW = colOrder.offsetWidth;\n            handle.classList.add(\'active\');\n        }, {passive:true});\n        document.addEventListener(\'touchmove\', (e) => {\n            if (!isResizing) return;\n            colOrder.style.width = clamp(startW + e.touches[0].clientX - startX) + \'px\';\n        }, {passive:true});\n        document.addEventListener(\'touchend\', () => {\n            isResizing = false; handle.classList.remove(\'active\');\n        });\n    }\n    if (document.readyState === \'loading\')\n        document.addEventListener(\'DOMContentLoaded\', initColResize);\n    else\n        initColResize();\n})();\nfunction escapeHtml(s){ return String(s).replace(/[&<>]/g, c => ({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\'}[c])); }\nconst sleep = ms => new Promise(r => setTimeout(r, ms));\n\n// Kill and restart ComfyUI process, then wait for it to come back online\nasync function doRestartComfy(){\n    if (!WEDGE_SERVER){\n        log(\'    Auto-restart: requires wedge_studio.py\', \'warn\'); return;\n    }\n    const comfyPath = document.getElementById(\'comfyPath\')?.value?.trim() || \'\';\n    if (!comfyPath){\n        log(\'    Auto-restart: no ComfyUI folder set in header\', \'warn\'); return;\n    }\n    log(\'    \\u21ba Restarting ComfyUI…\', \'warn\');\n    try {\n        const rr = await fetch(WEDGE_SERVER+\'/restart_comfy\', {\n            method:\'POST\', headers:{\'Content-Type\':\'application/json\'},\n            body: JSON.stringify({comfy_path: comfyPath})\n        });\n        const rd = await rr.json();\n        if (rd.ok){\n            log(\'    Process killed \\u2014 waiting for restart\\u2026\', \'warn\');\n            const ok = await waitForComfy(90000, 3000);\n            if (ok) log(\'    \\u2713 ComfyUI back online.\', \'ok\');\n            else    log(\'    ComfyUI did not respond after 90s.\', \'err\');\n        } else { log(\'    Restart failed: \' + (rd.error||\'?\'), \'err\'); }\n    } catch(e){ log(\'    Restart request failed: \' + e.message, \'err\'); }\n}\n\n// Clear ComfyUI VRAM (unload models + free memory)\nasync function freeVram(){\n    try {\n        log(\'    \\u21ba Clearing VRAM\\u2026\', \'muted\');\n        const _freeResp = await fetch(comfyBase() + \'/free\', {\n            method: \'POST\', headers: {\'Content-Type\':\'application/json\'},\n            body: JSON.stringify({unload_models: true, free_memory: true})\n        });\n        if (!_freeResp.ok) {\n            log(\'    VRAM clear failed: HTTP \' + _freeResp.status + \' \\u2014 /free endpoint missing or errored\', \'warn\');\n        } else {\n            log(\'    \\u2713 VRAM cleared.\', \'ok\');\n        }\n    } catch(e){\n        log(\'    VRAM clear failed: \' + e.message, \'warn\');\n    }\n}\n\n// ============ mode detection ============\n// All ComfyUI calls are proxied through /comfy_proxy when running via\n// _wedge_studio.py, so there are no cross-origin requests and no CORS\n// issues to detect or handle here.\nasync function checkComfy(){\n    const pill = document.getElementById(\'modePill\');\n    try {\n        const ctrl = new AbortController();\n        const t = setTimeout(() => ctrl.abort(), 3500);\n        const r = await fetch(comfyBase() + \'/system_stats\', {signal: ctrl.signal});\n        clearTimeout(t);\n        if (r.ok){\n            comfyOnline = true;\n            pill.className   = \'mode-pill local-ok\';\n            pill.textContent = \'\\u25cf Local \\u00b7 ComfyUI online\';\n            updateRunButton();\n            return true;\n        }\n    } catch(e){}\n    comfyOnline = false;\n    pill.className   = \'mode-pill local-bad\';\n    pill.textContent = \'COMFYUI OFFLINE\';\n    updateRunButton();\n    return false;\n}\nsetInterval(checkComfy, 6000);\n\nfunction updateRunButton(){\n    const btn = document.getElementById(\'runBtn\');\n    btn.disabled = !comfyOnline || running || !order.length;\n    btn.classList.toggle(\'btn-primary\', comfyOnline && order.length > 0);\n}\n\n// ============ load files (folder drag-drop or picker) ============\nconst dropzone = document.getElementById(\'dropzone\');\n[\'dragenter\',\'dragover\'].forEach(ev => dropzone.addEventListener(ev, e => {e.preventDefault(); dropzone.classList.add(\'over\');}));\n[\'dragleave\',\'drop\'].forEach(ev => dropzone.addEventListener(ev, e => {e.preventDefault(); dropzone.classList.remove(\'over\');}));\n// Also accept drops on the page so big-target gestures work\ndocument.addEventListener(\'dragover\', e => e.preventDefault());\ndropzone.addEventListener(\'drop\', async (e) => {\n    const items = e.dataTransfer.items;\n    if (!items) return;\n    const collected = [];\n    const promises = [];\n    for (const item of items){\n        const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();\n        if (entry){ promises.push(walkEntry(entry, collected)); }\n        else if (item.kind === \'file\'){\n            const f = item.getAsFile();\n            if (f && f.name.toLowerCase().endsWith(\'.json\')) collected.push(f);\n        }\n    }\n    await Promise.all(promises);\n    await ingestFiles(collected);\n});\n\nfunction walkEntry(entry, acc){\n    return new Promise((resolve) => {\n        if (entry.isFile){\n            if (entry.name.toLowerCase().endsWith(\'.json\')){\n                entry.file(f => { acc.push(f); resolve(); }, () => resolve());\n            } else resolve();\n        } else if (entry.isDirectory){\n            const reader = entry.createReader();\n            const readBatch = () => reader.readEntries(async (entries) => {\n                if (!entries.length) return resolve();\n                await Promise.all(entries.map(e => walkEntry(e, acc)));\n                readBatch();\n            }, () => resolve());\n            readBatch();\n        } else resolve();\n    });\n}\n\ndocument.getElementById(\'fileInput\').addEventListener(\'change\', async (e) => {\n    await ingestFiles([...e.target.files]);\n    e.target.value = \'\';\n});\n\nasync function ingestFiles(files){\n    if (!files || !files.length) return;\n    // capture folder name from the first file\'s path (webkitRelativePath gives folder/file.json)\n    if (files[0]) {\n        const rel = files[0].webkitRelativePath || files[0].name;\n        const parts = rel.split(\'/\');\n        if (parts.length > 1) folderName = parts[0];\n        else folderName = \'wedge\';\n    }\n    let okN = 0, invalidN = 0;\n    for (const f of files){\n        if (!f.name.toLowerCase().endsWith(\'.json\')) continue;\n        const name = f.name.replace(/\\.json$/i, \'\');\n        try {\n            const text = await f.text();\n            const wf = JSON.parse(text);\n            if (isApiFormat(wf)){ workflows[name] = {wf, validApi:true}; okN++; }\n            else { workflows[name] = {wf:null, validApi:false}; invalidN++; }\n        } catch(err){ workflows[name] = {wf:null, validApi:false}; invalidN++; }\n    }\n    // add as singles if not already in order\n    const existing = new Set();\n    for (const u of order){ if (u.type===\'single\') existing.add(u.name); else u.names.forEach(n=>existing.add(n)); }\n    for (const name of Object.keys(workflows)){\n        if (!existing.has(name)) order.push({type:\'single\', name});\n    }\n    if (okN) log(`Loaded ${okN} workflow(s).`, \'muted\');\n    if (invalidN) log(`${invalidN} file(s) skipped (not API format).`, \'warn\');\n    renderAvail(); renderOrder(); renderGraph(); updateRunButton();\n}\n\n// ============ available list ============\nfunction renderAvail(){\n    const el = document.getElementById(\'availList\');\n    el.innerHTML = \'\';\n    for (const name of Object.keys(workflows)){\n        const meta = workflows[name];\n        const div = document.createElement(\'div\');\n        const sel = chainSel.includes(name);\n        const cls = [\'wf-item\', sel && \'selected\', !meta.validApi && \'invalid\'].filter(Boolean).join(\' \');\n        div.className = cls;\n        const seq = sel ? (chainSel.indexOf(name)+1) : \'\';\n        const label = name + (meta.validApi ? \'\' : \'  · not API format\');\n        div.innerHTML = `<span class="seq">${seq}</span><span>${escapeHtml(label)}</span>`;\n        div.onclick = () => { if (meta.validApi) toggleSel(name); else log(`\'${name}\' is not API format — re-save with "Save (API Format)" in ComfyUI.`, \'warn\'); };\n        el.appendChild(div);\n    }\n    const txt = chainSel.length ? chainSel.join(\'  →  \') : \'(none)\';\n    document.getElementById(\'selInfo\').textContent = \'selected: \' + txt;\n}\nfunction toggleSel(name){\n    const i = chainSel.indexOf(name);\n    if (i >= 0) chainSel.splice(i,1); else chainSel.push(name);\n    renderAvail();\n}\nfunction clearSel(){ chainSel = []; renderAvail(); }\n\nfunction purgeNames(names){\n    const out = [];\n    for (const u of order){\n        if (u.type === \'single\'){ if (!names.includes(u.name)) out.push(u); }\n        else {\n            const kept = u.names.filter(n => !names.includes(n));\n            if (kept.length >= 2){ u.names = kept; out.push(u); }\n            else if (kept.length === 1){ out.push({type:\'single\', name:kept[0]}); }\n        }\n    }\n    order = out;\n}\nfunction makeChain(){\n    if (!order.length){ return; }\n    chainBuildMode = true;\n    orderChainSel = [];\n    const banner = document.getElementById(\'chainBuildBanner\');\n    if (banner){ banner.style.display = \'flex\'; }\n    const btn = document.getElementById(\'makeChainBtn\');\n    if (btn){ btn.style.borderColor = \'var(--accent-gold)\'; btn.style.background = \'rgba(209,141,31,0.15)\'; }\n    const title = document.getElementById(\'orderColTitle\');\n    if (title){ title.textContent = \'Chain Builder \u00b7 click items in order\'; }\n    renderOrder();\n}\nfunction cancelChainBuild(){\n    chainBuildMode = false;\n    orderChainSel = [];\n    const banner = document.getElementById(\'chainBuildBanner\');\n    if (banner){ banner.style.display = \'none\'; }\n    const btn = document.getElementById(\'makeChainBtn\');\n    if (btn){ btn.style.borderColor = \'\'; btn.style.background = \'\'; }\n    const title = document.getElementById(\'orderColTitle\');\n    if (title){ title.textContent = \'Run Order \u00b7 drag to reorder\'; }\n    renderOrder();\n}\nfunction confirmChain(){\n    if (orderChainSel.length < 2){ return; }\n    // Preserve full unit objects so any future per-unit data (params, overrides) survives\n    const pickedUnits = orderChainSel.map(i => order[i]);\n    const names = pickedUnits.map(u => u.type === \'single\' ? u.name : u.names[0]);\n    // nodes carries the full unit snapshot — safe to add fields to later\n    const nodes = pickedUnits.map(u => Object.assign({}, u));\n    const toRemove = new Set(orderChainSel);\n    order = order.filter((_,i) => !toRemove.has(i));\n    order.push({type:\'chain\', names, nodes, mode:\'success\'});\n    cancelChainBuild();\n    renderOrder(); renderGraph(); updateRunButton();\n}\nfunction addSingles(){\n    if (!chainSel.length) return;\n    const names = [...chainSel];\n    purgeNames(names);\n    for (const n of names) order.push({type:\'single\', name:n});\n    clearSel(); renderOrder(); renderGraph(); updateRunButton();\n}\n\n// ============ run order (drag) ============\nfunction renderOrder(){\n    const el = document.getElementById(\'orderList\');\n    el.innerHTML = \'\';\n    order.forEach((u, i) => {\n        const div = document.createElement(\'div\');\n        const _stCls = (u._status && u._status !== \'pending\') ? \' \' + u._status : \'\';\n        const _cpick = chainBuildMode && orderChainSel.includes(i);\n        div.className = \'unit\' + (u.type===\'chain\'?\' chain\':\'\') + (!chainBuildMode && selUnit===i?\' selected\':\'\') + (_cpick?\' selected\':\'\') + _stCls;\n        div.dataset.unitIdx = i;\n        if (u.type===\'single\') div.dataset.name = u.name;\n        div.draggable = !chainBuildMode;\n        if (chainBuildMode) div.style.cursor = \'pointer\';\n        let inner;\n        if (u.type === \'single\'){\n            const _pp = chainBuildMode ? orderChainSel.indexOf(i) : -1;\n            const _pb = _pp >= 0 ? `<span class="seq" style="display:inline-flex;">${_pp+1}</span>` : ``;\n            inner = `<span class="idx">${i+1}</span>${_pb}<span class="ico">○</span><span class="lbl">${escapeHtml(u.name)}</span>`;\n        } else {\n            const tag = u.mode === \'success\' ? \'success\' : \'failure\';\n            const tagtxt = u.mode === \'success\' ? \'✓ succ\' : \'✗ fail\';\n            inner = `<span class="idx">${i+1}</span><span class="ico">⛓</span><span class="lbl">${escapeHtml(u.names.join(\' → \'))}</span><span class="mode-tag ${tag}">${tagtxt}</span>`;\n        }\n        div.innerHTML = inner;\n        // ✕ remove button on each row\n        if (u.type===\'single\' && !chainBuildMode && workflows[u.name]?.validApi) {\n            const hasCfg=_pCfg[u.name]&&(_pCfg[u.name].promoted.size||_pCfg[u.name].variants.length);\n            const gBtn=document.createElement(\'button\');\n            gBtn.className=\'unit-gear\'+(hasCfg?\' cfg\':\'\');\n            gBtn.textContent=\'⚙\'; gBtn.title=\'Promote parameters\';\n            gBtn.addEventListener(\'click\',(e)=>{ e.stopPropagation(); openParamPanel(u.name); });\n            div.appendChild(gBtn);\n        }\n        const xBtn = document.createElement(\'span\');\n        xBtn.textContent = \'✕\';\n        xBtn.title = \'Remove from run list\';\n        xBtn.style.cssText = \'padding:0 6px;color:var(--text-dim);cursor:pointer;font-size:11px;flex-shrink:0;\';\n        xBtn.addEventListener(\'mouseenter\', () => xBtn.style.color = \'var(--err)\');\n        xBtn.addEventListener(\'mouseleave\', () => xBtn.style.color = \'var(--text-dim)\');\n        xBtn.addEventListener(\'click\', (e) => { e.stopPropagation(); if (!chainBuildMode) removeUnit(i); });\n        if (chainBuildMode) xBtn.style.opacity = \'0.3\';\n        div.appendChild(xBtn)\n        // VRAM clear checkbox\n        const vramWrap = document.createElement(\'label\');\n        vramWrap.className = \'vram-cb\' + (u.clearVram ? \' on\' : \'\');\n        vramWrap.title = \'Clear VRAM after this workflow\';\n        vramWrap.addEventListener(\'click\', e => e.stopPropagation());\n        const vramChk = document.createElement(\'input\');\n        vramChk.type = \'checkbox\'; vramChk.checked = !!u.clearVram;\n        vramChk.addEventListener(\'change\', e => {\n            u.clearVram = e.target.checked;\n            vramWrap.classList.toggle(\'on\', u.clearVram);\n        });\n        vramWrap.appendChild(vramChk);\n        vramWrap.appendChild(Object.assign(document.createElement(\'span\'), {textContent:\'VRAM\'}));\n        div.insertBefore(vramWrap, xBtn);;\n        // restart ComfyUI checkbox\n        const rstrtWrap = document.createElement(\'label\');\n        rstrtWrap.className = \'vram-cb restart-cb\' + (u.restartComfy ? \' on\' : \'\');\n        rstrtWrap.title = \'Kill and restart ComfyUI after this workflow\';\n        rstrtWrap.addEventListener(\'click\', e => e.stopPropagation());\n        const rstrtChk = document.createElement(\'input\');\n        rstrtChk.type = \'checkbox\'; rstrtChk.checked = !!u.restartComfy;\n        rstrtChk.addEventListener(\'change\', e => {\n            u.restartComfy = e.target.checked;\n            rstrtWrap.classList.toggle(\'on\', u.restartComfy);\n        });\n        rstrtWrap.appendChild(rstrtChk);\n        rstrtWrap.appendChild(Object.assign(document.createElement(\'span\'), {textContent:\'RSTRT\'}));\n        div.insertBefore(rstrtWrap, xBtn);\n        div.onclick = () => {\n            if (chainBuildMode) {\n                const pos = orderChainSel.indexOf(i);\n                if (pos >= 0) { orderChainSel.splice(pos, 1); }\n                else { orderChainSel.push(i); }\n                const confirmBtn = document.getElementById(\'confirmChainBtn\');\n                const hint = document.getElementById(\'chainBuildHint\');\n                if (confirmBtn) confirmBtn.disabled = orderChainSel.length < 2;\n                if (hint) hint.textContent = orderChainSel.length === 0\n                    ? \'Click items in order \u00b7 select \u22652\'\n                    : orderChainSel.map((idx,n) => (n+1)+\'. \'+(order[idx].type===\'single\' ? order[idx].name : order[idx].names[0])).join(\'  \u2192  \');\n                renderOrder();\n            } else {\n                selUnit = i; renderOrder();\n            }\n        };\n        div.addEventListener(\'dragstart\', e => { dragIdx = i; div.classList.add(\'dragging\'); });\n        div.addEventListener(\'dragend\',  e => { div.classList.remove(\'dragging\'); document.querySelectorAll(\'.unit\').forEach(u=>u.classList.remove(\'drag-over\')); });\n        div.addEventListener(\'dragover\', e => { e.preventDefault(); div.classList.add(\'drag-over\'); });\n        div.addEventListener(\'dragleave\',e => { div.classList.remove(\'drag-over\'); });\n        div.addEventListener(\'drop\', e => {\n            e.preventDefault();\n            div.classList.remove(\'drag-over\');\n            if (dragIdx === null || dragIdx === i) return;\n            const moved = order.splice(dragIdx, 1)[0];\n            order.splice(i, 0, moved);\n            selUnit = i; dragIdx = null;\n            renderOrder(); renderGraph();\n        });\n        el.appendChild(div);\n    });\n    if (!order.length) el.innerHTML = \'<div class="empty-hint">No units yet.<br>Drag a folder onto the left dropzone, then arrange chains/order here.</div>\';\n}\nfunction removeSelectedUnit(){\n    if (selUnit === null || selUnit >= order.length) return;\n    order.splice(selUnit, 1);\n    selUnit = null; renderOrder(); renderGraph(); updateRunButton();\n}\nfunction removeUnit(i){\n    order.splice(i, 1);\n    if (selUnit === i) selUnit = null;\n    else if (selUnit > i) selUnit--;\n    renderOrder(); renderGraph(); updateRunButton();\n}\n\n// ============ graph ============\nlet nodeEls = {};\nfunction renderGraph(){\n    const g = document.getElementById(\'graph\');\n    g.innerHTML = \'\'; nodeEls = {};\n    const chains = order.map((u,i)=>({u,i})).filter(x => x.u.type===\'chain\');\n    const title = document.getElementById(\'graphTitle\');\n    if (!chains.length){ title.textContent = \'Chain Graph · make a chain to see it here\'; return; }\n    title.textContent = \'Chain Graph · click a chain to flip mode · grey=pending blue=running green=ok red=fail\';\n    for (const {u,i} of chains){\n        const row = document.createElement(\'div\');\n        row.className = \'chain-row\';\n        row.onclick = () => { u.mode = u.mode===\'success\'?\'failure\':\'success\'; renderOrder(); renderGraph(); };\n        const mode = document.createElement(\'span\');\n        mode.className = \'chain-mode \' + u.mode;\n        mode.textContent = u.mode===\'success\' ? \'✓ stop on success\' : \'✗ stop on fail\';\n        row.appendChild(mode);\n        u.names.forEach((nm, ni) => {\n            const node = document.createElement(\'span\');\n            const _ns = (window._nodeStatus && window._nodeStatus[nm]) || null;\n            const _nsCls = _ns ? (\' \' + _ns.state + (_ns.reused ? \' reused\' : \'\')) : \'\';\n            node.className = \'gnode\' + _nsCls; node.dataset.name = nm;\n            // name label\n            const gnLbl = document.createElement(\'span\');\n            gnLbl.className = \'gnode-lbl\'; gnLbl.textContent = nm;\n            node.appendChild(gnLbl);\n            // per-node VRAM checkbox\n            const gnVramWrap = document.createElement(\'label\');\n            const gnVramOn = u.nodeVram && u.nodeVram[nm];\n            gnVramWrap.className = \'vram-cb\' + (gnVramOn ? \' on\' : \'\');\n            gnVramWrap.title = \'Clear VRAM after this node\';\n            gnVramWrap.addEventListener(\'click\', e => e.stopPropagation());\n            const gnVramChk = document.createElement(\'input\');\n            gnVramChk.type = \'checkbox\'; gnVramChk.checked = !!gnVramOn;\n            gnVramChk.addEventListener(\'change\', e => {\n                if (!u.nodeVram) u.nodeVram = {};\n                u.nodeVram[nm] = e.target.checked;\n                gnVramWrap.classList.toggle(\'on\', e.target.checked);\n            });\n            gnVramWrap.appendChild(gnVramChk);\n            gnVramWrap.appendChild(Object.assign(document.createElement(\'span\'), {textContent:\'VRAM\'}));\n            node.appendChild(gnVramWrap);\n            // per-node RSTRT checkbox\n            const gnRstrtWrap = document.createElement(\'label\');\n            const gnRstrtOn = u.nodeRstrt && u.nodeRstrt[nm];\n            gnRstrtWrap.className = \'vram-cb restart-cb\' + (gnRstrtOn ? \' on\' : \'\');\n            gnRstrtWrap.title = \'Kill and restart ComfyUI after this node\';\n            gnRstrtWrap.addEventListener(\'click\', e => e.stopPropagation());\n            const gnRstrtChk = document.createElement(\'input\');\n            gnRstrtChk.type = \'checkbox\'; gnRstrtChk.checked = !!gnRstrtOn;\n            gnRstrtChk.addEventListener(\'change\', e => {\n                if (!u.nodeRstrt) u.nodeRstrt = {};\n                u.nodeRstrt[nm] = e.target.checked;\n                gnRstrtWrap.classList.toggle(\'on\', e.target.checked);\n            });\n            gnRstrtWrap.appendChild(gnRstrtChk);\n            gnRstrtWrap.appendChild(Object.assign(document.createElement(\'span\'), {textContent:\'RSTRT\'}));\n            node.appendChild(gnRstrtWrap);\n            // per-node param override gear button\n            if (workflows[nm]?.validApi) {\n                const _hasOvr = (u.nodes||[])[ni]?.paramOverrides &&\n                    Object.keys((u.nodes[ni].paramOverrides)||{}).length > 0;\n                const gnGear = document.createElement(\'button\');\n                gnGear.className = \'unit-gear\' + (_hasOvr ? \' cfg\' : \'\');\n                gnGear.textContent = \'⚙\';\n                gnGear.title = \'Overrides \\u00b7 \' + nm;\n                gnGear.addEventListener(\'click\', (function(_u,_ni){\n                    return function(e){ e.stopPropagation(); openChainNodePanel(_u, _ni); };\n                })(u, ni));\n                node.appendChild(gnGear);\n            }\n            row.appendChild(node);\n            (nodeEls[nm] = nodeEls[nm] || []).push(node);\n            if (ni < u.names.length-1){\n                const a = document.createElement(\'span\'); a.className=\'garrow\'; a.textContent=\'→\'; row.appendChild(a);\n            }\n        });\n        g.appendChild(row);\n    }\n}\nfunction colorNode(name, state, reused){\n    (nodeEls[name]||[]).forEach(el => {\n        el.className = \'gnode \' + state + (reused ? \' reused\' : \'\');\n    });\n    // persist node status so renderGraph can restore it on rebuild\n    if (!window._nodeStatus) window._nodeStatus = {};\n    window._nodeStatus[name] = {state, reused: !!reused};\n    // persist on the data model so renderOrder restores it on rebuild\n    order.forEach(u => { if (u.type === \'single\' && u.name === name) u._status = state; });\n    // also highlight the unit row in the order list\n    document.querySelectorAll(`.unit[data-name="${CSS.escape(name)}"]`).forEach(el => {\n        el.classList.remove(\'running\',\'ok\',\'fail\');\n        if (state && state !== \'pending\') el.classList.add(state);\n    });\n}\n\nfunction colorChainUnit(unitIdx, state){\n    // persist on the data model so renderOrder restores on rebuild\n    if (order[unitIdx]) order[unitIdx]._status = state;\n    const el = document.querySelector(`.unit[data-unit-idx="${unitIdx}"]`);\n    if (!el) return;\n    el.classList.remove(\'running\',\'ok\',\'fail\');\n    if (state) el.classList.add(state);\n}\n\n// ============ download local copy with baked plan ============\nasync function downloadLocalCopy(){\n    if (!order.length){ alert(\'Build a plan first (add workflows and arrange them).\'); return; }\n    // Confirm at least one workflow has actual content (else local file can\'t run them)\n    const hasContent = Object.values(workflows).some(w => w && w.validApi && w.wf);\n    if (!hasContent){\n        if (!confirm(\'You haven\\\'t loaded any workflow content yet — the downloaded file will have your PLAN but no workflows baked in. On the target machine you\\\'ll need to drag the workflow folder again. Continue?\')) return;\n    }\n    // Build the baked plan\n    const plan = {\n        order: JSON.parse(JSON.stringify(order)),\n        server: document.getElementById(\'server\').value.trim(),\n        timeout: parseFloat(document.getElementById(\'timeout\').value) || 20,\n        workflows: {}\n    };\n    for (const [name, meta] of Object.entries(workflows)){\n        if (meta && meta.validApi && meta.wf) plan.workflows[name] = meta.wf;\n    }\n    // Fetch this very page and inject the plan as BAKED_PLAN\n    let pageHtml;\n    try {\n        const r = await fetch(window.location.href);\n        pageHtml = await r.text();\n    } catch(e){\n        // Fallback: use the live document — works when opened from file://\n        pageHtml = \'<!DOCTYPE html>\\n\' + document.documentElement.outerHTML;\n    }\n    const planJs = \'const BAKED_PLAN = \' + JSON.stringify(plan).replace(/<\\/script/gi, \'<\\\\/script\') + \';\';\n    const out = pageHtml.replace(/const BAKED_PLAN = null;/, planJs);\n\n    const stamp = new Date().toISOString().replace(/[:.]/g,\'-\').slice(0,19);\n    const blob = new Blob([out], {type:\'text/html;charset=utf-8\'});\n    const a = document.createElement(\'a\');\n    a.href = URL.createObjectURL(blob);\n    a.download = `wedge_studio_${stamp}.html`;\n    document.body.appendChild(a); a.click(); a.remove();\n    setTimeout(() => URL.revokeObjectURL(a.href), 5000);\n    log(`Downloaded local copy with ${Object.keys(plan.workflows).length} workflow(s) baked in.`, \'ok\');\n}\n\n// ============ run engine ============\nasync function startRun(){\n    if (running) return;\n    if (!comfyOnline){\n        alert(\'ComfyUI is offline.\\n\\nStart it with:\\n  python main.py --enable-cors-header "*"\\n\\nThen this page will switch to Local mode automatically.\');\n        return;\n    }\n    if (!order.length){ alert(\'Build a plan first.\'); return; }\n    // sanity: every name in order must have a loaded workflow\n    const missing = [];\n    for (const u of order){\n        const names = u.type===\'single\' ? [u.name] : u.names;\n        for (const n of names) if (!workflows[n] || !workflows[n].validApi || !workflows[n].wf) missing.push(n);\n    }\n    if (missing.length){\n        alert(`Missing workflow content for: ${[...new Set(missing)].join(\', \')}\\n\\nDrag the folder containing these .json files onto the dropzone to load them.`);\n        return;\n    }\n\n    // ── save config (_wedge_config.json) before running ─────────────────────\n    if (WEDGE_SERVER) {\n        const _cpEl = document.getElementById(\'comfyPath\');\n        const _cfg = {\n            timeout: parseFloat(document.getElementById(\'timeout\').value) || 20,\n            order: JSON.parse(JSON.stringify(order))\n        };\n        if (_cpEl && _cpEl.value.trim()) _cfg.comfy_path = _cpEl.value.trim();\n        fetch(WEDGE_SERVER+\'/save_config\', {\n            method: \'POST\',\n            headers: {\'Content-Type\': \'application/json\'},\n            body: JSON.stringify(_cfg)\n        }).catch(()=>{});\n        log(\'✓ Config saved to _wedge_config.json\', \'muted\');\n    }\n    running = true; stopFlag = false;\n    document.getElementById(\'runBtn\').disabled = true;\n    document.getElementById(\'stopBtn\').disabled = false;\n    document.getElementById(\'results\').innerHTML = \'\';\n    setBar(\'job\',0); setBar(\'batch\',0);\n    sessionResults = {};\n    _reportPaths.length = 0;\n    // clear stored statuses from previous run so colors don\'t carry over\n    window._nodeStatus = {};\n    order.forEach(u => { delete u._status; });\n    renderGraph();\n    // reset any leftover run-state colours on unit rows\n    document.querySelectorAll(\'.unit\').forEach(el => el.classList.remove(\'running\',\'ok\',\'fail\'));\n\n    const timeoutS = Math.max(10, (parseFloat(document.getElementById(\'timeout\').value)||20)*60);\n    log(`Batch: ${order.length} unit(s) | timeout ${(timeoutS/60).toFixed(0)} min`, \'header-line\');\n\n    let okCount = 0;\n    for (let i=0; i<order.length; i++){\n        if (stopFlag){ log(\'Stopped by user.\', \'warn\'); break; }\n        const u = order[i];\n        const head = u.type===\'single\' ? u.name : u.names[0];\n        setBar(\'batch\', i/order.length*100); document.getElementById(\'batchPct\').textContent = `${i+1}/${order.length}`;\n        document.getElementById(\'progressText\').textContent = `Running ${i+1}/${order.length}: ${head}`;\n        const jobTimeoutS = (u.timeout && u.timeout > 0) ? u.timeout * 60 : timeoutS;\n        if (u.timeout && u.timeout > 0)\n            log(`\\u2500 Job ${i+1}/${order.length}: ${head}  [timeout: ${u.timeout}min]`, \'muted\');\n        else\n            log(`\\\\u2500 Job ${i+1}/${order.length}: ${head}`, \'muted\');\n        let res;\n        try {\n            if (u.type===\'single\'){\n                // variant outputs: use label as filename_prefix so [v1]/[v2] don\'t clobber\n                const _pfx = (u.label && u.label !== u.name) ? u.label : null;\n                res = await runLink(u.name, head, jobTimeoutS, _pfx,\n                    u.paramOverrides || null, _pfx || u.name);\n            } else {\n                colorChainUnit(i, \'running\');\n                const chainResults = await runChainAll(u, jobTimeoutS);\n                let chainOk = false;\n                chainResults.forEach(cr => { if (cr.ok) chainOk = true; });\n                colorChainUnit(i, chainOk ? \'ok\' : \'fail\');\n                if (chainOk) okCount++;\n                res = chainResults[chainResults.length - 1] || {ok:false,status:\'error\',secs:0,outs:[]};\n                // add result cards for chain (separate try so DOM errors don\'t hide results)\n                chainResults.forEach(cr => {\n                    try { addResult(cr.used || cr.name, cr); } catch(e){ console.error(\'addResult error:\', e); }\n                });\n                // clear VRAM after the whole chain if the unit checkbox is on\n                if (u.clearVram) await freeVram();\n                if (u.restartComfy) await doRestartComfy();\n            }\n        } catch(jobErr) {\n            log(\'    Run error in job \' + (i+1) + \': \' + jobErr.message, \'err\');\n            console.error(\'Job run error:\', jobErr);\n            if (!res) res = {ok:false, status:\'error\', secs:0, outs:[]};\n        }\n        // add result card for single (separate try)\n        if (u.type===\'single\' && res){\n            if (res.ok) okCount++;\n            try { addResult(res.used || head, res); } catch(e){ console.error(\'addResult error:\', e); }\n            // clear VRAM after this single unit if the checkbox is on\n            if (u.clearVram) await freeVram();\n        }\n        // save report after every job so progress is never lost\n        if (_autoReportEnabled !== false && resultStore.length && WEDGE_SERVER && serverFolder) {\n            exportReport(true); // silent=true: no log spam per job\n        }\n    }\n    setBar(\'batch\',100); setBar(\'job\',100);\n    document.getElementById(\'progressText\').textContent = `Done — ${okCount}/${order.length} OK`;\n    log(\'Batch complete.\', \'header-line\');\n    const _dot=document.getElementById(\'terminal-dot\');\n    if(_dot){ _dot.classList.remove(\'blink\'); _dot.style.background=\'var(--ok)\'; _dot.classList.add(\'active\'); }\n    running = false;\n    updateRunButton();\n    document.getElementById(\'stopBtn\').disabled = true;\n    // keep last intermediate report as final; delete all earlier ones\n    if (_autoReportEnabled !== false && resultStore.length) {\n        setTimeout(async () => {\n            const _allPaths = _reportPaths.slice();\n            _reportPaths.length = 0;\n            if (!_allPaths.length) {\n                // no intermediate reports yet — save one final now\n                log(\'Auto-saving final report...\', \'muted\');\n                exportReport();\n            } else {\n                // promote last intermediate to final; delete earlier ones\n                const _last = _allPaths[_allPaths.length - 1];\n                log(\'\\u2713 final report \\u2014 \' + _last.split(/[\\\\/]/).pop(), \'muted\');\n                const _toDelete = _allPaths.slice(0, -1);\n                if (_toDelete.length && WEDGE_SERVER) {\n                    await new Promise(r => setTimeout(r, 400));\n                    fetch(WEDGE_SERVER + \'/cleanup_reports\', {\n                        method: \'POST\', headers: {\'Content-Type\': \'application/json\'},\n                        body: JSON.stringify({paths: _toDelete})\n                    }).then(r => r.json()).then(d => {\n                        if (d.deleted > 0) log(\'\\u2713 Removed \' + d.deleted + \' intermediate report(s).\', \'muted\');\n                    }).catch(() => {});\n                }\n            }\n        }, 800);\n    }\n}\nfunction stopRun(){\n    stopFlag = true;\n    if (nukeAbort) { nukeAbort.aborted = true; nukeAbort = null; }\n    log(\'Stop requested — probing ComfyUI (soft stop or hard kill)...\', \'warn\');\n    document.getElementById(\'stopBtn\').disabled = true;\n    nukeJob(null).then(() => log(\'Queue cleared.\', \'muted\'));\n}\n\nlet sessionResults = {};\nasync function runChain(u, timeoutS){\n    const mode = u.mode || \'success\';\n    let last = {ok:false,status:\'error\',secs:0,outs:[],used:u.names[0]};\n    let lastGood = null;\n    for (let idx=0; idx<u.names.length; idx++){\n        if (stopFlag) break;\n        const nm = u.names[idx];\n        const res = await runLink(nm, u.names[0], timeoutS);\n        last = res;\n        if (mode===\'success\'){\n            if (res.ok) return res;\n            if (idx < u.names.length-1) log(`    ↳ fallback: ${nm} → ${u.names[idx+1]}`, \'fallback\');\n        } else {\n            if (res.ok){ lastGood = res; if (idx<u.names.length-1) log(`    ↳ next: ${nm} → ${u.names[idx+1]}`, \'fallback\'); }\n            else { return lastGood || res; }\n        }\n    }\n    return (mode===\'failure\' && lastGood) ? lastGood : last;\n}\n\n// runChainAll: like runChain but returns ALL intermediate results (one per workflow that ran)\nasync function runChainAll(u, timeoutS){\n    const mode = u.mode || \'success\';\n    const allResults = [];\n    let lastGood = null;\n    const chainNodes = u.nodes || [];\n    for (let idx = 0; idx < u.names.length; idx++){\n        if (stopFlag) break;\n        const nm = u.names[idx];\n        const cn = chainNodes[idx] || {};\n        const cnOverrides = cn.paramOverrides || null;\n        const cnLabel = (cn.label && cn.label !== nm) ? cn.label : null;\n        const res = await runLink(nm, u.names[0], timeoutS, cnLabel,\n            cnOverrides, cnLabel || nm);\n        allResults.push(res);\n        // clear VRAM after this node if the per-node checkbox is on\n        if (u.nodeVram && u.nodeVram[nm]) await freeVram();\n        if (u.nodeRstrt && u.nodeRstrt[nm]) await doRestartComfy();\n        if (mode === \'success\'){\n            if (res.ok) break; // stop on first success\n            if (idx < u.names.length - 1) log(\'    ↳ fallback: \' + nm + \' → \' + u.names[idx+1], \'fallback\');\n        } else { // stop on failure\n            if (res.ok){\n                lastGood = res;\n                if (idx < u.names.length - 1) log(\'    ↳ next: \' + nm + \' → \' + u.names[idx+1], \'fallback\');\n            } else {\n                break;\n            }\n        }\n    }\n    return allResults;\n}\n\nasync function runLink(name, head, timeoutS, prefix, overrides, cacheKey){\n    const _key = cacheKey || name;\n    if (_key in sessionResults){\n        const r = sessionResults[_key];\n        colorNode(name, r.ok?\'ok\':\'fail\', true);\n        log(`    \'${_key}\' already done this session (${r.status}) — reusing`, \'muted\');\n        return {...r, used:_key};\n    }\n    colorNode(name, \'running\', false);\n    const r = await runOne(name, timeoutS, overrides);\n    sessionResults[_key] = r;\n    colorNode(name, r.ok?\'ok\':\'fail\', false);\n    return {...r, used:_key};\n}\n\n// waitForComfy: poll until ComfyUI responds (or give up after maxWait)\nasync function waitForComfy(maxWaitMs=120000, intervalMs=3000){\n    const deadline = performance.now() + maxWaitMs;\n    let warned = false;\n    // first check — if ComfyUI responds immediately, skip silently\n    try {\n        const r = await fetch(comfyBase()+\'/system_stats\',\n            {signal: AbortSignal.timeout(2500)});\n        if (r.ok) return true;\n    } catch(e){}\n    // not immediately responsive — log and poll\n    log(\'    Waiting for ComfyUI to become responsive...\', \'muted\');\n    while (performance.now() < deadline){\n        try {\n            const r = await fetch(comfyBase()+\'/system_stats\',\n                {signal: AbortSignal.timeout(2500)});\n            if (r.ok){\n                log(\'    ComfyUI responsive.\', \'muted\');\n                return true;\n            }\n        } catch(e){}\n        await new Promise(r => setTimeout(r, intervalMs));\n    }\n    log(\'    ComfyUI did not respond after \' + (maxWaitMs/1000) + \'s — proceeding anyway\', \'warn\');\n    return false;\n}\n\nasync function runOne(name, timeoutS, overrides){\n    const src = workflows[name]?.wf;\n    if (!src){ log(`  ${name}: no workflow content loaded`, \'err\'); return {ok:false,status:\'missing\',secs:0,outs:[]}; }\n    const wf = JSON.parse(JSON.stringify(src));\n    rewritePrefix(wf, name);\n    if (overrides) {\n        for (const [key, val] of Object.entries(overrides)) {\n            const dot = key.indexOf(\'.\');\n            if (dot < 0) continue;\n            const nid = key.slice(0, dot), inp = key.slice(dot + 1);\n            if (wf[nid]?.inputs) wf[nid].inputs[inp] = val;\n        }\n    }\n    // abort any in-progress nuke retry loops before starting new job\n    if (nukeAbort) { nukeAbort.aborted = true; nukeAbort = null; }\n    // wait for ComfyUI to be responsive before queuing\n    await waitForComfy();\n    log(`  running \'${name}\' …`, \'running\');\n    setBar(\'job\',0); document.getElementById(\'jobPct\').textContent=\'\';\n    const t0 = performance.now();\n    let pid;\n    try {\n        const resp = await fetch(comfyBase()+\'/prompt\', {\n            method:\'POST\', headers:{\'Content-Type\':\'application/json\'},\n            body: JSON.stringify({prompt:wf, client_id:clientId})\n        });\n        if (!resp.ok){ const b = await resp.text(); log(`    REJECTED (${resp.status}): ${b.slice(0,200)}`, \'err\'); return {ok:false,status:\'rejected\',secs:(performance.now()-t0)/1000,outs:[]}; }\n        const data = await resp.json();\n        pid = data.prompt_id;\n        if (!pid){ log(\'    no prompt_id returned\', \'err\'); return {ok:false,status:\'no_id\',secs:(performance.now()-t0)/1000,outs:[]}; }\n    } catch(e){ log(`    error queuing: ${e.message}`, \'err\'); return {ok:false,status:\'queue_error\',secs:(performance.now()-t0)/1000,outs:[]}; }\n\n    const entry = await awaitWithProgress(pid, t0, timeoutS);\n    const secs = (performance.now()-t0)/1000;\n    if (!entry) return {ok:false, status: (stopFlag?\'interrupted\':\'timeout\'), secs, outs:[]};\n\n    const status = entry.status || {};\n    const ok = status.status_str === \'success\' || status.completed === true;\n    const outs = [];\n    for (const node of Object.values(entry.outputs||{})){\n        for (const kind of [\'videos\',\'gifs\',\'images\',\'audio\']){\n            for (const item of (node[kind]||[])){\n                if (item.filename) outs.push({sub:item.subfolder||\'\', fn:item.filename, type:item.type||\'output\'});\n            }\n        }\n    }\n    if (!ok){\n        // log ComfyUI error details so user knows what went wrong\n        const msgs = status.messages || [];\n        msgs.forEach(m => {\n            if (Array.isArray(m) && m[0] === \'execution_error\'){\n                const d = m[1] || {};\n                log(\'    ComfyUI error: \' + (d.exception_message || d.node_type || JSON.stringify(d).slice(0,120)), \'err\');\n            }\n        });\n        if (!msgs.length && status.status_str){\n            log(\'    ComfyUI status: \' + status.status_str, \'err\');\n        }\n    }\n    log(\'    \' + (ok?\'OK\':\'finished (check)\') + \' in \' + secs.toFixed(1) + \'s\', ok?\'ok\':\'warn\');\n    return {ok, status: ok?\'ok\':\'check\', secs, outs};\n}\n\n// nukeJob: aggressively clear a stuck ComfyUI job\n// Phase 1 (immediate): interrupt + delete from queue + clear pending — retries up to 5x\n// Phase 2 (after 30s):  if job still running, force-unload all models from VRAM\n//                       NOTE: unloading models means next job reloads them from disk\nasync function fetchWithRetry(url, opts, retries=5, delayMs=3000, abortRef=null){\n    for (let i = 0; i < retries; i++){\n        // stop retrying if abort was requested\n        if (abortRef && abortRef.aborted) {\n            log(\'    retry aborted (new job starting)\', \'muted\');\n            return null;\n        }\n        try {\n            const r = await fetch(url, opts);\n            return r;\n        } catch(e){\n            if (abortRef && abortRef.aborted) return null;\n            if (i < retries - 1){\n                log(\'    retrying in \' + (delayMs/1000) + \'s... (attempt \' + (i+2) + \'/\' + retries + \')\', \'muted\');\n                await new Promise(r => setTimeout(r, delayMs));\n            } else {\n                throw e;\n            }\n        }\n    }\n}\n\n// shared abort controller for nukeJob — aborted when a new job starts\nlet nukeAbort = null;\n\nasync function nukeJob(pid){\n    const b = comfyBase();\n    const h = {\'Content-Type\':\'application/json\'};\n    nukeAbort = {aborted: false};\n    const myAbort = nukeAbort;\n\n    // ── Step 1: interrupt + clear queue ──────────────────────────────\n    log(\'    Sending interrupt + clearing queue...\', \'muted\');\n    let comfyResponsive = false;\n    try {\n        const ctrl = new AbortController();\n        setTimeout(() => ctrl.abort(), 2000);\n        await fetch(b+\'/interrupt\', {method:\'POST\', signal: ctrl.signal});\n        comfyResponsive = true;\n        if (pid) await fetch(b+\'/queue\', {method:\'POST\', headers:h,\n            body: JSON.stringify({delete:[pid]})});\n        await fetch(b+\'/queue\', {method:\'POST\', headers:h,\n            body: JSON.stringify({clear:true})});\n        log(\'    Interrupt sent, queue cleared.\', \'muted\');\n    } catch(e){\n        comfyResponsive = false;\n        log(\'    ComfyUI not responding to HTTP — going straight to hard kill.\', \'warn\');\n    }\n\n    // ── Step 2: verify nothing is still running (10s polling) ─────────\n    // A CUDA-frozen job can still accept HTTP but never actually stops.\n    // We must confirm queue_running is empty before calling it clean.\n    if (comfyResponsive) {\n        log(\'    Verifying queue is actually clear...\', \'muted\');\n        let confirmed = false;\n        const deadline = performance.now() + 10000;\n        while (performance.now() < deadline) {\n            await new Promise(r => setTimeout(r, 1500));\n            try {\n                const qr = await fetch(b+\'/queue\', {signal: AbortSignal.timeout(2000)});\n                const qd = await qr.json();\n                const running = (qd.queue_running || []).length;\n                if (running === 0) { confirmed = true; break; }\n                log(\'    Still \' + running + \' job(s) running — waiting...\', \'muted\');\n            } catch(e) { break; }\n        }\n        if (confirmed) {\n            log(\'    Queue confirmed empty. ComfyUI ready.\', \'ok\');\n            return;\n        }\n        // queue_running still has jobs — CUDA is stuck despite HTTP working\n        log(\'    Queue not clearing after 10s — CUDA stuck. Escalating to hard kill.\', \'warn\');\n    }\n\n    // ── Step 3: hard kill ─────────────────────────────────────────────\n    log(\'    Hard kill — restarting ComfyUI process...\', \'err\');\n\n    if (!WEDGE_SERVER){\n        log(\'    Auto-restart requires running via wedge_studio.py.\', \'warn\');\n        log(\'    Restart ComfyUI manually — waiting up to 3 min for it to come back...\', \'warn\');\n        await waitForComfy(180000, 4000);\n        return;\n    }\n    const comfyPath = document.getElementById(\'comfyPath\')?.value?.trim() || \'\';\n    if (!comfyPath){\n        log(\'    No ComfyUI folder set — set it in the header and click ✓.\', \'warn\');\n        log(\'    Restart ComfyUI manually — waiting up to 3 min for it to come back...\', \'warn\');\n        await waitForComfy(180000, 4000);\n        return;\n    }\n    try {\n        const rr = await fetch(WEDGE_SERVER+\'/restart_comfy\', {\n            method:\'POST\', headers:h,\n            body: JSON.stringify({comfy_path: comfyPath})\n        });\n        const rd = await rr.json();\n        if (rd.ok){\n            log(\'    Process killed. Waiting for ComfyUI to restart...\', \'warn\');\n            const recovered = await waitForComfy(90000, 3000);\n            if (recovered){ log(\'    ComfyUI back online.\', \'ok\'); }\n            else { log(\'    ComfyUI did not respond after 90s — check manually.\', \'err\'); }\n        } else {\n            log(\'    Kill failed: \' + rd.error, \'err\');\n        }\n    } catch(e){ log(\'    Restart request failed: \' + e.message, \'err\'); }\n}\n\n\nfunction awaitWithProgress(pid, t0, timeoutS){\n    return new Promise(async (resolve) => {\n        const deadline = t0 + timeoutS*1000;\n        let ws = null, done = false;\n        try {\n            ws = new WebSocket(\'ws://\'+server()+\'/ws?clientId=\'+clientId);\n            ws.onmessage = ev => {\n                try {\n                    const d = JSON.parse(ev.data);\n                    if (d.type===\'progress\' && d.data){\n                        const {value=0, max=1} = d.data;\n                        setBar(\'job\', value/Math.max(1,max)*100);\n                        document.getElementById(\'jobPct\').textContent = `${value}/${max}`;\n                    }\n                } catch(e){}\n            };\n            ws.onerror = () => {};\n        } catch(e){ ws = null; }\n\n        const finish = (val) => { if (done) return; done = true; if (ws){ try{ws.close();}catch(e){}} resolve(val); };\n\n        while (!done){\n            if (stopFlag){\n                await nukeJob(pid);\n                return finish(null);\n            }\n            if (performance.now() > deadline){\n                log(\'    TIMEOUT after \' + (timeoutS/60).toFixed(0) + \' min.\', \'err\');\n                log(\'    Probing ComfyUI — soft stop if responsive, hard kill if frozen...\', \'warn\');\n                await nukeJob(pid);\n                return finish(null);\n            }\n            try {\n                const r = await fetch(comfyBase()+`/history/${pid}`);\n                if (r.ok){ const h = await r.json(); if (h[pid]) return finish(h[pid]); }\n            } catch(e){}\n            await sleep(1500);\n        }\n    });\n}\n\nfunction setBar(which, pct){ document.getElementById(which+\'Fill\').style.width = pct + \'%\'; }\n\n// ============ results ============\nfunction viewUrl(out){\n    const p = new URLSearchParams({filename: out.fn, subfolder: out.sub, type: out.type});\n    return base() + \'/view?\' + p.toString();\n}\n// ── result store for lightbox navigation & report export ──\nconst resultStore = [];  // {name, used, status, secs, vidUrl, imgUrl}\nconst _reportPaths = []; // intermediate per-job report paths\nlet _autoReportEnabled = true; // toggled by the Auto-Report checkbox (cleaned up at batch end)\n\n// addResult: called by the runner — creates one card per output file\nfunction addResult(name, res){\n    const used = res.used && res.used!==name ? `${name} \\u2192 ${res.used}` : name;\n    const mediaOuts = (res.outs||[]).filter(o =>\n        /\\.(mp4|webm|mov|gif|png|jpe?g|webp)$/i.test(o.fn));\n\n    if (mediaOuts.length > 0){\n        // one card per output file\n        mediaOuts.forEach((o, i) => {\n            const isVid = /\\.(mp4|webm|mov)$/i.test(o.fn);\n            const isImg = /\\.(png|jpe?g|webp|gif)$/i.test(o.fn);\n            const label = mediaOuts.length > 1 ? `${used} [${i+1}/${mediaOuts.length}]` : used;\n            addResultCard(\n                name, label, res.status, res.secs,\n                isVid ? viewUrl(o) : (res.vidUrl||null),\n                isImg ? viewUrl(o) : (res.imgUrl||null),\n                o  // raw out for report media\n            );\n        });\n    } else {\n        // no outs — fall back to pre-baked URLs (report mode) or show no-preview\n        addResultCard(name, used, res.status, res.secs, res.vidUrl||null, res.imgUrl||null);\n    }\n}\n\nfunction addResultCard(name, used, status, secs, vidUrl, imgUrl, rawOut){\n    const grid = document.getElementById(\'results\');\n    const idx = resultStore.length;\n    resultStore.push({name, used, status, secs, vidUrl, imgUrl, rawOut: rawOut||null});\n\n    const card = document.createElement(\'div\');\n    card.className = \'result-card\';\n    card.dataset.idx = String(idx);\n\n    // thumbnail\n    const thumb = document.createElement(\'div\');\n    thumb.className = \'result-thumb\';\n    if (vidUrl){\n        const vid2 = document.createElement(\'video\');\n        vid2.src = vidUrl + \'#t=0.1\';\n        vid2.preload = \'metadata\';\n        vid2.muted = true;\n        thumb.appendChild(vid2);\n        const play = document.createElement(\'div\');\n        play.className = \'play\';\n        play.textContent = \'\\u25b6\';\n        thumb.appendChild(play);\n    } else if (imgUrl){\n        const im = document.createElement(\'img\');\n        im.src = imgUrl;\n        thumb.appendChild(im);\n    } else {\n        const np = document.createElement(\'span\');\n        np.className = \'no-prev\';\n        np.textContent = \'no preview\';\n        thumb.appendChild(np);\n    }\n    thumb.addEventListener(\'click\', () => lbOpen(idx));\n    card.appendChild(thumb);\n\n    // compare checkbox\n    const cb = document.createElement(\'span\');\n    cb.className = \'compare-cb\';\n    cb.textContent = \'\\u2713\';\n    cb.addEventListener(\'click\', (e) => { e.stopPropagation(); toggleCompare(e, idx); });\n    card.appendChild(cb);\n\n    // meta\n    const sc = {ok:\'ok\',check:\'check\'}[status] || \'fail\';\n    const meta = document.createElement(\'div\');\n    meta.className = \'result-meta\';\n    meta.innerHTML =\n        \'<div class="result-name">\' + escapeHtml(used) + \'</div>\' +\n        \'<div class="result-status \' + sc + \'">\' + status + \' \\u00b7 \' + secs.toFixed(0) + \'s</div>\';\n    card.appendChild(meta);\n\n    grid.appendChild(card);\n    const expBtn = document.getElementById(\'exportReportBtn\');\n    if (expBtn) expBtn.disabled = false;\n    const cBar = document.getElementById(\'compareBar\');\n    if (cBar) cBar.classList.add(\'visible\');\n}\n\n// ── compare selection ──────────────────────────────────────────────────\nconst compareSet = new Set();\nfunction toggleCompare(e, idx){\n    e.stopPropagation();\n    if (compareSet.has(idx)){\n        compareSet.delete(idx);\n    } else {\n        if (compareSet.size >= 2){\n            // deselect oldest\n            const first = compareSet.values().next().value;\n            compareSet.delete(first);\n            document.querySelector(`.result-card[data-idx="${first}"]`)?.classList.remove(\'in-compare\');\n        }\n        compareSet.add(idx);\n    }\n    document.querySelectorAll(\'.result-card\').forEach(c => {\n        c.classList.toggle(\'in-compare\', compareSet.has(Number(c.dataset.idx)));\n    });\n    const n = compareSet.size;\n    const countEl = document.getElementById(\'compareCount\');\n    const btnEl   = document.getElementById(\'compareBtn\');\n    if (countEl) countEl.textContent = n === 0 ? \'0 selected\' : n === 1 ? \'1 selected (pick one more)\' : \'2 selected\';\n    if (btnEl)   btnEl.disabled = n !== 2;\n}\nfunction clearCompare(){\n    compareSet.clear();\n    document.querySelectorAll(\'.result-card\').forEach(c => c.classList.remove(\'in-compare\'));\n    const countEl = document.getElementById(\'compareCount\');\n    const btnEl   = document.getElementById(\'compareBtn\');\n    if (countEl) countEl.textContent = \'0 selected\';\n    if (btnEl)   btnEl.disabled = true;\n    // also clear the results grid and store\n    document.getElementById(\'results\').innerHTML = \'\';\n    resultStore.length = 0;\n}\n\n// ── standard lightbox ──────────────────────────────────────────────────\nlet lbIdx = -1;\nfunction lbOpen(idx){\n    lbIdx = idx; lbRender();\n    const lb = document.getElementById(\'lightbox\');\n    if (lb) lb.classList.add(\'open\');\n}\nfunction lbClose(){\n    document.getElementById(\'lightbox\').classList.remove(\'open\');\n    // pause any playing video\n    document.getElementById(\'lbContent\').querySelectorAll(\'video\').forEach(v => v.pause());\n}\nfunction lbNav(dir){\n    if (!resultStore.length) return;\n    lbIdx = (lbIdx + dir + resultStore.length) % resultStore.length;\n    lbRender();\n}\nfunction lbRender(){\n    const r = resultStore[lbIdx];\n    if (!r) return;\n    const el = document.getElementById(\'lbContent\');\n    if (r.vidUrl){\n        el.innerHTML = `<video src="${r.vidUrl}" controls autoplay muted style="max-width:100%;max-height:calc(100vh - 120px);border-radius:3px;"></video>`;\n    } else if (r.imgUrl){\n        el.innerHTML = `<img src="${r.imgUrl}" style="max-width:100%;max-height:calc(100vh - 120px);border-radius:3px;">`;\n    } else {\n        el.innerHTML = `<div style="color:var(--text-dim);font-size:11px;letter-spacing:.1em;">No media</div>`;\n    }\n    document.getElementById(\'lbMeta\').textContent = `${r.used}  ·  ${r.status}  ·  ${r.secs.toFixed(0)}s`;\n    document.getElementById(\'lbCounter\').textContent = `${lbIdx+1} / ${resultStore.length}`;\n}\n\n// ── keyboard navigation ────────────────────────────────────────────────\ndocument.addEventListener(\'keydown\', e => {\n    if (document.getElementById(\'lightbox\').classList.contains(\'open\')){\n        if (e.key === \'ArrowLeft\')  lbNav(-1);\n        if (e.key === \'ArrowRight\') lbNav(1);\n        if (e.key === \'Escape\')     lbClose();\n    }\n    if (document.getElementById(\'wipeLb\').classList.contains(\'open\')){\n        if (e.key === \'Escape\') wipeClose();\n    }\n});\n\n// ── wipe compare ──────────────────────────────────────────────────────\nfunction openWipe(){\n    const idxs = [...compareSet];\n    if (idxs.length !== 2) return;\n    const [a, b] = idxs.map(i => resultStore[i]);\n    const aEl = document.getElementById(\'wipeA\');\n    const bEl = document.getElementById(\'wipeB\');\n    const mkMedia = (r) => r.vidUrl\n        ? `<video src="${r.vidUrl}" loop muted playsinline style="width:100%;height:100%;object-fit:contain;"></video>`\n        : r.imgUrl\n        ? `<img src="${r.imgUrl}" style="width:100%;height:100%;object-fit:contain;">`\n        : `<div style="color:var(--text-dim);font-size:11px;padding:20px;">No media</div>`;\n    aEl.innerHTML = mkMedia(a);\n    bEl.innerHTML = mkMedia(b);\n    document.getElementById(\'wipeLblA\').textContent = a.used;\n    document.getElementById(\'wipeLblB\').textContent = b.used;\n    // set initial wipe at 50%\n    wipeSetPos(50);\n    document.getElementById(\'wipeLb\').classList.add(\'open\');\n    // size the wrap to the natural video size\n    const wrapEl = document.getElementById(\'wipeWrap\');\n    wrapEl.style.width  = \'calc(100vw - 80px)\';\n    wrapEl.style.height = \'calc(100vh - 160px)\';\n    const playBtn = document.getElementById(\'wipePlayBtn\');\n    if (playBtn) playBtn.textContent = \'⏸ Pause\';\n    setTimeout(() => {\n        const vids = document.querySelectorAll(\'#wipeA video, #wipeB video\');\n        vids.forEach(v => { v.play().catch(()=>{}); });\n        wipeBindSync();\n        scrubInit();\n        wipeUpdatePlayBtn();\n    }, 100);\n}\nfunction wipeClose(){\n    document.getElementById(\'wipeLb\').classList.remove(\'open\');\n    document.querySelectorAll(\'#wipeA video, #wipeB video\').forEach(v => {\n        v.pause(); v.playbackRate = 1;\n    });\n    // reset speed buttons + scrubber state\n    document.querySelectorAll(\'.speed-btn\').forEach(b => b.classList.remove(\'active\'));\n    const b1 = document.getElementById(\'speedBtn1\');\n    if (b1) b1.classList.add(\'active\');\n    scrubDragging = false;\n    scrubTeardown();\n}\nfunction wipeSetPos(pct){\n    document.getElementById(\'wipeA\').style.clipPath = `inset(0 ${100-pct}% 0 0)`;\n    document.getElementById(\'wipeHandle\').style.left = pct + \'%\';\n    // force repaint of paused video frames via requestVideoFrameCallback if available\n    // deliberately NOT nudging currentTime (causes scrubber feedback loop)\n    if (!scrubDragging){\n        document.querySelectorAll(\'#wipeA video, #wipeB video\').forEach(v => {\n            if (v.paused && v.readyState >= 2){\n                if (v.requestVideoFrameCallback){\n                    v.requestVideoFrameCallback(() => {}); // nudge decoder\n                } else {\n                    // minimal canvas trick: draw one frame to force repaint\n                    try {\n                        const c = document.createElement(\'canvas\');\n                        c.width = 2; c.height = 2;\n                        c.getContext(\'2d\').drawImage(v, 0, 0, 2, 2);\n                    } catch(e){}\n                }\n            }\n        });\n    }\n}\n// drag the handle\n(function(){\n    let dragging = false;\n    document.addEventListener(\'mousedown\', e => { if (e.target.id === \'wipeHandle\') dragging = true; });\n    document.addEventListener(\'mouseup\',   () => dragging = false);\n    document.addEventListener(\'mousemove\', e => {\n        if (!dragging) return;\n        const wrap = document.getElementById(\'wipeWrap\');\n        if (!wrap) return;\n        const rect = wrap.getBoundingClientRect();\n        const pct = Math.max(2, Math.min(98, (e.clientX - rect.left) / rect.width * 100));\n        wipeSetPos(pct);\n    });\n    // touch\n    document.addEventListener(\'touchstart\', e => { if (e.target.id === \'wipeHandle\') dragging = true; }, {passive:true});\n    document.addEventListener(\'touchend\',   () => dragging = false);\n    document.addEventListener(\'touchmove\',  e => {\n        if (!dragging) return;\n        const wrap = document.getElementById(\'wipeWrap\');\n        if (!wrap) return;\n        const rect = wrap.getBoundingClientRect();\n        const pct = Math.max(2, Math.min(98, (e.touches[0].clientX - rect.left) / rect.width * 100));\n        wipeSetPos(pct);\n    }, {passive:true});\n})();\n\nfunction wipeBindSync(){\n    const va = document.querySelector(\'#wipeA video\');\n    const vb = document.querySelector(\'#wipeB video\');\n    if (!va || !vb) return;\n    let syncing = false;\n    const sync = (leader, follower) => {\n        if (syncing) return;\n        syncing = true;\n        if (Math.abs(follower.currentTime - leader.currentTime) > 0.05)\n            follower.currentTime = leader.currentTime;\n        if (!leader.paused && follower.paused) follower.play().catch(()=>{});\n        if (leader.paused && !follower.paused) follower.pause();\n        syncing = false;\n    };\n    va.addEventListener(\'timeupdate\', () => sync(va, vb));\n    va.addEventListener(\'play\',  () => { vb.play().catch(()=>{}); wipeUpdatePlayBtn(); });\n    va.addEventListener(\'pause\', () => { vb.pause(); wipeUpdatePlayBtn(); });\n    va.addEventListener(\'seeked\', () => { if (Math.abs(vb.currentTime - va.currentTime) > 0.05) vb.currentTime = va.currentTime; });\n    vb.addEventListener(\'play\',  () => { va.play().catch(()=>{}); wipeUpdatePlayBtn(); });\n    vb.addEventListener(\'pause\', () => { va.pause(); wipeUpdatePlayBtn(); });\n    vb.addEventListener(\'seeked\', () => { if (Math.abs(va.currentTime - vb.currentTime) > 0.05) va.currentTime = vb.currentTime; });\n}\n\n\nfunction wipeTogglePlay(){\n    const vids = [...document.querySelectorAll(\'#wipeA video, #wipeB video\')];\n    if (!vids.length) return;\n    const anyPlaying = vids.some(v => !v.paused);\n    if (anyPlaying){\n        vids.forEach(v => v.pause());\n    } else {\n        vids.forEach(v => v.play().catch(()=>{}));\n    }\n    // button label updated via the play/pause event listeners in wipeBindSync\n}\nfunction wipeUpdatePlayBtn(){\n    const vids = [...document.querySelectorAll(\'#wipeA video, #wipeB video\')];\n    const anyPlaying = vids.some(v => !v.paused);\n    const btn = document.getElementById(\'wipePlayBtn\');\n    if (btn) btn.textContent = anyPlaying ? \'⏸ Pause\' : \'▶ Play\';\n}\nfunction setWipeSpeed(rate){\n    document.querySelectorAll(\'#wipeA video, #wipeB video\').forEach(v => { v.playbackRate = rate; });\n    document.querySelectorAll(\'.speed-btn\').forEach(b => {\n        const btnRate = parseFloat(b.textContent.replace(\'×\',\'\'));\n        b.classList.toggle(\'active\', Math.abs(btnRate - rate) < 0.001);\n    });\n}\n\n// ── frame scrubber ────────────────────────────────────────────────────\nlet scrubDragging = false;\nlet _scrubTeardownFns = [];\nfunction scrubTeardown(){\n    scrubDragging = false;\n    _scrubTeardownFns.forEach(fn => fn());\n    _scrubTeardownFns = [];\n}\n\nfunction scrubUpdate(pct){\n    const va = document.querySelector(\'#wipeA video\');\n    const vb = document.querySelector(\'#wipeB video\');\n    const vid = va || vb;\n    if (!vid || !vid.duration) return;\n    const time = pct / 100 * vid.duration;\n    if (va){ va.currentTime = time; }\n    if (vb){ vb.currentTime = time; }\n    scrubSetPosition(pct, time, vid.duration);\n}\n\nfunction scrubSetPosition(pct, time, duration){\n    const needle = document.getElementById(\'scrubNeedle\');\n    const fill   = document.getElementById(\'scrubFill\');\n    const label  = document.getElementById(\'scrubLabel\');\n    if (!needle) return;\n    needle.style.left = pct + \'%\';\n    if (fill) fill.style.width = pct + \'%\';\n    if (label && duration){\n        // calculate frame number assuming 30fps (best guess without metadata)\n        const fps = wipeDetectedFps || 30;\n        const frame = Math.round(time * fps);\n        const totalFrames = Math.round(duration * fps);\n        label.textContent = \'frame \' + frame + \' / \' + totalFrames;\n    }\n}\n\nfunction scrubFromVideo(){\n    const va = document.querySelector(\'#wipeA video\');\n    const vid = va || document.querySelector(\'#wipeB video\');\n    if (!vid || !vid.duration) return;\n    const pct = vid.currentTime / vid.duration * 100;\n    scrubSetPosition(pct, vid.currentTime, vid.duration);\n}\n\nlet wipeDetectedFps = 30;\nfunction scrubInit(){\n    scrubTeardown(); // remove any previous listeners before re-attaching\n    const fpsEl = document.getElementById(\'scrubFps\');\n    if (fpsEl) wipeDetectedFps = parseInt(fpsEl.value) || 30;\n    setWipeSpeed(1);\n    const track = document.getElementById(\'scrubTrack\');\n    if (!track) return;\n    const va = document.querySelector(\'#wipeA video\');\n    if (va){\n        const _onTU = scrubFromVideo;\n        const _onMeta = () => {\n            const s = document.getElementById(\'wipeScrubber\');\n            if (s) s.style.opacity = \'1\';\n            scrubFromVideo();\n        };\n        va.addEventListener(\'timeupdate\', _onTU);\n        va.addEventListener(\'loadedmetadata\', _onMeta);\n        _scrubTeardownFns.push(() => {\n            va.removeEventListener(\'timeupdate\', _onTU);\n            va.removeEventListener(\'loadedmetadata\', _onMeta);\n        });\n    }\n\n    const getScrubPct = (e) => {\n        const rect = track.getBoundingClientRect();\n        const x = (e.touches ? e.touches[0].clientX : e.clientX);\n        return Math.max(0, Math.min(100, (x - rect.left) / rect.width * 100));\n    };\n\n    const _onDown  = e => { scrubDragging = true; document.querySelectorAll(\'#wipeA video, #wipeB video\').forEach(v => v.pause()); scrubUpdate(getScrubPct(e)); };\n    const _onMove  = e => { if (scrubDragging) scrubUpdate(getScrubPct(e)); };\n    const _onUp    = ()  => { scrubDragging = false; };\n    const _onTDown = e => { scrubDragging = true; scrubUpdate(getScrubPct(e)); };\n    const _onTMove = e => { if (scrubDragging) scrubUpdate(getScrubPct(e)); };\n    const _onTEnd  = ()  => { scrubDragging = false; };\n\n    track.addEventListener(\'mousedown\', _onDown);\n    document.addEventListener(\'mousemove\', _onMove);\n    document.addEventListener(\'mouseup\', _onUp);\n    track.addEventListener(\'touchstart\', _onTDown, {passive:true});\n    document.addEventListener(\'touchmove\', _onTMove, {passive:true});\n    document.addEventListener(\'touchend\', _onTEnd);\n\n    _scrubTeardownFns.push(() => {\n        track.removeEventListener(\'mousedown\', _onDown);\n        document.removeEventListener(\'mousemove\', _onMove);\n        document.removeEventListener(\'mouseup\', _onUp);\n        track.removeEventListener(\'touchstart\', _onTDown);\n        document.removeEventListener(\'touchmove\', _onTMove);\n        document.removeEventListener(\'touchend\', _onTEnd);\n    });\n}\n\n// ── export standalone report ──────────────────────────────────────────────\nfunction _exportUnitParams(){\n    const out = [];\n    order.forEach(function(u){\n        if (!u){ return; }\n        if (u.type === \'chain\'){\n            // Expand chain: one PG_PARAMS entry per node, individually selectable\n            (u.names || []).forEach(function(nm, ni){\n                const wf = (workflows[nm]||{}).wf;\n                if (!wf){ out.push(null); return; }\n                const _ovr = ((u.nodes||[])[ni]||{}).paramOverrides || {};\n                const map = {};\n                Object.keys(wf).forEach(function(nid){\n                    const node = wf[nid]; if (!node || !node.class_type) return;\n                    Object.keys(node.inputs||{}).forEach(function(inp){\n                        let v = node.inputs[inp];\n                        if (Array.isArray(v)) return;\n                        let ov = false;\n                        const okey = nid + \'.\' + inp;\n                        if (Object.prototype.hasOwnProperty.call(_ovr, okey)){ v = _ovr[okey]; ov = true; }\n                        if (typeof v === \'string\' && v.length > 120) v = v.slice(0,117) + \'...\';\n                        const col = node.class_type + \'.\' + inp;\n                        if (!map[col]) map[col] = [];\n                        map[col].push({v: v, ov: ov});\n                    });\n                });\n                out.push({label: \'\u26d3\u00a0\' + nm, name: nm, params: map});\n            });\n            return;\n        }\n        if (u.type !== \'single\'){ return; }\n        const wf = (workflows[u.name]||{}).wf;\n        if (!wf){ out.push(null); return; }\n        const map = {};\n        Object.keys(wf).forEach(function(nid){\n            const node = wf[nid]; if (!node || !node.class_type) return;\n            Object.keys(node.inputs||{}).forEach(function(inp){\n                let v = node.inputs[inp];\n                if (Array.isArray(v)) return;\n                let ov = false;\n                const okey = nid + \'.\' + inp;\n                if (u.paramOverrides && Object.prototype.hasOwnProperty.call(u.paramOverrides, okey)){ v = u.paramOverrides[okey]; ov = true; }\n                if (typeof v === \'string\' && v.length > 120) v = v.slice(0,117) + \'...\';\n                const col = node.class_type + \'.\' + inp;\n                if (!map[col]) map[col] = [];\n                map[col].push({v: v, ov: ov});\n            });\n        });\n        out.push({label: u.label || u.name, name: u.name, params: map});\n    });\n    return out;\n}\n\nfunction exportReport(silent=false){\n    if (!resultStore.length){\n        if (!silent) alert(\'No results yet \\u2014 run a batch first.\');\n        return;\n    }\n    if (!WEDGE_SERVER || !serverFolder){\n        log(\'No server \\u2014 report requires wedge_studio to be running.\', \'warn\');\n        return;\n    }\n    const stamp = new Date().toISOString();\n    const logLines = [...(document.getElementById(\'terminal-body\').querySelectorAll(\'.tlog-line\'))]\n        .map(d => d.innerText || d.textContent).join(\'\\n\');\n    const savePath = serverFolder.replace(/\\\\/g, \'/\').replace(/\\/$/, \'\')\n        + \'/wedge_report_\' + stamp.replace(/[:.]/g, \'-\').slice(0,19) + \'.html\';\n    const payload = {\n        path: savePath, stamp,\n        server:  document.getElementById(\'server\').value.trim() || \'127.0.0.1:8188\',\n        order:   JSON.parse(JSON.stringify(order)),\n        unitParams: _exportUnitParams(),\n        results: resultStore.map(r => ({\n            name: r.name, used: r.used, status: r.status, secs: r.secs,\n            rawOut: r.rawOut || null,\n        })),\n        logLines,\n    };\n    fetch(WEDGE_SERVER + \'/generate_report\', {\n        method: \'POST\', headers: {\'Content-Type\':\'application/json\'},\n        body: JSON.stringify(payload),\n    }).then(r => r.json()).then(d => {\n        if (d.ok){\n            if (!silent) log(\'Report saved: \' + d.path, \'ok\');\n            else { log(\'\\u2713 report \\u2014 \' + (d.path||\'\').split(/[\\\\\\/]/).pop(), \'muted\'); if (d.path) _reportPaths.push(d.path); }\n        } else {\n            log(\'Report error: \' + (d.error||\'?\'), \'warn\');\n        }\n    }).catch(e => log(\'Report failed: \' + e.message, \'warn\'));\n}\n\n\nfunction browserDownload(reportHtml, filename){\n    // Try 1: Blob URL\n    try {\n        const blob = new Blob([reportHtml], {type:\'text/html;charset=utf-8\'});\n        const url = URL.createObjectURL(blob);\n        const a = document.createElement(\'a\');\n        a.href = url; a.download = filename;\n        document.body.appendChild(a); a.click();\n        setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 3000);\n        if (!silent) log(\'Report downloaded: \' + filename, \'ok\');\n        return;\n    } catch(e1) { console.warn(\'Blob download failed:\', e1); }\n    // Try 2: data URI\n    try {\n        const a = document.createElement(\'a\');\n        a.href = \'data:text/html;charset=utf-8,\' + encodeURIComponent(reportHtml);\n        a.download = filename;\n        document.body.appendChild(a); a.click();\n        setTimeout(() => a.remove(), 1000);\n        log(\'Report downloaded (data URI): \' + filename, \'ok\');\n        return;\n    } catch(e2) { console.warn(\'Data URI failed:\', e2); }\n    // Try 3: new window\n    try {\n        const win = window.open(\'\', \'_blank\');\n        if (win){ win.document.open(); win.document.write(reportHtml); win.document.close();\n            log(\'Report opened in new tab -- Ctrl+S to save\', \'warn\'); return; }\n    } catch(e3) { console.warn(\'New window failed:\', e3); }\n    log(\'Download blocked -- check browser settings\', \'err\');\n}\n\nfunction playVideo(el, url){\n    el.innerHTML = `<video src="${url}" controls autoplay muted style="width:100%;height:100%;object-fit:contain;background:#000"></video>`;\n}\n\n// ============ load baked plan if present ============\nfunction loadBakedPlan(){\n    // report mode: restore results from baked data\n        // load baked plan (download mode)\n    if (!BAKED_PLAN) return;\n    try {\n        order = BAKED_PLAN.order || [];\n        if (BAKED_PLAN.server) document.getElementById(\'server\').value = BAKED_PLAN.server;\n        if (BAKED_PLAN.timeout) document.getElementById(\'timeout\').value = BAKED_PLAN.timeout;\n        for (const [name, wf] of Object.entries(BAKED_PLAN.workflows || {})){\n            workflows[name] = {wf, validApi: true};\n        }\n        log(`Loaded baked plan: ${order.length} unit(s), ${Object.keys(BAKED_PLAN.workflows||{}).length} workflow(s).`, \'header-line\');\n        renderAvail(); renderOrder(); renderGraph();\n    } catch(e){ log(\'Could not parse baked plan: \' + e.message, \'err\'); }\n}\n\n// init\n// load saved config (comfy path etc) from server\nif (WEDGE_SERVER) {\n    // show the comfyPath config field immediately\n    const cpCfg = document.getElementById(\'comfyPathCfg\');\n    if (cpCfg) cpCfg.style.display = \'flex\';\n    // load saved config\n    fetch(WEDGE_SERVER+\'/get_config\').then(r=>r.json()).then(d=>{\n        if (d.ok){\n            if (d.comfy_path){\n                const el = document.getElementById(\'comfyPath\');\n                if (el) el.value = d.comfy_path;\n            }\n            if (d.timeout !== undefined){\n                const tEl = document.getElementById(\'timeout\');\n                if (tEl) tEl.value = d.timeout;\n            }\n            if (d.order && d.order.length){\n                _pendingSavedOrder = d.order;\n                applyPendingSavedOrder(); // applies immediately if workflows already loaded\n            }\n            if (d.comfy_path)\n                log(\'Config loaded — ComfyUI: \' + d.comfy_path, \'muted\');\n            else\n                log(\'ComfyUI folder not set — enter path in header and click ✓ to enable auto-restart.\', \'warn\');\n        } else {\n            log(\'ComfyUI folder not set — enter path in header and click ✓ to enable auto-restart.\', \'warn\');\n        }\n    }).catch(e => {\n        log(\'Could not load config: \' + e.message, \'warn\');\n    });\n}\n\n// ── folder browser ───────────────────────────────────────────────────\nlet fbCurrentPath = \'\';\n\nasync function openFolderBrowser(){\n    if (!WEDGE_SERVER){ alert(\'Folder browser requires running via wedge_studio.py\'); return; }\n    const startPath = document.getElementById(\'folderPathInput\').value.trim() || \'.\';\n    document.getElementById(\'folderBrowser\').classList.add(\'open\');\n    await fbNavigate(startPath);\n}\nfunction closeFolderBrowser(){\n    document.getElementById(\'folderBrowser\').classList.remove(\'open\');\n}\nasync function fbNavigate(path){\n    try {\n        const r = await fetch(WEDGE_SERVER + \'/browse?folder=\' + encodeURIComponent(path));\n        const d = await r.json();\n        if (!d.ok){ log(\'Browse error: \' + d.error, \'err\'); return; }\n        fbCurrentPath = d.current;\n\n        // breadcrumb\n        const bc = document.getElementById(\'fbBreadcrumb\');\n        bc.innerHTML = \'\';\n        d.parents.forEach((p, i) => {\n            const span = document.createElement(\'span\');\n            span.className = \'fb-crumb\' + (i === d.parents.length - 1 ? \' current\' : \'\');\n            // show only the name part for readability, except the root\n            span.textContent = i === 0 ? p.name : p.name.split(/[/\\\\]/).pop() || p.name;\n            span.title = p.path;\n            if (i < d.parents.length - 1) span.addEventListener(\'click\', () => fbNavigate(p.path));\n            bc.appendChild(span);\n            if (i < d.parents.length - 1){\n                const sep = document.createElement(\'span\');\n                sep.className = \'fb-sep\'; sep.textContent = \'›\';\n                bc.appendChild(sep);\n            }\n        });\n\n        // list\n        const list = document.getElementById(\'fbList\');\n        list.innerHTML = \'\';\n        if (!d.subdirs.length){\n            const empty = document.createElement(\'div\');\n            empty.style.cssText = \'padding:16px 18px;font-size:10px;color:var(--text-dim);\';\n            empty.textContent = \'No subfolders here.\';\n            list.appendChild(empty);\n        }\n        d.subdirs.forEach(sub => {\n            const item = document.createElement(\'div\');\n            item.className = \'fb-item\';\n            item.innerHTML = \'<span class="fb-ico">&#128193;</span><span>\' + escapeHtml(sub.name) + \'</span>\';\n            item.addEventListener(\'click\', () => fbNavigate(sub.path));\n            list.appendChild(item);\n        });\n\n        // footer\n        document.getElementById(\'fbCurrentPath\').textContent = d.current;\n        const cnt = d.json_count;\n        document.getElementById(\'fbJsonCount\').textContent =\n            cnt === 0 ? \'no .json files\' : cnt + \' workflow\' + (cnt===1?\'\':\'s\') + \' found\';\n        document.getElementById(\'fbSelectBtn\').disabled = cnt === 0;\n    } catch(e){ log(\'Browse error: \' + e.message, \'err\'); }\n}\nfunction selectFolderFromBrowser(){\n    if (!fbCurrentPath) return;\n    document.getElementById(\'folderPathInput\').value = fbCurrentPath;\n    closeFolderBrowser();\n    loadFromServer();\n}\n\nfunction saveComfyPath(){\n    const path = document.getElementById(\'comfyPath\')?.value?.trim();\n    if (!path){ log(\'Enter a ComfyUI folder path first.\',\'warn\'); return; }\n    if (!WEDGE_SERVER){ log(\'Save requires running via wedge_studio.py\',\'warn\'); return; }\n    const tEl = document.getElementById(\'timeout\');\n    const payload = {\n        comfy_path: path,\n        timeout:    parseFloat(tEl?.value) || 20,\n        order:      JSON.parse(JSON.stringify(order))\n    };\n    fetch(WEDGE_SERVER+\'/save_config\', {method:\'POST\',\n        headers:{\'Content-Type\':\'application/json\'},\n        body: JSON.stringify(payload)\n    }).then(r=>r.json()).then(d=>{\n        if (d.ok){ log(\'\\u2713 Config saved: ComfyUI path, timeout (\' + (tEl?.value||20) + \' min), order (\' + order.length + \' unit(s)).\',\'ok\'); }\n        else { log(\'Save failed: \'+d.error,\'err\'); }\n    }).catch(e=>{ log(\'Could not save config: \'+e.message,\'warn\'); });\n}\n\nloadBakedPlan();\nrenderOrder();\ncheckComfy();\n// if running from wedge_studio.py server, show the path input\nif (WEDGE_SERVER) {\n    document.getElementById(\'serverFolderRow\').style.display = \'block\';\n    document.getElementById(\'dropzone\').style.display = \'none\';\n    // set default folder to server\'s working directory\n    fetch(WEDGE_SERVER + \'/list_workflows?folder=.\')\n        .then(r => r.json())\n        .then(d => {\n            if (d.ok) {\n                serverFolder = d.folder;\n                document.getElementById(\'folderPathInput\').value = d.folder;\n                autoLoadFromServer(d.folder, d.files);\n            }\n        }).catch(() => {});\n}\n\nasync function loadFromServer(){\n    const path = document.getElementById(\'folderPathInput\').value.trim();\n    if (!path) return;\n    try {\n        const r = await fetch(WEDGE_SERVER + \'/list_workflows?folder=\' + encodeURIComponent(path));\n        const d = await r.json();\n        if (!d.ok){ log(\'Cannot read folder: \' + d.error, \'err\'); return; }\n        serverFolder = d.folder;\n        document.getElementById(\'folderPathInput\').value = d.folder;\n        autoLoadFromServer(d.folder, d.files);\n    } catch(e){ log(\'Server error: \' + e.message, \'err\'); }\n}\n\n// Apply saved order from config once workflows are loaded\n// Called both from get_config (in case workflows already loaded) and from\n// autoLoadFromServer (after workflows are loaded).  Filters out any unit\n// names that weren\'t found on disk.\nfunction _rehydratePCfgFromOrder(){\n    for (var i=0;i<order.length;i++){\n        var u=order[i];\n        if(!u||u.type!==\'single\'||!u.paramOverrides)continue;\n        var keys=Object.keys(u.paramOverrides);\n        if(!keys.length)continue;\n        var nm=u.name;\n        if(!_pCfg[nm])_pCfg[nm]={promoted:new Set(),variants:[]};\n        var c=_pCfg[nm];\n        keys.forEach(function(k){c.promoted.add(k);});\n        var lbl=\'v\'+(c.variants.length+1);\n        if(typeof u.label===\'string\'){\n            var m=u.label.match(/\\[([^\\]]+)\\]\\s*$/);\n            if(m)lbl=m[1];\n        }\n        if(!c.variants.some(function(v){return v.label===lbl;})){\n            c.variants.push({label:lbl,overrides:Object.assign({},u.paramOverrides)});\n        }\n    }\n}\n\nfunction applyPendingSavedOrder(){\n    if (!_pendingSavedOrder || !Object.keys(workflows).length) return;\n    const saved = _pendingSavedOrder;\n    _pendingSavedOrder = null;\n    const loaded = new Set(Object.keys(workflows));\n    const filtered = [];\n    for (const u of saved){\n        if (u.type === \'single\'){\n            if (loaded.has(u.name)) filtered.push(u);\n        } else {\n            const names = u.names.filter(n => loaded.has(n));\n            if (names.length >= 2) filtered.push({...u, names});\n            else if (names.length === 1) filtered.push({type:\'single\', name:names[0]});\n        }\n    }\n    if (filtered.length){\n        order = filtered;\n        _rehydratePCfgFromOrder();\n        renderOrder(); renderGraph(); updateRunButton();\n        log(\'\\u2713 Run order restored from _wedge_config.json (\' + filtered.length + \' unit(s)).\', \'muted\');\n    }\n}\n\nasync function autoLoadFromServer(folder, files){\n    if (!files.length){ log(\'No .json files found in \' + folder, \'warn\'); return; }\n    // fetch all workflow contents in one POST\n    const r = await fetch(WEDGE_SERVER + \'/read_workflows\', {\n        method: \'POST\',\n        headers: {\'Content-Type\':\'application/json\'},\n        body: JSON.stringify({folder, files})\n    });\n    const d = await r.json();\n    workflows = {}; order = []; chainSel = []; selUnit = null;\n    let okN = 0, badN = 0;\n    for (const [fname, res] of Object.entries(d.workflows)){\n        const name = fname.replace(/\\.json$/i, \'\');\n        if (res.ok){\n            try {\n                const wf = JSON.parse(res.content);\n                if (isApiFormat(wf)){ workflows[name] = {wf, validApi:true}; order.push({type:\'single\',name}); okN++; }\n                else { workflows[name] = {wf:null, validApi:false}; badN++; }\n            } catch(e){ workflows[name] = {wf:null, validApi:false}; badN++; }\n        } else { badN++; }\n    }\n    folderName = folder.split(/[\\/\\\\]/).filter(Boolean).pop() || \'wedge\';\n    if (okN) log(\'Loaded \' + okN + \' workflow(s) from \' + folder, \'muted\');\n    if (badN) log(badN + \' file(s) skipped (not API format)\', \'warn\');\n    renderAvail(); renderOrder(); renderGraph(); updateRunButton();\n    applyPendingSavedOrder(); // restore saved order if config arrived before/after workflows\n}\n/* ── param promotion ── */\nfunction _ppCfg(name){if(!_pCfg[name])_pCfg[name]={promoted:new Set(),variants:[]};return _pCfg[name];}\nfunction _ppDef(wfName,key){var wf=(workflows[wfName]||{}).wf;if(!wf)return 0;var p=key.split(\'.\');var n=wf[p[0]];return(n&&n.inputs)?n.inputs[p[1]]:0;}\n\nfunction _ppExtractParams(wfName){\n  var wf=(workflows[wfName]||{}).wf;if(!wf)return[];var out=[];\n  Object.keys(wf).forEach(function(nid){var node=wf[nid];if(!node||!node.class_type)return;Object.keys(node.inputs||{}).forEach(function(inp){var val=node.inputs[inp];if(Array.isArray(val))return;out.push({key:nid+\'.\'+inp,nid:nid,inp:inp,cls:node.class_type,def:val,vt:typeof val});});});\n  out.sort(function(a,b){return a.cls<b.cls?-1:a.cls>b.cls?1:a.inp<b.inp?-1:a.inp>b.inp?1:0;});\n  return out;\n}\n\nfunction openParamPanel(wfName){\n  _ppChainUnit=null; _ppChainNodeIdx=-1;\n  _ppWf=wfName;document.getElementById(\'ppTitle\').textContent=wfName+\' \\u2014 Promote Parameters\';\n  document.getElementById(\'ppSearch\').value=\'\';document.getElementById(\'ppSheetWrap\').classList.add(\'open\');\n  var _vh=document.getElementById(\'ppVarHdr\');if(_vh)_vh.style.display=\'\';\n  var _fn=document.getElementById(\'ppFootNormal\');if(_fn)_fn.style.display=\'\';\n  var _fc=document.getElementById(\'ppFootChain\');if(_fc)_fc.style.display=\'none\';\n  ppRenderParams(\'\');ppRenderVariants();\n}\nfunction closeParamPanel(){\n  document.getElementById(\'ppSheetWrap\').classList.remove(\'open\');\n  _ppWf=null; _ppChainUnit=null; _ppChainNodeIdx=-1;\n}\nfunction openChainNodePanel(unitRef, ni){\n  _ppChainUnit=unitRef; _ppChainNodeIdx=ni;\n  var nm=unitRef.names[ni];\n  if(!unitRef.nodes)unitRef.nodes=[];\n  if(!unitRef.nodes[ni])unitRef.nodes[ni]={};\n  if(!unitRef.nodes[ni].paramOverrides)unitRef.nodes[ni].paramOverrides={};\n  _ppWf=nm;\n  document.getElementById(\'ppTitle\').textContent=\'⛓\\u00a0\'+nm+\' \\u2014 Chain Overrides\';\n  document.getElementById(\'ppSearch\').value=\'\';\n  document.getElementById(\'ppSheetWrap\').classList.add(\'open\');\n  var _vh=document.getElementById(\'ppVarHdr\');if(_vh)_vh.style.display=\'none\';\n  document.getElementById(\'ppVarList\').innerHTML=\'\';\n  document.getElementById(\'ppVarCnt\').textContent=\'\';\n  var _fn=document.getElementById(\'ppFootNormal\');if(_fn)_fn.style.display=\'none\';\n  var _fc=document.getElementById(\'ppFootChain\');if(_fc)_fc.style.display=\'flex\';\n  ppRenderParams(\'\');\n}\n\nfunction ppRenderParams(q){\n  var el=document.getElementById(\'ppParamList\');if(!el||!_ppWf)return;\n  var ps=_ppExtractParams(_ppWf),ql=(q||\'\').toLowerCase();\n  el.innerHTML=\'\';var grp={};\n  ps.forEach(function(p){if(ql&&p.key.toLowerCase().indexOf(ql)<0&&p.cls.toLowerCase().indexOf(ql)<0)return;if(!grp[p.cls])grp[p.cls]=[];grp[p.cls].push(p);});\n  if(_ppChainUnit!==null){\n    var node=(_ppChainUnit.nodes||[])[_ppChainNodeIdx]||{};\n    if(!node.paramOverrides)node.paramOverrides={};\n    var ovr=node.paramOverrides;\n    Object.keys(grp).sort().forEach(function(cls){\n      var gl=document.createElement(\'div\');gl.className=\'pp-grp-lbl\';gl.textContent=cls;el.appendChild(gl);\n      grp[cls].forEach(function(p){\n        var row=document.createElement(\'div\');row.className=\'pp-param\';row.style.gap=\'6px\';\n        var isOn=Object.prototype.hasOwnProperty.call(ovr,p.key);\n        var cb=document.createElement(\'input\');cb.type=\'checkbox\';cb.checked=isOn;\n        var nm=document.createElement(\'span\');nm.className=\'pp-pname\';nm.textContent=p.inp;\n        var ty=document.createElement(\'span\');ty.className=\'pp-pty\';ty.textContent=p.vt===\'number\'?(Number.isInteger(p.def)?\'int\':\'float\'):\'str\';\n        var vinp=document.createElement(\'input\');vinp.className=\'pp-param-inp\';\n        vinp.style.cssText=\'flex:1;max-width:130px;display:\'+(isOn?\'block\':\'none\');\n        var curVal=isOn?ovr[p.key]:p.def;\n        vinp.value=String(curVal!==undefined?curVal:\'\');\n        vinp.type=typeof curVal===\'number\'?\'number\':\'text\';if(vinp.type===\'number\')vinp.step=\'any\';\n        vinp.addEventListener(\'input\',function(){var n=parseFloat(vinp.value);ovr[p.key]=isNaN(n)?vinp.value:n;});\n        cb.addEventListener(\'change\',function(){\n          if(cb.checked){var n=parseFloat(vinp.value);ovr[p.key]=isNaN(n)?vinp.value:n;vinp.style.display=\'block\';}\n          else{delete ovr[p.key];vinp.style.display=\'none\';}\n          document.querySelectorAll(\'.gnode .unit-gear\').forEach(function(gb){\n            if(gb.title===\'Overrides \\u00b7 \'+_ppWf)gb.classList.toggle(\'cfg\',Object.keys(ovr).length>0);\n          });\n        });\n        row.addEventListener(\'click\',function(e){if(e.target===cb||e.target===vinp)return;cb.checked=!cb.checked;cb.dispatchEvent(new Event(\'change\'));});\n        row.appendChild(cb);row.appendChild(nm);row.appendChild(ty);row.appendChild(vinp);el.appendChild(row);\n      });\n    });\n  } else {\n    var c=_ppCfg(_ppWf);\n    Object.keys(grp).sort().forEach(function(cls){\n      var gl=document.createElement(\'div\');gl.className=\'pp-grp-lbl\';gl.textContent=cls;el.appendChild(gl);\n      grp[cls].forEach(function(p){\n        var row=document.createElement(\'div\');row.className=\'pp-param\';\n        var cb=document.createElement(\'input\');cb.type=\'checkbox\';cb.checked=c.promoted.has(p.key);\n        var nm=document.createElement(\'span\');nm.className=\'pp-pname\';nm.textContent=p.inp;\n        var vl=document.createElement(\'span\');vl.className=\'pp-pval\';vl.textContent=String(p.def).slice(0,20);vl.title=String(p.def);\n        var ty=document.createElement(\'span\');ty.className=\'pp-pty\';ty.textContent=p.vt===\'number\'?(Number.isInteger(p.def)?\'int\':\'float\'):\'str\';\n        row.appendChild(cb);row.appendChild(nm);row.appendChild(vl);row.appendChild(ty);\n        cb.addEventListener(\'change\',function(){\n          if(cb.checked){c.promoted.add(p.key);c.variants.forEach(function(v){if(!v.overrides.hasOwnProperty(p.key))v.overrides[p.key]=p.def;});}else{c.promoted.delete(p.key);}\n          ppRenderVariants();\n        });\n        row.addEventListener(\'click\',function(e){if(e.target===cb)return;cb.checked=!cb.checked;cb.dispatchEvent(new Event(\'change\'));});\n        el.appendChild(row);\n      });\n    });\n  }\n}\n\nfunction ppRenderVariants(){\n  if(_ppChainUnit!==null)return;\n  var el=document.getElementById(\'ppVarList\'),cnt=document.getElementById(\'ppVarCnt\');if(!el||!_ppWf)return;\n  var c=_ppCfg(_ppWf),promo=Array.from(c.promoted);\n  if(cnt)cnt.textContent=c.variants.length+\' variant\'+(c.variants.length===1?\'\':\'s\');\n  el.innerHTML=\'\';\n  if(!promo.length){el.innerHTML=\'<div class="pp-no-promo">Check parameters above to create columns.</div>\';return;}\n  c.variants.forEach(function(v,ri){\n    var card=document.createElement(\'div\');card.className=\'pp-var-card\';\n    /* label row */\n    var lblRow=document.createElement(\'div\');lblRow.className=\'pp-var-lbl-row\';\n    var lblInp=document.createElement(\'input\');lblInp.className=\'pp-var-lbl-inp\';lblInp.value=v.label;lblInp.placeholder=\'Label\';\n    lblInp.addEventListener(\'input\',function(){v.label=lblInp.value;if(cnt)cnt.textContent=c.variants.length+\' variant\'+(c.variants.length===1?\'\':\'s\');});\n    var delBtn=document.createElement(\'button\');delBtn.className=\'pp-var-del\';delBtn.textContent=\'\\u00d7\';delBtn.title=\'Remove variant\';\n    delBtn.addEventListener(\'click\',(function(i){return function(){c.variants.splice(i,1);ppRenderVariants();};})(ri));\n    lblRow.appendChild(lblInp);lblRow.appendChild(delBtn);card.appendChild(lblRow);\n    /* one row per promoted param */\n    promo.forEach(function(key){\n      var pRow=document.createElement(\'div\');pRow.className=\'pp-param-row\';\n      var klbl=document.createElement(\'span\');klbl.className=\'pp-param-key\';klbl.textContent=key.split(\'.\')[1];\n      var cur=v.overrides.hasOwnProperty(key)?v.overrides[key]:_ppDef(_ppWf,key);\n      var inp=document.createElement(\'input\');inp.className=\'pp-param-inp\';inp.value=String(cur!==undefined?cur:\'\');\n      inp.type=typeof cur===\'number\'?\'number\':\'text\';if(inp.type===\'number\')inp.step=\'any\';\n      inp.addEventListener(\'input\',function(){var n=parseFloat(inp.value);v.overrides[key]=isNaN(n)?inp.value:n;});\n      pRow.appendChild(klbl);pRow.appendChild(inp);card.appendChild(pRow);\n    });\n    el.appendChild(card);\n  });\n}\n\nfunction ppAddRow(){\n  if(!_ppWf)return;var c=_ppCfg(_ppWf);var ov={};c.promoted.forEach(function(k){ov[k]=_ppDef(_ppWf,k);});\n  var maxN=0;\n  c.variants.forEach(function(v){var m=(v.label||\'\').match(/^v(\\d+)$/);if(m){var n=parseInt(m[1],10);if(n>maxN)maxN=n;}});\n  order.forEach(function(u){if(!u||u.type!==\'single\'||u.name!==_ppWf||typeof u.label!==\'string\')return;var m=u.label.match(/\\[v(\\d+)\\]\\s*$/);if(m){var n=parseInt(m[1],10);if(n>maxN)maxN=n;}});\n  c.variants.push({label:\'v\'+(maxN+1),overrides:ov});ppRenderVariants();\n}\n\nfunction ppAddAllToOrder(){\n  if(!_ppWf)return;var c=_ppCfg(_ppWf);\n  if(!c.variants.length){ log(\'No variants to add — create a variant first.\',\'warn\'); return; }\n  c.variants.forEach(function(v){order.push({type:\'single\',name:_ppWf,label:_ppWf+\' [\'+v.label+\']\',paramOverrides:Object.assign({},v.overrides)});});\n  closeParamPanel(); renderOrder(); renderGraph(); updateRunButton();\n  log(\'Added \'+c.variants.length+\' variant(s) for \\\'\'+_ppWf+\'\\\' to run order.\');\n  renderAvail();\n}\n\nfunction saveOrderConfig(){\n    if(!WEDGE_SERVER){ log(\'Not connected\',\'warn\'); return; }\n    const el=document.getElementById(\'comfyPath\');\n    const cfg={timeout:parseFloat(document.getElementById(\'timeout\').value)||20,order:JSON.parse(JSON.stringify(order))};\n    if(el&&el.value.trim()) cfg.comfy_path=el.value.trim();\n    fetch(WEDGE_SERVER+\'/save_config\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(cfg)}).catch(()=>{});\n    log(\'✓ Config saved\',\'muted\');\n}\n\n</script>\n\n<!-- ── bottom log terminal ── -->\n<div id="terminal" class="collapsed">\n    <div id="terminal-bar">\n        <div id="terminal-bar-left">\n            <span id="terminal-dot"></span>\n            <span id="terminal-label">Log</span>\n        </div>\n        <div id="terminal-actions">\n            <button class="btn btn-sm" onclick="event.stopPropagation();clearTerminal()">Clear</button>\n            <button class="btn btn-sm" onclick="event.stopPropagation();toggleTerminal()">✕</button>\n        </div>\n    </div>\n    <div id="terminal-body"></div>\n</div>\n\n<!-- Param Promote Sheet -->\n<div class="pp-sheet-wrap" id="ppSheetWrap">\n  <div class="pp-overlay" onclick="closeParamPanel()"></div>\n  <div class="pp-sheet">\n    <div class="pp-head">\n      <span class="pp-wf-title" id="ppTitle">&#x2014;</span>\n      <button class="btn btn-sm" onclick="closeParamPanel()">&#x2715;</button>\n    </div>\n    <div class="pp-scroll" id="ppScroll">\n      <input class="pp-search" id="ppSearch" placeholder="Search parameters&hellip;" oninput="ppRenderParams(this.value)">\n      <div id="ppParamList"></div>\n      <div class="pp-var-hdr" id="ppVarHdr">\n        <span>Variants</span>\n        <span id="ppVarCnt" style="color:var(--accent-gold);font-size:9px"></span>\n      </div>\n      <div id="ppVarList"></div>\n    </div>\n    <div class="pp-foot" id="ppFootNormal">\n      <button class="btn btn-sm" onclick="ppAddRow()">+ Variant</button>\n      <button class="btn btn-sm btn-primary" onclick="ppAddAllToOrder()">Add to Run Order</button>\n    </div>\n    <div class="pp-foot" id="ppFootChain" style="display:none;">\n      <span style="font-size:9px;color:var(--text-dim);letter-spacing:.08em;flex:1;">Checked · overrides active · close when done</span>\n      <button class="btn btn-sm btn-primary" onclick="closeParamPanel()">Done</button>\n    </div>\n  </div>\n</div>\n</body>\n</html>\n'
# ── auto-detect ComfyUI installation path ────────────────────────────────────
def _detect_comfy_path():
    """Try to find ComfyUI root folder by inspecting running processes."""
    try:
        import psutil
        our_pid = os.getpid()
        for proc in psutil.process_iter(['pid','cmdline','cwd']):
            try:
                if proc.pid == our_pid: continue
                cmd = ' '.join(proc.info['cmdline'] or [])
                cwd = proc.info.get('cwd') or ''
                if 'main.py' in cmd and ('comfyui' in cmd.lower() or 'comfyui' in cwd.lower()):
                    if cwd and os.path.exists(os.path.join(cwd, 'main.py')):
                        return cwd
                    for part in (proc.info['cmdline'] or []):
                        if part.endswith('main.py'):
                            d = os.path.dirname(os.path.abspath(part))
                            if os.path.exists(os.path.join(d, 'main.py')):
                                return d
            except Exception: pass
    except ImportError: pass
    for p in [r'D:\ComfyUI', r'C:\ComfyUI',
              os.path.expanduser('~/ComfyUI'),
              os.path.expanduser('~/Desktop/ComfyUI')]:
        if os.path.exists(os.path.join(p, 'main.py')):
            return p
    return None


# ── server-side run state + SSE broadcast (Phase 1) ─────────────────────────
_state_lock  = threading.Lock()
_cfg_lock    = threading.Lock()   # serialises all _wedge_config.json reads/writes
_sse_clients = []           # list[queue.Queue] — one per SSE connection

_run_state = {
    'running':       False,
    'progress_text': '',
    'job_pct':       0.0,
    'batch_pct':     0.0,
    'unit_statuses': {},    # name → {'state': str, 'reused': bool}
    'order':         [],    # snapshot of run order with _status fields
    'results':       [],    # completed workflow results from Python executor
    'log_tail':      [],    # last 200 log lines from Python executor
    'ts':            0.0,
}


def _push_to_clients():
    """Fan-out current _run_state to all SSE queues. Must hold _state_lock."""
    payload = json.dumps(_run_state)
    dead = []
    for q in _sse_clients:
        try:   q.put_nowait(payload)
        except _queue.Full: dead.append(q)
    for q in dead:
        try:   _sse_clients.remove(q)
        except ValueError: pass


def _broadcast(patch):
    """Merge patch into _run_state and push full state to every SSE client."""
    with _state_lock:
        _run_state.update(patch)
        _run_state['ts'] = _time_mod.time()
        _push_to_clients()


# ── request handler ──────────────────────────────────────────────────────────
# ── report helpers ─────────────────────────────────────────────────────────
import base64 as _b64

def _report_key(ro):
    if not ro: return None
    sub = (ro.get('sub') or '').strip('/')
    fn  = ro.get('fn', '')
    return (sub + '/' + fn) if sub else fn


def _get_video_thumb(fp):
    """Extract poster frame at 0.1s via ffmpeg, return data URI or None."""
    import subprocess
    try:
        r = subprocess.run(
            ['ffmpeg', '-ss', '0.1', '-i', fp,
             '-vframes', '1', '-f', 'image2', '-vcodec', 'png',
             '-loglevel', 'error', '-'],
            capture_output=True, timeout=15
        )
        if r.returncode == 0 and r.stdout:
            return 'data:image/png;base64,' + _b64.b64encode(r.stdout).decode('ascii')
    except Exception:
        pass
    return None


def build_report_html(data, media_info):
    """media_info: key → {uri, thumb, path, is_vid, fn}"""
    import html as _h, re as _re
    esc  = _h.escape
    esca = lambda s: _h.escape(str(s), quote=True)

    stamp   = data.get('stamp', '')
    server  = data.get('server', '127.0.0.1:8188')
    order   = data.get('order', [])
    results = data.get('results', [])
    log_txt = data.get('logLines', '')
    ok_n    = sum(1 for r in results if r.get('status') == 'ok')
    chk_n   = sum(1 for r in results if r.get('status') == 'check')
    fail_n  = sum(1 for r in results if r.get('status') not in ('ok', 'check'))
    tot_s   = sum(r.get('secs', 0) for r in results)
    date_s  = stamp.replace('T', ' ')[:19]
    by_name = {}
    for r in results:
        n = r.get('name', '')
        if n not in by_name: by_name[n] = r

    def sc(s):
        return 'ok' if s == 'ok' else 'check' if s == 'check' else 'fail' if s else 'pending'
    def slabel(s):
        if s == 'ok':    return '&#x2713;&nbsp;ok'
        if s == 'check': return '&#x26A0;&nbsp;check'
        if s:            return '&#x2717;&nbsp;' + esc(s)
        return '&mdash;'
    def unit_card(name, disp=None, oidx=None):
        disp = disp or name
        r = by_name.get(disp) or by_name.get(name)
        s = r.get('status') if r else None
        t = f"{r['secs']:.1f}s" if r else '&mdash;'
        cl = sc(s)
        oattr = f' data-oidx="{oidx}"' if oidx is not None else ''
        return (f'<div class="uc {cl}"{oattr}><div class="uc-n" title="{esca(disp)}">{esc(disp)}</div>'
                f'<div class="uc-s {cl}">{slabel(s)}</div><div class="uc-t">{t}</div></div>')

    rows = []
    _pidx = 0  # flat index into PG_PARAMS (singles +1, chain nodes +1 each)
    for _oi, u in enumerate(order):
        if u.get('type') == 'single':
            rows.append(f'<div class="orow">{unit_card(u["name"], disp=u.get("label"), oidx=_pidx)}</div>')
            _pidx += 1
        else:
            mode  = u.get('mode', 'success')
            ml    = '&#x2717;&nbsp;stop on fail' if mode == 'failure' else '&#x2713;&nbsp;stop on succ'
            names = u.get('names', [])
            nodes_html = ''
            for i, nm in enumerate(names):
                nodes_html += unit_card(nm, oidx=_pidx)
                _pidx += 1
                if i < len(names) - 1:
                    nodes_html += '<div class="arr">&#x2192;</div>'
            rows.append(f'<div class="orow"><span class="ctag {mode}">{ml}</span>{nodes_html}</div>')
    order_html = '\n'.join(rows)

    cards = []
    for r in results:
        ro   = r.get('rawOut')
        nm   = r.get('used', r.get('name', ''))
        st   = r.get('status', '')
        sec  = r.get('secs', 0)
        cls  = 'ok' if st == 'ok' else 'check' if st == 'check' else 'fail'
        key  = _report_key(ro)
        info = media_info.get(key, {}) if key else {}
        fn   = info.get('fn', (ro or {}).get('fn', ''))
        uri  = info.get('uri')    # full embedded data URI
        thb  = info.get('thumb')  # poster frame / thumbnail
        path = info.get('path', '')
        is_v = info.get('is_vid', False)

        # card thumbnail display
        if thb:
            card_thumb = (f'<img src="{thb}" loading="lazy">' +
                          ('<div class="rc-play">&#9654;</div>' if is_v else ''))
        elif uri:
            card_thumb = f'<img src="{uri}" loading="lazy">'
        else:
            card_thumb = f'<span class="np" title="{esca(fn)}">{"too large" if fn else "no preview"}</span>'

        # data attributes for lightbox
        da = [f'data-fn="{esca(fn)}"']
        if path: da.append(f'data-path="{esca(path)}"'
                           )
        if is_v: da.append('data-vid="1"')
        # store uri only if present (used for image lightbox full res)
        has_lb = bool(uri or thb or path)
        onclick = 'onclick="lbOpen(this)"' if has_lb else ''

        cards.append(
            f'<div class="rc" {" ".join(da)} {onclick}>'
            f'<div class="rc-thumb">{card_thumb}</div>'
            f'<div class="rc-meta"><div class="rc-name" title="{esca(nm)}">{esc(nm)}</div>'
            f'<div class="rc-stat {cls}">{esc(st)} &middot; {sec:.0f}s</div></div></div>'
        )
    res_html = '\n'.join(cards)
    params_json = json.dumps(data.get('unitParams') or []).replace('</', '<\\/')

    tpl = _REPORT_TPL
    for k, v in [('__DATE_S__', date_s), ('__SERVER__', esc(server)),
                 ('__OK_N__', str(ok_n)), ('__CHK_N__', str(chk_n)),
                 ('__FAIL_N__', str(fail_n)), ('__TOT_S__', f"{tot_s:.0f}"),
                 ('__ORD_LEN__', str(len(order))), ('__ORDER_HTML__', order_html),
                 ('__RES_LEN__', str(len(results))), ('__RES_HTML__', res_html),
                 ('__PARAMS_JSON__', params_json),
                 ('__LOG_HTML__', esc(log_txt)), ('__DATE_SHORT__', stamp[:10])]:
        tpl = tpl.replace(k, v)
    return tpl


_REPORT_TPL = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Wedge Report &middot; __DATE_SHORT__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0a0a0a;--bg2:#0c0c0c;--bg3:#0e0e0e;--b1:#1e1e1e;--b2:#2a2a2a;
  --fg:#e8e4dc;--fg2:#888880;--dim:#555550;
  --gold:#d18d1f;--gdim:#8a5c14;
  --ok:#5ad17a;--warn:#f0b656;--err:#ff6b6b;
}
body{font-family:'DM Mono','Courier New',monospace;background:var(--bg);color:var(--fg);min-height:100vh}
body::before{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,rgba(209,141,31,.018) 0px,transparent 1px,transparent 2px,rgba(209,141,31,.018) 3px);pointer-events:none;z-index:1000}
.hdr{padding:18px 32px;border-bottom:1px solid var(--b1);display:flex;align-items:center;justify-content:space-between;gap:20px;background:var(--bg2)}
.logo{height:32px}
.ttl{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--gold)}
.stmp{font-size:9px;color:var(--dim);letter-spacing:.08em;margin-top:3px}
.sum{display:flex;gap:18px;align-items:center;font-size:9px;letter-spacing:.1em}
.stat{display:flex;align-items:center;gap:5px}.stat .dot{width:7px;height:7px;border-radius:50%}
.tot{color:var(--dim)}
.sec{padding:22px 32px;border-bottom:1px solid var(--b1)}
.sec-t{font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);margin-bottom:16px}
.olist{display:flex;flex-direction:column;gap:10px}
.orow{display:flex;align-items:stretch;flex-wrap:wrap;row-gap:6px}
.uc{background:var(--bg3);border:1px solid var(--b2);border-radius:3px;padding:10px 14px;min-width:110px;max-width:180px;display:flex;flex-direction:column;gap:3px}
.uc.ok{border-color:rgba(90,209,122,.45)}
.uc.check{border-color:rgba(209,141,31,.5);background:rgba(209,141,31,.04)}
.uc.fail{border-color:rgba(255,107,107,.45);background:rgba(255,107,107,.04)}
.uc-n{font-size:10px;color:var(--fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.uc-s{font-size:8px;letter-spacing:.1em;text-transform:uppercase}
.uc-s.ok{color:var(--ok)}.uc-s.check{color:var(--warn)}.uc-s.fail{color:var(--err)}.uc-s.pending{color:var(--dim)}
.uc-t{font-size:8px;color:var(--dim)}
.arr{display:flex;align-items:center;padding:0 8px;color:var(--dim);font-size:14px}
.ctag{font-size:7px;letter-spacing:.08em;text-transform:uppercase;padding:3px 7px;border-radius:2px;border:1px solid var(--b2);color:var(--fg2);align-self:center;margin-right:10px;flex-shrink:0}
.ctag.success{color:var(--ok);border-color:rgba(90,209,122,.3)}
.ctag.failure{color:var(--warn);border-color:rgba(240,182,86,.3)}
.rg{display:flex;flex-wrap:wrap;gap:12px}
.rc{background:var(--bg3);border:1px solid var(--b1);border-radius:4px;overflow:hidden;width:180px;transition:border-color .2s}
.rc[onclick]{cursor:pointer}.rc[onclick]:hover{border-color:var(--gdim)}
.rc-thumb{width:100%;height:101px;background:#000;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}
.rc-thumb img{width:100%;height:100%;object-fit:cover;display:block}
.rc-play{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#fff;font-size:28px;background:rgba(0,0,0,.35);opacity:0;transition:opacity .2s;pointer-events:none}
.rc[onclick]:hover .rc-play{opacity:1}
.np{font-size:9px;color:var(--dim);letter-spacing:.1em;text-transform:uppercase;padding:8px;text-align:center}
.rc-meta{padding:8px 10px}
.rc-name{font-size:10px;color:var(--fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rc-stat{font-size:9px;margin-top:2px;letter-spacing:.05em}
.rc-stat.ok{color:var(--ok)}.rc-stat.check{color:var(--warn)}.rc-stat.fail{color:var(--err)}
/* ── param inspect ── */
.sec-t-row{display:flex;align-items:center;gap:14px;margin-bottom:16px;flex-wrap:wrap}
.sec-t-row .sec-t{margin-bottom:0}
.pg-btn{font-family:inherit;font-size:9px;letter-spacing:.08em;text-transform:uppercase;padding:4px 10px;background:var(--bg3);border:1px solid var(--b2);color:var(--fg2);border-radius:2px;cursor:pointer;transition:all .2s}
.pg-btn:hover{color:var(--gold);border-color:var(--gdim)}
.pg-btn:disabled{opacity:.4;cursor:not-allowed}
.pg-btn.on{color:var(--gold);border-color:var(--gold);background:rgba(209,141,31,.1)}
.pg-bar{display:none;align-items:center;gap:10px;font-size:9px;letter-spacing:.08em;color:var(--fg2)}
.pg-bar.vis{display:flex}
.pg-mode .uc[data-oidx]{cursor:pointer}
.pg-mode .uc[data-oidx]:hover{border-color:var(--gdim)}
.uc.pg-on{outline:2px solid var(--gold);outline-offset:-2px;box-shadow:0 0 10px rgba(209,141,31,.35)}
.pg-table-wrap{overflow-x:auto;margin-top:16px;border:1px solid var(--b1);border-radius:3px;display:none;max-height:60vh;overflow-y:auto}
.pg-table-wrap.vis{display:block}
table.pg{border-collapse:collapse;font-size:9px}
.pg th,.pg td{padding:7px 12px;border-bottom:1px solid var(--b1);border-right:1px solid var(--b1);white-space:nowrap;text-align:left;font-weight:400}
.pg th{background:var(--bg2);color:var(--dim);letter-spacing:.06em;position:sticky;top:0;z-index:1}
.pg th .pg-cls{font-size:7px;color:var(--dim);opacity:.7;display:block;letter-spacing:.04em;text-transform:none}
.pg th .pg-inp{color:var(--fg2);text-transform:none;font-size:9px}
.pg td:first-child,.pg th:first-child{position:sticky;left:0;background:var(--bg3);z-index:2;max-width:240px;overflow:hidden;text-overflow:ellipsis;color:var(--fg)}
.pg th:first-child{z-index:3;background:var(--bg2)}
.pg td{color:var(--fg2);max-width:260px;overflow:hidden;text-overflow:ellipsis}
.pg td.ov{color:var(--gold)}
.pg td.miss{color:var(--dim)}
/* ── results compare ── */
.rc{position:relative}
.cmp-cb{position:absolute;top:6px;left:6px;z-index:50;width:22px;height:22px;border-radius:3px;border:1px solid var(--b2);background:rgba(10,10,10,.85);display:none;align-items:center;justify-content:center;cursor:pointer;font-size:11px;user-select:none;color:var(--fg2)}
.rc:hover .cmp-cb{display:flex}
.rc.in-cmp .cmp-cb{display:flex;border-color:var(--gold);background:var(--gold);color:#000}
.rc.in-cmp{border-color:var(--gold)!important;box-shadow:0 0 12px rgba(209,141,31,.4)}
.cmp-bar{display:none;align-items:center;gap:10px;margin-bottom:14px;font-size:9px;letter-spacing:.08em;color:var(--fg2)}
.cmp-bar.vis{display:flex}
.cmp-bar strong{color:var(--gold)}
/* ── wipe compare lightbox ── */
.wlb{position:fixed;inset:0;z-index:9500;background:rgba(0,0,0,.95);display:none;flex-direction:column;align-items:center;justify-content:center}
.wlb.open{display:flex}
.w-wrap{position:relative;overflow:hidden;width:calc(100vw - 80px);height:calc(100vh - 220px);border-radius:3px;user-select:none;background:#000}
.w-a,.w-b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;overflow:hidden}
.w-a video,.w-a img,.w-b video,.w-b img{width:100%;height:100%;object-fit:contain;display:block}
.w-a{clip-path:inset(0 50% 0 0)}
.w-handle{position:absolute;top:0;bottom:0;width:3px;background:var(--gold);left:50%;transform:translateX(-50%);cursor:ew-resize;z-index:10;box-shadow:0 0 10px rgba(209,141,31,.4)}
.w-handle::after{content:'◀ ▶';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:var(--gold);color:#000;font-size:10px;padding:5px 8px;border-radius:3px;white-space:nowrap}
.w-labels{position:absolute;bottom:0;left:0;right:0;display:flex;justify-content:space-between;padding:8px 12px;pointer-events:none}
.w-lbl{font-size:9px;letter-spacing:.1em;text-transform:uppercase;background:rgba(0,0,0,.7);padding:4px 8px;border-radius:3px;max-width:45%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.w-lbl.a{color:#6ea8fe}.w-lbl.b{color:var(--warn)}
.w-ctrl{display:flex;gap:14px;align-items:center;margin-top:12px;font-size:10px;color:var(--fg2);width:calc(100vw - 80px);flex-wrap:wrap}
.w-scrub{flex:1;min-width:220px;display:flex;align-items:center;gap:12px}
.w-track{flex:1;height:26px;background:var(--bg3);border:1px solid var(--b2);border-radius:3px;position:relative;cursor:ew-resize;overflow:hidden}
.w-fill{position:absolute;top:0;left:0;height:100%;width:0%;background:rgba(209,141,31,.25);pointer-events:none}
.w-needle{position:absolute;top:0;bottom:0;width:2px;background:var(--gold);pointer-events:none;transform:translateX(-50%)}
.w-flbl{font-size:9px;letter-spacing:.1em;color:var(--gold);min-width:90px;text-align:right;text-transform:uppercase}
.w-spd{display:flex;gap:4px}
.w-spd button{font-family:inherit;font-size:9px;padding:3px 8px;border:1px solid var(--b2);background:var(--bg2);color:var(--fg2);border-radius:3px;cursor:pointer}
.w-spd button.on{border-color:var(--gold);color:var(--gold)}
.log-toggle{cursor:pointer;display:inline-flex;align-items:center;gap:8px;user-select:none}
.log-toggle:hover .log-title{color:var(--fg2)}
.log-chv{transition:transform .2s;font-size:10px}
.log-toggle.open .log-chv{transform:rotate(180deg)}
.log-body{display:none;margin-top:14px;background:var(--bg2);border:1px solid var(--b1);border-radius:3px;padding:12px 16px;max-height:380px;overflow-y:auto;font-size:10px;line-height:1.8;white-space:pre-wrap;word-break:break-word;color:var(--fg2)}
.log-body.open{display:block}
.lb{position:fixed;inset:0;z-index:9000;background:rgba(0,0,0,.93);display:none;flex-direction:column;align-items:center;justify-content:center}
.lb.open{display:flex}
.lb-x{position:absolute;top:16px;right:20px;font-size:22px;color:var(--fg2);cursor:pointer;background:none;border:none;font-family:inherit;z-index:9100;transition:color .2s}
.lb-x:hover{color:var(--fg)}
.lb-nav{position:absolute;top:50%;transform:translateY(-50%);font-size:28px;color:var(--fg2);cursor:pointer;background:none;border:none;font-family:inherit;z-index:9100;padding:0 18px;transition:color .2s}
.lb-nav:hover{color:var(--gold)}.lb-p{left:0}.lb-n{right:0}
.lb-ct{max-width:calc(100vw - 120px);max-height:calc(100vh - 90px);display:flex;align-items:center;justify-content:center}
.lb-ct video,.lb-ct img{max-width:100%;max-height:calc(100vh - 90px);border-radius:3px;display:block}
.lb-foot{position:absolute;bottom:0;left:0;right:0;padding:10px 16px 12px;background:rgba(0,0,0,.85);border-top:1px solid var(--b1);display:none;flex-direction:column;gap:6px;z-index:9200}
.lb-foot.vis{display:flex}
.lb-fn{font-size:10px;color:var(--fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lb-fp{font-size:8px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:.04em}
.lb-actions{display:flex;gap:8px;flex-wrap:wrap}
.lb-act{font-family:inherit;font-size:9px;letter-spacing:.08em;padding:3px 10px;background:var(--b2);border:1px solid var(--b1);color:var(--fg2);border-radius:2px;cursor:pointer;transition:color .2s;text-decoration:none;display:inline-block}
.lb-act:hover{color:var(--gold);border-color:var(--gdim)}
::-webkit-scrollbar{width:8px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--b2);border-radius:4px}
</style>
</head>
<body>

<div class="hdr">
  <div style="display:flex;align-items:center;gap:14px">
    <a href="https://thedistrictzero.com/" target="_blank" rel="noopener" style="line-height:0">
      <img class="logo" src="https://cdn.jsdelivr.net/gh/Gerry-Malta/AI_LAB@main/_img/DZ_logo_5.png" alt="DZ" onerror="this.style.display='none'">
    </a>
    <div style="width:1px;height:24px;background:var(--b2)"></div>
    <div>
      <div class="ttl">Wedge Report</div>
      <div class="stmp">__DATE_S__ &middot; __SERVER__</div>
    </div>
  </div>
  <div class="sum">
    <div class="stat"><span class="dot" style="background:var(--ok)"></span><span>__OK_N__ ok</span></div>
    <div class="stat"><span class="dot" style="background:var(--warn)"></span><span>__CHK_N__ check</span></div>
    <div class="stat"><span class="dot" style="background:var(--err)"></span><span>__FAIL_N__ failed</span></div>
    <span class="tot">__TOT_S__s total</span>
  </div>
</div>

<div class="sec" id="orderSec">
  <div class="sec-t-row">
    <div class="sec-t">Run Order &middot; __ORD_LEN__ unit(s)</div>
    <button class="pg-btn" id="pgGear" onclick="pgToggleMode()">&#9881; Inspect Params</button>
    <div class="pg-bar" id="pgBar">
      <strong id="pgCnt">0 selected</strong>
      <span>&middot; click workflows to select</span>
      <button class="pg-btn" id="pgConfirmBtn" onclick="pgConfirm()" disabled>&#9881; Compare</button>
      <button class="pg-btn" onclick="pgCancel()">&#x2715; Cancel</button>
      <label style="display:flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" id="pgDiffOnly" onchange="pgRender()"> diff only</label>
    </div>
  </div>
  <div class="olist">__ORDER_HTML__</div>
  <div class="pg-table-wrap" id="pgPanel"></div>
</div>

<div class="sec">
  <div class="sec-t">Results &middot; __RES_LEN__ output(s) &middot; hover a card to select for compare</div>
  <div class="cmp-bar" id="cmpBar">
    <strong id="cmpCnt">0 selected</strong>
    <span>&middot; max 2</span>
    <button class="pg-btn" id="cmpBtn" onclick="wOpen()" disabled>&#x21CC; Compare</button>
    <button class="pg-btn" onclick="cmpClear()">Clear</button>
  </div>
  <div class="rg">__RES_HTML__</div>
</div>

<div class="sec" style="border-bottom:none">
  <div class="sec-t">
    <span class="log-toggle" id="lgT" onclick="toggleLog()">
      <span class="log-title">Log</span>
      <span class="log-chv">&#x25BE;</span>
    </span>
  </div>
  <div class="log-body" id="lgB">__LOG_HTML__</div>
</div>

<div class="lb" id="lb">
  <button class="lb-x" onclick="lbClose()">&#x2715;</button>
  <button class="lb-nav lb-p" onclick="lbNav(-1)">&#x2190;</button>
  <button class="lb-nav lb-n" onclick="lbNav(1)">&#x2192;</button>
  <div class="lb-ct" id="lbCt"></div>
  <div class="lb-foot" id="lbFoot">
    <div class="lb-fn" id="lbFn"></div>
    <div class="lb-fp" id="lbFp"></div>
    <div class="lb-actions">
      <a class="lb-act" id="lbOpenFile" href="#" target="_blank">&#x25B6;&nbsp;open file</a>
      <a class="lb-act" id="lbOpenDir"  href="#" target="_blank">&#x1F4C1;&nbsp;open folder</a>
      <button class="lb-act" id="lbCopyPath">copy path</button>
    </div>
  </div>
</div>

<div class="wlb" id="wlb">
  <button class="lb-x" onclick="wClose()">&#x2715;</button>
  <div class="w-wrap" id="wWrap">
    <div class="w-b" id="wB"></div>
    <div class="w-a" id="wA"></div>
    <div class="w-handle" id="wHandle"></div>
    <div class="w-labels"><span class="w-lbl a" id="wLblA"></span><span class="w-lbl b" id="wLblB"></span></div>
  </div>
  <div class="w-ctrl">
    <button class="pg-btn" id="wPlayBtn" onclick="wTogglePlay()">&#9654; Play</button>
    <div class="w-spd"><button onclick="wSpeed(0.1)">&times;0.1</button><button onclick="wSpeed(0.25)">&times;0.25</button><button onclick="wSpeed(0.5)">&times;0.5</button><button class="on" onclick="wSpeed(1)">&times;1</button></div>
    <div class="w-scrub">
      <div class="w-track" id="wTrack"><div class="w-fill" id="wFill"></div><div class="w-needle" id="wNeedle"></div></div>
      <span class="w-flbl" id="wFrame">frame &mdash;</span>
    </div>
    <label style="display:flex;align-items:center;gap:5px">fps <input id="wFps" type="number" value="30" min="1" max="120" style="width:46px;background:var(--bg3);border:1px solid var(--b2);color:var(--fg);font-family:inherit;font-size:10px;padding:3px 5px;border-radius:3px"></label>
  </div>
</div>

<script>
var cards = Array.from(document.querySelectorAll('.rc[onclick]'));
var lbI   = -1;

function lbOpen(el) {
  var i = cards.indexOf(el);
  if (i < 0) return;
  lbI = i; lbShow();
  document.getElementById('lb').classList.add('open');
}
function lbClose() {
  document.getElementById('lb').classList.remove('open');
  var v = document.querySelector('#lbCt video');
  if (v) v.pause();
}
function lbNav(d) {
  if (!cards.length) return;
  lbI = (lbI + d + cards.length) % cards.length;
  lbShow();
}
function lbShow() {
  var c = cards[lbI]; if (!c) return;
  var isV  = c.dataset.vid === '1';
  var path = c.dataset.path || '';
  var fn   = c.dataset.fn  || '';
  var el   = document.getElementById('lbCt');
  var nm   = c.querySelector('.rc-name');
  var cardImg = c.querySelector('.rc-thumb img');

  // pause any previous video
  var prev = el.querySelector('video');
  if (prev) prev.pause();
  el.innerHTML = '';

  if (isV) {
    // Try to play via file:/// path (works when file is on same machine)
    if (path) {
      var v = document.createElement('video');
      v.controls = true; v.autoplay = true; v.muted = true;
      v.style.cssText = 'max-width:100%;max-height:calc(100vh - 90px);border-radius:3px';
      v.src = 'file:///' + path.replace(/\\/g, '/');
      // On load error fall back to the poster thumbnail
      if (cardImg) {
        v.onerror = function() {
          el.innerHTML = '';
          var img = document.createElement('img');
          img.src = cardImg.src;
          img.style.cssText = 'max-width:100%;max-height:calc(100vh - 90px);border-radius:3px';
          el.appendChild(img);
        };
      }
      el.appendChild(v);
    } else if (cardImg) {
      var img = document.createElement('img');
      img.src = cardImg.src;
      img.style.cssText = 'max-width:100%;max-height:calc(100vh - 90px);border-radius:3px';
      el.appendChild(img);
    }
  } else {
    if (cardImg) {
      var img = document.createElement('img');
      img.src = cardImg.src;
      img.style.cssText = 'max-width:100%;max-height:calc(100vh - 90px);border-radius:3px';
      el.appendChild(img);
    }
  }

  // footer meta + copy button
  var dispName = nm ? (nm.title || nm.textContent) : fn;
  var foot = document.getElementById('lbFoot');
  if (path) {
    var fileUrl   = 'file:///' + path.replace(/\\\\/g, '/');
    var folderUrl = 'file:///' + path.replace(/\\\\/g, '/').replace(/\/[^/]+$/, '/');
    document.getElementById('lbFn').textContent = fn || dispName;
    document.getElementById('lbFp').textContent = path;
    document.getElementById('lbOpenFile').href  = fileUrl;
    document.getElementById('lbOpenDir').href   = folderUrl;
    document.getElementById('lbCopyPath').dataset.path = path;
    foot.classList.add('vis');
  } else {
    foot.classList.remove('vis');
  }
}

document.getElementById('lbCopyPath').addEventListener('click', function() {
  var p = this.dataset.path; if (!p) return;
  var btn = this;
  function done(){ btn.textContent='copied!'; setTimeout(function(){btn.textContent='copy path';},1500); }
  if (navigator.clipboard) {
    navigator.clipboard.writeText(p).then(done).catch(function(){
      var inp=document.createElement('input');inp.value=p;document.body.appendChild(inp);inp.select();document.execCommand('copy');document.body.removeChild(inp);done();
    });
  } else {
    var inp=document.createElement('input');inp.value=p;document.body.appendChild(inp);inp.select();document.execCommand('copy');document.body.removeChild(inp);done();
  }
});

/* ════ results compare ════ */
var cmpSet = [];
if (cards.length){
  document.getElementById('cmpBar').classList.add('vis');
  cards.forEach(function(c, i){
    var cb = document.createElement('span');
    cb.className = 'cmp-cb'; cb.textContent = '\u2713'; cb.title = 'Select for compare';
    cb.addEventListener('click', function(e){ e.stopPropagation(); cmpToggle(i); });
    c.appendChild(cb);
  });
}
function cmpToggle(i){
  var p = cmpSet.indexOf(i);
  if (p >= 0) cmpSet.splice(p, 1);
  else { if (cmpSet.length >= 2) cmpSet.shift(); cmpSet.push(i); }
  cards.forEach(function(c, j){ c.classList.toggle('in-cmp', cmpSet.indexOf(j) >= 0); });
  var n = cmpSet.length;
  document.getElementById('cmpCnt').textContent = n === 0 ? '0 selected' : (n === 1 ? '1 selected (pick one more)' : '2 selected');
  document.getElementById('cmpBtn').disabled = n !== 2;
}
function cmpClear(){
  cmpSet = [];
  cards.forEach(function(c){ c.classList.remove('in-cmp'); });
  document.getElementById('cmpCnt').textContent = '0 selected';
  document.getElementById('cmpBtn').disabled = true;
}
function wMedia(c, host){
  host.innerHTML = '';
  var isV = c.dataset.vid === '1', path = c.dataset.path || '';
  var img = c.querySelector('.rc-thumb img');
  if (isV && path){
    var v = document.createElement('video');
    v.loop = true; v.muted = true; v.playsInline = true;
    v.src = 'file:///' + path.replace(/\\/g, '/');
    if (img){ v.onerror = function(){ host.innerHTML = ''; var im = document.createElement('img'); im.src = img.src; host.appendChild(im); }; }
    host.appendChild(v);
  } else if (img){
    var im2 = document.createElement('img'); im2.src = img.src; host.appendChild(im2);
  } else {
    host.innerHTML = '<div style="color:var(--dim);font-size:10px;padding:20px">No media</div>';
  }
}
function wOpen(){
  if (cmpSet.length !== 2) return;
  var a = cards[cmpSet[0]], b = cards[cmpSet[1]];
  wMedia(a, document.getElementById('wA'));
  wMedia(b, document.getElementById('wB'));
  var na = a.querySelector('.rc-name'), nb = b.querySelector('.rc-name');
  document.getElementById('wLblA').textContent = na ? (na.title || na.textContent) : '';
  document.getElementById('wLblB').textContent = nb ? (nb.title || nb.textContent) : '';
  wSetPos(50);
  document.getElementById('wlb').classList.add('open');
  setTimeout(function(){
    document.querySelectorAll('#wA video, #wB video').forEach(function(v){ v.play().catch(function(){}); });
    wBindSync(); wScrubInit(); wPlayLbl();
  }, 120);
}
function wClose(){
  document.getElementById('wlb').classList.remove('open');
  document.querySelectorAll('#wA video, #wB video').forEach(function(v){ v.pause(); v.playbackRate = 1; });
}
function wSetPos(p){
  document.getElementById('wA').style.clipPath = 'inset(0 ' + (100 - p) + '% 0 0)';
  document.getElementById('wHandle').style.left = p + '%';
}
(function(){
  var drag = false;
  function pct(e){
    var w = document.getElementById('wWrap'); if (!w) return 50;
    var r = w.getBoundingClientRect();
    var x = e.touches ? e.touches[0].clientX : e.clientX;
    return Math.max(2, Math.min(98, (x - r.left) / r.width * 100));
  }
  document.addEventListener('mousedown', function(e){ if (e.target.id === 'wHandle') drag = true; });
  document.addEventListener('mouseup',   function(){ drag = false; });
  document.addEventListener('mousemove', function(e){ if (drag) wSetPos(pct(e)); });
  document.addEventListener('touchstart', function(e){ if (e.target.id === 'wHandle') drag = true; }, {passive:true});
  document.addEventListener('touchend',   function(){ drag = false; });
  document.addEventListener('touchmove',  function(e){ if (drag) wSetPos(pct(e)); }, {passive:true});
})();
function wBindSync(){
  var va = document.querySelector('#wA video'), vb = document.querySelector('#wB video');
  if (!va || !vb) return;
  var s = false;
  va.addEventListener('timeupdate', function(){
    if (s) return; s = true;
    if (Math.abs(vb.currentTime - va.currentTime) > .05) vb.currentTime = va.currentTime;
    if (!va.paused && vb.paused) vb.play().catch(function(){});
    if (va.paused && !vb.paused) vb.pause();
    s = false;
  });
  va.addEventListener('play',  function(){ vb.play().catch(function(){}); wPlayLbl(); });
  va.addEventListener('pause', function(){ vb.pause(); wPlayLbl(); });
  vb.addEventListener('play',  function(){ va.play().catch(function(){}); wPlayLbl(); });
  vb.addEventListener('pause', function(){ va.pause(); wPlayLbl(); });
}
function wTogglePlay(){
  var vids = Array.from(document.querySelectorAll('#wA video, #wB video'));
  if (!vids.length) return;
  var any = vids.some(function(v){ return !v.paused; });
  vids.forEach(function(v){ if (any) v.pause(); else v.play().catch(function(){}); });
}
function wPlayLbl(){
  var vids = Array.from(document.querySelectorAll('#wA video, #wB video'));
  var any = vids.some(function(v){ return !v.paused; });
  var b = document.getElementById('wPlayBtn');
  if (b) b.textContent = any ? '\u23F8 Pause' : '\u25B6 Play';
}
function wSpeed(r){
  document.querySelectorAll('#wA video, #wB video').forEach(function(v){ v.playbackRate = r; });
  document.querySelectorAll('.w-spd button').forEach(function(b){
    b.classList.toggle('on', Math.abs(parseFloat(b.textContent.replace('\u00d7','')) - r) < .001);
  });
}
var wScrubDrag = false;
function wScrubInit(){
  var va = document.querySelector('#wA video') || document.querySelector('#wB video');
  if (va){
    va.addEventListener('timeupdate', wScrubFromVid);
    va.addEventListener('loadedmetadata', wScrubFromVid);
  }
  var t = document.getElementById('wTrack');
  if (!t || t.dataset.init) return;
  t.dataset.init = '1';
  function pct(e){
    var r = t.getBoundingClientRect();
    var x = e.touches ? e.touches[0].clientX : e.clientX;
    return Math.max(0, Math.min(100, (x - r.left) / r.width * 100));
  }
  function upd(p){
    var v = document.querySelector('#wA video') || document.querySelector('#wB video');
    if (!v || !v.duration) return;
    var tm = p / 100 * v.duration;
    document.querySelectorAll('#wA video, #wB video').forEach(function(x){ x.currentTime = tm; });
    wScrubSet(p, tm, v.duration);
  }
  t.addEventListener('mousedown', function(e){ wScrubDrag = true; document.querySelectorAll('#wA video, #wB video').forEach(function(v){ v.pause(); }); upd(pct(e)); });
  document.addEventListener('mousemove', function(e){ if (wScrubDrag) upd(pct(e)); });
  document.addEventListener('mouseup',   function(){ wScrubDrag = false; });
  t.addEventListener('touchstart', function(e){ wScrubDrag = true; upd(pct(e)); }, {passive:true});
  document.addEventListener('touchmove', function(e){ if (wScrubDrag) upd(pct(e)); }, {passive:true});
  document.addEventListener('touchend',  function(){ wScrubDrag = false; });
}
function wScrubSet(p, tm, dur){
  var n = document.getElementById('wNeedle'), f = document.getElementById('wFill'), l = document.getElementById('wFrame');
  if (n) n.style.left = p + '%';
  if (f) f.style.width = p + '%';
  if (l && dur){
    var fps = parseInt((document.getElementById('wFps')||{}).value) || 30;
    l.textContent = 'frame ' + Math.round(tm * fps) + ' / ' + Math.round(dur * fps);
  }
}
function wScrubFromVid(){
  var v = document.querySelector('#wA video') || document.querySelector('#wB video');
  if (!v || !v.duration) return;
  wScrubSet(v.currentTime / v.duration * 100, v.currentTime, v.duration);
}

/* ════ param inspect (gear) ════ */
var PG_PARAMS = __PARAMS_JSON__;
var pgMode = false, pgSel = [];
document.querySelectorAll('.uc[data-oidx]').forEach(function(uc){
  uc.addEventListener('click', function(){
    if (!pgMode) return;
    var i = Number(uc.dataset.oidx);
    if (PG_PARAMS[i] == null) return;
    var p = pgSel.indexOf(i);
    if (p >= 0){ pgSel.splice(p, 1); uc.classList.remove('pg-on'); }
    else { pgSel.push(i); uc.classList.add('pg-on'); }
    document.getElementById('pgCnt').textContent = pgSel.length + ' selected';
    document.getElementById('pgConfirmBtn').disabled = pgSel.length < 1;
  });
});
function pgToggleMode(){
  if (pgMode){ pgCancel(); return; }
  pgMode = true;
  document.getElementById('orderSec').classList.add('pg-mode');
  document.getElementById('pgGear').classList.add('on');
  document.getElementById('pgBar').classList.add('vis');
}
function pgCancel(){
  pgMode = false; pgSel = [];
  document.getElementById('orderSec').classList.remove('pg-mode');
  document.getElementById('pgGear').classList.remove('on');
  document.getElementById('pgBar').classList.remove('vis');
  document.querySelectorAll('.uc.pg-on').forEach(function(u){ u.classList.remove('pg-on'); });
  var p = document.getElementById('pgPanel'); p.classList.remove('vis'); p.innerHTML = '';
  document.getElementById('pgCnt').textContent = '0 selected';
  document.getElementById('pgConfirmBtn').disabled = true;
}
function pgConfirm(){ pgRender(); }
function pgEsc(s){ return String(s).replace(/[&<>"]/g, function(c){ return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]; }); }
function pgCellText(entry){
  if (!entry) return null;
  return entry.map(function(e){ return String(e.v); }).join(' / ');
}
function pgRender(){
  if (!pgSel.length) return;
  var sel = pgSel.slice().sort(function(a,b){ return a - b; });
  var cols = {};
  sel.forEach(function(i){ var u = PG_PARAMS[i]; if (!u) return; Object.keys(u.params).forEach(function(k){ cols[k] = 1; }); });
  var colList = Object.keys(cols).sort();
  if (document.getElementById('pgDiffOnly').checked){
    colList = colList.filter(function(k){
      var seen = {}, n = 0;
      sel.forEach(function(i){
        var u = PG_PARAMS[i];
        var t = u ? pgCellText(u.params[k]) : null;
        var key = t === null ? '\u2014' : t;
        if (!seen[key]){ seen[key] = 1; n++; }
      });
      return n > 1;
    });
  }
  var h = '<table class="pg"><thead><tr><th>workflow</th>';
  colList.forEach(function(k){
    var d = k.lastIndexOf('.');
    var cls = k.slice(0, d), inp = k.slice(d + 1);
    h += '<th><span class="pg-inp">' + pgEsc(inp) + '</span><span class="pg-cls">' + pgEsc(cls) + '</span></th>';
  });
  h += '</tr></thead><tbody>';
  sel.forEach(function(i){
    var u = PG_PARAMS[i]; if (!u) return;
    h += '<tr><td title="' + pgEsc(u.label) + '">' + pgEsc(u.label) + '</td>';
    colList.forEach(function(k){
      var entry = u.params[k];
      if (!entry){ h += '<td class="miss">&mdash;</td>'; return; }
      var ov = entry.some(function(e){ return e.ov; });
      var txt = pgCellText(entry);
      h += '<td class="' + (ov ? 'ov' : '') + '" title="' + pgEsc(txt) + '">' + pgEsc(txt) + '</td>';
    });
    h += '</tr>';
  });
  h += '</tbody></table>';
  var p = document.getElementById('pgPanel');
  p.innerHTML = h; p.classList.add('vis');
}
document.addEventListener('keydown', function(e){
  if (e.key === 'Escape' && document.getElementById('wlb').classList.contains('open')) wClose();
});

function toggleLog() {
  document.getElementById('lgB').classList.toggle('open');
  document.getElementById('lgT').classList.toggle('open');
}
document.addEventListener('keydown', function(e) {
  if (document.getElementById('lb').classList.contains('open')) {
    if (e.key === 'ArrowLeft')  lbNav(-1);
    if (e.key === 'ArrowRight') lbNav(1);
    if (e.key === 'Escape')     lbClose();
  }
});
</script>
</body>
</html>"""


# ── SSE client code injected into HTML at serve time (Phase 1) ──────────────
# Written as a plain Python string; injected via _build_html().
# Uses only ES5-compatible syntax except async/await (used by the run engine
# already) so no transpilation is needed.

_SSE_JS = r"""
// ══════════════════════════════════════════════════════════════════════════════
// Phase 2 — Python background executor + SSE live view
//
// startRun  → POST /start_run  (submit plan to Python, JS becomes pure viewer)
// stopRun   → POST /stop_run   (signal Python executor to stop)
// connectSSE → EventSource /events  (all tabs receive authoritative live state)
// applyRunState → idempotent UI update driven entirely by server state
// ══════════════════════════════════════════════════════════════════════════════

var _sseResultCount = 0;   // how many results have been rendered from state
var _sseLogInited   = false; // true after first SSE event (skip log catchup)
var _sseLogCount    = 0;   // how many log entries have been rendered
var _lastOrderSig   = '';  // change-detect for order re-render

// ── _orderSig ────────────────────────────────────────────────────────────────
function _orderSig(ord) {
    return (ord||[]).map(function(u) {
        var id = u.type === 'single' ? (u.label||u.name) : (u.names||[]).join(',');
        return id + ':' + (u._status||'-');
    }).join('|');
}

// ── applyRunState — authoritative update from server state ───────────────────
function applyRunState(state) {
    // ── running flag + button states ─────────────────────────────────────────
    if (state.running !== undefined) {
        if (state.running !== running) {
            var _wasRunning = running;
            running = state.running;
            updateRunButton();
            if (_wasRunning && !running && window._autoReportEnabled !== false && typeof exportReport === 'function' && WEDGE_SERVER &&
                    window.resultStore && resultStore.length) {
                // ensure serverFolder is set (may be null if page was opened mid-run)
                if (!serverFolder) {
                    var _fi = document.getElementById('folderPathInput');
                    if (_fi && _fi.value) serverFolder = _fi.value;
                }
                if (!serverFolder) {
                    log('\u26a0 Auto-report: no workflow folder set.', 'warn');
                } else {
                setTimeout(function() {
                    var _allPaths = (window._reportPaths||[]).slice();
                    if (window._reportPaths) window._reportPaths.length = 0;
                    if (!_allPaths.length) {
                        exportReport(); // no intermediate saved — save final now
                    } else {
                        var _last = _allPaths[_allPaths.length - 1];
                        log('\u2713 final report \u2014 ' + _last.split(/[\\\/]/).pop(), 'muted');
                        var _toDelete = _allPaths.slice(0, -1);
                        if (_toDelete.length && WEDGE_SERVER) {
                            setTimeout(function() {
                                fetch(WEDGE_SERVER + '/cleanup_reports', {
                                    method: 'POST',
                                    headers: {'Content-Type': 'application/json'},
                                    body: JSON.stringify({paths: _toDelete})
                                }).then(function(r){ return r.json(); })
                                  .then(function(d){
                                    if (d.deleted > 0)
                                        log('\u2713 Removed ' + d.deleted + ' intermediate report(s).', 'muted');
                                  }).catch(function(){});
                            }, 400);
                        }
                    }
                }, 800);
                } // end else serverFolder
            }
        }
        var sb = document.getElementById('stopBtn');
        if (sb) sb.disabled = !state.running;
    }

    // ── progress bars + text ─────────────────────────────────────────────────
    if (state.job_pct   !== undefined) setBar('job',   state.job_pct);
    if (state.batch_pct !== undefined) setBar('batch', state.batch_pct);
    if (state.progress_text !== undefined) {
        var pt = document.getElementById('progressText');
        if (pt) pt.textContent = state.progress_text;
    }

    // ── 1. sync window._nodeStatus from unit_statuses (before renderGraph) ───
    if (state.unit_statuses) {
        window._nodeStatus = window._nodeStatus || {};
        for (var nm in state.unit_statuses) {
            var e = state.unit_statuses[nm];
            window._nodeStatus[nm] = (typeof e==='object' && e) ? e : {state:e, reused:false};
        }
    }

    // ── 2. re-render order + graph when signature changes ────────────────────
    if (state.order && state.order.length) {
        var sig = _orderSig(state.order);
        if (sig !== _lastOrderSig) {
            order = state.order;
            renderOrder();
            renderGraph();
            _lastOrderSig = sig;
        }
    }

    // ── 3. directly colour DOM nodes (fast path, no full re-render) ──────────
    if (state.unit_statuses) {
        for (var nm2 in state.unit_statuses) {
            var e2 = state.unit_statuses[nm2];
            var st = (typeof e2==='object' && e2) ? e2.state  : e2;
            var ru = (typeof e2==='object' && e2) ? !!e2.reused : false;
            (nodeEls[nm2]||[]).forEach(function(el) {
                el.className = 'gnode' + (st?' '+st:'') + (ru?' reused':'');
            });
            document.querySelectorAll('.unit[data-key="'+CSS.escape(nm2)+'"]')
                .forEach(function(el) {
                    el.classList.remove('running','ok','fail');
                    if (st && st!=='pending') el.classList.add(st);
                });
        }
    }

    // ── 4. results from Python executor ──────────────────────────────────────
    if (state.results !== undefined) {
        if (state.results.length === 0 && _sseResultCount > 0) {
            // Python started a new run — clear result cards
            document.getElementById('results').innerHTML = '';
            if (window.resultStore) resultStore.length = 0;
            _sseResultCount = 0;
            if (window._rebuildResultFilter) window._rebuildResultFilter();
        } else if (state.results.length > _sseResultCount) {
            state.results.slice(_sseResultCount).forEach(function(r) {
                try {
                    addResult(r.name, {
                        ok: r.status === 'ok', status: r.status,
                        secs: r.secs || 0, outs: r.outs || [],
                        used: r.used || r.name
                    });
                } catch(err) { console.error('addResult:', err); }
            });
            _sseResultCount = state.results.length;
            // per-job auto-report (silent)
            if (window._autoReportEnabled !== false && typeof exportReport === 'function' && WEDGE_SERVER && resultStore.length) {
                if (!serverFolder) {
                    var _fi2 = document.getElementById('folderPathInput');
                    if (_fi2 && _fi2.value) serverFolder = _fi2.value;
                }
                if (serverFolder) exportReport(true);
            }
        }
    }

    // ── 5. log lines from Python executor (skip stale entries on first connect)
    if (state.log_tail !== undefined) {
        if (!_sseLogInited) {
            _sseLogCount  = state.log_tail.length; // sync without rendering
            _sseLogInited = true;
        } else if (state.log_tail.length > _sseLogCount) {
            state.log_tail.slice(_sseLogCount).forEach(function(entry) {
                log(entry.msg, entry.tag || 'info');
            });
            _sseLogCount = state.log_tail.length;
        }
    }
}

// ── connectSSE ───────────────────────────────────────────────────────────────
function connectSSE() {
    if (!WEDGE_SERVER) return;
    var _es = new EventSource(WEDGE_SERVER + '/events');
    _es.onmessage = function(e) {
        try { applyRunState(JSON.parse(e.data)); } catch(err) {}
    };
}

// ── startRun: delegate to Python executor (file:// falls back to JS) ─────────
var _startRunOrig = startRun;
startRun = async function() {
    if (!WEDGE_SERVER) { return await _startRunOrig(); }

    if (running) return;
    if (!comfyOnline) {
        alert('ComfyUI is offline.\n\nStart it with:\n  python main.py --enable-cors-header "*"\n\nThen this page will switch to Local mode automatically.');
        return;
    }
    if (!order.length) { alert('Build a plan first.'); return; }

    var missing = [];
    order.forEach(function(u) {
        (u.type==='single' ? [u.name] : (u.names||[])).forEach(function(n) {
            if (!workflows[n] || !workflows[n].validApi || !workflows[n].wf) missing.push(n);
        });
    });
    if (missing.length) {
        alert('Missing workflow content for: ' + [...new Set(missing)].join(', ') +
              '\n\nLoad the workflow folder first.');
        return;
    }

    // Save config
    var _cpEl = document.getElementById('comfyPath');
    var _cfg  = { timeout: parseFloat(document.getElementById('timeout').value)||20,
                  order: JSON.parse(JSON.stringify(order)) };
    if (_cpEl && _cpEl.value.trim()) _cfg.comfy_path = _cpEl.value.trim();
    fetch(WEDGE_SERVER+'/save_config', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(_cfg)}).catch(function(){});

    // Reset UI for new run
    running        = true;
    _sseResultCount = 0;
    _sseLogCount    = 0;
    _sseLogInited   = false;
    _lastOrderSig   = '';
    window._nodeStatus = {};
    order.forEach(function(u){ delete u._status; });
    document.getElementById('results').innerHTML = '';
    document.getElementById('runBtn').disabled   = true;
    document.getElementById('stopBtn').disabled  = false;
    setBar('job',0); setBar('batch',0);
    document.getElementById('progressText').textContent = '';
    if (window.resultStore) resultStore.length = 0;
    if (window._reportPaths) window._reportPaths.length = 0;
    renderGraph();

    try {
        var resp = await fetch(WEDGE_SERVER+'/start_run', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({
                order:        JSON.parse(JSON.stringify(order)),
                comfy_server: document.getElementById('server').value.trim()||'127.0.0.1:8188',
                timeout:      parseFloat(document.getElementById('timeout').value)||20
            })
        });
        var d = await resp.json();
        if (!d.ok) {
            log('Could not start run: '+(d.error||'?'), 'err');
            running = false; updateRunButton();
            document.getElementById('stopBtn').disabled = true;
        }
    } catch(e) {
        log('Start run failed: '+e.message, 'err');
        running = false; updateRunButton();
        document.getElementById('stopBtn').disabled = true;
    }
};

// ── stopRun: signal Python executor ──────────────────────────────────────────
var _stopRunOrig = stopRun;
stopRun = function() {
    if (!WEDGE_SERVER) { return _stopRunOrig(); }
    log('Stop requested\u2026', 'warn');
    document.getElementById('stopBtn').disabled = true;
    fetch(WEDGE_SERVER+'/stop_run', {method:'POST'}).catch(function(){});
};

// ── autoLoadFromServer wrap: persist workflow_folder ─────────────────────────
var _autoLoadOrig = autoLoadFromServer;
autoLoadFromServer = async function(folder, files) {
    if (WEDGE_SERVER && folder) {
        fetch(WEDGE_SERVER+'/save_config', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({workflow_folder: folder})
        }).catch(function(){});
    }
    return await _autoLoadOrig(folder, files);
};

// Wrap loadFromServer: clear order in config when user loads a new folder
var _lfsOrig = loadFromServer;
loadFromServer = async function() {
    order = []; chainSel = []; selUnit = null;
    renderOrder(); renderGraph();
    await _lfsOrig();
    // after explicit folder load: reset order in config for fresh start
    if (WEDGE_SERVER) {
        fetch(WEDGE_SERVER + '/save_config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({order: []})
        }).catch(function(){});
    }
};


connectSSE();

// ── Resizable panel: Results only ───────────────────────────────────────────
(function () {
    var _sty = document.createElement('style');
    _sty.textContent =
        // handle: NO border-top — graph-wrap already has border-bottom above it,
        // and .results already has border-top below it. A third line here creates
        // the "shadow tab" artifact the user sees.
        '.resize-handle{' +
            'height:8px;cursor:ns-resize;flex-shrink:0;touch-action:none;' +
            'background:transparent;position:relative;transition:background .15s' +
        '}' +
        '.resize-handle::after{' +
            'content:"";position:absolute;left:50%;top:50%;' +
            'transform:translate(-50%,-50%);' +
            'width:32px;height:2px;border-radius:1px;' +
            'background:var(--accent-gold);opacity:.25;transition:opacity .15s' +
        '}' +
        '.resize-handle:hover{background:rgba(209,141,31,.08)}' +
        '.resize-handle:hover::after{opacity:.9}';
    document.head.appendChild(_sty);

    var DEFAULT_H = 220;
    var GW_MIN    = 60;

    var rv = document.querySelector('.results');
    var gw = document.querySelector('.graph-wrap');
    var pb = document.querySelector('.pbars');
    if (!rv) return;

    // graph-wrap: elastic. Override CSS max-height:200px so it can grow freely.
    if (gw) {
        gw.style.flex      = '1 1 0';
        gw.style.minHeight = GW_MIN + 'px';
        gw.style.maxHeight = 'none';      // ← remove CSS cap so graph absorbs space
        gw.style.overflowY = 'auto';
    }

    // pbars: margin-top:auto sticks it to the bottom permanently.
    // transition:none prevents any inherited animation on the margin change.
    if (pb) {
        pb.style.transition = 'none';
        pb.style.marginTop  = 'auto';
        pb.style.flexShrink = '0';
    }

    // results: override CSS max-height and set initial height
    rv.style.overflowY  = rv.style.overflowY || 'auto';
    rv.style.flexShrink = '0';
    rv.style.height     = DEFAULT_H + 'px';
    rv.style.maxHeight  = DEFAULT_H + 'px';

    // Handle above results — always visible at graph/results junction
    var rh = document.createElement('div');
    rh.className = 'resize-handle';
    rh.title = 'Drag \u2195 to resize results \u2022 double-click to reset';
    rv.parentNode.insertBefore(rh, rv);

    var dragging = false, startY = 0, startH = 0;

    function getMaxH() {
        // Exclude graph-wrap (gw) from measurement — it's elastic and its
        // offsetHeight lags by one frame during drag, causing upward resistance.
        // Use GW_MIN as its reserved floor instead (stable constant).
        var col = rv.parentNode, fixedH = 0;
        [].forEach.call(col.children, function(c) {
            if (c !== rv && c !== rh && c !== gw) fixedH += c.offsetHeight || 0;
        });
        return Math.max(60, (col.clientHeight || 600) - fixedH - GW_MIN
                           - (rh.offsetHeight || 8) - 4);
    }
    function applyH(clientY) {
        var h = Math.max(60, Math.min(getMaxH(), startH + (startY - clientY)));
        rv.style.height = rv.style.maxHeight = h + 'px';
    }
    function start(y) {
        dragging = true; startY = y; startH = rv.offsetHeight;
        document.body.style.userSelect = 'none';
        document.body.style.cursor     = 'ns-resize';
    }
    function end() {
        if (!dragging) return;
        dragging = false;
        document.body.style.cursor = document.body.style.userSelect = '';
    }

    rh.addEventListener('mousedown',  function(e){ start(e.clientY); e.preventDefault(); });
    document.addEventListener('mousemove',  function(e){ if(dragging){ applyH(e.clientY); e.preventDefault(); }});
    document.addEventListener('mouseup',    end);
    rh.addEventListener('touchstart', function(e){ if(e.touches.length===1){ start(e.touches[0].clientY); e.preventDefault(); }},{passive:false});
    document.addEventListener('touchmove',  function(e){ if(dragging&&e.touches.length===1){ applyH(e.touches[0].clientY); e.preventDefault(); }},{passive:false});
    document.addEventListener('touchend',   end);

    rh.addEventListener('dblclick', function(e){
        e.preventDefault();
        var h = Math.min(DEFAULT_H, getMaxH());
        rv.style.height = rv.style.maxHeight = h + 'px';
    });
}());

// ── Per-workflow + output-index result filter ─────────────────────────────────
(function () {

    /* ── CSS ───────────────────────────────────────────────────────────────── */
    var _sty = document.createElement('style');
    _sty.textContent =
        '.rfbar{display:none;align-items:center;gap:5px;padding:5px 18px 5px;' +
        'background:var(--bg-secondary);border-bottom:1px solid var(--border-primary);' +
        'flex-wrap:wrap}' +
        '.rfbar.on{display:flex}' +
        '.rfc{padding:2px 8px;border-radius:2px;cursor:pointer;font-size:8px;' +
        'letter-spacing:.08em;text-transform:uppercase;user-select:none;' +
        'border:1px solid var(--border-secondary);color:var(--text-secondary);' +
        'background:var(--bg-primary);transition:all .15s}' +
        '.rfc:hover{border-color:var(--accent-gold-dim)}' +
        '.rfc.on{border-color:var(--accent-gold);color:var(--accent-gold);' +
        'background:rgba(209,141,31,.1)}' +
        '.rfc.wfc.on{border-color:rgba(110,168,254,.5);color:#6ea8fe;' +
        'background:rgba(110,168,254,.08)}' +
        '.rfbar-sep{color:var(--text-dim);padding:0 3px;font-size:10px}' +
        '.rfbar-lbl{font-size:7px;letter-spacing:.1em;text-transform:uppercase;' +
        'color:var(--text-dim);white-space:nowrap}' +
        '.rf-toggle{font-size:8px;letter-spacing:.07em;text-transform:uppercase;' +
        'cursor:pointer;padding:2px 8px;border-radius:2px;flex-shrink:0;' +
        'border:1px solid var(--border-secondary);color:var(--text-dim);' +
        'background:transparent;transition:all .15s;white-space:nowrap}' +
        '.rf-toggle.on{border-color:var(--accent-gold);color:var(--accent-gold)}' +
        '.result-card.rf-hide{display:none!important}' +
        '.unit.rf-wf-hl{outline:1px solid rgba(110,168,254,.6);outline-offset:-2px}';
    document.head.appendChild(_sty);

    /* ── state ─────────────────────────────────────────────────────────────── */
    var _st = { active: false, wf: null, outs: null }; // outs = null|Set<number>

    /* ── build filter bar DOM ──────────────────────────────────────────────── */
    var resultsDiv = document.querySelector('.results');
    if (!resultsDiv) return;

    // toggle button inside section-label
    var secLabel = resultsDiv.querySelector('.section-label');
    if (secLabel) {
        secLabel.style.cssText += ';display:flex;align-items:center;justify-content:space-between;gap:8px';
        var tog = document.createElement('span');
        tog.className = 'rf-toggle';
        tog.id = 'rfTog';
        tog.textContent = '\u26a1 Filter';
        tog.title = 'Toggle result filtering.\nWhen on: click a workflow in Run Order to isolate its outputs.';
        tog.addEventListener('click', function (e) {
            e.stopPropagation();
            _st.active = !_st.active;
            tog.classList.toggle('on', _st.active);
            bar.classList.toggle('on', _st.active);
            if (!_st.active) { _st.wf = null; _st.outs = null; _clearWfHl(); }
            _applyFilter();
        });
        secLabel.appendChild(tog);
    }

    // filter bar
    var bar = document.createElement('div');
    bar.className = 'rfbar';
    bar.id = 'rfbar';

    var _wfRow = document.createElement('span');
    _wfRow.style.cssText = 'display:flex;align-items:center;gap:4px;flex-wrap:wrap';
    _wfRow.innerHTML = '<span class="rfbar-lbl">Workflow\u00a0</span>';
    bar.appendChild(_wfRow);

    var _sep = document.createElement('span');
    _sep.className = 'rfbar-sep';
    _sep.textContent = '\u00b7';
    bar.appendChild(_sep);

    var _outRow = document.createElement('span');
    _outRow.style.cssText = 'display:none;align-items:center;gap:4px;flex-wrap:wrap';
    _outRow.innerHTML = '<span class="rfbar-lbl">Output\u00a0</span>';
    bar.appendChild(_outRow);

    // insert bar after section-label
    if (secLabel) resultsDiv.insertBefore(bar, secLabel.nextSibling);
    else resultsDiv.prepend(bar);

    /* ── helpers ───────────────────────────────────────────────────────────── */
    function _clearWfHl() {
        document.querySelectorAll('.unit.rf-wf-hl').forEach(function (el) {
            el.classList.remove('rf-wf-hl');
        });
    }

    function _getWorkflows() {
        var seen = new Set(), list = [];
        (resultStore || []).forEach(function (r) {
            if (!seen.has(r.name)) { seen.add(r.name); list.push(r.name); }
        });
        return list;
    }

    function _maxOutsForWf(wf) {
        var mx = 1;
        document.querySelectorAll('#results .result-card').forEach(function (c) {
            if (wf && c.dataset.rfWf !== wf) return;
            var t = parseInt(c.dataset.rfTotal) || 1;
            if (t > mx) mx = t;
        });
        return mx;
    }

    /* ── rebuild workflow chips ────────────────────────────────────────────── */
    function _rebuildWfChips() {
        // remove old chips (keep the label span at index 0)
        while (_wfRow.children.length > 1) _wfRow.removeChild(_wfRow.lastChild);

        var all = document.createElement('span');
        all.className = 'rfc wfc' + (_st.wf ? '' : ' on');
        all.textContent = 'All';
        all.addEventListener('click', function () { _setWf(null); });
        _wfRow.appendChild(all);

        _getWorkflows().forEach(function (wf) {
            var c = document.createElement('span');
            c.className = 'rfc wfc' + (_st.wf === wf ? ' on' : '');
            c.textContent = wf;
            c.dataset.rfWf = wf;
            c.addEventListener('click', function () {
                _setWf(_st.wf === wf ? null : wf);
            });
            _wfRow.appendChild(c);
        });
    }

    /* ── rebuild output-index chips ────────────────────────────────────────── */
    function _rebuildOutChips(mx) {
        while (_outRow.children.length > 1) _outRow.removeChild(_outRow.lastChild);

        if (!mx || mx <= 1) { _outRow.style.display = 'none'; _sep.style.display = 'none'; return; }
        _outRow.style.display = 'flex';
        _sep.style.display = '';

        var allC = document.createElement('span');
        allC.className = 'rfc' + (_st.outs ? '' : ' on');
        allC.textContent = 'All';
        allC.addEventListener('click', function () { _st.outs = null; _rebuildOutChips(mx); _applyFilter(); });
        _outRow.appendChild(allC);

        for (var i = 1; i <= mx; i++) {
            (function (idx) {
                var c = document.createElement('span');
                c.className = 'rfc' + (_st.outs && _st.outs.has(idx) ? ' on' : '');
                c.textContent = idx;
                c.addEventListener('click', function () {
                    if (!_st.outs) _st.outs = new Set();
                    if (_st.outs.has(idx)) { _st.outs.delete(idx); if (!_st.outs.size) _st.outs = null; }
                    else _st.outs.add(idx);
                    _rebuildOutChips(mx);
                    _applyFilter();
                });
                _outRow.appendChild(c);
            }(i));
        }
    }

    /* ── set workflow ──────────────────────────────────────────────────────── */
    function _setWf(wf) {
        _st.wf   = wf;
        _st.outs = null;
        _clearWfHl();
        if (wf) {
            document.querySelectorAll('.unit[data-name="' + wf + '"]').forEach(function (el) {
                el.classList.add('rf-wf-hl');
            });
        }
        _rebuildWfChips();
        _rebuildOutChips(_maxOutsForWf(wf));
        _applyFilter();
    }

    /* ── apply filter ──────────────────────────────────────────────────────── */
    function _applyFilter() {
        document.querySelectorAll('#results .result-card').forEach(function (card) {
            var show = true;
            if (_st.active) {
                if (_st.wf && card.dataset.rfWf !== _st.wf) show = false;
                if (show && _st.outs && _st.outs.size) {
                    if (!_st.outs.has(parseInt(card.dataset.rfIdx) || 1)) show = false;
                }
            }
            card.classList.toggle('rf-hide', !show);
        });
    }

    /* ── tag new cards via addResultCard wrap ──────────────────────────────── */
    var _arcOrig = addResultCard;
    addResultCard = function (name, used, status, secs, vidUrl, imgUrl, rawOut) {
        _arcOrig(name, used, status, secs, vidUrl, imgUrl, rawOut);
        var grid = document.getElementById('results');
        if (!grid) return;
        var cards = grid.querySelectorAll('.result-card');
        var card  = cards[cards.length - 1];
        if (!card) return;
        var m = String(used).match(/\[(\d+)\/(\d+)\]$/);
        card.dataset.rfWf    = name;
        card.dataset.rfIdx   = m ? m[1] : '1';
        card.dataset.rfTotal = m ? m[2] : '1';
        if (_st.active) {
            var show = true;
            if (_st.wf && card.dataset.rfWf !== _st.wf) show = false;
            if (show && _st.outs && _st.outs.size) {
                if (!_st.outs.has(parseInt(card.dataset.rfIdx))) show = false;
            }
            if (!show) card.classList.add('rf-hide');
        }
        if (_st.active) { _rebuildWfChips(); _rebuildOutChips(_maxOutsForWf(_st.wf)); }
    };

    /* ── Run Order click → set workflow filter ─────────────────────────────── */
    var orderList = document.getElementById('orderList');
    if (orderList) {
        orderList.addEventListener('click', function (e) {
            if (!_st.active) return;
            var unit = e.target.closest('.unit[data-name]');
            if (!unit) return;
            e.stopPropagation();
            _setWf(_st.wf === unit.dataset.name ? null : unit.dataset.name);
        }, true);  // capture phase so it runs before drag handlers
    }

    /* ── expose reset for new-run SSE event ────────────────────────────────── */
    window._rebuildResultFilter = function () {
        _st.wf = null; _st.outs = null;
        _clearWfHl();
        _rebuildWfChips();
        _rebuildOutChips(0);
        _applyFilter();
    };

}());

// ── Parameter Promotion System ────────────────────────────────────────────────
(function () {

/* ── CSS ──────────────────────────────────────────────────────────────────── */
var _ppSty = document.createElement('style');
_ppSty.textContent =
    '.pp-ov{position:absolute;inset:0;z-index:25;background:var(--bg-primary);' +
    'display:flex;flex-direction:column;overflow:hidden}' +
    '.pp-hdr{display:flex;align-items:center;gap:10px;padding:10px 16px;' +
    'border-bottom:1px solid var(--border-primary);flex-shrink:0;' +
    'background:var(--bg-secondary)}' +
    '.pp-title{font-size:9px;letter-spacing:.15em;text-transform:uppercase;' +
    'color:var(--text-primary);flex:1}' +
    '.pp-wn{color:var(--accent-gold)}' +
    '.pp-body{display:flex;flex:1;overflow:hidden;min-height:0}' +
    '.pp-left{width:38%;border-right:1px solid var(--border-primary);' +
    'display:flex;flex-direction:column;overflow:hidden;min-width:200px}' +
    '.pp-right{flex:1;display:flex;flex-direction:column;overflow:hidden}' +
    '.pp-search{margin:7px;padding:5px 10px;background:var(--bg-tertiary);' +
    'border:1px solid var(--border-secondary);border-radius:3px;' +
    'color:var(--text-primary);font-family:inherit;font-size:10px;outline:none;' +
    'transition:border-color .15s}' +
    '.pp-search:focus{border-color:var(--accent-gold)}' +
    '.pp-plist{flex:1;overflow-y:auto;padding:0 7px 8px}' +
    '.pp-glbl{font-size:7px;letter-spacing:.12em;text-transform:uppercase;' +
    'color:var(--accent-gold);padding:8px 3px 3px;border-bottom:' +
    '1px solid var(--border-primary);margin-bottom:2px}' +
    '.pp-pi{display:flex;align-items:center;gap:6px;padding:3px 3px;' +
    'border-radius:2px;cursor:pointer;transition:background .1s}' +
    '.pp-pi:hover{background:var(--bg-tertiary)}' +
    '.pp-pi input[type=checkbox]{accent-color:var(--accent-gold);cursor:pointer;flex-shrink:0}' +
    '.pp-pname{font-size:10px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '.pp-pval{font-size:9px;color:var(--text-dim);flex-shrink:0;' +
    'max-width:68px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '.pp-pty{font-size:7px;color:var(--text-dim);border:1px solid var(--border-secondary);' +
    'padding:1px 3px;border-radius:2px;flex-shrink:0}' +
    '.pp-sw{font-size:9px;color:var(--warn);flex-shrink:0;cursor:help}' +
    '.pp-var-hdr{font-size:7px;letter-spacing:.14em;text-transform:uppercase;' +
    'color:var(--text-dim);padding:9px 13px 6px;border-bottom:' +
    '1px solid var(--border-primary);flex-shrink:0}' +
    '.pp-vwrap{flex:1;overflow:auto;padding:7px 11px}' +
    '.pp-vt{border-collapse:collapse;width:100%;min-width:340px}' +
    '.pp-vt th{font-size:8px;letter-spacing:.08em;text-transform:uppercase;' +
    'color:var(--text-dim);padding:4px 7px;border-bottom:' +
    '1px solid var(--border-primary);text-align:left;white-space:nowrap}' +
    '.pp-vt td{padding:3px 3px;border-bottom:1px solid var(--border-primary)}' +
    '.pp-vt input{background:var(--bg-tertiary);border:1px solid transparent;' +
    'color:var(--text-primary);font-family:inherit;font-size:10px;' +
    'padding:3px 6px;border-radius:2px;width:100%;min-width:54px;outline:none;' +
    'transition:border-color .15s;box-sizing:border-box}' +
    '.pp-vt input:focus{border-color:var(--accent-gold)}' +
    '.pp-vt .ll{min-width:78px}' +
    '.pp-db{background:none;border:none;color:var(--text-dim);' +
    'cursor:pointer;font-size:13px;padding:0 3px;line-height:1;transition:color .15s}' +
    '.pp-db:hover{color:var(--err)}' +
    '.pp-no-promoted{color:var(--text-dim);font-size:10px;padding:16px;text-align:center}' +
    '.pp-foot{display:flex;align-items:center;gap:8px;padding:8px 13px;' +
    'border-top:1px solid var(--border-primary);flex-shrink:0;' +
    'background:var(--bg-secondary)}' +
    '.pp-ar{font-size:8px;letter-spacing:.08em;text-transform:uppercase;' +
    'cursor:pointer;padding:4px 10px;border-radius:2px;' +
    'border:1px solid var(--border-secondary);color:var(--text-secondary);' +
    'background:transparent;transition:all .15s}' +
    '.pp-ar:hover{border-color:var(--accent-gold-dim);color:var(--accent-gold)}' +
    '.pp-aa{font-size:8px;letter-spacing:.08em;text-transform:uppercase;' +
    'cursor:pointer;padding:4px 13px;border-radius:2px;margin-left:auto;' +
    'border:1px solid var(--accent-gold);color:var(--accent-gold);' +
    'background:rgba(209,141,31,.1);transition:all .15s}' +
    '.pp-aa:hover{background:rgba(209,141,31,.22)}' +
    '.pp-cnt{font-size:8px;color:var(--text-dim)}' +
    '.pp-gb{margin-left:auto;flex-shrink:0;background:none;' +
    'border:1px solid transparent;color:var(--text-dim);' +
    'cursor:pointer;font-size:11px;padding:1px 5px;border-radius:2px;' +
    'line-height:1;transition:all .15s}' +
    '.pp-gb:hover{border-color:var(--accent-gold);color:var(--accent-gold)}' +
    '.pp-gb.cfg{color:var(--accent-gold);border-color:var(--accent-gold-dim)}' +
    '.unit.is-var{border-left:2px solid var(--accent-gold)!important;padding-left:5px}' +
    '.unit.is-var .ico{color:var(--accent-gold)!important}';
document.head.appendChild(_ppSty);

/* ── State ─────────────────────────────────────────────────────────────────── */
var _pCfg = {};  // { wfName: { promoted: Set<key>, variants: [{label, overrides}] } }
var _ppEl  = null;
var _pcfgHydrated = false;
function _rehydratePCfg(){
    if (typeof order === 'undefined' || !order) return;
    for (var i = 0; i < order.length; i++){
        var u = order[i];
        if (!u || u.type !== 'single' || !u.paramOverrides) continue;
        var keys = Object.keys(u.paramOverrides);
        if (!keys.length) continue;
        var nm = u.name;
        if (!_pCfg[nm]) _pCfg[nm] = { promoted: new Set(), variants: [] };
        var c = _pCfg[nm];
        keys.forEach(function(k){ c.promoted.add(k); });
        var lbl = 'v' + (c.variants.length + 1);
        if (typeof u.label === 'string'){
            var m = u.label.match(/\[([^\]]+)\]\s*$/);
            if (m) lbl = m[1];
        }
        if (!c.variants.some(function(v){ return v.label === lbl; })){
            c.variants.push({ label: lbl, overrides: Object.assign({}, u.paramOverrides) });
        }
    }
}

function _cfg(n) {
    if (!_pCfg[n]) _pCfg[n] = { promoted: new Set(), variants: [] };
    return _pCfg[n];
}

/* ── Extract all non-link inputs from a loaded workflow ───────────────────── */
function _extractParams(wfName) {
    var wf = (workflows[wfName] || {}).wf;
    if (!wf) return [];
    var out = [];
    Object.keys(wf).forEach(function (nid) {
        var node = wf[nid];
        if (!node || !node.class_type) return;
        Object.keys(node.inputs || {}).forEach(function (inp) {
            var val = node.inputs[inp];
            if (Array.isArray(val)) return;
            out.push({ key: nid+'.'+inp, nid: nid, inp: inp,
                       cls: node.class_type, def: val, vt: typeof val });
        });
    });
    out.sort(function (a, b) {
        return a.cls < b.cls ? -1 : a.cls > b.cls ? 1 :
               a.inp < b.inp ? -1 : a.inp > b.inp ? 1 : 0;
    });
    return out;
}

function _defVal(wfName, key) {
    var wf = (workflows[wfName] || {}).wf; if (!wf) return 0;
    var p = key.split('.'); var n = wf[p[0]];
    return (n && n.inputs) ? n.inputs[p[1]] : 0;
}

/* ── Open panel ──────────────────────────────────────────────────────────── */
function openParamPanel(wfName) {
    closeParamPanel();
    var cm = document.querySelector('.col.col-main') || document.querySelector('.col-main');
    if (!cm) return;
    cm.style.position = 'relative';

    var c   = _cfg(wfName);
    var ps  = _extractParams(wfName);

    var ov  = document.createElement('div'); ov.className = 'pp-ov'; _ppEl = ov;

    /* header */
    var hdr = document.createElement('div'); hdr.className = 'pp-hdr';
    var ttl = document.createElement('span'); ttl.className = 'pp-title';
    ttl.innerHTML = '<span class="pp-wn">'+escapeHtml(wfName)+'</span> \u2014 Promote Parameters';
    var xBtn = document.createElement('button');
    xBtn.className = 'btn btn-sm'; xBtn.textContent = '\u2715 Close';
    xBtn.onclick = closeParamPanel;
    hdr.appendChild(ttl); hdr.appendChild(xBtn); ov.appendChild(hdr);

    /* body */
    var body = document.createElement('div'); body.className = 'pp-body';

    /* LEFT */
    var lft = document.createElement('div'); lft.className = 'pp-left';
    var srch = document.createElement('input');
    srch.className = 'pp-search'; srch.placeholder = 'Search parameters\u2026'; srch.type = 'text';
    var pl = document.createElement('div'); pl.className = 'pp-plist';
    lft.appendChild(srch); lft.appendChild(pl);

    /* RIGHT */
    var rgt  = document.createElement('div'); rgt.className = 'pp-right';
    var rHdr = document.createElement('div'); rHdr.className = 'pp-var-hdr';
    rHdr.textContent = 'Variants \u2014 one row \u003d one run';
    var vw   = document.createElement('div'); vw.className = 'pp-vwrap';
    rgt.appendChild(rHdr); rgt.appendChild(vw);

    body.appendChild(lft); body.appendChild(rgt); ov.appendChild(body);

    /* footer */
    var foot = document.createElement('div'); foot.className = 'pp-foot';
    var arBtn = document.createElement('button'); arBtn.className = 'pp-ar'; arBtn.textContent = '+ Add row';
    var cntSp = document.createElement('span');  cntSp.className = 'pp-cnt';
    var aaBtn = document.createElement('button'); aaBtn.className = 'pp-aa';
    foot.appendChild(arBtn); foot.appendChild(cntSp); foot.appendChild(aaBtn);
    ov.appendChild(foot);
    cm.appendChild(ov);

    /* ── table renderer ──────────────────────────────────────────────────── */
    function renderTable() {
        vw.innerHTML = '';
        var promo = Array.from(c.promoted);
        cntSp.textContent = c.variants.length + ' variant' + (c.variants.length === 1 ? '' : 's');
        aaBtn.textContent  = '\u2713 Add to Run Order ('+(1+c.variants.length)+' units)';

        if (!promo.length) {
            vw.innerHTML = '<div class="pp-no-promoted">Check parameters on the left to create columns.</div>';
            return;
        }
        var tbl = document.createElement('table'); tbl.className = 'pp-vt';
        var thead = tbl.createTHead(); var hr = thead.insertRow();
        ['Label'].concat(promo.map(function(k){ return k.split('.')[1]; })).concat([''])
            .forEach(function(h){ var th = document.createElement('th'); th.textContent = h; hr.appendChild(th); });
        var tb = tbl.createTBody();
        c.variants.forEach(function(v, ri){
            var tr = tb.insertRow();
            /* label */
            var tdl = tr.insertCell(); var li = document.createElement('input');
            li.className = 'll'; li.value = v.label;
            li.addEventListener('input', function(){ v.label = li.value; cntSp.textContent = c.variants.length+' variant'+(c.variants.length===1?'':'s'); aaBtn.textContent='\u2713 Add to Run Order ('+(1+c.variants.length)+' units)'; });
            tdl.appendChild(li);
            /* param cells */
            promo.forEach(function(key){
                var td = tr.insertCell(); var inp = document.createElement('input');
                var cur = v.overrides.hasOwnProperty(key) ? v.overrides[key] : _defVal(wfName, key);
                inp.value = String(cur !== undefined ? cur : '');
                inp.type  = typeof cur === 'number' ? 'number' : 'text';
                if (inp.type === 'number') inp.step = 'any';
                inp.addEventListener('input', function(){
                    var n = parseFloat(inp.value);
                    v.overrides[key] = isNaN(n) ? inp.value : n;
                });
                td.appendChild(inp);
            });
            /* delete */
            var tdd = tr.insertCell(); var db = document.createElement('button');
            db.className = 'pp-db'; db.textContent = '\u00d7'; db.title = 'Remove variant';
            db.addEventListener('click', (function(i){ return function(){ c.variants.splice(i,1); renderTable(); }; })(ri));
            tdd.appendChild(db);
        });
        vw.appendChild(tbl);
    }

    /* ── param list renderer ─────────────────────────────────────────────── */
    function renderParams(q) {
        pl.innerHTML = ''; q = (q||'').toLowerCase();
        var grp = {};
        ps.forEach(function(p){
            if (q && p.key.toLowerCase().indexOf(q)===-1 && p.cls.toLowerCase().indexOf(q)===-1) return;
            if (!grp[p.cls]) grp[p.cls] = [];
            grp[p.cls].push(p);
        });
        Object.keys(grp).sort().forEach(function(cls){
            var gl = document.createElement('div'); gl.className = 'pp-glbl'; gl.textContent = cls;
            pl.appendChild(gl);
            grp[cls].forEach(function(p){
                var row = document.createElement('div'); row.className = 'pp-pi';
                var cb  = document.createElement('input'); cb.type = 'checkbox'; cb.checked = c.promoted.has(p.key);
                var nm  = document.createElement('span'); nm.className = 'pp-pname'; nm.textContent = p.inp;
                var vl  = document.createElement('span'); vl.className = 'pp-pval';
                vl.textContent = String(p.def).slice(0,22); vl.title = String(p.def);
                var ty  = document.createElement('span'); ty.className = 'pp-pty';
                ty.textContent = p.vt === 'number' ? (Number.isInteger(p.def) ? 'int' : 'float') : 'str';
                row.appendChild(cb); row.appendChild(nm); row.appendChild(vl); row.appendChild(ty);
                if (p.inp === 'seed' || p.inp === 'noise_seed') {
                    var sw = document.createElement('span'); sw.className = 'pp-sw';
                    sw.textContent = '\u26a0'; sw.title = 'Seed affects reproducibility'; row.appendChild(sw);
                }
                cb.addEventListener('change', function(){
                    if (cb.checked) {
                        c.promoted.add(p.key);
                        c.variants.forEach(function(v){ if (!v.overrides.hasOwnProperty(p.key)) v.overrides[p.key] = p.def; });
                    } else { c.promoted.delete(p.key); }
                    renderTable(); _refreshGear();
                });
                row.addEventListener('click', function(e){ if (e.target===cb) return; cb.checked=!cb.checked; cb.dispatchEvent(new Event('change')); });
                pl.appendChild(row);
            });
        });
    }

    srch.addEventListener('input', function(){ renderParams(srch.value); });
    arBtn.addEventListener('click', function(){
        var ov2 = {}; c.promoted.forEach(function(k){ ov2[k] = _defVal(wfName,k); });
        var maxN = 0;
        c.variants.forEach(function(v){ var m = (v.label||'').match(/^v(\d+)$/); if (m){ var n = parseInt(m[1],10); if (n > maxN) maxN = n; } });
        if (typeof order !== 'undefined' && order){
            order.forEach(function(u){
                if (!u || u.type !== 'single' || u.name !== wfName || typeof u.label !== 'string') return;
                var m = u.label.match(/\[v(\d+)\]\s*$/);
                if (m){ var n = parseInt(m[1],10); if (n > maxN) maxN = n; }
            });
        }
        c.variants.push({ label: 'v'+(maxN+1), overrides: ov2 });
        renderTable();
    });
    aaBtn.addEventListener('click', function(){ _addAll(wfName); });

    renderParams(''); renderTable(); srch.focus();
}

function closeParamPanel() {
    if (_ppEl) { _ppEl.remove(); _ppEl = null; }
}

/* ── Add original + all variants to run order ────────────────────────────── */
function _addAll(wfName) {
    var c = _pCfg[wfName]; if (!c) return;
    order.push({ type:'single', name: wfName });
    c.variants.forEach(function(v){
        order.push({ type:'single', name: wfName,
                     label: wfName+' ['+v.label+']',
                     paramOverrides: Object.assign({}, v.overrides) });
    });
    renderOrder(); renderGraph(); updateRunButton();
    closeParamPanel();
    log('Added '+(1+c.variants.length)+' unit(s) from \''+wfName+'\' to run order.', 'ok');
}

/* ── Wrap renderAvail: inject ⚙ gear button ──────────────────────────────── */
function _refreshGear() { /* gear lives in Run Order tab only */ }

function _itemName(item) {
    var sp = item.querySelectorAll('span:not(.seq)');
    for (var i=0;i<sp.length;i++){
        var t = sp[i].textContent.split('\u00b7')[0].trim();
        if (t && workflows[t]) return t;
    }
    return item.dataset.name || null;
}

var _raOrig = renderAvail;
renderAvail = function(){ _raOrig(); _refreshGear(); };

/* ── Wrap renderOrder: style variant units ───────────────────────────────── */
var _roOrig = renderOrder;
renderOrder = function(){
    _roOrig();
    if (!_pcfgHydrated && order && order.length){ _rehydratePCfg(); _pcfgHydrated = true; }
    var ol = document.getElementById('orderList'); if (!ol) return;
    ol.querySelectorAll('.unit[data-unit-idx]').forEach(function(div){
        var idx = parseInt(div.dataset.unitIdx);
        if (isNaN(idx) || idx >= order.length) return;
        var u = order[idx]; if (!u || u.type !== 'single') return;
        // data-key: unique per-unit coloring target (label beats name for variants)
        var _ukey = u.label || u.name;
        div.dataset.key = _ukey;
        // variant styling
        if (u.paramOverrides && Object.keys(u.paramOverrides).length) {
            div.classList.add('is-var');
            var ico = div.querySelector('.ico'); if (ico) ico.textContent = '\u25c9';
            var lbl = div.querySelector('.lbl'); if (lbl && u.label) lbl.textContent = u.label;
            div.dataset.name = u.label;   // keep data-name consistent for filter/highlight
        }
    });
};

}());
// ══ end Parameter Promotion ═══════════════════════════════════════════════════

// ── Desktop VRAM bar ─────────────────────────────────────────────────────────
(function () {
    if (!WEDGE_SERVER) return;   // no server = no proxy = skip

    // ── CSS ──────────────────────────────────────────────────────────────────
    var _sty = document.createElement('style');
    _sty.textContent =
        '#dVramFill{transition:width .6s,background .4s,box-shadow .4s}' +
        '#dVramPct{font-size:9px;color:var(--text-dim);min-width:102px;' +
        'text-align:right;white-space:nowrap;flex-shrink:0}' +
        '.d-gpu-lbl{font-size:8px;color:var(--text-dim);letter-spacing:.06em;' +
        'padding:2px 0 0 56px;line-height:1.4}';
    document.head.appendChild(_sty);

    // ── Inject VRAM row into .pbars after the batch row ───────────────────
    var batchFill = document.getElementById('batchFill');
    if (!batchFill) return;
    var pbars = batchFill.closest('.pbars');
    if (!pbars) return;

    var vrow = document.createElement('div');
    vrow.className = 'pbar-row';
    vrow.style.marginTop = '4px';
    vrow.innerHTML =
        '<span class="pbar-lbl">VRAM</span>' +
        '<div class="pbar-track">' +
        '  <div class="pbar-fill" id="dVramFill" style="width:0%;background:#5a9fd4"></div>' +
        '</div>' +
        '<span id="dVramPct">\u2014</span>';

    var gpuLbl = document.createElement('div');
    gpuLbl.className = 'd-gpu-lbl';
    gpuLbl.id = 'dGpuName';

    // Insert after batch row — find the batch row's parent's next pbar-row
    var batchRow = batchFill.closest('.pbar-row');
    var nextRow  = batchRow ? batchRow.nextElementSibling : null;
    if (nextRow) {
        pbars.insertBefore(vrow,   nextRow);
        pbars.insertBefore(gpuLbl, nextRow);
    } else {
        pbars.appendChild(vrow);
        pbars.appendChild(gpuLbl);
    }

    // ── Poll system_stats and update the bar ─────────────────────────────
    function _pollVram() {
        fetch(WEDGE_SERVER + '/comfy_proxy/system_stats', {
            signal: AbortSignal.timeout(3000)
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (!d.devices || !d.devices.length) return;
            var dev  = d.devices[0];
            var tot  = dev.vram_total || 0;
            var free = dev.vram_free  || 0;
            var used = tot - free;
            var pct  = tot > 0 ? (used / tot * 100) : 0;

            var fill = document.getElementById('dVramFill');
            var pctE = document.getElementById('dVramPct');
            var gpu  = document.getElementById('dGpuName');

            if (fill) {
                fill.style.width      = pct.toFixed(1) + '%';
                fill.style.background = pct > 85 ? 'var(--err)' :
                                        pct > 65 ? 'var(--warn)' : '#5a9fd4';
                fill.style.boxShadow  = pct > 85 ? '0 0 8px rgba(255,107,107,.4)' :
                                        pct > 65 ? '0 0 6px rgba(240,182,86,.3)' : 'none';
            }
            if (pctE) {
                pctE.textContent = (used  / 1073741824).toFixed(1) +
                                   ' / '  +
                                   (tot   / 1073741824).toFixed(1) + ' GB';
            }
            if (gpu && dev.name && !gpu.textContent) gpu.textContent = dev.name;
        })
        .catch(function () {});
    }

    _pollVram();
    setInterval(_pollVram, 4000);
}());

// ── Run Order features: chain-from-order · dedup · collapse workflows ─────────
(function () {

/* ── CSS ──────────────────────────────────────────────────────────────────── */
var _sty = document.createElement('style');
_sty.textContent =
    /* chain-select highlight on unit rows */
    '.unit.oc-sel{outline:2px solid var(--accent-gold)!important;' +
    'outline-offset:-2px;background:rgba(209,141,31,.06)!important}' +

    /* chain-mode action bar below col-order header */
    '.oc-bar{display:none;align-items:center;gap:6px;padding:6px 12px;' +
    'background:rgba(209,141,31,.07);border-bottom:1px solid var(--border-primary);' +
    'flex-shrink:0}' +
    '.oc-bar.on{display:flex}' +
    '.oc-hint{font-size:8px;letter-spacing:.1em;text-transform:uppercase;' +
    'color:var(--accent-gold);flex:1}' +

    /* small icon buttons in col-head */
    '.col-icon-btn{background:none;border:1px solid transparent;' +
    'color:var(--text-dim);cursor:pointer;font-size:11px;padding:2px 6px;' +
    'border-radius:2px;line-height:1;transition:all .15s;flex-shrink:0}' +
    '.col-icon-btn:hover{border-color:var(--border-secondary);color:var(--text-primary)}' +
    '.col-icon-btn.active{border-color:var(--accent-gold);color:var(--accent-gold)}' +

    /* collapse / expand */
    '.col.col-avail{transition:width .22s ease,min-width .22s ease}' +
    '.col.col-avail.av-col{width:28px!important;min-width:28px;overflow:hidden}' +
    '.col.col-avail.av-col .col-body,' +
    '.col.col-avail.av-col #serverFolderRow,' +
    '.col.col-avail.av-col .col-head>span,' +
    '.col.col-avail.av-col .col-head>.btn,' +
    '.col.col-avail.av-col .sel-info,' +
    '.col.col-avail.av-col .sel-row{display:none!important}' +
    '.col.col-avail.av-col .col-head{justify-content:center;padding:10px 0}' +
    '.av-expand-btn{display:none}' +
    '.col.col-avail.av-col .av-expand-btn{display:flex!important}' +
    '.col.col-avail.av-col .av-collapse-btn{display:none!important}';
document.head.appendChild(_sty);

/* ── state ─────────────────────────────────────────────────────────────────── */
var _ocMode = false;   // chain-selection mode active
var _ocSel  = [];      // array of order indices selected for chaining

/* ── inject buttons into col-avail header ────────────────────────────────── */
var avHead = document.querySelector('.col.col-avail .col-head');
if (avHead) {
    var colBtn = document.createElement('button');
    colBtn.className  = 'col-icon-btn av-collapse-btn';
    colBtn.title      = 'Collapse Workflows panel';
    colBtn.textContent = '\u00ab';
    colBtn.onclick    = function () { _toggleAvail(true); };

    var expBtn = document.createElement('button');
    expBtn.className  = 'col-icon-btn av-expand-btn';
    expBtn.title      = 'Expand Workflows panel';
    expBtn.textContent = '\u00bb';
    expBtn.onclick    = function () { _toggleAvail(false); };

    avHead.appendChild(colBtn);
    avHead.appendChild(expBtn);
}

/* ── move sel-info + sel-row (chain UI) from col-avail → col-order ─────────────── */
(function() {
    var selInfo = document.getElementById('selInfo');
    var selRow  = document.querySelector('.col-avail .sel-row');
    var orCol   = document.querySelector('.col.col-order');
    if (!selInfo || !selRow || !orCol) return;
    var orHead  = orCol.querySelector('.col-head');
    var after   = orHead ? orHead.nextSibling : null;
    orCol.insertBefore(selInfo, after);
    orCol.insertBefore(selRow,  selInfo.nextSibling);
    selInfo.style.cssText += ';padding:5px 14px;border-bottom:1px solid var(--border-primary);font-size:9px;';
    selRow.style.cssText  += ';padding:5px 12px;border-bottom:1px solid var(--border-primary);gap:6px';
}())

/* ── collapse / expand ────────────────────────────────────────────────────── */
function _toggleAvail(collapse) {
    var col = document.querySelector('.col.col-avail');
    if (col) col.classList.toggle('av-col', collapse);
}

/* ── chain-select mode ────────────────────────────────────────────────────── */
function _ocToggle() {
    _ocMode = !_ocMode;
    _ocSel  = [];
    _ocUpdateUI();
    renderOrder();
}
window._ocToggle = _ocToggle;

function _ocCancel() {
    _ocMode = false;
    _ocSel  = [];
    _ocUpdateUI();
    renderOrder();
}
window._ocCancel = _ocCancel;

function _ocUpdateUI() {
    var btn  = document.getElementById('ocBtn');
    var bar  = document.getElementById('ocBar');
    var hint = document.getElementById('ocHint');
    if (btn)  btn.classList.toggle('active', _ocMode);
    if (bar)  bar.classList.toggle('on', _ocMode);
    if (hint) hint.textContent = _ocMode
        ? ('\u26d3 ' + _ocSel.length + ' selected \u2014 click units to add/remove')
        : '\u26d3 select units to chain';
}

function _ocMakeChain() {
    if (_ocSel.length < 2) {
        alert('Select at least 2 units in the Run Order to chain.');
        return;
    }
    var sorted = _ocSel.slice().sort(function(a,b){ return a-b; });
    var names  = [];
    sorted.forEach(function(idx) {
        var u = order[idx];
        if (u && u.type === 'single') names.push(u.name);
    });
    if (names.length < 2) {
        alert('Only single-workflow units can be chained (not existing chains).');
        return;
    }
    /* remove selected units and insert the new chain at the first position */
    var insertAt = sorted[0];
    var newOrder = [];
    for (var i = 0; i < order.length; i++) {
        if (!_ocSel.includes(i)) newOrder.push(order[i]);
    }
    newOrder.splice(insertAt, 0, {type:'chain', names:names, mode:'success'});
    order.length = 0;
    newOrder.forEach(function(u){ order.push(u); });
    _ocMode = false;
    _ocSel  = [];
    _ocUpdateUI();
    renderOrder();
    renderGraph();
    updateRunButton();
    log('Chain created from ' + names.length + ' units.', 'ok');
}
window._ocMakeChain = _ocMakeChain;

/* ── delegated click on orderList for chain-select mode ─────────────────── */
var orderListEl = document.getElementById('orderList');
if (orderListEl) {
    orderListEl.addEventListener('click', function(e) {
        if (!_ocMode) return;
        var div = e.target.closest('.unit');
        if (!div) return;
        var idx = parseInt(div.dataset.unitIdx);
        if (isNaN(idx)) return;
        /* only single-workflow units can be chain-selected */
        var u = order[idx];
        if (!u || u.type !== 'single') return;
        var pos = _ocSel.indexOf(idx);
        if (pos >= 0) _ocSel.splice(pos, 1);
        else _ocSel.push(idx);
        e.stopPropagation();
        _ocUpdateUI();
        renderOrder();
    }, true);   /* capture: runs before drag handlers */
}

/* ── extend renderOrder wrap to paint oc-sel highlight ─────────────────── */
var _roForOc = renderOrder;
renderOrder = function () {
    _roForOc();
    if (!_ocMode) return;
    var ol = document.getElementById('orderList');
    if (!ol) return;
    ol.querySelectorAll('.unit[data-unit-idx]').forEach(function(div) {
        var idx = parseInt(div.dataset.unitIdx);
        div.classList.toggle('oc-sel', _ocSel.indexOf(idx) >= 0);
    });
};

/* ── dedup ──────────────────────────────────────────────────────────────── */
function _unitKey(u) {
    if (u.type === 'chain')
        return 'chain\u0000' + (u.names||[]).join(',') + '\u0000' + (u.mode||'success');
    /* for single units: compare by label (includes variant suffix) + overrides */
    var po   = u.paramOverrides || {};
    var keys = Object.keys(po).sort();
    var ovr  = keys.map(function(k){ return k+'='+po[k]; }).join(',');
    return 'single\u0000' + (u.label||u.name) + '\u0000' + ovr;
}

function _dedup() {
    var seen = new Set();
    var before = order.length;
    var kept = order.filter(function(u) {
        var k = _unitKey(u);
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
    });
    var removed = before - kept.length;
    if (!removed) { log('No duplicates found.', 'muted'); return; }
    order.length = 0;
    kept.forEach(function(u){ order.push(u); });
    renderOrder();
    renderGraph();
    updateRunButton();
    log('Removed ' + removed + ' duplicate unit' + (removed===1?'':'s') + '.', 'ok');
}

}());
// ══ end Run Order features ════════════════════════════════════════════════════

// ── Live UI link in desktop toolbar ──────────────────────────────────────────
(function () {
    if (!WEDGE_SERVER) return;
    var stop = document.getElementById('stopBtn');
    if (!stop) return;
    var a = document.createElement('a');
    a.href      = '/live';
    a.target    = '_blank';
    a.rel       = 'noopener';
    a.textContent = 'Live UI';
    a.style.cssText =
        'font-size:8px;letter-spacing:.1em;text-transform:uppercase;' +
        'color:var(--text-dim);text-decoration:none;padding:3px 8px;' +
        'border:1px solid var(--border-secondary);border-radius:2px;' +
        'margin-left:6px;transition:color .15s,border-color .15s;' +
        'white-space:nowrap;line-height:1;align-self:center;flex-shrink:0';
    a.onmouseover = function(){ a.style.color='var(--accent-gold)'; a.style.borderColor='var(--accent-gold-dim)'; };
    a.onmouseout  = function(){ a.style.color='var(--text-dim)';    a.style.borderColor='var(--border-secondary)'; };
    stop.parentNode.insertBefore(a, stop.nextSibling);
}());
// ══ end Phase 2 ══════════════════════════════════════════════════════════════

// ── Restart Wedge Studio ─────────────────────────────────────────────────────
function restartWedge() {
    if (!confirm('Restart Wedge Studio?\nComfyUI will also be restarted.\nPage will reload when back online.')) return;
    log('\u21bb Restarting Wedge Studio + ComfyUI\u2026', 'warn');
    var _cpPath = (document.getElementById('comfyPath')||{}).value||'';
    fetch(WEDGE_SERVER + '/restart_wedge', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({comfy_path: _cpPath})
    }).catch(function(){});
    log('   Server restarting \u2014 waiting\u2026', 'warn');
    var _wsWaited = 0;
    var _wsIv = setInterval(function() {
        _wsWaited += 2000;
        fetch(WEDGE_SERVER + '/get_config', {signal: AbortSignal.timeout(2000)})
            .then(function(r) {
                if (r.ok) {
                    clearInterval(_wsIv);
                    log('   \u2713 Server back online \u2014 reloading\u2026', 'ok');
                    setTimeout(function() { window.location.reload(); }, 600);
                }
            }).catch(function() {
                if (_wsWaited >= 60000) {
                    clearInterval(_wsIv);
                    log('   Server did not respond in 60s \u2014 reload manually', 'err');
                }
            });
    }, 2000);
}

// inject Restart button after stopBtn
(function() {
    var sb = document.getElementById('stopBtn');
    if (!sb) return;
    var btn = document.createElement('button');
    btn.className    = 'btn btn-sm';
    btn.id           = 'restartWedgeBtn';
    btn.title        = 'Restart Wedge Studio server and reload page';
    btn.textContent  = '\u21bb Restart';
    btn.style.cssText = 'opacity:.65;margin-left:4px;';
    btn.onclick      = restartWedge;
    sb.parentNode.insertBefore(btn, sb.nextSibling);
}());
"""


def _build_html():
    """Serve HTML with Phase 1 SSE client code injected before init calls."""
    return HTML.replace('loadBakedPlan();', _SSE_JS + 'loadBakedPlan();', 1)

# ── Phase 2: Python background executor ──────────────────────────────────────
import math     as _math
import urllib.request as _urllib_req

_executor_stop   = threading.Event()  # set() to request a stop
_executor_lock   = threading.Lock()   # one run at a time
_executor_thread = None               # active Thread | None


def _e_log(msg, tag='info'):
    """Append one log line to _run_state and broadcast; safe to call from executor thread."""
    with _state_lock:
        tail = _run_state.setdefault('log_tail', [])
        import time as _t2
        tail.append({'msg': msg, 'tag': tag,
                     'ts': _time_mod.strftime('%H:%M:%S', _time_mod.localtime())})
        if len(tail) > 200:
            _run_state['log_tail'] = tail[-200:]
        _run_state['ts'] = _time_mod.time()
        _push_to_clients()


def _e_free_vram(comfy_url):
    _e_log('  ↺ Clearing VRAM…', 'muted')
    try:
        req = _urllib_req.Request(
            f'http://{comfy_url}/free',
            data=json.dumps({'unload_models': True, 'free_memory': True}).encode(),
            headers={'Content-Type': 'application/json'}, method='POST')
        _urllib_req.urlopen(req, timeout=30)
        _e_log('  ✓ VRAM cleared', 'ok')
    except Exception as _fe:
        _e_log(f'  VRAM clear failed: {_fe}', 'warn')


def _e_rewrite_prefix(wf, name):
    _OUTPUT_TYPES = {
        'SaveVideo': 'filename_prefix', 'VHS_VideoCombine': 'filename_prefix',
        'SaveImage': 'filename_prefix', 'SaveAudio': 'filename_prefix',
    }
    for node in wf.values():
        if not isinstance(node, dict): continue
        key = _OUTPUT_TYPES.get(node.get('class_type', ''))
        if key and isinstance(node.get('inputs'), dict) and key in node['inputs']:
            node['inputs'][key] = 'wedge/' + name


def _e_safe_prefix(s):
    """Strip path separators / control chars from a label so it's safe as a
    ComfyUI filename_prefix. Keeps brackets and spaces (filesystem-safe)."""
    if not s: return ''
    out = []
    for ch in str(s):
        if ch in '/\\:*?"<>|' or ord(ch) < 32:
            out.append('_')
        else:
            out.append(ch)
    return ''.join(out).strip()


def _e_run_one(name, wf_json, comfy_url, timeout_s, prefix=None):
    """Submit workflow to ComfyUI, poll until done. Returns result dict.
    prefix overrides filename_prefix on save nodes (defaults to name) so
    variants produce distinct files instead of clobbering each other."""
    wf = json.loads(json.dumps(wf_json))
    _e_rewrite_prefix(wf, _e_safe_prefix(prefix) if prefix else name)
    client_id = f'wedge_py_{int(_time_mod.time()*1000)}'
    t0 = _time_mod.time()

    # ── submit ────────────────────────────────────────────────────────────────
    try:
        req = _urllib_req.Request(
            f'http://{comfy_url}/prompt',
            data=json.dumps({'prompt': wf, 'client_id': client_id}).encode(),
            headers={'Content-Type': 'application/json'}, method='POST')
        with _urllib_req.urlopen(req, timeout=10) as r:
            pid = json.loads(r.read()).get('prompt_id')
        if not pid:
            return {'ok': False, 'status': 'no_id', 'secs': 0, 'outs': []}
    except Exception as e:
        return {'ok': False, 'status': f'queue_error: {e}', 'secs': 0, 'outs': []}

    deadline = t0 + timeout_s

    # ── poll ─────────────────────────────────────────────────────────────────
    while _time_mod.time() < deadline:
        if _executor_stop.is_set():
            for ep in ('/interrupt', '/queue'):
                try:
                    body = b'{}' if ep == '/interrupt' else json.dumps({'clear': True}).encode()
                    req = _urllib_req.Request(f'http://{comfy_url}{ep}', data=body,
                          headers={'Content-Type': 'application/json'}, method='POST')
                    _urllib_req.urlopen(req, timeout=3)
                except Exception: pass
            return {'ok': False, 'status': 'interrupted', 'secs': _time_mod.time()-t0, 'outs': []}

        try:
            with _urllib_req.urlopen(f'http://{comfy_url}/history/{pid}', timeout=5) as r:
                hist = json.loads(r.read())
            if pid in hist:
                entry = hist[pid]
                st = entry.get('status', {})
                ok = st.get('status_str') == 'success' or st.get('completed') is True
                outs = []
                for node in entry.get('outputs', {}).values():
                    for kind in ('videos', 'gifs', 'images', 'audio'):
                        for item in node.get(kind, []):
                            if item.get('filename'):
                                outs.append({'sub': item.get('subfolder', ''),
                                             'fn': item['filename'],
                                             'type': item.get('type', 'output')})
                return {'ok': ok, 'status': 'ok' if ok else 'check',
                        'secs': _time_mod.time()-t0, 'outs': outs}
        except Exception:
            pass

        # sigmoid progress estimate (no WS in Phase 2 — capped at 95%)
        elapsed = _time_mod.time() - t0
        est = min(95.0, 100.0 * (1.0 - _math.exp(-elapsed / max(1.0, timeout_s * 0.15))))
        _broadcast({'job_pct': est})
        _time_mod.sleep(1.5)

    # ── timeout ───────────────────────────────────────────────────────────────
    try:
        req = _urllib_req.Request(f'http://{comfy_url}/interrupt', data=b'{}',
              headers={'Content-Type': 'application/json'}, method='POST')
        _urllib_req.urlopen(req, timeout=3)
    except Exception: pass
    return {'ok': False, 'status': 'timeout', 'secs': _time_mod.time()-t0, 'outs': []}


def _e_run_link(name, wf_cache, comfy_url, timeout_s, unit_statuses, session_results,
                cache_key=None, prefix=None):
    """Run one workflow. cache_key gives variants unique session-cache entries.
    prefix is forwarded to _e_run_one for variant-aware output filenames."""
    _key = cache_key if cache_key is not None else name

    if _key in session_results:
        r = session_results[_key]
        unit_statuses[_key] = {'state': 'ok' if r['ok'] else 'fail', 'reused': True}
        _broadcast({'unit_statuses': dict(unit_statuses)})
        _e_log(f"    '{_key}' already done this session \u2014 reusing", 'muted')
        return {**r, 'used': _key}

    unit_statuses[_key] = {'state': 'running', 'reused': False}
    _broadcast({'unit_statuses': dict(unit_statuses), 'job_pct': 0.0})
    _e_log(f"  running '{_key}' \u2026", 'running')

    wf = wf_cache.get(name)   # file lookup always uses base name
    if not wf:
        _e_log(f"  {_key}: workflow file not found in workflow folder", 'err')
        result = {'ok': False, 'status': 'missing', 'secs': 0.0, 'outs': []}
    else:
        result = _e_run_one(name, wf, comfy_url, timeout_s, prefix=prefix)

    session_results[_key] = result
    _st       = result.get('status', '')
    state_str = 'ok' if result['ok'] else 'fail'
    unit_statuses[_key] = {'state': state_str, 'reused': False}
    _broadcast({'unit_statuses': dict(unit_statuses),
                'job_pct': 100.0 if result['ok'] else 0.0})
    # status-aware log message and tag
    if result['ok']:
        _msg, _tag = '\u2713 OK', 'ok'
    elif _st == 'timeout':
        _msg, _tag = f'\u2717 TIMEOUT (limit {timeout_s/60:.0f} min)', 'warn'
    elif _st == 'interrupted':
        _msg, _tag = '\u29d2 stopped by user', 'muted'
    elif _st == 'missing':
        _msg, _tag = '\u2717 workflow file not found', 'err'
    elif _st and _st.startswith('queue_error'):
        _msg, _tag = f'\u2717 queue error: {_st[13:]}', 'err'
    else:
        _msg, _tag = 'finished \u2014 check ComfyUI output', 'warn'
    _e_log(f'    {_msg} in {result["secs"]:.1f}s', _tag)
    return {**result, 'used': _key}

def _e_restart_comfy(comfy_url):
    # Kill + relaunch ComfyUI, then wait for it to come back online.
    _e_log('  Restarting ComfyUI...', 'warn')
    _cf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
    try:
        _cd = json.loads(open(_cf).read()) if os.path.exists(_cf) else {}
        comfy_path = os.path.abspath(_cd.get('comfy_path', '').strip() or '')
    except Exception:
        comfy_path = ''
    if not comfy_path:
        _e_log('  RSTRT: ComfyUI folder not set in header settings', 'err'); return
    killed = False
    try:
        import psutil as _pu
        our_pid = os.getpid()
        cands = []
        for proc in _pu.process_iter(['pid', 'name', 'cmdline', 'cwd']):
            try:
                if proc.pid == our_pid: continue
                cmd = ' '.join(proc.info['cmdline'] or [])
                cwd = (proc.info['cwd'] or '').lower()
                if 'main.py' in cmd and (comfy_path.lower() in cwd or
                        'comfyui' in cmd.lower() or 'comfyui' in cwd):
                    cands.append(proc)
            except Exception: pass
        if cands:
            tgt = sorted(cands, key=lambda p: p.create_time())[-1]
            _e_log(f'  Killing ComfyUI PID {tgt.pid}', 'warn')
            tgt.kill(); tgt.wait(timeout=5); killed = True
        else:
            _e_log('  No ComfyUI process found via psutil', 'warn')
    except ImportError:
        if sys.platform.startswith('win'):
            r = os.system('taskkill /F /FI "WINDOWTITLE eq *ComfyUI*" 2>nul')
            if r != 0:
                _e_log('  taskkill failed - install psutil for reliable kills', 'warn')
    import time as _tm
    _tm.sleep(2)
    main_py = os.path.join(comfy_path, 'main.py')
    if not os.path.exists(main_py):
        _e_log(f'  RSTRT: main.py not found at {comfy_path}', 'err'); return
    venv_py = os.path.join(comfy_path, 'venv', 'Scripts', 'python.exe')
    emb_py  = os.path.join(comfy_path, 'python_embeded', 'python.exe')
    python_exe = (venv_py if os.path.exists(venv_py) else
                  emb_py  if os.path.exists(emb_py)  else sys.executable)
    import subprocess as _sp
    flags = _sp.CREATE_NEW_CONSOLE if sys.platform.startswith('win') else 0
    _sp.Popen([python_exe, main_py, '--enable-cors-header', '*'],
              cwd=comfy_path, creationflags=flags)
    _e_log(f'  Relaunching ComfyUI from {comfy_path}...', 'warn')
    import urllib.request as _ur
    host = comfy_url if '://' not in comfy_url else comfy_url.split('://', 1)[1]
    stats_url = f'http://{host}/system_stats'
    deadline = _tm.time() + 90
    while _tm.time() < deadline:
        try:
            _ur.urlopen(stats_url, timeout=3)
            _e_log('  ComfyUI is back online', 'ok'); return
        except Exception: pass
        _tm.sleep(3)
    _e_log('  ComfyUI restart timeout - continuing anyway', 'warn')


def _save_wedge_variant(wf, base_name, label, wf_folder):
    """Save a resolved workflow copy (overrides applied) to _wedge/ subfolder."""
    try:
        import re as _re
        wedge_dir = Path(wf_folder).resolve() / '_wedge'
        wedge_dir.mkdir(exist_ok=True)
        safe = _re.sub(r'[^\w\-\.\[\] ]', '_', label).strip()
        dest = wedge_dir / f'{safe}.json'
        dest.write_text(json.dumps(wf, indent=2), encoding='utf-8')
        _e_log(f'  ✓ _wedge/{safe}.json saved', 'muted')
    except Exception as _sve:
        _e_log(f'  ⚠ _wedge save failed for {label!r}: {_sve}', 'warn')


def _run_executor(order, comfy_url, timeout_s, wf_folder):
    """Background executor thread — runs the full batch via ComfyUI REST."""
    global _executor_thread
    try:
        # ── load workflow JSONs from disk ─────────────────────────────────────
        wf_dir = Path(wf_folder).resolve() if wf_folder else \
                 Path(os.path.abspath(__file__)).parent
        wf_cache = {}
        for unit in order:
            names = [unit['name']] if unit['type'] == 'single' else unit.get('names', [])
            for n in names:
                if n not in wf_cache:
                    p = wf_dir / (n + '.json')
                    try:   wf_cache[n] = json.loads(p.read_text(encoding='utf-8'))
                    except Exception: wf_cache[n] = None

        # ── working copy of order (tracks _status per unit) ──────────────────
        work = [dict(u) for u in order]
        unit_statuses  = {}
        results_list   = []
        session_results = {}
        ok_count = 0
        total = len(work)

        _broadcast({'running': True, 'job_pct': 0.0, 'batch_pct': 0.0,
                    'progress_text': f'Batch: {total} unit(s)', 'unit_statuses': {},
                    'results': [], 'log_tail': [], 'order': work})
        _e_log(f'Batch: {total} unit(s) | timeout {timeout_s/60:.0f} min', 'header-line')

        for i, unit in enumerate(work):
            if _executor_stop.is_set():
                _e_log('Stopped by user.', 'warn')
                work[i]['_status'] = 'fail'
                break

            head = unit.get('name') if unit['type'] == 'single' \
                   else unit.get('names', ['?'])[0]
            unit_to_s = (unit.get('timeout') or 0) * 60 or timeout_s
            batch_pct = i / total * 100

            work[i]['_status'] = 'running'
            _broadcast({'batch_pct': batch_pct,
                        'progress_text': f'Running {i+1}/{total}: {head}',
                        'order': list(work)})
            _e_log(f'\u2500 Job {i+1}/{total}: {head}', 'muted')

            try:
                if unit['type'] == 'single':
                    _u_name      = unit['name']
                    _u_label     = unit.get('label', _u_name)
                    _u_overrides = unit.get('paramOverrides', {})
                    if _u_overrides:
                        _u_base = wf_cache.get(_u_name)
                        if _u_base:
                            import copy as _cp
                            _u_patched = _cp.deepcopy(_u_base)
                            for _uk, _uv in _u_overrides.items():
                                if '.' in _uk:
                                    _uid, _uinp = _uk.split('.', 1)
                                    if _uid in _u_patched and isinstance(
                                            _u_patched[_uid].get('inputs'), dict):
                                        _u_patched[_uid]['inputs'][_uinp] = _uv
                            _u_wfc = {**wf_cache, _u_name: _u_patched}
                            _save_wedge_variant(_u_patched, _u_name, _u_label, wf_folder)
                        else:
                            _u_wfc = wf_cache
                    else:
                        _u_wfc = wf_cache
                    # Variant outputs: use label as filename_prefix so
                    # [v1]/[v2]/[v3] land in distinct files.
                    _u_prefix = _u_label if _u_label and _u_label != _u_name else None
                    res = _e_run_link(_u_name, _u_wfc, comfy_url,
                                      unit_to_s, unit_statuses, session_results,
                                      cache_key=_u_label, prefix=_u_prefix)
                    work[i]['_status'] = 'ok' if res['ok'] else 'fail'
                    if res['ok']: ok_count += 1
                    results_list.append({'name': _u_label, 'used': res.get('used', _u_label),
                                         'status': res['status'], 'secs': res['secs'],
                                         'outs': res.get('outs', [])})
                    if unit.get('clearVram'):    _e_free_vram(comfy_url)
                    if unit.get('restartComfy'): _e_restart_comfy(comfy_url)

                else:  # chain
                    mode = unit.get('mode', 'success')
                    last_good = None
                    chain_nodes = unit.get('nodes', [])
                    for ni, nm in enumerate(unit.get('names', [])):
                        if _executor_stop.is_set(): break
                        _cn      = chain_nodes[ni] if ni < len(chain_nodes) else {}
                        _cn_ovr  = (_cn.get('paramOverrides') or {}) if _cn else {}
                        _cn_lbl  = _cn.get('label') if _cn else None
                        if _cn_lbl == nm: _cn_lbl = None
                        if _cn_ovr:
                            import copy as _cp
                            _cn_base = wf_cache.get(nm)
                            if _cn_base:
                                _cn_pat = _cp.deepcopy(_cn_base)
                                for _ck, _cv in _cn_ovr.items():
                                    if '.' in _ck:
                                        _cid, _cinp = _ck.split('.', 1)
                                        if _cid in _cn_pat and isinstance(
                                                _cn_pat[_cid].get('inputs'), dict):
                                            _cn_pat[_cid]['inputs'][_cinp] = _cv
                                _cn_wfc = {**wf_cache, nm: _cn_pat}
                                _e_log(f'  Saving _wedge variant for {_cn_lbl or nm!r} ({len(_cn_ovr)} override(s))…', 'muted')
                                _save_wedge_variant(_cn_pat, nm,
                                                    _cn_lbl or nm, wf_folder)
                            else:
                                _e_log(f'  ⚠ _wedge save skipped — workflow {nm!r} not in cache', 'warn')
                                _cn_wfc = wf_cache
                        else:
                            _cn_wfc = wf_cache
                        _cn_key = _cn_lbl or nm
                        res = _e_run_link(nm, _cn_wfc, comfy_url,
                                          unit_to_s, unit_statuses, session_results,
                                          cache_key=_cn_key, prefix=_cn_lbl)
                        results_list.append({'name': _cn_key,
                                             'used': res.get('used', _cn_key),
                                             'status': res['status'], 'secs': res['secs'],
                                             'outs': res.get('outs', [])})
                        if unit.get('nodeVram',  {}).get(nm): _e_free_vram(comfy_url)
                        if unit.get('nodeRstrt', {}).get(nm): _e_restart_comfy(comfy_url)
                        if mode == 'success':
                            if res['ok']: last_good = res; break
                        else:
                            if res['ok']: last_good = res
                            else: break
                    chain_ok = last_good is not None
                    work[i]['_status'] = 'ok' if chain_ok else 'fail'
                    if chain_ok: ok_count += 1
                    if unit.get('clearVram'):    _e_free_vram(comfy_url)
                    if unit.get('restartComfy'): _e_restart_comfy(comfy_url)

            except Exception as e:
                work[i]['_status'] = 'fail'
                _e_log(f'    Run error: {e}', 'err')

            _broadcast({'results': list(results_list), 'order': list(work)})

        done_text = f'Done \u2014 {ok_count}/{total} OK'
        _broadcast({'running': False, 'batch_pct': 100.0, 'job_pct': 100.0,
                    'progress_text': done_text, 'order': list(work)})
        _e_log('Batch complete.', 'header-line')

    except Exception as e:
        _broadcast({'running': False, 'progress_text': f'Executor error: {e}'})
        _e_log(f'Executor crashed: {e}', 'err')
    finally:
        _executor_thread = None




# ── mobile live-view page (/viewer) ──────────────────────────────────────────
_VIEWER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Wedge &#xB7; Live</title>
<meta name="theme-color" content="#d18d1f">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Wedge">
<link rel="apple-touch-icon" href="https://cdn.jsdelivr.net/gh/Gerry-Malta/AI_LAB@main/_img/DZ_logo_5.png">
<link rel="manifest" href="/manifest.json">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{
  --bg:#0a0a0a;--bg2:#0c0c0c;--bg3:#141414;
  --b1:#1e1e1e;--b2:#2a2a2a;
  --fg:#e8e4dc;--fg2:#888880;--dim:#555550;
  --gold:#d18d1f;--gdim:#8a5c14;
  --ok:#5ad17a;--warn:#f0b656;--err:#ff6b6b;--run:#6ea8fe;
}
body{font-family:'DM Mono','Courier New',monospace;background:var(--bg);color:var(--fg);
  min-height:100dvh;padding-bottom:env(safe-area-inset-bottom,20px)}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:999;
  background:repeating-linear-gradient(0deg,rgba(209,141,31,.018) 0px,
  transparent 1px,transparent 2px,rgba(209,141,31,.018) 3px)}

/* ── header ── */
.hdr{position:sticky;top:0;z-index:100;background:rgba(10,10,10,.96);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--b1);
  padding:11px 16px;display:flex;align-items:center;justify-content:space-between;gap:10px}
.hdr-left{display:flex;align-items:center;gap:10px;min-width:0}
.hdr-logo{height:26px;width:auto;flex-shrink:0}
.hdr-title{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--gold)}
.hdr-sub{font-size:8px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin-top:1px}
.hdr-act{display:flex;align-items:center;gap:6px;flex-shrink:0}
.hdr-rbtn{background:none;border:1px solid var(--b1);color:var(--dim);font-size:13px;padding:4px 8px;border-radius:4px;cursor:pointer;transition:color .15s,border-color .15s;line-height:1;touch-action:manipulation}
.hdr-rbtn:active{color:var(--err);border-color:var(--err)}
.pill{font-size:8px;letter-spacing:.1em;text-transform:uppercase;
  padding:4px 9px;border-radius:3px;border:1px solid;white-space:nowrap;flex-shrink:0}
.pill-idle{color:var(--fg2);border-color:var(--b2)}
.pill-run{color:var(--run);border-color:rgba(110,168,254,.4)}
.pill-ok{color:var(--ok);border-color:rgba(90,209,122,.4)}
.pill-off{color:var(--err);border-color:rgba(255,107,107,.4)}

/* ── status ── */
.status-row{display:flex;align-items:flex-start;gap:10px;padding:12px 16px;border-bottom:1px solid var(--b1)}
.sdot{width:8px;height:8px;border-radius:50%;background:var(--dim);flex-shrink:0;margin-top:3px;transition:background .3s}
.sdot.run{background:var(--run);box-shadow:0 0 8px rgba(110,168,254,.6);animation:pulse .9s ease infinite}
.sdot.ok{background:var(--ok)}.sdot.err{background:var(--err)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.2}}
.stext{font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:var(--dim);transition:color .3s}
.stext.run{color:var(--run)}
.prog-text{font-size:10px;color:var(--fg2);margin-top:3px;line-height:1.5;word-break:break-word}

/* ── pbars ── */
.pbars{padding:11px 16px;border-bottom:1px solid var(--b1);display:flex;flex-direction:column;gap:8px}
.prow{display:flex;align-items:center;gap:8px}
.plbl{font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);width:36px;flex-shrink:0}
.ptrack{flex:1;height:5px;background:var(--bg3);border-radius:3px;overflow:hidden;border:1px solid var(--b1)}
.pfill{height:100%;width:0%;border-radius:3px;transition:width .3s}
.pfill.job{background:var(--ok)}.pfill.batch{background:var(--gold)}
.pfill.vram{background:#5a9fd4;transition:width .6s,background .4s}
.ppct{font-size:8px;color:var(--fg2);flex-shrink:0;text-align:right;white-space:nowrap}
.ppct.w{min-width:88px}
.gpu-name{font-size:7px;letter-spacing:.06em;color:var(--dim);padding:2px 0 0 44px}

/* ── ctrl bar ── */
.ctrl-bar{display:flex;gap:10px;padding:12px 16px;border-bottom:1px solid var(--b1)}
.cbtn{flex:1;padding:11px 10px;border-radius:3px;font-family:inherit;font-size:10px;
  letter-spacing:.1em;text-transform:uppercase;cursor:pointer;border:1px solid;
  transition:all .15s;touch-action:manipulation}
.cbtn:disabled{opacity:.3;cursor:not-allowed}
.cbtn-run{background:rgba(90,209,122,.08);border-color:var(--ok);color:var(--ok)}
.cbtn-run:not(:disabled):active{background:rgba(90,209,122,.18)}
.cbtn-stop{background:rgba(255,107,107,.08);border-color:var(--err);color:var(--err)}
.cbtn-stop:not(:disabled):active{background:rgba(255,107,107,.18)}

/* ── small button ── */
.sbtn{background:var(--bg3);border:1px solid var(--b2);color:var(--fg2);
  font-family:inherit;font-size:9px;letter-spacing:.06em;text-transform:uppercase;
  padding:6px 11px;border-radius:3px;cursor:pointer;flex-shrink:0;
  touch-action:manipulation;transition:all .15s;white-space:nowrap}
.sbtn:active{opacity:.7}
.sbtn.gold{border-color:var(--gdim);color:var(--gold);background:rgba(209,141,31,.08)}

/* ── collapsible sections ── */
.sec-wrap{border-bottom:1px solid var(--b1)}
.sec-hdr{display:flex;align-items:center;gap:9px;padding:13px 16px;
  cursor:pointer;user-select:none;transition:background .12s;touch-action:manipulation}
.sec-hdr:active{background:var(--bg3)}
.sec-arr{font-size:9px;color:var(--dim);flex-shrink:0;width:10px;text-align:center}
.sec-ttl{font-size:8px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);flex:1}
.sec-cnt{font-size:8px;color:var(--dim);letter-spacing:.05em}

/* ── VRAM / RSTRT toggle chips ── */
.tc{font-size:8px;letter-spacing:.06em;text-transform:uppercase;padding:3px 7px;
  border-radius:2px;border:1px solid var(--b2);color:var(--dim);cursor:pointer;
  flex-shrink:0;touch-action:manipulation;user-select:none;transition:all .15s}
.tc:active{opacity:.7}
.tc.on{border-color:var(--gold);color:var(--gold);background:rgba(209,141,31,.1)}
.tc.rstrt.on{border-color:var(--err);color:var(--err);background:rgba(255,107,107,.08)}

/* ── run order ── */
.m-unit{display:flex;flex-wrap:wrap;align-items:center;gap:6px;
  padding:10px 16px;border-bottom:1px solid rgba(30,30,30,.5);transition:background .2s,color .2s}
.m-unit.run{background:rgba(110,168,254,.07);color:var(--run)}
.m-unit.ok{color:var(--ok)}.m-unit.fail{color:var(--err)}
.m-idx{font-size:9px;color:var(--dim);flex-shrink:0;min-width:18px}
.m-ico{flex-shrink:0;font-size:12px}
.m-lbl{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:80px;font-size:11px}
.m-badge{font-size:7px;letter-spacing:.08em;text-transform:uppercase;
  padding:2px 7px;border-radius:2px;border:1px solid;flex-shrink:0}
.m-unit.run .m-badge{color:var(--run);border-color:rgba(110,168,254,.35)}
.m-unit.ok  .m-badge{color:var(--ok);border-color:rgba(90,209,122,.35)}
.m-unit.fail .m-badge{color:var(--err);border-color:rgba(255,107,107,.35)}
.m-chips{display:flex;gap:5px;width:100%;padding-left:42px}.m-rm{margin-left:auto;background:none;border:none;color:var(--dim);font-size:16px;padding:0 2px;cursor:pointer;flex-shrink:0;line-height:1;touch-action:manipulation;transition:color .15s;align-self:flex-start}.m-rm:active{color:var(--err)}
.m-empty{color:var(--dim);font-size:10px;padding:18px 16px;text-align:center;letter-spacing:.06em;line-height:1.9}

/* ── chain graph ── */
.graph-scroll{overflow-x:auto;padding:12px 16px;-webkit-overflow-scrolling:touch}
.chain-row{display:flex;align-items:flex-start;gap:0;flex-wrap:nowrap;margin-bottom:12px;min-width:min-content}
.cmode{font-size:8px;letter-spacing:.08em;text-transform:uppercase;padding:6px 10px;
  border-radius:3px;border:1px solid;cursor:pointer;touch-action:manipulation;
  flex-shrink:0;margin-right:10px;transition:all .15s;align-self:center}
.cmode.success{color:var(--ok);border-color:rgba(90,209,122,.4)}
.cmode.failure{color:var(--warn);border-color:rgba(240,182,86,.4)}
.cmode:active{opacity:.7}
.gnode{background:var(--bg3);border:1px solid var(--b2);border-radius:3px;padding:8px 10px;
  display:inline-flex;flex-direction:column;gap:6px;align-items:flex-start;
  flex-shrink:0;transition:border-color .25s,color .25s}
.gnode.running{border-color:var(--run);box-shadow:0 0 8px rgba(110,168,254,.2)}
.gnode.ok{border-color:var(--ok)}.gnode.fail{border-color:var(--err)}
.gnode.reused{border-style:dashed;opacity:.65}
.gnode-lbl{font-size:10px;color:var(--fg)}
.gnode-chips{display:flex;gap:4px}
.garrow{color:var(--dim);padding:0 6px;font-size:14px;align-self:center;flex-shrink:0}

/* ── results ── */
/* ── compare ── */
.vw-cb{position:absolute;top:8px;right:8px;z-index:50;width:24px;height:24px;border-radius:3px;border:1px solid var(--b2,#2a2a2a);background:rgba(10,10,10,.85);display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--fg2,#888880);user-select:none;cursor:pointer}
.rcard.in-cmp .vw-cb{border-color:var(--gold,#d18d1f);background:var(--gold,#d18d1f);color:#000}
.rcard.in-cmp{border-color:var(--gold,#d18d1f)!important;box-shadow:0 0 12px rgba(209,141,31,.4)}
.vw-bar{display:none;align-items:center;gap:8px;padding:8px 16px;font-size:9px;letter-spacing:.08em;color:var(--fg2,#888880)}
.vw-bar.vis{display:flex}
.vw-bar strong{color:var(--gold,#d18d1f);flex:1}
.vwlb{position:fixed;inset:0;z-index:9500;background:rgba(0,0,0,.96);display:none;flex-direction:column;align-items:center;justify-content:center;padding:12px}
.vwlb.open{display:flex}
.vw-x{position:absolute;top:10px;right:14px;font-size:20px;color:var(--fg2,#888880);background:none;border:none;font-family:inherit;z-index:9600;cursor:pointer}
.vw-wrap{position:relative;overflow:hidden;width:100%;height:52vh;border-radius:3px;user-select:none;background:#000}
.vw-a,.vw-b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;overflow:hidden}
.vw-a video,.vw-a img,.vw-b video,.vw-b img{width:100%;height:100%;object-fit:contain;display:block}
.vw-a{clip-path:inset(0 50% 0 0)}
.vw-handle{position:absolute;top:0;bottom:0;width:3px;background:var(--gold,#d18d1f);left:50%;transform:translateX(-50%);z-index:10;box-shadow:0 0 10px rgba(209,141,31,.4)}
.vw-handle::after{content:'◀ ▶';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:var(--gold,#d18d1f);color:#000;font-size:10px;padding:6px 9px;border-radius:3px;white-space:nowrap}
.vw-lbls{position:absolute;bottom:0;left:0;right:0;display:flex;justify-content:space-between;padding:6px 8px;pointer-events:none}
.vw-lbl{font-size:8px;letter-spacing:.08em;text-transform:uppercase;background:rgba(0,0,0,.7);padding:3px 6px;border-radius:3px;max-width:46%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.vw-lbl.a{color:#6ea8fe}.vw-lbl.b{color:var(--warn,#f0b656)}
.vw-ctrl{width:100%;display:flex;flex-direction:column;gap:10px;margin-top:12px;font-size:10px;color:var(--fg2,#888880)}
.vw-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.vw-track{flex:1;height:30px;background:var(--bg3,#0e0e0e);border:1px solid var(--b2,#2a2a2a);border-radius:3px;position:relative;overflow:hidden}
.vw-fill{position:absolute;top:0;left:0;height:100%;width:0%;background:rgba(209,141,31,.25);pointer-events:none}
.vw-needle{position:absolute;top:0;bottom:0;width:2px;background:var(--gold,#d18d1f);pointer-events:none;transform:translateX(-50%)}
.vw-flbl{font-size:9px;color:var(--gold,#d18d1f);min-width:84px;text-align:right;text-transform:uppercase}
.vw-spd{display:flex;gap:4px}
.vw-spd button{font-family:inherit;font-size:9px;padding:4px 9px;border:1px solid var(--b2,#2a2a2a);background:var(--bg2,#0c0c0c);color:var(--fg2,#888880);border-radius:3px;cursor:pointer}
.vw-spd button.on{border-color:var(--gold,#d18d1f);color:var(--gold,#d18d1f)}
.rcard{position:relative;background:var(--bg3);border:1px solid var(--b1);border-radius:3px;
  margin:8px 16px;padding:10px 12px;transition:border-color .25s}
.rcard.ok{border-color:rgba(90,209,122,.4)}.rcard.fail{border-color:rgba(255,107,107,.4)}
.rcard-hdr{display:flex;align-items:center;gap:8px;font-size:10px;flex-wrap:wrap}
.rcard-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:60px}
.rcard-badge{font-size:7px;letter-spacing:.08em;text-transform:uppercase;
  padding:2px 6px;border-radius:2px;border:1px solid;flex-shrink:0}
.rcard.ok  .rcard-badge{color:var(--ok);border-color:rgba(90,209,122,.4)}
.rcard.fail .rcard-badge{color:var(--err);border-color:rgba(255,107,107,.4)}
.rcard-secs{font-size:8px;color:var(--dim);flex-shrink:0}
.rcard-media{margin-top:8px;width:100%;max-height:260px;object-fit:contain;border-radius:2px;display:block}
.r-empty{color:var(--dim);font-size:10px;padding:18px 16px;text-align:center;letter-spacing:.06em}

/* ── workflows section ── */
.wf-path-row{display:flex;gap:6px;padding:10px 16px;border-bottom:1px solid var(--b1);align-items:center}
.wf-path-inp{flex:1;background:var(--bg3);border:1px solid var(--b2);color:var(--fg);
  font-family:inherit;font-size:11px;padding:7px 9px;border-radius:3px;outline:none;min-width:0}
.wf-path-inp:focus{border-color:var(--gold)}
.wf-action-row{display:flex;gap:6px;padding:8px 16px;border-bottom:1px solid var(--b1);flex-wrap:wrap}
.sel-info-m{padding:8px 16px;font-size:9px;color:var(--gold);
  letter-spacing:.06em;border-bottom:1px solid var(--b1);min-height:34px;
  display:flex;align-items:center;word-break:break-all}
.wf-item-m{display:flex;align-items:center;gap:8px;padding:11px 16px;
  border-bottom:1px solid rgba(30,30,30,.5);cursor:pointer;user-select:none;
  touch-action:manipulation;transition:background .12s}
.wf-item-m:active{background:var(--bg3)}
.wf-item-m.selected{background:rgba(209,141,31,.06)}
.wf-item-m.invalid{opacity:.5}
.wf-seq{width:17px;height:17px;border-radius:50%;background:var(--gold);color:#000;
  font-size:9px;display:flex;align-items:center;justify-content:center;
  flex-shrink:0;font-weight:500}
.wf-seq-empty{width:17px;height:17px;border-radius:50%;border:1px solid var(--b2);flex-shrink:0}
.wf-name-m{flex:1;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wf-gear{background:none;border:1px solid transparent;color:var(--dim);font-size:12px;
  padding:3px 7px;border-radius:2px;cursor:pointer;flex-shrink:0;touch-action:manipulation}
.wf-gear:active{border-color:var(--gold);color:var(--gold)}
.wf-gear.cfg{color:var(--gold);border-color:var(--gdim)}

/* ── folder browser bottom sheet ── */
.sheet{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.7);
  display:none;align-items:flex-end}
.sheet.open{display:flex}
.sheet-panel{width:100%;max-height:82dvh;background:var(--bg);
  border-top:1px solid var(--b1);border-radius:14px 14px 0 0;
  display:flex;flex-direction:column;overflow:hidden}
.sheet-head{display:flex;align-items:center;justify-content:space-between;
  padding:14px 16px;border-bottom:1px solid var(--b1);flex-shrink:0}
.sheet-title{font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--fg)}
.sheet-close{background:none;border:none;color:var(--fg2);font-size:16px;cursor:pointer;padding:0 4px}
.fb-bc{padding:8px 16px;border-bottom:1px solid var(--b1);font-size:9px;
  color:var(--dim);overflow-x:auto;white-space:nowrap;flex-shrink:0}
.fb-crumb{cursor:pointer;color:var(--fg2);display:inline;touch-action:manipulation}
.fb-crumb::after{content:' / ';color:var(--dim)}
.fb-crumb:last-child::after{content:''}
.fb-crumb:last-child{color:var(--fg)}
.fb-list-m{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch}
.fb-item{display:flex;align-items:center;gap:10px;padding:13px 16px;
  border-bottom:1px solid rgba(30,30,30,.5);cursor:pointer;touch-action:manipulation;font-size:11px}
.fb-item:active{background:var(--bg3)}
.fb-ico{font-size:14px;flex-shrink:0}
.fb-foot{display:flex;align-items:center;gap:8px;padding:10px 16px;
  border-top:1px solid var(--b1);flex-shrink:0;background:var(--bg2)}
.fb-cur-path{flex:1;font-size:9px;color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fb-json-cnt{font-size:8px;color:var(--gold);flex-shrink:0}

/* ── param promotion bottom sheet ── */
.pp-panel{width:100%;height:90dvh;background:var(--bg);
  border-top:1px solid var(--b1);border-radius:14px 14px 0 0;
  display:flex;flex-direction:column;overflow:hidden}
.pp-head{display:flex;align-items:center;gap:10px;padding:14px 16px;
  border-bottom:1px solid var(--b1);flex-shrink:0}
.pp-wf-title{font-size:10px;letter-spacing:.15em;text-transform:uppercase;
  color:var(--gold);flex:1;overflow:hidden;text-overflow:ellipsis}
.pp-scroll{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch}
.pp-search{display:block;width:100%;background:var(--bg3);border:none;
  border-bottom:1px solid var(--b1);color:var(--fg);font-family:inherit;
  font-size:11px;padding:11px 16px;outline:none}
.pp-grp-lbl{font-size:7px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold);
  padding:8px 16px 4px;border-bottom:1px solid var(--b1);position:sticky;top:0;
  background:var(--bg);z-index:5}
.pp-param{display:flex;align-items:center;gap:10px;padding:11px 16px;
  border-bottom:1px solid rgba(30,30,30,.5);cursor:pointer;touch-action:manipulation}
.pp-param:active{background:var(--bg3)}
.pp-param input[type=checkbox]{accent-color:var(--gold);width:16px;height:16px;flex-shrink:0}
.pp-pname{flex:1;font-size:11px}
.pp-pval{font-size:9px;color:var(--dim);max-width:80px;overflow:hidden;text-overflow:ellipsis}
.pp-pty{font-size:7px;border:1px solid var(--b2);padding:1px 4px;border-radius:2px;color:var(--dim);flex-shrink:0}
.pp-var-hdr{font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);
  padding:10px 16px 6px;border-top:2px solid var(--b2);border-bottom:1px solid var(--b1);
  display:flex;align-items:center;justify-content:space-between}
.pp-var-card{padding:10px 16px;border-bottom:1px solid rgba(30,30,30,.5)}
.pp-var-lbl-row{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.pp-var-lbl-inp{flex:1;background:var(--bg3);border:1px solid var(--b2);color:var(--fg);
  font-family:inherit;font-size:11px;padding:5px 8px;border-radius:2px;outline:none}
.pp-param-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.pp-param-key{font-size:8px;letter-spacing:.06em;color:var(--dim);min-width:60px;flex-shrink:0}
.pp-param-inp{flex:1;background:var(--bg3);border:1px solid var(--b2);color:var(--fg);
  font-family:inherit;font-size:11px;padding:5px 8px;border-radius:2px;outline:none;min-width:0}
.pp-var-del{background:none;border:none;color:var(--dim);font-size:16px;padding:0 4px;
  cursor:pointer;touch-action:manipulation;align-self:flex-start}
.pp-no-promo{color:var(--dim);font-size:10px;padding:18px 16px;text-align:center;letter-spacing:.06em;line-height:1.8}
.pp-foot{display:flex;gap:8px;padding:10px 16px;border-top:1px solid var(--b1);
  flex-shrink:0;background:var(--bg2)}
.pp-add-all{margin-left:auto;border-color:var(--gdim);color:var(--gold);background:rgba(209,141,31,.08)}

/* result filter */
.rcard.rf-hide{display:none!important}
.rf-bar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:8px 16px;border-bottom:1px solid var(--b1);background:var(--bg2)}
.rf-tog{background:var(--bg3);border:1px solid var(--b2);color:var(--fg2);font-family:inherit;font-size:9px;letter-spacing:.06em;text-transform:uppercase;padding:5px 10px;border-radius:3px;cursor:pointer;flex-shrink:0;touch-action:manipulation;transition:all .15s;white-space:nowrap}
.rf-tog.on{border-color:var(--gold);color:var(--gold);background:rgba(209,141,31,.1)}
.rfc{padding:2px 8px;border-radius:2px;cursor:pointer;font-size:8px;letter-spacing:.08em;text-transform:uppercase;user-select:none;border:1px solid var(--b2);color:var(--fg2);background:transparent;transition:all .15s;white-space:nowrap}
.rfc:active{opacity:.7}
.rfc.on{border-color:var(--gold);color:var(--gold);background:rgba(209,141,31,.1)}
.rfc.wfc.on{border-color:rgba(110,168,254,.5);color:#6ea8fe;background:rgba(110,168,254,.08)}
.rf-lbl{font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);white-space:nowrap}
.rf-sep{color:var(--dim);padding:0 3px}
/* ── footer ── */
.footer{padding:18px 16px 6px;border-top:1px solid var(--b1);
  font-size:8px;letter-spacing:.08em;color:var(--dim);
  display:flex;align-items:center;justify-content:space-between}
a{color:var(--gdim);text-decoration:none}
</style>
</head>
<body>

<!-- header -->
<div class="hdr">
  <div class="hdr-left">
    <img class="hdr-logo" src="https://raw.githubusercontent.com/Gerry-Malta/AI_LAB/main/_img/comfyui_logo_1.png" alt="ComfyUI" style="border-radius:4px;" onerror="this.style.display='none'">
    <span style="font-size:13px;color:var(--fg2,#888880);line-height:1;flex-shrink:0;">+</span>
    <a href="https://thedistrictzero.com/" target="_blank" rel="noopener" style="line-height:0;flex-shrink:0">
      <img class="hdr-logo" src="https://cdn.jsdelivr.net/gh/Gerry-Malta/AI_LAB@main/_img/DZ_logo_5.png" alt="DZ" onerror="this.style.display='none'">
    </a>
    <div>
      <div class="hdr-title">Wedge Studio</div>
      <div class="hdr-sub">Live Control</div>
    </div>
  </div>
  <div class="hdr-act">
    <span class="pill pill-idle" id="pill">Connecting&#x2026;</span>
    <input id="comfyPathV" style="display:none;">
    <button class="hdr-rbtn" onclick="saveComfyPathV()" title="Save ComfyUI folder path to config">&#x2713;</button>
    <button class="hdr-rbtn" onclick="restartWedge()" title="Restart Wedge + stop ComfyUI + clear VRAM">&#x21BB;</button>
  </div>
</div>

<!-- status -->
<div class="status-row">
  <div class="sdot" id="sdot"></div>
  <div style="flex:1;min-width:0">
    <div class="stext" id="stext">IDLE</div>
    <div class="prog-text" id="progressText"></div>
  </div>
</div>

<!-- pbars -->
<div class="pbars">
  <div class="prow"><span class="plbl">Job</span><div class="ptrack"><div class="pfill job" id="jobFill"></div></div><span class="ppct" id="jobPct">0%</span></div>
  <div class="prow"><span class="plbl">Batch</span><div class="ptrack"><div class="pfill batch" id="batchFill"></div></div><span class="ppct" id="batchPct">0%</span></div>
  <div class="prow"><span class="plbl">VRAM</span><div class="ptrack"><div class="pfill vram" id="vramFill"></div></div><span class="ppct w" id="vramPct">&#x2014;</span></div>
  <div class="gpu-name" id="gpuName"></div>
</div>

<!-- run / stop -->
<div class="ctrl-bar">
  <button class="cbtn cbtn-run" id="runBtn" onclick="startRun()" disabled>&#x25B6; Run</button>
  <button class="cbtn cbtn-stop" id="stopBtn" onclick="stopRun()" disabled>&#x25A0; Stop</button>
</div>

<!-- Workflows -->
<div class="sec-wrap">
  <div class="sec-hdr" onclick="_toggleSec('wf')">
    <span class="sec-arr" id="wf-arr">&#x25B8;</span>
    <span class="sec-ttl">Workflows</span>
    <span class="sec-cnt" id="wf-cnt"></span>
  </div>
  <div id="wf-body">
    <div class="wf-path-row">
      <input id="folderPathInput" class="wf-path-inp" placeholder="Workflow folder path">
      <button class="sbtn" onclick="openFolderBrowser()" title="Browse folders">&#x1F4C1;</button>
      <button class="sbtn" onclick="loadFromServer()">&#x21ba; Reload</button>
    </div>
    <div id="availList"><div class="m-empty">Enter a folder path and tap Load.</div></div>
  </div>
</div>

<!-- Run Order -->
<div class="sec-wrap">
  <div class="sec-hdr" onclick="_toggleSec('order')">
    <span class="sec-arr" id="order-arr">&#x25B8;</span>
    <span class="sec-ttl" id="orderSecTtl">Run Order</span>
    <span class="sec-cnt" id="order-cnt"></span>
  </div>
  <div class="sel-info-m" id="selInfo">selected: (none)</div>
  <div class="wf-action-row" id="orderActionRow">
    <button class="sbtn" id="makeChainBtn" onclick="makeChain()">&#x26D3; Chain</button>
    <button class="sbtn" id="chainCancelBtn" onclick="cancelChainBuild()" style="display:none;">✕ Cancel</button>
    <button class="sbtn" onclick="addSinglesMobile()">+ Add Singles</button>
    <button class="sbtn" onclick="clearSel()">Clear Sel</button>
    <button class="sbtn" onclick="saveOrderConfig()" title="Save run order to config">✓</button>
  </div>
  <div id="chainHintRow" style="display:none;padding:7px 14px;font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--gold);border-bottom:1px solid rgba(209,141,31,0.25);">
    <span id="chainBuildHint">Tap items in order · select ≥2</span>
  </div>
  <div id="order-body">
    <div id="orderList"><div class="m-empty">Loading&#x2026;</div></div>
  </div>
</div>

<!-- Chain Graph -->
<div class="sec-wrap" id="graphSec" style="display:none">
  <div class="sec-hdr" onclick="_toggleSec('graph')">
    <span class="sec-arr" id="graph-arr">&#x25B8;</span>
    <span class="sec-ttl">Chain Graph</span>
    <span class="sec-cnt" id="graph-cnt"></span>
  </div>
  <div id="graph-body">
    <div class="graph-scroll"><div id="graph"></div></div>
  </div>
</div>

<!-- Results -->
<div class="sec-wrap">
  <div class="sec-hdr" onclick="_toggleSec('results')">
    <span class="sec-arr" id="results-arr">&#x25B8;</span>
    <span class="sec-ttl">Results</span>
    <span class="sec-cnt" id="results-cnt"></span>
    <button class="rf-tog sbtn" id="rfTogV" onclick="event.stopPropagation();_rfToggle()" style="margin-left:auto">&#x26A1; Filter</button>
  </div>
  <div id="rfBarV" class="rf-bar" style="display:none">
    <span class="rf-lbl">Workflow&nbsp;</span>
    <span id="rfWfRowV" style="display:flex;flex-wrap:wrap;gap:4px"></span>
    <span class="rf-sep" id="rfSepV" style="display:none">&#xB7;</span>
    <span id="rfOutRowV" style="display:none;flex-wrap:wrap;gap:4px"></span>
  </div>
  <div id="results-body">
    <div class="vw-bar" id="vwBar"><strong id="vwCnt">0 selected</strong><button class="sbtn" id="vwBtn" onclick="vwOpen()" disabled>&#x21CC; Compare</button><button class="sbtn" onclick="vwClear()">Clear</button></div>
    <div id="resultsList"><div class="r-empty">No results yet.</div></div>
  </div>
</div>

<div class="footer">
  <span>District Zero &#xB7; Wedge Studio</span>
  <a href="/">Desktop UI</a>
</div>

<!-- compare wipe lightbox -->
<div class="vwlb" id="vwLb">
  <button class="vw-x" onclick="vwCloseLb()">&#x2715;</button>
  <div class="vw-wrap" id="vwWrap">
    <div class="vw-b" id="vwB"></div>
    <div class="vw-a" id="vwA"></div>
    <div class="vw-handle" id="vwHandle"></div>
    <div class="vw-lbls"><span class="vw-lbl a" id="vwLblA"></span><span class="vw-lbl b" id="vwLblB"></span></div>
  </div>
  <div class="vw-ctrl">
    <div class="vw-row">
      <button class="sbtn" id="vwPlayBtn" onclick="vwTogglePlay()">&#9654; Play</button>
      <div class="vw-spd"><button onclick="vwSpeed(0.1)">&times;0.1</button><button onclick="vwSpeed(0.25)">&times;0.25</button><button onclick="vwSpeed(0.5)">&times;0.5</button><button class="on" onclick="vwSpeed(1)">&times;1</button></div>
      <label style="display:flex;align-items:center;gap:4px;font-size:9px">fps <input id="vwFps" type="number" value="30" min="1" max="120" style="width:44px;background:var(--bg3,#0e0e0e);border:1px solid var(--b2,#2a2a2a);color:inherit;font-family:inherit;font-size:10px;padding:3px 5px;border-radius:3px"></label>
    </div>
    <div class="vw-row">
      <div class="vw-track" id="vwTrack"><div class="vw-fill" id="vwFill"></div><div class="vw-needle" id="vwNeedle"></div></div>
      <span class="vw-flbl" id="vwFrame">frame &mdash;</span>
    </div>
  </div>
</div>

<!-- Folder browser bottom sheet -->
<div class="sheet" id="fbSheet">
  <div class="sheet-panel">
    <div class="sheet-head">
      <span class="sheet-title">Select Workflow Folder</span>
      <button class="sheet-close" onclick="closeFolderBrowser()">&#x2715;</button>
    </div>
    <div class="fb-bc" id="fbBreadcrumb"></div>
    <div class="fb-list-m" id="fbList"></div>
    <div class="fb-foot">
      <span class="fb-cur-path" id="fbCurrentPath"></span>
      <span class="fb-json-cnt" id="fbJsonCnt"></span>
      <button class="sbtn gold" onclick="selectFolderFromBrowser()">Select</button>
      <button class="sbtn" onclick="closeFolderBrowser()">Cancel</button>
    </div>
  </div>
</div>

<!-- Param promotion bottom sheet -->
<div class="sheet" id="ppSheet">
  <div class="pp-panel">
    <div class="pp-head">
      <span class="pp-wf-title" id="ppTitle">&#x2014;</span>
      <button class="sheet-close" onclick="closeParamPanel()">&#x2715;</button>
    </div>
    <div class="pp-scroll" id="ppScroll">
      <input class="pp-search" id="ppSearch" placeholder="Search parameters…" oninput="ppRenderParams(this.value)">
      <div id="ppParamList"></div>
      <div class="pp-var-hdr">
        <span>Variants</span>
        <span id="ppVarCnt" style="color:var(--gold);font-size:9px"></span>
      </div>
      <div id="ppVarList"></div>
    </div>
    <div class="pp-foot">
      <button class="sbtn" onclick="ppAddRow()">+ Row</button>
      <button class="sbtn pp-add-all" id="ppAddAllBtn" onclick="ppAddAllToOrder()">Add to Run Order</button>
    </div>
  </div>
</div>

<script>
var WS = location.origin;

/* ── state ── */
var order        = [], _ns = {}, _nodeEls = {};
var _sig         = '', _resCount = 0;
var running      = false, _comfyOnline = false;
var _comfySrv    = '127.0.0.1:8188', _timeout = 20;
var workflows    = {}, chainSel = [], serverFolder = '';
var chainBuildMode = false, orderChainSel = [];
var _pCfg        = {}, _ppWf = null;
var _pendingSavedOrderV = null; // saved order waiting for workflows to load
var _fbCurPath   = '';

/* ── utils ── */
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];})}
function setBar(id,pct){var f=document.getElementById(id+'Fill'),p=document.getElementById(id+'Pct');if(f)f.style.width=(pct||0)+'%';if(p)p.textContent=Math.round(pct||0)+'%';}
function orderSig(ord){return(ord||[]).map(function(u){var id=u.type==='single'?(u.label||u.name):(u.names||[]).join(',');return id+':'+(u._status||'-');}).join('|');}
function isApiFormat(wf){if(!wf||typeof wf!=='object')return false;return Object.keys(wf).some(function(k){return wf[k]&&wf[k].class_type;});}
function _log(msg){var pt=document.getElementById('progressText');if(pt)pt.textContent=msg;}

/* ── collapse ── */
function _toggleSec(id){
  var body=document.getElementById(id+'-body'),arrow=document.getElementById(id+'-arr');
  if(!body)return;var open=body.style.display!=='none';
  body.style.display=open?'none':'';if(arrow)arrow.textContent=open?'\u25b8':'\u25be';
  try{localStorage.setItem('wl-'+id,open?'0':'1');}catch(e){}
}
function _initSec(id,def){
  var stored=null;try{stored=localStorage.getItem('wl-'+id);}catch(e){}
  var open=stored!==null?stored==='1':def;
  var body=document.getElementById(id+'-body'),arrow=document.getElementById(id+'-arr');
  if(body)body.style.display=open?'':'none';if(arrow)arrow.textContent=open?'\u25be':'\u25b8';
}
function _openSec(id){
  var body=document.getElementById(id+'-body'),arrow=document.getElementById(id+'-arr');
  if(body&&body.style.display==='none'){body.style.display='';if(arrow)arrow.textContent='\u25be';try{localStorage.setItem('wl-'+id,'1');}catch(e){}}
}

/* ── toggle chip factory ── */
function _chip(label,isOn,onToggle,extraCls){
  var c=document.createElement('span');c.className='tc'+(extraCls?' '+extraCls:'')+(isOn?' on':'');c.textContent=label;
  c.addEventListener('click',function(e){e.stopPropagation();var now=!c.classList.contains('on');c.classList.toggle('on',now);onToggle(now);});
  return c;
}

/* ── run / stop ── */
function _updateBtns(){
  var r=document.getElementById('runBtn'),s=document.getElementById('stopBtn');
  if(r)r.disabled=running||!order.length||!_comfyOnline;if(s)s.disabled=!running;
}
function startRun(){
  if(running||!order.length)return;running=true;_updateBtns();
  fetch(WS+'/start_run',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({order:order,comfy_server:_comfySrv,timeout:_timeout,
                         workflow_folder:serverFolder})})
  .then(function(r){return r.json();})
  .then(function(d){if(!d.ok){running=false;_updateBtns();_log('Error: '+(d.error||'could not start'));}})
  .catch(function(e){running=false;_updateBtns();_log('Error: '+e.message);});
}
function stopRun(){var s=document.getElementById('stopBtn');if(s)s.disabled=true;fetch(WS+'/stop_run',{method:'POST'}).catch(function(){});}

/* ── render order ── */
function renderOrder(){
  var el=document.getElementById('orderList'),cnt=document.getElementById('order-cnt');
  if(!el)return;
  if(cnt)cnt.textContent=order.length?order.length+' unit'+(order.length===1?'':'s'):'';
  if(!order.length){el.innerHTML='<div class="m-empty">No plan loaded.</div>';_updateBtns();return;}
  el.innerHTML='';
  order.forEach(function(u,i){
    var st=u._status||'',cls=st==='running'?'run':st==='ok'?'ok':st==='fail'?'fail':'';
    var div=document.createElement('div');div.className='m-unit'+(cls?' '+cls:'');
    var badge=cls?'<span class="m-badge">'+(st==='running'?'running':st==='ok'?'\u2713 ok':'\u2717 fail')+'</span>':'';
    var meta=workflows[u.name]||{};
    var _cpick=chainBuildMode&&orderChainSel.indexOf(i)>=0;
    if(_cpick){div.style.outline='2px solid var(--gold)';div.style.outlineOffset='-2px';}
    if(chainBuildMode){div.style.cursor='pointer';}
    (function(unitIdx){
      div.addEventListener('click',function(){
        if(!chainBuildMode){return;}
        var pos=orderChainSel.indexOf(unitIdx);
        if(pos>=0){orderChainSel.splice(pos,1);}else{orderChainSel.push(unitIdx);}
        var hint=document.getElementById('chainBuildHint');
        if(hint){hint.textContent=orderChainSel.length===0
          ?'Tap items in order · select ≥2'
          :orderChainSel.map(function(idx,n){return (n+1)+'. '+(order[idx].type==='single'?order[idx].name:order[idx].names[0]);}).join('  →  ');}
        var confirmBtn=document.getElementById('makeChainBtn');
        if(confirmBtn&&chainBuildMode){confirmBtn.disabled=orderChainSel.length<2;}
        renderOrder();
      });
    })(i);
    if(u.type==='single'){
      var lbl=u.label||u.name||'';
      var _pp=chainBuildMode?orderChainSel.indexOf(i):-1;
      var _pb=_pp>=0?'<span class="seq" style="display:inline-flex;margin-right:3px;">'+(_pp+1)+'</span>':'';
      div.innerHTML='<span class="m-idx">'+(i+1)+'</span>'+_pb+'<span class="m-ico">\u25cb</span><span class="m-lbl">'+esc(lbl)+'</span>'+badge;
      if(!chainBuildMode&&meta.validApi){
        var hasCfg=_pCfg[u.name]&&(_pCfg[u.name].promoted.size||_pCfg[u.name].variants.length);
        var gear=document.createElement('button');
        gear.className='wf-gear'+(hasCfg?' cfg':'');
        gear.textContent='\u2699';gear.title='Promote parameters';
        gear.addEventListener('click',(function(n){return function(e){e.stopPropagation();openParamPanel(n);};})(u.name));
        div.appendChild(gear);
      }
      var rm=document.createElement('button');rm.className='m-rm';rm.textContent='\u00d7';
      rm.title='Remove from run order';
      if(chainBuildMode){rm.style.opacity='0.3';}
      rm.addEventListener('click',(function(idx){return function(e){e.stopPropagation();if(!chainBuildMode){order.splice(idx,1);renderOrder();renderGraph();_updateBtns();}};})(i));
      div.appendChild(rm);
      if(!chainBuildMode){
        var chips=document.createElement('div');chips.className='m-chips';
        chips.appendChild(_chip('VRAM',!!u.clearVram,function(v){u.clearVram=v;},''));
        chips.appendChild(_chip('RSTRT',!!u.restartComfy,function(v){u.restartComfy=v;},'rstrt'));
        div.appendChild(chips);
      }
    } else {
      var names=(u.names||[]).join(' \u2192 ');
      div.innerHTML='<span class="m-idx">'+(i+1)+'</span><span class="m-ico">\u26d3</span><span class="m-lbl">'+esc(names)+'</span>'+badge;
      var rm2=document.createElement('button');rm2.className='m-rm';rm2.textContent='\u00d7';
      rm2.title='Remove from run order';
      if(chainBuildMode){rm2.style.opacity='0.3';}
      rm2.addEventListener('click',(function(idx){return function(e){e.stopPropagation();if(!chainBuildMode){order.splice(idx,1);renderOrder();renderGraph();_updateBtns();}};})(i));
      div.appendChild(rm2);
    }
    el.appendChild(div);
  });
  _updateBtns();
}

/* ── render graph ── */
function renderGraph(){
  var g=document.getElementById('graph'),sec=document.getElementById('graphSec'),cnt=document.getElementById('graph-cnt');
  if(!g)return;
  var chains=order.filter(function(u){return u.type==='chain';});
  if(!chains.length){if(sec)sec.style.display='none';g.innerHTML='';_nodeEls={};return;}
  if(sec)sec.style.display='';if(cnt)cnt.textContent=chains.length+' chain'+(chains.length===1?'':'s');
  g.innerHTML='';_nodeEls={};
  chains.forEach(function(u){
    var row=document.createElement('div');row.className='chain-row';
    var isSucc=u.mode!=='failure';var mb=document.createElement('span');
    mb.className='cmode '+(isSucc?'success':'failure');mb.textContent=isSucc?'\u2713 succ':'\u2717 fail';
    mb.addEventListener('click',(function(unit,btn){return function(){unit.mode=unit.mode==='failure'?'success':'failure';var s=unit.mode!=='failure';btn.className='cmode '+(s?'success':'failure');btn.textContent=s?'\u2713 succ':'\u2717 fail';};})(u,mb));
    row.appendChild(mb);
    (u.names||[]).forEach(function(nm,ni){
      var ns=_ns[nm]||{};var node=document.createElement('span');
      node.className='gnode'+(ns.state?' '+ns.state:'')+(ns.reused?' reused':'');
      var lbl=document.createElement('span');lbl.className='gnode-lbl';lbl.textContent=nm;node.appendChild(lbl);
      var gc=document.createElement('div');gc.className='gnode-chips';
      gc.appendChild(_chip('VRAM',!!(u.nodeVram&&u.nodeVram[nm]),function(v){if(!u.nodeVram)u.nodeVram={};u.nodeVram[nm]=v;},''));
      gc.appendChild(_chip('RSTRT',!!(u.nodeRstrt&&u.nodeRstrt[nm]),function(v){if(!u.nodeRstrt)u.nodeRstrt={};u.nodeRstrt[nm]=v;},'rstrt'));
      node.appendChild(gc);row.appendChild(node);(_nodeEls[nm]=_nodeEls[nm]||[]).push(node);
      if(ni<(u.names||[]).length-1){var arr=document.createElement('span');arr.className='garrow';arr.textContent='\u2192';row.appendChild(arr);}
    });
    g.appendChild(row);
  });
}

/* ── add result ── */
function _addOneMobileCard(name,used,ok,secs,o,idx,total){
  var list=document.getElementById('resultsList');if(!list)return;
  if(list.querySelector('.r-empty'))list.innerHTML='';
  var card=document.createElement('div');card.className='rcard '+(ok?'ok':'fail');
  var badge='<span class="rcard-badge">'+(ok?'\u2713 ok':'\u2717 fail')+'</span>';
  var label=used;if(total>1)label=used+' ['+idx+'/'+total+']';
  var hdr='<div class="rcard-hdr"><span class="rcard-name">'+esc(label)+'</span>'+badge+'<span class="rcard-secs">'+secs.toFixed(1)+'s</span></div>';
  var media='';var mUrl=null;var mVid=false;
  if(ok&&o){var url=WS+'/comfy_proxy/view?filename='+encodeURIComponent(o.fn)+'&subfolder='+encodeURIComponent(o.sub||'')+'&type='+(o.type||'output');
    mUrl=url;mVid=/\.(mp4|webm|mov)$/i.test(o.fn);
    media=mVid?'<video class="rcard-media" src="'+url+'" controls playsinline muted loop></video>':'<img class="rcard-media" src="'+url+'" loading="lazy">';}
  card.innerHTML=hdr+media;
  card.dataset.rfWf=name;card.dataset.rfIdx=String(idx);card.dataset.rfTotal=String(total);
  var vIdx=_vwStore.length;_vwStore.push({name:label,url:mUrl,isVid:mVid});
  card.dataset.vidx=vIdx;
  var vcb=document.createElement('span');vcb.className='vw-cb';vcb.textContent='\u2713';vcb.title='Select for compare';
  vcb.addEventListener('click',function(e){e.stopPropagation();_vwToggle(vIdx);});
  card.appendChild(vcb);
  list.appendChild(card);
  var vb=document.getElementById('vwBar');if(vb)vb.classList.add('vis');
  _rfApply();
  var rc=document.getElementById('results-cnt');var tot=list.querySelectorAll('.rcard').length;if(rc)rc.textContent=tot+' output'+(tot===1?'':'s');
}
function addMobileResult(r){
  var name=r.name||r.used||'';var used=r.used||name;var ok=r.status==='ok';
  var mediaOuts=(r.outs||[]).filter(function(o){return /\.(mp4|webm|mov|gif|png|jpe?g|webp)$/i.test(o.fn);});
  if(mediaOuts.length>0){
    mediaOuts.forEach(function(o,i){_addOneMobileCard(name,used,ok,r.secs||0,o,i+1,mediaOuts.length);});
  } else {
    _addOneMobileCard(name,used,ok,r.secs||0,null,1,1);
  }
}

function colorNodes(statuses){
  for(var nm in statuses){var e=statuses[nm],st=(e&&typeof e==='object')?e.state:e,ru=(e&&typeof e==='object')?!!e.reused:false;_ns[nm]={state:st,reused:ru};(_nodeEls[nm]||[]).forEach(function(el){el.className='gnode'+(st?' '+st:'')+(ru?' reused':'');});}
}

/* ── applyRunState ── */
function applyRunState(state){
  var wasRunning=running;
  if(state.running!==undefined){
    running=state.running;var sdot=document.getElementById('sdot'),st=document.getElementById('stext'),pill=document.getElementById('pill');
    if(running){if(sdot)sdot.className='sdot run';if(st){st.className='stext run';st.textContent='RUNNING';}if(pill&&pill.className.indexOf('pill-ok')<0){pill.className='pill pill-run';pill.textContent='\u25cf Running';}}
    else{if(sdot)sdot.className='sdot';if(st){st.className='stext';st.textContent='IDLE';}}
    _updateBtns();if(!wasRunning&&running)_openSec('order');
  }
  if(state.progress_text!==undefined){var pt=document.getElementById('progressText');if(pt)pt.textContent=state.progress_text||'';}
  if(state.job_pct!==undefined)setBar('job',state.job_pct);
  if(state.batch_pct!==undefined)setBar('batch',state.batch_pct);
  if(state.unit_statuses)colorNodes(state.unit_statuses);
  if(state.order&&state.order.length){var sig=orderSig(state.order);if(sig!==_sig){order=state.order;_rehydratePCfgFromOrderV();renderOrder();renderGraph();_sig=sig;}}
  if(state.unit_statuses){document.querySelectorAll('#orderList .m-unit').forEach(function(div,idx){if(idx>=order.length)return;var u=order[idx],nm=u.label||u.name;if(!nm||!state.unit_statuses[nm])return;var e=state.unit_statuses[nm],nst=(e&&typeof e==='object')?e.state:e;div.className='m-unit'+(nst==='running'?' run':nst==='ok'?' ok':nst==='fail'?' fail':'');});}
  if(state.results!==undefined){
    if(!state.results.length&&_resCount>0){var rl=document.getElementById('resultsList');if(rl)rl.innerHTML='<div class="r-empty">No results yet.</div>';var rc=document.getElementById('results-cnt');if(rc)rc.textContent='';_resCount=0;_vwResetCompare();}
    else if(state.results.length>_resCount){var newRes=state.results.slice(_resCount);if(_resCount===0&&newRes.length)_openSec('results');newRes.forEach(addMobileResult);_resCount=state.results.length;}
  }
}

/* ── SSE ── */
function connectSSE(){var es=new EventSource(WS+'/events');es.onmessage=function(e){try{applyRunState(JSON.parse(e.data));}catch(err){};};}

/* ── checkComfy + VRAM ── */
function checkComfy(){
  fetch(WS+'/comfy_proxy/system_stats',{signal:AbortSignal.timeout(3000)})
  .then(function(r){
    if(!r.ok){throw new Error('HTTP '+r.status);}
    return r.json();
  })
  .then(function(d){
    if(d&&d.error){throw new Error(d.error);}
    _comfyOnline=true;
    var pill=document.getElementById('pill'),st=document.getElementById('stext');
    if(pill){pill.className='pill pill-ok';pill.textContent='\u25cf ComfyUI online';}
    _updateBtns();
    if(d&&d.devices&&d.devices.length){var dev=d.devices[0],tot=dev.vram_total||0,free=dev.vram_free||0,used=tot-free,pct=tot>0?used/tot*100:0;var fill=document.getElementById('vramFill'),vpct=document.getElementById('vramPct'),gpu=document.getElementById('gpuName');if(fill){fill.style.width=pct.toFixed(1)+'%';fill.style.background=pct>85?'var(--err)':pct>65?'var(--warn)':'#5a9fd4';}if(vpct)vpct.textContent=(used/1073741824).toFixed(1)+' / '+(tot/1073741824).toFixed(1)+' GB';if(gpu&&dev.name&&!gpu.textContent)gpu.textContent=dev.name;}
  }).catch(function(){
    _comfyOnline=false;
    var pill=document.getElementById('pill');
    if(pill){pill.className='pill pill-off';pill.textContent='ComfyUI offline';}
    _updateBtns();
  });
}

/* ── load workflows from server ── */
function loadFromServer(){
  var path=(document.getElementById('folderPathInput')||{}).value||'';
  path=path.trim();if(!path)return;
  _log('\u21ba Reloading \u2014 clearing order and loading from '+path+'\u2026');
  fetch(WS+'/list_workflows?folder='+encodeURIComponent(path))
  .then(function(r){return r.json();})
  .then(function(d){
    if(!d.ok){_log('Cannot read folder: '+(d.error||''));return;}
    serverFolder=d.folder;
    document.getElementById('folderPathInput').value=d.folder;
    if(!d.files||!d.files.length){_log('No .json files found.');renderAvailMobile();return;}
    return fetch(WS+'/read_workflows',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:d.folder,files:d.files})});
  })
  .then(function(r){if(!r)return;return r.json();})
  .then(function(d){
    if(!d)return;workflows={};var ok=0,bad=0;
    Object.keys(d.workflows||{}).forEach(function(fname){
      var res=d.workflows[fname],name=fname.replace(/\.json$/i,'');
      if(res.ok){try{var wf=JSON.parse(res.content);if(isApiFormat(wf)){workflows[name]={wf:wf,validApi:true};ok++;}else{workflows[name]={wf:wf,validApi:false};bad++;}}catch(e){bad++;}}else{bad++;}
    });
    _log('Loaded '+ok+' workflow'+(ok===1?'':'s')+(bad?' ('+bad+' not API format)':'')+'.');
    renderAvailMobile();
    var cnt=document.getElementById('wf-cnt');if(cnt)cnt.textContent=ok+' loaded';
    _openSec('wf');
    /* new folder loaded — restore saved order or reset if none */
    chainSel=[];
    if(!_pendingSavedOrderV||!_pendingSavedOrderV.length){
      order=[];renderOrder();renderGraph();_updateBtns();
    } else {
      _applyPendingOrderV();
    }
    fetch(WS+'/save_config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({workflow_folder:serverFolder})}).catch(function(){});
  }).catch(function(e){_log('Load error: '+e.message);});
}

/* ── render available list ── */
function renderAvailMobile(){
  var el=document.getElementById('availList');if(!el)return;
  var names=Object.keys(workflows);
  if(!names.length){el.innerHTML='<div class="m-empty">No workflows loaded.</div>';return;}
  el.innerHTML='';
  names.forEach(function(name){
    var meta=workflows[name],sel=chainSel.includes(name);
    var div=document.createElement('div');
    div.className='wf-item-m'+(sel?' selected':'')+(meta.validApi?'':' invalid');
    /* seq bubble */
    if(sel){var seqEl=document.createElement('div');seqEl.className='wf-seq';seqEl.textContent=chainSel.indexOf(name)+1;div.appendChild(seqEl);}
    else{var seqEl2=document.createElement('div');seqEl2.className='wf-seq-empty';div.appendChild(seqEl2);}
    /* name */
    var nm=document.createElement('span');nm.className='wf-name-m';nm.textContent=name+(meta.validApi?'':' \u00b7 not API format');div.appendChild(nm);
    /* gear btn (only for valid API) */
    div.addEventListener('click',function(){if(meta.validApi)toggleSel(name);else _log("'"+name+"' is not API format \u2014 re-save with 'Save (API Format)' in ComfyUI.");});
    el.appendChild(div);
  });
  /* update selInfo */
  var si=document.getElementById('selInfo');
  if(si)si.textContent=chainSel.length?chainSel.join(' \u2192 '):'selected: (none)';
}

/* ── chain selection ── */
function toggleSel(name){var i=chainSel.indexOf(name);if(i>=0)chainSel.splice(i,1);else chainSel.push(name);renderAvailMobile();}
function clearSel(){chainSel=[];renderAvailMobile();}

function makeChain(){
  if(!order.length){return;}
  chainBuildMode=true;orderChainSel=[];
  var btn=document.getElementById('makeChainBtn');
  if(btn){btn.textContent='✓ Confirm';btn.style.borderColor='var(--gold)';btn.style.background='rgba(209,141,31,0.15)';btn.onclick=function(){confirmChain();};}
  var cancelBtn=document.getElementById('chainCancelBtn');
  if(cancelBtn){cancelBtn.style.display='inline-block';}
  var hint=document.getElementById('chainHintRow');
  if(hint){hint.style.display='block';}
  var ttl=document.getElementById('orderSecTtl');
  if(ttl){ttl.textContent='Chain Builder';}
  renderOrder();_openSec('order');
}
function cancelChainBuild(){
  chainBuildMode=false;orderChainSel=[];
  var btn=document.getElementById('makeChainBtn');
  if(btn){btn.innerHTML='&#x26D3; Chain';btn.style.borderColor='';btn.style.background='';btn.onclick=function(){makeChain();};}
  var cancelBtn=document.getElementById('chainCancelBtn');
  if(cancelBtn){cancelBtn.style.display='none';}
  var hint=document.getElementById('chainHintRow');
  if(hint){hint.style.display='none';}
  var ttl=document.getElementById('orderSecTtl');
  if(ttl){ttl.textContent='Run Order';}
  renderOrder();
}
function confirmChain(){
  if(orderChainSel.length<2){return;}
  var pickedUnits=orderChainSel.map(function(i){return order[i];});
  var names=pickedUnits.map(function(u){return u.type==='single'?u.name:u.names[0];});
  var nodes=pickedUnits.map(function(u){return Object.assign({},u);});
  var toRemove=new Set(orderChainSel);
  order=order.filter(function(_,i){return !toRemove.has(i);});
  order.push({type:'chain',names:names,nodes:nodes,mode:'success'});
  cancelChainBuild();renderOrder();renderGraph();_updateBtns();
  _log('Chain created: '+names.join(' → '));
}
function addSinglesMobile(){
  if(!chainSel.length)return;
  var _asmCnt=chainSel.length;
  chainSel.forEach(function(n){order.push({type:'single',name:n});});
  clearSel();renderOrder();renderGraph();_updateBtns();_openSec('order');_log(_asmCnt+' workflow(s) added to run order.');
}

/* ── folder browser ── */
function openFolderBrowser(){
  var start=(document.getElementById('folderPathInput')||{}).value||'.';
  document.getElementById('fbSheet').classList.add('open');
  fbNavigate(start.trim()||'.');
}
function closeFolderBrowser(){document.getElementById('fbSheet').classList.remove('open');}

function fbNavigate(path){
  fetch(WS+'/browse?folder='+encodeURIComponent(path))
  .then(function(r){return r.json();})
  .then(function(d){
    if(!d.ok){_log('Browse error: '+(d.error||''));return;}
    _fbCurPath=d.current;
    var fpEl=document.getElementById('fbCurrentPath');if(fpEl)fpEl.textContent=d.current;
    var jcEl=document.getElementById('fbJsonCnt');if(jcEl)jcEl.textContent=d.json_count?d.json_count+' .json':'';
    /* breadcrumb */
    var bc=document.getElementById('fbBreadcrumb');bc.innerHTML='';
    (d.parents||[]).forEach(function(p){var sp=document.createElement('span');sp.className='fb-crumb';sp.textContent=p.name||p.path;sp.addEventListener('click',function(){fbNavigate(p.path);});bc.appendChild(sp);});
    /* list */
    var list=document.getElementById('fbList');list.innerHTML='';
    (d.subdirs||[]).forEach(function(ch){
      var item=document.createElement('div');item.className='fb-item';
      var ico=document.createElement('span');ico.className='fb-ico';ico.textContent='📂';
      var nm=document.createElement('span');nm.textContent=ch.name;
      item.appendChild(ico);item.appendChild(nm);
      item.addEventListener('click',function(){fbNavigate(ch.path);});
      list.appendChild(item);
    });
  }).catch(function(e){_log('Browse error: '+e.message);});
}

function selectFolderFromBrowser(){
  if(!_fbCurPath)return;
  document.getElementById('folderPathInput').value=_fbCurPath;
  closeFolderBrowser();loadFromServer();
}

/* ── param promotion ── */
function _ppCfg(name){if(!_pCfg[name])_pCfg[name]={promoted:new Set(),variants:[]};return _pCfg[name];}
function _ppDef(wfName,key){var wf=(workflows[wfName]||{}).wf;if(!wf)return 0;var p=key.split('.');var n=wf[p[0]];return(n&&n.inputs)?n.inputs[p[1]]:0;}

function _ppExtractParams(wfName){
  var wf=(workflows[wfName]||{}).wf;if(!wf)return[];var out=[];
  Object.keys(wf).forEach(function(nid){var node=wf[nid];if(!node||!node.class_type)return;Object.keys(node.inputs||{}).forEach(function(inp){var val=node.inputs[inp];if(Array.isArray(val))return;out.push({key:nid+'.'+inp,nid:nid,inp:inp,cls:node.class_type,def:val,vt:typeof val});});});
  out.sort(function(a,b){return a.cls<b.cls?-1:a.cls>b.cls?1:a.inp<b.inp?-1:a.inp>b.inp?1:0;});
  return out;
}

function openParamPanel(wfName){
  _ppWf=wfName;document.getElementById('ppTitle').textContent=wfName+' \u2014 Promote Parameters';
  document.getElementById('ppSearch').value='';document.getElementById('ppSheet').classList.add('open');
  ppRenderParams('');ppRenderVariants();
}
function closeParamPanel(){document.getElementById('ppSheet').classList.remove('open');_ppWf=null;}

function ppRenderParams(q){
  var el=document.getElementById('ppParamList');if(!el||!_ppWf)return;
  var c=_ppCfg(_ppWf),ps=_ppExtractParams(_ppWf),ql=(q||'').toLowerCase();
  el.innerHTML='';var grp={};
  ps.forEach(function(p){if(ql&&p.key.toLowerCase().indexOf(ql)<0&&p.cls.toLowerCase().indexOf(ql)<0)return;if(!grp[p.cls])grp[p.cls]=[];grp[p.cls].push(p);});
  Object.keys(grp).sort().forEach(function(cls){
    var gl=document.createElement('div');gl.className='pp-grp-lbl';gl.textContent=cls;el.appendChild(gl);
    grp[cls].forEach(function(p){
      var row=document.createElement('div');row.className='pp-param';
      var cb=document.createElement('input');cb.type='checkbox';cb.checked=c.promoted.has(p.key);
      var nm=document.createElement('span');nm.className='pp-pname';nm.textContent=p.inp;
      var vl=document.createElement('span');vl.className='pp-pval';vl.textContent=String(p.def).slice(0,20);vl.title=String(p.def);
      var ty=document.createElement('span');ty.className='pp-pty';ty.textContent=p.vt==='number'?(Number.isInteger(p.def)?'int':'float'):'str';
      row.appendChild(cb);row.appendChild(nm);row.appendChild(vl);row.appendChild(ty);
      cb.addEventListener('change',function(){
        if(cb.checked){c.promoted.add(p.key);c.variants.forEach(function(v){if(!v.overrides.hasOwnProperty(p.key))v.overrides[p.key]=p.def;});}else{c.promoted.delete(p.key);}
        ppRenderVariants();
      });
      row.addEventListener('click',function(e){if(e.target===cb)return;cb.checked=!cb.checked;cb.dispatchEvent(new Event('change'));});
      el.appendChild(row);
    });
  });
}

function ppRenderVariants(){
  var el=document.getElementById('ppVarList'),cnt=document.getElementById('ppVarCnt');if(!el||!_ppWf)return;
  var c=_ppCfg(_ppWf),promo=Array.from(c.promoted);
  if(cnt)cnt.textContent=c.variants.length+' variant'+(c.variants.length===1?'':'s');
  el.innerHTML='';
  if(!promo.length){el.innerHTML='<div class="pp-no-promo">Check parameters above to create columns.</div>';return;}
  c.variants.forEach(function(v,ri){
    var card=document.createElement('div');card.className='pp-var-card';
    /* label row */
    var lblRow=document.createElement('div');lblRow.className='pp-var-lbl-row';
    var lblInp=document.createElement('input');lblInp.className='pp-var-lbl-inp';lblInp.value=v.label;lblInp.placeholder='Label';
    lblInp.addEventListener('input',function(){v.label=lblInp.value;if(cnt)cnt.textContent=c.variants.length+' variant'+(c.variants.length===1?'':'s');});
    var delBtn=document.createElement('button');delBtn.className='pp-var-del';delBtn.textContent='\u00d7';delBtn.title='Remove variant';
    delBtn.addEventListener('click',(function(i){return function(){c.variants.splice(i,1);ppRenderVariants();};})(ri));
    lblRow.appendChild(lblInp);lblRow.appendChild(delBtn);card.appendChild(lblRow);
    /* one row per promoted param */
    promo.forEach(function(key){
      var pRow=document.createElement('div');pRow.className='pp-param-row';
      var klbl=document.createElement('span');klbl.className='pp-param-key';klbl.textContent=key.split('.')[1];
      var cur=v.overrides.hasOwnProperty(key)?v.overrides[key]:_ppDef(_ppWf,key);
      var inp=document.createElement('input');inp.className='pp-param-inp';inp.value=String(cur!==undefined?cur:'');
      inp.type=typeof cur==='number'?'number':'text';if(inp.type==='number')inp.step='any';
      inp.addEventListener('input',function(){var n=parseFloat(inp.value);v.overrides[key]=isNaN(n)?inp.value:n;});
      pRow.appendChild(klbl);pRow.appendChild(inp);card.appendChild(pRow);
    });
    el.appendChild(card);
  });
}

function ppAddRow(){
  if(!_ppWf)return;var c=_ppCfg(_ppWf);var ov={};c.promoted.forEach(function(k){ov[k]=_ppDef(_ppWf,k);});
  var maxN=0;
  c.variants.forEach(function(v){var m=(v.label||'').match(/^v(\d+)$/);if(m){var n=parseInt(m[1],10);if(n>maxN)maxN=n;}});
  order.forEach(function(u){if(!u||u.type!=='single'||u.name!==_ppWf||typeof u.label!=='string')return;var m=u.label.match(/\[v(\d+)\]\s*$/);if(m){var n=parseInt(m[1],10);if(n>maxN)maxN=n;}});
  c.variants.push({label:'v'+(maxN+1),overrides:ov});ppRenderVariants();
}

function ppAddAllToOrder(){
  if(!_ppWf)return;var c=_ppCfg(_ppWf);
  order.push({type:'single',name:_ppWf});
  c.variants.forEach(function(v){order.push({type:'single',name:_ppWf,label:_ppWf+' ['+v.label+']',paramOverrides:Object.assign({},v.overrides)});});
  closeParamPanel();renderOrder();renderGraph();_updateBtns();_openSec('order');
  _log('Added '+(1+c.variants.length)+' unit(s) from \''+_ppWf+'\' to run order.');
  /* refresh gear btn */
  renderAvailMobile();
}

/* ── loadConfig ── */
function saveComfyPathV(){
  var p=(document.getElementById('comfyPathV')||{}).value||'';
  if(!p.trim()){_log('Set ComfyUI path in config first.','warn');return;}
  fetch(WS+'/save_config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({comfy_path:p.trim(),workflow_folder:serverFolder,order:JSON.parse(JSON.stringify(order))})}).catch(function(){});
  _log('\u2713 ComfyUI path saved');
}
function saveOrderConfig(){
  fetch(WS+'/save_config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({workflow_folder:serverFolder,order:JSON.parse(JSON.stringify(order)),timeout:_timeout})}).catch(function(){});
  _log('✓ Config saved');
}
function _applyPendingOrderV(){
  if(!_pendingSavedOrderV)return;
  if(!Object.keys(workflows).length)return;
  var saved=_pendingSavedOrderV;
  _pendingSavedOrderV=null;
  var loaded={};
  Object.keys(workflows).forEach(function(n){loaded[n]=true;});
  var filtered=[];
  saved.forEach(function(u){
    if(!u)return;
    if(u.type==='single'){
      if(loaded[u.name])filtered.push(u);
    } else if(u.type==='chain'){
      var names=(u.names||[]).filter(function(n){return loaded[n];});
      if(names.length>=2)filtered.push(Object.assign({},u,{names:names}));
      else if(names.length===1)filtered.push({type:'single',name:names[0]});
    }
  });
  if(!filtered.length)return;
  order=filtered;
  _rehydratePCfgFromOrderV();
  renderOrder();renderGraph();_updateBtns();
  _log('\u2713 Run order restored from config ('+filtered.length+' unit(s)).','muted');
}
function _rehydratePCfgFromOrderV(){
  for (var i=0;i<order.length;i++){
    var u=order[i];
    if(!u||u.type!=='single'||!u.paramOverrides)continue;
    var keys=Object.keys(u.paramOverrides);
    if(!keys.length)continue;
    var nm=u.name;
    if(!_pCfg[nm])_pCfg[nm]={promoted:new Set(),variants:[]};
    var c=_pCfg[nm];
    keys.forEach(function(k){c.promoted.add(k);});
    var lbl='v'+(c.variants.length+1);
    if(typeof u.label==='string'){
      var m=u.label.match(/\[([^\]]+)\]\s*$/);
      if(m)lbl=m[1];
    }
    if(!c.variants.some(function(v){return v.label===lbl;})){
      c.variants.push({label:lbl,overrides:Object.assign({},u.paramOverrides)});
    }
  }
}
function loadConfig(){
  fetch(WS+'/get_config').then(function(r){return r.json();})
  .then(function(d){
    if(d.comfy_server)_comfySrv=d.comfy_server;if(d.timeout)_timeout=d.timeout;
    if(d.comfy_path){var cp=document.getElementById('comfyPathV');if(cp)cp.value=d.comfy_path;}
    if(d.workflow_folder){var fp=document.getElementById('folderPathInput');if(fp&&!fp.value){fp.value=d.workflow_folder;serverFolder=d.workflow_folder;}}
    if(d.order&&d.order.length){_pendingSavedOrderV=d.order;}
    if(d.workflow_folder&&!Object.keys(workflows).length){loadFromServer();}
  }).catch(function(){});
}

/* ── boot ── */
_initSec('wf',    false);
_initSec('order', false);
_initSec('graph', false);
_initSec('results',false);
loadConfig();connectSSE();checkComfy();setInterval(checkComfy,4000);
function restartWedge(){
  if(!confirm('Restart Wedge Studio?\\nComfyUI will also be restarted.\\nPage will reload when back online.')) return;
  _log('\u21bb Restarting Wedge Studio + ComfyUI\u2026', 'warn');
  var _cpPath=(document.getElementById('comfyPathV')||{}).value||'';
  fetch(WS+'/restart_wedge',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({comfy_path:_cpPath})
  }).catch(function(){});
  _log('   Server restarting \u2014 waiting\u2026', 'warn');
  var _wsW=0, _wsIv=setInterval(function(){
    _wsW+=2000;
    fetch(WS+'/get_config').then(function(r){
      if(r.ok){
        clearInterval(_wsIv);
        _log('   \u2713 Server back \u2014 reloading\u2026','ok');
        setTimeout(function(){window.location.reload();},600);
      }
    }).catch(function(){
      if(_wsW>=60000){clearInterval(_wsIv);_log('   Server did not respond \u2014 reload manually','err');}
    });
  },2000);
}

/* ── compare + wipe (desktop parity) ── */
var _vwStore=[],_vwSel=[];
function _vwResetCompare(){
  _vwStore.length=0;_vwSel.length=0;
  var b=document.getElementById('vwBar');if(b)b.classList.remove('vis');
  var c=document.getElementById('vwCnt');if(c)c.textContent='0 selected';
  var btn=document.getElementById('vwBtn');if(btn)btn.disabled=true;
}
function _vwToggle(i){
  var p=_vwSel.indexOf(i);
  if(p>=0)_vwSel.splice(p,1);
  else{if(_vwSel.length>=2)_vwSel.shift();_vwSel.push(i);}
  document.querySelectorAll('.rcard').forEach(function(cd){
    var x=Number(cd.dataset.vidx);
    cd.classList.toggle('in-cmp',_vwSel.indexOf(x)>=0);
  });
  var n=_vwSel.length;
  var c=document.getElementById('vwCnt');
  if(c)c.textContent=n===0?'0 selected':(n===1?'1 selected (pick one more)':'2 selected');
  var btn=document.getElementById('vwBtn');if(btn)btn.disabled=n!==2;
}
function vwClear(){
  _vwSel.length=0;
  document.querySelectorAll('.rcard.in-cmp').forEach(function(cd){cd.classList.remove('in-cmp');});
  var c=document.getElementById('vwCnt');if(c)c.textContent='0 selected';
  var btn=document.getElementById('vwBtn');if(btn)btn.disabled=true;
}
function _vwMedia(r,host){
  host.innerHTML='';
  if(r&&r.url&&r.isVid){var v=document.createElement('video');v.src=r.url;v.loop=true;v.muted=true;v.playsInline=true;host.appendChild(v);}
  else if(r&&r.url){var im=document.createElement('img');im.src=r.url;host.appendChild(im);}
  else{host.innerHTML='<div style="color:#555550;font-size:10px;padding:20px">No media</div>';}
}
function vwOpen(){
  if(_vwSel.length!==2)return;
  var a=_vwStore[_vwSel[0]],b=_vwStore[_vwSel[1]];
  _vwMedia(a,document.getElementById('vwA'));
  _vwMedia(b,document.getElementById('vwB'));
  document.getElementById('vwLblA').textContent=a?a.name:'';
  document.getElementById('vwLblB').textContent=b?b.name:'';
  vwSetPos(50);
  document.getElementById('vwLb').classList.add('open');
  setTimeout(function(){
    document.querySelectorAll('#vwA video,#vwB video').forEach(function(v){v.play().catch(function(){});});
    _vwBindSync();_vwScrubInit();_vwPlayBtn();
  },120);
}
function vwCloseLb(){
  document.getElementById('vwLb').classList.remove('open');
  document.querySelectorAll('#vwA video,#vwB video').forEach(function(v){v.pause();v.playbackRate=1;});
}
function vwSetPos(p){
  document.getElementById('vwA').style.clipPath='inset(0 '+(100-p)+'% 0 0)';
  document.getElementById('vwHandle').style.left=p+'%';
}
(function(){
  var drag=false;
  function pct(e){var w=document.getElementById('vwWrap');if(!w)return 50;var r=w.getBoundingClientRect();var x=e.touches?e.touches[0].clientX:e.clientX;return Math.max(2,Math.min(98,(x-r.left)/r.width*100));}
  document.addEventListener('mousedown',function(e){if(e.target.id==='vwHandle')drag=true;});
  document.addEventListener('mouseup',function(){drag=false;});
  document.addEventListener('mousemove',function(e){if(drag)vwSetPos(pct(e));});
  document.addEventListener('touchstart',function(e){if(e.target.id==='vwHandle')drag=true;},{passive:true});
  document.addEventListener('touchend',function(){drag=false;});
  document.addEventListener('touchmove',function(e){if(drag)vwSetPos(pct(e));},{passive:true});
})();
function _vwBindSync(){
  var va=document.querySelector('#vwA video'),vb=document.querySelector('#vwB video');
  if(!va||!vb)return;
  var s=false;
  va.addEventListener('timeupdate',function(){
    if(s)return;s=true;
    if(Math.abs(vb.currentTime-va.currentTime)>.05)vb.currentTime=va.currentTime;
    if(!va.paused&&vb.paused)vb.play().catch(function(){});
    if(va.paused&&!vb.paused)vb.pause();
    s=false;
  });
  va.addEventListener('play',function(){vb.play().catch(function(){});_vwPlayBtn();});
  va.addEventListener('pause',function(){vb.pause();_vwPlayBtn();});
  vb.addEventListener('play',function(){va.play().catch(function(){});_vwPlayBtn();});
  vb.addEventListener('pause',function(){va.pause();_vwPlayBtn();});
}
function vwTogglePlay(){
  var vids=[].slice.call(document.querySelectorAll('#vwA video,#vwB video'));
  if(!vids.length)return;
  var any=vids.some(function(v){return !v.paused;});
  vids.forEach(function(v){if(any)v.pause();else v.play().catch(function(){});});
}
function _vwPlayBtn(){
  var vids=[].slice.call(document.querySelectorAll('#vwA video,#vwB video'));
  var any=vids.some(function(v){return !v.paused;});
  var b=document.getElementById('vwPlayBtn');if(b)b.textContent=any?'\u23F8 Pause':'\u25B6 Play';
}
function vwSpeed(r){
  document.querySelectorAll('#vwA video,#vwB video').forEach(function(v){v.playbackRate=r;});
  document.querySelectorAll('.vw-spd button').forEach(function(b){b.classList.toggle('on',Math.abs(parseFloat(b.textContent.replace('\u00d7',''))-r)<.001);});
}
var _vwScrubDrag=false;
function _vwScrubInit(){
  var va=document.querySelector('#vwA video')||document.querySelector('#vwB video');
  if(va){va.addEventListener('timeupdate',_vwScrubFromVid);va.addEventListener('loadedmetadata',_vwScrubFromVid);}
  var t=document.getElementById('vwTrack');
  if(!t||t.dataset.init)return;
  t.dataset.init='1';
  function pct(e){var r=t.getBoundingClientRect();var x=e.touches?e.touches[0].clientX:e.clientX;return Math.max(0,Math.min(100,(x-r.left)/r.width*100));}
  function upd(p){
    var v=document.querySelector('#vwA video')||document.querySelector('#vwB video');
    if(!v||!v.duration)return;
    var tm=p/100*v.duration;
    document.querySelectorAll('#vwA video,#vwB video').forEach(function(x){x.currentTime=tm;});
    _vwScrubSet(p,tm,v.duration);
  }
  t.addEventListener('mousedown',function(e){_vwScrubDrag=true;document.querySelectorAll('#vwA video,#vwB video').forEach(function(v){v.pause();});upd(pct(e));});
  document.addEventListener('mousemove',function(e){if(_vwScrubDrag)upd(pct(e));});
  document.addEventListener('mouseup',function(){_vwScrubDrag=false;});
  t.addEventListener('touchstart',function(e){_vwScrubDrag=true;upd(pct(e));},{passive:true});
  document.addEventListener('touchmove',function(e){if(_vwScrubDrag)upd(pct(e));},{passive:true});
  document.addEventListener('touchend',function(){_vwScrubDrag=false;});
}
function _vwScrubSet(p,tm,dur){
  var n=document.getElementById('vwNeedle'),f=document.getElementById('vwFill'),l=document.getElementById('vwFrame');
  if(n)n.style.left=p+'%';
  if(f)f.style.width=p+'%';
  if(l&&dur){var fps=parseInt((document.getElementById('vwFps')||{}).value)||30;l.textContent='frame '+Math.round(tm*fps)+' / '+Math.round(dur*fps);}
}
function _vwScrubFromVid(){
  var v=document.querySelector('#vwA video')||document.querySelector('#vwB video');
  if(!v||!v.duration)return;
  _vwScrubSet(v.currentTime/v.duration*100,v.currentTime,v.duration);
}
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&document.getElementById('vwLb').classList.contains('open'))vwCloseLb();});

/* result filter */
var _rfSt={active:false,wf:null,outs:null};
function _rfToggle(){
  var tog=document.getElementById('rfTogV'),bar=document.getElementById('rfBarV');
  _rfSt.active=!_rfSt.active;
  if(tog)tog.classList.toggle('on',_rfSt.active);
  if(bar)bar.style.display=_rfSt.active?'flex':'none';
  if(!_rfSt.active){_rfSt.wf=null;_rfSt.outs=null;}
  _rfApply();_rfRebuildWf();_rfRebuildOut(_rfMaxOuts(_rfSt.wf));
}
function _rfApply(){
  var list=document.getElementById('resultsList');if(!list)return;
  list.querySelectorAll('.rcard').forEach(function(c){
    var show=true;
    if(_rfSt.active){
      if(_rfSt.wf&&c.dataset.rfWf!==_rfSt.wf)show=false;
      if(show&&_rfSt.outs&&_rfSt.outs.size){if(!_rfSt.outs.has(parseInt(c.dataset.rfIdx)||1))show=false;}
    }
    c.classList.toggle('rf-hide',!show);
  });
  var rc=document.getElementById('results-cnt');
  if(rc){
    var l2=document.getElementById('resultsList');
    var tot=l2?l2.querySelectorAll('.rcard').length:0;
    var vis=l2?l2.querySelectorAll('.rcard:not(.rf-hide)').length:tot;
    rc.textContent=(_rfSt.active&&vis!==tot?vis+'/':'')+tot+' output'+(tot===1?'':'s');
  }
}
function _rfGetWfs(){
  var seen={},list=[];
  var el=document.getElementById('resultsList');if(!el)return list;
  el.querySelectorAll('.rcard').forEach(function(c){var w=c.dataset.rfWf;if(w&&!seen[w]){seen[w]=1;list.push(w);}});
  return list;
}
function _rfMaxOuts(wf){
  var mx=0;var el=document.getElementById('resultsList');if(!el)return mx;
  el.querySelectorAll('.rcard').forEach(function(c){
    if(wf&&c.dataset.rfWf!==wf)return;
    var t=parseInt(c.dataset.rfTotal)||1;if(t>mx)mx=t;
  });return mx;
}
function _rfSetWf(wf){
  _rfSt.wf=wf;_rfSt.outs=null;
  _rfRebuildWf();_rfRebuildOut(_rfMaxOuts(wf));_rfApply();
}
function _rfRebuildWf(){
  var row=document.getElementById('rfWfRowV');if(!row)return;
  row.innerHTML='';
  var all=document.createElement('span');all.className='rfc wfc'+((!_rfSt.wf)?' on':'');
  all.textContent='All';all.addEventListener('click',function(){_rfSetWf(null);});row.appendChild(all);
  _rfGetWfs().forEach(function(wf){
    var c=document.createElement('span');c.className='rfc wfc'+((_rfSt.wf===wf)?' on':'');
    c.textContent=wf;c.addEventListener('click',function(){_rfSetWf(_rfSt.wf===wf?null:wf);});
    row.appendChild(c);
  });
}
function _rfRebuildOut(mx){
  var row=document.getElementById('rfOutRowV'),sep=document.getElementById('rfSepV');
  if(!row)return;
  row.innerHTML='';
  if(!mx||mx<=1){row.style.display='none';if(sep)sep.style.display='none';return;}
  row.style.display='flex';if(sep)sep.style.display='';
  var lbl=document.createElement('span');lbl.className='rf-lbl';
  lbl.textContent='Output\u00a0';row.appendChild(lbl);
  var all=document.createElement('span');all.className='rfc'+((!_rfSt.outs||!_rfSt.outs.size)?' on':'');
  all.textContent='All';
  all.addEventListener('click',function(){_rfSt.outs=null;_rfRebuildOut(mx);_rfApply();});
  row.appendChild(all);
  for(var n=1;n<=mx;n++)(function(idx){
    var c=document.createElement('span');c.className='rfc'+((_rfSt.outs&&_rfSt.outs.has(idx))?' on':'');
    c.textContent=String(idx);
    c.addEventListener('click',function(){
      if(!_rfSt.outs)_rfSt.outs=new Set();
      if(_rfSt.outs.has(idx))_rfSt.outs.delete(idx);else _rfSt.outs.add(idx);
      if(!_rfSt.outs.size)_rfSt.outs=null;
      _rfRebuildOut(mx);_rfApply();
    });row.appendChild(c);
  })(n);
}
/* reset on new run */
var _rfOrigReset=_vwResetCompare;
_vwResetCompare=function(){
  _rfOrigReset();
  _rfSt.wf=null;_rfSt.outs=null;
  _rfRebuildWf();_rfRebuildOut(0);_rfApply();
};

</script>
</body>
</html>"""



def _clean_order_for_save(order):
    """Strip transient runtime-only keys (_status etc.) from order units."""
    _transient = {'_status', '_running', '_result'}
    cleaned = []
    for u in (order or []):
        cleaned.append({k: v for k, v in u.items() if k not in _transient})
    return cleaned

def _atomic_cfg_save(cfg_file, cfg):
    """Write cfg atomically: temp file → os.replace. Call inside _cfg_lock."""
    tmp = cfg_file + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(json.dumps(cfg, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, cfg_file)
    except Exception:
        try: os.unlink(tmp)
        except Exception: pass
        raise


class WedgeHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        code = args[1] if len(args) > 1 else '?'
        path = self.path.split('?')[0]
        # suppress high-frequency and low-value paths
        _quiet = {
            '/', '/wedge_studio.html', '/comfy_proxy/system_stats',
            '/get_config', '/local_output', '/browse', '/list_workflows',
            '/events', '/run_state',  # Phase 1 SSE
            '/live', '/viewer', '/manifest.json',
            '/start_run', '/stop_run',  # Phase 2 executor
        }
        if path in _quiet or path.startswith('/comfy_proxy/history/'):
            return
        print(f"  {code}  {path}")

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')

        # serve the main UI
        if path in ('', '/', '/wedge_studio.html', '/wedge_studio'):
            # Auto-redirect phones to the purpose-built mobile view.
            # Add ?desktop=1 to force the full UI on a mobile device.
            _ua = self.headers.get('User-Agent', '')
            _qs = parse_qs(parsed.query)
            if (any(m in _ua for m in ('iPhone','iPad','Android','Mobile'))
                    and 'desktop' not in _qs):
                self.send_response(302)
                self.send_header('Location', '/live')
                self.end_headers()
                return
            body = _build_html().encode('utf-8', errors='replace')
            self.send_response(200)
            self.send_header('Content-Type',   'text/html; charset=utf-8')
            self.send_header('Cache-Control',  'no-store, no-cache, must-revalidate')
            self.send_header('Pragma',         'no-cache')
            self.send_header('Expires',        '0')
            self.send_header('Content-Length', str(len(body)))
            self.send_cors()
            self.end_headers()
            self.wfile.write(body)
            return

        # load wedge config (comfy path, etc)
        if path == '/get_config':
            cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
            try:
                cfg = json.loads(open(cfg_file).read()) if os.path.exists(cfg_file) else {}
                # auto-detect ComfyUI path if not saved yet
                if not cfg.get('comfy_path'):
                    detected = _detect_comfy_path()
                    if detected:
                        cfg['comfy_path'] = detected
                        try:
                            with _cfg_lock: _atomic_cfg_save(cfg_file, cfg)
                        except Exception: pass
                self._json_ok(cfg)
            except Exception as e:
                self._json_error(str(e))
            return

        # browse directory tree (for folder picker)
        if path == '/browse':
            qs = parse_qs(parsed.query)
            folder = unquote(qs.get('folder', ['.'])[0])
            try:
                p = Path(folder).resolve()
                # get parent chain for breadcrumb
                parents = []
                cur = p
                for _ in range(10):
                    par = cur.parent
                    if par == cur: break
                    parents.insert(0, {'name': cur.name or str(cur), 'path': str(cur)})
                    cur = par
                parents.insert(0, {'name': str(cur), 'path': str(cur)})
                # list subdirectories
                subdirs = sorted(
                    [{'name': d.name, 'path': str(d)} for d in p.iterdir() if d.is_dir() and not d.name.startswith('.')],
                    key=lambda x: x['name'].lower()
                )
                # count .json files
                json_count = len([f for f in p.iterdir() if f.suffix.lower() == '.json'])
                body = json.dumps({'ok': True, 'current': str(p), 'parents': parents,
                                   'subdirs': subdirs, 'json_count': json_count}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_cors()
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self._json_error(str(e))
            return

        # list .json files in a directory
        if path == '/list_workflows':
            qs = parse_qs(parsed.query)
            folder = qs.get('folder', ['.'])[0]
            folder = unquote(folder)
            try:
                # '.' means default: use the script's own directory,
                # NOT os.getcwd() which changes depending on where you
                # launched the .py from.
                script_dir = Path(os.path.abspath(__file__)).parent
                if folder == '.':
                    # Prefer the last-used workflow folder saved in config.
                    # Falls back to script dir if not set or folder missing.
                    _wf_cfg = os.path.join(str(script_dir), '_wedge_config.json')
                    try:
                        _wf_data = json.loads(open(_wf_cfg).read()) if os.path.exists(_wf_cfg) else {}
                        _wf_dir  = _wf_data.get('workflow_folder', '')
                        p = Path(_wf_dir).resolve() if _wf_dir and Path(_wf_dir).is_dir() else script_dir
                    except Exception:
                        p = script_dir
                else:
                    p = Path(folder).resolve()
                files = sorted(
                    [f.name for f in p.iterdir() if f.suffix.lower() == '.json'],
                    key=str.lower
                )
                body = json.dumps({'ok': True, 'folder': str(p), 'files': files}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_cors()
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self._json_error(str(e))
            return


        # serve output files directly from ComfyUI output folder (for report media)
        if path == '/local_output':
            qs = parse_qs(parsed.query)
            filename  = unquote(qs.get('filename',  [''])[0])
            subfolder = unquote(qs.get('subfolder', [''])[0])
            ftype     = unquote(qs.get('type',      ['output'])[0])
            if not filename:
                self._json_error('filename required'); return
            cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
            try:
                cfg = json.loads(open(cfg_file).read()) if os.path.exists(cfg_file) else {}
            except Exception:
                cfg = {}
            comfy_path = cfg.get('comfy_path', '')
            if not comfy_path:
                self._json_error('ComfyUI path not configured — set it in the header and click ✓'); return
            output_root = os.path.join(comfy_path, ftype if ftype in ('output','input','temp') else 'output')
            file_path = os.path.join(output_root, subfolder, filename) if subfolder else os.path.join(output_root, filename)
            file_path = os.path.normpath(file_path)
            # safety: must stay inside the output root
            if not file_path.startswith(os.path.normpath(comfy_path)):
                self._json_error('path outside ComfyUI folder'); return
            try:
                with open(file_path, 'rb') as fh:
                    data = fh.read()
                mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.send_cors()
                self.end_headers()
                self.wfile.write(data)
            except FileNotFoundError:
                self._json_error(f'file not found: {file_path}')
            except Exception as e:
                self._json_error(str(e))
            return

        # proxy ComfyUI GET calls
        if path.startswith('/comfy_proxy/'):
            import urllib.request as _ur
            comfy_path = path[len('/comfy_proxy'):]
            qs = parsed.query
            _g_cf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
            try: _g_srv = json.loads(open(_g_cf).read()).get('comfy_server','127.0.0.1:8188') if os.path.exists(_g_cf) else '127.0.0.1:8188'
            except Exception: _g_srv = '127.0.0.1:8188'
            comfy_url = f'http://{_g_srv}{comfy_path}' + (f'?{qs}' if qs else '')
            try:
                with _ur.urlopen(comfy_url, timeout=5) as resp:
                    rbody = resp.read()
                    self.send_response(resp.status)
                    self.send_header('Content-Type', resp.headers.get('Content-Type','application/json'))
                    self.send_cors()
                    self.end_headers()
                    self.wfile.write(rbody)
            except Exception as e:
                self._json_error(f'ComfyUI unreachable: {e}')
            return

        # read a workflow file
        if path == '/read_workflow':
            qs = parse_qs(parsed.query)
            filepath = unquote(qs.get('path', [''])[0])
            try:
                content = Path(filepath).read_text(encoding='utf-8')
                body = json.dumps({'ok': True, 'content': content}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_cors()
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self._json_error(str(e))
            return

        # Legacy alias: /viewer → /live (keep old bookmarks/cache working)
        if path == '/viewer':
            self.send_response(301)
            self.send_header('Location', '/live')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return

        # Mobile read-only live view
        if path == '/live':
            body = _VIEWER_HTML.encode('utf-8', errors='replace')
            self.send_response(200)
            self.send_header('Content-Type',   'text/html; charset=utf-8')
            self.send_header('Cache-Control',  'no-store, no-cache, must-revalidate')
            self.send_header('Pragma',         'no-cache')
            self.send_header('Expires',        '0')
            self.send_header('Content-Length', str(len(body)))
            self.send_cors()
            self.end_headers()
            self.wfile.write(body)
            return

        # PWA web-app manifest (for Add to Home Screen)
        if path == '/manifest.json':
            manifest = {
                'name':             'Wedge Studio',
                'short_name':       'Wedge',
                'description':      'District Zero AI Lab — Wedge Studio Live View',
                'start_url':        '/live',
                'display':          'standalone',
                'background_color': '#0a0a0a',
                'theme_color':      '#d18d1f',
                'icons': [{
                    'src':     'https://cdn.jsdelivr.net/gh/Gerry-Malta/AI_LAB@main/_img/DZ_logo_5.png',
                    'sizes':   'any',
                    'type':    'image/png',
                    'purpose': 'any'
                }]
            }
            body = json.dumps(manifest, indent=2).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/manifest+json')
            self.send_header('Content-Length', str(len(body)))
            self.send_cors()
            self.end_headers()
            self.wfile.write(body)
            return

        # Phase 1: SSE live run-state stream
        if path == '/events':
            self._do_sse()
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n)


        # restart Wedge Studio server — also restarts ComfyUI if comfy_path known
        if path == '/shutdown':
            # Graceful self-shutdown — used by _kill_previous_instance()
            # on the next startup to cleanly terminate this process.
            try:
                self._json_ok({'ok': True, 'msg': 'Shutting down'})
                self.wfile.flush()
            except Exception:
                pass
            def _do_shutdown():
                import time as _ts
                _ts.sleep(0.3)   # let the HTTP response flush
                os.kill(os.getpid(), __import__('signal').SIGTERM
                        if sys.platform != 'win32' else
                        __import__('signal').SIGBREAK)
            threading.Thread(target=_do_shutdown, daemon=True).start()
            return

        if path == '/restart_wedge':
            try: _rw_body = json.loads(body) if body else {}
            except Exception: _rw_body = {}
            _rw_cp = _rw_body.get('comfy_path', '').strip()
            if not _rw_cp:
                _rw_cf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
                try: _rw_cp = (json.loads(open(_rw_cf).read()) if os.path.exists(_rw_cf) else {}).get('comfy_path', '').strip()
                except Exception: _rw_cp = ''
            if _rw_cp:
                _rw_cp = os.path.abspath(_rw_cp)
            try:
                self._json_ok({'ok': True, 'msg': 'Restarting Wedge Studio...'})
                self.wfile.flush()
            except Exception:
                pass
            def _do_restart_wedge(_cp=_rw_cp):
                import time as _t2
                # ── kill + relaunch ComfyUI first if path is known ────────────
                if _cp:
                    _e_log('  ↻ Killing ComfyUI…', 'warn')
                    try:
                        import psutil as _pu2
                        _our = os.getpid()
                        for _p in _pu2.process_iter(['pid', 'cmdline', 'cwd']):
                            try:
                                if _p.pid == _our: continue
                                _cmd = ' '.join(_p.info['cmdline'] or [])
                                _cwd = (_p.info['cwd'] or '').lower()
                                if 'main.py' in _cmd and ('comfyui' in _cmd.lower() or
                                        'comfyui' in _cwd or _cp.lower() in _cwd):
                                    _e_log(f'    Killed ComfyUI PID {_p.pid}', 'warn')
                                    _p.kill(); _p.wait(timeout=5); break
                            except Exception: pass
                    except ImportError:
                        if sys.platform.startswith('win'):
                            os.system('taskkill /F /FI "WINDOWTITLE eq *ComfyUI*" 2>nul')
                    _t2.sleep(1.5)
                    _main = os.path.join(_cp, 'main.py')
                    if os.path.exists(_main):
                        _vpy = os.path.join(_cp, 'venv', 'Scripts', 'python.exe')
                        _epy = os.path.join(_cp, 'python_embeded', 'python.exe')
                        _pexe = (_vpy if os.path.exists(_vpy) else
                                 _epy if os.path.exists(_epy) else sys.executable)
                        import subprocess as _sp3
                        _sp3.Popen([_pexe, _main, '--enable-cors-header', '*'], cwd=_cp,
                                   creationflags=_sp3.CREATE_NEW_CONSOLE if sys.platform.startswith('win') else 0)
                        _e_log(f'  ↻ ComfyUI relaunching from {_cp}', 'warn')
                    else:
                        _e_log(f'  ✗ ComfyUI main.py not found at {_cp}', 'err')
                # ── now restart Wedge Studio itself ───────────────────────────
                _t2.sleep(0.5)
                _script = os.path.abspath(__file__)
                _py2 = sys.executable
                import subprocess as _sp2
                _sp2.Popen([_py2, _script, '--no-browser', str(PORT)], cwd=os.path.dirname(_script))
                _t2.sleep(0.2)
                os._exit(0)
            import threading as _th2
            _th2.Thread(target=_do_restart_wedge, daemon=True).start()
            return

        # restart ComfyUI (kill + relaunch)
        if path == '/restart_comfy':
            try:
                data = json.loads(body) if body else {}
                _rcpath = data.get('comfy_path', '').strip()
                if not _rcpath:
                    # fallback: read from saved config
                    _rccf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
                    try: _rcpath = json.loads(open(_rccf).read()).get('comfy_path','') if os.path.exists(_rccf) else ''
                    except Exception: _rcpath = ''
                comfy_path = os.path.abspath(_rcpath) if _rcpath else ''
                if not comfy_path:
                    self._json_error('ComfyUI path not set'); return

                import signal as _signal

                # save path for future use
                cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
                try:
                    cfg = json.loads(open(cfg_file).read()) if os.path.exists(cfg_file) else {}
                    cfg['comfy_path'] = comfy_path
                    with _cfg_lock: _atomic_cfg_save(cfg_file, cfg)
                except Exception: pass

                # find ComfyUI process — target specific PID, never kill all python
                killed = False
                try:
                    import psutil
                    our_pid = os.getpid()  # wedge_studio.py PID — never kill this
                    candidates = []
                    for proc in psutil.process_iter(['pid','name','cmdline','cwd']):
                        try:
                            if proc.pid == our_pid: continue  # never kill ourselves
                            cmd = ' '.join(proc.info['cmdline'] or [])
                            cwd = (proc.info['cwd'] or '').lower()
                            if 'main.py' in cmd and (
                                comfy_path.lower() in cwd or
                                'comfyui' in cmd.lower() or
                                'comfyui' in cwd
                            ):
                                candidates.append(proc)
                        except Exception: pass
                    if candidates:
                        # kill the best match (most recently started)
                        target = sorted(candidates, key=lambda p: p.create_time())[-1]
                        print(f'  Killing ComfyUI PID {target.pid} (cmd: {" ".join(target.cmdline()[:3])})')
                        target.kill()
                        target.wait(timeout=5)
                        killed = True
                    else:
                        print('  No ComfyUI process found via psutil')
                except ImportError:
                    # psutil not available — use targeted taskkill by window title
                    if sys.platform.startswith('win'):
                        # kill by window title pattern, NOT /IM python.exe (would kill wedge too)
                        result = os.system('taskkill /F /FI "WINDOWTITLE eq *ComfyUI*" 2>nul')
                        killed = (result == 0)
                        if not killed:
                            print('  taskkill by window title failed — install psutil for reliable kills')
                            print('  Run: pip install psutil --break-system-packages')

                import time as _time
                _time.sleep(2)

                # relaunch ComfyUI
                main_py = os.path.join(comfy_path, 'main.py')
                if not os.path.exists(main_py):
                    self._json_error(f'main.py not found at {comfy_path}')
                    return

                # find python in the comfy venv or system
                venv_py = os.path.join(comfy_path, 'venv', 'Scripts', 'python.exe')
                emb_py  = os.path.join(comfy_path, 'python_embeded', 'python.exe')
                if os.path.exists(venv_py):
                    python_exe = venv_py
                elif os.path.exists(emb_py):
                    python_exe = emb_py
                else:
                    python_exe = sys.executable

                import subprocess as _sp
                _sp.Popen(
                    [python_exe, main_py, '--enable-cors-header', '*'],
                    cwd=comfy_path,
                    creationflags=_sp.CREATE_NEW_CONSOLE if sys.platform.startswith('win') else 0
                )
                print(f'  ComfyUI relaunching from {comfy_path}')
                self._json_ok({'killed': killed, 'relaunched': True, 'path': comfy_path})
            except Exception as e:
                self._json_error(str(e))
            return



        # save config
        if path == '/save_config':
            cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
            try:
                data = json.loads(body)
                if 'order' in data:
                    data['order'] = _clean_order_for_save(data['order'])
                with _cfg_lock:
                    existing = json.loads(open(cfg_file).read()) if os.path.exists(cfg_file) else {}
                    if data.get('workflow_folder') and data['workflow_folder'] != existing.get('workflow_folder'):
                        existing.pop('order', None)
                    existing.update(data)
                    _atomic_cfg_save(cfg_file, existing)
                self._json_ok()
            except Exception as e:
                self._json_error(str(e))
            return

        # save report HTML to disk


        if path == '/generate_report':
            try:
                data = json.loads(body)
            except Exception as e:
                self._json_error(f'bad JSON: {e}'); return
            cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
            try:
                cfg = json.loads(open(cfg_file).read()) if os.path.exists(cfg_file) else {}
            except Exception:
                cfg = {}
            comfy_path = cfg.get('comfy_path', '')
            media_info = {}
            MAX_EMBED  = 50 * 1024 * 1024  # 50 MB
            for r in data.get('results', []):
                ro    = r.get('rawOut')
                if not ro: continue
                fn    = ro.get('fn', '')
                sub   = (ro.get('sub') or '').strip('/')
                ftype = ro.get('type', 'output')
                key   = _report_key(ro)
                if not fn or not key: continue
                import re as _re
                is_v = bool(_re.search(r'\.(mp4|webm|mov)$', fn, _re.I))
                info = {'uri': None, 'thumb': None, 'path': None, 'is_vid': is_v, 'fn': fn}
                if comfy_path:
                    root = os.path.join(comfy_path, ftype if ftype in ('output','input','temp') else 'output')
                    fp   = os.path.normpath(os.path.join(root, sub, fn) if sub else os.path.join(root, fn))
                    if fp.startswith(os.path.normpath(comfy_path)):
                        info['path'] = fp
                        try:
                            fsize = os.path.getsize(fp)
                            if fsize <= MAX_EMBED:
                                with open(fp, 'rb') as fh: raw = fh.read()
                                mime = mimetypes.guess_type(fn)[0] or 'application/octet-stream'
                                info['uri'] = 'data:' + mime + ';base64,' + _b64.b64encode(raw).decode('ascii')
                                if not is_v:
                                    info['thumb'] = info['uri']
                            if is_v:
                                info['thumb'] = _get_video_thumb(fp)
                        except Exception:
                            pass
                media_info[key] = info
            try:
                html_content = build_report_html(data, media_info)
            except Exception as e:
                self._json_error(f'build error: {e}'); return
            save_path = data.get('path', '')
            if not save_path:
                self._json_error('no path'); return
            try:
                sp = Path(save_path).resolve()
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(html_content, encoding='utf-8')
                self._json_ok({'path': str(sp)})
            except Exception as e:
                self._json_error(f'save failed: {e}')
            return

        if path == '/save_report':
            try:
                data = json.loads(body)
                save_path = Path(data['path']).resolve()
                html_content = data['html']
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_text(html_content, encoding='utf-8')
                print(f"  Report saved: {save_path}")
                self._json_ok({'saved': str(save_path)})
            except Exception as e:
                self._json_error(str(e))
            return

        if path == '/cleanup_reports':
            try:
                data = json.loads(body)
                paths = data.get('paths', [])
                deleted = 0
                for p in paths:
                    try:
                        fp = Path(p).resolve()
                        if (fp.name.startswith('wedge_report_') and
                                fp.suffix.lower() == '.html' and
                                fp.is_file()):
                            fp.unlink()
                            deleted += 1
                    except Exception:
                        pass
                self._json_ok({'deleted': deleted})
            except Exception as e:
                self._json_error(str(e))
            return

        # proxy ComfyUI API calls (avoids CORS cross-port issues)
        if path.startswith('/comfy_proxy/'):
            import urllib.request as _ur
            comfy_path = path[len('/comfy_proxy'):]  # e.g. /system_stats
            _p_cf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
            try: _p_srv = json.loads(open(_p_cf).read()).get('comfy_server','127.0.0.1:8188') if os.path.exists(_p_cf) else '127.0.0.1:8188'
            except Exception: _p_srv = '127.0.0.1:8188'
            comfy_url = f'http://{_p_srv}{comfy_path}'
            # /free can take a while to unload models — give it more time
            _proxy_timeout = 30 if comfy_path == '/free' else 5
            try:
                req = _ur.Request(comfy_url, data=body or None,
                    headers={'Content-Type': self.headers.get('Content-Type','application/json')},
                    method=self.command)
                with _ur.urlopen(req, timeout=_proxy_timeout) as resp:
                    rbody = resp.read()
                    self.send_response(resp.status)
                    self.send_header('Content-Type', resp.headers.get('Content-Type','application/json'))
                    self.send_cors()
                    self.end_headers()
                    self.wfile.write(rbody)
            except Exception as e:
                self._json_error(f'ComfyUI unreachable: {e}')
            return

        # read multiple workflow files at once
        if path == '/read_workflows':
            try:
                data = json.loads(body)
                folder = Path(data['folder']).resolve()
                results = {}
                for fname in data.get('files', []):
                    try:
                        content = (folder / fname).read_text(encoding='utf-8')
                        results[fname] = {'ok': True, 'content': content}
                    except Exception as e:
                        results[fname] = {'ok': False, 'error': str(e)}
                self._json_ok({'workflows': results})
            except Exception as e:
                self._json_error(str(e))
            return

        # Phase 2: start Python executor
        if path == '/start_run':
            global _executor_thread, _executor_stop
            try:
                data = json.loads(body) if body else {}
                with _executor_lock:
                    if _executor_thread and _executor_thread.is_alive():
                        self._json_error('Run already in progress'); return
                    order_in   = data.get('order', [])
                    if not order_in:
                        self._json_error('Empty order'); return
                    comfy_url  = data.get('comfy_server', '127.0.0.1:8188').strip()
                    # persist order + server (+ optional workflow_folder from /live) to config
                    try:
                        _cf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
                        _cd = json.loads(open(_cf).read()) if os.path.exists(_cf) else {}
                        _update = {'order': order_in,
                                   'comfy_server': comfy_url,
                                   'timeout': data.get('timeout', 20)}
                        # if client explicitly sends workflow_folder, trust it
                        if data.get('workflow_folder'):
                            _update['workflow_folder'] = data['workflow_folder'].strip()
                        _cd.update(_update)
                        open(_cf, 'w').write(json.dumps(_cd, indent=2))
                    except Exception:
                        pass
                    timeout_s  = float(data.get('timeout', 20)) * 60
                    cfg_file   = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_wedge_config.json')
                    try:
                        cfg = json.loads(open(cfg_file).read()) if os.path.exists(cfg_file) else {}
                    except Exception:
                        cfg = {}
                    wf_folder  = cfg.get('workflow_folder',
                                         str(Path(os.path.abspath(__file__)).parent))
                    _executor_stop.clear()
                    _executor_thread = threading.Thread(
                        target=_run_executor,
                        args=(order_in, comfy_url, timeout_s, wf_folder),
                        daemon=True)
                    _executor_thread.start()
                self._json_ok({'started': True})
            except Exception as e:
                self._json_error(str(e))
            return

        # Phase 2: stop Python executor
        if path == '/stop_run':
            _executor_stop.set()
            self._json_ok({'stopping': True})
            return

        # Phase 1: receive run-state push from the driving client
        if path == '/run_state':
            try:
                data = json.loads(body) if body else {}
                _broadcast(data)
                self._json_ok()
            except Exception as e:
                self._json_error(str(e))
            return

        self.send_response(404)
        self.end_headers()

    def _json_ok(self, data=None):
        payload = json.dumps({'ok': True, **(data or {})}).encode()
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.send_cors()
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _json_error(self, msg):
        payload = json.dumps({'ok': False, 'error': msg}).encode()
        try:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.send_cors()
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass


    def _do_sse(self):
        """
        Handle GET /events — Server-Sent Events live run-state stream.

        Each connected client gets its own queue.  _broadcast() puts the
        serialised _run_state into every queue; we drain it here and write
        SSE frames to the socket.  A 15-second queue timeout generates an
        SSE comment (': heartbeat') to keep load-balancers and mobile
        radios from closing the connection.

        Runs in its own thread (ThreadingMixIn) so it never blocks other
        requests.  daemon_threads=True means it dies with the server on
        Ctrl-C without needing explicit cleanup.
        """
        q = _queue.Queue(maxsize=64)
        with _state_lock:
            # Auto-reset orphaned run: if running=True but the driver
            # hasn't pushed in >30 s and no other clients are connected,
            # the driving browser was closed mid-run.  Reset so a fresh
            # page-load shows clean idle state, not a frozen progress bar.
            if (_run_state.get('running') and
                    not _sse_clients and
                    not (_executor_thread and _executor_thread.is_alive()) and
                    _time_mod.time() - _run_state.get('ts', 0) > 30):
                _run_state.update({
                    'running': False, 'progress_text': '',
                    'job_pct': 0.0, 'batch_pct': 0.0,
                })
            _sse_clients.append(q)
            initial = json.dumps(_run_state)

        try:
            self.send_response(200)
            self.send_header('Content-Type',      'text/event-stream')
            self.send_header('Cache-Control',     'no-cache')
            self.send_header('Connection',        'keep-alive')
            self.send_header('X-Accel-Buffering', 'no')   # disable nginx buffering
            self.send_cors()
            self.end_headers()
            # send current state immediately so a late-joining viewer
            # gets the current progress without waiting for the next push
            self.wfile.write(('data: ' + initial + '\n\n').encode())
            self.wfile.flush()
        except Exception:
            with _state_lock:
                try:   _sse_clients.remove(q)
                except ValueError: pass
            return

        while True:
            try:
                payload = q.get(timeout=15)
                self.wfile.write(('data: ' + payload + '\n\n').encode())
                self.wfile.flush()
            except _queue.Empty:
                # heartbeat — SSE comment, browsers ignore it
                try:
                    self.wfile.write(b': heartbeat\n\n')
                    self.wfile.flush()
                except Exception:
                    break
            except Exception:
                break

        with _state_lock:
            try:   _sse_clients.remove(q)
            except ValueError: pass


# ── main ─────────────────────────────────────────────────────────────────────
class WedgeServer(ThreadingMixIn, HTTPServer):
    """
    Threading HTTP server for Wedge Studio.
    • ThreadingMixIn  — each request (incl. SSE) runs in its own thread
    • daemon_threads  — SSE threads die with the server on Ctrl-C
    • allow_reuse_address — no "Address already in use" on fast restarts
    • Silently drops client-disconnect tracebacks.
    """
    allow_reuse_address = True
    daemon_threads      = True
    def handle_error(self, request, client_address):
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, BrokenPipeError, ConnectionResetError)):
            return  # client dropped the connection — nothing to log
        super().handle_error(request, client_address)

def _kill_previous_instance():
    """
    Before binding the port, kill any previous Wedge Studio process so
    the new one gets a clean start.

    Strategy (Windows-first, graceful on all platforms):
      1. Write a PID file (_wedge.pid) next to this script on clean startup.
      2. On startup, read the PID file:
           a. Try to reach the old server via HTTP (graceful /shutdown).
           b. If that fails or the old process is frozen, kill by PID.
      3. Delete the stale PID file and write the current PID.

    Falls back silently on any error so a bad PID file never blocks startup.
    """
    import os, sys, time
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pid_file   = os.path.join(script_dir, '_wedge.pid')
    my_pid     = os.getpid()

    # ── try to kill the previous instance ────────────────────────────────
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                old_pid = int(f.read().strip())
        except Exception:
            old_pid = None

        if old_pid and old_pid != my_pid:
            print(f'  ↺  Previous instance (PID {old_pid}) detected — terminating…')
            killed = False

            # Attempt 1: graceful HTTP shutdown (same PORT)
            try:
                import urllib.request as _ur
                _ur.urlopen(
                    f'http://localhost:{PORT}/shutdown',
                    data=b'',
                    timeout=2
                )
                time.sleep(0.8)   # give it a moment to exit cleanly
                killed = True
                print('     Graceful shutdown sent.')
            except Exception:
                pass

            # Attempt 2: kill by PID
            if not killed:
                try:
                    import signal as _sig
                    if sys.platform == 'win32':
                        import subprocess as _sp
                        _sp.run(
                            ['taskkill', '/F', '/PID', str(old_pid)],
                            capture_output=True, timeout=5
                        )
                    else:
                        os.kill(old_pid, _sig.SIGTERM)
                        time.sleep(0.5)
                        # If still alive, SIGKILL
                        try:
                            os.kill(old_pid, 0)   # check if alive
                            os.kill(old_pid, _sig.SIGKILL)
                        except ProcessLookupError:
                            pass
                    print(f'     Process {old_pid} killed.')
                except Exception as e:
                    print(f'     Kill failed (already gone?): {e}')

        # Remove stale PID file regardless
        try:
            os.remove(pid_file)
        except Exception:
            pass

    # ── write our own PID ─────────────────────────────────────────────────
    try:
        with open(pid_file, 'w') as f:
            f.write(str(my_pid))
    except Exception:
        pass   # non-fatal — PID file is best-effort

    # ── clean up PID file on normal exit ──────────────────────────────────
    import atexit
    def _rm_pid():
        try:
            if os.path.exists(pid_file):
                with open(pid_file) as f:
                    if f.read().strip() == str(my_pid):
                        os.remove(pid_file)
        except Exception:
            pass
    atexit.register(_rm_pid)


if __name__ == '__main__':
    _kill_previous_instance()
    server = WedgeServer(('', PORT), WedgeHandler)
    url = f'http://localhost:{PORT}/'
    print()
    print('  ╔══════════════════════════════════════════════╗')
    print(f'  ║   Wedge Studio — District Zero               ║')
    print(f'  ║   http://localhost:{PORT}/                     ║')
    print('  ║   Python executor · SSE · Live Control       ║')
    print(f'  ║   Live:    http://<tailscale-ip>:{PORT}/live   ║')
    print('  ║   Ctrl+C to stop                             ║')
    print('  ╚══════════════════════════════════════════════╝')
    print()

    # open browser after short delay
    if '--no-browser' not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print('  Wedge Studio stopped.')
        server.server_close()
