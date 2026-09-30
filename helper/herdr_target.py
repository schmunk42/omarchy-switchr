#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-09-30 13:15:46 UTC
"""Find the herdr session that runs inside a terminal window.

Provenance: this module is a deliberate copy of `herdr_target()` and the
/proc helpers it depends on from the author's `schmunk42-terminal-cwd`
watcher script (an ActivityWatch cwd watcher), translated to English and
trimmed to what switchr needs. It is copied rather than imported so that
the plugin carries no dependency on scripts outside its own directory.
Changes against the original: messages in English, the herdr config
directory is resolved at call time (`herdr_config_dir()`) instead of at
import, and the terminal class set also lists kitty and Alacritty.

Why this is needed: herdr is not a window class of its own but a layer
INSIDE a foot/ghostty/... window -- a client in the window, a server next to
it, and the shells hang below the server. The only direct child of such a
window is the shell that started herdr, and its cwd is the window's
--working-directory, which never moves. A /proc lookup therefore returns a
value that looks valid and is wrong; the real answer comes from herdr
itself, via the socket of the session.
"""

import os
import socket
import sys
from collections import namedtuple
from pathlib import Path

sys.dont_write_bytecode = True

HOSTNAME = socket.gethostname()

# Window classes that count as terminals. `footclient` is listed although
# it can never be resolved (all windows of a `foot --server` share its PID):
# recognised as a terminal, the shared-PID check fires and the answer is
# "cannot be resolved" instead of "not a terminal".
TERMINAL_CLASSES = {
    "com.mitchellh.ghostty", "foot", "footclient", "kitty", "Alacritty", "alacritty",
}

# Hard cap for every herdr call. Not a comfort value: a herdr client call
# against the socket of a --remote session was observed to never answer.
HERDR_TIMEOUT = 3.0

# How many descendants of a window are searched at most before giving up on
# finding the herdr client. A terminal window has a handful; the limit only
# catches the degenerate case.
TREE_LIMIT = 200

HerdrTarget = namedtuple("HerdrTarget", "session sock host problem")


def herdr_config_dir():
    """Where herdr keeps its session sockets ($XDG_CONFIG_HOME/herdr)."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "herdr"


def children_of(pid):
    """The direct child processes of a PID.

    Read from /proc/<pid>/task/*/children: `children` is per THREAD, not
    per process, and multithreaded terminals fork the shell from any of
    their threads -- reading only the main thread's file misses it.
    """
    kids = []
    try:
        threads = os.listdir("/proc/{}/task".format(pid))
    except OSError:
        return kids
    for tid in threads:
        try:
            with open("/proc/{}/task/{}/children".format(pid, tid), encoding="ascii") as handle:
                kids.extend(int(entry) for entry in handle.read().split())
        except (OSError, ValueError):
            continue
    return kids


def start_time_of(pid):
    """Start time in clock ticks since boot, used to order child shells."""
    try:
        with open("/proc/{}/stat".format(pid), encoding="utf-8", errors="replace") as handle:
            stat = handle.read()
    except OSError:
        return None
    # The process name is field 2 in parentheses and may itself contain
    # spaces and parentheses -- split after the LAST closing one. What
    # follows starts with field 3 (state); starttime is field 22.
    tail = stat[stat.rfind(")") + 2:].split()
    try:
        return int(tail[19])
    except (IndexError, ValueError):
        return None


def cwd_of_window(pid):
    """The working directory of the youngest child process of a window.

    Not necessarily a shell: a terminal may be started as `ghostty -e
    claude`, then claude hangs directly below the window. Its cwd is the
    same, so the answer stays right.
    """
    kids = children_of(pid)
    if not kids:
        return None
    kids.sort(key=lambda child: (start_time_of(child) or 0, child))
    for child in reversed(kids):
        try:
            return os.readlink("/proc/{}/cwd".format(child))
        except OSError:
            continue
    return None


def cmdline_of(pid):
    """The command line of a PID as a list, or an empty list."""
    try:
        with open("/proc/{}/cmdline".format(pid), "rb") as handle:
            raw = handle.read()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def environ_of(pid):
    """The environment of a PID as a dict, or an empty dict."""
    found = {}
    try:
        with open("/proc/{}/environ".format(pid), "rb") as handle:
            raw = handle.read()
    except OSError:
        return found
    for entry in raw.split(b"\0"):
        if b"=" not in entry:
            continue
        key, _, value = entry.partition(b"=")
        found[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return found


def descendants(pid):
    """The descendants of a PID, breadth first -- the nearest ones first.

    Breadth first because the herdr client sits right below the window,
    while the process of the same name `herdr server` hangs one level
    deeper. A depth-first search would find the server.

    A generator rather than a list: the caller stops at the first herdr,
    which is usually the second or third process.
    """
    seen = {pid}
    queue = [pid]
    visited = 0
    while queue and visited < TREE_LIMIT:
        for kid in children_of(queue.pop(0)):
            if kid in seen:
                continue
            seen.add(kid)
            visited += 1
            queue.append(kid)
            yield kid
            if visited >= TREE_LIMIT:
                return


def herdr_target(window_pid):
    """Which herdr session runs in this window, or None.

    None means: no herdr runs in this window. A return value with `problem`
    set means herdr is there but its session cannot be resolved -- callers
    must then NOT fall back to the /proc cwd, whose plausible wrong value is
    exactly the error this function exists to avoid.
    """
    for pid in descendants(window_pid):
        argv = cmdline_of(pid)
        if not argv or os.path.basename(argv[0]) != "herdr":
            continue
        rest = argv[1:]

        # `herdr server` is the server, not the client in the window. It can
        # only show up if the client was skipped -- then something differs
        # from the assumptions, and guessing would be wrong.
        if rest[:1] == ["server"] or rest[:1] == ["client"]:
            continue

        # Monolithic run: no server and no socket, the panes hang directly
        # below the herdr process.
        if "--no-session" in rest:
            return HerdrTarget(None, None, None,
                               "herdr runs with --no-session; without a socket "
                               "the session cannot be queried")

        # A session on another machine: the panes live there. The socket is
        # in the environment of the client child process, not the starter.
        if "--remote" in rest:
            index = rest.index("--remote")
            host = rest[index + 1] if index + 1 < len(rest) else None
            for kid in descendants(pid):
                if cmdline_of(kid)[1:2] == ["client"]:
                    sock = environ_of(kid).get("HERDR_CLIENT_SOCKET_PATH")
                    if sock:
                        return HerdrTarget("remote:{}".format(host), sock, host, None)
            return HerdrTarget(None, None, host,
                               "herdr --remote {}: no client with "
                               "HERDR_CLIENT_SOCKET_PATH in the process tree".format(host))

        if "--session" in rest:
            index = rest.index("--session")
            name = rest[index + 1] if index + 1 < len(rest) else None
        elif rest[:2] == ["session", "attach"]:
            name = rest[2] if len(rest) > 2 else None
        else:
            name = "default"

        if not name:
            return HerdrTarget(None, None, None,
                               "herdr without a resolvable session name: " + " ".join(argv))

        # herdr's convention: the session "default" lives in the config
        # directory itself, every named one in sessions/<name>. Names are
        # case-sensitive -- "Earth" and "earth" are two sessions.
        config = herdr_config_dir()
        sock = (config / "herdr.sock") if name == "default" \
            else (config / "sessions" / name / "herdr.sock")
        if not sock.is_socket():
            return HerdrTarget(name, None, None,
                               "session {}: no socket at {}".format(name, sock))
        return HerdrTarget(name, str(sock), HOSTNAME, None)
    return None
