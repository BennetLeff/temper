"""Tests for scripts/sync_kicad_netclass_assignments.py -- the generator
that syncs pcb/temper.kicad_pro's net_settings.netclass_assignments from
TEMPER_NET_ASSIGNMENTS (packages/temper-placer/src/temper_placer/core/
design_rules.py), closing the "two hand-maintained copies of one mapping"
gap PR #1023's own commit message flagged and deliberately left open.

Groups:
  TestComputeTargetAssignments -- PROTECTED_NETS (PWR_RTN/CGND) are never
    included even if their class were to resolve to a declared kicad_pro
    netclass; only classes kicad_pro actually declares are targeted.
  TestComputeReserved -- the PWR_RTN/CGND reservation is reported per-net
    and is a report, not a gate: it never perturbs what else is synced.
  TestVerifyProtectedUnchanged -- the fail-closed pre-write guard rejects
    any rendered text in which a protected net was added, retargeted or
    removed.
  TestComputeDiff -- missing vs mismatched classification is correct and
    an already-agreeing entry produces neither.
  TestApplySync -- the surgical text edit produces valid JSON, corrects
    mismatched values in place without disturbing key order, appends
    missing entries with correct comma/brace handling (including the
    historical stray-blank-line regression), and touches nothing outside
    the netclass_assignments block.
  TestCLI -- --check exits 1 on drift and 0 once synced (idempotent);
    --write applies the fix and is idempotent; PWR_RTN/CGND are never
    written, never retargeted, and always reported, under a synthetic
    kicad_pro that declares every class they map to -- and one reserved
    net does not block any unrelated write.
  TestRealRepoInvariant -- the actual checked-in pcb/temper.kicad_pro
    never regresses relative to TEMPER_NET_ASSIGNMENTS, carries no
    protected net this script could have added, and holds the four OVP-01
    protective-divider nodes at HighVoltage.
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


class TestComputeReserved:
    def test_reports_protected_nets_whose_class_is_declared(self):
        declared = {"GND", "HighVoltage", "Power"}
        reserved = dict(sync.compute_reserved(declared))
        assert set(reserved) == set(sync.PROTECTED_NETS)
        for net, cls in reserved.items():
            assert cls == sync.TEMPER_NET_ASSIGNMENTS[net]

    def test_reports_nothing_when_no_protected_class_is_declared(self):
        # A protected net whose class kicad_pro does not declare was never
        # writable in the first place, so there is nothing to report.
        declared = {"FinePitch", "Differential"}
        assert sync.compute_reserved(declared) == []

    def test_is_a_report_not_a_gate(self):
        # compute_reserved must not perturb what the sync is authorized to
        # write -- the reservation covers its own nets and nothing else.
        declared = {"GND", "HighVoltage", "Power", "ACMains", "FinePitch"}
        targets = sync.compute_target_assignments(declared)
        assert sync.compute_reserved(declared)  # non-vacuous
        assert targets, "unrelated nets must still be targeted"
        assert not (set(targets) & set(sync.PROTECTED_NETS))


class TestVerifyProtectedUnchanged:
    """`_verify_protected_unchanged` is the fail-closed guard that makes the
    narrowed refusal a narrowing rather than a loosening: whatever the diff
    and text-edit path do, a protected net's assignment must be identical
    before and after, or nothing is written at all.
    """

    def test_passes_when_protected_nets_are_untouched(self):
        before = _make_kicad_pro(["Power", "GND"], {"PWR_RTN": "GND", "vcc": "Power"})
        after = _make_kicad_pro(["Power", "GND"], {"PWR_RTN": "GND", "vcc": "Power", "x": "Power"})
        sync._verify_protected_unchanged(before, after)  # must not raise

    def test_raises_when_a_protected_net_would_be_added(self):
        before = _make_kicad_pro(["Power", "GND"], {"vcc": "Power"})
        after = _make_kicad_pro(["Power", "GND"], {"vcc": "Power", "CGND": "GND"})
        with pytest.raises(sync.SyncError, match="CGND"):
            sync._verify_protected_unchanged(before, after)

    def test_raises_when_a_protected_net_would_be_retargeted(self):
        before = _make_kicad_pro(["Power", "GND"], {"PWR_RTN": "Power"})
        after = _make_kicad_pro(["Power", "GND"], {"PWR_RTN": "GND"})
        with pytest.raises(sync.SyncError, match="PWR_RTN"):
            sync._verify_protected_unchanged(before, after)

    def test_raises_when_a_protected_net_would_be_removed(self):
        before = _make_kicad_pro(["Power", "GND"], {"PWR_RTN": "GND"})
        after = _make_kicad_pro(["Power", "GND"], {})
        with pytest.raises(sync.SyncError, match="PWR_RTN"):
            sync._verify_protected_unchanged(before, after)


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

    def test_protected_nets_never_written_even_when_their_class_is_declared(self, tmp_path):
        # The core refusal, stated at the level that matters: with every
        # class TEMPER_NET_ASSIGNMENTS gives PWR_RTN and CGND declared, a
        # full --write must still leave BOTH absent from the file. This is
        # the load-bearing property; the exit code is not.
        declared = [
            "Default", "Power", "HighVoltage", "GND", "GateDriveHV",
            "GateDriveSELV", "HighVoltageIsolated", "ACMains", "FinePitch",
            "Differential", "HighVoltageSignal", "HighVoltageTank",
        ]
        # Pinned by name, not read from PROTECTED_NETS: a test that walks
        # the very set it is guarding passes vacuously the moment that set
        # is emptied, which is exactly the regression it must catch.
        assert sync.PROTECTED_NETS == frozenset({"PWR_RTN", "CGND"}), (
            "the reserved set changed -- PWR_RTN/CGND unwritability is a "
            "deliberate, load-bearing refusal; narrowing it needs a human"
        )
        for net in ("PWR_RTN", "CGND"):
            assert sync.TEMPER_NET_ASSIGNMENTS[net] in declared, (
                f"test is vacuous unless {net!r}'s class is declared here"
            )
        pro_path = self._write_pro(tmp_path, declared, {})

        write = self._run(["--write", "--kicad-pro", str(pro_path)])
        assert write.returncode == 0, write.stderr

        na = json.loads(pro_path.read_text())["net_settings"]["netclass_assignments"]
        for net in ("PWR_RTN", "CGND"):
            assert net not in na, (
                f"{net!r} was written despite being in PROTECTED_NETS -- the "
                "PWR_RTN/CGND reservation has been breached"
            )
        # ...while the rest of the sync did land, which is the whole point
        # of narrowing the refusal from file-wide to per-net.
        assert na.get("SW_NODE") == "HighVoltage"
        assert na.get("safety.ovp.r_adc_top1-p2") == "HighVoltage"

    def test_protected_net_already_on_file_is_never_retargeted(self, tmp_path):
        # The other half of "unwritable": a protected net that IS already
        # in the file, carrying a class that disagrees with the SSOT, must
        # be left exactly as found -- the reserved reclassification is
        # precisely the change this script must not make.
        declared = [
            "Default", "Power", "HighVoltage", "GND", "ACMains", "FinePitch",
            "GateDriveHV", "GateDriveSELV", "HighVoltageIsolated",
        ]
        assert sync.TEMPER_NET_ASSIGNMENTS["PWR_RTN"] != "Default"
        pro_path = self._write_pro(tmp_path, declared, {"PWR_RTN": "Default", "CGND": "Default"})

        write = self._run(["--write", "--kicad-pro", str(pro_path)])
        assert write.returncode == 0, write.stderr

        na = json.loads(pro_path.read_text())["net_settings"]["netclass_assignments"]
        assert na["PWR_RTN"] == "Default"
        assert na["CGND"] == "Default"

    def test_reservation_is_reported_loudly_on_every_run(self, tmp_path):
        # Narrowing the refusal must not make it silent: whenever a
        # protected net's class is declared, every run says so on stderr.
        declared = ["Default", "GND", "HighVoltage"]
        pro_path = self._write_pro(tmp_path, declared, {})
        result = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert "RESERVED" in result.stderr
        assert "PWR_RTN" in result.stderr
        assert "CGND" in result.stderr

    def test_one_reserved_net_does_not_block_unrelated_writes(self, tmp_path):
        # The regression this change exists to prevent. Between 2026-08-12
        # (kicad_pro declared "GND") and this fix, main() returned 5 before
        # computing any diff whenever a protected net's class was declared
        # -- so ONE reserved decision made EVERY pending assignment
        # unwritable, including four OVP protective-divider nets sitting at
        # KiCad's Default 0.2mm while reaching full +170V_BUS under
        # IEC 60335-1 cl. 8.1.4's required single fault.
        declared = [
            "Default", "Power", "HighVoltage", "GND", "ACMains", "FinePitch",
            "GateDriveHV", "GateDriveSELV", "HighVoltageIsolated",
        ]
        assert sync.compute_reserved(set(declared)), (
            "test is vacuous unless at least one protected net's class is declared"
        )
        pro_path = self._write_pro(tmp_path, declared, {})

        check = self._run(["--check", "--kicad-pro", str(pro_path)])
        assert check.returncode == 1, (
            "a reserved net must not turn real, writable drift into a "
            f"different exit code: {check.stdout}\n{check.stderr}"
        )
        write = self._run(["--write", "--kicad-pro", str(pro_path)])
        assert write.returncode == 0, write.stderr

        na = json.loads(pro_path.read_text())["net_settings"]["netclass_assignments"]
        for net in (
            "safety.ovp.r_div_top1-p2", "safety.ovp.r_div_top2-p2",
            "safety.ovp.r_adc_top1-p2", "safety.ovp.r_adc_top2-p2",
        ):
            assert na.get(net) == "HighVoltage", f"{net!r} still blocked"

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

        # Both protected nets' SSOT classes are DECLARED classes today --
        # PWR_RTN's is "HighVoltage" (commit 322cbf5b0, #1092, 2026-08-12,
        # no longer "GND" as this assertion originally pinned) and CGND's
        # is "GND", declared the same day. That is what makes the
        # PROTECTED_NETS guard the only thing standing between this script
        # and the reserved reclassification, so assert the stronger,
        # currently-live property rather than either net's specific class:
        # whatever they map to is resolvable, and they are excluded anyway.
        reserved = dict(sync.compute_reserved(declared))
        assert set(reserved) == set(sync.PROTECTED_NETS), (
            "both protected nets are expected to be resolvable-but-reserved "
            f"today; compute_reserved reported {reserved}"
        )
        for net, cls in reserved.items():
            assert cls in declared
            assert net not in targets

    def test_real_kicad_pro_carries_no_protected_net_the_sync_could_have_added(self):
        # End-to-end on the real file: CGND must be absent (this script has
        # never written it and must never start), and PWR_RTN must carry
        # whatever a human put there, not whatever this script would.
        real_pro = REPO_ROOT / "pcb" / "temper.kicad_pro"
        current = sync.load_current_assignments(real_pro.read_text(encoding="utf-8"))
        assert "CGND" not in current
        assert sync.compute_diff(current, sync.compute_target_assignments(
            sync.load_declared_classes(real_pro.read_text(encoding="utf-8"))
        )) == ([], []), "real file must be fully synced for this assertion to mean anything"
        assert "PWR_RTN" not in sync.compute_target_assignments(
            sync.load_declared_classes(real_pro.read_text(encoding="utf-8"))
        )

    def test_four_ovp_nets_resolve_to_highvoltage_on_the_real_file(self):
        # The defect this change closes: the four OVP-01 protective-divider
        # mid-chain nodes have been HighVoltage in TEMPER_NET_ASSIGNMENTS
        # since 2026-08-13 but were absent from pcb/temper.kicad_pro -- the
        # file kicad-cli's DRC actually reads -- so they resolved to
        # Default (0.2mm clearance, no creepage rule at all) while reaching
        # full +170V_BUS under IEC 60335-1 cl. 8.1.4's required single
        # fault. See docs/evidence/2026-08-13-ovp01-midchain-single-fault-
        # creepage.md.
        real_pro = REPO_ROOT / "pcb" / "temper.kicad_pro"
        current = sync.load_current_assignments(real_pro.read_text(encoding="utf-8"))
        for net in (
            "safety.ovp.r_div_top1-p2", "safety.ovp.r_div_top2-p2",
            "safety.ovp.r_adc_top1-p2", "safety.ovp.r_adc_top2-p2",
        ):
            assert current.get(net) == "HighVoltage", (
                f"{net!r} is {current.get(net)!r} in pcb/temper.kicad_pro -- "
                "it must be HighVoltage or kicad-cli holds it to Default 0.2mm"
            )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
