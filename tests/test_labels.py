#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-09-30 13:17:28 UTC
"""Tests for workspace label resolution (defaults, config file, shell widget)."""

import json
import os
import tempfile
import unittest
from unittest import mock

import support  # noqa: F401  (sets sys.path)

import switchr

WS6 = {"id": 6, "name": "6"}
DOCS = {"id": -98, "name": "special:docs"}
SCRATCH = {"id": -99, "name": "special:scratchpad"}


class LabelCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def write(self, relpath, content):
        path = os.path.join(self.tmp.name, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content if isinstance(content, str) else json.dumps(content))

    def resolve(self, ws):
        errors = []
        labels, names = switchr.load_labels(errors)
        info = switchr.workspace_info(ws, labels, names)
        return info, errors


class TestDefaults(LabelCase):

    def test_no_config_uses_workspace_name(self):
        info, errors = self.resolve(WS6)
        self.assertEqual(info, {"id": 6, "name": "6", "label": "6", "title": "6",
                                "special": False})
        self.assertEqual(errors, [])

    def test_specials_get_first_letter_and_capitalised_name(self):
        info, _ = self.resolve(DOCS)
        self.assertEqual((info["label"], info["title"], info["special"]), ("D", "Docs", True))
        info, _ = self.resolve(SCRATCH)
        self.assertEqual((info["label"], info["title"]), ("S", "Scratchpad"))

    def test_named_workspace_keeps_its_name(self):
        info, _ = self.resolve({"id": 12, "name": "mail"})
        self.assertEqual((info["label"], info["title"]), ("mail", "mail"))


class TestConfig(LabelCase):

    def test_labels_and_names_by_id_and_name(self):
        self.write("schmunk42-switchr/config.json", {
            "labels": {"6": "3", "docs": "N"},
            "names": {"6": "Earth", "special:docs": "Notes"},
        })
        info, errors = self.resolve(WS6)
        self.assertEqual((info["label"], info["title"]), ("3", "Earth"))
        info, _ = self.resolve(DOCS)
        self.assertEqual((info["label"], info["title"]), ("N", "Notes"))
        self.assertEqual(errors, [])

    def test_partial_config_falls_back_per_field(self):
        self.write("schmunk42-switchr/config.json", {"labels": {"6": "3"}})
        info, _ = self.resolve(WS6)
        self.assertEqual((info["label"], info["title"]), ("3", "6"))

    def test_malformed_config_is_an_error_not_a_crash(self):
        self.write("schmunk42-switchr/config.json", "{not json")
        info, errors = self.resolve(WS6)
        self.assertEqual(info["label"], "6")
        self.assertEqual(len(errors), 1)
        self.assertIn("not valid JSON", errors[0])

    def test_wrong_types_are_errors(self):
        self.write("schmunk42-switchr/config.json", {"labels": ["x"], "shellWidgetId": 3})
        info, errors = self.resolve(WS6)
        self.assertEqual(info["label"], "6")
        self.assertEqual(len(errors), 2)

    def test_config_values_are_cleaned(self):
        self.write("schmunk42-switchr/config.json", {"names": {"6": "Ea\trth\n"}})
        info, _ = self.resolve(WS6)
        self.assertEqual(info["title"], "Ea rth")


class TestShellWidget(LabelCase):

    SHELL = {"bar": {"layout": {"left": [
        {"id": "omarchy.clock"},
        {"id": "example.workspaces", "labels": {"6": "3", "7": "4"},
         "clockNames": {"6": "Earth", "7": "Mars"}},
    ]}}}

    def test_widget_labels_and_clock_names(self):
        self.write("omarchy/shell.json", self.SHELL)
        self.write("schmunk42-switchr/config.json", {"shellWidgetId": "example.workspaces"})
        info, errors = self.resolve(WS6)
        self.assertEqual((info["label"], info["title"]), ("3", "Earth"))
        self.assertEqual(errors, [])

    def test_explicit_labels_win_over_widget(self):
        self.write("omarchy/shell.json", self.SHELL)
        self.write("schmunk42-switchr/config.json", {
            "shellWidgetId": "example.workspaces", "names": {"6": "Terra"}})
        info, _ = self.resolve(WS6)
        self.assertEqual((info["label"], info["title"]), ("3", "Terra"))

    def test_missing_widget_is_reported(self):
        self.write("omarchy/shell.json", self.SHELL)
        self.write("schmunk42-switchr/config.json", {"shellWidgetId": "nope"})
        info, errors = self.resolve(WS6)
        self.assertEqual(info["label"], "6")
        self.assertEqual(len(errors), 1)
        self.assertIn("nope", errors[0])

    def test_missing_shell_json_is_reported(self):
        self.write("schmunk42-switchr/config.json", {"shellWidgetId": "example.workspaces"})
        info, errors = self.resolve(WS6)
        self.assertEqual(info["label"], "6")
        self.assertEqual(len(errors), 1)

    def test_widget_is_ignored_without_shell_widget_id(self):
        self.write("omarchy/shell.json", self.SHELL)
        info, errors = self.resolve(WS6)
        self.assertEqual(info["label"], "6")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
