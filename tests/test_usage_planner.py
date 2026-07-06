import json
import argparse
import tempfile
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import usage_planner


class UsagePlannerTests(unittest.TestCase):
    def run_cli(self, args):
        with redirect_stdout(StringIO()):
            return usage_planner.main(args)

    def test_parse_window(self):
        window = usage_planner.parse_window("19:30-23:00")
        self.assertEqual(window.start_minutes, 19 * 60 + 30)
        self.assertEqual(window.end_minutes, 23 * 60)

    def test_active_timer_commands_are_not_registered(self):
        parser = usage_planner.build_parser()
        subparsers = [
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ][0]

        self.assertNotIn("start", subparsers.choices)
        self.assertNotIn("stop", subparsers.choices)
        self.assertNotIn("status", subparsers.choices)

    def test_suggestion_uses_preferences_without_sessions(self):
        data = usage_planner.blank_data("Asia/Taipei")
        data["preferences"]["preferred_windows"] = [
            {"start": "20:00", "end": "23:00"},
        ]

        suggestion = usage_planner.make_suggestion(data, days=7)

        self.assertEqual(suggestion.source, "初始偏好")
        self.assertIn("冷啟動", suggestion.confidence)
        self.assertLessEqual(suggestion.start_minutes, 20 * 60)
        self.assertGreaterEqual(suggestion.end_minutes, 23 * 60)

    def test_cli_add_and_report_with_custom_data_file(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "usage.json"

            init_code = self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "init",
                    "--non-interactive",
                    "--timezone",
                    "Asia/Taipei",
                    "--preferred-window",
                    "19:00-23:00",
                ]
            )
            self.assertEqual(init_code, 0)

            add_code = self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "add",
                    "codex",
                    "--start",
                    "2026-07-06T20:00",
                    "--end",
                    "2026-07-06T22:00",
                ]
            )
            self.assertEqual(add_code, 0)

            data = usage_planner.load_data(data_path)
            self.assertEqual(len(data["sessions"]), 1)
            self.assertEqual(data["sessions"][0]["tool"], "codex")

    def test_init_allows_zero_setup_lead(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "usage.json"

            self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "init",
                    "--non-interactive",
                    "--timezone",
                    "Asia/Taipei",
                    "--setup-lead-minutes",
                    "0",
                ]
            )

            data = usage_planner.load_data(data_path)
            self.assertEqual(data["preferences"]["setup_lead_minutes"], 0)

    def test_upcoming_reminders_use_setup_lead(self):
        data = usage_planner.blank_data("Asia/Taipei")
        data["preferences"]["preferred_windows"] = [
            {"start": "20:00", "end": "21:00"},
        ]
        data["preferences"]["quota_window_minutes"] = 60
        data["preferences"]["setup_lead_minutes"] = 15
        from_at = usage_planner.parse_datetime("2026-07-06T19:00", data["timezone"])

        _, reminders = usage_planner.upcoming_reminders(
            data,
            analysis_days=7,
            count=1,
            from_at=from_at,
        )

        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0].remind_at.strftime("%H:%M"), "19:45")
        self.assertEqual(reminders[0].start_at.strftime("%H:%M"), "20:00")
        self.assertEqual(reminders[0].end_at.strftime("%H:%M"), "21:00")

    def test_tuned_windows_use_sessions_without_preference_bias(self):
        data = usage_planner.blank_data("Asia/Taipei")
        data["preferences"]["preferred_windows"] = [
            {"start": "20:00", "end": "21:00"},
        ]
        current = usage_planner.now_in(data["timezone"])
        session_day = (current - timedelta(days=1)).date()

        for offset in range(3):
            day = session_day - timedelta(days=offset)
            start = datetime(day.year, day.month, day.day, 9, 0)
            end = datetime(day.year, day.month, day.day, 10, 0)
            data["sessions"].append(
                {
                    "tool": "codex",
                    "start": start.isoformat(timespec="minutes"),
                    "end": end.isoformat(timespec="minutes"),
                }
            )

        windows, session_count, total_minutes = usage_planner.tuned_windows_from_sessions(
            data,
            days=7,
            count=1,
        )

        self.assertEqual(session_count, 3)
        self.assertEqual(total_minutes, 180)
        self.assertEqual(windows[0].start_minutes, 9 * 60)
        self.assertEqual(windows[0].end_minutes, 10 * 60)

    def test_wrap_records_command_and_returns_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "usage.json"
            self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "init",
                    "--non-interactive",
                    "--timezone",
                    "Asia/Taipei",
                ]
            )

            exit_code = self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "wrap",
                    "codex",
                    "--",
                    sys.executable,
                    "-c",
                    "import sys; sys.exit(7)",
                ]
            )

            data = usage_planner.load_data(data_path)
            self.assertEqual(exit_code, 7)
            self.assertEqual(len(data["sessions"]), 1)
            self.assertEqual(data["sessions"][0]["source"], "wrap")
            self.assertEqual(data["sessions"][0]["exit_code"], 7)
            self.assertEqual(data["sessions"][0]["command"][0], sys.executable)

    def test_import_logs_infers_sessions_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "usage.json"
            codex_root = root / "codex-sessions"
            claude_root = root / "claude-projects"
            codex_file = codex_root / "2026" / "07" / "06" / "rollout-test.jsonl"
            claude_file = claude_root / "project-a" / "session-a.jsonl"
            codex_file.parent.mkdir(parents=True)
            claude_file.parent.mkdir(parents=True)

            codex_lines = [
                {
                    "timestamp": "2026-07-06T04:00:00.000Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "codex secret prompt"},
                },
                {
                    "timestamp": "2026-07-06T04:05:00.000Z",
                    "type": "event_msg",
                    "payload": {"type": "task_complete"},
                },
                {
                    "timestamp": "2026-07-06T04:20:00.000Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "codex second secret"},
                },
            ]
            claude_lines = [
                {
                    "timestamp": "2026-07-06T05:00:00.000Z",
                    "type": "user",
                    "message": {"role": "user", "content": "claude secret prompt"},
                },
                {
                    "timestamp": "2026-07-06T05:03:00.000Z",
                    "type": "user",
                    "message": {"role": "user", "content": "tool result should not count"},
                    "toolUseResult": {"ok": True},
                },
                {
                    "timestamp": "2026-07-06T05:08:00.000Z",
                    "type": "assistant",
                    "message": {"role": "assistant", "content": "done"},
                },
            ]
            codex_file.write_text(
                "\n".join(json.dumps(item) for item in codex_lines) + "\n",
                encoding="utf-8",
            )
            claude_file.write_text(
                "\n".join(json.dumps(item) for item in claude_lines) + "\n",
                encoding="utf-8",
            )

            self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "init",
                    "--non-interactive",
                    "--timezone",
                    "Asia/Taipei",
                ]
            )
            import_args = [
                "--data",
                str(data_path),
                "import-logs",
                "--all",
                "--codex-root",
                str(codex_root),
                "--claude-root",
                str(claude_root),
                "--idle-minutes",
                "45",
                "--tail-minutes",
                "15",
            ]

            self.assertEqual(self.run_cli(import_args), 0)
            self.assertEqual(self.run_cli(import_args), 0)

            data = usage_planner.load_data(data_path)
            sessions = sorted(data["sessions"], key=lambda item: item["tool"])
            self.assertEqual(len(sessions), 2)
            self.assertEqual({item["source"] for item in sessions}, {"codex-log", "claude-log"})
            self.assertEqual(
                {item["tool"]: item["prompt_count"] for item in sessions},
                {"claude-code": 1, "codex": 2},
            )
            serialized = json.dumps(data)
            self.assertNotIn("secret prompt", serialized)
            self.assertNotIn("second secret", serialized)

    def test_warmup_dry_run_does_not_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "usage.json"
            self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "init",
                    "--non-interactive",
                    "--timezone",
                    "Asia/Taipei",
                    "--preferred-window",
                    "20:00-23:00",
                ]
            )

            exit_code = self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "warmup",
                    "--force",
                    "--dry-run",
                    "--method",
                    "cli",
                    "--prompt",
                    "ping",
                ]
            )

            self.assertEqual(exit_code, 0)
            data = usage_planner.load_data(data_path)
            # dry-run should not record any session
            self.assertEqual(len(data["sessions"]), 0)

    def test_warmup_force_records_session(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "usage.json"
            self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "init",
                    "--non-interactive",
                    "--timezone",
                    "Asia/Taipei",
                ]
            )

            # Use deeplink method which will fail gracefully on CI but
            # still record the session regardless of exit code.
            self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "warmup",
                    "--force",
                    "--method",
                    "deeplink",
                ]
            )

            data = usage_planner.load_data(data_path)
            self.assertEqual(len(data["sessions"]), 1)
            self.assertEqual(data["sessions"][0]["source"], "auto-warmup")
            self.assertEqual(data["sessions"][0]["warmup_method"], "deeplink")
            self.assertEqual(data["sessions"][0]["warmup_prompt"], "ping")

    def test_should_warmup_now_returns_true_at_correct_time(self):
        data = usage_planner.blank_data("Asia/Taipei")
        data["preferences"]["preferred_windows"] = [
            {"start": "22:00", "end": "23:00"},
        ]
        data["preferences"]["quota_window_minutes"] = 60

        suggestion = usage_planner.make_suggestion(data, days=7)
        # The suggestion should be around 22:00
        self.assertGreaterEqual(suggestion.start_minutes, 21 * 60)
        self.assertLessEqual(suggestion.start_minutes, 23 * 60)

    def test_generate_launchd_plist_contains_correct_structure(self):
        data = usage_planner.blank_data("Asia/Taipei")
        data["preferences"]["preferred_windows"] = [
            {"start": "22:00", "end": "23:00"},
        ]
        data["preferences"]["quota_window_minutes"] = 60

        plist, hour, minute = usage_planner.generate_launchd_plist(
            data,
            method="cli",
            prompt="ping",
            lead_minutes=30,
        )

        self.assertIn("<key>Label</key>", plist)
        self.assertIn("com.usage-planner.warmup", plist)
        self.assertIn("<key>ProgramArguments</key>", plist)
        self.assertIn("<key>StartCalendarInterval</key>", plist)
        self.assertIn("warmup", plist)
        self.assertIn("--force", plist)
        self.assertIn("--method", plist)
        self.assertIn("cli", plist)
        self.assertIn("ping", plist)
        # hour and minute should be valid
        self.assertGreaterEqual(hour, 0)
        self.assertLessEqual(hour, 23)
        self.assertGreaterEqual(minute, 0)
        self.assertLessEqual(minute, 59)

    def test_schedule_warmup_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "usage.json"
            self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "init",
                    "--non-interactive",
                    "--timezone",
                    "Asia/Taipei",
                    "--preferred-window",
                    "22:00-23:00",
                ]
            )

            exit_code = self.run_cli(
                [
                    "--data",
                    str(data_path),
                    "schedule-warmup",
                    "--dry-run",
                    "--method",
                    "cli",
                ]
            )

            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
