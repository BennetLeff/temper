# 1800 W realignment plan: status and evidence check (2026-11-24)

Input: the 2026-11-24 recommendation suite and misalignment review (external agent). This file records
what was executed and where the plan's fixes do not match the committed evidence. It changes no board.

## Executed

- s55 + device trade merged (`claude/native21-s55-unified`, `807354d43`); DECISIONS 81 / 82 from
  `codex/power-stage-integration` are now 83 / 84. Full merge, because the four listed commits cite `651c2e5e5`.
- FAULT-INTERFACE.md and README.md brought to s55 (more than the plan listed: U13 drives J4.10, CT 1:200 / 3 ohm,
  shunt OCP 92.59 A, isolator limits, PS1 removed from the barrier list).
- Firmware `fw/c51-s56-unified`: heatsink NTC CR-8 gain, with the open-sensor limit it requires.
- `ps-integrate`'s uncommitted datasheet ledger is an older c54 state (C2 on 1.5 A, L1 body 92.4 C); s55 supersedes it.
- `hardware/CURRENT.tsv` was not repinned (the plan repins at s56). `hardware/` is untracked in the main checkout;
  a tracked copy exists on `claude/hardware-baseline-guard` at stage 19b.

## Plan items that need changing before s56 / C51

| Plan item | Evidence | Use instead |
|---|---|---|
| F1 0.993: widen the binding trace >= 15 % | The 0.993 rows are the Q2 / Q5 TO-247 drain lands (terminal-limited, not a trace; DECISIONS item with the restated target). The lowest conductor is L1 -> BR1 AC1, B.Cu, 2.598 mm, 1.02x | Widen L1 -> BR1 AC1 if more margin is wanted; `fuse_copper_fusing_ratio` stays 0.993 |
| V24_RAW clamp: 1SMB5935B 27 V or SMBJ26A | PS2 supplies 0.9 A rated / 110-150 % overload: ~27 W into a 3 W Zener. SMBJ26A breakdown reaches ~31.9 V and clamps at ~42 V, so neither holds 32.0 V. (Vendor figures for the two clamps are from memory: confirm) | Not chosen. Options: two series silicon diodes ahead of AVIN / PVIN (needs the 21 V minimum-input check at 23.43 V), or accept the PS2-fault WARN. Decide at s56 |
| U41 / U42 CTRL bottom 27 k -> 18 k | 7.0 V is the abs max and 5.5 V the operating max (Rev. 1-2024 pp. 2, 8), so the `.ato` comment mislabels rather than contradicts. 18 k is not on the BOM | 16 k RT0603BRD0716KL (R34's line): 4.5 V at 32.4 V, >= 3.0 V at 23.43 V with 10 uA pin current, against 2.1 V enable |
| Firmware: cherry-pick `fw-ct` drivers | Both branches carry a full platform layer: 33 application functions defined twice; merging 12 conflicts would not link | Port fixes one at a time onto the s55 base |
| `CT_RAW_MAX_MV` 2510 -> 2850 | Not enough: `CT_RAW_MIN_MV` 800 rejects the negative half-wave past 56.7 A. The s55 base already uses 50 / 2850 mV | Keep the s55 base's `n21_signal.h`; do not port `ct_current.c` |
| MAX31865 thresholds "stale in `fw-ct`" | `fw-ct` has the C46 words as `MAX31865_C1_*` (35544 / 12844) and uses them; only the legacy words are old | Done in fw/c51-s56-unified 67a6c77b1 |
| MAX31865 manual cycle | s55 repeats the automatic cycle every 1 s. A manual cycle needs >= 5.5 + 5.5 + 11.5 ms of waits plus the ~52 ms first conversion, against the 100 ms stale limit | Done in 67a6c77b1 + 950823387: manual cycle at power-up and before a probe-fault reset, none while converting. Open: RUN_EN is killed until MCU reset on every latched fault, so that reset is refused on hardware (owner decision) |
| Pan control port | Not in the plan: native-21 has no bus-current sense, and no pan detection on target | Ported in c0b3f5653 with the stage's measured power; open items in firmware COMMISSIONING H13 (on/off chopping below the stage floor, C1 SIL not ported) |
| P06 as RTD2 CS | Confirmed reserved (controller DECISIONS) | As planned |

## Not started (and why)

s56 copper, D-22, C51, UI Rev 2, R45 CAD, coil former: each is its own stage with its own gates. B1, bench-h and D-8 need
hardware. The JLC and Intertek emails, quotes and orders need the owner's go-ahead; the Intertek questions were already
sent 2026-10-27, so a new message risks a duplicate.
