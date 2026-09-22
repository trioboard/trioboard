"""Mailbox behaviour on a temporary folder. Run: python3 -m unittest discover -s tests"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from trioboard.store import Store, TrioError, parse_message


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.init(["claude", "codex", "agy"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_send_lands_as_one_file_with_header_and_receipt_after_read(self):
        report = self.store.send("claude", "codex", "Add rate limiting", "Objective: limit /reports.\nDone when: tests pass.", ack=True)
        self.assertIn("sent to codex", report)
        files = self.store.unread("codex")
        self.assertEqual(len(files), 1)
        info, body = parse_message(files[0].read_text(encoding="utf-8"))
        self.assertEqual(info["from"], "claude")
        self.assertEqual(info["to"], "codex")
        self.assertEqual(info["ack"], "required")
        self.assertTrue(body.startswith("Objective"))
        self.assertFalse(list(self.store.mailbox.glob("codex/new/.*.tmp")), "no temp file left behind")
        text = self.store.inbox("codex")
        self.assertIn("Add rate limiting", text)
        self.assertEqual(self.store.unread("codex"), [])
        receipts = self.store.receipts()
        self.assertIn("read", receipts[info["id"]])
        self.assertIn("[ack requested]", self.store.timeline())

    def test_history_shows_unread_then_read_then_ack(self):
        self.store.send("claude", "agy", "Check the clip", "Watch it and list defects.", ack=True)
        self.assertIn("UNREAD", self.store.timeline())
        self.store.inbox("agy")
        self.assertIn("read ", self.store.timeline())
        mid = list(self.store.receipts())[0]
        self.store.acknowledge("agy", mid, "accepted, starting")
        line = self.store.timeline()
        self.assertIn("ack ", line)
        self.assertIn("accepted, starting", line)

    def test_ack_by_prefix_marks_unread_message_read(self):
        self.store.send("codex", "claude", "Diff ready", "See the attached path.")
        mid = list(self.store.unread_ids())[0]
        self.store.acknowledge("claude", mid, "seen")
        self.assertEqual(self.store.unread("claude"), [])
        with self.assertRaises(TrioError):
            self.store.acknowledge("claude", "20200101-000000-dead", "nothing")

    def test_job_id_validation_and_prefix(self):
        with self.assertRaises(TrioError):
            self.store.send("claude", "codex", "x", "y", job="J-1")
        job = self.store.new_job("Rate limit", "Ship it before the schema work.", coordinator="claude")
        self.assertRegex(job, r"^J-\d{8}-\d{2}$")
        self.store.send("claude", "codex", "Brief", "Do it.", job=job)
        self.assertIn(job, self.store.timeline(job=job))
        self.assertEqual(self.store.open_jobs()[0][0], job)
        second = self.store.new_job("Another")
        self.assertNotEqual(job, second)

    def test_owner_importance_only_for_owner(self):
        with self.assertRaises(TrioError):
            self.store.send("claude", "codex", "s", "b", importance="owner")
        self.store.send("owner", "all", "Stop", "Ship the rate limit first.", importance="owner")
        for agent in ("claude", "codex", "agy"):
            files = self.store.unread(agent)
            self.assertEqual(len(files), 1)
            info, body = parse_message(files[0].read_text(encoding="utf-8"))
            self.assertEqual(info["importance"], "owner")
            self.assertIn("OWNER INSTRUCTION", body)

    def test_all_excludes_sender_and_unknown_recipient_fails(self):
        self.store.send("codex", "all", "hello", "world")
        self.assertEqual(len(self.store.unread("codex")), 0)
        self.assertEqual(len(self.store.unread("claude")), 1)
        with self.assertRaises(TrioError):
            self.store.send("codex", "nobody", "hello", "world")
        with self.assertRaises(TrioError):
            self.store.send("codex", "codex", "hello", "me")

    def test_search_finds_body_text(self):
        self.store.send("claude", "codex", "Brief", "Use the existing middleware in src/api.")
        self.assertIn("middleware", self.store.search("middleware"))
        self.assertIn("No message contains", self.store.search("zebra"))

    def test_reservation_overlap_warns_and_notifies_holder(self):
        first = self.store.reserve("codex", ["/tmp/project/src/api"], 30, "rate limit")
        self.assertIn("Reserved until", first)
        second = self.store.reserve("agy", ["/tmp/project/src/api/routes.py"], 10, "review")
        self.assertIn("WARNING", second)
        self.assertEqual(len(self.store.unread("codex")), 1, "the holder gets a message about the overlap")
        self.assertEqual(len(self.store.reservations()), 2)
        self.assertIn("Released 1", self.store.release("codex"))
        self.assertIn("no matching", self.store.release("codex"))
        with self.assertRaises(TrioError):
            self.store.reserve("codex", ["relative/path"], 10, "x")
        with self.assertRaises(TrioError):
            self.store.reserve("codex", ["/tmp/x"], 0, "x")

    def test_expired_reservation_is_cleaned(self):
        self.store.reserve("claude", ["/tmp/a"], 1, "short")
        record_file = next(self.store.reservations_dir.glob("claude-*.json"))
        data = json.loads(record_file.read_text(encoding="utf-8"))
        data["until"] = "2000-01-01T00:00:00+00:00"
        record_file.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.store.reservations(), [])
        self.assertFalse(record_file.exists())

    def test_config_agents_and_env_override(self):
        (Path(self.tmp.name) / "config.json").write_text(json.dumps({"agents": ["alpha", "beta"]}), encoding="utf-8")
        self.assertEqual(Store(self.tmp.name).agents, ["alpha", "beta"])
        os.environ["TRIO_AGENTS"] = "one,two"
        try:
            self.assertEqual(Store(self.tmp.name).agents, ["one", "two"])
        finally:
            del os.environ["TRIO_AGENTS"]
        (Path(self.tmp.name) / "config.json").write_text(json.dumps({"agents": ["Bad Name"]}), encoding="utf-8")
        with self.assertRaises(TrioError):
            Store(self.tmp.name)

    def test_body_limit(self):
        with self.assertRaises(TrioError):
            self.store.send("claude", "codex", "big", "x" * 60_001)


if __name__ == "__main__":
    unittest.main()
