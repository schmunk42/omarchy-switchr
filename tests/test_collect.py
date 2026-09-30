#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-09-30 13:19:02 UTC
"""Tests for `switchr.py collect` against anonymised fixtures.

Every subprocess and /proc access is mocked: the tests must pass on a CI
runner without hyprctl or herdr. The herdr snapshot fixture is a real dump
with one synthetic second pane (w3:p9, with a tab and a newline in its
title) added to the focused tab, so that a tab with several panes exists.
"""

import os
import tempfile
import threading
import time
import unittest
from unittest import mock

import support  # noqa: F401  (sets sys.path)
from support import MONITORS, completed, fixture

import herdr_target as ht
import switchr

HERDR_PID = 1300          # foot on workspace 6
HERDR_ADDRESS = "0x56367a9807a0"
ACTIVE_ADDRESS = "0x563679e6db10"
SOCK = "/tmp/switchr-test/sessions/Earth/herdr.sock"
GROUP = ["0x56367a90b220", "0x56367ab0aed0"]


class CollectCase(unittest.TestCase):
    """Runs collect() with mocked hyprctl, herdr and /proc."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.clients = fixture("hyprctl-clients.json")
        self.active = ACTIVE_ADDRESS
        self.targets = {HERDR_PID: ht.HerdrTarget("Earth", SOCK, ht.HOSTNAME, None)}
        self.snapshot_run = self.default_snapshot_run
        self.runs = []

    def default_snapshot_run(self, args, **kwargs):
        import json
        return completed(args, stdout=json.dumps(fixture("herdr-snapshot.json")))

    def fake_hyprctl(self, command):
        if command == "clients":
            return self.clients
        if command == "monitors":
            return MONITORS
        if command == "activewindow":
            return {"address": self.active}
        raise AssertionError("unexpected hyprctl " + command)

    def fake_run(self, args, **kwargs):
        self.runs.append((list(args), kwargs))
        if list(args[:3]) == ["herdr", "api", "snapshot"]:
            return self.snapshot_run(args, **kwargs)
        raise AssertionError("unexpected subprocess " + repr(args))

    def run_collect(self):
        patches = [
            mock.patch.object(switchr, "hyprctl", side_effect=self.fake_hyprctl),
            mock.patch.object(switchr.subprocess, "run", side_effect=self.fake_run),
            mock.patch.object(ht, "herdr_target", side_effect=lambda pid: self.targets.get(pid)),
            mock.patch.object(ht, "cwd_of_window", return_value="/home/user/Work/plain"),
            mock.patch.object(ht, "descendants", side_effect=AssertionError("no /proc in tests")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        doc, status = switchr.collect()
        self.by_id = {e["id"]: e for e in doc["entries"]}
        return doc, status


class TestDocument(CollectCase):

    def test_top_level_fields(self):
        doc, status = self.run_collect()
        self.assertEqual(status, 0)
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["host"], ht.HOSTNAME)
        self.assertEqual(doc["errors"], [])
        self.assertTrue(doc["generated_at"].endswith("+00:00"))

    def test_unreadable_clients_gives_exit_1_and_empty_entries(self):
        self.clients = None
        doc, status = self.run_collect()
        self.assertEqual(status, 1)
        self.assertEqual(doc["entries"], [])
        self.assertEqual(doc["version"], 1)
        self.assertTrue(doc["errors"])

    def test_entries_are_sorted_by_sort_key(self):
        doc, _ = self.run_collect()
        keys = [e["sort_key"] for e in doc["entries"]]
        self.assertEqual(keys, sorted(keys))
        self.assertTrue(all(len(k) == 6 for k in keys))

    def test_workspace_order_numeric_then_specials(self):
        doc, _ = self.run_collect()
        order = []
        for e in doc["entries"]:
            if e["type"] == "window" and e["workspace"]["id"] not in order:
                order.append(e["workspace"]["id"])
        self.assertEqual(order, [1, 2, 3, 6, 7, 8, 11, -98])
        docs = next(e for e in doc["entries"] if e["workspace"]["id"] == -98)
        self.assertEqual(docs["sort_key"][0], 1001)

    def test_windows_within_workspace_by_focus_history(self):
        doc, _ = self.run_collect()
        ws3 = [e["id"] for e in doc["entries"]
               if e["type"] == "window" and e["workspace"]["id"] == 3]
        # foot has focusHistoryID 6, Thunderbird 7
        self.assertEqual(ws3, ["win:0x56367acdfe00", "win:0x56367ad4db80"])
        self.assertEqual(self.by_id["win:0x56367acdfe00"]["sort_key"][:2], [3, 0])
        self.assertEqual(self.by_id["win:0x56367ad4db80"]["sort_key"][:2], [3, 1])

    def test_ids_unique_and_well_formed(self):
        doc, _ = self.run_collect()
        ids = [e["id"] for e in doc["entries"]]
        self.assertEqual(len(ids), len(set(ids)))
        prefixes = {"window": "win:", "group_tab": "win:", "herdr_tab": "htab:Earth:",
                    "herdr_pane": "hpane:Earth:", "hint": "hint:"}
        for e in doc["entries"]:
            self.assertTrue(e["id"].startswith(prefixes[e["type"]]), e["id"])
            self.assertNotIn("\t", e["id"])
            self.assertNotIn("\n", e["id"])
        self.assertIn("htab:Earth:w3:t5", ids)
        self.assertIn("hpane:Earth:w3:p9", ids)

    def test_monitor_and_active(self):
        doc, _ = self.run_collect()
        active = [e["id"] for e in doc["entries"] if e["active"] and e["type"] == "window"]
        self.assertEqual(active, ["win:" + ACTIVE_ADDRESS])
        self.assertEqual(self.by_id["win:0x56367ae8c280"]["monitor"], "eDP-1")
        self.assertEqual(self.by_id["win:" + ACTIVE_ADDRESS]["monitor"], "DP-2")

    def test_plain_terminal_gets_proc_cwd(self):
        self.run_collect()
        ent = self.by_id["win:" + ACTIVE_ADDRESS]
        self.assertEqual(ent["cwd"], "/home/user/Work/plain")
        self.assertEqual(ent["detail"], "foot · /home/user/Work/plain")


class TestGroups(CollectCase):

    def test_visible_member_is_head(self):
        self.run_collect()
        head = self.by_id["win:0x56367ab0aed0"]
        tab = self.by_id["win:0x56367a90b220"]
        self.assertEqual(head["type"], "window")
        self.assertIsNone(head["parent"])
        self.assertEqual(head["depth"], 0)
        self.assertEqual(head["sort_key"], [1, 0, -1, -1, -1, -1])
        self.assertEqual(tab["type"], "group_tab")
        self.assertEqual(tab["parent"], "win:0x56367ab0aed0")
        self.assertEqual(tab["depth"], 1)
        self.assertEqual(tab["sort_key"], [1, 0, 0, -1, -1, -1])

    def test_group_tab_is_never_active(self):
        self.active = "0x56367a90b220"
        self.run_collect()
        self.assertFalse(self.by_id["win:0x56367a90b220"]["active"])

    def test_without_visible_member_lowest_focus_history_wins(self):
        for c in self.clients:
            if c["address"] in GROUP:
                c["visible"] = False
        self.clients[0]["focusHistoryID"] = 2  # 0x56367a90b220 now more recent
        self.run_collect()
        self.assertEqual(self.by_id["win:0x56367a90b220"]["type"], "window")
        self.assertEqual(self.by_id["win:0x56367ab0aed0"]["type"], "group_tab")

    def test_unmapped_clients_are_skipped(self):
        self.clients[1]["mapped"] = False
        self.run_collect()
        self.assertNotIn("win:" + self.clients[1]["address"], self.by_id)


class TestHerdr(CollectCase):

    def test_tabs_and_panes_below_window(self):
        doc, _ = self.run_collect()
        win = self.by_id["win:" + HERDR_ADDRESS]
        self.assertEqual(win["detail"], "foot · /home/user/Work/project-docs · herdr Earth")
        self.assertEqual(win["agent"], "claude")
        self.assertEqual(win["agent_status"], "working")
        tab = self.by_id["htab:Earth:w3:t5"]
        self.assertEqual(tab["parent"], win["id"])
        self.assertEqual(tab["depth"], 1)
        self.assertEqual(tab["label"], "ui › three")
        self.assertTrue(tab["active"])
        self.assertEqual(tab["detail"], "working · 2 panes · /home/user/Work/project-docs")
        self.assertEqual(tab["sort_key"], win["sort_key"][:3] + [2, 5, -1])
        self.assertEqual(tab["target"], {"address": HERDR_ADDRESS, "herdr": {
            "session": "Earth", "socket": SOCK, "workspace_id": "w3",
            "tab_id": "w3:t5", "pane_id": "w3:p7"}})
        pane = self.by_id["hpane:Earth:w3:p9"]
        self.assertEqual(pane["parent"], tab["id"])
        self.assertEqual(pane["depth"], 2)
        self.assertFalse(pane["active"])
        self.assertTrue(self.by_id["hpane:Earth:w3:p7"]["active"])
        self.assertEqual(pane["sort_key"], win["sort_key"][:3] + [2, 5, 1])
        self.assertEqual(pane["target"]["herdr"]["pane_id"], "w3:p9")
        # the two-pane tab keeps exactly its two pane rows
        children = [e["id"] for e in doc["entries"] if e["parent"] == tab["id"]]
        self.assertEqual(children, ["hpane:Earth:w3:p7", "hpane:Earth:w3:p9"])

    def test_single_pane_tab_is_one_entry(self):
        doc, _ = self.run_collect()
        win = self.by_id["win:" + HERDR_ADDRESS]
        single = self.by_id["htab:Earth:w1:t8"]
        self.assertEqual(single["type"], "herdr_tab")
        self.assertEqual(single["parent"], win["id"])
        self.assertEqual(single["depth"], 1)
        self.assertEqual(single["label"], "✳ Claude session w1:p8")
        self.assertEqual(single["title"], "✳ Claude session w1:p8")
        self.assertEqual(single["detail"],
                         "docs › 1 · /home/user/Work/project-docs · claude · idle")
        self.assertNotIn("pane", single["detail"].split(" · ")[1:])
        self.assertEqual(single["cwd"], "/home/user/Work/project-docs")
        self.assertEqual(single["agent"], "claude")
        self.assertEqual(single["agent_status"], "idle")
        self.assertEqual(single["sort_key"], win["sort_key"][:3] + [1, 8, -1])
        self.assertEqual(single["target"], {"address": HERDR_ADDRESS, "herdr": {
            "session": "Earth", "socket": SOCK, "workspace_id": "w1",
            "tab_id": "w1:t8", "pane_id": "w1:p8"}})
        self.assertNotIn("hpane:Earth:w1:p8", self.by_id)
        self.assertEqual([e for e in doc["entries"] if e["parent"] == single["id"]], [])

    def test_only_multi_pane_tabs_have_pane_rows(self):
        doc, _ = self.run_collect()
        panes = [e for e in doc["entries"] if e["type"] == "herdr_pane"]
        self.assertEqual({e["parent"] for e in panes}, {"htab:Earth:w3:t5"})
        self.assertEqual(len([e for e in doc["entries"] if e["type"] == "herdr_tab"]), 6)

    def test_single_pane_tab_without_agent_omits_null_parts(self):
        self.run_collect()
        plain = self.by_id["htab:Earth:w3:t9"]
        self.assertEqual(plain["label"], "user@host:~/Work/project-docs")
        self.assertEqual(plain["detail"], "ui › 3 · /home/user/Work/project-docs · unknown")
        self.assertIsNone(plain["agent"])

    def test_herdr_env_has_no_herdr_variables(self):
        with mock.patch.dict(os.environ, {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1"}):
            self.run_collect()
        env = self.runs[0][1]["env"]
        self.assertEqual(env["HERDR_SOCKET_PATH"], SOCK)
        self.assertEqual([k for k in env if k.startswith("HERDR_") and k != "HERDR_SOCKET_PATH"], [])

    def test_escaping_of_tab_newline_cr(self):
        for c in self.clients:
            if c["address"] == "0x56367ae8c280":
                c["title"] = "a\tb\nc\rd"
        self.run_collect()
        win = self.by_id["win:0x56367ae8c280"]
        self.assertEqual(win["label"], "a b c d")
        self.assertEqual(win["title"], "a b c d")
        pane = self.by_id["hpane:Earth:w3:p9"]
        self.assertEqual(pane["label"], "user@host:~/Work/project split")
        for e in self.by_id.values():
            for field in ("label", "title", "detail"):
                value = e[field] or ""
                self.assertFalse(set(value) & {"\t", "\n", "\r"}, (e["id"], field))

    def test_shared_pid_terminals_get_a_hint(self):
        for c in self.clients:
            if c["address"] in ("0x56367ac59e30", ACTIVE_ADDRESS):
                c["pid"] = 4242
        doc, status = self.run_collect()
        self.assertEqual(status, 0)
        hint = self.by_id["hint:win:" + ACTIVE_ADDRESS]
        self.assertEqual(hint["type"], "hint")
        self.assertEqual(hint["parent"], "win:" + ACTIVE_ADDRESS)
        self.assertEqual(hint["depth"], 1)
        self.assertEqual(hint["sort_key"], [7, 0, -1, 0, 0, 0])
        self.assertIn("2 windows share PID 4242", hint["label"])
        self.assertEqual(hint["target"], {"address": ACTIVE_ADDRESS, "herdr": None})
        self.assertTrue(any("share PID" in e for e in doc["errors"]))

    def test_remote_session_gets_a_hint_without_query(self):
        self.targets = {HERDR_PID: ht.HerdrTarget("remote:build", "/tmp/c.sock", "build", None)}
        self.run_collect()
        hint = self.by_id["hint:win:" + HERDR_ADDRESS]
        self.assertEqual(hint["label"], "Tabs not available (herdr --remote build)")
        self.assertEqual(self.runs, [])

    def test_failing_snapshot_is_a_hint_and_error(self):
        self.snapshot_run = lambda args, **kw: completed(args, returncode=1, stderr="boom\n")
        doc, status = self.run_collect()
        self.assertEqual(status, 0)
        hint = self.by_id["hint:win:" + HERDR_ADDRESS]
        self.assertEqual(hint["label"], "herdr session Earth: herdr api snapshot failed: boom")
        self.assertIn(hint["label"], doc["errors"])

    def test_session_in_two_windows_lists_tabs_once(self):
        self.targets[1200] = self.targets[HERDR_PID]   # foot on workspace 8, fhid 11
        self.run_collect()
        self.assertEqual(self.by_id["htab:Earth:w3:t5"]["parent"], "win:" + HERDR_ADDRESS)
        self.assertEqual(len(self.runs), 1)


class TestHerdrTimeout(CollectCase):

    BUDGET = 0.4

    def setUp(self):
        super().setUp()
        p = mock.patch.object(switchr, "SNAPSHOT_BUDGET", self.BUDGET)
        p.start()
        self.addCleanup(p.stop)

    def test_timeout_honouring_call_stays_within_budget(self):
        def slow(args, **kwargs):
            time.sleep(kwargs["timeout"])
            raise switchr.subprocess.TimeoutExpired(args, kwargs["timeout"])
        self.snapshot_run = slow
        started = time.monotonic()
        doc, status = self.run_collect()
        elapsed = time.monotonic() - started
        self.assertEqual(status, 0)
        self.assertLess(elapsed, self.BUDGET + 0.5)
        self.assertLessEqual(self.runs[0][1]["timeout"], self.BUDGET)
        hint = self.by_id["hint:win:" + HERDR_ADDRESS]
        self.assertIn("did not answer within", hint["label"])

    def test_hanging_call_is_abandoned_at_the_deadline(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def hang(args, **kwargs):
            release.wait(5)
            return completed(args, stdout="{}")
        self.snapshot_run = hang
        started = time.monotonic()
        doc, status = self.run_collect()
        elapsed = time.monotonic() - started
        release.set()
        self.assertEqual(status, 0)
        self.assertLess(elapsed, self.BUDGET + 0.5)
        hint = self.by_id["hint:win:" + HERDR_ADDRESS]
        self.assertTrue(hint["label"].startswith("herdr session Earth: herdr did not answer ("),
                        hint["label"])
        # the rest of the document is intact
        self.assertIn("win:0x56367ae8c280", self.by_id)


if __name__ == "__main__":
    unittest.main()
