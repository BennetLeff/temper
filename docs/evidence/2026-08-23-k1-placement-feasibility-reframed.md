<!-- provenance: commit=11b9573e432f4d0d21c39b8f5dd6ac02a2f747fd dirty=true (analysis scripts ran in-worktree; doc committed on k1/place-and-reroute) -->
# 2026-08-23 — K1 placement feasibility: fresh measurements + reframed solution space

Worktree: `k1-session` (branch `k1/place-and-reroute`, base = main @ 11b9573e4).
All numbers measured from `pcb/temper.kicad_pcb` via
`check_isolation_keepout.load_board` this session.

## Ground truth

K1 = Schrack RT33K012 (`temper:Relay_SPST_Schrack-RT33K012`) at **(90, 222) rot 0**.
Six THT pads:

| pad | net | board position |
|---|---|---|
| coil1 | power_in.bypass_relay-coil1 | (90.00, 222.00) |
| coil2 | power_in.bypass_relay-coil2 | (90.00, 214.50) |
| contact (w1_2) | w1_2 | (110.30, 214.50) and (110.30, 222.00) |
| contact (ntc-no) | power_in.ntc-no | (115.34, 214.50) and (115.34, 222.00) |

`power_in.ntc-no` and `w1_2`: **0 segments, 0 vias** (confirmed — HANDOFF §3.4 was right).

## Net endpoints (where the routes must reach)

```
w1_2:   RT1 @ (82.0, 205.5), L1 @ (153.5, 206.0)
ntc-no: RT1 @ (89.5, 205.5), U1 @ (65.1, 218.0), U2 @ (66.0, 226.0)
```

**RT1 is 17 mm from K1's contacts.** HANDOFF §3.3's "~345 mm" applies only to
the six far-away candidate sites from the earlier sweep — NOT to K1's current
pocket, where the endpoints are nearby.

## Blockers at the current site (the actual problem)

1. **C7↔K1 F.Fab body overlap, 77 mm²** — C7 (WIMA snubber, moved to
   (112, 218) rot 90 by #1244-era reconciliation) spans x≈106.5–117.5,
   y≈199–222: directly inside K1's restored THT envelope.
2. **K1.3 ↔ R56.1 creepage 5.036 mm vs 12.6 required** — R56 sits at
   (119.21, 207–209), just past K1.3's pad.
3. RT1 ↔ K1 coil-side 7.0 mm creepage (coil2 side).

## Reframed solution space

The handoff framed this as "move K1 → ~345 mm of new routing". The fresh
measurements show a second, plausibly cheaper direction that was never
solver-evaluated:

**(b) Keep K1 fixed** (nets stay short), relocate **C7** and **R56** — a film
cap and a resistor, both freely placed parts — out of K1's THT envelope,
subject to the pocket's other obstacles.

Recommended next step: CP-SAT/shapely pocket solve with K1 FIXED, C7+R56
free variables, all other courtyards fixed obstacles, then live-kicad-cli DRC
of the winning layout. If (b) is infeasible, fall back to (a) with the
handoff's site sweep.

Note: also evaluate RT1's position under (b) — the 7.0 mm coil-side creepage
may require an additional small displacement.
