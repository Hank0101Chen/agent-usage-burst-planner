#!/usr/bin/env python3
"""Send a minimal-usage warmup prompt before the predicted peak window.

This script reads the usage planner data to determine the optimal warmup
time and sends a lightweight prompt via Codex CLI or Codex App deep link.

Unlike the rest of the planner, this script *does* trigger an external
action that may consume usage. It is clearly marked as ``auto-warmup``
in the recorded session data.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import usage_planner

DEFAULT_WARMUP_PROMPT = "ping"


def send_warmup_cli(prompt: str, project_path: str | None = None) -> int:
    """Execute a warmup prompt via ``codex exec``."""
    command = ["codex"]
    if project_path:
        command += ["--path", project_path]
    command += ["exec", prompt]

    try:
        result = subprocess.run(
            command,
            check=False,
            timeout=120,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode
    except FileNotFoundError:
        print("錯誤：找不到 codex 命令。請安裝 Codex CLI 或改用 --method deeplink。", file=sys.stderr)
        return 127
    except subprocess.TimeoutExpired:
        print("警告：codex exec 超時（120 秒），已中斷。", file=sys.stderr)
        return 124


def send_warmup_deeplink(prompt: str, project_path: str | None = None) -> int:
    """Open Codex App with a pre-filled warmup prompt via deep link."""
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"codex://threads/new?prompt={encoded_prompt}"
    if project_path:
        encoded_path = urllib.parse.quote(project_path)
        url += f"&path={encoded_path}"

    if sys.platform == "darwin":
        command = ["open", url]
    elif sys.platform == "win32":
        command = ["powershell", "-Command", f'Start-Process "{url}"']
    else:
        print("錯誤：deep link 模式僅支援 macOS 和 Windows。", file=sys.stderr)
        return 1

    try:
        result = subprocess.run(
            command,
            check=False,
            timeout=30,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode
    except FileNotFoundError:
        print(f"錯誤：找不到命令 {command[0]}。", file=sys.stderr)
        return 127
    except subprocess.TimeoutExpired:
        print("警告：打開 deep link 超時。", file=sys.stderr)
        return 124


def should_warmup_now(
    data: dict,
    warmup_lead_minutes: int,
    tolerance_minutes: int = 10,
) -> tuple[bool, str, datetime | None]:
    """Check if now is the right time to send a warmup prompt.

    Returns ``(should_fire, reason, peak_start)`` where *peak_start* is the
    start of the upcoming peak window when ``should_fire`` is ``True``.
    """
    suggestion = usage_planner.make_suggestion(data, days=7)
    tz_name = data["timezone"]
    now = usage_planner.now_in(tz_name)
    tz = usage_planner.load_timezone(tz_name)

    # Check today and tomorrow
    for offset in range(2):
        day = now + timedelta(days=offset)
        midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
        peak_start = midnight + timedelta(minutes=suggestion.start_minutes)
        warmup_time = peak_start - timedelta(minutes=warmup_lead_minutes)

        delta = abs((now - warmup_time).total_seconds()) / 60
        if delta <= tolerance_minutes:
            return True, f"距離高峰 {usage_planner.format_clock(suggestion.start_minutes)} 還有 {warmup_lead_minutes} 分鐘", peak_start

    return False, "目前不在 warmup 時間範圍內", None


def run_warmup(
    data_path: Path,
    method: str,
    prompt: str,
    project_path: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    warmup_lead_minutes: int | None = None,
) -> int:
    """Execute the warmup flow: check timing, send prompt, record session."""
    data = usage_planner.load_data(data_path)
    tz_name = data["timezone"]
    if warmup_lead_minutes is None:
        warmup_lead_minutes = int(data["preferences"].get("setup_lead_minutes", 210))

    if not force:
        should_fire, reason, peak_start = should_warmup_now(data, warmup_lead_minutes)
        if not should_fire:
            print(f"跳過 warmup：{reason}")
            return 0
        print(f"Warmup 時間到：{reason}")
    else:
        print(f"強制執行 warmup（--force），提前量 {warmup_lead_minutes} 分鐘")

    if dry_run:
        print(f"[dry-run] 會使用 {method} 模式送出 prompt：{prompt!r}")
        if project_path:
            print(f"[dry-run] 專案路徑：{project_path}")
        print("[dry-run] 不會實際執行。")
        return 0

    started_at = usage_planner.now_in(tz_name)
    print(f"正在送出 warmup prompt（{method}）：{prompt!r}")

    if method == "cli":
        exit_code = send_warmup_cli(prompt, project_path)
    else:
        exit_code = send_warmup_deeplink(prompt, project_path)

    ended_at = usage_planner.now_in(tz_name)

    # Record the warmup session
    usage_planner.append_session(
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
    usage_planner.save_data(data_path, data)

    if exit_code == 0:
        print("✓ Warmup 完成，已記錄到 usage.json。")
    else:
        print(f"⚠ Warmup 結束，exit code {exit_code}，已記錄到 usage.json。")

    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="在高峰時間前送出極低 usage 的 warmup prompt。"
    )
    parser.add_argument(
        "--data",
        help="資料檔路徑",
    )
    parser.add_argument(
        "--method",
        choices=["cli", "deeplink"],
        default="cli",
        help="送出方式：cli 使用 codex exec，deeplink 使用 codex:// App（預設 cli）",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_WARMUP_PROMPT,
        help=f"Warmup prompt 內容（預設 {DEFAULT_WARMUP_PROMPT!r}）",
    )
    parser.add_argument(
        "--project-path",
        default=None,
        help="指定專案路徑",
    )
    parser.add_argument(
        "--lead-minutes",
        type=int,
        default=None,
        help="高峰前幾分鐘執行 warmup（預設使用 setup-lead-minutes 偏好值）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只顯示會做什麼，不實際執行",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="不檢查時間，強制執行 warmup",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    data_path = usage_planner.data_path_from_arg(args.data)
    return run_warmup(
        data_path=data_path,
        method=args.method,
        prompt=args.prompt,
        project_path=args.project_path,
        dry_run=args.dry_run,
        force=args.force,
        warmup_lead_minutes=args.lead_minutes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
