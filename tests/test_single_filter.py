"""Single-filter support thresholds retain weak candidates for review."""

import pytest

from groove.periods import recommend, settings


def candidate(fold_snr: float, peak_snr: float) -> dict:
    return {
        "file": "synthetic.csv",
        "source_id": "9900000000000000001",
        "series": "o",
        "status": "ok",
        "recommended_series_period_days": 12.7,
        "raw_ls_best_period_days": 12.7,
        "raw_ls_best_power": 0.9,
        "raw_ls_fap": 1e-20,
        "raw_fold_amp_snr": fold_snr,
        "ls_peak_snr": peak_snr,
        "best_to_second_power_ratio": 5.0,
        "best_to_fourth_power_ratio": 8.0,
        "peak_dominance_strong": True,
        "raw_fold_scatter_reduction": 0.8,
    }


@pytest.mark.parametrize(
    "fold,peak,supported",
    [(2.99, 10.0, False), (3.0, 10.0, True), (10.0, 3.99, False), (10.0, 4.0, True), (float("nan"), 10.0, False)],
)
def test_single_filter_thresholds(fold, peak, supported):
    row = recommend.choose_source_recommendations([candidate(fold, peak)]).iloc[0]
    assert row.recommended_period_days == 12.7
    assert row.recommended_period_source == ("o_single_filter" if supported else "o_low_support")
    assert ("single_filter_below_snr_thresholds" in row.warning_flags) is not supported


def test_single_filter_switch(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_SINGLE_FILTER_RECOMMENDATION", False)
    row = recommend.choose_source_recommendations([candidate(10.0, 10.0)]).iloc[0]
    assert row.recommended_period_days == 12.7
    assert row.recommended_period_source == "o_low_support"
    assert "single_filter_recommendation_disabled" in row.warning_flags
