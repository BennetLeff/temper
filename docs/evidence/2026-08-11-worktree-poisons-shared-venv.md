<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false -->

# A worktree silently poisons the shared venv: four confirmed modes (2026-08-11)

**Date:** 2026-08-11
**Status:** resolved — `scripts/check_venv_integrity.py` (added the same day) closes mode 3

## The incident

The shared `.venv` at the main checkout was found with its editable-install
pointers rewritten to **an agent's git worktree** rather than the main
checkout:

```
_editable_impl_temper_placer.pth      -> .claude/worktrees/agent-ab1dbe8162fa0fbae
_editable_impl_temper_workflow.pth    -> .claude/worktrees/agent-ab1dbe8162fa0fbae
__editable__.temper_rust_router_core  -> .claude/worktrees/agent-ab1dbe8162fa0fbae
```

Every measurement taken against that venv in that window ran against the
worktree's code, not `main` — and nothing indicated it: imports succeeded,
numbers came back confident and wrong.

## The four confirmed silent-staleness modes

All four are reachable from an ordinary worktree session running
`maturin`/`uv` directly instead of through `make`:

1. **`maturin` refuses outright if `VIRTUAL_ENV` and `CONDA_PREFIX` are
   both set.** A loud failure — the safe end of the list. Fix: unset
   whichever you are not using before invoking `maturin` directly.
2. **Plain `uv run maturin develop` from a worktree targets a *per-worktree*
   venv and no-ops against the shared one.** If `UV_PROJECT_ENVIRONMENT` is
   not pointed at the shared `.venv` (or the worktree has its own via
   `make venv-isolate`), the build "succeeds" into a venv nobody is
   importing from — a silent no-op, not a hijack, but just as misleading:
   the shared venv's extension is untouched and still stale.
3. **`maturin develop --active` run from a worktree rewrites the SHARED
   venv's editable pointers** — the incident above. `--active` targets
   whatever venv is currently *active* (`VIRTUAL_ENV`), not one scoped to
   the worktree it ran from. When that active venv is the shared one, every
   subsequent `import` from *any* worktree — including the main checkout —
   silently resolves into the worktree that ran the command, until someone
   notices or rebuilds. This is the mode `scripts/check_venv_integrity.py`
   exists to catch (added same day, commit `17fb06c11`).
4. **`maturin develop` can report "Installed" while leaving the `.so`
   untouched.** Five rebuilds exited 0 in a row while the artifact stayed
   dated a day behind the source that had changed underneath it. This is
   `scripts/check_stale_extensions.py`'s territory, and it is the reason
   "the build tool said success" is never trusted anywhere in this repo's
   gates.

## Why mode 3 is silent, even to the freshness gate

`check_stale_extensions.py` catches mode 4's mtime symptom but not mode 3's
redirection: a hijacked-but-not-yet-rebuilt venv still imports a `.so` that
is content-fresh *relative to the worktree it was built from* — which is
exactly what makes the hijack silent. The staleness gate has no way to know
it is comparing against the wrong checkout's sources in the first place.
That is why the venv-*identity* question (`check_venv_integrity.py`) is
logically prior to the per-crate *freshness* question and runs before it in
CI.

## Related measurement lies from stale `.so` files

Believing a measurement taken against a stale extension is the expensive
mistake, not the rebuild:

- One session's `tests/deterministic` run reported **76 failures, of which
  72 were stale extensions and only 4 were real**.
- Separately, an agent reported `temper_orchestration.RouterPipeline` as
  "missing — a pre-existing repo defect" when the symbol was simply absent
  from an installed `.so` that predated the commit adding it. Absence of a
  symbol is not evidence of a missing feature.

## Defences

- Run `make venv-isolate` in any worktree that builds or tests Rust
  extensions — it gets its own `.venv`, immune to any other checkout.
- Run `.venv/bin/python scripts/check_venv_integrity.py` (or `make
  venv-integrity-check`) any time a shared venv's trustworthiness is in
  doubt.
- Run `scripts/check_stale_extensions.py` *before* believing a number, not
  after a result surprises you.

## Related

- `docs/solutions/best-practices/shared-venv-silent-staleness-modes-2026-08-19.md`
  — the five-mode catalog (this incident plus the 2026-08-17 "shared venv
  serves main" mode) and the gate-ordering rationale.
- `docs/evidence/2026-08-17-shared-venv-serves-main-code.md` — the
  complementary mode: no poisoning needed, the healthy shared venv simply
  serves the wrong checkout.
- `docs/evidence/2026-07-27-stale-extension-gate.md` — the original
  stale-extension incident and the gate built for it.
