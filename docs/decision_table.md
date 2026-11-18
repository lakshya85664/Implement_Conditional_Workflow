
# Refund Conditional Routing Decision Table

## Policy assumptions

The assessment requires routing based on refund amount and risk signals.
The following thresholds are implementation assumptions for this exercise.

| Priority | Condition | Route |
|---|---|---|
| 1 | Risk score >= 0.70 OR fraud signal exists | Fraud review |
| 2 | Amount > 10000 OR risk score >= 0.30 | Manager approval |
| 3 | No previous condition matches | Auto-approval |

## Route behavior

### Auto-approval
- Records the routing decision.
- Records the automatic approval event.
- Transitions the workflow to completed.

### Manager approval
- Records the routing decision.
- Transitions the workflow to waiting.
- Records an approval request for a manager.

### Fraud review
- Records the routing decision.
- Transitions the workflow to waiting.
- Records an approval request for fraud review.

## Precedence

Fraud review has the highest priority. A refund that matches both fraud and manager conditions is routed to fraud review.

## Validation

- Risk score must be between 0.0 and 1.0.
- Refund amount must be greater than zero.
- A routing decision can only be applied to a running workflow.
- Invalid risk scores and invalid workflow states are rejected.
