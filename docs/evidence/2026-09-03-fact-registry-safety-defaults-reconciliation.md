<!-- provenance: commit=WORKTREE dirty=true -->
# Fact-registry safety and via-default reconciliation

On 2026-09-03 the three remaining production divergences reported by
`check_fact_registry_drift.py` were reconciled against the established
authorities. The PCB is a US 120 V RMS design (REQ-SYS-01 and the schematic's
100–130 V assertion), its as-built forced-air construction is PD3, and the
JLCPCB 2 oz annular-ring floor requires the board-wide fallback via pad to be
0.9 mm (the existing 0.3 mm drill is unchanged).

Changed together:

* `pcb_spec.yaml`: safety values 230 V / PD2 → 120 V / PD3.
* `design_rules.py` and its Rust-backed field oracle: ACMains metadata 240 V
  → 120 V.
* `temper-design-bundle` Rust `DesignRules()` default via diameter 0.6 mm →
  0.9 mm, with the pinned oracle updated in the same deliberate act.

The YAML value is consumed by `pipeline/derivation.py`; the live and pinned
physics-oracle paths were swept with explicit and config-loaded safety specs.
The design-rules oracle comparison was swept field-for-field: the only
intentional scalar changes are ACMains `voltage_v` and the bare-constructor
via diameter. No PCB file was changed and no oracle was repinned for an
unrelated behavior.

The remaining red fact-registry entries are separate, explicitly documented
tool-error or unresolved-domain findings and are not hidden by this change.
