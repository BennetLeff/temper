import pytest
from temper_placer.io.dsn_validator import DSNVersionValidator, DSNVersionMismatchError


def test_validate_passes_on_match():
    dsn = ";schema-version: sha256:abc123\n(pcb test)\n"
    DSNVersionValidator.validate(dsn, "abc123")


def test_validate_raises_on_mismatch():
    dsn = ";schema-version: sha256:abc123\n(pcb test)\n"
    with pytest.raises(DSNVersionMismatchError) as exc:
        DSNVersionValidator.validate(dsn, "def456")
    assert "expected sha256:def456" in str(exc.value)
    assert "got sha256:abc123" in str(exc.value)


def test_validate_raises_on_missing_header():
    dsn = "(pcb test)\n"
    with pytest.raises(DSNVersionMismatchError) as exc:
        DSNVersionValidator.validate(dsn, "abc123")
    assert "got sha256:MISSING" in str(exc.value)


def test_validate_or_warn_returns_true_on_match():
    dsn = ";schema-version: sha256:abc123\n(pcb test)\n"
    assert DSNVersionValidator.validate_or_warn(dsn, "abc123") is True


def test_validate_or_warn_returns_false_on_mismatch():
    dsn = ";schema-version: sha256:abc123\n(pcb test)\n"
    assert DSNVersionValidator.validate_or_warn(dsn, "def456") is False


def test_validate_or_warn_returns_false_on_missing():
    dsn = "(pcb test)\n"
    assert DSNVersionValidator.validate_or_warn(dsn, "abc123") is False


def test_error_fields():
    err = DSNVersionMismatchError("abc", "def")
    assert err.expected == "abc"
    assert err.received == "def"


def test_error_fields_none_received():
    err = DSNVersionMismatchError("abc", None)
    assert err.expected == "abc"
    assert err.received is None
