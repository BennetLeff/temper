# A3/A4 conditional power-stage envelope

This directory is a standalone, dependency-free Rust calculator for the
integration-06 A3/A4 handback. Build and run it with:

```sh
rustc --edition=2021 -O envelope.rs -o /tmp/temper-envelope
/tmp/temper-envelope > result.json
rustc --edition=2021 --test envelope.rs -o /tmp/temper-envelope-tests
/tmp/temper-envelope-tests
```

The default JSON evaluates the retained high-line conditional witness
(132 Vac RMS, 19.8 uF effective-C floor, 100/216 uH L sensitivity pair,
50 A at the chosen static trip point, and a 2 us target). The `conditional_region`
array gives the allowable delay and forward peaks for 40/45/50/60 A across
180/180, 144/216, and 100/216 uH pairs. Use numeric flags to screen another
finite point, for example:

```sh
/tmp/temper-envelope --current-a 45 --delay-us 5 --lmin-uh 144 --lmax-uh 216
```

Invalid, negative, non-finite, or inconsistent inputs are rejected with a
nonzero exit status. There is no Python engineering authority and no runtime
dependency on the donor checkout.

The screen uses the retained conservative construction:

```text
Vline,pk = sqrt(2) * Vin,rms,max
Iend     = Istart + Vline,pk * t / Lmin
Vend     = Vstart + Iend * t / Cmin
Vpeak    = Vline,pk + sqrt((Vend - Vline,pk)^2 + Lmax/Cmin * Iend^2)
ΔEcap    = 1/2 * Cmin * (Vend^2 - Vstart^2)
```

The current rise during the delay and the current at the threshold are
reported as separate fields. `ΔEcap` is energy charged into the isolated VD
local reservoir during the delay. The post-delay expression independently
credits the maximum inductor energy; the construction can double-count
mutually exclusive trajectory details and is therefore labelled a conservative
screen, not a physical transient solution or energy-closure proof.

The selected node records keep distinct quantities and authorities:

* VD local reservoir: 630 V candidate-part rating; 500 V is a chosen
  conditional engineering screen only.
* VB bulk bank: 450 V electrolytic rating; the 410 V value is a separate
  conditional initial state only. VB capacitance is not credited after F2 opens.
* VDS and diode reverse voltage: 650 V ratings; no operational transient target
  or rating margin is reported until ringing and installed parasitics are
  bounded. VD's idealized peak is not VDS evidence.
* VGS: ±25 V absolute rating; 15 V is a chosen conditional gate-drive target,
  not a manufacturer guarantee for the assembled driver loop.

The JSON also records the nominal RevB divider/controller anchors. The source-07
divider has a 987 kOhm upper chain, 200 Ohm step, and 5.62 kOhm bottom; its
2.5 V high and low tap-derived bus values are 426.469 V and 441.646 V nominal;
the low tap is not an installed OV comparator. The UCC28180 5.35/5.45 V OVP
anchors are 416.888/424.681 V with the 1 MOhm/13 kOhm feedback network; the
5.0 V regulation anchor is the retained 389.615 V nominal bus. The retained current-sense anchors are 0.285/0.259 V over
the 10 mOhm shunt (28.5/25.9 A), while the UCC28180 PCL threshold is separately
0.400 V typical and 0.438 V maximum (40/43.8 A before shunt tolerance). These
are thresholds, not instantaneous-current maxima.

Primary evidence is retained at
`zapote/power-entry/passive-reva/protection/f2-timing-02/README.md` and
`.../sources/ucc28180.pdf`, `.../sources/760800301.pdf` in the dirty experiment checkout based on
`5dde29ab3e2f1223c2d33c129ced2cf647238307`. Those local evidence files are
identified by content hashes in the integration receipt; their presence in that
commit is not claimed. The UCC28180 datasheet provides
the input-referred PCL threshold but no applicable maximum PCL-to-gate delay.
Würth 760800301 specifies 180 uH ±20%; its 43 A saturation figure is typical
at a stated 30% inductance reduction, not a current clamp or guaranteed
L(I,T) bound.

The result remains `INDETERMINATE` until the exact missing data are closed:
effective C over temperature/frequency, L(I,T) over the fault trajectory,
UCC28180 current-limit response, loaded STW65N65DM2AG current cessation,
installed VD/VDS/diode ringing limits, and fuse/interconnect arcing behavior.
The observed 51 A plant point and assumed 100 uH input remain examples only.

Host verification additionally integrates the independent circuit equations
`dV/dt=I/C`, `dI/dt=(Vin−V)/L` with RK4, including source work in energy
balance. Three L/current witnesses match the closed-form zero-delay peak.
Two added regressions exposed and fixed a silent1ms inverse-search cap and
acceptance of an initial voltage below the monotonic charged-boost domain.
The CLI rejects duplicate, missing and unknown arguments. The configurable
screen is reflected in the node metadata as well as the numerical verdict.
