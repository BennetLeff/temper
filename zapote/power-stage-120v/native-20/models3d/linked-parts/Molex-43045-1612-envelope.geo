// Provisional Micro-Fit 3.0 2x8 housing envelope, mm.
// Footprint-local y is inverted into CAD model coordinates.
SetFactory("OpenCASCADE");
Box(1) = {-3.57, -4.9, 0, 28.14, 7.37, 9.91};
// Housing mouth indicates the mating side; internal key geometry is omitted.
Box(2) = {-2.42, -3.7, 8.2, 25.84, 5.4, 2.0};
BooleanDifference{ Volume{1}; Delete; }{ Volume{2}; Delete; }
