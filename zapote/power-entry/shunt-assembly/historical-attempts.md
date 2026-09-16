# Historical shunt assembly attempts

Runs 01–14 and solver probes are retained for diagnosis only. They are rejected
or superseded, and must not qualify hardware or supply current acceptance
evidence. They predate the correction that separates 20 µm of solder mask from
the FR4 core in the 1.6 mm finished stackup. The corrected core is 1.44 mm.

The archives preserve original decoded bytes. Archive manifests record their
SHA-256 digests. Raw and gzip representations at the same path are ambiguous
and must not coexist. The oversized run-10/nominal-25 mesh is split into
numbered gzip parts; its parts manifest records reconstruction hashes.

The historical archive is committed in two batches to keep individual Git
transfers manageable. The current model, tests and accepted numerical profile
are delivered in the subsequent implementation commit. Numerical acceptance
does not establish the resistor's internal heat path or assembly cooling.
