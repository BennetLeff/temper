| pad | mA (max) | mΩ to R35.2 | mV at R35.2 | what |
| --- | ---: | ---: | ---: | --- |
| U3.2 | 0.1 | 152.4118 | 0.0152 | TPS70950 ground-pin current, over-bounded at 0.1 mA (datasheet IQ is microamp-class) |
| U4.3 | 9.7 | 156.8909 | 1.5218 | AMC1311B IDD1, 4.5 V < VDD1 < 5.5 V, max |
| U9.1 | 2.4 | 156.8909 | 0.3765 | ISO7710 ICC1, 5 V supply, DC signal, max (input state that draws more) |
| U6.2 | 0.065 | 154.6111 | 0.01 | TLV3201 IQ max, -40..125 C |
| U7.2 | 0.065 | 153.7086 | 0.01 | TLV3201 IQ max, -40..125 C |
| U8.2 | 0.01 | 153.81 | 0.0015 | SN74LVC1G10 ICC max |
| U15.3 | 0.01 | 154.6111 | 0.0015 | SN74LVC1G17 ICC max |
| U14.2 | 0.5433 | 152.4118 | 0.0828 | TPS3700 IDD max (VDD 18 V) + 10 k pull-up when OUTA asserted low |
| U5.2 | 0.496 | 153.81 | 0.0763 | all current through the 5.6 k reference bias (LM4040 + dividers), bounded as returned at the anode |
| R49.2 | 0.0461 | 156.6936 | 0.0072 | HOT5 UV divider 105 k + 10 k |
| R30.2 | 0.2131 | 153.81 | 0.0328 | bus divider at 400 V (above the 280 V maximum) |
| **total** | **13.648** | | **2.1359** | trip shift **-2.198 A**; band 47.33–97.77 A |
