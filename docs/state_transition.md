
# Conditional Workflow — State Transition Model

## Workflow states

| State | Meaning |
|---|---|
| created | Refund workflow has been initialized |
| running | Workflow is actively processing |
| waiting | Workflow is paused for an external action or approval |
| completed | Workflow has completed successfully |
| needs_review | Workflow failed or requires operator intervention |

## Legal transitions

| Current state | Event | Next state |
|---|---|---|
| created | start | running |
| running | complete | completed |
| running | pause | waiting |
| waiting | resume | running |
| running | fail | needs_review |
| waiting | fail | needs_review |

## State transition diagram

```text
created
   |
  start
   v
running -------- complete --------> completed
   |
  pause
   v
waiting -------- resume ---------> running
   |
  fail
   v
needs_review

running -------- fail -----------> needs_review
```

## Workflow event model

Every recorded event includes:
- Run ID
- Event name
- Current workflow state
- UTC timestamp
- Additional event details

## Validation rules

- Only explicitly defined transitions are allowed.
- An invalid transition raises ValueError.
- A workflow event is recorded after a successful transition.
- Refund amounts must be greater than zero.
- Each workflow run is associated with a business key.
