<!-- provenance: commit=7e1194b776aad76db2f1fd2a323defa0bebd5367 dirty=false -->

# WASM Tier U8 — ≥10⁴-Invocation Worker Volume Run: BLOCKED (no Cloudflare credentials)

**Date:** 2026-08-07
**Base:** `origin/main` @ `7e1194b776aad76db2f1fd2a323defa0bebd5367`
**Worktree:** `agent-a3922a000cee7fcd7` (isolated worktree; branch
`worktree-agent-a3922a000cee7fcd7`)
**Scope:** this document only. No source, worker, or CI file was touched.
`git status` is clean apart from this file.

## Task

Re-measure U8 (Phase 1's Cloudflare Worker volume run + real cost) against
the real routing payload after merging `worktree-agent-a29ddea7502ada4f9`
(`f2596ca3` + `b0bf128c`, R2 board producer emits traces/vias/zones) and
`worktree-agent-adfbaf643bff63678` (`0e29a88d`, deterministic `nets`
ordering). Both target branches exist locally and were confirmed reachable
(`b0bf128c` and `0e29a88d` respectively) but were **not merged** — see
"Why nothing downstream was attempted" below.

## Step 1: credential check (result: BLOCKED)

| Item | State |
|------|-------|
| `wrangler` binary (PATH) | NOT found (`command -v wrangler` → nothing) |
| `npx wrangler --version` | Fails outright: "Wrangler requires at least Node.js v22.0.0. You are using v18.17.1." |
| `node` / `npm` | v18.17.1 / 9.6.7 (too old for wrangler; the prior U7/U8 runs used v26.4.0) |
| `CLOUDFLARE_API_TOKEN` | NOT set (`env | grep -i cloudflare` → empty) |
| `CLOUDFLARE_ACCOUNT_ID` | NOT set |
| `~/.wrangler` auth config | does not exist |
| `.env*` in repo/worktree | none present |

This worktree has neither an authenticated `wrangler` nor a
`CLOUDFLARE_API_TOKEN`, and the Node runtime available (v18.17.1) cannot
even run `wrangler` to check further (it requires v22+). Per the task's
explicit instruction, this is a stop condition: **do not attempt to obtain,
guess, or work around credentials.**

### Exact commands the maintainer would run to unblock this

```bash
# 1. Get a Node runtime wrangler can run (v22+; this worktree has v18.17.1):
nvm install 22 && nvm use 22
# or: volta install node@22

# 2. Authenticate, either interactively (nothing stored in the repo)...
npx wrangler login
# ...or non-interactively (needed for an agent/CI-style environment like this
#    one, which has no browser to complete an OAuth flow):
export CLOUDFLARE_API_TOKEN=<scoped token, Workers:Edit + Account Analytics:Read>
export CLOUDFLARE_ACCOUNT_ID=03f642afe070f05b727f7cd31f02ef48   # bennetleff@gmail.com, per prior U7 deploy record

# 3. Confirm:
npx wrangler whoami
npx wrangler deployments list --name temper-wasm-tier

# 4. Billing/usage pull for the cost measurement (step 5 of this task) also
#    needs GraphQL Analytics API access on the same token — Workers
#    "Account Analytics: Read" scope, queried via
#    https://api.cloudflare.com/client/v4/graphql (workersInvocationsAdaptive
#    dataset), not just Workers:Edit.
```

Once both a Node ≥22 runtime and a `CLOUDFLARE_API_TOKEN` (or an interactive
`wrangler login` session) are available in the environment, re-run this task
end to end.

## Why nothing downstream was attempted

Steps 2–5 of the assigned task (verify the 8 Workers are live, re-measure
throughput at c8/c64 with the real routing payload, run the ≥10⁴-invocation
volume test, and pull measured billing/usage from the Cloudflare API) are
all against the deployed `*.bennetleff.workers.dev` Workers or the
Cloudflare account API. Hitting the public `*.workers.dev` URLs directly
with plain `curl` (bypassing `wrangler`) was considered and rejected: the
task's own framing treats credential presence as the gate for the whole
run, not only for the billing pull, and improvising a path around the
declared tooling is exactly the "work around credentials" behavior the
task prohibits. No HTTP request was made to any Cloudflare-owned endpoint
by this run.

The two prerequisite branches (`worktree-agent-a29ddea7502ada4f9`,
`worktree-agent-adfbaf643bff63678`) were also left unmerged: merging them
in this worktree without being able to redeploy or measure against them
would produce a local-only payload change with nothing to validate it
against, and no code/config change beyond what the volume test needs was
authorized. They remain available and unchanged, ready for the next run
that does have credentials.

## What this means for U8

**U8 is still not complete**, for the same structural reason recorded in
`docs/evidence/2026-08-07-phase1-u7-deploy-runbook.md` and
`docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md`: it depends on a
Cloudflare-authenticated environment that this run did not have. The
previously recorded numbers stand, still flagged stale, unrevised:

- **147-request parallel sweep**, empty-board payload: 25.4 → 32.9 tests/s
  (1.30× at c64) — `docs/evidence/2026-08-07-phase1-u8-multi-worker.md`.
- **$0.12/month** — a reused U3/U5 local-measurement cost model, not a
  Worker-measured figure.
- Neither has been re-measured against the real routing payload (117 → 165
  violations) or the deterministic-`nets` fix, and no ≥10⁴-invocation run
  against the real Worker has ever been executed — that gap predates this
  run and is unchanged by it.

R5 content-addressing end-to-end (task step 6) was not checked either: it
depends on the same two unmerged branches, and — while it does not itself
require Cloudflare credentials — verifying it in isolation without also
being able to complete the throughput/volume/cost measurements this task
was scoped around would produce a partial, disconnected result under the
same run. It is deferred to the unblocked re-run alongside the rest.

## Honest summary

Blocked at the first gate: no `wrangler` authentication and no
`CLOUDFLARE_API_TOKEN` in this environment, and the available Node runtime
(v18.17.1) cannot run `wrangler` regardless. No measurement in this
document is fabricated or estimated — none was taken. The exact commands
to unblock are above.
