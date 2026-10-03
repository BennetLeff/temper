# Round-3 decision review and owner decisions

After round 3, four review workers assessed proposals A–D (from the
reviewer's round-3 summary) against the saved data. Their dossiers and the
field-solver fixtures were in machine-local `/tmp`; they are preserved here.
The full monitoring handoff is [../HANDOFF-2026-09-28.md](../HANDOFF-2026-09-28.md).

## Owner decisions, 2026-09-28

| Item | Decision | Qualification |
| --- | --- | --- |
| A: current-limited operation | **Proceed** | 42 A is a **provisional ceiling on actual tank peak current** for analysis, not a firmware setpoint. The command must sit below it by the sensing/control error and transient allowance. Rejected power requests need fresh derated solves. |
| B: shunt as backup, resistor-only retune | **Hold** | No R34/R35 change until fault-current, device-energy and actual gate-off timing are proven. |
| C: 450 ns dead time | **Evaluate only** | 450 ns is nominal. TI characterizes 50 kΩ at 399/443/487 ns min/typ/max. Driver tolerance, extra body-diode dwell and recovery losses, and hard turn-on need evaluation. No hardware change. |
| D: field-solved gate/loop inductance | **Proceed** | FastHenry now builds (below); the board extraction, convergence and SPICE allocation remain. |
| Evidence storage | **Option 1** | See [../raw-evidence/README.md](../raw-evidence/README.md). |

Still separate, open gaps: F4 (a single stuck PWM is only cleared by the
0.9–2.5 s watchdog) and F5 (BUS_FAULT is not guaranteed asserted through a
slow HOT5 brownout). See task 02 round 3.

## Correction: the 724 V B1 event

The reviewer's round-3 summary called the 724 V peak a false turn-on and
shoot-through. **The saved waveforms don't show that.** At the 723.918 V peak
(2.492115 µs) the low-side die VGS was −2.107 V; the 7.365 V VGS peak came
later, at 3.095563 µs, with low-side VDS at 15.60 V. The simultaneous
high-side device current wasn't saved. Deciding the cause needs both device
currents and controlled comparisons (ideal off-gate; common-source
inductance removed). If false turn-on persists, the review's remedy order is:
source return / common-source inductance, then the paired gate loop and sink
impedance, then a Miller clamp or negative bias. None is approved.

## Dossiers

- [current/dossier.md](current/dossier.md), [current/screen.json](current/screen.json):
  the 135-case grid screened by peak tank current. At a 42 A ceiling, 73 of 135
  cases remain; only three 1710 W cases (cast iron, high coupling).
- [deadtime/dossier.md](deadtime/dossier.md): the 348 → 450 ns evaluation
  plan and its limits.

## FastHenry build (item D)

Official FastHenry2, commit `363e43ed57ad3b9affa11cba5a86624fad0edaa9`,
unmodified source, built on Apple clang with legacy-C flags:

```sh
git clone https://github.com/ediloren/FastHenry2 && cd FastHenry2
git checkout 363e43ed57ad3b9affa11cba5a86624fad0edaa9
make fasthenry CFLAGS='-O2 -DFOUR -std=gnu89 -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-incompatible-pointer-types -Wno-int-conversion -Wno-error=return-mismatch'
```

The warning suppressions don't prove every numerical path correct.
Fixtures (`fieldsolver/`): a 10 × 50 mm plane pair at 0.5 mm spacing gave
2.75069 / 2.94787 / 3.08025 nH at 10 MHz with 20/40/80 subdivisions,
against 3.14159 nH ideal (40→80 change 4.30 %, final discrepancy 1.95 %);
the straight-wire fixtures also ran. `build.log.gz` is the full build log.
This establishes a usable executable, not a board inductance.
