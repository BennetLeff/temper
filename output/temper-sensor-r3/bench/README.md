# sensor-r3 bench kit: cookware contact survey

This kit decides whether C1 stands. Every pan must give a C1-equivalent dry
τ63 of **≤ 1.2 s**; any pan above **1.35 s** means stop. Both lines come
from `../DECISIONS.md` §5.

| File | What |
|---|---|
| `RIG.md` | Surrogate probe, jig, pan reference, logger hardware, set-up checks, cost |
| `PROCEDURE.md` | Cookware set (15 pans, 6 classes), conditions, calibration, set-down steps, decision rule, safety |
| `DECISIONS.md` | Choices D1–D11 |
| `fit.py` | Fit, calibration, survey verdicts, and `--selftest` (synthetic end-to-end, about 35 s) |
| `logger.py` | Host logger (pyserial); `--selftest` checks the parser |
| `logger_fw/logger_fw.ino` | ESP32-S3 firmware for the MAX31865 + MAX31856 (Arduino core) |
| `jig.py` | build123d geometry → `jig-post.step`, `jig-holder.step`, `jig.json` (stack-up checks) |
| `surrogate.py` | Disc options vs C1 → `surrogate.json` |
| `bom.py` | Estimated BOM → `bom.json` (about $1,285) |
| `probe.example.json` | Probe constants template. Copy it to `probe.json` and measure the values. |
| `datasheet_template.csv` | Per-pan record |

## Order of work

1. Order the parts (`bom.py`). The disc lot is a quote item.
2. Machine the jig from the STEP files.
3. Build the probe and run the set-up checks (RIG §3).
4. Paste calibration: `python fit.py calibrate …`.
5. Survey set-downs: `python logger.py …`, then `python fit.py run …`.
6. `python fit.py survey runs/` gives the per-pan and overall verdicts.

## Rerun

| Command | Environment |
|---|---|
| `python3 fit.py --selftest` | numpy and scipy |
| `python3 logger.py --selftest` | |
| `python3 surrogate.py` | |
| `python3 bom.py` | |
| `cadenv/bin/python jig.py` | build123d 0.11.1; recipe in `../cad/DECISIONS.md` |
