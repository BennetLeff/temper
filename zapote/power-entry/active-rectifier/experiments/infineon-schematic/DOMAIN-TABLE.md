# Domain and connection table

| Domain | Nets | Members | Intent |
|---|---|---|---|
| AC input | `AC_L`, `AC_N` | J1, GBJ2510-F, IRM-10-15, Q1/Q2, BSP300 T1/T2 | Mains-side hot conductors. |
| Rectifier output | `PREBOOST_POS`, `HOT_GND` | passive bridge, Q1–Q4, IRM return | Active/passive bridge output into the existing boost stage. It is **not** the 390 V PFC bank and does not contain the post-boost F2. |
| Low-side sensing | `SENSE_A`, `SENSE_B`, `MOT`, `VS` | IR11688S, BSP300 extensions, R4/R5/C5/C6 | VDS sensing with the 800 V extension devices; bare IR11688S pins do not touch AC. |
| Driver input | `CMD_A`, `CMD_B`, `AUX_15V`, `HOT_GND` | J1, UCC21530BQDWKRQ1 | HOT-referenced logic/control. No SELV claim is made. |
| Floating gate domains | `HS_L`, `HS_N`, `BOOT_A`, `BOOT_B` | Q1/Q2 sources, UCC21530 VSSA/VSSB, bootstrap diodes/caps | Two explicit high-side domains. Package isolation does not qualify PCB output-to-output spacing. |

Conducting diagonals are represented as Q1/Q4 (AC_L to HOT_GND) and Q2/Q3
(AC_N to HOT_GND), with Q1/Q2 drains on PREBOOST_POS, Q1/Q2 sources on
AC_L/AC_N, Q3/Q4 drains on AC_L/AC_N, and Q3/Q4 sources on HOT_GND. The
passive GBJ path remains physically in parallel for surge protection. The
post-boost F2 is outside this preboost unit; no fuse or interruption claim is
made here.

The 15 V module is line-fed so control power can start before the boost stage.
Its exact footprint pin map is 1=AC/N, 2=AC/L, 3=-Vout, 4=+Vout; its negative is explicitly tied to `HOT_GND`; the isolation rating of the
module must not be interpreted as user-accessible SELV isolation in this design.
