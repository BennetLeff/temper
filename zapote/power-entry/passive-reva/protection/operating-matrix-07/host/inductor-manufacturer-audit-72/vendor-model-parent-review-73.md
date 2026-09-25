# Parent vendor-model review

The manufacturer ZIP and PDF were retrieved successfully with host network
access. The earlier sandbox DNS failures are historical, not evidence that
the files are unavailable. Original bytes, URLs and hashes are retained in
host-retrieval-73/acquisition.json.

The exact selected subcircuit is TOR75_760800301_180u. It contains a constant
180µH inductor with10µΩ Rser,18mΩ series resistance,46.9kΩ terminal parallel
resistance and11.58pF terminal parallel capacitance. No other subcircuit is
called. The bundled symbol defaults to a different118µH part, so inserting
that symbol without selecting the exact subcircuit would be wrong.

Rp is a dissipative fixed loss element; the worker's claim of no core-loss
element was too categorical. The network nevertheless contains no nonlinear
magnetic law, current-dependent inductance, saturation, temperature feedback
or thermal network. Its physical loss allocation is not established by the
library. It cannot close the saturation or thermal uncertainty. Compatibility
with ngspice has not been tested; no vendor model is adopted or executed.

The worker transcribed the library hash incorrectly. The parent receipt records
the full computed digest from the retained original bytes and preserves that
mismatch. Use vendor-model-parent-review-73.json and acquisition.json as the
hash authorities, not the worker's copied library digest.
