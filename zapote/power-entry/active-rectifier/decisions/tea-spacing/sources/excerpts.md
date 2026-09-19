# Retained primary-text excerpts

These are short excerpts transcribed in `evidence/vsense-bank-side-01/tea-dossier.md`;
the source identity and limitations are in `README.md`.

## NXP TEA2209T/1

- §7.2 Table 3 (p. 4) identifies pins 3/5, 10/12 and 14/16 and the HVS pins
  4/11/15 as “high-voltage spacer; not to be connected”.
- §9 Tables 6 (pp. 8–9) and §12 (p. 12) specify terminal operating/transient
  limits and the requirement to keep mains transients below 700 V at VR/L/R.
- The retained 19-page datasheet contains no PCB clearance, creepage,
  pollution-degree, CTI or spacer-metal measurement rule.

## IS 302-1:2008 recovery

- Clause 29.1.4: functional insulation uses Table 16 clearances, with the
  clause-19 short-circuit test route as an alternative when its conditions are
  actually met.
- Clause 29.2 delegates creepage measurement to IS 15382 (Part 1).
- Annex L keeps functional clearances and creepage in their respective
  clearance/creepage tables at PD3; it does not supply the missing spacer rule.

## IS 15382-1:2003 recovery

- Clauses 2.2.1.2 and 1.3.5 use the highest RMS working voltage across the
  insulation; transients are treated separately.
- Clause 3.1.4 uses the maximum impulse expected across the gap for functional
  clearance. Clause 3.2.2 uses Table 4 for functional creepage.
- Table 4 values recorded in the dossier are 1.5 mm for PD2/material group III
  and 2.4 mm for PD3/material group III at 125 V. The 500 V rows are much
  larger. These values cannot be applied until the working-voltage band,
  pollution degree and material group are adopted for this assembly.
- The recovered running text does not state how an intervening conductive,
  unconnected spacer pin is counted in the creepage path. That question is
  therefore still open.
