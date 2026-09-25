# Integration-06 controller review (read-only)

Reviewed `controller/ucc28180.inc`, `controller/integrated.cir`, `controller/protection.inc`, `controller/checks.rs`, the generated traces, and TI UCC28180 Rev-D text (`/private/tmp/ucc28180-host.txt`). Existing Rust checks and independent M1/M2 worked-example checks were run; these findings are additional.

## Findings

### P1 — ICOMP protection is omitted and the functional gate check cannot detect it

TI §8.3.7 says PWM is halted when ICOMP falls below 0.2 V (ICOMP external-overload protection); §8.3.8 includes ICOMPP in fault protection. `ucc28180.inc:16-17` defines `fault` only from UVLO, VSENSE OLP/standby, and ISENSE open-pin; `Biamp`/`Bgate` at lines 30/44 never test `V(icomp)<0.2`. A shorted ICOMP therefore still permits PWM (the ICOMP current source merely drives it toward 3 V). The supplied fixture hard-forces `Vic icomp 0 1` (`functional.cir`) and has no ICOMP-low/short case, so all current functional checks can pass while this required shutdown is absent. Add an explicit ICOMP<0.2 fault path and a low-ICOMP negative-control trace before treating controller protection as complete.

### P1 — EDR source current is clipped to 40 uA, defeating the TI EDR behavior

At `ucc28180.inc:24`, the post-soft-start low-VSENSE EDR branch requests `280u` (matching TI's approximately 275-uA EDR source at VSENSE below 4.75 V), but the common `clip(...,-275u,40u)` limits positive current to 40 uA. With the current-source orientation (`Bvamp gnd vcomp I=...`), positive current is current into VCOMP, i.e. the EDR source direction. High-VSENSE sinking is allowed to -275 uA, but low-VSENSE recovery is reduced by about 7x. This is a concrete sign/limit error, not an unknown vendor dynamic. The upper clip must permit the EDR source (about +275/280 uA) while retaining the normal/soft-start +40-uA limit outside EDR, or use separate branch limits.

### P1 — Fault VCOMP discharge uses an unsupported 40-ohm shunt and changes restart dynamics

`Bvamp` line 24 uses `-V(vcomp)/40` for every `fault`. At VCOMP=3 V this is 75 mA into the fault sink and gives an 8.8-us time constant on the 220-nF local capacitor. TI's 0.37-mA-at-2-V datum (§7.5, rapid discharge with VCC floating) is a different unpowered path, while the powered OLP condition is characterized at 0.04 V with 0.5 mA and OVP uses a documented 4-kOhm path (§8.3.4). Thus 40 ohm is an unsupported all-fault assumption and can materially alter fault/restart behavior; it should be tied to the intended powered/unpowered condition and not reused as a general timing claim. (The OVP/SOC `-V/4k` branch is separate and is not this finding.)

### P1 — ISENSE negative absolute clamp is absent in the coupled model and reversed in the retained source

The actual bridge/shunt polarity is correct (`Dbr1..Dbr4`, `Rshunt bridge_minus 0`, `Risense bridge_minus isense 220` in `integrated.cir:10-19`): controller ground is the MOS source side and bridge-minus becomes negative under inductor return current. However TI §8.3.14 explicitly requires a diode clamp so ISENSE stays between 0 and -1.1 V during inrush. No clamp exists in the coupled netlist or protection include. The retained source's `PfcIsenseClamp` is also oriented the wrong way for this polarity: `PfcIsenseClamp` defines A=pin2/K=pin1 and the source connects A to `shunt.p2` (bridge-minus), K to `control_gnd` (`source/power_entry_passive_reva.ato:124-128,430-431`), so it clamps positive shunt excursions and is reverse-biased on the required negative excursion. Reversing a Schottky without checking Vf would also conflict with TI's requirement that Vf exceed the maximum PCL threshold (-0.438 V) yet remain below 1.1 V. The recorded coupled trace reaches -0.3555 V at ~35.7 A (not yet violating -1.1 V), but this is an idealized nominal run; no fault/startup transient demonstrates the pin limit. The PCL check at -0.4 V does not substitute for the absolute pin clamp.

### P2 — The “SOC 4-kΩ discharge” check measures ideal-source current, not VCOMP discharge

`functional.cir` forces `vcomp` with `Vvc vcomp 0 3` and `icomp` with `Vic icomp 0 1`. `checks.rs:76-80` only checks `i(Vvc) == -0.75 mA` while ISENSE is below SOC. Because VCOMP is an ideal voltage source, this proves only that the behavioral branch draws current from the source; it cannot prove that a real compensation network discharges, nor its time constant/recovery. Add a capacitor-backed VCOMP fixture (or an explicit current/voltage transient assertion) before using this as SOC dynamic evidence.

### P2 — Required controller equations are not asserted by `checks.rs`

The source implements TI M1/M2 piecewise equations at lines 26-27, and independent external checks reportedly cover the worked point. However the integration checker never reads `v(xu.m1)`/`v(xu.m2)` (although integrated TSV exports columns 19-20), and the functional fixture does not export them. A future edit can break eq.81–88 while `checks.rs` continues to print all PASS. Keep the independent oracle, but add boundary/interior assertions (0.5/1/2/4.5/4.6 VCOMP and RFREQ scaling) to the acceptance checker or mark this as separate-only evidence.

### P2 — `GATE_TAU` is dead and the coupled driver has no explicit gate-current limit

`integrated.cir:4` declares `GATE_TAU=120n` but no element uses it. The actual included path uses `EN_TAU=18.75n`, a 1-ohm `Rdriver`, and 12-nF gate capacitance (`protection.inc`), with behavioral voltage sources. Thus changing the advertised gate time constant has no effect, and no UCC27511 source/sink current limit is represented in the coupled witness. This is acceptable only if the witness is explicitly nominal/static; it must not be used to infer real gate-current or turn-off-delay behavior.

## Overall disposition

The M1/M2 numerical equations and the observed bridge/shunt sign are structurally plausible, and the existing nominal traces/checks pass. The ICOMP shutdown omission, EDR +40-uA clipping, unsupported fault discharge impedance, and absent ISENSE absolute clamp are concrete controller/protection gaps. With these unresolved, the controller integration should not receive a complete B2/PASS claim; retain the warm/prequalified nominal witness as conditional evidence only.
