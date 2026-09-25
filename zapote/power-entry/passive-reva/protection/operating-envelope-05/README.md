# Operating-envelope planning result

The user requested detailed substeps and Luna delegation. Three Luna agents
completed product-requirement, exact-component and simulation-coverage audits;
the host reconciled them and mapped integration/consolidation work. A final
Luna review accepted the plan with no must-fix findings.

The plan is
`docs/plans/2026-09-19-power-stage-operating-envelope-plan.md`.
The current evidence contract is `envelope-contract.md`; supporting source
citations and proposed checks are under `research/`.

## What is established

- Retain120VAC nominal,108–132VAC,15Arms and40°C cooling-inlet requirements.
- Retain the current single~389.6V PFC bus and180µH selected inductor as source
  configuration; their full operating envelopes remain to be derived.
- 1.8kW is an AC-input class. Delivered continuous/burst output and low-line
  foldback must be established from losses, power factor and temperature.
- Keep all04 results as conditional observations. Neither51A opening current
  nor the500V local-node screen becomes a hardware operating limit.

## What the audit changed in the next-work order

1. Couple the actual ~130kHz PFC controller's regulation/current-limit/stop/retry
   behavior to the shutdown circuit.04 used synthetic100kHz PWM and fixed rails.
2. Derive separate VD/VB/VDS/VGS limits and the admissible current/energy region.
   A450V-rated bulk bank does not inherit the500V VD experiment screen.
3. Close real5V/15V producers and auxiliary overvoltage handling. The older
   IRM proposal's OVP envelope can exceed the selected driver's limits.
4. Count and simplify the combined implementation only after these functions
   are understood.79 protection parts and54 power-stage parts are different
   scopes; no reduced whole-board count is established yet.

A1's identity/requirements research is complete. A2–A7 contain the remaining
engineering derivations. StagesB (integrated simulation) andC (schematic
consolidation) are detailed plans, not work claimed to have run in this pass.
No source, PCB, firmware or frozen model changed. No simulations were rerun;
this was a research and planning task. The receipt verifies frozen04 hashes
and records the new research/plan identities.
