#!/usr/bin/env python3
"""Render four illustrative sheet-current maps for BUS_P's mixed A-leg case."""
from __future__ import annotations

import gzip
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import PowerNorm
import numpy as np

from run_board import HERE, load_net


def main():
    data=json.load(gzip.open(HERE/'inputs/power_copper.json.gz','rt'))
    net,_,pads=load_net(data,'bus_p',0.125,18)
    sources=[]
    for ref,amps in (('J8.1',15.0),('C38.1',9.5),('C39.1',9.5)):
        physical=pads[ref]
        sources.extend(('F.Cu',*p['centre'],amps/len(physical)) for p in physical)
    sinks=[('F.Cu',*p['centre']) for p in pads['Q2.2']]
    solved=net.solve(sources,sinks)
    grids,_,_,_=net._build()
    for layer,array in solved['current_per_mm'].items():
        grid=grids[layer]
        finite=array[np.isfinite(array)]
        high=float(finite.max()) if finite.size else 0.0
        fig,ax=plt.subplots(figsize=(7.5,5),layout='constrained')
        image=ax.imshow(np.ma.masked_invalid(array.T),origin='lower',interpolation='nearest',
            extent=(grid['xs'][0]-net.h/2,grid['xs'][-1]+net.h/2,
                    grid['ys'][0]-net.h/2,grid['ys'][-1]+net.h/2),
            aspect='equal',cmap='magma',norm=PowerNorm(gamma=.45,vmin=0,vmax=max(high,1e-9)))
        fig.colorbar(image,ax=ax,label='DC sheet current (A/mm width)')
        ax.set(xlabel='Board x (mm)',ylabel='Board y (mm)',
               title=f'BUS_P J8 15 A + C38/C39 19 A → Q2; {layer}')
        dest=HERE/'outputs'/f'current_density_{layer.replace(".","_")}.png'
        fig.savefig(dest,dpi=150)
        plt.close(fig)
        print(dest.name)


if __name__=='__main__':
    main()
