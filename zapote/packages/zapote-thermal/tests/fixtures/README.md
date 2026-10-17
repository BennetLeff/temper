# Captured Elmer reference output

These three cases were run by the Luna implementation worker on 2026-09-12
with Gmsh 4.15.2-git and Elmer 26.2, revision a19504a. Raw logs and SaveScalars
data/name files are retained verbatim. The parent independently reruns the
integrated command; see `zapote/thermal/` for the installation and run receipts.

Each case used the crate's `fixtures/bar.geo` and `fixtures/case.sif`.
Gmsh received `-setnumber h` with the mesh size in the directory name;
ElmerGrid received `14 2 bar.msh` without renumbering boundaries.
The analytic problem and its deliberately idealized boundaries are documented
in `zapote/thermal/README.md`. This is reference evidence, not a PCB model.

`../reference.sha256` binds all nine raw result files and both input templates.
The regression test also pins the manifest itself. Deliberate changes require
new solver evidence and review; do not regenerate hashes to hide a regression.
