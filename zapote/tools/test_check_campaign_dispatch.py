"""Tests for the campaign dispatch/handback admission checks."""
import datetime as dt
import json
import os
import pathlib
import stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import check_campaign_dispatch as gate  # noqa: E402

NOW = dt.datetime(2026, 9, 17, 12, 0, tzinfo=dt.timezone.utc)


def write_dispatch(
    directory: pathlib.Path,
    deadline: str,
    issued: dt.datetime | None = None,
    **overrides: object,
) -> pathlib.Path:
    payload = {
        "campaign_id": "c",
        "task_id": "T",
        "attempt_id": "attempt-001",
        "absolute_deadline_utc": deadline,
        "allowed_output_directory": str(directory),
        "checkout_path": "zapote",
        "source_revision": "deadbeef",
        "model_revision_and_sha256": "not_applicable: source-only",
        "checker_revision_and_sha256": "not_applicable: no checker issued",
        "contract_path_and_sha256": "contract.json abc",
        "exact_build_or_run_commands": "none",
    }
    payload.update(overrides)
    path = directory / "dispatch.json"
    path.write_text(json.dumps(payload))
    if issued is not None:
        stamp = issued.timestamp()
        import os

        os.utime(path, (stamp, stamp))
    return path


def test_future_deadline_is_admitted(tmp_path: pathlib.Path) -> None:
    path = write_dispatch(tmp_path, "2026-09-17T18:00:00Z", issued=NOW)
    assert gate.check_dispatch(path, NOW) == []


def test_expired_dispatch_is_rejected(tmp_path: pathlib.Path) -> None:
    # packet issued after its own deadline: the AR-ACTIVE failure
    issued = dt.datetime(2026, 9, 17, 13, 0, tzinfo=dt.timezone.utc)
    path = write_dispatch(tmp_path, "2026-09-17T12:30:00Z", issued=issued)
    failures = gate.check_dispatch(path, NOW)
    assert any("expired dispatch" in f for f in failures), failures


def test_deadline_not_after_now_is_rejected(tmp_path: pathlib.Path) -> None:
    path = write_dispatch(tmp_path, "2026-09-17T11:00:00Z", issued=dt.datetime(2026, 9, 17, 10, 0, tzinfo=dt.timezone.utc))
    failures = gate.check_dispatch(path, NOW)
    assert any("after now" in f for f in failures), failures


def test_missing_field_is_rejected(tmp_path: pathlib.Path) -> None:
    path = write_dispatch(tmp_path, "2026-09-17T18:00:00Z", issued=NOW, source_revision="")
    failures = gate.check_dispatch(path, NOW)
    assert any("source_revision" in f for f in failures), failures


def test_unparseable_deadline_is_rejected(tmp_path: pathlib.Path) -> None:
    path = write_dispatch(tmp_path, "tomorrow-ish", issued=NOW)
    failures = gate.check_dispatch(path, NOW)
    assert any("not a parseable" in f for f in failures), failures


def _handback(tmp_path: pathlib.Path, checker_field: str, receipt: object) -> pathlib.Path:
    write_dispatch(tmp_path, "2026-09-17T18:00:00Z", issued=NOW, checker_revision_and_sha256=checker_field)
    (tmp_path / "result.json").write_text(json.dumps({"checker_receipt": receipt}))
    return tmp_path


def test_handback_without_checker_is_not_a_validated_run(tmp_path: pathlib.Path) -> None:
    attempt = _handback(tmp_path, "not_applicable: no checker issued", None)
    failures, counted = gate.check_handback(attempt)
    assert failures == []
    assert counted is False


def test_handback_with_receipt_is_counted(tmp_path: pathlib.Path) -> None:
    attempt = _handback(tmp_path, "checker.rs abcd", {"status": "pass"})
    failures, counted = gate.check_handback(attempt)
    assert failures == []
    assert counted is True


def test_a_receipt_that_does_not_report_a_pass_is_not_counted(tmp_path: pathlib.Path) -> None:
    # a non-null receipt of any shape used to count as a validated run
    attempt = _handback(tmp_path, "checker.rs abcd", {"status": "fail", "detail": "unexplained"})
    failures, counted = gate.check_handback(attempt)
    assert counted is False
    assert any("does not report a pass" in f for f in failures), failures


def test_a_receipt_with_no_status_is_not_counted(tmp_path: pathlib.Path) -> None:
    attempt = _handback(tmp_path, "checker.rs abcd", {"note": "looks fine"})
    failures, counted = gate.check_handback(attempt)
    assert counted is False
    assert any("does not report a pass" in f for f in failures), failures


def test_a_receipt_with_passed_true_is_counted(tmp_path: pathlib.Path) -> None:
    attempt = _handback(tmp_path, "checker.rs abcd", {"passed": True})
    failures, counted = gate.check_handback(attempt)
    assert failures == []
    assert counted is True


def test_declared_checker_without_receipt_is_a_failure(tmp_path: pathlib.Path) -> None:
    attempt = _handback(tmp_path, "checker.rs abcd", None)
    failures, counted = gate.check_handback(attempt)
    assert any("no checker receipt" in f for f in failures), failures
    assert counted is False


def test_missing_result_is_a_failure(tmp_path: pathlib.Path) -> None:
    write_dispatch(tmp_path, "2026-09-17T18:00:00Z", issued=NOW)
    failures, counted = gate.check_handback(tmp_path)
    assert any("result.json" in f for f in failures), failures
    assert counted is False


# --- evidence-ledger admission for electrical-model attempts ---

def _model_attempt(tmp_path: pathlib.Path, kind: str, ledger: bool, body: str = "{}") -> pathlib.Path:
    write_dispatch(tmp_path, "2026-09-17T18:00:00Z", issued=NOW, kind=kind)
    (tmp_path / "result.json").write_text(json.dumps({"checker_receipt": None}))
    if ledger:
        (tmp_path / "claims.json").write_text(body)
    return tmp_path


def test_a_model_attempt_without_a_ledger_is_rejected(tmp_path: pathlib.Path) -> None:
    attempt = _model_attempt(tmp_path, "fault_assessment", ledger=False)
    failures, _ = gate.check_handback(attempt)
    assert any("required evidence ledger missing" in f for f in failures), failures


def test_a_non_model_attempt_owes_no_ledger(tmp_path: pathlib.Path) -> None:
    attempt = _model_attempt(tmp_path, "source_research", ledger=False)
    failures, _ = gate.check_handback(attempt)
    assert not any("evidence ledger" in f for f in failures), failures


def test_a_failing_ledger_rejects_the_handback(tmp_path: pathlib.Path) -> None:
    stub = make_stub(tmp_path, 'echo "VIOLATIONS DETECTED"\nexit 1\n')
    attempt = _model_attempt(tmp_path, "engineering_design", ledger=True)
    old = os.environ.get("ZAPOTE_CLAIMS_BIN")
    os.environ["ZAPOTE_CLAIMS_BIN"] = str(stub)
    try:
        failures, _ = gate.check_handback(attempt)
    finally:
        if old is None:
            os.environ.pop("ZAPOTE_CLAIMS_BIN", None)
        else:
            os.environ["ZAPOTE_CLAIMS_BIN"] = old
    assert any("evidence ledger failed its checks" in f for f in failures), failures


def test_a_passing_ledger_does_not_block_the_handback(tmp_path: pathlib.Path) -> None:
    stub = make_stub(tmp_path, 'echo "No violations detected"\nexit 0\n')
    attempt = _model_attempt(tmp_path, "engineering_design", ledger=True)
    old = os.environ.get("ZAPOTE_CLAIMS_BIN")
    os.environ["ZAPOTE_CLAIMS_BIN"] = str(stub)
    try:
        failures, _ = gate.check_handback(attempt)
    finally:
        if old is None:
            os.environ.pop("ZAPOTE_CLAIMS_BIN", None)
        else:
            os.environ["ZAPOTE_CLAIMS_BIN"] = old
    assert not any("evidence ledger" in f for f in failures), failures


def make_stub(directory: pathlib.Path, body: str) -> pathlib.Path:
    stub = directory / "zapote-claims"
    stub.write_text("#!/bin/sh\n" + body)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub

