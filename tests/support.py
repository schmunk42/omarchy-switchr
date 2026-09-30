#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-09-30 13:15:46 UTC
"""Shared test setup: make helper/ importable and load fixtures.

`python3 -B -m unittest discover -s tests` puts tests/ itself on sys.path
and does not import a package __init__, so every test module imports this
module first.
"""

import copy
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "helper")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
if HELPER not in sys.path:
    sys.path.insert(0, HELPER)

_cache = {}


def fixture(name):
    """A parsed fixture file (a fresh deep copy on every call)."""
    if name not in _cache:
        with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
            _cache[name] = json.load(handle)
    return copy.deepcopy(_cache[name])


def completed(args, stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)


MONITORS = [{"id": 0, "name": "eDP-1"}, {"id": 1, "name": "DP-2"}]
