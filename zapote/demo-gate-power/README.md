# Gate-drive and power-entry checkpoint demo

Open index.html locally, or serve this directory on localhost. All images are
native KiCad renders from the source-bound candidates. The gate-drive construction
passes; the PFC candidate remains unrouted and must fail acceptance.

The construction-checkpoint.json files under each unit/evidence/ hash the actual
source/native/PCB receipts. Demo JSON/image copies are display artifacts only.
Native tests: zapote/current-sense/tests/native_initialization_oracle.py and
zapote/tools/test_refresh_native_footprints.py with the KiCad bundled Python.
Rust tests: CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test
--manifest-path zapote/Cargo.toml --workspace (221 passed).
