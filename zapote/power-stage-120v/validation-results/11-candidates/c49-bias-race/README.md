# BIAS_GOOD boot-sample race (power board s48, OPEN-ITEMS B13 H2)

Analysis lane, 2026-10-16. Read-only on the repo (`worktrees/ps-integrate`, HEAD 923f78a63). Re-run:
`python3 -I scripts/bias_race.py`. It prints the tables below and writes `results/bias_race.json`.
Class tags: **G** = datasheet guaranteed limit, **T** = datasheet typical or characteristic curve, **C** = computed from
G tolerances, **S** = committed project SPICE, **E** = estimate from this analysis (the bench has to confirm it).

## Verdict

**The race is lost at worst case, and the datasheets don't guarantee a win at any corner.** The firmware POST
(`main.c:218`, the first statement of `app_main`) only passes if BIAS_GOOD is still low when it is sampled. Two facts
decide the outcome:

1. **BIAS_GOOD depends on the controller only through v3v3.** U32 side B, U46, U40 and the pump all run on v3v3 from
   J4.3 (netlist: `v3v3` includes J4.3). Suppose the HOT heartbeat is already running when v3v3 arrives. Then GPIO35
   crosses VIH 0.46–0.56 ms after v3v3 reaches 2.375 V:
   - CA-IS3720 tSU ≤ 40 µs (G);
   - pump design J start ≤ 10.5 µs (S, `c24-monitor-fmea/results/m1_pump_spice.json`);
   - the J4.1 220 k + 10 k / 1 MΩ / 1 nF RC to 0.75 VDD (C).

   The ESP32-S3 cannot even leave reset that soon. The 10 k / 1 µF CHIP_PU RC releases 8.9–17.7 ms after v3v3
   (VIH_nRST 0.75 VDD). At the fastest corner (VIL_nRST 0.25 VDD) it releases at 1.85 ms. **So no firmware, not even a
   bootloader hook, can sample first in this ordering.** Margin with a zero-time firmware: −1.3 ms. With this firmware:
   **−159 / −331 / −487 ms** (earliest / typ / latest sample).
2. **Nothing makes the HOT side wait for the controller.** PS2 (MPM-20-24, setup ≤ 1500 ms) and PS3 (MPM-65-15ST, setup
   ≤ 1000 ms) publish only maximum setup times (G, at 115 VAC full load, nothing at 108 VAC). The datasheets therefore
   allow D = (PS2 setup − PS3 setup) anywhere from −1000 to +1500 ms. The sample wins only if PS2 lags PS3 by more than
   **D_req = 59 / 291 / 475 ms** (min / typ / max). At typical chains the margin is −290 ms at D = 0 and turns positive
   only near D ≈ +290 ms.

Two other cases always fail, whatever D is:
- **A short mains dropout** where PS3's output, and so v3v3, falls to the ESP32's power-on reset but PS2's lightly
  loaded HOT chain rides through. On re-power, v3v3 returns into a running heartbeat and the boot is a power-on reset.
- **A PS2 that is simply faster than PS3** on a given unit.

The bench step in `COMMISSIONING.md` step 2 item 6 ("Sequencing") would find this as unit-to-unit, coin-flip POST
faults. It is settled here instead.

Phase angle at switch-on (0–8.3 ms of bulk charging, common to both modules on the same inlet) and line or temperature
only shift D inside a range the datasheets leave unbounded anyway. They don't change the verdict.

## Timeline from mains-on

| # | Event | min | typ | max | Class | Source |
|---|---|---:|---:|---:|---|---|
| C1 | PS3 setup (AC on → output starts) | 0 (none published) | — | 1000 | G (max only) | MPM-65-SPEC p.2 "SETUP, RISE TIME 1000ms, 30ms/115VAC at full load" |
| C2 | PS3 output start → U1 TPS62933F EN (VIN 11.2 V typ, 12.1 V max, 100 k / 12.1 k) | 0 | 23.0 | 24.8 | E | 30 ms rise (MPM-65 p.2), linear ramp; VEN_RISE 1.21 / 1.28 V (SLUSEA4D 7.5) |
| C3 | EN → v3v3 (soft start, CSS 10 nF) | 1.11 | 1.45 | 1.96 | G+C | SLUSEA4D Eq. 6, ISS 4.5 / 5.5 / 6.5 µA |
| C4 | v3v3 → CHIP_PU released (10 k / 1 µF, VIH_nRST 0.75 VDD) | 8.9 | 12.5 | 17.7 | C+E | ESP32-S3 datasheet v2.2 Table 5-4. CL10A105KB8NNNC X5R: ±10 % tolerance (G); temperature and DC-bias derating (E) |
| C5 | CHIP_PU → first statement of `app_main` (the sample) | 150 | 318.8 | 470 | T + E | Espressif ESP Techpedia "ESP Chip Startup Time Optimization": ESP32-S3, IDF v5.2.1, **318.8 ms before optimization** (26.9 ms after). Range is E (see below) |
| | **v3v3 → sample (C4 + C5)** | **158.9** | **331.3** | **487.7** | | |
| P1 | v3v3 ≥ 2.375 V → GPIO35 ≥ VIH, heartbeat already running | 0.46 | 0.50 | 0.56 | G+S+C | CA-IS3720 v1.08: UVLO+ ≤ 2.375 V, tSU ≤ 40 µs. Pump J ≤ 10.5 µs. J4.1 final value 0.810–0.816 × VDD |
| H1 | PS2 setup (AC on → output starts) | 0 (none published) | — | 1500 | G (max only) | MPM-20-SPEC 2024-10-30 p.2 "1500ms, 30ms/115VAC at full load" |
| H2 | PS2 output start → V15_LS in the LS window (U26 TPS7A4700, EN = IN, CNR/SS 1 µF) | 40 | 65 | 100 | T + E | SBVS204G Fig. 5-21 "Startup Time = 65 ms, CNR = 1 µF". No min / max published |
| H3 | PS2 output start → HS-A / HS-B P–N up (U41 / U42 R24C2T25) | 3 | 28 | 29.2 | G+E | RECOM R24C2T25/R p.4: UVLO rising 19 / 20 / 21 V, soft start 3 ms. CTRL = 24 × 27/127 V |
| H4 | rail up → monitor 5 V and 'good' (U37–U39 TPS70950 + LM2901 + ISO6721 + oscillator) | 0 | 0.5 | 1.5 | G | SBVS186H tSTR 500 typ / 1500 µs max; the rest are µs |
| | **PS2 output start → HOT vote good** | **40** | **65.5** | **101.5** | | |

Race: the sample wins only if D > D_req = (C2 + C3) + (C4 + C5) + P1 − (H2..H4) = **59 / 291 / 475 ms**. The
datasheets allow D ∈ [−1000, +1500] ms.

Typical-chain margin against D (ms): D = −1000 → −331; 0 → −290; +100 → −190; +200 → −90; +300 → +10; +500 → +210.

**Why the C5 range is an estimate.** Espressif publishes no boot-time limit. Their 318.8 ms is a measured typical
with the defaults. This build keeps every default the techpedia page removes; the resolved defaults are from the IDF
v5.3.6 Kconfig files, since `sdkconfig.defaults` overrides none of these:
- bootloader log INFO;
- app log INFO;
- image validation on every power-on (`BOOTLOADER_SKIP_VALIDATE_ON_POWER_ON` default n);
- ROM log on;
- RTC slow-clock calibration of 1024 cycles.

It also has:
- a 411 kB app (`build-evidence/esp-idf/build-strict.trimmed.log`, 0x64680);
- QIO 80 MHz flash;
- no PSRAM;
- no secure boot;
- a USB-Serial-JTAG console that, with no host attached, can stall up to 50 ms once (`usb_serial_jtag_vfs.c`
  `TX_FLUSH_TIMEOUT_US`).

Hence 150–470 ms. The verdict doesn't depend on this range: even at 0 ms it is lost, by C4 alone.

## What the bench step would have measured wrong

`platform_bias_good_capture_boot_sample()` logs `esp_timer_get_time()`. In IDF v5.3.6, `esp_timer_impl_early_init()`
resets the systimer when the app starts (`esp_timer_impl_systimer.c`). The logged time therefore leaves out the ROM, the
bootloader and the CHIP_PU RC, which are most of C4 + C5. For the bring-up record, use `esp_rtc_get_time_us()` (it
counts from chip power-up) plus a scope on v3v3 and J4.1.

## Fixes, ranked

The isolators are forward-only, so firmware cannot command the HOT side. It can't command the SELV heartbeat gate
either: no controller signal reaches U46.

| Rank | Fix | Coverage | Needs | Cost (500 boards) |
|---|---|---|---|---|
| **1 (recommended)** | **S: v3v3-referenced delay on the SELV pump gate.** Add a TPS3808G30DBVR whose open-drain RESET joins net `hsb_good` (U46.1, the heartbeat NAND's A input), with the existing R135 10 k to v3v3 as its pull-up. VDD (6) and SENSE (5) on v3v3, GND (2) on selv_gnd, CT (4) to 470 nF, MR (3) open (internal 90 k pull-up), 100 nF at VDD. While RESET is low, U46 stops the pump and BIAS_GOOD is held low. | **37 % kept.** Independent of the PS2 / PS3 order, line, phase and temperature, and of short dropouts (VIT 2.79 V ± 1.5 % is above the ESP32 2.44 V brown-out and its power-on reset, so any power-on-reset boot restarts the delay) | Power-board copper (SELV, outside the locked spine, beside U46 / R135). Firmware: none required | TPS3808G30DBVR **LCSC C189211**, JLC Extended, **2,338 in stock**, $0.4487 @ 500. Second source TECH PUBLIC TPS3808G30DBVR-TP C52817293 (2,602). CL10B474KA8NNNC **C1623**, Basic, 798,692 in stock, $0.0203 @ 600. 100 nF is the existing CC0603KRX7R9BB104 line. **≈ $0.47 per board**, +2 BOM lines, +3 placements |
| 2 | P: drive U46.A from PERMIT (permit_gate) instead of R135. BIAS_GOOD becomes bias_ok AND PERMIT. Firmware checks low with PERMIT low, then high within ~1 ms of raising RUN_EN with the PWM idle | ≥ 37 %, and a fresh low→high proof at **every start**, not once per power-on | Power-board copper (re-route only), a firmware sequence change, and an FMEA / DECISIONS 67 review (it changes "BIAS_GOOD high before PERMIT", and TP19 no longer shows bias health while PERMIT is low) | $0 parts |
| 3 | R: RC delay on `hsb_good` from existing lines: 220 k (RC1206FR-07220KL) × 10 µF (CL32B106KBJNNNE) plus a BAT54S half as the reset diode | 37 % nominally | Power-board copper | ~$0 new lines. Delay 1.04–3.11 s before diode leakage, but BAT54 reverse leakage at hot is comparable to the 15 µA charge current, and without the diode a short dropout (<~5 s) leaves no delay. Weaker than S |
| 4 | Firmware: move the sample into a bootloader hook (`bootloader_before_init`), or trim the boot (bootloader / app log WARN) | **0 % on its own.** BIAS_GOOD is at VIH ≤ 0.56 ms after v3v3; the CHIP_PU RC alone takes ≥ 1.85 ms | Firmware | Only useful combined with S at CT = VDD (no cap; td 180–420 ms G, SBVS050N 6.6): +0.12 s margin against a hook at ≤ CHIP_PU + 40 ms (E). Saves the 470 nF line, but rests on an estimated hook time |
| 5 | Firmware fallback: treat a high sample after a power-on reset as indeterminate (no fault) | 14 % | Firmware | $0. This is the "accept 14 %" branch in COMMISSIONING |
| 6 (rejected) | H: delay the HOT-side bias start (RC on the U26 / RECOM EN) | — | Power-board HOT copper | It would need > PS3 setup max (1000 ms) + 475 ms after PS2, against supplies with no published minimum setup. It doesn't cover short dropouts (HOT stays up), it adds ≥ 1.5 s to every HOT start, and it touches the reviewed HOT supply sequencing |

**Sizing of S** (`td` from SBVS050N 6.6: the CT = 180 nF row, 0.62 / 1.03 / 1.44 s, scaled by C per Eq. 1, which is
linear in CT. X7R ±10 % tolerance, ±15 % over temperature, −3 % DC bias are E. Insulation-resistance leakage
≤ 1.2 nA against 220 nA is negligible):

| CT | td min / typ / max (s) | Margin vs app_main sample (≤ 0.488 s after v3v3) | Margin vs bootloader hook (≤ 0.058 s) | BIAS_GOOD ready ≤ (s after PS3 out) |
|---|---|---:|---:|---:|
| CT = VDD (no cap) | 0.180 / 0.300 / 0.420 (G) | −0.308 | +0.122 | 0.45 |
| 100 nF (existing line) | 0.256 / 0.572 / 1.012 | −0.232 | +0.198 | 1.04 |
| 2 × 100 nF (existing line) | 0.511 / 1.143 / 2.024 | +0.023 | +0.453 | 2.05 |
| 330 nF (C107070, Extended) | 0.843 / 1.886 / 3.340 | +0.356 | +0.786 | 3.37 |
| **470 nF (C1623, Basic)** | **1.201 / 2.686 / 4.756** | **+0.714** | +1.144 | **4.78** |
| 1 µF (existing line) | 2.556 / 5.715 / 10.12 | +2.068 | +2.498 | 10.15 |

470 nF gives ≥ 0.71 s against the latest estimated sample, about 2.5× the estimate's own spread, with no firmware
change. The cost is readiness: START within ≤ 4.8 s (2.7 s typical) of mains-on is refused as "NO POWER BIAS" (check
2, not a fault). The UI could show "starting" until BIAS_GOOD rises.

Interface checks:
- TPS3808 VOL ≤ 0.4 V at 1 mA (into R135, 0.35 mA) against LVC1G132 VT− ≥ 0.84 V at 3 V (SCES546E 5.5).
- R135 at 10 k is inside TI's 10 k–1 MΩ pull-up range.
- G33 (VIT 3.07 V, 3.116 V max) is rejected: it leaves only 19 mV under the 3.135 V v3v3 contract, and its 20 µs
  response would see transients that RAIL_OK's 1 ms filter ignores.

How the parts fail (for the FMEA rows to add):
- RESET open or CT open (20 ms) → no or short delay → today's behaviour: a nuisance `BIAS GOOD POST` (announced).
- RESET stuck low, CT shorted, VDD open → BIAS_GOOD never rises → "NO POWER BIAS" (announced).
- An open-drain output can only pull `hsb_good` low, so the part can never hold the wave up. No dormant state is added.

**Firmware additions that go with S** (no copper, recommended):
- (a) Timestamp the sample with `esp_rtc_get_time_us()`. If it is later than a `BIAS_GOOD_POST_LATEST_MS` (for
  example 1000 ms, under td min 1.20 s less C4 max), a high sample is "late / indeterminate" (logged, no fault), so a
  slow boot can never false-fault. A low sample is valid whenever it is taken.
- (b) After a low sample, time the low→high edge from power-up. A rise earlier than ~1.1 s after power-on means the
  delay part is missing (CT open, RESET open). Log it as a warning, so a dormant delay failure shows before it causes a
  nuisance POST.
- (c) Fix the bring-up log timestamp (above).

## What stays for the bench

1. Measure C4 + C5 on the real controller and image: v3v3 → CHIP_PU → a GPIO marker at the sample, 10 cold and 10 hot,
   no USB host attached (the USJ timeout case). Gate: ≤ 1.0 s with S at 470 nF, or ≤ 0.12 s if the CT = VDD
   plus bootloader-hook variant is chosen.
2. With S fitted, measure td at −10 / 25 / 70 °C (expect 1.20–4.76 s) and BIAS_GOOD low at the sample on 20 power-ons
   at the inlet (108 / 120 / 132 VAC). Add short dropouts of 20 ms, 100 ms, 500 ms and 2 s: the sample must read low on
   every power-on-reset boot.
3. For information only (S makes it irrelevant): PS2 and PS3 setup times at 108 / 132 VAC, cold and hot, at the
   board's real light loads. On the s48 board as built, without S, expect `BIAS GOOD POST` whenever PS2 is not
   ≥ 59–475 ms behind PS3, and after short dropouts.
4. The TPS7A47 1 µF start-up figure (65 ms typical) and the RECOM 3 ms only set D_req. Scope V15_LS and P_HA to replace
   the H2 / H3 estimates.

## Scope notes

- Controller path as requested in CONTROLLER-REQUEST items 1, 2 and 12: PS3 → J13 merge → v15_selv → U1 TPS62933F →
  v3v3. The current controller branch (`controller-c1-crs` at C47) still takes 15 V on J4.1, so with an s48 board it is
  unpowered. The check is inert today: `CTRL_GPIO_BIAS_GOOD_RB` is undefined, so it reads NOT_FITTED. **Don't land
  the GPIO35 routing without S or fallback 5.** Otherwise the POST would latch on a unit-dependent share of power-ons.
- The TPS3823-33 (U21) is the interlock watchdog and does not reset the ESP32. ESP EN is the R / C only
  (controller.ato `r_en` / `c_en`).
- Sources fetched for this lane are in `ds/` (gitignored scratch, not committed):
  - TPS3808 SBVS050N rev. Aug 2026;
  - TPS62933 SLUSEA4D;
  - TPS7A47 SBVS204G;
  - ESP32-S3 datasheet v2.2 (sha256 2d5a7cb7fd559d8d…).

  Read in place:
  - MPM-20-SPEC (sha256 24d3a6bb…) and MPM-65-SPEC (3d324f12…);
  - R24C2T25/R Rev.1-2024;
  - CA-IS3720 v1.08;
  - SN74LVC1G132 SCES546E and TPS709 SBVS186H (`c24-monitor-fmea/evidence/ds`);
  - IDF v5.3.6 at `~/esp/esp-idf-v5.3.6`;
  - JLC records in `scripts/jlc-raw/` (fetched 2026-10-16).
