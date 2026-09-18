# AR-PROTECT attempt-001 — corrected fault-loop and protection assessment

Task **AR-PROTECT** · Attempt **attempt-001** · Campaign 2026-09-17-pfc-campaign · fault_assessment.
Contract C1.1 `0accd9bc…a825d6` (matches dispatch). Dispatch `source_revision` `3691798ca…`; HEAD `fd9d70577…`
= that commit plus the coordinator's withdraw/enforce commit that added this dispatch (AR-DESIGN/AR-VERIFY pattern). Source-only; the delta cannot affect a number.

**Hypothesis / changed variable.** None — source-only assessment of the existing routed candidate and
the **AR-DESIGN/AR-VERIFY proposed active bridge**, not the retained board. It tests whether the
internal 179.24 J discharge can be distributed through the real loop, whether the active bridge
survives its own fault path, and what protection actually interrupts each loop.

## 1. The active bridge under assessment

Proposed, **not on the retained board**: NXP **TEA2209T/1** driving four MOSFETs (reference
**IPW60R017C7**, 600 V CoolMOS C7, hot typ ~17.4 mΩ/device), replacing incumbent U1 GBJ2510-F. Two
devices conduct in the line path per half-cycle; high side bootstrap-supplied, low side from VCC;
body diodes form a passive bridge at start-up and whenever drivers are off. Sources:
`AR-DESIGN/attempt-001/raw/TEA2209T.pdf` `fb611299…`, `Infineon-IPW60R017C7.pdf` `2c5a60a2…`.

## 2. Active-bridge fault path and controller behaviour

- It sits **in** the line-fed fault loop (same series position as the passive bridge) and is **not** in the internal cap-discharge loop.
- The TEA2209T senses only mains polarity (±250 mV). It has **no overcurrent detection**. Its only
  relevant actions: gate pull-down on driver UVLO, a drain-source protection that disables all
  drivers (documented purpose: start-up), a 22 V minimum-mains gate, an external COMP disable.
- **Gate shutdown cannot interrupt an already-shorted transistor, and on this part it cannot open the
  line loop at all:** all drivers off leaves the body diodes conducting — it reverts to the
  passive-diode path. A shorted bridge device also defeats the diagonal-pair dead time.
- **Structural effect:** conducting through channels instead of ~2 diode drops *lowers* the line-fault
  loop impedance, so the prospective current is **higher** and survival is **more** dependent on F1,
  not less. (Magnitude null — §4.)

## 3. MOSFET survival — INDETERMINATE, and not transferable

| Metric | IPW60R017C7 (active bridge) |
|---|---|
| `ID,pulse` | 495 A at T_C 25 °C (pulse width T_j-limited) |
| Avalanche single pulse `E_AS` | 582 mJ |
| Avalanche single pulse `I_AS` | 12.6 A |
| **I²t / short-circuit withstand** | **none published for either** |
| SOA / Z_th | Diagrams 2–4 exist; coordinates not digitised (fault waveform unresolved) |

Survival at the fault = **null / INDETERMINATE**: it needs the prospective current (line impedance
unresolved) **and** duration (F1 total clearing unresolved) to map onto the SOA/Z_th curves. **The
GBJ passive bridge's 350 A IFSM / 510 A²s I²t are the incumbent's and are NOT used to qualify this
replacement.** Voltage is not the binding stress (line peak 186.7 V on a switch short; ~400 V bus on
a diode short — inside the 600 V device / 440 V controller operating limit).

## 4. The two fault classes, separated

| | (i) Line-fed switch short | (ii) Internal capacitor discharge |
|---|---|---|
| Source | AC mains | DC bus bank |
| Example | U9 D-S short; active-bridge MOSFET short | shorted U10 with U9 conducting |
| Limiting impedance | line/source + CMC/NTC + devices — **unknown** | U9 R_ds + SiC V_f + ESR — **not modelled at multi-kA** |
| Timescale | ms class (60 Hz half-cycle 8.333 ms) | **~100 µs** (τ = 94.1 µs = 42 mΩ × 2240.47 µF) |
| Energy | null | **179.238 J** stored (2240.47 µF at 400 V) |
| Loop | mains → active bridge → U8 → shorted U9 → U12 → back | **caps → shorted U10 → U9 → caps, bypassing U12** |
| Interrupter | F1, series — coordination unestablished | **none** |

The U9/U10 split and internal peak current stay **null**: the loop's high-current behaviour (SiC V_f(I), R_ds(T_j), ESR, layout) is not defensibly modelled. The withdrawn 116 µs / 7.7 kA / 34 J figures are **not reused** — the 116 µs wrongly included the 10 mΩ shunt, and U12 is outside the loop.

## 5. Protection arrangement — what acts, on which loop, and what it cannot do

- **Line-fed loop (i):** **F1** (Schurter 0034.3129, 16 A/250 V time-lag, holder U2) is a series,
  self-interrupting element in every line-fed path, so by topology it *can* interrupt them. It
  **cannot yet be relied on**: total clearing at the prospective current and matching conditions is
  unestablished — only a typical melting I²t of 1638 A²s at 10× rated and a 160 A breaking capacity
  at 250 VAC are published, and the prospective current is unknown. Gate shutdown cannot assist
  (body diodes).
- **Internal loop (ii):** **nothing acts.** F1 is outside it, shunt U12 has one terminal on it, the
  PFC controller UCC28180D cannot sense it, and gate shutdown cannot open a shorted U10 or a
  conducting U9. **Conclusion: no adequate protection exists on the current board for this loop.** A
  crowbar would divert, not interrupt, and needs a coordinated series interruption or energy path.

**Faults it cannot interrupt:** the internal discharge; any already-bolted short (gate shutdown cannot
open a physical short); a crowbar alone (diverts); a line-fed fault below F1's clearing threshold;
L–PE/common-mode surge (MOV is L–N only); active-bridge cross-conduction from a shorted device.

## 6. Loop-consistency gate (necessary connectivity check only)

Command (run; output retained in `raw/checker/`): `python3 zapote/tools/check_fault_loop.py --netlist raw/netlist_fault_loop.json --loop-nets PFC_BUS_PLUS_390V,PFC_BUS_MINUS,a1 --assignments <file>`

| Model file | Exit | Result |
|---|---|---|
| `assignments_corrected.json` (caps' ½CV²; U9/U10/U12 = 0 = null) | 0 | CONSISTENT |
| `assignments_null_distribution.json` (all null) | 0 | CONSISTENT |
| `assignments_withdrawn_negative_control.json` (U12 = 34.46) | 1 | INCONSISTENT — "U12 … only 1 of its terminals … lie on the declared loop" |

The failing file is the withdrawn AR-FAULT distribution, retained as the checker's teeth; it is **not**
a model of this attempt. The checker is connectivity only — a passing run does **not** prove a
conductive path, a device state, a direction or a distribution, and is not physical evidence.

## 7. Circuit recommendation and remaining evidence

**Recommendation:** add a **DC-rated, semiconductor-grade interrupting element in series with the
internal discharge path** (bus between the capacitor bank and the boost diode/switch junction),
coordinated to carry ~4.5 A steady and clear the ~100 µs multi-kA pulse; **or** a DC-bus crowbar
**plus** a coordinated series interruption/energy-handling path. For the line-fed loop, establish
F1's **total clearing** at the prospective current/matching conditions and confirm clearance inside
the device SOA; otherwise add a faster line-side element or an active overcurrent trip **with a
series interrupter**. Do not credit the TEA2209T with fault interruption.

**Evidence still required:** AC source/line impedance; F1 total-clearing curves; internal-loop
high-current impedance model; active-bridge SOA/Z_th digitised against the fault waveform; MOV clamp
at the specified surge; U9 gate state at the fault instant.

## 8. Accounting

- Case census: expected 1; attempted 1; **valid 1**; failed 0; unsupported 0; unrun 0. Solver
  invocations **0**; model/CAD/BOM edits **0**; bench **none**; no commits, no stash.
- Checker: worker-run and retained; dispatch declared it `not_applicable` (G0 unimplemented) → **not
  a harness-validated run**; citations carry `evidence_class: source_research`.
- Touched files: only this attempt directory. Wall time ≈ 35 min; handback before
  `2026-09-18T07:48:04Z`.
- Unresolved: line impedance; F1 total clearing; internal peak/split; device SOA mapping; controller
  post-fault response; active-bridge voltage rating still gated by the undeclared surge clamp.
- **Recommended next observation:** capture F1's total-clearing characteristic at the prospective
  current and matching conditions (itself needing the line impedance). It decides whether the
  line-fed class is protected at all.

---

## Completion-criteria checklist

1. **Assess the proposed active bridge** — **MET.** Fault path traced; TEA2209T behaviour under fault
   documented (no OCP; gate shutdown cannot open a body-diode path); MOSFET survival reported
   **INDETERMINATE** with the required waveform missing; the GBJ's 350 A / 510 A²s explicitly **not**
   used to qualify it.
2. **Separate the two fault classes** — **MET.** §4: line-fed (source-fed, ms, unknown impedance, F1)
   vs internal discharge (179.24 J, ~94 µs, bypasses U12, no interrupter), with distinct limiting
   impedance, timescale, energy and interrupting element.
3. **Protection arrangement that actually interrupts, plus what it cannot** — **MET.** F1 named for
   the line-fed loop (coordination unestablished); "nothing acts" for the internal loop; the
   cannot-interrupt list is explicit.
4. **Keep unresolved peak current / energy distribution null** — **MET.** Line impedance, line
   current/duration/energy, internal peak, U9/U10 split and F1 total clearing are null; the only
   filled energy is the defensible ½CV² total and its equal-voltage capacitor split.
5. **Concrete circuit recommendation + remaining evidence** — **MET.** §7.
6. **Loop-consistency gate passed, output retained** — **MET** for the model assignments (exit 0);
   the withdrawn negative control (exit 1) is retained and labelled. Presented as a necessary
   connectivity check only, not physical evidence.

**Single most important missing input:** the **AC source/line impedance at the fault, jointly with
F1's total clearing behaviour at matching conditions** — the impedance sets the prospective line-fed
current the active bridge must survive, and F1's total clearing (not its melting I²t at 10×) decides
whether the only series interrupter on the board acts before the device SOA is exceeded. The
internal-loop conclusion (no interrupter exists) does not depend on either.
