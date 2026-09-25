# B1/B2 controller-coupled integration fixture (conditional)

This directory is a bounded B1/B2 implementation fixture for source revision
`5dde29ab3e2f1223c2d33c129ced2cf647238307`.  It is intentionally separate
from the immutable `f2-shutdown-04` evidence and from the canonical package
checkout.  `run_cases.sh` runs three controller functional fixtures and one
reduced-order integrated plant witness; `checks.rs` emits Rust verdicts from
the ngspice measurement logs.

The official TI model retrieval was attempted three times.  TI's product page
identifies `SLUM528.ZIP` (TINA transient) and `SLUM423.ZIP` (PSpice average);
the browser transport exposes only `application/zip`, and the host's direct
curl path has no DNS.  The host later obtained both archives, but each begins
with TI's encrypted-library marker and cannot be loaded by ngspice.  The exact
attempts and links are retained in `model-retrieval.log`.

`ucc28180_behavioral.inc` is therefore a clearly conditional behavioral
model, not a manufacturer transient model.  It binds the main datasheet
functional values: 5-V VSENSE reference; 11.5/9.5-V VCC UVLO; 0.82-V
standby/open-loop threshold; 5.35-V OVP low discharge, 5.45-V OVP high stop,
and 5.10-V reset; -0.285-V SOC; -0.400-V cycle PCL; 300-ns leading-edge PCL
blanking; and the datasheet M1/M2 current-loop gain pieces.  The oscillator
is 130 kHz for the selected 16.2-kOhm design point, and each gate pulse's duty
is calculated from live VSENSE/VCOMP/ISENSE.  It is not a fixed PWM source
hidden behind an enable.  The remaining current-loop transconductance,
internal PWM ramp, exact soft-start trajectory, line-cycle shaping, and
stability are unknown until a usable TI model or measured data is available.

`integrated_closed_loop.cir` includes a rectified 120-VAC/60-Hz bridge with
1.2-ohm source impedance, 180-uH boost inductor, finite diode/switch
surrogates, 22-uF local reservoir with the required 19.8-uF minimum parameter,
F2 between VD and VB, 2240-uF bulk bank, 220-ohm load, and the actual HOT0
return shunt orientation: rectifier-minus -> 10 mOhm -> HOT0.  VB is sensed by
the 5x200-kOhm/13-kOhm divider and 680-pF filter; ISENSE is taken through the
220-ohm/1-nF network from the shunt's rectifier side.  The conditional
VD/VB protection latch is explicit and drives the model's run permission.
Initial bank/local capacitor values are used with `UIC`; startup and 100-ms
VCOMP charging are not claimed by the 0.8-ms reduced-order plant witness.

Run:

```sh
./run_cases.sh
```

The standalone controller checks are the independent evidence: normal gate
activity, OVP high stop and reset, VSENSE standby/VCOMP discharge, explicit
run stop/retry, and cycle-by-cycle PCL.  `controller_*_negative.cir` are
deliberate negative controls and must keep their stop assertion red if a fixed
PWM or enable-only regression is introduced.  A passing ngspice run is still
conditional dynamics evidence; it does not establish the complete operating
envelope, a 2240-uF startup, magnetic saturation, fuse arc/restrike, thermal
rating, or any production protection claim.
