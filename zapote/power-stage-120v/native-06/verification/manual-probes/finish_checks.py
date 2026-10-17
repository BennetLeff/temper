"""One-shot orchestration of existing validators; no engineering verdict logic."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
root=Path('/Users/bennet/Desktop/temper/worktrees/ps-build')
u=root/'zapote/power-stage-120v'; b=Path(sys.argv[1]).resolve(); out=b.parent/'verification';out.mkdir(exist_ok=True)
kpy='/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3'
cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
mpy='/Users/bennet/Miniforge3/bin/python3'; bins=Path('/tmp/ps-native-cargo/debug')
env=os.environ.copy();env.update(KICAD_CONFIG_HOME='/tmp/ps-placement-review-20260926/kicad-config',KICAD_NUM_THREADS='1',ZAPOTE_PAD_ESCAPE_BIN=str(bins/'zapote-pad-escape'),ZAPOTE_POWER_BARRIER_BIN=str(bins/'zapote-power-barrier'),ZAPOTE_POWER_COPPER_IDENTITY_BIN=str(bins/'zapote-power-copper-identity'))
commands=[]
def run(args,name=None):
 p=subprocess.run([str(a) for a in args],env=env,cwd=root,text=True,capture_output=True)
 commands.append({'argv':[str(a) for a in args],'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 if name:(out/name).write_text(p.stdout)
 print(name or str(args[1]),p.returncode,flush=True)
 p.check_returncode()
start=hashlib.sha256(b.read_bytes()).hexdigest()
run([kpy,u/'tools/check_copper_identity.py',b],'copper-identity.json')
run([kpy,u/'tools/check_native_parity.py',b,b.parent/'source-manifest.json',u/'frozen/default.net',bins/'zapote-power-native-parity'],'source-parity.json')
run([bins/'zapote-board',b],'stackup.json')
run([kpy,u/'tools/copper_dump.py',b,out/'copper.json'])
run([mpy,u/'tools/barrier_check.py',out/'copper.json'],'barrier.json')
run([kpy,'/tmp/ps-finish/connectivity-receipt.py',b,out/'connectivity.json'])
run([kpy,'/tmp/ps-finish/gate-path-lengths.py',b],'gate-lengths.json')
run([mpy,'/tmp/ps-finish/hardware_surface_screen.py',out/'copper.json',u/'native-05/placement-metrics.json'],'hardware-surface.json')
for i in range(1,4):
 run([cli,'pcb','drc','--all-track-errors','--schematic-parity','--severity-all','--format','json','--output',out/f'drc-{i}.json',b])
 assert hashlib.sha256(b.read_bytes()).hexdigest()==start
(out/'board-sha256.txt').write_text(start+'\n')
