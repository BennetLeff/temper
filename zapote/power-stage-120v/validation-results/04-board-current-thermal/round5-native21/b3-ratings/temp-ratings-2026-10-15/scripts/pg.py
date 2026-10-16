import sys,re
# usage: pg.py file.txt regex [context]  -> prints matches with PDF page number
f,rx=sys.argv[1],re.compile(sys.argv[2],re.I); ctx=int(sys.argv[3]) if len(sys.argv)>3 else 0
pages=open(f,errors='replace').read().split('\f')
for i,p in enumerate(pages,1):
    L=p.split('\n')
    for j,l in enumerate(L):
        if rx.search(l):
            for k in range(max(0,j-ctx),min(len(L),j+ctx+1)):
                print(f"p{i}:{L[k].rstrip()}")
            if ctx: print('--')
