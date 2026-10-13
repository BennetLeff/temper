"""OTT-EMC review: arithmetic and results.json queries. Usage: python3 -I ott_arith.py results.json"""
import sys,json,math
print('OTT-19 Y 9.1 nF/line at 140 V 60 Hz: %.3f mA'%(9.1e-9*2*math.pi*60*140*1e3))
print('OTT-21 tab 7.0 pF x 170 V/26.8 ns: %.1f mA per tab'%(7e-12*170/26.8e-9*1e3))
r=json.load(open(sys.argv[1]))
def mm(v):
    m=[]
    def w(x):
        if isinstance(x,dict):
            if x.get('margin_dB') is not None: m.append(x['margin_dB'])
            for y in x.values(): w(y)
    w(v); return min(m)
for k in['nominal','module_DM_80uH','module_DM_18uH_only (D-22 as specified)','board_only_no_module','L1_winding_C_x2','X_caps_minus20pct','Y_caps_ESL_x3','PE_bond_200nH','INFO_pan_earthed_91pF','INFO_pan_earthed_102pF','coil_PE_100pF_one_sided_100_0']:
    print('OTT-18/21 scenario %-45s min margin %.1f dB'%(k,mm(r['scenarios'][k])))
