# Native-21 FEM setup (2026-10-08): mesh gates pass, campaign pending

Copper: `native-21/verification/native21-all-copper.json.gz` (routed board `76ec8cca…`,
`extract_geometry.py`). Closures: [`../closures-legA-n21.json`](../closures-legA-n21.json),
[`../closures-legB-n21.json`](../closures-legB-n21.json). Mesher legs `A21` / `B21`
(`scripts/mesh25d_hybrid.py`); the campaign driver accepts them.

What changed from native-19:
- The power core keeps its native-19 arrangement (FET row, film caps, gate resistors, R5),
  re-positioned: the film caps sit 6.2 mm lower and further right, and the drivers moved, so the
  loops are new and need the full extraction.
- **Gate-loop returns.** The drivers' VSSA is the -2 V rail (N_HA / N_HB) and VSSB is N_LS, not
  SW_x / LEG_RET. Each gate loop now closes through the 0402 bias decoupling beside its driver
  (C110-C113, C114-C117, C118-C121, C122-C125), modelled as bridges. The 0603/1210 parallels
  are left open: their ESL keeps them out of the HF path, and leaving them open errs high.
- Loop nets add N_HA/N_HB and N_LS.

Coarse check here (arch 1 mm, edge 0.7 mm; no solve): leg A 5.78 M tets, leg B 4.73 M tets; both
pass every campaign gate: no PEC columns, zero port leakage, every port a closed loop, all 19
closure ends on the main conductor body.

Pending: the round-17 campaign on the remote box (fine 1/2/3 mm + coarse, four single-port solves
per height per leg) and then the decision grid on the new matrices. Blocked on SSH access to the
remote box (Tailscale SSH check), and the fine meshes do not fit on the Mac (~2 GB free).

    campaign.py WORKDIR --leg A21 --export <native21-all-copper.json.gz> \
        --closures closures-legA-n21.json --cases 1:0.35 2:0.35 3:0.35 1:0.5 1:0.7
