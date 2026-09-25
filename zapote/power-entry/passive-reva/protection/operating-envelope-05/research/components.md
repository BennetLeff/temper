# Temper passive-reva / F2-shutdown-revB component envelope

Source revision reviewed: `5dde29ab3` (`/private/tmp/temper-pkgs-1-4`).  The
electrical source is `elec/src/power_entry_passive_reva.ato`
(MOSFET/diode/inductor/bulk bank at lines 65--156; connections and net names at
227--403) plus
`zapote/power-entry/passive-reva/protection/f2-shutdown-04/source-07/elec/src/power_entry_f2_shutdown_revb.ato`
(detector/driver at lines 193--552).  The accepted 79-part export is
`zapote/power-entry/passive-reva/protection/f2-shutdown-04/source-07/resolved-components.json`.

The retained loss/cooling evidence says this is a screening model, not a
qualification: nominal 120 Vrms, 15 Arms ceiling, ~389.6 V bus, 129.1 kHz,
180 uH boost L, and 105 W is only a prior cooling allowance.  In the archived
waveform screen, switch RMS is about 11.6--12.3 A, diode RMS 8.65--9.56 A,
rectified mean 13.46--13.49 A, and mean turn-off current reaches 15.45 A
(`zapote/power-entry/loss-budget/evidence/pfc-loss-simulation-2026-09-17.json`).
The loss report remains `indeterminate`; MOSFET overlap/hot RDS(on), diode
waveform, inductor AC/core loss, capacitor HF ESR, PCB/fuse/contact loss and
total cooling are explicitly open
(`zapote/power-entry/loss-budget/evidence/correction-02/loss-report.json`).

## Verified ratings and bounded use

| item in retained circuit | manufacturer rating / specified condition | bounded design interpretation | derating or unknown |
|---|---|---|---|
| **STW65N65DM2AG** boost MOSFET | 650 V breakdown; absolute continuous ID 60 A at TC=25 C and 38 A at TC=100 C; ±25 V VGS; Tj −55..150 C; RDS(on) typ 42 mΩ/max 50 mΩ at VGS=10 V, ID=30 A, TC=25 C; RthJC 0.28 C/W. Dynamic typ: Coss=210 pF at 100 V/1 MHz, **Coss(eq)=456 pF for VDS 0→520 V**, Qg=120 nC at VDD=520 V, ID=60 A, VGS=0→10 V, Qgd=58 nC. [ST product page](https://www.st.com/en/power-transistors/stw65n65dm2ag.html) · [ST datasheet](https://www.st.com/resource/en/datasheet/stw65n65dm2ag.pdf) | 389.6 V bus is below 650 V static rating, but switching overshoot must be measured. Use 0.05 Ω only as a 25 C/30 A test-point maximum; use hot RDS curve/measurement for loss. Qg 120 nC is a typical, condition-specific number; do not use as a guaranteed corner. | **Coss(eq) is a time-equivalent capacitance, not Eoss.** Eoss must come from the ST curve or measured VDS waveform; do not calculate `0.5*Coss*V²` from 456 pF as a claimed loss bound. Gate-source drive must stay within ±25 V and thermal path must establish Tj; RthJC alone is not an assembly limit. |
| **C3D20065D** dual-die common-cathode SiC diode | 650 V VRRM/VRSM/VDC; IF continuous 27.5 A per leg/55 A device at TC=25 C, 13/26 A at TC=135 C, 10/20 A at TC=149 C; IFSM 90 A/leg at TC=25 C (10 ms half sine), 71 A at 110 C; Tj/Tc −55..175 C. VF max 1.8 V at 10 A, 25 C and 2.4 V at 10 A, 175 C; QC typ 24 nC at VR=400 V, IF=10 A, di/dt=500 A/us; no reverse-recovery charge; Ec typ 3.6 uJ at 400 V. RthJC typ 1.3 C/W/device or 0.65 C/W/leg (footnote interpretation must be retained). [Wolfspeed datasheet](https://assets.wolfspeed.com/uploads/2023/12/Wolfspeed_C3D20065D_data_sheet.pdf) | 389.6 V bus is below 650 V. The 15 Arms input screen does not establish diode peak/average current or junction temperature; use the actual CCM waveform and two-die current sharing. | VF points are only at 10 A and are not a full hot curve. QC/Ec are single-condition typicals, not guaranteed per-cycle loss. Package-to-heatsink/contact and per-leg heat split remain unqualified. |
| **Lboost = Würth 760800301** (selected in passive-reva) | 180 uH ±20% at 100 kHz/100 mV; RDC ≤20 mΩ at 20 C; IR=24.5 A for ΔT=40 K without fan (IR2=48 A at 4 m/s); Isat 43 A typ for ΔL/L<30%; 1000 Vdc; −40..155 C. [Würth datasheet](https://www.we-online.com/components/products/datasheet/760800301.pdf) | Retain 180 uH nominal for the 129 kHz model. The modeled 15 Arms input and ~15.5 A turn-off mean are below the published current-screen values, but this is not a measured waveform or saturation proof. | 20 mΩ is cold DC only. Hot copper loss, core loss and actual ripple/temperature must be measured or modeled from vendor curves; no 130 kHz loss rating is published. Fault-current L(I,T) and saturation under worst-case startup/short are unknown. |
| **Bulk bank: 4× Nichicon LGX2W561MELC50** | 450 V, 560 uF each, ±20% at 120 Hz/20 C; rated ripple 1,980 mArms at 105 C/120 Hz; category −25..105 C; 5,000 h at 105 C/rated ripple. [Nichicon LGX PDF](https://www.nichicon.co.jp/products/pdfs/lgx.pdf) | Nominal 2,240 uF at 450 V; 389.6 V nominal bus leaves only ~60 V static headroom. | 120 Hz ripple rating cannot be applied to 129 kHz switching ripple. ESR, HF current sharing, ripple heating, tolerance and transient overshoot are unbound. Do not credit 4×1.98 A as a guaranteed HF rating. |
| **C_hf: TDK/EPCOS B32672P6474K000** | 470 nF ±10%, 630 Vdc, 200 Vrms, max dV/dt 180 V/us, PP boxed radial, 8×14×18 mm, 15 mm pitch, AEC-Q200. [TDK product page](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32672P6474K000) | 630 V is a static margin over the nominal bus only; place at the switch/diode loop as drawn. | Exact-part ESR, dissipation factor and RMS-current capability at 129 kHz are not given on the product page; no HF loss bound. dV/dt is not an energy or fault-current rating. |
| **F1 link / holder**: Schurter 0034.3129 in FUP 0031.2510 | FST 5×20 pigtail 0034.3129: 16 A, 250 Vac, 10×In test, 3,300 A²s pre-arcing value shown in the [official FST table](https://www.schurter.com/en/datasheet/typ_fst_5x20_pigtail.pdf). FUP 0031.2510 holder: 5×20, 16 A VDE/500 Vac (600 V UL/CSA), 4 W at 16 A/Ta 23 C, −40..85 C, contact resistance ≤10 mΩ. [official holder page](https://www.schurter.com/de/part/0031.2510) | This is an AC-input fuse/holder; it does not bound the DC-link/F2 fault current. The 16 A nominal link is close to the 15 Arms design ceiling and needs time-current/inrush coordination. | Prospective mains short-circuit, let-through/I²t at the actual system, holder derating, arc interruption, and PCB/terminal temperature are not qualified. Never use the 3,300 A²s table value as a DC bus fault bound. |
| **F2 supervisors: 2× TPS389001DSER** | Recommended VDD 1.5..5.5 V; VSENSE/RESET 0..5.5 V; CT 0..22 uF; RESET current ±5 mA; TJ −40..125 C. SENSE threshold accuracy ±1% (typ ±0.5%), hysteresis 0.325..0.825%; tPD(f) max 18 us at 3.3 V/8 us at 5.5 V, tPD(r) max 25 us (CT open); CT charge 0.90..1.35 uA, VCT 1.17..1.29 V. [TI datasheet](https://www.ti.com/lit/ds/symlink/tps3890.pdf) | ATO dividers are 294 k/100 k for logic5 (nominal trip ~4.53 V) and 1.03 M/100 k for aux (~12.9 V), with 100 pF CT and 47 k sense isolation. These values are design intent, not verified trip corners. | The circuit's claimed ~132 us reset-release hold is an RC/threshold calculation and must be checked with tolerance, leakage and the actual CT current. Operation below 1.5 V VDD is not specified; do not promote LVC “Ioff” behavior into a timing guarantee. |
| **F2 logic: SN74HCS21PWR AND + SN74HCS74PWR latch** | TI HCS family: 2..6 V operation, Schmitt inputs, ±7.8 mA output at 6 V, −40..125 C. [HCS21](https://www.ti.com/product/SN74HCS21) · [HCS74](https://www.ti.com/product/SN74HCS74/part-details/SN74HCS74PWR) | Logic5 should be constrained to the family's 2..6 V range (nominal 5 V). Health/clear/run behavior is valid only while both devices are within this range. | Threshold, propagation and power-up/down behavior must be checked at the actual 5 V rail, temperature and RC loads. The 100 nF bypass parts are not a substitute for supply-ramp characterization. |
| **F2 partial-power barriers: SN74LVC1G08DBVR + SN74LVC1G17DBVR** | 1.65..5.5 V VCC, inputs up to 5.5 V, Ioff partial-power-down/back-drive protection, −40..125 C; ±24 mA (3.3 V) class output. [LVC1G08](https://www.ti.com/product/SN74LVC1G08) · [LVC1G17](https://www.ti.com/product/SN74LVC1G17) | Ioff supports a powered-down interface, but only within the datasheet's Ioff test/use conditions. Keep logic5 in range during asserted-operation checks. | Below VCC(min), logical function/timing is unqualified even if pins remain protected. Verify no external ARM/PERMIT source can exceed the 5.5 V pin limits during reverse rail order. |
| **F2 comparator: TLV3202IDR** | 2.7..5.5 V supply, −40..125 C, push-pull dual comparator; 40 ns typ propagation, input common-mode −0.2..5.7 V. [TI product page](https://www.ti.com/product/TLV3202) · [datasheet](https://www.ti.com/lit/ds/symlink/tlv3202.pdf) | Use only on logic5; 22 k input isolators limit charged-bus injection as intended by the source comments. | Comparator input absolute/current limits, saturation recovery and behavior while logic5 collapses need an adversarial rail-order test. “Sub-microsecond” aux-loss claim is not established by the 40 ns typical figure. |
| **F2 driver: UCC27511ADBVR** | Absolute VDD −0.3..20 V; recommended 4.5..18 V; input −5..18 V; source/sink peak 4 A/8 A (0.5 us pulse), continuous source/sink abs max 0.3/0.6 A; UVLO VON max 4.65 V over −40..140 C, VOFF max 4.35 V; TJ −40..150 C abs / operating −40..140 C. Outputs held low in UVLO and when inputs float. [TI product page](https://www.ti.com/product/UCC27511A) · [datasheet](https://www.ti.com/lit/ds/symlink/ucc27511a.pdf) | Driver VDD is `aux` (nominal 15 V in passive-reva context); keep it 4.5..18 V in any guaranteed gate-drive operating point. The ATO 1 kΩ IN− pull-up gives 18 mA at 18 V and 0.324 W in the resistor at that extreme, so the selected 1210 resistor must be checked for pulse/temperature. | 4/8 A are peak pulse capabilities, not a continuous gate current. Actual gate waveform, Miller plateau, VDS overshoot and switching energy are unqualified. The “default-off” topology is structurally specified but must be tested through aux/logic brownout and input reverse order. |
| **F2 disable NMOS: BSS138** | The retained exact source is [Nexperia BSS138 datasheet](https://assets.nexperia.com/documents/data-sheet/BSS138.pdf), but its exact SOT-23 suffix data was not independently recovered in this checkout. | IN− pull-down current is only the 1 kΩ pull-up path; it is a small-signal switch, not a power path. | RDS(on), VDS, current and temperature limits for the exact BSS138 order code remain unverified; do not borrow values from BSS138PW or another suffix. |
| **LM4040A25IDBZR reference** | 2.5 V fixed shunt; TI lists minimum regulation cathode current 45 uA (80 uA over full range for the A25I family), −40..125 C, up to 15 mA operating current. [TI LM4040 page](https://www.ti.com/product/LM4040) · [datasheet](https://www.ti.com/lit/ds/symlink/lm4040.pdf) | The 10 kΩ bias from logic5 provides ~250 uA at 5 V before reference voltage, plausibly above the minimum. | Exact tolerance/temperature grade and cathode current under comparator loading must be included in trip-corner analysis. |

## Decisive bounded next checks

1. **Power-stage operating envelope:** measure or simulate worst-case line (108/120/132 Vrms), bus regulation, current limit and PWM duty with the real controller. Record MOSFET/diode peak and RMS currents, VDS/VF waveforms, gate voltage and switch-node overshoot at hot and cold corners. Do not treat the 650 V ratings as a transient allowance.
2. **Inductor L(I,T) closure:** obtain the exact 760800301 inductance-vs-current/temperature and core-loss data or bench-characterize it at the 129 kHz ripple waveform. Bound saturation and winding temperature under startup, low-line foldback and a physical short. The current model's 15 Arms ceiling does not define a fault current maximum.
3. **Capacitor closure:** measure four-can sharing, ESR and temperature at 120 Hz plus 129 kHz; prove bus transients stay below the 450 V electrolytic rating and 630 V film rating with tolerance and layout inductance. The existing 105 W cooling allowance is not evidence of capacity.
4. **F1/F2 fault coordination:** derive prospective mains short-circuit and DC-link fault current from source impedance, bridge/inductor saturation, capacitor stored energy and loop L/R. Obtain the fuse's applicable time-current, DC interruption and let-through data; the retained 0034.3129 AC table does not qualify F2 or any downstream fault.
5. **F2 rail-order/timing proof:** sweep logic5 and aux15 ramps, dips and reverse order at −40..125 C, including TPS3890 CT tolerance/leakage and LVC below-VCC conditions. Verify that `clear_ok`, retained `run`, UCC27511A IN− and gate output are off before any unsafe aux-powered pulse; measure the claimed ~132 us hold rather than inferring it from nominal 100 pF.
6. **Thermal/partial-power qualification:** build a coupled package/lead/PCB/heatsink model or measure it. The current evidence explicitly leaves MOSFET/SiC losses, HF capacitor loss, inductor loss, PCB/fuse/contact loss and cooling unqualified; no partial-power or fault-current rating may be inferred from nominal logic behavior.

## F2 load-bearing candidate and rail addendum

The retained protection disposition identifies **Mersen A70QS50-14F + UltraSafe
US141/Z331153** as the exact F2 candidate, but explicitly leaves coordination
unestablished.  The A70QS evidence gives 50 A rated current, 14×51 mm body,
890 Vdc capacitor-discharge rating only for the stated 2.5 ms time-constant
condition, 280 A²s maximum pre-arcing/melting I²t, and 1,500 A²s maximum
clearing I²t at 700 Vac.  The AC clearing number is not a capacitor-discharge
or DC-bus let-through value; no A70QS minimum-breaking-current or 890 Vdc
discharge clearing curve is published in the retained packet.  The US141
holder record gives 1000 Vdc/50 A/50 kA UL ratings, 750 Vdc general rating,
8 kV impulse withstand and 5 W dissipation at 50 A, with mounting, airflow,
ambient and conductor derating conditions.  A holder short-circuit rating is
not an independent fuse-interruption result.

Source paths: `zapote/power-entry/passive-reva/protection/DISPOSITION.md`, retained
holder PDF `zapote/power-entry/passive-reva/protection/sources/Mersen-US14.pdf`
(SHA-256 `776c47a6781b1d82d762a827d2ceed9d7e17b15439217b9fb5dc259aa9884562`),
[Mersen US14 datasheet](https://www.mersen.com/sites/default/files/medias/PIM/files/DS-Semiconductor-Modular-Fuse-Holders-UltraSafe-US14-EN.pdf),
and [US141/Z331153 product record](https://www.mersen.com/en/products/ultrasafe-us14-modular-fuse-holders/z331153-us141).
The required next bound is a source-impedance, capacitor-tolerance, failed-U10/
failed-U9 residual, loop-L/R and fuse-application analysis, followed by an
exact-assembly current-limited test.  F1 remains the separate AC-line
interrupter; neither F1 nor the holder rating bounds stored bank fault current.

The local reservoir candidate in the earlier F2 construction is **TDK
B32776P6226K000**, 22 uF, 630 Vdc, ±10%, 35 V/us, 42×28×42.5 mm maximum body,
37.5 mm lead pitch.  It is a candidate requiring new placement/footprint and
temperature, ripple, ESL and pulse review; the 630 V label is not a desired
transient operating point.  The retained interface calculation gives 449.174 V
for 22 uF at nominal conditions but 451.765 V at the −10% capacitance (19.8 uF)
corner, before detection delay, so the nominal <450 V screen has no tolerance
margin.  At +10%/500 V the stored local energy is 3.025 J and lies outside F2;
it needs a separate failed-short/discharge disposition.  See
`zapote/power-entry/passive-reva/INTERFACE-DESIGN.md`
§5 and the [TDK product page](https://product.tdk.com/en/search/capacitor/film/dc-link/info?part_no=B32776P6226K000).

The same interface draft proposes **Mean Well IRM-10-15** as an auxiliary
producer: 15 V, 0.67 A, ±2.5%, 200 mVpp under stated test conditions.  Its
overvoltage-protection range is 17.25–20.25 V.  That range crosses the
UCC27511A recommended VDD maximum of 18 V and approaches its 20 V absolute
maximum, so it is a concrete unresolved rail interface gap.  The run
requirement must include an independently specified OVP/shutdown disposition
that prevents the driver from seeing 18–20.25 V; the producer's OVP range is
not a guaranteed driver-safe waveform.  Do not select a replacement here.
See `zapote/power-entry/passive-reva/INTERFACE-DESIGN.md`
§2, [Mean Well IRM-10 datasheet](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF),
and [TI UCC27511A datasheet](https://www.ti.com/lit/ds/symlink/ucc27511a.pdf).

Finally, C3D20065D's datasheet prints `RθJC = 1.3 °C/W **` per device and
`0.65 °C/W *` per leg.  Those are the literal manufacturer footnotes, but the
relationship to the package's Ptot and shared heat path must be clarified
before assigning heat between its two dies or using either value as an
assembly acceptance limit.
