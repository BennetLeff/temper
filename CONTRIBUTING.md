# Contributing

## Layout

- `zapote/` — board validation workspace (Rust ERC/DRC/DFM, units, 120 V power stage). Start at [zapote/CHECKS.md](zapote/CHECKS.md); rules in [zapote/AGENTS.md](zapote/AGENTS.md).
- `firmware/` — ESP32-S3 firmware (C, 8-state machine); generators and gates in `firmware/tools/`.
- `docs/` — plans, solutions, evidence; `scripts/` — CI and worktree-safety tooling only.

## Workflow

1. Check [`docs/solutions/`](docs/solutions/) for documented fixes and patterns in the area you're touching.
2. Branch (`git checkout -b feat/your-change`), one worktree per agent. Never `git stash`.
3. Run what your change touches:

```bash
make zapote          # zapote/** changes
make firmware-test   # firmware/** changes (plus the firmware/tools gates in firmware-tests.yml)
```

4. Open a PR. `Required Python Tests` passes when the checks for the paths you changed
   (`zapote / rust`, Firmware Tests, `actionlint`) pass.

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/) for commit
messages and PR titles (release-please reads them):

- `feat:` new feature (minor bump)
- `fix:` bug fix (patch bump)
- `docs:`, `refactor:`, `test:`, `chore:`, `ci:`, `perf:` — no version bump

Breaking changes: add `!` after the type (e.g. `feat!: remove legacy API`) or a
`BREAKING CHANGE:` footer.
