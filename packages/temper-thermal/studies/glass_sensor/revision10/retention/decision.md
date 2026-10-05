# C9 retention: define location and preload before strength claims

Reviewed 2026-10-05. **CLOSED_DECISION:** keep C9 as a dry experimental attachment concept; do not select an assembly torque or claim retention capacity yet. The next drawing must specify bracket location and carrier material/process before structural qualification. Physical **NOT_RUN**.

This follows the Temper mechanical/manufacturing review skills. It adds partial tolerance and reaction-normalized bearing budgets to R9's nominal CAD. No new worktree, CAD export, material allowable or product proof load was introduced.

## The fastener holds; it does not uniquely locate the bracket

The modeled 1.8 mm hole around a nominal 1.6 mm shaft admits 0.10 mm radial shaft movement in each part. Two such aligned holes can admit up to 0.20 mm relative center separation before the nominal shaft envelopes cease to fit, considered in isolation. The carrier passages constrain the bracket separately: the foot has 0.10 mm nominal total vertical excess and 0.10 mm each lateral side; the upright passage likewise has 0.10 mm each lateral side. Those contacts can limit motion earlier. These numbers are **clearance budgets, not a calculated assembled displacement envelope**.

The head-to-ring radial gap is only 0.20 mm nominally. A 0.10 mm inward shaft offset within the carrier hole consumes half of it before hole location error, ring variation, distortion or growth. The catch's 0.10 mm unloaded clearance is also of this order, but on a different axis. Tightening friction cannot serve as a repeatable locating datum. R9's centered bolts and exactly positioned brackets therefore do not demonstrate robust catch overlap or assembly variation.

The next prototype drawing should locate each bracket from controlled carrier seats and tangential/radial surfaces, explicitly permit needed thermal motion, and specify inspection of all three catch heights/overlaps after assembly. A jig could establish the position during tightening, but it would not establish resistance to later slip. Do not silently add interference fits, washers, locking compounds or a second locating pin to the checked CAD.

## Load sharing changes the result by a factor of three

`budget.rs` computes mean pressure per newton of **summed reaction at the named interface**, assuming that reaction is shared by three, two or one contact. It does not calculate joint preload, bolt prying, actual pressure distribution, bending stress or failure load. In particular, head/nut reaction is not automatically equal to external pan or pull load; preload and joint stiffness must be included in a later joint model.

| Surface, per joint | Area (mm²) | Three equal contacts (MPa/N total) | One contact carries all (MPa/N total) |
| :-- | --: | --: | --: |
| Existing cap hook bearing | 0.240000 | 1.388889 | 4.166667 |
| Island / bracket | 0.594659 | 0.560546 | 1.681637 |
| Head / bracket, nominal | 4.523893 | 0.073683 | 0.221049 |
| Nut / carrier, nominal | 6.323410 | 0.052714 | 0.158143 |

The original small hook contact remains in series with the larger new screw-bearing surfaces. Larger screws alone do not qualify that hook, its formed/welded attachment or the island. Manufacturing differences can make one catch engage first; equal thirds is only a scenario. The model needs measured catch-height variation, part stiffness, actual external load directions and lateral/tilting escape cases before load sharing can be justified.

## Published fastener extremes do not complete the stack

The exact [SSCF-M1.6-4-A4 screw](https://www.accu.co.uk/metric-cap-head-screws/3942-SSCF-M1-6-4-A4) specifies a 3.00 mm head with −0.14 mm tolerance. At its minimum diameter, the ideal centered head-bearing annulus drops to **3.879553 mm²**, increasing mean pressure for the same reaction. The exact [HPN-M1.6-A4 nut](https://www.accu.co.uk/hexagon-nuts/7901-HPN-M1-6-A4) specifies 3.20 mm across flats with −0.18 mm tolerance and 1.30 mm height with −0.25 mm tolerance. Its ideal centered bearing area drops to **5.353808 mm²** and its minimum height envelope is **1.05 mm**. Sources checked 2026-10-05; availability was not established.

These calculations keep the hole at its CAD nominal. They exclude chamfers, partial seating, eccentricity, face flatness and the actual threaded engagement after end chamfers/runout. Neither 1.05 mm height nor nominal thread matching is a thread-strength result. The supplier pages do not qualify this installed joint at 250°C; no room-temperature class is treated as a hot allowable.

For growth bookkeeping, each 1 ppm/K differential strain across a common 7.1 mm span over an illustrative 225 K rise produces 0.0015975 mm differential movement. This is a unit sensitivity only. An actual clearance requires expansion from the correct datums for each part, local temperatures and the selected material grades; it cannot be obtained by subtracting this scalar from every cold gap.

## Remaining release inputs

| Input | Why it changes the calculation | Owner / disposition |
| :-- | :-- | :-- |
| Carrier material, grade, process, flaws and hot properties | Bearing, reduced sections near passages, growth and creep | Mechanical/materials; **UNKNOWN** |
| Formed or machined bracket process and root radii | Sharp ideal unions are not fatigue or bending evidence | Mechanical/fabricator; **UNKNOWN** |
| Required pull/lateral/abuse loads and duty | Defines structural cases and proof procedure | Product/mechanical; **UNKNOWN**, no fabricated limits |
| Hot joint preload window and locking method | Must retain contact without crushing or relaxing carrier | Mechanical/fastener supplier; **UNKNOWN** |
| Catch height/overlap tolerances and restraint datums | Determines first-contact load sharing and escape | Mechanical/metrology; budget now explicit, values **UNKNOWN** |
| Thermally cycled pull, looseness and slip observations | Checks the actual joint and process | Bench; **PHYSICAL_NOT_RUN** |

Reproduce the small calculation with `sh run.sh` from the saved repository copy, or set `TEMPER_REPO_ROOT` to the existing sensor checkout for a scratch copy; six focused tests passed. `inputs.sha256` pins the CAD and recorded contact evidence and is checked before running; `results.sha256` pins the calculator and output. This is an arithmetic audit of inherited nominal dimensions, not a new B-rep inspection, full tolerance analysis or structural solver.
