# Implement Conditional Workflow

## Project overview
This project implements a conditional refund workflow. Each refund request is evaluated using its amount, risk score, and risk signals. Based on the routing policy, the request is sent to automatic approval, manager approval, or fraud review.

The project demonstrates explicit workflow states, deterministic decision routing, bounded retry behavior, replay protection, injectable integration adapters, structured observability, and operator evidence generation.

## Scenario
- Refund ID: `REFUND-1001`
- Customer ID: `CUSTOMER-501`
- Amount: INR 2,500
- Currency: INR
- Reason: Damaged product

## Routing policy
These thresholds are implementation assumptions for this exercise:
1. Risk score >= 0.70 or a fraud signal: fraud review.
2. Amount > INR 10,000 or risk score >= 0.30: manager approval.
3. Otherwise: automatic approval.

Fraud review has priority over manager approval.

## Project structure
```text
Implement_Conditional_Workflow/
├── conditional_workflow.py
├── conditional_router.py
├── conditional_reliability.py
├── conditional_adapters.py
├── runbook.py
├── tests/
│   ├── test_workflow_contract.py
│   ├── test_conditional_routing.py
│   ├── test_conditional_recovery.py
│   ├── test_conditional_observability.py
│   └── test_conditional_runbook.py
├── docs/
│   └── decision_table.md
├── outputs/
├── traces/
└── reports/
    ├── OPERATOR_RUNBOOK.md
    └── evidence_report.json
```

## Implementation tasks
1. **Workflow contract and state model:** defines refund data, workflow states, legal transitions, and event records.
2. **Conditional routing:** evaluates amount, risk score, and fraud signals using a deterministic decision table. Auto-approved refunds complete; manager and fraud cases wait for review.
3. **Failure, retry, and replay safety:** implements bounded retries for transient errors and timeouts, permanent-failure handling, malformed-response quarantine, duplicate-trigger blocking, and idempotency replay.
4. **Integration and observability:** uses injectable fake risk and approval adapters, structured traces, workflow status, route metrics, duration measurements, and recursive secret redaction.
5. **Operator runbook and evidence report:** generates operator instructions and validates the presence and JSON validity of expected evidence files.

## Setup and execution (Windows CMD)
```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -v
```

Run demonstrations:
```cmd
python conditional_workflow.py
python conditional_router.py
python conditional_reliability.py
python conditional_adapters.py
python runbook.py
```

## Verification
The complete test suite was executed using `python -m pytest -q`.

**Verified result: 54 passed in 0.32s.**
- Task 1: 9 passed
- Task 2: 10 passed
- Task 3: 11 passed
- Task 4: 14 passed
- Task 5: 10 passed

The evidence report confirmed 7 expected files, 7 found, and 7 valid JSON files. The final evidence status was `True`.

## Limitations
The assessment uses local fake adapters rather than live payment, risk, or approval services. Retry and timeout examples are controlled simulations; production network clients must enforce their own timeouts. The idempotency store is in-memory and must be replaced with durable shared storage and concurrency controls for production. Routing thresholds are exercise assumptions and require business approval before real use.

## Reflection
This activity helped me understand how a workflow can make decisions based on business conditions rather than following one fixed execution path. I started by defining the refund workflow contract and legal state transitions. This gave the workflow a clear structure and made it possible to reject invalid transitions instead of allowing the process to move into an inconsistent state.

The conditional routing task connected business rules to workflow behavior. I implemented a decision table using refund amount, risk score, and fraud signals. The priority order matters: fraud review must take precedence over manager approval, while low-risk requests can complete automatically. I also tested the different paths to ensure that the same input consistently produces the same decision.

The reliability task taught me to consider failures and repeated requests. I implemented bounded retries for transient errors and timeouts, stopped retries for permanent failures, and routed malformed responses for review. Duplicate-trigger protection and idempotency replay demonstrated how to avoid repeating a successful side effect. I also learned that a real external client must enforce its own timeout and that in-memory idempotency is not sufficient for production.

In the integration task, I separated risk and approval dependencies behind adapter interfaces. Structured traces, workflow status, metrics, and secret redaction made the execution easier to inspect. Finally, I generated an operator runbook and an evidence report to support troubleshooting and verification.

The complete suite finished with 54 passing tests, and all seven expected evidence files were found and validated. This project strengthened my understanding of conditional orchestration, decision policies, recovery strategies, integration boundaries, and operational observability.
