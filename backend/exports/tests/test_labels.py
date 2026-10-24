from core.domain import DriftResult, ReopenReason
from exports.labels import DRIFT_RESULT_LABELS, REOPEN_REASON_LABELS


def test_reopen_reasons_and_drift_results_use_the_ui_words() -> None:
    # frontend/src/ui/labels.ts: drift is "Live copy changed" everywhere; results are Unchanged / Changed / Missing.
    assert set(REOPEN_REASON_LABELS) == set(ReopenReason)
    assert set(DRIFT_RESULT_LABELS) == set(DriftResult)
    assert REOPEN_REASON_LABELS[ReopenReason.DRIFT_DETECTED] == "Live copy changed"
    assert REOPEN_REASON_LABELS[ReopenReason.TERMS_CHANGED] == "Offer terms changed"
    assert [DRIFT_RESULT_LABELS[r] for r in DriftResult] == ["Unchanged", "Changed", "Missing"]
