<!-- provenance: commit=1bf621573089524bcd2a85ec4cf4cfb05c3d7f26 dirty=false (clean tree; `git status --porcelain` empty at measurement time). pcb/temper.kicad_pcb sha256=1dfff173ca672c84a23a7241b8b15b3e832ef603ae6e6cee8d6622273bcb8bea -- the post-#1506 board, NOT the 62bff72d board docs/evidence/2026-08-24-pd3-creepage-burndown-remeasure.md measured, which is why that document's per-band figures are superseded here. Extensions verified 10/10 fresh via scripts/check_stale_extensions.py BEFORE the run, per AGENTS.md. Tool: scripts/measure_cross_domain_creepage.py --min-creepage-mm 12.6, read-only; pcb/ was not written. -->

# HV↔SELV creepage: the eight-pair burn-down list, and a convention error that ran in both directions

**Date:** 2026-08-25
**Base:** `origin/main` @ `1bf621573`
**Board:** `1dfff173ca672c84…` (post-#1506)

## Bottom line

**98 violations below the enforced PD3 12.6 mm bar. Eight are actionable.**

| class | count | meaning |
|---|---:|---|
| `body_free` | **8** | straight-line path is clear — a routed slot or a move fixes it |
| `body_crossing` | 89 | line passes through a component body; blocked on the Annex L question #1386 settled the geometry half of |
| `unknown` | 1 | no body outline data |

The eight are the whole tractable job, and they are **five components**: `C27` x3, `C14` x2, `R4` x2, `R23` x1.

## 1. The list

| gap (mm) | shortfall | HV side | SELV side | convention-sensitive |
|---:|---:|---|---|---|
| 8.743 | **3.857** | `R23.2(hb-gnd)` | `R43.1(+3V3)` | no |
| 8.972 | **3.628** | `C27.2(tank.c_tank1-p2)` | `U21.4(gnd)` | no |
| 9.293 | **3.307** | `C27.2(tank.c_tank1-p2)` | `U21.5(+3V3)` | no |
| 9.756 | **2.844** | `C14.1(+170V_BUS)` | `U13.4(gnd)` | yes |
| 10.616 | **1.984** | `C14.1(+170V_BUS)` | `U13.5(+3V3)` | yes |
| 12.192 | **0.408** | `R4.2(PWR_RTN)` | `U6.3(+3V3)` | yes |
| 12.331 | **0.269** | `R4.1(+170V_BUS)` | `U16.5(+3V3)` | yes |
| 12.465 | **0.135** | `C27.2(tank.c_tank1-p2)` | `R48.2(safety.ovp.comp-inp)` | no |

Three are **sub-millimetre** (0.135, 0.269, 0.408 mm) — nudges, not re-solves.
`C27` accounts for three of the eight on its own and is the only part touching
both the tank node and the OVP comparator input, so it is the highest-leverage
single move.

## 2. The convention error ran in BOTH directions

The tool now cross-checks against KiCad's real R(−θ), verified against pcbnew
through `scripts/kicad_pad_rotation_oracle.py`:

```
violations the pre-fix R(+theta) would have MISSED:     34
phantom violations R(+theta) would have INVENTED:       67
```

So before #1376/#1380 landed, the instrument was not merely miscounting. It
**hid 34 genuine mains-to-SELV proximities while manufacturing 67 that do not
exist**, against a reported set of ~100. Anyone burning this list down
beforehand would have spent most of the effort on phantoms and still shipped
the real ones.

**Four of the eight actionable pairs are convention-sensitive**, including both
`C14.1(+170V_BUS)` pairs — the largest shortfalls in that group. They are real
under KiCad's actual convention and were invisible before the fix.

This is the concrete reason the earlier "137 violations, 70 convention-sensitive"
figure could not be acted on, and why the rotation work was a prerequisite
rather than a detour.

## 3. What #1506 changed

Four board moves clearing the body-collision cluster and K1's isolation barrier:

| | pre-#1506 (`62bff72d…`) | post-#1506 (`1dfff173…`) |
|---|---:|---:|
| total | 101 | **98** |
| `body_free` | 8 | **8** |
| `body_crossing` | 92 | **89** |

All three cleared came from `body_crossing`; the actionable set is unchanged.
Consistent with the ceiling's own DRC instrument (creepage 114 → 108).

## 4. Scope

- No board file was written. This is measurement only.
- The 89 `body_crossing` pairs are **not** actionable by placement alone —
  #1386 established that opening a slot end changes which pad pair governs,
  never the number, so IEC 60335-1 Annex L is load-bearing either way. That
  question is packaged for a certification lab
  (`docs/cert-lab-inquiry-final-2026-08-16.md`).
- Supersedes the per-band figures in
  `docs/evidence/2026-08-24-pd3-creepage-burndown-remeasure.md`, which measured
  the pre-#1506 board. That document's cross-method confirmation of the ceiling
  still stands.

## 5. Reproducing

```bash
uv run --no-sync python scripts/check_stale_extensions.py      # do this FIRST
uv run --no-sync python scripts/measure_cross_domain_creepage.py \
  --min-creepage-mm 12.6 --json /tmp/pairs.json
python3 -c "import json;r=json.load(open('/tmp/pairs.json'))['reports'][0];\
print([ (v['hv'],v['selv'],round(v['distance_mm'],3)) \
for v in r['violations'] if v['body_class']=='body_free'])"
```
