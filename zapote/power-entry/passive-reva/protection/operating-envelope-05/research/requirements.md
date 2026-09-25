# Temper power-entry / F2 operating-envelope research

Revision inspected: canonical checkout `/private/tmp/temper-pkgs-1-4`, branch
`codex/power-entry-pkgs-1-4`, HEAD `5dde29ab3e2f1223c2d33c129ced2cf647238307`.
Instructions read: root `AGENTS.md` and `zapote/AGENTS.md`. No repository files
were changed; this report is the only output.

## Authority and classification

For the next passive Rev A integration, use `zapote/power-entry/passive-reva/MILESTONE.md`
and `README.md`, the current passive source, and `INTERFACES.md` as the product
baseline. The `f2-shutdown-04` directory is immutable simulation evidence, not a
hardware or product-limit authority. Numeric values below are labelled as
requirements, source configuration, model assumptions, or measured observations.
Component absolute ratings are not promoted into allowed operating limits.

## Operating-envelope rows

| Quantity | Current value / status | Classification and exact authority |
|---|---|---|
| Mains nominal | **120 VAC RMS** | Product baseline requirement: `zapote/power-entry/passive-reva/MILESTONE.md:17`; current interface also says 120 VAC: `zapote/power-entry/INTERFACES.md:5-8`. |
| Mains design envelope | **108–132 VAC RMS** | Product baseline requirement for the next passive milestone: `zapote/power-entry/passive-reva/MILESTONE.md:17-19`. The source/protection review separately requires 108–132 Vac loading/startup/dropout evidence but does not qualify it: `zapote/power-entry/passive-reva/INTERFACE-DESIGN.md:64-70`. |
| Mains frequency | **60 Hz nominal; 59–61 Hz assertion exists only in legacy full-cooker source** | 60 Hz is an explicit PFC calculation assumption at `zapote/power-entry/evidence/pfc-control-calculation.md:14-18`. The 59–61 Hz range is from the legacy doubler top level `elec/src/main.ato:62-69`; it is not an independent PFC product requirement. |
| Input current | **15 A RMS ceiling** | Product baseline requirement: `zapote/power-entry/passive-reva/MILESTONE.md:17-19`; current interface repeats the bound: `zapote/power-entry/INTERFACES.md:13-15`. Low-line foldback is required and remains open: `zapote/power-entry/ACCEPTANCE.md:20-25`, `zapote/power-entry/pfc-source-manifest.json:18-25`. |
| Nominal power | **1,800 W nominal AC-input class at 120 VAC** | Product class, not a delivered-power or qualification claim: `zapote/power-entry/README.md:29-31`; `zapote/power-entry/PFC-ARCHITECTURE.md:9-15`. At PF 0.99 the documented real input is **1,782 W**, with lower output after losses: `zapote/power-entry/INTERFACES.md:13-15`. |
| Continuous / burst power | **No accepted continuous or burst rating found** | The 1,800 W statement is a nominal class/current-limit point. Low-line behavior, thermal, ripple, startup and fault evidence remain open: `zapote/power-entry/ACCEPTANCE.md:20-26`; `zapote/power-entry/README.md:52-57`. Do not invent a burst envelope. |
| Low-line reachable power | **1,617.1 W ideal-model input at 108 VAC/15 A; 179.3 W shortfall to the 1,796.4 W model point** | Conditional ideal CCM model, not product requirement or measurement: `zapote/power-entry/loss-budget/RESULTS.md:53-67` and the caveat at `:83-90`. |
| PFC bus nominal | **389.615 V (documented interface); source net label `PFC_BUS_PLUS_390V`** | Current nominal setpoint only, not a worst-case envelope: `zapote/power-entry/INTERFACES.md:11-12,22-26`; source override at `elec/src/power_entry_unit.ato:473-482`. The PFC control calculation rounds this to 390 V: `zapote/power-entry/evidence/pfc-control-calculation.md:14-21`. |
| PFC bus allowed range | **Unknown / unclosed** | The interface explicitly says bus-envelope evidence is still INDETERMINATE: `zapote/power-entry/INTERFACES.md:22-26`. Do not use 450 V capacitor rating (`elec/src/power_entry_unit.ato:138-146`) or 650 V switch/diode ratings as an allowed bus range. |
| Legacy bus conflict | **340 V nominal, 280–380 V range in old doubler top-level** | Legacy full-cooker configuration: `elec/src/main.ato:48-69`. It conflicts with the standalone active-PFC 389.615/390 V bus. The current interface says legacy split-bus consumers are not accepted: `zapote/power-entry/INTERFACES.md:28-32`. |
| PFC switching frequency | **130 kHz nominal design point (conditional)** | PFC control calculation assumes 130 kHz and derives `RFREQ ≈ 16.2 kΩ`; actual assembled frequency must be verified: `zapote/power-entry/evidence/pfc-control-calculation.md:33-36,45-54`. Current passive source sets `r_freq = 16.2 kΩ` as a starting value and labels compensation/current limit unqualified: `elec/src/power_entry_passive_reva.ato:282-300`. The source manifest calls 130 kHz pending hot/core-loss verification: `zapote/power-entry/pfc-source-manifest.json:9-25`. |
| Alternate model frequency | **129.107 kHz** | Nominal value used by the loss-budget model at 120 Vrms/15 A/180 µH: `zapote/power-entry/loss-budget/RESULTS.md:7-18,42-48`. This is a model input, not a measured controller frequency. |
| PFC boost inductance | **180 µH nominal in current passive source; source field 24.5 A** | Current source configuration: `elec/src/power_entry_passive_reva.ato:65-71`; current passive loss model also uses nominal 180 µH: `zapote/power-entry/loss-budget/RESULTS.md:7-14`. |
| Lboost tolerance / fault bounds | **No qualified L(I,T) bounds** | F2 timing uses **100 µH minimum / 216 µH maximum** only as an explicit simulation assumption, with nominal 180 µH: `zapote/power-entry/passive-reva/protection/f2-timing-02/README.md:58-61,65-93`; F2-04 cases instantiate 100/180/216 µH: `zapote/power-entry/passive-reva/protection/f2-shutdown-04/plant/run_cases.sh:56-75`. The audit warns 180 µH ±20% is small-signal and the 43 A saturation value is typical, not a clamp or guaranteed hot limit: `zapote/power-entry/passive-reva/protection/f2-timing-02/README.md:58-61,92-94`. |
| Stale active-PFC inductor identity | **150 µH / 30 A IHV30EB150 at 130 kHz, pending** | Historical active manifest only: `zapote/power-entry/pfc-source-manifest.json:9-12,18-25`. The mechanical audit says IHV30EB150 is limited to 20 kHz and unsuitable for 130 kHz, while the selected frequency-capable replacement is Würth 760800301, 180 µH ±20%: `zapote/power-entry/evidence/parts-mechanical-audit.md:19-48`. Do not mix the 150 µH manifest with the current passive baseline. |
| Cooling inlet / ambient | **40 °C cooling-inlet target** | Current passive milestone requirement: `zapote/power-entry/passive-reva/MILESTONE.md:20-21`. The proposed qualification protocol samples 25 °C and 40 °C ambient and then a specified maximum ambient, but does not define that maximum: `zapote/power-entry/passive-reva/cooling/qualification-protocol.md:20-37`. |
| Component-temperature limits | **Not yet a product operating envelope** | Passive cooling acceptance proposes board contacts <110 °C, bridge terminals <95 °C, and qualified junction estimate <125 °C, but only for a measured exact assembly: `zapote/power-entry/passive-reva/cooling/qualification-protocol.md:39-60`. The 40 W bridge allowance and 110.6 W shared screen are explicitly assumed design inputs, not measured limits: `zapote/power-entry/passive-reva/cooling/thermal-budget.json:27-46`. Original `elec/src/constraints.ato:111-130` values (175 °C IGBT absolute/125 °C derate, etc.) belong to the legacy constraint set and are not a PFC qualification envelope. |
| PFC current-limit threshold | **40 A nominal controller PCL; conditional 44.562 A threshold under stated shunt assumptions** | F2 timing audit derives 40 A typical, 43.8 A at the electrical maximum threshold, 44.242 A with 1% shunt tolerance, and 44.562 A with an assumed −40…100 °C shunt/TCR case; it explicitly says this is not an instantaneous maximum: `zapote/power-entry/passive-reva/protection/f2-timing-02/README.md:27-47`. The audit says 40 A is nominal, not maximum fault current: `:1-11`. |
| Firmware current interlocks | **40 A software over-current trip; 50 A IGBT-short latch** | Firmware configuration, not the PFC input limit: `firmware/config.yaml:272-299`. The file itself says 40 A is a peak interlock layered above a 15 A RMS/1,800 W operating point and that 50 A is uncited; do not treat either as product continuous current. |
| F2-04 bus / timing screen | **Provisional 500 V screen, 2 µs target; nominal simulation only** | The F2 timing audit calls 500 V provisional and 2 µs a design target with little margin: `zapote/power-entry/passive-reva/protection/f2-timing-02/README.md:63-68,102-106`. F2-04 reports accepted simulated bus peaks below 478 V and current-at-opening 41.658/46.228/51.095 A, but marks all as local surrogate-model observations: `zapote/power-entry/passive-reva/protection/f2-shutdown-04/README.md:15-26,37-45`; `claims.json:172-185`. |
| F2 hardware status | **Not installed; no hardware qualification** | Current passive README says F2, holder and film reservoir are not in CAD/BOM: `zapote/power-entry/passive-reva/README.md:1-21`. F2-04 is a 79-component simulation candidate and explicitly not an assembled-board change: `zapote/power-entry/passive-reva/protection/f2-shutdown-04/README.md:9-13,37-45`; circuit README `:1-6`. |

## Conflicts and recommended planning baseline

1. Freeze the next plan to the current passive product baseline: **120 VAC nominal,
   108–132 VAC design envelope, 60 Hz nominal assumption, 15 A RMS input ceiling,
   389.615 V nominal single PFC bus, 40 °C cooling-inlet target, 180 µH nominal
   boost inductor, and 130 kHz nominal PFC design point**. Mark 130 kHz and 180 µH
   as conditional until assembled-frequency and hot magnetic measurements exist.
2. Treat **1,800 W as nominal AC-input class**, not continuous delivered power; at
   low line the model only reaches 1,617.1 W under the 15 A ceiling. No burst rating
   is currently authoritative.
3. Do not carry the legacy 340 V doubler range into this PFC/F2 work. Do not turn
   450 V capacitor, 500 V F2 screen, or semiconductor ratings into an allowed bus
   range. First define an authoritative bus envelope from controller regulation,
   line/surge/transient conditions, capacitor tolerance/temperature, and downstream
   load behavior.
4. Keep current quantities separate: 15 A RMS input, 40 A nominal UCC28180 PCL,
   firmware 40/50 A interlocks, and F2 simulation 40–50 A opening cases are different
   quantities. The F2 timing audit says the actual peak and complete detector-to-
   switch-off maximum remain unknown.
5. Before an F2 ECO or powered test, Luna should close (a) exact detector threshold
   and worst-case latency through gate-current cessation, (b) L(I,T), bus capacitance
   and line/fault envelope, (c) F2 DC capacitor-discharge clearing/let-through and
   holder/interconnect withstand, (d) failed-short U9/U10 paths, and (e) restart,
   precharge and active-discharge behavior. F2-04's 0.749/1.536 µs detector results,
   0.505 µs controlled turnoff and <478 V simulated peaks are regression evidence for
   its surrogate, not acceptance limits.
6. For thermal planning, bind losses and installed airflow to the exact GBJ/STW
   assembly. Keep 40 °C inlet as the planning target; leave maximum ambient,
   component-case/junction envelope, and continuous/burst duration as explicit
   unknowns until the qualification protocol is completed.

These findings support planning and delegation only. They do not claim hardware
qualification, mains safety, protection coordination, or an authorized powered run.
