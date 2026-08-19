#!/usr/bin/env python3
"""CI entry point: DRC ratchet check.

Loads drc_ceiling.json, runs DRC on each board, checks against ceilings.
Exit codes: 0 = pass, 1 = ceiling exceeded, 2 = ceiling raised without
approval, 3 = noise-headroom guard failed (see below),
4 = a category count saturates KiCad's reporting cap (see below).

Cap-saturation guard (exit code 4)
----------------------------------
KiCad's DRC engine truncates per-category violation reports at
``ERROR_LIMIT`` (199) / ``EXTENDED_ERROR_LIMIT`` (499) — GUI list-widget
constants inherited by kicad-cli (``pcbnew/drc/drc_engine.cpp``; see
``docs/evidence/2026-08-12-dru-rule-precedence.md`` sec 4). A count at
exactly its category's cap is a SATURATION FLOOR (true count >= N), NOT a
count. When any measured per-type count is capped, or any committed
ceiling value itself sits at its category's cap ("a ceiling pinned to a
saturated value protects nothing"), the ratchet comparison for that
category is *inconclusive* — the true count can exceed the ceiling while
the capped reading never crosses it — so this script reports the
saturated categories with their ``DrcCount.display()`` rendering and fails
loudly (exit 4) instead of pretending the ceiling comparison meant
something. ``DrcRatchetResult.capped_error_categories`` /
``capped_warning_categories`` (populated by the kicad-cli backend) carry
the per-measurement signal; the ceiling scan below is a pure function of
the already-loaded ``drc_ceiling.json``.

Noise-headroom guard (exit code 3)
-----------------------------------
``DrcRatchet.check()`` runs ``run_drc`` exactly ONCE per invocation and
compares that single sample directly against the ceiling -- it does not
itself account for kicad-cli's documented run-to-run noise on a handful of
categories (``drc_ceiling.json``'s own ``nondeterministic_error_types``
block, populated by the file's 120-sample re-measurement protocol; see
AGENTS.md's "Board Change -> DRC Ceiling Re-measurement" section). Single-
sampling is safe only as long as every such category's ceiling headroom
(``ceiling - observed max``) is at least as wide as its own measured
spread (``observed max - observed min``) -- otherwise a single fresh
sample can land outside the historically-observed range from noise alone,
failing a board that never regressed. ``DrcRatchet.check_noise_headroom()``
checks that invariant against the already-committed ceiling data (no extra
DRC run, negligible added time) and this script fails loudly -- rather
than silently continuing to assume the single sample is representative --
the moment it does not hold for some category. See
``packages/temper-placer/src/temper_placer/regression/drc_ratchet.py``'s
``NoiseHeadroomViolation`` docstring for the full reasoning.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def _setup_path(repo_root: Path) -> None:
    import sys

    src_path = repo_root / "packages" / "temper-placer" / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def _regenerate_kicad_dru(repo_root: Path) -> Path:
    """Regenerate ``pcb/temper.kicad_dru`` from its SSOT generator script
    before measuring DRC with the kicad-cli backend.

    This file is neither git-tracked nor gitignored, and nothing previously
    generated it in CI -- so a local run could have a stale (or absent)
    rules file on disk while CI had a different one (or none at all), for
    byte-identical board content. That made kicad-cli's DRC output for the
    same board depend on ambient local state instead of committed inputs
    (custom rules add categories like ``track_width`` that bare kicad-cli
    never reports; see ``scripts/generate_kicad_dru.py``'s ``track_width``
    rules and the KiCad rule_severities schema).

    Regenerating unconditionally here -- on every kicad-cli-backend
    invocation, CI and local alike -- removes the ambiguity: the ratchet
    always measures against the one canonical rules file the SSOT script
    produces from ``TEMPER_NET_CLASSES``, never whatever happened to be
    left on disk from a prior run.
    """
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    import generate_kicad_dru

    content = generate_kicad_dru.generate_dru()
    generate_kicad_dru.OUTPUT_PATH.write_text(content, encoding="utf-8")
    return generate_kicad_dru.OUTPUT_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="DRC ratchet CI check")
    parser.add_argument(
        "--backend",
        type=str,
        default="kicad-cli",
        choices=["rust", "kicad-cli"],
        help="DRC backend: 'kicad-cli' (default, KiCad truth gate) or 'rust' (temper_drc_rs diagnostic)",
    )
    args = parser.parse_args()

    repo_root = _find_repo_root()
    _setup_path(repo_root)

    if args.backend == "kicad-cli":
        dru_path = _regenerate_kicad_dru(repo_root)
        print(
            f"Regenerated {dru_path.relative_to(repo_root)} from "
            "scripts/generate_kicad_dru.py (SSOT) before measuring"
        )

    ceiling_path = repo_root / "power_pcb_dataset" / "drc_ceiling.json"

    if not ceiling_path.exists():
        print(f"DRC ceiling not found: {ceiling_path}")
        print("DRC: SKIPPED (ceiling file not found)")
        return 0

    from _lib.drc_ceiling import load_ceiling

    from temper_placer.regression.drc_ratchet import DrcRatchet

    ratchet = DrcRatchet(ceiling_path, backend=args.backend)
    # The shared loader is the single read+parse entry point for
    # drc_ceiling.json across the three CI gates (see _lib/drc_ceiling.py);
    # load_data constructs the same DrcCeilingEntry dataclasses
    # DrcRatchet.load() always built, from the already-parsed dict.
    ratchet.load_data(load_ceiling(ceiling_path))

    if not ratchet.entries:
        print("DRC: SKIPPED (no boards in ceiling)")
        return 0

    results = ratchet.check(repo_root)

    exit_code = 0
    for result in results:
        if result.passed:
            print(f"PASS: {result.message}")
        else:
            print(f"FAIL: {result.message}")
            exit_code = max(exit_code, result.exit_code)

    # Cap-saturation guard: a measured count at exactly its category's
    # KiCad reporting cap is a floor ("true count >= N"), not a count, so a
    # ceiling comparison on it is inconclusive -- the true count can exceed
    # the ceiling while the capped reading never crosses it. Same for a
    # committed ceiling value that itself sits at a cap ("a ceiling pinned
    # to a saturated value protects nothing" -- the de-saturation correction
    # in PR #1178 raised ceilings to true counts for exactly this reason).
    # Fail loudly (exit 4) rather than let the comparison silently mean
    # nothing. See DrcCount (temper_drc_rs.drc_count) for the cap table.
    from temper_placer.validation._drc_api import classify_counts

    saturated: dict[str, str] = {}
    for result in results:
        saturated.update(result.capped_error_categories)
        saturated.update(result.capped_warning_categories)

    for board_id, entry in ratchet.entries.items():
        for rule, count in sorted(entry.violations_by_type.items()):
            info = classify_counts({rule: count})[rule]
            if info.is_capped:
                saturated[f"{board_id} ceiling errors[{rule}]"] = info.display
        for rule, count in sorted(entry.warnings_by_type.items()):
            info = classify_counts({rule: count})[rule]
            if info.is_capped:
                saturated[f"{board_id} ceiling warnings[{rule}]"] = info.display

    if saturated:
        print(
            "FAIL: cap-saturation guard -- DRC count(s) at KiCad's reporting "
            "cap are FLOORS (true count >= N), not counts; the ceiling "
            "comparison for these categories is inconclusive:"
        )
        for category, display in sorted(saturated.items()):
            print(f"  {category}: {display}")
        exit_code = max(exit_code, 4)
    else:
        print("PASS: cap-saturation guard (no category count at a KiCad reporting cap)")

    headroom_violations = ratchet.check_noise_headroom()
    if headroom_violations:
        print(
            "FAIL: noise-headroom guard -- single-sample DRC is not safe for "
            f"{len(headroom_violations)} nondeterministic categor"
            f"{'y' if len(headroom_violations) == 1 else 'ies'}:"
        )
        for violation in headroom_violations:
            print(f"  {violation.message}")
        exit_code = max(exit_code, 3)
    else:
        print("PASS: noise-headroom guard (single-sample DRC is safe for every recorded category)")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
