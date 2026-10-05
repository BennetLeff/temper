# R5 mechanical package

Start with [the build package](BUILD_PACKAGE.md) and [verification record](VERIFICATION.md).

- `R5-D8-*.step` and `R5-D6-*.step`: two cartridge candidates, six motion poses each, plus standalone caps.
- `R5-D8-section.svg` and `R5-D6-section.svg`: section drawings.
- `thermal_geometry.csv`: final CAD scalar contract consumed by the thermal model.
- `geometry.json`, `route_audit.json`, `weld_connectivity.json`: nominal dimensional and topology checks.
- `build.py`, `audit_routes.py`: reproducible CAD generation and checks; original R2 source is SHA256-pinned.
- `R5-pressure-reference.step`, `pressure_reference.json`, `build_pressure_reference.py`: **REFERENCE_ONLY_UNCONNECTED_DRY_APPARATUS**. An ID1.5/OD3mm straight100mm tube, a10mL cold cavity and open dry-reference port illustrate the pressure-study dimensions. The separate apparatus is not mounted or connected to the cartridge. Neither the assumed1mL hot volume nor a liquid seal is established by this model.

All physical qualification remains NOT_RUN. These are controlled engineering prototype preparation files, not production drawings or cooking enablement.
