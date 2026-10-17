"""Display two recorded boundary captures, without deriving acceptance decisions."""
from __future__ import annotations
import gzip
import os
from pathlib import Path
import runpy
import numpy as np
HERE=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']=str(HERE/'.mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=runpy.run_path(str(HERE.parent/'out-D22/periodic.py'))
fig,axes=plt.subplots(3,2,figsize=(11,8),sharex=True)
for column,phase in enumerate((120,125)):
    label=f'complementary-v170-r2-p{phase}-s0.5' if phase==120 else 'boundary-v170-r2-p125-s0.5'
    w=P['read_binary'](gzip.decompress((HERE/'runs'/label/'waves.raw.gz').read_bytes()))
    for leg,shift,sign,color in (('a',0,-1,'#185fa5'),('b',phase/360/50000,1,'#c45825')):
        t=(w['time']-(2e-6+38/50000+shift))*1e9
        use=(t>=0)&(t<=900)
        q=f'xl{leg}.xqh'
        vds=w[f'v({q}.dd)']-w[f'v({q}.s)']
        q=f'xl{leg}.xql'
        gate=w[f'v({q}.g)']-w[f'v({q}.s)']
        for ax,signal in zip(axes[:,column],(vds,gate,sign*w['i(ltank)'])):
            ax.plot(t[use],signal[use],color=color,label=f'Leg {leg.upper()}',linewidth=1)
    axes[0,column].set_title(f'{phase}° separation',fontsize=13)
    axes[0,column].axhline(8.5,color='#555',linestyle=':',linewidth=.8,label='8.5 V ZVS screen')
    axes[1,column].axhline(1.9,color='#555',linestyle=':',linewidth=.8,label='1.9 V hot screen')
    # Show gate recovery after its commanded turn-off, omitting the initial 15 V edge.
    axes[1,column].set_ylim(-1,3.5)
    for ax in axes[:,column]:
        ax.axvline(443,color='#777',linestyle='--',linewidth=.9)
        ax.grid(alpha=.18)
        ax.spines[['top','right']].set_visible(False)
        ax.legend(fontsize=8,loc='upper right')
    axes[2,column].set_xlabel('Time after outgoing off command (ns)')
axes[0,0].set_ylabel('Incoming die VDS (V)')
axes[1,0].set_ylabel('Outgoing die VGS (V)')
axes[2,0].set_ylabel('Tank current (A)\ninductive polarity')
fig.suptitle('D-28 | Recorded nominal boundary at 170 V, 2 Ω',fontsize=16,x=.08,ha='left')
fig.text(.08,.93,'50 kHz · 0.5 ns maximum step · high-side turn-on · dashed line: incoming command at 443 ns',fontsize=10,color='#555')
fig.text(.08,.015,'PROVISIONAL captures: waveform screens do not establish numerical qualification or an approved phase range.',fontsize=10,color='#555')
fig.tight_layout(rect=(.02,.04,1,.91))
fig.savefig(HERE/'boundary-waveforms.png',dpi=170)
fig.savefig(HERE/'boundary-waveforms.svg')
