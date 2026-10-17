"""One-shot KiCad oracle receipt; preserve raw clusters and the sole exception."""
import collections,hashlib,json,sys,pcbnew
from pathlib import Path
p=Path(sys.argv[1]); before=hashlib.sha256(p.read_bytes()).hexdigest();b=pcbnew.LoadBoard(str(p));b.BuildConnectivity();c=b.GetConnectivity()
pads=[(f.GetReference(),q) for f in b.GetFootprints() for q in f.Pads() if q.GetNetname()]
all_pad_ids={q.m_Uuid.AsString() for _,q in pads}
by_net=collections.defaultdict(list)
for ref,q in pads:
 ids=frozenset([q.m_Uuid.AsString()]+[v.m_Uuid.AsString() for v in c.GetConnectedItems(q) if v.m_Uuid.AsString() in all_pad_ids])
 for g in by_net[q.GetNetname()]:
  if ids & g['ids']:g['ids']|=ids;g['pads'].append(f'{ref}.{q.GetNumber()}');break
 else:by_net[q.GetNetname()].append({'ids':set(ids),'pads':[f'{ref}.{q.GetNumber()}']})
clusters={n:[{'pads':sorted(g['pads']),'connected_pad_count':len(g['ids'])} for g in groups] for n,groups in sorted(by_net.items())}
splits={n:v for n,v in clusters.items() if len(v)>1}
leg=splits.get('leg_ret',[])
pass_=(set(splits)=={'leg_ret'} and len(leg)==2 and any('R5.1' in g['pads'] and 'R5.2' not in g['pads'] for g in leg) and any('R5.2' in g['pads'] and 'R5.1' not in g['pads'] for g in leg))
assert before==hashlib.sha256(p.read_bytes()).hexdigest()
out={'board_sha256':before,'oracle':'KiCad pcbnew GetConnectedItems, UUID AsString','expected_exception':'R5 internal LEG_RET current/sense connection only','pass':pass_,'split_nets':splits,'pad_clusters':clusters}
Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'pass':pass_,'split_nets':{n:len(v) for n,v in splits.items()}}));sys.exit(0 if pass_ else 1)
