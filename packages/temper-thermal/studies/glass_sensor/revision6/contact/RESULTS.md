# R6 contact results

**No candidate closes the combined response and complete-system accuracy target.** At identical assumed contact and losses, thinner packaging helps response but does not remove the thermal underread. Characterization of the existing package remains necessary to decide whether a new element actually buys enough improvement.

Nominal uniform contact, href2000, full-envelope capacity proxy, assumed 1 mm native leads:

| Element / bond | t90 to pan | Thermal underread at200°C | Underread at end of5°C/s ramp |
| :-- | --: | --: | --: |
| Frozen R5 M222 /0.10 mm |2.94s|2.474°C|9.784°C|
| M222 /0.075 mm |2.81s|2.441°C|9.485°C|
| IST308 /0.10 mm |2.27s|2.576°C|8.550°C|
| IST308 /0.075 mm |2.14s|2.520°C|8.222°C|
| IST161 geometry only /0.10 mm |2.42s|2.860°C|9.086°C|

The nominal IST308 full-envelope proxy gains0.67s at0.10mm, about23%, but adds0.102°C thermal underread. Its smaller footprint approximately doubles bond resistance. The half-substrate film-path assumption contributes to this comparison: sweeping IST308 film path0.125→0.6mm shifts its nominal result2.27→2.38s and2.576→2.666°C. These are hypotheses, not alternate demonstrated packages.

**Unknown installed mass is consequential.** At0.10mm bond, the M222 half/full envelope assumptions span2.18–2.94s. IST308 substrate-only/full-envelope spans1.87–2.27s. These overlapping conditional ranges do not prove which physical package wins. Assigning the alternative's bare substrate mass while leaving the baseline's entire rectangular envelope would overstate certainty.

**Contact and thermal losses still dominate accuracy.** The0.075mm IST308 full-envelope proxy at rim contact is5.75s and6.014°C underread. At uniform nominal contact but higher losses, the0.10mm IST308 becomes2.47s and4.843°C. Its favourable href4000/nominal-loss/0.075mm case gives1.36s and1.499°C, but that contact law is uncalibrated and the figure is thermal error alone.

Of324 grid cases,32 meet t90-pan≤2s and thermal underread<2°C. **Zero meet t90-pan≤2s and thermal underread≤1°C**, the inherited proposed thermal allocation needed to leave1°C for the rest of a2°C worst-case budget. That allocation is a planning choice, not a measured budget or certification requirement. The324 cases do not constitute a probability distribution or a robustness guarantee.

Native-lead sensitivity also matters: retaining7mm instead of1mm in the lumped IST308 model reduces heat leakage, giving2.08s/2.031°C at0.10mm bond instead of2.27s/2.576°C. Added heat capacity is included. This is **not a ready geometry improvement**: routing, cover volume, lead cooling/gradient, weld position and mechanical durability would need redesign. R5's original lead cooling approximation does not become evidence for a7mm layout.

Next steps are therefore specific: measure M222 assembled response/capacity and bond coverage, hold the existing D6 assembly as control, characterize a thin-bond build, then compare a fully modeled IST308 coupon with actual joins and lead routing. Build no production claim from these parametric rows. Physical qualification remains NOT_RUN.
