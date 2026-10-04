// Provisional pair of 102071 fuse clips with a 6.3 x 32 mm fuse installed.
// Dimensions follow footprint pad span; clip spring shape is simplified.
SetFactory("OpenCASCADE");
// Two clip bases, each supported at the two plated pad positions.
Box(1) = {0.25, -3.75, 0, 7.10, 7.50, 1.5};
Box(2) = {27.35, -3.75, 0, 7.10, 7.50, 1.5};
// Four spring side walls.
Box(3) = {0.25, -3.75, 1.5, 7.10, 0.7, 5.5};
Box(4) = {0.25, 3.05, 1.5, 7.10, 0.7, 5.5};
Box(5) = {27.35, -3.75, 1.5, 7.10, 0.7, 5.5};
Box(6) = {27.35, 3.05, 1.5, 7.10, 0.7, 5.5};
// Fuse cartridge axis along the holder, radius 3.15 mm.
Cylinder(7) = {1.35, 0, 5.0, 32.0, 0, 0, 3.15};
