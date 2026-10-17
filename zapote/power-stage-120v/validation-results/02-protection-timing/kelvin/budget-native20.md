| pad | mA (max) | mΩ to R35.2 | mV at R35.2 | what |
| --- | ---: | ---: | ---: | --- |
| U3.2 | 7.6 | 98.5391 | 0.7489 | MC78L05AC input bias (ground-pin) current, 25 C max 6.0 mA + line (1.5) + load (0.1) change |
| U4.3 | 9.7 | 100.5061 | 0.9749 | AMC1311B IDD1, 4.5 V < VDD1 < 5.5 V, max |
| U9.1 | 2.4 | 103.6842 | 0.2488 | ISO7710 ICC1, 5 V supply, DC signal, max (input state that draws more) |
| U6.2 | 0.065 | 92.773 | 0.006 | TLV3201 IQ max, -40..125 C |
| U7.2 | 0.065 | 100.5061 | 0.0065 | TLV3201 IQ max, -40..125 C |
| U8.2 | 0.01 | 103.6842 | 0.001 | SN74LVC1G10 ICC max |
| U15.3 | 0.01 | 100.5061 | 0.001 | SN74LVC1G17 ICC max |
| U14.2 | 0.5433 | 100.0856 | 0.0544 | TPS3700 IDD max (VDD 18 V) + 10 k pull-up when OUTA asserted low |
| U5.2 | 0.496 | 116.3904 | 0.0577 | all current through the 5.6 k reference bias (LM4040 + dividers), bounded as returned at the anode |
| R49.2 | 0.0461 | 100.5061 | 0.0046 | HOT5 UV divider 105 k + 10 k |
| R30.2 | 0.2131 | 100.5061 | 0.0214 | bus divider at 400 V (above the 280 V maximum) |
| **total** | **21.148** | | **2.1254** | trip shift **-2.187 A**; band 47.54–97.98 A |
