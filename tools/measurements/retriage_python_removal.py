"""Re-score the NEVER-PORT rows against 'delete Python entirely'.

The original verdicts answered 'should this compute move to Rust?'. Under full
removal the question is different: 'what has to happen to this code before the
interpreter can go away?' -- which has four possible answers, only one of which
is a port.
"""
import sys

CAT = {
 "BLOCKER-ortools": "Bound to the OR-Tools Python API. Not portable by rewriting: needs an FFI to the C++ library, or a different solver.",
 "BLOCKER-scipy":   "Bound to scipy.ndimage EDT. Portable in principle (EDT is a known algorithm) but it is a real numeric port, not glue.",
 "REPLACE":         "Reimplemented natively in Rust rather than translated line-by-line (clap for CLI, direct HTML emission for plots).",
 "PORT":            "Must move. Mechanical orchestration/glue -- no third-party blocker, no design question.",
 "DELETE":          "Disappears with the interpreter: re-export shims, dict-marshalling at the Rust boundary, dead code.",
 "OUT-OF-RUNTIME":  "Dev/CI tooling, not shipped runtime. In scope only if the goal is 'no Python in the repo', not 'no Python at runtime'.",
}

# (loc, category, name) -- category assigned from the triage's own recorded reason
ROWS = [
 (717,"BLOCKER-ortools","CP-SAT solve entry (_encoder_solve.py)"),
 (590,"BLOCKER-ortools","Constraint handlers (handlers/*.py)"),
 (584,"BLOCKER-ortools","Encoder dispatch + validation (cp_sat/__init__)"),
 (518,"BLOCKER-ortools","CpModel wrapper (model.py)"),
 (433,"BLOCKER-ortools","UNSAT extraction + surfacing (unsat.py)"),
 (757,"BLOCKER-ortools","Clearance repair (clearance_repair.py) - solve wrapper"),
 (477,"BLOCKER-scipy","Routability EDT check (routability_check.py)"),
 (196,"BLOCKER-scipy","A* heuristic + demand budget (_astar_heuristics.py)"),
 (6086,"REPLACE","visualization/ (HTML/Plotly)"),
 (2177,"REPLACE","Reporting/CLI/evidence/diagnostics"),
 (1501,"REPLACE","cli/ (click dispatcher + rich panels)"),
 (3582,"PORT","pipeline/ - orchestration/UI"),
 (2624,"PORT","Pipeline/stage orchestration"),
 (2564,"PORT","Type/registry/gate glue"),
 (2238,"PORT","Loop controller"),
 (1962,"PORT","pcl/ - parser/compiler/glue"),
 (1484,"PORT","Adapter I/O (KiCad s-expression writing)"),
 (1424,"PORT","Stage wiring"),
 (1228,"PORT","Type/registry/constant/spec glue"),
 (1076,"PORT","External-tool subprocess wrappers"),
 (1033,"PORT","_constraint_types/"),
 (926,"PORT","Pipeline factory/wiring"),
 (641,"PORT","io/ - live glue (1165 less 524 dead)"),
 (521,"PORT","(root) package entry points"),
 (509,"PORT","Post-solve audit (validator_audit.py)"),
 (477,"PORT","Feedback classifier (feedback.py)"),
 (398,"PORT","adapters/"),
 (393,"PORT","temper_workflow/"),
 (279,"PORT","fields/"),
 (168,"PORT","Loop stability/field detection"),
 (157,"PORT","Net/trace classification config"),
 (1963,"OUT-OF-RUNTIME","Experiment-harness orchestrators"),
 (1302,"OUT-OF-RUNTIME","profiling/"),
 (1181,"OUT-OF-RUNTIME","regression/"),
 (733,"OUT-OF-RUNTIME","testing/"),
 (393,"OUT-OF-RUNTIME","fixtures/ (synthetic netlist generator)"),
 (806,"DELETE","Re-export/type shims"),
 (524,"DELETE","io/net_class_manager.py (zero consumers, already RETIRE)"),
 (133,"DELETE","constraints/_payload.py (marshals to dict at the Rust boundary)"),
 (76,"DELETE","explainability/ (__init__ re-export)"),
 (23,"DELETE","manufacturing/ (__init__ re-export)"),
 (1,"DELETE","placer/ top-level __init__"),
 (1,"DELETE","analysis/ __init__"),
]

tot = {}
for loc, cat, _ in ROWS:
    tot[cat] = tot.get(cat, 0) + loc
grand = sum(tot.values())
print(f"  {'category':<18} {'LOC':>7}  {'%':>5}")
for k in ("BLOCKER-ortools","BLOCKER-scipy","PORT","REPLACE","OUT-OF-RUNTIME","DELETE"):
    print(f"  {k:<18} {tot[k]:>7}  {100*tot[k]/grand:>4.1f}%")
print(f"  {'TOTAL':<18} {grand:>7}")
print()
print(f"  runtime-blocking (BLOCKER+PORT+REPLACE+DELETE): {grand - tot['OUT-OF-RUNTIME']:,}")
print(f"  of which needs a DECISION not a port (blockers): {tot['BLOCKER-ortools']+tot['BLOCKER-scipy']:,}")
