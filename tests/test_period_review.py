"""Review routing must retain coherent dips and independently record warnings."""
import pytest
from groove.periods.classify import classify_series_detection
from groove.periods.files import plot_review_folders
from pathlib import Path


def row(ratio2, ratio4, **overrides):
    return {
        'raw_ls_fap': 1e-23, 'ls_peak_snr': 77.6,
        'raw_fold_amp_snr': 115.3,
        'best_to_second_power_ratio': ratio2,
        'best_to_fourth_power_ratio': ratio4,
        'raw_alias_score': 0.0, **overrides,
    }


@pytest.mark.parametrize('ratio2,ratio4', [
    (1.1860538774, 3.3513179389), (1.2363283087, 3.9026813798),
    (1.2297077621, 4.4425805357), (1.3040030867, 3.3933938600),
])
def test_demo_dips_with_competitive_second_peak_remain_strong(ratio2, ratio4):
    primary, warnings = classify_series_detection(row(ratio2, ratio4))
    assert (primary, warnings) == ('strong', 'none')
    assert plot_review_folders({'secondary_classification': warnings}, primary) == [
        Path('best_per_star'), Path('strong')]


@pytest.mark.parametrize('ratio2,ratio4', [
    (1.0159, 1.0483), (1.0485, 1.1134), (1.4499, 1.5270), (1.1812, 1.4500),
])
def test_competitive_noise_peaks_are_not_promoted(ratio2, ratio4):
    primary, _ = classify_series_detection(row(ratio2, ratio4, raw_ls_fap=0.5))
    assert primary == 'weak_or_ambiguous'


def test_dominance_without_significance_is_not_strong():
    primary, _ = classify_series_detection(row(
        1.2, 3.4, raw_ls_fap=0.5, ls_peak_snr=1.0, raw_fold_amp_snr=1.0))
    assert primary == 'weak_or_ambiguous'


@pytest.mark.parametrize('flags,expected,warning', [
    ({'raw_alias_score': 1.0}, 'alias_possible', 'alias_possible'),
    ({'two_p_supported': True}, 'harmonic_possible', 'harmonic_possible'),
])
def test_dip_strength_does_not_erase_alias_or_harmonic_review(flags, expected, warning):
    assert classify_series_detection(row(1.2, 3.4, **flags)) == (expected, warning)


def test_extended_demo_preserves_baseline_and_has_real_cadence_and_single_filters(tmp_path):
    import pandas as pd
    import numpy as np
    import yaml
    from groove.demo import create
    from groove.cli import build_parser
    create(tmp_path / 'baseline')
    path = create(tmp_path / 'extended', extended=True)
    baseline = tmp_path / 'baseline/raw'
    extended = tmp_path / 'extended/raw'
    for file in baseline.glob('*.csv'):
        assert file.read_bytes() == (extended / file.name).read_bytes()
    truth = pd.read_csv(tmp_path / 'extended/truth.csv', dtype={'source_id': str})
    assert len(truth) == 24 and not truth.source_id.duplicated().any()
    cfg = yaml.safe_load(path.read_text())
    assert cfg['periods']['auto_plot_alias_suspects'] and cfg['periods']['run_bls']
    for kind, band in [('cyan_only', 'c'), ('orange_only', 'o')]:
        gid = truth.loc[truth.injected_shape.eq(kind), 'source_id'].iloc[0]
        frame = pd.read_csv(extended / f'synthetic__GaiaDR3_{gid}.csv')
        assert set(frame.F) == {band}
    gid = truth.loc[truth.injected_shape.eq('nightly_sampling'), 'source_id'].iloc[0]
    frame = pd.read_csv(extended / f'synthetic__GaiaDR3_{gid}.csv')
    assert np.ptp(frame.MJD % 1) < .041
    assert build_parser().parse_args(['demo', 'a', '--extended']).extended
    assert build_parser().parse_args(['demo-check', 'a']).command == 'demo-check'


def test_extended_binary_supports_full_cycle_without_catalogue_hint(tmp_path):
    import pandas as pd
    import yaml
    from groove.demo import create
    from groove import config, pipeline
    path = create(tmp_path / 'binary', extended=True)
    for file in (path.parent / 'raw').glob('*.csv'):
        if '3216489845356186510' not in file.name:
            file.unlink()
    raw = yaml.safe_load(path.read_text())
    raw['clean'].update(make_summary_plots=False, make_reason_plot=False, make_example_plots=False)
    raw['periods'].update(run_bls=False, plot_mode='none',
        auto_plot_alias_suspects=False, auto_plot_harmonic_suspects=False)
    path.write_text(yaml.safe_dump(raw))
    cfg = config.load(path)
    pipeline.run_clean(cfg)
    pipeline.run_select(cfg)
    pipeline.run_periods(cfg)
    table = pd.read_csv(cfg.periods_dir / 'tables/source_period_recommendations.csv')
    assert abs(table.recommended_period_days.iloc[0] / 10.8 - 1) < .001
    assert table.recommendation_label.iloc[0] == 'harmonic_possible'
