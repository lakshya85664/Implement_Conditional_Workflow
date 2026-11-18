
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


LEGAL_TRANSITIONS = {
    ("created", "start"): "running",
    ("running", "complete"): "completed",
    ("running", "pause"): "waiting",
    ("waiting", "resume"): "running",
    ("running", "fail"): "needs_review",
    ("waiting", "fail"): "needs_review",
}


class WorkflowEvent(BaseModel):
    run_id: str
    event: str
    state: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    details: dict[str, Any] = Field(default_factory=dict)


class RefundRequest(BaseModel):
    refund_id: str
    customer_id: str
    amount: float = Field(gt=0)
    currency: str = "INR"
    reason: str


class WorkflowRun(BaseModel):
    run_id: str
    business_key: str
    state: str = "created"
    attempts: int = 0
    context: dict[str, Any] = Field(default_factory=dict)
    events: list[WorkflowEvent] = Field(default_factory=list)

    def record(self, event: str, **details: Any) -> None:
        self.events.append(
            WorkflowEvent(
                run_id=self.run_id,
                event=event,
                state=self.state,
                details=details,
            )
        )


def transition(run: WorkflowRun, event: str) -> WorkflowRun:
    """Apply one legal workflow state transition."""

    next_state = LEGAL_TRANSITIONS.get((run.state, event))

    if next_state is None:
        raise ValueError(
            f"Illegal transition: ({run.state}) + ({event})"
        )

    run.state = next_state
    run.record(event)

    return run


def run_topic_fixture() -> dict[str, Any]:
    """Create a sample refund workflow and start it."""

    refund = RefundRequest(
        refund_id="REFUND-1001",
        customer_id="CUSTOMER-501",
        amount=2500.00,
        currency="INR",
        reason="Damaged product",
    )

    run = WorkflowRun(
        run_id="RUN-REFUND-001",
        business_key=refund.refund_id,
        context={
            "refund": refund.model_dump(),
            "risk_score": 0.15,
            "risk_signals": [],
        },
    )

    transition(run, "start")
    run.record(
        "workflow.initialized",
        refund_id=refund.refund_id,
        amount=refund.amount,
    )

    return {
        "run_id": run.run_id,
        "business_key": run.business_key,
        "state": run.state,
        "context": run.context,
        "events": [
            event.model_dump() for event in run.events
        ],
    }


if __name__ == "__main__":
    import json

    result = run_topic_fixture()
    print("=" * 60)
    print("TOPIC 5 - CONDITIONAL WORKFLOW: TASK 1")
    print("=" * 60)
    print(json.dumps(result, indent=2))
