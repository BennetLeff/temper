# Capacitor assembly envelopes

These six `.step` files are original, simple 3D envelopes for thirteen
capacitor footprints (eleven from native-09, plus the KEMET R463N410000N1M X2
capacitors C1/C2 from native-14, which are modelled at the datasheet's
maximum body, not nominal). They are **not manufacturer CAD** or evidence of a
mechanical fit. The body dimensions and pad pitches come from the linked
manufacturer tables in `../model-map-capacitors.json`. The shape of molded
corners, lead bends, and stand-off is illustrative. For the Murata disc, only
diameter, thickness, lead pitch, and lead diameter are documented in the
referenced part table; installed height remains provisional.

`generate_step.cpp` builds the STEP files with OpenCascade 7.9.3. On the
current macOS workstation:

```sh
c++ -std=c++17 -O2 -I/opt/homebrew/include/opencascade generate_step.cpp \
  -L/opt/homebrew/lib -Wl,-rpath,/opt/homebrew/lib \
  -lTKDESTEP -lTKDE -lTKXSBase -lTKPrim -lTKTopAlgo -lTKBRep \
  -lTKG3d -lTKG2d -lTKGeomBase -lTKMath -lTKernel \
  -o /tmp/power-cap-generate-step
/tmp/power-cap-generate-step .
```

The generator replaces OpenCascade's wall-clock STEP header timestamp with a
fixed value, so rerunning it produces the hashes recorded in the map. The
`.wrl` files from `generate.py` are optional colored viewer substitutes;
their source coordinates are divided by 2.54 because KiCad treats one VRML
coordinate unit as 2.54 mm. The map uses STEP so KiCad can also include these
components in a STEP assembly export.

KiCad 10.0.4 loaded the C5, C21 and C3 VRML previews in GLB exports. For C5,
the STEP body and all four pins appeared at the same pad coordinates as the
VRML counterpart; `kicad-cli pcb export step` included C5 once the `.step`
model was assigned. The native-09 copper and footprints were not modified by
this model-generation work.
