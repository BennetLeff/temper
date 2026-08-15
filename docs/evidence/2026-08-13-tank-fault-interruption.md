<!-- provenance: commit=a3e117347b55755d5099a2f12bed4555feb9ec87 dirty=false (worktree analysis/tank-fault-interruption, base origin/main at fetch time). pcb/** was not opened for writing at any point in this session -- no `git status --porcelain` line under pcb/** exists at any commit in this branch's history. `which ngspice` returns nothing (exit 1) in this environment, consistent with every prior evidence document cited below; no SPICE run was attempted here either, and the ~1.1 kA figure carried forward in Sec 3 is repeated with its original label (undamped upper bound, not a result) and not re-derived. This document is a determination over three already-merged evidence documents plus one hardware derivation note; no `elec/src/**` or `pcb/**` value is changed by it. -->

# The obligation cannot be discharged by any change available inside this repo's current scope. Every option costs a circuit change the owner has not approved; the cheapest is a series fuse in the DC-bus loop itself, and the closest thing to "free" — closing the residual 4.87mm creepage gap — is real but does not remove the clause 19.11.2(a) obligation, only the trigger for the specific pad-pair that reopened it.

**Verdict, up front.**

1. **The obligation.** `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` establishes that the tank node's 570.5 Vrms working voltage against the bus rails requires 10.0mm creepage at PD3 (IEC 60335-1 Table 18, band >500–800V, material group IIIa/IIIb) and the board provides 2.0mm at the netclass level, which — via clause 19.11.2(a) — makes short-circuiting that gap a **mandatory** fault condition judged by clause 19.13's fire criteria (no flames, no molten metal, no ignitable gas, Table 9 temperature rises, post-cooling electric-strength test).
2. **Why it cannot be met today.** `docs/evidence/2026-08-12-f1-fault-protection.md` establishes that the fault current never reaches F1 (or any other AC-side device): the short's loop is bus-cap-bank → tank coil → CT1 primary → bus-cap-bank, entirely on the DC side of the doubler. **Nothing on the board interrupts it.** This document does not relitigate that finding; it starts from it.
3. **Four routes were enumerated and costed (Sec 1–4 below).** None is free. Route 1 (creepage geometry) is real progress but does not, by itself, close the clause — a routing-aware keepout is unbuilt tooling, not a value change. Route 2 (an interrupting device) is the only route that actually stops Path 1, and it is a genuine circuit change: a fuse or breaker in series with the bus-capacitor bank, sized against a fault current this repo has only bounded by hand. Route 3 (smaller bus bank) is real but small — at most ~17% less stored energy, already recommended and unimplemented for an unrelated reason, and does not change the qualitative finding that nothing interrupts the loop. Route 4 (test-based compliance) is procedurally available under 29.2.4/19.13 but nothing in this repository's test procedures addresses this fault at all, so it is a test design task, not evidence already in hand.
4. **OCP-01 drives the IGBT gate driver's shared `DIS` pin** (`elec/src/main.ato:898`), which forces the UCC21550's outputs off via the gate-source pulldowns on both `GateDriveHS` and `GateDriveLS` (`elec/src/modules.ato:179-182,234-239`). It does not, and structurally cannot, interrupt Path 1: the short runs `+170V_BUS → short → coil → CT1 primary → PWR_RTN → bus caps`, a loop that never touches `switch_node`, so turning the IGBTs off removes nothing from the path (Sec 2).
5. **My recommendation:** add a series fuse (or fast breaker) directly across each half-bus capacitor bank's discharge path, sized to clear before the local LC event does damage, **as a circuit change the owner must approve** — Sec 6 states exactly what and what it costs. Pursue the routing-aware creepage keepout in parallel (it's needed regardless, and it's the cheaper, more mechanical of the two real fixes), but do not present it as sufficient on its own: even a perfect 10.0mm-everywhere board still owes the clause-19 fault-condition test, whose current answer — per `docs/evidence/2026-08-12-f1-fault-protection.md` — is "nothing on this board ends it."

---

## 1. Route 1 — Remove the trigger: close the 4.87mm residual to 10.0mm everywhere

### 1.1 What's already closed

`docs/evidence/2026-08-12-tank-creepage-geometry.md` (measured on branch `fix/tank-creepage-geometry`, merged to `origin/main` at `b5e94b6f1`, PR #1109) closed both pad-level violations that existed on the committed board:

- `R30` pad 1 ↔ pad 2: **5.0000mm → 10.0000mm** (footprint pitch widened 13.0mm → 18.0mm, `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`).
- `C25` pad 2 ↔ `discharge.k_dis1-nc`: **2.2656mm → 31.3800mm** (moved by the composed CP-SAT solve: barrier + tank-creepage @10.0mm + heatsink co-location, `optimal`, 0 violations across 180 pad-pairs).

### 1.2 What routing put back — the 4.87mm pair

Per that same document (§3), the router then re-created a *new*, worse violation on the *identical electrical pair* as violation 1 — `tank.c_tank1-p2` against `R30` pad 2 (`tank-out`), 544.6 Vrms, same Table 18 row, 10.0mm required:

```
4.8668mm   Track [tank.c_tank1-p2] on F.Cu, length 83.0124mm  ↔  PTH pad 2 [tank-out] of R30
```

3mm closer than the pad pair the footprint fix had just resolved. Two more pairs also land under 10.0mm on the routed board (6.2350mm `w1_1` track vs. `C27` pad 2; 6.5525mm a stub of `tank.c_tank1-p2` vs. `C25` pad 1, `docs/evidence/2026-08-12-tank-creepage-geometry.md` §3). **All three are pad-to-routed-copper. None is pad-to-pad.** The placement constraint (`separated`, a component-box bound) provably cannot see this class of violation — it guarantees separation between footprints, not between a footprint and wherever a trace later runs. `docs/evidence/2026-08-12-tank-creepage-geometry.md:183-189`.

### 1.3 What closing it would take

The document names the fix directly: **a routing-stage creepage keepout.** `docs/evidence/2026-08-12-tank-creepage-geometry.md:202-203`: "closing them needs a routing-aware creepage keepout — the router honours netclass *clearance*, not the DRU's *creepage* rules." This does not exist anywhere in `router_v6/` today (confirmed by the same document's own scope statement, §7: "The routed board is not PD3-compliant... Closing them needs a routing-stage creepage keepout... it is not attempted here"). It is new router functionality — teach the router to keep tank-node copper 10.0mm from every other HV pad, not just other HV *footprints* — not a value or geometry edit.

### 1.4 Whether the board tolerates it

Two independent signals say margin is already gone, not merely tight, before this fix is attempted:

- **`clearance` is already over its own ceiling on the geometry-fixed board.** `docs/evidence/2026-08-12-tank-creepage-geometry.md` Sec 5, Errors table: `clearance` measures **499** against a ceiling of **386** (+113, "❌ +113 over"), and every freshly re-solved/re-routed board in this family lands at 499–503 regardless of the tank-creepage work (§5.2: "It moved with the *placement family*, not with the tank constraint"). A routing-aware creepage keepout adds a *further* constraint on top of an already-over-ceiling clearance metric.
- **Pad connectivity is already degrading.** 50/139 nets fully pad-connected on the geometry-fixed board vs. 55/139 on the prior (heatsink) board — "down 5 nets on the primary metric" (`docs/evidence/2026-08-12-tank-creepage-geometry.md` Sec 6) — attributed as a plausible-but-unablated hypothesis to R30's widened footprint making a hard 10.0mm keep-away harder to route around. A creepage-aware router constraint is the same class of pressure, applied more broadly (every HV pad-pair, not just one footprint).

**Conclusion for Route 1.** The geometry fix that could be made without a circuit-value change (footprint pitch) is already merged and did its job on pad-pad pairs. What remains — pad-to-track — needs new router capability, not a value edit, and the board's own DRC trend (clearance already 113 over ceiling, pad connectivity already declining) says the board is not obviously tolerant of another hard keep-away constraint; it might cost more unroutable nets, not just solve time. **Even a perfect fix here does not discharge the obligation** — Route 1 removes the *creepage trigger* for the 19.11.2(a) fault condition on this specific pair, but the fault condition, once triggered, is judged by clause 19.13's fire criteria applied to the *actual* fault physics (Sec 2), which Route 1 does not touch. If the creepage gap were closed to 10.0mm everywhere, the 19.11.2(a) condition itself would no longer be *owed* for this pair — but only for this pair; if any other HV↔HV net pair on the board is short of Table 18 (this document does not re-run that survey), the same clause-19 exposure exists there too.

---

## 2. Route 2 — Add an interrupting device in the actual fault loop

### 2.1 The loop, restated with citations

`docs/evidence/2026-08-12-f1-fault-protection.md` Sec 2.4, read directly from `elec/src/main.ato:816-824` and `elec/src/modules.ato:551-557,793-830`:

```
+170V_BUS (dc_bus.hv_plus)
  → [short across the 2.0mm/4.87mm creepage gap]
  → tank.c_tank1-p2
  → L 88uH (inductor_conn, DCR 0.1ohm)
  → tank.out
  → CT1 primary (ct_sense)
  → PWR_RTN (dc_bus.gnd_ref)
  → c_bus1 + c_bus1b (3600uF @ 170V)  [closes back to +170V_BUS]
```

No rectifier diode, no CMC winding, no inrush NTC, no bypass relay, and no F1 sits in this loop — all of them sit between the AC mains and the same bus capacitors, not between the bus capacitors and the short.

### 2.2 What OCP-01 actually drives, and why it cannot help here

Traced fresh in this session, not carried forward unread:

- `elec/src/main.ato:898`: `safety.shutdown.line ~ hb.gate_hs.driver.DIS`. OCP-01's fault output feeds a fault-OR aggregation (`elec/src/main.ato:3213` `ocp.fault.line ~ fault_or.A1`, further gates at :3220-3369) that latches into `safety.shutdown`, which drives `hb.gate_hs.driver.DIS` — the disable pin of the **single** UCC21550 dual-channel gate driver instantiated once in `GateDriveHS` (`elec/src/modules.ato:94`).
- **There is only one physical driver IC for the whole half-bridge.** `GateDriveLS` (`elec/src/modules.ato:209-239`) has no driver instance of its own — its input is `gate_hs.driver.OUTB` (`elec/src/modules.ato:423`: `gate_hs.driver.OUTB ~ gate_ls.input`). So `DIS` going active removes gate drive from **both** IGBTs (`OUTA` and `OUTB`) via the same event, not just the high side.
- **What `DIS` does physically:** it forces `OUTA`/`OUTB` low (or high-Z, pulled to `drive.vss` by `rgs`, `elec/src/modules.ato:165-169,181-182,223-227,237-238`), which starves both IGBT gates and stops switching at `switch_node`.
- **Why that is irrelevant to Path 1:** Path 1's loop (Sec 2.1) never passes through `switch_node`, `q_high`, or `q_low` at all. It sources and returns entirely at the DC bus rails, through the coil and CT1's primary. Turning off gate drive removes the IGBTs from conducting; it does not open, and has no electrical connection to, the short-to-coil-to-CT1-to-bus-cap loop. **OCP-01 sees this fault (its own CT, `ct_sense`, sits directly in the tank-return leg of the loop, `elec/src/main.ato:823-824`) and its fault output correctly latches — but the only actuator it drives is upstream of a bypass, not in series with the fault.** This is exactly the "fault bypasses the IGBTs" case the task anticipated.

### 2.3 CT1's role, and why it is not itself a protective element

`CT1` (`ct_sense`, `CurrentSensing` module, `elec/src/modules.ato:1606-1676`) is a current transformer: its primary is a single-turn (effectively zero-impedance, aside from winding resistance not recorded in this repo — `docs/evidence/2026-08-12-f1-fault-protection.md` §3.2) pass-through conductor, instrumented by a secondary/burden-resistor pair for *sensing*, not interruption. Being electrically in the loop is what lets OCP-01 *see* the fault at all (Sec 2.2) — it is not, and was never designed to be, a current-limiting or current-interrupting element. Nothing about its function changes this determination; it is the sensor for a comparator whose only actuator is out of path.

### 2.4 What could sit in the loop

Two structural candidate points, both requiring new hardware not on the board today:

1. **A fast fuse or breaker in series with each bus-capacitor bank**, between `c_bus1`/`c_bus1b` (or `c_bus2`/`c_bus2b`) and the `dc_bus.hv_plus`/`dc_bus.hv_minus` nodes. This is squarely `docs/evidence/2026-08-12-f1-fault-protection.md`'s own §6 item 3 recommendation: "Candidates would need to sit inside the DC bus loop itself (e.g., a fast fuse or breaker in series with the bus capacitor bank, or fast-acting tank-side protection) rather than on the AC mains line." Sizing input: the loop's own hand-derived scale (Sec 3 below) — an underdamped LC event peaking, undamped-bound, at ~1.1 kA in ~880 µs, more realistically hundreds of amps given the 0.1 Ω coil DCR alone (unknown CT1 winding resistance, cap ESR, and PCB trace resistance would only add damping, i.e., only lower this bound further). A fuse in this position would need a let-through energy low enough to satisfy 19.13, characterized against a fault current this repo has only bounded by hand — the same class of gap `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` already flagged for F1's own uncharacterised I²t (§5.2 item 1), now transplanted to a new, currently-nonexistent component.
2. **Fast tank-side protection** — e.g., a crowbar or clamp across the tank node that would divert fault energy before it can sustain the LC ring — is named as a candidate by the same source but not designed, sized, or evaluated anywhere in this repository. This is a bigger circuit change than a series fuse (an active or semi-active element, not a passive series link) and this document does not attempt to design it.

Either candidate is **a circuit change the owner must approve.** Neither exists in `elec/src/**` today; adding either changes topology, not just a value, so it is explicitly out of this determination's "implement only what is unambiguous" scope.

### 2.5 Scale of what any such device would need to survive/interrupt

Carried forward, explicitly labelled, from `docs/evidence/2026-08-12-f1-fault-protection.md` Sec 3 (hand-derived, no simulation — `ngspice` is unavailable in this environment too, confirmed again this session, `which ngspice` → exit 1):

- Stored energy per half-bus: E = ½CV² = ½ × 3600µF × 170V² ≈ **52 J**.
- Undamped series-LC model (L=88µH, C=3600µF, R=0 — an explicit simplification): natural period **T ≈ 3.5 ms**, characteristic impedance **Z₀ ≈ 0.156 Ω**, undamped peak current bound **I_pk ≈ V/Z₀ ≈ 1.1 kA at t ≈ 880 µs**. **This is an explicitly labelled upper bound, not a prediction** — real loop resistance (coil DCR 0.1 Ω known; CT1 winding resistance, cap ESR, and PCB trace resistance of this loop are not recorded anywhere in this repo) would lower it, but no committed number exists to compute the damped figure.
- Any interrupting device sized for this position needs a let-through I²t compatible with clause 19.13's fire/temperature-rise criteria on a sub-millisecond timescale — a design and characterization task, not a value already sitting in the repo.

---

## 3. Route 3 — Reduce the stored energy: is the bus bank sized by ripple, hold-up, or resonance?

### 3.1 What `elec/src/modules.ato:793-830` says, and what it doesn't

The as-built comments (`elec/src/modules.ato:798-812`) record the bank's *history* — it replaced a nonexistent 3300µF/250V part with 2×1800µF in parallel per half-bus "≥ the original 3300µF target for ripple" — but do not themselves derive a floor. The derivation exists separately.

### 3.2 `docs/hardware/BUS_CAPACITANCE_DERIVATION.md` — the answer, already worked

This document (dated 2026-07-26, present on `origin/main`, not modified by this session) derives the governing constraint from first principles and its central finding is unambiguous:

- **Not sized by resonance/ZVS margin.** §1.2: the Coss-charging timing budget for zero-voltage switching has "one to two orders of magnitude" of margin regardless of bus ripple; ripple would have to move by ~250V-scale before this became tight, and the ripple range under consideration moves ΔV by "tens of volts."
- **Not sized (in the sense of "protected") by ripple current, and reducing C does not fix ripple current.** §3, the load-bearing table: at the installed 3600µF the design already fails its rated ripple current by **4.26×**; shrinking capacitance toward zero can mathematically recover **at most ~27%** of that margin (because the dominant term is a 35kHz high-frequency component that is *structurally independent* of bulk capacitance, not the 120Hz line-frequency term that does shrink with C). At the document's own recommended 3000µF/half, the recovery is **~2.3%** (4.26×→4.16×) — "not a fix."
- **Actually sized by `BusDischarge`'s hold-up/discharge-time requirement, and that is where a real, quantified reduction is available.** §5: the <60s bus-discharge target (`elec/src/modules.ato` comments at lines 445/636/773 — an internal target that, per the same document, never made it into `FUNCTIONAL_TEST_CRITERIA.md`) is the actual ceiling on C. §5.1's new finding: the currently-installed 3600µF/half already has **no real margin** against the capacitor's own ±20% tolerance spec — worst-case tolerance (4320µF) pushes discharge to 65.4s, failing the 60s target. §5.2 solves for the largest nominal C that clears 60s at worst-case (+20%) tolerance: **≈3000µF/half** (recommendation stated in §10), or equivalently (§5.3) leave C unchanged and resize `BusDischarge`'s resistors from 9.4kΩ to ~8.6kΩ per string.

### 3.3 What that would buy for this determination

At the recommended 3000µF/half:

```
E = ½ × 3000µF × 170V² ≈ 43.35 J   (vs. 52 J today — a ~17% reduction)
```

**This is real but modest, and it does not change the qualitative finding.** A 17% smaller LC reservoir still delivers tens of joules on a sub-millisecond timescale through the same uninterrupted loop; it moves the undamped peak-current bound down by the square root of the capacitance ratio (√(3000/3600) ≈ 0.913, i.e. ~9% lower I_pk, and a correspondingly shorter T/4) — not an order of magnitude, and not a substitute for an interrupting device. It is also **not yet implemented**: `elec/src/modules.ato:793-822` still shows 4×1800µF (3600µF/half) as of this session, and `BUS_CAPACITANCE_DERIVATION.md` §6.1 flags that the specific ~1500µF/250V D35-class replacement part is **UNVERIFIED — no distributor page fetched**, and §7 flags the recommendation itself as **provisional** on a still-blocked tank-Q/power-transfer measurement (`TANK_COIL_SPECIFICATION.md`'s ~10×-wrong Q model). Reducing the bank is a legitimate, independently-justified change (it closes a real tolerance gap in `BusDischarge`, per §5.1) — but it is being recommended for a *different* reason than this fault, buys only a modest energy reduction for this fault, and carries its own open items (part sourcing, the §7 ripple-vs-power-transfer question) before it could be implemented.

**Conclusion for Route 3.** The bank is sized by hold-up/discharge-time margin, not by ripple (ripple current already fails today regardless of C, per §3 of the derivation) and not by resonance (§1.2 shows ~100× margin there). A smaller bank at a different ESR is possible and already has a from-first-principles target (3000µF/half) — but it is a ~17% energy cut, not a fix, and it is gated on its own unresolved items.

---

## 4. Route 4 — Demonstrate compliance by test: what evidence is required, and what exists

### 4.1 What clause 19.13/29.2.4 actually require, restated from the recovered primary text

Per `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` Sec 2 and 4.2, quoting IS 302-1:2008 (the recovered IEC 60335-1 primary text): the fault-condition test is run per clause 19 ("the appliance is operated under the conditions specified in 11 but supplied at rated voltage... the test is ended if a non-self-resetting interruption of the supply occurs within the appliance"), and acceptance is clause 19.13's fire criteria verbatim: *"the appliance shall not emit flames, molten metal, or poisonous or ignitable gas in hazardous amounts and temperature rises shall not exceed the values shown in Table 9... [and after cooling] shall withstand the electric strength test of 16.3."* This is a **physical test on real hardware with the functional insulation short-circuited**, not a simulation or an argument from headroom — 29.2.4's own text: "creepage distances may be reduced **if** the appliance complies with 19 with the functional insulation short-circuited. **Compliance is checked by measurement.**"

### 4.2 What this repo's test procedures actually cover

Both procedure documents named in the task were read in full this session:

- **`docs/HV_SAFETY_TEST_PROCEDURE.md`** (Status: DRAFT) covers ground-bond testing, dielectric strength (hi-pot, mains-to-SELV and DC-bus-to-SELV), and leakage/touch current. Every section is a **mains-or-DC-bus-to-SELV barrier** test. None of its four sections short-circuits functional insulation *within* the hazardous-live domain (HV↔HV), and none references clause 19 or 19.11.2 by number.
- **`docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md`** (Status: DRAFT) covers OCP verification (current injection and controlled overload up to the 50A trip point), thermal shutdown (heatsink and coil NTC), OVP verification (bus overvoltage via Variac), and watchdog timeout. These are **trip-point characterisations of the *intended* protection chain under conditions that protection chain is designed for** — none is a 19.11.2(a) fault-injection test, and none deliberately creates the tank↔bus short this determination is about. The OCP test even explicitly injects current "into the current transformer (CT) burden resistor" to simulate 50A — i.e., it tests OCP-01's trip threshold via CT1, the exact sensor Sec 2.3 above shows is *not* the problem; it does not test whether anything downstream of the trip actually interrupts a bus-side fault.

**Neither document, nor anything else found in this repository** (`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` §5.3 and `docs/evidence/2026-08-12-f1-fault-protection.md` §4.3 both independently searched `simulation/harness/nets/` and found no 19.11.2 fault-injection deck; this session's search of `docs/HV_SAFETY_TEST_PROCEDURE.md` and `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` extends that same negative result to the two named test procedures) **addresses this specific fault condition.**

### 4.3 What would be required

A genuinely new test procedure section, not an extrapolation of either existing document:

1. A defined method to short-circuit the functional insulation at the specific pair(s) below Table 18's figure (currently: the R30/tank-node pair at minimum; Route 1 may add or remove candidates depending on what a full HV↔HV survey finds), on a live unit under clause 11 operating conditions at rated voltage — per 29.2.4/19.11.2(a)'s own text, this is a deliberate short, not a passive observation.
2. Direct observation against 19.13's criteria: flames, molten metal, ignitable gas in hazardous amounts (none permitted), Table 9 temperature-rise limits (not transcribed in any evidence document in this repo — `Table 9` does not appear searched-and-quoted anywhere in the three source documents), and a post-cooling electric-strength test per clause 16.3.
3. Given `docs/evidence/2026-08-12-f1-fault-protection.md`'s finding that nothing today ends the fault (no "non-self-resetting interruption of the supply... within the appliance" occurs), a **safe test method** cannot simply run this on an unmodified unit and wait — the fault runs until the local capacitor bank's energy is spent through whatever fails first (Sec 5 of that document: "the flames-and-molten-metal outcome... untested and unmitigated"). Running this test today, on the board as it stands, is not a "pass or fail" proposition — it is closer to a controlled destructive test whose outcome this repository's own analysis (Sec 3) cannot bound tightly (hand-derived undamped bound only). Running it responsibly presupposes either an interrupting device already in place (Route 2) to make the test survivable and repeatable, or accepting the first run as a one-shot destructive characterisation.

**Conclusion for Route 4.** The test-based route is procedurally real (29.2.4 explicitly allows it) and is the only route that could, in principle, validate the *current* board without any circuit change — but it requires evidence that categorically does not exist in this repository (no procedure, no Table 9 transcription, no safe/instrumented method for a fault this repo's own analysis says nothing currently terminates), and running it safely arguably first requires Route 2's interrupting device or an accepted one-shot destructive test. It is not a cheaper alternative to a circuit change today; it is a parallel, larger undertaking (new test-procedure authorship, physical test setup, and — on the current board — an unbounded destructive-test risk) that this document can name but not discharge.

---

## 5. Summary table

| Route | What it changes | Discharges the 19.11.2(a) obligation? | Cost | Owner approval needed? |
|---|---|---|---|---|
| 1. Close creepage to 10.0mm everywhere | New router keepout capability (not a value edit); footprint-level part already merged | For the *specific pair(s)* closed, yes — removes the trigger. Any other HV↔HV pair under Table 18 remains exposed (not surveyed here). | New router feature; board already 113/386 over its `clearance` ceiling and losing pad connectivity (50/139 vs 55/139) before this constraint is even added | No circuit value changes, but is new tooling work with an uncertain routability outcome |
| 2. Interrupting device in the bus-cap↔coil↔CT1 loop | New component(s): series fuse/breaker on the bus-cap bank, or tank-side crowbar/clamp | Yes, if sized correctly — this is the only route that puts a "non-self-resetting interruption" inside the actual fault loop | New part, new footprint, sizing against a fault current only hand-bounded (~1.1kA undamped ceiling, real figure lower and uncharacterised) | **Yes — circuit topology change** |
| 3. Smaller bus bank | Capacitor value 3600µF→~3000µF/half (already recommended for an unrelated reason: `BusDischarge` tolerance margin) | No — ~17% less energy, same uninterrupted loop | Part re-sourcing (unverified MPN), gated on a separately-blocked tank-Q measurement | Yes, but independently justified regardless of this fault |
| 4. Test-based compliance | No circuit change; new test-procedure authorship + physical test | Possibly, if the physical test passes — but nothing in the repo yet supports running it safely | New test procedure (Table 9 criteria not transcribed anywhere in this repo), and running it today is closer to a one-shot destructive test absent Route 2 | No repo change, but real engineering/test effort and physical risk |

---

## 6. Recommendation

**Rank, cost, risk, reversibility:**

1. **Route 2 (interrupting device) is the only route that closes the obligation on its own terms** — it is the one candidate that puts a device *inside* the loop clause 19.11.2 actually cares about ("non-self-resetting interruption of the supply... within the appliance"). It is also the most expensive in engineering terms (new part, new footprint, a sizing exercise this repo cannot do today without either a real SPICE run — `ngspice` unavailable here — or the missing CT1-winding-resistance/cap-ESR/trace-resistance inputs `docs/evidence/2026-08-12-f1-fault-protection.md` §3.2 names) and it is **the change I would choose to pursue**, because it is the only one that is not partial: Route 1 only closes the trigger for specific pairs already found (and needs new router capability besides); Route 3 only shrinks the energy modestly; Route 4 cannot be run safely without something like Route 2 already in place.
2. **Route 1 (creepage geometry) should proceed in parallel, not instead** — it is real, mechanical, and (for the routing-aware keepout) additive to work already merged. But it should not be represented to the owner as "closing the obligation": it removes the *trigger* for pairs it reaches, not the underlying fault-loop hazard, and the board's clearance/connectivity trend says it may not be free to push further.
3. **Route 3 (smaller bus bank) should be adopted anyway, on its own justification** (`BusDischarge` tolerance margin, `docs/hardware/BUS_CAPACITANCE_DERIVATION.md` §5.1's finding that the current bank already fails worst-case-tolerance hold-up) — it is a modest win for this fault as a side effect, not a reason to pursue it for this fault specifically.
4. **Route 4 (test-based) is not a shortcut.** It requires writing a test procedure this repo has never had for this fault class, transcribing Table 9's temperature-rise limits (absent from every evidence document read for this determination), and — most materially — it cannot be run safely on the board as it stands without either accepting a one-shot destructive result or having Route 2 in place first to bound the outcome.

**If the answer is "this needs a circuit change the owner must approve" — it is:** add a fast-clearing series interrupter (fuse or breaker) in series with each half-bus capacitor bank (`c_bus1`+`c_bus1b` and `c_bus2`+`c_bus2b`, `elec/src/modules.ato:793-822`), positioned so it sits between the doubler diodes and the bus-rail nodes the tank-coil/CT1 loop closes through (`dc_bus.hv_plus` / `dc_bus.gnd_ref` / `dc_bus.hv_minus`, `elec/src/modules.ato:887-899`). **What it costs:**

- A new component (or two, one per half-bus) with its own MPN, footprint, and BOM line — none exists today.
- A sizing exercise this repo cannot complete without new inputs: CT1's primary winding resistance, the bus capacitors' ESR, and this loop's PCB trace resistance, none recorded anywhere in `elec/src/**` or the datasheets checked in (`docs/evidence/2026-08-12-f1-fault-protection.md` §3.2), plus (ideally) a real SPICE run once `ngspice` is available in some environment, replacing the hand-derived ~1.1kA undamped bound with a damped figure.
- A let-through-energy target derived against clause 19.13's Table 9 limits (also not transcribed anywhere in this repo) rather than against a generic ampere rating, since the acceptance criterion is fire/temperature-rise, not just "the fuse cleared."
- Routing and placement impact on `pcb/**` once a part is chosen — out of this determination's scope (`pcb/**` was not touched here) but real, and likely non-trivial given the board's already-strained clearance/connectivity budget (Sec 1.4).

This is a genuine circuit-topology addition, not a value tweak, and per the task's instruction ("implement only what is unambiguous") it is not implemented here.

---

## 7. What this determination does not do

- It does not change any value in `elec/src/**` or `pcb/**`.
- It does not run ngspice — unavailable in this environment (`which ngspice` → exit 1, confirmed this session), consistent with all three source evidence documents.
- It does not re-derive the 570.5 Vrms working voltage, the 2.0mm/10.0mm creepage figures, the F1 topology trace, or the ~1.1kA undamped bound — all are carried forward with citation from the three merged evidence documents and the bus-capacitance derivation note, and are repeated with their original uncertainty labels intact, not upgraded to results.
- It does not survey the whole board for other HV↔HV pairs below Table 18's figure beyond the ones `docs/evidence/2026-08-12-tank-creepage-geometry.md` already measured; Route 1's "closes the obligation" caveat in Sec 5 depends on that survey not existing yet.
- It does not design, size, or select a part for Route 2's interrupting device — it identifies where such a device would need to sit and what inputs are missing to size it.
- It does not write the clause-19 test procedure Route 4 would require.
