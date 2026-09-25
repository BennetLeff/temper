* RevB source-07 node-mapped controller. Authored nominal behavior; no vendor maximum.
* Every supply and detector timing state resets on loss of its qualification.
.param VABS=426.469072165 MISMATCH=1.0355871886
.param FAULT_TAU=79.3n EN_TAU=18.75n GATE_C=12n BYPASS=0
.param CT_HOLD=132u
* Actual tapped dividers; nominal comparator input capacitance2pF is an assumption.
Rdt vd dh 987k
Rds dh dl 200
Rdb dl 0 5620
Cdf dh 0 47p
Rbt vb bh 987k
Rbs bh bl 200
Rbb bl 0 5620
Cbf bh 0 47p
Rivdo dh ivdo 22k
Rivbo bh ivbo 22k
Rivdh dh ivdh 22k
Rivbl bl ivbl 22k
Rivbh bh ivbh 22k
Rivdl dl ivdl 22k
Rirefd ref25 irefd 22k
Rirefb ref25 irefb 22k
Civdo ivdo 0 2p
Civbo ivbo 0 2p
Civdh ivdh 0 2p
Civbl ivbl 0 2p
Civbh ivbh 0 2p
Civdl ivdl 0 2p
Cirefd irefd 0 2p
Cirefb irefb 0 2p
* LM4040 powered by logic5. Reference model assumes regulation above2.8V.
Breference ref25 0 V=(V(logic5)>2.8) ? 2.5 : 0
Rbleed logic5 0 220
* Fault indicators have the same polarity as comparisons, inverted for trace clarity.
Bch_vd_raw ch_vd_raw 0 V=(V(ivdo)>V(irefd)) ? 5 : 0
Bch_vb_raw ch_vb_raw 0 V=(V(ivbo)>V(irefb)) ? 5 : 0
Bch_fwd_raw ch_fwd_raw 0 V=(V(ivdl)>V(ivbh)) ? 5 : 0
Bch_rev_raw ch_rev_raw 0 V=(V(ivbl)>V(ivdh)) ? 5 : 0
Rch_vd ch_vd_raw ch_vd 1
Cch_vd ch_vd 0 {FAULT_TAU}
Rch_vb ch_vb_raw ch_vb 1
Cch_vb ch_vb 0 {FAULT_TAU}
Rch_fwd ch_fwd_raw ch_fwd 1
Cch_fwd ch_fwd 0 {FAULT_TAU}
Rch_rev ch_rev_raw ch_rev 1
Cch_rev ch_rev 0 {FAULT_TAU}
* Actual supervisor divider values and series SENSE isolation. No invented feedback R.
Rlogic_top logic5 lsense_pre 294k
Rlogic_bot lsense_pre 0 100k
Rlogic_iso lsense_pre lsense 47k
Clsense lsense 0 1p
Raux_top aux15 asense_pre 1.03Meg
Raux_bot asense_pre 0 100k
Raux_iso asense_pre asense 47k
Casense asense 0 1p
* Nominal TPS389001 thresholds. Hysteresis is omitted, explicitly, in this fixture.
Blogic_good logic_good 0 V=(V(logic5)>1.5 && V(lsense)>1.157) ? 5 : 0
Baux_good aux_good 0 V=(V(logic5)>1.5 && V(asense)>1.157) ? 5 : 0
* Authored8us low-going qualification delay (typical datasheet condition),
* plus a132us retriggerable release timer representing100pF CT + internal delay.
Aqual [logic_good aux_good] [lg_d ag_d] adc
Alg lg_d lg_delayed_d sup_delay
Aag ag_d ag_delayed_d sup_delay
.model sup_delay d_buffer(rise_delay=1n fall_delay=8u)
Asup [lg_delayed_d ag_delayed_d] [lg_delayed ag_delayed] dac
Blt 0 ltimer I=(V(lg_delayed)>2.5 && V(logic5)>1.5 && V(ltimer)<2) ? 1u : ((V(lg_delayed)<2.5 || V(logic5)<1.5) ? -V(ltimer)/200 : 0)
Bat 0 atimer I=(V(ag_delayed)>2.5 && V(logic5)>1.5 && V(atimer)<2) ? 1u : ((V(ag_delayed)<2.5 || V(logic5)<1.5) ? -V(atimer)/200 : 0)
Cltimer ltimer 0 100p
Catimer atimer 0 100p
Blogic_reset logic_reset 0 V=(V(ltimer)>{CT_HOLD*1u/100p} && V(logic5)>1.5) ? 5 : 0
Baux_reset aux_reset 0 V=(V(atimer)>{CT_HOLD*1u/100p} && V(logic5)>1.5) ? 5 : 0
Brails rails_ok 0 V=(V(logic_reset)>2.5 && V(aux_reset)>2.5) ? 5 : 0
* Fast aux comparator uses the existing health AND's fourth input.
Rfasttop aux15 fast_pre 430k
Rfastbot fast_pre 0 100k
Rfastiso fast_pre fast_input 22k
Cfast fast_input 0 2p
Bfast_raw fast_raw 0 V=(V(fast_input)>V(ref25) && V(logic5)>2.8) ? 5 : 0
Rfast fast_raw fast_good 1
Cfastout fast_good 0 79.3n
* Input buffers: Ioff at VCC0; behavior below1.65V is explicitly modeled off,
* not claimed as a guaranteed hardware transfer function through brownout.
Barmbuf arm_safe 0 V=(V(logic5)>=1.65 && V(arm)>2.74) ? V(logic5) : 0
Bpermitbuf permit_safe 0 V=(V(logic5)>=1.65 && V(permit)>2.74) ? V(logic5) : 0
Bfault fault_raw 0 V=({BYPASS}>0.5) ? 0 : ((V(ch_vd)>2.5 || V(ch_vb)>2.5 || V(ch_fwd)>2.5 || V(ch_rev)>2.5) ? 5 : 0)
Rfault fault_raw fault 1
Cfault fault 0 1p
Bhealth_raw health_raw 0 V=(V(fault)<2.5 && V(rails_ok)>2.5 && V(permit_safe)>2.5 && V(fast_good)>2.5 && V(logic5)>4.4) ? 5 : 0
Rhealth health_raw health 1
Chealth health 0 40n
Bready ready 0 V=V(health)
* Invert active-low hardware CLR to XSPICE's ACTIVE-HIGH reset.
Bclear clear 0 V=(V(health)<2.5 || V(logic5)<2) ? 5 : 0
Ainput [logic_good arm_safe clear] [data_d clk_d reset_d] adc
.model adc adc_bridge(in_low=2.5 in_high=2.5)
Alatch data_d clk_d NULL reset_d q_d qn_d latch
.model latch d_dff(clk_delay=19n reset_delay=19n set_delay=19n rise_delay=1p fall_delay=1p ic=0)
Aoutput [q_d qn_d] [q_logic qn_logic] dac
.model dac dac_bridge(out_low=0 out_high=5 out_undef=2.5)
Bq q 0 V=V(q_logic)*min(V(logic5)/5,1)
Bqn qn 0 V=V(qn_logic)*min(V(logic5)/5,1)
* Final enable AND +10k PD, BSS138 interface with explicit parasitic assumptions.
Benable enable_src 0 V=(V(q)>2.5 && V(health)>2.5 && V(logic5)>=1.65) ? V(logic5) : 0
Renable enable_src enable_good 20
Renablepd enable_good 0 10k
Rsmallgate enable_good smallgate 1k
Rsmallpd smallgate 0 100k
Rdisable aux15 disable 1k
Mdisable disable smallgate 0 0 DISABLE_FET
.model DISABLE_FET NMOS(VTO=1.5 KP=.1 RD=2 RS=2)
Csmallgs smallgate 0 60p
Csmallgd smallgate disable 10p
Csmallds disable 0 15p
Rpwm_series pwm pwm_input 1k
Rpwmpd pwm_input 0 10k
* UCC27511A functional surrogate; actual unchanged TI model checked separately.
Bdriver_req drv_req 0 V=(V(disable)<1.2 && V(pwm_input)>2.2 && V(aux15)>4.5) ? V(aux15) : 0
Rdriver_delay drv_req drv 1
Cdriver_delay drv 0 {EN_TAU}
Ben en 0 V=(V(disable)<1.2 && V(aux15)>4.5) ? 5 : 0
Rdriver drv gate_cmd 1
Rgate gate_cmd gate 10
Cgate gate 0 {GATE_C}
Rgs gate 0 10k
Bpair detector_pair 0 V=(V(fault)<2.5) ? 5 : 0
