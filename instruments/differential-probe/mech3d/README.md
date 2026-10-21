# Printed parts (CadQuery)

Code-generated 3D-printed parts for the Rev C probe: lead bridge, external lead spine, stage-53 docking bracket and shield-fit parts. Each part script exports STEP (for the owner's enclosure CAD) and STL (for printing).

Environment, isolated from the main workspace (CadQuery's OCP kernel is about 1.3 GB):

```sh
cd instruments/differential-probe/mech3d
uv sync --no-cache        # Python 3.12, cadquery from uv.lock
.venv/bin/python <part>.py
```

Printed resin carries no insulation credit: Formlabs publishes no dielectric strength or tracking index, so the rated wire insulation, the air clearances and the FR4 creepage paths remain the HV design. Printed parts fix geometry only, and every part near the divider or leads is mirror-symmetric about the leg axis.
