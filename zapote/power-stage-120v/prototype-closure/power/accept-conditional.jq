# T1=2u is in the hash-pinned deck; this runner never overrides it.
# TD has the explicit microsecond suffix used by all three experiment loops.
# FALL=1 has no FROM guard: reject a pre-command crossing from the initial ramp.
.aborted == false and (.failed | length) == 0 and (.meas | length) == 7
and (.params | has("T1") | not)
and (.params.TD | test("^[0-9]+(\\.[0-9]+)?u$"))
and (.meas.gate_first_1p9 | type) == "number"
and (.meas.gate_first_1p9 > (2e-6 + (.params.TD | rtrimstr("u") | tonumber) * 1e-6))
