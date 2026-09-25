# Source patch proposal (host review required)

This is a proposed mechanical patch for the first fault decks. It is not a
change to `normal-tracked/cold.cir`, and it has not been simulated.

## Common trace additions

Replace the normal deck's `.save` list in each fault copy with the following
prefix, followed by the diagnostics needed for the case:

```spice
.save time v(acsrc,acn) v(vd) v(vb) v(sw) v(gate) i(Lboost) i(Vchannel) i(Vbody) i(Vac) v(q) v(en) v(fault) v(f2ctl) v(standby_req) v(arm) v(permit) i(Vf2sense) i(Vdboost1sense) i(Vdboost2sense) v(fault_inject)
```

`fault_inject` is a deck-local 0/5 V marker. Its edge must be the declared
mutation edge and must be saved in every fault case, including F2 cases. Keep
the current `v(fault)` detector signal separate. Do not rename `v(fault)` to
the injection marker.

ngspice 45.2 does not expose direct `i(S...)` or `i(D...)` vectors. The
proposal therefore puts named 0-V sense sources in series with the F2 and each
boost-diode branch. Their currents are legal voltage-source branch vectors and
do not add impedance. The sense-source topology change and names belong in the
case receipt.

## F2-CREST / F2-ZERO mutation

Keep the existing `Sf2 vd vb f2ctl 0 SWF2` path. Replace only its control
source with a case-specific event:

```spice
.param T_FAULT=<receipted settled event time>
Vf2ctl f2ctl 0 PWL(0 5 {T_FAULT-1n} 5 {T_FAULT} 0 {TSTOP} 0)
Bfault_inject fault_inject 0 V=(time >= T_FAULT) ? 5 : 0
```

For branch-current evidence, split each path with an ideal sense source:

```spice
Sf2 vd f2_path f2ctl 0 SWF2
Vf2sense f2_path vb 0
Dboost1 sw d1_path DBOOST
Vdboost1sense d1_path vd 0
Dboost2 sw d2_path DBOOST
Vdboost2sense d2_path vd 0
```

For the failed-short branch, `i(Vchannel)` remains the total channel-source
current because both the healthy MOSFET and the parallel `Sswfail` branch
return through the existing `Vchannel` source. This is the current that the
failed-short criterion must inspect.

The crest/zero classification is evidence from the accepted normal trace,
not an assumed nominal source period. Record the measured source phase and the
1% crest/zero selection test in the receipt.

## SW-SHORT mutation

Keep the healthy `Msw` branch and add one explicit failed-short branch in the
fault copy:

```spice
.param T_FAULT=<receipted settled event time> RFAIL=1m
Vswfail_ctl swfail_ctl 0 PWL(0 0 {T_FAULT-1n} 0 {T_FAULT} 5 {TSTOP} 5)
Sswfail sw channel_source swfail_ctl 0 SWFAIL
.model SWFAIL SW(Ron={RFAIL} Roff=1e12 Vt=2.5 Vh=.1)
Bfault_inject fault_inject 0 V=(time >= T_FAULT) ? 5 : 0
```

The source hash and `RFAIL` belong to the case receipt. This branch is a
failed-short stress surrogate, not evidence of a real MOSFET short-circuit
impedance or safe operating area. The verdict must remain
`PROTECTION_GAP`/failure if current persists; the controller's gate command
cannot interrupt this branch.

## Evidence changes still needed before execution

The existing Rust checker should not be edited in this preparation slice, but
the host must either extend it or provide an equally strict receipt-bound
adapter that checks `fault_inject` for SW-SHORT and diode cases. The current
checker can validate F2's `f2ctl` edge, but it cannot prove that a
command-line `switch-short` or `diode-short` deck actually applied the
declared graph mutation. It also uses only `q`/`en`/`fault` for its prefault
healthy window; the first campaign receipt should require `arm`, `permit`,
and the case's source-path control to be high there.
