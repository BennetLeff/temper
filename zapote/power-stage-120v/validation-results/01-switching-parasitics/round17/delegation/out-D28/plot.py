"""Plot the Rust ideal-tank output without adding an engineering decision rule."""
from __future__ import annotations
import csv
import os
from pathlib import Path
HERE=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']=str(HERE/'.mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
rows=list(csv.DictReader((HERE/'ideal.csv').open()))
fig,axes=plt.subplots(2,2,figsize=(12,8),sharex=True)
for n,resistance in enumerate((2,100)):
    for bus,style in ((170,'-'),(198,'--')):
        selected=[r for r in rows if r['R_ohm']==str(resistance) and r['bus_V']==str(bus)]
        phase=[float(r['phase_deg']) for r in selected]
        for field,label,color in (('leading_A','A: freewheel to active','#185fa5'),('lagging_A','B: active to freewheel','#c45825')):
            axes[n,0].plot(phase,[float(r[field]) for r in selected],style,color=color,label=f'{label}, {bus} V')
        axes[n,1].plot(phase,[float(r['power_W']) for r in selected],style,label=f'{bus} V',color='#185fa5' if bus==170 else '#c45825')
    axes[n,0].axhline(0,color='#555',linewidth=.8)
    axes[n,0].set_ylabel(f'R = {resistance} Ω\nInductive commutation current (A)')
    axes[n,1].set_ylabel('Ideal load power (W)')
    axes[n,1].axhline(150,color='#777',linewidth=.8,linestyle=':')
    axes[n,1].text(5,155,'150 W low-power reference',color='#555',fontsize=9)
    for ax in axes[n]:
        ax.grid(alpha=.18)
        ax.set_xlim(0,180)
        ax.legend(fontsize=8,loc='upper left')
        ax.spines[['top','right']].set_visible(False)
for ax in axes[1]:ax.set_xlabel('A/B separation (degrees)')
fig.suptitle('D-28 | Ideal tank current and power at 50 kHz',fontsize=17,x=.07,ha='left')
fig.text(.07,.935,'70 µH · 0.54 µF · exact periodic RLC state; semiconductor capacitance and dead time omitted',fontsize=10,color='#555')
fig.text(.07,.02,'Negative commutation current has the wrong sign for ZVS. These curves do not approve an operating range.',fontsize=10,color='#555')
fig.tight_layout(rect=(.02,.045,1,.92))
fig.savefig(HERE/'ideal-phase.png',dpi=170)
fig.savefig(HERE/'ideal-phase.svg')
