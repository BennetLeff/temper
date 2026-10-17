"""One-shot saved-board comparison with only footprint annotations/models removed."""
import hashlib,json,re,sys
from pathlib import Path

def ast(path):
 tokens=iter(re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',Path(path).read_text()))
 def seq():
  out=[]
  for t in tokens:
   if t=='(':out.append(seq())
   elif t==')':return out
   else:out.append(t)
  return out
 tree=seq()
 def clean(n):
  if not isinstance(n,list):return n
  if n and n[0]=='footprint':n=[c for c in n if not (isinstance(c,list) and c and c[0] in ['property','model','fp_text','fp_text_box'])]
  return [clean(c) for c in n]
 return clean(tree)
a,b=map(Path,sys.argv[1:]);x,y=ast(a),ast(b)
result={'before_board_sha256':hashlib.sha256(a.read_bytes()).hexdigest(),'after_board_sha256':hashlib.sha256(b.read_bytes()).hexdigest(),'scope':'All saved KiCad nodes except footprint properties/text/models; compare after native normalization','identical':x==y}
if x!=y:
 def diff(x,y,path=''):
  if isinstance(x,list) and isinstance(y,list):
   if len(x)!=len(y):print('length',path,len(x),len(y),file=sys.stderr)
   for i,(u,v) in enumerate(zip(x,y)):
    if u!=v:diff(u,v,path+'/'+str(i));break
  else: print('first difference',path,repr(x),repr(y),file=sys.stderr)
 diff(x,y)
print(json.dumps(result,indent=2));sys.exit(0 if x==y else 1)
