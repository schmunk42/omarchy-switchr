<!-- file generated with AI assistance: Claude Code - 2026-10-01 22:40:00 UTC -->

# Design notes

Why Switchr works the way it does, and what has been measured. User-facing usage is in the [README](../README.md); the authoritative description of the data format is the module docstring of [`helper/switchr.py`](../helper/switchr.py).

## Collector and overlay are separate

The overlay never queries Hyprland or herdr itself. It starts `helper/switchr.py collect`, reads its JSON (Format Version 1) and builds its rows from it; to jump it starts `helper/switchr.py jump`. The contract between the two is the format and the helper's command line.

The split is deliberate: browser tabs (Chromium, Firefox) are planned as further sources that write into the same document, and the collector should be replaceable by a daemon that keeps the list warm instead of collecting on every open. Neither change should touch the overlay. A new optional field is added without a version bump (as `workspace.color` was); an incompatible change increments `version`.

`target.address` is always set, also for herdr entries and hints: every target ultimately lives in a Hyprland window, and `jump` checks exactly that address. A future browser tab will carry the address of its browser window plus its own object next to `herdr`.

## The overlay

A layer-shell window with namespace `schmunk42-switchr` and `WlrKeyboardFocus.Exclusive`. It opens on the **focused** monitor: `screen` is derived from the name of `Hyprland.focusedMonitor`, matched against `Quickshell.screens`, with `screens[0]` as fallback — a `HyprlandMonitor` has no `screen` property.

On every open the collector runs again as `timeout -k 2 8 python3 -B helper/switchr.py collect`. Until the new document is read, the previous list stays on screen instead of an empty overlay. A format version other than `1`, or output that is not JSON, is shown as a message in the overlay together with the helper's exit status.

External control is `open(payload)`, `close()`, `dismiss()` and `toggle(payload)`. `dismiss()` also calls `shell.hide(manifest.id)`, so the shell learns that the overlay closed itself — otherwise its `toggle` gets out of step and the next key press does nothing.

The list is flat by decision. An earlier version had workspace header rows; they were replaced by a badge per row because the header cost a row per workspace and the badge carries the same information. Only the panes of a multi-pane herdr tab are indented.

## Jumping

`jump` always exits 0, because it runs detached from the overlay and nobody reads the status; errors go to `notify-send` and stderr.

1. The address must match `^0x[0-9a-fA-F]+$` and is checked against a **fresh** `hyprctl -j clients`. Seconds may pass between collecting and choosing; if the window is gone, there is a message and **no** dispatch. This matters because a dispatch to a non-existent address also answers `ok`.
2. For a herdr target, **herdr is switched first**, then the window is focused, so the window already shows the right tab when it appears. All `HERDR_*` variables are removed from the environment beforehand (otherwise herdr refuses with `nested herdr is disabled by default` when the helper runs from a herdr pane). A herdr error is reported but does not cancel the window jump.
3. The window is focused with `hyprctl dispatch 'hl.dsp.focus({ window = "address:0x…" })'` (the Lua form), and the answer must be exactly `ok`; hyprctl writes errors to stdout.

A herdr pane is focused over the socket API — one NDJSON line `{"id": …, "method": "pane.focus", "params": {"pane_id": "w2:p7"}}` on the session's `herdr.sock`. The CLI does not do this: `herdr pane focus` only knows `--direction`, and `herdr agent focus` only reaches panes with a detected agent. `pane.focus` pulls herdr workspace and tab along. Only without a pane id does `herdr tab focus <tab_id>` run. Side effect: a pane jumped to counts as seen in herdr, a done badge on it disappears.

**The overlay dismisses first, then jumps** (`Quickshell.execDetached([… "jump", …])`). The other way round, the closing overlay with exclusive keyboard focus would hand focus back to the previous window and undo the jump.

### What has been measured

With Hyprland 0.56 on two monitors, opening the overlay, closing it via `toggle`, jumping and reading `hyprctl activewindow` after 1.2 s:

| Target | Result |
|---|---|
| window on another workspace that is not visible, other monitor | the monitor switches to that workspace and gets focus |
| inactive tab of a window group | `hl.dsp.focus` brings the tab to the front, no `hl.dsp.group.*` call needed |
| window in a special workspace (scratchpad) | the special workspace opens — on the **focused** monitor, regardless of the `monitor` field of the window |
| herdr pane in another tab / another herdr workspace | `pane.focus` pulls tab and workspace along |
| closed address | message on stderr, no dispatch, focus unchanged |

The `monitor` field is therefore of little use for special workspaces: a special always appears on the focused monitor. A typical collection (about 60 entries, several herdr sessions) took about 0.12 s.

## Labels and colours

Without a config file the Hyprland workspace name is the label; a special workspace gets its capitalised first letter as label and its capitalised name as title (`S`/`Scratchpad`, `D`/`Docs`). The plugin thus runs on any machine.

`shellWidgetId` looks a bar widget up by its **id**, not by its position in the layout: a fixed index silently points to another widget as soon as one is added or moved.

A missing config file is silent. A broken file, or one pointing to a widget that does not exist, shows up under `errors` in the document, never as a hint row — on a machine without that widget a hint would be a permanent message.

Order: workspaces by id, then `special:scratchpad`, `special:docs` and other specials; within a workspace by `focusHistoryID`, most recently used first.

## Window groups

A Hyprland group appears as **one** `window` entry for the visible tab, with the other tabs next to it as `group_tab` in the order of the group bar (`grouped` from `hyprctl -j clients`), on the same level: a group is a row of windows side by side, not a hierarchy. `parent` of a `group_tab` still names the visible tab, so a filter hit on a tab keeps its group visible. Visible is the member with `visible: true`, otherwise the one with the lowest `focusHistoryID`.

## herdr

Which session runs in a terminal window is determined by `helper/herdr_target.py` from the process tree of the window (command line and environment of the herdr client).

**One snapshot per session.** Exactly one `herdr api snapshot` call per session returns workspaces, tabs, panes and layouts in one answer and in about 4 ms — instead of four `list` calls that take longer together and between which the session can change, so a tab points to a pane the next list no longer knows.

Sessions are queried in parallel, each call with a hard timeout, all together within 2.5 s (`SNAPSHOT_BUDGET`). When that expires the collector exits with `os._exit`, because a hanging worker thread would block a normal exit and overrun the deadline after all. A session that does not answer in time becomes a hint `herdr did not answer within 2.5 s`; everything else is complete. The overlay's `timeout -k 2 8` is deliberately far above that and only fires if the collector itself hangs.

**A tab with one pane is one row.** A second, indented row for the pane would point to the same target. The merge happens in the collector, not in the overlay, so the overlay and future consumers of the format stay simple.

**One session in several windows** lists its tabs only under the most recently used window; listing them three times would lengthen the list without adding a target.

Two cases get a hint instead of tabs:

- **`herdr --remote`** — the client socket does not answer there, so the collector does not ask it.
- **Two windows sharing a PID** (`foot --server` with `footclient`) — which session runs in which window cannot be determined, and the collector does not guess.

Stopped sessions are not listed: no window shows them, so there is no target. IDs of herdr entries include the session name (`htab:<session>:<tab_id>`), because herdr ids like `w2:t5` repeat across sessions; session names are case-sensitive.

## Saving inside the plugin closes every open panel

Omarchy's shell watches the whole plugin directory with `inotifywait -m -r -e close_write,create,delete,move` (`shell/services/PluginRegistry.qml`); only `.git/` and dot entries are excluded. Every change triggers a reload that unloads **all** panels and clears the component cache. `keepLoaded` protects services, not overlays.

- **A QML change only takes effect after `omarchy restart shell`.** The reload runs (the journal shows `Local plugin changed, reloading: io.github.schmunk42.switchr`, one line per inotify event), but the already instantiated overlay of an enabled plugin with `keepLoaded: true` keeps its old component. Measured with Omarchy 4.0.4; not measured is whether a plugin without `keepLoaded` behaves differently.
- **Every save closes every open shell panel and menu** — also a save in `tests/`, `README.md` or a freshly written `__pycache__`. That is why the helper and the tests run with `python3 -B`.
- **Broken QML only shows in the journal**, as `WARN … Plugin widget … failed`, not as `error`.

So a change to the overlay is applied and checked in this order: save, `omarchy restart shell`, check the journal for `failed` (must be empty), open the overlay and look at it — a missing `failed` alone does not prove the new version is running.

## Predecessor: a menu instead of an overlay

The first version showed the same document through `omarchy-menu-select`. It was replaced because the menu falls short in three places:

- **No tree.** Indentation could only be faked with characters in the label, and a filter hit lost its connection to its window because it stood without its ancestors.
- **No keyboard navigation** beyond up and down — no skipping, no paging through 60 entries.
- **The id had to be visible.** `omarchy-menu-select` only returns `<label>\t<subtext>` and has no hidden column; since two windows titled "New Tab" differ only by address, every row carried the id as the last field of its subtext.

## Not planned

Closing windows, window previews, showing or starting stopped herdr sessions, replacing the existing cycling switchers (`ALT + TAB` and friends).
