
import pytest

from conditional_workflow import (
    RefundRequest,
    WorkflowRun,
    run_topic_fixture,
    transition,
)


def create_run():
    return WorkflowRun(
        run_id="RUN-TEST-001",
        business_key="REFUND-TEST-001",
    )


def test_workflow_starts_in_created_state():
    run = create_run()

    assert run.state == "created"


def test_legal_transition_created_to_running():
    run = create_run()

    transition(run, "start")

    assert run.state == "running"
    assert len(run.events) == 1
    assert run.events[0].event == "start"


def test_legal_transition_running_to_completed():
    run = create_run()

    transition(run, "start")
    transition(run, "complete")

    assert run.state == "completed"


def test_legal_transition_running_to_waiting():
    run = create_run()

    transition(run, "start")
    transition(run, "pause")

    assert run.state == "waiting"


def test_legal_transition_waiting_to_running():
    run = create_run()

    transition(run, "start")
    transition(run, "pause")
    transition(run, "resume")

    assert run.state == "running"


def test_illegal_transition_is_rejected():
    run = create_run()

    with pytest.raises(ValueError, match="Illegal transition"):
        transition(run, "complete")

    assert run.state == "created"
    assert len(run.events) == 0


def test_refund_amount_must_be_positive():
    with pytest.raises(ValueError):
        RefundRequest(
            refund_id="REFUND-INVALID",
            customer_id="CUSTOMER-INVALID",
            amount=0,
            reason="Invalid amount",
        )


def test_fixture_creates_running_workflow():
    result = run_topic_fixture()

    assert result["state"] == "running"
    assert result["run_id"] == "RUN-REFUND-001"
    assert result["business_key"] == "REFUND-1001"


def test_fixture_records_initialization_event():
    result = run_topic_fixture()

    event_names = [
        event["event"] for event in result["events"]
    ]

    assert "start" in event_names
    assert "workflow.initialized" in event_names
