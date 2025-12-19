# Temper Requirements System

This directory contains domain-specific requirements documents for the Temper project.

## Files

| File | Domain | ID Prefix | Description |
|------|--------|-----------|-------------|
| `REQUIREMENTS.md` (root) | Hardware/System | REQ-SYS, REQ-PWR, REQ-THERMAL | System-level hardware requirements |
| `FIRMWARE_REQUIREMENTS.md` | Firmware | REQ-FW-* | ESP32-S3 firmware requirements |
| `PLACER_REQUIREMENTS.md` | PCB Placer | REQ-PLACER-* | temper-placer optimizer requirements |

## Requirement ID Format

```
REQ-<DOMAIN>-<SUBSYSTEM>-<NUMBER>
```

### Examples

| ID | Domain | Subsystem | Description |
|----|--------|-----------|-------------|
| `REQ-SYS-01` | System | General | System-level requirement |
| `REQ-PWR-02` | Power | General | Power system requirement |
| `REQ-FW-SM-01` | Firmware | State Machine | Firmware state machine requirement |
| `REQ-FW-CTRL-02` | Firmware | Control | Firmware control loop requirement |
| `REQ-PLACER-OPT-01` | Placer | Optimizer | Placer optimization requirement |
| `REQ-PLACER-HEUR-03` | Placer | Heuristics | Placer heuristics requirement |

## Status Values

| Status | Description |
|--------|-------------|
| `NOT_STARTED` | Requirement defined but no work begun |
| `IN_PROGRESS` | Implementation or verification underway |
| `VERIFIED` | Validation complete, requirement met |
| `BLOCKED` | Cannot proceed (see linked issues) |
| `DEFERRED` | Postponed to future release |

## Linking to bd Issues

### Adding `req:` Labels

Use `req:REQ-XXX` labels on bd issues to link requirements to work items:

```bash
# When creating an issue
bd create "Implement PID stability" --label req:REQ-FW-CTRL-01 -t task -p 1

# When updating an existing issue
bd update temper-xxx --label req:REQ-FW-CTRL-01
```

### Finding Issues by Requirement

```bash
# Find all issues linked to a requirement
bd list --label-any req:REQ-FW-CTRL-01 --json

# Find all issues for firmware requirements
bd list --label-any "req:REQ-FW" --json
```

## Requirement Document Structure

Each requirements document should include:

1. **Header** - Version, date, status, domain
2. **Sections by Subsystem** - Grouped requirements
3. **Each Requirement** - ID, priority, status, description, validation method
4. **Traceability Matrix** - Links to tests, simulations, bd issues

### Requirement Template

```markdown
### REQ-<DOMAIN>-<SUBSYSTEM>-<NN>: <Short Title>
**Priority:** P0 | P1 | P2 | P3
**Status:** NOT_STARTED | IN_PROGRESS | VERIFIED | BLOCKED | DEFERRED

<Detailed description of the requirement>

| Parameter | Value |
|-----------|-------|
| Key spec | Value |

**Validation:** <How to verify this requirement>
**Linked Issues:** <bd issue IDs or "none">
```

## GPBM Integration

The GPBM workflow uses requirements for:

1. **GATHER Phase** - Query requirements to understand scope
2. **PLAN Phase** - Create issues with `req:` labels
3. **MEASURE Phase** - Track `req_verified_pct` metrics

### Requirements Parser

```bash
# Check requirement coverage
python3 tools/gpbm/requirements_parser.py --status

# Find unlinked requirements
python3 tools/gpbm/requirements_parser.py --unlinked

# Export requirements as JSON
python3 tools/gpbm/requirements_parser.py --json > requirements.json
```

## Priority Definitions

| Priority | Description | Verification Required |
|----------|-------------|----------------------|
| P0 | Critical - Must ship | 100% verified |
| P1 | High - Core functionality | 100% verified |
| P2 | Medium - Important but not blocking | Best effort |
| P3 | Low - Nice to have | Optional |

## Cross-References

- **Main hardware requirements**: See `REQUIREMENTS.md` in project root
- **Firmware implementation**: See `firmware/README.md`
- **Placer implementation**: See `temper-placer/README.md` and `TEMPER_PLACER_DESIGN.md`
- **Metrics system**: See `metrics/METRICS.md`
