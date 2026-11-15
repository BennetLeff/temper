# Rev G100 pre-order optimization review (2026-11-15)

An independent Fable agent reviewed the board and BOM at c9f67da79, read-only. Its scripts and outputs are in this folder. The raw JLC library search responses (`jlc/*.json`, 4.3 MB) are not committed, but `alt-parts.json` and `alt-search.txt` summarize them, and `jlc_search*.py` refetch them. The review is reproduced below, with dispositions at the end.

**Recommendation: order as-is.**
- The same-land BOM savings total about $9 for five boards ($8 for two). That does not justify a gate rerun and a new package while relay stock falls.
- The agent's fee model reproduces the committed totals: $430.70 for five, $282.93 for two.
- Live JLC prices at 14:13 give $436.29 and $285.04 (`estimate-out.txt`).

## (A) BOM-only changes, same lands

| # | Change | Saving, 5 / 2 boards | Evidence |
|---|---|---|---|
| A1 | C39 / C40 / C44 / C45 / C48 / C49: 2.2 µF 50 V X7R 0805 (C125847, extended) → Samsung CL21A225KBQNNNE 2.2 µF 50 V X5R 0805 (C377773, basic) | $5.21 / $4.30 (live) | Same value, voltage, tolerance and land; the rail is at most 12.38 V. X5R is rated to 85 °C, not 125 °C. DC-bias equivalence is **believed**: no curve was fetched (`a1-spec.txt`) |
| A2 | R94: 22 Ω 0.1 % (C861239, extended) → 22 Ω 1 % (C23345, basic) | $3.85 / $3.85 | R94 is in series with R125 (10 Ω 1 %) and U21's RON on DUT_LO, so its 0.1 % is already diluted. Its tempco is worse (100 vs 25 ppm/°C): a small trade |

Rejected after checking:
- **R121:** the basic 1 Ω and 2.2 Ω fail the hot-plug limit (6.71 / 6.77 V against 6.5 V; `hotplug-spice.json`).
- **C0G 1 nF / 560 pF / 4.7 nF and R101 0.33 Ω:** no basic 0603 equivalent exists.
- **U2 → W25Q128JVSIQ:** it costs more at five.
- **AP2112K:** no basic equivalent exists.
- **R30–R33 at 1 %:** they lose about 20 dB of source common-mode rejection.
- **Attrition waste:** $9.90 at five and $15.02 at two, spread over every line, so nothing to act on (`attrition.txt`).

## (B) Pareto changes, no copper

- **B1. Fab note 6 on User.Drawings said "Panel: edge rails added by JLCPCB, V-cut on the LEFT and RIGHT edges only".** It contradicts the Economic tooling-hole order (`board-scan.txt`). **Verified.**
- **B2. The estimate charges no extended-part fee on the hand-fit lines** (BNC, J4). If JLC does charge it, add about $6.
- **B3.** SW2's JLC BOM comment reads "BOOTSEL" because SW2 shares SW1's line. This is cosmetic.

The agent found no Pareto copper change. Its BOM / CPL / board cross-check was clean: 253 = 253 = 253 references, and no position mismatches.

## (C) Respin trades

- **The ten 10 µF 50 V 1210 capacitors** (C80, C82, C89–C92, C94, C95, C99, C100; C138687, extended) on a 1206 land with CL31A106KBHNNNE (C13585, basic). This saves $7.31 for five and $5.14 for two. It needs a DC-bias recheck at 14 V.
- **A1 and A2.**
- **C119 / C120, 1 nF → 560 pF** (a line already paid for). This saves $3.07, but changes the protection screens.

## (D) Supply risk (live, 14:13, `stock-trend.txt`)

| Part | 11-10 | 11-15 | Cover at 5 boards | Note |
|---|---|---|---|---|
| Relay C2684450 | 1,269 | 209 | 10× | Locked |
| Y1 C20625731 | 850 | 328 | 66× | Locked. It went from 675 to 0 in one day on 2026-10-30 |
| TPS65131 C87663 | 755 | 187 | 37× | No stocked alternate |
| TAC5112 C44853692 | 83 | 73 | 15× | Single source |
| OPA2810 C2864204 | 170 | 168 | 17× | Small-reel C2869782 has 21 |
| LM3880 C486059 | 388 | 245 | 49× | Variants on the same land: C2650186 (43), C701873 (133) |
| R123 / R124 C844725 | 105,663 | 3,385 | 188× | Pulse-rated alternates on the same land: C510086, C441916 (pulse curves not compared) |

## Dispositions (2026-11-15)

- **Order as-is:** accepted. A1, A2 and the 1206 change go to the respin list (`docs/rev-g100-handoff.md`, "When boards arrive" step 4).
- **B1: fixed at the source.** In `cad/tools/rev_g100.py`, fab note 6 now reads: "Panel: none (Economic PCBA). JLCPCB adds tooling holes through GND pour only, e.g. X 1.5 Y 98.5, X 98.5 Y 95.0, X 94.0 Y 8.0 mm from lower-left. Rails only if asked: L/R V-cut." Only User.Drawings and the fab drawing change, so the Gerber zip has a new hash (see the handoff).
- **B2:** a budget note in the handoff.
- **B3:** left as is.
- **D:** the handoff's pre-buy list now has Y1 and TPS65131 alongside the relays.
