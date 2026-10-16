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
# s43 BOM (stage 43: C12/C13/C19/C20 source MPN GRM31A5C3A102JW01D -> CC1206JKNPOCBN102, the YAGEO part JLC C113872 the
# order already placed as the declared substitute). A re-key, not a new part: the s43 JLC record is the cached C113872 record
# of the GRM31A5C3A102JW01D line, renamed, and the STOCK-2026-10-13-addendum-s43 row is the 2026-10-13 row renamed. The
# committed ../SNAPSHOT-2026-10-15.csv is snapshot/s43/SNAPSHOT-s43.csv plus every earlier row whose MPN the s43 BOM no
# longer has (GRM31A5C3A102JW01D and the s42 / s38 / s35 / s32 ones).
python3 -I -c "import json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
r=dict(next(b for b in d['bom'] if b['mpn']=='GRM31A5C3A102JW01D'));r.update(mpn='CC1206JKNPOCBN102',bom_assembly='JLC (Extended)');d['bom']=[b for b in d['bom'] if b['mpn']!='CC1206JKNPOCBN102']+[r]
json.dump(d,open('snapshot/s43/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s43/bom-jlcpcb.s43.csv snapshot/s43/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s43/SNAPSHOT-s43.csv snapshot/s43/SNAPSHOT-s43.json
rm -f snapshot/s43/jlc-bom-plus-extra.json snapshot/s43/SNAPSHOT-s43.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s43/SNAPSHOT-s43.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
# s44 BOM (stage 44, candidate 44: seven more CC0603KRX7R9BB104, C169-C175, on the existing JLC Basic C14663 line; no new
# MPN). Built from the s43 JLC records with the s44 BOM's quantity (51 per board, was 44); the committed
# ../SNAPSHOT-2026-10-15.csv is snapshot/s44/SNAPSHOT-s44.csv plus every earlier row whose MPN the s44 BOM no longer has.
python3 -I -c "import json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
r=dict(next(b for b in d['bom'] if b['mpn']=='GRM31A5C3A102JW01D'));r.update(mpn='CC1206JKNPOCBN102',bom_assembly='JLC (Extended)');d['bom']=[b for b in d['bom'] if b['mpn']!='CC1206JKNPOCBN102']+[r]
json.dump(d,open('snapshot/s44/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s44/bom-jlcpcb.s44.csv snapshot/s44/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s44/SNAPSHOT-s44.csv snapshot/s44/SNAPSHOT-s44.json
rm -f snapshot/s44/jlc-bom-plus-extra.json snapshot/s44/SNAPSHOT-s44.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s44/SNAPSHOT-s44.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
# s45 BOM (stage 45, S16 option 1c-4420, DECISIONS 59: TL431BIDBZR = JLC C41283 and the tap tops RT0603BRD07750RL /
# 072K94L / 0790K9L / 07104KL = C861551 / C705761 / C728600 / C861070, read 2026-10-15 by the S16 study's jlc.py and copied
# into scripts/jlc-raw; the STOCK-2026-10-13-addendum-s45 rows carry them). RT0603BRD0710KL (28 -> 19 per board) and
# RT0603BRD0711KL (2 -> 8) are re-priced on their own ladders at the new quantity. The committed ../SNAPSHOT-2026-10-15.csv is
# snapshot/s45/SNAPSHOT-s45.csv plus every earlier row whose MPN the s45 BOM no longer has (TL431AIDBZR, RT0603BRD077K68L,
# RT0603BRD07120KL, ARG03BTC1333 and the earlier ones).
python3 -I -c "import json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD'),
    ('C41283','TL431BIDBZR','U17,U19,U21',3,'SMD'),('C861551','RT0603BRD07750RL','R81,R99,R114',3,'SMD'),('C705761','RT0603BRD072K94L','R83,R101,R116',3,'SMD'),
    ('C728600','RT0603BRD0790K9L','R85,R103,R118',3,'SMD'),('C861070','RT0603BRD07104KL','R87,R105,R120',3,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
r=dict(next(b for b in d['bom'] if b['mpn']=='GRM31A5C3A102JW01D'));r.update(mpn='CC1206JKNPOCBN102',bom_assembly='JLC (Extended)');d['bom']=[b for b in d['bom'] if b['mpn']!='CC1206JKNPOCBN102']+[r]
for b in d['bom']:
    if b['mpn'] in ('RT0603BRD0710KL','RT0603BRD0711KL') and b.get('jlc_ladder'):
        q={'RT0603BRD0710KL':19,'RT0603BRD0711KL':8}[b['mpn']];b.update(qty=q,jlc_unit_5=S.unit_at(b['jlc_ladder'],5*q),jlc_unit_500=S.unit_at(b['jlc_ladder'],500*q))
json.dump(d,open('snapshot/s45/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s45/bom-jlcpcb.s45.csv snapshot/s45/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s45/SNAPSHOT-s45.csv snapshot/s45/SNAPSHOT-s45.json
rm -f snapshot/s45/jlc-bom-plus-extra.json snapshot/s45/SNAPSHOT-s45.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s45/SNAPSHOT-s45.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
# s46 BOM (stage 46, S17 hot copper, c46-monitor-grades: the 125 C monitor grades TL431BQDBZR = JLC C190245 and
# LM2901BIDR = C22427890, read 2026-10-15 by the c46 jlc.py copy (runs-native21/s46/dl/jlc-raw) and copied into
# scripts/jlc-raw; the STOCK-2026-10-13-addendum-s46 rows carry them). Same s45 records otherwise; the committed
# ../SNAPSHOT-2026-10-15.csv is snapshot/s46/SNAPSHOT-s46.csv plus every earlier row whose MPN the s46 BOM no longer has
# (TL431BIDBZR, LM339BIDR and the earlier ones).
python3 -I -c "import json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD'),
    ('C861551','RT0603BRD07750RL','R81,R99,R114',3,'SMD'),('C705761','RT0603BRD072K94L','R83,R101,R116',3,'SMD'),
    ('C728600','RT0603BRD0790K9L','R85,R103,R118',3,'SMD'),('C861070','RT0603BRD07104KL','R87,R105,R120',3,'SMD'),
    ('C190245','TL431BQDBZR','U17,U19,U21',3,'SMD'),('C22427890','LM2901BIDR','U29,U30,U31',3,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
r=dict(next(b for b in d['bom'] if b['mpn']=='GRM31A5C3A102JW01D'));r.update(mpn='CC1206JKNPOCBN102',bom_assembly='JLC (Extended)');d['bom']=[b for b in d['bom'] if b['mpn']!='CC1206JKNPOCBN102']+[r]
for b in d['bom']:
    if b['mpn'] in ('RT0603BRD0710KL','RT0603BRD0711KL') and b.get('jlc_ladder'):
        q={'RT0603BRD0710KL':19,'RT0603BRD0711KL':8}[b['mpn']];b.update(qty=q,jlc_unit_5=S.unit_at(b['jlc_ladder'],5*q),jlc_unit_500=S.unit_at(b['jlc_ladder'],500*q))
json.dump(d,open('snapshot/s46/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s46/bom-jlcpcb.s46.csv snapshot/s46/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s46/SNAPSHOT-s46.csv snapshot/s46/SNAPSHOT-s46.json
rm -f snapshot/s46/jlc-bom-plus-extra.json snapshot/s46/SNAPSHOT-s46.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s46/SNAPSHOT-s46.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
# s47 BOM (stage 47, S17 hot copper, c47-ref25-grade: U5 REF25 LM4050AEM3-2.5/NOPB = JLC C2156518, read 2026-10-15 by
# the c47 jlc.py copy and copied into scripts/jlc-raw; 50 in stock against 500, so the STOCK-2026-10-13-addendum-s47 row
# flags it LOW_JLC_STOCK / OWNER_PREORDER_CONSIGN). Same s46 records otherwise; the committed ../SNAPSHOT-2026-10-15.csv is
# snapshot/s47/SNAPSHOT-s47.csv plus every earlier row whose MPN the s47 BOM no longer has (LM4040A25IDBZR and earlier).
python3 -I -c "import json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD'),
    ('C861551','RT0603BRD07750RL','R81,R99,R114',3,'SMD'),('C705761','RT0603BRD072K94L','R83,R101,R116',3,'SMD'),
    ('C728600','RT0603BRD0790K9L','R85,R103,R118',3,'SMD'),('C861070','RT0603BRD07104KL','R87,R105,R120',3,'SMD'),
    ('C190245','TL431BQDBZR','U17,U19,U21',3,'SMD'),('C22427890','LM2901BIDR','U29,U30,U31',3,'SMD'),
    ('C2156518','LM4050AEM3-2.5/NOPB','U5',1,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
r=dict(next(b for b in d['bom'] if b['mpn']=='GRM31A5C3A102JW01D'));r.update(mpn='CC1206JKNPOCBN102',bom_assembly='JLC (Extended)');d['bom']=[b for b in d['bom'] if b['mpn']!='CC1206JKNPOCBN102']+[r]
for b in d['bom']:
    if b['mpn'] in ('RT0603BRD0710KL','RT0603BRD0711KL') and b.get('jlc_ladder'):
        q={'RT0603BRD0710KL':19,'RT0603BRD0711KL':8}[b['mpn']];b.update(qty=q,jlc_unit_5=S.unit_at(b['jlc_ladder'],5*q),jlc_unit_500=S.unit_at(b['jlc_ladder'],500*q))
json.dump(d,open('snapshot/s47/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s47/bom-jlcpcb.s47.csv snapshot/s47/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s47/SNAPSHOT-s47.csv snapshot/s47/SNAPSHOT-s47.json
rm -f snapshot/s47/jlc-bom-plus-extra.json snapshot/s47/SNAPSHOT-s47.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s47/SNAPSHOT-s47.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
# s48 BOM (stage 48, S19 / B13 H1-H2, c48-ldo-en-ref-watch: U3 / U37-U39 on TPS70950QDBVRQ1 = JLC C485909, read
# 2026-10-16 by the u3-286 analysis lane and copied into scripts/jlc-raw; the STOCK-2026-10-13-addendum-s48 row carries it).
# New designators on existing lines change their quantities: 0603WAF1003T5E 4 -> 8, 0603WAF2702T5E 2 -> 6,
# RT0603BRD0763K4L 2 -> 3, TNPW060311K7BEEA 1 -> 2, RC1206FR-07220KL 2 -> 3, CC0603KRX7R9BB104 +3 (C176-C178). Same s47
# records otherwise; the committed ../SNAPSHOT-2026-10-15.csv is snapshot/s48/SNAPSHOT-s48.csv plus every earlier row whose
# MPN the s48 BOM no longer has (TPS70950DBVR and earlier).
python3 -I -c "import csv,json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD'),
    ('C861551','RT0603BRD07750RL','R81,R99,R114',3,'SMD'),('C705761','RT0603BRD072K94L','R83,R101,R116',3,'SMD'),
    ('C728600','RT0603BRD0790K9L','R85,R103,R118',3,'SMD'),('C861070','RT0603BRD07104KL','R87,R105,R120',3,'SMD'),
    ('C190245','TL431BQDBZR','U17,U19,U21',3,'SMD'),('C22427890','LM2901BIDR','U29,U30,U31',3,'SMD'),
    ('C2156518','LM4050AEM3-2.5/NOPB','U5',1,'SMD'),('C485909','TPS70950QDBVRQ1','U3,U37,U38,U39',4,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
r=dict(next(b for b in d['bom'] if b['mpn']=='GRM31A5C3A102JW01D'));r.update(mpn='CC1206JKNPOCBN102',bom_assembly='JLC (Extended)');d['bom']=[b for b in d['bom'] if b['mpn']!='CC1206JKNPOCBN102']+[r]
qty={r['Manufacturer Part Number']:len([x for x in r['Designator'].split(',') if x.strip()]) for r in csv.DictReader(open('snapshot/s48/bom-jlcpcb.s48.csv'))}
for b in d['bom']:
    if b['mpn'] in ('RT0603BRD0710KL','RT0603BRD0711KL','0603WAF1003T5E','0603WAF2702T5E','RT0603BRD0763K4L','TNPW060311K7BEEA','RC1206FR-07220KL','CC0603KRX7R9BB104') and b.get('jlc_ladder'):
        q=qty[b['mpn']];b.update(qty=q,jlc_unit_5=S.unit_at(b['jlc_ladder'],5*q),jlc_unit_500=S.unit_at(b['jlc_ladder'],500*q))
json.dump(d,open('snapshot/s48/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s48/bom-jlcpcb.s48.csv snapshot/s48/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s48/SNAPSHOT-s48.csv snapshot/s48/SNAPSHOT-s48.json
rm -f snapshot/s48/jlc-bom-plus-extra.json snapshot/s48/SNAPSHOT-s48.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s48/SNAPSHOT-s48.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
# s49 BOM (stage 49, c49-c34-bank: bank C21-C23 / C151 / C152 on B32643B8104J000 = JLC C3781430, listed with 0 stock, an
# owner pre-order consigned to JLC (untaped MOQ 2080, 28 weeks; STOCK-2026-10-13-addendum-s49 row); S23 B'-1.02 V: R33
# RT0603BRD077K5L = C728597, R34 RT0603BRD0716KL = C326732, R35 onto RT0603BRD0711KL (C728581). JLC reads 2026-10-16 in
# scripts/jlc-raw (C105188 TLV3201AIDBVR re-read the same day: 3,221 in stock against 2,500 for U6 / U7 / U10 / U11 / U12
# at 500 boards). Quantity moves: RT0603BRD0710KL 19 -> 18, RT0603BRD0711KL 8 -> 9, TNPW060311K7BEEA 2 -> 1; the
# B32654A1104J000 and RT0603BRD0712K6L lines leave. The committed ../SNAPSHOT-2026-10-15.csv is snapshot/s49/SNAPSHOT-s49.csv
# plus every earlier row whose MPN the s49 BOM no longer has.
python3 -I -c "import csv,json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD'),
    ('C861551','RT0603BRD07750RL','R81,R99,R114',3,'SMD'),('C705761','RT0603BRD072K94L','R83,R101,R116',3,'SMD'),
    ('C728600','RT0603BRD0790K9L','R85,R103,R118',3,'SMD'),('C861070','RT0603BRD07104KL','R87,R105,R120',3,'SMD'),
    ('C190245','TL431BQDBZR','U17,U19,U21',3,'SMD'),('C22427890','LM2901BIDR','U29,U30,U31',3,'SMD'),
    ('C2156518','LM4050AEM3-2.5/NOPB','U5',1,'SMD'),('C485909','TPS70950QDBVRQ1','U3,U37,U38,U39',4,'SMD'),
    ('C3781430','B32643B8104J000','C21,C22,C23,C151,C152',5,'THT'),('C728597','RT0603BRD077K5L','R33',1,'SMD'),
    ('C326732','RT0603BRD0716KL','R34',1,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
r=dict(next(b for b in d['bom'] if b['mpn']=='GRM31A5C3A102JW01D'));r.update(mpn='CC1206JKNPOCBN102',bom_assembly='JLC (Extended)');d['bom']=[b for b in d['bom'] if b['mpn']!='CC1206JKNPOCBN102']+[r]
qty={r['Manufacturer Part Number']:len([x for x in r['Designator'].split(',') if x.strip()]) for r in csv.DictReader(open('snapshot/s49/bom-jlcpcb.s49.csv'))}
for b in d['bom']:
    if b['mpn'] in ('RT0603BRD0710KL','RT0603BRD0711KL','0603WAF1003T5E','0603WAF2702T5E','RT0603BRD0763K4L','TNPW060311K7BEEA','RC1206FR-07220KL','CC0603KRX7R9BB104') and b.get('jlc_ladder'):
        q=qty[b['mpn']];b.update(qty=q,jlc_unit_5=S.unit_at(b['jlc_ladder'],5*q),jlc_unit_500=S.unit_at(b['jlc_ladder'],500*q))
json.dump(d,open('snapshot/s49/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s49/bom-jlcpcb.s49.csv snapshot/s49/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s49/SNAPSHOT-s49.csv snapshot/s49/SNAPSHOT-s49.json
rm -f snapshot/s49/jlc-bom-plus-extra.json snapshot/s49/SNAPSHOT-s49.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s49/SNAPSHOT-s49.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
# s50 BOM (stage 50, c50-permit-gate: R135 moves from 0603WAF1002T5E (10 k) to 0603WAF1003T5E (100 k), both JLC Basic
# lines already on the BOM; no line added or removed). Quantity moves: 0603WAF1003T5E 8 -> 9, 0603WAF1002T5E 10 -> 9. Same
# method as s49 (the extra rows and ladder re-reads carried); no new vendor read. The committed ../SNAPSHOT-2026-10-15.csv is
# snapshot/s50/SNAPSHOT-s50.csv plus every earlier row whose MPN the s50 BOM no longer has.
python3 -I -c "import csv,json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD'),
    ('C861551','RT0603BRD07750RL','R81,R99,R114',3,'SMD'),('C705761','RT0603BRD072K94L','R83,R101,R116',3,'SMD'),
    ('C728600','RT0603BRD0790K9L','R85,R103,R118',3,'SMD'),('C861070','RT0603BRD07104KL','R87,R105,R120',3,'SMD'),
    ('C190245','TL431BQDBZR','U17,U19,U21',3,'SMD'),('C22427890','LM2901BIDR','U29,U30,U31',3,'SMD'),
    ('C2156518','LM4050AEM3-2.5/NOPB','U5',1,'SMD'),('C485909','TPS70950QDBVRQ1','U3,U37,U38,U39',4,'SMD'),
    ('C3781430','B32643B8104J000','C21,C22,C23,C151,C152',5,'THT'),('C728597','RT0603BRD077K5L','R33',1,'SMD'),
    ('C326732','RT0603BRD0716KL','R34',1,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
r=dict(next(b for b in d['bom'] if b['mpn']=='GRM31A5C3A102JW01D'));r.update(mpn='CC1206JKNPOCBN102',bom_assembly='JLC (Extended)');d['bom']=[b for b in d['bom'] if b['mpn']!='CC1206JKNPOCBN102']+[r]
qty={r['Manufacturer Part Number']:len([x for x in r['Designator'].split(',') if x.strip()]) for r in csv.DictReader(open('snapshot/s50/bom-jlcpcb.s50.csv'))}
for b in d['bom']:
    if b['mpn'] in ('RT0603BRD0710KL','RT0603BRD0711KL','0603WAF1003T5E','0603WAF1002T5E','0603WAF2702T5E','RT0603BRD0763K4L','TNPW060311K7BEEA','RC1206FR-07220KL','CC0603KRX7R9BB104') and b.get('jlc_ladder'):
        q=qty[b['mpn']];b.update(qty=q,jlc_unit_5=S.unit_at(b['jlc_ladder'],5*q),jlc_unit_500=S.unit_at(b['jlc_ladder'],500*q))
json.dump(d,open('snapshot/s50/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s50/bom-jlcpcb.s50.csv snapshot/s50/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s50/SNAPSHOT-s50.csv snapshot/s50/SNAPSHOT-s50.json
rm -f snapshot/s50/jlc-bom-plus-extra.json snapshot/s50/SNAPSHOT-s50.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s50/SNAPSHOT-s50.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
# s51 BOM (stage 51, DECISIONS 73, c51-bank-source: bank C21-C23 / C151 / C152 on KNSCHA MMK104J3DF1KN208G2 = JLC C528962,
# Extended THT, 4,952 in stock at the 2026-10-16T17:48Z read against 2,500 for 500 boards; the B32643B8104J000 line
# (C3781430) leaves the BOM and stays the not-fitted 28 A alternate). Same method as s50; the C528962 detail record is the
# c51-bank-source lane's read (scripts/jlc-raw/detail_C528962.json), no new vendor read. The committed
# ../SNAPSHOT-2026-10-15.csv is snapshot/s51/SNAPSHOT-s51.csv plus every earlier row whose MPN the s51 BOM no longer has.
python3 -I -c "import csv,json,sys;sys.path.insert(0,'scripts');import jlc_snapshot as S;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m]
for code,mpn,des,q,ma in (('C6675337','MPM-20-24','PS2',1,'THT'),('C50371','25121WF680JT4E','R10,R12,R18,R20',4,'SMD'),('C85980','GRM1885C1H472JA01D','C55,C56,C62,C63',4,'SMD'),
    ('C861551','RT0603BRD07750RL','R81,R99,R114',3,'SMD'),('C705761','RT0603BRD072K94L','R83,R101,R116',3,'SMD'),
    ('C728600','RT0603BRD0790K9L','R85,R103,R118',3,'SMD'),('C861070','RT0603BRD07104KL','R87,R105,R120',3,'SMD'),
    ('C190245','TL431BQDBZR','U17,U19,U21',3,'SMD'),('C22427890','LM2901BIDR','U29,U30,U31',3,'SMD'),
    ('C2156518','LM4050AEM3-2.5/NOPB','U5',1,'SMD'),('C485909','TPS70950QDBVRQ1','U3,U37,U38,U39',4,'SMD'),
    ('C528962','MMK104J3DF1KN208G2','C21,C22,C23,C151,C152',5,'THT'),('C728597','RT0603BRD077K5L','R33',1,'SMD'),
    ('C326732','RT0603BRD0716KL','R34',1,'SMD')):
    r=S.rec_from_detail(code);lad=r['jlc_ladder'];r.update(mpn=mpn,designators=des,qty=q,mount=ma,bom_assembly='JLC (Extended)',jlc_unit_5=S.unit_at(lad,5*q),jlc_unit_500=S.unit_at(lad,500*q));d['bom']=[b for b in d['bom'] if b['mpn']!=mpn]+[r]
r=dict(next(b for b in d['bom'] if b['mpn']=='GRM31A5C3A102JW01D'));r.update(mpn='CC1206JKNPOCBN102',bom_assembly='JLC (Extended)');d['bom']=[b for b in d['bom'] if b['mpn']!='CC1206JKNPOCBN102']+[r]
qty={r['Manufacturer Part Number']:len([x for x in r['Designator'].split(',') if x.strip()]) for r in csv.DictReader(open('snapshot/s51/bom-jlcpcb.s51.csv'))}
for b in d['bom']:
    if b['mpn'] in ('RT0603BRD0710KL','RT0603BRD0711KL','0603WAF1003T5E','0603WAF1002T5E','0603WAF2702T5E','RT0603BRD0763K4L','TNPW060311K7BEEA','RC1206FR-07220KL','CC0603KRX7R9BB104') and b.get('jlc_ladder'):
        q=qty[b['mpn']];b.update(qty=q,jlc_unit_5=S.unit_at(b['jlc_ladder'],5*q),jlc_unit_500=S.unit_at(b['jlc_ladder'],500*q))
json.dump(d,open('snapshot/s51/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s51/bom-jlcpcb.s51.csv snapshot/s51/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s51/SNAPSHOT-s51.csv snapshot/s51/SNAPSHOT-s51.json
rm -f snapshot/s51/jlc-bom-plus-extra.json snapshot/s51/SNAPSHOT-s51.json
python3 -I -c "import csv;a=list(csv.DictReader(open('snapshot/s51/SNAPSHOT-s51.csv')));m={r['mpn'] for r in a};o=list(csv.DictReader(open('../SNAPSHOT-2026-10-15.csv')));x=[r for r in o if r['mpn'] not in m];w=csv.DictWriter(open('../SNAPSHOT-2026-10-15.csv','w',newline=''),fieldnames=list(a[0]));w.writeheader();w.writerows(a+x)"
python3 -I scripts/buildability.py --control
python3 -I scripts/buildability.py snapshot/SNAPSHOT-2026-10-15.csv --json results/buildability-s32.json
# needs TDK's B32674-678 PDF (June 2026; tdk-electronics.tdk.com) at downloads/tdk-b3267x/MKP_B32674_678.pdf, not committed:
# python3 -I scripts/digitize_b32676_irms.py downloads/tdk-b3267x/MKP_B32674_678.pdf results/b32676_irms_curves.json
python3 -I scripts/c5c6_ripple.py results/b32676_irms_curves.json results/c5c6_ripple.json
python3 -I scripts/bank_stock.py $VR/11-candidates/c34-bank-margin/results/bank_margin.json snapshot/octopart-2026-10-15.json \
    snapshot/octopart-2026-10-15.json snapshot/jlc-2026-10-15.json results/bank_stock.json
