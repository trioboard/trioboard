"""The MCP server and the hook, end to end through real processes on a temporary folder."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trioboard.store import Store
from trioboard import hook

ROOT = Path(__file__).resolve().parents[1]


def rpc(agent, home, requests):
    """Run one server process for `agent`, feed JSON-RPC lines, return the parsed responses."""
    env = dict(os.environ, TRIO_HOME=home, TRIO_AGENT=agent, PYTHONPATH=str(ROOT))
    proc = subprocess.run([sys.executable, "-m", "trioboard.cli", "mcp"], input="\n".join(json.dumps(r) for r in requests) + "\n",
                          capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30)
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        Store(self.tmp.name).init(["claude", "codex", "agy"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_initialize_lists_tools_and_round_trips_a_message(self):
        out = rpc("claude", self.tmp.name, [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "trio_send", "arguments": {
                "to": "codex", "subject": "Brief", "body": "Objective: add rate limiting.", "ack": True}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "trio_history", "arguments": {}}},
        ])
        by_id = {m["id"]: m for m in out if "id" in m}
        self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "trioboard")
        names = [t["name"] for t in by_id[2]["result"]["tools"]]
        self.assertIn("trio_send", names)
        self.assertIn("trio_reserve", names)
        self.assertFalse(by_id[3]["result"]["isError"], by_id[3])
        self.assertIn("sent to codex", by_id[3]["result"]["content"][0]["text"])
        self.assertIn("UNREAD", by_id[4]["result"]["content"][0]["text"])

        out = rpc("codex", self.tmp.name, [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "trio_whoami", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "trio_inbox", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "trio_inbox", "arguments": {}}},
        ])
        by_id = {m["id"]: m for m in out if "id" in m}
        self.assertIn("Unread messages for you: 1", by_id[2]["result"]["content"][0]["text"])
        self.assertIn("Objective: add rate limiting.", by_id[3]["result"]["content"][0]["text"])
        self.assertIn("No new messages", by_id[4]["result"]["content"][0]["text"])

    def test_unknown_agent_and_unknown_method(self):
        out = rpc("ghost", self.tmp.name, [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "trio_whoami", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "nope"},
        ])
        by_id = {m["id"]: m for m in out if "id" in m}
        self.assertTrue(by_id[1]["result"]["isError"])
        self.assertIn("Unknown agent", by_id[1]["result"]["content"][0]["text"])
        self.assertEqual(by_id[2]["error"]["code"], -32601)

    def test_hook_delivers_and_marks_read(self):
        store = Store(self.tmp.name)
        store.send("codex", "claude", "Diff ready", "The diff is in the job record.")
        import io
        out = io.StringIO()
        hook.main("claude", "claude", store=store, stdin=io.StringIO('{"hook_event_name": "UserPromptSubmit"}'), stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("Diff ready", payload["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(store.unread("claude"), [])
        out = io.StringIO()
        hook.main("claude", "claude", store=store, stdin=io.StringIO("{}"), stdout=out)
        self.assertEqual(out.getvalue().strip(), "{}")

    def test_cli_round_trip(self):
        env = dict(os.environ, TRIO_HOME=self.tmp.name, PYTHONPATH=str(ROOT))
        run = lambda *a: subprocess.run([sys.executable, "-m", "trioboard.cli", *a], capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30)
        self.assertIn("sent to agy", run("send", "agy", "Watch", "Watch the clip.", "--from", "claude").stdout)
        self.assertIn("Watch the clip.", run("inbox", "--agent", "agy").stdout)
        self.assertIn("OWNER INSTRUCTION", run("send", "all", "Stop", "Halt.").stdout + run("inbox", "--agent", "codex").stdout)
        status = run("status").stdout
        self.assertIn("codex: 0 unread", status)
        self.assertIn("agy: 1 unread", status)
        self.assertEqual(run("inbox").returncode, 1, "no identity given")


if __name__ == "__main__":
    unittest.main()
