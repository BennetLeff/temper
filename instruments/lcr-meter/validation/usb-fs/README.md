# USB Full Speed routing (2026-11-03)

Run it with `<kicad-python> validation/usb-fs/usb_fs_check.py`. It writes `usb-fs-check.json`.

The RP2040 is Full Speed only (12 Mb/s), and FS edges are 4–20 ns (USB 2.0 §7.1.2.1). A trace is electrically short when its delay is under a sixth of the rise time. At about 7 ps/mm on FR-4, that limit is 95 mm for the fastest legal edge. Below it, impedance control and length matching have no effect.

| Segment | D+ | D− | Mismatch |
|---|---|---|---|
| J1 → R3/R4 (USB_DP/DM, both receptacle orientations) | 36.98 mm, 4 vias | 43.38 mm, 2 vias | 6.4 mm, 45 ps |
| R3/R4 → U1 (USB_DP/DM_MCU) | 7.80 mm | 8.28 mm | 0.5 mm, 3 ps |
| Connector to MCU | 44.8 mm | 51.7 mm | 48 ps |

Both lines are about half the short-line limit, and the 48 ps skew is about 1 % of the fastest edge. **0 findings.** No impedance or matching work is warranted on Rev F.
