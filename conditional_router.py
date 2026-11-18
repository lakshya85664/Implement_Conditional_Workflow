
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from conditional_workflow import (
    RefundRequest,
    WorkflowRun,
    run_topic_fixture,
    transition,
)


OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


class RoutingDecision(BaseModel):
    refund_id: str
    route: Literal[
        "auto_approval",
        "manager_approval",
        "fraud_review",
    ]
    reason: str
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_signals: list[str] = Field(default_factory=list)


# Decision table: evaluated from top to bottom.
ROUTING_POLICY = [
    {
        "priority": 1,
        "condition": "risk_score >= 0.70 OR fraud signal exists",
        "route": "fraud_review",
    },
    {
        "priority": 2,
        "condition": "amount > 10000 OR risk_score >= 0.30",
        "route": "manager_approval",
    },
    {
        "priority": 3,
        "condition": "otherwise",
        "route": "auto_approval",
    },
]


def decide_route(
    refund: RefundRequest,
    risk_score: float,
    risk_signals: list[str] | None = None,
) -> RoutingDecision:
    """Choose a refund route using the deterministic policy."""

    signals = risk_signals or []

    # Validate the risk score using the Pydantic model.
    validated = RoutingDecision(
        refund_id=refund.refund_id,
        route="auto_approval",
        reason="Initial routing evaluation",
        risk_score=risk_score,
        risk_signals=signals,
    )

    normalized_signals = {
        signal.strip().lower() for signal in validated.risk_signals
    }

    if validated.risk_score >= 0.70 or "fraud" in normalized_signals:
        route = "fraud_review"
        reason = "High risk score or fraud signal detected"

    elif refund.amount > 10000 or validated.risk_score >= 0.30:
        route = "manager_approval"
        reason = "Refund amount or risk score requires manager approval"

    else:
        route = "auto_approval"
        reason = "Refund is within automatic approval policy"

    return RoutingDecision(
        refund_id=refund.refund_id,
        route=route,
        reason=reason,
        risk_score=validated.risk_score,
        risk_signals=validated.risk_signals,
    )


def apply_decision(
    run: WorkflowRun,
    decision: RoutingDecision,
) -> WorkflowRun:
    """Record a routing decision and apply its workflow transition."""

    if run.state != "running":
        raise ValueError(
            f"Routing requires a running workflow, got: {run.state}"
        )

    run.context["routing_decision"] = decision.model_dump()

    run.record(
        "routing.decision",
        route=decision.route,
        reason=decision.reason,
    )

    if decision.route == "auto_approval":
        run.record("refund.auto_approved")
        transition(run, "complete")

    elif decision.route in ("manager_approval", "fraud_review"):
        transition(run, "pause")
        run.record(
            "approval.requested",
            approval_type=decision.route,
        )

    return run


def run_demo() -> dict:
    """Execute a deterministic low-risk refund happy path."""

    fixture = run_topic_fixture()

    refund = RefundRequest.model_validate(
        fixture["context"]["refund"]
    )

    run = WorkflowRun(
        run_id=fixture["run_id"],
        business_key=fixture["business_key"],
        state=fixture["state"],
        context=fixture["context"],
    )

    decision = decide_route(
        refund=refund,
        risk_score=0.15,
        risk_signals=[],
    )

    apply_decision(run, decision)

    result = {
        "run_id": run.run_id,
        "refund_id": refund.refund_id,
        "amount": refund.amount,
        "risk_score": decision.risk_score,
        "route": decision.route,
        "reason": decision.reason,
        "final_state": run.state,
        "events": [
            event.model_dump() for event in run.events
        ],
    }

    output_file = OUTPUT_DIR / "task2_conditional_workflow.json"
    output_file.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print("Conditional workflow result:")
    print(json.dumps(result, indent=2))
    print(f"\nSaved: {output_file}")

    return result


if __name__ == "__main__":
    print("=" * 60)
    print("TASK 2 - CONDITIONAL WORKFLOW IMPLEMENTATION")
    print("=" * 60)

    run_demo()
