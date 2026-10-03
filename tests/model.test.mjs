// file generated with AI assistance: Claude Code - 2026-10-03 09:40:00 UTC
//
// Tests for SwitchrModel.js under Node (`node --test tests/model.test.mjs`).
// The file is a QML JavaScript library: apart from the `.pragma library`
// line it is plain ES5, so the line is stripped and the rest evaluated in a
// function scope that hands the public functions back.

import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const root = join(dirname(fileURLToPath(import.meta.url)), "..")
const source = readFileSync(join(root, "SwitchrModel.js"), "utf8")
  .replace(/^\.pragma library\s*$/m, "")
const Model = new Function(source + `
  return { oneLine, parseDocument, buildRows, countMatches, jumpCommand,
           workspaceBadge, herdrHosts }`)()

const ws = (id, label, color = null) => ({ id, name: String(id), label, title: label, special: false, color })

function win(address, label, extra = {}) {
  return {
    id: "win:" + address, type: "window", parent: null, depth: 0,
    workspace: ws(6, "3", "#aabbcc"), label, detail: "foot", cwd: null,
    active: false, agent_status: null,
    target: { address, herdr: null }, ...extra,
  }
}

function herdr(type, id, parent, label, extra = {}) {
  return {
    id, type, parent, depth: type === "herdr_pane" ? 2 : 1,
    workspace: ws(6, "3", "#aabbcc"), label, detail: "", cwd: "/home/u/Work/p",
    active: false, agent_status: "unknown",
    target: { address: "0x2", herdr: { session: "Earth", socket: "/s.sock",
                                       workspace_id: "w1", tab_id: "w1:t1", pane_id: "w1:p1" } },
    ...extra,
  }
}

const doc = [
  win("0x1", "Thunderbird", { detail: "org.mozilla.Thunderbird" }),
  win("0x2", "host: project", { detail: "foot · ~/Work/p · herdr Earth" }),
  herdr("herdr_tab", "htab:Earth:w1:t1", "win:0x2", "docs › one"),
  herdr("herdr_pane", "hpane:Earth:w1:p1", "htab:Earth:w1:t1", "-zsh"),
  herdr("herdr_pane", "hpane:Earth:w1:p2", "htab:Earth:w1:t1", "claude"),
  win("0x3", "remote term"),
  { id: "hint:win:0x3", type: "hint", parent: "win:0x3", depth: 1, workspace: ws(6, "3"),
    label: "Tabs not available", detail: "Hint", target: { address: "0x3", herdr: null } },
]

test("oneLine replaces every control character", () => {
  assert.equal(Model.oneLine("a\tb\nc\x1b[0md\x0be f"), "a b c [0md e f")
  assert.equal(Model.oneLine(null), "")
})

test("host windows produce no row, their tabs do", () => {
  const ids = Model.buildRows(doc, "").map(r => r.rowId)
  assert.ok(!ids.includes("win:0x2"))
  assert.deepEqual(ids, ["win:0x1", "htab:Earth:w1:t1", "hpane:Earth:w1:p1",
                         "hpane:Earth:w1:p2", "win:0x3", "hint:win:0x3"])
})

test("a window with only a hint is not a host and stays selectable", () => {
  const rows = Model.buildRows(doc, "")
  assert.equal(rows.find(r => r.rowId === "win:0x3").selectable, true)
  assert.equal(rows.find(r => r.rowId === "hint:win:0x3").selectable, false)
})

test("filter on the host's text shows its tabs as matches", () => {
  const rows = Model.buildRows(doc, "herdr earth")
  assert.deepEqual(rows.map(r => [r.rowId, r.contextOnly]),
                   [["htab:Earth:w1:t1", false], ["hpane:Earth:w1:p1", false],
                    ["hpane:Earth:w1:p2", false]])
})

test("a matching child keeps its ancestors as context", () => {
  const rows = Model.buildRows(doc, "claude")
  assert.deepEqual(rows.map(r => [r.rowId, r.contextOnly]),
                   [["htab:Earth:w1:t1", true], ["hpane:Earth:w1:p2", false]])
})

test("countMatches counts selectable matches, not context or hints", () => {
  assert.equal(Model.countMatches(Model.buildRows(doc, "claude")), 1)
  assert.equal(Model.countMatches(Model.buildRows(doc, "")), 5)
  assert.equal(Model.countMatches(Model.buildRows(doc, "nothing-matches")), 0)
})

test("jumpCommand passes every value with '=' so '-zsh' stays a value", () => {
  const argv = Model.jumpCommand("/p/helper/switchr.py", doc[3])
  assert.deepEqual(argv, ["python3", "-B", "/p/helper/switchr.py", "jump",
                          "--address=0x2", "--herdr-socket=/s.sock", "--tab-id=w1:t1",
                          "--pane-id=w1:p1", "--label=-zsh"])
  assert.ok(argv.slice(4).every(a => a.startsWith("--") && a.includes("=")))
})

test("jumpCommand for a plain window has no herdr options", () => {
  assert.deepEqual(Model.jumpCommand("h", doc[0]),
                   ["python3", "-B", "h", "jump", "--address=0x1", "--label=Thunderbird"])
})

test("parseDocument rejects other format versions", () => {
  assert.match(Model.parseDocument('{"version":2,"entries":[]}').error, /version 2/)
  assert.deepEqual(Model.parseDocument('{"version":1,"entries":[]}').doc.errors, [])
  assert.ok(Model.parseDocument("").error)
})

test("workspace badge colour is empty without a valid colour", () => {
  assert.deepEqual(Model.workspaceBadge(doc[0]), { wsLabel: "3", wsColor: "#aabbcc" })
  assert.deepEqual(Model.workspaceBadge({ workspace: { name: "special:docs", label: "D", color: "red" } }),
                   { wsLabel: "D", wsColor: "" })
})
