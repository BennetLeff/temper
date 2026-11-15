"""Compare the live JLC library answers (jlc-live/*.json, fetched 2026-11-15) with the 2026-11-10 snapshot and the order need."""
import csv, json, sys, os
R = os.path.dirname(os.path.abspath(__file__))
root = sys.argv[1]
snap = json.load(open(root + '/validation/rev-g/prices/jlc-parts-2026-11-10.json'))['parts']
N = 5
rows = []
ext = 0; tot_old = tot_new = 0
for r in csv.DictReader(open(root + '/manufacturing/bom-complete.csv')):
    c = r['LCSC']
    try:
        l = json.load(open(f'{R}/jlc-live/{c}.json'))['data']['componentPageInfo']['list']
    except Exception as e:
        print('FETCH FAIL', c, e); continue
    m = [x for x in l if x['componentCode'] == c]
    if not m: print('NOT FOUND', c, r['MPN']); continue
    x = m[0]
    need = N * int(r['Quantity'])
    buy = max(need + (x['lossNumber'] or 0), x['leastPatchNumber'] or 0)
    def price(tiers, q):
        p = None
        for t in sorted(tiers, key=lambda t: t['startNumber']):
            if q >= t['startNumber']: p = t['productPrice']
        return p
    pn = price(x['componentPrices'], buy)
    s = snap[c]
    po = None
    for a, b in s['tiers']:
        if buy >= a: po = b
    rows.append((c, r['MPN'], r['Assembly'], need, buy, s['stock'], x['stockCount'], x['componentLibraryType'], x['preferredComponentFlag'],
                 po, pn, x.get('componentSpecificationEn'), x.get('isBuyComponent'), x.get('noBuyReason'), x.get('componentProductType'), x.get('allowPostFlag'), x['componentModelEn']))
print(f'{"code":10} {"mpn":22} {"asm":8} need buy  stock10th stock15th  x-need lib     pref  unit10th unit15th  pkg')
for t in sorted(rows, key=lambda t: t[6] / max(t[4], 1)):
    c, mpn, asm, need, buy, so, sn, lib, pref, po, pn, pkg, isbuy, nobuy, ptype, post, model = t
    flag = ''
    if sn < buy: flag += ' SHORT'
    elif sn < 5 * buy: flag += ' TIGHT'
    if lib != snap[c]['library'] or pref != snap[c]['preferred']: flag += ' LIBCHANGE'
    if po and pn and abs(pn - po) / po > 0.1: flag += ' PRICE'
    if model != mpn: flag += f' MODEL={model}'
    if isbuy != '1' or nobuy: flag += f' isBuy={isbuy} noBuy={nobuy}'
    print(f'{c:10} {mpn[:22]:22} {asm:8} {need:4} {buy:4} {so:9} {sn:9} {sn/max(buy,1):7.1f} {lib:7} {str(pref):5} {po or 0:8.4f} {pn or 0:8.4f}  {pkg}{flag}')
smt = [t for t in rows if t[2] == 'SMT']
print('lines', len(rows), 'SMT', len(smt), 'extended (expand, not preferred):', sum(1 for t in smt if t[7] == 'expand' and not t[8]),
      'basic/preferred:', sum(1 for t in smt if not (t[7] == 'expand' and not t[8])))
print('SMT parts cost 10th: %.2f  15th: %.2f' % (sum(t[4] * t[9] for t in smt), sum(t[4] * t[10] for t in smt)))
hf = [t for t in rows if t[2] == 'Hand fit']
print('hand-fit parts cost 10th: %.2f  15th: %.2f' % (sum(t[4] * t[9] for t in hf), sum(t[4] * t[10] for t in hf)))
