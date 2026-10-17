#!/usr/bin/env python3
"""Negative and positive cases for matrix_gate (D-9 review, P2). Prints PASS or raises."""
from __future__ import annotations

import numpy as np

import matrix_gate as mg


def refused(fn, *args) -> str:
    try:
        fn(*args)
    except SystemExit as e:
        return str(e)
    raise AssertionError(f"{fn.__name__}{args!r:.80} was accepted")


def main() -> None:
    good = np.array([[30.0, 19.0], [19.0, 30.0]])
    assert mg.check(good, "good") > 0
    assert "not symmetric" in refused(mg.check, np.array([[30.0, 19.0], [18.0, 30.0]]), "asym")
    # a nonsymmetric matrix whose symmetric part is SPD must still be refused
    assert "not symmetric" in refused(mg.check, np.array([[30.0, 25.0], [13.0, 30.0]]), "asym-spd-part")
    assert "positive definite" in refused(mg.check, np.array([[10.0, 20.0], [20.0, 10.0]]), "indef")
    assert "non-finite" in refused(mg.check, np.array([[np.nan, 0.0], [0.0, 1.0]]), "nan")
    assert "square" in refused(mg.check, np.ones((2, 3)), "rect")
    pid = lambda k2: {"port_identity": [{"name": "P1", "physical": 10, "k_A_per_m": [-2500, 0, 0]},
                                        {"name": "P2", "physical": 11, "k_A_per_m": k2}]}
    same = mg.common_identity({"a": pid([-2500, 0, 0]), "b": pid([-2500, 0, 0]), "c": {"names": ["P1", "P2"]}})
    assert [p["physical"] for p in same] == [10, 11]
    assert "differs" in refused(mg.common_identity, {"a": pid([-2500, 0, 0]), "b": pid([2500, 0, 0])})
    swapped = {"port_identity": list(reversed(pid([-2500, 0, 0])["port_identity"]))}
    assert "order differs" in refused(mg.common_identity, {"a": pid([-2500, 0, 0]), "b": swapped})
    assert "ascending" in refused(mg.common_identity, {"a": pid([-2500, 0, 0]), "b": {"ports": ["11", "10"]}})
    print("PASS test_matrix_gate: symmetry before SPD, indefinite, non-finite, shape, "
          "signed-K and order mismatch refused")


if __name__ == "__main__":
    main()
