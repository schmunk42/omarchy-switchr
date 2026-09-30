// file generated with AI assistance: Claude Code - 2026-09-30 13:09:46 UTC
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

// Tabs, newlines and carriage returns would break a single-line row. The
// helper already replaces them in `label`, but not every field promises
// that, and a stray newline must not tear the list apart.
function oneLine(value) {
  if (value === null || value === undefined)
    return ""
  return String(value).replace(/[\t\r\n]+/g, " ")
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

function workspaceKey(entry) {
  var ws = entry.workspace || {}
  return String(ws.id !== undefined && ws.id !== null ? ws.id : ws.name)
}

function headerRow(entry) {
  var ws = entry.workspace || {}
  var label = oneLine(ws.label)
  var title = oneLine(ws.title)
  return {
    kind: "header",
    src: -1,
    rowId: "ws:" + workspaceKey(entry),
    depth: 0,
    main: label !== "" && title !== "" ? label + "  " + title : (label || title || oneLine(ws.name)),
    detail: oneLine(entry.monitor),
    isActive: false,
    status: "",
    selectable: false,
    contextOnly: false
  }
}

// Builds the rows for the current filter. `entries` is already in display
// order and is never re-sorted here. A matching child keeps its ancestors
// visible (marked as `contextOnly`), and a workspace header is emitted only in
// front of a workspace that has at least one visible row.
function buildRows(entries, filterText) {
  var terms = splitTerms(filterText)
  var list = Array.isArray(entries) ? entries : []

  var indexById = {}
  for (var i = 0; i < list.length; i++) {
    if (list[i] && list[i].id !== undefined && list[i].id !== null)
      indexById[String(list[i].id)] = i
  }

  var matched = []
  var visible = []
  for (i = 0; i < list.length; i++) {
    matched.push(false)
    visible.push(false)
  }

  for (i = 0; i < list.length; i++) {
    if (!list[i] || !matches(list[i], terms))
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
  var lastWorkspace = null
  for (i = 0; i < list.length; i++) {
    if (!visible[i])
      continue
    var entry = list[i]
    var wsKey = workspaceKey(entry)
    if (wsKey !== lastWorkspace) {
      rows.push(headerRow(entry))
      lastWorkspace = wsKey
    }
    var isHint = entry.type === "hint"
    var status = oneLine(entry.agent_status)
    if (status === "unknown")
      status = ""
    rows.push({
      kind: isHint ? "hint" : "entry",
      src: i,
      rowId: String(entry.id),
      depth: Math.max(0, Number(entry.depth) || 0),
      main: oneLine(entry.label),
      detail: oneLine(entry.detail),
      isActive: entry.active === true,
      status: status,
      selectable: !isHint && !!(entry.target && entry.target.address),
      contextOnly: !matched[i]
    })
  }
  return rows
}

// The argv for a jump, exactly as the helper contract states it.
function jumpCommand(helper, entry) {
  var target = entry.target || {}
  var argv = ["python3", "-B", helper, "jump", "--address", String(target.address)]
  var herdr = target.herdr
  if (herdr !== null && herdr !== undefined) {
    argv.push("--herdr-socket", String(herdr.socket), "--tab-id", String(herdr.tab_id))
    if (herdr.pane_id !== null && herdr.pane_id !== undefined)
      argv.push("--pane-id", String(herdr.pane_id))
  }
  argv.push("--label", oneLine(entry.label))
  return argv
}
