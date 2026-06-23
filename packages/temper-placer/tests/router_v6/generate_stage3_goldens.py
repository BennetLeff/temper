"""Generate golden fixtures for Stage 3 micro-stages."""
import json, sys
from enum import Enum
from pathlib import Path
import networkx as nx
import numpy as np
from networkx.readwrite import node_link_data

HERE = Path(__file__).resolve().parent
GOLDEN_DIR = HERE.parent / 'fixtures' / 'stage3_goldens'

class GoldenEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum): return obj.value
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, (nx.Graph, nx.DiGraph)): return node_link_data(obj)
        if hasattr(obj, '__dataclass_fields__'):
            return {f: self._enc(getattr(obj, f)) for f in obj.__dataclass_fields__}
        return super().default(obj)
    def _enc(self, val):
        if isinstance(val, Enum): return val.value
        if isinstance(val, np.ndarray): return {'_type':'ndarray','dtype':str(val.dtype),'shape':list(val.shape)}
        if isinstance(val, np.integer): return int(val)
        if isinstance(val, np.floating): return float(val)
        if isinstance(val, (nx.Graph, nx.DiGraph)): return node_link_data(val)
        if isinstance(val, dict): return {str(k): self._enc(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)): return [self._enc(v) for v in val]
        if hasattr(val, '__dataclass_fields__'): return {f: self._enc(getattr(val, f)) for f in val.__dataclass_fields__}
        return val

def generate_goldens(regenerate=False):
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.dense_package_detection import identify_dense_packages
    from temper_placer.router_v6.escape_via_generator import generate_escape_vias
    from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator
    from temper_placer.router_v6.stage3_orchestrator import Stage3Orchestrator
    from temper_placer.router_v6.test_boards import get_available_boards
    boards = get_available_boards()
    if not boards:
        print('ERROR: No test boards available.'); sys.exit(1)
    for board in boards:
        d = GOLDEN_DIR / board.name
        if not regenerate and d.exists():
            print(f'  Skip {board.name}'); continue
        d.mkdir(parents=True, exist_ok=True)
        print(f'Processing {board.name}...')
        pcb = parse_kicad_pcb_v6(str(board.path))
        dp = identify_dense_packages(pcb.components)
        vias = []
        for p in dp:
            v = generate_escape_vias(p, pcb.design_rules, strategy='dog-bone')
            vias.extend(v or [])
        orch2 = Stage2Orchestrator(verbose=False)
        state2 = orch2.run(pcb, vias)
        orch3 = Stage3Orchestrator(verbose=False)
        state3 = orch3.run(pcb, state2.channel_skeletons, state2.channel_widths)
        outs = {'constraint_model':state3.constraint_model,'sat_model':state3.sat_variable_map,'topological_solution':state3.topological_solution,'assignment_validation':state3.assignment_valid,'topology_graph':state3.topology_graph}
        for name, data in outs.items():
            with open(d/f'{name}.json','w') as f: json.dump(data,f,cls=GoldenEncoder,indent=2)
        print(f'  Wrote {len(outs)} fixtures')
    print(f'Done: {GOLDEN_DIR}')
if __name__=='__main__': generate_goldens(regenerate='--regenerate' in sys.argv)
