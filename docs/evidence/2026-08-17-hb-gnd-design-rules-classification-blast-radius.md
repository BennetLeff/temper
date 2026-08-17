<!-- provenance: commit=8157b4344881ccd607ebaad5ba73c80ea85e97a8 dirty=false
     board sha256 (verify unchanged before and after this investigation):
     6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1 -->

# `hb-gnd` classification divergence: `elec/domain_manifest.yaml` (HV) vs `TEMPER_NET_ASSIGNMENTS` (GND/LV)

**STUB — investigation in progress.**

## Task

`hb-gnd` is classified HV by `elec/domain_manifest.yaml` (PR #1145) and by
`_classify_net_class()` (both Python and Rust backends, per PR #1300), but
`core/design_rules.py`'s `TEMPER_NET_ASSIGNMENTS` table classifies it
GND/LV. This doc will:

1. Derive `hb-gnd`'s actual electrical potential from `elec/src/*.ato`
   schematic source (not trusting the manifest's trace uncritically).
2. Trace what each classification table is actually consumed by (call
   sites, CI wiring) to determine whether the divergence reaches real
   clearance/creepage geometry or only a placer-feasibility model.
3. Determine which table is authoritative for `hb-gnd`, or whether they
   serve genuinely separate purposes.
4. Assess blast radius of correcting `TEMPER_NET_ASSIGNMENTS`, and whether
   it falls inside handoff §9.6's reserved PWR_RTN/CGND decision.
5. Apply a fix only if blast radius is contained and direction is stricter.
6. Register the invariant in `scripts/check_fact_registry_drift.py`.

Will be filled in as the investigation proceeds. See
`docs/evidence/2026-08-17-hb-gnd-classification-stale-test.md` (PR #1300)
and PR #1322's evidence doc (`fix/netclass-classifier-and-creepage-gate`
branch, §1a) for prior related findings.
