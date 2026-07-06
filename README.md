# Agent Usage Burst Planner

Plan and track AI coding sessions to concentrate usage into your most valuable working windows.

規劃與追蹤 AI coding 使用時段，幫助你把 usage 集中在最有價值的工作窗口。

This is a local CLI and web tool for tracking real Codex / Claude Code usage patterns, importing local prompt logs, and estimating when you usually work most actively.

這是一個本地 CLI 與網頁工具，用來追蹤 Codex / Claude Code 的實際使用時段、匯入本機 prompt log，並推算你最常工作的高峰時間。

It does not automatically call Codex, Claude Code, or any external service. It also does not automatically consume usage. The purpose is planning and reminders.

它不會自動呼叫 Codex、Claude Code 或任何外部服務，也不會自動消耗 usage。用途是提醒與規劃。

## Quick Start / 快速開始

Initialize preferences:

初始化偏好設定：

```bash
python3 usage_planner.py init
```

Run setup non-interactively:

也可以直接用非互動模式：

```bash
python3 usage_planner.py init --non-interactive --preferred-window 19:00-23:00 --setup-lead-minutes 240
```

Manually add a historical session:

手動補上一筆歷史紀錄：

```bash
python3 usage_planner.py add claude-code --start 2026-07-06T20:00 --end 2026-07-06T22:30
```

Wrap a real command so the tool records its start and end time:

用 `wrap` 包住你實際要跑的命令，工具會在命令結束後自動記錄使用時間：

```bash
python3 usage_planner.py wrap codex -- codex
python3 usage_planner.py wrap claude-code -- claude
```

If your Claude Code command is not `claude`, replace the final command with the one you use locally.

如果你的 Claude Code 命令不是 `claude`，把最後的命令換成你本機實際使用的名稱。

## Import Logs / 匯入 Log

Import actual prompt times from local Codex / Claude Code logs without changing your daily launch flow:

直接從 Codex / Claude Code 的本機 log 匯入實際 prompt 時間，不需要改變日常啟動流程：

```bash
python3 usage_planner.py import-logs --days 7
```

Preview without writing data:

先預覽不寫入：

```bash
python3 usage_planner.py import-logs --days 7 --dry-run
```

View the last 7 days of analysis:

查看最近 7 天分析：

```bash
python3 usage_planner.py report --days 7
```

Show only the suggested usage window:

只看建議時段：

```bash
python3 usage_planner.py suggest --days 7
```

List the next 7 local reminder times:

列出接下來 7 次本地提醒時間：

```bash
python3 usage_planner.py reminders --analysis-days 7 --count 7
```

Tune preferred windows from recent real sessions:

用最近一週實際紀錄微調偏好時段：

```bash
python3 usage_planner.py tune --days 7
```

## Web UI / 網頁介面

macOS:

```bash
python3 usage_web.py --open
```

Windows:

```powershell
py usage_web.py --open
```

If `py` is unavailable:

如果 `py` 不存在：

```powershell
python usage_web.py --open
```

Default local URL:

預設本機網址：

```text
http://127.0.0.1:8765/
```

The web UI and CLI use the same data file: `.usage_planner/usage.json`. The app runs locally and does not send your data to external services.

網頁介面和 CLI 使用同一份資料檔 `.usage_planner/usage.json`。它只在本機執行，不會把資料傳到外部服務。

## Data Location / 資料位置

Default data path:

預設資料位置：

```text
.usage_planner/usage.json
```

Use a custom data file:

改用其他資料檔：

```bash
python3 usage_planner.py --data /path/to/usage.json report
```

Or set an environment variable:

或設定環境變數：

```bash
export USAGE_PLANNER_DATA=/path/to/usage.json
```

## How Suggestions Work / 建議邏輯

- When there are no sessions yet, the tool starts from the preferred window configured during `init`.
- 沒有使用紀錄時，先根據 `init` 輸入的偏好時段做冷啟動建議。
- After sessions are available, it scores daily 30-minute buckets from the recent `--days` window.
- 有使用紀錄後，使用最近 `--days` 天的 session 計算每日 30 分鐘區塊的活躍度。
- `wrap` runs the command you provide and records its start and end time.
- `wrap` 會執行你指定的命令並記錄開始/結束時間。
- `import-logs` parses local Codex / Claude Code logs and stores only time, source, and counts. It does not save prompt text.
- `import-logs` 會解析本機 Codex / Claude Code log，只保存時間、來源與計數，不保存 prompt 文字。
- During log import, activities separated by more than 45 minutes are split into separate sessions. The final prompt gets a 15-minute tail buffer.
- 匯入 log 時，預設兩次活動間隔超過 45 分鐘就切成新 session，最後一次 prompt 後補 15 分鐘當作結束緩衝。
- The default planning window is 300 minutes.
- 預設規劃視窗長度為 300 分鐘。
- `setup-lead-minutes` defaults to 240 minutes, so reminders are listed 4 hours before the suggested peak window.
- `setup-lead-minutes` 預設是 240 分鐘，也就是高峰前 4 小時提醒你檢查當天安排與可用用量。
- `tune` updates preferred windows from real sessions. By default, it needs at least 3 sessions and 180 total minutes.
- `tune` 只使用實際 session 來更新偏好，預設至少需要 3 筆紀錄且合計 180 分鐘。

## Example Workflow / 範例工作流

First week:

第一週：

```bash
python3 usage_planner.py init
python3 usage_planner.py import-logs --days 7
python3 usage_planner.py report
python3 usage_planner.py reminders
```

If you want to record usage live from now on:

如果你想從現在開始即時記錄：

```bash
python3 usage_planner.py wrap codex -- codex
python3 usage_planner.py wrap claude-code -- claude
```

Later:

之後：

```bash
python3 usage_planner.py tune --days 7
python3 usage_planner.py suggest
```

If the suggested window does not match your real habits, keep collecting data for a few more days. More data makes the suggestion closer to your actual working pattern.

如果建議時段不符合真實習慣，就繼續紀錄幾天；資料越多，建議會越貼近實際使用模式。

## License / 授權

MIT
