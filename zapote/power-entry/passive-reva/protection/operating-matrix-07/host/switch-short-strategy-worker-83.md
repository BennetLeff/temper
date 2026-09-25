# SW-SHORT protection-strategy review

The frozen SW-SHORT deck proves a topology boundary. `SWF2` is the closed
VD-to-VB path (`vd -> f2_path -> vb`), so opening F2 can isolate the 2240 µF
bank from VD. The failed-switch surrogate is a separate gate-independent
`Sswfail sw -> channel_source` branch. It is fed by the bridge/source through
the 180 µH boost path and therefore bypasses F2; F2 opening alone cannot stop
that mains-fed failed-MOS path. The 19.8 µF local VD capacitor also remains on
the diode side of F2.

The saved tail is only partial model evidence. Its rows show `q=en=5`,
`arm=permit=5`, `f2ctl=5`, and gate samples near 0.18 V while PWM is low;
those are ordinary PWM/operating samples, not an external-latch shutdown.
One row reports about 182 A in the fixed 180 µH model, but that is not a
physical current claim: the run stopped at 0.6544026486296868 s before the
0.662 s endpoint with an unresolved timestep-too-small condition. The
inductor authority says the model has no DC-bias, saturation, or thermal law;
43 A is typical saturation and 24.5 A is a 40 K-rise rating, so the sample is
not a selected-part survival result.

A future current-interruption strategy must therefore (1) detect and latch a
failed-MOS/failed-channel condition independently of PWM low samples, (2)
interrupt the source-fed failed branch, and (3) isolate and safely discharge
the charged VD/VB bank path. It must specify default-off behavior, fault
energy/current withstand, DC interruption and no-restrike behavior, and
measure VD, VB, both F2 terminals/current, source/failed-branch current, and
q/en/gate transitions. Those are future tests and hardware requirements; no
such strategy or part has been selected here. The numerical-abort tail does
not establish interruption, hardware protection, or a causal mechanism.

