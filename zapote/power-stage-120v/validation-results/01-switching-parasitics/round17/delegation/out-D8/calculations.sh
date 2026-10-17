#!/bin/sh
# Planning arithmetic only, no instrument control or simulation.
set -eu
awk 'BEGIN {
  L=100e-6; Cboard=5.8e-6; Cext=100e-6; R=10000;
  print "Proposed L=100uH; native bus=5.8uF nominal; external reservoir=100uF; dump=10kohm";
  print "Vbus I_target ideal_t1_us L_energy_J board_bus_J total_bus_J ideal_droop_V dump_initial_W ideal_dump_to_1V_s";
  for (j=1;j<=4;j++) {
    V=(j==1?50:(j==2?100:(j==3?170:198))); I=20; C=Cboard+Cext;
    printf "%.0f %.1f %.6f %.6f %.6f %.6f %.6f %.6f %.6f\n",V,I,1e6*L*I/V,L*I*I/2,Cboard*V*V/2,C*V*V/2,V-sqrt(V*V-L*I*I/C),V*V/R,R*C*log(V);
  }
  V=400; I=58.2; C=Cext;
  print "Separate coupon only (no native board or T1), same proposed L and external C:";
  printf "%.0f %.1f %.6f %.6f n/a %.6f %.6f %.6f %.6f\n",V,I,1e6*L*I/V,L*I*I/2,C*V*V/2,V-sqrt(V*V-L*I*I/C),V*V/R,R*C*log(V);
  print "Native T1 planning proxy uses N=100,R_secondary_total=3ohm, I=20A.";
  for(j=1;j<=4;j++) {
    V=(j==1?50:(j==2?100:(j==3?170:198))); I=20; t1=1e6*L*I/V;
    # conservative nominal-current tail allowance 10us; actual integral still required
    printf "V=%.0f ramp_plus_10us_nominal_tail_Vus=%.6f\n",V,3*I/100*(t1/2+10);
  }
  printf "Native final decay integral bound conditional L110uH I22A R0.3135ohm: %.9f A.s; nominal CT %.6f Vus\n",110e-6*22/.3135,110e-6*22/.3135*.03*1e6;
  print "At 198V, 1us second pulse adds ideal 1.98A; at 400V, 6us adds ideal 24A.";
  print "All outputs ideal planning estimates; use measured C,L,V,I and losses for an actual shot.";
}'
