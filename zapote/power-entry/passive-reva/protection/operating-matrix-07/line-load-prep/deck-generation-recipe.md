# Deck generation recipe (pending source acceptance)

This recipe records how to make a nine-point batch after the corrected cold
source is accepted. It does not execute simulations or claim any result.

1. Copy the accepted cold-source deck and its exact include closure into a
   new batch directory. Bind `source_identity.deck` and
   `source_identity.includes_sha256` in `manifest.json` to the accepted
   bytes. A `PENDING` identity is not executable evidence.
2. For each manifest row, change only the line source RMS and `RLOAD` parameter.
   Preserve the 60 Hz source, switching model, startup/ARM/PERMIT waveforms,
   timestep controls, probes, and output column order. Record a distinct deck
   hash for every generated input.
3. Run the simulator to its declared endpoint (the current corrected cold
   deck is staged for a 1 s endpoint with a 500 ms checkpoint). Normalize the
   floating source with `v(acsrc)-v(acn)` and `-i(Vac)` using the maintained
   normalizer, then invoke the strict checker with the exact endpoint, for
   example:

   ```sh
   rustc --edition=2021 -O checker/normalize.rs -o /tmp/matrix07-normalize
   rustc --edition=2021 -O checker/operating_point_checker.rs -o /tmp/matrix07-checker
   /tmp/matrix07-normalize RLOAD_OHM < raw.tsv \
     | /tmp/matrix07-checker --end-s ENDPOINT_S
   ```

4. Retain each raw trace, normalized trace hash, checker report, simulator
   log and source/deck hashes. A rejected, truncated, aliased, disabled-loop
   or energy-inconsistent row remains failed/unexecuted; do not widen a
   criterion or replace its source identity.
5. Fault scenarios remain downstream of an accepted normal point. This grid
   is a normal operating-point screen and does not qualify thermal behavior,
   component ratings, continuous output power or hardware operation.

