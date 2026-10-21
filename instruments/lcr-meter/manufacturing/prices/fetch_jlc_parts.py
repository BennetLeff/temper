"""Snapshot the JLC assembly-library entry of every LCSC code in bom-complete.csv (read-only search).

python3 manufacturing/prices/fetch_jlc_parts.py   ->  manufacturing/prices/jlc-parts-<today>.json

Uses curl (macOS Python's certificate store fails on this host). One POST per code to the parts
search the JLC BOM tool uses; only an exact componentCode match is kept.  Same schema as
jlc-parts-2026-10-20.json, which order_estimate.py reads.
"""
import csv
import datetime
import json
import subprocess
from pathlib import Path

MFG = Path(__file__).resolve().parents[1]
URL = 'https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList'


def lookup(code):
    body = json.dumps({'keyword': code, 'currentPage': 1, 'pageSize': 25})
    raw = subprocess.run(['curl', '-s', '-X', 'POST', '-H', 'Content-Type: application/json',
                          '-A', 'Mozilla/5.0', '-d', body, URL], check=True, capture_output=True).stdout
    hits = [c for c in json.loads(raw)['data']['componentPageInfo']['list'] if c['componentCode'] == code]
    assert len(hits) == 1, (code, len(hits))
    c = hits[0]
    return {'model': c['componentModelEn'], 'library': c['componentLibraryType'],
            'preferred': bool(c['preferredComponentFlag']), 'stock': c['stockCount'],
            'least': c['leastPatchNumber'], 'loss': c['lossNumber'],
            'tiers': [[p['startNumber'], p['productPrice']] for p in c['componentPrices']]}


codes = sorted({row['LCSC'] for row in csv.DictReader(open(MFG / 'bom-complete.csv'))})
today = datetime.date.today().isoformat()
out = {'source': f'POST {URL} {{"keyword": <LCSC>}}, exact componentCode match', 'fetched': today,
       'parts': {code: lookup(code) for code in codes}}
dest = MFG / f'prices/jlc-parts-{today}.json'
dest.write_text(json.dumps(out, indent=1) + '\n')
print(f'{len(codes)} parts -> {dest}')
