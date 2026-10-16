| pad | mA (max) | mΩ to R35.2 | mV at R35.2 | what |
| --- | ---: | ---: | ---: | --- |
| U3.2 | 0.1 | 150.3813 | 0.015 | TPS70950 ground-pin current, over-bounded at 0.1 mA (datasheet IQ is microamp-class) |
| U4.3 | 9.7 | 149.8411 | 1.4535 | AMC1311B IDD1, 4.5 V < VDD1 < 5.5 V, max |
| U9.1 | 4.1 | 149.8411 | 0.6143 | CA-IS3720HW IDDA max, healthy state: INA = bus_fault_hot low (VIN = 0 V, H version), VDDA 5 V +-10 %, TA -40..125 C (fault state VIN = VDDA: 1.3 mA max) |
| U6.2 | 0.065 | 148.8294 | 0.0097 | TLV3201 IQ max, -40..125 C |
| U7.2 | 0.065 | 148.7878 | 0.0097 | TLV3201 IQ max, -40..125 C |
| U8.2 | 0.01 | 150.3893 | 0.0015 | SN74LVC1G10 ICC max |
| U15.3 | 0.01 | 148.8294 | 0.0015 | SN74LVC1G17 ICC max |
| U14.2 | 0.5433 | 150.2231 | 0.0816 | TPS3700 IDD max (VDD 18 V) + 10 k pull-up when OUTA asserted low |
| U5.2 | 0.496 | 150.3225 | 0.0746 | all current through the 5.6 k reference bias (LM4040 + dividers), bounded as returned at the anode |
| R49.2 | 0.0461 | 149.7872 | 0.0069 | HOT5 UV divider 105 k + 10 k |
| R30.2 | 0.2131 | 150.4912 | 0.0321 | bus divider at 400 V (above the 280 V maximum) |
| R137.2 | 0.123 | 150.3767 | 0.0185 | U3 EN divider R136 100 k / R137 27 k from V15_LS (15.46 V max above GND) |
| R145.2 | 0.0335 | 150.2587 | 0.005 | REF25 watchdog R144 63.4 k + R145 11.7 k (also inside the U5.2 bound) |
| **total** | **15.505** | | **2.3239** | trip shift **-2.41 A**; band 66.22–117.7 A |
