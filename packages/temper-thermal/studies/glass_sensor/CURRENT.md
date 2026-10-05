# Current through-glass sensor CAD

**R7 — complete experimental coupon comparison, not released. All physical tests NOT_RUN.**

- [Clearance-corrected M222 / 0.100 mm control](revision7/mechanical/R7-M222_control_010-rest.step)
- [M222 / 0.075 mm thin-bond coupon](revision7/mechanical/R7-M222_thin_0075-rest.step)
- [IST308 / 0.075 mm complete candidate](revision7/mechanical/R7-IST308_thin_0075-rest.step)
- [Motion poses, section drawings and package assumptions](revision7/mechanical/README.md)
- [CAD-coupled results and test preparation](revision7/report.html)
- [Exact current CAD identities](current-cad.json) and [R7 artifact provenance](revision7/source-provenance.json)

R7 corrects supplier maximum-package clashes, models the complete installed native leads/joins/covers and full60mm extension routes, and exports their geometry to the thermal model. Native trimming/forming, film orientation, pad pitch, bond/weld process and insulation remain qualification inputs. The separate pressure fixture is not the cartridge seal.

Nominal modeled results: control2.91s/2.474°C underread; thin-bond M2222.78s/2.441°C; IST3082.05s/2.577°C. Contact and package-property uncertainty materially worsen these results. No candidate establishes the combined <2s/<2°C whole-system target.

[R5](revision5/report.html) remains a frozen numerical baseline. Its previous mutable index bytes are archived in [R7 history](revision7/history/R5-CURRENT.md) with the unchanged [R5 CAD identity record](revision7/history/R5-current-cad.json). Historical manifest hashes are preserved, not rewritten. R6 remains the research comparison; R7 supplies complete experimental alternatives.
