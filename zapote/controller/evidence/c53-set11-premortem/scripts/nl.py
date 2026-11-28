"""Parse frozen netlist + resolved components. Usage: nl.py [netfile] ; writes nets.txt and comps.txt to _scratch."""
import re, json, sys, os
HERE=os.path.dirname(os.path.abspath(__file__))
def load(net, resolved=None):
    t=open(net).read()
    comps={}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(footprint "([^"]*)"\)\s*\(libsource .*?\)\s*\(sheetpath \(names "([^"]*)"\)',t,re.S):
        comps[m.group(1)]={'fp':m.group(3),'addr':m.group(4).split('::')[-1]}
    if resolved:
        rc=json.load(open(resolved))['components']
        by={c['address'].split('::')[-1]:c['attributes'] for c in rc}
        for r,c in comps.items():
            a=by.get(c['addr'],{})
            c['mpn']=a.get('mpn'); c['value']=a.get('value')
    nets={}
    ni=t.index('(nets')
    for blk in re.split(r'\(net \(code',t[ni:])[1:]:
        name=re.search(r'\(name "([^"]*)"\)',blk).group(1)
        nets[name]=re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)',blk)
    return comps,nets
if __name__=='__main__':
    base=os.path.join(HERE,'..','controller','frozen')
    comps,nets=load(os.path.join(base,'default.net'),os.path.join(base,'resolved-components.json'))
    with open(os.path.join(HERE,'nets.txt'),'w') as f:
        for n,nodes in sorted(nets.items()):
            f.write(f"{n}: "+' '.join(f"{r}.{p}" for r,p in nodes)+"\n")
    pins={}
    for n,nodes in nets.items():
        for r,p in nodes: pins.setdefault(r,{})[p]=n
    def key(r):
        m=re.match(r'([A-Za-z]+)(\d+)',r); return (m.group(1),int(m.group(2)))
    with open(os.path.join(HERE,'comps.txt'),'w') as f:
        for r in sorted(comps,key=key):
            c=comps[r]
            ps=pins.get(r,{})
            f.write(f"{r} [{c.get('mpn')}] {c.get('value')} <{c['addr']}> {c['fp'].split(':')[-1]}\n")
            for p in sorted(ps,key=lambda x:(len(x),x)):
                f.write(f"    {p}: {ps[p]}\n")
    print(len(comps),len(nets))
