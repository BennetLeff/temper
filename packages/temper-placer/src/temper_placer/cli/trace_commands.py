import click
import json
from pathlib import Path

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
        
    decisions = [d for d in data.get("decisions", []) if d.get("subject") == subject]
    
    if not decisions:
        click.echo(f"No decisions found for {subject}")
        return
        
    click.echo(f"Decisions for {subject}:")
    for d in decisions:
        click.echo(f"- [{d['phase']}] {d['decision_type']}: {d['value']}")
        click.echo(f"  Reason: {d['reason']}")
        if d.get('constraint_refs'):
            click.echo(f"  Constraints: {', '.join(d['constraint_refs'])}")

@trace.command()
@click.argument("trace_file", type=click.Path(exists=True))
@click.argument("subject")
@click.argument("value")
def why_not(trace_file: str, subject: str, value: str):
    """Explain why a particular value wasn't chosen for a subject."""
    with open(trace_file) as f:
        data = json.load(f)
        
    decisions = [d for d in data.get("decisions", []) if d.get("subject") == subject]
    
    for d in decisions:
        for alt in d.get("alternatives_considered", []):
            if str(alt.get("value")) == value:
                click.echo(f"Rejected {value} for {subject}:")
                click.echo(f"Rejection Reason: {alt['rejection_reason']}")
                if alt.get('constraint_violated'):
                    click.echo(f"Constraint Violated: {alt['constraint_violated']}")
                return
                
    click.echo(f"Value {value} was not explicitly considered as an alternative for {subject}")

@trace.command()
@click.argument("trace_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output Markdown file")
def report(trace_file: str, output: str):
    """Generate a Markdown report from a decision trace."""
    from temper_placer.core.decision import DecisionTrace, Decision, Alternative
    from temper_placer.pipeline.explainability import generate_markdown_report
    from datetime import datetime
    
    with open(trace_file) as f:
        data = json.load(f)
        
    # Reconstruct objects for report generator
    trace = DecisionTrace(
        run_id=data["run_id"],
        start_time=datetime.fromisoformat(data["start_time"]),
        end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
        final_metrics=data.get("final_metrics", {})
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
                    loss_if_chosen=a.get("loss_if_chosen")
                ) for a in d_data.get("alternatives_considered", [])
            ]
        )
        trace.add_decision(decision)
        
    report_text = generate_markdown_report(trace)
    
    if output:
        with open(output, 'w') as f:
            f.write(report_text)
        click.echo(f"Report written to {output}")
    else:
        click.echo(report_text)
