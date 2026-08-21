<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false -->

# The fifth venv mode: the shared venv reads *main*, not your worktree (2026-08-17)

**Date:** 2026-08-17
**Status:** resolved as a documented defence (no poisoning involved — the healthy state is the hazard)

## The mode

The four 2026-08-11 modes (`docs/evidence/2026-08-11-worktree-poisons-shared-venv.md`)
are all "a worktree poisons the venv." The complementary mode needs **no
poisoning at all**: it is the healthy, correct state of a shared venv.

The shared `.venv`'s `temper_placer` is editable-installed against the
**main checkout**:

```
$ .venv/bin/python -c "import temper_placer; print(temper_placer.__file__)"
/home/bennet/Desktop/temper/packages/temper-placer/src/temper_placer/__init__.py
```

So a worktree agent that edits Python and then runs
`.venv/bin/python scripts/route_board.py` **measures `main`'s code, not its
own change.** Nothing errors. The route succeeds. The numbers come back
confident and wrong.

## The cost: a real round trip

An agent fixing the pour-stitch `track_width` defect measured **197
violations still present after its fix**, and would have reported a
regression. The tell was that every violation still read
`"actual 0.3000 mm"` — the literal value the fix had just removed. Code
that no longer exists cannot produce violations; the measurement was of
`main`.

## The defences (in order of preference)

1. **`make venv-isolate` in your worktree.** The worktree gets its own
   `.venv` and the question disappears — it fixes reads as well as writes.
2. **If you must use the shared venv, verify what you are importing before
   you believe a number** — `python -c "import temper_placer; print(temper_placer.__file__)"`
   and confirm the path is your worktree. A `sys.path` override wrapper
   works, but is easy to get subtly wrong.

## The generalizable rule

When a measurement contradicts a change you just made, suspect the
measurement before the change. Ask what the number would look like if your
edit were not in effect at all — here, "identical to before" was exactly
the observed result, and that is the signature.

## Related

- `docs/solutions/best-practices/shared-venv-silent-staleness-modes-2026-08-19.md`
  — the five-mode catalog this mode completes.
- `docs/evidence/2026-08-11-worktree-poisons-shared-venv.md` — the four
  poisoning modes.
