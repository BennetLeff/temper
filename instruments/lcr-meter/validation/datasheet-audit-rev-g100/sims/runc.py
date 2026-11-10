import sys, json, concurrent.futures as cf
import run50
def main():
  cases=[]
  for c in (1e-6, 2.2e-6, 3.3e-6, 4.7e-6, 10e-6, 100e-9):
      for scn in ('h_to_gnd','current_only','kelvin'):
          for v in (50, 30):
              cases.append(('parts_jackside', scn, 'unpowered', 'open', '100R', c, v))
  with cf.ProcessPoolExecutor(6) as ex:
      for case, out in ex.map(run50.one, cases):
          s=out['stress']; t=s['tvs1_hcur']
          print(case[1], case[5], case[6], out['class'], 'TVS1 hcur Ipk %.1f A Ppk %.0f W w50 %.2f us E %.0f uJ' % (t['i_pk'], t['p_pk'], t['w50_us'], t['e_uj']), 'iso_v %.1f' % s['iso_hcur']['v_pk'])

if __name__=='__main__':
  main()
