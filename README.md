# Agent Usage Burst Planner

這是一個本地 CLI 工具，用來追蹤 Codex / Claude Code 的實際使用時段，並根據最近一週資料推算你最常工作的高峰時間。

它不會自動呼叫 Codex、Claude Code 或任何外部服務，也不會自動消耗 usage。用途是提醒與規劃，避免用量被浪費或在真正要工作時才發現沒有安排好。

## 快速開始

初始化偏好設定：

```bash
python3 usage_planner.py init
```

也可以直接用非互動模式：

```bash
python3 usage_planner.py init --non-interactive --preferred-window 19:00-23:00 --setup-lead-minutes 240
```

手動補上一筆紀錄：

```bash
python3 usage_planner.py add claude-code --start 2026-07-06T20:00 --end 2026-07-06T22:30
```

更推薦的方式是用 `wrap` 包住你實際要跑的命令，工具會在命令結束後自動記錄使用時間：

```bash
python3 usage_planner.py wrap codex -- codex
python3 usage_planner.py wrap claude-code -- claude
```

如果你的 Claude Code 命令不是 `claude`，把最後的命令換成你本機實際使用的名稱。

也可以直接從 Codex / Claude Code 的本機 log 匯入實際 prompt 時間，這種方式不需要改變日常啟動流程：

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

列出接下來 7 次提醒：

```bash
python3 usage_planner.py reminders --analysis-days 7 --count 7
```

用最近一週實際紀錄微調偏好時段：

```bash
python3 usage_planner.py tune --days 7
```

## 網頁介面

macOS：

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

預設網址是：

```text
http://127.0.0.1:8765/
```

網頁介面和 CLI 使用同一份資料檔 `.usage_planner/usage.json`。它只在本機執行，不會把資料傳到外部服務。

## 資料位置

預設資料會存在：

```text
.usage_planner/usage.json
```

如要改位置：

```bash
python3 usage_planner.py --data /path/to/usage.json report
```

或設定環境變數：

```bash
export USAGE_PLANNER_DATA=/path/to/usage.json
```

## 建議邏輯

- 沒有使用紀錄時，先根據 `init` 輸入的偏好時段做冷啟動建議。
- 有使用紀錄後，使用最近 `--days` 天的 session 計算每日 30 分鐘區塊的活躍度。
- `wrap` 會執行你指定的命令並記錄開始/結束時間，適合用來累積第一週資料。
- `import-logs` 會解析本機 Codex / Claude Code log，把每次 prompt 時間推估成使用 session；它只保存時間、來源與計數，不保存 prompt 文字。
- 匯入 log 時，預設兩次活動間隔超過 45 分鐘就切成新 session，最後一次 prompt 後補 15 分鐘當作結束緩衝。
- 程式會找出最適合涵蓋高峰的規劃視窗，預設長度為 300 分鐘。
- `setup-lead-minutes` 預設是 240 分鐘，也就是高峰前 4 小時提醒你檢查當天安排與可用用量；它不是自動消耗 usage。
- `reminders` 會依照目前推算出的高峰時段列出接下來的本地提醒時間。
- `tune` 只使用實際 session 來更新偏好，預設至少需要 3 筆紀錄且合計 180 分鐘；資料不足時不會覆蓋原本偏好。

## 範例工作流

第一週：

```bash
python3 usage_planner.py init
python3 usage_planner.py import-logs --days 7
python3 usage_planner.py report
python3 usage_planner.py reminders
```

如果你想從現在開始即時記錄，也可以改用：

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

## License

MIT
