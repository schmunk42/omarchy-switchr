#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-09-30 13:17:28 UTC
"""Tests for `switchr.py jump`. Every subprocess call is mocked."""

import io
import json
import os
import unittest
from contextlib import redirect_stderr
from unittest import mock

import support  # noqa: F401  (sets sys.path)
from support import completed, fixture

import switchr

ADDRESS = "0x563679e6db10"
SOCK = "/tmp/switchr-test/herdr.sock"


class JumpCase(unittest.TestCase):

    def setUp(self):
        self.clients = fixture("hyprctl-clients.json")
        self.dispatch_answer = "ok"
        self.calls = []
        self.rpc = mock.patch.object(switchr, "herdr_rpc", return_value=None)
        self.rpc_mock = self.rpc.start()
        self.addCleanup(self.rpc.stop)
        for p in (mock.patch.object(switchr.subprocess, "run", side_effect=self.fake_run),
                  mock.patch.object(switchr.shutil, "which", return_value="/usr/bin/notify-send")):
            p.start()
            self.addCleanup(p.stop)

    def fake_run(self, args, **kwargs):
        args = list(args)
        self.calls.append((args, kwargs))
        if args == ["hyprctl", "-j", "clients"]:
            if self.clients is None:
                return completed(args, returncode=1)
            return completed(args, stdout=json.dumps(self.clients))
        if args[:2] == ["hyprctl", "dispatch"]:
            return completed(args, stdout=self.dispatch_answer + "\n")
        if args[:3] == ["herdr", "tab", "focus"]:
            return completed(args)
        if args[0] == "notify-send":
            return completed(args)
        raise AssertionError("unexpected subprocess " + repr(args))

    def main(self, *argv):
        err = io.StringIO()
        with redirect_stderr(err):
            status = switchr.main(["jump"] + list(argv))
        return status, err.getvalue()

    def dispatches(self):
        return [a for a, _ in self.calls if "dispatch" in a]

    def notifications(self):
        return [a for a, _ in self.calls if a[0] == "notify-send"]


class TestJump(JumpCase):

    def test_closed_window_is_not_dispatched(self):
        status, err = self.main("--address", "0xdeadbeef", "--label", "Gone")
        self.assertEqual(status, 0)
        self.assertEqual(self.dispatches(), [])
        self.assertEqual(len(self.notifications()), 1)
        self.assertIn("Gone", err)
        self.assertIn("closed", err)

    def test_closed_window_skips_herdr_too(self):
        self.main("--address", "0xdeadbeef", "--herdr-socket", SOCK,
                  "--tab-id", "w1:t1", "--pane-id", "w1:p1")
        self.rpc_mock.assert_not_called()
        self.assertFalse(any(a[:1] == ["herdr"] for a, _ in self.calls))

    def test_unreadable_clients_is_not_dispatched(self):
        self.clients = None
        status, err = self.main("--address", ADDRESS)
        self.assertEqual(status, 0)
        self.assertEqual(self.dispatches(), [])
        self.assertIn("not readable", err)

    def test_invalid_address_is_not_dispatched(self):
        status, err = self.main("--address", "window-1")
        self.assertEqual(status, 0)
        self.assertEqual(self.calls[-1][0][0], "notify-send")
        self.assertEqual(self.dispatches(), [])

    def test_missing_address_reports_and_exits_0(self):
        with self.assertRaises(SystemExit) as ctx:
            self.main()
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(len(self.notifications()), 1)

    def test_window_focus(self):
        status, err = self.main("--address", ADDRESS)
        self.assertEqual(status, 0)
        self.assertEqual(self.dispatches(), [
            ["hyprctl", "dispatch", 'hl.dsp.focus({ window = "address:%s" })' % ADDRESS]])
        self.assertEqual(self.notifications(), [])
        self.assertEqual(err, "")

    def test_dispatch_answer_other_than_ok_is_reported(self):
        self.dispatch_answer = "error: no such window"
        status, err = self.main("--address", ADDRESS, "--label", "Term")
        self.assertEqual(status, 0)
        self.assertEqual(len(self.notifications()), 1)
        self.assertIn("no such window", err)

    def test_notify_send_missing_still_reports_on_stderr(self):
        with mock.patch.object(switchr.shutil, "which", return_value=None):
            status, err = self.main("--address", "0xdeadbeef")
        self.assertEqual(status, 0)
        self.assertEqual(self.notifications(), [])
        self.assertIn("closed", err)

    def test_pane_focus_via_socket_api_before_window(self):
        status, _ = self.main("--address", ADDRESS, "--herdr-socket", SOCK,
                              "--tab-id", "w3:t5", "--pane-id", "w3:p7")
        self.assertEqual(status, 0)
        self.rpc_mock.assert_called_once_with(SOCK, "pane.focus", {"pane_id": "w3:p7"})
        self.assertFalse(any(a[:1] == ["herdr"] for a, _ in self.calls))
        self.assertEqual(len(self.dispatches()), 1)

    def test_tab_focus_via_cli_without_herdr_variables(self):
        with mock.patch.dict(os.environ, {"HERDR_ENV": "1", "HERDR_SOCKET_PATH": "/wrong"}):
            self.main("--address", ADDRESS, "--herdr-socket", SOCK, "--tab-id", "w3:t5")
        tab_calls = [(a, kw) for a, kw in self.calls if a[:3] == ["herdr", "tab", "focus"]]
        self.assertEqual(len(tab_calls), 1)
        args, kwargs = tab_calls[0]
        self.assertEqual(args, ["herdr", "tab", "focus", "w3:t5"])
        self.assertEqual(kwargs["env"]["HERDR_SOCKET_PATH"], SOCK)
        self.assertNotIn("HERDR_ENV", kwargs["env"])
        # herdr first, then the window
        order = [a[0] for a, _ in self.calls if a[0] in ("herdr", "hyprctl") and a[1] != "-j"]
        self.assertEqual(order, ["herdr", "hyprctl"])

    def test_herdr_failure_still_focuses_window(self):
        self.rpc_mock.return_value = "herdr pane.focus: connection refused"
        status, err = self.main("--address", ADDRESS, "--herdr-socket", SOCK,
                                "--tab-id", "w3:t5", "--pane-id", "w3:p7")
        self.assertEqual(status, 0)
        self.assertIn("connection refused", err)
        self.assertEqual(len(self.dispatches()), 1)

    def test_tab_without_socket_is_reported_and_window_focused(self):
        status, err = self.main("--address", ADDRESS, "--tab-id", "w3:t5")
        self.assertEqual(status, 0)
        self.assertIn("--herdr-socket", err)
        self.assertEqual(len(self.dispatches()), 1)


class TestHerdrRpc(unittest.TestCase):
    """herdr_rpc against a fake socket object."""

    def run_rpc(self, answer):
        conn = mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.recv.side_effect = [answer, b""]
        with mock.patch.object(switchr.socket, "socket", return_value=conn):
            result = switchr.herdr_rpc(SOCK, "pane.focus", {"pane_id": "w1:p1"})
        sent = json.loads(conn.sendall.call_args[0][0].decode())
        return result, sent

    def test_success(self):
        result, sent = self.run_rpc(b'{"id":"switchr:pane.focus","result":{}}\n')
        self.assertIsNone(result)
        self.assertEqual(sent["method"], "pane.focus")
        self.assertEqual(sent["params"], {"pane_id": "w1:p1"})

    def test_error(self):
        result, _ = self.run_rpc(b'{"id":"x","error":{"code":"not_found","message":"no pane"}}\n')
        self.assertEqual(result, "herdr pane.focus: no pane")


if __name__ == "__main__":
    unittest.main()
