# Agent Usage Burst Planner

Plan and track AI coding sessions to concentrate usage into your most valuable working windows.

規劃與追蹤 AI coding 使用時段，幫助你把 usage 集中在最有價值的工作窗口。

## Languages / 語言

- [English](#english)
- [中文](#中文)

## Web UI Quick Start / 網頁介面快速開始

> **Note / 注意**: To use the `warmup` (CLI mode) and `wrap` features, please make sure you have downloaded and installed the **Codex CLI**.
> 若要使用 `warmup` (CLI 模式) 或 `wrap` 功能，請務必記得先下載安裝 **Codex CLI**。

macOS:

```bash
python3 usage_web.py --open
```

Windows:

```powershell
py usage_web.py --open
```

If `py` is unavailable:

```powershell
python usage_web.py --open
```

Default local URL:

```text
http://127.0.0.1:8765/
```

---

## English

Agent Usage Burst Planner is a local CLI and web tool for tracking real Codex / Claude Code usage patterns, importing local prompt logs, and estimating when you usually work most actively.

It does not automatically call Codex, Claude Code, or any external service. It also does not automatically consume usage. The purpose is planning and reminders.

The `warmup` command is an exception: it deliberately sends a minimal prompt (e.g. `"ping"`) via Codex CLI before your predicted peak window so the session is already active when you start working. This consumes a very small amount of usage and is clearly marked as `auto-warmup` in the data.

### Guides

- [Codex Prompt Commands](docs/codex-prompt-commands.md): CLI and Codex App command examples for sending or pre-filling prompts.

### Web UI

Start the local web UI:

```bash
python3 usage_web.py --open
```

On Windows:

```powershell
py usage_web.py --open
```

If `py` is unavailable:

```powershell
python usage_web.py --open
```

The web UI and CLI use the same data file: `.usage_planner/usage.json`. The app runs locally and does not send your data to external services.

Opening the web UI is enough for the dashboard features: importing logs, tuning preferred windows, editing preferences, adding historical sessions, viewing suggestions, and listing reminder times. It must remain running while you use the web page. To stop the web server, simply press `Ctrl+C` in the terminal or close the terminal window. It is not a background notification service after you close it.

### CLI Quick Start

Initialize preferences:

```bash
python3 usage_planner.py init
```

Run setup non-interactively:

```bash
python3 usage_planner.py init --non-interactive --preferred-window 19:00-23:00 --setup-lead-minutes 210
```

Manually add a historical session:

```bash
python3 usage_planner.py add claude-code --start 2026-07-06T20:00 --end 2026-07-06T22:30
```

Wrap a real command so the tool records its start and end time:

```bash
python3 usage_planner.py wrap codex -- codex
python3 usage_planner.py wrap claude-code -- claude
```

If your Claude Code command is not `claude`, replace the final command with the one you use locally.

### Import Logs

Import actual prompt times from local Codex / Claude Code logs without changing your daily launch flow:

```bash
python3 usage_planner.py import-logs --days 7
```

Preview without writing data:

```bash
python3 usage_planner.py import-logs --days 7 --dry-run
```

View the last 7 days of analysis:

```bash
python3 usage_planner.py report --days 7
```

Show only the suggested usage window:

```bash
python3 usage_planner.py suggest --days 7
```

List the next 7 local reminder times:

```bash
python3 usage_planner.py reminders --analysis-days 7 --count 7
```

Tune preferred windows from recent real sessions:

```bash
python3 usage_planner.py tune --days 7
```

### Warmup (Auto Pre-Peak Prompt)

Send a minimal-usage prompt before the peak window to warm up the session. **This consumes a small amount of usage.**

Preview without executing:

```bash
python3 usage_planner.py warmup --force --dry-run
```

Send warmup now (force ignores timing check):

```bash
python3 usage_planner.py warmup --force
```

Customize the prompt and lead time:

```bash
python3 usage_planner.py warmup --force --prompt "ping" --lead-minutes 30
```

Install a daily macOS launchd schedule:

```bash
python3 usage_planner.py schedule-warmup
```

Preview the schedule without installing:

```bash
python3 usage_planner.py schedule-warmup --dry-run
```

Remove the schedule:

```bash
python3 usage_planner.py schedule-warmup --uninstall
```

The standalone script `warmup_sender.py` can also be used directly:

```bash
python3 warmup_sender.py --force --dry-run
```

### Data Location

Default data path:

```text
.usage_planner/usage.json
```

Use a custom data file:

```bash
python3 usage_planner.py --data /path/to/usage.json report
```

Or set an environment variable:

```bash
export USAGE_PLANNER_DATA=/path/to/usage.json
```

### How Suggestions Work

- When there are no sessions yet, the tool starts from the preferred window configured during `init`.
- After sessions are available, it scores daily 30-minute buckets from the recent `--days` window.
- `wrap` runs the command you provide and records its start and end time.
- `import-logs` parses local Codex / Claude Code logs and stores only time, source, and counts. It does not save prompt text.
- During log import, activities separated by more than 45 minutes are split into separate sessions. The final prompt gets a 15-minute tail buffer.
- The default planning window is 300 minutes.
- `setup-lead-minutes` defaults to 210 minutes, so reminders are listed 3.5 hours before the suggested peak window.
- `tune` updates preferred windows from real sessions. By default, it needs at least 3 sessions and 180 total minutes.

### Example Workflow

First week:

```bash
python3 usage_planner.py init
python3 usage_planner.py import-logs --days 7
python3 usage_planner.py report
python3 usage_planner.py reminders
```

If you want to record usage live from now on:

```bash
python3 usage_planner.py wrap codex -- codex
python3 usage_planner.py wrap claude-code -- claude
```

Later:

```bash
python3 usage_planner.py tune --days 7
python3 usage_planner.py suggest
```

If the suggested window does not match your real habits, keep collecting data for a few more days. More data makes the suggestion closer to your actual working pattern.

### License

MIT

---

## 中文

Agent Usage Burst Planner 是一個本地 CLI 與網頁工具，用來追蹤 Codex / Claude Code 的實際使用時段、匯入本機 prompt log，並推算你最常工作的高峰時間。

它不會自動呼叫 Codex、Claude Code 或任何外部服務，也不會自動消耗 usage。用途是提醒與規劃。

`warmup` 命令是唯一的例外：它會在預測的高峰時間前，透過 Codex CLI 主動送出一段極簡 prompt（例如 `"ping"`），讓 session 在你真正開始工作前就已經啟動。這會消耗極少量 usage，並在資料中明確標記為 `auto-warmup`。

### 文件

- [Codex Prompt Commands](docs/codex-prompt-commands.md)：整理 CLI 與 Codex App 用指令送出或預填 prompt 的方式。

### 網頁介面

啟動本機網頁介面：

```bash
python3 usage_web.py --open
```

Windows：

```powershell
py usage_web.py --open
```

如果 `py` 不存在：

```powershell
python usage_web.py --open
```

網頁介面和 CLI 使用同一份資料檔 `.usage_planner/usage.json`。它只在本機執行，不會把資料傳到外部服務。

只要開啟 Web UI，就可以使用儀表板上的主要功能：匯入 log、微調偏好時段、修改偏好、手動新增歷史 session、查看建議時段、列出提醒時間。使用網頁時，本機 server 需要持續開著。要關閉網頁伺服器，只需在終端機按下 `Ctrl+C`，或直接關閉終端機視窗即可。關掉後它不會變成背景通知服務。

### CLI 快速開始

初始化偏好設定：

```bash
python3 usage_planner.py init
```

也可以直接用非互動模式：

```bash
python3 usage_planner.py init --non-interactive --preferred-window 19:00-23:00 --setup-lead-minutes 210
```

手動補上一筆歷史紀錄：

```bash
python3 usage_planner.py add claude-code --start 2026-07-06T20:00 --end 2026-07-06T22:30
```

用 `wrap` 包住你實際要跑的命令，工具會在命令結束後自動記錄使用時間：

```bash
python3 usage_planner.py wrap codex -- codex
python3 usage_planner.py wrap claude-code -- claude
```

如果你的 Claude Code 命令不是 `claude`，把最後的命令換成你本機實際使用的名稱。

### 匯入 Log

直接從 Codex / Claude Code 的本機 log 匯入實際 prompt 時間，不需要改變日常啟動流程：

```bash
python3 usage_planner.py import-logs --days 7
```

先預覽不寫入：

```bash
python3 usage_planner.py import-logs --days 7 --dry-run
```

查看最近 7 天分析：

```bash
python3 usage_planner.py report --days 7
```

只看建議時段：

```bash
python3 usage_planner.py suggest --days 7
```

列出接下來 7 次本地提醒時間：

```bash
python3 usage_planner.py reminders --analysis-days 7 --count 7
```

用最近一週實際紀錄微調偏好時段：

```bash
python3 usage_planner.py tune --days 7
```

### Warmup（高峰前自動暖機）

在高峰時間前自動送出一段極低 usage 的 prompt，讓 session 提前啟動。**這會消耗少量 usage。**

先預覽不執行：

```bash
python3 usage_planner.py warmup --force --dry-run
```

立即送出 warmup（--force 跳過時間檢查）：

```bash
python3 usage_planner.py warmup --force
```

自訂 prompt 和提前時間：

```bash
python3 usage_planner.py warmup --force --prompt "ping" --lead-minutes 30
```

安裝 macOS 每日 launchd 排程：

```bash
python3 usage_planner.py schedule-warmup
```

預覽排程內容：

```bash
python3 usage_planner.py schedule-warmup --dry-run
```

移除排程：

```bash
python3 usage_planner.py schedule-warmup --uninstall
```

也可以直接使用獨立腳本：

```bash
python3 warmup_sender.py --force --dry-run
```

### 資料位置

預設資料位置：

```text
.usage_planner/usage.json
```

改用其他資料檔：

```bash
python3 usage_planner.py --data /path/to/usage.json report
```

或設定環境變數：

```bash
export USAGE_PLANNER_DATA=/path/to/usage.json
```

### 建議邏輯

- 沒有使用紀錄時，先根據 `init` 輸入的偏好時段做冷啟動建議。
- 有使用紀錄後，使用最近 `--days` 天的 session 計算每日 30 分鐘區塊的活躍度。
- `wrap` 會執行你指定的命令並記錄開始/結束時間。
- `import-logs` 會解析本機 Codex / Claude Code log，只保存時間、來源與計數，不保存 prompt 文字。
- 匯入 log 時，預設兩次活動間隔超過 45 分鐘就切成新 session，最後一次 prompt 後補 15 分鐘當作結束緩衝。
- 預設規劃視窗長度為 300 分鐘。
- `setup-lead-minutes` 預設是 210 分鐘，也就是高峰前 3.5 小時提醒你檢查當天安排與可用用量。
- `tune` 只使用實際 session 來更新偏好，預設至少需要 3 筆紀錄且合計 180 分鐘。

### 範例工作流

第一週：

```bash
python3 usage_planner.py init
python3 usage_planner.py import-logs --days 7
python3 usage_planner.py report
python3 usage_planner.py reminders
```

如果你想從現在開始即時記錄：

```bash
python3 usage_planner.py wrap codex -- codex
python3 usage_planner.py wrap claude-code -- claude
```

之後：

```bash
python3 usage_planner.py tune --days 7
python3 usage_planner.py suggest
```

如果建議時段不符合真實習慣，就繼續紀錄幾天；資料越多，建議會越貼近實際使用模式。

### 授權

MIT
