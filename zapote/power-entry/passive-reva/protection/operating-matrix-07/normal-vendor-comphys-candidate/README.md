# Normal vendor-COMPHYS candidate (prepared, unlaunched)

This directory is a source-only candidate for a bounded passive-reva normal run.
It is **PREPARED_UNLAUNCHED**: no simulation, trace, acceptance result, or
hardware qualification claim is present.  The parent task must review the model
fidelity before launching it.

`cold.cir` is an exact copy of the 650 ms
`normal-hysteretic-settling-extension` source.  `protection.inc`, `standby.inc`,
`clamp.inc`, `ucc28180-pwm-latch.inc`, and `progress.rs` are also byte-identical
copies; their hashes are recorded in [`inputs.json`](inputs.json).  The only
replacement is the authored driver include:

* Source candidate:
  [`numerical-repair/driver-vendor-comphys-candidate/authored_logic_vendor_comphys.inc`](../numerical-repair/driver-vendor-comphys-candidate/authored_logic_vendor_comphys.inc)
* Staged include:
  [`authored_logic_hysteretic.inc`](authored_logic_hysteretic.inc)
* Exact substitutions in the staged copy: one
  `.subckt AUTH_UCC27511A_HV` → `.subckt AUTH_UCC27511A_H` and one
  `.ends AUTH_UCC27511A_HV` → `.ends AUTH_UCC27511A_H`.  The
  `COMPHYS_BASIC_GEN` primitive body and its internal `R1`, `C1`, `EIN`, `EHYS`,
  `EOUT`, and `RINP1` lines are unchanged byte-for-byte.  The existing
  `protection.inc` instance `Xdriver ... AUTH_UCC27511A_H` therefore resolves
  without changing the full-plant source.

The COMPHYS front-end uses the source candidate's nominal PWM/INM threshold and
hysteresis values (2.2/1.0 V) and AUX values (4.2/0.3 V), plus the TI macro's
nominal input loading.  Its product logic and 18.75 nF/1 ohm output surrogate
remain authored approximations.  In particular, the TI primitive's 5 nF node is
not evidence that the complete UCC27511A output-current topology has been
reproduced; the unchanged TI model remains the comparison oracle.

No file outside this new candidate directory was modified while staging it.  No
simulation was launched.
