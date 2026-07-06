#!/usr/bin/env python3
"""Local web UI for Usage Planner.

This server intentionally binds to 127.0.0.1 by default and uses only Python's
standard library so it works on macOS and Windows without extra dependencies.
"""

from __future__ import annotations

import argparse
import json
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
        <h1>Usage Planner</h1>
        <div id="dataPath" class="muted"></div>
      </div>
      <div class="row">
        <button id="refreshBtn" title="重新整理">↻ 重新整理</button>
        <button id="importBtn" class="primary" title="匯入本機 log">↓ 匯入 log</button>
      </div>
    </header>

    <main class="grid">
      <section class="panel span-3 metric">
        <div class="muted">主要使用視窗</div>
        <div id="mainWindow" class="value">--</div>
        <div id="confidence" class="muted">--</div>
      </section>
      <section class="panel span-3 metric">
        <div class="muted">提醒時間</div>
        <div id="remindTime" class="value">--</div>
        <div class="muted">本地提醒，不消耗 usage</div>
      </section>
      <section class="panel span-3 metric">
        <div class="muted">最近用量</div>
        <div id="totalUsage" class="value">--</div>
        <div id="sessionCount" class="muted">--</div>
      </section>
      <section class="panel span-3 metric">
        <div class="muted">來源</div>
        <div id="source" class="value">--</div>
        <div id="timezone" class="muted">--</div>
      </section>

      <section class="panel span-12">
        <h2>Log 匯入</h2>
        <div class="form-grid">
          <label>範圍（天）
            <input id="importDays" type="number" min="1" value="7">
          </label>
          <label>閒置切段（分鐘）
            <input id="idleMinutes" type="number" min="1" value="45">
          </label>
          <label>結尾緩衝（分鐘）
            <input id="tailMinutes" type="number" min="0" value="15">
          </label>
          <div class="tools">
            <label><input id="toolCodex" type="checkbox" checked> Codex</label>
            <label><input id="toolClaude" type="checkbox" checked> Claude Code</label>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <button id="previewImportBtn">◌ 預覽</button>
          <button id="runImportBtn" class="primary">↓ 匯入</button>
          <button id="tuneBtn">◎ 微調偏好</button>
        </div>
        <div id="importStatus" class="status"></div>
      </section>

      <section class="panel span-7">
        <h2>近期高峰</h2>
        <div id="topSlots" class="timeline"></div>
      </section>

      <section class="panel span-5">
        <h2>接下來提醒</h2>
        <table>
          <thead><tr><th>提醒</th><th>工作視窗</th></tr></thead>
          <tbody id="reminders"></tbody>
        </table>
      </section>

      <section class="panel span-6">
        <h2>手動新增</h2>
        <div class="form-grid">
          <label>工具
            <select id="manualTool">
              <option value="codex">Codex</option>
              <option value="claude-code">Claude Code</option>
            </select>
          </label>
          <label>開始
            <input id="manualStart" type="datetime-local">
          </label>
          <label>結束
            <input id="manualEnd" type="datetime-local">
          </label>
          <button id="addSessionBtn" class="primary">＋ 新增</button>
        </div>
        <div id="manualStatus" class="status"></div>
      </section>

      <section class="panel span-6">
        <h2>設定</h2>
        <div class="form-grid">
          <label>偏好時段
            <input id="preferredWindows" placeholder="19:00-23:00">
          </label>
          <label>視窗長度（分鐘）
            <input id="quotaWindow" type="number" min="1" max="1440">
          </label>
          <label>提前提醒（分鐘）
            <input id="setupLead" type="number" min="0" max="1440">
          </label>
          <button id="savePrefsBtn" class="primary">✓ 儲存</button>
        </div>
        <div id="prefsStatus" class="status"></div>
      </section>

      <section class="panel span-12">
        <div class="danger-note">這個工具只分析本機使用時段與提醒規劃，不會自動呼叫 Codex、Claude Code 或消耗任何 usage。</div>
      </section>
    </main>
  </div>

  <script>
    const $ = (id) => document.getElementById(id);

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
      $("sessionCount").textContent = `${state.suggestion.total_sessions} 段 session`;
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
        setStatus("importStatus", "至少選一個工具。", "error");
        return;
      }
      setStatus("importStatus", "處理中...");
      const result = await api("/api/import-logs", {
        method: "POST",
        body: JSON.stringify(importPayload(dryRun)),
      });
      const pieces = result.tools.map((item) => (
        `${item.tool}: ${item.prompts} prompt, 新增 ${item.added} 段`
      ));
      setStatus("importStatus", `${pieces.join("；")}；重複 ${result.duplicates} 段${dryRun ? "；未寫入" : ""}`, "ok");
      if (!dryRun) await refresh();
    }

    async function tune() {
      setStatus("importStatus", "微調中...");
      const days = Number($("importDays").value || 7);
      const result = await api("/api/tune", {
        method: "POST",
        body: JSON.stringify({days, force: true, windows: 2}),
      });
      setStatus("importStatus", `新偏好：${result.windows_text || "無"}`, "ok");
      await refresh();
    }

    async function savePrefs() {
      setStatus("prefsStatus", "儲存中...");
      const payload = {
        preferred_windows: $("preferredWindows").value,
        quota_window_minutes: Number($("quotaWindow").value || 300),
        setup_lead_minutes: Number($("setupLead").value || 0),
      };
      await api("/api/preferences", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setStatus("prefsStatus", "已儲存", "ok");
      await refresh();
    }

    async function addSession() {
      setStatus("manualStatus", "新增中...");
      await api("/api/session", {
        method: "POST",
        body: JSON.stringify({
          tool: $("manualTool").value,
          start: $("manualStart").value,
          end: $("manualEnd").value,
        }),
      });
      setStatus("manualStatus", "已新增", "ok");
      await refresh();
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

    wire("refreshBtn", refresh);
    wire("importBtn", () => runImport(false));
    wire("previewImportBtn", () => runImport(true));
    wire("runImportBtn", () => runImport(false));
    wire("tuneBtn", tune);
    wire("savePrefsBtn", savePrefs);
    wire("addSessionBtn", addSession);

    refresh().catch((error) => setStatus("importStatus", error.message, "error"));
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
                "setup_lead_minutes": prefs.get("setup_lead_minutes", 240),
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
        return {
            "session_count": session_count,
            "total_minutes": total_minutes,
            "windows_text": ",".join(
                f"{item['start']}-{item['end']}"
                for item in data["preferences"]["preferred_windows"]
            ),
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
        return {"saved": True}


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
            return

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
