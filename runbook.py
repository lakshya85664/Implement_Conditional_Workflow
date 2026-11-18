
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conditional_workflow import run_topic_fixture


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
TRACE_DIR = BASE_DIR / "traces"
REPORT_DIR = BASE_DIR / "reports"

for directory in (OUTPUT_DIR, TRACE_DIR, REPORT_DIR):
    directory.mkdir(exist_ok=True)


EXPECTED_EVIDENCE = [
    OUTPUT_DIR / "task1_workflow_contract.json",
    OUTPUT_DIR / "task2_conditional_workflow.json",
    OUTPUT_DIR / "task3_failure_recovery.json",
    OUTPUT_DIR / "task4_conditional_observability.json",
    OUTPUT_DIR / "task4_conditional_measurements.json",
    TRACE_DIR / "task3_recovery_trace.json",
    TRACE_DIR / "task4_conditional_observability.json",
]


def generate_task1_evidence() -> Path:
    """Persist the Task 1 workflow contract fixture as JSON."""

    path = OUTPUT_DIR / "task1_workflow_contract.json"
    path.write_text(
        json.dumps(run_topic_fixture(), indent=2),
        encoding="utf-8",
    )
    return path


def inspect_evidence() -> dict[str, Any]:
    """Check expected evidence files and validate JSON content."""

    inventory = []

    for path in EXPECTED_EVIDENCE:
        exists = path.is_file()
        valid_json = False
        error = None

        try:
            display_path = str(path.relative_to(BASE_DIR))
        except ValueError:
            display_path = str(path)

        if exists:
            try:
                with path.open("r", encoding="utf-8") as file:
                    json.load(file)
                valid_json = True
            except json.JSONDecodeError:
                error = "JSONDecodeError"
            except OSError:
                error = "OSError"

        inventory.append({
            "file": display_path,
            "exists": exists,
            "valid_json": valid_json,
            "error": error,
        })

    found_count = sum(item["exists"] for item in inventory)
    valid_count = sum(item["valid_json"] for item in inventory)

    return {
        "expected_count": len(EXPECTED_EVIDENCE),
        "found_count": found_count,
        "valid_json_count": valid_count,
        "complete": (
            found_count == len(EXPECTED_EVIDENCE)
            and valid_count == len(EXPECTED_EVIDENCE)
        ),
        "files": inventory,
    }


def build_runbook() -> str:
    return """# Conditional Refund Workflow — Operator Runbook

## 1. Purpose

This runbook explains how to execute, inspect, and recover the
conditional refund workflow.

## 2. Workflow routing

The workflow evaluates refund amount, risk score, and risk signals.

| Priority | Condition | Route |
|---|---|---|
| 1 | Risk score >= 0.70 or fraud signal exists | Fraud review |
| 2 | Amount > 10000 or risk score >= 0.30 | Manager approval |
| 3 | Otherwise | Auto-approval |

These thresholds are exercise policy assumptions and should be
confirmed by a business owner before production use.

## 3. Execution commands

Run commands from the project root with the virtual environment active.

```cmd
python conditional_workflow.py
python conditional_router.py
python conditional_reliability.py
python conditional_adapters.py
python runbook.py
python -m pytest -v
```

## 4. Workflow states

- created: workflow initialized
- running: processing is active
- waiting: approval or external action is pending
- completed: workflow completed successfully
- needs_review: operator investigation is required

## 5. Failure and recovery

- Transient errors: retry within the configured attempt limit.
- Timeout: retry according to policy; verify the external service state
  before manually replaying a real refund.
- Permanent failure: stop and escalate.
- Malformed response: quarantine and review the response.
- Retry exhaustion: send the case to manual recovery.
- Duplicate trigger: do not process the same workflow run again.

## 6. Idempotency and replay safety

The Idempotency mechanism uses an idempotency key to prevent
a repeated operation from producing a duplicate side effect.

The demonstration uses in-memory storage. Production deployments
must use durable shared storage and safe concurrency controls.

## 7. Integration and observability

Risk and approval dependencies are isolated behind adapter interfaces.
Inspect structured traces for event names, workflow states, outcomes,
timestamps, and redacted details.

Metrics include workflow counts, adapter calls, adapter failures,
route counts, and execution duration.

## 8. Evidence locations

- outputs/: workflow results and measurement reports
- traces/: structured execution and recovery traces
- reports/: operator documentation and evidence inventory

## 9. Operator checklist

1. Confirm the workflow run ID and refund business key.
2. Inspect the latest workflow status.
3. Check the selected route and its reason.
4. Inspect trace events and adapter outcomes.
5. Verify sensitive values are redacted.
6. Check retry count and next_action before recovery.
7. Confirm the evidence report is complete.
8. Escalate unresolved or ambiguous refund outcomes.

## 10. Operational limitations

This assessment uses local fake adapters and in-memory idempotency.
It does not connect to live payment, risk, or approval services.
Production integrations require client-level timeouts, durable
idempotency, access controls, and audited operator actions.
"""


def generate_reports() -> dict[str, Any]:
    """Generate the operator runbook and evidence report."""

    generate_task1_evidence()

    evidence = inspect_evidence()

    runbook_path = REPORT_DIR / "OPERATOR_RUNBOOK.md"
    runbook_path.write_text(
        build_runbook(),
        encoding="utf-8",
    )

    report = {
        "project": "Implement Conditional Workflow",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence": evidence,
        "runbook": str(runbook_path.relative_to(BASE_DIR)),
        "recommendation": (
            "All expected evidence is present and valid."
            if evidence["complete"]
            else "Review missing or invalid evidence files."
        ),
    }

    evidence_path = REPORT_DIR / "evidence_report.json"
    evidence_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    output_path = OUTPUT_DIR / "task5_operator_report.json"
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    return {
        "evidence": evidence,
        "runbook_path": runbook_path,
        "evidence_path": evidence_path,
        "output_path": output_path,
    }


if __name__ == "__main__":
    print("=" * 65)
    print("TASK 5 - OPERATOR RUNBOOK AND EVIDENCE REPORT")
    print("=" * 65)

    result = generate_reports()
    evidence = result["evidence"]

    print(f"Expected evidence files: {evidence['expected_count']}")
    print(f"Found evidence files: {evidence['found_count']}")
    print(f"Valid JSON files: {evidence['valid_json_count']}")
    print(f"Evidence complete: {evidence['complete']}")

    for key in ("runbook_path", "evidence_path", "output_path"):
        print(f"Created: {result[key]}")
