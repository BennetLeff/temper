#!/bin/bash
# Re-run every number in the 2026-10-15 sourcing study. Offline steps read only the committed caches; ONLINE steps are
# commented out (they re-read the vendors and stop at the first bot check; DigiKey was read by hand in a browser).
set -e; cd "$(dirname "$0")"
VR=../../../..                                      # validation-results
# ONLINE: python3 -I scripts/jlc_snapshot.py snapshot/bom-jlcpcb.s32.csv snapshot/jlc-2026-10-15.json scripts/extra_mpns.txt
# ONLINE: scripts/octopart_fetch.sh scripts/octopart_mpns.txt; scripts/octopart_fetch.sh scripts/octopart_mpns_2.txt
# ONLINE: python3 -I scripts/octopart_parse.py downloads/octopart snapshot/octopart-2026-10-15.json   (downloads/ not committed)
python3 -I scripts/build_snapshot.py snapshot/bom-jlcpcb.s32.csv snapshot/jlc-2026-10-15.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/SNAPSHOT-2026-10-15.csv snapshot/SNAPSHOT-2026-10-15.json
# s35 BOM (J2/J5 7466004R, which the JLC cache holds under "extra"): the committed ../SNAPSHOT-2026-10-15.csv is
# snapshot/s35/SNAPSHOT-s35.csv plus the s32 74650074 row, so the s32 and s35 cards join against one dated snapshot.
python3 -I -c "import json;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m];json.dump(d,open('snapshot/s35/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s35/bom-jlcpcb.s35.csv snapshot/s35/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s35/SNAPSHOT-s35.csv snapshot/s35/SNAPSHOT-s35.json
rm -f snapshot/s35/jlc-bom-plus-extra.json snapshot/s35/SNAPSHOT-s35.json
# s38 BOM (stage 38, candidate 23: PS1 deleted, PS2 MPM-20-24 = JLC C6675337, read 2026-10-15 into scripts/jlc-raw by
# `jlc_fetch.py detail C6675337`; DigiKey's public page gave the price ladder and lead, no stock, so the
# STOCK-2026-10-13-addendum-s38 row carries them). The committed ../SNAPSHOT-2026-10-15.csv is snapshot/s38/SNAPSHOT-s38.csv
# plus every s35 / s32 row whose MPN the s38 BOM no longer has (IRM-20-15, IRM-20-24, 74650074), so the s32, s35 and
# s38 cards join against one dated snapshot.
python3 -I -c "import json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m];r=S.rec_from_detail('C6675337');lad=r['jlc_ladder'];r.update(mpn='MPM-20-24',designators='PS2',qty=1,mount='THT',bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5),jlc_unit_500=S.unit_at(lad,500));d['bom']=[b for b in d['bom'] if b['mpn']!='MPM-20-24']+[r];json.dump(d,open('snapshot/s38/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s38/bom-jlcpcb.s38.csv snapshot/s38/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s38/SNAPSHOT-s38.csv snapshot/s38/SNAPSHOT-s38.json
rm -f snapshot/s38/jlc-bom-plus-extra.json snapshot/s38/SNAPSHOT-s38.json
python3 -I -c "import csv;f='snapshot/s38/SNAPSHOT-s38.csv';a=list(csv.DictReader(open(f)));m={r['mpn'] for r in a};o=list(csv.DictReader(open('snapshot/s35/SNAPSHOT-s35.csv')))+[r for r in csv.DictReader(open('snapshot/SNAPSHOT-2026-10-15.csv')) if r['mpn']=='74650074'];x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
# s42 BOM (stage 42, candidate 39, DECISIONS 54: R10/R12/R18/R20 25121WF680JT4E = JLC C50371, C55/C56/C62/C63
# GRM1885C1H472JA01D = JLC C85980, read 2026-10-15 into scripts/jlc-raw by `jlc_fetch.py detail`; the
# STOCK-2026-10-13-addendum-s42 rows carry them). The committed ../SNAPSHOT-2026-10-15.csv is snapshot/s42/SNAPSHOT-s42.csv
# plus every earlier row whose MPN the s42 BOM no longer has (RS-06L8R20FT and the s38 / s35 / s32 ones), so every card
# joins against one dated snapshot.
python3 -I -c "import json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
json.dump(d,open('snapshot/s42/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s42/bom-jlcpcb.s42.csv snapshot/s42/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s42/SNAPSHOT-s42.csv snapshot/s42/SNAPSHOT-s42.json
rm -f snapshot/s42/jlc-bom-plus-extra.json snapshot/s42/SNAPSHOT-s42.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s42/SNAPSHOT-s42.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
python3 -I scripts/buildability.py --control
python3 -I scripts/buildability.py snapshot/SNAPSHOT-2026-10-15.csv --json results/buildability-s32.json
# needs TDK's B32674-678 PDF (June 2026; tdk-electronics.tdk.com) at downloads/tdk-b3267x/MKP_B32674_678.pdf, not committed:
# python3 -I scripts/digitize_b32676_irms.py downloads/tdk-b3267x/MKP_B32674_678.pdf results/b32676_irms_curves.json
python3 -I scripts/c5c6_ripple.py results/b32676_irms_curves.json results/c5c6_ripple.json
python3 -I scripts/bank_stock.py $VR/11-candidates/c34-bank-margin/results/bank_margin.json snapshot/octopart-2026-10-15.json \
    snapshot/octopart-2026-10-15.json snapshot/jlc-2026-10-15.json results/bank_stock.json
