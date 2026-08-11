"""Tests for scripts/sync_kicad_netclass_assignments.py -- the generator
that syncs pcb/temper.kicad_pro's net_settings.netclass_assignments from
TEMPER_NET_ASSIGNMENTS (packages/temper-placer/src/temper_placer/core/
design_rules.py), closing the "two hand-maintained copies of one mapping"
gap PR #1023's own commit message flagged and deliberately left open.

Groups:
  TestComputeTargetAssignments -- PROTECTED_NETS (PWR_RTN/CGND) are never
    included even if their class were to resolve to a declared kicad_pro
    netclass; only classes kicad_pro actually declares are targeted.
  TestComputeDiff -- missing vs mismatched classification is correct and
    an already-agreeing entry produces neither.
  TestApplySync -- the surgical text edit produces valid JSON, corrects
    mismatched values in place without disturbing key order, appends
    missing entries with correct comma/brace handling (including the
    historical stray-blank-line regression), and touches nothing outside
    the netclass_assignments block.
  TestCLI -- --check exits 1 on drift and 0 once synced (idempotent);
    --write applies the fix and is idempotent; PWR_RTN/CGND are refused
    even under a synthetic kicad_pro that declares a "GND" class.
  TestRealRepoInvariant -- the actual checked-in pcb/temper.kicad_pro
    never regresses relative to TEMPER_NET_ASSIGNMENTS once this fix
    lands (skipped/xfail-documented until the sync itself is committed).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import sync_kicad_netclass_assignments as sync  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_kicad_pro(classes: list[str], assignments: dict[str, str]) -> str:
    """Build a minimal, valid kicad_pro JSON text with the given declared
    classes and netclass_assignments -- enough structure for every
    function under test, nothing else.
    """
    data = {
        "net_settings": {
            "classes": [{"name": c} for c in classes],
            "netclass_assignments": assignments,
            "netclass_patterns": [],
        }
    }
    return json.dumps(data, indent=2)


class TestComputeTargetAssignments:
    def test_protected_nets_never_targeted_even_if_class_declared(self):
        # Even in a hypothetical world where kicad_pro declares "GND" (the
        # class TEMPER_NET_ASSIGNMENTS gives PWR_RTN/CGND today), the
        # protected-net guard must still exclude them -- defense in depth
        # on top of the structural "GND has no declared class" protection.
        declared = {"GND"}
        targets = sync.compute_target_assignments(declared)
        assert "PWR_RTN" not in targets
        assert "CGND" not in targets

    def test_only_covers_classes_kicad_pro_declares(self):
        # TEMPER_NET_ASSIGNMENTS has classes (HighSpeed, Signal, HighCurrent,
        # GND) with no kicad_pro counterpart -- none of their nets should
        # ever appear in the target set.
        declared = {"ACMains", "HighVoltage", "FinePitch"}
        targets = sync.compute_target_assignments(declared)
        for net, cls in targets.items():
            assert cls in declared, f"{net!r} targets undeclared class {cls!r}"

    def test_covers_a_known_real_entry(self):
        declared = {"ACMains", "HighVoltage", "FinePitch", "GateDriveHV", "GateDriveSELV", "Power", "HighVoltageIsolated"}
        targets = sync.compute_target_assignments(declared)
        assert targets.get("ac_l") == "ACMains"
        assert targets.get("SW_NODE") == "HighVoltage"


class TestComputeDiff:
    def test_missing_and_mismatched_and_agreeing(self):
        current = {"ac_l": "ACMains", "PWM_H": "FinePitch", "GATE_H": "GateDriveHV"}
        targets = {"ac_l": "ACMains", "PWM_H": "GateDriveSELV", "GATE_H": "GateDriveHV", "vcc": "Power"}
        missing, mismatched = sync.compute_diff(current, targets)
        assert missing == [("vcc", "Power")]
        assert mismatched == [("PWM_H", "FinePitch", "GateDriveSELV")]

    def test_empty_diff_when_fully_synced(self):
        targets = {"ac_l": "ACMains", "vcc": "Power"}
        missing, mismatched = sync.compute_diff(dict(targets), targets)
        assert missing == []
        assert mismatched == []


class TestApplySync:
    def _base_text(self) -> str:
        return _make_kicad_pro(
            ["Default", "Power", "ACMains", "FinePitch", "GateDriveSELV"],
            {
                "+15V": "Power",
                "ac_l": "ACMains",
                "PWM_H": "FinePitch",
                "hb.power_loop.q_high-g": "ACMains",
            },
        )

    def test_mismatch_corrected_in_place(self):
        text = self._base_text()
        new_text = sync.apply_sync(text, missing=[], mismatched=[("PWM_H", "FinePitch", "GateDriveSELV")])
        data = json.loads(new_text)
        na = data["net_settings"]["netclass_assignments"]
        assert na["PWM_H"] == "GateDriveSELV"
        # Everything else untouched.
        assert na["+15V"] == "Power"
        assert na["ac_l"] == "ACMains"

    def test_missing_appended_with_valid_json_and_no_stray_blank_line(self):
        text = self._base_text()
        new_text = sync.apply_sync(text, missing=[("vcc", "Power"), ("DC_BUS_RTN", "ACMains")], mismatched=[])
        # Must parse: this is the primary correctness bar for a text-level edit.
        data = json.loads(new_text)
        na = data["net_settings"]["netclass_assignments"]
        assert na["vcc"] == "Power"
        assert na["DC_BUS_RTN"] == "ACMains"
        # Regression guard: the first version of this function's insertion
        # logic left a trailing-whitespace-only blank line between the last
        # pre-existing entry and the first appended one (git diff showed
        # "+    \n" as its own hunk line). No line in the whole file may be
        # pure whitespace.
        for line in new_text.splitlines():
            assert line == line.rstrip() or line.strip() != "", (
                f"line has trailing-whitespace-only content: {line!r}"
            )

    def test_missing_and_mismatched_combined(self):
        text = self._base_text()
        new_text = sync.apply_sync(
            text,
            missing=[("vcc", "Power")],
            mismatched=[("PWM_H", "FinePitch", "GateDriveSELV")],
        )
        data = json.loads(new_text)
        na = data["net_settings"]["netclass_assignments"]
        assert na["vcc"] == "Power"
        assert na["PWM_H"] == "GateDriveSELV"

    def test_only_netclass_assignments_block_is_touched(self):
        # A value equal to a net name elsewhere in the file (e.g. inside
        # "classes") must not be mutated by the mismatch-correction regex.
        text = self._base_text()
        untouched_marker = '"name": "GateDriveSELV"'
        assert untouched_marker in text
        new_text = sync.apply_sync(text, missing=[], mismatched=[("PWM_H", "FinePitch", "GateDriveSELV")])
        assert untouched_marker in new_text


class TestCLI:
    def _write_pro(self, tmp_path: Path, classes, assignments) -> Path:
        p = tmp_path / "test.kicad_pro"
        p.write_text(_make_kicad_pro(classes, assignments), encoding="utf-8")
        return p

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "sync_kicad_netclass_assignments.py"), *args],
            capture_output=True,
            text=True,
        )

    def test_check_fails_then_write_fixes_then_check_passes(self, tmp_path):
        # Use a subset of real declared classes so the target set is the
        # real TEMPER_NET_ASSIGNMENTS-derived one, minus PWR_RTN/CGND.
        declared = [
            "Default", "Power", "HighVoltage", "GateDriveHV", "GateDriveSELV",
            "HighVoltageIsolated", "ACMains", "FinePitch", "Differential",
        ]
        pro_path = self._write_pro(tmp_path, declared, {"AC_L": "ACMains"})

        check1 = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert check1.returncode == 1
        assert "MISSING" in check1.stdout or "MISMATCHED" in check1.stdout

        write = self._run(["--write", "--kicad-pro", str(pro_path)])
        assert write.returncode == 0

        check2 = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert check2.returncode == 0, check2.stdout

        # Written file must still be valid JSON and PWR_RTN/CGND must not
        # appear (GND is not among the declared classes above).
        data = json.loads(pro_path.read_text())
        na = data["net_settings"]["netclass_assignments"]
        assert "PWR_RTN" not in na
        assert "CGND" not in na
        # A real, known entry landed correctly.
        assert na.get("SW_NODE") == "HighVoltage"
        assert na.get("+3V3") == "Power"

    def test_write_is_idempotent(self, tmp_path):
        declared = ["Default", "Power", "ACMains", "FinePitch"]
        pro_path = self._write_pro(tmp_path, declared, {})
        r1 = self._run(["--write", "--kicad-pro", str(pro_path)])
        assert r1.returncode == 0
        after_first = pro_path.read_text()
        r2 = self._run(["--write", "--kicad-pro", str(pro_path)])
        assert r2.returncode == 0
        assert pro_path.read_text() == after_first

    def test_protected_net_refused_even_if_gnd_class_declared(self, tmp_path):
        # If kicad_pro ever declares a "Ground"-equivalent class matching
        # TEMPER_NET_ASSIGNMENTS's "GND" class name exactly, the script
        # must still refuse rather than silently pick up PWR_RTN/CGND.
        declared = ["Default", "GND"]
        pro_path = self._write_pro(tmp_path, declared, {})
        result = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert result.returncode == 5
        assert "PWR_RTN" in result.stderr or "protected" in result.stderr.lower()

    def test_missing_kicad_pro_file_fails_closed(self, tmp_path):
        result = self._run(["--check", "--kicad-pro", str(tmp_path / "nonexistent.kicad_pro")])
        assert result.returncode == 5

    def test_no_mode_flag_errors(self, tmp_path):
        pro_path = self._write_pro(tmp_path, ["Default"], {})
        result = self._run(["--kicad-pro", str(pro_path)])
        assert result.returncode != 0


class TestRealRepoInvariant:
    """Guards the actual checked-in pcb/temper.kicad_pro. Once this sync
    lands, --check against the real file must pass -- if it doesn't, either
    the sync regressed or TEMPER_NET_ASSIGNMENTS gained a new entry nobody
    propagated. This is the CI tripwire the module docstring's "a generator
    without a CI check just relocates the drift bug" line refers to.
    """

    def test_real_kicad_pro_agrees_with_ssot(self):
        real_pro = REPO_ROOT / "pcb" / "temper.kicad_pro"
        text = real_pro.read_text(encoding="utf-8")
        declared = sync.load_declared_classes(text)
        current = sync.load_current_assignments(text)
        targets = sync.compute_target_assignments(declared)
        missing, mismatched = sync.compute_diff(current, targets)
        assert not missing and not mismatched, (
            f"pcb/temper.kicad_pro has drifted from TEMPER_NET_ASSIGNMENTS again: "
            f"{len(missing)} missing, {len(mismatched)} mismatched -- run "
            f"`uv run python scripts/sync_kicad_netclass_assignments.py --write`"
        )

    def test_pwr_rtn_structurally_unreachable(self):
        # Defense-in-depth check on the real file: GND must not be a
        # declared kicad_pro netclass today, so PWR_RTN/CGND cannot be
        # picked up even without the PROTECTED_NETS guard.
        real_pro = REPO_ROOT / "pcb" / "temper.kicad_pro"
        declared = sync.load_declared_classes(real_pro.read_text(encoding="utf-8"))
        assert "GND" not in declared
        assert "Ground" not in declared


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
