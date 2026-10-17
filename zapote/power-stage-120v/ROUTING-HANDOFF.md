# Routing handoff (2026-09-26)

State at b67c5adf9 + this note: batches 01-04 route clean under the real rules
(0 DRC violations, 0 cross-layer barrier hits); 74 opens remain, all HOT aux
nets (leg_ret signal, hot5, v15_ls, ref25, vsense_in, ovp_*, ocp_*, bus_fault_hot).

Important: before the write_rules fix in b67c5adf9, the rule file was invalid
on KiCad-saved boards, so every earlier "0 violations" routed result was
not valid. Re-run everything through tools/write_rules.py.

## Plan for batch_05_aux (tools/routes.py)
- Swap LDO caps in tools/floorplan.py: c_ldo_out (hot5) to (57.5,18,90),
  c_v15 to (66.5,18,90), so each cap sits at its own U3 pin.
- Aux ground island ties to power LEG_RET only at R5.2 (Kelvin). Driver
  bypass caps tie locally: C15.2 -> VSSB y38.55; C16.2 via (113,33.4) +
  In1 to a via on VSSB at (114.9,33.4); C8.2/C9.2 via U1.9 -> (156.27,41.6).
- U4/U7 cluster: In1 leg_ret zone
  [(41,78),(61,78),(61,88),(63,92),(66,94.5),(68.5,97),(68.5,103),(41,103)]
  (8 mm from SELV island). leg_ret vias: C28.2 (58.4,80.4), U4.3/4 (58.2,85.3),
  C27.2 (55.6,91.9), U7.2 (59.3,95), R37.2/C33.2 link at y98.2 via (62.5,98.2),
  C34.2 (67.3,96.6). vsense_in: U4.2 via (58.6,83.4), R30.1 via (58.4,89.6),
  U7.4 via (63.14,96.9), In2 between; F.Cu R29.2->(54,93.6)->C27.1->(58.3,92.3)->R30.1 via.
  ovp_thresh on F.Cu via x59.5 channel. hot5 vias U4.1 (60.17,80.6),
  U7.5 (63.4,92.8), B.Cu at x<=60.9. ovp_ok_hot via (59.6,93.1), B.Cu x59.35-59.9.
  ref25 via (56.4,99.8), B.Cu x57.2.
- Trunk: B.Cu west of C5 (x 35-48; the column right of D3 fails the barrier near
  (69.2,74)), north to y~38, east to the LDO (x 55-67) and U8/U9 (F.Cu locally,
  vias at x<=83; SW_B B.Cu pour bubble).
- East of U8/U9, the SW_B stitch vias (97.4,36.6) and (102.09,39) block In2.
  Proposed fix: merge them into one via at (102.1,33.0) (reroute C18.2 on F.Cu),
  which opens In2 lanes at y 37-41.2 from x 88 to 130 (hot5, ref25, ocp_ok_hot,
  leg_ret, v15_ls to U2). Then run v15_ls to D1.2/U1 on an In1 lane at y 28.8 (inside
  HV_RET plane, clear of D1.1/D2.1 bubbles) -> (150.5,28.8) -> via (150.5,35.3)
  -> F.Cu to U1.11, C9.1 -> C8.1.
- OCP cluster: R5.2 sense on F.Cu x123.0 down past the hv_ret vias,
  then x121.5 between C40.2 and the leg B lanes; ocp_kelvin_n from R5.3 at x127.75,
  then between C40.2 and C38.2 (x125.2-127.8).

## After routing
Official native dirs via tools/route_board.py; full creepage DRC; parity; stackup
gate; barrier_check; metrics. Update tests (they still point at native-04 and
2-layer), PLACEMENT-REVIEW, DECISIONS (D1 240 mm, D3 4 layers), ROUTING.md. Placement
changed after D4, so it needs a new D4 review. The write_rules courtyard exemption
needs reviewer sign-off.
