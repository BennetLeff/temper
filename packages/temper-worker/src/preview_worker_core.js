/** Capability-gated, base-owned wrapper for a PR-built Wasm Worker. */

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

function capability(request) {
  const header = request.headers.get("x-temper-preview-capability");
  return typeof header === "string" ? header : "";
}

function authorized(request, env, nowMs) {
  const expected = env?.PREVIEW_CAPABILITY;
  const expiresAt = Number(env?.PREVIEW_EXPIRES_AT ?? 0) * 1000;
  if (!expected || !Number.isSafeInteger(expiresAt) || expiresAt <= nowMs) {
    return { ok: false, status: 410 };
  }
  if (capability(request) !== expected) return { ok: false, status: 403 };
  return { ok: true };
}

export function createPreviewWorker(innerWorker, { now = () => Date.now() } = {}) {
  if (!innerWorker || typeof innerWorker.fetch !== "function") throw new Error("preview inner Worker is invalid");
  return {
    async fetch(request, env, ctx) {
      const auth = authorized(request, env, now());
      if (!auth.ok) return json({ status: "denied" }, auth.status);

      const url = new URL(request.url);
      if (url.pathname !== "/health" && url.pathname !== "/run-test") {
        return json({ status: "not-found" }, 404);
      }
      const response = await innerWorker.fetch(request, env, ctx);
      if (url.pathname !== "/health" || !response.ok) return response;

      let health;
      try { health = await response.json(); } catch { return json({ status: "invalid-inner-health" }, 500); }
      const testCount = health?.test_count;
      const maxTests = Number(env?.PREVIEW_MAX_TESTS ?? 10_000);
      if (
        !Number.isSafeInteger(maxTests) || maxTests <= 0 || maxTests > 10_000 ||
        !Number.isSafeInteger(testCount) || testCount <= 0 || testCount > maxTests
      ) {
        return json({ status: "invalid-census" }, 500);
      }
      const versionId = env?.CF_VERSION_METADATA?.id;
      if (!versionId) return json({ status: "missing-version-identity" }, 500);
      return json({
        ...health,
        status: "ok",
        head_sha: env.PREVIEW_HEAD_SHA,
        module_sha256: env.PREVIEW_MODULE_SHA256,
        comparison_contract_sha256: env.PREVIEW_COMPARISON_CONTRACT_SHA256,
        worker_service: env.PREVIEW_SERVICE,
        worker_version_id: versionId,
      }, 200);
    },
  };
}
