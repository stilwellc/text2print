"""
ui_server.py — text2print live design UI
=========================================

A Flask companion server providing a real-time browser UI while Claude
designs a 3D-printable object via the text2print skill.

Usage
-----
    python3 tools/ui_server.py                    # port 7384, current directory
    python3 tools/ui_server.py --port 8080        # custom port
    python3 tools/ui_server.py --dir /path        # custom working directory
    python3 tools/ui_server.py --no-browser       # skip auto-opening browser

How it works
------------
1. On startup the server watches the working directory for changes to
   *.stl, *.png, ui_state.json, and ui_approval.json every 400 ms.
2. Changes are broadcast to connected browsers via Server-Sent Events.
3. The browser renders the latest STL in a Three.js viewer, shows render
   images, phase progress, parameters, and the slicer report.
4. VERIFICATION GATES: when ui_state.json contains an "awaiting" object,
   the UI shows an approval banner. The user's decision is written to
   ui_approval.json for Claude to read before proceeding.

ui_state.json schema (written by Claude)
-----------------------------------------
{
  "phase": "Phase 2 — Features",
  "phase_id": "phase2",
  "object": "Arduino Uno enclosure",
  "material": "PETG",
  "printer": "Bambu X1C",
  "message": "Adding M3 heat insert holes on the base corners...",
  "parameters": { "width": 80.0, "depth": 65.0 },
  "slicer_report": { "time": "3h 40m", "filament_g": "31",
                     "support_pct": 0.0, "layers": 184 },
  "awaiting": { "gate": "design-brief",
                "question": "Does this brief match what you want?" }
}

ui_approval.json (written by this server when the user responds)
-----------------------------------------------------------------
{ "gate": "design-brief", "decision": "approve" | "changes",
  "note": "make it 10mm taller", "ts": 1730000000.0 }
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
import time
import webbrowser
from pathlib import Path
from typing import Dict, List

from flask import (Flask, Response, jsonify, render_template_string,
                   request, send_from_directory)

# ---------------------------------------------------------------------------
# Embedded single-page application
# ---------------------------------------------------------------------------

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>text2print — live design</title>

<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:         #100e0b;
  --bg2:        #171410;
  --glass:      rgba(255, 244, 224, 0.045);
  --glass2:     rgba(255, 244, 224, 0.08);
  --border:     rgba(255, 220, 170, 0.12);
  --border2:    rgba(255, 220, 170, 0.25);
  --amber:      #e8a33d;
  --amber2:     #f5c069;
  --amber-dim:  rgba(232, 163, 61, 0.15);
  --text:       #f2e9dc;
  --text-dim:   #a89a84;
  --text-dimmer:#5d5344;
  --green:      #7fc97f;
  --red:        #e07a5f;
  --sidebar-w:  272px;
  --header-h:   52px;
}
html, body { height: 100%; overflow: hidden;
  font-family: 'Avenir Next', 'Segoe UI', system-ui, sans-serif;
  background: var(--bg); color: var(--text); font-size: 13px; }
body::before {   /* golden-hour wash */
  content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background:
    radial-gradient(1200px 500px at 85% -10%, rgba(232,163,61,0.10), transparent 60%),
    radial-gradient(900px 500px at -10% 110%, rgba(232,120,61,0.06), transparent 60%);
}
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }

#app { display: flex; flex-direction: column; height: 100vh; position: relative; z-index: 1; }

/* ── Header ─────────────────────────────────────────────────────────── */
#header {
  height: var(--header-h); min-height: var(--header-h);
  display: flex; align-items: center; gap: 14px; padding: 0 18px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(255,244,224,0.03), transparent);
  backdrop-filter: blur(10px);
}
#logo { font-size: 17px; font-weight: 700; letter-spacing: -0.4px; flex-shrink: 0; }
#logo .t2p-text { color: var(--text); }
#logo .t2p-2 { color: var(--amber); font-weight: 800; }
#logo .t2p-print { background: linear-gradient(90deg, var(--amber2), var(--amber));
  -webkit-background-clip: text; background-clip: text; color: transparent; }
#header-sep { width: 1px; height: 22px; background: var(--border); flex-shrink: 0; }
#obj-name { font-size: 13.5px; color: var(--text); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; max-width: 300px; }
#header-chips { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
.chip { display: inline-flex; align-items: center; padding: 3px 10px;
  border-radius: 20px; font-size: 11px; font-weight: 600; letter-spacing: 0.3px;
  border: 1px solid var(--border); background: var(--glass); color: var(--text-dim); }
.chip.active { background: var(--amber-dim); color: var(--amber2); border-color: var(--border2); }
#status-dot { width: 10px; height: 10px; border-radius: 50%; background: #4a4238;
  flex-shrink: 0; margin-left: auto; transition: background 0.4s; }
#status-dot.connected { background: var(--green); box-shadow: 0 0 8px rgba(127,201,127,0.6); }
#status-dot.working { background: var(--amber);
  animation: pulse-dot 1.4s ease-in-out infinite; }
@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 4px var(--amber); }
  50% { box-shadow: 0 0 14px var(--amber), 0 0 26px rgba(232,163,61,0.4); } }

/* ── Body ───────────────────────────────────────────────────────────── */
#body-row { display: flex; flex: 1; overflow: hidden; }
#sidebar { width: var(--sidebar-w); min-width: var(--sidebar-w);
  border-right: 1px solid var(--border); background: var(--glass);
  display: flex; flex-direction: column; overflow-y: auto; overflow-x: hidden; }
.sb-section { padding: 14px 16px; border-bottom: 1px solid var(--border); }
.sb-title { font-size: 10px; font-weight: 700; letter-spacing: 1.4px;
  text-transform: uppercase; color: var(--text-dimmer); margin-bottom: 10px; }

/* Phase timeline */
#steps-list { display: flex; flex-direction: column; }
.step { display: flex; align-items: center; gap: 10px; padding: 3.5px 0; position: relative; }
.step-circle { width: 20px; height: 20px; border-radius: 50%;
  border: 1.5px solid var(--border2);
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 700; color: var(--text-dimmer);
  flex-shrink: 0; transition: all 0.3s; background: var(--bg); z-index: 1; }
.step:not(:last-child)::after { content: ''; position: absolute; left: 9.5px;
  top: 24px; bottom: -8px; width: 1px; background: var(--border); }
.step.done .step-circle { background: var(--amber); border-color: var(--amber); color: #1a1408; }
.step.done:not(:last-child)::after { background: var(--amber); opacity: 0.4; }
.step.active .step-circle { border-color: var(--amber); color: var(--amber);
  box-shadow: 0 0 10px rgba(232,163,61,0.45); }
.step-label { font-size: 11.5px; color: var(--text-dim); transition: color 0.3s; }
.step.done .step-label { color: var(--text); }
.step.active .step-label { color: var(--amber2); font-weight: 600; }

/* Parameters */
#params-table { font-family: ui-monospace, 'Cascadia Code', monospace;
  font-size: 11px; width: 100%; border-collapse: collapse; }
#params-table td { padding: 2.5px 0; border-bottom: 1px dotted rgba(255,220,170,0.07); }
#params-table td:first-child { color: var(--text-dim); padding-right: 10px; white-space: nowrap; }
#params-table td:last-child { color: var(--amber2); text-align: right; }
#params-empty, #slicer-empty { color: var(--text-dimmer); font-size: 11px; font-style: italic; }

/* Slicer */
#slicer-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.slicer-card { background: var(--glass); border: 1px solid var(--border);
  border-radius: 8px; padding: 7px 9px; }
.slicer-label { font-size: 9.5px; color: var(--text-dimmer);
  text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 2px; }
.slicer-value { font-size: 13px; font-weight: 600; color: var(--text); }
.slicer-value.green { color: var(--green); }
.slicer-value.red { color: var(--red); }

/* Status log */
#status-log { display: flex; flex-direction: column; gap: 6px; }
.log-line { font-size: 11.5px; line-height: 1.45; color: var(--text-dim);
  padding-left: 10px; border-left: 2px solid var(--border); }
.log-line.latest { color: var(--text); border-left-color: var(--amber); }

/* ── Verification banner ────────────────────────────────────────────── */
#verify-banner { display: none; margin: 14px 16px 0; padding: 14px 16px;
  border-radius: 12px; border: 1px solid var(--border2);
  background: linear-gradient(135deg, rgba(232,163,61,0.13), rgba(232,163,61,0.05));
  box-shadow: 0 0 30px rgba(232,163,61,0.12), inset 0 1px 0 rgba(255,244,224,0.06);
  flex-shrink: 0; }
#verify-banner.show { display: block; animation: verify-in 0.3s ease; }
@keyframes verify-in { from { opacity: 0; transform: translateY(-6px); } }
#verify-gate { font-size: 10px; font-weight: 700; letter-spacing: 1.4px;
  text-transform: uppercase; color: var(--amber); margin-bottom: 5px; }
#verify-q { font-size: 13.5px; line-height: 1.5; color: var(--text); margin-bottom: 12px; }
#verify-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.v-btn { border: none; border-radius: 8px; padding: 8px 18px; font-size: 12.5px;
  font-weight: 700; cursor: pointer; font-family: inherit; transition: all 0.15s; }
#v-approve { background: var(--amber); color: #1a1408; }
#v-approve:hover { background: var(--amber2); box-shadow: 0 2px 14px rgba(232,163,61,0.45); }
#v-changes { background: transparent; color: var(--text-dim); border: 1px solid var(--border2); }
#v-changes:hover { color: var(--text); background: var(--glass2); }
#v-note { display: none; width: 100%; margin-top: 10px; background: var(--bg2);
  border: 1px solid var(--border2); border-radius: 8px; color: var(--text);
  font-family: inherit; font-size: 12.5px; padding: 9px 11px; resize: vertical;
  min-height: 58px; }
#v-note:focus { outline: none; border-color: var(--amber); }
#v-send { display: none; margin-top: 8px; background: var(--glass2);
  color: var(--amber2); border: 1px solid var(--border2); }
#v-send:hover { background: var(--amber-dim); }
#verify-done { display: none; font-size: 12.5px; color: var(--green); }
#verify-done.changes { color: var(--amber2); }

/* ── Main / tabs ────────────────────────────────────────────────────── */
#main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }
#tabs { display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0; padding: 0 6px; }
.tab-btn { padding: 0 18px; height: 40px; font-size: 12.5px; font-weight: 600;
  color: var(--text-dim); cursor: pointer; border: none; background: none;
  border-bottom: 2px solid transparent; font-family: inherit;
  transition: color 0.2s, border-color 0.2s; }
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--amber2); border-bottom-color: var(--amber); }
#tab-panels { flex: 1; position: relative; overflow: hidden; }
.tab-panel { position: absolute; inset: 0; display: none; }
.tab-panel.active { display: flex; flex-direction: column; }

/* ── Viewer ─────────────────────────────────────────────────────────── */
#viewer-wrap { flex: 1; position: relative; background: #0b0a08; overflow: hidden; }
#three-canvas { display: block; width: 100% !important; height: 100% !important; }
.hud { position: absolute; font-size: 11px;
  font-family: ui-monospace, 'Cascadia Code', monospace;
  background: rgba(16,14,11,0.72); border: 1px solid var(--border);
  padding: 4px 9px; border-radius: 7px; backdrop-filter: blur(6px); }
#stl-filename { top: 12px; left: 14px; color: var(--amber2); display: none; }
#dims-chip { top: 12px; right: 14px; color: var(--text-dim); display: none; }
#viewer-hint { position: absolute; bottom: 12px; left: 14px; font-size: 11px;
  color: var(--text-dimmer); pointer-events: none; }
#viewer-controls { position: absolute; bottom: 12px; right: 14px; display: flex; gap: 6px; }
.viewer-btn { background: rgba(23,20,16,0.85); border: 1px solid var(--border);
  color: var(--text-dim); font-size: 11px; padding: 5px 12px; border-radius: 7px;
  cursor: pointer; font-family: inherit; transition: all 0.15s; }
.viewer-btn:hover { color: var(--text); border-color: var(--border2); }
.viewer-btn.active { background: var(--amber-dim); color: var(--amber2); border-color: var(--border2); }
#viewer-placeholder { position: absolute; inset: 0; display: flex;
  flex-direction: column; align-items: center; justify-content: center;
  gap: 14px; color: var(--text-dimmer); }
#viewer-placeholder svg { opacity: 0.35; }

/* ── Gallery ────────────────────────────────────────────────────────── */
#gallery-panel { overflow-y: auto; padding: 16px; display: grid !important;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px; align-content: start; }
#gallery-panel:not(.active) { display: none !important; }
.gal-card { border: 1px solid var(--border); border-radius: 12px;
  overflow: hidden; background: var(--glass); cursor: zoom-in;
  transition: border-color 0.2s, transform 0.15s; }
.gal-card:hover { border-color: var(--border2); transform: translateY(-1px); }
.gal-card img { width: 100%; display: block; background: #0b0a08; }
.gal-label { font-size: 11px; padding: 7px 11px; color: var(--text-dim);
  font-family: ui-monospace, monospace; display: flex; justify-content: space-between; }
#gallery-empty { color: var(--text-dimmer); font-style: italic; grid-column: 1/-1; margin: auto; }
#lightbox { display: none; position: fixed; inset: 0; z-index: 50;
  background: rgba(8,7,5,0.92); cursor: zoom-out;
  align-items: center; justify-content: center; padding: 30px; }
#lightbox.show { display: flex; }
#lightbox img { max-width: 100%; max-height: 100%; border-radius: 8px; }

/* ── Files ──────────────────────────────────────────────────────────── */
#files-panel { overflow-y: auto; padding: 14px; flex-direction: column; gap: 5px; }
.file-row { display: flex; align-items: center; gap: 10px; padding: 9px 13px;
  border-radius: 10px; cursor: pointer; border: 1px solid transparent;
  transition: all 0.15s; }
.file-row:hover { background: var(--glass); border-color: var(--border); }
.file-name { font-family: ui-monospace, monospace; font-size: 12px; color: var(--text);
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-meta { font-size: 10.5px; color: var(--text-dimmer);
  font-family: ui-monospace, monospace; flex-shrink: 0; }
.badge-latest { background: var(--amber-dim); color: var(--amber2); font-size: 10px;
  font-weight: 700; padding: 2px 8px; border-radius: 12px;
  border: 1px solid var(--border2); flex-shrink: 0; }
.file-dl { color: var(--text-dimmer); text-decoration: none; font-size: 14px;
  padding: 2px 6px; border-radius: 6px; flex-shrink: 0; }
.file-dl:hover { color: var(--amber2); background: var(--glass2); }
#files-empty, #gallery-empty { font-size: 13px; }
#files-empty { color: var(--text-dimmer); font-style: italic; margin: auto; }
</style>
</head>
<body>
<div id="app">

  <header id="header">
    <div id="logo"><span class="t2p-text">text</span><span class="t2p-2">2</span><span class="t2p-print">print</span></div>
    <div id="header-sep"></div>
    <div id="obj-name">—</div>
    <div id="header-chips">
      <span class="chip" id="chip-material">Material</span>
      <span class="chip" id="chip-printer">Printer</span>
    </div>
    <div id="status-dot"></div>
  </header>

  <div id="body-row">

    <aside id="sidebar">
      <div class="sb-section">
        <div class="sb-title">Pipeline</div>
        <div id="steps-list"></div>
      </div>
      <div class="sb-section">
        <div class="sb-title">Parameters</div>
        <table id="params-table"><tbody></tbody></table>
        <div id="params-empty" style="display:none">No parameters yet</div>
      </div>
      <div class="sb-section">
        <div class="sb-title">Slicer Report</div>
        <div id="slicer-grid" style="display:none"></div>
        <div id="slicer-empty">Not yet run</div>
      </div>
      <div class="sb-section" style="border-bottom:none">
        <div class="sb-title">Activity</div>
        <div id="status-log"><div class="log-line latest">Waiting for Claude…</div></div>
      </div>
    </aside>

    <main id="main">

      <!-- Verification gate banner -->
      <div id="verify-banner">
        <div id="verify-gate">Verification needed</div>
        <div id="verify-q"></div>
        <div id="verify-actions">
          <button class="v-btn" id="v-approve">Approve — continue</button>
          <button class="v-btn" id="v-changes">Request changes…</button>
          <span id="verify-done"></span>
        </div>
        <textarea id="v-note" placeholder="What should change?"></textarea>
        <button class="v-btn" id="v-send">Send to Claude</button>
      </div>

      <div id="tabs">
        <button class="tab-btn active" data-tab="viewer">Model</button>
        <button class="tab-btn" data-tab="gallery">Renders</button>
        <button class="tab-btn" data-tab="files">Files</button>
      </div>
      <div id="tab-panels">

        <div id="panel-viewer" class="tab-panel active">
          <div id="viewer-wrap">
            <canvas id="three-canvas"></canvas>
            <div id="viewer-placeholder">
              <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
                <path d="M32 4L60 20V44L32 60L4 44V20L32 4Z" stroke="#a89a84" stroke-width="2"/>
                <path d="M32 4L32 60M4 20L60 20M4 44L60 44" stroke="#a89a84" stroke-width="1.2" stroke-dasharray="4 3"/>
              </svg>
              <p>Waiting for first STL export…</p>
            </div>
            <div class="hud" id="stl-filename"></div>
            <div class="hud" id="dims-chip"></div>
            <div id="viewer-hint">Drag to rotate · Scroll to zoom · Right-drag to pan</div>
            <div id="viewer-controls">
              <button class="viewer-btn" id="btn-spin">Spin</button>
              <button class="viewer-btn" id="btn-wire">Wireframe</button>
              <button class="viewer-btn" id="btn-reset">Reset view</button>
            </div>
          </div>
        </div>

        <div id="panel-gallery" class="tab-panel">
          <div id="gallery-panel" class="active">
            <div id="gallery-empty">No renders yet</div>
          </div>
        </div>

        <div id="panel-files" class="tab-panel">
          <div id="files-panel" class="tab-panel active" style="display:flex">
            <div id="files-empty">No STL files yet</div>
          </div>
        </div>

      </div>
    </main>
  </div>
</div>

<div id="lightbox"><img id="lightbox-img" alt=""/></div>

<script>
// ═══ Tabs ═══════════════════════════════════════════════════════════════
const tabBtns = document.querySelectorAll('.tab-btn');
const panels = { viewer: 'panel-viewer', gallery: 'panel-gallery', files: 'panel-files' };
function switchTab(name) {
  tabBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  Object.entries(panels).forEach(([k, id]) =>
    document.getElementById(id).classList.toggle('active', k === name));
  document.getElementById('gallery-panel').classList.toggle('active', name === 'gallery');
  if (name === 'viewer') resizeRenderer();
}
tabBtns.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));

// ═══ Phases ═════════════════════════════════════════════════════════════
const PHASES = [
  { id: 'requirements', label: 'Requirements' },
  { id: 'search',       label: 'Repo Search' },
  { id: 'dimensions',   label: 'Dimensions' },
  { id: 'brief',        label: 'Design Brief' },
  { id: 'phase1',       label: 'Phase 1 — Base Shape' },
  { id: 'phase2',       label: 'Phase 2 — Features' },
  { id: 'structural',   label: 'Structural Check' },
  { id: 'phase3',       label: 'Phase 3 — Finish' },
  { id: 'slicer',       label: 'Slicer Verification' },
  { id: 'delivered',    label: 'Delivered' },
];
const PHASE_ORDER = PHASES.map(p => p.id);
const stepsList = document.getElementById('steps-list');
PHASES.forEach((p, i) => {
  const div = document.createElement('div');
  div.className = 'step'; div.id = 'step-' + p.id;
  div.innerHTML = `<div class="step-circle" id="circle-${p.id}">${i + 1}</div>
                   <div class="step-label">${p.label}</div>`;
  stepsList.appendChild(div);
});
function updateSteps(phaseId) {
  const activeIdx = PHASE_ORDER.indexOf(phaseId);
  PHASES.forEach((p, i) => {
    const step = document.getElementById('step-' + p.id);
    const circle = document.getElementById('circle-' + p.id);
    step.classList.remove('done', 'active');
    if (activeIdx < 0) return;
    if (i < activeIdx || (i === activeIdx && phaseId === 'delivered')) {
      step.classList.add('done'); circle.innerHTML = '✓';
    } else if (i === activeIdx) {
      step.classList.add('active'); circle.innerHTML = i + 1;
    } else circle.innerHTML = i + 1;
  });
}

// ═══ Header ═════════════════════════════════════════════════════════════
const dot = document.getElementById('status-dot');
function setDot(state) {
  dot.className = '';
  if (state === 'connected') dot.classList.add('connected');
  else if (state === 'working') dot.classList.add('working');
}
function updateHeader(state) {
  document.getElementById('obj-name').textContent = state.object || '—';
  const mat = document.getElementById('chip-material');
  const prt = document.getElementById('chip-printer');
  mat.textContent = state.material || 'Material';
  mat.classList.toggle('active', !!state.material);
  prt.textContent = state.printer || 'Printer';
  prt.classList.toggle('active', !!state.printer);
  const working = state.phase_id && state.phase_id !== 'delivered';
  setDot(working ? 'working' : 'connected');
}

// ═══ Verification gate ══════════════════════════════════════════════════
let currentGate = null;
let respondedGate = null;
const banner = document.getElementById('verify-banner');
const noteBox = document.getElementById('v-note');
const sendBtn = document.getElementById('v-send');
const doneMsg = document.getElementById('verify-done');

function updateVerify(state) {
  const awaiting = state.awaiting || null;
  const approval = state._approval || null;
  if (!awaiting) { banner.classList.remove('show'); currentGate = null; return; }
  currentGate = awaiting.gate || 'gate';
  document.getElementById('verify-gate').textContent =
    'Verification needed — ' + currentGate.replace(/-/g, ' ');
  document.getElementById('verify-q').textContent =
    awaiting.question || 'Does this look right?';
  const answered = approval && approval.gate === currentGate;
  document.getElementById('v-approve').style.display = answered ? 'none' : '';
  document.getElementById('v-changes').style.display = answered ? 'none' : '';
  noteBox.style.display = 'none'; sendBtn.style.display = 'none';
  if (answered) {
    doneMsg.style.display = '';
    doneMsg.className = approval.decision === 'approve' ? '' : 'changes';
    doneMsg.textContent = approval.decision === 'approve'
      ? '✓ Approved — Claude will continue'
      : '✎ Change request sent — Claude will pick it up';
  } else doneMsg.style.display = 'none';
  banner.classList.add('show');
}
function sendVerify(decision, note) {
  fetch('/verify', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gate: currentGate, decision, note: note || '' }),
  }).catch(console.error);
}
document.getElementById('v-approve').addEventListener('click', () => sendVerify('approve'));
document.getElementById('v-changes').addEventListener('click', () => {
  noteBox.style.display = 'block'; sendBtn.style.display = 'inline-block'; noteBox.focus();
});
sendBtn.addEventListener('click', () => sendVerify('changes', noteBox.value.trim()));

// ═══ Parameters / slicer ════════════════════════════════════════════════
function updateParams(params) {
  const tbody = document.querySelector('#params-table tbody');
  const empty = document.getElementById('params-empty');
  tbody.innerHTML = '';
  const has = params && Object.keys(params).length;
  document.getElementById('params-table').style.display = has ? '' : 'none';
  empty.style.display = has ? 'none' : '';
  if (!has) return;
  for (const [k, v] of Object.entries(params)) {
    const tr = document.createElement('tr');
    const val = typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : v;
    tr.innerHTML = `<td>${k}</td><td>${val}</td>`;
    tbody.appendChild(tr);
  }
}
function updateSlicer(report) {
  const grid = document.getElementById('slicer-grid');
  const empty = document.getElementById('slicer-empty');
  if (!report) { grid.style.display = 'none'; empty.style.display = ''; return; }
  grid.style.display = 'grid'; empty.style.display = 'none';
  const sup = report.support_pct;
  const supColor = sup === 0 || sup < 25 ? 'green' : 'red';
  grid.innerHTML = `
    <div class="slicer-card"><div class="slicer-label">Print time</div>
      <div class="slicer-value">${report.time || '—'}</div></div>
    <div class="slicer-card"><div class="slicer-label">Filament</div>
      <div class="slicer-value">${report.filament_g || '—'}g</div></div>
    <div class="slicer-card"><div class="slicer-label">Supports</div>
      <div class="slicer-value ${supColor}">${sup != null ? sup + '%' : '—'}</div></div>
    <div class="slicer-card"><div class="slicer-label">Layers</div>
      <div class="slicer-value">${report.layers || '—'}</div></div>`;
}

// ═══ Activity log ═══════════════════════════════════════════════════════
const logEl = document.getElementById('status-log');
let lastMsg = null;
function pushLog(msg) {
  if (!msg || msg === lastMsg) return;
  lastMsg = msg;
  logEl.querySelectorAll('.log-line').forEach(l => l.classList.remove('latest'));
  const div = document.createElement('div');
  div.className = 'log-line latest'; div.textContent = msg;
  logEl.prepend(div);
  while (logEl.children.length > 6) logEl.lastChild.remove();
}

// ═══ Gallery ════════════════════════════════════════════════════════════
const lightbox = document.getElementById('lightbox');
lightbox.addEventListener('click', () => lightbox.classList.remove('show'));
function updateGallery(files) {
  const panel = document.getElementById('gallery-panel');
  const empty = document.getElementById('gallery-empty');
  panel.querySelectorAll('.gal-card').forEach(el => el.remove());
  empty.style.display = files && files.length ? 'none' : '';
  if (!files) return;
  const ts = Date.now();
  files.forEach(f => {
    const card = document.createElement('div');
    card.className = 'gal-card';
    card.innerHTML = `<img src="/file/${encodeURIComponent(f.name)}?t=${ts}" alt="${f.name}" loading="lazy"/>
      <div class="gal-label"><span>${f.name}</span><span>${f.when}</span></div>`;
    card.addEventListener('click', () => {
      document.getElementById('lightbox-img').src = '/file/' + encodeURIComponent(f.name) + '?t=' + ts;
      lightbox.classList.add('show');
    });
    panel.appendChild(card);
  });
}

// ═══ Files ══════════════════════════════════════════════════════════════
function updateFiles(stls) {
  const panel = document.getElementById('files-panel');
  const empty = document.getElementById('files-empty');
  panel.querySelectorAll('.file-row').forEach(el => el.remove());
  empty.style.display = stls && stls.length ? 'none' : '';
  if (!stls) return;
  stls.forEach((f, idx) => {
    const row = document.createElement('div');
    row.className = 'file-row';
    row.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <path d="M9 1.5L15.5 5.25V12.75L9 16.5L2.5 12.75V5.25L9 1.5Z"
              fill="rgba(232,163,61,0.15)" stroke="#e8a33d" stroke-width="1.2"/>
      </svg>
      <span class="file-name">${f.name}</span>
      <span class="file-meta">${f.size} · ${f.when}</span>
      ${idx === 0 ? '<span class="badge-latest">latest</span>' : ''}
      <a class="file-dl" href="/file/${encodeURIComponent(f.name)}" download title="Download">⬇</a>`;
    row.addEventListener('click', (e) => {
      if (e.target.closest('.file-dl')) return;
      loadSTL(f.name); switchTab('viewer');
    });
    panel.appendChild(row);
  });
}

// ═══ Three.js viewer ════════════════════════════════════════════════════
let scene, camera, renderer, controls, model;
let isWireframe = false, currentSTLFile = null;

function initThree() {
  const canvas = document.getElementById('three-canvas');
  const wrap = document.getElementById('viewer-wrap');
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b0a08);
  scene.fog = new THREE.Fog(0x0b0a08, 700, 1600);

  camera = new THREE.PerspectiveCamera(45, wrap.clientWidth / wrap.clientHeight, 0.1, 10000);
  camera.position.set(150, 120, 180);

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(wrap.clientWidth, wrap.clientHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.08;
  controls.autoRotateSpeed = 1.1;
  controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };

  // golden-hour studio lighting
  scene.add(new THREE.AmbientLight(0xffe8c8, 0.35));
  const key = new THREE.DirectionalLight(0xfff1dc, 1.25);
  key.position.set(90, 170, 110); key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  const s = 220;
  key.shadow.camera.left = -s; key.shadow.camera.right = s;
  key.shadow.camera.top = s; key.shadow.camera.bottom = -s;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x8a97c8, 0.35);
  fill.position.set(-120, 50, -90); scene.add(fill);
  const rim = new THREE.DirectionalLight(0xe8a33d, 0.45);
  rim.position.set(0, 30, -160); scene.add(rim);

  // print bed: 256mm Bambu plate
  const bed = new THREE.Mesh(
    new THREE.PlaneGeometry(256, 256),
    new THREE.MeshStandardMaterial({ color: 0x161310, roughness: 0.95, metalness: 0 }));
  bed.rotation.x = -Math.PI / 2; bed.position.y = -0.15; bed.receiveShadow = true;
  scene.add(bed);
  const grid = new THREE.GridHelper(256, 16, 0x37301f, 0x241f15);
  grid.material.opacity = 0.85; grid.material.transparent = true;
  scene.add(grid);
  const edge = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.PlaneGeometry(256, 256).rotateX(-Math.PI / 2)),
    new THREE.LineBasicMaterial({ color: 0xe8a33d, transparent: true, opacity: 0.35 }));
  scene.add(edge);

  (function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  })();
  window.addEventListener('resize', resizeRenderer);
}
function resizeRenderer() {
  const wrap = document.getElementById('viewer-wrap');
  if (!wrap || !renderer) return;
  const w = wrap.clientWidth, h = wrap.clientHeight;
  if (!w || !h) return;
  camera.aspect = w / h; camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}
function frameModel(mesh) {
  const box = new THREE.Box3().setFromObject(mesh);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  let dist = Math.max(Math.abs(maxDim / Math.sin(fov / 2)) * 0.7, maxDim * 1.5);
  camera.position.set(center.x + dist * 0.6, center.y + dist * 0.5, center.z + dist * 0.8);
  controls.target.copy(center); controls.update();
}
function loadSTL(filename) {
  const placeholder = document.getElementById('viewer-placeholder');
  const fnLabel = document.getElementById('stl-filename');
  const dims = document.getElementById('dims-chip');
  if (model) {
    scene.remove(model);
    model.geometry.dispose(); model.material.dispose(); model = null;
  }
  currentSTLFile = filename;
  fnLabel.textContent = filename; fnLabel.style.display = '';
  const loader = new THREE.STLLoader();
  loader.load('/file/' + encodeURIComponent(filename), (geometry) => {
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    const b = geometry.boundingBox;
    const sx = b.max.x - b.min.x, sy = b.max.y - b.min.y, sz = b.max.z - b.min.z;
    const tris = geometry.attributes.position.count / 3;
    const trisTxt = tris > 1e6 ? (tris / 1e6).toFixed(1) + 'M' : Math.round(tris / 1e3) + 'k';
    dims.textContent = `${sx.toFixed(0)} × ${sy.toFixed(0)} × ${sz.toFixed(0)} mm · ${trisTxt} tris`;
    dims.style.display = '';
    // STL is Z-up; scene is Y-up: rotate, center on plate, base at y=0
    geometry.rotateX(-Math.PI / 2);
    geometry.computeBoundingBox();
    const bb = geometry.boundingBox;
    geometry.translate(-(bb.min.x + bb.max.x) / 2, -bb.min.y, -(bb.min.z + bb.max.z) / 2);
    const mat = new THREE.MeshPhysicalMaterial({
      color: 0xd9a05b, roughness: 0.42, metalness: 0.08,
      clearcoat: 0.25, clearcoatRoughness: 0.6, wireframe: isWireframe });
    model = new THREE.Mesh(geometry, mat);
    model.castShadow = true; model.receiveShadow = true;
    scene.add(model);
    placeholder.style.display = 'none';
    frameModel(model);
  }, undefined, (err) => console.error('STL load error:', err));
}
document.getElementById('btn-reset').addEventListener('click', () => model && frameModel(model));
document.getElementById('btn-wire').addEventListener('click', () => {
  isWireframe = !isWireframe;
  document.getElementById('btn-wire').classList.toggle('active', isWireframe);
  if (model) model.material.wireframe = isWireframe;
});
document.getElementById('btn-spin').addEventListener('click', () => {
  controls.autoRotate = !controls.autoRotate;
  document.getElementById('btn-spin').classList.toggle('active', controls.autoRotate);
});

// ═══ State render ═══════════════════════════════════════════════════════
function renderState(state) {
  updateHeader(state);
  updateSteps(state.phase_id || '');
  updateParams(state.parameters || null);
  updateSlicer(state.slicer_report || null);
  updateVerify(state);
  pushLog(state.message);
  const stls = state._stl_files || [];
  if (stls.length && stls[0].name !== currentSTLFile) loadSTL(stls[0].name);
  updateGallery(state._preview_files || []);
  updateFiles(stls);
}

// ═══ SSE ════════════════════════════════════════════════════════════════
let evtSource = null;
function connectSSE() {
  if (evtSource) { evtSource.close(); evtSource = null; }
  evtSource = new EventSource('/events');
  evtSource.addEventListener('open', () => {
    setDot('connected');
    fetch('/state').then(r => r.json()).then(renderState).catch(console.error);
  });
  evtSource.addEventListener('update', (e) => {
    try { renderState(JSON.parse(e.data)); }
    catch (err) { console.error('SSE parse error:', err); }
  });
  evtSource.addEventListener('error', () => {
    setDot('disconnected');
    evtSource.close(); evtSource = null;
    setTimeout(connectSSE, 2000);
  });
}

initThree();
connectSSE();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__)

_lock = threading.Lock()
_subscribers: List[queue.Queue] = []
_last_mtimes: Dict[str, float] = {}
_work_dir: Path = Path.cwd()

_WATCH_SUFFIXES = (".stl", ".png")
_WATCH_NAMES = ("ui_state.json", "ui_approval.json")


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _human_when(mtime: float) -> str:
    delta = time.time() - mtime
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


def _scan_state(work_dir: Path) -> dict:
    """Read ui_state.json + ui_approval.json and augment with file lists."""
    state: dict = {}
    state_file = work_dir / "ui_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}

    approval_file = work_dir / "ui_approval.json"
    if approval_file.exists():
        try:
            state["_approval"] = json.loads(approval_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    stls: List[tuple] = []
    previews: List[tuple] = []
    try:
        for entry in work_dir.iterdir():
            if not entry.is_file():
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            if entry.name.endswith(".stl"):
                stls.append((st.st_mtime, entry.name, st.st_size))
            elif entry.name.endswith(".png"):
                previews.append((st.st_mtime, entry.name))
    except FileNotFoundError:
        pass

    stls.sort(key=lambda x: x[0], reverse=True)
    previews.sort(key=lambda x: x[0], reverse=True)
    state["_stl_files"] = [
        {"name": n, "size": _human_size(s), "when": _human_when(m)}
        for m, n, s in stls
    ]
    state["_preview_files"] = [
        {"name": n, "when": _human_when(m)} for m, n in previews
    ]
    return state


def _get_watched_mtimes(work_dir: Path) -> Dict[str, float]:
    mtimes: Dict[str, float] = {}
    try:
        for entry in work_dir.iterdir():
            if not entry.is_file():
                continue
            name = entry.name
            if name.endswith(_WATCH_SUFFIXES) or name in _WATCH_NAMES:
                try:
                    mtimes[name] = entry.stat().st_mtime
                except OSError:
                    pass
    except FileNotFoundError:
        pass
    return mtimes


def _broadcast(state: dict) -> None:
    payload = json.dumps(state, ensure_ascii=False)
    msg = f"event: update\ndata: {payload}\n\n"
    dead: List[queue.Queue] = []
    with _lock:
        for q in _subscribers:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _subscribers.remove(q)


def _watcher_loop(work_dir: Path, interval: float = 0.4) -> None:
    last_heartbeat = time.monotonic()
    while True:
        time.sleep(interval)
        now = time.monotonic()
        try:
            current = _get_watched_mtimes(work_dir)
        except Exception:
            current = {}
        changed = False
        with _lock:
            if current != _last_mtimes:
                _last_mtimes.clear()
                _last_mtimes.update(current)
                changed = True
        if changed:
            _broadcast(_scan_state(work_dir))
        if now - last_heartbeat >= 15.0:
            last_heartbeat = now
            with _lock:
                dead = []
                for q in _subscribers:
                    try:
                        q.put_nowait(": heartbeat\n\n")
                    except queue.Full:
                        dead.append(q)
                for q in dead:
                    _subscribers.remove(q)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/state")
def state():
    return jsonify(_scan_state(_work_dir))


@app.route("/verify", methods=["POST"])
def verify():
    """Record the user's verification decision for Claude to read.

    Writes ui_approval.json: {gate, decision, note, ts}. Claude checks
    this file at each verification gate before proceeding.
    """
    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    if decision not in ("approve", "changes"):
        return jsonify({"error": "decision must be approve|changes"}), 400
    record = {
        "gate": str(data.get("gate", ""))[:200],
        "decision": decision,
        "note": str(data.get("note", ""))[:2000],
        "ts": time.time(),
    }
    (_work_dir / "ui_approval.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8")
    _broadcast(_scan_state(_work_dir))
    return jsonify({"ok": True})


@app.route("/events")
def events():
    sub_q: queue.Queue = queue.Queue(maxsize=10)
    with _lock:
        _subscribers.append(sub_q)

    initial = json.dumps(_scan_state(_work_dir), ensure_ascii=False)
    first_msg = f"event: update\ndata: {initial}\n\n"

    def generate():
        yield first_msg
        while True:
            try:
                yield sub_q.get(timeout=20)
            except queue.Empty:
                yield ": keepalive\n\n"

    def cleanup(q):
        with _lock:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass

    response = Response(
        generate(),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache",
                 "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )
    response.call_on_close(lambda: cleanup(sub_q))
    return response


@app.route("/file/<path:filename>")
def serve_file(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        return ("Not found", 404)
    try:
        return send_from_directory(str(_work_dir), filename, as_attachment=False)
    except FileNotFoundError:
        return ("Not found", 404)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "text2print live design UI server.\n\n"
            "Watches the working directory for *.stl, *.png, ui_state.json,\n"
            "and ui_approval.json changes and streams updates to a browser\n"
            "3D viewer via Server-Sent Events. Verification-gate decisions\n"
            "made in the browser are written to ui_approval.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=7384,
                        help="TCP port to listen on (default: 7384)")
    parser.add_argument("--dir", type=str, default=None, metavar="PATH",
                        help="Working directory to watch (default: cwd)")
    parser.add_argument("--no-browser", action="store_true", default=False,
                        help="Do not automatically open the browser")
    return parser.parse_args()


def _open_browser(url: str, delay: float = 0.5) -> None:
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    global _work_dir
    args = parse_args()
    _work_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    if not _work_dir.is_dir():
        print(f"[text2print] ERROR: directory does not exist: {_work_dir}")
        raise SystemExit(1)

    url = f"http://127.0.0.1:{args.port}"
    print(f"[text2print] Watching : {_work_dir}")
    print(f"[text2print] Serving  : {url}")

    with _lock:
        _last_mtimes.update(_get_watched_mtimes(_work_dir))

    threading.Thread(target=_watcher_loop, args=(_work_dir,),
                     daemon=True, name="ui-watcher").start()

    if not args.no_browser:
        _open_browser(url, delay=0.5)

    app.run(host="127.0.0.1", port=args.port, debug=False,
            use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
