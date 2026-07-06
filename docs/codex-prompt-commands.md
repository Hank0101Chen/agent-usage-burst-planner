# Codex Prompt Commands

這份文件整理如何用「指令」把 prompt 交給 Codex。分成兩種版本：

- Codex CLI：在終端機直接執行 prompt。
- Codex App：用 `codex://` deep link 打開 App 並預填 prompt。

## Codex CLI 版本

Codex CLI 是終端機版 Codex。這種方式需要你的系統已經安裝 `codex` 指令。

先確認是否可用：

```bash
codex --version
```

如果出現版本號，代表 Codex CLI 已安裝。若顯示 `command not found`，表示需要另外安裝 Codex CLI。

### 開啟互動模式

```bash
codex
```

這會進入 Codex 的 terminal UI，你可以在裡面輸入 prompt。

### 啟動時直接帶 prompt

```bash
codex "Explain this codebase to me"
```

這會開啟 Codex CLI，並把字串當成初始 prompt。

### 快速執行單次 prompt

如果你只想讓 Codex 跑一次任務並把結果輸出到終端機，可以用：

```bash
codex exec "Explain this codebase"
```

這適合腳本、自動化或不需要互動 UI 的情境。

### 指定工作目錄

在目標專案資料夾內執行：

```bash
cd /path/to/project
codex "Summarize this repo"
```

或在支援的版本中搭配路徑參數使用：

```bash
codex --path /path/to/project "Summarize this repo"
```

### CLI 適合什麼情境

- 你想直接在終端機跑 Codex。
- 你想把 prompt 放進 shell script。
- 你想用 `codex exec` 做非互動任務。
- 你想在 CI 或自動化流程裡使用 Codex。

## Codex App 版本

Codex App 是桌面版。只安裝 Codex App 不一定會讓終端機多出 `codex` 指令，但你可以用 App 的 deep link 從命令列打開 App 並預填 prompt。

官方支援的形式是：

```text
codex://threads/new?prompt=...
```

`prompt=` 會設定新 thread composer 裡的初始文字。注意：這通常是「預填 prompt」，不一定會自動送出；你可能仍需要在 Codex App 裡按送出。

### macOS

```bash
open "codex://threads/new?prompt=Explain%20this%20repo"
```

### Windows PowerShell

```powershell
Start-Process "codex://threads/new?prompt=Explain%20this%20repo"
```

### 指定專案路徑

可以加上 `path=` 指定本機工作資料夾。`path` 必須是絕對路徑。

macOS：

```bash
open "codex://threads/new?path=/Users/hank/Documents/my-project&prompt=Explain%20this%20repo"
```

Windows PowerShell：

```powershell
Start-Process "codex://threads/new?path=C%3A%5CUsers%5CHank%5CDocuments%5Cmy-project&prompt=Explain%20this%20repo"
```

### URL encode prompt

Deep link 裡的 prompt 要做 URL encoding，尤其是空白、中文、符號、換行。

常見對照：

```text
空白 -> %20
換行 -> %0A
中文 -> 需要 URL encode
```

macOS 可以用 Python 快速 encode：

```bash
python3 -c 'import urllib.parse; print(urllib.parse.quote("幫我解釋這個 repo"))'
```

輸出可放進 `prompt=`：

```bash
open "codex://threads/new?prompt=%E5%B9%AB%E6%88%91%E8%A7%A3%E9%87%8B%E9%80%99%E5%80%8B%20repo"
```

Windows PowerShell：

```powershell
[uri]::EscapeDataString("幫我解釋這個 repo")
```

### App deep link 適合什麼情境

- 你只安裝 Codex App，沒有安裝 Codex CLI。
- 你想從 shell、捷徑、Raycast、Alfred、PowerShell 腳本打開 Codex App。
- 你想預填 prompt 和專案路徑，但最後仍由你在 App 裡確認送出。

## CLI vs App 差異

| 項目 | Codex CLI | Codex App deep link |
| --- | --- | --- |
| 是否需要安裝 CLI | 需要 | 不需要 |
| 是否打開桌面 App | 不會 | 會 |
| 是否能直接執行 prompt | 可以 | 通常只預填 composer |
| 是否適合自動化 | 適合 | 適合半自動化 |
| 是否支援指定專案 | 透過目前目錄或 CLI 參數 | 透過 `path=` |

## 進階：App Server

Codex 也有 `codex app-server`，可以用 JSON-RPC 建立 thread、啟動 turn，並串流事件。這是給產品整合或進階開發用的方式，不是一般使用者最簡單的命令列操作。

如果只是想「從終端機送一段 prompt 給 Codex」，優先選：

- 想直接執行：用 Codex CLI。
- 想打開桌面 App 並預填：用 `codex://` deep link。
