"""Phase 5, final leaves — anti-vacuity mutation campaign for the final
deterministic leaf kernels migrated to Rust (Wave 4).

Reproducible driver: for every registered mutant, apply the Rust-source edit,
rebuild the owning crate, run the owning differential suite, require at least
one FAILURE (the mutant must be caught), then revert and verify the source is
pristine (`git diff` clean) before the next mutant. Only a pytest exit-code-1
suite failure counts as a kill; exit 0 is a SURVIVOR and any other exit code
(2/3/4/5...) is an infrastructure ERROR, both recorded as errors.

Usage::

    source scripts/cargo_shared_env.sh        # shared CARGO_TARGET_DIR
    export UV_NO_SYNC=1
    python scripts/phase5_final_leaves_mutations.py

The campaign must end with a PRISTINE rebuild of both touched crates (the
final pass re-installs the unmutated extensions and re-runs the full
differential + PBT set green).
"""

from __future__ import annotations

import os
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


# --- effective_ghost_pad_radius (deterministic_phase.rs) ---------------------
add(TD, "src/deterministic_phase.rs",
    "let d_len = crate::host_math::hypot(dx, dy);",
    "let d_len = (dx * dx + dy * dy).sqrt();",
    ["test_phase_rotation_rust_differential.py"],
    "ghost-pad hypot Dekker->libm (last-ulp divergence)")
add(TD, "src/deterministic_phase.rs",
    "if projection > 0.0 {",
    "if projection != 0.0 {",
    ["test_phase_rotation_rust_differential.py"],
    "ghost-pad negative projections accumulate")
add(TD, "src/deterministic_phase.rs",
    "py_max(0.0, base_radius - reduction)",
    "base_radius - reduction",
    ["test_phase_rotation_rust_differential.py"],
    "ghost-pad clamp dropped")

# --- compute_wirelength (deterministic_phase.rs) -----------------------------
add(TD, "src/deterministic_phase.rs",
    "let component_on_net = pins.iter().any(|(ref_, _)| ref_ == component_ref);",
    "let component_on_net = pins.iter().all(|(ref_, _)| ref_ == component_ref);",
    ["test_phase_zones_rust_differential.py"],
    "hpwl net-membership any->all")
add(TD, "src/deterministic_phase.rs",
    "(py_list_max(&xs) - py_list_min(&xs)) + (py_list_max(&ys) - py_list_min(&ys))",
    "py_list_max(&xs) - py_list_min(&xs)",
    ["test_phase_zones_rust_differential.py"],
    "hpwl y-axis term dropped")

# --- find_critical_bottleneck_violations (deterministic_phase.rs) ------------
add(TD, "src/deterministic_phase.rs",
    "out.push((\n                ref_.clone(),\n                gx,\n                gy,\n                layer.clone(),\n                last_severity.clone().unwrap_or_default(),\n            ));",
    "out.push((\n                ref_.clone(),\n                gx,\n                gy,\n                layer.clone(),\n                \"CRITICAL\".to_string(),\n            ));",
    ["test_phase_validation_rust_differential.py"],
    "bottleneck severity reads matched cell (bug corrected)")
add(TD, "src/deterministic_phase.rs",
    "Some((_, existing_score)) => *score > *existing_score,",
    "Some((_, existing_score)) => *score >= *existing_score,",
    ["test_phase_validation_rust_differential.py"],
    "bottleneck score tie last-wins")
add(TD, "src/deterministic_phase.rs",
    "Ok(q.floor() as i64)",
    "Ok(q.trunc() as i64)",
    ["test_phase_validation_rust_differential.py"],
    "bottleneck grid index trunc (not floor)")

# --- point_in_polygon / point_to_segment_distance (deterministic_phase.rs) ---
add(TD, "src/deterministic_phase.rs",
    "if y > py_min(p1y, p2y) && y <= py_max(p1y, p2y) && x <= py_max(p1x, p2x) {",
    "if y > py_min(p1y, p2y) && y < py_max(p1y, p2y) && x <= py_max(p1x, p2x) {",
    ["test_zone_aware_slot_generation_rust_differential.py"],
    "ray-cast top edge open (y <= max -> y < max)")
add(TD, "src/deterministic_phase.rs",
    "pow(pow(px - proj_x, 2.0) + pow(py - proj_y, 2.0), 0.5)",
    "crate::host_math::sqrt(pow(px - proj_x, 2.0) + pow(py - proj_y, 2.0))",
    ["test_zone_aware_slot_generation_rust_differential.py"],
    "point-segment **0.5 -> sqrt (1-ulp divergence)")

# --- count_connected_layers (temper-drc-rs) ----------------------------------
add(DRC, "src/deterministic_leaf_drc.rs",
    "if is_plane && plane_layers.contains(layer) {",
    "if plane_layers.contains(layer) {",
    ["test_via_validation_rust_differential.py"],
    "via plane-layer auto-connect drops is_plane gate")
add(DRC, "src/deterministic_leaf_drc.rs",
    "if !connected_layers.contains(layer)\n            && let Some(pts) = pin_index.get(layer)\n        {\n            for &(px, py) in pts {\n                let dist_sq = pow(vx - px, 2.0) + pow(vy - py, 2.0);\n                if dist_sq <= tol_sq {",
    "if !connected_layers.contains(layer)\n            && let Some(pts) = pin_index.get(layer)\n        {\n            for &(px, py) in pts {\n                let dist_sq = pow(vx - px, 2.0) + pow(vy - py, 2.0);\n                if dist_sq < tol_sq {",
    ["test_via_validation_rust_differential.py"],
    "via pin-sweep boundary <= -> <")

# --- dedup_via_positions (temper-drc-rs) --------------------------------------
add(DRC, "src/deterministic_leaf_drc.rs",
    "if dist_sq <= tol_sq {\n                is_duplicate = true;\n                duplicates += 1;\n                break;\n            }",
    "if dist_sq < tol_sq {\n                is_duplicate = true;\n                duplicates += 1;\n                break;\n            }",
    ["test_via_validation_rust_differential.py"],
    "via dedup boundary <= -> <")

PRISTINE_TESTS = [
    "test_phase_rotation_rust_differential.py",
    "test_phase_rotation_pbt.py",
    "test_phase_zones_rust_differential.py",
    "test_phase_zones_pbt.py",
    "test_phase_validation_rust_differential.py",
    "test_phase_validation_pbt.py",
    "test_via_validation_rust_differential.py",
    "test_via_validation_pbt.py",
    "test_zone_aware_slot_generation_rust_differential.py",
    "test_zone_aware_slot_generation_pbt.py",
]


def shared_env() -> dict:
    env = dict(os.environ)
    # Derive the shared target dir from the repo's common git dir, exactly
    # like scripts/cargo_shared_env.sh / the Makefile.
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    env["CARGO_TARGET_DIR"] = str(Path(common).parent / "target-shared")
    env.setdefault("UV_NO_SYNC", "1")
    return env


def build(crate_root: Path, env: dict) -> None:
    subprocess.run(
        ["maturin", "develop", "--release", "--manifest-path", str(crate_root / "Cargo.toml")],
        check=True,
        capture_output=True,
        env=env,
    )


def run_pytest(tests: list[str], env: dict) -> subprocess.CompletedProcess:
    paths = [str(TESTS / t) for t in tests]
    return subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q"],
        capture_output=True,
        text=True,
        env={**env, "PYTHONPATH": str(REPO / "packages" / "temper-placer")},
    )


def main() -> int:
    env = shared_env()
    # Verify every `old` source string is present before the campaign starts.
    mismatches = 0
    for i, m in enumerate(MUTANTS, 1):
        src = (m["crate"] / m["file"]).read_text()
        if m["old"] not in src:
            print(f"M{i:02d} ({m['label']}): OLD not found — cannot apply")
            mismatches += 1
    if mismatches:
        return 1

    kills = 0
    errors = []
    for i, m in enumerate(MUTANTS, 1):
        path = m["crate"] / m["file"]
        src = path.read_text()
        path.write_text(src.replace(m["old"], m["new"], 1))
        try:
            build(m["crate"], env)
        except subprocess.CalledProcessError:
            errors.append(f"M{i} ({m['label']}): REBUILD FAILED (infra, not a kill)")
            path.write_text(src)
            continue
        proc = run_pytest(m["tests"], env)
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
    build(TD, env)
    build(DRC, env)
    proc = run_pytest(PRISTINE_TESTS, env)
    if proc.returncode != 0:
        errors.append(f"PRISTINE rebuild suite FAILED: {proc.stdout[-2000:]}")

    print(f"\nkills={kills}/{len(MUTANTS)} errors={len(errors)}")
    for e in errors:
        print("  ", e)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
