| pad | mA (max) | mΩ to R35.2 | mV at R35.2 | what |
| --- | ---: | ---: | ---: | --- |
| U3.2 | 0.1 | 148.3519 | 0.0148 | TPS70950 ground-pin current, over-bounded at 0.1 mA (datasheet IQ is microamp-class) |
| U4.3 | 9.7 | 148.4146 | 1.4396 | AMC1311B IDD1, 4.5 V < VDD1 < 5.5 V, max |
| U9.1 | 2.4 | 148.4146 | 0.3562 | ISO7710 ICC1, 5 V supply, DC signal, max (input state that draws more) |
| U6.2 | 0.065 | 147.9481 | 0.0096 | TLV3201 IQ max, -40..125 C |
| U7.2 | 0.065 | 147.9086 | 0.0096 | TLV3201 IQ max, -40..125 C |
| U8.2 | 0.01 | 148.4631 | 0.0015 | SN74LVC1G10 ICC max |
| U15.3 | 0.01 | 147.9481 | 0.0015 | SN74LVC1G17 ICC max |
| U14.2 | 0.5433 | 148.3515 | 0.0806 | TPS3700 IDD max (VDD 18 V) + 10 k pull-up when OUTA asserted low |
| U5.2 | 0.496 | 148.4556 | 0.0736 | all current through the 5.6 k reference bias (LM4040 + dividers), bounded as returned at the anode |
| R49.2 | 0.0461 | 148.4017 | 0.0068 | HOT5 UV divider 105 k + 10 k |
| R30.2 | 0.2131 | 148.6385 | 0.0317 | bus divider at 400 V (above the 280 V maximum) |
| **total** | **13.648** | | **2.0256** | trip shift **-2.101 A**; band 67.79–116.44 A |
