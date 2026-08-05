"""``temper-placer trace`` — query and analyze placement decision traces.

Wave-4 Phase-5 delegation shim: the decision-trace filtering compute of the
``why`` and ``why_not`` commands — the subject filter and the nested
alternative scan — is implemented in Rust in the ``temper-orchestration``
crate (``temper_orchestration.filter_decisions`` /
``temper_orchestration.find_rejected_alternative``), pinned bit-identically
by ``tests/cli/test_trace_commands_rust_differential.py`` against the
VERBATIM pre-migration oracle ``tests/cli/_trace_commands_py_oracle.py``.
The click surface (flags, help, exit codes, output text) stays Python, and
the comparisons that decide the filters stay Python value semantics — the
Rust side calls back into Python for each leaf comparison (``dict.get``,
``str()``, ``==``), so ``d.get("subject") == subject`` and
``str(alt.get("value")) == value`` behave exactly as before, including the
``AttributeError``/``TypeError`` failure modes.

The ``report`` command stays entirely Python: it reconstructs
``Decision``/``DecisionTrace`` objects (a ``temper_placer.core`` surface)
and calls ``generate_markdown_report`` (a ``temper_placer.pipeline``
surface) — both owned by other slices; there is no standalone compute here
to migrate.
"""

from __future__ import annotations

import json

import click
import temper_orchestration as _to


@click.group()
def trace():
    """Query and analyze placement decision traces."""
    pass


@trace.command()
@click.argument("trace_file", type=click.Path(exists=True))
@click.argument("subject")
def why(trace_file: str, subject: str):
    """Explain why a decision was made for a component or net."""
    with open(trace_file) as f:
        data = json.load(f)

    decisions = data.get("decisions", [])
    matches = _to.filter_decisions(decisions, subject)

    if not matches:
        click.echo(f"No decisions found for {subject}")
        return

    click.echo(f"Decisions for {subject}:")
    for i in matches:
        d = decisions[i]
        click.echo(f"- [{d['phase']}] {d['decision_type']}: {d['value']}")
        click.echo(f"  Reason: {d['reason']}")
        if d.get("constraint_refs"):
            click.echo(f"  Constraints: {', '.join(d['constraint_refs'])}")


@trace.command()
@click.argument("trace_file", type=click.Path(exists=True))
@click.argument("subject")
@click.argument("value")
def why_not(trace_file: str, subject: str, value: str):
    """Explain why a particular value wasn't chosen for a subject."""
    with open(trace_file) as f:
        data = json.load(f)

    decisions = data.get("decisions", [])
    hit = _to.find_rejected_alternative(decisions, subject, value)

    if hit is not None:
        di, ai = hit
        alt = decisions[di]["alternatives_considered"][ai]
        click.echo(f"Rejected {value} for {subject}:")
        click.echo(f"Rejection Reason: {alt['rejection_reason']}")
        if alt.get("constraint_violated"):
            click.echo(f"Constraint Violated: {alt['constraint_violated']}")
        return

    click.echo(f"Value {value} was not explicitly considered as an alternative for {subject}")


@trace.command()
@click.argument("trace_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output Markdown file")
def report(trace_file: str, output: str):
    """Generate a Markdown report from a decision trace."""
    from datetime import datetime

    from temper_placer.core.decision import Alternative, Decision, DecisionTrace
    from temper_placer.pipeline.explainability import generate_markdown_report

    with open(trace_file) as f:
        data = json.load(f)

    # Reconstruct objects for report generator
    trace = DecisionTrace(
        run_id=data["run_id"],
        start_time=datetime.fromisoformat(data["start_time"]),
        end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
        final_metrics=data.get("final_metrics", {}),
    )

    for d_data in data.get("decisions", []):
        decision = Decision(
            id=d_data["id"],
            timestamp=datetime.fromisoformat(d_data["timestamp"]),
            phase=d_data["phase"],
            decision_type=d_data["decision_type"],
            subject=d_data["subject"],
            value=d_data["value"],
            reason=d_data["reason"],
            constraint_refs=d_data.get("constraint_refs", []),
            alternatives_considered=[
                Alternative(
                    value=a["value"],
                    rejection_reason=a["rejection_reason"],
                    constraint_violated=a.get("constraint_violated"),
                    loss_if_chosen=a.get("loss_if_chosen"),
                )
                for a in d_data.get("alternatives_considered", [])
            ],
        )
        trace.add_decision(decision)

    report_text = generate_markdown_report(trace)

    if output:
        with open(output, "w") as f:
            f.write(report_text)
        click.echo(f"Report written to {output}")
    else:
        click.echo(report_text)
