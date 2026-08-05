"""Tests for check_hash_order_determinism.py.

Two layers, deliberately:

``TestDetector`` / ``TestExemptions`` build synthetic modules in ``tmp_path`` and
run the analyser directly, so the detection *rules* are pinned independently of
whatever the real tree contains on any given day. Each exemption has a test that
proves the exemption fires AND a neighbouring test that proves the nearly
identical unsafe shape still fails -- an exemption with no adjacent negative is
indistinguishable from a hole.

``TestRealRepo`` runs the gate against the actual repo, pinning: the two sites
fixed by the PR this shipped with are gone, the sites PR #730 fixes are still
detected on this branch, the inventory is exact, and the gate fails closed when
its scope evaporates.

The single most important test in this file is
``TestFreshSite::test_detects_a_site_the_gate_was_not_written_against``: it
injects a *new* hash-order dependency into a module that had none, in a package
this gate's author never looked at, and requires detection. A gate tuned to the
known instances is a regression test wearing a gate's clothes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_hash_order_determinism as gate  # noqa: E402

REPO_ROOT = Path(gate.REPO_ROOT)


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _analyze(tmp_path: Path, source: str, rel: str = "packages/p/src/m.py"):
    _write(tmp_path, rel, source)
    return gate.analyze(tmp_path, gate.iter_scope_files(tmp_path))


def _constructs(findings) -> list[str]:
    return [f.construct for f in findings]


class TestDetector:
    def test_hash_builtin_is_flagged(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def pick(cid, nodes):\n    return nodes[hash(cid) % len(nodes)]\n",
        )
        assert _constructs(findings) == ["hash-builtin"]
        assert findings[0].line == 2
        assert findings[0].qualname == "pick"

    def test_list_of_a_set_is_flagged(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(items):\n    refs = {i.ref for i in items}\n    return list(refs)\n",
        )
        assert _constructs(findings) == ["set-materialised"]

    def test_frozenset_annotated_parameter_is_flagged(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(nets: frozenset[str], out: list) -> None:\n"
            "    for n in nets:\n"
            "        out.append(n)\n",
        )
        assert _constructs(findings) == ["set-loop-records-order"]

    def test_set_returning_function_is_recognised_across_files(self, tmp_path):
        _write(
            tmp_path,
            "packages/p/src/a.py",
            "def get_component_refs(self) -> set[str]:\n    return set()\n",
        )
        findings = _analyze(
            tmp_path,
            "def f(net, exclude):\n    return list(net.get_component_refs() - exclude)\n",
            rel="packages/p/src/b.py",
        )
        assert _constructs(findings) == ["set-materialised"]

    def test_set_difference_is_still_a_set(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(a: set[str], b: set[str]):\n    return list(a - b)\n",
        )
        assert _constructs(findings) == ["set-materialised"]

    def test_enumerate_over_a_set_is_flagged(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(refs: set[str]):\n    return {r: i for i, r in enumerate(refs)}\n",
        )
        assert "set-indexed" in _constructs(findings)

    def test_next_iter_of_a_set_is_flagged(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(refs: set[str]):\n    return next(iter(refs))\n",
        )
        assert _constructs(findings) == ["set-first-element"]

    def test_float_sum_over_a_set_is_flagged(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(comps: set[str], pos):\n    return sum(pos[c].x for c in comps)\n",
        )
        assert _constructs(findings) == ["set-accumulated"]

    def test_dict_keyed_by_the_loop_variable_is_flagged(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(refs: set[str], zones):\n"
            "    out = {}\n"
            "    for ref in refs:\n"
            "        out[ref] = zones.get(ref)\n"
            "    return out\n",
        )
        assert _constructs(findings) == ["set-loop-records-order"]

    def test_break_that_captures_the_element_is_flagged(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(cands: set[str]):\n"
            "    chosen = None\n"
            "    for c in cands:\n"
            "        if c.startswith('U'):\n"
            "            chosen = c\n"
            "            break\n"
            "    return chosen\n",
        )
        assert _constructs(findings) == ["set-loop-records-order"]

    def test_findings_name_file_line_and_construct(self, tmp_path):
        findings = _analyze(tmp_path, "\n\ndef f(s: set[str]):\n    return list(s)\n")
        rendered = findings[0].render()
        assert "m.py:4:" in rendered
        assert "[set-materialised]" in rendered
        assert "in f()" in rendered


class TestExemptions:
    """Each exemption, with the adjacent unsafe shape that must still fail."""

    def test_dunder_hash_is_exempt(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "class C:\n    def __hash__(self):\n        return hash(self.key)\n",
        )
        assert findings == []

    def test_hash_outside_dunder_hash_is_not_exempt(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "class C:\n    def name(self):\n        return 'z%04x' % (hash(self.key) & 0xFFFF)\n",
        )
        assert _constructs(findings) == ["hash-builtin"]

    def test_integer_sum_over_a_set_is_exempt(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(paths: set[str], seen):\n    return sum(1 for p in paths if p in seen)\n",
        )
        assert findings == []

    def test_len_sum_over_a_set_is_exempt(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(groups: set[str], members):\n    return sum(len(members[g]) for g in groups)\n",
        )
        assert findings == []

    def test_singleton_guarded_index_is_exempt(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(zones: set[str]):\n"
            "    if len(zones) == 1:\n"
            "        return list(zones)[0]\n"
            "    return None\n",
        )
        assert findings == []

    def test_unguarded_index_is_not_exempt(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(zones: set[str]):\n"
            "    if len(zones) > 1:\n"
            "        return list(zones)[0]\n"
            "    return None\n",
        )
        assert _constructs(findings) == ["set-materialised"]

    def test_break_setting_a_constant_flag_is_exempt(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(endpoints: set[tuple], px):\n"
            "    connected = False\n"
            "    for ex in endpoints:\n"
            "        if abs(ex[0] - px) < 0.01:\n"
            "            connected = True\n"
            "            break\n"
            "    return connected\n",
        )
        assert findings == []

    def test_set_accumulation_without_iteration_is_exempt(self, tmp_path):
        """The `identify_thermal_components` shape: build a set, re-project it.

        This is the in-repo idiom the fixes adopt, and the single most important
        thing for this gate NOT to flag -- it is correct code, and a gate that
        fires on correct code is a defect in the gate.
        """
        findings = _analyze(
            tmp_path,
            "def identify(netlist, constraints):\n"
            "    refs: set[str] = set()\n"
            "    refs.update(constraints.high_power)\n"
            "    for tc in constraints.thermal:\n"
            "        refs.update(tc.components)\n"
            "    for comp in netlist.components:\n"
            "        if comp.ref in refs:\n"
            "            continue\n"
            "        if comp.ref.startswith('Q'):\n"
            "            refs.add(comp.ref)\n"
            "    return [c for c in netlist.components if c.ref in refs]\n",
        )
        assert findings == []

    def test_sorted_removes_the_order_dependency(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(refs: set[str], out: list):\n"
            "    for r in sorted(refs):\n"
            "        out.append(r)\n"
            "    return out\n",
        )
        assert findings == []

    def test_membership_and_len_are_not_flagged(self, tmp_path):
        findings = _analyze(
            tmp_path,
            "def f(refs: set[str], x):\n"
            "    if x in refs and len(refs) > 2:\n"
            "        return any(r for r in refs)\n"
            "    return None\n",
        )
        assert findings == []


class TestFailClosed:
    def test_empty_scope_fails(self, tmp_path):
        rc = gate.main(["--root", str(tmp_path), "--inventory", str(tmp_path / "inv")])
        assert rc == 1

    def test_unparseable_file_is_a_gate_error(self, tmp_path):
        _write(tmp_path, "packages/p/src/bad.py", "def (:\n")
        with pytest.raises(SystemExit) as excinfo:
            gate.analyze(tmp_path, gate.iter_scope_files(tmp_path))
        assert excinfo.value.code == 1


class TestInventory:
    def test_a_site_absent_from_the_inventory_fails(self, tmp_path):
        _write(tmp_path, "packages/p/src/m.py", "def f(s: set[str]):\n    return list(s)\n")
        inv = tmp_path / "inv"
        inv.write_text("", encoding="utf-8")
        rc = gate.main(["--root", str(tmp_path), "--inventory", str(inv), "--min-files", "1"])
        assert rc == 1

    def test_an_inventoried_site_passes(self, tmp_path):
        _write(tmp_path, "packages/p/src/m.py", "def f(s: set[str]):\n    return list(s)\n")
        inv = tmp_path / "inv"
        inv.write_text("packages/p/src/m.py::f::set-materialised 1\n", encoding="utf-8")
        rc = gate.main(["--root", str(tmp_path), "--inventory", str(inv), "--min-files", "1"])
        assert rc == 0

    def test_a_second_site_in_an_inventoried_function_fails(self, tmp_path):
        _write(
            tmp_path,
            "packages/p/src/m.py",
            "def f(s: set[str], t: set[str]):\n    return list(s), list(t)\n",
        )
        inv = tmp_path / "inv"
        inv.write_text("packages/p/src/m.py::f::set-materialised 1\n", encoding="utf-8")
        rc = gate.main(["--root", str(tmp_path), "--inventory", str(inv), "--min-files", "1"])
        assert rc == 1

    def test_a_stale_entry_fails(self, tmp_path):
        _write(tmp_path, "packages/p/src/m.py", "def f(s: set[str]):\n    return sorted(s)\n")
        inv = tmp_path / "inv"
        inv.write_text("packages/p/src/m.py::f::set-materialised 1\n", encoding="utf-8")
        rc = gate.main(["--root", str(tmp_path), "--inventory", str(inv), "--min-files", "1"])
        assert rc == 1, "a paid-down entry must be recorded, not silently tolerated"


class TestFreshSite:
    """The gate must catch a site it was not written against.

    ``pcl/`` is not one of the four modules that motivated this gate, was not
    read while writing it, and contributes zero entries to the inventory. A
    dependency injected there must be detected with no change to the gate.
    """

    FRESH_TARGET = REPO_ROOT / "packages/temper-placer/src/temper_placer/pcl/__init__.py"

    def test_pcl_is_not_in_the_inventory(self):
        inventory = (REPO_ROOT / ".hash-order-inventory").read_text(encoding="utf-8")
        assert "/pcl/" not in inventory, (
            "pcl/ now has inventoried sites, so it is no longer a fresh target; "
            "point this test at another module the gate has never flagged."
        )

    def test_detects_a_site_the_gate_was_not_written_against(self, tmp_path):
        assert self.FRESH_TARGET.is_file(), self.FRESH_TARGET
        original = self.FRESH_TARGET.read_text(encoding="utf-8")
        injected = original + (
            "\n\n"
            "def _fresh_site_probe(tags: frozenset[str], out: list) -> list:\n"
            "    for tag in tags:\n"
            "        out.append(tag)\n"
            "    return out\n"
        )
        try:
            self.FRESH_TARGET.write_text(injected, encoding="utf-8")
            findings = gate.analyze(REPO_ROOT, gate.iter_scope_files(REPO_ROOT))
            hits = [f for f in findings if f.qualname == "_fresh_site_probe"]
            assert hits, (
                "the gate missed a freshly injected hash-order dependency in a "
                "module it was never pointed at"
            )
            assert hits[0].construct == "set-loop-records-order"
            assert "pcl/__init__.py" in hits[0].path
        finally:
            self.FRESH_TARGET.write_text(original, encoding="utf-8")

        # And the tree is clean again afterwards.
        findings = gate.analyze(REPO_ROOT, gate.iter_scope_files(REPO_ROOT))
        assert not [f for f in findings if f.qualname == "_fresh_site_probe"]


class TestRealRepo:
    def test_gate_passes_on_this_branch(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/check_hash_order_determinism.py")],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_fixed_modules_are_no_longer_detected(self):
        findings = gate.analyze(REPO_ROOT, gate.iter_scope_files(REPO_ROOT))
        offenders = [
            f.render()
            for f in findings
            if f.path.endswith(("router_v6/channel_mapping.py", "router_v6/thermal_relief.py"))
        ]
        assert offenders == [], offenders

    def test_scans_the_real_surface(self):
        paths = gate.iter_scope_files(REPO_ROOT)
        assert len(paths) >= gate.MIN_FILES_SCANNED
        assert any(p.name == "channel_mapping.py" for p in paths)
        assert any(p.name == "thermal_relief.py" for p in paths)

    def test_inventory_matches_the_tree_exactly(self):
        findings = gate.analyze(REPO_ROOT, gate.iter_scope_files(REPO_ROOT))
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding.key] = counts.get(finding.key, 0) + 1
        inventory = gate.load_inventory(REPO_ROOT / ".hash-order-inventory")
        assert counts == inventory
