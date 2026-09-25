# Zero-time state budget for the current cold deck

This is a static audit of the exact current run at
`numerical-repair/nonstopping-first-invalid/run/`. That run is the 650 ms
native-switch diagnostic; it is not the older 500 ms hard-driver deck. This
audit does not rerun ngspice, change `.save`, relax the timestamp checker, or
turn the diagnostic into an accepted operating point. It asks which energy
coordinates are absent from the current 31-column stream and whether those
missing coordinates prevent bounding the effect of an equal-time callback.

The read inputs and hashes are:

```
db9d544938b792aac009c1ee4fcf27f52a8283beb167e40262d495d4c098ac94  nonstopping-first-invalid/run/cold.cir
2e885755aad4d03fb9c06d7c556faf23ad0ae7922f581d56752db78933b97251  nonstopping-first-invalid/run/ucc28180-pwm-latch.inc
61385002bc7c55313814b7ea606c1198129da20a1f76cd44fe197de0468a70e8  nonstopping-first-invalid/run/protection.inc
94d995d17a85ef932fe511bb2adbee02a1cd3fd1c88604b16d6b6929b31a50eb  nonstopping-first-invalid/run/standby.inc
96cd8d6bfd3870b22403c39437ef2625f0a930f9e06632adcebbc45b61b9dcde  nonstopping-first-invalid/run/clamp.inc
95ae31864ffa55bf33833849ee38c4654bbdb769c9c52976e25a5b4afb73445b  nonstopping-first-invalid/run/authored_logic_hysteretic.inc
19d3bfcfe391bbdd678240297d02e9678802d134f627856601f839b927fa406b  nonstopping-first-invalid/run/event-audit.txt
```

Line references below are to those exact files. `cold.cir:79` saves `time`
plus 30 scalar values. It saves the main inductor current, the two HV node
voltages, the gate/switch voltages, `isense`, the UCC state outputs, and the
native-driver request/delay state. It does not save branch currents through
the protection, controller, diode, switch, or auxiliary-rail paths.

## Coordinates that are saved

`cold.cir:24` saves `i(Lboost)` for the 180 uH inductor and `cold.cir:40,42`
saves `v(vd)`/`v(vb)` for the 19.8 uF local and 2240 uF bank capacitors.
`cold.cir:37-39` saves `v(sw)`/`v(gate)` for the 344 pF `Cds`, 112 pF `Cgd`,
and 12 nF `Cgs` surrogates. `cold.cir:79` also saves `v(isense)`,
`v(xu.blank)`, `v(xdriver.drv_delay)`, and the UCC/PWM states. For constant-C
terms, adjacent rows provide an exact model-energy difference:

```
ΔE_C = 0.5*C*(V_after - V_before)*(V_after + V_before)
ΔE_L = 0.5*L*(I_after - I_before)*(I_after + I_before)
```

An equal-time row can therefore change a saved state while contributing zero
elapsed-time measure to an ordinary integral. That state change remains part of
the event/peak record and can alter later energy. Saved coordinates do not by
themselves qualify the device or behavioral model.

## Unsaved coordinates and conditional bounds

The table uses `VHV = 500 V` only as a declared stress-ceiling premise. The
current cold deck does not enforce that ceiling. `VLOG = 5 V`, `VAUX = 15 V`,
and `VG = 15.2 V` follow from the explicit sources and gate expression in
`cold.cir:63-67` and `ucc28180-pwm-latch.inc:8,71`.

| Unsaved state or path | Netlist anchor | What can be bounded from this deck | Equal-time limitation |
|---|---|---|---|
| `Cvcomp_s` (4.7 uF); `vcomp_s` is hidden while `vcomp`/`Cvcomp_p` are saved | `cold.cir:57-59`, `ucc28180-pwm-latch.inc:23-31` | `Cvcomp_s` is driven only through `Rvcomp=40.2 kΩ` from saved `vcomp`, starts at 0, and has `tau=Rvcomp·Cvcomp_s=188.94 ms`. The retained all-row `event-audit.txt` reports `v(vcomp)` in `[-4.6e-288, 3.2778119089] V`; using a conservative 3.3 V envelope gives `E <= 0.5·4.7 uF·3.3² = 25.6 uJ`. For the exact linear RC recurrence, the 500 ns maximum step is far below `2·tau`, so both recurrence coefficients are positive and a bounded input cannot overshoot; this is a mathematical bound on the deck's RC, not a silicon claim. | `vcomp_s` remains unsaved, so the local ΔE is not measured. Solver residuals/nonlinear source changes can invalidate the ideal maximum-principle premise; retain the 25.6 uJ as conditional until the hidden node is saved or independently checked. |
| `Cvsense` (680 pF); `vsense` is hidden | `cold.cir:53-55`, `standby.inc:8,13-14` | The 1 MΩ/13 kΩ divider alone would give `6.417 V` at `VHV`, but standby `Cigd=50 pF` couples the hidden `inhibit_gate` into `vsense` and the AO3400 channel can pull that node. The pure-divider bound is therefore insufficient. Taking the explicit 15 V auxiliary envelope as a conservative connected-source bound gives `E <= 0.5·680 pF·15² = 76.5 nJ`, conditional on passive bounded coupling and the nominal MOS model. | `vsense` and the MOS/Cigd charge are not saved; 76.5 nJ is an envelope, not a measured ΔE or a hardware guarantee. |
| Protection divider/filter caps `Cdf`,`Cbf` (47 pF each) | `protection.inc:7-14` | The 5,820/992,820 divider ratio gives at most 2.931 V per cap under `VHV`, or `E <= 0.202 nJ` each. | `dh`/`bh` are hidden RC states; matching `v(vd)`/`v(vb)` does not prove matching filter states. |
| Logic/protection timing caps `Cch_*` (4×79.3 nF), `Cfastout` (79.3 nF), `Chealth` (40 nF) | `protection.inc:39-46,78-90` | Their drivers are 0/5 V logic or first-order buffers; passive bounds give 3.97 uJ + 0.991 uJ + 0.500 uJ. | XSPICE buffer state is not saved; these are absolute envelopes, not measured equal-time changes. |
| Other protection/filter/timer caps (`Civ*`,`Ciref*`,`Clsense`,`Casense`,`Cfast`,`Cltimer`,`Catimer`,`Cfault`,`Csmall*`) | `protection.inc:23-30,51,55,68-69,77,87,111-113` | Inputs are bounded by the 0/5 V rails or divider envelopes. For example 8×2 pF at 5 V is 0.20 nJ, both 100 pF timers at their 2 V charge limit are 0.40 nJ, and the 85 pF `Csmall*` total at 15.2 V is 9.8 nJ. | A behavioral source can violate a presumed rail unless its expression supplies the bound; unsaved nodes prevent a local ΔE measurement. |
| Standby MOS parasitic caps (total 1.31 nF) | `standby.inc:10-17` | With the explicit 15 V auxiliary envelope, `E <= 0.5·1.31 nF·15² = 147 nJ`. The include calls these constant capacitances a sensitivity model. | `inhibit_gate`, `permit_gate`, and `vsense` are not all saved; no vendor charge curve is represented. |
| Native driver hidden switch states (`pwm_state`,`inm_state`,`aux_state`) and analog bridge nodes | `authored_logic_hysteretic.inc:5-40` | The native SW elements are algebraic state; their normalized outputs are bounded 0..1 and `Bdriver_req` is bounded by `VDD <= 15 V`. The 18.75 nF `Cdriver_delay` state itself is saved as `v(xdriver.drv_delay)` (`cold.cir:79`). | State ordering at an equal timestamp is observable only through saved outputs; internal switch state and output-branch current are not energy coordinates in the stream. |
| Explicit diode junction capacitors | `cold.cir:17-21,28-29,34-36`; `clamp.inc:8` | Conditional `VHV` bounds give four bridge `100 pF` caps <=50.0 uJ total, two boost `45 pF` caps <=11.25 uJ, body `1 pF` <=0.125 uJ, and clamp `2 pF` at its assumed 250 V `BV` <=62.5 nJ. | Diode terminal voltages/currents are not saved. `TT` charge/recovery (bridge/boost 0, body 8 ns, clamp 50 ns) is not represented by `0.5CV²`; equal-time charge and source work remain unknown without branch-current/charge traces. |
| Ideal source work and resistor/channel loss | `cold.cir:8-25,41-67`; `protection.inc:7-124`; includes above | Some resistor power is reconstructible if both endpoint voltages are saved, but most protection/driver endpoint nodes and all ideal-source currents are absent. Rail values are bounded (0/5/15 V), yet a current bound for every B-source/diode/channel branch is not supplied. | A zero-`dt` interval has zero rectangular integral, but an ideal mixed-signal state update can carry unsaved charge/work. It cannot be called an energy closure from row timestamps alone. |

Parent review of the table: the 15 V envelopes for capacitively coupled
standby nodes have not been proved merely by identifying a 15 V source;
capacitive coupling can drive nodes beyond a supply rail. They remain
conditional estimates, not certified bounds. Likewise `BV=250 V` is a diode
breakdown parameter, not an enforced terminal-voltage ceiling. The clamp's
actual voltage is reconstructible as `-v(isense)`, both boost-diode voltages
as `v(sw)-v(vd)`, and the body-diode voltage as `-v(sw)` because its sense
source is zero volts. Their currents and diffusion-charge states are unsaved.
`CJO` is a junction-model parameter, not generally a constant capacitance;
the table's simple half-C-V-squared numbers require the stated constant-C
approximation or an independently established bound on the nonlinear model.
The two boost models explicitly use `M=0`; the other junctions require care.

The largest listed explicit hidden-capacitor envelope in this trace is the compensation
capacitor at about 25.6 uJ under the saved-`vcomp` RC envelope. The other
listed static-cap bounds total roughly 0.1 mJ under the 500 V premise. These are not a
closed residual: diode recovery charge, ideal-source work, resistor/channel
loss, and any branch without a proven current bound remain unknown.

The clamp topology matters to that bound. The current deck has one explicit
instance, `DCLAMP 0 isense BAV23C_ASSUMED_V2` (`cold.cir:72-74`), with anode at
ground and cathode at `isense`; the model is the single-diode
`BAV23C_ASSUMED_V2` definition (`clamp.inc:1-8`). It therefore forward-clamps
negative `isense` and uses its assumed 250 V reverse-breakdown branch for
positive `isense`. There is no second clamp-diode instance in this deck. The
2 pF/250 V static-energy figure is only an illustrative conditional estimate and
says nothing about unmodelled package/common-cathode coupling or its 50 ns
reverse-recovery work.

## Equal-time error budget

For a hidden capacitor with only `0 <= V <= Vmax`, stored energy is bounded by
`Emax = 0.5*C*Vmax²`. One equal-time transition has unknown absolute energy
change no larger than `Emax`; a group with `m` rows has at most `(m-1)Emax`
of path-variation budget for that term. Across groups, sum this quantity per
term and group. If only endpoint state matters, the net difference is bounded
by `Emax`; if resistor/source work or hidden diode charge along the path
matters, the path-variation bound is safer.

The current native-switch diagnostic itself has 45 equal-time groups, 111
equal-time rows, and 66 repeats in the retained 650 ms `event-audit.txt`
(maximum group size three). The earlier hysteretic extension had two groups
(five rows, three repeats), and the native COMPHYS trace had one three-row
group (three rows, two repeats). These counts are evidence, not a released
row-count limit. Applying the formula to bounded static capacitors is possible
once the conditional voltage premises are accepted. Applying it to diode `TT`
storage, ideal behavioral sources, or unsaved branch currents is not justified
by row counts alone; those terms need current/charge instrumentation or a
stronger source/model bound.

For saved capacitor/inductor coordinates, use the exact adjacent-row formula
and report a same-time state change separately from the positive-`dt` integral.
For an unsaved bounded state, report its envelope and the resulting
`(m-1)Emax` diagnostic budget; do not fold it into a residual and call the
balance closed. A finite envelope answers how large a hidden state could be,
not what its numerical error was at this callback.

## Boundary and conclusion

The 500 V ceiling, behavioral rail limits, and 1 mA `Bvamp` source envelope
are assumptions to validate; BAV23C `BV` supplies no hard voltage limit.
This 650 ms cold trace reaches its endpoint but is rejected by the unchanged
timestamp rule, so none of these bounds qualifies
normal operation. Unsaved coordinates do not make all equal-time numerical
error unquantifiable: many passive states have finite analytical envelopes,
and saved states have exact row-to-row formulas. They do prevent an exact
local error or closed energy balance until compensation/filter voltages,
diode charge/currents, ideal-source work, and channel/resistor paths are
instrumented or independently bounded. Raw rows and the strict checker remain
unchanged.
