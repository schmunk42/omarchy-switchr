<!-- file generated with AI assistance: Claude Code - 2026-09-30 22:07:04 UTC -->

# Switchr

A task switcher overlay for [Omarchy](https://omarchy.org/): every window, every tab of a window group and every herdr tab and pane in one flat list, each row marked with a badge for its workspace. Type to filter, press `Enter` to jump — to the window, and inside herdr straight to the tab and pane.

![Screenshot](preview.png)

<!-- TODO: add preview.png -->

## Install

```bash
omarchy plugin add https://github.com/schmunk42/omarchy-switchr
omarchy plugin enable io.github.schmunk42.switchr
```

Open it from a terminal:

```bash
omarchy-shell shell toggle io.github.schmunk42.switchr
```

Or bind a key in `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + less", "switchr", "omarchy-shell shell toggle io.github.schmunk42.switchr")
```

The overlay opens on the focused monitor and collects a fresh list every time it opens. Until the new list arrives, the previous one stays on screen.

## Usage

Every row is a target: a window, a tab of a window group, a herdr tab or a herdr pane. There are no workspace headers; instead each row carries a square badge at its left edge in the style of the bar's workspace badges — a tinted fill and a thin ring in the workspace colour, with the short workspace label in the middle. Rows of the same workspace repeat the badge. Without a configured colour (and for special workspaces, as a rule) the badge is neutral.

A terminal that hosts a herdr session is not listed itself: its tabs and panes are the targets. A herdr tab with a single pane is one row (the pane title as the main line, `<workspace> › <tab> · cwd · agent · status` below); only the panes of a tab with two or more panes are listed, indented one step under their tab. No other row is indented. The active entry has a bold main line; the agent status of a herdr entry is shown on the right.

| Key | Action |
|---|---|
| typing | filter over the main line, the detail line and the working directory; case-insensitive, several space-separated terms must all match |
| `Up` / `Down`, `Shift + Tab` / `Tab` | previous / next entry |
| `Page Up` / `Page Down` | move by a page |
| `Enter` | jump to the selected entry |
| `Backspace`, `Ctrl + Backspace`, `Ctrl + U` | delete a character, a word, the whole filter |
| `Esc` | clear the filter; close the overlay when the filter is already empty |

With the mouse: hovering selects, a click jumps, the wheel scrolls. Clicking outside the card closes the overlay.

The filter also sees the title, detail line and working directory of a hidden herdr host, so typing the session name finds its tabs. While filtering, a matching entry keeps its parent visible for context (dimmed) — a pane its tab, a group tab its window — except a herdr host, which is never drawn. Muted italic rows without a badge are hints, for example a herdr session whose tabs could not be read (`herdr --remote`); they cannot be activated. The window above such a hint stays listed and selectable, since it is the only way to reach it.

## Requirements

- Python 3.11 or newer (`python3`)
- `hyprctl` (comes with Hyprland)
- `timeout` from coreutils
- optional: `herdr` for tabs and panes of herdr sessions
- optional: `notify-send`

## Configure

The config file is optional.

`~/.config/schmunk42-switchr/config.json`:

```json
{
  "labels": { "6": "3", "special:docs": "D" },
  "names": { "6": "Earth", "special:docs": "Docs" },
  "colors": { "6": "#3b7fe0" },
  "shellWidgetId": "schmunk42.workspaces"
}
```

| Key | What it does |
|---|---|
| `labels` | workspace id or name → short label shown in the row badge |
| `names` | workspace id or name → long title (`workspace.title` in the data format) |
| `colors` | workspace id or name → colour `#rrggbb`, used for the row badges; invalid values are ignored |
| `shellWidgetId` | id of a bar widget in Omarchy's `shell.json` whose `labels` / `clockNames` / `colors` are read as defaults (the example uses the author's own workspace widget) |

A key is the workspace id as a string (`"6"`), the full name (`"special:docs"`) or the bare name (`"docs"`). Explicit `labels`, `names` and `colors` win over the widget.

## Data format

The overlay draws what `helper/switchr.py collect` prints: a JSON document in **Format Version 1**, with the entries already in display order. The authoritative description of every field is the module docstring of `helper/switchr.py`. A jump is `helper/switchr.py jump --address …` plus the herdr target when there is one. Why things are built this way, and what has been measured, is in [docs/DESIGN.md](docs/DESIGN.md).

## Development

Every save inside the plugin directory makes the Omarchy shell rescan its plugins, which closes any open shell panel or menu. After changing a QML file, restart the shell (`omarchy restart shell`) and check the journal — a QML error only shows up as a warning line:

```bash
journalctl --user -t omarchy-shell --since "-2 minutes" | grep -i 'failed\|switchr'
```

Run the tests:

```bash
python3 -B -m unittest discover -s tests
```

## License

MIT, see [LICENSE](LICENSE).
