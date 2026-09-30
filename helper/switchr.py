#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-09-30 19:16:18 UTC
"""switchr helper -- collect jump targets and jump to one of them.

Two subcommands, both usable without a TTY and without any HERDR_*
variable in the environment (the overlay starts them detached):

    switchr.py collect [--pretty]
        Print exactly one JSON document (Format Version 1, below) on stdout:
        every mapped window of every workspace including the special
        workspaces, the tabs of a Hyprland group below their group, and for
        every terminal window running a herdr session that session's tabs
        and panes.

    switchr.py jump --address 0x... [--herdr-socket PATH --tab-id T
                    [--pane-id P]] [--label L]
        Check the address against a fresh `hyprctl -j clients`, focus the
        herdr pane (socket API `pane.focus`, when --pane-id is given) or
        tab (`herdr tab focus`, when only --tab-id is given), then focus the
        window. Always exits 0; problems go to notify-send (if available)
        and stderr. --label is only used in messages.

Exit status of `collect`: 0 as soon as the window list from Hyprland was
readable -- also when herdr is missing entirely or partly (that shows up as
an entry of type `hint` in the document and additionally under `errors`).
1 when `hyprctl -j clients` is not readable; a valid document with an empty
`entries` list is printed anyway.


Format (Version 1)
==================

Top level, one JSON object:

    version       int     Format version, currently 1. An incompatible
                          change increments it; new fields do not.
    generated_at  string  Time of collection, ISO 8601 in UTC.
    host          string  Host name (socket.gethostname()).
    errors        [string] Sources that were missing or did not answer, as a
                          readable sentence. Empty when everything was there.
    entries       [Entry] All entries, already in display order.

An Entry:

    id          string  Stable identifier, unique within the document:
                          win:<address>                  type window and group_tab
                          htab:<session>:<tab_id>        type herdr_tab
                          hpane:<session>:<pane_id>      type herdr_pane
                          hint:<id of the parent entry>  type hint
                        <session> is the herdr session name (case-sensitive);
                        herdr ids such as `w2:t5` repeat between sessions and
                        are therefore never unique without the session. The
                        identifier contains no tab and no line break.
    type        string  window | group_tab | herdr_tab | herdr_pane | hint
                          window     a window; for a Hyprland group exactly
                                     ONE per group, namely the visible tab.
                          group_tab  the other tabs of a group, in the order
                                     of the group bar.
                          herdr_tab  a tab of a herdr session. A tab with
                                     exactly one pane is a single entry that
                                     already carries that pane (label, title,
                                     cwd, agent, pane_id); it has no
                                     herdr_pane child.
                          herdr_pane a pane of a tab with two or more panes,
                                     one per pane below its herdr_tab.
                          hint       a notice instead of content ("tabs not
                                     available", timeout, error). Informational
                                     only, not a jump target, although
                                     target.address is set (the parent's
                                     window); the overlay does not make it
                                     selectable.
    parent      string|null  id of the parent entry; null for window.
    depth       int     Indentation depth: window 0, group_tab 0 (a group
                        is windows side by side, not a hierarchy; `parent`
                        still names the head), herdr_tab one level below its
                        window, herdr_pane one below its tab, hint one below
                        its parent.
    sort_key    [int]   Lexicographically comparable sort key; `entries` is
                        already sorted by it. Layout:
                        [workspace rank, window rank, group tab rank,
                        herdr workspace number, herdr tab number, pane rank].
                        Workspace rank: the Hyprland id 1..n, then 1000
                        special:scratchpad, 1001 special:docs, 1002 other
                        specials, 2000 anything unexpected. Window rank:
                        position within the workspace by focusHistoryID.
                        Group tab rank: position in `grouped`, -1 for the
                        head of the group and for every window without a
                        group. -1 at a position means "the entry itself", so
                        that it sorts before its children: window
                        [w, f, -1, -1, -1, -1], group_tab [w, f, g, -1, -1, -1],
                        herdr_tab [w, f, g, hw, ht, -1], herdr_pane
                        [w, f, g, hw, ht, p], hint [w, f, g, 0, 0, 0] -- the
                        herdr entries take the first three positions from
                        their window, i.e. -1 at position 3 below a window.
    workspace   object  Hyprland workspace the window is on:
                          id       int     Hyprland id (specials negative)
                          name     string  Hyprland name, e.g. "6" or
                                           "special:docs"
                          label    string  short label (see "Workspace
                                           labels" below)
                          title    string  long name (see below)
                          special  bool    true for special:*
    monitor     string|null  Name of the monitor (e.g. "DP-2"), if known.
    label       string  Main line: window title; for herdr_tab with two or
                        more panes "<herdr workspace> › <tab>", for a
                        single-pane herdr_tab and for herdr_pane the
                        terminal title (emojis such as ✳/◐ are kept), for
                        hint the notice text. Tab, line feed and CR are
                        replaced by spaces.
    detail      string  Secondary line, already composed for reading, parts
                        joined by " · ", null parts left out, e.g.
                        "foot · ~/Work/project · herdr Earth". herdr_tab with
                        two or more panes: "<status> · N panes · <cwd>";
                        single-pane herdr_tab: "<herdr workspace> › <tab> ·
                        <cwd> · <agent> · <pane status>"; herdr_pane:
                        "<cwd> · <agent> · <status>".
    class       string|null  Window class (window/group_tab only).
    title       string|null  Window title or terminal title (cleaned); on a
                        herdr_tab only when it has exactly one pane.
    cwd         string|null  Working directory: for herdr the foreground_cwd
                        of the shown pane, for a terminal without herdr that
                        of the youngest child shell.
    agent       string|null  herdr: detected agent ("claude") or null. On a
                        window with herdr: that of the pane focused in the
                        session; on a herdr_tab: that of the pane shown there.
    agent_status string|null herdr: idle | working | blocked | done | unknown,
                        assigned like `agent`; on a herdr_tab the tab status.
    active      bool    window: the focused window of the desktop.
                        group_tab: never (the visible tab is the window
                        entry). herdr_tab/-pane: the tab focused in herdr,
                        or the pane shown in its tab.
    target      object  Jump target:
                          address  string  Hyprland window address "0x…",
                                           always set
                          herdr    object|null  only for herdr_tab/herdr_pane:
                            session       string  session name
                            socket        string  path to herdr.sock
                            workspace_id  string  herdr id, e.g. "w2"
                            tab_id        string  e.g. "w2:t5"
                            pane_id       string|null  e.g. "w2:p7"; on a
                                          herdr_tab the pane shown there

Example (shortened to one window with one single-pane herdr tab, which is
therefore one entry without a herdr_pane child; the "hint" entry comes from
a run in which the same window was a herdr --remote session):

    {
      "version": 1,
      "generated_at": "2026-09-29T08:56:18+00:00",
      "host": "host",
      "errors": [],
      "entries": [
        {
          "id": "win:0x55afe5bbd340", "type": "window", "parent": null,
          "depth": 0, "sort_key": [7, 0, -1, -1, -1, -1],
          "workspace": {"id": 7, "name": "7", "label": "7",
                        "title": "7", "special": false},
          "monitor": "DP-2", "label": "host: project",
          "detail": "foot · ~/Work/project · herdr Mars",
          "class": "foot", "title": "host: project",
          "cwd": "/home/user/Work/project",
          "agent": null, "agent_status": "unknown", "active": false,
          "target": {"address": "0x55afe5bbd340", "herdr": null}
        },
        {
          "id": "htab:Mars:w2:t5", "type": "herdr_tab",
          "parent": "win:0x55afe5bbd340",
          "depth": 1, "sort_key": [7, 0, -1, 1, 5, -1],
          "workspace": {"id": 7, "name": "7", "label": "7",
                        "title": "7", "special": false},
          "monitor": "DP-2", "label": "✳ Claude session",
          "detail": "project › 2 · ~/Work/project · claude · idle",
          "class": null, "title": "✳ Claude session",
          "cwd": "/home/user/Work/project",
          "agent": "claude", "agent_status": "idle", "active": false,
          "target": {"address": "0x55afe5bbd340",
                     "herdr": {"session": "Mars",
                               "socket": "/home/user/.config/herdr/sessions/Mars/herdr.sock",
                               "workspace_id": "w2", "tab_id": "w2:t5",
                               "pane_id": "w2:p7"}}
        },
        {
          "id": "hint:win:0x55afe5bbd340", "type": "hint",
          "parent": "win:0x55afe5bbd340",
          "depth": 1, "sort_key": [7, 0, -1, 0, 0, 0],
          "workspace": {"id": 7, "name": "7", "label": "7",
                        "title": "7", "special": false},
          "monitor": "DP-2",
          "label": "Tabs not available (herdr --remote build-host)",
          "detail": "Hint · host: project",
          "class": null, "title": null, "cwd": null,
          "agent": null, "agent_status": null, "active": false,
          "target": {"address": "0x55afe5bbd340", "herdr": null}
        }
      ]
    }


Where the data comes from
=========================

Windows from `hyprctl -j clients` (only `mapped`). Order: workspaces
numerically, then special:scratchpad, special:docs and other specials;
within a workspace by `focusHistoryID`, most recently used first.

Workspace labels: by default `label` and `title` are the Hyprland workspace
name; for a special workspace the label is the first letter of its name
without the `special:` prefix, upper-cased ("S" for special:scratchpad),
and the title is that name capitalised ("Scratchpad"). An optional file
$XDG_CONFIG_HOME/schmunk42-switchr/config.json may set:

    labels         {key: short label}
    names          {key: long title}
    shellWidgetId  string -- take `labels` and `clockNames` from the widget
                   with this `id` anywhere in $XDG_CONFIG_HOME/omarchy/shell.json

A key is the workspace id as a string ("6", "-98"), the full name
("special:docs") or the name without the special prefix ("docs"). Explicit
`labels`/`names` win over the widget. A missing config file is silent; a
malformed one, or a configured widget that cannot be found, is reported
under `errors`.

Groups: all members carry the same `grouped`. The visible tab is the member
with `visible: true`, otherwise the one with the lowest `focusHistoryID`;
it becomes the window entry, the others follow as group_tab in the order
of `grouped`, on the same depth as the window entry (0): the tabs of a group
are siblings, `parent` only records which one is the head.

herdr: which session runs in a terminal window is determined by
`herdr_target()` (helper/herdr_target.py). Per session exactly one call
`herdr api snapshot` (workspaces, tabs, panes and layouts in one answer),
all sessions in parallel, each call with a hard timeout, all together
within SNAPSHOT_BUDGET seconds. When a session is shown in several windows,
the window with the lowest `focusHistoryID` gets the tabs; the others show
none. herdr over `--remote` is not queried (its client socket does not
answer), a hint "Tabs not available" is shown instead. Stopped sessions do
not appear, because no window shows them.
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Deliberate copy of the herdr session detection from the author's
# `schmunk42-terminal-cwd` script, see the provenance note in the module;
# the original is not imported.
import herdr_target as ht  # noqa: E402

FORMAT_VERSION = 1
APP = "switchr"

# Overall deadline for all herdr queries together, measured from the start
# of the collection. Below the budget of the whole collector, so that
# hyprctl and /proc before it and the JSON output after it still fit.
SNAPSHOT_BUDGET = 2.5
HERDR_TIMEOUT = ht.HERDR_TIMEOUT

# Rank of the special workspaces in `sort_key` (part of Format Version 1).
SPECIAL_ORDER = ["special:scratchpad", "special:docs"]

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]+$")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def clean(text):
    """Replace tab, line feed and CR by spaces.

    Consumers may build tab-separated lines; a tab in a title would shift
    the fields there, a line break would split the entry in two.
    """
    if text is None:
        return ""
    return str(text).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def short_path(path):
    if not path:
        return ""
    home = str(Path.home())
    if path == home or path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def hyprctl(command):
    """One `hyprctl -j <command>` query as parsed JSON, or None."""
    try:
        proc = subprocess.run(["hyprctl", "-j", command],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError:
        return None


def herdr_env(sock=None):
    """The environment for a herdr call, without any HERDR_* variable.

    When the helper runs inside a herdr pane itself, herdr would otherwise
    refuse with "nested herdr" or query its own session instead of the
    intended one.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
    if sock:
        env["HERDR_SOCKET_PATH"] = sock
    return env


# ---------------------------------------------------------------------------
# Workspace labels
# ---------------------------------------------------------------------------

def config_home():
    return Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser()


def config_path():
    return config_home() / "schmunk42-switchr" / "config.json"


def shell_json_path():
    return config_home() / "omarchy" / "shell.json"


def find_widget(node, widget_id):
    """The widget with this `id` anywhere in shell.json.

    Searched by id and not by position in the layout: a fixed index points
    silently at another widget as soon as one is added.
    """
    if isinstance(node, dict):
        if node.get("id") == widget_id:
            return node
        values = node.values()
    elif isinstance(node, list):
        values = node
    else:
        return None
    for value in values:
        found = find_widget(value, widget_id)
        if found is not None:
            return found
    return None


def load_labels(errors):
    """Workspace labels and titles as two dicts (key -> string)."""
    path = config_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}, {}  # no config is the normal case
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as err:
        errors.append("{} is not valid JSON ({}), workspace labels ignored".format(path, err))
        return {}, {}
    if not isinstance(config, dict):
        errors.append("{} is not a JSON object, workspace labels ignored".format(path))
        return {}, {}

    labels, names = {}, {}
    widget_id = config.get("shellWidgetId")
    if widget_id is not None:
        if not isinstance(widget_id, str) or not widget_id:
            errors.append("{}: shellWidgetId must be a non-empty string".format(path))
        else:
            shell = shell_json_path()
            try:
                widget = find_widget(json.loads(shell.read_text(encoding="utf-8")), widget_id)
            except (OSError, json.JSONDecodeError) as err:
                errors.append("{} not readable ({}), widget labels missing".format(shell, err))
                widget = None
            else:
                if widget is None:
                    errors.append("widget {} not found in {}, widget labels missing"
                                  .format(widget_id, shell))
            if widget is not None:
                if isinstance(widget.get("labels"), dict):
                    labels.update(widget["labels"])
                if isinstance(widget.get("clockNames"), dict):
                    names.update(widget["clockNames"])

    for field, target in (("labels", labels), ("names", names)):
        value = config.get(field)
        if value is None:
            continue
        if not isinstance(value, dict):
            errors.append("{}: {} must be an object".format(path, field))
            continue
        target.update(value)
    return labels, names


def lookup(mapping, wid, name):
    """The configured value for a workspace: by id, full name, bare name."""
    keys = [str(wid), name]
    if name.startswith("special:"):
        keys.append(name[len("special:"):])
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return None


def workspace_info(ws, labels, names):
    wid = ws.get("id")
    name = str(ws.get("name") or wid)
    special = name.startswith("special:")
    if special:
        bare = name[len("special:"):]
        default_label = bare[:1].upper() if bare else name
        default_title = (bare[:1].upper() + bare[1:]) if bare else name
    else:
        default_label = default_title = name
    label = lookup(labels, wid, name) or default_label
    title = lookup(names, wid, name) or default_title
    return {"id": wid, "name": name, "label": clean(label), "title": clean(title),
            "special": special}


def workspace_rank(ws):
    """Normal workspaces numerically, then the specials."""
    wid = ws.get("id")
    name = str(ws.get("name") or "")
    if name.startswith("special:"):
        extra = SPECIAL_ORDER.index(name) if name in SPECIAL_ORDER else len(SPECIAL_ORDER)
        return 1000 + extra
    if isinstance(wid, int) and wid > 0:
        return wid
    return 2000  # anything unexpected goes last, but is not lost


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------

def fetch_snapshot(sock, deadline):
    """One `herdr api snapshot` against a socket, as (snapshot, problem)."""
    timeout = max(0.1, min(HERDR_TIMEOUT, deadline - time.monotonic()))
    try:
        proc = subprocess.run(["herdr", "api", "snapshot"], capture_output=True,
                              text=True, timeout=timeout, env=herdr_env(sock))
    except subprocess.TimeoutExpired:
        return None, "herdr did not answer within {:.1f} s".format(timeout)
    except OSError as err:
        return None, "herdr not executable: {}".format(err)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return None, "herdr api snapshot failed: " + (detail[0] if detail else "no message")
    try:
        return json.loads(proc.stdout)["result"]["snapshot"], None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, "herdr api snapshot returned nothing readable"


def entry(**fields):
    base = {
        "id": None, "type": None, "parent": None, "depth": 0, "sort_key": [],
        "workspace": None, "monitor": None, "label": "", "detail": "",
        "class": None, "title": None, "cwd": None, "agent": None,
        "agent_status": None, "active": False,
        "target": {"address": None, "herdr": None},
    }
    base.update(fields)
    return base


def join_detail(*parts):
    return " · ".join(clean(p) for p in parts if p)


def pane_title(pane):
    return clean(pane.get("terminal_title")) or clean(pane.get("agent")) or pane.get("pane_id")


def herdr_entries(parent, snap, session, sock, depth, key_prefix, ws, monitor):
    """Tabs and panes of a session below its window."""
    out = []
    address = parent["target"]["address"]
    ws_labels = {w.get("workspace_id"): clean(w.get("label")) or str(w.get("number"))
                 for w in snap.get("workspaces") or []}
    ws_numbers = {w.get("workspace_id"): w.get("number") or 0
                  for w in snap.get("workspaces") or []}
    shown_pane = {lay.get("tab_id"): lay.get("focused_pane_id")
                  for lay in snap.get("layouts") or []}
    focused_tab = snap.get("focused_tab_id")
    panes_by_tab = {}
    for pane in snap.get("panes") or []:
        panes_by_tab.setdefault(pane.get("tab_id"), []).append(pane)

    tabs = sorted(snap.get("tabs") or [],
                  key=lambda t: (ws_numbers.get(t.get("workspace_id"), 0), t.get("number") or 0))
    for tab in tabs:
        tab_id = tab.get("tab_id")
        wsid = tab.get("workspace_id")
        panes = panes_by_tab.get(tab_id, [])
        shown = shown_pane.get(tab_id)
        shown_obj = next((p for p in panes if p.get("pane_id") == shown),
                         panes[0] if panes else None)
        cwd = (shown_obj or {}).get("foreground_cwd") or (shown_obj or {}).get("cwd")
        count = len(panes)
        tab_path = "{} › {}".format(ws_labels.get(wsid, wsid), clean(tab.get("label")))
        tab_entry = entry(
            id="htab:{}:{}".format(session, tab_id), type="herdr_tab", parent=parent["id"],
            depth=depth,
            sort_key=key_prefix + [ws_numbers.get(wsid, 0), tab.get("number") or 0, -1],
            workspace=ws, monitor=monitor,
            label=tab_path,
            detail=join_detail(tab.get("agent_status"),
                               "{} panes".format(count), short_path(cwd)),
            cwd=cwd, agent=(shown_obj or {}).get("agent"),
            agent_status=tab.get("agent_status"),
            active=tab_id == focused_tab,
            target={"address": address, "herdr": {
                "session": session, "socket": sock, "workspace_id": wsid,
                "tab_id": tab_id, "pane_id": shown}},
        )
        if count == 1:
            # A tab with exactly one pane is a single row: the pane's title
            # is the informative line, and a child row would only repeat
            # the same jump target.
            pane = panes[0]
            pcwd = pane.get("foreground_cwd") or pane.get("cwd")
            title = pane_title(pane)
            tab_entry.update(
                label=title, title=title, cwd=pcwd, agent=pane.get("agent"),
                detail=join_detail(tab_path, short_path(pcwd), pane.get("agent"),
                                   pane.get("agent_status")),
            )
            tab_entry["target"]["herdr"]["pane_id"] = pane.get("pane_id")
            out.append(tab_entry)
            continue
        out.append(tab_entry)
        for rank, pane in enumerate(panes):
            pane_id = pane.get("pane_id")
            pcwd = pane.get("foreground_cwd") or pane.get("cwd")
            title = pane_title(pane)
            out.append(entry(
                id="hpane:{}:{}".format(session, pane_id), type="herdr_pane",
                parent=tab_entry["id"], depth=depth + 1,
                sort_key=key_prefix + [ws_numbers.get(wsid, 0), tab.get("number") or 0, rank],
                workspace=ws, monitor=monitor,
                label=title,
                detail=join_detail(short_path(pcwd), pane.get("agent"),
                                   pane.get("agent_status")),
                title=title, cwd=pcwd, agent=pane.get("agent"),
                agent_status=pane.get("agent_status"),
                active=pane_id == shown,
                target={"address": address, "herdr": {
                    "session": session, "socket": sock, "workspace_id": wsid,
                    "tab_id": tab_id, "pane_id": pane_id}},
            ))
    return out


def problem_target(text):
    return ht.HerdrTarget(None, None, None, text)


def hint_for(parent, text):
    return entry(
        id="hint:{}".format(parent["id"]), type="hint", parent=parent["id"],
        depth=parent["depth"] + 1, sort_key=parent["sort_key"][:3] + [0, 0, 0],
        workspace=parent["workspace"], monitor=parent["monitor"],
        label=clean(text), detail=join_detail("Hint", parent["label"]),
        target={"address": parent["target"]["address"], "herdr": None},
    )


def collect():
    """Build the document; returns (document, exit status)."""
    started = time.monotonic()
    errors = []
    doc = {
        "version": FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": ht.HOSTNAME,
        "errors": errors,
        "entries": [],
    }

    clients = hyprctl("clients")
    if not isinstance(clients, list):
        errors.append("hyprctl -j clients not readable")
        return doc, 1
    monitors = hyprctl("monitors")
    monitor_names = {}
    if isinstance(monitors, list):
        monitor_names = {m.get("id"): m.get("name") for m in monitors}
    else:
        errors.append("hyprctl -j monitors not readable, monitor names missing")
    active = hyprctl("activewindow")
    active_address = active.get("address") if isinstance(active, dict) else None

    labels, names = load_labels(errors)

    clients = [c for c in clients if isinstance(c, dict) and c.get("mapped", True)
               and str(c.get("address") or "").startswith("0x")]
    by_address = {c["address"]: c for c in clients}
    pid_count = {}
    for c in clients:
        pid_count[c.get("pid")] = pid_count.get(c.get("pid"), 0) + 1

    def fhid(c):
        value = c.get("focusHistoryID")
        return value if isinstance(value, int) and value >= 0 else 10 ** 6

    # Reduce groups to their visible tab.
    heads = []          # (client, [other members in `grouped` order])
    consumed = set()
    for c in clients:
        if c["address"] in consumed:
            continue
        members = [by_address[a] for a in (c.get("grouped") or []) if a in by_address]
        if len(members) < 2:
            heads.append((c, []))
            consumed.add(c["address"])
            continue
        visible = [m for m in members if m.get("visible")]
        head = visible[0] if len(visible) == 1 else min(members, key=fhid)
        heads.append((head, [m for m in members if m is not head]))
        consumed.update(m["address"] for m in members)

    heads.sort(key=lambda h: (workspace_rank(h[0].get("workspace") or {}), fhid(h[0])))

    window_entries = []     # (entry, client, [(tab_entry, tab_client)])
    ws_seen = {}
    for head, tabs in heads:
        ws_obj = head.get("workspace") or {}
        wrank = workspace_rank(ws_obj)
        wpos = ws_seen.get(wrank, 0)
        ws_seen[wrank] = wpos + 1
        ws = workspace_info(ws_obj, labels, names)
        monitor = monitor_names.get(head.get("monitor"))

        def window_entry(c, etype, parent, depth, key, ws=ws, monitor=monitor):
            title = clean(c.get("title")) or clean(c.get("class")) or c["address"]
            return entry(
                id="win:{}".format(c["address"]), type=etype, parent=parent, depth=depth,
                sort_key=key, workspace=ws, monitor=monitor,
                label=title, title=title,
                active=c["address"] == active_address,
                target={"address": c["address"], "herdr": None},
                **{"class": c.get("class")}
            )

        head_entry = window_entry(head, "window", None, 0, [wrank, wpos, -1, -1, -1, -1])
        tab_entries = []
        for rank, tab in enumerate(tabs):
            te = window_entry(tab, "group_tab", head_entry["id"], 0,
                              [wrank, wpos, rank, -1, -1, -1])
            te["active"] = False
            tab_entries.append((te, tab))
        window_entries.append((head_entry, head, tab_entries))

    # herdr: which windows show a session, and which one gets its tabs.
    # address -> HerdrTarget; a problem without session is in `problem`,
    # as with herdr_target() itself.
    targets = {}
    for head_entry, head, tab_entries in window_entries:
        for ent, client in [(head_entry, head)] + list(tab_entries):
            if client.get("class") not in ht.TERMINAL_CLASSES:
                continue
            pid = client.get("pid")
            if pid_count.get(pid, 0) > 1:
                targets[client["address"]] = problem_target(
                    "{} windows share PID {}, herdr session cannot be resolved"
                    .format(pid_count[pid], pid))
                continue
            try:
                target = ht.herdr_target(pid)
            except Exception as err:  # a /proc error must not cost the rest
                targets[client["address"]] = problem_target("herdr detection: {}".format(err))
                continue
            if target is None:
                cwd = ht.cwd_of_window(pid)
                if cwd:
                    ent["cwd"] = cwd
                continue
            targets[client["address"]] = target

    owners = {}             # socket -> address with the lowest focusHistoryID
    for address, target in targets.items():
        if target.problem or target.host != ht.HOSTNAME:
            continue
        current = owners.get(target.sock)
        if current is None or fhid(by_address[address]) < fhid(by_address[current]):
            owners[target.sock] = address

    deadline = started + SNAPSHOT_BUDGET
    snapshots = {}
    if owners:
        # No `with`: its shutdown(wait=True) would wait for a hanging
        # worker. Every call has its own timeout up to the deadline, so the
        # worker ends there by itself at the latest.
        pool = ThreadPoolExecutor(max_workers=min(8, len(owners)))
        futures = {sock: pool.submit(fetch_snapshot, sock, deadline) for sock in owners}
        for sock, future in futures.items():
            remaining = max(0.05, deadline - time.monotonic() + 0.2)
            try:
                snapshots[sock] = future.result(timeout=remaining)
            except Exception as err:
                snapshots[sock] = (None, "herdr did not answer ({})"
                                   .format(err.__class__.__name__))
        pool.shutdown(wait=False, cancel_futures=True)

    out = []
    for head_entry, head, tab_entries in window_entries:
        for ent, client in [(head_entry, head)] + list(tab_entries):
            target = targets.get(client["address"])
            children = []
            if target is not None:
                if target.problem:
                    errors.append("{}: {}".format(ent["label"], target.problem))
                    children.append(hint_for(ent, target.problem))
                elif target.host != ht.HOSTNAME:
                    children.append(hint_for(
                        ent, "Tabs not available (herdr --remote {})"
                        .format(target.host or "unknown")))
                elif owners.get(target.sock) == client["address"]:
                    snap, problem = snapshots.get(target.sock, (None, "not queried"))
                    if problem:
                        text = "herdr session {}: {}".format(target.session, problem)
                        errors.append(text)
                        children.append(hint_for(ent, text))
                    else:
                        shown = snap.get("focused_pane_id")
                        for pane in snap.get("panes") or []:
                            if pane.get("pane_id") == shown:
                                ent["cwd"] = pane.get("foreground_cwd") or pane.get("cwd")
                                ent["agent"] = pane.get("agent")
                                ent["agent_status"] = pane.get("agent_status")
                        children.extend(herdr_entries(
                            ent, snap, target.session, target.sock, ent["depth"] + 1,
                            ent["sort_key"][:3], ent["workspace"], ent["monitor"]))
            herdr_part = None
            if target is not None and target.session:
                herdr_part = "herdr {}".format(target.session)
            ent["detail"] = join_detail(client.get("class"), short_path(ent["cwd"]), herdr_part)
            out.append(ent)
            out.extend(children)

    doc["entries"] = out
    return doc, 0


def cmd_collect(args):
    doc, status = collect()
    sys.stdout.write(json.dumps(doc, ensure_ascii=False, indent=2 if args.pretty else None))
    sys.stdout.write("\n")
    sys.stdout.flush()
    # os._exit instead of return: a worker still stuck in subprocess.run at
    # the deadline would hold the interpreter at shutdown.
    os._exit(status)


# ---------------------------------------------------------------------------
# jump
# ---------------------------------------------------------------------------

def report(message):
    """Report a problem: notify-send for the detached case, stderr for tests."""
    print("switchr: {}".format(message), file=sys.stderr, flush=True)
    if shutil.which("notify-send") is None:
        return
    try:
        subprocess.run(["notify-send", "--app-name", APP, APP, message],
                       capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def focus_window(address):
    """Focus an address; None on success, otherwise the reason.

    Never with an empty address: `address:` without a value answers `ok`
    too and does nothing. hyprctl writes errors to stdout, which is why the
    answer is checked for exactly `ok`.
    """
    if not address or not ADDRESS_RE.match(address):
        return "no valid window address"
    try:
        proc = subprocess.run(
            ["hyprctl", "dispatch",
             'hl.dsp.focus({{ window = "address:{}" }})'.format(address)],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return "hyprctl not executable: {}".format(err)
    answer = (proc.stdout or "").strip()
    if answer == "ok":
        return None
    return "focus refused: {}".format(answer or (proc.stderr or "").strip() or "no answer")


def herdr_tab_focus(sock, tab_id):
    try:
        proc = subprocess.run(["herdr", "tab", "focus", tab_id], capture_output=True,
                              text=True, timeout=HERDR_TIMEOUT, env=herdr_env(sock))
    except (OSError, subprocess.TimeoutExpired) as err:
        return "herdr tab focus {}: {}".format(tab_id, err)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return "herdr tab focus {}: {}".format(
            tab_id, detail[0] if detail else "exit {}".format(proc.returncode))
    return None


def herdr_rpc(sock, method, params):
    """One call of the herdr socket API (NDJSON, one line out, one back).

    The way to `pane.focus`: the CLI knows `pane focus` only with
    --direction, and `agent focus` only takes panes running an agent.
    """
    request = {"id": "switchr:{}".format(method), "method": method, "params": params}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(HERDR_TIMEOUT)
            conn.connect(sock)
            conn.sendall((json.dumps(request) + "\n").encode())
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except OSError as err:
        return "herdr {}: {}".format(method, err)
    try:
        answer = json.loads(buf.split(b"\n", 1)[0])
    except json.JSONDecodeError:
        return "herdr {}: unreadable answer".format(method)
    if not isinstance(answer, dict):
        return "herdr {}: unreadable answer".format(method)
    if "error" in answer:
        err = answer["error"] or {}
        if isinstance(err, dict):
            err = err.get("message") or err.get("code") or err
        return "herdr {}: {}".format(method, err)
    return None


def jump(address, herdr_socket=None, tab_id=None, pane_id=None, label=None):
    """Jump to a window (and herdr tab/pane). Always returns 0."""
    address = (address or "").strip()
    name = clean(label) or address or "?"
    if not ADDRESS_RE.match(address):
        report("“{}” has no valid window address, not jumping".format(name))
        return 0

    clients = hyprctl("clients")
    if not isinstance(clients, list):
        report("hyprctl -j clients not readable, not jumping")
        return 0
    if not any(isinstance(c, dict) and c.get("address") == address for c in clients):
        report("The window “{}” has been closed in the meantime.".format(name))
        return 0

    if (tab_id or pane_id) and not herdr_socket:
        report("herdr tab/pane given without --herdr-socket, focusing the window only")
    elif herdr_socket and (tab_id or pane_id):
        # herdr first, then the window: it then shows the right tab when it
        # appears. A herdr error does not cost the window jump. `pane.focus`
        # moves herdr workspace and tab along by itself.
        if pane_id:
            problem = herdr_rpc(herdr_socket, "pane.focus", {"pane_id": pane_id})
        else:
            problem = herdr_tab_focus(herdr_socket, tab_id)
        if problem:
            report("herdr: {}".format(problem))

    problem = focus_window(address)
    if problem:
        report("Jump to “{}” failed: {}".format(name, problem))
    return 0


class _SubParser(argparse.ArgumentParser):
    """Usage errors of `jump` go to notify-send too: it runs detached."""

    def error(self, message):
        if self.prog.endswith(" jump"):
            report("jump: {}".format(message))
            sys.exit(0)
        super().error(message)


def cmd_jump(args):
    return jump(args.address, herdr_socket=args.herdr_socket, tab_id=args.tab_id,
                pane_id=args.pane_id, label=args.label)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="switchr.py", description="switchr helper: collect jump targets or jump to one")
    sub = parser.add_subparsers(dest="command", metavar="{collect,jump}",
                                parser_class=_SubParser)
    sub.required = True

    p_collect = sub.add_parser("collect", help="print the jump targets as JSON (format 1)")
    p_collect.add_argument("--pretty", action="store_true", help="indent the JSON")
    p_collect.set_defaults(func=cmd_collect)

    p_jump = sub.add_parser("jump", help="focus a window, optionally a herdr tab or pane")
    p_jump.add_argument("--address", required=True, help="Hyprland window address 0x...")
    p_jump.add_argument("--herdr-socket", metavar="PATH", help="herdr session socket")
    p_jump.add_argument("--tab-id", metavar="T", help="herdr tab id, e.g. w2:t5")
    p_jump.add_argument("--pane-id", metavar="P", help="herdr pane id, e.g. w2:p7")
    p_jump.add_argument("--label", metavar="L", help="name used in messages")
    p_jump.set_defaults(func=cmd_jump)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
