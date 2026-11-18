
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


OUTPUT_DIR = Path("outputs")
TRACE_DIR = Path("traces")

OUTPUT_DIR.mkdir(exist_ok=True)
TRACE_DIR.mkdir(exist_ok=True)


class TransientError(Exception):
    """An error that may succeed if retried."""


class PermanentError(Exception):
    """An error that should not be retried."""


class MalformedResponseError(Exception):
    """The dependency returned an invalid response."""


class RefundGatewayResponse(BaseModel):
    accepted: bool
    transaction_id: str


class IdempotencyStore:
    """In-memory store for protected side effects."""

    def __init__(self):
        self.results: dict[str, dict[str, Any]] = {}

    def get(self, key: str):
        return self.results.get(key)

    def save(self, key: str, result: dict[str, Any]):
        self.results[key] = result


class TriggerRegistry:
    """Prevents duplicate processing of the same workflow run."""

    def __init__(self):
        self.seen_runs: set[str] = set()

    def register(self, run_id: str) -> bool:
        if run_id in self.seen_runs:
            return False

        self.seen_runs.add(run_id)
        return True


class FakeRefundGateway:
    """Local fake gateway; never calls a real payment service."""

    def __init__(self, outcomes: list[Any] | None = None):
        self.outcomes = list(outcomes or [])
        self.side_effect_count = 0

    
    def issue_refund(self, refund_id: str) -> dict[str, Any]:
        if self.outcomes:
            outcome = self.outcomes.pop(0)

            if isinstance(outcome, Exception):
                raise outcome

            if isinstance(outcome, dict) and outcome.get("accepted") is True:
                self.side_effect_count += 1

            return outcome

        self.side_effect_count += 1

        return {
            "accepted": True,
            "transaction_id": f"TX-{refund_id}",
        }



class ConditionalRefundProcessor:
    def __init__(
        self,
        gateway: FakeRefundGateway,
        max_attempts: int = 3,
        backoff_seconds: float = 0.0,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        if backoff_seconds < 0:
            raise ValueError("backoff_seconds cannot be negative")

        self.gateway = gateway
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.sleeper = sleeper

        self.idempotency = IdempotencyStore()
        self.triggers = TriggerRegistry()
        self.trace: list[dict[str, Any]] = []

    def record(
        self,
        run_id: str,
        refund_id: str,
        event: str,
        outcome: str,
        attempt: int,
        next_action: str,
        details: dict[str, Any] | None = None,
    ):
        self.trace.append({
            "run_id": run_id,
            "refund_id": refund_id,
            "event": event,
            "outcome": outcome,
            "attempt": attempt,
            "next_action": next_action,
            "details": details or {},
        })

    def process(
        self,
        run_id: str,
        refund_id: str,
    ) -> dict[str, Any]:
        """Execute a bounded, replay-safe refund operation."""

        if not run_id or not refund_id:
            raise ValueError("run_id and refund_id are required")

        # Duplicate trigger protection.
        if not self.triggers.register(run_id):
            self.record(
                run_id,
                refund_id,
                "duplicate_trigger",
                "blocked",
                0,
                "do_not_process_again",
            )

            return {
                "status": "duplicate_blocked",
                "next_action": "do_not_process_again",
                "attempts": 0,
            }

        # Replay protection for a previously completed side effect.
        cached = self.idempotency.get(refund_id)

        if cached is not None:
            self.record(
                run_id,
                refund_id,
                "idempotency_replay",
                "cached",
                0,
                "return_cached_result",
            )

            return {
                **cached,
                "status": "replayed",
                "next_action": "return_cached_result",
                "attempts": 0,
            }

        for attempt in range(1, self.max_attempts + 1):
            self.record(
                run_id,
                refund_id,
                "refund_attempt",
                "started",
                attempt,
                "call_gateway",
            )

            try:
                raw_response = self.gateway.issue_refund(refund_id)

                if not isinstance(raw_response, dict):
                    raise MalformedResponseError(
                        "Gateway response must be an object"
                    )

                try:
                    response = RefundGatewayResponse.model_validate(
                        raw_response
                    )
                except ValidationError as exc:
                    raise MalformedResponseError(
                        "Gateway response failed schema validation"
                    ) from exc

                if not response.accepted:
                    raise PermanentError(
                        "Gateway rejected the refund"
                    )

                result = {
                    "status": "succeeded",
                    "refund_id": refund_id,
                    "transaction_id": response.transaction_id,
                }

                # Save only after a valid successful response.
                self.idempotency.save(refund_id, result)

                self.record(
                    run_id,
                    refund_id,
                    "refund_succeeded",
                    "success",
                    attempt,
                    "continue_workflow",
                )

                return {
                    **result,
                    "next_action": "continue_workflow",
                    "attempts": attempt,
                }

            except TimeoutError:
                error_type = "timeout"
                retryable = True
                message = "Gateway call timed out"

            except TransientError:
                error_type = "transient_error"
                retryable = True
                message = "Temporary gateway failure"

            except MalformedResponseError as exc:
                error_type = "malformed_response"
                retryable = False
                message = str(exc)

            except PermanentError as exc:
                error_type = "permanent_failure"
                retryable = False
                message = str(exc)

            except Exception:
                # Do not expose raw exception text or secrets in traces.
                error_type = "unexpected_error"
                retryable = False
                message = "Unexpected dependency error"

            if retryable and attempt < self.max_attempts:
                delay = self.backoff_seconds * (2 ** (attempt - 1))

                self.record(
                    run_id,
                    refund_id,
                    error_type,
                    "retry_scheduled",
                    attempt,
                    "retry",
                    {"message": message, "backoff_seconds": delay},
                )

                self.sleeper(delay)
                continue

            if retryable:
                next_action = "manual_recovery"
                status = "retry_exhausted"
            elif error_type == "malformed_response":
                next_action = "quarantine_and_review"
                status = "needs_review"
            else:
                next_action = "stop_and_escalate"
                status = "failed"

            self.record(
                run_id,
                refund_id,
                error_type,
                status,
                attempt,
                next_action,
                {"message": message},
            )

            return {
                "status": status,
                "error_type": error_type,
                "next_action": next_action,
                "attempts": attempt,
            }

        raise RuntimeError("Unexpected retry loop exit")

    def save_trace(self, filename: str = "task3_recovery_trace.json"):
        path = TRACE_DIR / filename
        path.write_text(
            json.dumps(self.trace, indent=2),
            encoding="utf-8",
        )
        return path


def run_demo() -> dict[str, Any]:
    gateway = FakeRefundGateway([
        TransientError("Temporary unavailable"),
        TimeoutError("Simulated timeout"),
        {
            "accepted": True,
            "transaction_id": "TX-REFUND-1001",
        },
    ])

    processor = ConditionalRefundProcessor(
        gateway=gateway,
        max_attempts=3,
        backoff_seconds=0.1,
        sleeper=lambda seconds: None,
    )

    result = processor.process(
        run_id="RUN-REFUND-003",
        refund_id="REFUND-1001",
    )

    trace_path = processor.save_trace()

    report = {
        "result": result,
        "trace_entries": len(processor.trace),
        "gateway_side_effect_count": gateway.side_effect_count,
        "trace_file": str(trace_path),
    }

    output_path = OUTPUT_DIR / "task3_failure_recovery.json"
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2))
    print(f"\nSaved: {output_path}")

    return report


if __name__ == "__main__":
    print("=" * 60)
    print("TASK 3 - FAILURE, RETRY, AND REPLAY SAFETY")
    print("=" * 60)
    run_demo()
