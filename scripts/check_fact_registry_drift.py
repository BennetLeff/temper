#!/usr/bin/env python3
"""Scalar fact-drift gate: a non-creepage/clearance value declared in more
than one place must agree, or the gate fails closed.

Motivation
----------
``scripts/check_creepage_clearance_drift.py`` (PR #1238) already gates
creepage/clearance millimetre figures. It deliberately does not scan for
other kinds of duplicated fact -- the 2026-08-17 fact-deduplication audit
(``docs/evidence/2026-08-17-fact-dedup-inventory-and-gate.md``) found the
same "one fact, many homes, drifting" shape recurring for values that are
not creepage or clearance: most concretely, this board's own **mains
voltage** and **pollution degree** (SafetySpec).

The concrete finding this gate encodes
----------------------------------------
This design is a US 120V RMS +-10% appliance (``docs/specs/REQUIREMENTS.md``
REQ-SYS-01: "AC Input Voltage: 120V RMS +-10%, US residential mains"),
confirmed independently by:

  - ``elec/src/main.ato`` -- ``v_ac_nominal = 120V``, with its own assertion
    ``assert v_ac_nominal within 100V to 130V`` (NEMA 5-15 tolerance).
  - ``docs/hardware/VOLTAGE_DOUBLER_DESIGN.md`` -- the voltage-doubler exists
    *specifically* so the appliance needs no 240V input ("Compatible with
    120V/15A outlet (no 240V required)").
  - ``docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`` Sec 2.1 (revision 1.4,
    2026-08-14) -- corrected its own "120-240V RMS" row to "120V RMS +-10%"
    to match REQ-SYS-01, and explicitly states "No 240V variant is intended
    for this design."

And the pollution degree this board enforces is **PD3** (2026-08-15,
``docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`` + PR #1224/#1229:
"PD3 governs (12.6mm reinforced, 10.0mm tank)").

Despite both being unambiguously decided, THREE other declaration sites
still carry the pre-decision values and have never been updated:

  - ``packages/temper-placer/configs/pcb_spec.yaml`` -- ``safety:
    mains_voltage_v: 230.0`` / ``pollution_degree: 2``. Feeds
    ``pipeline/derivation.py``'s ``hv_lv_isolation_mm`` derivation (consumed
    by the regression/scoring oracle, NOT the board's enforced DRC gate --
    see ``docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`` Sec 2.1 revision-history
    entry 1.4 for the prior, deliberately-not-fixed investigation of this
    exact site).
  - ``packages/temper-placer/src/temper_placer/core/design_rules.py`` --
    the ``ACMains`` net-class carries ``voltage_v=240.0``. Consumed by
    ``temper-drc-rs``'s ``partial_discharge.rs`` (>=60V HV-inner-layer
    filter -- both 120V and 240V clear the 60V threshold identically, so
    this specific consumer's *behaviour* does not change) and marshalled
    verbatim into WASM board-serialization and ``drc_ratchet.py`` reports
    (cosmetic passthrough). This exact site was already identified stale by
    the 2026-08-14 correction above and deliberately left unfixed pending an
    owner ("should be reconciled to 120V by whoever owns that config").
  - ``packages/temper-design-bundle/src/specification_contracts.rs`` -- the
    Rust ``SafetySpec`` pyclass's own ``#[new]`` default:
    ``mains_voltage_v: opt_or(py, mains_voltage_v, 230.0_f64)``,
    ``pollution_degree: opt_or(py, pollution_degree, 2_i64)``. Python's own
    ``SafetySpec`` (``temper_placer.core.specification``) is a bare
    re-export of this Rust pyclass (``SafetySpec = _tdb.specification_
    contracts.SafetySpec``) -- there is no independent Python default to
    also fix; this Rust default IS the only runtime default in the whole
    system.

Why this gate does not fix these itself
------------------------------------------
The correct VALUES are not in question (120.0 / PD3) -- this is NOT a
judgment call like the drift gate's own open ``[clearance/reinforced]``
family. What blocks a mechanical fix is that both the ``design_rules.py``
and ``specification_contracts.rs`` sites are pinned-oracle-entangled:

  - ``design_rules.py``'s ACMains ``voltage_v=240.0`` is differentially
    compared, field-for-field, against the PINNED oracle
    ``tests/core/_design_rules_py_oracle.py`` (hash-pinned in
    ``scripts/oracle_hashes.json``; also carries its own ``voltage_v=240.0``
    for the matching class). Changing production without the oracle would
    fail ``test_design_rules_field_parity.py``/``test_design_rules_rust_
    differential.py``; changing the oracle requires the separate, deliberate
    re-pin ceremony this repo's own rules reserve for oracle changes.
  - ``specification_contracts.rs``'s Rust default is differentially compared
    against the PINNED oracle ``tests/core/_specification_py_oracle.py``
    (also hash-pinned; ``mains_voltage_v: float = 230.0`` /
    ``pollution_degree: int = 2``) AND is asserted directly by
    ``tests/core/test_specification.py::test_safety_spec_defaults`` --
    itself a live instance of handoff Sec 11's thesis ("a running,
    CI-required test asserted a wrong safety value"): it asserts
    ``s.mains_voltage_v == pytest.approx(230.0)`` under the docstring
    "SafetySpec default values match IEC 60335-1 typical consumer
    appliance" -- a generic justification, not one that is true of this
    specific 120V design.
  - ``pcb_spec.yaml`` itself is NOT oracle-pinned and could be edited
    directly, but its value flows into the SAME oracle-compared derivation
    surface (``_physics_oracle_py_oracle.py`` defaults to loading this exact
    file when no explicit spec path is given), so fixing it in isolation,
    without also verifying the physics-oracle differential surface end to
    end, risks silently breaking a pinned comparison this gate has not
    exhaustively swept. Left for the same coordinated fix.

So: this is a MECHANIZED, VERIFIED, currently-failing gate, deliberately
left red. Un-redding it requires one coordinated PR that (1) updates all
three production sites to 120.0/3, (2) re-pins both affected oracles per
the standing oracle re-pin ceremony with the required exhaustive-divergence
evidence, and (3) fixes ``test_safety_spec_defaults`` and ``test_load_pcb_
spec_yaml_has_safety`` to assert the corrected values. That is a deliberate,
attributed, single act -- explicitly NOT something this gate, or the agent
that wrote it, may do by fiat.

Design
------
Unlike ``check_creepage_clearance_drift.py``'s whole-repo AST discovery,
this gate is an EXPLICIT registry (mirrors ``duplicate_predicate_registry.
py``'s own rationale: a hand-reviewed, falsifiable list of sites already
proven to hold this fact, not a repo-wide sweep for arbitrary numbers named
"voltage" -- most such numbers are unrelated per-component ratings, not
declarations of the system's own mains input). Adding a new fact is a
reviewed act, matching this repo's established convention for narrowly
scoped ``check_*.py`` gates.

Exit codes (mirrors check_creepage_clearance_drift.py / check_duplicate_predicates.py)
------------------------------------------------------------------------------------------
  0 - CLEAN: registry non-empty, every home found and matched its pattern,
      every home's value equals its fact's authoritative value.
  3 - VIOLATION: at least one home's extracted value diverges from its
      fact's authoritative value.
  5 - TOOL ERROR: registry empty (vacuous), a home file is missing, or a
      home's pattern failed to match at all (the site drifted structurally
      -- e.g. renamed field -- and the gate can no longer trust its own
      scan; never conflated with "0 violations").

Usage
-----
  uv run --no-sync python scripts/check_fact_registry_drift.py
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_CLEAN = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass(frozen=True)
class FactSite:
    """One declaration site for a Fact."""

    file: str  # repo-relative path
    description: str
    pattern: str  # regex with exactly one capture group: the value
    scope_anchor: str | None = None  # optional regex; search is scoped to
    # the window starting at the anchor's match, so the same field name
    # elsewhere in the file (a different net class, a different struct)
    # cannot be matched by accident.
    scope_lines: int = 40


@dataclass(frozen=True)
class Fact:
    name: str
    category: str
    authoritative_value: float
    value_kind: str  # "float" | "int" (controls comparison + rendering)
    authoritative_source: str
    homes: tuple[FactSite, ...]
    notes: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: tuple[Fact, ...] = (
    Fact(
        name="mains_voltage_v",
        category="board-spec",
        authoritative_value=120.0,
        value_kind="float",
        authoritative_source=(
            "docs/specs/REQUIREMENTS.md REQ-SYS-01 ('AC Input Voltage: 120V "
            "RMS +-10%, US residential mains'); cross-confirmed by elec/src/"
            "main.ato's own 'assert v_ac_nominal within 100V to 130V' and "
            "docs/hardware/VOLTAGE_DOUBLER_DESIGN.md ('Compatible with "
            "120V/15A outlet (no 240V required)'). No 240V (or 120/240V "
            "dual-input) variant is declared as a design target anywhere."
        ),
        homes=(
            FactSite(
                file="elec/src/main.ato",
                description="atopile SSOT nominal AC input",
                pattern=r"v_ac_nominal\s*=\s*([\d.]+)V",
            ),
            FactSite(
                file="packages/temper-placer/configs/pcb_spec.yaml",
                description="placer physical-spec safety.mains_voltage_v",
                pattern=r"mains_voltage_v:\s*([\d.]+)",
            ),
            FactSite(
                file=(
                    "packages/temper-placer/src/temper_placer/core/"
                    "design_rules.py"
                ),
                description="ACMains net-class metadata voltage_v",
                pattern=r"voltage_v=([\d.]+),",
                scope_anchor=r'"ACMains":\s*NetClassRules\(',
            ),
            FactSite(
                file="packages/temper-design-bundle/src/specification_contracts.rs",
                description="Rust SafetySpec::new() default mains_voltage_v",
                pattern=r"mains_voltage_v,\s*([\d.]+)_f64",
            ),
        ),
        notes=(
            "KNOWN RED (see module docstring): design_rules.py and "
            "specification_contracts.rs are pinned-oracle-entangled; "
            "pcb_spec.yaml shares their derivation surface. Fixing requires "
            "a coordinated PR with an oracle re-pin, not a mechanical edit "
            "here."
        ),
    ),
    Fact(
        name="pollution_degree",
        category="board-spec",
        authoritative_value=3.0,
        value_kind="int",
        authoritative_source=(
            "docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md + PR "
            "#1224/#1229: 'PD3 governs (12.6mm reinforced, 10.0mm tank)'."
        ),
        homes=(
            FactSite(
                file="packages/temper-placer/configs/pcb_spec.yaml",
                description="placer physical-spec safety.pollution_degree",
                pattern=r"pollution_degree:\s*(\d+)",
            ),
            FactSite(
                file="packages/temper-design-bundle/src/specification_contracts.rs",
                description="Rust SafetySpec::new() default pollution_degree",
                pattern=r"pollution_degree,\s*(\d+)_i64",
            ),
        ),
        notes=(
            "KNOWN RED (see module docstring): both homes are "
            "pinned-oracle-entangled (same SafetySpec sites as "
            "mains_voltage_v). Same coordinated-fix requirement."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


@dataclass
class SiteResult:
    fact: str
    site: FactSite
    found_value: float | None
    matches: bool
    error: str | None = None


def _extract(repo_root: Path, fact: Fact, site: FactSite) -> SiteResult:
    path = repo_root / site.file
    if not path.is_file():
        return SiteResult(
            fact=fact.name,
            site=site,
            found_value=None,
            matches=False,
            error=f"file not found: {site.file}",
        )
    text = path.read_text(encoding="utf-8")

    search_text = text
    if site.scope_anchor is not None:
        anchor_re = re.compile(site.scope_anchor)
        anchor_match = anchor_re.search(text)
        if anchor_match is None:
            return SiteResult(
                fact=fact.name,
                site=site,
                found_value=None,
                matches=False,
                error=(
                    f"scope anchor {site.scope_anchor!r} not found in "
                    f"{site.file}"
                ),
            )
        # Scope the search to N lines starting at the anchor, so the same
        # field name elsewhere in the file cannot be matched by accident.
        start = anchor_match.start()
        prefix_lines = text[:start].count("\n")
        all_lines = text.splitlines(keepends=True)
        window = "".join(all_lines[prefix_lines : prefix_lines + site.scope_lines])
        search_text = window

    value_re = re.compile(site.pattern)
    value_match = value_re.search(search_text)
    if value_match is None:
        return SiteResult(
            fact=fact.name,
            site=site,
            found_value=None,
            matches=False,
            error=f"pattern {site.pattern!r} did not match in {site.file}",
        )
    raw = value_match.group(1)
    try:
        found = float(raw)
    except ValueError:
        return SiteResult(
            fact=fact.name,
            site=site,
            found_value=None,
            matches=False,
            error=f"matched value {raw!r} in {site.file} is not numeric",
        )

    matches = abs(found - fact.authoritative_value) < 1e-9
    return SiteResult(fact=fact.name, site=site, found_value=found, matches=matches)


def run(repo_root: Path) -> list[SiteResult]:
    if not REGISTRY:
        raise GateError("REGISTRY is empty -- vacuous run, refusing to report clean")
    results: list[SiteResult] = []
    for fact in REGISTRY:
        if not fact.homes:
            raise GateError(f"fact {fact.name!r} has zero homes -- vacuous entry")
        for site in fact.homes:
            results.append(_extract(repo_root, fact, site))
    return results


def _fmt_value(v: float, kind: str) -> str:
    return str(int(v)) if kind == "int" else f"{v:g}"


def _print_report(results: list[SiteResult]) -> tuple[bool, bool]:
    by_fact: dict[str, list[SiteResult]] = {}
    for r in results:
        by_fact.setdefault(r.fact, []).append(r)

    facts_by_name = {f.name: f for f in REGISTRY}
    has_violation = False
    has_tool_error = False

    for name, site_results in by_fact.items():
        fact = facts_by_name[name]
        print(f"=== {fact.category}/{fact.name} ===")
        print(f"  Authoritative: {_fmt_value(fact.authoritative_value, fact.value_kind)}")
        print(f"  Source: {fact.authoritative_source}")
        for r in site_results:
            if r.error is not None:
                has_tool_error = True
                print(f"  TOOL ERROR  {r.site.file}: {r.error}")
                continue
            assert r.found_value is not None
            tag = "OK  " if r.matches else "DIFF"
            if not r.matches:
                has_violation = True
            print(
                f"  {tag}  {r.site.file} ({r.site.description}): "
                f"{_fmt_value(r.found_value, fact.value_kind)}"
            )
        if fact.notes:
            print(f"  Notes: {fact.notes}")
        print()

    return has_violation, has_tool_error


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.parse_args()

    repo_root = find_repo_root()

    try:
        results = run(repo_root)
    except GateError as e:
        print(f"TOOL ERROR: {e}")
        sys.exit(EXIT_TOOL_ERROR)

    has_violation, has_tool_error = _print_report(results)

    if has_tool_error:
        state = "tool_error"
    elif has_violation:
        state = "violation"
    else:
        state = "clean"

    if state == "clean":
        print(f"PASS -- {len(REGISTRY)} fact(s), {len(results)} site(s), 0 divergences.")
    elif state == "violation":
        print(
            "FAILED -- a registered fact has homes with disagreeing values. "
            "See the notes above for whether this is a known, deliberately "
            "left-red finding (do not silently 'fix' by editing this "
            "registry's authoritative_value to match the wrong site)."
        )
    else:
        print(
            "TOOL ERROR -- a home file, scope anchor, or value pattern could "
            "not be resolved; the scan cannot be trusted as-is."
        )

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Fact registry drift gate: {state}\n")
            f.write(f"- Facts checked: {len(REGISTRY)}\n")
            f.write(f"- Sites checked: {len(results)}\n")

    if state == "tool_error":
        sys.exit(EXIT_TOOL_ERROR)
    sys.exit(EXIT_VIOLATION if has_violation else EXIT_CLEAN)


if __name__ == "__main__":
    main()
