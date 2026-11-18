
import pytest

from conditional_reliability import (
    ConditionalRefundProcessor,
    FakeRefundGateway,
    TransientError,
    PermanentError,
)


def no_wait(seconds):
    pass


def make_processor(outcomes=None, max_attempts=3):
    gateway = FakeRefundGateway(outcomes or [])

    processor = ConditionalRefundProcessor(
        gateway=gateway,
        max_attempts=max_attempts,
        backoff_seconds=0.01,
        sleeper=no_wait,
    )

    return processor, gateway


def test_transient_error_is_retried():
    processor, gateway = make_processor([
        TransientError("Temporary issue"),
        {"accepted": True, "transaction_id": "TX-1"},
    ])

    result = processor.process("RUN-1", "REFUND-1")

    assert result["status"] == "succeeded"
    assert result["attempts"] == 2
    assert gateway.side_effect_count == 1


def test_timeout_is_retried():
    processor, gateway = make_processor([
        TimeoutError("Simulated timeout"),
        {"accepted": True, "transaction_id": "TX-2"},
    ])

    result = processor.process("RUN-2", "REFUND-2")

    assert result["status"] == "succeeded"
    assert result["attempts"] == 2


def test_permanent_failure_is_not_retried():
    processor, gateway = make_processor([
        PermanentError("Rejected permanently"),
    ])

    result = processor.process("RUN-3", "REFUND-3")

    assert result["status"] == "failed"
    assert result["error_type"] == "permanent_failure"
    assert result["attempts"] == 1


def test_malformed_response_is_quarantined():
    processor, gateway = make_processor([
        {"unexpected": "invalid response"},
    ])

    result = processor.process("RUN-4", "REFUND-4")

    assert result["status"] == "needs_review"
    assert result["error_type"] == "malformed_response"
    assert result["next_action"] == "quarantine_and_review"


def test_retry_limit_is_enforced():
    processor, gateway = make_processor(
        [
            TransientError("Temporary 1"),
            TransientError("Temporary 2"),
            TransientError("Temporary 3"),
            TransientError("Should not be reached"),
        ],
        max_attempts=3,
    )

    result = processor.process("RUN-5", "REFUND-5")

    assert result["status"] == "retry_exhausted"
    assert result["attempts"] == 3
    assert len(gateway.outcomes) == 1


def test_duplicate_trigger_is_blocked():
    processor, gateway = make_processor([
        {"accepted": True, "transaction_id": "TX-6"},
    ])

    first = processor.process("RUN-6", "REFUND-6")
    second = processor.process("RUN-6", "REFUND-6")

    assert first["status"] == "succeeded"
    assert second["status"] == "duplicate_blocked"
    assert gateway.side_effect_count == 1


def test_replay_returns_cached_result_without_duplicate_side_effect():
    processor, gateway = make_processor([
        {"accepted": True, "transaction_id": "TX-7"},
    ])

    first = processor.process("RUN-7A", "REFUND-7")
    replay = processor.process("RUN-7B", "REFUND-7")

    assert first["status"] == "succeeded"
    assert replay["status"] == "replayed"
    assert replay["transaction_id"] == "TX-7"
    assert gateway.side_effect_count == 1


def test_retry_trace_contains_explicit_next_action():
    processor, gateway = make_processor([
        TransientError("Temporary"),
        {"accepted": True, "transaction_id": "TX-8"},
    ])

    processor.process("RUN-8", "REFUND-8")

    retry_events = [
        item for item in processor.trace
        if item["outcome"] == "retry_scheduled"
    ]

    assert len(retry_events) == 1
    assert retry_events[0]["next_action"] == "retry"


def test_empty_identifiers_are_rejected():
    processor, gateway = make_processor()

    with pytest.raises(ValueError, match="required"):
        processor.process("", "REFUND-9")


def test_zero_retry_limit_is_rejected():
    gateway = FakeRefundGateway()

    with pytest.raises(ValueError, match="max_attempts"):
        ConditionalRefundProcessor(
            gateway=gateway,
            max_attempts=0,
        )


def test_negative_backoff_is_rejected():
    gateway = FakeRefundGateway()

    with pytest.raises(ValueError, match="backoff_seconds"):
        ConditionalRefundProcessor(
            gateway=gateway,
            backoff_seconds=-1,
        )
