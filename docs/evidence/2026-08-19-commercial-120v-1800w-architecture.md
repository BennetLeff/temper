<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false
     (branch analysis/commercial-1800w-architecture, cut from origin/main).
     pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     -- verified before and after this analysis; the board file was never opened
     for writing.  NO elec/**/*.ato file was edited or read for modification.
     NO clearance, creepage, copper-weight, loop-area, ampacity or DRU threshold
     was changed; MIN_BARRIER_WIDTH_MM untouched.  power_pcb_dataset/drc_ceiling.json
     untouched and not re-baselined.  No _*_py_oracle.py touched, deleted or
     re-pinned.  No test skipped, xfailed, relaxed or allowlisted.  git stash never
     invoked.  No pushed history rewritten.  Two files are added: this document and
     its companion script, and nothing else.
     This artifact reads no repo state and loads no compiled extension, so
     `make venv-isolate` was NOT run -- stated explicitly per the task's
     environment rule. -->
---
module: power
tags: [power-input, output-rating, nameplate, iec-60335-1, topology, quasi-resonant, half-bridge, dc-link, power-factor, zvs, competitive-context, analysis-only]
problem_type: engineering-analysis
---

# Commercial 120 V / 1800 W induction cooktops: the nameplate is **rated power INPUT**, they reach unity power factor with a **4–8 µF dc link and no PFC**, and the single-hob ones are **single-switch quasi-resonant, not half-bridge**

**The hypothesis in the brief is right on the units and wrong on the mechanism,
and there is a third finding neither the brief nor the prior derivations
contain.**

1. **Input.** The 1800 W on a 120 V induction cooktop is `rated power input`
   in the IEC 60335-1 sense — real power drawn from the supply, not delivered
   pan power. Settled from the standard's own definition, from IEC TC 61's
   official measurement guidance, and from two manufacturers' spec sheets whose
   own `1800 W` and `15 A` figures are only mutually consistent under the input
   reading. `main.ato:494`'s `p_output_max: power = 1800W` is a **units error**
   against industry convention.

2. **Not PFC.** Commercial induction cooktops do **not** typically reach
   PF ≈ 1 with an active PFC stage. They reach it with a **full-bridge diode
   rectifier and a deliberately tiny dc-link capacitor** — measured at **8 µF**
   in a 1.8 kW 120 V single-hob unit and **4 µF per half-bridge** in an 8 kW
   230 V cooktop — so the bus follows the rectified line and the input current
   follows it with it. A peer-reviewed review by the field's leading group says
   this in as many words and describes PFC as *"being prospected"*, i.e. a
   research direction, not standard practice. **This design carries 1800 µF
   effective — 225× to 450× the commercial figure.**

3. **A rippling bus does not cost ZVS, and the prior derivation's FFPC argument
   is a power-regulation constraint mis-labelled as a ZVS one.** Under FHA the
   dead-time commutation charge `C_s·V_bus` and the tank current available to
   move it are *both* proportional to `V_bus`, so the commutation time is
   **invariant across a 17× bus swing** (§5.2, script §5). What actually blocks
   route 2 here is not soft switching — it is that the committed tank is scaled
   for a 340 V stiff bus and delivers only **317–321 W** from a line-following
   120 V bus at the 44 kHz floor. The obstacle is the **coil**, not the PLL.

4. **The single-hob topology at this power is not a half-bridge.** Infineon's
   own application note puts half-bridge series-resonant at *"designs with
   inverter power rating above 2.5 kW"* and multi-zone cooktops, and single-switch
   quasi-resonant at single-zone appliances *"limited to 2.2 kW"*. This project
   has built the multi-hob/high-end topology for a single-hob/1.8 kW appliance,
   and then fed it from a doubler that the topology's own reference designs do
   not use.

Reproduce the arithmetic with (pure stdlib, reads no repo state,
`make venv-isolate` **not** required):

```
python3 docs/evidence/2026-08-19-commercial-120v-1800w-architecture.py
```

**Nothing in this document changes the design.** No `.ato`, no board, no
threshold, no gate.

---

## 0. Evidence classification, stated up front

Every claim below carries one of these tags. The tag is the claim's warrant;
where a claim would need a stronger tag than the evidence supports, it is
stated as unobtainable instead.

| tag | meaning |
|---|---|
| `[standard]` | text of, or an official IEC/TC-committee document about, a published standard, retrieved this session |
| `[manufacturer]` | a manufacturer-published specification sheet or application note, retrieved this session |
| `[peer-reviewed]` | a journal or magazine paper by identified authors, retrieved this session |
| `[teardown]` | a published hardware teardown with named component values; medium strength, corroboration noted per claim |
| `[retail]` | a retailer or distributor listing; **weak**, used only to corroborate a `[manufacturer]` figure, never alone |
| `[repo]` | a value already committed in this repository |
| `[derived]` | arithmetic on the above, reproducible in the companion script |
| `[NOT OBTAINABLE]` | tried and failed; the attempt is recorded |

---

## 1. THE ANSWER TO "INPUT OR OUTPUT"

### 1.1 The standard defines it, and it is an input

IEC 60335-1 defines **`rated power input`** as *"power input assigned to the
appliance by the manufacturer"* `[standard]`, and clause 7.1 requires
appliances to be marked with the rated power input in watts. This is the same
clause family this repository already relies on: `docs/evidence/2026-07-30-c6-touch-current-budget-and-part2-routes.md`
computes the appliance's touch-current limit as
`0.75 mA/kW × 1.8 kW = 1.35 mA` from clause 13.2/16.2's *"0,75 mA per kW rated
power input"* `[repo]` `[standard]`.

**That is an internal contradiction this repository is already carrying.** The
same 1800 W figure is used as **rated power input** in the touch-current
derivation and declared as **output** in `main.ato:494`. One of the two is
wrong, and §1.2–§1.3 establish that it is `main.ato`.

### 1.2 IEC TC 61's own measurement guidance settles that it is real input power

IEC TC 61 document **61/5396A/INF, "Guidance on measurement of power input
based of the requirements of 10.1 and 10.2 of IEC 60335-1", 2017-08-01**,
retrieved in full from `assets.iec.ch` `[standard]`. Verbatim, Annex 1:

> "If the appliance is marked with rated power input rather than rated current
> it is necessary to sample both the input current and voltage. The
> instantaneous input power is then calculated from the current and voltage
> samples. The AMV of the input power is then calculated – this automatically
> takes into account reactive power when the pf is less than unity. For most
> appliances the pf will be unity or lagging close to it."

and

> "Note that for power the AMV = VrmsIrmscosƟ where cosƟ = power factor"

**Three things follow, and the third is a correction to the brief's
hypothesis:**

1. The marked figure is measured **at the supply inlet**, so it is an *input*
   quantity. Confirmed.
2. It is **real power (W)**, not apparent power (VA). The brief's hypothesis
   said *"a rated input (120 V × 15 A = 1800 VA)"*. That is not what the
   standard measures. The distinction matters (§1.4).
3. The guidance's own aside — *"For most appliances the pf will be unity or
   lagging close to it"* — is the standard-writers' baseline expectation, and
   it is the expectation this design's PF 0.60–0.76 `[repo]` violates.

**Note the direction of the error this creates.** Because the plate figure is
`V·I·cosθ` and not `V·I`, a marked 1800 W at 120 V within a 15 A branch
requires **PF = 1.000 exactly**, not merely "high". The brief's VA framing was
*more* forgiving than the standard actually is.

### 1.3 The manufacturers' own numbers are only self-consistent under the input reading

| source | figures published together | tag |
|---|---|---|
| **Vollrath 6950020**, 120 V Commercial-Series countertop induction range, manufacturer product page | `Watts: 1800` · `Volts: 120` · `Amps: 15` · `Hertz: 60` · `NEMA 5-15P` | `[manufacturer]` |
| **Vollrath 59500P** Mirage Pro, distributor spec table | `120 Volts` · `1,800 Watts` · `15 Amps` · `1 Phase` · `NEMA 5-15P` | `[retail]`, corroborating |
| **Breville/PolyScience CMC850BSS USA** technical specification sheet | `120V ~ 60 Hz / 1800 W` · `Power Range 100–1800 Watts` · `Agency Certification: UL/IEC Commercial Certification` | `[manufacturer]` |

`1800 W = 120 V × 15 A` **exactly**. That identity holds only if the 1800 W is
input power and the manufacturer computed the amperage as `W / V` at unity
power factor.

Under an output reading at this repo's own `eta_min = 0.90` `[repo]`, the same
appliance would draw **16.67 A** at unity PF — the manufacturer's own printed
15 A would be **wrong by 11.1 %**, and no power factor could rescue it, because
`PF ≥ 1.111` is required (script §1). Two manufacturers do not both misprint
their own plate current by 11 % in the same direction.

| PF | I_line, **input** reading | I_line, **output** reading (η 0.90) |
|---|---|---|
| 1.00 | **15.00 A** ✅ | 16.67 A ❌ |
| 0.98 | 15.31 A | 17.01 A |
| 0.95 | 15.79 A | 17.54 A |
| 0.90 | 16.67 A | 18.52 A |
| **0.70 (this design, central)** | **21.43 A** | 23.81 A |

### 1.4 A second, independent confirmation from Breville's own two market variants

The CMC850 ships in two electrical variants with a common chassis
`[manufacturer]`:

| variant | rating-plate marking | published "Power Range" |
|---|---|---|
| USA / USC | `120V ~ 60 Hz / 1800 W` | `100–1800 Watts` |
| 220–240 V | (220–240 V variant sheet) | `100–2400 Watts` |

**In both variants the top of the user-facing power scale equals the
rating-plate figure exactly.** If the scale were delivered pan power it would
sit at roughly η × plate — near 1620 W and 2160 W, not on the plate number.
The coincidence is only explicable if Breville's power scale is *input* power,
or a nominal proxy for it. This is `[derived]` from two `[manufacturer]`
documents and is offered as corroboration, not as the primary warrant.

### 1.5 Verdict

> **`main.ato:494`'s `p_output_max: power = 1800W` declares as OUTPUT the
> number that the entire industry, and IEC 60335-1's own marking clause,
> use as rated power INPUT.** The brief's hypothesis is confirmed on the
> units question, with the correction that the quantity is real input watts
> (`V·I·cosθ`), not input volt-amperes.

**The prior derivations are not wrong anywhere.**
`docs/evidence/2026-08-19-input-stage-power-ceiling.md`'s arithmetic —
`P_out = V·I·PF·η`, so 1800 W *out* of a 15 A/120 V branch needs
`PF × η = 1.000` — is correct and survives intact. What this document adds is
that **no competitor is attempting that**, because no competitor's 1800 W means
what `main.ato` means by it.

### 1.6 What I could NOT establish

- **UL/ETL listing data.** `[NOT OBTAINABLE]` UL's Product iQ and Intertek's
  directory were not reachable in a form that yields per-model electrical
  ratings this session. The Breville sheet's own *"UL/IEC Commercial
  Certification"* line is the only listing evidence carried here, and it names
  no file number.
- **FCC filings.** `[NOT OBTAINABLE]`, and this repository already established
  why: an 1800 W induction cooktop with no intentional radiator falls under
  FCC Part 18 (ISM), for which consumer equipment needs no published grant, so
  absence of a filing carries no information
  (`docs/evidence/2026-07-28-reference-appliance-and-cap-rating.md`, Q2)
  `[repo]`. I did not repeat that search.
- **Energy-labelling requirements.** `[NOT OBTAINABLE]` for this product class
  in the US: cooktops are not covered by an FTC EnergyGuide label, so there is
  no labelling regime forcing an output figure to be published. I did not find
  a primary source stating the exclusion and am recording it as unestablished
  rather than asserting it.
- **IEC 60335-1 Annex L and IEC 60664-4** remain paywalled, as the brief
  anticipated. Nothing here depends on them.
- **IEC 60335-2-6's own text** remains unread (paywalled); the touch-current
  work in this repo flagged the same gap `[repo]`.

---

## 2. THE 15 A QUESTION — the framing in the brief needs one correction

The brief asks how these units *"achieve that on a 15 A branch circuit."*
**Partly, they don't.**

`[secondary source; NFPA 70 text is paywalled and was not retrieved]` NEC
**210.23(A)(1)** states that the rating of any one cord-and-plug-connected
utilization equipment not fastened in place shall not exceed **80 %** of the
branch-circuit ampere rating. At 80 % a 15 A branch permits **12 A / 1440 W**;
a 20 A branch permits **16 A / 1920 W**. A 1800 W / 15 A cord-connected
appliance therefore belongs on a **20 A** branch circuit, even though it ships
with a NEMA 5-15P plug — which is itself legal on a 20 A circuit.

**Two honest caveats, both material:**

- 210.23 is scoped to **multiple-outlet** branch circuits (its own title is
  *"Permissible Loads, Multiple-Outlet Branch Circuits"*) `[secondary]`. Whether
  the 80 % figure binds an *individual* branch circuit serving only this
  appliance is **not established here** and I did not find a retrievable primary
  source that settles it.
- I retrieved no manufacturer statement requiring a 20 A circuit. Vollrath's
  own page says 15 A and NEMA 5-15P and adds no circuit note `[manufacturer]`.

**What this does and does not change.** It does not rescue 1800 W of *output*:
on a 20 A branch at PF 1.000 and η 0.90 the output ceiling is 2160 W, so the
number would be reachable — but that is a different appliance on a different
circuit, and the *existing* `assert p_output_max within 1500W to 1800W
# 15A circuit limit` would then be commenting on a circuit the product no longer
uses. It is recorded here because the brief's question presupposed a constraint
that the industry partly sidesteps rather than solves.

---

## 3. HOW THEY REACH PF ≈ 1 — the answer is *not* PFC

### 3.1 The primary source

**Guillén, Sarnago, Acero, Burdío, Llorente, Lucía, "Induction Heating
Appliances: 50 Years of Technological Success Paving the Path for Sustainable
Homes"** (author manuscript, retrieved in full from the University of Zaragoza
repository, `zaguan.unizar.es/record/165185`) `[peer-reviewed]`. This is the
Zaragoza group — the field's principal academic group — with a co-author
(Llorente) from a domestic-appliance manufacturer. Verbatim, §B "Power
converter":

> "The rectifying stage provides a dc-link voltage while ensuring proper mains
> power consumption. **The simplest implementation, and thus, the most common,
> relies on a full-bridge diode rectifier with a low-value dc-link capacitor.**
> This way, it provides the dc-bus and high-frequency-current decoupling
> required by the inverter while **ensuring an input power factor close to
> unity [24, 25] without the need for an additional power factor correction
> stage.** Moreover, when the induction heating load non-linear effects make it
> necessary, the inverter modulation is adapted to ensure sinusoidal
> consumption. This allows to reduce the EMC filter requirements but **results
> on a high-ripple dc voltage, decreasing the rms voltage.**"

And on PFC, from the same paper's "High performance" section — note the tense:

> "Additionally, the inclusion of **a PFC stage is being prospected** not only
> to improve mains power consumption but also to achieve higher bus voltages
> and reduce the current through the power devices [85]."

Its reference [85] is Pérez-Tarragona, Sarnago, Lucía, Burdío, *"Design and
Experimental Analysis of PFC Rectifiers for Domestic Induction Heating
Applications"*, IEEE TPEL 33(8), 2018 — i.e. PFC for domestic IH is a **2018
research contribution**, not the installed base.

> **Verdict on the brief's hypothesis:** *"commercial units reach PF ≈ 1 either
> through active PFC or by using small (film-only) bus capacitance"* — the
> second disjunct is right and is the norm; the first is **not** typical and is
> best described as an emerging option. The design principle is explicit:
> a high-ripple dc bus is accepted **on purpose**, as the price of unity PF.

### 3.2 Three independent hardware corroborations of the capacitance figure

| unit | mains | rating | dc-link capacitance | tag |
|---|---|---|---|---|
| cheap single-hob countertop cooktop, Hackaday teardown (2016-02-19) | 120 V / 60 Hz | **1.8 kW** | *"The 8uF is the input cap located right after the bridge rectifier"*; unit *"eats a LOT of ripple at 60Hz"* | `[teardown]` |
| 4-zone cooktop, Kaizer Power Electronics teardown | 230 V | 8 kW total | *"4 uF of DC bus capacitance"* per half-bridge zone; rectifier D25XB60 (25 A/600 V); IGBTs Toshiba GT60J323 (**600 V**); resonant caps 0.68 µF/800 V | `[teardown]` |
| same 4-zone cooktop, HighVoltageForum reverse-engineering thread with schematic | 230 V | 8 kW | 4 µF/400 V close to each half-bridge; the bus *"tracks rectified line voltage, so current remains proportional to voltage"*; *"high power factor"* by *"allowing the DC bus to follow the rectified sinusoid without large bulk capacitance"* | `[teardown]`, forum — **weak alone**, carried only because it independently reproduces the Kaizer figure and matches §3.1 |

**Measured power factor, for calibration** `[secondary]`: an industry review
citing an EPRI 2014 study reports induction stoves at *"power factor of 0.98
and above"* and *"near unity power factor at all levels of power drawn except
in standby mode"*, with current THD *"less than 6%"*. The same article
attributes this to *"an active power factor correction circuit"* — **that
attribution is wrong**, and it contradicts §3.1's peer-reviewed statement. It is
recorded here as an example of the confident-but-unsourced claim the brief
warned about, and its *measurement* is used while its *explanation* is not.

### 3.3 The comparison this repository has to face

| design | dc-link capacitance | bus behaviour | PF |
|---|---|---|---|
| 120 V / 1.8 kW single-hob commercial unit | **8 µF** `[teardown]` | follows rectified line | ≈ 0.98+ `[secondary]` |
| 230 V half-bridge cooktop, per zone | **4 µF** `[teardown]` | follows rectified line | ≈ 1 `[peer-reviewed]` |
| **Temper, as built** | **3600 µF per half; 1800 µF effective** `[repo]` | 22 V p-p on 340 V `[repo]` | **0.595–0.763** `[repo]` |

**225× to 450×** the commercial figure (script §6). The 2026-07-26 architecture
review already found that the 3600 µF has *no derivation anywhere in this
repository* and that its only cited justification —
`sim_33_voltage_doubler.cir` — **does not exist in the repo** `[repo]`. This
document adds the external half of that finding: the number is not merely
underived, it is **two to three orders of magnitude away from what the industry
builds.**

---

## 4. WHAT TOPOLOGY THEY ACTUALLY USE

### 4.1 The vendor's own guidance

**Infineon Application Note AN2014-01, "Reverse-conducting IGBTs for induction
cooking and resonant applications", V3.01, 2021-08-24**, retrieved in full
`[manufacturer]`. §3 names three topologies and assigns them:

> "**Quasi-resonant converter**, also know as single-ended parallel resonant
> converter: mainly used in **single-hob stoves** and rice cookers…"
> "**Half-bridge series resonant converter:** mostly used to build **high-end
> multi-hob cookers** and microwave ovens."
> "**Full-bridge series resonant converter:** usually limited to the commercial
> cooker market, due to the higher power capability."

§3.2.4 on the QR converter:

> "The QR converter is mostly used in induction cooking appliances that have
> **only one cooking zone**. In this case, it offers the best trade-off between
> cost and performance. **Usually the inverter power rating is limited to
> 2.2 kW**…"

§3.3.3 on the half-bridge:

> "The HBSR topology is mostly used in the induction cooking appliances with
> **multiple cooking zones or when the required output power per inverter is
> above 2.5 kW.** Due to the higher cost compared to the quasi-resonant
> topology, the usage of the half-bridge is mainly restricted to high-end
> models."

and §4.2 repeats the threshold from the device side:

> "The HBSR converter is a current resonant topology, and therefore the peak
> VCE of the device is constant with the output power. For this reason, **the
> half bridge topology is used mainly in designs with inverter power rating
> above 2.5 kW.**"

**Temper is a single-hob, 1.8 kW appliance built on the multi-hob / >2.5 kW
topology.** That is not automatically wrong — the half-bridge's advantages
(accurate frequency control, device voltage independent of load and power) are
real and §7 credits them — but it is a deliberate departure from the industry
norm for this power class, and nothing in the repository records it as a
decision.

### 4.2 The device-voltage consequence, which the repo is on the wrong side of

Infineon's HBSR advantages list, verbatim:

> "**600 V/650 V IGBTs can be used** which have a much better conduction vs.
> switching losses trade-off with respect to IGBTs in higher voltage classes"

and the worked loss example in §4.2 uses the **IHW30N65R6 (650 V)**
`[manufacturer]`. The Kaizer teardown's production half-bridge uses **600 V**
Toshiba GT60J323 `[teardown]`. The 1200–1350 V class is what Infineon assigns to
the **QR** topology, because there the collector swings to *"3 to 4 times the
mains peak voltage"* `[peer-reviewed]`.

**Temper uses `IKW40N120H3`, a 1200 V IGBT** (`elec/src/components.ato:9-19`)
`[repo]` **on a 340 V half-bridge.** In a half-bridge the device can never
exceed the bus, so this is roughly a 3.5× voltage overspecification, paid for
in conduction loss on the very parameter Infineon names as *"the largest
contribution to the overall power losses"*. This is a finding, not a
recommendation — a part change is out of scope here and other agents own that
file.

### 4.3 What the 120 V single-hob market actually contains

`[teardown]` The Hackaday teardown of a 1.8 kW 120 V countertop cooktop found a
**bridge rectifier** feeding an **8 µF** cap — no doubler, no bulk bank. The
universally stocked induction-cooker repair IGBT is the **H20R1203 /
IHW20N120R3, 1200 V** `[retail]`, which is the QR single-switch device class,
not a half-bridge device.

**Honest limit on this claim.** I could not retrieve a dimensioned schematic of
a US-market 1800 W single-hob unit. The AllAboutCircuits "Teardown Tuesday:
Induction Cooktop" article returned HTTP 403 on every attempt, and a
search-engine paraphrase of it (naming paralleled IHW20N120R3 devices) is
**not used as evidence** — a paraphrase is not a retrieval. So: *"120 V
single-hob units use a bridge + small cap"* is `[teardown]`, one unit, and
*"they are single-switch QR"* is **inferred** from the topology-assignment
guidance in §4.1 plus the 1200 V repair-part class, not directly observed.

### 4.4 No 120 V unit was found using a voltage doubler

`[NOT OBTAINABLE]` I searched patents, teardowns and vendor literature for a
120 V induction cooktop using a voltage-doubler front end to synthesise a
~320–340 V bus, and **found none**. Absence of evidence is weak evidence here,
and I am not asserting that none exists. But the *reason* one would not expect
to find one is arithmetic and strong: a doubler needs bulk capacitance to
double, bulk capacitance costs power factor, and at 120 V a 1800 W nameplate
has **no power-factor budget at all** (§1.2 — PF must be 1.000). **The doubler
and the 1800 W plate are mutually exclusive on a 120 V/15 A supply**, and this
project has both.

---

## 5. THE CRUX: how a rippling bus and ZVS coexist — and what really blocks route 2 here

### 5.1 What the sources say

Guillén et al., on the half-bridge `[peer-reviewed]`:

> "Additionally, **operation is preferred above resonant frequency to achieve a
> ZVS commutation** and by means of snubber capacitors, Cs, in parallel with
> the switching devices, the turn-off losses can be mitigated."

Infineon AN2014-01 `[manufacturer]`, footnote to §3.3: the inductive (ZVS)
region is *"when the switching frequency of the inverter is larger than the
resonant frequency of the RLC network"*, and both its QR and HBSR analyses
state that `V_BUS` is *"assumed to be constant **during the given switching
cycle**"* — a per-switching-cycle assumption, explicitly **not** a per-line-cycle
one.

**Neither source conditions ZVS on bus stiffness.** The ZVS condition is a
statement about the *phase* of the tank impedance, and `V_bus` does not appear
in `X(f) = ωL − 1/ωC`.

### 5.2 The mechanism, derived — commutation time is invariant with bus voltage

The one place `V_bus` could plausibly enter is the dead-time commutation: the
lagging tank current must move `Q = C_s·V_bus` to swing the switch node. A
sagging bus reduces the tank current, so does it starve the commutation?

**No — to first order the two effects cancel exactly.** Under FHA the tank
current is `I ∝ V1 = √2·V_bus/π`, so:

```
t_comm  ≈  C_s · V_bus / I(V_bus)  =  C_s · V_bus / (k · V_bus)  =  C_s / k
```

Script §5, using Infineon's own 12 nF snubber figure `[manufacturer]` and the
repo's committed tank `[repo]`:

| V_bus | I_tank (R_eq 3.55 Ω, 47 kHz) | **t_comm** |
|---|---|---|
| 340 V | 20.95 A | **137.7 ns** |
| 170 V | 10.48 A | **137.7 ns** |
| 60 V | 3.70 A | **137.7 ns** |
| 20 V | 1.23 A | **137.7 ns** |

**Constant across a 17× bus swing.** And in the region where the cancellation
does eventually fail — very near the line zero crossing, where fixed diode and
`V_CE(sat)` drops stop being negligible — the residual hard-switching energy is
`½C_s·V_bus²`, which at 20 V is **2.4 µJ**, or 0.11 W even if it happened on
every cycle, against 693 µJ / 32.6 W at 340 V. **The bus is smallest exactly
where hard switching is cheapest.** That is why the industry can accept it.

### 5.3 So what *does* block route 2 in this design?

**Not ZVS. The coil.** Re-running the repo's own FHA model against a
line-following 120 V bridge bus (script §3):

| bus | mean(V_bus²) | P at the 44 kHz floor, R_eq 3.55 Ω | P at 47 kHz |
|---|---|---|---|
| stiff 340 V doubler (as built) | 115 600 V² | — | **1559 W** (R 3.55) / **1804 W** (R 5.31) — reproduces `main.ato:80` |
| line-following 120 V bridge | **14 400 V²** | **317 W** (R 3.55) / **321 W** (R 5.31) | lower |

The stiff bus is worth **8.03×** more power into the *same* tank. That factor is
not recoverable by frequency: the entire 47 kHz → 44 kHz travel is worth
**G = 1.43–1.63** `[repo]`, and 8.03 ≫ 1.63. **The 2026-08-19 bus-capacitance
derivation's conclusion — that route 2 is unavailable — is CORRECT. Its stated
reason is not.**

- What that document says: a rippling bus violates `f_pll_tracking_min`, *"putting
  a 1200 V IGBT half-bridge into hard switching."*
- What is actually true: the bus can ripple all the way to zero without losing
  ZVS (§5.2). The 44 kHz floor is a real and correctly-derived constraint on
  **holding power through a sag**, and the document's own FFPC inequality
  (`mean(V_bus²) ≥ P_target/k44`) is a **power-regulation** bound. Labelling it
  a ZVS bound over-states it and, more importantly, points at the wrong fix.

**This distinction is worth money.** If the obstacle is "the PLL floor forbids
a rippling bus", nothing can be done — the floor is a safety derivation and
`docs/evidence/2026-07-27-inductance-range-sweep.md` §2.3 establishes the 1.05
ZVS cliff as a threshold `[repo]`. If the obstacle is "the tank is scaled for
340 V", it is a coil re-specification, which is a design task with a known
answer.

### 5.4 What that coil re-specification would cost — named, per the brief's request

For a line-following 120 V half-bridge to deliver **1800 W mean** (script §4):

| quantity | required | committed today |
|---|---|---|
| `R_eq` at resonance | **1.62 Ω** | 3.55 Ω `[repo]` — a **2.19× reduction** |
| tank current at the line peak | **47.1 A rms** | — |
| tank current, line-cycle rms | **33.3 A rms** | 22.5 A `[repo]` |
| instantaneous output at the line peak | **3600 W** | — (P ∝ V_bus² ∝ sin², so the peak is 2× the mean) |

and that is **at** resonance, i.e. zero ZVS margin; a real design sits above it,
so `R_eq` must go lower still. **Concretely: a new coil with roughly 0.7× the
turns, a tank current ~1.5× higher in rms and ~2× higher in peak, a re-derived
`c_tank`, a re-derived `f_pll_tracking_min`, re-derived OCP thresholds, and a
re-derived tank-capacitor current rating** — the last of which is already
failing by 2× at the *present* current
(`docs/evidence/2026-07-28-reference-appliance-and-cap-rating.md`, 5.2 A
permissible vs 10.37 A required) `[repo]`. **This is a new power stage, not a
capacitor swap.** The brief asked whether the answer is "a different topology";
for the half-bridge route the answer is "the same topology, a different coil,
and every number downstream of the coil re-derived."

**The alternative the industry actually picks at this power** is the
single-switch QR converter (§4.1), where output power is set by IGBT **on-time**
rather than by `V_bus²/|Z(f)|`, giving the controller a wide authority that does
not run into a resonance-referenced frequency floor. Its costs are equally
concrete and Infineon lists them `[manufacturer]`: collector voltage *"in the
range of a thousand volt"* and unbounded by the bus, *"high sensitivity to
grid-voltage variation"*, *"switching frequency cannot be controlled
accurately, as it depends on the load"*, and a minimum continuous power set by
the onset of hard switching — remedied by **burst mode at 0.2–0.3 Hz**, which
this repository has already recorded `[repo]`. **For this project that is a
full redesign: different device count, different device voltage class,
different control law, different EMI signature, different everything below the
coil.** It is named because the brief asked for it to be named. It is not
recommended here.

---

## 6. THE CONTROL FREAK SPECIFICALLY

**What is established** `[manufacturer]`, from the CMC850 USA technical
specification sheet:

- Rating-plate marking `120V ~ 60 Hz / 1800 W`, models `CMC850BSS USA`,
  `CMC850BSS USC`.
- `Power Range 100–1800 Watts`; the 220–240 V variant sheet reads
  `100–2400 Watts` (§1.4).
- `Agency Certification: UL/IEC Commercial Certification`, `NSF Commercial
  Certification`, `IPX3`.
- `PRECISION INDUCTION HOB — Heat intensity control / Dual fan cooling system`.
- `Unit Dimensions 110 × 350 × 470 mm`, `Shipping Weight 11.2 kg`.

**What is NOT established, and I will not infer it from the class:**

- **Its inverter topology is unknown.** `[NOT OBTAINABLE]` No teardown, service
  manual, or schematic of the CMC850 or BMC800 exists publicly that I could
  retrieve. This repository's prior pass reached the same conclusion
  independently and searched patents (only `AU2021203832B2`, which describes
  power only as discrete ~90 W levels and *"contains no description of the
  inverter modulation scheme"*), iFixit (only a different Breville model), and
  FCC (Part 18, no grant expected) `[repo]`. I re-checked nothing there and
  found nothing new.
- **Its dc-link capacitance, power factor, and measured input current are
  unknown.** `[NOT OBTAINABLE]`
- **Whether it duty-cycles or modulates continuously is unknown.**
  `[NOT OBTAINABLE]`, per the same prior pass.

**What can be said without inference.** The plate figure is 1800 W at 120 V,
which by §1.2 is rated power *input* measured as `V·I·cosθ`. If the unit
actually draws its rated input on a 15 A branch, its power factor is
**necessarily ≈ 1.000**. That is a constraint on the Control Freak derived from
its own published plate and the standard's own measurement definition — not an
inference from what other manufacturers do. It excludes a PFC-less
capacitor-input doubler for that appliance. It does **not** tell us which of the
two PF ≈ 1 architectures it uses.

---

## 7. THE HONEST COMPARISON

**Is a half-bridge series-resonant inverter with a 44 kHz PLL floor and a
3600 µF/half doubler bus a reasonable architecture for a 120 V / 15 A
appliance?**

**The half-bridge is defensible. The doubler and the bus bank are not.** They
are the mismatch, and they are separable from the topology.

### 7.1 What is genuinely fine

- **Half-bridge series resonant** is the topology Guillén et al. call *"currently
  considered the best alternative in terms of performance, cost, and complexity
  for the power levels considered in induction cooking"* `[peer-reviewed]`. Using
  it below Infineon's 2.5 kW guideline is a cost/complexity choice, not an
  engineering error, and it buys accurate frequency control and a device voltage
  that does not depend on the load — both of which a single-hob QR design lacks.
- **Operating above resonance with a ZVS margin** is exactly what the sources
  prescribe. The 1.05 factor and the derivation at `main.ato:171-186` are
  sound work and this document does not touch them.
- **The 44 kHz floor is correctly derived** and worst-cased on both L and C
  tolerance. It is not the problem.

### 7.2 What is structurally mismatched

| # | the mismatch | the evidence |
|---|---|---|
| 1 | **The output/input units error.** `p_output_max = 1800W` is declared as output; the industry and IEC 60335-1 mean input. The design has been targeting ~2000 W of input where every competitor targets 1800 W. | §1 |
| 2 | **The doubler.** Its bulk capacitance is what destroys PF, and at 120 V an 1800 W plate has a PF budget of exactly zero. Doubler and plate are mutually exclusive. No 120 V commercial unit using one was found. | §1.2, §4.4 |
| 3 | **1800 µF effective dc link against a commercial 4–8 µF.** 225×–450×. And the value has no derivation in the repo, and its sole cited justification is a file that does not exist. | §3.2–3.3, `[repo]` |
| 4 | **PF 0.595–0.763 against an industry ≥ 0.98.** This is not a margin shortfall; it is a different class of front end. | `[repo]`, §3.2 |
| 5 | **A 1200 V IGBT in a 340 V half-bridge**, where the vendor's own note says 600–650 V and production hardware uses 600 V. ~3.5× overspecified on the parameter that dominates the loss budget. | §4.2 |
| 6 | **The delivered figure is 292 W** `[repo]` against a 1800 W declaration — a 6× gap that the bus bank's ripple rating, not the branch circuit, currently sets. | `[repo]` |

### 7.3 The uncomfortable summary

> **This design's inverter is a reasonable choice built on an input stage that
> the product class abandoned.** The industry's answer to "1800 W on 120 V" is:
> *make the nameplate an input figure, throw the bulk capacitance away, let the
> bus follow the line, take PF ≈ 1 for free, and scale the coil to the bus you
> actually have.* This project did the opposite on all four counts — it read the
> nameplate as output, added 1800 µF, stiffened the bus, and then scaled the
> coil to the stiffened bus. Each of those choices is individually arguable;
> together they produce a converter that cannot draw its rated input from the
> circuit it is specified for.
>
> **The good news is that the constraint chain is shorter than the prior
> derivations concluded.** Route 2 is blocked by the coil, not by the PLL floor
> (§5.3), and coils are re-specifiable in a way that safety floors are not.

### 7.4 What this does NOT establish

- **It does not say the half-bridge should be abandoned.** §5.4 prices the coil
  re-spec honestly and it is expensive; §5.4 also prices the QR alternative and
  it is a full redesign. Neither is recommended here; the brief asked for the
  comparison, not the decision.
- **It does not re-open any prior derivation's arithmetic.** The input-stage
  ceiling, the decision table and the capacitance selection are all arithmetically
  sound and this document reproduces `main.ato:80`'s 1804 W anchor and
  `main.ato:96`'s 37 563 Hz from their own inputs (script §3) as a cross-check.
  The one correction is to the *attribution* of the route-2 blocker (§5.3).
- **It settles nothing about the Control Freak's internals** (§6).

---

## 8. MARKET AND COMPETITIVE CONTEXT — quarantined

**No derivation in §1–§7 depends on anything in this section.** It is recorded
because the brief asked for the product class to be characterised, and it is
fenced because it is commercial information, not engineering.

- The 120 V / 1800 W commercial countertop induction range is a crowded,
  commoditised category: Vollrath (Mirage, Commercial-Series, MPI4-1800),
  Avantco (IC1800, ICBTM-20), Waring, CookTek, Hatco, Breville/PolyScience
  `[retail]`. All the ones checked publish the identical `120 V / 1800 W /
  15 A / NEMA 5-15P` block.
- The Breville Control Freak CMC850 sits at the top of the category on control
  sophistication (397 settable holding temperatures, ±1 °C stability, dual NTC
  probe, through-glass sensing) `[manufacturer]`, not on power — its 1800 W is
  the same commodity number as everyone else's.
- The EU/AU variant of the same chassis is rated 2400 W `[manufacturer]`, which
  at 230 V is 10.4 A — comfortably inside a 16 A socket. **The 120 V market is
  the constrained one**; the same product on 230 V has ~35 % more headroom and
  33 % more nameplate power from the same box.
- Consumer-facing "1800 W" therefore functions as a category label, not a
  performance claim: it is the largest round number that `120 V × 15 A` permits.

---

## 9. EVERYTHING I TRIED AND COULD NOT GET

Recorded so nobody pays for these attempts twice.

| target | outcome |
|---|---|
| Hsieh et al., IET Power Electronics 16, 1929–1942 (2023), `10.1049/pel2.12503` — the line-rectified-DC HBSR cooker paper this repo cites | **HTTP 402 Payment Required** on Wiley `pdfdirect`; **403** on IET Digital Library and DOAJ. Confirms the repo's existing note. A search-engine snippet reports PF *"0.95 to 0.98"* for it — **not used**, it is a paraphrase. |
| Zungor, Bodur, Ozturk, Obdan, *"Design Methodology of Series Resonant Half Bridge Inverter for Induction Cooker"*, IEEE Access 11, 135476 (2023) — open access, would have given a dc-link value for exactly this topology | **HTTP 418** from `ieeexplore` stampPDF; Semantic Scholar returned an empty body; ResearchGate not attempted (login-walled). Only its abstract-level frequency range (50.6 → 24.7 kHz for a 3 kW cooker) reached me, via a search summary — **not used**. |
| Lucía, Maussion, Dede, Burdío, IEEE TIE 61 (2014) via HAL | Anubis bot-protection interstitial. Superseded anyway by the 2024 Zaragoza paper in §3.1, which is stronger and was retrieved in full. |
| AllAboutCircuits *"Teardown Tuesday: Induction Cooktop"* | **403** on every attempt, including via search-cache. A paraphrase naming paralleled IHW20N120R3 devices exists but **is not used as evidence**. |
| `matrix108.wordpress.com` induction stove teardown | **403** |
| `imajeenyus.com` 2 kW induction cooker instrumented analysis | **TLS certificate expired**; WebFetch refuses |
| UL Product iQ / Intertek ETL directory listing data for any 1800 W induction range | Not reachable in a form yielding electrical ratings |
| NFPA 70 (NEC) 210.23 primary text | Paywalled; UpCodes served only an AI summary, which it itself disclaims. §2's figure is `[secondary]` and flagged as such. |
| A 120 V induction cooktop using a voltage doubler | None found (§4.4). Absence, not proof. |
| IEC 60335-1 Annex L, IEC 60664-4, IEC 60335-2-6 full text | Paywalled, as the brief anticipated. Nothing here depends on them. |

---

## 10. WHAT THIS SUGGESTS, WITHOUT DECIDING ANYTHING

Ordered by cost. **All of these are the owner's call; this document implements
none of them.**

1. **Free, and it is a documentation defect either way:** `main.ato:494` is
   named `p_output_max` and is **used nowhere else in the source** — a repo-wide
   search finds it only in its own declaration, its own assertion, and two build
   logs `[repo]`. Whatever it is renamed to, or whatever value it takes, nothing
   downstream moves. The gap between "the number everything is designed around"
   and "a number nothing reads" should be closed deliberately.
2. **Cheap:** reconcile the two readings of 1800 W already in-tree — output at
   `main.ato:494`, rated power *input* in the touch-current derivation (§1.1).
   They cannot both be right, and the touch-current one is the one with a clause
   citation behind it.
3. **Medium, and it is where the leverage is:** re-examine the doubler. It is
   the single component of the architecture that is both (a) incompatible with
   the nameplate the product class uses, and (b) upstream of the ripple failure,
   the PF failure and the bus-bank sizing simultaneously.
4. **Expensive, and honestly priced in §5.4:** if a line-following bus is ever
   pursued, the binding item is the **coil**, not the PLL floor. That reordering
   is this document's most actionable finding.

---

## 11. SOURCES

**Standards**
- IEC TC 61, *61/5396A/INF — Guidance on measurement of power input based of the requirements of 10.1 and 10.2 of IEC 60335-1*, 2017-08-01. Retrieved in full: <https://assets.iec.ch/public/tc61/61_5396A_INF_Guidance%20on%20measurement%20of%2010.1%20and%2010.2%20of%20IEC%2060335-1.pdf>
- IEC 60335-1, definition of *rated power input* (3.1.5) and marking (7.1) — definition text corroborated via search; full standard paywalled. Also as already quoted in-tree at `docs/evidence/2026-07-30-c6-touch-current-budget-and-part2-routes.md`.
- NFPA 70 (NEC) 210.23(A)(1) — **secondary only**, via <https://up.codes/s/cord-and-plug-connected-equipment-not-fastened-in-place> and <https://www.jadelearning.com/blog/210-23a12-permissible-loads-multiple-outlet-branch-circuits/>

**Manufacturer**
- Infineon, *AN2014-01, Reverse-conducting IGBTs for induction cooking and resonant applications*, V3.01, 2021-08-24. Retrieved in full: <https://www.infineon.com/assets/row/public/documents/60/42/infineon-an2014-01-reverse-conducting-igbt-applicationnotes-en.pdf>
- Infineon, *Smart Induction Cooktops* application brief. Retrieved: <https://www.infineon.com/assets/row/public/documents/30/53/infineon-smart-induction-cooktop-application-brief-applicationbrief-en.pdf>
- Breville/PolyScience, *the Control °Freak™ CMC850 Technical Specifications*, USA sheet (`120V ~ 60 Hz / 1800 W`): <https://savagebros.com/wp-content/uploads/2024/10/Breville-ControlFreak-CMC850_USA.pdf>
- Vollrath, model 6950020, 120 V Commercial-Series countertop induction range: <https://www.vollrathfoodservice.com/products/countertop-equipment/cooking-equipment/induction-ranges/commercial-series-countertop-induction-ranges/6950020>

**Peer-reviewed**
- P. Guillén, H. Sarnago, J. Acero, J. M. Burdío, S. Llorente, Ó. Lucía, *Induction Heating Appliances: 50 Years of Technological Success Paving the Path for Sustainable Homes*. Author manuscript retrieved in full: <https://zaguan.unizar.es/record/165185/files/texto_completo.pdf>

**Teardowns (medium strength; cross-corroborated where used)**
- Kaizer Power Electronics, *8 kW Induction Cooktop Teardown*: <https://kaizerpowerelectronics.dk/teardown/8-kw-induction-cooktop-teardown/>
- HighVoltageForum, *8 kW Induction Cooktop Teardown and Reverse engineering*: <https://highvoltageforum.net/index.php?topic=2334.0>
- Hackaday, *What Can We Learn From A Cheap Induction Cooktop?*, 2016-02-19: <https://hackaday.com/2016/02/19/what-can-we-learn-from-a-cheap-induction-cooktop/>

**Secondary / weak (labelled at every point of use)**
- Modern Energy Cooking Services, *Induction stoves, not inductive loads* (cites EPRI 2014 measurements): <https://mecs.org.uk/blog/induction-stoves-not-inductive-loads/>
- WebstaurantStore listing, Vollrath 59500P: <https://www.webstaurantstore.com/vollrath-59500p-mirage-pro-countertop-induction-cooker-120v-1800w/92259500.html>
- Induction-cooker repair-IGBT listings (H20R1203 / IHW20N120R3, 1200 V), e.g. <https://us.amazon.com/H20R1203-20R1203-Induction-Replacement-IHW20N120R3/dp/B0DRCB9SH6>

**In-tree, relied on and not re-derived**
- `docs/evidence/2026-08-19-input-stage-power-ceiling.md`
- `docs/evidence/2026-08-19-output-rating-decision-table.md`
- `docs/evidence/2026-08-19-bus-capacitance-selection.md`
- `docs/evidence/2026-07-26-bus-capacitor-architecture-review.md`
- `docs/evidence/2026-07-28-reference-appliance-and-cap-rating.md`
- `docs/evidence/2026-07-30-c6-touch-current-budget-and-part2-routes.md`
