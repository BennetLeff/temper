# Operating-envelope plan review

Verdict: **ACCEPT**. No must-fix found in the reviewed plan.

Evidence checked:

- The plan carries the settled product baseline (120 VAC nominal, 108–132 VAC,
  15 Arms, 40 °C inlet) and separately marks full bus range, continuous/burst
  output, hot inductance, maximum fault current, and worst-case shutdown time as
  unresolved (`docs/plans/2026-09-19-power-stage-operating-envelope-plan.md:43-48`).
- Low-line power is treated as an A2-derived, voltage-dependent curve with
  explicit PF/efficiency/thermal inputs; A6 separately binds inlet temperature
  to assembly/component temperatures and refuses unjustified duration claims
  (`:36-40`, `:85-89`). This avoids turning the 1,800 W AC-input class into a
  low-line delivered-power requirement.
- The plan explicitly prevents promotion of the 500 V provisional VD screen to
  a bulk limit and prevents promotion of the 51 A simulation point to a current
  guarantee (`:37`, `:50-55`). Simulation completion and physical qualification
  are separate gates (`:115-118`, `:140-143`); no B/C implementation or
  qualification is claimed.
- Scope identity is explicit: the retained 54-part power stage and standalone
  79-part protection experiment are mapped separately, with 79 not treated as
  an integrated-board count (`:122-125`).
- Dependencies and stop conditions are coherent: A7 freezes inputs before B's
  broad matrix, B remains conditional while A4 is unresolved, and C follows
  controller/fault conclusions (`:145-158`).

The opening phrase “verified F2 shutdown experiment” is bounded by the same
section's explicit simulation-only/qualification-not-run language and does not
create a qualified hardware claim.
