// file generated with AI assistance: Claude Code - 2026-09-30 21:19:59 UTC
//
// Task switcher overlay: every window, every tab of a window group and
// every herdr tab and pane in one filterable tree, in workspace order; each
// row carries a workspace badge at its left edge instead of section headers.
// Opened via a Hyprland binding:
//
//     omarchy-shell shell toggle io.github.schmunk42.switchr
//
// The scaffolding follows Omarchy's own overlays
// (/usr/share/omarchy/shell/plugins/emojis/Emojis.qml for the
// open/close/dismiss contract and the menu tokens, plugins/clipboard for
// the list, the pointer gate and the scrolling).
//
// The data comes entirely from helper/switchr.py (Format Version 1, see
// the helper's module docstring). This file only draws and navigates;
// filtering and row building live in SwitchrModel.js, jumping is the
// helper's job again.

import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "SwitchrModel.js" as Model

Item {
  id: root

  // Wired up by the host (see shell.qml, Instantiator delegate).
  property string omarchyPath: Quickshell.env("OMARCHY_PATH")
  property var shell: null
  property var manifest: null

  property bool opened: false
  property string filterText: ""

  // The last successfully parsed document and its entries. Kept across
  // refreshes and across closing (`keepLoaded: true`), so the list is on
  // screen right away and only gets swapped once the new answer arrives --
  // never an empty list just because a refresh is in flight.
  property var entries: []
  property var sourceErrors: []
  property bool loaded: false
  property bool loading: false
  property bool refreshPending: false
  property string loadError: ""

  // Index into displayModel, -1 when nothing is selected.
  property int selectedIndex: -1
  // The selected row's id, so a refresh landing after the user already
  // moved keeps the cursor on the same entry.
  property string selectedRowId: ""
  property bool userMoved: false

  // The helper lives inside the plugin itself. `__sourceDir` is stamped by
  // Omarchy's PluginRegistry onto every manifest; the fallback is the path
  // `omarchy plugin add` uses.
  readonly property string pluginId: (root.manifest && root.manifest.id) || "io.github.schmunk42.switchr"
  readonly property string pluginDir:
    (root.manifest && root.manifest.__sourceDir)
      ? String(root.manifest.__sourceDir)
      : Quickshell.env("HOME") + "/.config/omarchy/plugins/io.github.schmunk42.switchr"
  readonly property string helper: root.pluginDir + "/helper/switchr.py"

  // The theme's menu tokens, as in Emojis.qml -- themes that style the menu
  // also style the switcher.
  readonly property color background: Color.menu.background
  readonly property color foreground: Color.menu.text
  readonly property color scrim: Color.menu.scrim
  readonly property color selectedBackground: Color.menu.selectedBackground
  readonly property color selectedText: Color.menu.selectedText
  readonly property var borderSpec: Border.surfaceSpec("menu", "border", Color.menu.border, Math.max(1, Style.space(2)))
  readonly property int cornerRadius: Style.cornerRadius
  readonly property string fontFamily: Style.font.menuFamily
  readonly property int contentMargin: Style.spacing.panelPadding
  readonly property int contentSpacing: Style.spacing.md
  readonly property int headerHeight: Math.max(Style.space(34), Style.font.title + Style.spacing.controlPaddingY * 2)

  readonly property int cardWidth: Math.min(Math.max(Style.space(560), Math.round(panel.width * 0.45)), panel.width - Style.gapsOut * 2)
  readonly property int cardHeight: Math.min(Math.max(Style.space(420), Math.round(panel.height * 0.7)), panel.height - Style.gapsOut * 2)

  readonly property int entryHeight: Math.max(Style.space(40), Style.font.title + Style.font.caption + Style.spacing.md * 2 + Style.spacing.xxs)
  readonly property int hintHeight: Style.font.bodySmall + Style.spacing.md * 2
  readonly property int hostHeight: Style.font.title + Style.spacing.sm * 2
  readonly property int indentStep: Style.space(18)

  // Workspace badge, in the style of the bar's workspace badges: tinted
  // fill (the bar's `fillOccupied` 0.35), a 1 px ring in the same colour at
  // 0.7, the short label centred. Side = row height minus a vertical inset
  // on both ends, so badges of adjacent rows don't touch. The badge sits
  // centred in a column as wide as an entry row's badge, so the text of
  // every row kind starts at the same x regardless of its row height.
  readonly property int badgeInset: Style.spacing.xxs
  readonly property int badgeColumn: root.entryHeight - root.badgeInset * 2
  readonly property int badgeLeft: Style.spacing.xs
  readonly property int textLeft: root.badgeLeft + root.badgeColumn + Style.spacing.md
  readonly property real badgeFillAlpha: 0.35
  readonly property real badgeRingAlpha: 0.7
  readonly property real badgeNeutralAlpha: 0.12

  readonly property string statusText: {
    var parts = []
    for (var i = 0; i < root.sourceErrors.length; i++)
      parts.push(Model.oneLine(root.sourceErrors[i]))
    if (root.loaded && root.loadError !== "")
      parts.push("refresh failed: " + root.loadError)
    return parts.join("  ·  ")
  }

  function open(payloadJson) {
    root.opened = true
    root.filterText = ""
    root.selectedRowId = ""
    root.userMoved = false
    root.rebuild()
    root.refresh()
    Qt.callLater(function () { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.opened = false
  }

  // On self-closing, the host must find out it's closed -- otherwise its
  // `toggle` gets out of sync and the next key press does nothing.
  function dismiss() {
    root.opened = false
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide(root.pluginId)
  }

  function toggle(payloadJson) {
    if (root.opened) root.dismiss()
    else root.open(payloadJson || "{}")
  }

  function refresh() {
    if (collectProc.running) {
      root.refreshPending = true
      return
    }
    root.loading = true
    collectProc.running = true
  }

  function applyResult(raw, err, exitCode) {
    var result = Model.parseDocument(raw)
    if (result.doc) {
      root.entries = result.doc.entries
      root.sourceErrors = result.doc.errors
      root.loadError = ""
      root.loaded = true
      root.rebuild()
      return
    }
    var tail = String(err || "").trim()
    root.loadError = result.error + " (exit " + exitCode + ")" + (tail !== "" ? ": " + tail.split("\n").pop() : "")
    if (!root.loaded)
      root.rebuild()
  }

  function isSelectable(index) {
    return index >= 0 && index < displayModel.count && displayModel.get(index).selectable
  }

  function firstSelectable(preferMatches) {
    var fallback = -1
    for (var i = 0; i < displayModel.count; i++) {
      var row = displayModel.get(i)
      if (!row.selectable)
        continue
      if (!preferMatches || !row.contextOnly)
        return i
      if (fallback === -1)
        fallback = i
    }
    return fallback
  }

  function rebuild() {
    var rows = Model.buildRows(root.entries, root.filterText)
    displayModel.clear()
    for (var i = 0; i < rows.length; i++)
      displayModel.append(rows[i])

    var index = -1
    if (root.userMoved && root.selectedRowId !== "") {
      for (i = 0; i < displayModel.count; i++) {
        var row = displayModel.get(i)
        if (row.selectable && row.rowId === root.selectedRowId) {
          index = i
          break
        }
      }
    }
    if (index === -1)
      index = root.firstSelectable(root.filterText !== "")
    root.setSelected(index)
    pointerGate.reset()
    Qt.callLater(root.revealSelected)
  }

  function setSelected(index) {
    root.selectedIndex = index
    root.selectedRowId = index >= 0 && index < displayModel.count ? displayModel.get(index).rowId : ""
  }

  // Keeps the selection in view.
  function revealSelected() {
    var index = root.selectedIndex
    if (index < 0 || index >= displayModel.count)
      return
    resultList.positionViewAtIndex(index, ListView.Contain)
  }

  // One step to the next selectable row; wraps around at both ends.
  function step(delta) {
    var count = displayModel.count
    if (count === 0)
      return
    var start = root.selectedIndex
    if (start < 0)
      start = delta > 0 ? -1 : count
    for (var n = 1; n <= count; n++) {
      var index = ((start + delta * n) % count + count) % count
      if (root.isSelectable(index)) {
        root.moveTo(index)
        return
      }
    }
  }

  // A page at a time; stops at the ends instead of wrapping.
  function page(delta) {
    var count = displayModel.count
    if (count === 0)
      return
    var perPage = Math.max(1, Math.floor(resultList.height / root.entryHeight))
    var target = Math.max(0, Math.min(count - 1, (root.selectedIndex < 0 ? 0 : root.selectedIndex) + delta * perPage))
    for (var i = target; i >= 0 && i < count; i += delta) {
      if (root.isSelectable(i)) { root.moveTo(i); return }
    }
    for (i = target; i >= 0 && i < count; i -= delta) {
      if (root.isSelectable(i)) { root.moveTo(i); return }
    }
  }

  function moveTo(index) {
    root.userMoved = true
    root.setSelected(index)
    pointerGate.reset()
    root.revealSelected()
  }

  function selectFromPointer(index, item, mouse) {
    if (!pointerGate.moved(item, mouse))
      return
    if (!root.isSelectable(index) || index === root.selectedIndex)
      return
    root.userMoved = true
    root.setSelected(index)
  }

  function setFilter(nextFilter) {
    root.filterText = nextFilter
    root.userMoved = false
    root.rebuild()
  }

  // Dismiss first, then hand over to the helper -- the same order as
  // Emojis.qml, so the overlay's exclusive keyboard focus is gone before
  // the target window gets focused.
  function activateIndex(index) {
    if (!root.isSelectable(index))
      return
    var row = displayModel.get(index)
    var entry = root.entries[row.src]
    if (!entry || !entry.target || !entry.target.address)
      return
    var argv = Model.jumpCommand(root.helper, entry)
    root.dismiss()
    Quickshell.execDetached(argv)
  }

  function statusColor(status) {
    if (status === "working") return Color.accent
    if (status === "blocked") return Color.urgent
    return root.foreground
  }

  ListModel { id: displayModel }

  PointerMoveGate {
    id: pointerGate
    referenceItem: card
  }

  Process {
    id: collectProc

    // `timeout` in front so a stuck helper can't take the overlay down
    // with it; the last list stays on screen in that case.
    command: ["timeout", "-k", "2", "8", "python3", "-B", root.helper, "collect"]

    // Both streams, read at exit: stderr carries a Python traceback when
    // the helper died before printing JSON.
    stdout: StdioCollector { id: collectOut; waitForEnd: true }
    stderr: StdioCollector { id: collectErr; waitForEnd: true }

    onExited: function (exitCode, exitStatus) {
      root.loading = false
      root.applyResult(collectOut.text, collectErr.text, exitCode)
      if (root.refreshPending) {
        root.refreshPending = false
        if (root.opened)
          Qt.callLater(root.refresh)
      }
    }
  }

  PanelWindow {
    id: panel

    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"

    WlrLayershell.namespace: "schmunk42-switchr"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    // The focused monitor, resolved through its name: a `HyprlandMonitor`
    // has no `screen` property, the direct route returns `undefined`. The
    // first output is the fallback as long as Hyprland hasn't reported a
    // focused monitor yet.
    screen: {
      var screens = Quickshell.screens
      if (!screens || screens.length === 0)
        return null
      var monitor = Hyprland.focusedMonitor
      var name = monitor ? String(monitor.name || "") : ""
      for (var i = 0; i < screens.length; i++) {
        if (screens[i].name === name)
          return screens[i]
      }
      return screens[0]
    }

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    BorderSurface {
      id: card

      width: root.cardWidth
      height: root.cardHeight
      radius: root.cornerRadius
      anchors.centerIn: parent
      color: root.background
      borderSpec: root.borderSpec
      padding: root.contentMargin

      // Swallows clicks so a hit on the card doesn't count as a click on
      // the scrim. Declared before the list so the list gets the wheel.
      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true

        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function (event) {
          if (event.key === Qt.Key_Escape) {
            if (root.filterText) root.setFilter("")
            else root.dismiss()
            event.accepted = true
          } else if (Util.editsFilter(event, root.filterText)) {
            root.setFilter(Util.editedFilter(event, root.filterText))
            event.accepted = true
          } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Backtab) {
            root.step(-1)
            event.accepted = true
          } else if (event.key === Qt.Key_Down || event.key === Qt.Key_Tab) {
            root.step(1)
            event.accepted = true
          } else if (event.key === Qt.Key_PageUp) {
            root.page(-1)
            event.accepted = true
          } else if (event.key === Qt.Key_PageDown) {
            root.page(1)
            event.accepted = true
          } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            root.activateIndex(root.selectedIndex)
            event.accepted = true
          } else if (event.text && event.text.length >= 1
                     && event.text.charCodeAt(0) >= 32 && event.text.charCodeAt(0) !== 127) {
            root.setFilter(root.filterText + event.text)
            event.accepted = true
          }
        }
      }

      Column {
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset
        spacing: root.contentSpacing

        // Filter line, with the row count (or a refresh marker) on the
        // right.
        Item {
          width: parent.width
          height: root.headerHeight

          Text {
            id: counter
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: root.loading ? "…" : (root.loaded ? String(root.entries.length) : "")
            color: root.foreground
            opacity: 0.5
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          Text {
            anchors.left: parent.left
            anchors.right: counter.left
            anchors.rightMargin: Style.spacing.md
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: root.filterText || "Switch to…"
            color: root.foreground
            opacity: root.filterText ? 1 : 0.58
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            elide: Text.ElideRight
            maximumLineCount: 1
          }
        }

        Item {
          width: parent.width
          height: parent.height - root.headerHeight - root.contentSpacing
                  - (statusLine.visible ? statusLine.height + root.contentSpacing : 0)
          clip: true

          ListView {
            id: resultList
            anchors.fill: parent
            model: displayModel
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
              id: row

              required property int index
              required property string kind
              required property int src
              required property string rowId
              required property int depth
              required property int indent
              required property string main
              required property string detail
              required property bool isActive
              required property string status
              required property bool selectable
              required property bool contextOnly
              required property string wsLabel
              required property string wsColor

              readonly property bool hasCursor: row.selectable && row.index === root.selectedIndex
              // Rows are flush; only herdr panes carry one step (see
              // SwitchrModel.buildRows). `depth` is not used for layout.
              readonly property int indentX: row.indent * root.indentStep
              // "host": a terminal window whose herdr tabs are listed below
              // it. Drawn as a bold text-only line at entry-label size; it
              // is not selectable (see
              // SwitchrModel.herdrHosts).
              readonly property bool isHost: row.kind === "host"
              // Workspace colour of the badge; "" when the helper had none.
              readonly property bool hasWsColor: row.wsColor !== ""
              readonly property color wsTint: row.hasWsColor ? row.wsColor : root.foreground

              width: ListView.view.width
              height: row.kind === "hint" ? root.hintHeight
                      : row.isHost ? root.hostHeight
                      : root.entryHeight
              radius: root.cornerRadius
              color: row.hasCursor ? root.selectedBackground : "transparent"

              // Workspace badge (see root.badge*). Without a workspace colour
              // the fill is the muted foreground at low alpha and the label
              // is drawn in the foreground colour.
              Rectangle {
                id: wsBadge
                readonly property int side: Math.max(0, row.height - root.badgeInset * 2)
                x: root.badgeLeft + Math.round((root.badgeColumn - side) / 2)
                anchors.verticalCenter: parent.verticalCenter
                width: side
                height: side
                radius: Math.min(Style.cornerRadius, side / 4)
                color: Qt.rgba(row.wsTint.r, row.wsTint.g, row.wsTint.b,
                               row.hasWsColor ? root.badgeFillAlpha : root.badgeNeutralAlpha)
                border.width: 1
                border.color: Qt.rgba(row.wsTint.r, row.wsTint.g, row.wsTint.b,
                                      row.hasWsColor ? root.badgeRingAlpha : root.badgeNeutralAlpha * 2)

                Text {
                  anchors.centerIn: parent
                  width: parent.width - 2
                  horizontalAlignment: Text.AlignHCenter
                  textFormat: Text.PlainText
                  text: row.wsLabel
                  color: row.hasWsColor
                         ? Model.badgeInk(row.wsColor, root.badgeFillAlpha, root.background)
                         : root.foreground
                  opacity: row.hasWsColor ? 1 : 0.7
                  font.family: root.fontFamily
                  font.pixelSize: Math.min(Style.font.bodySmall, Math.max(6, Math.round(wsBadge.side * 0.55)))
                  font.bold: true
                  elide: Text.ElideRight
                  maximumLineCount: 1
                }
              }

              // Hint: informational, muted, not activatable.
              Text {
                visible: row.kind === "hint"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: root.textLeft + row.indentX
                anchors.rightMargin: Style.spacing.rowPaddingX
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: row.kind === "hint" ? (row.detail !== "" ? row.main + "  ·  " + row.detail : row.main) : ""
                color: root.foreground
                opacity: 0.5
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                font.italic: true
                elide: Text.ElideRight
                maximumLineCount: 1
              }

              // Host: the window title as one line at entry-label size, bold,
              // muted (same tone as an entry's detail line), nothing else --
              // no detail, status or background.
              Text {
                visible: row.isHost
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: root.textLeft
                anchors.rightMargin: Style.spacing.rowPaddingX
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: row.isHost ? row.main : ""
                color: root.foreground
                opacity: 0.6
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                font.bold: true
                elide: Text.ElideRight
                maximumLineCount: 1
              }

              // Entry: main line and detail line, agent status on the right.
              // The active entry is marked only by its bold main line.
              Item {
                visible: row.kind === "entry"
                anchors.fill: parent
                anchors.leftMargin: root.textLeft + row.indentX
                anchors.rightMargin: Style.spacing.rowPaddingX

                Text {
                  id: statusBadge
                  visible: row.status !== ""
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  text: row.status
                  color: root.statusColor(row.status)
                  opacity: row.status === "working" || row.status === "blocked" ? 1 : 0.55
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }

                Column {
                  anchors.left: parent.left
                  anchors.right: statusBadge.visible ? statusBadge.left : parent.right
                  anchors.rightMargin: statusBadge.visible ? Style.spacing.lg : 0
                  anchors.verticalCenter: parent.verticalCenter
                  spacing: Style.spacing.xxs
                  opacity: row.contextOnly ? 0.6 : 1

                  Text {
                    width: parent.width
                    textFormat: Text.PlainText
                    text: row.kind === "entry" ? row.main : ""
                    color: row.hasCursor ? root.selectedText : root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.title
                    font.bold: row.isActive
                    elide: Text.ElideRight
                    wrapMode: Text.NoWrap
                    maximumLineCount: 1
                  }

                  Text {
                    width: parent.width
                    visible: row.detail !== ""
                    textFormat: Text.PlainText
                    text: row.kind === "entry" ? row.detail : ""
                    color: root.foreground
                    opacity: 0.6
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                    wrapMode: Text.NoWrap
                    maximumLineCount: 1
                  }
                }
              }

              MouseArea {
                anchors.fill: parent
                enabled: row.selectable
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onPositionChanged: function (mouse) {
                  root.selectFromPointer(row.index, row, mouse)
                }
                onClicked: {
                  root.userMoved = true
                  root.setSelected(row.index)
                  root.activateIndex(row.index)
                }
              }
            }
          }

          // Single message when there is nothing to list: first collect
          // still running or failed, no windows at all, or no match.
          Text {
            anchors.centerIn: parent
            width: parent.width - Style.spacing.xxl * 2
            visible: displayModel.count === 0
            textFormat: Text.PlainText
            text: {
              if (!root.loaded)
                return root.loadError !== "" ? "Could not collect windows: " + root.loadError : "Collecting windows…"
              if (root.filterText !== "")
                return "No matches for “" + root.filterText + "”"
              return "No windows"
            }
            color: root.foreground
            opacity: 0.7
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            maximumLineCount: 4
            elide: Text.ElideRight
          }
        }

        // Sources that were missing or did not answer, as reported by the
        // helper, plus a failed refresh after an earlier success.
        Text {
          id: statusLine
          width: parent.width
          visible: root.statusText !== ""
          textFormat: Text.PlainText
          text: root.statusText
          color: root.foreground
          opacity: 0.5
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
          maximumLineCount: 1
        }
      }
    }
  }
}
