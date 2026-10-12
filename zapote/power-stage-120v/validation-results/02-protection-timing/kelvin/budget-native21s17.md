| pad | mA (max) | mΩ to R35.2 | mV at R35.2 | what |
| --- | ---: | ---: | ---: | --- |
| U3.2 | 0.1 | 148.9558 | 0.0149 | TPS70950 ground-pin current, over-bounded at 0.1 mA (datasheet IQ is microamp-class) |
| U4.3 | 9.7 | 153.4596 | 1.4886 | AMC1311B IDD1, 4.5 V < VDD1 < 5.5 V, max |
| U9.1 | 2.4 | 153.4596 | 0.3683 | ISO7710 ICC1, 5 V supply, DC signal, max (input state that draws more) |
| U6.2 | 0.065 | 151.1413 | 0.0098 | TLV3201 IQ max, -40..125 C |
| U7.2 | 0.065 | 150.1824 | 0.0098 | TLV3201 IQ max, -40..125 C |
| U8.2 | 0.01 | 150.2864 | 0.0015 | SN74LVC1G10 ICC max |
| U15.3 | 0.01 | 151.1413 | 0.0015 | SN74LVC1G17 ICC max |
| U14.2 | 0.5433 | 148.9558 | 0.0809 | TPS3700 IDD max (VDD 18 V) + 10 k pull-up when OUTA asserted low |
| U5.2 | 0.496 | 150.2864 | 0.0745 | all current through the 5.6 k reference bias (LM4040 + dividers), bounded as returned at the anode |
| R49.2 | 0.0461 | 153.2591 | 0.0071 | HOT5 UV divider 105 k + 10 k |
| R30.2 | 0.2131 | 150.2864 | 0.032 | bus divider at 400 V (above the 280 V maximum) |
| **total** | **13.648** | | **2.0889** | trip shift **-2.166 A**; band 67.72–116.44 A |
