import json
import tempfile
import unittest
from pathlib import Path

import usage_planner
import usage_web


class UsageWebTests(unittest.TestCase):
    def test_web_import_logs_reuses_planner_without_prompt_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "usage.json"
            codex_root = root / "codex" / "sessions"
            codex_file = codex_root / "2026" / "07" / "06" / "rollout-test.jsonl"
            codex_file.parent.mkdir(parents=True)
            codex_file.write_text(
                "\n".join(
                    json.dumps(item)
                    for item in [
                        {
                            "timestamp": "2026-07-06T12:00:00.000Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "user_message",
                                "message": "private prompt",
                            },
                        },
                        {
                            "timestamp": "2026-07-06T12:10:00.000Z",
                            "type": "event_msg",
                            "payload": {"type": "task_complete"},
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            data = usage_planner.blank_data("Asia/Taipei")
            usage_planner.save_data(data_path, data)
            app = usage_web.WebApp(data_path)

            result = app.import_logs(
                {
                    "tools": ["codex"],
                    "all": True,
                    "idle_minutes": 45,
                    "tail_minutes": 15,
                    "codex_root": str(codex_root),
                }
            )

            self.assertEqual(result["tools"][0]["added"], 1)
            saved = usage_planner.load_data(data_path)
            self.assertEqual(len(saved["sessions"]), 1)
            self.assertEqual(saved["sessions"][0]["source"], "codex-log")
            self.assertNotIn("private prompt", json.dumps(saved))

    def test_web_state_shapes_dashboard_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "usage.json"
            data = usage_planner.blank_data("Asia/Taipei")
            data["preferences"]["preferred_windows"] = [
                {"start": "20:00", "end": "22:00"},
            ]
            usage_planner.save_data(data_path, data)
            app = usage_web.WebApp(data_path)

            state = app.state(days=7, reminder_count=2)

            self.assertEqual(state["timezone"], "Asia/Taipei")
            self.assertEqual(state["preferences"]["preferred_windows_text"], "20:00-22:00")
            self.assertEqual(len(state["reminders"]), 2)
            self.assertIn("suggestion", state)


if __name__ == "__main__":
    unittest.main()
