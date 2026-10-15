// DigiKey half of the 2026-10-15 snapshot. Run in a normal browser tab on https://www.digikey.com (same-origin fetch of
// the public search page, which redirects to the product page on an exact match). No login, no cart.
// Set window.__MPNS = [[mpn, qty_per_board], ...] first; the result is window.__DK (paste into snapshot/digikey-2026-10-15.json).
async function dk(mpn, q) {
  const url = '/en/products/result?keywords=' + encodeURIComponent(mpn);
  let r = await fetch(url, {credentials: 'omit'}); let h = await r.text(); let final = r.url;
  const nd = (x) => { const m = x.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/); return m ? JSON.parse(m[1]) : null; };
  let d = nd(h);
  let env = d && d.props && d.props.pageProps && d.props.pageProps.envelope && d.props.pageProps.envelope.data;
  if (!env || !env.priceQuantity) {          // list page: follow an exact-MPN product link if there is one
    const esc = mpn.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\//g, '%2F');
    const m = h.match(new RegExp('href="(/en/products/detail/[^"/]+/' + esc.replace(/,/g,'(?:,|%2C)') + '/\\d+)"', 'i'));
    if (!m) return {mpn, status: r.status === 200 ? 'not listed (no exact match)' : 'HTTP ' + r.status, url: location.origin + url};
    r = await fetch(m[1], {credentials: 'omit'}); h = await r.text(); final = r.url; d = nd(h);
    env = d && d.props.pageProps.envelope && d.props.pageProps.envelope.data;
    if (!env || !env.priceQuantity) return {mpn, status: 'unparsed', url: final};
  }
  const pq = env.priceQuantity; const s = JSON.stringify(env);
  const lt = (s.match(/"standardLeadTime":"([^"]*)"/) || [])[1] || null;
  const mfr = (s.match(/"manufacturerProductNumber":"([^"]*)"/) || [])[1] || null;
  const tiers = [];
  for (const p of pq.pricing || []) for (const t of p.mergedPricingTiers || [])
    tiers.push([p.packaging, p.minOrderQuantity, +String(t.brkQty).replace(/,/g, ''), +String(t.unitPrice).replace(/[$,]/g, '')]);
  const at = (n) => { let b = null; for (const [pk, moq, bq, u] of tiers) if (bq <= n && moq <= n && (b === null || u < b)) b = u; return b; };
  return {mpn, mfr_mpn: mfr, status: 'ok', stock: +String(pq.qtyAvailable || '0').replace(/,/g, ''), lead: lt,
          unit_5: at(5 * q), unit_500: at(500 * q), tiers: tiers.length, url: final.split('?')[0]};
}
async function run() { const out = []; const L = window.__MPNS.slice();
  async function worker() { while (L.length) { const [m, q] = L.shift(); try { out.push(await dk(m, q)); } catch (e) { out.push({mpn: m, status: 'error ' + e}); } } }
  await Promise.all([worker(), worker(), worker()]); window.__DK = out; return out.length; }
