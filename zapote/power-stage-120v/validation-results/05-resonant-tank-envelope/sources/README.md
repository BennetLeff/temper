# Source record for task 05

All three PDFs below are manufacturer-authored. The CDE and Coilcraft files
were fetched from their own domains on 2026-09-27. The older Yageo PDF was
fetched from a distributor mirror after the newer Mouser-hosted V.4 file
failed twice; its working-voltage and power entries agree with Yageo V.4 as
rendered at the [Mouser mirror](https://www.mouser.com/ds/2/447/yageo_pyu-rc1206_51_rohs_l-4-1212095.pdf).

| File | Original URL | Revision and exact location | SHA-256 |
| --- | --- | --- | --- |
| `942C.pdf` | https://www.cde.com/resources/catalogs/942C.pdf | No printed revision; PDF creation 2021-11-16. Printed p. 3, 1200 Vdc rows: 942C12P22K-F is 0.22 µF, 10.3 A RMS at 70 °C/100 kHz; 942C12P1K-F is 0.10 µF, 9.2 A at the same condition. Printed p. 4: RMS voltage versus frequency curves at 25 °C for 0.10, 0.33 and 0.90 µF; no exact 0.22 µF curve. | `f99395446ba25a0adcef85862ff9eaee90bac68fae6664decccab1ebea3e4310` |
| `cst3015.pdf` | https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf | Document 1608-1, revised 09/08/25, p. 1, CST3015-100ED row and notes 4–6: 1:100; 638 V·µs secondary volt-time; 88 A *sensed current thermal reference*, not an absolute peak maximum; 1 Ω terminating resistance is the value for 1 V output at 100 A, not a specified allowed range. | `0da51f0ee5831b9b633eb10bc8008332e6f461f05f10eacff6d288fdee60bd5f` |
| `rc1206.pdf` | https://pccomponents.com/datasheets/yageo-rc.pdf | Yageo RC1206 product specification V.2, 2004-09-03, printed p. 4 Table 2 and p. 5 power section: 200 V maximum working voltage, 400 V overload voltage, 0.25 W at 70 °C; p. 2 ordering scheme identifies RC1206FR as 1% series. | `7445a468b35a28771c4ec09f3f9b8f3fa4348338fa6a52838942185e58e8c044` |

The CDE p. 3 table is **not** a 34–55 kHz current rating, and the p. 4
voltage curves are **not** specified at a hot local temperature. No such
rating was substituted during this partial study.
