#!/usr/bin/env python3
"""D6 follow-up combinations motivated by separate-remedy trade-offs."""
import run_study

# Lower Roff fixes gate peaks but leaves S4 VDS high; 1nF reduces that VDS
# while worsening the gate peak. Test their combination before adding bias.
run_study.VARIANTS.update({'roff1_cgs1n': {'roff':1, 'cgs':'1n'},
                          'roff1_cgs2p2n': {'roff':1, 'cgs':'2.2n'}})
VARIANTS=run_study.VARIANTS

if __name__=='__main__':
    run_study.main()
