
import json

from runbook import (
    EXPECTED_EVIDENCE,
    build_runbook,
    generate_reports,
    inspect_evidence,
)


def test_evidence_inventory_detects_existing_files(tmp_path, monkeypatch):
    import runbook

    files = []

    for index in range(2):
        path = tmp_path / f"evidence_{index}.json"
        path.write_text('{"valid": true}', encoding="utf-8")
        files.append(path)

    monkeypatch.setattr(runbook, "EXPECTED_EVIDENCE", files)
    monkeypatch.setattr(runbook, "BASE_DIR", tmp_path)

    report = runbook.inspect_evidence()

    assert report["expected_count"] == 2
    assert report["found_count"] == 2
    assert report["valid_json_count"] == 2
    assert report["complete"] is True


def test_evidence_inventory_detects_missing_file(tmp_path, monkeypatch):
    import runbook

    existing = tmp_path / "existing.json"
    existing.write_text('{"ok": true}', encoding="utf-8")

    missing = tmp_path / "missing.json"

    monkeypatch.setattr(
        runbook,
        "EXPECTED_EVIDENCE",
        [existing, missing],
    )
    monkeypatch.setattr(runbook, "BASE_DIR", tmp_path)

    report = runbook.inspect_evidence()

    assert report["found_count"] == 1
    assert report["complete"] is False


def test_evidence_inventory_detects_invalid_json(tmp_path, monkeypatch):
    import runbook

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{invalid json", encoding="utf-8")

    monkeypatch.setattr(
        runbook,
        "EXPECTED_EVIDENCE",
        [invalid],
    )
    monkeypatch.setattr(runbook, "BASE_DIR", tmp_path)

    report = runbook.inspect_evidence()

    assert report["found_count"] == 1
    assert report["valid_json_count"] == 0
    assert report["files"][0]["error"] == "JSONDecodeError"
    assert report["complete"] is False


def test_runbook_contains_execution_instructions():
    content = build_runbook()

    assert "python conditional_router.py" in content
    assert "python conditional_reliability.py" in content
    assert "python -m pytest -v" in content


def test_runbook_documents_failure_recovery():
    content = build_runbook()

    assert "Transient errors" in content
    assert "Permanent failure" in content
    assert "Malformed response" in content
    assert "Retry exhaustion" in content


def test_runbook_documents_idempotency_and_replay_safety():
    content = build_runbook()

    assert "Idempotency" in content
    assert "duplicate side effect" in content


def test_runbook_documents_operator_states():
    content = build_runbook()

    assert "created" in content
    assert "running" in content
    assert "waiting" in content
    assert "completed" in content
    assert "needs_review" in content


def test_report_generation_creates_all_documents(tmp_path, monkeypatch):
    import runbook

    monkeypatch.setattr(runbook, "BASE_DIR", tmp_path)
    monkeypatch.setattr(runbook, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(runbook, "TRACE_DIR", tmp_path / "traces")
    monkeypatch.setattr(runbook, "REPORT_DIR", tmp_path / "reports")

    runbook.OUTPUT_DIR.mkdir()
    runbook.TRACE_DIR.mkdir()
    runbook.REPORT_DIR.mkdir()

    monkeypatch.setattr(
    runbook,
    "EXPECTED_EVIDENCE",
    [
        runbook.OUTPUT_DIR / "task1_workflow_contract.json",
        runbook.OUTPUT_DIR / "task2_conditional_workflow.json",
        runbook.OUTPUT_DIR / "task3_failure_recovery.json",
        runbook.OUTPUT_DIR / "task4_conditional_observability.json",
        runbook.OUTPUT_DIR / "task4_conditional_measurements.json",
        runbook.TRACE_DIR / "task3_recovery_trace.json",
        runbook.TRACE_DIR / "task4_conditional_observability.json",
    ],
)

    # Create the six Task 2–4 evidence files.
    for path in runbook.EXPECTED_EVIDENCE[1:]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"valid": true}', encoding="utf-8")

    result = runbook.generate_reports()

    assert result["runbook_path"].exists()
    assert result["evidence_path"].exists()
    assert result["output_path"].exists()
    assert result["evidence"]["complete"] is True


def test_report_marks_incomplete_evidence(tmp_path, monkeypatch):
    import runbook

    monkeypatch.setattr(runbook, "BASE_DIR", tmp_path)
    monkeypatch.setattr(runbook, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(runbook, "TRACE_DIR", tmp_path / "traces")
    monkeypatch.setattr(runbook, "REPORT_DIR", tmp_path / "reports")

    runbook.OUTPUT_DIR.mkdir()
    runbook.TRACE_DIR.mkdir()
    runbook.REPORT_DIR.mkdir()

    monkeypatch.setattr(
    runbook,
    "EXPECTED_EVIDENCE",
    [
        runbook.OUTPUT_DIR / "task1_workflow_contract.json",
        runbook.OUTPUT_DIR / "task2_conditional_workflow.json",
        runbook.OUTPUT_DIR / "task3_failure_recovery.json",
        runbook.OUTPUT_DIR / "task4_conditional_observability.json",
        runbook.OUTPUT_DIR / "task4_conditional_measurements.json",
        runbook.TRACE_DIR / "task3_recovery_trace.json",
        runbook.TRACE_DIR / "task4_conditional_observability.json",
    ],
)

    # Deliberately do not create the Task 2–4 evidence files.
    result = runbook.generate_reports()

    assert result["evidence"]["complete"] is False
    assert "Review missing or invalid" in (
        result["evidence_path"].read_text(encoding="utf-8")
    )


def test_generated_task1_evidence_is_valid_json(tmp_path, monkeypatch):
    import runbook

    monkeypatch.setattr(runbook, "BASE_DIR", tmp_path)
    monkeypatch.setattr(runbook, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(runbook, "TRACE_DIR", tmp_path / "traces")
    monkeypatch.setattr(runbook, "REPORT_DIR", tmp_path / "reports")

    runbook.OUTPUT_DIR.mkdir()
    runbook.TRACE_DIR.mkdir()
    runbook.REPORT_DIR.mkdir()

    path = runbook.generate_task1_evidence()

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["run_id"] == "RUN-REFUND-001"
    assert data["state"] == "running"
