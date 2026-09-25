# Normal hysteretic slew candidate (prepared, unlaunched)

This directory is a source-only candidate for a bounded follow-up to the
`normal-hysteretic-settling-extension` run.  It is **PREPARED_UNLAUNCHED**:
there is no trace, simulation log, acceptance result, or hardware qualification
claim here.  The parent task must review the source and decide whether to launch
it.

The copied `cold.cir` retains `TSTOP=650m`, the full passive-reva power stage,
controller, protection, and solver settings from the settling extension.  Four of the five included source files, `cold.cir`, and `progress.rs` are
byte-identical copies of that source.  The only modeled change is the driver include:

* Source candidate:
  [`numerical-repair/driver-hysteresis-slew-candidate/authored_logic_hysteretic_slew.inc`](../numerical-repair/driver-hysteresis-slew-candidate/authored_logic_hysteretic_slew.inc)
* Staged include:
  [`authored_logic_hysteretic.inc`](authored_logic_hysteretic.inc)
* Exact substitutions in the staged copy: one
  `.subckt AUTH_UCC27511A_HS` → `.subckt AUTH_UCC27511A_H` and one
  `.ends AUTH_UCC27511A_HS` → `.ends AUTH_UCC27511A_H`.  Internal
  `SW_*_HS` model names are unchanged.  This preserves the existing
  `protection.inc` instance line `Xdriver ... AUTH_UCC27511A_H`.

The candidate keeps the native PWM/INM/AUX hysteresis and adds finite poles to
the normalized state signals.  Its 1 ohm/5 nF poles are a declared sensitivity
approximation inspired by the TI macro's internal `COMPHYS_BASIC_GEN` node;
they do not claim to reproduce the vendor's separate output-current topology.
The unchanged TI model remains the oracle for any later comparison.

`inputs.json` records every copied-source hash, the candidate-source hash, the
staged hash, and both exact name substitutions.  No source outside this new
directory was modified and no simulation was launched while preparing it.

Parent disposition: **UNLAUNCHED / NOT ADOPTED**. The additional pole moves
benchmark gate edges about5ns farther from the TI model. TI's5ns RC belongs
to internal hysteresis feedback, not its exported output path. The original
source bytes used for staging are retained in `candidate-source-at-staging.txt`
so subsequent explanatory-comment edits do not break this provenance.
