# Physical-model integration handoff

The model extension and baseline/3 mm comparison are implemented. The maintained
board is unchanged. Candidate selection and hardware qualification remain open.

- U1: native pad shape, drill, trace UUID/net/length/width and stackup are checked;
  original exact-board replay stays immutable. Only the reviewed GBU geometry is
  supported. GBJ receives no inherited model acceptance.
- U2: four conforming material domains are solved by Gmsh/Elmer. The shared
  package allowance appears once. Electrical and thermal balances are independent;
  contact coupling is checked at every accepted final iteration. Native,
  rectangular and obround references and adversarial mutations are retained.
- U3: the common runner requires the physical/loss and resolved-joint checks,
  binds their complete evidence inputs and serializes each finding. Replay
  regenerates geometry/physics and checks raw mesh, scalar and solver records.
- U4: the [comparison](comparison.md) covers both supported boards at three mesh
  resolutions, a wider domain and the predeclared weak-assembly sensitivity.
  Neither board gains physical acceptance. The 3 mm improvement is modest.

Verification receipts and the final common-suite snapshot are in
`zapote/thermal/bridge-redesign-verification-20260914/`. The previous reduced
network is retained as an explicit approximation, separately from joint FEM.
Numerical validity does not validate the assumed package internals, solder,
lead material, convection or 40 W loss bound.

The earlier Luna FEM attempts in the
separate `/private/tmp/zapote-bridge-fem-20260914` worktree were not accepted or integrated. Their geometry
and boundary assumptions did not establish the required physical problem.
The replacement has executable negative controls for those failure classes.
The untrimmed local solver directories remain at the dated
`/private/tmp/zapote-joint-baseline-20260914-v1` and
`/private/tmp/zapote-joint-3mm-20260914-v2` paths; replay-required bytes are
archived in the repository, with large meshes compressed losslessly.

The next physical decision is the package and cooling assembly, informed by a
GBJ-specific model or measurements of the uncertain paths. Do not keep refining
the GBU mesh to conceal that uncertainty. No purchase, fabrication or powered
qualification has been performed.
