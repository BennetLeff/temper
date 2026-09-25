# Late-time minimal-event reproducer

This bounded fixture asks one narrow question: does a reduced driver model
produce an accepted transient row at exactly the same time as the previous
row, followed by ordinary positive time advance, when the PWM input crosses
the late threshold seen in the rejected full-plant run near 0.501554914 s?

It is a reproducer attempt, not a substitute for the power-stage run. The
two decks use the same native translated COMPHYS input-state candidate and the
native hysteretic authored reference used by the preceding bounded benches.
They retain the small output/load network, but omit the plant state, so a
non-reproduction cannot clear the full-plant numerical issue.

## Fixture bounds

Both decks use ngspice 45.2, `uic`, `.tran 500u 0.501558 0 500u`, and the
same tolerances as the preceding driver benches. The 500 us maximum step is
used for the quiescent interval; explicit PWL breakpoints bracket the local
threshold edge from 0.501554000 s through 0.501555000 s. No fixed 1 ns step
is used across the 0.5 s interval. Each process was externally bounded by a
20 s alarm; both completed in under 0.1 s wall time.

Commands (run from this directory):

```text
/usr/bin/time -p perl -e 'alarm 20; exec @ARGV' /opt/homebrew/bin/ngspice -b -o native-comphys-late.log native-comphys-late.cir
/usr/bin/time -p perl -e 'alarm 20; exec @ARGV' /opt/homebrew/bin/ngspice -b -o native-sw-late.log native-sw-late.cir
rustc --edition=2021 -D warnings -O inspect.rs -o inspect
./inspect native-comphys-late.tsv native-sw-late.tsv
```

The inspector parses every saved row, rejects non-finite times, and checks
exact adjacent-time equality and negative time steps. It does not round times
or apply a tolerance to the equality test.

## Result

The bounded runs completed normally:

| deck | saved rows | ngspice transient timepoints | rejected timepoints | first time (s) | last time (s) | minimum positive `dt` (s) | exact equal pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| native COMPHYS | 1071 | 1080 | 8 | 5.00000000000000041e-6 | 5.01557999999999948e-1 | 3.00056646196367183e-11 | 0 |
| native hysteretic | 1057 | 1061 | 3 | 5.00000000000000041e-6 | 5.01557999999999948e-1 | 8.79200046099981591e-11 | 0 |

All parsed timestamps were finite, strictly increasing, and reached the
requested endpoint. Therefore this reduced event does **not** reproduce an
exact same-time accepted pair, and there is no “equal then positive” sequence
to show. The local PWL edge was exercised: both traces contain rows around
0.501554900 s where `pwm_input` crosses 2.2 V and `driver_req` changes to the
15 V state, followed by ordinary positive time increments.

The result narrows the fault hypothesis: a bare late PWM threshold edge plus
the reduced output load is insufficient to trigger the full-plant timestamp
pathology. The next discriminating capture must preserve the plant state and
record internal diagnostic nodes at the first invalid full-run sample; this
fixture does not justify changing solver settings or checker policy.

## Source and artifact hashes

SHA-256 (generated with `shasum -a 256`):

```text
native-comphys-late.cir  f561349c61dfa867eef6820f516cac2722bab13ae25b34b5a80aba049edf35c1
native-sw-late.cir       63a6c17fdd3502515f03e95ec0eb06123abee58b04fc22d238ee9fc7403d0f64
native-comphys-late.tsv  f138142ea1080825f7df033d5e996d48b11847873af40de1700706a483780f96
native-sw-late.tsv       2cd63bcb1b5baabaee083ec3aa970158d150e9fdd4c933ef2761496d87600177
inspect.rs               cf06acd67e34b7fe0c37dbd870716b35a776d33675916bb804b74d04e890f4c6
```

The included source identities are recorded separately in their owning
candidate folders. At the time of this run their hashes were:

```text
../driver-vendor-comphys-native-candidate/authored_logic_vendor_comphys_native.inc  d4ca097746830488fdf0336767829ecb442f1b95a039728587777fc11b22ba6b
../driver-hysteresis-candidate/authored_logic_hysteretic.inc                         95ae31864ffa55bf33833849ee38c4654bbdb769c9c52976e25a5b4afb73445b
```

