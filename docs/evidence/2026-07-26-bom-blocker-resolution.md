# BOM Blocker Resolution — 3 Confirmed Procurement Blockers

**Date:** 2026-07-26. **Scope:** resolves the 3 blockers found in `docs/evidence/2026-07-26-bom-availability-sweep.md` against `docs/hardware/BOM.md` rev 1.5 and `elec/src/*.ato`. **Method:** direct distributor/manufacturer page fetches and directly-read PDF datasheets (DigiKey, Schurter, EPCOS/TDK, KEMET), cross-checked against `elec/src/modules.ato`/`components.ato`, `elec/src/constraints.ato`, and `pcb/temper.kicad_pcb`. No component was drawn (footprints) — only described.

**`ato build` could not be run in this environment** — it fails on this checkout with `atopile.address.AddressError: Cannot add instance to something without an entry section` regardless of edits (reproduced on a clean, unmodified checkout too, both with the installed `ato` 0.2.69 and with `ato` pinned to 0.2.68 via `uv tool run`). This is a pre-existing toolchain issue, unrelated to this change. Instance-count reconciliation below was therefore done by static analysis of the instantiation graph (every `main.ato` module instantiation traced by hand), not by generating `elec/build/default.net`.

---

## Blocker 1 — `GRM188R71E104KA01D` (100nF/0603/X7R decoupling, Obsolete)

### True instance count: 16, not 22

`elec/build/default.net` does not exist in this checkout (gitignored, never built, and `ato build` is broken here — see above), so the "22 instances" figure from the sweep could not be reproduced from a netlist. Reconciling against source instead:

Every top-level module in `main.ato` (`PowerInput`, `BusDischarge`, `PowerManagement`→`BuckConverter3V3`, `AuxSupply`, `HalfBridge`, `ResonantTank`, `CurrentSensing`, `RTDSensing`, `SafetyInterlock`→`OCPComparator`/`OVPComparator`/`ThermalComparator`/`Watchdog`, `MCU`, `ThermalSystem`) is instantiated **exactly once** — grep for `= new HalfBridge`, `= new AuxSupply`, `= new RTDSensing`, etc. across `main.ato`/`modules.ato` confirms no module with a `GRM188R71E104KA01D` instance is instantiated more than once. Counting literal `.mpn = "GRM188R71E104KA01D"` assignments in `elec/src/modules.ato` (pre-fix) gives exactly **16**, matching the BOM's own §10.1-style per-instance count and the sweep's "16 refs" figure:

| Instance | Module | BOM ref/section |
|---|---|---|
| `c_vcci1`, `c_vdda`, `c_vddb` | `HalfBridge` | §1.1 (3) |
| `c_boot`, `c_out_hf` | `BuckConverter3V3` | §2.1 (2) |
| `c_out_hf` | `AuxSupply` | §2.3 (1) |
| `c_vcc1` | `MCU` | §3.1 (1) |
| `c_vdd`, `c_reference`, `c_low_window`, `c_high_window`, `c_window_and`, `c_rail_monitor`, `c_fault_nand` | `RTDSensing` | §4.1 `C_DEC_RTD` (7) |
| `c_bypass` | `Watchdog` | §5.3 `C_WDT` (1) |
| `c_adc_filter` | `OVPComparator` | §5.6 `C_OVP_ADC` (1) |

**16 total.** The sweep's "22 instances" figure is not reproducible from source and is most likely a netlist-format artifact (e.g. a raw netlist commonly repeats a part's value/MPN string across multiple sections — `components`, `libparts`, per-pin `nets` entries — so a naive `grep -c` over a `.net` file can overcount actual physical instances). **Verdict: 16 is the correct instance count.** Treat "22" as an unverified/likely-erroneous figure from the prior sweep, not a discrepancy this pass left open.

### Falsifier

*Stated before searching:* "If no 100nF/0603/X7R/≥25V part can be found that is both (a) listed Active with non-zero stock on a distributor page I directly fetch, and (b) available in the exact 0603 case size already used in every instance, Blocker 1 is not resolved and must be reported UNVERIFIED."

**Falsifier did not fire.** Found `C0603C104K5RACTU` (KEMET): direct DigiKey fetch (`digikey.com/en/products/detail/kemet/C0603C104K5RACTU/1465594`, 2026-07-26) shows **Active**, **6,707,514 units in stock**, 100nF ±10% X7R 50V, 0603 (1608 Metric) — same case size as every existing instance. (An intermediate candidate, Yageo `CC0603KRX7R9BB104`, was checked first and rejected: Active but **0 units in stock** at DigiKey at check time — falsifier fired for that candidate specifically, which is why KEMET was selected instead.)

### Chosen replacement

`GRM188R71E104KA01D` → **`C0603C104K5RACTU`** (KEMET, 100nF ±10% X7R 50V, 0603) in all 16 instances, `elec/src/modules.ato`. 50V was chosen over matching the original 25V rating specifically to improve DC-bias headroom on the three 15V-rail instances (below) — since one universal part is already this codebase's existing pattern (all 16 instances shared one MPN despite different `voltage_rating` annotations of 10V/16V/25V), a single higher-voltage replacement is a strict superset and keeps that pattern.

### DC-bias derating flag (new finding, not previously assessed)

Three of the sixteen instances decouple a **15V rail** and were declared at `voltage_rating = 25V` (60% of rated voltage) before this fix:

- `HalfBridge.c_vdda` — UCC21550 VDDA (high-side gate-drive supply)
- `HalfBridge.c_vddb` — UCC21550 VDDB (low-side gate-drive supply)
- `AuxSupply.c_out_hf` — isolated 15V SELV output rail

0603 X7R MLCCs are a known-bad case for DC-bias derating (thin dielectric layers required for the small case size). Industry rule-of-thumb curves put capacitance loss at roughly 40–60% of nominal near 50% of a part's rated voltage. The original 25V-rated part at 15V bias sat at 60% of rated voltage — squarely in that lossy region. The replacement's 50V rating drops the same 15V bias to **30% of rated voltage**, which should retain meaningfully more capacitance, but:

**No part-specific DC-bias curve was pulled for either the old or the new part** (KEMET's own K-SIM curve tool was not reachable in this session). This is flagged, not resolved — treat the effective capacitance on these three rails as unverified, not as "still 100nF," until a real curve or bench measurement is available. Comments recording this were added at both `HalfBridge.c_vdda`/`c_vddb` and `AuxSupply.c_out_hf` in `elec/src/modules.ato`.

The remaining 13 instances sit on 3.3V-class rails (post-buck 3.3V, RTD's `power` at 3.3V) or a low-bias bootstrap-flying-cap position (`BuckConverter3V3.c_boot`, nominal ~5V across it despite the SW node swinging to ~15V) — none of these are materially bias-stressed, old rating or new.

### Evidence

- Obsolescence: DigiKey product page `GRM188R71E104KA01D/587154` (cited by the prior sweep, re-confirmed by this pass via WebSearch — Obsolete, no restock).
- Replacement stock: DigiKey `C0603C104K5RACTU/1465594`, direct fetch 2026-07-26 — Active, 6,707,514 units, 100nF ±10% 50V X7R 0603.
- Rejected intermediate candidate: DigiKey `CC0603KRX7R9BB104/2103082` (Yageo) — Active but 0 units in stock, direct fetch 2026-07-26.
- DC-bias derating: general MLCC-industry guidance (WebSearch synthesis of multiple manufacturer app notes); **no P/N-specific curve independently verified** — UNVERIFIED numeric magnitude.

---

## Blocker 2 — `C_X2` value/MPN

### Circuit role

`PowerInput` (`elec/src/modules.ato`): `c_x2` sits directly across L–N, after the fuse and after the MOV (`fuse.p2 ~ c_x2.p1`, `c_x2.p2 ~ ac_n`), in parallel with the MOV — standard differential-mode (line-to-neutral) EMI suppression, the textbook role for an X2-class capacitor at a mains input stage, immediately upstream of the common-mode choke.

### What the circuit actually needs

The **value was already correct**: 0.22µF (220nF) is a standard X2 line-EMI capacitance for this position, and the BOM's own description ("0.22µF 20% X2 310V") matches the source's `c_x2.value = 0.22uF +/- 20%` / `c_x2.voltage_rating = 310V` exactly. Only the **MPN** was wrong — and implausible on its face, as the sweep found: Murata's DE2-series "221" suffix decodes to 220**pF** by the same convention confirmed on sibling part `DE2B3SA221KA3BT02F` (220pF, Farnell), and Murata's DE2 leaded safety-disc line tops out around 10nF — 1000× short of the 220nF this circuit needs, and outside that product family's range regardless of suffix decoding.

### Falsifier

*Stated before searching:* "If no 220nF X2 capacitor can be found whose safety-agency approvals (ENEC/UL/CQC, IEC 60384-14) I personally read from a manufacturer or distributor page — not a search-engine summary — Blocker 2 must be reported UNVERIFIED, and no MPN may be committed to source."

**Falsifier did not fire.** Found and directly read the primary manufacturer datasheet.

### Candidates considered

1. **Vishay MKP3362X2** (`BFC2336...`) — real, 310VAC, IEC 60384-14/EN132400/UL 60384-14/CQC-approved family (confirmed by directly reading Vishay's own datasheet, doc 28120). **Rejected**: datasheet header reads "Not for New Designs — Alternative Device: MKP339X2."
2. **EPCOS/TDK B32921...B32926, X2/305VAC** (specifically `B32922C3224M289`, the 15mm-pitch/0.22µF member) — **selected**. Directly read from EPCOS's own datasheet (mirrored at `media.digikey.com`, fetched successfully after the manufacturer's own domain (`tdk-electronics.tdk.com`, `product.tdk.com`) returned HTTP 403 to automated fetch in this session).

### Chosen replacement

`DE2E3KH221MA3B` → **`B32922C3224M289`** (EPCOS/TDK, 0.22µF ±20% X2, 15mm lead pitch).

**Directly read from the primary datasheet** (EPCOS "B32921 ... B32926, X2/305 VAC," dated May 2005 — the specific document mirrored by DigiKey for this series; a newer TDK-hosted revision could not be fetched in this session, see UNVERIFIED list):

- Rated AC voltage (IEC 60384-14): **305V**; maximum continuous AC voltage: **310V** — matches this design's original 310V spec exactly.
- Maximum continuous DC voltage: 760V (630V for the C/D "miniaturized" version, which `B32922C...` is).
- Approvals table (page 2 of the datasheet):
  - EN 132400, IEC 60384-14 — Certificate 40005536/40010694
  - UL 1414 / UL 1283 — Certificate E97863 / E157153
  - CSA C22.2 No.1 / No.8 — Certificate E97863/E157153 (approved by UL)
  - CQC (GB/T 14472-1998) — Certificate CQC001007-14859
- Ordering-code table (page 4): `B32922C3224M289` = 220nF, ±20% tolerance ("M"), 15mm lead spacing, ammo-pack ("289") — matches the circuit's `0.22uF +/- 20%` exactly.
- Body dimensions at this value/pitch: **7.0 × 12.5 × 18.0 mm** (w×h×l).

Stock: DigiKey product page `B32922C3224M289/2504694`, direct fetch 2026-07-26 — **Active**, **28,179 units in stock**.

### Footprint — new part required, not drawn

The existing footprint (`Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm`) matched the old, fictional disc-style part and does **not** fit the real MKP box-style replacement. A correct footprint needs: 2-pin THT radial box body, **15mm lead pitch**, body envelope **~7.0(w) × 12.5(h) × 18.0(l) mm**, 0.8mm lead diameter. Per task instructions this is described here and in an inline `elec/src/modules.ato` comment, and is **not drawn** — same open item this codebase already carries for `CT1`/`CST3015` ("footprint drawn... not yet visually confirmed").

---

## Blocker 3 — `F1` fuse holder gap

### Confirmed: `0034.3129` is a bare fuse link, and no holder exists in the design

- `elec/src/components.ato`'s `Fuse` component docstring read `"""Fuse holder with fuse"""` before this fix — false. `0034.3129` is Schurter's FST 5×20mm fuse-**link** family (confirmed by the prior sweep: real, stocked at DigiKey, $1.19).
- `pcb/temper.kicad_pcb` line ~3692 carries the footprint `Fuse:Fuse_Holder_5x20mm` with its own generator comment: `"Stub for Schurter 0034.3128 fuse holder."` — i.e., even the PCB footprint's own authoring comment conflates the *link* part number with a *holder*, and is explicitly a stub (2-pin THT, 22.5mm pad spacing) invented for placement purposes, not drawn from a real holder's mechanical drawing.
- `grep -rn "holder" elec/src/*.ato` returns nothing beyond the `Fuse` component's own now-corrected docstring. **No PCB-mount fuseholder is instantiated anywhere in the 155-component design.** This is a genuine gap, not a false positive — confirmed, not just "UNVERIFIED at the primary source" as the original sweep left it.

### Mechanical context: PCB-mount, not panel-mount

`pcb/temper.kicad_pcb`'s `F1` footprint is `attr through_hole` with 2 THT pads (2.5mm dia, 1.4mm drill) at 22.5mm spacing — a PCB-mount pattern, not a panel cutout. There is no separate panel-mount fuse-holder hardware or chassis document referencing a front-panel fuse carrier. **Conclusion: PCB-mount holder is the correct mechanical fit**, consistent with the existing footprint's mounting style (even though that stub's exact dimensions don't match any real part, as established above).

### Falsifier

*Stated before searching:* "If no 5×20mm PCB-mount fuseholder rated ≥16A can be found in stock at a distributor I directly fetch, this blocker is not resolved as a drop-in fix and must be reported as requiring either a design change (lower fuse current) or a non-standard/high-current holder family, marked UNVERIFIED."

**Falsifier did not fire, but it came close.** Nearly every commodity 5×20mm PCB fuseholder found (Schurter `0031.3501`/`0031.3571`/`0031.8001` "OG" series, etc.) is rated only **6.3–10A** — well under this circuit's 16A fuse. A 16A-rated part does exist:

### Chosen replacement (new BOM line, additive — does not replace `F1`)

**Schurter `0031.2510`** (FUP series), confirmed via Schurter's own FUP datasheet (`schurter.com/en/datasheet/typ_FUP.pdf`, directly read):

- Variants table (page 4): `0031.2510` = **5 × 20mm** fuse-link acceptance, slotted cap, IP40 — explicitly distinguished in the same table from `0031.2520` (the 6.3×32mm sibling), so the fuse-size match is unambiguous, not inferred.
- Rated current: **16A (VDE) / 30A (UL,CSA)**. Rated voltage: 250/500VAC (VDE), 600V (UL,CSA). This **meets** the circuit's 16A/250V requirement exactly at the VDE rating, with margin at the UL/CSA rating.
- Mounting: PCB, Solder THT, PC-pin terminals.
- Approvals (page 2, directly read): VDE Certificate 40045336; UL File Number E39328 (UR — Recognized Component); designed to IEC 60127-6 (fuse-holders for miniature fuse-links), UL 4248-1, CSA C22.2 no. 4248.1; suitable per **IEC 60335-1** (household electrical appliances, including the enhanced glow-wire requirements for unattended use) — directly applicable to this induction-cooker application.
- Stock: DigiKey product page `0031-2510/1522962`, direct fetch 2026-07-26 — **Active**, **83 units in stock**, 12-week manufacturer lead time.

Added to `docs/hardware/BOM.md` §1.2 as `F1_HOLDER`. **Not modeled as a separate `elec/src` component**: mechanically, a fuseholder occupies the same two electrical nodes the fuse link already does (`ac_l` and the fuse's downstream node) — it adds no new net, matching this codebase's existing convention for other mechanical-only BOM lines (heatsink, TIM pads, mounting hardware, §11). A comment describing the gap and its resolution was added at `PowerInput.fuse` in `elec/src/modules.ato` and in the `Fuse` component's docstring in `components.ato`.

### Footprint — new part required, not drawn

The existing 2-pad/22.5mm-pitch stub does not match FUP's real drilling diagram (Schurter FUP datasheet page 3: ~30.48mm primary pin spacing plus a third, smaller orientation/locating pin at an offset dimension). A correct footprint needs to be drawn from that diagram before fab. **Not drawn here**, per task instructions.

### Fuse rating sanity check — 16A/250V on an 1800W appliance

`elec/src/constraints.ato`: `ACMainsConstraints.i_max = 15A`, `v_max = 135V` ("120V + margin") — this is a **120VAC, 15A branch-circuit** design (`main.ato`: `power_max = 1800W`, and a `# 15A circuit limit` comment at the `p_output_max` assertion), consistent with a voltage-doubler topology feeding a ~340V DC bus from 120VAC input. 1800W / 120V = 15A continuous, matching the constraint exactly.

**16A fuse against 15A continuous full-load current is only ~7% headroom.** Standard practice for continuous loads is closer to 125%+ of full-load current for the fuse's continuous rating (this is itself why `0034.3129`, the 16A time-lag variant, was chosen over the 12.5A `0034.3128` sibling per the source's own 2026-07-16 comment — but 16A itself is still tight, not comfortable, headroom over 15A). This project has **no I²t/time-current coordination analysis** anywhere in the repo relating `F1` (fuse link and its time-lag curve), `NTC_INRUSH` (the `SL32 10015` inrush limiter, 10Ω cold/15A rating), and `K_BYPASS` (the relay that shorts out the NTC once the bus has charged) — i.e., no documented check that the fuse rides through the NTC-limited inrush transient without nuisance-tripping, nor that its continuous rating has adequate margin at elevated enclosure ambient (the FUP holder's own derating curve shows admissible power acceptance falling with ambient temperature, and this enclosure sits next to IGBTs/heatsink). **This is stated here as an open question per the task brief — it is not resolved or fixed in this pass.**

---

## UNVERIFIED — full list

- **Blocker 1 DC-bias derating magnitude**: no part-specific curve pulled for `C0603C104K5RACTU` (or the old `GRM188R71E104KA01D`) at 15V bias. General MLCC-industry guidance was used to flag the issue; the actual retained capacitance on `C_VDDA`/`C_VDDB`/`AuxSupply.C_OUT_HF` is not measured or curve-verified.
- **Blocker 2 approvals currency**: the EPCOS X2/305VAC datasheet directly read for `B32922C3224M289`'s approvals is dated **May 2005** (the specific document DigiKey mirrors for this series). A WebSearch-only (not independently fetched) snippet suggested a newer TDK-hosted revision carries updated certificate numbers (e.g. "ENEC-05489") for the same standards — this newer revision could not be fetched directly in this session (TDK's own domains returned HTTP 403 to automated fetch on every URL pattern tried). The approvals *standards* (IEC 60384-14, UL, CSA, CQC) are not in doubt; the *current certificate numbers* should be re-confirmed from a live TDK page before order, since certificate numbers can be reissued over a 20-year span even when the underlying approval is maintained.
- **Blocker 3 lead time**: Schurter `0031.2510` shows only 83 units at DigiKey with a 12-week manufacturer lead time — adequate for prototype/first-run quantities but worth ordering early, not confirmed against production volume needs.
- **Fuse I²t/inrush coordination**: stated as an open question in Blocker 3 above; genuinely unresolved, not merely undocumented-but-fine. No time-current curve comparison was performed in this pass.
- **New footprints** for both `C_X2` (box-style MKP, 15mm pitch) and `F1_HOLDER` (Schurter FUP drilling diagram) are described with dimensions above but **not drawn**, per task instructions. Board is not fabricable with these two positions until footprints exist and are checked in the KiCad footprint editor — same standing caveat this codebase already carries for `CT1`/`CST3015`.
- **`ato build`**: broken in this environment on an unmodified checkout (pre-existing, unrelated to this change) — instance-count claims above rest on manual static analysis of the `.ato` instantiation graph, not a generated netlist. Recommend fixing the toolchain issue separately so `elec/build/default.net` can be regenerated and cross-checked against this pass's 16-instance count and the BOM's 155-component total.
