#!/usr/bin/env python3
"""Plot the nominal-threshold reference crossing on a different lobe."""
from __future__ import annotations
import gzip
import json
import tempfile
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from run_ct import HERE,read_raw


def main()->None:
    rows=json.loads((HERE/'outputs/ct_sweep.json').read_text())['rows']
    row=min(rows,key=lambda r:r['detection_delay_ns'])
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'wave.raw'
        path.write_bytes(gzip.decompress((HERE/'outputs'/f"{row['analog_run']}.raw.gz").read_bytes()))
        w=read_raw(path)
    t=np.array(w['time'])*1e6
    mask=(t>=40)&(t<=58)
    fig,axs=plt.subplots(2,1,figsize=(10,6),sharex=True)
    axs[0].plot(t[mask],np.array(w['v(ipri)'])[mask],label='Primary current (model)')
    for i in (-55.17,55.17):axs[0].axhline(i,color='grey',linestyle=':')
    axs[0].set_ylabel('Primary current / A')
    decision=(np.array(w['v(ref_lo)'])-np.array(w['v(sense)'])+.004)*1e3
    axs[1].plot(t[mask],decision[mask],label='Negative comparator input minus offset')
    axs[1].axhline(0,color='grey',linestyle=':')
    axs[1].set_ylabel('Decision overdrive / mV')
    axs[1].set_xlabel('Time / microseconds')
    for ax in axs:
        ax.axvline(row['t_or']*1e6,color='tab:red',label='First modeled OR trip')
        ax.axvline(min(row['t_ip_trip'],row['t_in_trip'])*1e6,color='tab:green',linestyle='--',label='First nominal 55.17 A crossing')
        ax.grid(alpha=.2)
        ax.legend(fontsize=8,loc='upper left')
    fig.suptitle('CT model: offset changes the first trip lobe\n39 kHz, 10 A initial amplitude, 1 MA/s, -4 mV offset, 45 ns fixed delay')
    fig.tight_layout()
    fig.savefig(HERE/'outputs/reference-lobe.png',dpi=150)

if __name__=='__main__':main()
