# Conditional Refund Workflow — Operator Runbook

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
