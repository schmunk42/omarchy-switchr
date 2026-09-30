<!-- file generated with AI assistance: Claude Code - 2026-09-30 13:09:46 UTC -->

# Switchr

A task switcher overlay for [Omarchy](https://omarchy.org/): every window, every tab of a window group and every herdr tab and pane in one tree, grouped by workspace. Type to filter, press `Enter` to jump — to the window, and inside herdr straight to the tab and pane.

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

| Key | Action |
|---|---|
| typing | filter over the main line, the detail line and the working directory; case-insensitive, several space-separated terms must all match |
| `Up` / `Down`, `Shift + Tab` / `Tab` | previous / next entry |
| `Page Up` / `Page Down` | move by a page |
| `Enter` | jump to the selected entry |
| `Backspace`, `Ctrl + Backspace`, `Ctrl + U` | delete a character, a word, the whole filter |
| `Esc` | clear the filter; close the overlay when the filter is already empty |

With the mouse: hovering selects, a click jumps, the wheel scrolls. Clicking outside the card closes the overlay.

While filtering, a matching tab or pane keeps its window visible for context (dimmed), and a workspace heading only stays when something below it is visible. Muted italic rows are hints, for example a herdr session whose tabs could not be read; they cannot be activated.

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
  "shellWidgetId": "schmunk42.workspaces"
}
```

| Key | What it does |
|---|---|
| `labels` | workspace id or name → short label shown in the heading |
| `names` | workspace id or name → long title shown next to the label |
| `shellWidgetId` | id of a bar widget in Omarchy's `shell.json` whose `labels` / `clockNames` are read as defaults (the example uses the author's own workspace widget) |

## Data format

The overlay draws what `helper/switchr.py collect` prints: a JSON document in **Format Version 1**, with the entries already in display order. The authoritative description of every field is the module docstring of `helper/switchr.py`. A jump is `helper/switchr.py jump --address …` plus the herdr target when there is one.

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
