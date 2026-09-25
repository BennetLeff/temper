# Revision 26 Atopile build environment

## Result

Atopile is usable in this checkout when invoked from the locally cached uv
tool environment. I verified Atopile 0.2.69 and completed a build of a
disposable copy of the already compiled Revision 11 candidate. The source
fixture in the repository was not modified. This verifies the build tool and
offline cache path; it does **not** build or qualify a Revision 26 design.

Revision 26 did not contain an Atopile source candidate at the time of this
environment probe. The parent subsequently staged and built an AUX-only
candidate; see [the Revision 26 receipt](receipt.json). The unresolved
source/control requirements still prevent product qualification. Atopile
writes generated files under `build/` in the project directory.

## Pin discrepancy

The top-level `Makefile` invokes `atopile==0.2.69`. The root
`elec/ato.yaml` says `ato-version: 0.2.68`. The preserved Revision 11
reproduction record and its successful build also use 0.2.69. For reproducing
that established candidate and following the Makefile, use **0.2.69**; resolve
the manifest mismatch separately before treating `ato.yaml` as authoritative.

The checkout has Python 3.12.12 at
`/opt/homebrew/opt/python@3.12/bin/python3.12`, and uv 0.12.2 at
`/Users/bennet/.local/bin/uv`. The worktree `.venv` has Python 3.12 but does
not contain Atopile. The active Python 3.14.7 does not contain the `atopile`
module either.

## Verified offline route

The sandbox cannot access uv's default cache because that cache contains a
`.git` entry which the sandbox refuses to open. A prior successful Revision
11 build left Atopile 0.2.69 and its dependencies in
`/private/tmp/temper09-uv-cache`. Pointing uv at that cache works:

```sh
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --version
```

Observed output: `ato, version 0.2.69` (exit 0).

I copied the immutable Revision 11 source candidate to
`/tmp/power-entry-rev26-atopile-probe` and ran this build there:

```sh
cd /tmp/power-entry-rev26-atopile-probe
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --non-interactive build \
  elec/src/power_entry_pfc_control_candidate.ato:PowerEntryPfcControlCandidate
```

Observed result: exit 0, `Build complete!`, with the known implicit field
declaration and missing-MPN warnings. The copied source's top-level `.ato`
hash was `8491fb2fba480bcfa45713a0c2d9f67563bc6f197b727528c570d4939c345006`,
matching the preserved Revision 11 identity. The disposable build wrote only
to `/tmp/power-entry-rev26-atopile-probe/build/`.

## Network failure and recovery

An empty temporary uv cache cannot fetch Atopile in this sandbox. The
attempted command was:

```sh
UV_CACHE_DIR=/tmp/temper-rev26-uv-cache \
UV_TOOL_DIR=/tmp/temper-rev26-uv-tools \
uv tool run --from 'atopile==0.2.69' ato --version
```

It exited 2 after three retries with:

```text
Failed to fetch: `https://pypi.org/simple/atopile/`
client error (Connect)
dns error
failed to lookup address information: nodename nor servname provided, or not known
```

When network access to PyPI is available, the concrete recovery command for
an empty, writable temporary cache is:

```sh
UV_CACHE_DIR=/private/tmp/temper-rev26-uv-cache \
UV_TOOL_DIR=/private/tmp/temper-rev26-uv-tools \
/Users/bennet/.local/bin/uv tool run \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --version
```

Then, from the reviewed Atopile candidate directory, run the build form shown
above with that candidate's actual entry path and module name. Keep the
resulting `build/` outputs with that isolated candidate and verify their
hashes against the intended source before using them as integration evidence.

## Evidence boundary

This environment probe did not build Revision 26. Its later AUX-only build is
recorded separately in the parent receipt. Revision 11 built successfully in
a disposable copy as an environment check; that output is not a Rev26 netlist.
The offline cache path depends on the existing temporary cache remaining
present.
