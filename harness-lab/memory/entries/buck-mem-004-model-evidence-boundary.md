# buck-mem-004 — A plausible simulation is evidence only inside its declared model boundary

- **Claim / procedure:** Before using simulation output for a design
  decision, write down (1) what is sourced vs assumed, (2) what the
  circuit physically exercises, (3) what the retained receipt actually
  identifies (model snapshot, deck, simulator, logs, waveform identity),
  and (4) where the claim stops. Nominal regulation or timestep
  convergence supports model development only — not transient accuracy,
  efficiency, stability, thermal/fault behavior, or hardware performance
  without independent evidence. A cross-check that influenced model
  changes is a development cross-check, not a blind holdout.
- **Applicability:**
  portable general claim-scoping guidance, board- and simulator-
  independent. Required capabilities: simulation-evidence scoping,
  assumption-ledger reading. The LMR51430 values (0.600 V reference,
  3.314861 V nominal, 4.759 V rejected artifact, 10 Meg → 1 Tohm fix)
  are buck-model context, not MCU facts (R3).
- **Evidence:**
  `docs/solutions/best-practices/behavioral-model-evidence-boundary.md`
  (`sha256:a7c95cd4…c84d74c33c37`) — full evidence ladder, rejected-model
  retention (`measured-v2` vs `measured-v3`), and the fail-closed runner
  boundary. Source audit:
  `harness-lab/audits/buck-20260909/model-simulation.md`.
- **Provenance class:** expert-curated (manual curation 2026-09-10; not
  automatic learning — the full-buck pilot has not run).
- **Validation state:** source-reviewed. No live full-buck inheritance
  result claimed.
