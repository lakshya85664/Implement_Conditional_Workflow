
import json

import pytest

from conditional_workflow import RefundRequest
from conditional_adapters import (
    ConditionalWorkflowService,
    FakeRiskAdapter,
    FakeApprovalAdapter,
    redact,
)


def make_refund(amount=2500):
    return RefundRequest(
        refund_id="REFUND-TEST-4001",
        customer_id="CUSTOMER-TEST-4001",
        amount=amount,
        reason="Damaged product",
    )


def make_service(risk_score=0.15, risk_signals=None):
    risk = FakeRiskAdapter(
        risk_score=risk_score,
        risk_signals=risk_signals or [],
    )
    approval = FakeApprovalAdapter()

    service = ConditionalWorkflowService(
        risk_adapter=risk,
        approval_adapter=approval,
    )

    return service, risk, approval


def test_auto_approval_uses_injected_risk_adapter():
    service, risk, approval = make_service()

    result = service.execute(
        "RUN-4001",
        make_refund(),
    )

    assert result["status"] == "completed"
    assert result["route"] == "auto_approval"
    assert risk.calls == 1
    assert approval.calls == []


def test_manager_route_calls_approval_adapter():
    service, risk, approval = make_service(risk_score=0.40)

    result = service.execute(
        "RUN-4002",
        make_refund(),
    )

    assert result["status"] == "waiting"
    assert result["route"] == "manager_approval"
    assert len(approval.calls) == 1
    assert approval.calls[0]["approval_type"] == "manager_approval"


def test_fraud_route_calls_fraud_review_adapter():
    service, risk, approval = make_service(
        risk_score=0.85
    )

    result = service.execute(
        "RUN-4003",
        make_refund(),
    )

    assert result["status"] == "waiting"
    assert result["route"] == "fraud_review"
    assert approval.calls[0]["approval_type"] == "fraud_review"


def test_duplicate_run_is_blocked():
    service, risk, approval = make_service()

    first = service.execute("RUN-4004", make_refund())
    second = service.execute("RUN-4004", make_refund())

    assert first["status"] == "completed"
    assert second["status"] == "duplicate_blocked"
    assert risk.calls == 1


def test_status_function_returns_current_state():
    service, risk, approval = make_service()

    service.execute("RUN-4005", make_refund())

    status = service.get_status("RUN-4005")

    assert status["state"] == "completed"
    assert status["route"] == "auto_approval"


def test_unknown_status_raises_key_error():
    service, risk, approval = make_service()

    with pytest.raises(KeyError, match="Unknown workflow run"):
        service.get_status("UNKNOWN-RUN")


def test_trace_function_filters_by_run_id():
    service, risk, approval = make_service()

    service.execute("RUN-4007A", make_refund())
    service.execute(
        "RUN-4007B",
        RefundRequest(
            refund_id="REFUND-4007B",
            customer_id="CUSTOMER-4007B",
            amount=2500,
            reason="Damaged item",
        ),
    )

    trace = service.get_trace("RUN-4007A")

    assert len(trace) >= 3
    assert all(item["run_id"] == "RUN-4007A" for item in trace)


def test_metrics_count_workflow_and_adapter_calls():
    service, risk, approval = make_service()

    service.execute("RUN-4008", make_refund())

    metrics = service.get_metrics()

    assert metrics["workflow_started"] == 1
    assert metrics["workflow_completed"] == 1
    assert metrics["adapter_calls"] == 1
    assert metrics["adapter_failures"] == 0
    assert metrics["duration_count"] == 1


def test_approval_adapter_call_is_counted():
    service, risk, approval = make_service(risk_score=0.40)

    service.execute("RUN-4009", make_refund())

    metrics = service.get_metrics()

    assert metrics["adapter_calls"] == 2
    assert metrics["workflow_waiting"] == 1


def test_secret_values_are_redacted_recursively():
    data = {
        "api_key": "secret-value",
        "nested": {
            "password": "password-value",
            "message": "safe",
        },
        "items": [
            {"token": "token-value"}
        ],
    }

    cleaned = redact(data)

    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["password"] == "[REDACTED]"
    assert cleaned["nested"]["message"] == "safe"
    assert cleaned["items"][0]["token"] == "[REDACTED]"


def test_adapter_secrets_do_not_appear_in_trace():
    service, risk, approval = make_service()

    service.execute("RUN-4010", make_refund())

    serialized = json.dumps(service.get_trace())

    assert "fake-risk-secret" not in serialized
    assert "fake-approval-secret" not in serialized


def test_invalid_risk_response_is_captured_for_review():
    risk = FakeRiskAdapter(risk_score=2.0)
    approval = FakeApprovalAdapter()

    service = ConditionalWorkflowService(
        risk_adapter=risk,
        approval_adapter=approval,
    )

    result = service.execute(
        "RUN-4011",
        make_refund(),
    )

    assert result["status"] == "needs_review"
    assert result["state"] == "needs_review"
    assert result["next_action"] == "operator_investigation"


def test_risk_adapter_failure_is_observable():
    class BrokenRiskAdapter:
        def assess(self, refund):
            raise TimeoutError("Simulated dependency timeout")

    service = ConditionalWorkflowService(
        risk_adapter=BrokenRiskAdapter(),
        approval_adapter=FakeApprovalAdapter(),
    )

    result = service.execute(
        "RUN-4012",
        make_refund(),
    )

    metrics = service.get_metrics()

    assert result["status"] == "needs_review"
    assert result["error_type"] == "TimeoutError"
    assert metrics["adapter_failures"] == 1
    assert metrics["workflow_failed"] == 1


def test_evidence_files_are_generated(tmp_path, monkeypatch):
    import conditional_adapters

    monkeypatch.setattr(
        conditional_adapters,
        "TRACE_DIR",
        tmp_path / "traces",
    )
    monkeypatch.setattr(
        conditional_adapters,
        "OUTPUT_DIR",
        tmp_path / "outputs",
    )

    conditional_adapters.TRACE_DIR.mkdir()
    conditional_adapters.OUTPUT_DIR.mkdir()

    service, risk, approval = make_service()
    service.execute("RUN-4013", make_refund())

    trace_path, metrics_path = service.save_evidence()

    assert trace_path.exists()
    assert metrics_path.exists()

    trace_data = json.loads(trace_path.read_text(encoding="utf-8"))
    metrics_data = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert len(trace_data) >= 3
    assert metrics_data["workflow_completed"] == 1
