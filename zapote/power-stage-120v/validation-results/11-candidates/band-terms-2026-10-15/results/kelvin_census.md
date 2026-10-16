| pad | mA (max) | mOhm to R35.2 | mV at R35.2 | what | datasheet basis |
|---|---:|---:|---:|---|---|
| U3.2 | 0.1 | 148.7469 | 0.0149 | TPS70950 ground-pin current; over-bound kept from the committed census | SBVS186H 6.5 p.5: IGND 2.25 uA max at IOUT 0; 350 uA typ (no max) at 150 mA, so ~35 uA typ at the ~15 mA load |
| U4.4 | 9.7 | 150.0045 | 1.455 | AMC1311B IDD1 (GND1 return; SHTDN pin U4.3 tied to GND1, its <= 70 uA pull current is inside IDD1) | SBAS786C 6.10 p.11: IDD1 9.7 mA max, 4.5 V < VDD1 < 5.5 V, SHTDN low; SHTDN IIN -70..1 uA (same table) |
| U9.1 | 4.1 | 150.0045 | 0.615 | CA-IS3720HW IDDA (GNDA pins U9.1 / U9.7), healthy state: INA = bus_fault_hot low (VIN = 0 V, H version); unused INB floats to its default-high (low-current) state | Chipanalog CA-IS372x v1.05 7.9.1 p.11 (EN v1.02 p.11 same table): IDDA 4.1 max, 'VIN = 0V (CA-IS3720H)', VDDA = VDDB = 5 V +-10 %, TA -40..125 C. Fault state (VIN = VDDA) 1.3 mA max |
| U6.2 | 0.065 | 148.8623 | 0.0097 | TLV3201 IQ (OCP comparator) | SBOS561C 6.5 p.5: IQ 65 uA max, TA -40..125 C, VCC 5 V |
| U7.2 | 0.065 | 148.8074 | 0.0097 | TLV3201 IQ (OVP comparator) | SBOS561C 6.5 p.5 |
| U8.2 | 0.01 | 150.7169 | 0.0015 | SN74LVC1G10 ICC | SCES486E p.4: ICC 10 uA max, VI = 5.5 V or GND |
| U8.2 | 0.015 | 150.7169 | 0.0023 | SN74LVC1G10 input leakage, 3 inputs driven from HOT5-powered outputs (U6, U7, U15) | SCES486E p.4: II +-5 uA max each |
| U15.3 | 0.01 | 148.8623 | 0.0015 | SN74LVC1G17 ICC | SCES351Y p.6: ICC 10 uA max |
| U15.3 | 0.005 | 148.8623 | 0.0007 | SN74LVC1G17 input leakage (A from hot5_uv_raw) | SCES351Y p.6: II +-5 uA |
| U14.2 | 0.013 | 148.7469 | 0.0019 | TPS3700 IDD (supplied from V15_LS, returned on ocp_kelvin_p) | SBVS187G 6.5 p.6: IDD 13 uA max at VDD 18 V |
| U14.2 | 0.5303 | 148.7469 | 0.0789 | R50 10 k pull-up into OUTA, only while OUTA asserts (HOT5 UV); 0 in normal running (OUTA open-drain released). Kept at its asserted value, as committed | R50 10 k 1 %; SBVS187G Table 1 p.10 (INA+ > VIT+ -> OUTA high, released) |
| U5.2 | 0.3785 | 150.7157 | 0.057 | R31 current less the two threshold strings: U5 cathode current plus the R32/R33 string. The R32/R33 share (~0.133 mA) actually returns via ocp_kelvin_n into R5.3 and never crosses the plane: kept here (conservative) | R31 5.6 k 1 %; LM4050AEM3 VR min 2.4838 V (SNOS455H 5.6 p.7) |
| R35.2 | 0.1037 | 152.9021 | 0.0158 | R34/R35 OCP-threshold string, returned at R35.2 (the probe pad) | R34 12.6 k + R35 11.7 k, 0.1 %; VR max 2.5162 V |
| R37.2 | 0.0168 | 150.0087 | 0.0025 | R36/R37 OVP-threshold string, returned at R37.2 | R36 10 k + R37 140 k, 0.1 %; VR max 2.5162 V |
| R49.2 | 0.0461 | 149.9438 | 0.0069 | HOT5 UV divider R48 105 k + R49 10 k | power_stage_120v.ato; as committed |
| R30.2 | 0.2131 | 150.7551 | 0.0321 | bus divider at 400 V (above the 287.62 V OVP top; kept as committed). U4 VIN input bias (+-15 nA, SBAS786C p.10) is inside this | power_stage_120v.ato r_div_top x4 / r_div_bot |
| **total** | **15.371** | | **2.3056** | trip shift **-2.391 A** (committed -2.123); bound -2.437 A | |
