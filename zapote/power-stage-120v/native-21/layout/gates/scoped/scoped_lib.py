"""Shared logic of the scoped chain: path classification, content keys, the step plan and the scoped card.

Imported by scoped_chain.py (the CLI) and backtest.py. Standard library only (python3 -I).
"""
from __future__ import annotations

import hashlib
import os
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = "zapote/power-stage-120v"
# the repository the trees are read from: this checkout (gates/scoped sits at <unit>/native-21/layout/gates/scoped),
# or $SCOPED_REPO (another checkout / worktree of the same repository; read with git show / ls-tree / diff only)
REPO = Path(os.environ["SCOPED_REPO"]).resolve() if os.environ.get("SCOPED_REPO") else HERE.parents[5]
UNIT = REPO / PS
# read-only git: never refresh the index of a checkout another session may be using
os.environ.setdefault("GIT_OPTIONAL_LOCKS", "0")
DEPMAP = json.loads((HERE / "depmap.json").read_text())
STEPS = DEPMAP["steps"]
KEYED = [s for s, v in STEPS.items() if v["policy"] == "keyed"]


# ---- path classification ------------------------------------------------------------------------------------------
def _expand(glob: str) -> list[str]:
    m = re.search(r"\{([^{}]*)\}", glob)
    if not m:
        return [glob]
    out = []
    for alt in m.group(1).split(","):
        out += _expand(glob[:m.start()] + alt + glob[m.end():])
    return out


def _regex(glob: str) -> re.Pattern:
    parts = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            parts.append(r"(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            parts.append(r".*")
            i += 2
        elif glob[i] == "*":
            parts.append(r"[^/]*")
            i += 1
        elif glob[i] == "?":
            parts.append(r"[^/]")
            i += 1
        else:
            parts.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(parts) + "$")


RULES = [(r, [_regex(g) for g in _expand(r["glob"])]) for r in DEPMAP["path_rules"]]


def classify_path(path: str) -> dict:
    """path relative to the unit (zapote/power-stage-120v) or '@repo/...'; returns the first matching rule."""
    for r, rxs in RULES:
        if any(rx.match(path) for rx in rxs):
            return r
    return {"glob": None, "class": "unknown"}


def unit_relative(repo_path: str) -> str:
    return repo_path[len(PS) + 1:] if repo_path.startswith(PS + "/") else "@repo/" + repo_path


# ---- trees: a git commit or a directory -----------------------------------------------------------------------------
class Tree:
    """Read files of the unit at a git commit (ref) or from a checkout (root = repo root)."""

    def __init__(self, ref: str | None = None, root: Path = REPO):
        self.ref, self.root = ref, Path(root)
        self._ls = None
        self._blob: dict = {}

    def _repo_path(self, p: str) -> str:
        return p[6:] if p.startswith("@repo/") else f"{PS}/{p}"

    def read(self, p: str) -> bytes | None:
        rp = self._repo_path(p)
        if self.ref is None:
            f = self.root / rp
            return f.read_bytes() if f.is_file() else None
        r = subprocess.run(["git", "-C", str(self.root), "show", f"{self.ref}:{rp}"], capture_output=True)
        return r.stdout if r.returncode == 0 else None

    def files(self) -> list[str]:
        if self._ls is None:
            if self.ref is None:
                r = subprocess.run(["git", "-C", str(self.root), "ls-files", "-co", "--exclude-standard", "--", PS, "firmware"],
                                   capture_output=True, text=True, check=True)
                self._ls = [unit_relative(x) for x in r.stdout.split("\n") if x]
            else:
                r = subprocess.run(["git", "-C", str(self.root), "ls-tree", "-r", self.ref, "--", PS, "firmware"],
                                   capture_output=True, text=True, check=True)
                self._ls = []
                for line in r.stdout.split("\n"):
                    if line:
                        meta, path = line.split("\t", 1)
                        self._blob[unit_relative(path)] = meta.split()[2]
                        self._ls.append(unit_relative(path))
        return self._ls

    def blob_id(self, p: str) -> str:
        """git blob id of a file (for a git tree straight from ls-tree; for a checkout computed the same way)."""
        if self.ref is not None:
            self.files()
            return self._blob.get(p, "-")
        d = self.read(p)
        return git_blob_id(d) if d is not None else "-"

    def glob(self, g: str) -> list[str]:
        rxs = [_regex(x) for x in _expand(g)]
        return sorted(f for f in self.files() if any(rx.match(f) for rx in rxs))


def changed_paths(bench: Tree, cand: Tree) -> list[str]:
    """Paths (unit-relative) that differ between two trees, git-aware."""
    args = ["git", "-C", str(bench.root), "diff", "--name-only", bench.ref]
    if cand.ref is not None:
        args.append(cand.ref)
    r = subprocess.run(args + ["--", PS, "firmware"], capture_output=True, text=True, check=True)
    out = {unit_relative(x) for x in r.stdout.split("\n") if x}
    if cand.ref is None:          # untracked files in the working tree
        u = subprocess.run(["git", "-C", str(cand.root), "ls-files", "--others", "--exclude-standard", "--", PS, "firmware"],
                           capture_output=True, text=True, check=True)
        out |= {unit_relative(x) for x in u.stdout.split("\n") if x}
    return sorted(out)


def effective_changes(bench: Tree, cand: Tree, paths: list[str]) -> list[str]:
    """Drop the files chain.sh rewrites per TAG (DEPMAP normalise) when they are equal after normalising."""
    out = []
    for p in paths:
        if p in DEPMAP["normalise"]:
            a, b = bench.read(p), cand.read(p)
            if a is not None and b is not None and _normalised(p, a) == _normalised(p, b):
                continue
        out.append(p)
    return out


# ---- content keys ----------------------------------------------------------------------------------------------------
def _normalised(path: str, data: bytes) -> bytes:
    for pat, rep in [DEPMAP["normalise"].get(path, [])] if path in DEPMAP["normalise"] else []:
        data = re.sub(pat.encode(), rep.encode(), data)
    return data


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def files_digest(tree: Tree, globs: list[str]) -> tuple[str, dict]:
    """Digest over the files the globs name: each file by its git blob id (the same for a commit and a checkout), the
    files chain.sh rewrites per TAG (DEPMAP normalise) by the blob id of their normalised content."""
    rows = {}
    for g in globs:
        hits = tree.glob(g) if any(c in g for c in "*{?") else [g]
        for f in hits:
            if f in DEPMAP["normalise"]:
                d = tree.read(f)
                rows[f] = git_blob_id(_normalised(f, d)) if d is not None else "-"
            else:
                rows[f] = tree.blob_id(f)
    h = hashlib.sha256()
    for f in sorted(rows):
        h.update(f"{f}\0{rows[f]}\n".encode())
    return h.hexdigest(), rows


def _h(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def step_keys(tree: Tree, nk: dict, extra: dict | None = None) -> dict:
    """Content keys of the keyed and manual steps for one tree + its built board's net_keys.json (nk).

    keyed steps: the board's canonical copper key + the step's files (+ upstream keys);
    manual steps: the net_fill keys of the nets they read, the part_geom keys of the parts, their own folder."""
    extra = extra or {}
    ck = nk["copper_key_canonical"]
    files = {s: files_digest(tree, DEPMAP["step_files"][s]) for s in DEPMAP["step_files"]}
    k = {}
    k["task04"] = _h("task04", ck, files["task04"][0], extra.get("sheet_barrel", ""))
    k["b3_study"] = _h("b3", ck, files["b3_study"][0], k["task04"])
    k["ceiling_sweep"] = k["b3_study"]
    k["b3_ratings"] = _h("ratings", ck, files["b3_ratings"][0], k["task04"])
    k["core_barrier"] = _h("barrier", nk.get("board_sha256", ""), files["core_barrier"][0], extra.get("barrier_bin", ""))
    for s in ("necks", "ocp_pickup"):
        rd = STEPS[s]["reads"]
        parts = [nk["net_fill"].get(n, "-") for n in rd.get("net_fill", [])]
        parts += [nk["part_geom"].get(r, "-") for r in rd.get("parts_geom", [])]
        k[s] = _h(s, *parts)
    net = tree.read("native-21/frozen/default.net") or b""
    k["audit_rs"] = _h("audit_rs", hashlib.sha256(net).hexdigest(),
                       hashlib.sha256(tree.read("audit.rs") or b"").hexdigest(),
                       hashlib.sha256(tree.read("audit_f6.rs") or b"").hexdigest())
    return {"keys": k, "files": {s: v[1] for s, v in files.items()}}


# ---- board diff ------------------------------------------------------------------------------------------------------
def board_diff(a: dict, b: dict) -> dict:
    def d(x, y):
        return sorted(n for n in set(x) | set(y) if x.get(n) != y.get(n))
    geom = d(a["part_geom"], b["part_geom"])
    return {"copper_changed": a["copper_key_canonical"] != b["copper_key_canonical"],
            "rules_changed": a["context"] != b["context"],
            "nets_own": d(a["net_own"], b["net_own"]), "nets_fill": d(a["net_fill"], b["net_fill"]),
            "parts_geom": geom, "parts_value_only": [r for r in d(a["part"], b["part"]) if r not in geom]}


def bom_diff(a: bytes | None, b: bytes | None) -> list[str]:
    """Designators whose BOM row (MPN / value / footprint / LCSC) differs between two frozen default.csv files."""
    import csv
    import io

    def rows(x):
        out = {}
        if not x:
            return out
        for r in csv.DictReader(io.StringIO(x.decode())):
            for ref in r["Designator"].split(","):
                out[ref.strip()] = (r.get("Comment"), r.get("Footprint"), r.get("LCSC"))
        return out
    ra, rb = rows(a), rows(b)
    return sorted(r for r in set(ra) | set(rb) if ra.get(r) != rb.get(r))


def input_classes(paths_by_class: dict, bd: dict | None, bom: list[str]) -> list[str]:
    """Human labels for the change: bom_only / placement / copper(N nets) / model / desk / firmware / ..."""
    out = []
    if paths_by_class.get("full"):
        out.append("full-chain input (" + ", ".join(sorted(paths_by_class["full"]))[:120] + ")")
    if paths_by_class.get("unknown"):
        out.append("UNKNOWN paths")
    if bd is not None:
        if bd["copper_changed"]:
            out.append(f"copper ({len(bd['nets_own'])} nets authored, {len(bd['nets_fill'])} with refill reach"
                       + (", rules file changed" if bd["rules_changed"] else "") + ")")
        if bd["parts_geom"]:
            out.append(f"placement / footprint ({len(bd['parts_geom'])} parts)")
        if bd["parts_value_only"] and not bd["copper_changed"] and not bd["parts_geom"]:
            out.append(f"bom_only ({len(bd['parts_value_only'])} parts, same footprint and copper)")
        elif bd["parts_value_only"]:
            out.append(f"values ({len(bd['parts_value_only'])} parts)")
    elif bom:
        out.append(f"bom ({len(bom)} designators)")
    steps = {s for c, ps in paths_by_class.items() if c == "input" for p in ps for s in ps[p]}
    if steps & {"task04", "b3_study", "ceiling_sweep", "b3_ratings", "heat_sources"}:
        out.append("thermal model")
    if any(p.startswith("@repo/firmware/") for c in ("input", "not_read") for p in paths_by_class.get(c, {})):
        out.append("firmware")
    if steps & {"card", "necks", "ocp_pickup"}:
        out.append("desk / card inputs")
    if steps - {"task04", "b3_study", "ceiling_sweep", "b3_ratings", "heat_sources", "card", "necks", "ocp_pickup"}:
        out.append("gate scripts (" + ", ".join(sorted(steps - {"task04", "b3_study", "ceiling_sweep", "b3_ratings", "heat_sources", "card", "necks", "ocp_pickup"})) + ")")
    return out or ["no input changed"]


# ---- the plan --------------------------------------------------------------------------------------------------------
def plan(paths: list[str], bench_keys: dict | None, cand_keys: dict | None, bd: dict | None,
         rebuilt_board_differs: bool | None = None, cand_tag: str | None = None) -> dict:
    """Decide every step: RUN (with the reason) or REUSE (with the key that proves it).

    paths: changed unit-relative paths; bench_keys / cand_keys: step_keys()['keys'] of each side (cand_keys None
    before the build: keyed decisions are then provisional); bd: board_diff of the two builds (None before the build).
    """
    by_class: dict = {}
    for p in paths:
        r = classify_path(p)
        c = r["class"]
        steps = list(r.get("steps", [])) + list(r.get("also_steps", []))
        by_class.setdefault(c, {})[p] = steps
    full = bool(by_class.get("full") or by_class.get("unknown"))
    rebuild = full or bool(by_class.get("build"))
    triggered = {}
    for c in ("input", "build"):
        for p, steps in by_class.get(c, {}).items():
            for s in steps:
                triggered.setdefault(s, []).append(p)
    dec = {}
    if full:
        for s in STEPS:
            dec[s] = {"do": "RUN", "why": "full chain: " + ", ".join(sorted(set(by_class.get("full", {})) | set(by_class.get("unknown", {}))))[:300]}
        return {"mode": "FULL", "by_class": by_class, "steps": dec}
    for s, v in STEPS.items():
        pol = v["policy"]
        if pol == "rebuild":
            dec[s] = {"do": "RUN", "why": "board inputs changed: " + ", ".join(sorted(by_class.get("build", {})))[:200]} if rebuild \
                else {"do": "REUSE", "why": "no board input changed", "proof": "benchmark build (board_sha256 in its manifest)"}
        elif pol == "on_rebuild":
            if rebuild:
                dec[s] = {"do": "RUN", "why": "rebuilt board (safety / export step runs on every rebuilt board)"}
            elif s in triggered:
                dec[s] = {"do": "RUN", "why": "own inputs changed: " + ", ".join(triggered[s])[:200]}
            else:
                dec[s] = {"do": "REUSE", "why": "same board, inputs unchanged", "proof": "benchmark build + step files"}
        elif pol == "cheap":
            dec[s] = {"do": "RUN", "why": "cheap (always recomputed)" + (": own inputs changed" if s in triggered else "")}
    # keyed thermal steps: by key; plus the B3 same-board rule on a rebuilt board
    for s in KEYED:
        if s in triggered:          # a path rule names the step: run, whatever the key says (the key may not list it)
            dec[s] = {"do": "RUN", "why": "own inputs changed: " + ", ".join(triggered[s])[:200]}
        elif cand_keys is None or bench_keys is None:
            dec[s] = {"do": "RUN?", "why": "key not known before the build (decided after it)"}
        elif cand_keys[s] == bench_keys[s]:
            dec[s] = {"do": "REUSE", "why": "content key unchanged", "proof": cand_keys[s]}
        else:
            dec[s] = {"do": "RUN", "why": "content key changed" + (": " + ", ".join(triggered[s])[:200] if s in triggered else " (copper / upstream)")}
    # downstream of task 04: B3, the sweep and the ratings read its A4 fields (their keys carry task 04's key; this also
    # covers a task-04 trigger by a path the key does not list)
    if dec["task04"]["do"] == "RUN":
        for s in ("b3_study", "ceiling_sweep", "b3_ratings"):
            if dec[s]["do"] == "REUSE":
                dec[s] = {"do": "RUN", "why": "upstream task 04 recomputes"}
    if rebuild and rebuilt_board_differs is not False and dec["task04"]["do"] == "REUSE" \
            and (dec["b3_study"]["do"] != "REUSE"):
        dec["task04"] = {"do": "RUN", "why": "forced: B3 recomputes on a rebuilt board and thermal.py requires the A4 cases from the same board"}
    for s in ("necks", "ocp_pickup", "audit_rs"):
        tf = DEPMAP["manual_tag_files"].get(s, "").format(tag=(cand_tag or "").replace("native21", ""))
        if cand_tag and tf and tf in paths:
            dec[s] = {"do": "RUN", "why": f"lane provided {tf} (manual step rerun for this tag)"}
        elif cand_keys is None or bench_keys is None:
            dec[s] = {"do": "RUN?", "why": "manual step; key decided after the build"}
        elif cand_keys[s] == bench_keys[s] and s not in triggered:
            dec[s] = {"do": "REUSE", "why": "content key unchanged (carried from the benchmark card)", "proof": cand_keys[s]}
        else:
            dec[s] = {"do": "STALE", "why": "inputs changed: the lane must rerun it (manual step)"
                      + (" - " + ", ".join(triggered[s])[:150] if s in triggered else "")}
    return {"mode": "REBUILD" if rebuild else "REUSE-BUILD", "by_class": by_class, "steps": dec}


def card_entries(step: str) -> list[str]:
    return STEPS[step]["card"]


def entry_values(card: dict, entry: str) -> dict:
    grp, key = entry.split(".", 1)
    g = card.get(grp, {})
    if key == "*":
        return {f"{grp}.{k}": v for k, v in g.items()}
    return {entry: g.get(key, "<absent>")}


def producers(entry: str) -> list[str]:
    """Steps whose data an entry is computed from (depmap entry_producers, else the step listing it in 'card')."""
    if entry in DEPMAP.get("entry_producers", {}):
        return DEPMAP["entry_producers"][entry]
    grp = entry.split(".", 1)[0]
    return [s for s, v in STEPS.items() if entry in v["card"] or f"{grp}.*" in v["card"]] or ["card"]


def owner_of(entry: str) -> str | None:
    p = producers(entry)
    return p[0] if p else None


def entry_decision(entry: str, steps: dict) -> dict:
    """REUSE only if every producer is reused; STALE if any is stale; else RUN."""
    ds = [steps.get(s, {"do": "RUN"}) for s in producers(entry)]
    if any(d["do"] == "STALE" for d in ds):
        return next(d for d in ds if d["do"] == "STALE")
    if all(d["do"] == "REUSE" for d in ds):
        return {"do": "REUSE", "proof": ",".join(str(d.get("proof")) for d in ds), "step": "+".join(producers(entry))}
    return {"do": "RUN"}


def scoped_card(fresh: dict, bench: dict, pl: dict) -> dict:
    """Merge: every entry of a RUN step from the fresh card, every entry of a REUSE step from the benchmark card with the
    key that justifies it; STALE manual entries are kept from the benchmark and flagged."""
    out = {"tag": fresh.get("tag"), "build": fresh.get("build"), "board_sha256": fresh.get("board_sha256"),
           "gates": {}, "performance": {}, "cost": {}, "sources": dict(fresh.get("sources", {})),
           "scoped": {"mode": pl["mode"], "benchmark": bench.get("tag"), "recomputed": {}, "reused": {}, "stale": {}}}
    for grp in ("gates", "performance", "cost"):
        for k in sorted(set(fresh.get(grp, {})) | set(bench.get(grp, {}))):
            e = f"{grp}.{k}"
            s = "+".join(producers(e))
            d = entry_decision(e, pl["steps"])
            if d["do"] == "REUSE":
                # the fresh scorecard recomputes the entry from the reused outputs when it can (same board); otherwise
                # the benchmark card's value is carried; a scorecard change makes a carried value stale
                if k in fresh.get(grp, {}):
                    out[grp][k] = fresh[grp][k]
                    out["scoped"]["reused"][e] = {"step": s, "proof": d.get("proof"), "value": "recomputed by the card from reused outputs"}
                elif pl["steps"].get("card", {}).get("why", "").endswith("own inputs changed"):
                    out["scoped"]["stale"][e] = {"step": s, "why": "scorecard inputs changed and the reused value cannot be recomputed on this build"}
                    if k in bench.get(grp, {}):
                        out[grp][k] = bench[grp][k]
                else:
                    if k in bench.get(grp, {}):
                        out[grp][k] = bench[grp][k]
                    out["scoped"]["reused"][e] = {"step": s, "proof": d.get("proof"), "value": "carried from the benchmark card"}
            elif d["do"] == "STALE" and s == "audit_rs" and k in fresh.get(grp, {}):
                # audit.rs is run by the lane and attested to scorecard.py (--audit PASS|FAIL), as in the full flow
                out[grp][k] = fresh[grp][k]
                out["scoped"]["recomputed"][e] = {"step": s, "value": "lane attestation (--audit)"}
            elif d["do"] == "STALE":
                if k in bench.get(grp, {}):
                    out[grp][k] = bench[grp][k]
                out["scoped"]["stale"][e] = {"step": s, "why": d["why"]}
            else:
                if k in fresh.get(grp, {}):
                    out[grp][k] = fresh[grp][k]
                out["scoped"]["recomputed"][e] = {"step": s or "card"}
    return out
