# Manufacturer-reference benchmark for the PFC switching model

**Result: INSUFFICIENT EVIDENCE.** Two independent manufacturer references provide
measured whole-board operating points, but neither publishes a source-bound
MOSFET `vDS/iD/vGS` switching capture with the event current, gate current,
temperature, and time axes needed by `pfc_switching`. The references therefore
check architecture and whole-board loss only; they do not validate the Rust
switching-energy result.

## Primary sources and measured points

TI's TIDA-00779 design guide, TIDUBE1D Rev D (August 2024), is captured as
`TIDUBE1D.pdf` (SHA-256
`1f2abaf8f7460ec110186d59f3d01624bdbd260d57ae7b7b698d0754c717d465`). Printed
page 9, Table 3-1, reports a 230-V test with a Yokogawa WT500. A high-load row
is 226.62 VAC, 14.680 A, 3314.7 W input, 381.55 V/8.497 A/3242.4 W output,
97.820% efficiency; the full-load row is 226.07 VAC, 16.775 A, 3778.5 W in,
381.17 V/9.686 A/3692.1 W out, 97.714%. The reported losses are respectively
72.3 W and 86.4 W (`Pin - Pout`). The same guide specifies 45 kHz switching,
180 uH boost inductance, a 15-V bias, IPW60R099P6, and a 22-ohm gate resistor
with an antiparallel diode (printed pages 5-6). It lists UCC27524 5-A source and
5-A sink peak ratings (p. 4), but those are ratings, not measured gate-current
waveforms. The guide names Q1/Q6 and D1/D3; the populated parallel-device
configuration must be resolved from its schematic/BOM before any per-device
model comparison. No single-switch population is assumed here.

One Table 3-1 row (227.33 VAC, 2513.6 W in, 2560.7 W out) is internally
inconsistent (`Pout > Pin` despite a printed 97.974% efficiency); it is excluded
from the calculations above rather than silently treated as a measured loss.

Infineon's AN201408, `EVAL_2.5KW_CCM_4PIN`, Revision 1.3 (2026-01-20), is
available as a primary web PDF but CloudFront returns an AWS-WAF 202 response to
the reproducibility environment; no local bytes or honest SHA-256 are claimed.
The exact URL and page identity are in `SOURCES.md`. PDF page index 18 (the
19th PDF page), Table 2,
states that all tests use a 60 C heatsink and direct voltage sensing. At 100 kHz
with IPZ60R040C7 in the 4-pin configuration, the 230-V full-load row is
229.56 VAC, 11.178 A, 2561.5 W in, 401.15 V/6.235 A/2500.9 W out, 97.6342%
(60.6 W whole-board loss). Low-line rows are 84.61 V/8.924 A/753.7 W in to
716.8 W out (95.104%, 36.9 W loss) and 84.31 V/15.215 A/1280.2 W in to
1197.6 W out (93.548%, 82.6 W loss). The board BOM identifies the 1EDI60N12AF
6-A isolated driver, and the efficiency figures identify a 3.3-ohm gate test
setting (pp. 14 and 20). These are board measurements, not per-event switching
energy measurements.

The IPZ60R040C7 datasheet gives useful source anchors in the web-rendered
primary PDF: `Qg=107 nC`, `Qgd=36 nC`, `Qgs=22 nC`, `Vplateau=5.0 V`,
`Rg=0.77 ohm`, and `RDS(on)=40 mOhm max at 10 V, 24.9 A, 25 C` (datasheet
pp. 4-6). It also gives `Co(er)=158 pF` over 0--400 V; the simple inferred
`0.5*Co(er)*400^2 = 12.64 uJ` is an input candidate, not a measured switching
energy. The PDF bytes were also WAF-blocked, so this source is web-parsed only.

## What the Rust model can and cannot observe

`zapote-erc::pfc_switching` requires bus voltage, switching frequency, separate
turn-on/off event currents, switch RMS current, gate bias, Qg/Qgd, explicit
current-transfer charge, plateau voltage, external and intrinsic gate resistance,
driver source/sink peak limits, Eoss, loop inductance, and RDS(on). The references
provide bus/output voltage, frequency, nominal driver supply, board gate resistor,
device charge/static anchors, and whole-board Pin/Pout. They do **not** provide:

* phase-resolved switch event-current moments or duty-weighted switch RMS;
* measured gate-current I-V curves or actual plateau/transfer charge at the
  board's instantaneous current;
* simultaneous, de-embedded VDS/VGS/ID transition waveforms and junction
  temperature; or
* commutation/diode recovery, loop inductance, ringing, or per-device loss.

Consequently, substituting input RMS current for the model's event currents would
be a category error. Likewise, a 12-V/15-V bias label is not a measured gate-high
or plateau waveform, and a 5-A/6-A driver headline is not a dynamic source/sink
impedance.

## Comparison with the maintained experiment

The retained experiment-02 C7 case is IPW65R045C7 at 120 Vrms, 400-V bus,
129.107 kHz, 15-A input RMS, 12-V driver, and 4.7-ohm external resistance.
Its source-bound conditional totals are 37.7767 W (full-assist), 45.5023 W
(no-assist), and 53.4723 W (DC-max); the report's event currents are 11.927 A
turn-on, 15.027 A turn-off, and 11.999 A switch RMS. Those numbers are useful
for software regression only. They do not match either reference: TI uses
IPW60R099P6 at 230-V class input and 45 kHz; Infineon uses IPZ60R040C7 at
230-V/100 kHz and a 60 C heatsink. No manufacturer point is a valid same-case
holdout for the current Rust model.

Whole-board loss can be a falsification check only after all inputs and the same
device/test point are matched: a nonnegative model MOSFET-plus-gate loss above
measured `Pin-Pout` cannot be true for that board. The present references do not
meet that condition, so no contradiction or validation is claimed.

## Next discriminating experiment

At one reference operating point, capture `VDS`, `VGS`, and drain current with
the same time base, while recording gate supply, gate resistor/jumper state,
heatsink and junction-temperature proxy, line phase, bus voltage, and switching
frequency. Integrate `vDS*iD` over individually identified turn-on and turn-off
events, repeat across at least three phase-current levels, and report probe
bandwidth/de-embedding uncertainty. Feed those measured event moments and Eoss
into the current Rust API without fitting unknown charge or resistance. Until
that receipt exists, the bounded claim is **architecture/whole-board reference
only; switching-model validation remains indeterminate**.
