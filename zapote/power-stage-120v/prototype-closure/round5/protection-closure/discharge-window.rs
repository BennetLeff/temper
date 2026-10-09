//! DC window corner screen. Two explicit installed-error allocations are not
//! promoted to datasheet maxima: comparator hysteresis2mV and extra AFE leakage.
fn bit(n:usize,b:usize)->f64 { if n&(1<<b)==0 {-1.0} else {1.0} }
fn main(){
 let tol=0.001+25e-6*65.0; //0.1% +25ppm/K,maxdelta65K; LM4040A25I caps Ta at85C.
 let mut lo=f64::INFINITY;let mut hi=f64::NEG_INFINITY;
 let mut zero_min=f64::INFINITY;
 // Resistor,reference,commonmode,offset,gain corners. Linear-fractional circuit
 // functions attain extrema at component endpoints (positive denominators).
 for n in 0..(1<<17){
  let r=|base:f64,b|base*(1.0+tol*bit(n,b));
  let v25=2.5+0.028*bit(n,0);
  let vref=v25*r(10000.,1)/(r(10000.,1)+r(10000.,2)) +0.00235*bit(n,3);
  let rp=r(20000.,4);let rr=r(10000.,5);let rn=r(20000.,6);let rf=r(10000.,7);
  let k=rf/rn;
  let a=(1.0+k)*rr/(rp+rr);let b=(1.0+k)*rp/(rp+rr);
  let cm=1.44+0.05*bit(n,8);
  let amc_gain=2.0*(1.0+0.009425*bit(n,9));
  let ratio=r(2490.,10)/(r(2490.,10)+8.0*r(249000.,11));
  let slope=(a+k)*amc_gain*ratio/2.0;
  let offset=(a-k)*cm+b*vref+(a+k)*amc_gain*0.00096*bit(n,12)/2.0
       +(1.0+k)*0.00285*bit(n,13);
  let rt=r(620000.,14);let rb=r(10000.,15);
  let thresh_hi=vref+(v25-vref)*rb/(rt+rb);
  let thresh_lo=vref*rt/(rt+rb);
  let cmp=0.00665*bit(n,16);
  hi=hi.max((thresh_hi+cmp-offset)/slope);
  lo=lo.min((thresh_lo+cmp-offset)/slope);
  //Minimum distance of zero signal from either nominal worst threshold with
  //comparator sign applied outward vs inward, conservatively independent.
  zero_min=zero_min.min((thresh_hi-offset).min(offset-thresh_lo)-0.00665);
 }
 assert!(lo > -30. && hi < 30.,"outside30V: {lo} {hi}");
 assert!(zero_min>0.,"zero may be rejected {zero_min}");
 println!("conditional_DC_window,corner_count,131072,lower_V,{lo:.9},upper_V,{hi:.9},zero_acceptance_margin_V,{zero_min:.9}");
 println!("allocations_not_datasheet_guarantees,comparator_hysteresis_le_2mV,extra_AFE_bias_leak_error_le_0.5mV;no_power_release");
}
