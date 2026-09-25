# Independent review disposition

The parent independently reproduced a false restart in v1 despite the worker's
12 passing tests. See `parent-v1-witness.rs`. The defect was in the production
PERMIT-loss path, while the worker's reset helper invalidated the session and
therefore concealed the difference in the tested path.

The worker corrected invalidation, added a bounded handshake deadline, source
challenge ordering and explicit fault observation. The parent added separate
adversarial tests and checked that deliberately retaining a session in
`invalidate()` causes the independent tests to fail (`parent-mutation.log`).

A second Luna agent (`pfc_stage`, read-only) reviewed v2 and found no stale-session
bypass under decoded-message semantics. It identified the in-flight START / source
reset window and the need for a PERMIT/health observer independent of transport
traffic. The final implementation supplies `observe_inputs` and no-traffic tests;
calling it in time still belongs to physical hardware/firmware integration.
The parent reproduced the in-flight window as `parent_boundary_witness`.

Disposition: bounded logical model only. It requires the stated persistent
counter, source intent, independent observer and scheduler contracts. It is not
accepted as an electrical replacement for revision-11 ARM. No waveform decoder,
processor-failure path, nonvolatile storage implementation, absolute time budget,
or isolation design is validated by these tests.

The requested delegation model was `gpt-5.6-luna`; the tool does not independently
attest the model actually served. Workers were interrupted after handback.
