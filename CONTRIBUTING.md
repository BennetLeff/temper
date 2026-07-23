# Contributing

## Project Structure

- `firmware/` — ESP32-S3 induction cooker firmware (C, 8-state machine)
- `packages/temper-placer/` — JAX-based PCB placement optimizer
- `packages/temper-*` — supporting Python packages (DRC, workflow, tools, testing)
- `pcb/` — KiCad schematics and layout
- `docs/` — plans, solutions, architecture, specs
- `scripts/` — CI gates, profiling, regression tools

## Development Workflow

### Before You Start

1. Check [`docs/solutions/`](docs/solutions/) for documented fixes and patterns
   relevant to the area you're touching.
2. If this is a significant feature, create a plan in [`docs/plans/`](docs/plans/)
   following the existing naming convention (`YYYY-MM-DD-NNN-feat-*-plan.md`).

### Making Changes

1. Create a feature branch: `git checkout -b feat/your-feature`
2. Make your changes, following existing code conventions
3. Run the gates:

```bash
# Firmware tests
cmake -B firmware/test/build firmware/test
cmake --build firmware/test/build
./firmware/test/build/test_state_machine_only

# Import boundary check
uv run python scripts/import_linter_gate.py
```

### Codegen Regeneration

If you edit the following YAML manifests, you **must** regenerate and commit
the derived files:

| Manifest | Generated File(s) | Command |
|----------|-------------------|---------|
| `firmware/config.yaml` | `firmware/config.h` | `python3 firmware/tools/gen_config.py` |
| `firmware/transition_table.yaml` | `firmware/main/transition_table.h`, `firmware/test/test_transition_table_generated.c` | `python3 firmware/tools/gen_transition_table.py` |

CI checks for drift and will fail if you forget.

### Script Manifest

Every `scripts/*.py` file must have an entry in `scripts/manifest.yaml`.
After adding a new script:

1. Add an entry to `scripts/manifest.yaml`
2. Run `uv run python scripts/trace_invocations.py`

CI enforces this via `check_manifest_gate`.

### Import Boundaries

The `.importlinter` file defines permitted imports between packages. Before
pushing, run:

```bash
uv run python scripts/import_linter_gate.py
```

### CI Changes — Docker-PR Workflow

Any change to `.github/docker/**`, the CI Dockerfile, or the Rust toolchain
config must follow this workflow:

1. **Local pre-check**: build the image locally before opening the PR:

   ```bash
   docker build -f .github/docker/ci.Dockerfile -t temper-ci-check .
   docker run --rm temper-ci-check rustc --version
   ```

   If Docker is unavailable locally, document that in the PR body and request
   explicit review of the Dockerfile diff.

2. **Pre-merge validation**: as of PR #316, `docker-build.yml` triggers on
   `pull_request` for `.github/docker/**` and
   `.github/workflows/docker-build.yml` paths. The `Docker CI Image / build`
   job runs automatically on Dockerfile-only PRs --- wait for it to pass before
   requesting review or merging.

3. **Commit scope**: keep Dockerfile-only PRs narrow. Do not bundle Dockerfile
   changes with feature work --- a Docker-image rebuild on every feature PR
   slows CI for everyone and hides the regression source if a build breaks.

4. **Toolchain pin discipline**: `RUSTUP_HOME` and `CARGO_HOME` are set
   explicitly in the Dockerfile (landed via PR #292 and #316 --- see issue
   [#315](https://github.com/BennetLeff/temper/issues/315) for context). Any
   new env-var or toolchain change must document *why* it's needed and which
   CI step breaks without it.

5. **Iteration discipline**: if a Dockerfile PR breaks post-merge (something
   that only surfaces once the image is actually built by a downstream job),
   file a focused PR that fixes the root cause rather than patching symptoms
   iteratively. The `fix/docker-rustup-final` arc (December 2026 --- 19 of 25
   recent merges, see issue
   [#315](https://github.com/BennetLeff/temper/issues/315)) is the cautionary
   example: each fix closed a gap the previous one missed because no pre-merge
   Docker build was running.

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new feature
- `fix:` — bug fix
- `chore:` — maintenance (CI, deps, tooling)
- `docs:` — documentation
- `test:` — tests
- `refactor:` — code change that neither fixes a bug nor adds a feature

## Traceability

Use `@req(<plan-id>, <req-id>): <note>` annotations in source code to link
implementation back to plan requirements. See [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md)
for the full specification.
