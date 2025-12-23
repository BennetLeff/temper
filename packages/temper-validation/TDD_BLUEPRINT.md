# TDD Blueprint for temper-validation Package

## Overview

This document tracks Test-Driven Development progress for the temper-validation package.

## TDD Cycle for Each Module

1. **Write failing tests (RED)** → Create test file with expected behavior
2. **Run pytest** → Verify tests fail
3. **Implement code** → Write minimum code to pass tests
4. **Run pytest** → Verify tests pass (GREEN)
5. **Refactor** → Clean up implementation
6. **Repeat** → Next test case

## Progress Tracking

### Module 1: Wirelength Comparison (temper-1mmr.2)

| Task | ID | Status | Date |
|------|-----|--------|------|
| Write tests (RED) | temper-1mmr.2.1 | ✅ Done | 2025-12-23 |
| Implement (GREEN) | temper-1mmr.2.2 | 🔴 TODO | - |
| Refactor | - | ⚪ Pending | - |

**Test file**: `tests/comparison/test_wirelength.py`
**Implementation**: `src/temper_validation/comparison/wirelength.py`

**Tests written** (5 tests):
- ✅ test_manhattan_wirelength_simple
- ✅ test_manhattan_wirelength_multi_net  
- ✅ test_compare_wirelength_ratio
- ✅ test_compare_wirelength_verdict
- ✅ test_steiner_tree_approximation

**Test status**: ⚠️ Not runnable (pytest not installed, module not implemented)

### Module 2: DRC Compliance (temper-1mmr.3)

| Task | ID | Status | Date |
|------|-----|--------|------|
| Write tests (RED) | temper-1mmr.3.1 | 🔴 TODO | - |
| Implement (GREEN) | temper-1mmr.3.2 | 🔴 TODO | - |

**Test file**: `tests/comparison/test_drc_compliance.py`
**Implementation**: `src/temper_validation/comparison/drc_compliance.py`

### Module 3: Stress Test Runner (temper-8ggu.2)

| Task | ID | Status | Date |
|------|-----|--------|------|
| Write tests (RED) | temper-8ggu.2.1 | 🔴 TODO | - |
| Implement (GREEN) | temper-8ggu.2.2 | 🔴 TODO | - |

**Test file**: `tests/test_stress_runner.py`
**Implementation**: `src/temper_stress/runner.py`

### Module 4: Database Schema (temper-j84e.1)

| Task | ID | Status | Date |
|------|-----|--------|------|
| Write tests (RED) | temper-j84e.1.1 | 🔴 TODO | - |
| Implement (GREEN) | temper-j84e.1.2 | 🔴 TODO | - |

**Test file**: `tests/storage/test_database.py`
**Implementation**: `src/temper_benchmark/storage/database.py`

## TDD Task Pattern

All TDD tasks follow this naming convention:
- **RED tasks**: `{parent}.1` - Write failing tests
- **GREEN tasks**: `{parent}.2` - Implement to pass tests

## Current State

**Package structure**: ✅ Created
```
packages/temper-validation/
├── pyproject.toml
├── src/temper_validation/
│   ├── comparison/
│   ├── metrics/
│   └── reporting/
└── tests/
    ├── comparison/
    │   └── test_wirelength.py  ← 5 tests written
    └── fixtures/
```

**Progress by module**:
- Wirelength: 50% (tests written, implementation pending)
- DRC Compliance: 0% (tests not written)
- Stress Runner: 0% (tests not written)
- Database: 0% (tests not written)

**Overall progress**: 12.5% (1 of 8 modules at test-writing stage)

## Next Steps

1. Implement `wirelength.py` to pass wirelength tests
2. Write DRC compliance tests (temper-1mmr.3.1)
3. Write stress runner tests (temper-8ggu.2.1)
4. Write database schema tests (temper-j84e.1.1)

## Command Reference

```bash
# Run specific test file
pytest tests/comparison/test_wirelength.py -v

# Run all tests for module
pytest tests/comparison/ -v

# Run with coverage
pytest --cov=temper_validation tests/

# See which tests fail
pytest tests/comparison/test_wirelength.py -v 2>&1 | grep FAILED
```
