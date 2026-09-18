"""Keep procurement metadata out of printed PCB artwork."""
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parents[1]
path=root/'candidate/section.kicad_pcb'
io=p.PCB_IO_KICAD_SEXPR();b=io.LoadBoard(str(path),None)
for f in b.GetFootprints():
 for key in ['SourceInstance','MPN','Datasheet']:
  if f.HasField(key):f.GetField(key).SetVisible(False)
io.SaveBoard(str(path),b)
