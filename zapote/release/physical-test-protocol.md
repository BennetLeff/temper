# Staged assembled-cooker test record — template only

**Campaign status: NOT_RUN. No stage below has been performed.** A qualified
test owner must adopt limits, fixtures and safe-work procedures before use.
This template does not authorize mains or high-voltage energization.

## Article and campaign identity (unfilled)

| Field | Record before testing |
| --- | --- |
| Assembled article/serial/rework history | NOT_RECORDED |
| Frozen integrated PCB SHA-256 and source revision | NOT_RECORDED |
| Firmware binary SHA-256, build settings and programming receipt | NOT_RECORDED |
| Exact BOM revision, part lots and assembly record SHA-256 | NOT_RECORDED |
| Enclosure, coil, pan, fan and thermal-interface identities | NOT_RECORDED |
| Test owner, independent reviewer and adopted limits | NOT_RECORDED |
| Instruments, calibration dates, ranges and uncertainty | NOT_RECORDED |
| Fixture schematics, isolation, current/energy limits and emergency stop | NOT_RECORDED |

For **each** stage retain: stage/article IDs, prerequisite receipt hashes,
source and firmware hashes, instrument/settings/calibration/uncertainty,
raw waveform/log file SHA-256, observed extrema and units, adopted acceptance
limit and margin, stop event/time, operator/reviewer, deviations, corrective
action revision, and full retest chain. A photo or summary number without raw
data and identity is not a passing record. A failed stage holds all later
stages. No restart or rearm may occur automatically after a stop/fault.

## Stage ledger

| Stage | Current status | Required entry evidence | Measurements and stop criteria |
| --- | --- | --- | --- |
| 0. Article inspection and isolation | NOT_RUN | Frozen board/BOM/firmware identities; qualified instrument and visual inspection procedure | Net/domain continuity and isolation under adopted limits; inspect assembly, barriers, solder, heat paths. Stop on short, damage, discrepancy or indeterminate isolation. |
| 1. Current-limited low-voltage rails | NOT_RUN | Stage 0 reviewed pass; isolated supply and current limit; power stages physically prevented from switching | Rail order, regulation, load/start/dropout, watchdog and fault defaults. Stop on unintended stage enable, overcurrent, rail collapse or thermal rise. |
| 2. Isolated energy-limited HV DC | NOT_RUN | Stages 0–1 reviewed pass; **measured default-off on control loss and independently verified VD and VB stop/discharge paths**, each under adopted time/voltage/energy limits; known C and safe measurement path | Apply only an approved energy-limited isolated DC fixture. Record VD and VB separately, F2 open/closed, supply loss, control loss, commanded stop, residual energy and service holdoff. Stop on unexpected rise, failed stop, discharge timeout, rearm or measurement ambiguity. |
| 3. Controlled PFC | NOT_RUN | Stage 2 pass; reviewed mains fixture/protection, precharge, bus ceiling and independent stop; safe enclosure and personnel controls | Input, inrush, precharge, F2, VB/VD, PFC switching, fault and restart behavior across declared line/load corners. Stop on overvoltage/current, protection disagreement, lost sensing or unsafe residual energy. |
| 4. Loaded inverter and pan | NOT_RUN | Stage 3 pass; qualified gate drive, tank/coil, loaded pan envelope, current sensing and cooling | Coil/pan current, VB/VD, switch stress, PERMIT loss, rail loss, pan removal, no-pan and stop-to-current-zero timing. Stop on device/cap limit, uncontrolled heating or continuing oscillation. |
| 5. Thermal endurance | NOT_RUN | Stage 4 pass; selected fan/rail, airflow and sensor-lag evidence | Device, bridge, shunt, board, coil, enclosure and discharge heat; fan-off/stall/blocked-flow cases with uncertainty and trip window. Stop on any adopted limit, sensing invalidity, insufficient margin or failed cooling fault response. |
| 6. Cross-unit faults, restart and service | NOT_RUN | Stages 0–5 pass; approved fault-injection fixture and recovery policy | Sensor-open/short, interlock, watchdog, AUX/bias/fan loss, F2 open, control reset, power interruptions, VD/VB discharge and service access. Stop on any unexpected power command, fault masking, automatic rearm or live accessible energy. |

## Correction and retest chain (unfilled)

| Finding ID | Raw record SHA-256 | Stop time/state | Cause and corrective revision | Affected earlier stages | Full retest receipts | Independent disposition |
| --- | --- | --- | --- | --- | --- | --- |
| NOT_RECORDED | NOT_RECORDED | NOT_RECORDED | NOT_RECORDED | NOT_RECORDED | NOT_RECORDED | NOT_RECORDED |

The stage ledger is deliberately all `NOT_RUN`. Hand-entering `PASS` here does
not alter the machine release gate or qualify hardware.
