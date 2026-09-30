#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-09-30 13:17:28 UTC
"""Tests for herdr_target() with a mocked process tree (no /proc access)."""

import os
import socket
import tempfile
import unittest
from unittest import mock

import support  # noqa: F401  (sets sys.path)

import herdr_target as ht


class TestHerdrTarget(unittest.TestCase):

    def setUp(self):
        # AF_UNIX paths are limited to ~108 bytes; keep the temp dir short.
        self.tmp = tempfile.TemporaryDirectory(prefix="swr", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def tree(self, cmdlines, environs=None):
        """Mock a process tree: pid 1 is the window, children in order."""
        children = {1: [p for p in cmdlines if p < 100]}
        for pid in cmdlines:
            children.setdefault(pid, [k for k in cmdlines if k // 100 == pid])
        patches = [
            mock.patch.object(ht, "children_of", side_effect=lambda pid: children.get(pid, [])),
            mock.patch.object(ht, "cmdline_of", side_effect=lambda pid: cmdlines.get(pid, [])),
            mock.patch.object(ht, "environ_of",
                              side_effect=lambda pid: (environs or {}).get(pid, {})),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def make_socket(self, *parts):
        path = os.path.join(self.tmp.name, "herdr", *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(path)
        self.addCleanup(sock.close)
        return path

    def test_no_herdr_returns_none(self):
        self.tree({2: ["/usr/bin/zsh"]})
        self.assertIsNone(ht.herdr_target(1))

    def test_named_session(self):
        path = self.make_socket("sessions", "Earth", "herdr.sock")
        self.tree({2: ["/usr/bin/zsh"], 3: ["herdr", "--session", "Earth"]})
        self.assertEqual(ht.herdr_target(1), ht.HerdrTarget("Earth", path, ht.HOSTNAME, None))

    def test_default_session(self):
        path = self.make_socket("herdr.sock")
        self.tree({2: ["herdr"]})
        self.assertEqual(ht.herdr_target(1).sock, path)

    def test_missing_socket_is_a_problem(self):
        self.tree({2: ["herdr", "session", "attach", "Mars"]})
        target = ht.herdr_target(1)
        self.assertEqual(target.session, "Mars")
        self.assertIsNone(target.sock)
        self.assertIn("no socket", target.problem)

    def test_no_session_is_a_problem(self):
        self.tree({2: ["herdr", "--no-session"]})
        self.assertIn("--no-session", ht.herdr_target(1).problem)

    def test_remote_session(self):
        self.tree({2: ["herdr", "--remote", "build"], 201: ["herdr", "client"]},
                  {201: {"HERDR_CLIENT_SOCKET_PATH": "/run/c.sock"}})
        self.assertEqual(ht.herdr_target(1),
                         ht.HerdrTarget("remote:build", "/run/c.sock", "build", None))

    def test_server_process_is_skipped(self):
        self.tree({2: ["herdr", "server"]})
        self.assertIsNone(ht.herdr_target(1))


if __name__ == "__main__":
    unittest.main()
