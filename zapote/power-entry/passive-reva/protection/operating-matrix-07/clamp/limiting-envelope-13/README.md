# ISENSE clamp limiting envelope (bounded simulation)

Date: 2026-09-21 (UTC)  
Status: sensitivity evidence only; no part selection, qualification, or
schematic change.

This fixture quantifies the missing forward-voltage/current envelope called
out by `host/model-gap-closeout-12.md`. It is deliberately separate from the
full plant and from the selected Vishay model. The retained controller facts
and the reason the low-current VF bounds are missing are in
`../datasheet-audit/report.md`:

- TI UCC28180 section 8.3.14 asks for an external diode VF greater than the
  maximum PCL magnitude (0.438 V) and below 1.1 V over temperature and
  component variation; section 9.2.2.9 uses 220 ohm/1000 pF.
- The Vishay BAV23C PDF has guaranteed VF maxima at 100/200 mA and 25 °C, but
  no guaranteed low-current VF(min)/VF(max) curve over the controller range.
  Its page-3 plot is typical, not a bound. The selected-part document is
  `../datasheet-audit/bav23c.pdf`.

## Fixture and declared limiting law

The topology is the existing negative ISENSE path:

```text
VSHUNT (negative) ── 220 ohm ── ISENSE ── 1 nF ── ground
                                      │
                         clamp current: ground → ISENSE
```

Each case uses an ngspice 45.2 transient source with a finite pulse:

```text
0 V for 1.00 us → VSHUNT in 10 ns → VSHUNT for 4.00 us
→ 0 V in 10 ns; period 8.00 us
```

There are three open-clamp cases (`-0.438`, `-1.1`, `-5 V`) and eighteen
piecewise hard-clamp cases: each source amplitude crossed with VF magnitudes
`0.350, 0.438, 0.550, 0.700, 0.900, 1.100 V`. The hard clamp is an explicit
limiting surrogate, not a diode model:

```text
Iclamp = 0                         when -VISENSE <= VF
Iclamp = (-VISENSE - VF) / 1 mOhm  when -VISENSE > VF
```

The 1 mOhm slope is only a numerical hard-clamp parameter. For a flat source,
the independent Rust oracle is therefore, when active,

```text
I = (|VSHUNT| - VF) / (220 ohm + 1 mOhm)
VISENSE = -VF - I * 1 mOhm
```

The resistor current reported below is its magnitude. The ngspice branch
current through the source-oriented measurement element has the opposite
sign when the clamp conducts.

## Results

The complete machine-readable result is `results.csv`. It reports flat-state
ISENSE, resistor/clamp current, transient peak current (**UNVALIDATED**), active-pulse energy
(1.00–5.02 us), full-window energy (0–8 us), and the declared 4 us flat pulse.
The table below gives the flat state, peak currents (**UNVALIDATED**), and full-window energies;
energies are joules and currents are amperes.

### Open clamp

| VSHUNT | VISENSE(flat) | resistor I(flat) | peak |Ires| (**UNVALIDATED**) | Eres(0–8 us) |
| ---: | ---: | ---: | ---: | ---: |
| -0.438 V | -0.4379999 V | 0.65 nA | 1.946 mA | 0.189 nJ |
| -1.100 V | -1.1000000 V | 1.64 nA | 4.888 mA | 1.192 nJ |
| -5.000 V | -4.9999980 V | 7.45 nA | 22.219 mA | 24.626 nJ |

The small open-clamp flat current is the residual from the 1 nF transient,
not a DC conduction path.

### Piecewise hard clamp

For each row, `Ires(flat) = Iclamp(flat)` by KCL. `Ires(pk)` includes the
10 ns source edge and the 1 nF charging transient; `Iclamp(pk)` is the peak of
the piecewise current source. Both instantaneous peak columns are
**UNVALIDATED**: the 1 mOhm hard-clamp slope makes them solver-tolerance
sensitive. The bounded convergence evidence is in
[`peak-diagnostic/README.md`](peak-diagnostic/README.md). `Eres` and `Eclamp`
are full 0–8 us energies.

| VSHUNT | VF | VISENSE(flat) | Ires = Iclamp(flat) | Ires(pk) (**UNVALIDATED**) | Iclamp(pk) (**UNVALIDATED**) | Eres | Eclamp |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| -0.438 | 0.350 | -0.3500004 | 0.400 mA | 1.946 mA | 0.757 mA | 0.280 nJ | 0.511 nJ |
| -0.438 | 0.438 | -0.4379999 | 0 | 1.946 mA | 0 | 0.189 nJ | 0 |
| -0.438 | 0.550 | -0.4379999 | 0 | 1.946 mA | 0 | 0.189 nJ | 0 |
| -0.438 | 0.700 | -0.4379999 | 0 | 1.946 mA | 0 | 0.189 nJ | 0 |
| -0.438 | 0.900 | -0.4379999 | 0 | 1.946 mA | 0 | 0.189 nJ | 0 |
| -0.438 | 1.100 | -0.4379999 | 0 | 1.946 mA | 0 | 0.189 nJ | 0 |
| -1.100 | 0.350 | -0.3500034 | 3.409 mA | 4.888 mA | 6.750 mA | 10.406 nJ | 4.682 nJ |
| -1.100 | 0.438 | -0.4380030 | 3.009 mA | 4.888 mA | 3.451 mA | 8.232 nJ | 5.135 nJ |
| -1.100 | 0.550 | -0.5500025 | 2.500 mA | 4.888 mA | 3.058 mA | 5.894 nJ | 5.301 nJ |
| -1.100 | 0.700 | -0.7000018 | 1.818 mA | 4.888 mA | 2.030 mA | 3.510 nJ | 4.816 nJ |
| -1.100 | 0.900 | -0.9000009 | 0.909 mA | 4.888 mA | 1.424 mA | 1.636 nJ | 2.971 nJ |
| -1.100 | 1.100 | -1.1000000 | 0 | 4.888 mA | 0 | 1.192 nJ | 0 |
| -5.000 | 0.350 | -0.3500211 | 21.136 mA | 22.219 mA | 27.095 mA | 393.921 nJ | 29.546 nJ |
| -5.000 | 0.438 | -0.4380207 | 20.736 mA | 22.219 mA | 26.270 mA | 379.248 nJ | 36.235 nJ |
| -5.000 | 0.550 | -0.5500202 | 20.227 mA | 22.219 mA | 22.642 mA | 361.013 nJ | 44.321 nJ |
| -5.000 | 0.700 | -0.7000195 | 19.545 mA | 22.219 mA | 36.489 mA | 337.363 nJ | 54.402 nJ |
| -5.000 | 0.900 | -0.9000186 | 18.636 mA | 22.219 mA | 31.477 mA | 307.199 nJ | 66.512 nJ |
| -5.000 | 1.100 | -1.1000177 | 17.727 mA | 22.219 mA | 21.712 mA | 278.599 nJ | 77.108 nJ |

The active-pulse energy columns in `results.csv` exclude the post-edge
discharge tail by definition; the full-window columns include it. This is a
bookkeeping distinction, not a package-energy or thermal model.

## Independent check and commands

`generate.rs` is the Rust fixture generator and analytic-table owner;
`check.rs` independently parses the ngspice measurement logs and compares all
21 flat operating points with the resistor/clamp equations above. It checks
finite/nonnegative energies and that every reported peak is at least its flat
current. This is an internal numerical consistency check, not peak
qualification. The comparison bounds are 5 µV and 0.5 µA, chosen for the printed
`.meas` precision and the late 4.0–4.8 us sampling interval. They are
numerical comparison bounds only, not silicon requirements.

```text
rustc --edition=2021 -O generate.rs -o generate
./generate .
for cir in generated/*.cir; do
  perl -e 'alarm 30; exec @ARGV' ngspice -b -o "${cir%.cir}.log" "$cir"
done
rustc --edition=2021 -D warnings -O check.rs -o check
./check .
```

Observed result:

```text
PASS 21 bounded ngspice fixtures; flat-state values agree with independent resistor oracle
```

The generated circuits/logs/raw files are listed and hashed in
`generated.sha256` (63 files, SHA-256
`37f8e14c2de1266c2dcc83830f5800b0ff144c7486d978fa6d06384520365801`). Other
source/result hashes are:

| file | SHA-256 |
| --- | --- |
| `generate.rs` | `b8c1f5ff2feba9bd31b245350cbc6e9e7d754b22e884d6159cb4e0b400fdfeed` |
| `check.rs` | `a2475fdca1bfc68dcfcd42170d2432946a811ef5c76fa01b9124482b491f33a6` |
| `analytic.csv` | `fc0a7d626cf57ed9e232b8608bbb0c65d7a0201f05b3a80016653592ab9f2f94` |
| `results.csv` | `fcc07a36d1df32799ffe6344088398e82307829974e62dcdf5938338d659adc2` |

## Interpretation

This experiment demonstrates how much a declared forward-voltage envelope can
move ISENSE loading and pulse energy. It does **not** select a VF range for the
Vishay BAV23C-E3-08, convert typical curves into limits, or qualify its pulse
SOA/thermal behavior. The 1 µA/2 mV screens remain engineering screens only.
The piecewise clamp is a limiting control; its 1 mOhm slope, 1 nF capacitor,
10 ns source edges, and transient peaks are not a vendor diode model. The
original-tolerance instantaneous peaks are retained as unvalidated diagnostics;
the separate solver comparison shows convergence only after tighter tolerances
or a smaller step. The next evidence needed for a part claim is a selected-part
low-current VF(min)/VF(max) versus temperature/tolerance curve or an assembled
temperature/pulse characterization. Until then, carry these tables as model
sensitivity, not worst-case hardware bounds.
