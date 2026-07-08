#!/usr/bin/env python3
"""Local usage planner for Codex and Claude Code.

The tool records real work sessions, learns preferred time windows, and prints
planning suggestions. It deliberately does not automate calls to any external
service or try to consume quota on the user's behalf.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import urllib.parse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


VERSION = 1
SUPPORTED_TOOLS = ("codex", "claude-code")
BUCKET_MINUTES = 30
BUCKETS_PER_DAY = 24 * 60 // BUCKET_MINUTES
DEFAULT_DATA_PATH = Path.cwd() / ".usage_planner" / "usage.json"
DEFAULT_CODEX_LOG_ROOT = Path.home() / ".codex" / "sessions"
DEFAULT_CLAUDE_LOG_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_WARMUP_PROMPT = "ping"
LAUNCHD_LABEL = "com.usage-planner.warmup"
LAUNCHD_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
SCHTASKS_TASK_NAME = "UsagePlannerWarmup"
SCHTASKS_LOG_DIR = Path.home() / ".usage_planner" / "logs"


@dataclass(frozen=True)
class TimeWindow:
    start_minutes: int
    end_minutes: int


@dataclass(frozen=True)
class Suggestion:
    source: str
    confidence: str
    start_minutes: int
    end_minutes: int
    remind_minutes: int
    total_sessions: int
    total_minutes: int
    top_slots: list[tuple[int, int, float]]


@dataclass(frozen=True)
class ReminderOccurrence:
    remind_at: datetime
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class LogEvent:
    timestamp: datetime
    is_prompt: bool
    path: Path


@dataclass(frozen=True)
class InferredSession:
    tool: str
    source: str
    start_at: datetime
    end_at: datetime
    prompt_count: int
    event_count: int
    source_file_count: int


def default_timezone_name() -> str:
    return os.environ.get("TZ") or "Asia/Taipei"


def load_timezone(name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        print(f"找不到時區 {name!r}，改用系統本地時區。", file=sys.stderr)
        return datetime.now().astimezone().tzinfo or timezone.utc


def now_in(tz_name: str) -> datetime:
    return datetime.now(load_timezone(tz_name))


def data_path_from_arg(value: str | None) -> Path:
    raw = value or os.environ.get("USAGE_PLANNER_DATA")
    return Path(raw).expanduser() if raw else DEFAULT_DATA_PATH


def blank_data(tz_name: str | None = None) -> dict[str, Any]:
    tz_name = tz_name or default_timezone_name()
    return {
        "version": VERSION,
        "created_at": now_in(tz_name).isoformat(timespec="seconds"),
        "timezone": tz_name,
        "preferences": {
            "tools": list(SUPPORTED_TOOLS),
            "preferred_windows": [
                {"start": "19:00", "end": "23:00"},
            ],
            "quota_window_minutes": 300,
            "setup_lead_minutes": 210,
        },
        "sessions": [],
    }


def load_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        return blank_data()

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if data.get("version") != VERSION:
        raise SystemExit(f"不支援的資料版本：{data.get('version')}")

    data.setdefault("timezone", default_timezone_name())
    data.setdefault("preferences", {})
    data["preferences"].setdefault("tools", list(SUPPORTED_TOOLS))
    data["preferences"].setdefault("preferred_windows", [])
    data["preferences"].setdefault("quota_window_minutes", 300)
    data["preferences"].setdefault("setup_lead_minutes", 210)
    data.setdefault("sessions", [])
    return data


def save_data(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(path)


def append_session(
    data: dict[str, Any],
    tool: str,
    started_at: datetime,
    ended_at: datetime,
    source: str,
    command: list[str] | None = None,
    exit_code: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    session: dict[str, Any] = {
        "tool": tool,
        "start": started_at.isoformat(timespec="microseconds"),
        "end": ended_at.isoformat(timespec="microseconds"),
        "source": source,
    }
    if command is not None:
        session["command"] = command
    if exit_code is not None:
        session["exit_code"] = exit_code
    if extra:
        session.update(extra)
    data["sessions"].append(session)


def parse_clock(value: str) -> int:
    try:
        hour_text, minute_text = value.strip().split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"時間必須是 HH:MM：{value}") from exc

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise argparse.ArgumentTypeError(f"時間超出範圍：{value}")

    return hour * 60 + minute


def parse_window(value: str) -> TimeWindow:
    try:
        start_text, end_text = value.split("-", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"時段必須是 HH:MM-HH:MM：{value}"
        ) from exc

    start = parse_clock(start_text)
    end = parse_clock(end_text)
    if start == end:
        raise argparse.ArgumentTypeError("偏好時段不能是 0 分鐘。")
    return TimeWindow(start, end)


def parse_datetime(value: str | None, tz_name: str) -> datetime:
    if value is None:
        return now_in(tz_name)

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"時間必須是 ISO 格式，例如 2026-07-06T20:30：{value}"
        ) from exc

    tz = load_timezone(tz_name)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def parse_log_timestamp(value: Any, tz_name: str) -> datetime | None:
    tz = load_timezone(tz_name)
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            return datetime.fromtimestamp(value / 1000, timezone.utc).astimezone(tz)
        return datetime.fromtimestamp(value, timezone.utc).astimezone(tz)
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def format_clock(total_minutes: int) -> str:
    total_minutes %= 24 * 60
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def format_duration(minutes: int) -> str:
    hours, remainder = divmod(int(round(minutes)), 60)
    if hours and remainder:
        return f"{hours} 小時 {remainder} 分鐘"
    if hours:
        return f"{hours} 小時"
    return f"{remainder} 分鐘"


def window_to_dict(window: TimeWindow) -> dict[str, str]:
    return {
        "start": format_clock(window.start_minutes),
        "end": format_clock(window.end_minutes),
    }


def window_from_dict(raw: dict[str, str]) -> TimeWindow:
    return TimeWindow(parse_clock(raw["start"]), parse_clock(raw["end"]))


def bucket_indices_for_window(window: TimeWindow) -> list[int]:
    indices: list[int] = []
    cursor = window.start_minutes
    end = window.end_minutes
    if end <= cursor:
        end += 24 * 60

    while cursor < end:
        indices.append((cursor // BUCKET_MINUTES) % BUCKETS_PER_DAY)
        cursor += BUCKET_MINUTES
    return indices


def session_overlaps_analysis(
    session: dict[str, str],
    start_at: datetime,
    end_at: datetime,
    tz_name: str,
) -> tuple[datetime, datetime] | None:
    session_start = parse_datetime(session["start"], tz_name)
    session_end = parse_datetime(session["end"], tz_name)
    if session_end <= session_start:
        return None

    clipped_start = max(session_start, start_at)
    clipped_end = min(session_end, end_at)
    if clipped_end <= clipped_start:
        return None
    return clipped_start, clipped_end


def add_session_to_profile(profile: list[float], start_at: datetime, end_at: datetime) -> int:
    total_minutes = 0.0
    cursor = start_at
    while cursor < end_at:
        minute_of_day = cursor.hour * 60 + cursor.minute
        next_bucket_minute = ((minute_of_day // BUCKET_MINUTES) + 1) * BUCKET_MINUTES
        if next_bucket_minute >= 24 * 60:
            next_boundary = (cursor + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            next_boundary = cursor.replace(
                hour=next_bucket_minute // 60,
                minute=next_bucket_minute % 60,
                second=0,
                microsecond=0,
            )

        segment_end = min(end_at, next_boundary)
        minutes = max(0.0, (segment_end - cursor).total_seconds() / 60)
        if minutes:
            profile[minute_of_day // BUCKET_MINUTES] += minutes
            total_minutes += minutes
        cursor = segment_end

    return int(round(total_minutes))


def build_profile(
    data: dict[str, Any],
    days: int,
    include_preferences: bool = True,
) -> tuple[list[float], int, int, str]:
    tz_name = data["timezone"]
    end_at = now_in(tz_name)
    start_at = end_at - timedelta(days=days)
    profile = [0.0 for _ in range(BUCKETS_PER_DAY)]
    session_count = 0
    total_minutes = 0

    for session in data["sessions"]:
        overlap = session_overlaps_analysis(session, start_at, end_at, tz_name)
        if overlap is None:
            continue
        session_count += 1
        total_minutes += add_session_to_profile(profile, overlap[0], overlap[1])

    if include_preferences:
        preference_weight = 20.0 if session_count == 0 else 5.0
        for raw_window in data["preferences"].get("preferred_windows", []):
            window = window_from_dict(raw_window)
            for index in bucket_indices_for_window(window):
                profile[index] += preference_weight

    source = "實際使用紀錄" if session_count else "初始偏好"
    return profile, session_count, total_minutes, source


def find_best_block(profile: list[float], window_minutes: int) -> tuple[int, int, float]:
    span = max(1, math.ceil(window_minutes / BUCKET_MINUTES))
    best_start = 0
    best_score = -1.0

    for start_index in range(BUCKETS_PER_DAY):
        score = sum(profile[(start_index + offset) % BUCKETS_PER_DAY] for offset in range(span))
        if score > best_score:
            best_score = score
            best_start = start_index

    start_minutes = best_start * BUCKET_MINUTES
    end_minutes = start_minutes + window_minutes
    return start_minutes, end_minutes, best_score


def top_slots(profile: list[float], count: int = 3) -> list[tuple[int, int, float]]:
    slots: list[tuple[int, int, float]] = []
    for start_index in range(BUCKETS_PER_DAY):
        score = profile[start_index] + profile[(start_index + 1) % BUCKETS_PER_DAY]
        start = start_index * BUCKET_MINUTES
        slots.append((start, start + 60, score))
    slots.sort(key=lambda item: item[2], reverse=True)

    selected: list[tuple[int, int, float]] = []
    used: set[int] = set()
    for start, end, score in slots:
        bucket = start // BUCKET_MINUTES
        if bucket in used or (bucket + 1) % BUCKETS_PER_DAY in used:
            continue
        selected.append((start, end, score))
        used.add(bucket)
        used.add((bucket + 1) % BUCKETS_PER_DAY)
        if len(selected) >= count:
            break
    return selected


def confidence_label(session_count: int, total_minutes: int) -> str:
    if session_count == 0:
        return "冷啟動：目前只根據你輸入的偏好判斷"
    if session_count < 3 or total_minutes < 180:
        return "低：資料還少，建議先累積一週"
    if session_count < 7 or total_minutes < 600:
        return "中：已有一些使用模式"
    return "高：近期使用模式相對穩定"


def make_suggestion(data: dict[str, Any], days: int) -> Suggestion:
    profile, session_count, total_minutes, source = build_profile(data, days)
    window_minutes = int(data["preferences"].get("quota_window_minutes", 300))
    setup_lead = int(data["preferences"].get("setup_lead_minutes", 210))
    start, end, _ = find_best_block(profile, window_minutes)
    remind = start - setup_lead
    return Suggestion(
        source=source,
        confidence=confidence_label(session_count, total_minutes),
        start_minutes=start,
        end_minutes=end,
        remind_minutes=remind,
        total_sessions=session_count,
        total_minutes=total_minutes,
        top_slots=top_slots(profile),
    )


def tuned_windows_from_sessions(
    data: dict[str, Any],
    days: int,
    count: int,
) -> tuple[list[TimeWindow], int, int]:
    profile, session_count, total_minutes, _ = build_profile(
        data,
        days,
        include_preferences=False,
    )
    windows = [
        TimeWindow(start, end)
        for start, end, score in top_slots(profile, count=count)
        if score > 0
    ]
    return windows[:count], session_count, total_minutes


def midnight_for(day: datetime, tz_name: str) -> datetime:
    tz = load_timezone(tz_name)
    return datetime(day.year, day.month, day.day, tzinfo=tz)


def upcoming_reminders(
    data: dict[str, Any],
    analysis_days: int,
    count: int,
    from_at: datetime | None = None,
) -> tuple[Suggestion, list[ReminderOccurrence]]:
    suggestion = make_suggestion(data, analysis_days)
    current = from_at or now_in(data["timezone"])
    current = current.astimezone(load_timezone(data["timezone"]))
    occurrences: list[ReminderOccurrence] = []

    # Include yesterday so a wrapped reminder, such as 23:45 for a 00:00 window,
    # is still considered when it belongs to today's planning window.
    for offset in range(-1, count + 2):
        day = current + timedelta(days=offset)
        midnight = midnight_for(day, data["timezone"])
        remind_at = midnight + timedelta(minutes=suggestion.remind_minutes)
        start_at = midnight + timedelta(minutes=suggestion.start_minutes)
        end_at = midnight + timedelta(minutes=suggestion.end_minutes)
        if remind_at >= current:
            occurrences.append(ReminderOccurrence(remind_at, start_at, end_at))
        if len(occurrences) >= count:
            break

    return suggestion, occurrences


def iter_jsonl(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def is_internal_codex_message(payload: dict[str, Any]) -> bool:
    message = payload.get("message")
    if isinstance(message, str):
        return message.lstrip().startswith("<codex_internal_context")
    if isinstance(message, list):
        for item in message:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.lstrip().startswith("<codex_internal_context"):
                    return True
    return False


def codex_log_events(paths: list[Path], tz_name: str, cutoff: datetime | None) -> list[LogEvent]:
    events: list[LogEvent] = []
    activity_types = {
        "user_message",
        "agent_message",
        "task_started",
        "task_complete",
        "patch_apply_end",
        "token_count",
    }
    response_activity_types = {
        "message",
        "function_call",
        "function_call_output",
        "custom_tool_call",
    }

    for path in paths:
        for obj in iter_jsonl(path):
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue
            ts = parse_log_timestamp(obj.get("timestamp"), tz_name)
            if ts is None or (cutoff is not None and ts < cutoff):
                continue

            payload_type = payload.get("type")
            outer_type = obj.get("type")
            is_prompt = payload_type == "user_message" and not is_internal_codex_message(payload)
            is_activity = payload_type in activity_types
            if outer_type == "response_item" and payload_type in response_activity_types:
                is_activity = True
            if not is_prompt and not is_activity:
                continue
            events.append(LogEvent(ts, is_prompt, path))

    events.sort(key=lambda event: event.timestamp)
    return events


def is_claude_prompt(obj: dict[str, Any]) -> bool:
    message = obj.get("message")
    if obj.get("type") != "user" or not isinstance(message, dict):
        return False
    if message.get("role") != "user":
        return False
    if obj.get("toolUseResult") is not None:
        return False
    if obj.get("isCompactSummary") or obj.get("isVisibleInTranscriptOnly") or obj.get("isMeta"):
        return False
    return True


def claude_log_events(paths: list[Path], tz_name: str, cutoff: datetime | None) -> list[LogEvent]:
    events: list[LogEvent] = []
    activity_types = {"user", "assistant", "system", "attachment"}

    for path in paths:
        for obj in iter_jsonl(path):
            if obj.get("type") not in activity_types:
                continue
            ts = parse_log_timestamp(obj.get("timestamp"), tz_name)
            if ts is None or (cutoff is not None and ts < cutoff):
                continue
            events.append(LogEvent(ts, is_claude_prompt(obj), path))

    events.sort(key=lambda event: event.timestamp)
    return events


def discover_codex_logs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.glob("**/rollout-*.jsonl"))


def discover_claude_logs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.glob("**/*.jsonl")
        if "subagents" not in path.parts
    )


def infer_sessions_from_events(
    events: list[LogEvent],
    tool: str,
    source: str,
    idle_minutes: int,
    tail_minutes: int,
) -> list[InferredSession]:
    idle_delta = timedelta(minutes=idle_minutes)
    tail_delta = timedelta(minutes=tail_minutes)
    sessions: list[InferredSession] = []

    current_start: datetime | None = None
    current_end: datetime | None = None
    prompt_count = 0
    event_count = 0
    source_files: set[Path] = set()

    def close_current() -> None:
        nonlocal current_start, current_end, prompt_count, event_count, source_files
        if current_start is None or current_end is None or prompt_count == 0:
            current_start = None
            current_end = None
            prompt_count = 0
            event_count = 0
            source_files = set()
            return
        if current_end <= current_start:
            current_end = current_start + tail_delta
        sessions.append(
            InferredSession(
                tool=tool,
                source=source,
                start_at=current_start,
                end_at=current_end,
                prompt_count=prompt_count,
                event_count=event_count,
                source_file_count=len(source_files),
            )
        )
        current_start = None
        current_end = None
        prompt_count = 0
        event_count = 0
        source_files = set()

    for event in events:
        if current_end is not None and event.timestamp - current_end > idle_delta:
            close_current()

        if event.is_prompt:
            if current_start is None:
                current_start = event.timestamp
                current_end = event.timestamp + tail_delta
                prompt_count = 0
                event_count = 0
                source_files = set()
            prompt_count += 1
            event_count += 1
            source_files.add(event.path)
            current_end = max(current_end or event.timestamp, event.timestamp + tail_delta)
        elif current_start is not None:
            event_count += 1
            source_files.add(event.path)
            current_end = max(current_end or event.timestamp, event.timestamp)

    close_current()
    return sessions


def import_id_for_session(session: InferredSession, idle_minutes: int, tail_minutes: int) -> str:
    return "|".join(
        [
            session.source,
            session.tool,
            session.start_at.isoformat(timespec="seconds"),
            session.end_at.isoformat(timespec="seconds"),
            str(session.prompt_count),
            str(idle_minutes),
            str(tail_minutes),
        ]
    )


def imported_session_ids(data: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for session in data.get("sessions", []):
        import_id = session.get("import_id")
        if isinstance(import_id, str):
            ids.add(import_id)
    return ids


def append_inferred_session(
    data: dict[str, Any],
    session: InferredSession,
    import_id: str,
    idle_minutes: int,
    tail_minutes: int,
) -> None:
    append_session(
        data,
        session.tool,
        session.start_at,
        session.end_at,
        source=session.source,
        extra={
            "import_id": import_id,
            "prompt_count": session.prompt_count,
            "event_count": session.event_count,
            "source_file_count": session.source_file_count,
            "idle_minutes": idle_minutes,
            "tail_minutes": tail_minutes,
            "inferred": True,
        },
    )


def prompt_csv(prompt: str, default: list[str]) -> list[str]:
    default_text = ",".join(default)
    answer = input(f"{prompt} [{default_text}]: ").strip()
    return [item.strip() for item in (answer or default_text).split(",") if item.strip()]


def prompt_windows(default: list[str]) -> list[TimeWindow]:
    default_text = ",".join(default)
    answer = input(f"常用時段，格式 HH:MM-HH:MM，可用逗號分隔 [{default_text}]: ").strip()
    raw_values = [item.strip() for item in (answer or default_text).split(",") if item.strip()]
    return [parse_window(item) for item in raw_values]


def prompt_int(prompt: str, default: int) -> int:
    answer = input(f"{prompt} [{default}]: ").strip()
    return int(answer or default)


def cmd_init(args: argparse.Namespace) -> int:
    path = data_path_from_arg(args.data)
    data = blank_data(args.timezone or default_timezone_name()) if args.reset else load_data(path)
    data["timezone"] = args.timezone or data.get("timezone") or default_timezone_name()
    prefs = data["preferences"]

    if args.tool:
        tools = args.tool
    elif args.non_interactive:
        tools = prefs.get("tools") or list(SUPPORTED_TOOLS)
    else:
        tools = prompt_csv("要追蹤的工具，可用 codex 或 claude-code", prefs.get("tools") or list(SUPPORTED_TOOLS))

    unknown_tools = sorted(set(tools) - set(SUPPORTED_TOOLS))
    if unknown_tools:
        raise SystemExit(f"不支援的工具：{', '.join(unknown_tools)}")

    if args.preferred_window:
        windows = [parse_window(item) for item in args.preferred_window]
    elif args.non_interactive:
        windows = [window_from_dict(item) for item in prefs.get("preferred_windows", [])]
        if not windows:
            windows = [parse_window("19:00-23:00")]
    else:
        defaults = [
            f"{item['start']}-{item['end']}"
            for item in prefs.get("preferred_windows", [])
        ] or ["19:00-23:00"]
        windows = prompt_windows(defaults)

    prefs["tools"] = list(dict.fromkeys(tools))
    prefs["preferred_windows"] = [window_to_dict(window) for window in windows]
    prefs["quota_window_minutes"] = (
        args.quota_window_minutes
        if args.quota_window_minutes is not None
        else int(prefs.get("quota_window_minutes", 300))
    )
    prefs["setup_lead_minutes"] = (
        args.setup_lead_minutes
        if args.setup_lead_minutes is not None
        else int(prefs.get("setup_lead_minutes", 210))
    )

    if not args.non_interactive and args.quota_window_minutes is None:
        prefs["quota_window_minutes"] = prompt_int("規劃視窗長度（分鐘）", int(prefs["quota_window_minutes"]))
    if not args.non_interactive and args.setup_lead_minutes is None:
        prefs["setup_lead_minutes"] = prompt_int("開始前提醒提前量（分鐘）", int(prefs["setup_lead_minutes"]))

    save_data(path, data)
    print(f"已初始化：{path}")
    print("注意：這個工具只做紀錄與提醒，不會自動消耗任何服務用量。")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    path = data_path_from_arg(args.data)
    data = load_data(path)
    started_at = parse_datetime(args.start, data["timezone"])
    ended_at = parse_datetime(args.end, data["timezone"])
    if ended_at <= started_at:
        raise SystemExit("結束時間必須晚於開始時間。")

    append_session(data, args.tool, started_at, ended_at, source="manual")
    save_data(path, data)
    duration = int((ended_at - started_at).total_seconds() // 60)
    print(f"已新增 {args.tool} 使用紀錄：{format_duration(duration)}")
    return 0


def cmd_wrap(args: argparse.Namespace) -> int:
    path = data_path_from_arg(args.data)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("wrap 需要指定要執行的命令，例如：wrap codex -- codex")

    data = load_data(path)
    started_at = now_in(data["timezone"])
    print(f"開始執行並記錄 {args.tool}: {shlex.join(command)}", flush=True)
    try:
        completed = subprocess.run(command, check=False)
    except FileNotFoundError:
        print(f"找不到命令：{command[0]}", file=sys.stderr)
        return 127
    ended_at = now_in(data["timezone"])

    append_session(
        data,
        args.tool,
        started_at,
        ended_at,
        source="wrap",
        command=command,
        exit_code=completed.returncode,
    )
    save_data(path, data)

    duration = int((ended_at - started_at).total_seconds() // 60)
    print(
        f"已記錄 {args.tool} 使用時間：{format_duration(duration)}，"
        f"exit code {completed.returncode}"
    )
    return completed.returncode


def cmd_import_logs(args: argparse.Namespace) -> int:
    path = data_path_from_arg(args.data)
    data = load_data(path)
    tools = args.tool or list(SUPPORTED_TOOLS)
    cutoff = None
    if not args.all:
        cutoff = now_in(data["timezone"]) - timedelta(days=args.days)

    inferred: list[InferredSession] = []
    scanned_files: dict[str, int] = {}
    prompt_records: dict[str, int] = {}

    if "codex" in tools:
        codex_paths = discover_codex_logs(Path(args.codex_root).expanduser())
        codex_events = codex_log_events(codex_paths, data["timezone"], cutoff)
        scanned_files["codex"] = len(codex_paths)
        prompt_records["codex"] = sum(1 for event in codex_events if event.is_prompt)
        inferred.extend(
            infer_sessions_from_events(
                codex_events,
                tool="codex",
                source="codex-log",
                idle_minutes=args.idle_minutes,
                tail_minutes=args.tail_minutes,
            )
        )

    if "claude-code" in tools:
        claude_paths = discover_claude_logs(Path(args.claude_root).expanduser())
        claude_events = claude_log_events(claude_paths, data["timezone"], cutoff)
        scanned_files["claude-code"] = len(claude_paths)
        prompt_records["claude-code"] = sum(1 for event in claude_events if event.is_prompt)
        inferred.extend(
            infer_sessions_from_events(
                claude_events,
                tool="claude-code",
                source="claude-log",
                idle_minutes=args.idle_minutes,
                tail_minutes=args.tail_minutes,
            )
        )

    known_ids = imported_session_ids(data)
    added = 0
    duplicates = 0
    by_tool: dict[str, int] = {}

    for session in inferred:
        import_id = import_id_for_session(session, args.idle_minutes, args.tail_minutes)
        if import_id in known_ids:
            duplicates += 1
            continue
        by_tool[session.tool] = by_tool.get(session.tool, 0) + 1
        if not args.dry_run:
            append_inferred_session(
                data,
                session,
                import_id,
                idle_minutes=args.idle_minutes,
                tail_minutes=args.tail_minutes,
            )
            known_ids.add(import_id)
        added += 1

    if not args.dry_run:
        save_data(path, data)

    scope = "全部歷史" if args.all else f"最近 {args.days} 天"
    print(f"匯入範圍：{scope}")
    for tool in tools:
        print(
            f"- {tool}: 掃描 {scanned_files.get(tool, 0)} 個檔案，"
            f"{prompt_records.get(tool, 0)} 筆 prompt，"
            f"新增 {by_tool.get(tool, 0)} 段"
        )
    if duplicates:
        print(f"略過重複 session：{duplicates} 段")
    if args.dry_run:
        print("dry-run：未寫入資料檔。")
    else:
        print(f"已寫入資料檔：{path}")
    print("注意：匯入只保存推估時間、來源與計數，不保存 prompt 文字。")
    return 0


def print_suggestion(suggestion: Suggestion, days: int) -> None:
    print(f"分析範圍：最近 {days} 天")
    print(f"資料來源：{suggestion.source}")
    print(f"信心：{suggestion.confidence}")
    print(f"紀錄：{suggestion.total_sessions} 筆，合計 {format_duration(suggestion.total_minutes)}")
    print()
    print("建議規劃：")
    print(f"- 主要使用視窗：{format_clock(suggestion.start_minutes)}-{format_clock(suggestion.end_minutes)}")
    print(f"- 提醒時間：{format_clock(suggestion.remind_minutes)}")
    print("- 行動：在提醒時間檢查當天工作安排與可用用量；程式不會自動消耗 usage。")
    if suggestion.top_slots:
        print()
        print("近期高峰時段：")
        for start, end, _ in suggestion.top_slots:
            print(f"- {format_clock(start)}-{format_clock(end)}")


def format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M %Z")


def cmd_suggest(args: argparse.Namespace) -> int:
    data = load_data(data_path_from_arg(args.data))
    suggestion = make_suggestion(data, args.days)
    print_suggestion(suggestion, args.days)
    return 0


def cmd_reminders(args: argparse.Namespace) -> int:
    data = load_data(data_path_from_arg(args.data))
    from_at = parse_datetime(args.at, data["timezone"]) if args.at else None
    suggestion, occurrences = upcoming_reminders(
        data,
        analysis_days=args.analysis_days,
        count=args.count,
        from_at=from_at,
    )

    print(f"分析範圍：最近 {args.analysis_days} 天")
    print(f"資料來源：{suggestion.source}")
    print(f"信心：{suggestion.confidence}")
    print("提醒排程：")
    if not occurrences:
        print("- 尚無可列出的提醒")
    for occurrence in occurrences:
        print(
            "- "
            f"{format_datetime(occurrence.remind_at)} "
            f"| 建議工作視窗 {format_datetime(occurrence.start_at)}"
            f"-{occurrence.end_at.strftime('%H:%M %Z')}"
        )
    print("注意：這些是本地規劃提醒，不會自動消耗任何 usage。")
    return 0


def cmd_tune(args: argparse.Namespace) -> int:
    path = data_path_from_arg(args.data)
    data = load_data(path)
    windows, session_count, total_minutes = tuned_windows_from_sessions(
        data,
        days=args.days,
        count=args.windows,
    )

    enough_data = session_count >= args.min_sessions and total_minutes >= args.min_minutes
    if not windows:
        print("最近資料內沒有可用的 session，偏好未更新。")
        return 0
    if not enough_data and not args.force:
        print(
            "資料量還不足，偏好未更新："
            f"{session_count} 筆 / {format_duration(total_minutes)}。"
        )
        print(
            f"門檻：至少 {args.min_sessions} 筆且 {format_duration(args.min_minutes)}。"
            "可加上 --force 強制用目前資料調整。"
        )
        return 0

    old_windows = [
        f"{item['start']}-{item['end']}"
        for item in data["preferences"].get("preferred_windows", [])
    ]
    new_windows = [window_to_dict(window) for window in windows]
    data["preferences"]["preferred_windows"] = new_windows
    save_data(path, data)

    print(f"已根據最近 {args.days} 天實際使用紀錄更新偏好。")
    print(f"資料：{session_count} 筆，合計 {format_duration(total_minutes)}")
    print(f"原偏好：{', '.join(old_windows) if old_windows else '無'}")
    print(
        "新偏好："
        + ", ".join(f"{item['start']}-{item['end']}" for item in new_windows)
    )
    return 0


def send_notification(title: str, message: str) -> None:
    """Send a desktop notification. Works on macOS and Windows."""
    try:
        if sys.platform == "darwin":
            script = (
                f'display notification "{message}" '
                f'with title "{title}"'
            )
            subprocess.run(
                ["osascript", "-e", script],
                check=False,
                timeout=10,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "win32":
            # Use PowerShell BalloonTip notification (works without extra modules)
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $true; "
                f"$n.ShowBalloonTip(5000, '{title}', '{message}', "
                "[System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep -Seconds 3; "
                "$n.Dispose()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                check=False,
                timeout=15,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


# Backward compatibility alias
send_macos_notification = send_notification


def send_warmup_cli(
    prompt: str,
    project_path: str | None = None,
) -> int:
    """Execute a warmup prompt via ``codex exec``."""
    command = ["codex"]
    if project_path:
        command += ["--path", project_path]
    command += ["exec", "--ephemeral", prompt]

    try:
        result = subprocess.run(
            command,
            check=False,
            timeout=120,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode
    except FileNotFoundError:
        print(
            "錯誤：找不到 codex 命令。請安裝 Codex CLI 或改用 --method deeplink。",
            file=sys.stderr,
        )
        return 127
    except subprocess.TimeoutExpired:
        print("警告：codex exec 超時（120 秒），已中斷。", file=sys.stderr)
        return 124


def send_warmup_deeplink(
    prompt: str,
    project_path: str | None = None,
) -> int:
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
    data: dict[str, Any],
    warmup_lead_minutes: int,
    tolerance_minutes: int = 10,
    days: int = 7,
) -> tuple[bool, str, datetime | None]:
    """Check if now is the right time to send a warmup prompt.

    Returns ``(should_fire, reason, peak_start)``.
    """
    suggestion = make_suggestion(data, days=days)
    tz_name = data["timezone"]
    current = now_in(tz_name)
    tz = load_timezone(tz_name)

    for offset in range(2):
        day = current + timedelta(days=offset)
        midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
        peak_start = midnight + timedelta(minutes=suggestion.start_minutes)
        warmup_time = peak_start - timedelta(minutes=warmup_lead_minutes)

        delta = abs((current - warmup_time).total_seconds()) / 60
        if delta <= tolerance_minutes:
            return (
                True,
                f"距離高峰 {format_clock(suggestion.start_minutes)} 還有 {warmup_lead_minutes} 分鐘",
                peak_start,
            )

    return False, "目前不在 warmup 時間範圍內", None


def cmd_warmup(args: argparse.Namespace) -> int:
    """Send a minimal-usage warmup prompt before the peak window."""
    path = data_path_from_arg(args.data)
    data = load_data(path)
    tz_name = data["timezone"]
    lead_minutes = args.lead_minutes
    if lead_minutes is None:
        lead_minutes = int(data["preferences"].get("setup_lead_minutes", 210))

    if not args.force:
        should_fire, reason, _ = should_warmup_now(
            data, lead_minutes, tolerance_minutes=args.tolerance_minutes, days=args.days
        )
        if not should_fire:
            print(f"跳過 warmup：{reason}")
            return 0
        print(f"Warmup 時間到：{reason}")
    else:
        print(f"強制執行 warmup（--force），提前量 {lead_minutes} 分鐘")

    if args.dry_run:
        print(f"[dry-run] 會使用 {args.method} 模式送出 prompt：{args.prompt!r}")
        if args.project_path:
            print(f"[dry-run] 專案路徑：{args.project_path}")
        print("[dry-run] 不會實際執行。")
        return 0

    started_at = now_in(tz_name)
    print(f"正在送出 warmup prompt（{args.method}）：{args.prompt!r}")

    if args.method == "cli":
        exit_code = send_warmup_cli(args.prompt, args.project_path)
    else:
        exit_code = send_warmup_deeplink(args.prompt, args.project_path)

    ended_at = now_in(tz_name)

    append_session(
        data,
        "codex",
        started_at,
        ended_at,
        source="auto-warmup",
        extra={
            "warmup_method": args.method,
            "warmup_prompt": args.prompt,
            "exit_code": exit_code,
        },
    )
    save_data(path, data)

    if exit_code == 0:
        print("✓ Warmup 完成，已記錄到 usage.json。")
        send_notification("Usage Planner", "✓ Warmup 完成，已記錄到 usage.json。")
    else:
        print(f"⚠ Warmup 結束，exit code {exit_code}，已記錄到 usage.json。")
        send_notification("Usage Planner", f"⚠ Warmup 結束，exit code {exit_code}。")
    print("注意：warmup 會消耗少量 usage。")
    return exit_code


def generate_launchd_plist(
    data: dict[str, Any],
    method: str,
    prompt: str,
    lead_minutes: int | None = None,
    project_path: str | None = None,
    days: int = 7,
) -> tuple[str, int, int]:
    """Generate a macOS launchd plist for daily warmup.

    Returns ``(plist_xml, hour, minute)``.
    """
    if lead_minutes is None:
        lead_minutes = int(data["preferences"].get("setup_lead_minutes", 210))
    suggestion = make_suggestion(data, days=days)
    warmup_minutes = suggestion.start_minutes - lead_minutes
    warmup_minutes %= 24 * 60
    hour = warmup_minutes // 60
    minute = warmup_minutes % 60

    python = sys.executable
    script = str(Path(__file__).resolve())

    program_args = [
        python, script, "warmup",
        "--method", method,
        "--prompt", prompt,
        "--lead-minutes", str(lead_minutes),
        "--days", str(days),
        "--force",
    ]
    if project_path:
        program_args += ["--project-path", project_path]

    args_xml = "\n".join(f"        <string>{arg}</string>" for arg in program_args)

    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
        '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{LAUNCHD_LABEL}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"{args_xml}\n"
        "    </array>\n"
        "    <key>WorkingDirectory</key>\n"
        f"    <string>{Path(__file__).parent.resolve()}</string>\n"
        "    <key>EnvironmentVariables</key>\n"
        "    <dict>\n"
        "        <key>PATH</key>\n"
        f"        <string>{os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin')}</string>\n"
        "    </dict>\n"
        "    <key>StartCalendarInterval</key>\n"
        "    <dict>\n"
        "        <key>Hour</key>\n"
        f"        <integer>{hour}</integer>\n"
        "        <key>Minute</key>\n"
        f"        <integer>{minute}</integer>\n"
        "    </dict>\n"
        "    <key>StandardOutPath</key>\n"
        f"    <string>/tmp/{LAUNCHD_LABEL}.out.log</string>\n"
        "    <key>StandardErrorPath</key>\n"
        f"    <string>/tmp/{LAUNCHD_LABEL}.err.log</string>\n"
        "</dict>\n"
        "</plist>\n"
    )
    return plist, hour, minute


def _compute_warmup_time(
    data: dict[str, Any],
    lead_minutes: int | None,
    days: int,
) -> tuple[int, int]:
    """Return ``(hour, minute)`` for the daily warmup schedule."""
    if lead_minutes is None:
        lead_minutes = int(data["preferences"].get("setup_lead_minutes", 210))
    suggestion = make_suggestion(data, days=days)
    warmup_minutes = suggestion.start_minutes - lead_minutes
    warmup_minutes %= 24 * 60
    return warmup_minutes // 60, warmup_minutes % 60


def install_schedule_darwin(
    data: dict[str, Any],
    method: str,
    prompt: str,
    lead_minutes: int | None,
    project_path: str | None,
    days: int,
    dry_run: bool,
) -> int:
    """Install or display a macOS launchd warmup schedule."""
    plist_path = LAUNCHD_PLIST_PATH
    plist_content, hour, minute = generate_launchd_plist(
        data,
        method=method,
        prompt=prompt,
        lead_minutes=lead_minutes,
        project_path=project_path,
        days=days,
    )

    if dry_run:
        print(f"[dry-run] 會在 {plist_path} 建立排程")
        print(f"[dry-run] 每日 {hour:02d}:{minute:02d} 執行 warmup")
        print(f"[dry-run] plist 內容：")
        print(plist_content)
        return 0

    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content, encoding="utf-8")

    result = subprocess.run(["launchctl", "load", str(plist_path)], check=False)
    if result.returncode == 0:
        print(f"✓ 已安裝 warmup 排程：每日 {hour:02d}:{minute:02d}")
        print(f"  plist 位置：{plist_path}")
        print(f"  log 位置：/tmp/{LAUNCHD_LABEL}.out.log")
        print("注意：warmup 排程會在指定時間自動送出 prompt，會消耗少量 usage。")
    else:
        print(f"錯誤：launchctl load 失敗，exit code {result.returncode}", file=sys.stderr)
    return result.returncode


def uninstall_schedule_darwin() -> tuple[bool, str]:
    """Remove a macOS launchd warmup schedule. Returns ``(removed, message)``."""
    plist_path = LAUNCHD_PLIST_PATH
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink()
        return True, f"已移除排程：{plist_path}"
    return False, "排程檔不存在，無需移除。"


def install_schedule_windows(
    data: dict[str, Any],
    method: str,
    prompt: str,
    lead_minutes: int | None,
    project_path: str | None,
    days: int,
    dry_run: bool,
) -> int:
    """Install a Windows Task Scheduler warmup schedule."""
    hour, minute = _compute_warmup_time(data, lead_minutes, days)

    python = sys.executable
    script = str(Path(__file__).resolve())
    log_dir = SCHTASKS_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    out_log = log_dir / "warmup.out.log"
    err_log = log_dir / "warmup.err.log"

    warmup_args = [
        python, script, "warmup",
        "--method", method,
        "--prompt", prompt,
        "--lead-minutes", str(lead_minutes or int(data["preferences"].get("setup_lead_minutes", 210))),
        "--days", str(days),
        "--force",
    ]
    if project_path:
        warmup_args += ["--project-path", project_path]

    # Build a cmd /c command that redirects stdout/stderr to log files
    inner_cmd = subprocess.list2cmdline(warmup_args)
    task_cmd = f'cmd /c "{inner_cmd} > "{out_log}" 2> "{err_log}""'

    if dry_run:
        print(f"[dry-run] 會建立 Windows 排程任務：{SCHTASKS_TASK_NAME}")
        print(f"[dry-run] 每日 {hour:02d}:{minute:02d} 執行 warmup")
        print(f"[dry-run] 命令：{task_cmd}")
        return 0

    # Remove existing task first (ignore errors if it doesn't exist)
    subprocess.run(
        ["schtasks", "/Delete", "/TN", SCHTASKS_TASK_NAME, "/F"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    result = subprocess.run(
        [
            "schtasks", "/Create",
            "/TN", SCHTASKS_TASK_NAME,
            "/TR", task_cmd,
            "/SC", "DAILY",
            "/ST", f"{hour:02d}:{minute:02d}",
            "/F",
        ],
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        print(f"✓ 已安裝 warmup 排程：每日 {hour:02d}:{minute:02d}")
        print(f"  任務名稱：{SCHTASKS_TASK_NAME}")
        print(f"  log 位置：{out_log}")
        print("注意：warmup 排程會在指定時間自動送出 prompt，會消耗少量 usage。")
    else:
        print(f"錯誤：schtasks /Create 失敗，exit code {result.returncode}", file=sys.stderr)
    return result.returncode


def uninstall_schedule_windows() -> tuple[bool, str]:
    """Remove a Windows Task Scheduler warmup schedule. Returns ``(removed, message)``."""
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", SCHTASKS_TASK_NAME],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return False, "排程任務不存在，無需移除。"
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", SCHTASKS_TASK_NAME, "/F"],
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        return True, f"已移除排程任務：{SCHTASKS_TASK_NAME}"
    return False, f"移除排程任務失敗，exit code {result.returncode}"


def cmd_schedule_warmup(args: argparse.Namespace) -> int:
    """Install or remove a daily warmup schedule (macOS launchd / Windows Task Scheduler)."""
    if sys.platform not in ("darwin", "win32"):
        print("錯誤：schedule-warmup 目前只支援 macOS 和 Windows。", file=sys.stderr)
        return 1

    if args.uninstall:
        if sys.platform == "darwin":
            removed, msg = uninstall_schedule_darwin()
        else:
            removed, msg = uninstall_schedule_windows()
        print(msg)
        return 0

    path = data_path_from_arg(args.data)
    data = load_data(path)

    if sys.platform == "darwin":
        return install_schedule_darwin(
            data, args.method, args.prompt, args.lead_minutes,
            args.project_path, args.days, args.dry_run,
        )
    else:
        return install_schedule_windows(
            data, args.method, args.prompt, args.lead_minutes,
            args.project_path, args.days, args.dry_run,
        )


def cmd_report(args: argparse.Namespace) -> int:
    path = data_path_from_arg(args.data)
    data = load_data(path)
    suggestion = make_suggestion(data, args.days)
    print(f"資料檔：{path}")
    print(f"時區：{data['timezone']}")
    print()

    tool_totals: dict[str, int] = {}
    tz_name = data["timezone"]
    end_at = now_in(tz_name)
    start_at = end_at - timedelta(days=args.days)
    for session in data["sessions"]:
        overlap = session_overlaps_analysis(session, start_at, end_at, tz_name)
        if overlap is None:
            continue
        minutes = int(round((overlap[1] - overlap[0]).total_seconds() / 60))
        tool_totals[session["tool"]] = tool_totals.get(session["tool"], 0) + minutes

    print(f"最近 {args.days} 天工具用量：")
    if tool_totals:
        for tool, minutes in sorted(tool_totals.items()):
            print(f"- {tool}: {format_duration(minutes)}")
    else:
        print("- 尚無紀錄")
    print()
    print_suggestion(suggestion, args.days)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="本地 Codex/Claude Code 使用時段追蹤與提醒工具。"
    )
    parser.add_argument(
        "--data",
        help=f"資料檔路徑，預設為 {DEFAULT_DATA_PATH}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="建立或更新偏好設定")
    init_parser.add_argument("--tool", action="append", choices=SUPPORTED_TOOLS)
    init_parser.add_argument(
        "--preferred-window",
        action="append",
        help="常用時段，格式 HH:MM-HH:MM；可重複指定",
    )
    init_parser.add_argument("--timezone", default=None, help="IANA 時區，例如 Asia/Taipei")
    init_parser.add_argument("--quota-window-minutes", type=int, default=None)
    init_parser.add_argument("--setup-lead-minutes", type=int, default=None)
    init_parser.add_argument("--non-interactive", action="store_true")
    init_parser.add_argument("--reset", action="store_true", help="重新建立資料檔中的設定")
    init_parser.set_defaults(func=cmd_init)

    add_parser = subparsers.add_parser("add", help="手動補上一筆使用紀錄")
    add_parser.add_argument("tool", choices=SUPPORTED_TOOLS)
    add_parser.add_argument("--start", required=True)
    add_parser.add_argument("--end", required=True)
    add_parser.set_defaults(func=cmd_add)

    wrap_parser = subparsers.add_parser("wrap", help="執行命令並自動記錄實際使用時間")
    wrap_parser.add_argument("tool", choices=SUPPORTED_TOOLS)
    wrap_parser.add_argument("command", nargs=argparse.REMAINDER)
    wrap_parser.set_defaults(func=cmd_wrap)

    import_parser = subparsers.add_parser("import-logs", help="從 Codex/Claude Code 本機 log 匯入推估使用時間")
    import_parser.add_argument("--tool", action="append", choices=SUPPORTED_TOOLS)
    import_parser.add_argument("--days", type=int, default=7, help="只匯入最近幾天；預設 7")
    import_parser.add_argument("--all", action="store_true", help="匯入全部歷史 log")
    import_parser.add_argument("--idle-minutes", type=int, default=45, help="活動間隔超過此值就切成新 session")
    import_parser.add_argument("--tail-minutes", type=int, default=15, help="最後一次 prompt 後補上的結束緩衝")
    import_parser.add_argument("--codex-root", default=str(DEFAULT_CODEX_LOG_ROOT))
    import_parser.add_argument("--claude-root", default=str(DEFAULT_CLAUDE_LOG_ROOT))
    import_parser.add_argument("--dry-run", action="store_true", help="只顯示會匯入多少，不寫入資料")
    import_parser.set_defaults(func=cmd_import_logs)

    report_parser = subparsers.add_parser("report", help="顯示用量摘要與建議")
    report_parser.add_argument("--days", type=int, default=7)
    report_parser.set_defaults(func=cmd_report)

    suggest_parser = subparsers.add_parser("suggest", help="只顯示建議使用視窗")
    suggest_parser.add_argument("--days", type=int, default=7)
    suggest_parser.set_defaults(func=cmd_suggest)

    reminders_parser = subparsers.add_parser("reminders", help="列出接下來的本地提醒排程")
    reminders_parser.add_argument("--analysis-days", type=int, default=7)
    reminders_parser.add_argument("--count", type=int, default=7)
    reminders_parser.add_argument("--at", help="從指定時間之後開始列出，預設現在")
    reminders_parser.set_defaults(func=cmd_reminders)

    tune_parser = subparsers.add_parser("tune", help="用實際使用紀錄微調偏好時段")
    tune_parser.add_argument("--days", type=int, default=7)
    tune_parser.add_argument("--windows", type=int, default=2)
    tune_parser.add_argument("--min-sessions", type=int, default=3)
    tune_parser.add_argument("--min-minutes", type=int, default=180)
    tune_parser.add_argument("--force", action="store_true")
    tune_parser.set_defaults(func=cmd_tune)

    warmup_parser = subparsers.add_parser(
        "warmup",
        help="在高峰前送出極低 usage 的 warmup prompt（會消耗少量 usage）",
    )
    warmup_parser.add_argument(
        "--method",
        choices=["cli", "deeplink"],
        default="cli",
        help="送出方式：cli 使用 codex exec，deeplink 使用 codex:// App（預設 cli）",
    )
    warmup_parser.add_argument(
        "--prompt",
        default=DEFAULT_WARMUP_PROMPT,
        help=f"Warmup prompt 內容（預設 {DEFAULT_WARMUP_PROMPT!r}）",
    )
    warmup_parser.add_argument(
        "--project-path",
        default=None,
        help="指定專案路徑",
    )
    warmup_parser.add_argument(
        "--lead-minutes",
        type=int,
        default=None,
        help="高峰前幾分鐘執行 warmup（預設使用 setup-lead-minutes 偏好值）",
    )
    warmup_parser.add_argument(
        "--tolerance-minutes",
        type=int,
        default=10,
        help="判斷是否在 warmup 時間範圍內的容忍分鐘數（預設 10）",
    )
    warmup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只顯示會做什麼，不實際執行",
    )
    warmup_parser.add_argument(
        "--force",
        action="store_true",
        help="不檢查時間，強制執行 warmup",
    )
    warmup_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="計算高峰時間的歷史天數（預設 7）",
    )
    warmup_parser.set_defaults(func=cmd_warmup)

    schedule_parser = subparsers.add_parser(
        "schedule-warmup",
        help="安裝或移除每日 warmup 排程（macOS launchd / Windows Task Scheduler，會消耗少量 usage）",
    )
    schedule_parser.add_argument(
        "--method",
        choices=["cli", "deeplink"],
        default="cli",
        help="送出方式（預設 cli）",
    )
    schedule_parser.add_argument(
        "--prompt",
        default=DEFAULT_WARMUP_PROMPT,
        help=f"Warmup prompt 內容（預設 {DEFAULT_WARMUP_PROMPT!r}）",
    )
    schedule_parser.add_argument(
        "--project-path",
        default=None,
        help="指定專案路徑",
    )
    schedule_parser.add_argument(
        "--lead-minutes",
        type=int,
        default=None,
        help="高峰前幾分鐘執行 warmup（預設使用 setup-lead-minutes 偏好值）",
    )
    schedule_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只顯示 plist 內容，不安裝",
    )
    schedule_parser.add_argument(
        "--uninstall",
        action="store_true",
        help="移除已安裝的排程",
    )
    schedule_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="計算高峰時間的歷史天數（預設 7）",
    )
    schedule_parser.set_defaults(func=cmd_schedule_warmup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if hasattr(args, "days") and args.days <= 0:
        raise SystemExit("--days 必須大於 0。")
    if hasattr(args, "analysis_days") and args.analysis_days <= 0:
        raise SystemExit("--analysis-days 必須大於 0。")
    if hasattr(args, "count") and args.count <= 0:
        raise SystemExit("--count 必須大於 0。")
    if hasattr(args, "windows") and args.windows <= 0:
        raise SystemExit("--windows 必須大於 0。")
    if hasattr(args, "min_sessions") and args.min_sessions < 0:
        raise SystemExit("--min-sessions 必須大於等於 0。")
    if hasattr(args, "min_minutes") and args.min_minutes < 0:
        raise SystemExit("--min-minutes 必須大於等於 0。")
    if hasattr(args, "idle_minutes") and args.idle_minutes <= 0:
        raise SystemExit("--idle-minutes 必須大於 0。")
    if hasattr(args, "tail_minutes") and args.tail_minutes < 0:
        raise SystemExit("--tail-minutes 必須大於等於 0。")
    if hasattr(args, "quota_window_minutes") and args.quota_window_minutes is not None:
        if args.quota_window_minutes <= 0 or args.quota_window_minutes > 24 * 60:
            raise SystemExit("--quota-window-minutes 必須介於 1 到 1440。")
    if hasattr(args, "setup_lead_minutes") and args.setup_lead_minutes is not None:
        if args.setup_lead_minutes < 0 or args.setup_lead_minutes > 24 * 60:
            raise SystemExit("--setup-lead-minutes 必須介於 0 到 1440。")

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
