# Discharge topology and fault disposition, 23 September 2026

**Decision: keep product schematic and PCB on hold.** The next circuit concept worth developing is two separately contacted, normally closed VB-to-HOT0 fast resistor branches, plus two independent always-connected VD-to-HOT0 strings and a local path for any capacitance isolated downstream. This is a *topology*, not a selected contact, resistor, connector, winding supply, accepted time, safe-to-service result, or routed board. The old single common contact is rejected as a one-contact-open fast-discharge concept under the illustrative screen below.

## Source identities and assumptions

- Calculation base: `47265a2f86534d3c09cbfb57375aae4d9855f989` on `codex/zapote-discharge-next-20260923` before this note. The committed Rev38 `pfc_power.ato` hash is `e3daa14ea8b74344c307a86908c86cbf4d9b44447af367febeb4b581a84ba761`; the existing five-file `source-inputs.sha256` lock passes. The committed Rev38 source puts the local film capacitance on VD_LOCAL, four electrolytics on VB_BANK, with F2 between the positive rails and HOT0 common.
- Read-only active power-entry revision inspected: `115894582c9df4d7609b5bc2c6e27e28041e0724`; its `pfc_power.ato` hash is `6810c5fd757f95413fb0a6c5edc34ea2d30eb8cef0feeb501e5916105e1eb4ff`. Its active-worktree `F2-BOARD-INTERFACE.md` hash is `fcc2913246e23169f86181984d1839a53aa0e8590b0f24ca0dde4c6f1ec60c5a`. It places F2 in an off-board holder via a proposed two-potential Phoenix 1017526 PCB terminal. The manufacturer's [product record](https://www.phoenixcontact.com/en-pc/products/pcb-terminal-block-tdpt-16-2-sc-1016-zb-1017526) confirms two potentials and two solder pins per potential; the active note still has unresolved drill/pin data and fault-current acceptance. No discharge tap, HOT0 terminal, service point, or inverter isolation may be inferred from that F2 terminal. F2 does not clear a VB-bank-to-inverter short by itself.
- Capacitance screen: VD 24.717 µF and VB 2688 µF from tolerance-high committed Rev38 parts, plus hypothetical 100 µF *direct* inverter input and a separate hypothetical 100 µF *detached* inverter island. [TDK's film part record](https://product.tdk.com/en/search/capacitor/film/dc-link/info?part_no=B32776P6226K000) and [Nichicon LGX catalog](https://www.nichicon.co.jp/english/series_items/catalog_pdf/e-lgx.pdf) support the source part-family values. No real inverter capacitor or disconnect is selected.
- Two **illustrative only** isolated-source scenarios are 400 → 80 V within 120 s and 450 → 34 V within 60 s. The latter starts at the VB capacitor's 450 V rating edge; that rating is not an allowed bus operating voltage. These numbers are not an adopted service, access or restart rule. The [IEC 60335-1 scope page](https://webstore.iec.ch/en/publication/61880) does not determine the applicable voltage/time clause for this appliance; that determination and edition remain a product-safety decision.
- Model charges a 5 s release allowance to an entire switched decay, uses +1% path resistance for time and −1% for initial heat/current, assumes ideal parallel branches, and ignores leakage and powered load. The delay, tolerances and fault behavior are hypothetical. Contact bounce, wiring, capacitor capacitance over frequency/temperature, bank imbalance, switch inrush, resistor drift, current source and heat transfer are **not** bounded.

## Candidate comparison

The table is from [`topology-output.csv`](topology-output.csv), specifically the 450 → 34 V / 60 s, F2-open, mains-isolated case. The existing Rev38 450 kΩ bank bleeder and 992.82 kΩ F2 detector remain parallel slow paths. VD has two proposed 800 kΩ strings; its result is 25.792 s nominal topology and 51.584 s if one string opens, using the same +1% assumption. That thin one-string margin has no aging or heat qualification.

| VB candidate | Intact VB time | One resistor branch open | One contact stuck open | Common hold remains energized | Initial fast-path power at 450 V, −1% R | Disposition |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| One always-connected 7.5 kΩ branch | 53.258 s | 2252.114 s | no contact | no hold coil | 27.273 W continuously if VB is held up | Misses one-open case; substantial continuous heat. |
| Old one-NC-contact, two 15 kΩ branches behind it | 58.258 s | 109.056 s | 2257.114 s | 2252.114 s | 27.273 W when engaged | Fails one branch/contact fast case. |
| Two independent NC contacts, each with its own 7.5 kΩ branch | 31.948 s | 58.258 s | 58.258 s | 2252.114 s | 54.545 W with both closed | Only arithmetic survivor under one independent open; common hold fault still fails. |

At 450 V the VB bank plus hypothetical direct 100 µF holds **282.285 J** before losses. The passive-only path's open-resistor time and both switched candidates' common-hold time are governed by the unqualified Rev38 slow resistors. An open contact or branch in the two-contact concept leaves only 1.742 s illustrative margin after the assumed 5 s release allowance. Exact timing, tolerance drift and assembly temperature could erase it. No branch resistor order code is selected; one 7.5 kΩ *branch* may need several suitably rated elements and a heat sink. All quoted wattages are source-held initial values at −1% R, not a resistor-body temperature prediction or a validated continuous-duty rating.

With F2 closed, VD and VB form one bus and both discharge networks share the stored energy. With F2 open, VD and VB are distinct islands. A *detached* 100 µF inverter capacitor with a hypothetical 1 MΩ local path takes 260.872 s at 450 → 34 V; with no path it has no bounded RC completion. Neither VB path can drain an island cut off by a downstream disconnect. The detached path must be designed and measured on the detached side of that disconnect; 1 MΩ is merely a sensitivity case.

## Fault and operating-state disposition

| State or fault | Circuit-level disposition before qualification |
| --- | --- |
| One VB branch resistor open or one independent contact stuck open | The two-contact concept retains one candidate path in the ideal model. Detect which path failed, inhibit restart, and keep service access locked until independent voltage measurement; the 58.258 s illustrative value does not waive detection or thermal checks. |
| One shared control/hold fault, welded supply, contact bounce, or coil unable to release after AUX loss | Two contacts can remain open together. The slow Rev38 paths are not accepted fast paths. Require a release-under-AUX-loss/brownout test and an independent fault response; do not claim single-fault fast decay for a common-mode fault. |
| Mains attached or AC isolation unverified | **No RC deadline is asserted.** The input/bridge/boost-diode path can replenish VD, and an intact F2 can pass replenishment to VB. At a hypothetically held 450 V, both fast branches draw 54.545 W / 0.12121 A at −1% R; a surviving branch draws 27.273 W / 0.06061 A. Prove source isolation for a timed decay, or rate the engaged resistor/contact assembly for source-held continuous duty and keep access blocked. F2 open can separate the VB recharge route but does not establish mains isolation of VD. |
| F2 opens charged, including off-board holder/cable fault | VD, VB and any detached inverter C each need their own path and observation. Do not bridge VD to VB through the discharge module, measurement cable or F2 board connector. The off-board F2 holder and two-potential terminal are separate from discharge connections. |
| One sense path opens, sense power disappears, VD=VB while charged, or residual reading is stale | Absolute VD-to-HOT0 and VB-to-HOT0 readings are unknown, even if the F2 differential detector reports equality. Inhibit rearm and service release. A detached inverter island needs its own reading or an approved isolated measurement procedure. |
| Inverter bridge short at VB | F2 is upstream of the bank and is not a VB-bank disconnect. Coordinate bank-to-inverter fault interruption and discharge separately with the inverter and Rev38 owners. |

## Minimum interface before a schematic

1. Separate voltage-rated VD/HOT0 and VB/HOT0 discharge connections on the proper sides of F2, with independent branch conductors/contacts where the one-open claim matters. The active F2 Phoenix two-potential terminal carries **VD-out and VB-return for the fuse only**; it supplies neither a HOT0 return nor a discharge or sense port. Select connector/cable, creepage, strain relief, fault current and fuse coordination against the frozen envelope.
2. Define an NC drive whose **physical** de-energized state engages the fast path after loss of its control supply, with bounded loaded release time and no automatic re-energization during repeated brownout. Independent contacts sharing a stuck-energized hold control do not provide independent fault coverage. Select exact DC contact life and pulse/current ratings for the actual opening waveform and source-held condition.
3. Provide independent absolute VD, VB, and any detached-node observation referenced to HOT0, with powered-off measurement or a controlled service procedure. Keep HOT0 hazardous and the SELV interface isolated. Treat open sense, absent supply, failed contact proof or F2 continuity unknown as **unknown charged state**, requiring lockout and deliberate rearm only after a validated discharge/measurement sequence.
4. Record the adopted maximum initial and fault VD/VB voltages, node-specific target voltage/time and start event, access class, exact inverter direct/detached capacitance and switch position, one-fault policy, and test method. Then size resistance and series element count at tolerance/aging extremes; verify steady mains-held and pulse energy with actual installed chassis/fan-off thermal data. The legacy 34 V/60 s figure cannot be promoted by this arithmetic.

The design-freeze blockers remain: adopted criterion and authority; final Rev38 voltage/source/F2 fault envelope and terminal assembly; exact inverter capacitor/disconnect/short topology; selected resistor/contact/coil data; independent powered-off observations; assembled fan-off thermal and fault/restart tests. These inputs, not an extra calculation run, permit a candidate schematic. Product PCB construction and hardware qualification remain open.

## Replay

Run from the repository root:

```sh
shasum -a 256 -c zapote/discharge/evidence/source-inputs.sha256
rustfmt --check zapote/discharge/evidence/next-topology-2026-09-23/topology_screen.rs
rustc --edition=2021 --test zapote/discharge/evidence/next-topology-2026-09-23/topology_screen.rs -o /tmp/zapote-discharge-next-tests
/tmp/zapote-discharge-next-tests
rustc --edition=2021 zapote/discharge/evidence/next-topology-2026-09-23/topology_screen.rs -o /tmp/zapote-discharge-next-screen
/tmp/zapote-discharge-next-screen > /tmp/zapote-discharge-next-output.csv
cmp /tmp/zapote-discharge-next-output.csv zapote/discharge/evidence/next-topology-2026-09-23/topology-output.csv
```

This independent screen extends the earlier [`discharge_screen.rs`](../discharge_screen.rs) and [`qualification.rs`](../qualification.rs) sensitivity and evidence gate; it does not replace their source-locked validation or change their physical-qualification verdict. Five focused tests cover the old common-contact cut, the one-contact survivor, common hold failure, detached island, and refusal to claim mains-live RC completion. The saved output has 30 data rows covering 2 scenarios × 3 candidates × 5 faults, and no product PASS column.
