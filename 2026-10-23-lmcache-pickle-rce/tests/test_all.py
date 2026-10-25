"""Tests: prove the toy bug, prove the fix, and check detect logic.

Run from the issue folder:  python3 -I -m pytest -q
"""

from __future__ import annotations

import json
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import detect  # noqa: E402
import fix  # noqa: E402
import reproduce  # noqa: E402


# --- the toy bug: pickle.loads runs code before the type check ---

def test_vulnerable_handler_runs_side_effect(tmp_path):
    marker = str(tmp_path / "marker")
    raw = pickle.dumps(reproduce.MarkerDescriptor(marker))
    assert not os.path.exists(marker)
    try:
        reproduce.vulnerable_handler(raw)
    except TypeError:
        pass  # rejected, but too late
    assert os.path.exists(marker)  # side effect already ran


def test_vulnerable_handler_accepts_legit():
    raw = pickle.dumps(reproduce.CacheDescriptor(1, (2, 2)))
    obj = reproduce.vulnerable_handler(raw)
    assert isinstance(obj, reproduce.CacheDescriptor)


# --- the fix: typed allowlisted decode, no callable reconstruction ---

def test_safe_handler_accepts_legit():
    raw = json.dumps({"kind": "cache_descriptor", "slot": 3, "shape": [4, 8]}).encode()
    d = fix.safe_handler(raw)
    assert d.slot == 3 and d.shape == [4, 8]


def test_safe_handler_refuses_unknown_kind():
    raw = json.dumps({"kind": "os.system", "slot": 0, "shape": [1]}).encode()
    try:
        fix.safe_handler(raw)
    except ValueError:
        return
    raise AssertionError("hostile message was not refused")


def test_safe_handler_cannot_run_reduce():
    # Even if an attacker had a pickle of a reduce payload, the JSON path
    # never deserialises it: feeding raw pickle bytes fails to decode.
    raw = pickle.dumps(reproduce.MarkerDescriptor("/tmp/should_not_happen"))
    try:
        fix.safe_handler(raw)
    except Exception:
        return
    raise AssertionError("pickle bytes should not decode on the JSON path")


# --- detect: version range logic ---

def test_version_status_boundaries():
    assert detect.version_status("0.3.9") == "affected"
    assert detect.version_status("0.5.5") == "affected"
    assert detect.version_status("0.5.6rc3") == "affected"  # rc still < 0.5.6
    assert detect.version_status("0.5.6") == "fixed"
    assert detect.version_status("0.3.8") == "unknown"
    assert detect.version_status(None) == "not-installed"
