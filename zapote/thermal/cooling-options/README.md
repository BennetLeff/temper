# Bridge cooling assembly options

This directory is a candidate comparison for the bridge redesign batch.  It
does not modify the retained v1 contract, PCB, Rust solver or maintained unit
registry.  Every fit and qualification claim remains conditional.

* [`loss-budget.md`](loss-budget.md) — exact GBU2510A evidence, loss equation,
  resistance budgets and concurrent-load airflow arithmetic.
* [`comparison.md`](comparison.md) — baseline, compact and shared-airflow
  concepts with ranked disposition.
* [`protection.md`](protection.md) — candidate thermal/tach supervision
  contract; no protection is implemented here.
* [`recommendation.md`](recommendation.md) — handoff requirements and open
  qualification work.
* [`envelope.json`](envelope.json) — machine-readable common assumptions and
  uncertainty envelope.
* [`proposals/`](proposals/) — source-bound machine-readable concept records.
* [`drawings/assembly-comparison.svg`](drawings/assembly-comparison.svg) —
  dimensioned concept allowances, bannered as provisional.
* [`sources/README.md`](sources/README.md) — retained datasheets, hashes and
  dated DigiKey snapshots.

The recommended next model is `shared-392-120ab-sanyo-120cfm-system-airflow`;
the retained `baseline-395-1ab-two-fan` is the control.  The earlier
`shared-392-120ab-system-airflow` record is retained as a superseded comparison
because its two 41 CFM free-air fans cannot reach 100 CFM before duct losses.
The low-profile
`compact-396-1ab-single-fan` is screened out of the leading rank under the
retained legacy `RθJC=1.25 °C/W` screen because its published resistance gives a
142.8 °C junction.  That is a conditional comparison, not a validated
whole-bridge aggregate resistance.  Enclosure fit is explicitly
**INDETERMINATE** until enclosure CAD and service clearances are supplied.
