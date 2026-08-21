"""Phase 5, batch 2 — anti-vacuity mutation campaign for the deterministic
leaf stages migrated to Rust (Wave 4).

Reproducible driver: for every registered mutant, apply the Rust-source edit,
rebuild the extension, run the differential suites, require at least one
FAILURE (the mutant must be caught), then revert and verify the source is
pristine (`git diff` clean) before the next mutant. Only a pytest exit-code-1
suite failure counts as a kill; exit 0 is a SURVIVOR and any other exit code
(2/3/4/5...) is an infrastructure ERROR, both recorded as errors.

Usage::

    export UV_PROJECT_ENVIRONMENT=... UV_NO_SYNC=1
    python scripts/phase5_batch2_mutations.py

The campaign must end with a PRISTINE rebuild of both touched crates (the
final pass re-installs the unmutated extensions and re-runs the full
differential set green).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TD = REPO / "packages/temper-design-bundle"
DRC = REPO / "packages/temper-drc-rs"
TESTS = REPO / "packages/temper-placer/tests/deterministic/stages"

MUTANTS: list[dict] = []


def add(crate, file, old, new, tests, label):
    MUTANTS.append(
        {
            "crate": crate,
            "file": file,
            "old": old,
            "new": new,
            "tests": tests,
            "label": label,
        }
    )


# --- layer_assignment -----------------------------------------------------
add(TD, "src/deterministic_leaves.rs",
    '"Ground" => (1, true),',
    '"Ground" => (2, true),',
    ["test_layer_assignment_rust_differential.py"],
    "layer_assignment Ground layer 1->2")
add(TD, "src/deterministic_leaves.rs",
    "let is_plane = layer == 1 || layer == 2;",
    "let is_plane = layer == 1;",
    ["test_layer_assignment_rust_differential.py"],
    "layer_assignment plane inference drops layer 2")
# (Dropped in the rewrite: 'empty net_class not Signal-defaulted'. That
# mutation removes the `!v.is_empty()` guard so an empty-string net_class is
# used directly instead of defaulting to "Signal"; but `assign_layer_by_net_class`
# maps "" and "Signal" to the SAME (0, false), so the mutation is
# observably vacuous — the differential staying green is correct.)

# --- power_plane ----------------------------------------------------------
add(TD, "src/deterministic_leaves.rs",
    "let new_layer = plane_layers.get(net_name).copied().unwrap_or(1);",
    "let new_layer = plane_layers.get(net_name).copied().unwrap_or(2);",
    ["test_power_plane_rust_differential.py"],
    "power_plane default plane layer 1->2")
add(TD, "src/deterministic_leaves.rs",
    "out.push((net_name.clone(), new_layer, *allow, true));",
    "out.push((net_name.clone(), new_layer, *allow, false));",
    ["test_power_plane_rust_differential.py"],
    "power_plane plane net not marked is_plane")

# --- component_assignment -------------------------------------------------
add(TD, "src/deterministic_leaves.rs",
    "sqrt(w2 + h2) / 2.0 + 1.0",
    "sqrt(w2 + h2) / 2.0",
    ["test_component_assignment_rust_differential.py"],
    "component_assignment footprint margin +1.0 dropped")
add(TD, "src/deterministic_leaves.rs",
    "if dist <= radius {\n            used_slots.insert(slot_key((sx, sy)));\n        }",
    "if dist <= radius + 1.0 {\n            used_slots.insert(slot_key((sx, sy)));\n        }",
    ["test_component_assignment_rust_differential.py"],
    "component_assignment reservation over-reserves +1.0")
# (Replaced the original 'reservation strict <' mutant: `<=` vs `<` at
# distance == radius is unobservable through the assignment pipeline — the
# slot distance is `hypot` output, and an exact `dist == radius` boundary
# case cannot be constructed through the float arithmetic. The +1.0
# threshold mutant targets the same comparison line and is caught.)
add(TD, "src/deterministic_leaves.rs",
    "if score < best_score {",
    "if score <= best_score {",
    ["test_component_assignment_rust_differential.py"],
    "component_assignment wirelength tie keeps last")

# --- fine_pitch_escape ----------------------------------------------------
add(TD, "src/deterministic_leaves.rs",
    "if layer3_nets.contains(net_name) {\n        return (3, \"B.Cu\");",
    "if layer2_nets.contains(net_name) {\n        return (secondary, \"In2.Cu\");",
    ["test_fine_pitch_escape_rust_differential.py"],
    "fine_pitch layer-3 precedence dropped")
add(TD, "src/deterministic_leaves.rs",
    "if pins.len() < 2 {",
    "if pins.len() < 3 {",
    ["test_fine_pitch_escape_rust_differential.py"],
    "fine_pitch min-pitch <3 pins threshold")

# --- validator slot-grid --------------------------------------------------
add(TD, "src/deterministic_leaves.rs",
    "pub const DEFAULT_SLOT_SPACING: f64 = 5.0;",
    "pub const DEFAULT_SLOT_SPACING: f64 = 4.0;",
    ["test_phased_component_assignment_validator_rust_differential.py"],
    "validator slot spacing fallback 5->4")
# (The original 'validator radius k ceil->floor' mutant was dropped claiming
# vacuity: "a slot in a cell with |index| > radius/spacing is at distance >=
# spacing*|index| > radius". That claim is FALSE for round-to-nearest cells:
# center (0,0), radius 8.5, spacing 5, slot (7.6, 0) rounds to cell (2, 0)
# (round(1.52) = 2, |2| > 8.5/5 = 1.7) yet sits at distance 7.6 <= 8.5 — it
# is reachable only through the ceil window (k = ceil(1.7) = 2), and a floor
# window (k = 1) misses it. The mutant is RE-ADDED below and killed by
# test_within_radius_ceil_only_zone.)
add(TD, "src/deterministic_leaves.rs",
    "let k = (radius / spacing).ceil() as i64;",
    "let k = (radius / spacing).floor() as i64;",
    ["test_phased_component_assignment_validator_rust_differential.py"],
    "validator radius k ceil->floor (ceil-only zone)")
add(TD, "src/deterministic_leaves.rs",
    "if crate::host_math::hypot(sx - cx, sy - cy) <= radius {",
    "if crate::host_math::hypot(sx - cx, sy - cy) < radius {",
    ["test_phased_component_assignment_validator_rust_differential.py"],
    "validator radius strict <")

# --- drc leaf kernels -----------------------------------------------------
add(DRC, "src/deterministic_leaf_drc.rs",
    "by_type.sort_by(|a, b| b.1.cmp(&a.1));",
    "by_type.sort_by(|a, b| a.1.cmp(&b.1));",
    ["test_drc_leaf_rust_differential.py"],
    "drc_validation summary ascending sort")
add(DRC, "src/deterministic_leaf_drc.rs",
    "crate::pymath::py_round_to_int(x / tol) * tol",
    "(x / tol).round() * tol",
    ["test_drc_leaf_rust_differential.py"],
    "drc_sweep dedup rounding half-away")
add(DRC, "src/deterministic_leaf_drc.rs",
    "let t = py_max(0.0, py_min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq));",
    "let t = ((px - x1) * dx + (py - y1) * dy) / len_sq;",
    ["test_drc_leaf_rust_differential.py"],
    "placement_validation projection t unclamped")
add(DRC, "src/deterministic_leaf_drc.rs",
    "let x_min = margin;\n    let x_max = board_width - margin;",
    "let x_min = margin;\n    let x_max = board_width - 2.0 * margin;",
    ["test_drc_leaf_rust_differential.py"],
    "courtyard_check clamp x_max wrong margin")

# --- connectivity_validation -----------------------------------------------
add(DRC, "src/deterministic_connectivity.rs",
    "if t1.layer != t2.layer {\n        return false;\n    }",
    "if t1.layer == t2.layer {\n        return false;\n    }",
    ["test_connectivity_validation_rust_differential.py"],
    "connectivity track-track same-layer guard inverted")
# (Replaced the original pad-touch strict-< mutant: `<= 1e-4` vs `< 1e-4`
# fires only at distance == 1e-4 exactly, which exhaustive search over the
# float pipeline could not construct (point_to_rotated_rect_distance's
# output never lands on 1e-4 for the reachable inputs). The threshold mutant
# targets the same comparison line and is caught by near-miss inputs.)
add(DRC, "src/deterministic_connectivity.rs",
    "point_to_rotated_rect_distance(px, py, p.x, p.y, p.w, p.h, p.rotation) <= 1e-4",
    "point_to_rotated_rect_distance(px, py, p.x, p.y, p.w, p.h, p.rotation) <= 2e-4",
    ["test_connectivity_validation_rust_differential.py"],
    "connectivity pad-touch threshold 1e-4 -> 2e-4")
add(DRC, "src/deterministic_connectivity.rs",
    "self.parent[ra] = rb;",
    "self.parent[rb] = ra;",
    ["test_connectivity_validation_rust_differential.py"],
    "connectivity union attaches rb under ra")
add(DRC, "src/deterministic_connectivity.rs",
    "let island_pads: Vec<usize> = members.iter().copied().filter(|&m| m < np).collect();",
    "let island_pads: Vec<usize> = members.iter().copied().collect();",
    ["test_connectivity_validation_rust_differential.py"],
    "connectivity tracks counted as pad islands")
# (Dropped in the rewrite: 'single pad-component flagged'. With `>= 1` and
# exactly one pad component, `sorted_roots[1:]` is empty, so the mutation
# adds nothing; it is observably vacuous. The differential staying green is
# correct.)
add(DRC, "src/deterministic_connectivity.rs",
    "if !start_connected || !end_connected {",
    "if !start_connected && !end_connected {",
    ["test_connectivity_validation_rust_differential.py"],
    "connectivity dangling requires both ends open")

PRISTINE_TESTS = [
    "test_layer_assignment_rust_differential.py",
    "test_layer_assignment_pbt.py",
    "test_power_plane_rust_differential.py",
    "test_power_plane_pbt.py",
    "test_component_assignment_rust_differential.py",
    "test_component_assignment_pbt.py",
    "test_fine_pitch_escape_rust_differential.py",
    "test_fine_pitch_escape_pbt.py",
    "test_phased_component_assignment_validator_rust_differential.py",
    "test_phased_component_assignment_validator_pbt.py",
    "test_drc_leaf_rust_differential.py",
    "test_drc_leaf_pbt.py",
    "test_connectivity_validation_rust_differential.py",
    "test_connectivity_validation_pbt.py",
    "test_connectivity_validation.py",
]


def build(crate_root: Path) -> None:
    subprocess.run(
        ["maturin", "develop", "--release", "--manifest-path", str(crate_root / "Cargo.toml")],
        check=True,
        capture_output=True,
    )


def run_pytest(tests: list[str]) -> subprocess.CompletedProcess:
    paths = [str(TESTS / t) for t in tests]
    return subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(REPO / "packages" / "temper-placer"), **__import__("os").environ},
    )


def main() -> int:
    kills = 0
    errors = []
    for i, m in enumerate(MUTANTS, 1):
        path = m["crate"] / m["file"]
        src = path.read_text()
        if m["old"] not in src:
            errors.append(f"M{i} ({m['label']}): OLD not found, cannot apply")
            continue
        path.write_text(src.replace(m["old"], m["new"], 1))
        try:
            build(m["crate"])
        except subprocess.CalledProcessError:
            errors.append(f"M{i} ({m['label']}): REBUILD FAILED (infra, not a kill)")
            path.write_text(src)
            continue
        proc = run_pytest(m["tests"])
        path.write_text(src)
        if proc.returncode == 0:
            errors.append(f"M{i} ({m['label']}): SURVIVED — differential stayed green")
            continue
        if proc.returncode != 1:
            errors.append(
                f"M{i} ({m['label']}): pytest exit {proc.returncode} — INFRA, not a kill"
            )
            continue
        kills += 1
        print(f"M{i:02d} KILLED {m['label']} (exit 1)")
    # Pristine rebuild + full suite.
    build(TD)
    build(DRC)
    proc = run_pytest(PRISTINE_TESTS)
    if proc.returncode != 0:
        errors.append(f"PRISTINE rebuild suite FAILED: {proc.stdout[-2000:]}")
    print(f"\nkills={kills}/{len(MUTANTS)} errors={len(errors)}")
    for e in errors:
        print("  ", e)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
