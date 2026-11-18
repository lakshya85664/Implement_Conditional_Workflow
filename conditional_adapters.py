
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from conditional_workflow import RefundRequest, WorkflowRun, transition
from conditional_router import decide_route, apply_decision


OUTPUT_DIR = Path("outputs")
TRACE_DIR = Path("traces")
OUTPUT_DIR.mkdir(exist_ok=True)
TRACE_DIR.mkdir(exist_ok=True)


SENSITIVE_KEYS = {
    "password",
    "api_key",
    "token",
    "access_token",
    "secret",
    "authorization",
    "card_number",
}


def redact(value: Any) -> Any:
    """Recursively redact values stored under sensitive keys."""

    if isinstance(value, dict):
        cleaned = {}

        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = redact(item)

        return cleaned

    if isinstance(value, list):
        return [redact(item) for item in value]

    return value


class RiskAssessment(BaseModel):
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_signals: list[str] = Field(default_factory=list)


class RiskAdapter(Protocol):
    def assess(self, refund: RefundRequest) -> dict[str, Any]:
        ...


class ApprovalAdapter(Protocol):
    def request_approval(
        self,
        refund_id: str,
        approval_type: str,
    ) -> dict[str, Any]:
        ...


class FakeRiskAdapter:
    """Local injectable risk service."""

    def __init__(
        self,
        risk_score: float = 0.15,
        risk_signals: list[str] | None = None,
    ):
        self.risk_score = risk_score
        self.risk_signals = risk_signals or []
        self.calls = 0

    def assess(self, refund: RefundRequest) -> dict[str, Any]:
        self.calls += 1

        return {
            "risk_score": self.risk_score,
            "risk_signals": self.risk_signals,
            "provider": "fake-risk-service",
            "api_key": "fake-risk-secret",
        }


class FakeApprovalAdapter:
    """Local injectable manager/fraud approval service."""

    def __init__(self):
        self.calls: list[dict[str, str]] = []

    def request_approval(
        self,
        refund_id: str,
        approval_type: str,
    ) -> dict[str, Any]:
        request = {
            "refund_id": refund_id,
            "approval_type": approval_type,
            "status": "requested",
        }

        self.calls.append(request)

        return {
            **request,
            "authorization": "fake-approval-secret",
        }


class WorkflowMetrics:
    """Simple in-memory counters and latency measurements."""

    def __init__(self):
        self.workflow_started = 0
        self.workflow_completed = 0
        self.workflow_waiting = 0
        self.workflow_failed = 0
        self.adapter_calls = 0
        self.adapter_failures = 0
        self.routes: dict[str, int] = {}
        self.durations_ms: list[float] = []

    def record_route(self, route: str):
        self.routes[route] = self.routes.get(route, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        durations = self.durations_ms

        return {
            "workflow_started": self.workflow_started,
            "workflow_completed": self.workflow_completed,
            "workflow_waiting": self.workflow_waiting,
            "workflow_failed": self.workflow_failed,
            "adapter_calls": self.adapter_calls,
            "adapter_failures": self.adapter_failures,
            "routes": dict(self.routes),
            "duration_count": len(durations),
            "average_duration_ms": (
                round(sum(durations) / len(durations), 3)
                if durations else 0.0
            ),
        }


class ConditionalWorkflowService:
    def __init__(
        self,
        risk_adapter: RiskAdapter,
        approval_adapter: ApprovalAdapter,
    ):
        self.risk_adapter = risk_adapter
        self.approval_adapter = approval_adapter

        self.metrics = WorkflowMetrics()
        self.traces: list[dict[str, Any]] = []
        self.statuses: dict[str, dict[str, Any]] = {}

    def record(
        self,
        run_id: str,
        event: str,
        state: str,
        outcome: str,
        details: dict[str, Any] | None = None,
    ):
        entry = {
            "run_id": run_id,
            "event": event,
            "state": state,
            "outcome": outcome,
            "timestamp": time.time(),
            "details": redact(details or {}),
        }

        self.traces.append(entry)

    def execute(
        self,
        run_id: str,
        refund: RefundRequest,
    ) -> dict[str, Any]:
        """Run risk assessment and conditional refund routing."""

        if not run_id:
            raise ValueError("run_id is required")

        if run_id in self.statuses:
            return {
                "status": "duplicate_blocked",
                "run_id": run_id,
                "next_action": "do_not_process_again",
            }

        started = time.perf_counter()
        self.metrics.workflow_started += 1

        run = WorkflowRun(
            run_id=run_id,
            business_key=refund.refund_id,
            context={"refund": refund.model_dump()},
        )

        transition(run, "start")

        self.statuses[run_id] = {
            "run_id": run_id,
            "refund_id": refund.refund_id,
            "state": run.state,
            "status": "running",
            "route": None,
            "next_action": "assess_risk",
        }

        self.record(
            run_id,
            "workflow.started",
            run.state,
            "success",
            {"refund_id": refund.refund_id},
        )

        try:
            # Dependency call 1: risk assessment.
            self.metrics.adapter_calls += 1
            risk_started = time.perf_counter()

            try:
                raw_risk = self.risk_adapter.assess(refund)
            except Exception:
                self.metrics.adapter_failures += 1
                raise

            risk_duration = (
                time.perf_counter() - risk_started
            ) * 1000

            self.record(
                run_id,
                "risk_adapter.completed",
                run.state,
                "success",
                {
                    "duration_ms": round(risk_duration, 3),
                    "response": raw_risk,
                },
            )

            risk = RiskAssessment.model_validate(raw_risk)

            decision = decide_route(
                refund=refund,
                risk_score=risk.risk_score,
                risk_signals=risk.risk_signals,
            )

            self.metrics.record_route(decision.route)

            self.record(
                run_id,
                "routing.decided",
                run.state,
                "success",
                decision.model_dump(),
            )

            if decision.route == "auto_approval":
                apply_decision(run, decision)

                final_status = "completed"
                next_action = "none"

            else:
                # Manager or fraud review requires an external approval request.
                transition(run, "pause")

                approval_type = decision.route

                self.metrics.adapter_calls += 1
                approval_started = time.perf_counter()

                try:
                    approval_response = (
                        self.approval_adapter.request_approval(
                            refund.refund_id,
                            approval_type,
                        )
                    )
                except Exception:
                    self.metrics.adapter_failures += 1
                    raise

                approval_duration = (
                    time.perf_counter() - approval_started
                ) * 1000

                self.record(
                    run_id,
                    "approval_adapter.completed",
                    run.state,
                    "success",
                    {
                        "duration_ms": round(approval_duration, 3),
                        "response": approval_response,
                    },
                )

                run.record(
                    "approval.requested",
                    approval_type=approval_type,
                )

                final_status = "waiting"
                next_action = "await_approval"

            elapsed = (time.perf_counter() - started) * 1000
            self.metrics.durations_ms.append(elapsed)

            if final_status == "completed":
                self.metrics.workflow_completed += 1
            else:
                self.metrics.workflow_waiting += 1

            self.statuses[run_id] = {
                "run_id": run_id,
                "refund_id": refund.refund_id,
                "state": run.state,
                "status": final_status,
                "route": decision.route,
                "next_action": next_action,
                "duration_ms": round(elapsed, 3),
            }

            self.record(
                run_id,
                "workflow.finished",
                run.state,
                final_status,
                {
                    "route": decision.route,
                    "duration_ms": round(elapsed, 3),
                    "next_action": next_action,
                },
            )

            return self.get_status(run_id)

        except Exception as exc:
            if run.state in ("running", "waiting"):
                transition(run, "fail")

            elapsed = (time.perf_counter() - started) * 1000
            self.metrics.workflow_failed += 1
            self.metrics.durations_ms.append(elapsed)

            # Keep error information classified and avoid raw exception text.
            error_type = type(exc).__name__

            self.statuses[run_id] = {
                "run_id": run_id,
                "refund_id": refund.refund_id,
                "state": run.state,
                "status": "needs_review",
                "route": None,
                "error_type": error_type,
                "next_action": "operator_investigation",
                "duration_ms": round(elapsed, 3),
            }

            self.record(
                run_id,
                "workflow.failed",
                run.state,
                "needs_review",
                {
                    "error_type": error_type,
                    "next_action": "operator_investigation",
                },
            )

            return self.get_status(run_id)

    def get_status(self, run_id: str) -> dict[str, Any]:
        """Return the latest workflow status."""

        if run_id not in self.statuses:
            raise KeyError(f"Unknown workflow run: {run_id}")

        return dict(self.statuses[run_id])

    def get_trace(self, run_id: str | None = None) -> list[dict[str, Any]]:
        """Return all traces or traces for one workflow run."""

        selected = self.traces

        if run_id is not None:
            selected = [
                item for item in self.traces
                if item["run_id"] == run_id
            ]

        return [dict(item) for item in selected]

    def get_metrics(self) -> dict[str, Any]:
        return self.metrics.snapshot()

    def save_evidence(self):
        trace_path = TRACE_DIR / "task4_conditional_observability.json"
        metrics_path = OUTPUT_DIR / "task4_conditional_measurements.json"

        trace_path.write_text(
            json.dumps(self.traces, indent=2),
            encoding="utf-8",
        )

        metrics_path.write_text(
            json.dumps(self.get_metrics(), indent=2),
            encoding="utf-8",
        )

        return trace_path, metrics_path


def run_demo():
    risk_adapter = FakeRiskAdapter(
        risk_score=0.15,
        risk_signals=[],
    )

    approval_adapter = FakeApprovalAdapter()

    service = ConditionalWorkflowService(
        risk_adapter=risk_adapter,
        approval_adapter=approval_adapter,
    )

    refund = RefundRequest(
        refund_id="REFUND-4001",
        customer_id="CUSTOMER-501",
        amount=2500,
        reason="Damaged product",
    )

    result = service.execute(
        run_id="RUN-REFUND-004",
        refund=refund,
    )

    trace_path, metrics_path = service.save_evidence()

    report = {
        "result": result,
        "metrics": service.get_metrics(),
        "trace_count": len(service.get_trace()),
        "trace_file": str(trace_path),
        "metrics_file": str(metrics_path),
    }

    output_path = OUTPUT_DIR / "task4_conditional_observability.json"
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2))
    print(f"\nSaved: {output_path}")

    return report


if __name__ == "__main__":
    print("=" * 60)
    print("TASK 4 - INTEGRATION AND OBSERVABILITY")
    print("=" * 60)
    run_demo()
