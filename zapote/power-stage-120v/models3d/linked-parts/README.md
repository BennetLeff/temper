# Local 3D envelopes for unavailable model links

These STEP files are authored from public package dimensions and KiCad footprint
origins. They make PS2, J4, R5, J3, and F1 visible in KiCad's 3D viewer. They
are **provisional mechanical envelopes**, not manufacturer CAD and not evidence
that a mating harness, enclosure, fuse or insulation system fits.

The `.geo` file alongside each STEP is its Gmsh/OpenCASCADE source. Regenerate
all five, with a fixed STEP header timestamp, using:

```sh
sh generate.sh
```

The exact Vishay WSK2512 STEP can be downloaded from the public link in
`../model-map-linked-parts.json`. Its manufacturer notice reserves ownership,
so it is not redistributed here. JST's exact B2P-VH download explicitly bars
third-party disclosure and is also absent. The F1 model includes a generic
6.3 × 32 mm fuse between a simplified pair of clips; the clips' actual spring
profile must be checked with sample hardware.
