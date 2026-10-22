"""Seeded numerical regressions for adopted periods and their provenance."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from groove.demo import DEMO_SOURCE_ID_BASE, create
from groove.periods import aliases, loading, recommend, settings


@pytest.fixture(autouse=True)
def numerical_settings(monkeypatch):
    monkeypatch.setattr(settings, 'RUN_BLS', False)
    monkeypatch.setattr(settings, 'MAX_PERIOD_DAYS', 30.)
    monkeypatch.setattr(settings, 'LS_SAMPLES_PER_PEAK', 30)


def analyse(frame: pd.DataFrame, band: str = 'o') -> tuple[dict, list, tuple]:
    frame = loading.normalise_columns(frame)
    meta = loading.extract_metadata(frame, Path('synthetic.csv'))
    prepared = loading.prepare_series(frame, band)
    row, peaks, payload = recommend.analyse_one_series(meta, prepared, np.nan)
    return row, peaks, (meta, prepared, row, payload, np.nan)


def wave(period: float, *, double: bool = False, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    time = np.sort(rng.uniform(58000, 58400, 2400))
    angle = 2 * np.pi * time / period
    signal = .5 * np.cos(2 * angle) + .22 * np.cos(angle) if double else .3 * np.sin(angle)
    return pd.DataFrame({'MJD': time, 'm': 14.5 + signal + rng.normal(0, .015, len(time)),
                         'dm': .015, 'F': 'o', 'target_GaiaDR3': str(DEMO_SOURCE_ID_BASE + 1),
                         'RA': 84., 'Dec': -2.5})


def adopt(row: dict, peaks: list, payload: tuple | None = None) -> pd.Series:
    aliases.annotate_aliases_and_choose_series_period([row], peaks, pd.DataFrame())
    if payload is not None:
        aliases.update_post_alias_harmonics([row], peaks, [payload])
    return recommend.choose_source_recommendations([row]).iloc[0]


def test_clean_recovery():
    row, peaks, payload = analyse(wave(12.7))
    result = adopt(row, peaks, payload)
    assert abs(result.recommended_period_days / 12.7 - 1) < .01
    assert result.recommended_period_source == 'o_single_filter'


def test_harmonic_doubling():
    row, peaks, payload = analyse(wave(14.2, double=True))
    result = adopt(row, peaks, payload)
    assert abs(row['raw_ls_best_period_days'] / 7.1 - 1) < .01
    assert row['two_p_supported']
    assert abs(result.recommended_period_days / 14.2 - 1) < .01
    assert result.harmonic_status == '2P_supported_by_odd_even_difference'


def test_no_false_doubling():
    row, peaks, payload = analyse(wave(12.7))
    result = adopt(row, peaks, payload)
    assert not row['two_p_supported']
    assert not row['mh_2p_supported']
    assert abs(result.recommended_period_days / 12.7 - 1) < .01


def test_alias_replacement(tmp_path):
    folder = create(tmp_path / 'alias', extended=True).parent
    frame = pd.read_csv(folder / 'raw' / f'synthetic__GaiaDR3_{DEMO_SOURCE_ID_BASE + 23}.csv')
    row, peaks, payload = analyse(frame)
    result = adopt(row, peaks, payload)
    assert abs(row['raw_ls_best_period_days'] - 1) < .02
    assert row['raw_is_alias_suspect'] and row['alias_correction_applied']
    assert row['alias_corrected_rank'] == 2
    assert abs(result.recommended_period_days / 8.3 - 1) < .01


def test_alias_without_credible_alternative():
    frame = wave(1.)
    row, peaks, payload = analyse(frame)
    assert all(p['power_fraction_of_best'] < .25 for p in peaks[1:])
    result = adopt(row, peaks, payload)
    assert row['raw_is_alias_suspect'] and not row['alias_correction_applied']
    assert result.recommended_period_days == row['raw_ls_best_period_days']
    assert 'alias_warning' in result.warning_flags


@pytest.mark.parametrize('weight,expected', [(.49, False), (.51, True)])
def test_alias_score_agreement(monkeypatch, weight, expected):
    monkeypatch.setattr(settings, 'ALIAS_WEIGHT_UNIVERSAL', weight)
    time = np.arange(1000) * .137
    diagnostic = aliases.alias_diagnostics(1., time, 84., -2.5, pd.DataFrame())
    row = {'file': 's.csv', 'source_id': 'synthetic', 'series': 'o', 'status': 'ok',
           'raw_ls_best_power': .8, 'raw_sampling_window_power': diagnostic['sampling_window_power']}
    peaks = [{**row, 'rank': 1, 'period_days': 1., 'power': .8, 'power_fraction_of_best': 1.}]
    aliases.annotate_aliases_and_choose_series_period([row], peaks, pd.DataFrame())
    assert row['raw_alias_score'] == pytest.approx(diagnostic['alias_score'])
    assert row['raw_is_alias_suspect'] == diagnostic['is_alias_suspect'] == expected


@pytest.mark.parametrize('cyan_period,anchor', [(12.76, 'o'), (25.4, 'shorter')])
def test_cross_filter_arbitration(cyan_period, anchor):
    orange, _, _ = analyse(wave(12.7))
    cyan_frame = wave(cyan_period, seed=43).assign(F='c')
    cyan, _, _ = analyse(cyan_frame, 'c')
    result = recommend.choose_source_recommendations([orange, cyan]).iloc[0]
    expected = orange['recommended_series_period_days'] if anchor == 'o' else min(
        orange['recommended_series_period_days'], cyan['recommended_series_period_days'])
    assert result.recommended_period_source == 'o_c_consensus'
    assert result.photometric_period_days == expected
    assert result.recommended_period_days == expected


def test_multiharmonic_doubling_without_odd_even(monkeypatch):
    monkeypatch.setattr(settings, 'RUN_ODD_EVEN_2P_TEST', False)
    row, peaks, payload = analyse(wave(14.2, double=True))
    result = adopt(row, peaks, payload)
    assert settings.MULTIHARMONIC_NTERMS == 3
    assert not row['two_p_supported'] and row['mh_2p_supported']
    assert result.harmonic_status == '2P_supported_by_multiharmonic'
    assert abs(result.recommended_period_days / 14.2 - 1) < .01
