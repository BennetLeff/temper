| pad | mA (max) | mΩ to R35.2 | mV at R35.2 | what |
| --- | ---: | ---: | ---: | --- |
| U3.2 | 0.1 | 152.4083 | 0.0152 | TPS70950 ground-pin current, over-bounded at 0.1 mA (datasheet IQ is microamp-class) |
| U4.3 | 9.7 | 158.2713 | 1.5352 | AMC1311B IDD1, 4.5 V < VDD1 < 5.5 V, max |
| U9.1 | 2.4 | 158.2713 | 0.3799 | ISO7710 ICC1, 5 V supply, DC signal, max (input state that draws more) |
| U6.2 | 0.065 | 154.4705 | 0.01 | TLV3201 IQ max, -40..125 C |
| U7.2 | 0.065 | 153.6242 | 0.01 | TLV3201 IQ max, -40..125 C |
| U8.2 | 0.01 | 154.0567 | 0.0015 | SN74LVC1G10 ICC max |
| U15.3 | 0.01 | 154.4705 | 0.0015 | SN74LVC1G17 ICC max |
| U14.2 | 0.5433 | 152.4083 | 0.0828 | TPS3700 IDD max (VDD 18 V) + 10 k pull-up when OUTA asserted low |
| U5.2 | 0.496 | 154.0567 | 0.0764 | all current through the 5.6 k reference bias (LM4040 + dividers), bounded as returned at the anode |
| R49.2 | 0.0461 | 157.9904 | 0.0073 | HOT5 UV divider 105 k + 10 k |
| R30.2 | 0.2131 | 154.0567 | 0.0328 | bus divider at 400 V (above the 280 V maximum) |
| **total** | **13.648** | | **2.1528** | trip shift **-2.215 A**; band 47.51–97.98 A |
