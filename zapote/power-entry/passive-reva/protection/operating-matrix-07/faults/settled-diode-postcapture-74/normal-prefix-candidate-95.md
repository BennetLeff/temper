# DIODE-SHORT normal-prefix candidate

This candidate records the complete-capture normal-prefix analysis while the DIODE-SHORT case remains `PARENT_REVIEW_PENDING` and `accepted=false`. The raw capture is complete to `0.662 s` with 32,309,024 rows, 5,340,687,952 bytes, and SHA-256 `19f8068d73fb4b2379b3111504fd92efbf769984eb4e3775d5b6378294a6c02c` (receipt: `full-DIODE-SHORT/preflight.json`).

The normal-prefix selector cut off at `0.65 s`, retaining 30,113,471 rows through `0.6499999878048587 s`, a `1.2195141341209137e-8 s` gap against the 1 us bound. The measured fault-control rising edge is later at `0.6541666661706754 s`; the timing-window review is still a failure/pending item and is not waived here.

The last-three-cycle normal metrics (`full-DIODE-SHORT/normal-metrics.txt`) are: RMS input 7.316235 A, input power 867.951112 W, load power 773.412291 W, PF 0.988613, bus mean 383.367154 V with 381.316730–385.364541 V extrema, and drift 0.002658 (range divided by absolute first cycle mean). Report-only inductor peak is 30.639630 A; VD peak 385.475199 V, VDS peak 386.774078 V, and VGS peak 14.982192 V. Armed/on fractions are both 1.0 and the screen count is zero.

The bounded repeated-time audit (`normal15-audit.txt`) retained every selected row: 41 equal-time groups, 54 repeated intervals, maximum group size 3, no missing right neighbor, backward step, logic change, or boundary group. E3 spread is `1.7415469999695023e-13 J`; E3 sum-absolute is `2.3522398841417582e-12 J`.

Source and raw identities are bound in `normal-prefix-candidate-95.json`; tool pins are `full-DIODE-SHORT/tools-parent.sha256`. Pending proof is the phase/observation review, the legacy terminal witness, and parent electrical review. A zero normal-prefix screen count cannot make this DIODE-SHORT fault case pass, especially while the timing-window failure remains unresolved.
