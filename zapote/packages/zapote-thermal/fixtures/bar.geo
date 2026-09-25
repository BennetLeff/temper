SetFactory("OpenCASCADE");
L = 0.01; W = 0.002; H = 0.001;
If (!Exists(h))
  h = 0.0005;
EndIf
Box(1) = {0, 0, 0, L, W, H};
eps = 1e-6;
left[] = Surface In BoundingBox{-eps,-eps,-eps,eps,W+eps,H+eps};
right[] = Surface In BoundingBox{L-eps,-eps,-eps,L+eps,W+eps,H+eps};
Physical Volume("copper", 1) = {1};
Physical Surface("left", 11) = {left[]};
Physical Surface("right", 12) = {right[]};
Mesh.MeshSizeMin = h;
Mesh.MeshSizeMax = h;
Mesh.MshFileVersion = 2.2;
