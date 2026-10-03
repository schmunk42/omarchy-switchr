// file generated with AI assistance: Claude Code - 2026-09-30 21:44:58 UTC
//
// Pure functions that turn a Format Version 1 document from
// helper/switchr.py into the flat row list the overlay draws. No QML
// types in here -- that keeps the logic testable outside the shell and
// keeps Switchr.qml down to drawing and key handling.
//
// Every row has the same fixed schema without nulls, because the rows go
// into a ListModel: a nested object would become a sub-model there and a
// null would make the role's type unstable. The entry itself stays in the
// plain JS array; a row only points at it through `src`.

.pragma library

var FORMAT_VERSION = 1

// Control characters (tab, newline, ESC, ...) and the Unicode line
// separators would break a single-line row. The helper already replaces
// them in `label`, but not every field promises that, and a stray newline
// must not tear the list apart.
function oneLine(value) {
  if (value === null || value === undefined)
    return ""
  return String(value).replace(/[\u0000-\u001f\u007f\u2028\u2029]+/g, " ")
}

// Parses the helper's stdout. Returns {doc} on success, {error} otherwise.
// A document with an empty `entries` list and filled `errors` (the
// helper's exit 1 case) is a valid result, not a failure.
function parseDocument(raw) {
  var text = String(raw || "").trim()
  if (text === "")
    return { error: "the helper returned nothing" }
  var doc
  try {
    doc = JSON.parse(text)
  } catch (e) {
    return { error: "the helper output is not JSON: " + e }
  }
  if (!doc || typeof doc !== "object")
    return { error: "the helper output is not a JSON object" }
  if (doc.version !== FORMAT_VERSION)
    return { error: "unsupported format version " + doc.version + " (expected " + FORMAT_VERSION + ")" }
  if (!Array.isArray(doc.entries))
    return { error: "the helper output has no entries list" }
  if (!Array.isArray(doc.errors))
    doc.errors = []
  return { doc: doc }
}

function splitTerms(filterText) {
  var parts = String(filterText || "").toLowerCase().split(/\s+/)
  var out = []
  for (var i = 0; i < parts.length; i++) {
    if (parts[i] !== "")
      out.push(parts[i])
  }
  return out
}

// Case-insensitive substring match over label, detail and cwd; every term
// has to be found somewhere in them.
function matches(entry, terms) {
  if (terms.length === 0)
    return true
  var hay = (oneLine(entry.label) + " " + oneLine(entry.detail) + " " + oneLine(entry.cwd)).toLowerCase()
  for (var i = 0; i < terms.length; i++) {
    if (hay.indexOf(terms[i]) === -1)
      return false
  }
  return true
}

// The workspace badge every row carries at its left edge (there are no
// section headers; the badge is the only workspace cue). `wsColor` is the
// helper's `workspace.color` ("#rrggbb") or "" when it is null -- a
// ListModel role must not switch between string and null.
var HEX_RE = /^#[0-9a-fA-F]{6}$/

function workspaceBadge(entry) {
  var ws = entry.workspace || {}
  var label = oneLine(ws.label) || oneLine(ws.name)
  var color = typeof ws.color === "string" && HEX_RE.test(ws.color) ? ws.color.toLowerCase() : ""
  return { wsLabel: label, wsColor: color }
}

// A terminal window (window or group_tab) that hosts a listed herdr
// session: at least one herdr_tab names it as parent. Its tabs are the jump
// targets and stand on their own, so the window itself produces no row at
// all. A window whose only child is a hint (herdr --remote, timeout) is not
// a host and stays listed and selectable -- it is the only way to reach
// that window.
function herdrHosts(list) {
  var hosts = {}
  for (var i = 0; i < list.length; i++) {
    var e = list[i]
    if (e && e.type === "herdr_tab" && e.parent !== null && e.parent !== undefined)
      hosts[String(e.parent)] = true
  }
  return hosts
}

// The text a filter sees for entry `i`: its own label, detail and cwd, plus
// those of every host window above it. The host has no row of its own, so
// typing its title or session name (e.g. "herdr Sonne") shows its tabs as
// real matches instead of nothing.
function withHostText(list, i, indexById, hosts) {
  var entry = list[i]
  var extra = []
  var up = entry.parent
  var hops = 0
  while (up !== null && up !== undefined && hops < 64) {
    var u = indexById[String(up)]
    if (u === undefined)
      break
    if (hosts[String(list[u].id)] === true)
      extra.push(oneLine(list[u].label), oneLine(list[u].detail), oneLine(list[u].cwd))
    up = list[u].parent
    hops++
  }
  if (extra.length === 0)
    return entry
  return {
    label: entry.label,
    detail: oneLine(entry.detail) + " " + extra.join(" "),
    cwd: entry.cwd
  }
}

// Builds the rows for the current filter. `entries` is already in display
// order and is never re-sorted here. A matching child keeps its ancestors
// visible (marked as `contextOnly`); a host window among those ancestors is
// still not drawn. There are no header rows: every row except a hint
// carries its workspace badge (`wsLabel`, `wsColor`, `showBadge`) instead.
function buildRows(entries, filterText) {
  var terms = splitTerms(filterText)
  var list = Array.isArray(entries) ? entries : []

  var indexById = {}
  for (var i = 0; i < list.length; i++) {
    if (list[i] && list[i].id !== undefined && list[i].id !== null)
      indexById[String(list[i].id)] = i
  }
  var hosts = herdrHosts(list)

  var matched = []
  var visible = []
  for (i = 0; i < list.length; i++) {
    matched.push(false)
    visible.push(false)
  }

  for (i = 0; i < list.length; i++) {
    if (!list[i] || !matches(withHostText(list, i, indexById, hosts), terms))
      continue
    matched[i] = true
    visible[i] = true
    // Walk the parent chain. The guard stops a malformed document with a
    // parent cycle from hanging the shell.
    var parent = list[i].parent
    var guard = 0
    while (parent !== null && parent !== undefined && guard < 64) {
      var p = indexById[String(parent)]
      if (p === undefined || visible[p])
        break
      visible[p] = true
      parent = list[p].parent
      guard++
    }
  }

  var rows = []
  for (i = 0; i < list.length; i++) {
    if (!visible[i])
      continue
    var entry = list[i]
    // Host windows are never listed (see herdrHosts); their tabs follow
    // directly with their own badges.
    if ((entry.type === "window" || entry.type === "group_tab")
        && hosts[String(entry.id)] === true)
      continue
    var badge = workspaceBadge(entry)
    var isHint = entry.type === "hint"
    var status = oneLine(entry.agent_status)
    if (status === "unknown")
      status = ""
    rows.push({
      kind: isHint ? "hint" : "entry",
      src: i,
      rowId: String(entry.id),
      depth: Math.max(0, Number(entry.depth) || 0),
      // Indent steps for rendering. Rows are flush; only a herdr pane (the
      // child of a tab with two or more panes) keeps one step so it reads as
      // belonging to its tab. `depth` stays as the helper reported it.
      indent: entry.type === "herdr_pane" ? 1 : 0,
      main: oneLine(entry.label),
      detail: oneLine(entry.detail),
      isActive: entry.active === true,
      status: status,
      selectable: !isHint && !!(entry.target && entry.target.address),
      contextOnly: !matched[i],
      wsLabel: badge.wsLabel,
      wsColor: badge.wsColor,
      // A hint is a muted sub-line, not an entry of its own: no badge.
      showBadge: !isHint
    })
  }
  return rows
}

// The rows a filter actually found: selectable and not just shown as
// context for a matching child. This is the number the header shows.
function countMatches(rows) {
  var n = 0
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].selectable && !rows[i].contextOnly)
      n++
  }
  return n
}

// The argv for a jump, exactly as the helper contract states it. Every
// value goes as `--option=value`: a separate argument starting with "-"
// (a login shell's title is "-zsh") would be read by argparse as an option
// and the jump would not happen.
function jumpCommand(helper, entry) {
  var target = entry.target || {}
  var argv = ["python3", "-B", helper, "jump", "--address=" + String(target.address)]
  var herdr = target.herdr
  if (herdr !== null && herdr !== undefined) {
    argv.push("--herdr-socket=" + String(herdr.socket), "--tab-id=" + String(herdr.tab_id))
    if (herdr.pane_id !== null && herdr.pane_id !== undefined)
      argv.push("--pane-id=" + String(herdr.pane_id))
  }
  argv.push("--label=" + oneLine(entry.label))
  return argv
}
