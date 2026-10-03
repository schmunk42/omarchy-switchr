#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-10-03 10:46:50 UTC
"""End-to-end tests: the real helper CLI against stub programs.

The unit tests mock subprocess and /proc. These run `helper/switchr.py`
as a separate process, the way the overlay does, with stub `hyprctl`,
`herdr` and `notify-send` first on PATH, a real process tree whose child
is named `herdr` (so `herdr_target()` walks the real /proc), and a real
herdr socket that answers `pane.focus`. The contract test at the end runs
the argv that SwitchrModel.js builds for a collected entry (through Node)
and checks that the jump arrives.

Linux only (/proc). Run with:

    python3 -B -m unittest discover -s tests/integration -v

Without `node` the contract test is skipped, unless SWITCHR_REQUIRE_NODE=1
(as in CI) turns that into a failure.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HELPER = os.path.join(ROOT, "helper", "switchr.py")
MODEL = os.path.join(ROOT, "SwitchrModel.js")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

HERDR_ADDRESS = "0x56367a9807a0"     # foot on workspace 6 in the fixture
PLAIN_ADDRESS = "0x563679e6db10"     # foot on workspace 7
MONITORS = [{"id": 0, "name": "eDP-1"}, {"id": 1, "name": "DP-2"}]

# Above any pid_max, so no PID of the fixture can hit a real process.
NO_PID = 99_999_000

# One stub serves as hyprctl, herdr and notify-send; it looks at its own
# name. Every call is appended to calls.jsonl with argv and the HERDR_*
# part of its environment.
STUB = textwrap.dedent("""\
    #!{python}
    import json, os, sys
    stub = os.environ["SWITCHR_STUB_DIR"]
    name = os.path.basename(sys.argv[0])
    args = sys.argv[1:]
    with open(os.path.join(stub, "calls.jsonl"), "a", encoding="utf-8") as log:
        log.write(json.dumps({{"name": name, "args": args, "env": {{
            k: v for k, v in os.environ.items() if k.startswith("HERDR_")}}}}) + "\\n")

    def emit(file):
        with open(os.path.join(stub, file), encoding="utf-8") as handle:
            sys.stdout.write(handle.read())

    if name == "hyprctl":
        if args[:1] == ["-j"]:
            emit(args[1] + ".json")
        elif args[:1] == ["dispatch"]:
            with open(os.path.join(stub, "dispatch.json"), encoding="utf-8") as handle:
                answers = json.load(handle)
            kind = "lua" if args[1].startswith("hl.") else "legacy"
            print(answers[kind])
    elif name == "herdr":
        if args[:2] == ["api", "snapshot"]:
            emit("snapshot.json")
        elif args[:2] == ["tab", "focus"]:
            pass
        else:
            sys.exit("unexpected herdr call")
    """)


class FakeHerdrSocket:
    """A herdr session socket that answers socket API calls.

    Like a real server it may send other lines first; the answer to a
    request carries its id. Received requests are kept in `requests`.
    """

    def __init__(self, path):
        self.requests = []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(4)
        self.server.settimeout(10)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                buf = b""
                while b"\n" not in buf:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                if not buf:
                    continue
                request = json.loads(buf.split(b"\n", 1)[0])
                self.requests.append(request)
                conn.sendall(b'{"event":"pane.updated"}\n')
                conn.sendall((json.dumps({"id": request["id"], "result": {}}) + "\n").encode())

    def close(self):
        self.server.close()


class CliCase(unittest.TestCase):

    def setUp(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("needs /proc")
        # Unix socket paths are limited to ~108 bytes: keep the root short.
        self.tmp = tempfile.mkdtemp(prefix="swi", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.stub = os.path.join(self.tmp, "stub")
        self.config = os.path.join(self.tmp, "cfg")
        os.makedirs(self.stub)
        os.makedirs(self.config)
        for name in ("hyprctl", "herdr", "notify-send"):
            path = os.path.join(self.stub, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(STUB.format(python=sys.executable))
            os.chmod(path, 0o755)

        with open(os.path.join(FIXTURES, "hyprctl-clients.json"), encoding="utf-8") as handle:
            self.clients = json.load(handle)
        for index, client in enumerate(self.clients):
            client["pid"] = NO_PID + index
        with open(os.path.join(FIXTURES, "herdr-snapshot.json"), encoding="utf-8") as handle:
            self.snapshot = json.load(handle)
        self.active = PLAIN_ADDRESS
        self.dispatch = {"lua": "ok", "legacy": "error: unknown dispatcher"}

    # -- environment --------------------------------------------------------

    def write_state(self):
        files = {
            "clients.json": self.clients,
            "monitors.json": MONITORS,
            "activewindow.json": {"address": self.active},
            "snapshot.json": self.snapshot,
            "dispatch.json": self.dispatch,
        }
        for name, data in files.items():
            with open(os.path.join(self.stub, name), "w", encoding="utf-8") as handle:
                json.dump(data, handle)

    def env(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
        env.update(PATH=self.stub + os.pathsep + env.get("PATH", ""),
                   XDG_CONFIG_HOME=self.config, SWITCHR_STUB_DIR=self.stub,
                   # as if the overlay were started from inside a herdr pane
                   HERDR_ENV="1", HERDR_PANE_ID="w9:p9")
        return env

    def calls(self, name=None):
        path = os.path.join(self.stub, "calls.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as handle:
            calls = [json.loads(line) for line in handle]
        return [c for c in calls if name is None or c["name"] == name]

    def session_socket(self, name="Earth"):
        path = os.path.join(self.config, "herdr", "sessions", name, "herdr.sock")
        os.makedirs(os.path.dirname(path))
        server = FakeHerdrSocket(path)
        self.addCleanup(server.close)
        return path, server

    def terminal_running_herdr(self, *herdr_args):
        """A process standing in for a terminal window, with a child whose
        argv[0] is `herdr` -- the shape herdr_target() looks for."""
        child = " ".join(["exec -a herdr", sys.executable, "-c 'import time; time.sleep(60)'"]
                         + ["'{}'".format(a) for a in herdr_args])
        proc = subprocess.Popen(["bash", "-c", "({}) & wait".format(child)])
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            for kid in self.children(proc.pid):
                with open("/proc/{}/cmdline".format(kid), "rb") as handle:
                    if handle.read().split(b"\0")[0] == b"herdr":
                        self.addCleanup(self.kill, kid)
                        return proc.pid
            time.sleep(0.02)
        self.fail("herdr child did not start")

    @staticmethod
    def children(pid):
        kids = []
        for tid in os.listdir("/proc/{}/task".format(pid)):
            with open("/proc/{}/task/{}/children".format(pid, tid), encoding="ascii") as handle:
                kids.extend(int(k) for k in handle.read().split())
        return kids

    @staticmethod
    def kill(pid):
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass

    def set_pid(self, address, pid):
        for client in self.clients:
            if client["address"] == address:
                client["pid"] = pid

    # -- running the helper -------------------------------------------------

    def run_helper(self, *args):
        self.write_state()
        return subprocess.run([sys.executable, "-B", HELPER] + list(args),
                              capture_output=True, text=True, timeout=20, env=self.env())

    def collect(self):
        proc = self.run_helper("collect")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.by_id = {e["id"]: e for e in doc["entries"]}
        return doc


class TestCollect(CliCase):

    def test_herdr_session_from_the_real_process_tree(self):
        sock, _ = self.session_socket()
        self.set_pid(HERDR_ADDRESS, self.terminal_running_herdr("--session", "Earth"))
        self.active = HERDR_ADDRESS
        doc = self.collect()

        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["errors"], [])
        tab = self.by_id["htab:Earth:w3:t5"]
        self.assertEqual(tab["parent"], "win:" + HERDR_ADDRESS)
        self.assertEqual(tab["target"]["herdr"]["socket"], sock)
        active = [e["id"] for e in doc["entries"] if e["active"]]
        self.assertEqual(active, ["win:" + HERDR_ADDRESS, "hpane:Earth:w3:p7"])

        snapshots = self.calls("herdr")
        self.assertEqual([c["args"] for c in snapshots], [["api", "snapshot"]])
        # no HERDR_* of the caller leaks into the herdr call
        self.assertEqual(snapshots[0]["env"], {"HERDR_SOCKET_PATH": sock})

    def test_session_option_with_equals_sign(self):
        self.session_socket()
        self.set_pid(HERDR_ADDRESS, self.terminal_running_herdr("--session=Earth"))
        self.collect()
        self.assertIn("htab:Earth:w3:t5", self.by_id)

    def test_remote_session_is_a_hint_and_not_queried(self):
        self.set_pid(HERDR_ADDRESS, self.terminal_running_herdr("--remote=build"))
        doc = self.collect()
        hint = self.by_id["hint:win:" + HERDR_ADDRESS]
        self.assertIn("--remote build", hint["label"])
        self.assertEqual(self.calls("herdr"), [])
        self.assertTrue(doc["errors"])

    def test_null_snapshot_keeps_the_document(self):
        self.session_socket()
        self.set_pid(HERDR_ADDRESS, self.terminal_running_herdr("--session", "Earth"))
        self.snapshot = {"id": "x", "result": {"snapshot": None}}
        self.collect()
        self.assertIn("nothing readable", self.by_id["hint:win:" + HERDR_ADDRESS]["label"])
        self.assertIn("win:" + PLAIN_ADDRESS, self.by_id)

    def test_unreadable_clients_is_exit_1_with_a_document(self):
        self.clients = "not a list"
        proc = self.run_helper("collect")
        self.assertEqual(proc.returncode, 1)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["entries"], [])
        self.assertTrue(doc["errors"])


class TestJump(CliCase):

    def dispatched(self):
        return [c["args"][1] for c in self.calls("hyprctl") if c["args"][:1] == ["dispatch"]]

    def test_label_starting_with_a_dash(self):
        proc = self.run_helper("jump", "--address=" + PLAIN_ADDRESS, "--label=-zsh")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(self.dispatched(),
                         ['hl.dsp.focus({ window = "address:%s" })' % PLAIN_ADDRESS])
        self.assertEqual(self.calls("notify-send"), [])

    def test_legacy_dispatcher_fallback(self):
        self.dispatch = {"lua": "error: invalid dispatcher", "legacy": "ok"}
        proc = self.run_helper("jump", "--address=" + PLAIN_ADDRESS)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(self.dispatched()[-1], "focuswindow address:" + PLAIN_ADDRESS)

    def test_closed_window_is_reported_not_dispatched(self):
        proc = self.run_helper("jump", "--address=0xdeadbeef", "--label=Gone")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.dispatched(), [])
        notes = self.calls("notify-send")
        self.assertEqual(len(notes), 1)
        self.assertIn("closed", notes[0]["args"][-1])

    def test_pane_focus_over_the_real_socket(self):
        sock, server = self.session_socket()
        proc = self.run_helper("jump", "--address=" + HERDR_ADDRESS, "--herdr-socket=" + sock,
                               "--tab-id=w3:t5", "--pane-id=w3:p7")
        self.assertEqual(proc.stderr, "")
        self.assertEqual([(r["method"], r["params"]) for r in server.requests],
                         [("pane.focus", {"pane_id": "w3:p7"})])
        self.assertEqual(len(self.dispatched()), 1)

    def test_tab_focus_over_the_cli(self):
        sock, _ = self.session_socket()
        self.run_helper("jump", "--address=" + HERDR_ADDRESS, "--herdr-socket=" + sock,
                        "--tab-id=w3:t5")
        tab = [c for c in self.calls("herdr") if c["args"][:2] == ["tab", "focus"]]
        self.assertEqual([c["args"] for c in tab], [["tab", "focus", "w3:t5"]])
        self.assertEqual(tab[0]["env"], {"HERDR_SOCKET_PATH": sock})


NODE_JUMP = """
const fs = require("fs")
const src = fs.readFileSync(process.argv[1], "utf8").replace(/^\\.pragma library\\s*$/m, "")
const Model = new Function(src + "; return { jumpCommand }")()
const entry = JSON.parse(fs.readFileSync(0, "utf8"))
process.stdout.write(JSON.stringify(Model.jumpCommand(process.argv[2], entry)))
"""


class TestOverlayContract(CliCase):
    """collect -> SwitchrModel.jumpCommand (Node) -> jump."""

    def setUp(self):
        super().setUp()
        self.node = shutil.which("node")
        if self.node is None:
            if os.environ.get("SWITCHR_REQUIRE_NODE") == "1":
                self.fail("node is required (SWITCHR_REQUIRE_NODE=1)")
            self.skipTest("node not installed")

    def overlay_argv(self, entry):
        proc = subprocess.run([self.node, "-e", NODE_JUMP, MODEL, HELPER],
                              input=json.dumps(entry), capture_output=True, text=True,
                              timeout=20, check=True)
        argv = json.loads(proc.stdout)
        self.assertEqual(argv[:2], ["python3", "-B"])
        return [sys.executable] + argv[1:]

    def test_collected_pane_named_dash_zsh_is_reached(self):
        sock, server = self.session_socket()
        self.set_pid(HERDR_ADDRESS, self.terminal_running_herdr("--session", "Earth"))
        for pane in self.snapshot["result"]["snapshot"]["panes"]:
            if pane["pane_id"] == "w3:p7":
                pane["terminal_title"] = "-zsh"
        self.collect()
        entry = self.by_id["hpane:Earth:w3:p7"]
        self.assertEqual(entry["label"], "-zsh")

        argv = self.overlay_argv(entry)
        self.write_state()
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=20, env=self.env())
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        self.assertEqual([r["params"] for r in server.requests], [{"pane_id": "w3:p7"}])
        dispatches = [c for c in self.calls("hyprctl") if c["args"][:1] == ["dispatch"]]
        self.assertEqual(len(dispatches), 1)
        self.assertIn(HERDR_ADDRESS, dispatches[0]["args"][1])


if __name__ == "__main__":
    unittest.main()
