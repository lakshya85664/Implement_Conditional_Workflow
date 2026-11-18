
import pytest
from pydantic import ValidationError

from conditional_workflow import RefundRequest, WorkflowRun
from conditional_router import decide_route, apply_decision


def make_refund(amount=2500.0):
    return RefundRequest(
        refund_id="REFUND-TEST-001",
        customer_id="CUSTOMER-TEST-001",
        amount=amount,
        reason="Damaged product",
    )


def make_run(state="running"):
    return WorkflowRun(
        run_id="RUN-TEST-001",
        business_key="REFUND-TEST-001",
        state=state,
    )


def test_low_risk_refund_routes_to_auto_approval():
    decision = decide_route(
        make_refund(2500),
        risk_score=0.15,
        risk_signals=[],
    )

    assert decision.route == "auto_approval"


def test_high_amount_routes_to_manager_approval():
    decision = decide_route(
        make_refund(15000),
        risk_score=0.10,
        risk_signals=[],
    )

    assert decision.route == "manager_approval"


def test_medium_risk_routes_to_manager_approval():
    decision = decide_route(
        make_refund(),
        risk_score=0.40,
        risk_signals=[],
    )

    assert decision.route == "manager_approval"


def test_high_risk_routes_to_fraud_review():
    decision = decide_route(
        make_refund(),
        risk_score=0.85,
        risk_signals=[],
    )

    assert decision.route == "fraud_review"


def test_fraud_signal_overrides_other_conditions():
    decision = decide_route(
        make_refund(2500),
        risk_score=0.10,
        risk_signals=["FRAUD"],
    )

    assert decision.route == "fraud_review"


def test_fraud_route_has_priority_over_manager_route():
    decision = decide_route(
        make_refund(20000),
        risk_score=0.80,
        risk_signals=[],
    )

    assert decision.route == "fraud_review"


def test_invalid_risk_score_is_rejected():
    with pytest.raises(ValidationError):
        decide_route(
            make_refund(),
            risk_score=1.5,
            risk_signals=[],
        )


def test_auto_approval_completes_workflow():
    run = make_run()
    decision = decide_route(
        make_refund(),
        risk_score=0.10,
    )

    apply_decision(run, decision)

    assert run.state == "completed"
    assert run.context["routing_decision"]["route"] == "auto_approval"


def test_manager_approval_moves_workflow_to_waiting():
    run = make_run()
    decision = decide_route(
        make_refund(15000),
        risk_score=0.10,
    )

    apply_decision(run, decision)

    assert run.state == "waiting"
    assert run.events[-1].event == "approval.requested"


def test_routing_rejects_non_running_workflow():
    run = make_run(state="created")
    decision = decide_route(
        make_refund(),
        risk_score=0.10,
    )

    with pytest.raises(ValueError, match="Routing requires"):
        apply_decision(run, decision)
