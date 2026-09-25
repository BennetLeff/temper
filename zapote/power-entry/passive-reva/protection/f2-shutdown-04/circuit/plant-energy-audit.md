# F2 plant energy audit

Scope: read-only review of `f2-shutdown-04/plant` while the extractor is being updated.  The exact STW/C3D vendor SPICE archives are unavailable; the declared level-1 NMOS and diode surrogates are acceptable as bounded experiments when their limits remain explicit.

The source-channel probe is structurally useful.  `Msw` has a zero-volt `Vg_sense` in series with its source, so `i(vg_sense)` measures controlled MOS-channel current.  It does not measure commutation/body-diode current; positive channel current is the right metric for cessation, with reverse terminal settling reported separately.

The initial model had two physical-path hazards that the worker is correcting: a level-1 MOS bulk diode duplicated by an explicit `DBODY`, and `Coss(eq)=456 pF` added in parallel with `Cgd=112 pF`.  The current worker snapshot suppresses the intrinsic diode (`IS=1e-40`), adds a dedicated `Vbody_sense`, and uses Cds=344 pF plus Cgd=112 pF.  Keep those changes.  The explicit Cgs remains `Qg/10 V` (12 nF nominal) while Cgd is also present; this is a conservative gate-charge/timing overload, not an exact capacitance extraction.  Do not use it as a physical gate-energy claim unless that convention is stated.

The energy table must state its boundary.  `-V(line)*i(vline)` is a consistent line-source work sign.  The high-voltage fault-window balance beginning at `T_OPEN` can use local 19.8-uF headroom; the 2240-uF bank is isolated by F2 and must not be used as post-open absorbing energy.  A full simulation interval is not closed yet unless it includes the following terms:

* `Vlogic5` and `Vaux15` source work (logic bleed, aux pull-up/BSS current, and gate-driver output supply are otherwise omitted).
* Conductive F2 `Ron=15 mΩ` loss before opening.  Its current is not presently saved.  At 40–50 A this can be millijoule-scale over the pre-open interval.  Either save a fuse current and integrate `I²R`, or exclude pre-open time and call the result a fault-window balance.
* The explicit body-diode branch (`i(vbody_sense)`) after adding its trace/parser, and Dboost junction-capacitor stored energy.  Until those are included, retain residual as an honest closure diagnostic; do not describe it as “all explicitly represented dissipation.”
* The resistor denominator should be the actual divider chain, 992.82 kΩ (987 kΩ plus the 200 Ω step and 5.62 kΩ bottom), rather than 987 kΩ.  The difference is only about 0.6%, but the source already records the exact value in `DIV_GAIN`.

The extraction should keep separate columns for positive channel cessation, body/terminal reverse excursion, and diode energy.  A late negative pulse must not be folded into “shutdown latency,” and channel current must not be treated as total branch current in conservation.  For published evidence, report the strict post-open fault-window residual and its denominator, then list omitted control-rail and pre-open terms; this gives a bounded, reviewable result without claiming a vendor-qualified transient model.
