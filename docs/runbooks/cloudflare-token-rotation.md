# Cloudflare API Token Rotation (`CF_TOKEN`)

**Trigger for this runbook:** the current `CF_TOKEN` repository secret was
pasted in plaintext into an assistant conversation transcript. It carries
account-wide Workers edit permission. Treat it as compromised and rotate it.

This is a mechanical checklist, not an investigation — the investigation
(what consumes the token, what the token actually needs to be able to do,
what breaks if the rotation goes wrong) is recorded below the checklist so
the reasoning survives the next time this has to happen.

---

## 0. Before you start

- You need an authenticated session on the Cloudflare dashboard for account
  `03f642afe070f05b727f7cd31f02ef48` (`bennetleff@gmail.com`) and `gh` CLI
  access with permission to write repository secrets on
  `BennetLeff/temper`.
- **Do not revoke the old token until step 4 (verification) passes.** The
  old token has already been exposed, so there is no security benefit to
  deleting it before the new one is confirmed working — but there is a real
  cost: revoking first and then discovering the new token is mis-scoped
  turns a 5-minute rotation into an outage of the deploy path with no way
  to fix it except creating a third token. Leaving a leaked-but-still-valid
  token active for the ~5 extra minutes this takes is the correct trade.

## 1. Create the new token (Cloudflare dashboard)

Cloudflare dashboard → **My Profile → API Tokens → Create Token → Create
Custom Token**.

Grant exactly this permission — no more:

| Scope | Resource | Permission |
|---|---|---|
| Account | Workers Scripts | Edit |

- **Account Resources**: restrict to the single account `03f642afe070f05b727f7cd31f02ef48` (not "All accounts").
- **Zone Resources**: none. Do not add a Zone Resources row at all.
- Add no other permission group (no Workers KV Storage, no Workers Routes,
  no Workers Tail, no Account Settings, no D1/R2/Durable Objects).
- Leave **Client IP Address Filtering** and **TTL** at their defaults unless
  your own security policy requires otherwise — narrowing those further is
  fine, but not required by anything this deploy path does.

This is narrower than the token being replaced (which carries account-wide
Workers edit permission — see §A below for why `Workers Scripts:Edit` on one
account is the actual requirement, not an approximation of it). Rotating to
an equally broad token resets the exposure clock without reducing the blast
radius of the next leak; do the narrowing now, while you're already in the
dashboard.

Copy the token value. You will paste it once, into `gh secret set` in the
next step, and nowhere else — not into a chat transcript, not into a file
in this repo, not into a commit message.

## 2. Update the GitHub secret

From a terminal with `gh` authenticated against `BennetLeff/temper`:

```bash
gh secret set CF_TOKEN --repo BennetLeff/temper
```

Use the interactive prompt (paste when prompted, then press Enter/Ctrl-D)
rather than piping the value in with `echo` — `echo` without `-n` appends a
trailing newline to the secret value, which is exactly the kind of
non-empty-but-wrong value the deploy workflow's own emptiness check
(`.github/workflows/wasm-tier-deploy.yml:477`) does **not** catch (see §B —
that check only guards against an empty string, not a malformed one). If you
must pipe it, use `printf '%s' "$TOKEN" | gh secret set CF_TOKEN --repo BennetLeff/temper`.

Confirm the secret was updated (this does not reveal the value):

```bash
gh secret list --repo BennetLeff/temper
```

You should see `CF_TOKEN` with an updated timestamp.

## 3. Verify the new token before revoking the old one

**Do not use `dry_run=true` for this.** It deliberately never touches
`CF_TOKEN` (see §C) — it proves the build/bundle path works, not that the
credential works. Verifying the credential requires a real deploy.

Trigger a real (non-dry-run) run of the deploy workflow by hand:

```bash
gh workflow run wasm-tier-deploy.yml --repo BennetLeff/temper
```

(Leave `dry_run` at its default of `false` — omit the flag, or pass
`-f dry_run=false` explicitly.) This redeploys all 19 Workers with whatever
is currently on `main`. That is safe to do speculatively: redeploying
byte-identical content is idempotent, not disruptive (the workflow's own
header makes the same point about the nightly schedule's unconditional
redeploy).

Watch the run:

```bash
gh run watch --repo BennetLeff/temper $(gh run list --repo BennetLeff/temper \
  --workflow wasm-tier-deploy.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

**Both of these must go green** for the rotation to be verified:

1. The **"Deploy every Worker in the topology"** step — if the new token is
   empty, wrong, expired, or scoped to the wrong account/permission, this
   step fails here (an auth or permission error from `wrangler deploy`
   itself, non-zero exit under `set -euo pipefail`).
2. The **"Verify the deployed corpus is what was just built (R5.1)"** step
   — confirms every one of the 19 Workers is actually serving what this run
   just built, not just that the deploy command reported success.

If both pass, the new token is confirmed working end-to-end. Only now:

## 4. Revoke the old token

Cloudflare dashboard → **My Profile → API Tokens** → find the old token →
**Roll** or **Delete**. Confirm it no longer appears in the active token
list.

## 5. Rollback (if step 3 fails)

If the workflow run from step 3 fails at the deploy step (bad credential) or
the verify step (deployed anyway but not what was expected — unlikely for a
credential problem, but check):

1. **Do not revoke the old token** — it is still valid and the deploy path
   still works on it, since you have not touched it.
2. Diagnose from the failed step's `::error::` annotation:
   - Empty-token message → the secret didn't get set correctly; redo step 2.
   - Auth/permission error from `wrangler` itself → the new token is
     missing the `Workers Scripts:Edit` permission on account
     `03f642afe070f05b727f7cd31f02ef48`, or was scoped to the wrong account;
     go back to step 1 and recreate it.
3. Once fixed, re-run step 2 and step 3. The old token remains the one
   actually in use in the interim (nothing regresses).
4. Only proceed to step 4 once a real, non-dry-run run has gone fully
   green.

---

## Background — why the steps above are what they are

### §A. What the token actually needs (minimum permission set)

The deploy path is entirely: `wrangler deploy` against 19 committed
`wrangler.toml` files (one per Worker: `packages/temper-worker/wrangler.toml`
+ 18 under `packages/temper-worker/families/*/wrangler.toml`), all pointed
at the same `account_id = "03f642afe070f05b727f7cd31f02ef48"`. Checked all
19: none declares `[[routes]]`, `route`, `kv_namespaces`, `r2_buckets`,
`d1_databases`, or `durable_objects` — the Workers are stateless code with
no bindings, published only to their default `*.workers.dev` subdomain.
That means:

- **Required**: Account → **Workers Scripts** → **Edit**, scoped to account
  `03f642afe070f05b727f7cd31f02ef48`. This is not an inference — it's stated
  directly in the deploy workflow's own error message
  (`.github/workflows/wasm-tier-deploy.yml:478`) and in
  `docs/evidence/2026-08-07-phase1-u7-deploy-runbook.md:30` ("a token with
  `Workers Scripts:Edit` is in `CF_TOKEN`" — i.e. this is what the *current*
  token was scoped to have, whether or not it has drifted since).
- **Not required, and should not be granted**: Workers Routes (no zone
  routes anywhere in this repo's `wrangler.toml` files), Workers KV
  Storage, Workers Tail, Zone-anything, Account Settings, D1/R2/Durable
  Objects. The task framing that the current token carries "account-wide
  Workers edit permission" is broader than what's inferred here from the
  repo's own config — that gap is the actual security improvement rotation
  gives you, but only if the replacement token is scoped this narrowly
  rather than recreated with the same broad grant.

### §B. Consumption — the complete list

Grepped `.github/workflows/`, `tools/wasm/`, `scripts/`, and `Makefile` for
`CF_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and `wrangler`.

- **The only place `CF_TOKEN` is read, anywhere in CI**: one step, one job,
  one workflow — `.github/workflows/wasm-tier-deploy.yml`, job `deploy`,
  step **"Deploy every Worker in the topology"** (line 471-498). It maps
  the repo secret to the environment variable name `wrangler` actually
  reads:
  ```yaml
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_TOKEN }}
  ```
  This mapping is load-bearing and deliberate — the secret is named
  `CF_TOKEN`, not `CLOUDFLARE_API_TOKEN`; `wrangler` only ever reads the
  latter from the environment. `secrets.CLOUDFLARE_API_TOKEN` would resolve
  to empty and every deploy would auth-fail (this exact trap is called out
  in the workflow's own comments at line 445-449).
  - This step's own precondition check (line 477) only verifies the mapped
    value is **non-empty**:
    ```bash
    if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then ... exit 1; fi
    ```
    It does **not** validate the token is well-formed, unexpired, or
    correctly scoped — that's checked implicitly, later, by `wrangler
    deploy` itself failing on auth. This is why step 3 above (a real
    dispatch) is necessary; the empty-check alone cannot confirm a rotation
    succeeded.
- **`.github/workflows/wasm-tier-pr.yml`** and **`.github/workflows/wasm-tier-nightly.yml`**:
  neither reads `CF_TOKEN` or any Cloudflare secret. Both say so in their
  own header comments and both were verified by grep to contain zero
  `secrets.` references to anything Cloudflare-related. `wasm-tier-nightly.yml`'s
  `worker-dispatch-r19` job talks to the deployed Workers over their public,
  unauthenticated `*.workers.dev` HTTPS endpoints (`/health`, `/run-test`) —
  no credential involved, by design (see that workflow's own "Preflight"
  step comment, which documents removing a prior, unnecessary
  `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` presence-gate that nothing
  it ran ever actually consumed).
- **`Makefile` target `wasm-worker-deploy`** (and the `wasm-worker-stage`
  it depends on) is a second, *local*, operator-run path to the same
  `wrangler deploy` loop — for use outside CI. It does not read `CF_TOKEN`
  at all; it relies on whatever Cloudflare credential is present in the
  operator's own shell (`wrangler login` OAuth session, or a locally
  exported `CLOUDFLARE_API_TOKEN`). **Rotating the GitHub secret does not
  touch this path.** If you have ever run `make wasm-worker-deploy` locally
  and have a lingering `wrangler login` session or a `CLOUDFLARE_API_TOKEN`
  in your shell environment/profile, that is a separate credential with the
  same account access and is outside this runbook's scope — check
  `npx wrangler whoami` locally and revoke/rotate that session too if it
  exists. This repo contains no such credential (confirmed: no `.dev.vars`,
  no `.wrangler/` state, nothing wrangler-related in `.gitignore` beyond the
  gitignored staged `.wasm` build artifacts).
- No other workflow in `.github/workflows/` references `CF_TOKEN`,
  `CLOUDFLARE_API_TOKEN`, or `CLOUDFLARE_ACCOUNT_ID`. `gh secret list`
  confirms `CF_TOKEN` is the only secret on this repository.

### §C. What `dry_run=true` does and does not prove

`.github/workflows/wasm-tier-deploy.yml`'s `workflow_dispatch` input
`dry_run` gates two steps, both `if: ${{ !inputs.dry_run }}` — meaning when
`dry_run` is true, **neither the credentialed deploy step nor the R5.1
freshness-verify step runs at all**. In their place, a separate
`if: ${{ inputs.dry_run }}` step runs `wrangler deploy --dry-run` per
Worker, which resolves `wrangler.toml`, bundles with esbuild, and reports
bundle size — all without ever setting `CLOUDFLARE_API_TOKEN` in its
environment. The workflow's own comment says this explicitly: dry-run
"needs no credential, which is exactly why it is the pre-merge proof for a
change to this file." **`dry_run=true` deliberately proves nothing about
whether `CF_TOKEN` is valid** — it is a build/bundle check, not a
credential check. Do not use it to validate a rotation; use step 3 above
(a real, non-dry-run `workflow_dispatch`) instead.

### §D. Blast radius of a bad rotation — read this before step 3

**This is the most important finding in this audit.** This repo has a
documented history (`.github/workflows/wasm-tier-deploy.yml`'s own header,
"WHY THIS EXISTS") of the deployed WASM verification tier going stale while
CI reported green: a 2026-08-07 → 2026-08-10 window where the deployed
Workers carried 147 tests against a 1,708-test suite, and the nightly sweep
reported `agreement_rate: 1.0` the entire time — because nothing was
redeploying automatically, and the fact that a redeploy was needed was
purely a human-noticing problem.

Since 2026-08-10, that gap is structurally narrower but **not fully
closed**, and a bad token rotation lands squarely in what's left:

- A wrong/expired/mis-scoped-but-**non-empty** `CF_TOKEN` passes the
  workflow's only precondition check (§B) and fails later, inside
  `wrangler deploy` itself, on the **first** Worker in the deploy loop.
  Under `set -euo pipefail` this fails the step immediately — no partial
  deploy, the tier's currently-live Workers are untouched (this is
  fail-safe, not fail-silent, in the sense that it can't corrupt the
  deployed state; the failure just doesn't do anything).
- Because the step failed, GitHub Actions **skips** the subsequent "Verify
  the deployed corpus" (R5.1) step in the *same* run (it has no
  `if: always()`) — so this specific run never gets to explicitly say "the
  tier is stale," it just shows as a failed job.
- **Whether a human notices that failure is exactly the variable the
  2026-08-07 incident turned on.** The deploy workflow now runs
  automatically — on every push that touches a corpus path, and on a
  `30 3 * * *` schedule — so if the token is broken, *every single one of
  those runs fails*, repeatedly, for as long as the token stays broken.
  That is loud in the sense that the Actions tab and (for push-triggered
  failures) GitHub's default failure notifications will show it. It is
  silent in the sense that nothing pages anyone or blocks a PR — this
  workflow is explicitly advisory (`permissions: contents: read`, never a
  required check, not reachable from `pull_request`).
- **The backstop that keeps this from recreating the 2026-08-07 window
  indefinitely**: `wasm-tier-nightly.yml`'s `worker-dispatch-r19` job runs
  its *own*, independent R5.1 freshness check
  (`tools/wasm/check_deployed_freshness.mjs`, workflow line ~921) every
  night at `40 4 * * *` — about 70 minutes after the deploy workflow's own
  schedule — and **fails the job outright on any staleness/count mismatch,
  with no `continue-on-error`**. So even in the worst case (a rotation
  breaks the token, nobody watches the Actions tab, every push-triggered
  deploy quietly fails for a day), the tier does not go stale *unnoticed
  forever* the way it did before — the next nightly run reports it loudly,
  within at most ~24 hours.

**Net answer**: a bad rotation cannot reproduce the old failure mode
exactly (checks reporting green over a stale tier) — both the deploy
workflow's own auth failure and the nightly's independent R5.1 check fail
loudly, with no code path that reports success while serving stale
Workers. But there is a real **detection-lag window of up to ~24 hours**
between "the rotation silently broke the automatic deploy path" and "a
human-visible, unambiguous failure shows up," because the deploy workflow
itself is advisory and nothing currently pages on its failure. **This is
exactly why step 3 exists**: verifying the new token with a real,
watched, on-demand dispatch closes that window to minutes instead of
leaving it to the next scheduled run to find.

### §E. Other credential exposure checked in the same class

- **19 `wrangler.toml` files** (`packages/temper-worker/wrangler.toml` +
  18 under `packages/temper-worker/families/*/`) were read in full. Every
  one carries `account_id = "03f642afe070f05b727f7cd31f02ef48"` and nothing
  else besides `name`, `main`, `compatibility_date`, and an `ABI_VERSION`
  var. A committed `account_id` is normal — Cloudflare account IDs are not
  secret, they're a routing identifier, and `wrangler` needs one to know
  which account to target — so this is not a finding, it's confirmation
  that nothing *else* is sitting next to it. No token, no email, no zone
  ID, no KV/R2/D1 identifiers in any of the 19 files.
  - Minor, unrelated latent bug noticed in passing (not a security issue,
    not touched by this change): several of the family `wrangler.toml`
    files place `account_id` *after* the `[vars]` table header, which TOML
    parses as `vars.account_id` rather than the top-level key — the files'
    own comments (e.g. `families/geometry/wrangler.toml`) already document
    this as latent-but-harmless because the token currently resolves to a
    single account regardless. Not a credential-exposure issue; noted only
    because it was visible while auditing every file's account_id line.
  - No `.dev.vars`, no `.wrangler/` state directory, and nothing
    Cloudflare-related in `.gitignore` beyond the already-gitignored staged
    `.wasm` build artifacts and their sha256 sidecars.
- **`gh secret list`** on `BennetLeff/temper` shows exactly one secret:
  `CF_TOKEN`. No `CLOUDFLARE_API_TOKEN`, no `CLOUDFLARE_ACCOUNT_ID`, no
  second Cloudflare token under a different name anywhere at the repo
  level.
- **Other workflows' secrets** (grepped every `.github/workflows/*.yml` for
  `secrets.`): `dashboard-deploy.yml`, `metrics-reconcile.yml`,
  `docker-build.yml`, `firmware-perf-record.yml`, and
  `pr-pipeline-scorecard.yml` each reference only `secrets.GITHUB_TOKEN`
  (GitHub's own ambient, auto-rotated token) — none references anything
  Cloudflare-related. This audit found no second leaked-token-shaped risk
  riding along with `CF_TOKEN`.
