#!/usr/bin/env python3
"""Local web UI for Usage Planner.

This server intentionally binds to 127.0.0.1 by default and uses only Python's
standard library so it works on macOS and Windows without extra dependencies.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from datetime import timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import usage_planner as planner


HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Usage Planner</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --panel-soft: #f0f4f7;
      --ink: #1f2933;
      --muted: #607080;
      --line: #d6dde3;
      --accent: #0f766e;
      --accent-ink: #ffffff;
      --warn: #b45309;
      --bad: #b91c1c;
      --shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
      letter-spacing: 0;
    }

    button, input, select {
      font: inherit;
    }

    button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      min-height: 36px;
      padding: 0 12px;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: var(--accent-ink);
    }

    button:disabled {
      opacity: 0.6;
      cursor: wait;
    }

    input, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      min-height: 36px;
      padding: 6px 9px;
      background: #fff;
      color: var(--ink);
    }

    label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.25;
    }

    .shell {
      max-width: 1180px;
      margin: 0 auto;
      padding: 18px;
    }

    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      margin-bottom: 14px;
    }

    h1 {
      margin: 0;
      font-size: 26px;
      line-height: 1.1;
    }

    h2 {
      font-size: 15px;
      margin: 0 0 10px;
    }

    .muted {
      color: var(--muted);
      font-size: 13px;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 12px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 14px;
    }

    .span-3 { grid-column: span 3; }
    .span-4 { grid-column: span 4; }
    .span-5 { grid-column: span 5; }
    .span-6 { grid-column: span 6; }
    .span-7 { grid-column: span 7; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }

    .metric {
      display: grid;
      gap: 6px;
      min-height: 96px;
    }

    .metric .value {
      font-size: 26px;
      line-height: 1.05;
      font-weight: 700;
    }

    .row {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      align-items: end;
    }

    .tools {
      display: flex;
      gap: 10px;
      align-items: center;
      min-height: 36px;
    }

    .tools label {
      display: inline-flex;
      grid-template-columns: none;
      align-items: center;
      gap: 6px;
      color: var(--ink);
      font-size: 13px;
    }

    .tools input {
      width: auto;
      min-height: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }

    th, td {
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 8px 6px;
      vertical-align: top;
    }

    th {
      color: var(--muted);
      font-weight: 600;
      background: var(--panel-soft);
    }

    .status {
      min-height: 24px;
      color: var(--muted);
      font-size: 13px;
    }

    .status.error {
      color: var(--bad);
    }

    .status.ok {
      color: var(--accent);
    }

    .badge {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      color: var(--muted);
      background: #fff;
    }

    .timeline {
      display: grid;
      gap: 8px;
    }

    .slot {
      display: grid;
      grid-template-columns: 96px 1fr;
      gap: 10px;
      align-items: center;
    }

    .bar {
      min-height: 12px;
      border-radius: 4px;
      background: linear-gradient(90deg, #0f766e, #2563eb);
      width: var(--w, 8%);
    }

    .danger-note {
      border-left: 3px solid var(--warn);
      padding: 8px 10px;
      background: #fff7ed;
      color: #7c2d12;
      font-size: 13px;
    }

    .warmup-note {
      border-left: 3px solid var(--accent);
      padding: 8px 10px;
      background: #f0fdfa;
      color: #134e4a;
      font-size: 13px;
      margin-bottom: 10px;
    }

    @media (max-width: 900px) {
      .span-3, .span-4, .span-5, .span-6, .span-7, .span-8 {
        grid-column: span 12;
      }
      .form-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      header {
        align-items: flex-start;
        flex-direction: column;
      }
    }

    @media (max-width: 560px) {
      .shell { padding: 12px; }
      .form-grid { grid-template-columns: 1fr; }
      .slot { grid-template-columns: 80px 1fr; }
      .metric .value { font-size: 22px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <h1 data-i18n="title">Usage Planner</h1>
        <div id="dataPath" class="muted"></div>
      </div>
      <div class="row">
        <button id="langToggleBtn">EN / 中文</button>
        <button id="refreshBtn" title="重新整理" data-i18n="header-refresh">↻ 重新整理</button>
        <button id="importBtn" class="primary" title="匯入本機 log" data-i18n="header-import">↓ 匯入 log</button>
      </div>
    </header>

    <main class="grid">
      <section class="panel span-3 metric">
        <div class="muted" data-i18n="title-main">主要使用視窗</div>
        <div id="mainWindow" class="value">--</div>
        <div id="confidence" class="muted">--</div>
      </section>
      <section class="panel span-3 metric">
        <div class="muted" data-i18n="title-remind">提醒時間</div>
        <div id="remindTime" class="value">--</div>
        <div class="muted" data-i18n="remind-note">本地提醒，不消耗 usage</div>
      </section>
      <section class="panel span-3 metric">
        <div class="muted" data-i18n="title-usage">最近用量</div>
        <div id="totalUsage" class="value">--</div>
        <div id="sessionCount" class="muted">--</div>
      </section>
      <section class="panel span-3 metric">
        <div class="muted" data-i18n="title-source">來源</div>
        <div id="source" class="value">--</div>
        <div id="timezone" class="muted">--</div>
      </section>

      <section class="panel span-12">
        <h2 data-i18n="section-import">Log 匯入</h2>
        <div class="form-grid">
          <label><span data-i18n="lbl-range">範圍（天）</span>
            <input id="importDays" type="number" min="1" value="7">
          </label>
          <label><span data-i18n="lbl-idle">閒置切段（分鐘）</span>
            <input id="idleMinutes" type="number" min="1" value="45">
          </label>
          <label><span data-i18n="lbl-tail">結尾緩衝（分鐘）</span>
            <input id="tailMinutes" type="number" min="0" value="15">
          </label>
          <div class="tools">
            <label><input id="toolCodex" type="checkbox" checked> Codex</label>
            <label><input id="toolClaude" type="checkbox" checked> Claude Code</label>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <button id="previewImportBtn" data-i18n="btn-preview">◌ 預覽</button>
          <button id="runImportBtn" class="primary" data-i18n="btn-import">↓ 匯入</button>
          <button id="tuneBtn" data-i18n="btn-tune">◎ 微調偏好</button>
        </div>
        <div id="importStatus" class="status"></div>
      </section>

      <section class="panel span-7">
        <h2 data-i18n="section-peaks">近期高峰</h2>
        <div id="topSlots" class="timeline"></div>
      </section>

      <section class="panel span-5">
        <h2 data-i18n="section-reminders">接下來提醒</h2>
        <table>
          <thead><tr><th data-i18n="th-reminder">提醒</th><th data-i18n="th-window">工作視窗</th></tr></thead>
          <tbody id="reminders"></tbody>
        </table>
      </section>

      <section class="panel span-6">
        <h2 data-i18n="section-manual">手動新增</h2>
        <div class="form-grid">
          <label><span data-i18n="lbl-tool">工具</span>
            <select id="manualTool">
              <option value="codex">Codex</option>
              <option value="claude-code">Claude Code</option>
            </select>
          </label>
          <label><span data-i18n="lbl-start">開始</span>
            <input id="manualStart" type="datetime-local">
          </label>
          <label><span data-i18n="lbl-end">結束</span>
            <input id="manualEnd" type="datetime-local">
          </label>
          <button id="addSessionBtn" class="primary" data-i18n="btn-add">＋ 新增</button>
        </div>
        <div id="manualStatus" class="status"></div>
      </section>

      <section class="panel span-6">
        <h2 data-i18n="section-settings">設定</h2>
        <div class="form-grid">
          <label><span data-i18n="lbl-prefs">偏好時段</span>
            <input id="preferredWindows" placeholder="19:00-23:00">
          </label>
          <label><span data-i18n="lbl-quota">視窗長度（分鐘）</span>
            <input id="quotaWindow" type="number" min="1" max="1440">
          </label>
          <label><span data-i18n="lbl-lead">提前提醒（分鐘）</span>
            <input id="setupLead" type="number" min="0" max="1440">
          </label>
          <button id="savePrefsBtn" class="primary" data-i18n="btn-save">✓ 儲存</button>
        </div>
        <div id="prefsStatus" class="status"></div>
      </section>

      <section class="panel span-12">
        <h2 data-i18n="section-warmup">Warmup（高峰前自動暖機）</h2>
        <div class="warmup-note" data-i18n="warmup-desc">⚡ Warmup 會透過 Codex CLI 送出一段極低 usage 的 prompt，讓 session 在高峰前提前啟動。<strong>這會消耗少量 usage。</strong></div>
        <div class="form-grid">
          <label><span data-i18n="lbl-method">方式</span>
            <select id="warmupMethod">
              <option value="cli" data-i18n="opt-cli">CLI（codex exec）</option>
              <option value="deeplink" data-i18n="opt-dl">Deep Link（codex:// App）</option>
            </select>
          </label>
          <label><span data-i18n="lbl-prompt">Prompt</span>
            <input id="warmupPrompt" value="ping" placeholder="ping">
          </label>
          <label><span data-i18n="lbl-project">專案路徑（選填）</span>
            <input id="warmupProjectPath" placeholder="/path/to/project">
          </label>
          <div class="tools">
            <label><input id="warmupForce" type="checkbox" checked> <span data-i18n="lbl-force">強制執行</span></label>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <button id="warmupDryRunBtn" data-i18n="btn-preview-warmup">◌ 預覽</button>
          <button id="warmupSendBtn" class="primary" data-i18n="btn-send-warmup">⚡ 送出 Warmup</button>
          <button id="scheduleWarmupBtn" data-i18n="btn-schedule-warmup">⏰ 安裝排程</button>
          <button id="uninstallWarmupBtn" data-i18n="btn-uninstall-warmup">✕ 移除排程</button>
        </div>
        <div id="warmupStatus" class="status"></div>
      </section>

      <section class="panel span-12">
        <div class="danger-note" data-i18n="danger-note">除了 Warmup 功能外，這個工具只分析本機使用時段與提醒規劃，不會自動呼叫 Codex、Claude Code 或消耗任何 usage。</div>
      </section>
    </main>
  </div>

  <script>
    const i18nDict = {
      zh: {
        "title": "Usage Planner",
        "header-refresh": "↻ 重新整理",
        "header-import": "↓ 匯入 log",
        "title-main": "主要使用視窗",
        "title-remind": "提醒時間",
        "remind-note": "本地提醒，不消耗 usage",
        "title-usage": "最近用量",
        "title-source": "來源",
        "section-import": "Log 匯入",
        "lbl-range": "範圍（天）",
        "lbl-idle": "閒置切段（分鐘）",
        "lbl-tail": "結尾緩衝（分鐘）",
        "btn-preview": "◌ 預覽",
        "btn-import": "↓ 匯入",
        "btn-tune": "◎ 微調偏好",
        "section-peaks": "近期高峰",
        "section-reminders": "接下來提醒",
        "th-reminder": "提醒",
        "th-window": "工作視窗",
        "section-manual": "手動新增",
        "lbl-tool": "工具",
        "lbl-start": "開始",
        "lbl-end": "結束",
        "btn-add": "＋ 新增",
        "section-settings": "設定",
        "lbl-prefs": "偏好時段",
        "lbl-quota": "視窗長度（分鐘）",
        "lbl-lead": "提前提醒（分鐘）",
        "btn-save": "✓ 儲存",
        "section-warmup": "Warmup（高峰前自動暖機）",
        "warmup-desc": "⚡ Warmup 會透過 Codex CLI 送出一段極低 usage 的 prompt，讓 session 在高峰前提前啟動。<strong>這會消耗少量 usage。</strong>",
        "lbl-method": "方式",
        "opt-cli": "CLI（codex exec）",
        "opt-dl": "Deep Link（codex:// App）",
        "lbl-prompt": "Prompt",
        "lbl-project": "專案路徑（選填）",
        "lbl-force": "強制執行",
        "btn-preview-warmup": "◌ 預覽",
        "btn-send-warmup": "⚡ 送出 Warmup",
        "btn-schedule-warmup": "⏰ 安裝排程",
        "btn-uninstall-warmup": "✕ 移除排程",
        "danger-note": "除了 Warmup 功能外，這個工具只分析本機使用時段與提醒規劃，不會自動呼叫 Codex、Claude Code 或消耗任何 usage。",
        "msg-session-unit": "段 session",
        "msg-processing": "處理中...",
        "msg-tuning": "微調中...",
        "msg-saving": "儲存中...",
        "msg-saved": "已儲存",
        "msg-adding": "新增中...",
        "msg-added": "已新增",
        "msg-previewing": "預覽中...",
        "msg-sending": "送出中...",
        "msg-scheduling": "安裝排程中...",
        "msg-unscheduling": "移除排程中...",
        "msg-no-tool": "至少選一個工具。",
        "msg-import-res-1": "prompt, 新增",
        "msg-import-res-2": "段",
        "msg-dup-1": "；重複",
        "msg-dup-2": "段",
        "msg-not-written": "；未寫入",
        "msg-new-pref": "新偏好："
      },
      en: {
        "title": "Usage Planner",
        "header-refresh": "↻ Refresh",
        "header-import": "↓ Import Logs",
        "title-main": "Main Window",
        "title-remind": "Reminder Time",
        "remind-note": "Local reminder, no usage consumed",
        "title-usage": "Recent Usage",
        "title-source": "Source",
        "section-import": "Import Logs",
        "lbl-range": "Range (days)",
        "lbl-idle": "Idle Split (min)",
        "lbl-tail": "Tail Buffer (min)",
        "btn-preview": "◌ Preview",
        "btn-import": "↓ Import",
        "btn-tune": "◎ Tune Prefs",
        "section-peaks": "Recent Peaks",
        "section-reminders": "Upcoming Reminders",
        "th-reminder": "Reminder",
        "th-window": "Work Window",
        "section-manual": "Add Session",
        "lbl-tool": "Tool",
        "lbl-start": "Start",
        "lbl-end": "End",
        "btn-add": "＋ Add",
        "section-settings": "Settings",
        "lbl-prefs": "Preferred Windows",
        "lbl-quota": "Window Length (min)",
        "lbl-lead": "Setup Lead (min)",
        "btn-save": "✓ Save",
        "section-warmup": "Warmup (Auto Pre-Peak)",
        "warmup-desc": "⚡ Warmup sends a minimal usage prompt via Codex CLI so the session starts before the peak. <strong>This consumes a small amount of usage.</strong>",
        "lbl-method": "Method",
        "opt-cli": "CLI (codex exec)",
        "opt-dl": "Deep Link (codex:// App)",
        "lbl-prompt": "Prompt",
        "lbl-project": "Project Path (optional)",
        "lbl-force": "Force execution",
        "btn-preview-warmup": "◌ Preview",
        "btn-send-warmup": "⚡ Send Warmup",
        "btn-schedule-warmup": "⏰ Install Schedule",
        "btn-uninstall-warmup": "✕ Remove Schedule",
        "danger-note": "Aside from Warmup, this tool only analyzes local usage times and plans reminders. It does not automatically call Codex, Claude Code, or consume usage.",
        "msg-session-unit": "sessions",
        "msg-processing": "Processing...",
        "msg-tuning": "Tuning...",
        "msg-saving": "Saving...",
        "msg-saved": "Saved",
        "msg-adding": "Adding...",
        "msg-added": "Added",
        "msg-previewing": "Previewing...",
        "msg-sending": "Sending...",
        "msg-scheduling": "Installing schedule...",
        "msg-unscheduling": "Removing schedule...",
        "msg-no-tool": "Choose at least one tool.",
        "msg-import-res-1": "prompts, added",
        "msg-import-res-2": "sessions",
        "msg-dup-1": "; duplicates ",
        "msg-dup-2": " sessions",
        "msg-not-written": "; dry-run",
        "msg-new-pref": "New Prefs: "
      }
    };

    let currentLang = localStorage.getItem("usagePlannerLang") || "zh";

    function setLanguage(lang) {
      currentLang = lang;
      localStorage.setItem("usagePlannerLang", lang);
      document.documentElement.lang = lang === "zh" ? "zh-Hant" : "en";
      document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        if (i18nDict[currentLang][key]) {
          el.innerHTML = i18nDict[currentLang][key];
        }
      });
      refresh().catch((error) => setStatus("importStatus", error.message, "error"));
    }

    const $ = (id) => document.getElementById(id);

    function getMsg(key) { return i18nDict[currentLang][key] || key; }

    function pad(n) { return String(n).padStart(2, "0"); }

    function clock(minutes) {
      minutes = ((minutes % 1440) + 1440) % 1440;
      return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
    }

    function setStatus(id, text, kind = "") {
      const el = $(id);
      el.textContent = text;
      el.className = `status ${kind}`;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: {"Content-Type": "application/json"},
        ...options,
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      return payload;
    }

    function selectedTools() {
      const tools = [];
      if ($("toolCodex").checked) tools.push("codex");
      if ($("toolClaude").checked) tools.push("claude-code");
      return tools;
    }

    function importPayload(dryRun) {
      return {
        days: Number($("importDays").value || 7),
        idle_minutes: Number($("idleMinutes").value || 45),
        tail_minutes: Number($("tailMinutes").value || 15),
        tools: selectedTools(),
        dry_run: dryRun,
      };
    }

    async function refresh() {
      const days = Number($("importDays").value || 7);
      const state = await api(`/api/state?days=${days}&reminders=7`);
      $("dataPath").textContent = state.data_path;
      $("mainWindow").textContent = `${clock(state.suggestion.start_minutes)}-${clock(state.suggestion.end_minutes)}`;
      $("remindTime").textContent = clock(state.suggestion.remind_minutes);
      $("totalUsage").textContent = state.suggestion.total_duration;
      $("sessionCount").textContent = `${state.suggestion.total_sessions} ${getMsg("msg-session-unit")}`;
      $("confidence").textContent = state.suggestion.confidence;
      $("source").textContent = state.suggestion.source;
      $("timezone").textContent = state.timezone;
      $("preferredWindows").value = state.preferences.preferred_windows_text;
      $("quotaWindow").value = state.preferences.quota_window_minutes;
      $("setupLead").value = state.preferences.setup_lead_minutes;

      const maxScore = Math.max(1, ...state.suggestion.top_slots.map((slot) => slot.score));
      $("topSlots").innerHTML = state.suggestion.top_slots.map((slot) => {
        const width = Math.max(8, Math.round((slot.score / maxScore) * 100));
        return `<div class="slot"><span class="badge">${clock(slot.start)}-${clock(slot.end)}</span><div class="bar" style="--w:${width}%"></div></div>`;
      }).join("");

      $("reminders").innerHTML = state.reminders.map((item) => (
        `<tr><td>${item.remind_at}</td><td>${item.start_at} - ${item.end_clock}</td></tr>`
      )).join("");
    }

    async function runImport(dryRun) {
      if (selectedTools().length === 0) {
        setStatus("importStatus", getMsg("msg-no-tool"), "error");
        return;
      }
      setStatus("importStatus", getMsg("msg-processing"));
      const result = await api("/api/import-logs", {
        method: "POST",
        body: JSON.stringify(importPayload(dryRun)),
      });
      const pieces = result.tools.map((item) => (
        `${item.tool}: ${item.prompts} ${getMsg("msg-import-res-1")} ${item.added} ${getMsg("msg-import-res-2")}`
      ));
      const notWritten = dryRun ? getMsg("msg-not-written") : "";
      setStatus("importStatus", `${pieces.join(", ")}${getMsg("msg-dup-1")}${result.duplicates}${getMsg("msg-dup-2")}${notWritten}`, "ok");
      if (!dryRun) await refresh();
    }

    async function tune() {
      setStatus("importStatus", getMsg("msg-tuning"));
      const days = Number($("importDays").value || 7);
      const result = await api("/api/tune", {
        method: "POST",
        body: JSON.stringify({days, force: true, windows: 2}),
      });
      setStatus("importStatus", `${getMsg("msg-new-pref")}${result.windows_text || "無/None"}`, "ok");
      await refresh();
    }

    async function savePrefs() {
      setStatus("prefsStatus", getMsg("msg-saving"));
      const payload = {
        preferred_windows: $("preferredWindows").value,
        quota_window_minutes: Number($("quotaWindow").value || 300),
        setup_lead_minutes: Number($("setupLead").value || 0),
      };
      await api("/api/preferences", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setStatus("prefsStatus", getMsg("msg-saved"), "ok");
      await refresh();
    }

    async function addSession() {
      setStatus("manualStatus", getMsg("msg-adding"));
      await api("/api/session", {
        method: "POST",
        body: JSON.stringify({
          tool: $("manualTool").value,
          start: $("manualStart").value,
          end: $("manualEnd").value,
        }),
      });
      setStatus("manualStatus", getMsg("msg-added"), "ok");
      await refresh();
    }

    function warmupPayload(dryRun) {
      return {
        method: $("warmupMethod").value,
        prompt: $("warmupPrompt").value || "ping",
        project_path: $("warmupProjectPath").value || null,
        force: $("warmupForce").checked,
        dry_run: dryRun,
        days: Number($("importDays").value || 7),
      };
    }

    async function sendWarmup(dryRun) {
      setStatus("warmupStatus", dryRun ? getMsg("msg-previewing") : getMsg("msg-sending"));
      const result = await api("/api/warmup", {
        method: "POST",
        body: JSON.stringify(warmupPayload(dryRun)),
      });
      
      // Backend returns a chinese message, but we can do a simple prefix replacement if we want to be nice
      let msg = result.message;
      if (currentLang === "en") {
        msg = msg.replace("跳過 warmup：", "Skip warmup: ")
                 .replace("[dry-run] 會使用", "[dry-run] Will use")
                 .replace("模式送出 prompt：", " mode to send prompt: ")
                 .replace("，提前量", ", setup lead ")
                 .replace("分鐘", " min")
                 .replace("✓ Warmup 完成，已記錄到 usage.json。", "✓ Warmup completed, recorded to usage.json.")
                 .replace("⚠ Warmup 結束，exit code", "⚠ Warmup finished, exit code")
                 .replace("，已記錄。", ", recorded.");
      }
      
      setStatus("warmupStatus", msg, result.exit_code === 0 ? "ok" : "error");
      if (!dryRun) await refresh();
    }

    async function scheduleWarmup() {
      setStatus("warmupStatus", getMsg("msg-scheduling"));
      const result = await api("/api/schedule-warmup", {
        method: "POST",
        body: JSON.stringify({
          method: $("warmupMethod").value,
          prompt: $("warmupPrompt").value || "ping",
          project_path: $("warmupProjectPath").value || null,
          days: Number($("importDays").value || 7),
        }),
      });
      let msg = result.message;
      if (currentLang === "en") {
        msg = msg.replace("✓ 已安裝 warmup 排程：每日", "✓ Installed warmup schedule: daily");
      }
      setStatus("warmupStatus", msg, "ok");
    }

    async function uninstallWarmup() {
      setStatus("warmupStatus", getMsg("msg-unscheduling"));
      const result = await api("/api/schedule-warmup", {
        method: "DELETE",
      });
      let msg = result.message;
      if (currentLang === "en") {
        msg = msg.replace("已移除排程：", "Removed schedule: ")
                 .replace("排程檔不存在，無需移除。", "Schedule file not found, nothing to remove.");
      }
      setStatus("warmupStatus", msg, "ok");
    }

    function wire(id, fn) {
      $(id).addEventListener("click", async () => {
        const buttons = Array.from(document.querySelectorAll("button"));
        buttons.forEach((button) => button.disabled = true);
        try {
          await fn();
        } catch (error) {
          setStatus("importStatus", error.message, "error");
        } finally {
          buttons.forEach((button) => button.disabled = false);
        }
      });
    }

    $("langToggleBtn").addEventListener("click", () => {
      setLanguage(currentLang === "zh" ? "en" : "zh");
    });

    wire("refreshBtn", refresh);
    wire("importBtn", () => runImport(false));
    wire("previewImportBtn", () => runImport(true));
    wire("runImportBtn", () => runImport(false));
    wire("tuneBtn", tune);
    wire("savePrefsBtn", savePrefs);
    wire("addSessionBtn", addSession);
    wire("warmupDryRunBtn", () => sendWarmup(true));
    wire("warmupSendBtn", () => sendWarmup(false));
    wire("scheduleWarmupBtn", scheduleWarmup);
    wire("uninstallWarmupBtn", uninstallWarmup);

    setLanguage(currentLang);
  </script>
</body>
</html>
"""


class WebApp:
    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path

    def load(self) -> dict[str, Any]:
        return planner.load_data(self.data_path)

    def save(self, data: dict[str, Any]) -> None:
        planner.save_data(self.data_path, data)

    def state(self, days: int, reminder_count: int) -> dict[str, Any]:
        data = self.load()
        suggestion = planner.make_suggestion(data, days)
        _, reminders = planner.upcoming_reminders(data, days, reminder_count)
        prefs = data["preferences"]
        return {
            "data_path": str(self.data_path),
            "timezone": data["timezone"],
            "preferences": {
                "preferred_windows_text": ",".join(
                    f"{item['start']}-{item['end']}"
                    for item in prefs.get("preferred_windows", [])
                ),
                "quota_window_minutes": prefs.get("quota_window_minutes", 300),
                "setup_lead_minutes": prefs.get("setup_lead_minutes", 210),
            },
            "suggestion": {
                "source": suggestion.source,
                "confidence": suggestion.confidence,
                "start_minutes": suggestion.start_minutes,
                "end_minutes": suggestion.end_minutes,
                "remind_minutes": suggestion.remind_minutes,
                "total_sessions": suggestion.total_sessions,
                "total_minutes": suggestion.total_minutes,
                "total_duration": planner.format_duration(suggestion.total_minutes),
                "top_slots": [
                    {"start": start, "end": end, "score": score}
                    for start, end, score in suggestion.top_slots
                ],
            },
            "reminders": [
                {
                    "remind_at": planner.format_datetime(item.remind_at),
                    "start_at": planner.format_datetime(item.start_at),
                    "end_clock": item.end_at.strftime("%H:%M %Z"),
                }
                for item in reminders
            ],
        }

    def import_logs(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        tools = payload.get("tools") or list(planner.SUPPORTED_TOOLS)
        tools = [tool for tool in tools if tool in planner.SUPPORTED_TOOLS]
        if not tools:
            raise ValueError("至少選一個工具。")
        days = positive_int(payload.get("days"), 7, "days")
        idle_minutes = positive_int(payload.get("idle_minutes"), 45, "idle_minutes")
        tail_minutes = nonnegative_int(payload.get("tail_minutes"), 15, "tail_minutes")
        dry_run = bool(payload.get("dry_run", False))
        cutoff = None
        if not payload.get("all", False):
            cutoff = planner.now_in(data["timezone"]) - timedelta(days=days)

        inferred: list[planner.InferredSession] = []
        stats: dict[str, dict[str, int]] = {}

        if "codex" in tools:
            paths = planner.discover_codex_logs(Path(payload.get("codex_root") or planner.DEFAULT_CODEX_LOG_ROOT).expanduser())
            events = planner.codex_log_events(paths, data["timezone"], cutoff)
            stats["codex"] = {
                "files": len(paths),
                "prompts": sum(1 for event in events if event.is_prompt),
                "added": 0,
            }
            inferred.extend(
                planner.infer_sessions_from_events(events, "codex", "codex-log", idle_minutes, tail_minutes)
            )

        if "claude-code" in tools:
            paths = planner.discover_claude_logs(Path(payload.get("claude_root") or planner.DEFAULT_CLAUDE_LOG_ROOT).expanduser())
            events = planner.claude_log_events(paths, data["timezone"], cutoff)
            stats["claude-code"] = {
                "files": len(paths),
                "prompts": sum(1 for event in events if event.is_prompt),
                "added": 0,
            }
            inferred.extend(
                planner.infer_sessions_from_events(events, "claude-code", "claude-log", idle_minutes, tail_minutes)
            )

        known = planner.imported_session_ids(data)
        duplicates = 0
        for session in inferred:
            import_id = planner.import_id_for_session(session, idle_minutes, tail_minutes)
            if import_id in known:
                duplicates += 1
                continue
            stats.setdefault(session.tool, {"files": 0, "prompts": 0, "added": 0})
            stats[session.tool]["added"] += 1
            if not dry_run:
                planner.append_inferred_session(data, session, import_id, idle_minutes, tail_minutes)
                known.add(import_id)

        if not dry_run:
            self.save(data)

        return {
            "dry_run": dry_run,
            "duplicates": duplicates,
            "tools": [
                {"tool": tool, **stats.get(tool, {"files": 0, "prompts": 0, "added": 0})}
                for tool in tools
            ],
        }

    def tune(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        days = positive_int(payload.get("days"), 7, "days")
        count = positive_int(payload.get("windows"), 2, "windows")
        min_sessions = nonnegative_int(payload.get("min_sessions"), 3, "min_sessions")
        min_minutes = nonnegative_int(payload.get("min_minutes"), 180, "min_minutes")
        force = bool(payload.get("force", False))
        windows, session_count, total_minutes = planner.tuned_windows_from_sessions(data, days, count)
        enough = session_count >= min_sessions and total_minutes >= min_minutes
        if not windows:
            raise ValueError("最近資料內沒有可用 session。")
        if not enough and not force:
            raise ValueError("資料量不足，請累積更多資料或使用 force。")
        data["preferences"]["preferred_windows"] = [planner.window_to_dict(window) for window in windows]
        self.save(data)
        windows_text = ",".join(
            f"{item['start']}-{item['end']}"
            for item in data["preferences"]["preferred_windows"]
        )
        print(f"[WebUI] ✓ 自動微調偏好時段：{windows_text}（sessions={session_count}, 總計 {total_minutes} 分鐘）")
        return {
            "session_count": session_count,
            "total_minutes": total_minutes,
            "windows_text": windows_text,
        }

    def save_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        prefs = data["preferences"]
        raw_windows = str(payload.get("preferred_windows") or "").strip()
        if raw_windows:
            prefs["preferred_windows"] = [
                planner.window_to_dict(planner.parse_window(item.strip()))
                for item in raw_windows.split(",")
                if item.strip()
            ]
        prefs["quota_window_minutes"] = bounded_int(
            payload.get("quota_window_minutes"),
            300,
            "quota_window_minutes",
            minimum=1,
            maximum=1440,
        )
        prefs["setup_lead_minutes"] = bounded_int(
            payload.get("setup_lead_minutes"),
            240,
            "setup_lead_minutes",
            minimum=0,
            maximum=1440,
        )
        self.save(data)
        windows_text = ",".join(
            f"{item['start']}-{item['end']}"
            for item in prefs.get("preferred_windows", [])
        ) or "（未設定）"
        print(
            f"[WebUI] ✓ 偏好設定已儲存 — "
            f"時段：{windows_text} / "
            f"視窗長度：{prefs['quota_window_minutes']} 分鐘 / "
            f"提前提醒：{prefs['setup_lead_minutes']} 分鐘"
        )
        return {"saved": True}

    def add_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        tool = payload.get("tool")
        if tool not in planner.SUPPORTED_TOOLS:
            raise ValueError("不支援的工具。")
        start = planner.parse_datetime(str(payload.get("start") or ""), data["timezone"])
        end = planner.parse_datetime(str(payload.get("end") or ""), data["timezone"])
        if end <= start:
            raise ValueError("結束時間必須晚於開始時間。")
        planner.append_session(data, tool, start, end, source="manual-web")
        self.save(data)
        duration = int((end - start).total_seconds() // 60)
        print(f"[WebUI] ✓ 已新增 {tool} 使用紀錄：{planner.format_duration(duration)}（{start.strftime('%H:%M')}–{end.strftime('%H:%M')}）")
        return {"saved": True}

    def warmup(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        tz_name = data["timezone"]
        method = payload.get("method", "cli")
        if method not in ("cli", "deeplink"):
            raise ValueError("method 必須是 cli 或 deeplink。")
        prompt = str(payload.get("prompt") or "ping")
        project_path = payload.get("project_path") or None
        force = bool(payload.get("force", False))
        dry_run = bool(payload.get("dry_run", False))

        lead_minutes = int(data["preferences"].get("setup_lead_minutes", 210))
        days = int(payload.get("days", 7))

        if not force:
            should_fire, reason, _ = planner.should_warmup_now(
                data, lead_minutes, days=days
            )
            if not should_fire:
                print(f"[WebUI] 跳過 warmup：{reason}")
                return {"exit_code": 0, "message": f"跳過 warmup：{reason}", "skipped": True}

        if dry_run:
            print(f"[WebUI] [dry-run] 會使用 {method} 模式送出 prompt：{prompt!r}，提前量 {lead_minutes} 分鐘")
            return {
                "exit_code": 0,
                "message": f"[dry-run] 會使用 {method} 模式送出 prompt：{prompt!r}，提前量 {lead_minutes} 分鐘",
                "dry_run": True,
            }

        started_at = planner.now_in(tz_name)
        print(f"[WebUI] 正在送出 warmup prompt（{method}）：{prompt!r}")

        if method == "cli":
            exit_code = planner.send_warmup_cli(prompt, project_path)
        else:
            exit_code = planner.send_warmup_deeplink(prompt, project_path)

        ended_at = planner.now_in(tz_name)

        planner.append_session(
            data,
            "codex",
            started_at,
            ended_at,
            source="auto-warmup",
            extra={
                "warmup_method": method,
                "warmup_prompt": prompt,
                "exit_code": exit_code,
            },
        )
        self.save(data)

        if exit_code == 0:
            msg = "✓ Warmup 完成，已記錄到 usage.json。"
        else:
            msg = f"⚠ Warmup 結束，exit code {exit_code}，已記錄。"
        print(f"[WebUI] {msg}")
        planner.send_macos_notification("Usage Planner", msg)
        return {"exit_code": exit_code, "message": msg}

    def schedule_warmup(self, payload: dict[str, Any]) -> dict[str, Any]:
        if sys.platform not in ("darwin", "win32"):
            raise ValueError("schedule-warmup 目前只支援 macOS 和 Windows。")
        data = self.load()
        method = payload.get("method", "cli")
        prompt = str(payload.get("prompt") or "ping")
        project_path = payload.get("project_path") or None
        days = int(payload.get("days", 7))
        lead_minutes = payload.get("lead_minutes")
        if lead_minutes is not None:
            lead_minutes = int(lead_minutes)

        if sys.platform == "darwin":
            plist_content, hour, minute = planner.generate_launchd_plist(
                data,
                method=method,
                prompt=prompt,
                lead_minutes=lead_minutes,
                project_path=project_path,
                days=days,
            )

            plist_path = planner.LAUNCHD_PLIST_PATH
            if plist_path.exists():
                subprocess.run(
                    ["launchctl", "unload", str(plist_path)],
                    check=False,
                )

            plist_path.parent.mkdir(parents=True, exist_ok=True)
            plist_path.write_text(plist_content, encoding="utf-8")

            result = subprocess.run(
                ["launchctl", "load", str(plist_path)],
                check=False,
            )
            if result.returncode == 0:
                msg = f"✓ 已安裝 warmup 排程：每日 {hour:02d}:{minute:02d}"
                print(f"[WebUI] {msg}")
                print(f"[WebUI]   plist 位置：{plist_path}")
                print(f"[WebUI]   log 位置：/tmp/{planner.LAUNCHD_LABEL}.out.log")
                return {"message": msg}
            raise ValueError(f"launchctl load 失敗，exit code {result.returncode}")
        else:
            # Windows
            rc = planner.install_schedule_windows(
                data, method, prompt, lead_minutes, project_path, days, dry_run=False,
            )
            if rc == 0:
                hour, minute = planner._compute_warmup_time(data, lead_minutes, days)
                msg = f"✓ 已安裝 warmup 排程：每日 {hour:02d}:{minute:02d}"
                print(f"[WebUI] {msg}")
                print(f"[WebUI]   任務名稱：{planner.SCHTASKS_TASK_NAME}")
                return {"message": msg}
            raise ValueError(f"schtasks /Create 失敗，exit code {rc}")

    def uninstall_warmup(self) -> dict[str, Any]:
        if sys.platform == "darwin":
            removed, msg = planner.uninstall_schedule_darwin()
        elif sys.platform == "win32":
            removed, msg = planner.uninstall_schedule_windows()
        else:
            return {"message": "目前平台不支援排程。"}
        if removed:
            print(f"[WebUI] {msg}")
        else:
            print(f"[WebUI] {msg}")
        return {"message": msg}


def positive_int(value: Any, default: int, name: str) -> int:
    result = int(value if value not in (None, "") else default)
    if result <= 0:
        raise ValueError(f"{name} 必須大於 0。")
    return result


def nonnegative_int(value: Any, default: int, name: str) -> int:
    result = int(value if value not in (None, "") else default)
    if result < 0:
        raise ValueError(f"{name} 必須大於等於 0。")
    return result


def bounded_int(value: Any, default: int, name: str, minimum: int, maximum: int) -> int:
    result = int(value if value not in (None, "") else default)
    if result < minimum or result > maximum:
        raise ValueError(f"{name} 必須介於 {minimum} 到 {maximum}。")
    return result


def make_handler(app: WebApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "UsagePlannerWeb/1.0"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self.send_html(HTML)
                    return
                if parsed.path == "/api/state":
                    query = parse_qs(parsed.query)
                    days = positive_int(first(query.get("days")), 7, "days")
                    reminders = positive_int(first(query.get("reminders")), 7, "reminders")
                    self.send_json({"ok": True, **app.state(days, reminders)})
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self.read_json()
                if parsed.path == "/api/import-logs":
                    self.send_json({"ok": True, **app.import_logs(payload)})
                    return
                if parsed.path == "/api/tune":
                    self.send_json({"ok": True, **app.tune(payload)})
                    return
                if parsed.path == "/api/preferences":
                    self.send_json({"ok": True, **app.save_preferences(payload)})
                    return
                if parsed.path == "/api/session":
                    self.send_json({"ok": True, **app.add_session(payload)})
                    return
                if parsed.path == "/api/warmup":
                    self.send_json({"ok": True, **app.warmup(payload)})
                    return
                if parsed.path == "/api/schedule-warmup":
                    self.send_json({"ok": True, **app.schedule_warmup(payload)})
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/schedule-warmup":
                    self.send_json({"ok": True, **app.uninstall_warmup()})
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def send_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            # Only suppress GET request logs to reduce noise; show POST/DELETE actions
            if self.command == "GET":
                return
            sys.stderr.write(f"[WebUI] {self.command} {self.path} — {format % args}\n")

    return Handler


def first(values: list[str] | None) -> str | None:
    if not values:
        return None
    return values[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Usage Planner local web UI")
    parser.add_argument("--data", help=f"資料檔路徑，預設為 {planner.DEFAULT_DATA_PATH}")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="啟動後用預設瀏覽器開啟")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_path = planner.data_path_from_arg(args.data)
    app = WebApp(data_path)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    url = f"http://{args.host}:{args.port}/"
    print(f"Usage Planner Web: {url}")
    print(f"Data: {data_path}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
