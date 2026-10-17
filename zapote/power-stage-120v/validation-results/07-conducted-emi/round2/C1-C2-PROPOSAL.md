# C1/C2 replacement review — proposal only

> **Implemented 2026-09-27 in native-14/15** after the owner approved it; see
> `native-15/verification/README.md`. The note below is kept as written.

Reviewed 2026-09-27 against source revision `267dcee72` and unchanged native-13
board SHA-256 `8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`.
No part, footprint, board or placement approval is recorded by this note.

The proposed **R463N410000N1M** is supported by the same official KEMET R46
datasheet already preserved at [the saved PDF](../sources/KEM_F3095_R46_X2_310_110C.pdf). The exact row is `R463N4100(1)N1(2)` on
page 10, with packaging `00` and tolerance `M` decoded on pages 1–2. It is
1.0 µF, ±20%, 310 VAC, class X2, with 22.5 mm nominal lead pitch and
26.5 × 11.0 × 20.0 mm body (length × width × height). The row's dV/dt is
200 V/µs, compared with 150 V/µs for the original 27.5 mm-pitch part.

Source: [KEMET R46, 2026-05-13](https://content.kemet.com/datasheets/KEM_F3095_R46_X2_310_110C.pdf),
SHA-256 `5a3131ce8de7445130b777cab1a5e1a17e6b5f3343faddfe19735221db205094`.

The exact replacement pitch matches the existing C1/C2 pad spacing. This is a
technically supported candidate for correcting the part/footprint conflict,
subject to regenerated source/native parity and mechanical checks. It does
not resolve the separate high-frequency parasitic inputs needed by task 07.

A local footprint must represent the nominal **11.0 mm width**, not the saved
10.5 mm width. Its courtyard must also account for the page-3 dimensional
maximums: length **26.8 mm**, width **11.2 mm**, height **20.1 mm**, plus the
chosen assembly allowance. Pad/drill fit must be checked against lead diameter
0.8 ± 0.05 mm and pitch 22.5 ± 0.4 mm. Update the associated 3D envelope too;
a corrected text label on the old 10.5 mm model would remain misleading.

C2 is rotated 90°, so width grows along board X; its length stays along board
Y. Thus widening the nominal body does not reduce its gap toward C5 along Y.
This directional fact is not a substitute for a tolerance-aware mechanical
check of both parts and their installed positions. No D4 carry-over or
fabrication release is inferred from an unchanged pose alone.

Implementation awaits the owner's source-change decision under master-plan
rule 4. The current simulation runs continue using the unchanged native-13
copper and original source identity.
