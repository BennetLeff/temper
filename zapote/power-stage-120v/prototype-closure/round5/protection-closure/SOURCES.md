# Primary-source receipt

Retrieved official manufacturer files are local research evidence in `output/temper-prototype-closure/round5/protection-closure/`; redistribution of raw PDFs is not part of this authored ECO. Page references below refer to PDF pages. Manufacturer conditions are not broadened by the candidate calculation. No supplier was contacted.

| File | Official source | Version/page and use | SHA256 |
|---|---|---|---|
|LC1D18BD.pdf|[Schneider LC1D18BD](https://iportal.se.com/Contents/docs/SQD-LC1D18BD.PDF)|Document dated September13,2017; p1 AC1≤440V32A≤60°C; p3 coil24VDC5.4W20°C, closing53.55–72.45ms/opening16–24ms, NC mirror, auxiliary minimum17V/5mA,45×77×95mm W×H×D. This older dated exact-part PDF was retrieved from the official endpoint; it is not represented as a newly issued qualification.|`23b9ff28a3acf1ed40d6acddba447264405dd662f59f9acc859ed4183d5f228d`|
|ISO1211.pdf|[TI ISO1211](https://www.ti.com/lit/ds/symlink/iso1211.pdf)|RevG,February2025; pp3,10–11,21–23. Exact selected orderable ISO1211DR SOIC8. RSENSE562Ω±1%,RTHR0; input2.05–2.75mA for VIL<VSENSE<30V; VIH≤8.55V,VIL≥6.5V; supply/load and edge conditions retained in receiver-ECO.|`41e0bc7308dd4e0cc8c7f30efb6a2cd87bcc865d9195095ff849be6036cb2328`|
|TPL7407L.pdf|[TI TPL7407L](https://www.ti.com/lit/ds/symlink/tpl7407l.pdf)|RevD,March2016; pp3–5. Exact selected orderable TPL7407LDR SOIC16. COM supply8.5–40V, output≤40V, logic VIH1.5V/VIL0.9V;0.32Vmax sink drop at100mA;500nA off leakage test at24V only;350ns switching typical only.|`8d610edc083388a90d99b0cc07ab5c7be18ea51e49502d6fdf9f119df03bd1ec`|

Current official exact-part product listing checked: [Schneider LC1D18BD](https://www.se.com/uk/en/product/LC1D18BD/tesys-d-contactor-3p3-no-ac3-440-v-18-a-24-v-dc-coil/). Product listing is not a stock reservation, environmental approval or application-specific short-circuit coordination report.

The frozen model source used in the rejected whole-plant adaptation was `round5/model/averaged.cir`, SHA256 `82cbac2ef8752f8c349c0e98f7cdbff95344fd2b0620ebee54f47d3b651900c5`. Its copy and failed generator/logs are retained in the output folder with failed labels. The accepted54-case prescribed-exposure experiment consumes only the authored `exposure.rs` constants; it does not consume this rejected adaptation or silently inherit its device model validity.

The existing `round5/protection/interface.json` and parent model RESULTS supply the earlier resistor/fuse/catch context. This work introduces no new vendor guarantee for Ohmite pulse energy, Sensience TCO interruption, Eaton DC clearing or Infineon catch-diode survival. Unavailable exact DC clearing/arc limits remain null in the candidate interface.

## Added discharge-window source identities

- [tlv9061 official PDF](https://www.ti.com/lit/ds/symlink/tlv9061.pdf): local `tlv9061-window.pdf`, SHA256 `7a5517d7f74bedddf4b8404fce93e21100d2833a6f4ae16a93f934eaf0c6477c`. Exact conditions and page references are in discharge-window-ECO.md.
- [tlv3201 official PDF](https://www.ti.com/lit/ds/symlink/tlv3201.pdf): local `tlv3201-window.pdf`, SHA256 `1777bba814c74772bb54c6f1f56702985039043ce2fb2affaf996a83eaf1076e`. Exact conditions and page references are in discharge-window-ECO.md.
- [lm4040 official PDF](https://www.ti.com/lit/ds/symlink/lm4040.pdf): local `lm4040-window.pdf`, SHA256 `f43b6b6d3ecd51c8c90b70a7c4630c7e3140822b0073953ed2459df81b251c1c`. Exact conditions and page references are in discharge-window-ECO.md.
- [amc3330 official PDF](https://www.ti.com/lit/ds/symlink/amc3330.pdf): local `amc3330-window.pdf`, SHA256 `f5d60f1ccdfbf42b22f44d283f650fd85f3eb64591fdc5309cafc2bd850235f7`. Exact conditions and page references are in discharge-window-ECO.md.

[Vishay TNPW document28758,10-Apr-2026](https://www.vishay.com/docs/28758/tnpw_e3.pdf), pp1,3:0603ends332kΩ,0805extends1MΩ. The620k threshold is0805, not0603. [ADI LTC6993 RevF](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc6993-6993-1-6993-2-6993-3-6993-4.pdf), pp1,14:−1 rising nonretriggerable,−2 rising retriggerable. Exactexistingnative timer remains LTC6993HS6-1#TRMPBF.
