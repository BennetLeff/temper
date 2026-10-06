// Provisional body envelope from MEAN WELL IRM-05 datasheet, mm.
// Model Y is the negative of footprint Y: [-11.2,14.2] -> [-14.2,11.2].
SetFactory("OpenCASCADE");
Box(1) = {-3.6, -14.2, 0.0, 45.7, 25.4, 21.5};
// Pins mark orientation but do not certify lead shape or insertion depth.
Cylinder(2) = {0, 0, -3.0, 0, 0, 3.0, 0.7};
Cylinder(3) = {0, -10.75, -3.0, 0, 0, 3.0, 0.7};
Cylinder(4) = {38.5, -10.75, -3.0, 0, 0, 3.0, 0.7};
Cylinder(5) = {38.5, -2.75, -3.0, 0, 0, 3.0, 0.7};
