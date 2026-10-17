from pathlib import Path
import json,os,subprocess,sys,hashlib
import cairosvg
board=Path(sys.argv[1]).resolve();out=board.parent/'previews';out.mkdir(exist_ok=True)
env=os.environ.copy();env['KICAD_CONFIG_HOME']='/tmp/ps-placement-review-20260926/kicad-config'
cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
records=[]
for name,layers in [('front','F.Cu,F.Silkscreen,Edge.Cuts'),('inner-return','In1.Cu,Edge.Cuts'),('inner-bus','In2.Cu,Edge.Cuts'),('back','B.Cu,B.Silkscreen,Edge.Cuts')]:
 svg=out/(name+'.svg');png=out/(name+'.png')
 args=[cli,'pcb','export','svg','--layers',layers,'--mode-single','--fit-page-to-board','--exclude-drawing-sheet','--output',str(svg),str(board)]
 p=subprocess.run(args,env=env,text=True,capture_output=True,check=True)
 cairosvg.svg2png(url=str(svg),write_to=str(png),output_width=1800)
 records.append({'argv':args,'exit_code':p.returncode,'stdout':p.stdout,'svg_sha256':hashlib.sha256(svg.read_bytes()).hexdigest(),'png_sha256':hashlib.sha256(png.read_bytes()).hexdigest()})
(out/'render-receipt.json').write_text(json.dumps({'board_sha256':hashlib.sha256(board.read_bytes()).hexdigest(),'renderer':'CairoSVG '+cairosvg.__version__,'renders':records},indent=2)+'\n')
