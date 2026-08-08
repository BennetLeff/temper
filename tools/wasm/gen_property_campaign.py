#!/usr/bin/env python3
"""Regenerate the seeded #[test] wrapper block in
packages/temper-drc-rs/src/rules/drc/property_campaigns.rs.

Why this exists
----------------
`temper_run_test(index)` (the wasm32 host ABI, see
`packages/temper-wasm-test-runner/src/lib.rs`) dispatches by a flat
`(name, fn())` registry index -- there is no way to pass a `u64` seed
argument at call time. So each distinct seed needs its own zero-argument
`#[test]` wrapper function; `scripts/gen_wasm_test_registry.py` then picks
up each one (by scanning `#[test]` attributes inside an eligible module's
`tests` block) and folds it into the crate-wide registry automatically.
This script generates ONLY those thin wrappers -- one line each, calling a
hand-written `..._impl(seed)` property function -- between the
`// --- BEGIN/END generated seeded property wrappers ---` markers already
present in `property_campaigns.rs`. It does not touch anything else in
that file (the corpus, the geometry helpers, the property implementations,
or the hand-written sanity tests all live outside the markers).

Usage
-----
    python3 tools/wasm/gen_property_campaign.py [--seeds N] [--check]

`--seeds N` (default 300) sets how many seeds each property gets; rerun
after changing `PROPERTIES` below (e.g. adding a new property) or to scale
the volume campaign up or down, then run
`python3 scripts/gen_wasm_test_registry.py` to fold the new wrapper names
into the crate-wide wasm registry.

`--check` fails (without writing) if the committed block has drifted from
what this script would generate -- the same drift-gate convention
`scripts/gen_wasm_test_registry.py --check` uses. Run this script BEFORE
`scripts/gen_wasm_test_registry.py`: that second script rewrites every
`#[test]` in the `tests` module (including this block's) to
`#[cfg_attr(test, test)]` so the functions survive into a non-test wasm32
build (see its own docstring) -- `--check` here tolerates either spelling
so running it after `gen_wasm_test_registry.py` doesn't falsely report
drift, but writing (no `--check`) always emits plain `#[test]`.

Properties NOT listed here (currently
`edge_distance_monotonic_under_separation_impl`) are deliberately excluded:
see that function's doc comment in `property_campaigns.rs` for why (it
fails at real volume on fully-nested real geometry, and that failure is a
genuine finding documented in
`docs/evidence/2026-08-07-property-campaign-containment-gap.md`, not
something to wrap into an always-green registry entry).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "packages" / "temper-drc-rs" / "src" / "rules" / "drc" / "property_campaigns.rs"

BEGIN = "    // --- BEGIN generated seeded property wrappers (tools/wasm/gen_property_campaign.py) ---"
END = "    // --- END generated seeded property wrappers ---"

# (short name used in the generated fn, the hand-written `..._impl` fn it calls).
# Order matters only for readability of the generated block.
PROPERTIES: list[tuple[str, str]] = [
    ("symmetric", "edge_distance_symmetric_impl"),
    ("translation_invariant", "edge_distance_translation_invariant_impl"),
    ("rotation_invariant", "edge_distance_rotation_invariant_impl"),
    ("scale_invariant", "edge_distance_scale_invariant_impl"),
    ("naive_reference_agreement", "edge_distance_naive_reference_agreement_impl"),
]


def generated_block(n_seeds: int) -> str:
    lines = [BEGIN]
    lines.append(
        f"    // {len(PROPERTIES)} properties x {n_seeds} seeds = "
        f"{len(PROPERTIES) * n_seeds} distinct-input wasm tests."
    )
    for short, impl in PROPERTIES:
        for seed in range(n_seeds):
            lines.append("    #[test]")
            lines.append(f"    fn {short}_seed_{seed:06d}() {{ {impl}({seed}); }}")
    lines.append(END)
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=300, help="seeds per property (default 300)")
    ap.add_argument("--check", action="store_true", help="fail on drift instead of writing")
    args = ap.parse_args()

    text = TARGET.read_text()
    try:
        begin_idx = text.index(BEGIN)
        end_idx = text.index(END, begin_idx) + len(END)
    except ValueError:
        print(f"could not find the generated-block markers in {TARGET}", file=sys.stderr)
        return 2

    new_block = generated_block(args.seeds)
    new_text = text[:begin_idx] + new_block.rstrip("\n") + text[end_idx:]

    if args.check:
        # Tolerate scripts/gen_wasm_test_registry.py's `#[test]` ->
        # `#[cfg_attr(test, test)]` rewrite (see docstring above): compare
        # with that one substitution normalized away on both sides.
        norm = lambda s: s.replace("#[cfg_attr(test, test)]", "#[test]")
        if norm(new_text) != norm(text):
            print("property campaign wrapper block is stale; run tools/wasm/gen_property_campaign.py")
            return 1
        print(f"property campaign wrappers up to date: {len(PROPERTIES)} properties x {args.seeds} seeds")
        return 0

    if new_text != text:
        TARGET.write_text(new_text)
        print(f"wrote {len(PROPERTIES) * args.seeds} wrapper tests to {TARGET.relative_to(REPO_ROOT)}")
    else:
        print("no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
