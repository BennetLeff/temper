import pytest
from temper_placer.io.dsn_validator import DSNVersionValidator, DSNVersionMismatchError


def test_validate_passes_when_hash_matches():
    dsn = ";schema-version: sha256:abc123\n(pcb test (unit mm))\n"
    DSNVersionValidator.validate(dsn, "abc123")


def test_validate_raises_when_hash_differs():
    dsn = ";schema-version: sha256:abc123\n(pcb test (unit mm))\n"
    with pytest.raises(DSNVersionMismatchError) as exc:
        DSNVersionValidator.validate(dsn, "xyz789")
    assert "expected sha256:xyz789" in str(exc.value)
    assert "got sha256:abc123" in str(exc.value)


def test_validate_raises_when_header_missing():
    dsn = "(pcb test (unit mm))\n"
    with pytest.raises(DSNVersionMismatchError) as exc:
        DSNVersionValidator.validate(dsn, "abc123")
    assert "MISSING" in str(exc.value)


def test_error_message_contains_both_hashes():
    try:
        DSNVersionValidator.validate(
            ";schema-version: sha256:rechash\n(pcb test)\n",
            "exphash"
        )
    except DSNVersionMismatchError as e:
        assert e.expected == "exphash"
        assert e.received == "rechash"
        assert "expected sha256:exphash" in str(e)
        assert "got sha256:rechash" in str(e)


def test_validate_or_warn_returns_true_on_match():
    dsn = ";schema-version: sha256:abc123\n(pcb test (unit mm))\n"
    assert DSNVersionValidator.validate_or_warn(dsn, "abc123") is True


def test_validate_or_warn_returns_false_on_mismatch():
    dsn = ";schema-version: sha256:wrong\n(pcb test (unit mm))\n"
    assert DSNVersionValidator.validate_or_warn(dsn, "correct") is False


def test_validate_or_warn_returns_false_on_missing():
    dsn = "(pcb test (unit mm))\n"
    assert DSNVersionValidator.validate_or_warn(dsn, "abc123") is False
