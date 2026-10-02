"""Shared acceptance for composed port matrices (round 17, D-9 review P2).

Every script that combines matrices (extrapolate, margin_correct,
extrap_delta) must:
- check each result is square, finite and symmetric BEFORE the eigenvalue
  test, and is positive definite;
- carry the port identity (name, physical id, signed drive K) of its inputs
  through to its output, and refuse inputs whose identities disagree;
- write its output only after every gate passes.
"""
from __future__ import annotations

import json

import numpy as np

SYM_RTOL = 1e-9


def check(L: np.ndarray, label: str) -> float:
    """Gate a matrix; return its smallest eigenvalue. Raises SystemExit on failure."""
    L = np.asarray(L, dtype=float)
    if L.ndim != 2 or L.shape[0] != L.shape[1] or L.shape[0] == 0:
        raise SystemExit(f"{label}: not a square matrix, shape {L.shape}")
    if not np.all(np.isfinite(L)):
        raise SystemExit(f"{label}: non-finite entries")
    scale = max(1.0, float(np.abs(L).max()))
    asym = float(np.abs(L - L.T).max())
    if asym > SYM_RTOL * scale:
        raise SystemExit(f"{label}: not symmetric (max |L - L^T| = {asym:.3g} nH)")
    eig = float(np.linalg.eigvalsh(L).min())
    if eig <= 0:
        raise SystemExit(f"{label}: not positive definite (min eigenvalue {eig:.4g} nH)")
    return eig


def identity(d: dict) -> list[dict] | None:
    """Port identity from a RESULT dict: inductance_matrix's port_identity, or a
    composed file's port_identity; names-only files give names with no K."""
    pid = d.get("port_identity")
    if pid:
        return [{"name": p["name"], "physical": p.get("physical"),
                 "k_A_per_m": [float(x) for x in p["k_A_per_m"]] if p.get("k_A_per_m") is not None else None}
                for p in pid]
    if d.get("names"):
        return [{"name": n, "physical": None, "k_A_per_m": None} for n in d["names"]]
    return None


def common_identity(dicts: dict[str, dict], fallback_names: list[str] | None = None) -> list[dict]:
    """The identity shared by all inputs; refuse disagreement in name, id or signed K.
    An input without any identity must have ascending physical port ids. If no
    input records an identity, explicit fallback_names (e.g. extrapolate.py
    --names) are used and marked as asserted, not recorded."""
    known = {}
    for label, d in dicts.items():
        ident = identity(d)
        if ident is None:
            ids = [int(x) for x in d.get("ports", []) if str(x).isdigit()]
            if not ids or ids != sorted(ids):
                raise SystemExit(f"{label}: no port identity and no ascending port ids")
            continue
        known[label] = ident
    if not known:
        if not fallback_names:
            raise SystemExit("no input records port identities")
        return [{"name": n, "physical": None, "k_A_per_m": None, "asserted_by_caller": True} for n in fallback_names]
    ref_label, ref = next(iter(known.items()))
    merged = [dict(p) for p in ref]
    for label, ident in known.items():
        if [p["name"] for p in ident] != [p["name"] for p in ref]:
            raise SystemExit(f"port order differs: {label} {[p['name'] for p in ident]} vs {ref_label} {[p['name'] for p in ref]}")
        for m, p in zip(merged, ident):
            for key in ("physical", "k_A_per_m"):
                if p[key] is None:
                    continue
                if m[key] is None:
                    m[key] = p[key]
                elif (m[key] != p[key] if key == "physical"
                      else not np.allclose(m[key], p[key], rtol=1e-9, atol=1e-9)):
                    raise SystemExit(f"{label}: port {p['name']} {key} {p[key]} differs from {m[key]}")
    return merged


def read(path: str) -> tuple[np.ndarray, dict]:
    d = json.loads([line for line in open(path) if line.startswith("RESULT ")][-1][7:])
    return np.array(d.get("L0_nH") or d["L_nH"], dtype=float), d
