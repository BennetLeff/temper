---
date: "2026-07-09"
topic: external-mfem-fem-corroboration
status: requirements
tier: deep-feature
relationship: "Climbs the validity ladder for the physics-informed placement/routing thermal verification chain (#145). External-FEM corroboration is the next independent model above the solver-verified 2-D FDM — a genuinely different solver family (finite-element, 2-D/3-D, unstructured mesh) from a different codebase (LLNL, peer-reviewed, HPC-validated), adding physics (higher-order elements, mixed BCs, convection) the 2-D in-plane FDM lacks."
---

# External MFEM-FEM Corroboration for the Thermal Verification Chain

## Summary

Add **MFEM** (LLNL, `brew install mfem` — serial version has zero external dependencies, builds in <1 min) — a lightweight open-source C++ finite-element library with built-in Poisson/heat-equation examples, VTK output, and support for arbitrary-order elements on 2D/3D unstructured meshes — as a second genuinely-independent model to corroborate the in-house 2-D FDM's temperature distribution across the whole temper board. Two different solver families (FDM vs FEM), two different mesh types (structured 2-D grid vs unstructured 2-D/3-D mesh), and a genuinely different codebase (LLNL, peer-reviewed). Agreement across the full thermal field strengthens the validity rung from "single-model, solver-verified" to "multi-model-corroborated" — the strongest non-hardware evidence that the thermal model reflects physical reality.

---

## Problem Frame

The 2-D FDM is now correctness-proven (MMS, 2nd-order) and soundness-proven (verified-interval bounds), and the U11 lumped R_θ cross-check corroborates device T_j via a 0-D resistor network. It is still one model family. A genuinely independent finite-element solver — different mesh, different element type, different codebase — provides a new axis of evidence. MFEM's serial build has zero external dependencies, installs in <1 min, and ships a Poisson example (steady-state heat conduction — exactly our PDE) with VTK output. If MFEM's unstructured mesh produces a temperature field consistent with the FDM's structured grid across the whole board, the thermal model is corroborated by an independent method.

---

## Requirements

**Integration**
- R1. An MFEM steady-state thermal simulation runs from a Python orchestrator using a compiled serial example binary (e.g., `make ex1 -j`, called as subprocess with a mesh + config file) or PyMFEM Python bindings — no manual steps in the verify path.
- R2. The temper board geometry (board outline, copper planes, device footprints, keepouts, stackup, through-plane sink regions) is converted to an MFEM-compatible mesh and configuration. MFEM supports Gmsh, VTK, and native `.mesh` formats. A semi-automated translation from the existing board model is acceptable.

**Comparison**
- R3. The MFEM and FDM temperature fields are compared across the full board domain — not just at device peaks. The comparison metric is the per-cell temperature delta mapped to the common (coarser) of the two grids, enabling a spatial ΔT map.
- R4. Device junction temperatures (Q1-Q2 IGBTs, D1-D2 rectifiers) serve as key spot-checks within the full-field comparison.
- R5. The comparison is **same-objective**: both models solve steady-state conduction on the same geometry with the same power dissipation and the same ambient conditions, differing only in solver, mesh, dimensionality, and element type (the independence axes).

**Validity claim**
- R6. The corroboration scope is explicitly scoped: agreement across the field is evidence, not proof. The power-on hardware measurement remains the only closing instrument for physical correspondence.

**Gate discipline**
- R7. The corroboration is fail-closed: if MFEM cannot run (missing binary, failed mesh, solver error), the comparison result is `UNMEASURED` — never a silent pass. Disagreement carries a spatial attribution map.

---

## Success Criteria

- MFEM produces a steady-state thermal field across the temper board mesh, and a per-cell ΔT map vs the FDM field is generated.
- Device T_j from MFEM agrees with the FDM within the U11 tau tolerance at the worst-case operating point.
- The full-field comparison identifies where the models diverge (edge convection, through-plane gradients, far-field copper spreading).
- The corroboration is fail-closed and CI-wired as an `l3_pbt`-cadence gate.

---

## Scope Boundaries

- Semi-automated mesh generation from the existing board model — not a full KiCad→mesh pipeline.
- MFEM is a separate, infrequently-invoked corroboration instrument — not a replacement for the in-loop FDM.
- No GUI, no web interface.
- The power-on hardware measurement remains the deferred closing instrument.
- **Elmer is a deferred alternative** — the Elmer pipeline scaffold proved the pipeline shape (preflight → mesh → solve → project → compare → gate). MFEM was chosen as the primary backend for its zero-dependency serial build, `brew install` simplicity, and clean VTK output.

---

## Key Decisions

- MFEM over Elmer: zero-external-dependency serial build (`make serial -j`), `brew install mfem` in ~30s (vs Elmer's complex build chain), BSD license, LLNL-developed and peer-reviewed, Poisson example maps directly to steady-state thermal.
- Full-field comparison over device-only T_j (as before).
- Same-objective discipline (R5).
- Fail-closed gate (R7).

---

## Dependencies / Assumptions

- MFEM is installable via `brew install mfem` (macOS) or `make serial -j` from source (Linux). The serial build has zero external dependencies.
- The compiled serial example binary (or pymfem) is callable as a subprocess from Python with a mesh file + parameter file.
- Mesh generation can use Gmsh / MFEM's native `.mesh` format; a representative temper board mesh is sufficient.

---

## Outstanding Questions

- [Affects R2] How far to automate the mesh pipeline vs a one-time manual mesh for the temper board? Record as a planning decision.
- [Affects R3] What is the pre-registered agreement tolerance for CLEAN? Tie to the U11 tau precedent.
