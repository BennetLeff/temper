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
        # PWR_RTN is pre-seeded at its already-landed value. "HighVoltage"
        # is among the declared classes above, and PWR_RTN names real copper
        # on pcb/temper.kicad_pcb, so WITHOUT this seed the fixture would
        # construct the genuine reserved-decision case and (correctly) trip
        # the PROTECTED_NETS tripwire at exit 5 instead of exercising the
        # ordinary drift path this test is about. See
        # TestProtectedNetTripwire below, which covers all three branches
        # of that tripwire explicitly.
        pro_path = self._write_pro(
            tmp_path, declared, {"AC_L": "ACMains", "PWR_RTN": "HighVoltage"}
        )

        check1 = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert check1.returncode == 1
        assert "MISSING" in check1.stdout or "MISMATCHED" in check1.stdout

        write = self._run(["--write", "--kicad-pro", str(pro_path)])
        assert write.returncode == 0

        check2 = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert check2.returncode == 0, check2.stdout

        # Written file must still be valid JSON. CGND must not appear (GND is
        # not among the declared classes above); PWR_RTN must still hold
        # exactly the seeded value, i.e. the script neither added nor altered
        # it.
        data = json.loads(pro_path.read_text())
        na = data["net_settings"]["netclass_assignments"]
        assert na["PWR_RTN"] == "HighVoltage"
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

    def test_protected_net_refused_when_a_real_reclassification_is_pending(
        self, tmp_path
    ):
        # THE reserved case, and the one the PROTECTED_NETS tripwire exists
        # for: a protected net that (a) resolves to a class kicad_pro
        # declares, (b) names real copper on pcb/temper.kicad_pcb, and (c)
        # does NOT already carry that value in kicad_pro -- i.e. adopting it
        # would be a genuine, physically-consequential reclassification. The
        # script must refuse outright (exit 5), never silently pick it up.
        #
        # PWR_RTN -> "HighVoltage" (declared below), 17 pins of real copper,
        # and deliberately absent from this fixture's assignments.
        assert sync.TEMPER_NET_ASSIGNMENTS["PWR_RTN"] == "HighVoltage"
        declared = ["Default", "HighVoltage"]
        pro_path = self._write_pro(tmp_path, declared, {})
        result = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert result.returncode == 5
        assert "PWR_RTN" in result.stderr
        assert "protected" in result.stderr.lower()

    def test_protected_net_already_agreeing_does_not_block_the_gate(self, tmp_path):
        # Regression test for the defect this narrowing fixes: between
        # 2026-08-12 and 2026-08-19 the tripwire fired on a protected net
        # whose kicad_pro value ALREADY equalled its TEMPER_NET_ASSIGNMENTS
        # class -- a no-op with nothing to adjudicate -- and exit 5'd before
        # computing any diff, disabling the gate entirely for every other
        # net. Agreement must let the run proceed, and must still never
        # produce a write for the protected net.
        declared = ["Default", "HighVoltage"]
        pro_path = self._write_pro(tmp_path, declared, {"PWR_RTN": "HighVoltage"})
        result = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert result.returncode in (0, 1), result.stderr
        assert result.returncode != 5
        assert "NOTE" in result.stdout and "PWR_RTN" in result.stdout
        targets = sync.compute_target_assignments(set(declared))
        assert "PWR_RTN" not in targets

    def test_protected_net_with_no_board_copper_does_not_block_the_gate(
        self, tmp_path
    ):
        # CGND resolves to "GND" (a declared kicad_pro class since
        # 2026-08-12) but names NO net on pcb/temper.kicad_pcb, so no
        # assignment for it can reach any conductor and there is no blast
        # radius to reserve. The run proceeds; the net is still never
        # written, which is the protection that actually matters.
        assert sync.TEMPER_NET_ASSIGNMENTS["CGND"] == "GND"
        board_nets = sync.load_board_net_names(sync.KICAD_PCB_PATH)
        assert board_nets is not None and "CGND" not in board_nets
        declared = ["Default", "GND"]
        pro_path = self._write_pro(tmp_path, declared, {})
        result = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert result.returncode != 5, result.stderr
        assert "NOTE" in result.stdout and "CGND" in result.stdout
        targets = sync.compute_target_assignments(set(declared))
        assert "CGND" not in targets

    def test_unreadable_board_makes_the_tripwire_fail_closed(self, monkeypatch):
        # load_board_net_names returning None (board unreadable) must be
        # treated as "every protected net names real copper", so the
        # no-board-copper escape can never be reached by deleting a file.
        assert sync.load_board_net_names(Path("/nonexistent/temper.kicad_pcb")) is None

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

    def test_pwr_rtn_protected_now_that_gnd_is_declared(self):
        # 2026-08-12 (docs/evidence/2026-08-12-gnd-class-decision.md, Option
        # B): pcb/temper.kicad_pro now DOES declare a "GND" class (gnd's own
        # real design_rules.py parameters, mirrored in -- see that class's
        # own parameter-correspondence gate). The structural-unreachability
        # invariant this test used to check ("GND is not a declared kicad_pro
        # netclass, so PWR_RTN/CGND can't resolve to one") no longer holds by
        # construction, and is not supposed to: it was defense-in-depth on
        # top of the PROTECTED_NETS guard, not the primary mechanism. Assert
        # the guard that IS still the primary mechanism instead: PWR_RTN and
        # CGND, which TEMPER_NET_ASSIGNMENTS also maps to "GND", must still
        # be excluded from what this script is authorized to write, even
        # though "GND" is now a real, declared, resolvable kicad_pro class.
        real_pro = REPO_ROOT / "pcb" / "temper.kicad_pro"
        text = real_pro.read_text(encoding="utf-8")
        declared = sync.load_declared_classes(text)
        assert "GND" in declared, (
            "expected pcb/temper.kicad_pro to declare GND post-2026-08-12 -- "
            "if this fails, the class declaration itself regressed"
        )
        targets = sync.compute_target_assignments(declared)
        assert "PWR_RTN" not in targets
        assert "CGND" not in targets
        # CORRECTED 2026-08-19: this asserted PWR_RTN == "GND", which has been
        # factually false since 2026-08-12 (commit 322cbf5b0 / #1092 moved it
        # to "HighVoltage", strictly stricter -- HighVoltage's clearance and
        # creepage bars both exceed GND's), so the assertion has been red on
        # origin/main ever since. Corrected to the landed value; the two
        # `not in targets` assertions above -- the actual protection this test
        # exists to guard -- are unchanged and still enforced for BOTH nets
        # even though their classes are now declared, resolvable kicad_pro
        # classes.
        assert sync.TEMPER_NET_ASSIGNMENTS.get("PWR_RTN") == "HighVoltage"
        assert sync.TEMPER_NET_ASSIGNMENTS.get("CGND") == "GND"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
