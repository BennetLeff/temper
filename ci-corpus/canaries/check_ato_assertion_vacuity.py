"""Canary fixtures for check_ato_assertion_vacuity.py.

Each ``pristine_*``/``seed_*`` function takes the (possibly mutated)
``check_ato_assertion_vacuity`` module and returns a normalized verdict
string: ``"clean"``, ``"violation"``, or ``"error"``.

The point of these fixtures is to make the gate's own claim falsifiable.  The
gate says "this assertion cannot fail".  A gate that says that about
everything, or about nothing, is worthless in exactly the way the assertions
it audits are worthless.  So each seed is a minimal ``.ato`` tree carrying one
known-vacuous or one known-sound assertion, and the mutation runner checks
that weakening the gate's detection logic flips the verdict.

``_CIRCUIT_COUPLED`` in particular is the specificity fixture: a resistor
whose ``.value`` genuinely drives the quantity being asserted on.  If the gate
ever reports that as vacuous, it has become a gate that fires on correct
input, which is itself a defect.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

#: A rating checked against a value the circuit actually produces.  The
#: dissipation in ``r_load`` depends on ``r_load.value``, so perturbing that
#: value can falsify the assertion.  Must read ``clean``.
_CIRCUIT_COUPLED = """\
component Resistor:
    value: resistance
    power_rating: power

module Load:
    v_rail: voltage = 100V
    r_load = new Resistor
    r_load.value = 1kohm
    r_load.power_rating = 25W
    p_load: power = v_rail * v_rail / r_load.value
    assert r_load.power_rating >= p_load * 2
"""

#: The ``PowerInput`` shape: a datasheet rating compared against a declared
#: spec constant.  Nothing the circuit does can falsify it.
_RATING_VS_DECLARED = """\
component Fuse:
    current_rating: current

module Mains:
    i_declared: current = 15A
    fuse = new Fuse
    fuse.current_rating = 16A
    assert fuse.current_rating >= i_declared
"""

#: The ``main.ato:494-495`` shape: the declared value sits exactly on the
#: upper end of the band the assertion claims to constrain it inside.
_TIE_MARGIN = """\
module Budget:
    p_output_max: power = 1800W
    assert p_output_max within 1500W to 1800W
"""

#: A ``within`` band whose value IS circuit-derived but lands exactly on the
#: upper endpoint. Isolates TIE_MARGIN: the assertion is circuit-coupled, so
#: NO_CIRCUIT_COUPLING does not also fire and the flip is unambiguous.
_TIE_MARGIN_CIRCUIT_COUPLED = """\
component Resistor:
    value: resistance

module Load:
    v_rail: voltage = 100V
    r_load = new Resistor
    r_load.value = 1kohm
    p_load: power = v_rail * v_rail / r_load.value
    assert p_load within 5W to 10W
"""

#: A second sound assertion, this one leaning on a capacitor's ``.value``.
#: It exists to make the CIRCUIT_ATTRS table observable: if ``value`` stops
#: counting as circuit-determining, this stops being classifiable at all and
#: the gate must refuse rather than silently re-label it.
_CIRCUIT_VALUE_CLASSIFIED = """\
component Capacitor:
    value: capacitance
    voltage_rating: voltage

module Tank:
    i_ripple: current = 2A
    f_sw: frequency = 50kHz
    c_tank = new Capacitor
    c_tank.value = 470nF
    c_tank.voltage_rating = 1000V
    v_ripple: voltage = i_ripple / (f_sw * c_tank.value)
    assert c_tank.voltage_rating >= v_ripple * 2
"""

#: Sources exist but declare no assertions at all. Isolates the assertion
#: floor from the file floor.
_NO_ASSERTIONS = """\
module Empty:
    v_rail: voltage = 12V
"""

#: A component attribute the gate's classification tables do not know.  The
#: gate must refuse rather than guess whether it describes a datasheet limit
#: or a circuit-determining property.
_UNCLASSIFIED_ATTR = """\
component Widget:
    exotic_limit: voltage

module Board:
    w = new Widget
    w.exotic_limit = 5V
    assert w.exotic_limit >= 1V
"""


def _state(gate_module, sources: dict[str, str], **kwargs) -> str:
    """Run the gate over a synthetic ``.ato`` tree and normalise the verdict."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "elec" / "src"
        src.mkdir(parents=True)
        for name, text in sources.items():
            (src / name).write_text(text, encoding="utf-8")
        try:
            findings, _stats = gate_module.find_violations(src, root, **kwargs)
        except Exception:
            # Any refusal -- GateError, UnitError, ParseError -- normalises to
            # "error" so the mutation runner never has to know each gate's
            # own exception type.
            return "error"
        ledgered = [f for f in findings if f.kind in gate_module.LEDGERED_KINDS]
        return "violation" if ledgered else "clean"


def _small(gate_module, sources: dict[str, str]) -> str:
    """Analyse a fixture too small to clear the production anti-vacuity floors."""
    return _state(gate_module, sources, min_files=1, min_assertions=1)


def pristine_circuit_coupled(gate_module) -> str:
    """A sound assertion: the gate must NOT flag it."""
    return _small(gate_module, {"design.ato": _CIRCUIT_COUPLED})


def seed_rating_vs_declared(gate_module) -> str:
    """The PowerInput class. The gate must flag it."""
    return _small(gate_module, {"design.ato": _RATING_VS_DECLARED})


def seed_tie_margin(gate_module) -> str:
    """The main.ato:494-495 class. The gate must flag it."""
    return _small(gate_module, {"design.ato": _TIE_MARGIN})


def seed_unclassified_attribute(gate_module) -> str:
    """An attribute the tables do not cover. The gate must ERROR, not guess."""
    return _small(gate_module, {"design.ato": _UNCLASSIFIED_ATTR})


def seed_tie_margin_only(gate_module) -> str:
    """A circuit-coupled assertion pinned to its own endpoint: TIE_MARGIN alone."""
    return _small(gate_module, {"design.ato": _TIE_MARGIN_CIRCUIT_COUPLED})


def seed_circuit_value_classification(gate_module) -> str:
    """A sound, ``.value``-driven assertion. Clean only while the table knows it."""
    return _small(gate_module, {"design.ato": _CIRCUIT_VALUE_CLASSIFIED})


def seed_scope_evaporated(gate_module) -> str:
    """No .ato sources at all. A scan that finds nothing must not pass.

    ``min_assertions=0`` isolates the *file* floor so that stripping it alone
    is observable; otherwise the assertion floor would mask the flip.
    """
    return _state(gate_module, {}, min_files=1, min_assertions=0)


def seed_no_assertions(gate_module) -> str:
    """Sources present but assertion-free. Isolates the *assertion* floor."""
    return _state(
        gate_module, {"design.ato": _NO_ASSERTIONS}, min_files=1, min_assertions=1
    )
