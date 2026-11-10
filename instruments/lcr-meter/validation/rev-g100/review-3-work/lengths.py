"""Routed length, via count and layer use per net for USB, QSPI, I2S, I2C, crystal and the switcher nodes. Output work/lengths.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
from collections import defaultdict
b=load(); T=tracks(b)
nets=['USB_DP','USB_DM','USB_DP_MCU','USB_DM_MCU','QSPI_CLK','QSPI_CS','QSPI0','QSPI1','QSPI2','QSPI3','QSPI_SCK','QSPI_D0','QSPI_D1','QSPI_D2','QSPI_D3','I2S_BCLK','I2S_FSYNC','I2S_DIN','I2S_DOUT','I2C_SDA','I2C_SCL','XIN','XOUT','SW_P','SW_N','RUN','BOOTSEL','CONV_FBP','CONV_FBN','CONV_CP','CONV_CN','CONV_REF','TIA_SUM','TIA_OUT','SRC_DRV','RLY_RST','RLY_SET_LO','RLY_SET_MED','RLY_SET_HI','RLY_SET_REF','JACK_HC','JACK_LC','STATUS','MON12','MON_N12','USB_SENSE']
all_nets=set(t['net'] for t in T)
out=[]
for n in nets:
    if n not in all_nets:
        cand=[m for m in all_nets if n.split('_')[0] in m]
        continue
    L=defaultdict(float); vias=0; wmin=9
    for t in T:
        if t['net']!=n: continue
        if t['kind']=='via': vias+=1
        else: L[t['layer']]+=dist(t['a'],t['b']); wmin=min(wmin,t['w'])
    out.append(f"{n:12s} total {sum(L.values()):6.1f} mm  {dict((k,round(v,1)) for k,v in L.items())}  vias {vias}  min w {wmin}")
print('nets present with QSPI/USB/I2S:', sorted(m for m in all_nets if any(k in m for k in ('QSPI','USB','I2S','SW_'))))
open('work/lengths.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
