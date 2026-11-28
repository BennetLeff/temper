import re,json,sys
s=open('../controller/frozen/default.net').read()
# simple sexpr parser
def parse(s):
    tok=re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+',s)
    st=[[]]
    for t in tok:
        if t=='(': st.append([])
        elif t==')': x=st.pop(); st[-1].append(x)
        else: st[-1].append(t[1:-1] if t.startswith('"') else t)
    return st[0][0]
t=parse(s)
def find(n,k): return [c for c in n if isinstance(c,list) and c and c[0]==k]
comps={}
for c in find(find(t,'components')[0],'comp'):
    d={x[0]:x[1] for x in c[1:] if isinstance(x,list) and len(x)==2 and isinstance(x[1],str)}
    for f in find(c,'fields'):
        for ff in find(f,'field'):
            nm=find(ff,'name')[0][1]; d['f_'+nm]=ff[-1] if isinstance(ff[-1],str) else ''
    for p in find(c,'property'):
        nm=find(p,'name')[0][1]; v=find(p,'value'); d['p_'+nm]=v[0][1] if v and len(v[0])>1 else ''
    comps[d['ref']]=d
nets={}
for n in find(find(t,'nets')[0],'net'):
    name=find(n,'name')[0][1]
    nets[name]=[(find(x,'ref')[0][1],find(x,'pin')[0][1],(find(x,'pinfunction') or [[0,'']])[0][1]) for x in find(n,'node')]
json.dump(dict(comps=comps,nets=nets),open('net.json','w'))
if __name__=='__main__':
    print(len(comps),len(nets))
    import itertools
    for r in ['U1','U2','U51','U30','U50','J4','J13','L2','C9']: print(comps.get(r))
