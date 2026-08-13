<!-- provenance: commit=c47761757de8f62dc307c3bb79d1180ebe412ef3 dirty=false (worktree analysis/f1-fault-protection, base origin/main at fetch time). pcb/** was opened read-only: temper.kicad_pcb was grepped for the F1 footprint stub (lines 3769-3782) and never written. No netlist, netclass, or source value was changed by this document. `which ngspice` returns nothing in this environment (exit 1) -- consistent with docs/evidence/2026-08-12-hv-hv-creepage-determination.md's same finding -- so no SPICE run was attempted; simulation/harness/nets/zvs_margin_sweep.cir was read instead of run (Sec 4.3) and does not model this fault regardless. All circuit topology below is read directly from elec/src/main.ato and elec/src/modules.ato at the commit above; no value in this document is inherited unread from a prior evidence file -- where a prior document's figure is reused (the 570.5 Vrms working voltage, the 88uH/0.1ohm coil, the 3600uF/170V bus bank) the source is cited at the point of use. -->

# F1 cannot discharge the clause-19 obligation, because the fault current the obligation is about never reaches it. The tank-to-bus short is fed and returned entirely by the local DC bus capacitor bank; F1 sits upstream of the rectifier bridge that bank hangs off of, and is not electrically part of that loop. The clause-19 route is not merely uncharacterised — for this fault, it is unavailable.

**Verdict, up front.**

1. **What F1 is.** Schurter `0034.3129`: a bare 5×20 mm fuse **link**, 16 A / 250 V, **time-lag (slow-blow)**, part of Schurter's FST family (`docs/hardware/BOM.md:44`, `elec/src/modules.ato:657-664`). Its holder is a *separate* part, Schurter FUP `0031.2510` (`docs/hardware/BOM.md:45,77`). **No datasheet for either part is checked into this repository** — `datasheets/` holds only the IGBT and gate-driver datasheets (`datasheets/infineon-ikw40n120h3-datasheet-en.pdf`, `components/UCC21550/datasheet.pdf`); nothing for `0034.3129` or `0031.2510`. No I²t figure, no time-current curve, no breaking-capacity figure is recorded anywhere in this repo for F1. `elec/src/modules.ato:665-673` and `docs/hardware/BOM.md:79` both flag this as an open, unresolved question, and `docs/hardware/PART_STRESS_AUDIT.md:202-207` reconfirms it unchanged. **I have not substituted a figure from memory; this section reports an absence, not a number.**

2. **F1 is not in the fault loop.** Tracing the schematic net-by-net (Sec 2): the short is between `tank.c_tank1-p2` and a DC bus rail (`+170V_BUS` or `DC_BUS_RTN`), both of which are terminals of the **local bus capacitor bank** — `c_bus1`+`c_bus1b` (3600 µF, bridging `+170V_BUS`↔`PWR_RTN`) or `c_bus2`+`c_bus2b` (3600 µF, bridging `PWR_RTN`↔`DC_BUS_RTN` via OCP-02's unplaced CT splice). F1 sits on `ac_l`, in series *before* the CMC, the inrush NTC, the bypass relay, and rectifier diodes D1/D2 (`elec/src/modules.ato:857-867`) — i.e. upstream of the entire doubler and every bus capacitor. The short-circuit loop closes entirely through the local capacitor bank, the coil, and `CT1`'s primary, and never passes through the rectifier diodes, the CMC, or F1. **This holds for both fault paths the prior determination identified** (Sec 5.1 of `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`): Path 1 (through the coil/CT1) and Path 2 (through the tank caps into the half-bridge) both terminate on locally-stored DC-side energy, not on the AC mains.

3. **Whether F1 could clear it in time is therefore the wrong question for this fault.** There is no current through F1 to clear. I do not compute an I²t margin for a path that does not exist. Sec 3 makes the topological case explicit and gives a labelled hand estimate of what the local loop *does* deliver, to show the scale of what F1 is excused from handling.

4. **The stub footprint is real, and independently confirmed.** `pcb/temper.kicad_pcb:3769-3782` (read-only) is a `(generator stub)` 2-pin THT footprint, 22.5 mm pin pitch, explicitly commented `"Stub for Schurter 0034.3128 fuse holder."` (note: even the stub's own comment cites the *link* MPN `0034.3128`, not the *holder* `0031.2510`, nor the correct link `0034.3129` — three different part numbers now associated with F1 across BOM/comment/footprint). This does not match the FUP `0031.2510`'s real ~30.48 mm, 3-pin (2 electrical + 1 orientation) drilling diagram per `docs/hardware/BOM.md:77`. Confirmed independently in this session, not just cited: I opened the PCB file and measured the stub's own pad geometry. **A fuse that cannot yet be fitted to the board protects nothing — but this is now the second-order problem.** Even a correctly drawn F1 footprint would not put F1 in this fault's current path.

5. **Net effect on the clause-19 route.** Clause 19.11.2 ends a fault-condition test on "a non-self-resetting interruption of the supply … within the appliance." F1 is one candidate for that interruption; it is not the only one in principle, but it is the only fuse in this design (verified: `Fuse` is instantiated exactly once, `elec/src/modules.ato:34,657`; no second fuse exists anywhere in `elec/src/*.ato`). Given F1 is outside the loop, and every other device that could interrupt AC-side supply (the bypass relay, the NTC, D1/D2) is *also* upstream of the local capacitor bank and therefore equally outside the loop, **nothing on this board interrupts the tank↔bus short once it starts.** The fault runs until the local capacitor bank is depleted or something fails uncontrolled (PCB copper, the coil, CT1, or the tank caps themselves) — which is precisely the flames/molten-metal condition clause 19.13 exists to rule out, and precisely the condition no protective device here is positioned to prevent. That is a stronger, and worse, finding than "uncharacterised": there is no candidate mechanism to characterise.

---

## 1. Scope and what this document does not do

This document determines whether F1 can serve as the clause-19 fault-termination
device for the short-circuit-of-functional-insulation fault that
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` §5 established is
owed under IEC 60335-1 clause 19.11.2(a) (creepage below the clause-29 figure
makes the short-circuit fault condition mandatory; acceptance is judged by
clause 19.13's fire criteria). It does not re-derive the creepage shortfall,
the 570.5 Vrms working voltage, or the clause-29/29.2.4 analysis — all of that
is carried forward from that document, cited at each point of use, and not
re-verified here. It changes no value in `elec/src/**` or `pcb/**`.

## 2. Circuit topology, traced net-by-net

### 2.1 What F1 is in series with

`elec/src/modules.ato:857-867`, verbatim connection order:

```
ac_l ~ fuse.p1
fuse.p2 ~ mov.p1              # MOV, parallel across L-N, after fuse
fuse.p2 ~ c_x2.p1             # X2 EMI cap, parallel across L-N, after fuse
fuse.p2 ~ cmc.W1_1            # L path into the common-mode choke
cmc.W1_2 ~ ntc.p1
ntc.p2 ~ d1.A
cmc.W1_2 ~ bypass_relay.COM
bypass_relay.NO ~ d1.A
```

F1 is the very first component the incoming line conductor (`ac_l`) meets.
Everything downstream of it — MOV, X2 cap, common-mode choke, inrush NTC,
bypass relay, and the two doubler diodes (`d1`, `d2`) — sits *between* F1 and
the DC bus. This chain is confirmed independently by the PCB stub footprint
itself (`pcb/temper.kicad_pcb:3778-3780`): F1's two pads carry nets `ac_l` and
`w1_1` (the CMC's first winding terminal), matching the source exactly.

### 2.2 What the DC bus rails are terminals of

`elec/src/modules.ato:793-830` (the `PowerInput` module's connections),
verbatim for the bus capacitor wiring:

```
d1.K ~ dc_bus.hv_plus
c_bus1.plus ~ dc_bus.hv_plus
c_bus1.minus ~ dc_bus.gnd_ref
c_bus1b.plus ~ dc_bus.hv_plus
c_bus1b.minus ~ dc_bus.gnd_ref
...
d2.K ~ d1.A
d2.A ~ dc_bus.hv_minus
c_bus2.plus ~ dc_bus.gnd_ref
c_bus2.minus ~ dc_bus.hv_minus
c_bus2b.plus ~ dc_bus.gnd_ref
c_bus2b.minus ~ dc_bus.hv_minus
```

`c_bus1`/`c_bus1b` are two 1800 µF, 250 V-rated snap-in electrolytics
(Chemi-Con `EKMQ251VSN182MA50S`, `elec/src/modules.ato:794-802`), 3600 µF
combined, wired **directly** across `dc_bus.hv_plus` (→ `+170V_BUS`,
`elec/src/main.ato:520,682`) and `dc_bus.gnd_ref` (→ `PWR_RTN`, the doubler
midpoint, `elec/src/main.ato:527-528,688`). `c_bus2`/`c_bus2b` are the same
part, same total capacitance, wired across `dc_bus.gnd_ref` and
`dc_bus.hv_minus` (→ `DC_BUS_RTN` via OCP-02's series CT splice,
`elec/src/main.ato:794-795`, `elec/src/modules.ato:2615-2622`). No resistor,
inductor, or other series element sits between either capacitor pair and its
two bus terminals within `PowerInput` — the caps *are* the bus rail at that
node, locally.

### 2.3 The tank node and its return path

`elec/src/main.ato:816-824`:

```
hb.switch_node ~ tank.in                      # SW_NODE
tank.out ~ ct_sense.primary_in
ct_sense.primary_out ~ power_return           # tank return, THROUGH CT1's primary, to PWR_RTN
```

and `elec/src/modules.ato:551-557` (carried forward from
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` Sec 5.1, re-verified
here against the same lines):

```
SW_NODE ── 3×100nF (c_tank1‖c_tank2‖c_tank3) ── tank.c_tank1-p2 ── L 88uH (inductor_conn, DCR 0.1ohm) ── tank-out ── CT1 primary ── PWR_RTN
```

### 2.4 The loop the short actually closes

A short from `tank.c_tank1-p2` to `+170V_BUS` closes this loop:

```
+170V_BUS (dc_bus.hv_plus)
  → [short]
  → tank.c_tank1-p2
  → L 88uH (inductor_conn, DCR 0.1ohm)
  → tank.out
  → CT1 primary (ct_sense)
  → PWR_RTN (dc_bus.gnd_ref)
  → c_bus1 + c_bus1b (3600uF @ 170V)  [closes back to +170V_BUS]
```

A short to `DC_BUS_RTN` instead closes the mirror-image loop through
`c_bus2`/`c_bus2b` and OCP-02's (unplaced) series CT splice
(`elec/src/modules.ato:2610-2622`). Either way, **the loop is a local RLC
circuit consisting of a bus capacitor pair, the tank coil, and the CT1
primary winding. It does not include the rectifier diodes D1/D2, the CMC, the
inrush NTC, the bypass relay, or F1** — every one of which sits between the
AC input and these same bus capacitors, not between the bus capacitors and
the short. **F1 is topologically excluded from this loop.** This is the
central finding of this document: it is read directly off the net
connectivity above, not inferred.

This also holds for the second fault path the prior determination named
(`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` Sec 5.1, "Path
2" — through the 300 nF tank caps into whichever IGBT is conducting, dumping
½CV² ≈ 17 mJ per switching edge into the half-bridge). That loop is local to
the switch node and the tank caps and never reaches the bus capacitor
terminals at all, let alone F1.

### 2.5 A qualification to the prior determination's Sec 5.2

`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` Sec 5.2 states:
*"The fault current continues, sourced by the bus capacitors and then by the
mains through the rectifier, until something opens the circuit. What opens it
is F1…"* The first half of that sentence is consistent with what Sec 2.4
above establishes: the fault is indeed sourced by the bus capacitors. But the
conclusion does not follow from the topology. **Mains recharging the sagged
bus through D1/D2 is a real, separate, secondary current, and *that* current
would pass through F1 — but it is not the fault current clause 19.11.2(a)/
19.13 is judging.** The acute event — the energy release described in Sec 3
below, delivered by the already-charged local capacitor bank — completes
before any mains-side response could matter (Sec 3.2), and happens entirely
without F1 in the circuit. F1 opening later, on the slower secondary
recharge current, would only stop the appliance from continuing to draw mains
power into a circuit that has already released its local energy — a
different, later, lesser protective function than the one clause 19.13 is
testing. I am revising the prior document's Sec 5.2 conclusion on this point;
its Sec 5.2 items 1-3 (F1's uncharacterised I²t, the stub footprint, OCP-02's
absence from the board) remain accurate as *separate* facts, just not as
support for "F1 terminates this fault."

---

## 3. Scale of the local event, and why F1's rating is irrelevant to it

**Everything in this section is DERIVED BY HAND, labelled as such. No
simulation was run and none exists that models this fault** (Sec 4). It is
offered only to show the order of magnitude of what F1 is excused from
handling, not as a certified fault-current figure.

### 3.1 Available local energy

The relevant bus capacitor pair is 3600 µF at 170 V
(`v_bus_half: voltage = 170V`, `elec/src/modules.ato:815`; capacitance from
Sec 2.2). Stored energy:

E = ½CV² = ½ × 3600×10⁻⁶ F × (170 V)² ≈ **52 J**

For scale: this is ~3,000× the ½CV² ≈ 17 mJ per switching edge the prior
document computed for Path 2's tank-cap discharge, and it is available in a
single event, not spread over switching edges.

### 3.2 Timescale and peak-current bound

Treating the loop as an undamped series LC circuit (L = 88 µH, C = 3600 µF,
ignoring all resistance — an explicit simplification, not a measured
result):

- Natural period: T = 2π√(LC) = 2π√(88×10⁻⁶ × 3600×10⁻⁶) ≈ **3.5 ms**
- Characteristic impedance: Z₀ = √(L/C) = √(88×10⁻⁶ / 3600×10⁻⁶) ≈ **0.156 Ω**
- Undamped peak current bound: I_pk ≈ V/Z₀ = 170 V / 0.156 Ω ≈ **1.1 kA**,
  reached at t ≈ T/4 ≈ **~880 µs** after the short occurs.

**This is an upper bound, not a prediction.** The real loop has resistance
this repo does not fully specify: the coil's DCR is given (0.1 Ω,
`inductor_conn.dcr = 0.1ohm`, `elec/src/modules.ato:551`), but CT1's primary
winding resistance, the bus capacitors' ESR, and the PCB copper resistance of
this loop are not recorded anywhere I found. Z₀ ≈ 0.156 Ω is low enough that
plausible total loop resistance (order 0.1-0.3 Ω) would move the circuit from
underdamped toward critically damped, which would lower the peak current
below the 1.1 kA bound and could stretch or compress the ~880 µs figure. **I
am not asserting a specific damped peak current** — the missing resistances
make that a real gap, named rather than papered over.

What survives the uncertainty: whatever the damped peak current is, it is
delivered on a timescale set by √(LC) ≈ 0.56 ms (Sec 3.2's period divided by
2π) for as long as the loop resistance stays well below 2·Z₀ ≈ 0.31 Ω — a
condition the known 0.1 Ω coil DCR alone does not violate, and only
additional series resistance beyond what this repo documents could push
toward. This is a sub-tens-of-milliseconds local event either way, and F1,
being outside the loop entirely (Sec 2.4), is not exposed to any part of it
regardless of exactly how damped it is.

### 3.3 Comparison to F1's rating, for scale only

F1 is rated 16 A continuous, time-lag (slow-blow) — a fuse family deliberately
designed to tolerate multi-second inrush without opening. Even the low end of
plausible damped peak currents here (hundreds of amps) is one to two orders
of magnitude above F1's rated current, delivered in under a few milliseconds
— a timescale at which a 16 A time-lag link would not even begin to open under
normal I²t behaviour for this class of part. **This comparison is offered
only to underline that F1's slow-blow characteristic would be irrelevant even
if it were in the loop; it is not a computed I²t margin, and I have not
invented one, because no I²t curve for `0034.3129` exists in this repo (Sec
0/Verdict item 1).** The comparison is moot regardless, because F1 is not in
the loop (Sec 2.4).

---

## 4. What was checked and found absent

### 4.1 F1 datasheet / I²t figure

Searched `datasheets/`, `docs/hardware/BOM.md`, and `elec/src/**` for any
Schurter `0034.3129` or `0031.2510` datasheet, time-current curve, or I²t
figure. None exists. `elec/src/modules.ato:665-673`, `docs/hardware/BOM.md:79`,
and `docs/hardware/PART_STRESS_AUDIT.md:202-207` all independently record this
as an open, unresolved question — three separate documents, written on
different dates, agreeing it has never been closed.

### 4.2 A second fuse or breaker

Searched `elec/src/*.ato` for any other `Fuse` instantiation or equivalent
protective disconnect device. `Fuse` is imported once
(`elec/src/modules.ato:34`) and instantiated exactly once
(`elec/src/modules.ato:657`, designator `F1`). `docs/hardware/BOM.md:547`
records a separate part, `FUSE1` — a **thermal** fuse (NEC/Schott `SF152E`,
157°C, 15A, 250V) — but that is a temperature-triggered disconnect for
overheat protection, not a current-sensing device in this loop, and it is not
wired into `elec/src/*.ato` at all (it is a chassis/mechanical BOM line per
`docs/hardware/BOM.md:571`, same treatment as the heatsink). No current-rated
protective device other than F1 exists in the design, and F1 is outside the
fault loop (Sec 2.4).

### 4.3 A SPICE deck that could settle this

`ngspice` is **not installed in this environment** (`which ngspice` returns
nothing, exit code 1) — the same absence
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md`'s provenance header
records. No run was attempted for that reason. Independently of tool
availability, I read `simulation/harness/nets/zvs_margin_sweep.cir` (the deck
`docs/brainstorms/2026-07-25-spice-harness-zvs-sweep-requirements.md`
specifies) and it would not answer this question even if run: its own header
(lines 44-64) states the bus rails are modelled as **ideal ±170 V DC
sources** (`V_HVP`/`V_HVN`), not as finite capacitor banks, and it contains no
fault-injection element (no short, no switch modelling a creepage breakdown).
An ideal voltage source cannot sag under fault load and cannot represent the
finite-energy capacitor discharge Sec 3 depends on; this deck answers ZVS
switching-margin questions, not clause-19 fault-current questions. No other
`.cir` file under `simulation/harness/nets/` (`ocp01_trip_point.cir`,
`ocp02_option_a_*.cir`, `ovp01_trip_point.cir`, `thm01/02_trip_point.cir`,
`uvl02_*.cir`) models a 19.11.2 fault injection either — the same absence
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` Sec 5.3 already
recorded, reconfirmed here by directory listing.

### 4.4 The stub footprint, checked directly

`pcb/temper.kicad_pcb:3769-3782` (read-only; not modified by this session):

```
(footprint "Fuse:Fuse_Holder_5x20mm" ... (generator stub) ...
  (descr "Stub for Schurter 0034.3128 fuse holder.")
  (property "Reference" "F1")
  (pad "1" thru_hole circle (at 0 0) ... (net 29 "ac_l"))
  (pad "2" thru_hole circle (at 22.5 0) ... (net 158 "w1_1")))
```

Confirmed: 2-pin, 22.5 mm pitch, generator stub — matching
`docs/hardware/BOM.md:77`'s description exactly, and independently verified
by opening the file rather than trusting the BOM's characterisation of it.
The pad nets (`ac_l`, `w1_1`) also independently confirm the Sec 2.1 topology
trace: F1's real board position is the CMC input, nowhere near the bus
capacitors. The stub's own description string names `0034.3128` — a fourth,
still different part number from the BOM's `0034.3129` (link) and `0031.2510`
(holder), a minor additional documentation inconsistency noted for
completeness, not a safety-relevant one on its own.

---

## 5. Determination

**F1 cannot discharge the clause-19 obligation for this fault, because F1 is
not in the fault's current path.** The short between `tank.c_tank1-p2` and
either DC bus rail draws its energy from, and returns it to, the local bus
capacitor bank (3600 µF at 170 V per half-bus) through the tank coil and
CT1's primary — a loop that closes entirely on the DC side of the doubler.
F1 sits on the AC line, upstream of the doubler diodes, the CMC, the inrush
NTC, and the bypass relay, none of which are in this loop either. **No
component on this board is positioned to interrupt this fault once it
starts.**

This means the three sub-questions in the task collapse:

- **What F1 is:** established (Sec 0 item 1) — Schurter `0034.3129`, 16 A/250 V
  time-lag fuse link, no datasheet or I²t figure in-repo.
- **Whether the fault current passes through F1:** **no** (Sec 2.4), for
  either fault path identified in the prior determination.
- **Whether F1 could clear it in time:** **not applicable** — there is no
  current through F1 to clear. I have not computed a margin because there is
  no path for the question to apply to.
- **The stub footprint:** confirmed genuinely unfinished by direct inspection
  (Sec 4.4), and now a secondary issue: fixing it would not put F1 in this
  fault's path.

**The clause-19 route, as a way of closing the 3.2×-5.0× creepage shortfall
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` established, is not
viable on this board as designed.** Not because nobody has run the clause-19
test (true, but secondary) — because the device the route's happy-ending
narrative depended on to end the test is wired somewhere the fault current
never reaches. A clause-19 fault-injection test run on this board today would
have no on-board mechanism to produce the "non-self-resetting interruption of
the supply" that ends the test; it would run until the local capacitor bank's
energy is spent through whatever happens to fail first in the tank/coil/CT1
loop — the flames-and-molten-metal outcome clause 19.13 exists to rule out,
untested and unmitigated by anything currently on the board.

---

## 6. What a reviewer must still check

Ordered by what would most change this answer.

1. **Confirm the net-connectivity trace in Sec 2 against the compiled
   netlist**, not just the `.ato` source. This document reads
   `elec/src/main.ato` and `elec/src/modules.ato` directly; it does not
   re-run `atopile build` or diff against `elec/build/default.net`. If the
   compiled netlist disagrees with the source read here, that is a build
   discrepancy this document does not have the tooling access to catch.
2. **A real fault-injection SPICE deck**, once ngspice is available in some
   environment, modelling the bus as finite capacitance (not the ZVS deck's
   ideal sources) with a switch representing the creepage breakdown, to
   replace Sec 3's hand bounds with a damped, resistance-inclusive result.
   The missing inputs are CT1 primary winding resistance, bus capacitor ESR,
   and this loop's PCB trace resistance — none recorded in this repo.
3. **Whether any device *should* be added to interrupt this loop**, since
   none exists today. That is a design decision, not something this
   determination makes. Candidates would need to sit inside the DC bus
   loop itself (e.g., a fast fuse or breaker in series with the bus
   capacitor bank, or fast-acting tank-side protection) rather than on the
   AC mains line, because the AC mains line is demonstrably the wrong place
   for this specific fault.
4. **F1's actual datasheet**, to close the still-open question of whether
   F1 is even adequately rated for its *intended* job (mains overcurrent /
   inrush coordination with `NTC_INRUSH` and `K_BYPASS`) — a real, separate,
   still-open question this document does not resolve, only reconfirms as
   open (Sec 4.1).
5. **The other route(s) to closing the creepage shortfall** — geometry
   (distance/slot) or a qualified conformal coating to PD1 (a parallel
   analysis's subject, per the task's framing) — since this document's
   finding removes the clause-19 route from consideration, not the
   shortfall itself.
