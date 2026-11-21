# Brief: judge the Rev G100 LCR meter order package

You are an independent judge. An AI agent (Claude) did the work below between 2026-11-09 and 2026-11-15, on a board that is about to be ordered. Your job is to find out whether that work is right. Do not decide how well it is written.

Be adversarial:
- Read the files and rerun the numbers. Do not take the agent's documents, commit messages or review records as evidence; treat them as claims.
- Several earlier reviewers were the same model family (Fable). Look hardest where they might share a blind spot.

## 1. The board, in two lines

Temper LCR meter Rev G100 is a USB-C-powered, four-terminal LCR meter on a 100 × 100 mm 4-layer board, made to measure Temper's induction coil, pan and resonant tank. Main parts:
- RP2040 MCU and TAC5112 codec;
- OPA2810 source and transimpedance amplifier;
- TPS65131 ±14 V switcher with ±12 V LDOs;
- four TQ2SA latching range relays;
- TLP172AM photoMOS jack-isolation switches with TVS protection;
- four BNCs.

It is ordered as JLCPCB Economic PCBA (top-side SMT), with the BNCs and the J4 SWD header hand-fitted by JLC. The host CLI `temper-lcr` drives it. **No board of this line has been built, and its firmware has never run on hardware.**

## 2. The snapshot

- **Content:** branch `study/lcr-rev-g100` at commit **412a11f7a**, the tree `instruments/lcr-meter/` and its shared tooling in `instruments/boardkit/`.
- **Export:** `export.sh` in this folder writes a frozen copy with `git archive`. It adds the gitignored upload file `manufacturing/temper-lcr-gerbers.zip`, and checks its SHA-256: `ac6f45a6a8af1b21a5cd7a72e03637d6f95ca536834a5cd39923aa9f26498504`.
- **Board file:** `cad/temper-lcr.kicad_pcb`, SHA-256 `0822e8e24ff3728290f0c9bdde0be265a797a50410383ae9804c167c9cc1a4cd`.
- **The same firmware on Rev G:** `study/lcr-rev-g` at **a8e3e3211**. Rev G is the 100 × 110 mm sibling, not being ordered.
- **Git history:** the export has no `.git`. `history/` holds `git log --stat` for the commits under judgement, and one patch per commit covering source and doc files (Python, C, Rust, shell, Markdown, CSV, text); the Rev G carry commits are the last two. The generated Gerbers, images and binaries are listed in the `--stat` but not diffed. If you have the repository instead, `git log --oneline 286f4c05f~1..412a11f7a` lists the commits under judgement, and `git show <sha>` gives each diff. Use three-dot diffs against older branches.

**Tools on the owner's Mac** (adjust if yours differ):
- **KiCad Python (pcbnew):** `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`.
- **kicad-cli:** `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`.
- **Board gates:** `sh validation/rev-g100/gates.sh`, about 10 minutes. It **rewrites tracked files** (manufacturing/, previews/, validation/), so run it only in your own copy. A rerun changes the Gerbers' creation-date lines, and so the zip hash; compare file contents, not zip hashes.
- **Firmware:**
  ```
  PICO_SDK_PATH=<pico-sdk 2.2.0, rev a1438dff> PICO_TOOLCHAIN_PATH=<arm-gnu 14.2.rel1> \
    TEMPER_LCR_BUILD_DIR=<scratch> sh firmware-rev-e/build.sh
  ```
  It rewrites `bin/` and `verification/`. The host-side unit tests alone build with
  ```
  cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -DLCR_FS_375K=0 -DLCR_REV_G=1 -Ifirmware-rev-e/src \
    firmware-rev-e/test/test_host.c firmware-rev-e/src/{syncavg,wave,tac5112,relay,rails,jackguard}.c -lm
  ```
- **Host CLI tests:** `cd host && cargo test`. Use a fresh `CARGO_TARGET_DIR`.
- **Screens that need no rebuild:**
  - `python3 validation/firmware-pins/firmware_pins_check.py`;
  - `python3 validation/rev-g-protection/drive_budget.py`, which needs `build/pad-coordinates.json` from a gates run;
  - `python3 validation/power-spurs/current_check.py`.

## 3. The work under judgement

| Commit | What the agent says it did |
|---|---|
| 286f4c05f, ba746cf71 | Host `relaycheck`, which makes a relay that missed its RESET pulse visible. The bring-up G6a rework ladder: R101 to 0 Ω, then 4.5 V coils |
| 6419ce4fb, 73c4d2bf2, aff63119d | Third independent layout review and its fixes: VRLY / RLY_RST widened (coil 4.149 → 4.169 V), 3V3A on In2 at 0.4 mm, stubs removed, RUN entry, and `current_check.py` extended. Then a re-check |
| 7c7b8a479, 1ea381450 | G100 chosen. Order package and `docs/rev-g100-handoff.md`. Package-review fixes: Economic tooling holes instead of edge rails, `manufacturing/preview-checklist.csv`, flash the Rev G image first |
| a12077019 | Pre-mortem fixes (`validation/rev-g100/premortem-2026-11-15/`): the RP2040 pad pull-down on USB_SENSE, which the agent says would have left every board without USB; LCUR zero; `JACKS FORCE`; boot relay RESET on a rail fault; Rev G 375 kHz image; `BUILD` command; a new firmware-pins gate; "G100 first power" bring-up steps |
| 5d9562977 | Fixes from an independent firmware review (`premortem-2026-11-15/firmware-review.md`): USB never dropped on USB_SENSE; run-time rail watch; FORCE bounded; LCUR zero clamp ±300 mV with a 0.4 V trip; gate made code-aware and checking the ELFs |
| c9f67da79 | J4 (SWD header) changed from DNP to JLC hand fit. `drive_budget.py` updated to the new firmware constants (a gate had caught the stale copy) |
| 412a11f7a | Optimization review (`optimization-review-2026-11-15/`): order as-is; fab note 6 corrected from edge rails to tooling holes |
| 91a321cd6, a8e3e3211 (on `study/lcr-rev-g`) | The same firmware, pins gate and `drive_budget.py` carried to Rev G through a scratch git index (no worktree) |

The agent's final recommendation to the owner was to order now, with five boards assembled ($430.70) rather than two ($282.92).

## 4. Claims to verify

Mark each **Confirmed**, **Refuted** or **Unverified**, with your evidence.

1. **USB_SENSE bug.**
   - The RP2040 pads reset with the pull-down on (datasheet text in `sources/new/RP2040-datasheet.txt`, PADS_BANK0 "PDE … RW 0x1"; RPD 50–80 kΩ).
   - pico-sdk 2.2.0's `gpio_init()` leaves the pulls alone.
   - With R5 / R6 = 100 k / 100 k (`cad/design.json`), GPIO13 therefore sat under VIH 2.0 V, and the old `main()` waited on it before `stdio_init_all()`.
   - Is the bug real, is the fix (`firmware-rev-e/src/main.c`) right, and is any path left where the console can be hidden?
2. **The pins gate** (`validation/firmware-pins/firmware_pins_check.py`) catches this class of bug: a commented-out call, a call after the first read, an image without the call. Can it still pass falsely?
3. **LCUR zero** (`firmware-rev-e/src/jackguard.{h,c}`, `test/test_host.c`, `drive_budget.py` rows).
   - The premise: with the switches closed, LCUR's true DC is about 0 V whatever the DUT.
   - The bound: a DC fault present at the close stays connected only up to 0.7 V + |E|, with E = 0.222 V from 1 % resistors, under the 1.05 V where R43 reaches 0.1 W (`validation/datasheet-audit-rev-g100/afe.md`, G-AFE-01).
   - Is ADC offset handled honestly? Can normal use trip it, given the tone ripple after the sense filter?
4. **Firmware behaviour:**
   - a low USB_SENSE gives a held fault, not a disconnect;
   - the run-time rail watch, at 3 bad readings per 100 ms poll;
   - FORCE: FAULT lit, 2-minute expiry, captures refused;
   - boot RESET on a rail fault: safe with the codec not started?
   - the hot-loop cycle bound (209) is unchanged, and the four images build from source.
5. **RP2040-E5:** the SDK's USB enumeration workaround, which would borrow GPIO15 (ISO_DRIVE), is not compiled in.
6. **J4 hand fit:**
   - the CPL offset of 270 (an EasyEDA fit, `sources/placement-rev-c.json`) giving a CPL angle of 180;
   - BOM 81 lines and CPL entries consistent;
   - the cost model (`manufacturing/order_estimate.py`, `../boardkit/src/temper_boardkit/jlc/order.py`) gives $430.70 for five and $282.92 for two on `validation/rev-g/prices/jlc-parts-2026-11-10.json`.
7. **Gerbers:**
   - the zip matches the board, with 0 shorts and 0 opens against the IPC-D-356 netlist (`validation/rev-g100/gerber-netlist-check.json`);
   - since 1ea381450, only `User_Drawings` and the files' date lines changed, so the copper is untouched by the J4 and fab-note changes.
8. **The order instructions are consistent with each other and with the files:**
   - `docs/rev-g100-handoff.md` "To order";
   - `manufacturing/FABRICATION.md`;
   - the fab notes on the drawing layer (`cad/tools/rev_g100.py` `fab_notes()`);
   - `manufacturing/preview-checklist.csv`;
   - `bom-jlcpcb.csv` and `cpl-jlcpcb.csv`.

   This covers counts (253 components, 248 SMT, 5 hand-fit refs), tooling holes, via covering and the J1 / Y1 / BNC notes. Do the fab drawing's notes contradict the order anywhere else? Note 4's "JLC's plugging fills them" was flagged once before.
9. **Relay RESET margin:** 4.169 V at the coils in the RESET pulse at VBUS 4.40 V, against 4.125 V for a 45 °C relay (`validation/rev-g100/drive-budget.json`). Is it real, and is the `relaycheck` logic (`host/src/main.rs`, `host/tests/rev_e.rs`) sound for the failure it claims to expose?
10. **Third-review fixes:** they made no change outside the intended nets, and `current_check.py` now covers 3V3A / 5VA / LDOIN at the stated currents.
11. **The Rev G carry** (91a321cd6, a8e3e3211) touched only `firmware-rev-e/`, `validation/firmware-pins/` and `validation/rev-g-protection/drive_budget.py`, and Rev G's netlist passes the pins gate.
12. **The five-board recommendation:** "three more later ≈ $333.53" against "+$147.78 now". Is the cost reasoning right, and is the risk argument (no copper-level failure mode found) supported?

## 5. Beyond the claims

Look for what nobody checked. For example:
- first-power hazards in states the firmware cannot control (blank flash, BOOTSEL, RUN held);
- anything in the BOM / CPL a JLC operator could misread;
- protection limits the firmware now relies on;
- documentation that would send the owner down the wrong path at bring-up.

You may judge the agent's process too: where it was overconfident, and where it reported something as verified that the files do not show.

## 6. Known gaps (the agent's own list; confirm or extend)

- The firmware has never run on hardware; only host tests, disassembly checks and static bounds.
- No DC-bias curves were fetched for the capacitor changes, which only went to the respin list.
- `drive_budget.py` was not run on the Rev G branch: it needs a board rebuild there.
- Rev F (`study/lcr-in-box`) still carries the USB_SENSE bug and is not being built.
- JLC stock was last read live on 2026-11-15; the relays were at 209 against 20 needed and falling.
- The hot-plug SPICE and the protection screens were not rerun after the firmware changes. The firmware thresholds feed the protection argument only through `drive_budget.py`.
- G8 (charged-part touch) and G9 (ESD) are model-only.

## 7. Rules

- Work read-only on the snapshot. Do not order, add to a cart, sign in or enter credentials anywhere. Reading public JLC / LCSC part data signed out is fine.
- Every number you report must come from a file you read or a computation you ran. Keep your scripts and outputs, and cite them.
- Do not propose substituting K1–K4 (relays) or Y1 (crystal); both are deliberately locked. After three layout reviews, a copper change must be better on every count; a trade goes on a respin list.

## 8. Deliverable

A report of at most about 1500 words:
1. **Verdict:** order as-is / order after listed fixes / do not order. One paragraph of why.
2. **Findings,** ranked BLOCKER / MAJOR / MINOR / NOTE. Each with file:line, the concrete failure scenario, and a fix.
3. **Claims table:** 1–12, each Confirmed / Refuted / Unverified, with evidence.
4. **Process critique:** where the agent's confidence ran ahead of its evidence.
5. **Paths to your scripts and outputs.**
