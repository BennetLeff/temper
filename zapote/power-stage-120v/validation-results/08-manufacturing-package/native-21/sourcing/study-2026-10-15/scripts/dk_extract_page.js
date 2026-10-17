// Run on a DigiKey page reached by navigating to /en/products/result?keywords=<MPN> in a normal browser tab (no login,
// no cart). Appends {q: searched MPN, mpn, stock, lead, tiers[[pack, moq, break, unit]], url, t} to localStorage.__dksnap.
(() => { const q = decodeURIComponent((location.search.match(/keywords=([^&]*)/) || [, ''])[1]) || document.title.split(' ')[0];
  const nd = document.getElementById('__NEXT_DATA__'); let rec;
  try { const d = JSON.parse(nd.textContent).props.pageProps.envelope.data; const pq = d.priceQuantity;
    if (!pq) throw 0; const s = JSON.stringify(d); const tiers = [];
    for (const p of pq.pricing || []) for (const t of p.mergedPricingTiers || []) tiers.push([p.packaging, p.minOrderQuantity, +String(t.brkQty).replace(/,/g, ''), +String(t.unitPrice).replace(/[$,]/g, '')]);
    rec = {mpn: (s.match(/"manufacturerProductNumber":"([^"]*)"/) || [])[1], stock: +String(pq.qtyAvailable || '0').replace(/,/g, ''),
           lead: (s.match(/"standardLeadTime":"([^"]*)"/) || [])[1] || null, tiers, url: location.origin + location.pathname, t: new Date().toISOString()};
  } catch (e) { rec = {mpn: null, status: 'not a single product page (no exact match or blocked)', title: document.title, url: location.href.split('&')[0], t: new Date().toISOString()}; }
  const all = JSON.parse(localStorage.__dksnap || '[]'); all.push(rec); localStorage.__dksnap = JSON.stringify(all);
  return [rec.mpn, rec.stock, rec.lead, (rec.tiers || []).length].join('|'); })()
