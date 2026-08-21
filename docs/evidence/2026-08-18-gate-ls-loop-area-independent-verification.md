<!-- provenance: commit=9019da63fe1f8cfccb98c53fafbbf0a8537ee7a6 dirty=false (branch analysis/gate-ls-loop-area) -->

# GATE_LS gate-drive loop area: independent verification, cause, and placement proposal

Board: `pcb/temper.kicad_pcb` sha256 `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
(verified before and after; **the board was not modified by this investigation**).

Measurement environment: worktree-local `.venv` via `make venv-isolate`
(`temper_placer` resolved from
`/home/bennet/Desktop/temper-gate-ls-loop/packages/temper-placer/...`, not the
shared checkout).

---

## 1. The 1131.34 mm² figure reproduces. I agree with it.

Two independent methods, agreeing to the last digit:

| method | GATE_HS | GATE_LS |
|---|---|---|
| `physics.gate_drive` + `temper_geometry.convex_hull_area_py` (production kernel) | 96.47 mm² | 1131.34 mm² |
| from-scratch: own s-expression parser, own monotone-chain hull, own shoelace | 96.47 mm² | 1131.34 mm² |

Trace counts also agree: 81 go-segments on `GATE_HS`, 132 on `GATE_LS`
(all `B.Cu`), 0 return segments on either — hence the public
`gate_drive_loop_area()` correctly returns `None`/`UNMEASURED` for both.

Topology resolution reproduces as briefed:
`GATE_HS` →[R18]→ `hb.power_loop.q_high-g` → U4, return `SW_NODE`;
`GATE_LS` → U5 (direct), return `hb-gnd`.

Monotonicity does not need randomised trials: the convex hull of a superset
contains the convex hull of a subset, so the go-arm hull is a lower bound on the
go∪return hull by construction.

## 2. A stronger, routing-independent bound

The brief's bound is "the go arm as currently routed". A stronger statement is
available. `GATE_LS` has exactly three pads:

| pad | net | position (mm) |
|---|---|---|
| `R22.2` | GATE_LS | (57.002, 223.100) |
| `R23.1` | GATE_LS | (51.750, 185.045) |
| `U5.1`  | GATE_LS | (100.070, 159.330) |

Any fully-connected routing of `GATE_LS` must place copper on all three. The
triangle they span is **986.94 mm²**. So for this placement, **every possible
routing yields ≥ 986.94 mm², i.e. ≥ 1.97× the 500 mm² limit** — routing choice
cannot matter. Pairwise separations: R22–U5 **76.95 mm**, R23–U5 54.74 mm,
R22–R23 38.42 mm. Total routed `GATE_LS` copper length is **123.5 mm**.

The as-routed 1131.34 mm² is that floor plus **+10.6%** of routing excursion.

## 3. Cause: R22 is the outlier, not a spread-out topology

The low-side gate path is
`U6.10 (OUTB, net "input")` → **R22** (series gate resistor, 1206) → `GATE_LS`
→ `U5.1` (IGBT gate), with **R23** (0603) as the gate–`hb-gnd` pulldown.

R22 sits at (55.540, 223.100). Its driver pin U6.10 is at (82.735, 147.305) —
**81.0 mm away**. Its load U5.1 is **76.95 mm away**. R22 is in the
bottom-left of the board while both its source and its destination are in the
mid-right. R23 is likewise 54.7 mm from U5.1.

Against the project's own layout rules
(`docs/hardware/CRITICAL_LOOP_DESIGN.md` §5.2 / §9.2):

| rule | required | actual |
|---|---|---|
| gate resistor to driver | < 5 mm | R22 **81.0 mm**, R18 **52.4 mm** |
| total gate trace length | < 30 mm | GATE_LS **123.5 mm** |
| loop area per gate | < 2 cm² (200 mm²) | GATE_LS **1131.34 mm²** |

## 4. Two routing defects found incidentally

Both gate nets terminate copper on a **foreign pad** (exact coordinate
coincidence, d = 0.0000 mm):

- `GATE_LS` copper lands on **`R23.2`, which is on net `hb-gnd`** — the pulldown's
  return pad — while its own pad `R23.1` has **no copper within 0.90 mm**. As
  drawn this is gate-to-return metal on the low-side gate net.
- `GATE_HS` copper lands on **`U6.7`, net `nc_7`** (a primary-side no-connect),
  while its own driver pad `U6.15` is **11.64 mm away with no copper**. The
  `GATE_HS` routed copper lies entirely on the primary side (y ≤ 137.56) and
  never reaches the secondary-side output pin it belongs to.

These are reported, not fixed — they are board changes.

## 5. The GATE_HS comparison is not a valid comparison

`GATE_HS` is not "structurally similar but 12× better". It is smaller only
because most of its go arm carries no copper yet:

- its device-side net `hb.power_loop.q_high-g` has **0 routed segments**, and its
  pads span **y = 21.5 mm (R19.1) to y = 233.25 mm (U4.1)** — a 212 mm spread;
- its own driver pad `U6.15` is unrouted (§4).

Completing the high-side routing gives:

| high-side quantity | area |
|---|---|
| as measured today (GATE_HS copper only) | 96.47 mm² |
| anchor-only lower bound (R18.1, R18.2, R19.1, U4.1) | **1206.36 mm²** |
| go-arm hull once `q_high-g` is routed | **4674.40 mm²** |

**The high side is the worse loop, by ~4×.** The 12× asymmetry is an artifact of
routing progress, not a design asymmetry, and it points at U4/R19 placement as a
larger problem than the one under investigation.

Related: the check's own walk under-measures the low side. Because `_find_switch`
runs before the first hop, `GATE_LS` resolves with `forward_nets = {GATE_LS}` and
**never includes the driver-output leg** (net `input`, U6.10 → R22.1), whereas
`GATE_HS` resolves to two nets and does include its driver leg. Once `input` is
routed the physical low-side go arm is **1688.50 mm²**, not 1131.34 mm².

## 6. Placement proposals

Free-space audit: the region below U5 (x 88–104, y 163–178) and above it
(y 148–156) contains **no components**. Nearest neighbour to U5 is R62 at
14.49 mm. U5's courtyard is x[86.42, 102.82] y[156.38, 161.91]. There is ample
room for a 1206 and an 0603.

Predicted `GATE_LS` go-arm hull (anchor hull, and with the measured +10.6%
routing overhead):

| option | anchor hull | with routing | verdict |
|---|---|---|---|
| baseline today | 1022.47 | **1131.34** | 2.26× over |
| A. perfect routing, no parts moved | 986.94 | 1131.34 | **still 1.97× over** |
| B. move R22 only, to 6 mm from U5.1 | 19.49 | **21.57** | passes |
| C. move R23 only, to 4 mm from U5.1 | 41.40 | **45.81** | passes |
| D. **move R22 + R23 within 6 mm of U5.1** | 8.75 | **9.68** | passes, recommended |
| E. R22 + R23 within 10 mm | 27.00 | 29.88 | passes |
| F. R22 + R23 within 14 mm | 52.00 | 57.54 | passes |

Slack is large: both resistors may sit up to **~26 mm** from U5.1 and still come
in under 500 mm² (~318 mm²). Even option B alone — moving the single worst part —
clears the limit by 23×.

**What option D disturbs:**

- *Isolation barrier*: nothing adverse. `GATE_LS`/`GATE_HS` are netclass
  `GateDriveHV`, and `hb-gnd` is `HighVoltage`; R22, R23 and U5 are already all
  in the HV/secondary domain. Moving R22/R23 toward U5 moves them **away** from
  the SELV side, so `MIN_BARRIER_WIDTH_MM` (12.6 mm PD3) pressure decreases.
  The move must not be made toward U6, whose barrier is already at 8.100 mm
  against a 12.6 mm requirement (`docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md`).
- *Existing copper*: 132 `GATE_LS` segments and 8 segments starting in the
  target box are invalidated and must be re-routed. `GATE_LS` and `input` are
  currently among the 79 unrouted/incomplete nets anyway.
- *Thermal / heatsink*: U5 is a `TO-247-3_Vertical` with a heatsink tab.
  Placing 1206/0603 parts within 6 mm of the gate pin needs a heatsink and
  mounting-hardware keepout check that this analysis did **not** perform — this
  is the one constraint I could not clear from the board file alone, and it is
  the reason options E/F (10–14 mm) are listed: they retain a comfortable
  margin and still pass by an order of magnitude.
- The `input` net (U6.10 → R22.1) gets **longer** under option D (~76 mm). That
  leg is not measured by this sub-check but is physically part of the gate loop,
  so R22 should be understood as trading a measured violation for an unmeasured
  one unless the driver-to-Rg leg is routed as a tight differential pair with
  `hb-gnd`. **Option D is the right move only if the driver-side leg is treated
  as part of the same fix.** A fuller fix relocates U6's low-side output region
  and U5 together; that is a larger placement change than this brief scopes.

## 7. Is 500 mm² the right limit? It is a project figure, and it is too loose.

**It is not from a datasheet or a standard.** Its provenance:

- `placer/cp_sat/gates.py:889` — `_GATE_DRIVE_LOOP_MAX_MM2: float = 500.0`, no citation.
- `docs/plans/2026-07-08-005-...-plan.md` R2 states `≤ 500` for gate drive, no derivation.
- The only quantitative 500 mm² derivation in the repo,
  `docs/solutions/best-practices/commutation-loop-area-physics-derivation-2026-07-04.md`,
  derives 500 mm² for the **commutation** loop (79% of a 635 mm² IGBT-overvoltage
  ceiling at 1 nH/mm², 1 A/ns) and validates `commutation.yaml`'s
  `max_area_mm2: 500`. It says nothing about gate loops.

Meanwhile the repo's own gate-loop figures are **stricter**:

| source | gate-drive limit |
|---|---|
| `configs/templates/loops/gate_drive_low.yaml` / `gate_drive_high.yaml` | **100 mm²** |
| `docs/hardware/CRITICAL_LOOP_DESIGN.md` §5.2, §9.2 | **200 mm²** (<2 cm²) |
| `placer/cp_sat/gates.py` (enforced) | 500 mm² |

The most likely reading is that the commutation loop's 500 was transcribed onto
the gate-drive sub-check; note the same file carries `_COMMUTATION_LOOP_MAX_MM2 =
2000.0`, i.e. 4× looser than the value that derivation calls a hard ceiling. Both
constants look mismatched to their own documentation.

**Not changed, per instruction.** Recording it because it cuts one way only: the
enforced limit is the *loosest* of the three project figures, so the finding is
robust — `GATE_LS` at 1131.34 mm² is 2.26× over the enforced 500, 5.7× over the
hardware doc's 200, and 11.3× over the loop template's 100. Whichever the owner
picks, the low side fails. The commutation constant (2000 vs a documented 635 mm²
destruction threshold) deserves separate owner attention.

## Reproduction

```sh
make venv-isolate
.venv/bin/python - <<'PY'
import pathlib, temper_geometry
from temper_placer.physics.gate_drive import _resolve_gate_loop

pcb = pathlib.Path("pcb/temper.kicad_pcb")
for gate in ("GATE_HS", "GATE_LS"):
    go, ret = _resolve_gate_loop(pcb, gate)
    pts = set()
    for t in go:
        pts.add((round(t.start[0], 3), round(t.start[1], 3)))
        pts.add((round(t.end[0], 3), round(t.end[1], 3)))
    flat = [c for p in sorted(pts) for c in (float(p[0]), float(p[1]))]
    print(gate, "go=", len(go), "return=", len(ret),
          "hull=", round(float(temper_geometry.convex_hull_area_py(flat)), 2), "mm^2")
PY
```

Expected output:

```
GATE_HS go= 81 return= 0 hull= 96.47 mm^2
GATE_LS go= 132 return= 0 hull= 1131.34 mm^2
```

The anchor-triangle bound in §2 needs no `temper_placer`: it is the shoelace area
of `R22.2 (57.002, 223.100)`, `R23.1 (51.750, 185.045)`, `U5.1 (100.070,
159.330)`, all read directly from the three `GATE_LS` pads in
`pcb/temper.kicad_pcb`.
