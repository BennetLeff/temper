"""Replay contract for the R14/high-voltage campaign terminal receipt."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / "docs/evidence/r14-hv-domain-refloorplan-20260831"


def load_campaign_module():
    path = EVIDENCE / "run_campaign.py"
    spec = importlib.util.spec_from_file_location("r14_hv_campaign_receipt", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_terminal_receipt_is_derived_and_tamper_evident():
    campaign = load_campaign_module()
    declaration_path = EVIDENCE / "declaration.json"
    manifest_path = EVIDENCE / "pre-route-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    actual = json.loads((EVIDENCE / "terminal-receipt.json").read_text())
    expected = campaign.build_terminal_receipt(manifest, declaration_path, manifest_path)
    campaign.validate_terminal_receipt(actual, expected)

    tampered = copy.deepcopy(actual)
    tampered["coverage"]["evaluated_candidates"] -= 1
    with pytest.raises(RuntimeError, match="coverage"):
        campaign.validate_terminal_receipt(tampered, expected)


def test_missing_generated_input_fails_with_recovery_command():
    campaign = load_campaign_module()
    campaign.NETLIST = campaign.ROOT / "elec/build/definitely-missing.net"
    with pytest.raises(RuntimeError, match="make netlist"):
        campaign.verify_generated_inputs()
