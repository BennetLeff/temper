# Native-expression vendor-COMPHYS hybrid

This is a bounded parser-compatibility experiment. It keeps the same hybrid
topology as `../driver-vendor-comphys-candidate`: the TI COMPHYS input-state
front end, exact 2.2/1.2 V PWM/INM and 4.2/3.9 V AUX references, 200 kΩ/230 kΩ
input loads, and the authored state-product/18.75 nF/1 Ω output surrogate.
It does not model the TI OUTH/OUTL stage, repair the full-plant stall, or create
an accepted source.

The prior hybrid used the TI model's PSpice `IF(...)` expressions and required
`.spiceinit` (`set ngbehavior=ps`) for ngspice parsing. The full cold host uses
default ngspice mode, so this candidate translates only those two expressions
to ngspice-native ternary syntax:

```text
TI EHYS: IF( V(1) > {VTHRESH},-V(HYS),0)
native:  V(1) > {VTHRESH} ? -V(HYS) : 0

TI EOUT: IF( V(INP2)>V(INM1), {VDD} ,{VSS})
native:  V(INP2) > V(INM1) ? {VDD} : {VSS}
```

No `.spiceinit` is present in this folder. The three vendor-oracle TSVs are
copied from `../driver-vendor-comphys-candidate`, where they were run under
the documented PSpice compatibility mode; their hashes are retained below.
They were not rerun in native mode, so the vendor oracle remains explicitly
PSpice-mode evidence.

## Bounded checks

Each authored ngspice process ran in default mode with an explicit 30 s alarm:

```sh
perl -e 'alarm 30; exec @ARGV' /opt/homebrew/bin/ngspice -b -o CASE.log CASE.cir
```

The copied vendor traces and native authored traces passed the existing strict
Rust checker:

```sh
rustc --edition=2021 -D warnings -O check_hysteretic.rs -o /tmp/matrix07-vendor-comphys-native-check
/tmp/matrix07-vendor-comphys-native-check .
```

The six authored traces are byte-identical to the corresponding prior hybrid
PSpice-mode authored traces, not merely numerically close:

```text
authored-threshold-hysteretic.tsv  exact-match
authored-fast.tsv                 exact-match
authored-sequence.tsv             exact-match
authored-aux-sweep.tsv            exact-match
authored-inm-sweep.tsv            exact-match
authored-late.tsv                 exact-match
```

The late reduced fixture reached 0.25702 s with 514,094 rows and gate off. The
checks therefore show that the parser-mode translation preserves this bounded
hybrid's output exactly, while saying nothing about the full 650 ms plant.

## Fidelity and limits

The expression translation is the only model transformation. The COMPHYS
internal R1/C1 topology and hard `EOUT` remain unchanged. The source is not
byte-verbatim to TI because the two conditional expressions are intentionally
translated; the normalized TI primitive body and the native body should be
reviewed as equivalent parser forms, not treated as a vendor-library hash.

Hashes:

```text
native candidate include   d4ca097746830488fdf0336767829ecb442f1b95a039728587777fc11b22ba6b
TI UCC27511A.lib source     eb78c0ce0d9cf2dd5bbc5f937bbfc6cc38c95215e035feaeb3950672e8c05c6d
vendor-threshold.tsv       71f7805368708e9a020491a928dc807bee8b7a9ed41a4a0c3efa46006865dd2d
vendor-fast.tsv            0591ca5a088f59a9a73a404fb8df8521bcb8db6cd5082a561069bfbc9d925a81
vendor-sequence.tsv        67225984f7f01782914e0f44849d91a54151d522b5ac0d2b61a252cef4a29fad
```

No global `.spiceinit` was changed or installed, no full cold run was
launched, and no adoption decision follows from this parser-compatibility
result.
