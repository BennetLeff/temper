# Independent manufacturer-model checks

Official archives downloaded 2026-09-19:

- [UCC27624 Rev A model, SLUM884](https://www.ti.com/lit/zip/SLUM884).
  `ucc27624.lib` is extracted unchanged from the archive.
- [SN74HCS74 model, SCEM774](https://www.ti.com/lit/zip/SCEM774).
  `SN74HCS74.CIR` is extracted unchanged.
- The official [STW65N65DM2AG model](https://www.st.com/resource/en/spice_model/stw65n65dm2ag_spice.zip)
  was identified, but the download timed out with zero bytes. It is **not used**.

From this directory, run ngspice45.2 with:

```sh
ngspice -n -D ngbehavior=ps -b driver-load-check.cir > driver-load-check.log 2>&1
ngspice -n -D ngbehavior=ps -b latch-behavior-check.cir > latch-behavior-check.log 2>&1
rustc --edition=2021 check_measurements.rs -o /tmp/f2-vendor-check
/tmp/f2-vendor-check .
```

The latch fixture uses the source circuit's D=CLR=qualified health and raw
ARM clock. Its observed output is high after arm, low during fault, still low
after health returns with ARM held high, and high after a fresh edge. Supply
is fixed5V; this is not a brownout or back-power qualification.

The driver fixture uses15V,10Ω and12nF with10kΩ gate pulldown. The capacitor
is an authored lumped load based on120nC/10V, not the exact ST MOSFET.
Observed EN0.8V→OUT13.5V delay is0.193464µs and EN0.8V→gate4V is0.360851µs.
Gate4V is an observation, not proof of drain-current cessation. These are
model results at one condition, not maximum hardware delays.

Ngspice reports four ignored `TD=0` switch-model parameters. Inspection of the
unchanged vendor bytes confirms all four are zero; the log retains the warnings.
No nonzero timing parameter was silently removed. The model result does not
establish complete PSpice equivalence or guarantee the datasheet's maximum.

The HCS74 macro-model also contains internal input capacitances that must not
be assumed to equal real pin capacitance. Ideal voltage sources drive this
logic-retention fixture. Use it as an independent functional check, not as
loading evidence for the comparator/AND chain.
