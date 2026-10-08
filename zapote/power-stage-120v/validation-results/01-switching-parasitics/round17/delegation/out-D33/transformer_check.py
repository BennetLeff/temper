"""Engineering check of the two-transformer SN6507 output stage.

Linear transformer (manufacturer minimum L, maximum DCR increased 40% for hot copper, typical leakage),
Nexperia rectifier model, and datasheet maximum switch RON. This does not model
the SN6507 control IC, core loss/saturation or qualified worst-case leakage.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import urllib.request

import rail_campaign

HERE = Path(__file__).resolve().parent


def main() -> None:
    model = HERE/'.models/PMEG10030ELP.txt'
    model.parent.mkdir(exist_ok=True)
    if not model.exists():
        req = urllib.request.Request('https://assets.nexperia.com/documents/spice-model/PMEG10030ELP.txt',
                                     headers={'User-Agent': 'Mozilla/5.0'})
        model.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    if hashlib.sha256(model.read_bytes()).hexdigest() != 'dada2dcd3a57b45fddfa5e53e482bb4311f0030683c3b72ab23b8ffc9a2008c3':
        raise ValueError('Nexperia rectifier model hash mismatch')
    rows = []
    for vin in (23.3, 24.7):
        for frequency in (500000, 700000):
            period = 1/frequency
            text = f'''* D33 two-core driver stage, bounded RON/L/DCR; estimated leakage
.include {model}
.include ../common/options.inc
.include params.inc
Vraw vp 0 {vin}
Vc1 c1 0 PULSE(0 5 0 5n 5n {period/2-70e-9} {period})
Vc2 c2 0 PULSE(0 5 {period/2} 5n 5n {period/2-70e-9} {period})
.model SW SW(RON=1 ROFF=1e9 VT=2.5 VH=.1)
.model BODY D(IS=1n RS=.1)
Vs1 d1 x1 0
Vs2 d2 x2 0
S1 x1 0 c1 0 SW
S2 x2 0 c2 0 SW
Dbody1 0 x1 BODY
Dbody2 0 x2 BODY
Rsn1 d1 sn1 680
Csn1 sn1 vp 100p
Rsn2 d2 sn2 680
Csn2 sn2 vp 100p
'''
            for tag in ('a', 'b'):
                text += f'''Rp1{tag} d1 pa{tag} .287
Lp1{tag} pa{tag} vp 75u
Lp2{tag} vp pb{tag} 75u
Rp2{tag} pb{tag} d2 .287
Ls1{tag} sa{tag} 0 52.083333u
Ls2{tag} 0 sb{tag} 52.083333u
Rs1{tag} sa{tag} da{tag} .203
Rs2{tag} sb{tag} db{tag} .203
Kp{tag} Lp1{tag} Lp2{tag} .999999
Ks{tag} Ls1{tag} Ls2{tag} .999999
K11{tag} Lp1{tag} Ls1{tag} .984885
K12{tag} Lp1{tag} Ls2{tag} .984885
K21{tag} Lp2{tag} Ls1{tag} .984885
K22{tag} Lp2{tag} Ls2{tag} .984885
Xd1{tag} da{tag} rect{tag} PMEG10030ELP
Xd2{tag} db{tag} rect{tag} PMEG10030ELP
Lfilter{tag} rect{tag} lf{tag} 80u
Rfilter{tag} lf{tag} out{tag} 1
Cout{tag} out{tag} 0 10u
Bload{tag} out{tag} 0 I={{.085*max(0,min(1,v(out{tag})/17))}}
.meas tran out{tag}_min MIN v(out{tag}) from=1m to=2m
.meas tran out{tag}_max MAX v(out{tag}) from=1m to=2m
.meas tran rectifier{tag}_reverse MAX par('v(rect{tag})-v(da{tag})') from=1m to=2m
'''
            text += '''.tran 10n 2m 0 10n
.meas tran switch1_max MAX i(Vs1) from=1m to=2m
.meas tran switch2_max MAX i(Vs2) from=1m to=2m
.meas tran drain1_max MAX v(d1) from=1m to=2m
.meas tran drain2_max MAX v(d2) from=1m to=2m
.meas tran input_w AVG par('-v(vp)*i(Vraw)') from=1m to=2m
.end
'''
            folder = HERE/'transformer-check'
            folder.mkdir(exist_ok=True)
            (folder/'.gitignore').write_text('runs/\n')
            deck = folder/f'{vin}-{frequency}.cir'
            deck.write_text(text)
            result = rail_campaign.f6.run_d2.run(deck, {}, keep=folder/'runs'/deck.stem)
            (folder/'runs'/deck.stem/'IFX_CFD7_650V.lib').unlink(missing_ok=True)
            row = {'vin': vin, 'frequency': frequency, 'complete': not result['aborted'], 'measurements': result['meas']}
            rows.append(row)
            print(row, flush=True)
    (folder/'results.json').write_text(json.dumps(rows, indent=2)+'\n')


if __name__ == '__main__':
    main()
