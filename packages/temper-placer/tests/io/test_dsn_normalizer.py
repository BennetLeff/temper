from temper_placer.io.dsn_normalizer import DSNNormalizer


def test_normalize_strips_non_semantic_lines():
    dsn = (
        ";exported-at: 2026-06-22T10:00:00\n"
        ";tool-version: temper-placer 1.2.3\n"
        "(pcb test (unit mm))\n"
    )
    result = DSNNormalizer.normalize(dsn)
    assert ";exported-at" not in result
    assert ";tool-version" not in result
    assert "(pcb test (unit mm))" in result


def test_normalize_preserves_schema_version_line():
    dsn = (
        ";schema-version: sha256:abc123def456\n"
        "(pcb test (unit mm))\n"
    )
    result = DSNNormalizer.normalize(dsn)
    assert ";schema-version: sha256:abc123def456" in result
    assert "(pcb test (unit mm))" in result


def test_normalize_strips_machine_and_path_lines():
    dsn = (
        ";machine: macbook-pro\n"
        ";path: /tmp/output.dsn\n"
        "(pcb test (unit mm))\n"
    )
    result = DSNNormalizer.normalize(dsn)
    assert ";machine:" not in result
    assert ";path:" not in result


def test_normalize_ensures_single_trailing_newline():
    dsn = "(pcb test (unit mm))\n\n\n"
    result = DSNNormalizer.normalize(dsn)
    assert result.endswith("\n")
    assert not result.endswith("\n\n")


def test_normalize_strips_trailing_whitespace():
    dsn = "(pcb test (unit mm))   \n"
    result = DSNNormalizer.normalize(dsn)
    lines = result.split("\n")
    assert lines[0] == "(pcb test (unit mm))"


def test_is_normalized_rejects_bare_non_semantic():
    dsn = ";exported-at: 2026-06-22\n(pcb test)\n"
    assert not DSNNormalizer.is_normalized(dsn)


def test_is_normalized_accepts_clean_dsn():
    dsn = ";schema-version: sha256:abc123\n(pcb test)\n"
    assert DSNNormalizer.is_normalized(dsn)


def test_is_normalized_rejects_control_characters():
    dsn = "\x00(pcb test)\n"
    assert not DSNNormalizer.is_normalized(dsn)


def test_normalize_empty_input():
    result = DSNNormalizer.normalize("")
    assert result in ("\n", "")


def test_normalize_only_non_semantic_lines():
    dsn = ";exported-at: now\n;tool-version: v1\n"
    result = DSNNormalizer.normalize(dsn)
    assert result in ("\n", "")
