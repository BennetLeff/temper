from temper_placer.io.dsn_normalizer import DSNNormalizer


def test_normalize_strips_non_semantic_lines():
    dsn = """\
;exported-at: 2026-06-22T10:00:00
;tool-version: temper-placer 1.2.3
;machine: macos-arm64
;path: /tmp/output.dsn
(pcb test
  (structure (layer F.Cu (type signal)))
)
"""
    result = DSNNormalizer.normalize(dsn)
    assert ";exported-at:" not in result
    assert ";tool-version:" not in result
    assert ";machine:" not in result
    assert ";path:" not in result
    assert "(pcb test" in result
    assert result.endswith("\n")


def test_normalize_preserves_schema_version():
    dsn = """\
;schema-version: sha256:abc123def4567890abcdef1234567890abcdef1234567890abcdef12345678
;exported-at: 2026-06-22T10:00:00
(pcb test (unit mm))
"""
    result = DSNNormalizer.normalize(dsn)
    assert ";schema-version: sha256:" in result
    assert ";exported-at:" not in result


def test_normalize_trailing_whitespace():
    dsn = """(pcb test
  (unit mm)
)
"""
    result = DSNNormalizer.normalize(dsn)
    assert "   " not in result
    assert result.endswith("\n")
    assert not result.endswith("\n\n")


def test_normalize_single_trailing_newline():
    dsn = "(pcb test)\n\n\n"
    result = DSNNormalizer.normalize(dsn)
    assert result == "(pcb test)\n"


def test_is_normalized_clean():
    dsn = "(pcb test)\n"
    assert DSNNormalizer.is_normalized(dsn)


def test_is_normalized_rejects_noise():
    dsn = ";exported-at: now\n(pcb test)\n"
    assert not DSNNormalizer.is_normalized(dsn)


def test_is_normalized_rejects_double_newline():
    dsn = "(pcb test)\n\n"
    assert not DSNNormalizer.is_normalized(dsn)


def test_is_normalized_rejects_no_trailing_newline():
    dsn = "(pcb test)"
    assert not DSNNormalizer.is_normalized(dsn)


def test_strip_control_chars():
    dsn = "(pcb\x00 test)\n"
    result = DSNNormalizer.strip_control_chars(dsn)
    assert "\x00" not in result
    assert "(pcb test)" in result
